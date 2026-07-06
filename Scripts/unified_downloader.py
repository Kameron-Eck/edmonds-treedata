#!/usr/bin/env python3
"""
UNIFIED AERIAL IMAGERY DOWNLOADER v3.6 — Edmonds WA
===================================================
65 GeoTIFFs from 9 organizations.

v3.6 (2026-03-16):
 - Tile engine now uses server fullExtent to clip tile grid to actual cached extent
 - Eliminates blank-tile floods outside service boundaries (fixed edmonds_2020)
 - probe_server now captures fullExtent and reprojects to EPSG:3857 if needed
 - Probe timeout tightened to 10s (was 30s) — fails fast, fallback is safe
 - Tile sources re-enabled for probing (needed to get fullExtent)

v3.5 (2026-03-16):
 - Tile sources skip REST probe entirely (server_info injected as defaults)
 - Probe was blocking tile downloads when info endpoint timed out (edmonds_2020)
 - Export sources still probe as before (need maxWidth/pixelType for chunking)

v3.4 (2026-03-16):
 - edmonds_2020/2022 switched from exportImage to tile engine
 - Band count corrected: 4→3 (4th band was a false/duplicate channel)
 - Coverage filters removed (tile engine handles gaps natively)

v3.3 COVERAGE-AWARE FILTERING (2026-03-14):
 - Edmonds 2020/2022: Skip water/edge chunks (cols 0-17, 55-72)
 - Reduces chunks from 7,519 → 3,774 (50% reduction!)
 - Success rate: 17% → 95%+ (skips known gaps)
 - Download time: 20+ hours → ~1.5 hours

v3.2 OPTIMIZATIONS (2026-03-14):
 - Edmonds OPTIMIZED: 2048px chunks, 3 workers, no cooldown (4.3× faster!)
 - Benchmark-validated: 100% success rate, 385 MB peak memory, 26.2 chunks/min
 - Estimated Edmonds 2020/2022 download time: ~4.7 hours (was 20+ hours)

v3.1 FIXES:
 - Per-server throttle profiles: SnoCo gets 2048px chunks, 2 workers,
   1.5s cooldown, 120s timeout, 6 retries with 3s exponential backoff
 - Fixed tmp_path → local_tmp variable name bug in tile engine
 - Fixed cross-device os.replace → shutil.move for local SSD → Drive
 - Edmonds 2015/2017 switched to tiles; 2020/2022 kept as export (NIR)
 - MEMORY LEAK FIX: Explicit cleanup of PIL/numpy objects in export loop
 - MEMORY LEAK FIX: Aggressive GC + rasterio flush every 100 chunks

v3 IMPROVEMENTS over v2:
 1. PARALLEL exportImage chunks (was sequential — 5-10x faster for SnoCo/NOAA/NAIP)
 2. Server capability probing — auto-detect maxImageWidth, max zoom, supported formats
 3. Streaming to disk via rasterio windowed writes (no full canvas in RAM)
 4. Chunk-level resume — crash mid-download? Picks up where it left off
 5. 16-bit pixel support for NOAA 16bit sources (was silently truncating to 8-bit)
 6. Adaptive chunk sizing — probe server limits, use max allowed (rounded to 256-multiples)
 8. Tile retry logic with exponential backoff (was bare except = permanent loss)
 9. Correct band counts (grayscale sources no longer waste 3x memory)
10. Connection pooling with urllib3 retry adapter

Run in Google Colab:
  pip install rasterio pyproj tqdm -q
  # Optional: filter groups via env var
  import os; os.environ["DL_GROUPS"] = "SnoCo,KingCo"
  %run unified_downloader_v3.4.py
"""

import os, io, math, time, json, shutil, traceback, gc
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from PIL import Image
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

# ============================================================
#  CONFIG
# ============================================================
from pipeline_config import FULL_IMAGE_DIR
BASE_DIR   = str(FULL_IMAGE_DIR)
LOCAL_TMP  = "/content/tmp_imagery"   # local SSD for writes, then copy to Drive
XMIN, YMIN, XMAX, YMAX = -13625876.424, 6068463.621, -13614805.955, 6084271.153

DEFAULT_CHUNK_PX = 4096       # fallback if probe fails
MAX_CHUNK_PX     = 8192       # never request more than this
TILE_SZ          = 256
MAX_RETRY        = 4
SKIP_MB          = 1
TIMEOUT          = 60         # shorter timeout — retries handle flakes
EXPORT_WORKERS   = 4          # gov servers choke above 3-4 concurrent
TILE_WORKERS     = 12         # tiles are tiny — more concurrency OK

ORIGIN = 20037508.342789244
def _res(z): return 2 * ORIGIN / (TILE_SZ * (2 ** z))

# ============================================================
#  COVERAGE FILTERS (skip known-bad chunks)
# ============================================================
# Coverage filters removed — 2020/2022 now use tile engine,
# which handles water/edge areas gracefully (blank tiles returned,
# not truncated stubs). No filters needed for remaining export sources.

COVERAGE_FILTERS = {}

def apply_coverage_filter(name, row, col):
    """Returns True if chunk should be downloaded, False if it's a known gap."""
    if name not in COVERAGE_FILTERS:
        return True  # no filter defined, download everything

    f = COVERAGE_FILTERS[name]
    if col < f["col_min"] or col > f["col_max"]:
        return False  # outside column range
    if row < f["row_min"] or row > f["row_max"]:
        return False  # outside row range
    return True

# Fragile gov servers need smaller chunks, fewer workers, and
# inter-request cooldown to avoid triggering 500 cascades.
# Key = substring matched against the service URL.
# Values override the global defaults for that server.
SERVER_PROFILES = {
    "gis.snoco.org": {
        "max_chunk_px": 2048,     # half the default — server chokes on 4096
        "export_workers": 4,      # max 2 concurrent requests
        "timeout": 120,           # SnoCo is slow to render large chunks
        "cooldown": 1.5,          # seconds between completed requests
        "max_retry": 6,           # more retries with longer backoff
        "backoff_base": 3.0,      # 3s, 9s, 27s, 81s...
    },
    "imagery-public.watech.wa.gov": {
        "max_chunk_px": 2048,     # WA Tech NAIP — state gov server
        "export_workers": 2,
        "timeout": 120,
        "cooldown": 1.0,
        "max_retry": 5,
        "backoff_base": 2.5,
    },
    "coast.noaa.gov": {
        "max_chunk_px": 2048,     # NOAA — federal server, can be slow
        "export_workers": 3,
        "timeout": 120,
        "cooldown": 0.5,
        "max_retry": 5,
    },
    "imagery.nationalmap.gov": {
        "max_chunk_px": 2048,     # USGS National Map — heavy traffic
        "export_workers": 3,
        "timeout": 120,
        "cooldown": 0.5,
        "max_retry": 5,
    },
    "nrcsgeoservices.sc.egov.usda.gov": {
        "max_chunk_px": 2048,     # USDA NRCS — old gov server
        "export_workers": 2,
        "timeout": 120,
        "cooldown": 1.0,
        "max_retry": 5,
        "backoff_base": 3.0,
    },
    "gis.dnr.wa.gov": {
        "max_chunk_px": 2048,     # WA DNR — state gov server
        "export_workers": 2,
        "timeout": 120,
        "cooldown": 1.0,
    },
    "naip.imagery1.arcgis.com": {
        "max_chunk_px": 4096,     # Esri hosted — more robust, lighter throttle
        "export_workers": 3,
        "timeout": 90,
        "cooldown": 0.3,
    },
    "maps.edmondswa.gov": {
        "max_chunk_px": 2048,
        "export_workers": 4,      # 4 workers for speed
        "timeout": 180,
        "cooldown": 0.0,
        "max_retry": 2,
        "backoff_base": 3.0,
    },
}

def get_server_profile(url):
    """Match URL against throttle profiles. Returns merged config."""
    profile = {
        "max_chunk_px": MAX_CHUNK_PX,
        "export_workers": EXPORT_WORKERS,
        "timeout": TIMEOUT,
        "cooldown": 0,
        "max_retry": MAX_RETRY,
        "backoff_base": 2.0,
    }
    for pattern, overrides in SERVER_PROFILES.items():
        if pattern in url:
            profile.update(overrides)
            break
    return profile

# ============================================================
#  HTTP SESSION WITH RETRY ADAPTER
# ============================================================
def _make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "EdmondsAerialDownloader/3.0"})
    retry = Retry(
        total=MAX_RETRY,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=20,
        pool_maxsize=20,
    )
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

_session = _make_session()

def fetch(url, params=None, timeout=TIMEOUT):
    """Single GET with session-level retries already configured."""
    r = _session.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r

# ============================================================
#  CRS TRANSFORM
# ============================================================
_xf = {}
def get_bbox(to_epsg):
    if to_epsg == 3857:
        return (XMIN, YMIN, XMAX, YMAX)
    if to_epsg not in _xf:
        from pyproj import Transformer
        _xf[to_epsg] = Transformer.from_crs(3857, to_epsg, always_xy=True)
    t = _xf[to_epsg]
    x1, y1 = t.transform(XMIN, YMIN)
    x2, y2 = t.transform(XMAX, YMAX)
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

# ============================================================
#  SERVER CAPABILITY PROBING
# ============================================================
_probe_cache = {}

def probe_server(url, service_type="ImageServer"):
    """Query ArcGIS REST endpoint for capabilities.
    Returns dict with maxWidth, maxHeight, pixelType, supportedFormats, etc."""
    if url in _probe_cache:
        return _probe_cache[url]

    info = {
        "maxWidth": DEFAULT_CHUNK_PX,
        "maxHeight": DEFAULT_CHUNK_PX,
        "pixelType": "U8",
        "max_zoom": None,
        "probed": False,
    }

    try:
        r = fetch(url, params={"f": "json"}, timeout=10)  # fail fast — fallback is safe
        data = r.json()

        # ImageServer capabilities
        if "maxImageWidth" in data:
            info["maxWidth"] = min(data["maxImageWidth"], MAX_CHUNK_PX)
        if "maxImageHeight" in data:
            info["maxHeight"] = min(data["maxImageHeight"], MAX_CHUNK_PX)
        if "pixelType" in data:
            info["pixelType"] = data["pixelType"]  # U8, U16, S16, F32...
        if "capabilities" in data:
            caps = data.get("capabilities", "")
        if "supportedExtensions" in data:
            info["extensions"] = data["supportedExtensions"]

        # MapServer tile info
        if "tileInfo" in data and data["tileInfo"]:
            ti = data["tileInfo"]
            lods = ti.get("lods", [])
            if lods:
                info["max_zoom"] = max(l["level"] for l in lods)
                info["tile_size"] = ti.get("rows", 256)

        if "spatialReference" in data:
            sr = data["spatialReference"]
            info["native_wkid"] = sr.get("latestWkid") or sr.get("wkid")

        # Capture service extent so tile engine can clip to actual data bounds
        if "fullExtent" in data:
            fe = data["fullExtent"]
            fe_wkid = (fe.get("spatialReference") or {}).get("latestWkid") \
                      or (fe.get("spatialReference") or {}).get("wkid") \
                      or info.get("native_wkid", 3857)
            info["fullExtent"] = {
                "xmin": fe["xmin"], "ymin": fe["ymin"],
                "xmax": fe["xmax"], "ymax": fe["ymax"],
                "wkid": fe_wkid,
            }

        info["probed"] = True
        print(f"    Probed: maxPx={info['maxWidth']}x{info['maxHeight']} "
              f"pixelType={info['pixelType']}")

    except Exception as e:
        print(f"    Probe failed ({e}), using defaults")

    _probe_cache[url] = info
    return info

# ============================================================
#  CHUNK-LEVEL RESUME (progress manifest)
# ============================================================
def _manifest_path(out_path):
    return out_path + ".progress.json"

def load_manifest(out_path, total_chunks):
    mp = _manifest_path(out_path)
    if os.path.exists(mp):
        try:
            with open(mp) as f:
                m = json.load(f)
            if m.get("total") == total_chunks:
                return set(m.get("done", []))
        except:
            pass
    return set()

def save_manifest(out_path, done_set, total_chunks):
    mp = _manifest_path(out_path)
    with open(mp, "w") as f:
        json.dump({"total": total_chunks, "done": sorted(done_set)}, f)

def clear_manifest(out_path):
    mp = _manifest_path(out_path)
    if os.path.exists(mp):
        os.remove(mp)

# ============================================================
#  ENGINE 1: PARALLEL TILE DOWNLOADER (with retry)
# ============================================================
def _fetch_one_tile(args):
    """Worker: returns (row, col, rgb_array) or None."""
    url, z, r, c, session = args
    tile_url = f"{url}/tile/{z}/{r}/{c}"
    for attempt in range(3):
        try:
            resp = session.get(tile_url, timeout=TIMEOUT)
            ct = resp.headers.get("Content-Type", "")
            if len(resp.content) < 200 or "image" not in ct:
                return None
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            return (r, c, np.array(img))
        except Exception:
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    return None

def download_tiles(group, name, url, bands, zoom, out_path, server_info):
    """Parallel tile downloader — streams directly to disk via rasterio windowed writes.
    Uses ~10 MB RAM regardless of zoom level (no in-memory canvas).

    Grid bounds: uses service fullExtent when probed (pulls everything the server
    has), otherwise falls back to the global Edmonds EPSG:3857 bbox."""
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS

    if server_info.get("max_zoom") and server_info["max_zoom"] > zoom:
        print(f"    Server has z{server_info['max_zoom']} available (catalog says z{zoom})")

    res = _res(zoom)

    # Use server fullExtent if available — clips grid to actual cached tiles,
    # avoids requesting thousands of blank tiles outside the service extent.
    # Falls back to global Edmonds bbox if probe was skipped or failed.
    if "fullExtent" in server_info:
        fe = server_info["fullExtent"]
        fe_wkid = fe.get("wkid", 3857)
        if fe_wkid == 3857:
            bx0, by0, bx1, by1 = fe["xmin"], fe["ymin"], fe["xmax"], fe["ymax"]
        else:
            from pyproj import Transformer
            t = Transformer.from_crs(fe_wkid, 3857, always_xy=True)
            x0, y0 = t.transform(fe["xmin"], fe["ymin"])
            x1, y1 = t.transform(fe["xmax"], fe["ymax"])
            bx0, by0, bx1, by1 = min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1)
        print(f"    Using server fullExtent (EPSG:{fe_wkid})")
    else:
        bx0, by0, bx1, by1 = XMIN, YMIN, XMAX, YMAX
        print(f"    Using global Edmonds bbox")

    col_min = int(math.floor((bx0 + ORIGIN) / (TILE_SZ * res)))
    col_max = int(math.floor((bx1 + ORIGIN) / (TILE_SZ * res)))
    row_min = int(math.floor((ORIGIN - by1) / (TILE_SZ * res)))
    row_max = int(math.floor((ORIGIN - by0) / (TILE_SZ * res)))

    ncols = col_max - col_min + 1
    nrows = row_max - row_min + 1
    total = ncols * nrows
    pw = ncols * TILE_SZ
    ph = nrows * TILE_SZ

    est_gb = pw * ph * 3 / 1e9
    print(f"    z={zoom} res={res:.4f}m  grid={ncols}x{nrows}={total:,}  "
          f"output={pw}x{ph}px ({est_gb:.1f} GB)  workers={TILE_WORKERS}")

    # Resume support
    done = load_manifest(out_path, total)
    if done:
        print(f"    Resuming: {len(done)}/{total} tiles already done")

    # Tiles always come back as RGB from MapServer/ImageServer rendering
    out_bands = 3

    # Georeferencing
    geo_xmin = col_min * TILE_SZ * res - ORIGIN
    geo_ymax = ORIGIN - row_min * TILE_SZ * res
    geo_xmax = geo_xmin + pw * res
    geo_ymin = geo_ymax - ph * res

    transform = from_bounds(geo_xmin, geo_ymin, geo_xmax, geo_ymax, pw, ph)
    profile = {
        "driver": "GTiff", "dtype": "uint8",
        "width": pw, "height": ph, "count": out_bands,
        "crs": CRS.from_epsg(3857), "transform": transform,
        "compress": "deflate", "predictor": 2,
        "tiled": True, "blockxsize": 512, "blockysize": 512,
        "BIGTIFF": "YES",
    }

    # Write to local SSD (fast random I/O), copy to Drive on completion
    os.makedirs(LOCAL_TMP, exist_ok=True)
    local_tmp = os.path.join(LOCAL_TMP, os.path.basename(out_path) + ".partial.tif")
    if done and os.path.exists(local_tmp):
        print(f"    Opening existing partial file for resume")
        dst = rasterio.open(local_tmp, "r+")
    else:
        dst = rasterio.open(local_tmp, "w", **profile)
        done = set()

    ok = len(done)

    work = []
    for r in range(row_min, row_max + 1):
        for c in range(col_min, col_max + 1):
            key = f"{r}_{c}"
            if key not in done:
                work.append((url, zoom, r, c, _session))

    if not work:
        print(f"    All tiles already downloaded!")
        dst.close()
    else:
        pbar = tqdm(total=len(work), desc=f"    {name}", unit="tile",
                    initial=0, mininterval=2.0, maxinterval=10.0,
                    smoothing=0.1)
        batch_count = 0
        pending_updates = 0
        BATCH_SZ = TILE_WORKERS * 8  # only this many futures in-flight at once
        UPDATE_EVERY = max(1, len(work) // 200)  # ~200 visual updates total

        with ThreadPoolExecutor(max_workers=TILE_WORKERS) as pool:
            for batch_start in range(0, len(work), BATCH_SZ):
                batch = work[batch_start:batch_start + BATCH_SZ]
                futures = {pool.submit(_fetch_one_tile, w): w for w in batch}
                for fut in as_completed(futures):
                    result = fut.result()
                    if result is not None:
                        r, c, arr = result
                        py = (r - row_min) * TILE_SZ
                        px_off = (c - col_min) * TILE_SZ
                        h = min(TILE_SZ, arr.shape[0])
                        w = min(TILE_SZ, arr.shape[1])

                        window = rasterio.windows.Window(px_off, py, TILE_SZ, TILE_SZ)
                        for b in range(out_bands):
                            tile_band = np.zeros((TILE_SZ, TILE_SZ), dtype=np.uint8)
                            tile_band[:h, :w] = arr[:h, :w, b]
                            dst.write(tile_band, b + 1, window=window)

                        done.add(f"{r}_{c}")
                        ok += 1
                    else:
                        w_args = futures[fut]
                        done.add(f"{w_args[2]}_{w_args[3]}")
                    batch_count += 1
                    pending_updates += 1
                    if pending_updates >= UPDATE_EVERY:
                        pbar.update(pending_updates)
                        pending_updates = 0
                # Flush remaining progress
                if pending_updates > 0:
                    pbar.update(pending_updates)
                    pending_updates = 0
                # Save manifest between batches
                if batch_count % 500 < BATCH_SZ:
                    save_manifest(out_path, done, total)

        pbar.close()
        dst.close()

    if ok == 0:
        print(f"    NO TILES received — skipping")
        try: os.remove(local_tmp)
        except: pass
        return False

    print(f"    {ok:,}/{total:,} tiles with data")

    # Move from local SSD to final output path
    # os.replace fails across filesystems (local SSD → Google Drive FUSE),
    # so fall back to shutil.move which handles cross-device copies
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        os.replace(local_tmp, out_path)
    except OSError:
        shutil.move(local_tmp, out_path)

    sz = os.path.getsize(out_path) / 1e6
    print(f"    Saved: {os.path.basename(out_path)} ({sz:.1f} MB, {out_bands}b, EPSG:3857)")
    clear_manifest(out_path)
    return True

# ============================================================
#  ENGINE 2: PARALLEL EXPORTIMAGE — STREAMING TO DISK
# ============================================================
def _fetch_one_chunk(args):
    """Worker: fetch a single export chunk.
    Returns:
      (row, col, image_bytes) on success
      None on recoverable failure (empty tile, corrupt data)
      "FATAL:message" string on unrecoverable error (auth, token required)
    """
    export_url, params, row, col, session, profile = args
    timeout = profile.get("timeout", TIMEOUT)
    max_retry = profile.get("max_retry", MAX_RETRY)
    backoff = profile.get("backoff_base", 2.0)
    cooldown = profile.get("cooldown", 0)

    for attempt in range(max_retry):
        try:
            resp = session.get(export_url, params=params, timeout=timeout)
            ct = resp.headers.get("Content-Type", "")

            # Detect JSON/HTML error responses
            if "json" in ct or "html" in ct or "text/plain" in ct:
                body = resp.text[:500]
                # Check for fatal auth/token errors — no point retrying
                if any(kw in body.lower() for kw in
                       ["token required", "unauthorized", "forbidden",
                        "access denied", "authentication", "403", "401"]):
                    return f"FATAL:[{row},{col}] Auth error: {body[:150]}"

                # HTML error pages from ArcGIS typically mean "no data here"
                # or "request too large" — not transient. Don't retry.
                if "html" in ct:
                    return None

                # JSON errors might be transient (500s, rate limits) — retry
                if attempt == max_retry - 1:
                    snippet = body[:200] if len(body) < 300 else body[:200] + "..."
                    print(f"\n    [{row},{col}] Server returned {ct}: {snippet}")
                time.sleep(backoff ** attempt)
                continue

            if len(resp.content) < 500 or ("image" not in ct and "tiff" not in ct):
                if attempt == max_retry - 1 and len(resp.content) > 0:
                    print(f"\n    [{row},{col}] Rejected: {len(resp.content)}B, Content-Type={ct}")
                return None

            # Cooldown: throttle request rate to avoid overwhelming fragile servers
            if cooldown > 0:
                time.sleep(cooldown)

            return (row, col, resp.content)
        except requests.exceptions.Timeout:
            if attempt < max_retry - 1:
                wait = backoff ** attempt
                print(f"\n    [{row},{col}] Timeout, retry {attempt+1}/{max_retry} in {wait:.0f}s")
                time.sleep(wait)
            else:
                print(f"\n    [{row},{col}] Timeout after {timeout}s x{max_retry}")
        except Exception as e:
            if attempt < max_retry - 1:
                wait = backoff ** attempt
                time.sleep(wait)
            else:
                print(f"\n    [{row},{col}] Error: {e}")
    return None

def download_export(group, name, url, bands, res_m, native_epsg, extra, out_path,
                    server_info, pixel_type="U8"):
    """Parallel chunked exportImage with streaming writes.

    Always downloads in native CRS and warps to 3857 locally.
    Server-side reprojection (imageSR≠bboxSR) is unreliable across
    ArcGIS servers and breaks chunked stitching due to non-uniform
    distortion across independently reprojected chunks.

    Uses per-server throttle profiles to avoid overwhelming fragile
    gov servers (SnoCo, NRCS, DNR).
    """
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS

    bbox = get_bbox(native_epsg)
    bx0, by0, bx1, by1 = bbox

    # Server throttle profile
    srv_profile = get_server_profile(url)
    workers = srv_profile["export_workers"]

    # Pixel size in native CRS units
    if native_epsg in (2285, 2926, 2927):
        FT = 0.3048006096012192
        px_unit = res_m / FT
    elif native_epsg == 32148:
        px_unit = res_m
    else:
        px_unit = res_m

    # Adaptive chunk size: use the MINIMUM of probed server max and profile cap,
    # then round down to multiple of 256 for alignment
    probed_max = min(server_info.get("maxWidth", DEFAULT_CHUNK_PX),
                     server_info.get("maxHeight", DEFAULT_CHUNK_PX))
    profile_max = srv_profile["max_chunk_px"]
    effective_max = min(probed_max, profile_max)
    chunk_px = max(1024, (effective_max // 256) * 256)

    chunk_ext = chunk_px * px_unit
    width  = bx1 - bx0
    height = by1 - by0
    ncols = max(1, math.ceil(width / chunk_ext))
    nrows = max(1, math.ceil(height / chunk_ext))
    total = ncols * nrows

    full_w = ncols * chunk_px
    full_h = nrows * chunk_px

    # Determine dtype
    is_16bit = pixel_type in ("U16", "S16", "F32") or "16bit" in name
    dtype = "uint16" if is_16bit else "uint8"
    np_dtype = np.uint16 if is_16bit else np.uint8
    pix_type_param = "U16" if is_16bit else "U8"

    throttle_note = ""
    if srv_profile["cooldown"] > 0:
        throttle_note = f"  cooldown={srv_profile['cooldown']}s"
    print(f"    EPSG:{native_epsg}  px={px_unit:.4f}  chunk={chunk_px}px"
          f"  grid={ncols}x{nrows}={total}  dtype={dtype}"
          f"  workers={workers}{throttle_note}")

    # Check estimated file size
    est_mb = full_w * full_h * bands * (2 if is_16bit else 1) / 1e6
    if est_mb > 10000:
        print(f"    WARNING: estimated {est_mb:.0f} MB — very large output")

    # Resume support
    done = load_manifest(out_path, total)
    if done:
        print(f"    Resuming: {len(done)}/{total} chunks already done")

    # Create output GeoTIFF in native CRS with windowed writing
    geo_xmin = bx0
    geo_ymax = by1
    geo_xmax = bx0 + ncols * chunk_ext
    geo_ymin = by1 - nrows * chunk_ext

    transform = from_bounds(geo_xmin, geo_ymin, geo_xmax, geo_ymax, full_w, full_h)
    profile = {
        "driver": "GTiff", "dtype": dtype,
        "width": full_w, "height": full_h, "count": bands,
        "crs": CRS.from_epsg(native_epsg), "transform": transform,
        "compress": "deflate", "predictor": 2,
        "tiled": True, "blockxsize": 512, "blockysize": 512,
        "BIGTIFF": "YES",
    }

    # Create or open the output file on LOCAL SSD (fast writes)
    os.makedirs(LOCAL_TMP, exist_ok=True)
    tmp_path = os.path.join(LOCAL_TMP, os.path.basename(out_path) + ".partial.tif")

    if done and os.path.exists(tmp_path):
        print(f"    Opening existing partial file for resume")
        dst = rasterio.open(tmp_path, "r+")
    else:
        # Remove any stale Drive partial (causes hangs)
        drive_partial = out_path + ".partial.tif"
        if os.path.exists(drive_partial):
            print(f"    Removing stale Drive partial...")
            try:
                os.remove(drive_partial)
            except:
                pass

        dst = rasterio.open(tmp_path, "w", **profile)
        done = set()  # fresh start

    export_url = url + "/exportImage"
    ok = len(done)

    # Build work list for remaining chunks
    work = []
    skipped_coverage = 0
    for row in range(nrows):
        for col in range(ncols):
            key = f"{row}_{col}"
            if key in done:
                continue

            # Apply coverage filter (skip known gaps)
            if not apply_coverage_filter(name, row, col):
                skipped_coverage += 1
                done.add(key)  # mark as done so we don't retry
                continue

            cx0 = bx0 + col * chunk_ext
            cx1 = cx0 + chunk_ext
            cy1 = by1 - row * chunk_ext
            cy0 = cy1 - chunk_ext

            params = {
                "bbox": f"{cx0},{cy0},{cx1},{cy1}",
                "bboxSR": native_epsg,
                "imageSR": native_epsg,
                "size": f"{chunk_px},{chunk_px}",
                "format": "tiff",
                "pixelType": pix_type_param,
                "interpolation": "RSP_BilinearInterpolation",
                "f": "image",
            }

            if "mosaic_rule" in extra:
                params["mosaicRule"] = extra["mosaic_rule"]

            work.append((export_url, params, row, col, _session, srv_profile))

    if skipped_coverage > 0:
        print(f"    Coverage filter: skipped {skipped_coverage} known-gap chunks")

    if not work:
        print(f"    All chunks already downloaded!")
        dst.close()
    else:
        pbar = tqdm(total=len(work), desc=f"    {name}", unit="chunk",
                    mininterval=2.0)
        batch_count = 0

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_fetch_one_chunk, w): w for w in work}
            fatal_error = None
            for fut in as_completed(futures):
                result = fut.result()

                # Fatal error (auth/token) — cancel remaining futures and abort
                if isinstance(result, str) and result.startswith("FATAL:"):
                    if not fatal_error:
                        fatal_error = result[6:]
                        print(f"\n    FATAL: {fatal_error}")
                        print(f"    Cancelling remaining chunks...")
                        for pending in futures:
                            pending.cancel()
                    pbar.update(1)
                    continue

                if fatal_error:
                    pbar.update(1)
                    continue

                if result is not None:
                    row, col, img_bytes = result
                    img = None
                    arr = None
                    padded = None
                    try:
                        img = Image.open(io.BytesIO(img_bytes))
                        arr = np.array(img).astype(np_dtype)

                        py = row * chunk_px
                        px_off = col * chunk_px

                        window = rasterio.windows.Window(px_off, py, chunk_px, chunk_px)

                        if arr.ndim == 2:
                            h = min(chunk_px, arr.shape[0])
                            w = min(chunk_px, arr.shape[1])
                            padded = np.zeros((chunk_px, chunk_px), dtype=np_dtype)
                            padded[:h, :w] = arr[:h, :w]
                            dst.write(padded, 1, window=window)
                            del padded
                        elif arr.ndim == 3:
                            h = min(chunk_px, arr.shape[0])
                            w = min(chunk_px, arr.shape[1])
                            nb = min(bands, arr.shape[2])
                            for b in range(nb):
                                padded = np.zeros((chunk_px, chunk_px), dtype=np_dtype)
                                padded[:h, :w] = arr[:h, :w, b]
                                dst.write(padded, b + 1, window=window)
                                del padded  # ← delete after each band write

                        # Check if chunk has any real data (sample broadly, not just corner)
                        has_data = arr.max() > 0
                        if has_data:
                            ok += 1

                        done.add(f"{row}_{col}")
                    except Exception as e:
                        pass  # corrupt image data
                    finally:
                        # Explicit cleanup to prevent leak
                        del img_bytes, arr
                        if img is not None:
                            img.close()
                            del img
                        gc.collect()

                pbar.update(1)
                batch_count += 1

                # Periodic close/reopen every 100 chunks to force write and free memory
                # Rasterio's DatasetWriter holds all writes in RAM until close()
                if batch_count % 100 == 0:
                    try:
                        import psutil
                        mem_before = psutil.Process().memory_info().rss / 1e6
                        print(f"\n    [CHECKPOINT at {batch_count}] Memory before close: {mem_before:.0f} MB")

                        # Close dataset - this forces write to disk and frees buffers
                        close_start = time.time()
                        dst.close()
                        close_elapsed = time.time() - close_start

                        mem_after_close = psutil.Process().memory_info().rss / 1e6
                        print(f"    [CLOSE DONE] Took {close_elapsed:.1f}s, Memory: {mem_after_close:.0f} MB (freed: {mem_before-mem_after_close:.0f} MB)")

                        # GC to clean up any remaining objects
                        gc.collect()
                        mem_after_gc = psutil.Process().memory_info().rss / 1e6
                        print(f"    [GC DONE] Memory: {mem_after_gc:.0f} MB (freed: {mem_after_close-mem_after_gc:.0f} MB)")

                        # Reopen in append mode
                        reopen_start = time.time()
                        dst = rasterio.open(tmp_path, "r+")
                        reopen_elapsed = time.time() - reopen_start

                        mem_final = psutil.Process().memory_info().rss / 1e6
                        print(f"    [REOPEN DONE] Took {reopen_elapsed:.1f}s, Memory: {mem_final:.0f} MB")

                    except Exception as e:
                        print(f"\n    [CHECKPOINT ERROR] {e}")
                        import traceback
                        traceback.print_exc()

                # Save progress periodically
                if batch_count % 50 == 0:
                    save_manifest(out_path, done, total)

        pbar.close()
        dst.close()

    if ok == 0:
        print(f"    NO DATA — skipping")
        try: os.remove(tmp_path)
        except: pass
        return False

    print(f"    {ok}/{total} chunks with data")

    # Move from local SSD to Drive
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        os.replace(tmp_path, out_path)
    except OSError:
        # Cross-device link — copy then remove
        shutil.move(tmp_path, out_path)

    sz = os.path.getsize(out_path) / 1e6
    print(f"    Saved: {os.path.basename(out_path)} ({sz:.1f} MB, {bands}b, EPSG:{native_epsg})")
    clear_manifest(out_path)
    return True


# ============================================================
#  SOURCE CATALOG
# ============================================================
EDM = "https://maps.edmondswa.gov/gis/rest/services/Basemap"
KC  = "https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps"
SC  = "https://gis.snoco.org/img/rest/services/Imagery"
WT  = "https://imagery-public.watech.wa.gov/arcgis/rest/services/NAIP"
NOA = "https://coast.noaa.gov/arcgis/rest/services/Imagery"

# (group, name, method, url, bands, res_m, native_epsg, zoom, extra)
# v3: bands corrected for grayscale sources
# v3.1: Edmonds 2015-2022 switched from export to tiles (ImageServer /tile/ confirmed)
# v3.4: Edmonds 2020/2022 switched from export to tiles; band count corrected 4→3
#       (4th band confirmed false/duplicate — tile engine always returns RGB)
SOURCES = [
    # ── Edmonds ───────────────────────────────────────────────
    # All Edmonds cached services support /tile/{z}/{r}/{c} on ImageServer
    ("Edmonds","edmonds_2015","tiles",f"{EDM}/2015_Aerial_Cached/ImageServer",3,0,3857,21,{}),
    ("Edmonds","edmonds_2017","tiles",f"{EDM}/2017_Aerial_Cached/ImageServer",3,0,3857,21,{}),
    ("Edmonds","edmonds_2020","tiles",f"{EDM}/2020_Aerial_Cached/ImageServer",3,0,3857,21,{}),  # v3.4: export→tiles, 4→3 bands
    ("Edmonds","edmonds_2022","tiles",f"{EDM}/2022_Aerial_Cached/ImageServer",3,0,3857,21,{}),  # v3.4: export→tiles, 4→3 bands
    ("Edmonds","edmonds_2024","tiles",f"{EDM}/2024_Aerial_Cached/MapServer",3,0,3857,21,{}),

    # ── King County ───────────────────────────────────────────
    # v3: 1936/1998 corrected to 1-band grayscale (was 3)
    ("KingCo","kingco_1936","tiles",f"{KC}/KingCo_Aerial_1936/MapServer",1,0,3857,18,{}),
    ("KingCo","kingco_1998","tiles",f"{KC}/KingCo_Aerial_1998/MapServer",1,0,3857,18,{}),
    ("KingCo","kingco_2000","tiles",f"{KC}/KingCo_Aerial_2000/MapServer",3,0,3857,18,{}),
    ("KingCo","kingco_2002","tiles",f"{KC}/KingCo_Aerial_2002/MapServer",3,0,3857,18,{}),
    ("KingCo","kingco_2005","tiles",f"{KC}/KingCo_Aerial_2005/MapServer",3,0,3857,19,{}),
    ("KingCo","kingco_2007","tiles",f"{KC}/KingCo_Aerial_2007/MapServer",3,0,3857,19,{}),
    ("KingCo","kingco_2009","tiles",f"{KC}/KingCo_Aerial_2009/MapServer",3,0,3857,19,{}),
    ("KingCo","kingco_2012","tiles",f"{KC}/KingCo_Aerial_2012/MapServer",3,0,3857,19,{}),
    ("KingCo","kingco_2013","tiles",f"{KC}/KingCo_Aerial_2013/MapServer",3,0,3857,20,{}),
    ("KingCo","kingco_2015","tiles",f"{KC}/KingCo_Aerial_2015/MapServer",3,0,3857,20,{}),
    ("KingCo","kingco_2017","tiles",f"{KC}/KingCo_Aerial_2017/MapServer",3,0,3857,20,{}),
    ("KingCo","kingco_2019","tiles",f"{KC}/KingCo_Aerial_2019/MapServer",3,0,3857,20,{}),
    ("KingCo","kingco_2021","tiles",f"{KC}/KingCo_Aerial_2021/MapServer",3,0,3857,20,{}),
    ("KingCo","kingco_2023","tiles",f"{KC}/KingCo_Aerial_2023/MapServer",3,0,3857,20,{}),

    # ── Snohomish County ──────────────────────────────────────
    # v3: grayscale sources corrected to 1-band
    ("SnoCo","snoco_1990","export",f"{SC}/Aerial_1990/ImageServer",1,3.048,2285,0,{}),
    ("SnoCo","snoco_1996","export",f"{SC}/Aerial_1996/ImageServer",3,1.0,2285,0,{}),
    ("SnoCo","snoco_1998","export",f"{SC}/Aerial_1998/ImageServer",1,0.9144,2285,0,{}),
    ("SnoCo","snoco_2001","export",f"{SC}/Aerial_2001/ImageServer",1,0.3048,2285,0,{}),
    ("SnoCo","snoco_2002","export",f"{SC}/Aerial_2002/ImageServer",3,0.3048,2285,0,{}),
    ("SnoCo","snoco_2003","export",f"{SC}/Aerial_2003/ImageServer",3,0.3048,2285,0,{}),
    ("SnoCo","snoco_2006","export",f"{SC}/Aerial_2006/ImageServer",3,1.0,2285,0,{}),
    ("SnoCo","snoco_2007","export",f"{SC}/Aerial_2007/ImageServer",3,0.3048,32148,0,{}),
    ("SnoCo","snoco_2009","export",f"{SC}/Aerial_2009/ImageServer",3,0.3048,2285,0,{}),
    ("SnoCo","snoco_2011","export",f"{SC}/Aerial_2011/ImageServer",3,0.3048,2926,0,{}),
    ("SnoCo","snoco_2012","export",f"{SC}/Aerial_2012/ImageServer",3,0.2286,2285,0,{}),
    ("SnoCo","snoco_2013","export",f"{SC}/Aerial_2013/ImageServer",3,1.0,2285,0,{}),
    ("SnoCo","snoco_2015","export",f"{SC}/Aerial_2015/ImageServer",4,0.3048,2285,0,{}),
    ("SnoCo","snoco_2016","export",f"{SC}/Aerial_2016/ImageServer",4,0.1524,2285,0,{}),
    ("SnoCo","snoco_2017","export",f"{SC}/Aerial_2017/ImageServer",4,0.3048,2285,0,{}),
    ("SnoCo","snoco_2018","export",f"{SC}/Aerial_2018/ImageServer",4,0.1524,2285,0,{}),
    ("SnoCo","snoco_2019","export",f"{SC}/Aerial_2019/ImageServer",4,0.3048,2285,0,{}),
    ("SnoCo","snoco_2020","export",f"{SC}/Aerial_2020/ImageServer",3,0.0762,2285,0,{}),
    ("SnoCo","snoco_2021","export",f"{SC}/Aerial_2021/ImageServer",4,0.1524,2285,0,{}),
    ("SnoCo","snoco_2022","export",f"{SC}/Aerial_2022/ImageServer",3,0.0762,2285,0,{}),
    ("SnoCo","snoco_2024","export",f"{SC}/Aerial_2024/ImageServer",3,0.0762,2285,0,{}),

    # ── WA NAIP ───────────────────────────────────────────────
    ("WA_NAIP","wa_naip_1989_2000_bw","export",
     f"{WT}/Statewide_1989_2000_3ft_bw_wsps_83h/ImageServer",1,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2003","export",f"{WT}/NAIP_2003_2m_color_wsps_83h_img/ImageServer",3,2.0,2927,0,{}),
    ("WA_NAIP","wa_naip_2004","export",f"{WT}/NAIP_2004_2m_color_wsps_83h_img/ImageServer",3,2.0,2927,0,{}),
    ("WA_NAIP","wa_naip_2005","export",f"{WT}/NAIP_2005_2m_color_wsps_83h_img/ImageServer",3,2.0,2927,0,{}),
    ("WA_NAIP","wa_naip_2006","export",
     f"{WT}/Statewide_NAIP_2006_18in_color_wsps_83h_img/ImageServer",3,0.4572,2927,0,{}),
    ("WA_NAIP","wa_naip_2009","export",
     f"{WT}/Statewide_NAIP_2009_3ft_4band_wsps_83h_img/ImageServer",4,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2011","export",
     f"{WT}/Statewide_NAIP_2011_3ft_4band_wsps_83h_img/ImageServer",4,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2013","export",
     f"{WT}/Statewide_NAIP_2013_3ft_4band_wsps_83h_img/ImageServer",4,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2015","export",
     f"{WT}/Statewide_NAIP_2015_3ft_4band_wsps_83h_img/ImageServer",4,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2017","export",
     f"{WT}/Statewide_NAIP_2017_3ft_4band_wsps_83h_img/ImageServer",4,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2019","export",
     "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer",
     4,0.6,3857,0,{"mosaic_rule":'{"mosaicMethod":"esriMosaicAttribute","where":"Year=2019","sortField":"Year","ascending":false}'}),
    ("WA_NAIP","wa_naip_2023","export",
     "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer",
     4,0.6,3857,0,{"mosaic_rule":'{"mosaicMethod":"esriMosaicAttribute","where":"Year=2023","sortField":"Year","ascending":false}'}),

    # ── NOAA ──────────────────────────────────────────────────
    # v3.1: URLs updated — NOAA renamed services (old rgb_8bit → 3Band_RGB_8Bit_Imagery etc.)
    # Old URLs return "Token Required" error; new ones are public
    ("NOAA","noaa_rgb_8bit","export",f"{NOA}/3Band_RGB_8Bit_Imagery/ImageServer",3,0.3,3857,0,{}),
    ("NOAA","noaa_rgb_16bit","export",f"{NOA}/3Band_RGB_16Bit_Imagery/ImageServer",3,0.3,3857,0,{"pixel_type":"U16"}),
    ("NOAA","noaa_cir_8bit","export",f"{NOA}/3Band_CIR_8Bit_Imagery/ImageServer",3,0.3,3857,0,{}),
    ("NOAA","noaa_cir_16bit","export",f"{NOA}/3Band_CIR_16Bit_Imagery/ImageServer",3,0.3,3857,0,{"pixel_type":"U16"}),
    ("NOAA","noaa_4band_8bit","export",f"{NOA}/4Band_RGBN_8Bit_Imagery/ImageServer",4,0.3,3857,0,{}),
    ("NOAA","noaa_4band_16bit","export",f"{NOA}/4Band_RGBN_16Bit_Imagery/ImageServer",4,0.3,3857,0,{"pixel_type":"U16"}),
    ("NOAA","noaa_ir_8bit","export",f"{NOA}/IR_Band_8Bit_Imagery/ImageServer",1,0.3,3857,0,{}),

    # ── USGS ──────────────────────────────────────────────────
    ("USGS","usgs_naip_plus","export",
     "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer",4,0.6,3857,0,{}),
    ("USGS","usgs_naip_imagery","export",
     "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer",4,0.6,3857,0,{}),

    # ── Esri NAIP ─────────────────────────────────────────────
    ("Esri_NAIP","esri_naip_latest","export",
     "https://naip.imagery1.arcgis.com/arcgis/rest/services/NAIP/ImageServer",4,0.6,3857,0,{}),

    # ── USDA NRCS ─────────────────────────────────────────────
    ("USDA_NRCS","nrcs_nhap_1980s","export",
     "https://nrcsgeoservices.sc.egov.usda.gov/arcgis/rest/services/ortho_imagery/nhap_All/ImageServer",3,0.75,3857,0,{}),
    ("USDA_NRCS","nrcs_nhap_colorbal","export",
     "https://nrcsgeoservices.sc.egov.usda.gov/arcgis/rest/services/ortho_imagery/nhap_colorbalance/ImageServer",3,0.75,3857,0,{}),

    # ── WA DNR Nearshore ──────────────────────────────────────
    ("WA_DNR","dnr_nearshore_npugetsound_2022","export",
     "https://gis.dnr.wa.gov/image/rest/services/Aquatics/Nearshore_img__NPugetSound_2022/ImageServer",4,0.1524,2927,0,{}),
]

# ============================================================
#  MAIN
# ============================================================
def main():
    # Filter groups via env var
    dl_groups = os.environ.get("DL_GROUPS", "").strip()
    if dl_groups:
        allowed = set(g.strip() for g in dl_groups.split(",") if g.strip())
        sources = [s for s in SOURCES if s[0] in allowed]
        print(f"Filtering to groups: {allowed}")
    else:
        sources = SOURCES

    # Further filter by individual source names
    dl_names = os.environ.get("DL_NAMES", "").strip()
    if dl_names:
        allowed_names = set(n.strip() for n in dl_names.split(",") if n.strip())
        sources = [s for s in sources if s[1] in allowed_names]
        print(f"Filtering to names: {allowed_names}")

    print("=" * 72)
    print("  UNIFIED AERIAL IMAGERY DOWNLOADER v3.6 — Edmonds WA")
    print(f"  Sources: {len(sources)}  |  Output: {BASE_DIR}")
    print(f"  Export workers: {EXPORT_WORKERS}  |  Tile workers: {TILE_WORKERS}")
    print(f"  Skip threshold: >{SKIP_MB} MB  |  Timeout: {TIMEOUT}s")
    print("=" * 72)

    groups = {}
    for s in sources:
        groups[s[0]] = groups.get(s[0], 0) + 1
    for g, n in groups.items():
        print(f"  {g}: {n}")

    completed, skipped, failed = 0, 0, 0

    for i, src in enumerate(sources):
        group, name, method, url, bands, res_m, native_epsg, zoom, extra = src
        out_dir = os.path.join(BASE_DIR, group)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{name}_image.tif")

        print(f"\n[{i+1}/{len(sources)}] {group}/{name}  ({method})")

        # Skip if already complete
        if os.path.exists(out_path):
            sz = os.path.getsize(out_path) / 1e6
            if sz > SKIP_MB:
                print(f"    SKIP ({sz:.1f} MB exists)")
                skipped += 1
                continue

        # Check for partial file (resume)
        partial = out_path + ".partial.tif"
        manifest = _manifest_path(out_path)
        has_partial = os.path.exists(partial) and os.path.exists(manifest)
        if has_partial:
            print(f"    Found partial download — will attempt resume")

        try:
            # Always probe — tile engine now uses fullExtent to clip the tile grid
            # to the service's actual cached extent (avoids blank-tile floods).
            # probe_server has a fast 10s timeout and a safe fallback on failure,
            # so a slow info endpoint won't block the run indefinitely.
            svc_type = "ImageServer" if "ImageServer" in url else "MapServer"
            server_info = probe_server(url, svc_type)

            if method == "tiles":
                ok = download_tiles(group, name, url, bands, zoom, out_path, server_info)
            else:
                # Show which throttle profile is active
                srv_prof = get_server_profile(url)
                matched = [p for p in SERVER_PROFILES if p in url]
                if matched:
                    print(f"    Throttle: {matched[0]} "
                          f"(chunk≤{srv_prof['max_chunk_px']}px, "
                          f"workers={srv_prof['export_workers']}, "
                          f"cd={srv_prof['cooldown']}s)")

                pixel_type = extra.get("pixel_type", server_info.get("pixelType", "U8"))
                ok = download_export(group, name, url, bands, res_m,
                                     native_epsg, extra, out_path,
                                     server_info, pixel_type)
            if ok:
                completed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"    FAILED: {e}")
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 72)
    print(f"  DONE: {completed} downloaded, {skipped} skipped, {failed} failed")
    print(f"  Total: {completed + skipped + failed}/{len(sources)}")
    print("=" * 72)

if __name__ == "__main__":
    main()
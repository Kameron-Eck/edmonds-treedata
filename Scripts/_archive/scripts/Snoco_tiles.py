"""
Snohomish County Aerial Imagery Downloader — Edmonds extent
Downloads all available years from gis.snoco.org/img/rest/services/Imagery
using the exportImage endpoint, and saves each as a georeferenced GeoTIFF.

All SnoCo services are ImageServer with exportImage support.  The script
requests TIFF chunks in EPSG:3857 (server reprojects on the fly) and
stitches them into a single GeoTIFF per year.

Output files: snoco_{year}_image.tif

Usage:
    Set YEARS_TO_DOWNLOAD to the years you want, then run.
    Years already present in OUTPUT_DIR are skipped automatically.
"""

import os
import io
import math
import time
import json
import shutil
import requests
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image
from tqdm import tqdm

# ── Configuration ─────────────────────────────────────────────────────────────

YEARS_TO_DOWNLOAD = [
    1990, 1996, 1998, 2001, 2002, 2003, 2006, 2007, 2009, 2011,
    2012, 2013, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2024,
]

from pipeline_config import FULL_IMAGE_DIR
OUTPUT_DIR  = str(FULL_IMAGE_DIR / "SnoCo" / "v2")
MAX_WORKERS = 6
DELAY_SEC   = 0.05
TIMEOUT     = 120
TEMP_DIR    = Path("/tmp/snoco_download")

# exportImage chunk size — server maxImageHeight=4100, maxImageWidth=15000
# We use 4096 as a safe, round ceiling.
CHUNK_PX = 4096

# ── Edmonds bounding box (EPSG:3857, Web Mercator) ───────────────────────────
EXTENT_XMIN = -13625876.424
EXTENT_YMIN =   6068463.621
EXTENT_XMAX = -13614805.955
EXTENT_YMAX =   6084271.153

# ── Service registry ──────────────────────────────────────────────────────────
# All services confirmed from the REST directory.
# 'px_ft' is the native pixel size in US feet (from the server metadata).
# 'bands' is the band count reported by the server.
# The script converts px_ft to a metres-per-pixel resolution for export in 3857.

BASE = "https://gis.snoco.org/img/rest/services/Imagery"

SERVICES = {
    1990: {"url": f"{BASE}/Aerial_1990/ImageServer", "px_ft": 10.0,   "bands": 1},
    1996: {"url": f"{BASE}/Aerial_1996/ImageServer", "px_ft": 3.2808, "bands": 3},
    1998: {"url": f"{BASE}/Aerial_1998/ImageServer", "px_ft": 3.0,    "bands": 1},
    2001: {"url": f"{BASE}/Aerial_2001/ImageServer", "px_ft": 1.0,    "bands": 1},
    2002: {"url": f"{BASE}/Aerial_2002/ImageServer", "px_ft": 1.0,    "bands": 3},
    2003: {"url": f"{BASE}/Aerial_2003/ImageServer", "px_ft": 1.0,    "bands": 3},
    2006: {"url": f"{BASE}/Aerial_2006/ImageServer", "px_ft": 3.2808, "bands": 3},
    2007: {"url": f"{BASE}/Aerial_2007/ImageServer", "px_ft": 1.0,    "bands": 3},
    2009: {"url": f"{BASE}/Aerial_2009/ImageServer", "px_ft": 1.0,    "bands": 3},
    2011: {"url": f"{BASE}/Aerial_2011/ImageServer", "px_ft": 1.0,    "bands": 3},
    2012: {"url": f"{BASE}/Aerial_2012/ImageServer", "px_ft": 0.75,   "bands": 3},
    2013: {"url": f"{BASE}/Aerial_2013/ImageServer", "px_ft": 3.2815, "bands": 3},
    2015: {"url": f"{BASE}/Aerial_2015/ImageServer", "px_ft": 1.0,    "bands": 4},
    2016: {"url": f"{BASE}/Aerial_2016/ImageServer", "px_ft": 0.5,    "bands": 4},
    2017: {"url": f"{BASE}/Aerial_2017/ImageServer", "px_ft": 1.0,    "bands": 4},
    2018: {"url": f"{BASE}/Aerial_2018/ImageServer", "px_ft": 0.5,    "bands": 4},
    2019: {"url": f"{BASE}/Aerial_2019/ImageServer", "px_ft": 1.0,    "bands": 4},
    2020: {"url": f"{BASE}/Aerial_2020/ImageServer", "px_ft": 0.25,   "bands": 3},
    2021: {"url": f"{BASE}/Aerial_2021/ImageServer", "px_ft": 0.5,    "bands": 4},
    2022: {"url": f"{BASE}/Aerial_2022/ImageServer", "px_ft": 0.25,   "bands": 3},
    2024: {"url": f"{BASE}/Aerial_2024/ImageServer", "px_ft": 0.25,   "bands": 3},
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) "
                  "Gecko/20100101 Firefox/148.0",
    "Referer":    "https://scopi.snoco.org/Html5Viewer/Index.html",
    "Accept":     "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
}

# US survey foot → metres
FT_TO_M = 0.3048006096012192


# ── Resolution helpers ────────────────────────────────────────────────────────

def resolution_m(px_ft):
    """Convert a pixel size in US survey feet to approximate metres in Web Mercator
    at the latitude of Edmonds (~47.8°N)."""
    # At lat ~47.8°, the scale factor for Web Mercator is ~1/cos(47.8°) ≈ 1.489
    # But since we're requesting the server to reproject, and the server handles
    # the distortion, we just need a consistent metre value for our chunk math.
    # Use the simple survey-foot conversion:
    return px_ft * FT_TO_M


# ── Chunk builder ─────────────────────────────────────────────────────────────

def build_chunks(res_m):
    """
    Divide the Edmonds extent into CHUNK_PX × CHUNK_PX pixel chunks
    at the given resolution (metres/pixel in EPSG:3857 space).

    Returns list of (chunk_id, xmin, ymin, xmax, ymax, px_w, px_h).
    """
    chunk_m = CHUNK_PX * res_m
    chunks = []
    cid = 0
    y = EXTENT_YMAX
    while y > EXTENT_YMIN:
        y0 = max(y - chunk_m, EXTENT_YMIN)
        x = EXTENT_XMIN
        while x < EXTENT_XMAX:
            x1 = min(x + chunk_m, EXTENT_XMAX)
            pw = round((x1 - x) / res_m)
            ph = round((y - y0) / res_m)
            if pw > 0 and ph > 0:
                chunks.append((cid, x, y0, x1, y, pw, ph))
                cid += 1
            x = x1
        y = y0
    return chunks


# ── Chunk download ────────────────────────────────────────────────────────────

def download_chunk(session, export_url, chunk_id, xmin, ymin, xmax, ymax,
                   px_w, px_h, n_bands, out_dir):
    out_path = out_dir / f"chunk_{chunk_id:06d}.tif"
    if out_path.exists() and out_path.stat().st_size > 1000:
        return chunk_id, xmin, ymin, xmax, ymax, px_w, px_h, "skipped"

    params = {
        "bbox":      f"{xmin},{ymin},{xmax},{ymax}",
        "bboxSR":    3857,
        "imageSR":   3857,
        "size":      f"{px_w},{px_h}",
        "format":    "tiff",
        "pixelType": "U8",
        "f":         "image",
    }
    # Request all bands explicitly for 4-band services
    if n_bands == 4:
        params["bandIds"] = "0,1,2,3"
    elif n_bands == 3:
        params["bandIds"] = "0,1,2"

    try:
        r = session.get(export_url, params=params, timeout=TIMEOUT)
        ct = r.headers.get("Content-Type", "")
        if r.status_code == 200 and ("image" in ct or "tiff" in ct):
            out_path.write_bytes(r.content)
            time.sleep(DELAY_SEC)
            return chunk_id, xmin, ymin, xmax, ymax, px_w, px_h, "ok"
        elif r.status_code == 200 and "json" in ct:
            # Server returned an error JSON instead of an image
            try:
                err = r.json()
                msg = err.get("error", {}).get("message", "unknown")
            except Exception:
                msg = "json_error"
            return chunk_id, xmin, ymin, xmax, ymax, px_w, px_h, f"err_{msg[:40]}"
        else:
            return chunk_id, xmin, ymin, xmax, ymax, px_w, px_h, f"http_{r.status_code}"
    except requests.exceptions.Timeout:
        return chunk_id, xmin, ymin, xmax, ymax, px_w, px_h, "timeout"
    except Exception as e:
        return chunk_id, xmin, ymin, xmax, ymax, px_w, px_h, f"error_{str(e)[:40]}"


def retry_failed(session, export_url, failed_chunks, n_bands, out_dir, max_retries=3):
    """Retry failed chunks with exponential backoff."""
    remaining = list(failed_chunks)
    for attempt in range(1, max_retries + 1):
        if not remaining:
            break
        print(f"  Retry {attempt}/{max_retries}: {len(remaining)} chunks...")
        time.sleep(2 ** attempt)
        still_failed = []
        for cid, x0, y0, x1, y1, pw, ph in remaining:
            result = download_chunk(session, export_url, cid, x0, y0, x1, y1,
                                    pw, ph, n_bands, out_dir)
            if result[-1] not in ("ok", "skipped"):
                still_failed.append((cid, x0, y0, x1, y1, pw, ph))
        remaining = still_failed
    return len(remaining)


# ── Stitch chunks into GeoTIFF ────────────────────────────────────────────────

def stitch_chunks(chunks, res_m, n_bands, output_path):
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS

    total_w = round((EXTENT_XMAX - EXTENT_XMIN) / res_m)
    total_h = round((EXTENT_YMAX - EXTENT_YMIN) / res_m)

    print(f"  Stitching {len(chunks):,} chunks -> {total_w:,} x {total_h:,} px  ({n_bands} bands)")
    print(f"  Estimated uncompressed: ~{total_w * total_h * n_bands / 1e9:.2f} GB")

    transform = from_bounds(EXTENT_XMIN, EXTENT_YMIN, EXTENT_XMAX, EXTENT_YMAX,
                            total_w, total_h)
    crs = CRS.from_epsg(3857)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(
        out_path, "w",
        driver="GTiff", height=total_h, width=total_w,
        count=n_bands, dtype="uint8", crs=crs, transform=transform,
        compress="deflate", predictor=2,
        tiled=True, blockxsize=512, blockysize=512, BIGTIFF="YES",
    ) as dst:
        with tqdm(total=len(chunks), unit="chunk", desc="  Stitching",
                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} chunks "
                             "[{elapsed}<{remaining}]") as pbar:
            for cid, bx0, by0, bx1, by1, pw, ph in chunks:
                chunk_path = TEMP_DIR / f"chunk_{cid:06d}.tif"
                if not chunk_path.exists() or chunk_path.stat().st_size < 1000:
                    pbar.update(1)
                    continue
                try:
                    with rasterio.open(chunk_path) as src:
                        arr = src.read()  # (bands, h, w)
                except Exception as e:
                    print(f"  WARN: chunk {cid}: {e}")
                    pbar.update(1)
                    continue

                # Pad or trim bands
                if arr.shape[0] < n_bands:
                    pad = np.zeros((n_bands - arr.shape[0], arr.shape[1], arr.shape[2]),
                                   dtype=arr.dtype)
                    arr = np.concatenate([arr, pad], axis=0)
                arr = arr[:n_bands]

                col_off = round((bx0 - EXTENT_XMIN) / res_m)
                row_off = round((EXTENT_YMAX - by1) / res_m)

                window = rasterio.windows.Window(col_off, row_off, pw, ph)
                # Clamp to actual array dims in case of rounding
                arr = arr[:, :ph, :pw]
                dst.write(arr, window=window)
                pbar.update(1)

    size_gb = out_path.stat().st_size / 1e9
    print(f"  Saved: {out_path.name}  ({size_gb:.2f} GB,  {n_bands} bands)")


# ── Pre-flight: probe the service to confirm band count and check coverage ────

def probe_service(session, base_url):
    """Fetch service JSON to confirm band count and pixel size."""
    try:
        r = session.get(f"{base_url}?f=json", timeout=30)
        if r.status_code == 200:
            info = r.json()
            bands = info.get("bandCount", None)
            px_x  = info.get("pixelSizeX", None)
            px_y  = info.get("pixelSizeY", None)
            stype = info.get("serviceDataType", "")
            return {"bands": bands, "px_x": px_x, "px_y": px_y, "type": stype}
    except Exception:
        pass
    return None


# ── Per-year download pipeline ─────────────────────────────────────────────────

def run_year(year, svc, output_path):
    base_url   = svc["url"]
    export_url = f"{base_url}/exportImage"
    n_bands    = svc["bands"]
    px_ft      = svc["px_ft"]
    res_m      = resolution_m(px_ft)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    with requests.Session() as session:
        session.headers.update(BROWSER_HEADERS)

        # Probe service
        print(f"  Probing service...")
        info = probe_service(session, base_url)
        if info and info["bands"]:
            if info["bands"] != n_bands:
                print(f"  NOTE: Server reports {info['bands']} bands (expected {n_bands}), using server value.")
                n_bands = info["bands"]

        # Build chunks
        chunks = build_chunks(res_m)
        total  = len(chunks)
        total_w = round((EXTENT_XMAX - EXTENT_XMIN) / res_m)
        total_h = round((EXTENT_YMAX - EXTENT_YMIN) / res_m)

        print(f"  Resolution: {res_m:.4f} m/px  ({px_ft} ft/px)")
        print(f"  Output size: {total_w:,} x {total_h:,} px  ({n_bands} bands)")
        print(f"  Chunks: {total:,}  ({CHUNK_PX}x{CHUNK_PX} px each)")
        print(f"  Downloading...")

        # Download chunks
        ok = skipped = errors = 0
        failed_list = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(download_chunk, session, export_url,
                                cid, x0, y0, x1, y1, pw, ph, n_bands, TEMP_DIR): cid
                for cid, x0, y0, x1, y1, pw, ph in chunks
            }
            with tqdm(total=total, unit="chunk",
                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} "
                                 "[{elapsed}<{remaining}, {rate_fmt}]") as pbar:
                for future in as_completed(futures):
                    result = future.result()
                    cid_r, x0, y0, x1, y1, pw, ph, status = result
                    if status == "ok":
                        ok += 1
                    elif status == "skipped":
                        skipped += 1
                    else:
                        errors += 1
                        failed_list.append((cid_r, x0, y0, x1, y1, pw, ph))
                    pbar.set_postfix(ok=ok, skip=skipped, err=errors)
                    pbar.update(1)

        print(f"  First pass: {ok + skipped:,} ready, {errors:,} failed.")

        # Retry failures
        if failed_list:
            still_bad = retry_failed(session, export_url, failed_list,
                                     n_bands, TEMP_DIR)
            if still_bad:
                print(f"  WARNING: {still_bad} chunks still failed after retries.")
            else:
                print(f"  All retries succeeded.")

    # Stitch
    stitch_chunks(chunks, res_m, n_bands, output_path)
    shutil.rmtree(TEMP_DIR)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        from google.colab import drive as _drive
        if not os.path.exists("/content/drive/MyDrive"):
            print("Mounting Google Drive...")
            _drive.mount("/content/drive")
    except ImportError:
        pass

    print("Snohomish County Aerial Imagery Downloader (Edmonds extent)")
    print(f"Years: {YEARS_TO_DOWNLOAD}")
    print(f"Extent (EPSG:3857): [{EXTENT_XMIN}, {EXTENT_YMIN}] "
          f"to [{EXTENT_XMAX}, {EXTENT_YMAX}]")
    print(f"Output: {OUTPUT_DIR}")

    # Print size estimates
    print(f"\n{'Year':>6}  {'Px (ft)':>8}  {'Res (m)':>8}  {'Bands':>5}  "
          f"{'Width':>8}  {'Height':>8}  {'Chunks':>7}  {'~Raw GB':>8}")
    print("-" * 75)
    for year in YEARS_TO_DOWNLOAD:
        if year not in SERVICES:
            continue
        svc   = SERVICES[year]
        res   = resolution_m(svc["px_ft"])
        w     = round((EXTENT_XMAX - EXTENT_XMIN) / res)
        h     = round((EXTENT_YMAX - EXTENT_YMIN) / res)
        nc    = len(build_chunks(res))
        raw   = w * h * svc["bands"] / 1e9
        print(f"{year:>6}  {svc['px_ft']:>8.2f}  {res:>8.4f}  {svc['bands']:>5}  "
              f"{w:>8,}  {h:>8,}  {nc:>7,}  {raw:>8.1f}")
    print()

    for year in YEARS_TO_DOWNLOAD:
        if year not in SERVICES:
            print(f"WARN: No service registered for {year} — skipping.")
            continue

        svc = SERVICES[year]
        output_path = Path(OUTPUT_DIR) / f"snoco_{year}_image.tif"

        print(f"\n{'='*65}")
        print(f"  {year}  ({svc['bands']}-band,  {svc['px_ft']} ft/px)")
        print(f"  {svc['url']}")
        print(f"{'='*65}")

        if output_path.exists():
            print(f"  Already exists — skipping.")
            continue

        try:
            run_year(year, svc, output_path)
        except Exception as e:
            print(f"  ERROR on {year}: {e}")
            import traceback
            traceback.print_exc()
            if TEMP_DIR.exists():
                shutil.rmtree(TEMP_DIR)

    print(f"\nAll done.")


if __name__ == "__main__":
    main()
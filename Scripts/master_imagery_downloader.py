"""
Master Aerial Imagery Downloader — All Sources, Edmonds Extent
===============================================================
Downloads aerial imagery from every cataloged source and saves each as a
georeferenced GeoTIFF, organized into folders by source organization.

Output structure:
  {BASE_DIR}/
    Edmonds/          {year}_coe_rgb.tif
    KingCo/           kingco_{year}_image.tif
    SnoCo/            snoco_{year}_image.tif
    WA_NAIP/          wa_naip_{year}_image.tif
    NOAA/             noaa_{name}_image.tif
    USGS/             usgs_{name}_image.tif
    Esri_NAIP/        esri_naip_{year}_image.tif
    USDA_NRCS/        nrcs_{name}_image.tif

Download methods:
  - exportImage: For ImageServer services (most sources)
  - tiles:       For MapServer tile caches (King County)

Usage:
    Edit GROUPS_TO_DOWNLOAD to select which org groups to process.
    Files already present are skipped automatically.
    Run in Google Colab with Drive mounted.
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

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

from pipeline_config import FULL_IMAGE_DIR
BASE_DIR = str(FULL_IMAGE_DIR)

# Which groups to download — comment out any you want to skip
GROUPS_TO_DOWNLOAD = [
    # "Edmonds",       # Already handled by existing script
    # "KingCo",        # Already handled by existing script
    # "SnoCo",         # Already handled by existing script
    "WA_NAIP",
    "NOAA",
    "USGS",
    "Esri_NAIP",
    "USDA_NRCS",
]

MAX_WORKERS = 6
DELAY_SEC   = 0.05
TIMEOUT     = 120
CHUNK_PX    = 4096
TEMP_BASE   = Path("/tmp/imagery_download")

# ── Edmonds bounding box (EPSG:3857) ─────────────────────────────────────────
EXTENT_XMIN = -13625876.424
EXTENT_YMIN =   6068463.621
EXTENT_XMAX = -13614805.955
EXTENT_YMAX =   6084271.153

EARTH = 20037508.342789244
FT_TO_M = 0.3048006096012192

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) "
                  "Gecko/20100101 Firefox/148.0",
    "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
}

# ══════════════════════════════════════════════════════════════════════════════
# SERVICE REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
# Each entry: {
#   "file":     output filename (without .tif),
#   "url":      service base URL,
#   "method":   "export" or "tiles",
#   "res_m":    resolution in metres/pixel for export method,
#   "bands":    expected band count,
#   ... (tiles-specific fields: "zoom_hint")
# }

WT = "https://imagery-public.watech.wa.gov/arcgis/rest/services/NAIP"
NC = "https://coast.noaa.gov/arcgis/rest/services/Imagery"
NM = "https://imagery.nationalmap.gov/arcgis/rest/services"
NRCS = "https://nrcsgeoservices.sc.egov.usda.gov/arcgis/rest/services/ortho_imagery"

SERVICES = {
    # ── WA State NAIP (WaTech) ────────────────────────────────────────────
    "WA_NAIP": [
        {"file": "wa_naip_2003", "url": f"{WT}/NAIP_2003_2m_color_wsps_83h_img/ImageServer",
         "method": "export", "res_m": 2.0, "bands": 3},
        {"file": "wa_naip_2004", "url": f"{WT}/NAIP_2004_2m_color_wsps_83h_img/ImageServer",
         "method": "export", "res_m": 2.0, "bands": 3},
        {"file": "wa_naip_2005", "url": f"{WT}/NAIP_2005_2m_color_wsps_83h_img/ImageServer",
         "method": "export", "res_m": 2.0, "bands": 3},
        {"file": "wa_naip_2006", "url": f"{WT}/Statewide_NAIP_2006_18in_color_wsps_83h_img/ImageServer",
         "method": "export", "res_m": 0.4572, "bands": 3},
        {"file": "wa_naip_2009", "url": f"{WT}/Statewide_NAIP_2009_3ft_4band_wsps_83h_img/ImageServer",
         "method": "export", "res_m": 0.9144, "bands": 4},
        {"file": "wa_naip_2011", "url": f"{WT}/Statewide_NAIP_2011_3ft_4band_wsps_83h_img/ImageServer",
         "method": "export", "res_m": 0.9144, "bands": 4},
        {"file": "wa_naip_2013", "url": f"{WT}/Statewide_NAIP_2013_3ft_4band_wsps_83h_img/ImageServer",
         "method": "export", "res_m": 0.9144, "bands": 4},
        {"file": "wa_naip_2015", "url": f"{WT}/Statewide_NAIP_2015_3ft_4band_wsps_83h_img/ImageServer",
         "method": "export", "res_m": 0.9144, "bands": 4},
        {"file": "wa_naip_2017", "url": f"{WT}/Statewide_NAIP_2017_3ft_4band_wsps_83h_img/ImageServer",
         "method": "export", "res_m": 0.9144, "bands": 4},
    ],

    # ── NOAA Digital Coast ────────────────────────────────────────────────
    "NOAA": [
        {"file": "noaa_rgb_8bit",  "url": f"{NC}/3Band_RGB_8Bit_Imagery/ImageServer",
         "method": "export", "res_m": 0.3, "bands": 3},
        {"file": "noaa_rgb_16bit", "url": f"{NC}/3Band_RGB_16Bit_Imagery/ImageServer",
         "method": "export", "res_m": 0.3, "bands": 3},
        {"file": "noaa_cir_8bit",  "url": f"{NC}/3Band_CIR_8Bit_Imagery/ImageServer",
         "method": "export", "res_m": 0.3, "bands": 3},
        {"file": "noaa_cir_16bit", "url": f"{NC}/3Band_CIR_16Bit_Imagery/ImageServer",
         "method": "export", "res_m": 0.3, "bands": 3},
        {"file": "noaa_4band_8bit",  "url": f"{NC}/4Band_RGBN_8Bit_Imagery/ImageServer",
         "method": "export", "res_m": 0.3, "bands": 4},
        {"file": "noaa_4band_16bit", "url": f"{NC}/4Band_RGBN_16Bit_Imagery/ImageServer",
         "method": "export", "res_m": 0.3, "bands": 4},
        {"file": "noaa_ir_8bit", "url": f"{NC}/IR_Band_8Bit_Imagery/ImageServer",
         "method": "export", "res_m": 0.3, "bands": 1},
    ],

    # ── USGS National Map ─────────────────────────────────────────────────
    "USGS": [
        {"file": "usgs_naip_plus", "url": f"{NM}/USGSNAIPPlus/ImageServer",
         "method": "export", "res_m": 0.6, "bands": 4},
        {"file": "usgs_naip_imagery", "url": f"{NM}/USGSNAIPImagery/ImageServer",
         "method": "export", "res_m": 0.6, "bands": 4},
    ],

    # ── Esri NAIP (filterable by year) ────────────────────────────────────
    "Esri_NAIP": [
        {"file": "esri_naip_latest", "url": "https://naip.imagery1.arcgis.com/arcgis/rest/services/NAIP/ImageServer",
         "method": "export", "res_m": 0.6, "bands": 4},
    ],

    # ── USDA NRCS Historic (NHAP 1980s) ───────────────────────────────────
    "USDA_NRCS": [
        {"file": "nrcs_nhap_1980s",  "url": f"{NRCS}/nhap_All/ImageServer",
         "method": "export", "res_m": 0.75, "bands": 3},
        {"file": "nrcs_nhap_colorbal", "url": f"{NRCS}/nhap_colorbalance/ImageServer",
         "method": "export", "res_m": 0.75, "bands": 3},
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT IMAGE ENGINE (for ImageServer services)
# ══════════════════════════════════════════════════════════════════════════════

def build_chunks(res_m):
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


def download_chunk(session, export_url, cid, xmin, ymin, xmax, ymax,
                   pw, ph, n_bands, out_dir):
    out_path = out_dir / f"chunk_{cid:06d}.tif"
    if out_path.exists() and out_path.stat().st_size > 1000:
        return cid, xmin, ymin, xmax, ymax, pw, ph, "skipped"

    params = {
        "bbox":      f"{xmin},{ymin},{xmax},{ymax}",
        "bboxSR":    3857,
        "imageSR":   3857,
        "size":      f"{pw},{ph}",
        "format":    "tiff",
        "pixelType": "U8",
        "f":         "image",
    }
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
            return cid, xmin, ymin, xmax, ymax, pw, ph, "ok"
        elif r.status_code == 200 and "json" in ct:
            try:
                msg = r.json().get("error", {}).get("message", "unknown")
            except Exception:
                msg = "json_error"
            return cid, xmin, ymin, xmax, ymax, pw, ph, f"err_{msg[:40]}"
        else:
            return cid, xmin, ymin, xmax, ymax, pw, ph, f"http_{r.status_code}"
    except requests.exceptions.Timeout:
        return cid, xmin, ymin, xmax, ymax, pw, ph, "timeout"
    except Exception as e:
        return cid, xmin, ymin, xmax, ymax, pw, ph, f"error_{str(e)[:40]}"


def retry_failed(session, export_url, failed, n_bands, out_dir, max_retries=3):
    remaining = list(failed)
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


def stitch_chunks(chunks, res_m, n_bands, output_path, temp_dir):
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS

    total_w = round((EXTENT_XMAX - EXTENT_XMIN) / res_m)
    total_h = round((EXTENT_YMAX - EXTENT_YMIN) / res_m)

    print(f"  Stitching {len(chunks):,} chunks -> {total_w:,} x {total_h:,} px  ({n_bands} bands)")

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
                chunk_path = temp_dir / f"chunk_{cid:06d}.tif"
                if not chunk_path.exists() or chunk_path.stat().st_size < 1000:
                    pbar.update(1)
                    continue
                try:
                    with rasterio.open(chunk_path) as src:
                        arr = src.read()
                except Exception as e:
                    print(f"  WARN: chunk {cid}: {e}")
                    pbar.update(1)
                    continue

                if arr.shape[0] < n_bands:
                    pad = np.zeros((n_bands - arr.shape[0], arr.shape[1], arr.shape[2]),
                                   dtype=arr.dtype)
                    arr = np.concatenate([arr, pad], axis=0)
                arr = arr[:n_bands, :ph, :pw]

                col_off = round((bx0 - EXTENT_XMIN) / res_m)
                row_off = round((EXTENT_YMAX - by1) / res_m)
                window = __import__("rasterio").windows.Window(col_off, row_off, pw, ph)
                dst.write(arr, window=window)
                pbar.update(1)

    size_gb = out_path.stat().st_size / 1e9
    print(f"  Saved: {out_path.name}  ({size_gb:.2f} GB,  {n_bands} bands)")


def probe_service(session, base_url):
    try:
        r = session.get(f"{base_url}?f=json", timeout=30)
        if r.status_code == 200:
            info = r.json()
            return {
                "bands": info.get("bandCount"),
                "px_x":  info.get("pixelSizeX"),
                "px_y":  info.get("pixelSizeY"),
                "type":  info.get("serviceDataType", ""),
            }
    except Exception:
        pass
    return None


def run_export(svc, output_path, temp_dir):
    base_url   = svc["url"]
    export_url = f"{base_url}/exportImage"
    n_bands    = svc["bands"]
    res_m      = svc["res_m"]

    temp_dir.mkdir(parents=True, exist_ok=True)

    with requests.Session() as session:
        session.headers.update(BROWSER_HEADERS)

        print(f"  Probing service...")
        info = probe_service(session, base_url)
        if info and info["bands"]:
            if info["bands"] != n_bands:
                print(f"  NOTE: Server reports {info['bands']} bands (expected {n_bands}), using server value.")
                n_bands = info["bands"]

        chunks = build_chunks(res_m)
        total  = len(chunks)
        total_w = round((EXTENT_XMAX - EXTENT_XMIN) / res_m)
        total_h = round((EXTENT_YMAX - EXTENT_YMIN) / res_m)
        raw_gb  = total_w * total_h * n_bands / 1e9

        print(f"  Resolution: {res_m:.4f} m/px  |  {n_bands} bands")
        print(f"  Output: {total_w:,} x {total_h:,} px  |  ~{raw_gb:.1f} GB raw")
        print(f"  Chunks: {total:,}  |  Downloading...")

        ok = skipped = errors = 0
        failed_list = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(download_chunk, session, export_url,
                                cid, x0, y0, x1, y1, pw, ph, n_bands, temp_dir): cid
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

        if failed_list:
            still_bad = retry_failed(session, export_url, failed_list,
                                     n_bands, temp_dir)
            if still_bad:
                print(f"  WARNING: {still_bad} chunks still failed.")
            else:
                print(f"  All retries succeeded.")

    stitch_chunks(chunks, res_m, n_bands, output_path, temp_dir)
    shutil.rmtree(temp_dir)


# ══════════════════════════════════════════════════════════════════════════════
# TILE DOWNLOAD ENGINE (for MapServer tile caches — King County)
# ══════════════════════════════════════════════════════════════════════════════

def merc_to_tile(x, y, z):
    lon = x / EARTH * 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * y / EARTH)))
    n = 2 ** z
    col = int((lon + 180.0) / 360.0 * n)
    row = int((1.0 - math.log(math.tan(math.radians(lat)) +
              1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n)
    return row, col


def tile_origin_merc(row, col, z):
    n = 2 ** z
    lon = col / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * row / n)))
    lat = math.degrees(lat_rad)
    x = lon / 180.0 * EARTH
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / math.pi * EARTH
    return x, y


def tile_bounds_for_extent(z):
    r_nw, c_nw = merc_to_tile(EXTENT_XMIN, EXTENT_YMAX, z)
    r_se, c_se = merc_to_tile(EXTENT_XMAX, EXTENT_YMIN, z)
    return r_nw, r_se, c_nw, c_se


def detect_max_zoom(session, base_url, zoom_hint):
    try:
        r = session.get(f"{base_url}?f=json", timeout=TIMEOUT)
        if r.status_code == 200:
            info = r.json()
            lods = info.get("tileInfo", {}).get("lods", [])
            if lods:
                return min(max(lod["level"] for lod in lods), 21)
    except Exception:
        pass
    return zoom_hint


def verify_tiles_exist(session, base_url, z, r_min, r_max, c_min, c_max):
    r_mid = (r_min + r_max) // 2
    c_mid = (c_min + c_max) // 2
    try:
        r = session.get(f"{base_url}/tile/{z}/{r_mid}/{c_mid}", timeout=15)
        return r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image")
    except Exception:
        return False


def download_tile(session, base_url, z, row, col, out_dir):
    tile_path = out_dir / f"{row}_{col}.jpg"
    if tile_path.exists():
        return row, col, "skipped"
    try:
        r = session.get(f"{base_url}/tile/{z}/{row}/{col}", timeout=TIMEOUT)
        if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image"):
            tile_path.write_bytes(r.content)
            time.sleep(DELAY_SEC)
            return row, col, "ok"
        elif r.status_code == 404:
            return row, col, "no_tile"
        else:
            return row, col, f"http_{r.status_code}"
    except Exception as e:
        return row, col, f"error_{e}"


def stitch_tiles(tile_dir, z, row_min, row_max, col_min, col_max, output_path):
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS

    tile_size = 256
    n_rows = row_max - row_min + 1
    n_cols = col_max - col_min + 1
    total_w = n_cols * tile_size
    total_h = n_rows * tile_size

    print(f"  Stitching {n_rows:,} x {n_cols:,} tiles -> {total_w:,} x {total_h:,} px")

    x_min, y_max = tile_origin_merc(row_min, col_min, z)
    x_max, y_min = tile_origin_merc(row_max + 1, col_max + 1, z)
    transform = from_bounds(x_min, y_min, x_max, y_max, total_w, total_h)
    crs = CRS.from_epsg(3857)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(
        out_path, "w",
        driver="GTiff", height=total_h, width=total_w,
        count=3, dtype="uint8", crs=crs, transform=transform,
        compress="deflate", predictor=2,
        tiled=True, blockxsize=512, blockysize=512, BIGTIFF="YES",
    ) as dst:
        with tqdm(total=n_rows, unit="row", desc="  Stitching",
                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} rows "
                             "[{elapsed}<{remaining}]") as pbar:
            for row in range(row_min, row_max + 1):
                strip = np.zeros((tile_size, total_w, 3), dtype=np.uint8)
                for col in range(col_min, col_max + 1):
                    tile_path = tile_dir / f"{row}_{col}.jpg"
                    if tile_path.exists():
                        try:
                            arr = np.array(Image.open(tile_path).convert("RGB"))
                            x = (col - col_min) * tile_size
                            strip[:, x:x + tile_size, :] = arr
                        except Exception:
                            pass
                y = (row - row_min) * tile_size
                for b in range(3):
                    dst.write(strip[:, :, b], b + 1,
                              window=rasterio.windows.Window(0, y, total_w, tile_size))
                pbar.update(1)

    size_gb = out_path.stat().st_size / 1e9
    print(f"  Saved: {out_path.name}  ({size_gb:.2f} GB,  3 bands)")


def run_tiles(svc, output_path, temp_dir):
    base_url = svc["url"]
    zoom_hint = svc.get("zoom_hint", 20)

    temp_dir.mkdir(parents=True, exist_ok=True)

    with requests.Session() as session:
        session.headers.update(BROWSER_HEADERS)

        print(f"  Probing tile info...")
        zoom = detect_max_zoom(session, base_url, zoom_hint)

        MIN_ZOOM = 17
        while zoom >= MIN_ZOOM:
            row_min, row_max, col_min, col_max = tile_bounds_for_extent(zoom)
            if verify_tiles_exist(session, base_url, zoom,
                                  row_min, row_max, col_min, col_max):
                break
            print(f"  No tiles at zoom {zoom}, trying {zoom - 1}...")
            zoom -= 1
        else:
            print(f"  ERROR: No tiles found!")
            return

        row_min, row_max, col_min, col_max = tile_bounds_for_extent(zoom)
        total_tiles = (row_max - row_min + 1) * (col_max - col_min + 1)
        res_m = 2 * EARTH / (2**zoom * 256)

        print(f"  Zoom: {zoom}  |  Resolution: {res_m:.4f} m/px")
        print(f"  Downloading {total_tiles:,} tiles...")

        tiles = [(r, c) for r in range(row_min, row_max + 1)
                         for c in range(col_min, col_max + 1)]
        ok = skipped = no_tile = errors = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(download_tile, session, base_url,
                                zoom, r, c, temp_dir): (r, c)
                for r, c in tiles
            }
            with tqdm(total=total_tiles, unit="tile",
                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} "
                                 "[{elapsed}<{remaining}, {rate_fmt}]") as pbar:
                for future in as_completed(futures):
                    _, _, status = future.result()
                    if   status == "ok":      ok      += 1
                    elif status == "skipped": skipped += 1
                    elif status == "no_tile": no_tile += 1
                    else:                     errors  += 1
                    pbar.set_postfix(ok=ok, skip=skipped, empty=no_tile, err=errors)
                    pbar.update(1)

        print(f"  Download: {ok + skipped:,} ready, {no_tile:,} empty, {errors:,} errors.")

    stitch_tiles(temp_dir, zoom, row_min, row_max, col_min, col_max, output_path)
    shutil.rmtree(temp_dir)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    try:
        from google.colab import drive as _drive
        if not os.path.exists("/content/drive/MyDrive"):
            print("Mounting Google Drive...")
            _drive.mount("/content/drive")
    except ImportError:
        pass

    print("=" * 70)
    print("  MASTER AERIAL IMAGERY DOWNLOADER — All Sources, Edmonds Extent")
    print("=" * 70)
    print(f"Base: {BASE_DIR}")
    print(f"Groups: {GROUPS_TO_DOWNLOAD}")
    print(f"Extent: [{EXTENT_XMIN}, {EXTENT_YMIN}] to [{EXTENT_XMAX}, {EXTENT_YMAX}]")

    # Print size estimates
    print(f"\n{'Group':<12} {'File':<28} {'Res(m)':>7} {'Bands':>5} "
          f"{'Width':>9} {'Height':>9} {'~Raw GB':>8}")
    print("-" * 85)
    total_raw = 0
    for group in GROUPS_TO_DOWNLOAD:
        if group not in SERVICES:
            continue
        for svc in SERVICES[group]:
            if svc["method"] == "export":
                res = svc["res_m"]
                w = round((EXTENT_XMAX - EXTENT_XMIN) / res)
                h = round((EXTENT_YMAX - EXTENT_YMIN) / res)
                raw = w * h * svc["bands"] / 1e9
                total_raw += raw
                print(f"{group:<12} {svc['file']:<28} {res:>7.3f} {svc['bands']:>5} "
                      f"{w:>9,} {h:>9,} {raw:>8.1f}")
            else:
                print(f"{group:<12} {svc['file']:<28} {'tiles':>7} {svc.get('bands',3):>5} "
                      f"{'(varies)':>9} {'':>9} {'~3-6':>8}")
    print(f"{'':>12} {'TOTAL (export only)':<28} {'':>7} {'':>5} "
          f"{'':>9} {'':>9} {total_raw:>8.1f}")
    print()

    for group in GROUPS_TO_DOWNLOAD:
        if group not in SERVICES:
            print(f"WARN: Unknown group '{group}' — skipping.")
            continue

        group_dir = Path(BASE_DIR) / group
        group_dir.mkdir(parents=True, exist_ok=True)

        for svc in SERVICES[group]:
            output_path = group_dir / f"{svc['file']}_image.tif"
            temp_dir = TEMP_BASE / svc['file']

            print(f"\n{'=' * 65}")
            print(f"  [{group}] {svc['file']}  ({svc['bands']}-band, {svc['method']})")
            print(f"  {svc['url']}")
            print(f"  -> {output_path}")
            print(f"{'=' * 65}")

            if output_path.exists():
                print(f"  Already exists — skipping.")
                continue

            try:
                if svc["method"] == "export":
                    run_export(svc, output_path, temp_dir)
                elif svc["method"] == "tiles":
                    run_tiles(svc, output_path, temp_dir)
                else:
                    print(f"  Unknown method '{svc['method']}' — skipping.")
            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)

    print(f"\n{'=' * 70}")
    print(f"  ALL DONE")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()

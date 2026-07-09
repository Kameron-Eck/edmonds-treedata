"""
Edmonds Aerial Imagery Downloader
Acquires all available years from maps.edmondswa.gov and saves each as a
georeferenced GeoTIFF to Google Drive.

Strategy per year:
  3-band years (2015, 2017, 2024) — cached tile download (zoom 21, JPEG)
  4-band years (2020, 2022)       — exportImage chunks (TIFF, all 4 bands)

All services confirmed from the REST directory. All output files follow the
pipeline naming convention: {year}_{source}_{bands}.tif

Usage:
    Set YEARS_TO_DOWNLOAD to the years you want, then run.
    Years already present in OUTPUT_DIR are skipped automatically.
"""

import os
import io
import math
import time
import shutil
import requests
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image
from tqdm import tqdm

# ── Configuration ─────────────────────────────────────────────────────────────

YEARS_TO_DOWNLOAD = [2015, 2017, 2020, 2022, 2024]

from pipeline_config import IMAGERY_DIR
OUTPUT_DIR  = str(IMAGERY_DIR)
ZOOM_LEVEL  = 21
TILE_SIZE   = 256
MAX_WORKERS = 8
DELAY_SEC   = 0.05
TIMEOUT     = 60
TEMP_DIR    = Path("/tmp/edmonds_download")

# exportImage chunk size in pixels per request — safe ceiling for this server
CHUNK_PX    = 4096
# Resolution for 4-band export (metres/pixel) — matches the cached tile res
RESOLUTION_M = 0.07464553541190416

# ── Service registry ──────────────────────────────────────────────────────────

SERVICES = {
    2015: {
        "method":  "tiles",
        "url":     "https://maps.edmondswa.gov/gis/rest/services/Basemap/2015_Aerial_Cached/ImageServer",
        "bands":   3,
        "row_min": 730126, "row_max": 730993,
        "col_min": 335498, "col_max": 336084,
    },
    2017: {
        "method":  "tiles",
        "url":     "https://maps.edmondswa.gov/gis/rest/services/Basemap/2017_Aerial_Cached/ImageServer",
        "bands":   3,
        "row_min": 730088, "row_max": 730994,
        "col_min": 335462, "col_max": 336191,
    },
    2020: {
        "method":  "export",
        "url":     "https://maps.edmondswa.gov/gis/rest/services/Basemap/2020_Aerial_Cached/ImageServer/exportImage",
        "bands":   4,
        "xmin": -13625876.424, "ymin": 6068463.621,
        "xmax": -13614805.955, "ymax": 6084271.153,
    },
    2022: {
        "method":  "export",
        "url":     "https://maps.edmondswa.gov/gis/rest/services/Basemap/2022_Aerial_Cached/ImageServer/exportImage",
        "bands":   4,
        "xmin": -13625876.424, "ymin": 6068463.621,
        "xmax": -13614805.955, "ymax": 6084271.153,
    },
    2024: {
        "method":  "tiles",
        "url":     "https://maps.edmondswa.gov/gis/rest/services/Basemap/2024_Aerial_Cached/MapServer",
        "bands":   3,
        "row_min": 730182, "row_max": 731009,
        "col_min": 335524, "col_max": 336104,
    },
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    "Referer":    "https://maps.edmondswa.gov/Html5Viewer/?viewer=Edmonds_SSL.HTML",
    "Accept":     "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
}

# ── Coordinate helpers ────────────────────────────────────────────────────────

EARTH = 20037508.342789244


def tile_origin_merc(row, col, level):
    n       = 2 ** level
    lon     = col / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * row / n)))
    lat     = math.degrees(lat_rad)
    x       = lon / 180.0 * EARTH
    y       = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / math.pi * EARTH
    return x, y


# ── Tile download (3-band years) ──────────────────────────────────────────────

def download_tile(session, base_url, level, row, col, out_dir):
    tile_path = out_dir / f"{row}_{col}.jpg"
    if tile_path.exists():
        return row, col, "skipped"
    try:
        r = session.get(f"{base_url}/tile/{level}/{row}/{col}", timeout=TIMEOUT)
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


def stitch_tiles(tile_dir, svc, level, tile_size, output_path):
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS

    row_min = svc["row_min"];  row_max = svc["row_max"]
    col_min = svc["col_min"];  col_max = svc["col_max"]
    n_rows  = row_max - row_min + 1
    n_cols  = col_max - col_min + 1
    total_w = n_cols * tile_size
    total_h = n_rows * tile_size

    print(f"  Stitching {n_rows:,} x {n_cols:,} tiles -> {total_w:,} x {total_h:,} px")
    print(f"  Estimated uncompressed: ~{total_w * total_h * 3 / 1e9:.2f} GB")

    x_min, y_max = tile_origin_merc(row_min,     col_min,     level)
    x_max, y_min = tile_origin_merc(row_max + 1, col_max + 1, level)

    _write_geotiff(output_path, total_w, total_h, 3,
                   from_bounds(x_min, y_min, x_max, y_max, total_w, total_h),
                   CRS.from_epsg(3857),
                   lambda dst: _stitch_tiles_to_dst(
                       dst, tile_dir, row_min, row_max, col_min, col_max, tile_size, n_rows, total_w))


def _stitch_tiles_to_dst(dst, tile_dir, row_min, row_max,
                          col_min, col_max, tile_size, n_rows, total_w):
    import rasterio
    with tqdm(total=n_rows, unit="row", desc="  Stitching",
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} rows [{elapsed}<{remaining}]") as pbar:
        for row in range(row_min, row_max + 1):
            strip = np.zeros((tile_size, total_w, 3), dtype=np.uint8)
            for col in range(col_min, col_max + 1):
                tile_path = tile_dir / f"{row}_{col}.jpg"
                if tile_path.exists():
                    try:
                        arr = np.array(Image.open(tile_path).convert("RGB"))
                        x   = (col - col_min) * tile_size
                        strip[:, x : x + tile_size, :] = arr
                    except Exception as e:
                        print(f"  WARN: tile {row}_{col}: {e}")
            y = (row - row_min) * tile_size
            for b in range(3):
                dst.write(strip[:, :, b], b + 1,
                          window=rasterio.windows.Window(0, y, total_w, tile_size))
            pbar.update(1)


def run_tile_download(year, svc, output_path):
    row_min     = svc["row_min"];  row_max = svc["row_max"]
    col_min     = svc["col_min"];  col_max = svc["col_max"]
    total_tiles = (row_max - row_min + 1) * (col_max - col_min + 1)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    tiles = [(r, c) for r in range(row_min, row_max + 1)
                    for c in range(col_min, col_max + 1)]
    ok = skipped = no_tile = errors = 0

    print(f"  Downloading {total_tiles:,} tiles...")
    with requests.Session() as session:
        session.headers.update(BROWSER_HEADERS)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(download_tile, session, svc["url"],
                                ZOOM_LEVEL, r, c, TEMP_DIR): (r, c)
                for r, c in tiles
            }
            with tqdm(total=total_tiles, unit="tile",
                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]") as pbar:
                for future in as_completed(futures):
                    _, _, status = future.result()
                    if   status == "ok":      ok      += 1
                    elif status == "skipped": skipped += 1
                    elif status == "no_tile": no_tile += 1
                    else:                     errors  += 1
                    pbar.set_postfix(ok=ok, skip=skipped, empty=no_tile, err=errors)
                    pbar.update(1)

    print(f"  Download complete — {ok + skipped:,} tiles ready.")
    stitch_tiles(TEMP_DIR, svc, ZOOM_LEVEL, TILE_SIZE, output_path)
    shutil.rmtree(TEMP_DIR)


# ── exportImage download (4-band years) ───────────────────────────────────────

def build_export_chunks(svc):
    """
    Divide the extent into CHUNK_PX x CHUNK_PX pixel chunks.
    Returns list of (chunk_id, xmin, ymin, xmax, ymax, px_w, px_h).
    """
    xmin = svc["xmin"];  xmax = svc["xmax"]
    ymin = svc["ymin"];  ymax = svc["ymax"]
    chunk_m = CHUNK_PX * RESOLUTION_M

    chunks = []
    cid = 0
    y = ymax
    while y > ymin:
        y0 = max(y - chunk_m, ymin)
        x  = xmin
        while x < xmax:
            x1   = min(x + chunk_m, xmax)
            pw   = round((x1 - x)  / RESOLUTION_M)
            ph   = round((y  - y0) / RESOLUTION_M)
            if pw > 0 and ph > 0:
                chunks.append((cid, x, y0, x1, y, pw, ph))
                cid += 1
            x = x1
        y = y0
    return chunks


def download_export_chunk(session, url, chunk_id, xmin, ymin, xmax, ymax,
                           px_w, px_h, out_dir):
    out_path = out_dir / f"chunk_{chunk_id:06d}.tif"
    if out_path.exists():
        return chunk_id, xmin, ymin, xmax, ymax, px_w, px_h, "skipped"

    params = {
        "bbox":        f"{xmin},{ymin},{xmax},{ymax}",
        "bboxSR":      3857,
        "imageSR":     3857,
        "size":        f"{px_w},{px_h}",
        "format":      "tiff",
        "pixelType":   "U8",
        "f":           "image",
    }
    try:
        r = session.get(url, params=params, timeout=TIMEOUT)
        if r.status_code == 200 and "image" in r.headers.get("Content-Type", ""):
            out_path.write_bytes(r.content)
            time.sleep(DELAY_SEC)
            return chunk_id, xmin, ymin, xmax, ymax, px_w, px_h, "ok"
        else:
            return chunk_id, xmin, ymin, xmax, ymax, px_w, px_h, f"http_{r.status_code}"
    except Exception as e:
        return chunk_id, xmin, ymin, xmax, ymax, px_w, px_h, f"error_{e}"


def stitch_export_chunks(chunks, svc, out_dir, output_path, n_bands):
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS

    xmin = svc["xmin"];  xmax = svc["xmax"]
    ymin = svc["ymin"];  ymax = svc["ymax"]
    total_w = round((xmax - xmin) / RESOLUTION_M)
    total_h = round((ymax - ymin) / RESOLUTION_M)

    print(f"  Stitching {len(chunks):,} chunks -> {total_w:,} x {total_h:,} px  ({n_bands} bands)")
    print(f"  Estimated uncompressed: ~{total_w * total_h * n_bands / 1e9:.2f} GB")

    transform = from_bounds(xmin, ymin, xmax, ymax, total_w, total_h)
    crs       = CRS.from_epsg(3857)

    _write_geotiff(output_path, total_w, total_h, n_bands, transform, crs,
                   lambda dst: _stitch_chunks_to_dst(
                       dst, chunks, out_dir, xmin, ymax, n_bands, total_w, total_h))


def _stitch_chunks_to_dst(dst, chunks, out_dir, xmin, ymax, n_bands, total_w, total_h):
    import rasterio
    with tqdm(total=len(chunks), unit="chunk", desc="  Stitching",
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} chunks [{elapsed}<{remaining}]") as pbar:
        for i, (cid, bx0, by0, bx1, by1, pw, ph) in enumerate(chunks):
            chunk_path = out_dir / f"chunk_{cid:06d}.tif"
            if not chunk_path.exists():
                print(f"  WARN: missing chunk {cid} — leaving black")
                pbar.update(1)
                continue
            try:
                with rasterio.open(chunk_path) as src:
                    arr = src.read()   # shape: (actual_bands, h, w)
            except Exception as e:
                print(f"  WARN: chunk {cid}: {e}")
                pbar.update(1)
                continue

            col_off = round((bx0 - xmin) / RESOLUTION_M)
            row_off = round((ymax - by1) / RESOLUTION_M)

            # Pad or trim band count to match expected n_bands
            if arr.shape[0] < n_bands:
                pad = np.zeros((n_bands - arr.shape[0], arr.shape[1], arr.shape[2]),
                               dtype=arr.dtype)
                arr = np.concatenate([arr, pad], axis=0)
            arr = arr[:n_bands]

            window = rasterio.windows.Window(col_off, row_off, pw, ph)
            dst.write(arr, window=window)
            pbar.update(1)


def run_export_download(year, svc, output_path):
    chunks = build_export_chunks(svc)
    total  = len(chunks)
    n_bands = svc["bands"]

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    ok = skipped = errors = 0

    print(f"  Downloading {total:,} chunks ({n_bands}-band TIFF)...")
    with requests.Session() as session:
        session.headers.update(BROWSER_HEADERS)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(download_export_chunk, session, svc["url"],
                                cid, x0, y0, x1, y1, pw, ph, TEMP_DIR): cid
                for cid, x0, y0, x1, y1, pw, ph in chunks
            }
            with tqdm(total=total, unit="chunk",
                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]") as pbar:
                for future in as_completed(futures):
                    cid, *_, status = future.result()
                    if   status == "ok":      ok      += 1
                    elif status == "skipped": skipped += 1
                    else:                     errors  += 1
                    pbar.set_postfix(ok=ok, skip=skipped, err=errors)
                    pbar.update(1)

    print(f"  Download complete — {ok + skipped:,}/{total:,} chunks ready.")
    stitch_export_chunks(chunks, svc, TEMP_DIR, output_path, n_bands)
    shutil.rmtree(TEMP_DIR)


# ── Shared GeoTIFF writer ─────────────────────────────────────────────────────

def _write_geotiff(output_path, width, height, n_bands, transform, crs, fill_fn):
    import rasterio
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path, "w",
        driver     = "GTiff",
        height     = height,
        width      = width,
        count      = n_bands,
        dtype      = "uint8",
        crs        = crs,
        transform  = transform,
        compress   = "deflate",
        predictor  = 2,
        tiled      = True,
        blockxsize = 512,
        blockysize = 512,
        BIGTIFF    = "YES",
    ) as dst:
        fill_fn(dst)

    size_gb = Path(output_path).stat().st_size / 1e9
    print(f"  Saved: {Path(output_path).name}  ({size_gb:.2f} GB,  {n_bands} bands)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        from google.colab import drive as _drive
        if not os.path.exists("/content/drive/MyDrive"):
            print("Mounting Google Drive...")
            _drive.mount("/content/drive")
    except ImportError:
        pass

    print(f"Edmonds Aerial Imagery Downloader")
    print(f"Years: {YEARS_TO_DOWNLOAD}")
    print(f"Output: {OUTPUT_DIR}\n")

    for year in YEARS_TO_DOWNLOAD:
        if year not in SERVICES:
            print(f"WARN: No service registered for {year} — skipping.")
            continue

        svc         = SERVICES[year]
        # Naming: {year}_{source}_{bands}.tif — set source/bands per downloader call
output_path = Path(OUTPUT_DIR) / f"{year}_coe_rgb.tif"

        print(f"\n{'='*60}")
        print(f"  {year}  ({svc['bands']}-band,  method={svc['method']})")
        print(f"{'='*60}")

        if output_path.exists():
            print(f"  Already exists — skipping.")
            continue

        if svc["method"] == "tiles":
            run_tile_download(year, svc, output_path)
        elif svc["method"] == "export":
            run_export_download(year, svc, output_path)

    print(f"\nAll done.")


if __name__ == "__main__":
    main()
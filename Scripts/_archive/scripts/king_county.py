"""
King County Aerial Imagery Downloader — Edmonds extent
Downloads aerial imagery from gismaps.kingcounty.gov for the same geographic
extent as the Edmonds imagery, and saves each year as a georeferenced GeoTIFF.

All King County services are cached MapServer (tile-based, 3-band RGB).
The script auto-detects the maximum available zoom level for each service,
then downloads tiles covering the Edmonds bounding box.

Output files: kingco_{year}_image.tif

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

YEARS_TO_DOWNLOAD = [2007, 2009, 2012, 2013, 2015, 2017, 2019, 2021, 2023]

from pipeline_config import FULL_IMAGE_DIR
OUTPUT_DIR  = str(FULL_IMAGE_DIR / "KingCo")
TILE_SIZE   = 256
MAX_WORKERS = 8
DELAY_SEC   = 0.05
TIMEOUT     = 60
TEMP_DIR    = Path("/tmp/kingco_download")

# ── Edmonds bounding box (EPSG:3857, Web Mercator) ───────────────────────────
# This is the same extent used by the Edmonds 4-band exports.
EXTENT_XMIN = -13625876.424
EXTENT_YMIN =   6068463.621
EXTENT_XMAX = -13614805.955
EXTENT_YMAX =   6084271.153

# ── Service registry ──────────────────────────────────────────────────────────
# All services are MapServer with cached tiles.
# 'zoom_hint' is the expected max zoom; the script probes each service to
# confirm and will use the deepest LOD available.

BASE = "https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps"

SERVICES = {
    1936: {"url": f"{BASE}/KingCo_Aerial_1936/MapServer", "zoom_hint": 19, "bands": 1},
    1998: {"url": f"{BASE}/KingCo_Aerial_1998/MapServer", "zoom_hint": 19, "bands": 1},
    2000: {"url": f"{BASE}/KingCo_Aerial_2000/MapServer", "zoom_hint": 19, "bands": 3},
    2002: {"url": f"{BASE}/KingCo_Aerial_2002/MapServer", "zoom_hint": 19, "bands": 3},
    2005: {"url": f"{BASE}/KingCo_Aerial_2005/MapServer", "zoom_hint": 19, "bands": 3},
    2007: {"url": f"{BASE}/KingCo_Aerial_2007/MapServer", "zoom_hint": 19, "bands": 3},
    2009: {"url": f"{BASE}/KingCo_Aerial_2009/MapServer", "zoom_hint": 19, "bands": 3},
    2012: {"url": f"{BASE}/KingCo_Aerial_2012/MapServer", "zoom_hint": 19, "bands": 3},
    2013: {"url": f"{BASE}/KingCo_Aerial_2013/MapServer", "zoom_hint": 20, "bands": 3},
    2015: {"url": f"{BASE}/KingCo_Aerial_2015/MapServer", "zoom_hint": 20, "bands": 3},
    2017: {"url": f"{BASE}/KingCo_Aerial_2017/MapServer", "zoom_hint": 20, "bands": 3},
    2019: {"url": f"{BASE}/KingCo_Aerial_2019/MapServer", "zoom_hint": 20, "bands": 3},
    2021: {"url": f"{BASE}/KingCo_Aerial_2021/MapServer", "zoom_hint": 20, "bands": 3},
    2023: {"url": f"{BASE}/KingCo_Aerial_2023/MapServer", "zoom_hint": 20, "bands": 3},
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) "
                  "Gecko/20100101 Firefox/148.0",
    "Accept":     "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
}

# ── Coordinate helpers ────────────────────────────────────────────────────────

EARTH = 20037508.342789244


def merc_to_tile(x, y, z):
    """Convert EPSG:3857 coordinate to tile (row, col) at zoom z."""
    lon = x / EARTH * 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * y / EARTH)))
    n = 2 ** z
    col = int((lon + 180.0) / 360.0 * n)
    row = int((1.0 - math.log(math.tan(math.radians(lat)) +
              1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n)
    return row, col


def tile_origin_merc(row, col, z):
    """Return the top-left corner of tile (row, col) in EPSG:3857."""
    n = 2 ** z
    lon = col / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * row / n)))
    lat = math.degrees(lat_rad)
    x = lon / 180.0 * EARTH
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / math.pi * EARTH
    return x, y


def tile_bounds_for_extent(z):
    """Return (row_min, row_max, col_min, col_max) covering the Edmonds extent."""
    r_nw, c_nw = merc_to_tile(EXTENT_XMIN, EXTENT_YMAX, z)   # NW corner
    r_se, c_se = merc_to_tile(EXTENT_XMAX, EXTENT_YMIN, z)    # SE corner
    return r_nw, r_se, c_nw, c_se


# ── Zoom level detection ──────────────────────────────────────────────────────

def detect_max_zoom(session, base_url, zoom_hint):
    """
    Probe the MapServer JSON to find the deepest available LOD.
    Falls back to zoom_hint on failure.
    """
    try:
        r = session.get(f"{base_url}?f=json", timeout=TIMEOUT)
        if r.status_code == 200:
            info = r.json()
            tile_info = info.get("tileInfo", {})
            lods = tile_info.get("lods", [])
            if lods:
                max_lod = max(lod["level"] for lod in lods)
                return min(max_lod, 21)   # cap at 21 to be safe
    except Exception as e:
        print(f"  WARN: Could not probe tile info: {e}")
    return zoom_hint


def verify_tiles_exist(session, base_url, z, row_min, row_max, col_min, col_max):
    """Quick check: try fetching a center tile to confirm this zoom has data."""
    r_mid = (row_min + row_max) // 2
    c_mid = (col_min + col_max) // 2
    try:
        r = session.get(f"{base_url}/tile/{z}/{r_mid}/{c_mid}", timeout=15)
        if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image"):
            return True
        # If 404 at this zoom, try one level up
        return False
    except Exception:
        return False


# ── Tile download ─────────────────────────────────────────────────────────────

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


# ── Stitch tiles into GeoTIFF ─────────────────────────────────────────────────

def stitch_tiles(tile_dir, z, row_min, row_max, col_min, col_max, n_bands, output_path):
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS

    n_rows = row_max - row_min + 1
    n_cols = col_max - col_min + 1
    total_w = n_cols * TILE_SIZE
    total_h = n_rows * TILE_SIZE

    # Force at least 3 bands for the output (grayscale → RGB for consistency)
    out_bands = max(n_bands, 3)

    print(f"  Stitching {n_rows:,} x {n_cols:,} tiles -> {total_w:,} x {total_h:,} px  ({out_bands} bands)")
    print(f"  Estimated uncompressed: ~{total_w * total_h * out_bands / 1e9:.2f} GB")

    x_min, y_max = tile_origin_merc(row_min,     col_min,     z)
    x_max, y_min = tile_origin_merc(row_max + 1, col_max + 1, z)

    transform = from_bounds(x_min, y_min, x_max, y_max, total_w, total_h)
    crs = CRS.from_epsg(3857)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(
        out_path, "w",
        driver="GTiff", height=total_h, width=total_w,
        count=out_bands, dtype="uint8", crs=crs, transform=transform,
        compress="deflate", predictor=2,
        tiled=True, blockxsize=512, blockysize=512, BIGTIFF="YES",
    ) as dst:
        with tqdm(total=n_rows, unit="row", desc="  Stitching",
                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} rows "
                             "[{elapsed}<{remaining}]") as pbar:
            for row in range(row_min, row_max + 1):
                strip = np.zeros((TILE_SIZE, total_w, 3), dtype=np.uint8)
                for col in range(col_min, col_max + 1):
                    tile_path = tile_dir / f"{row}_{col}.jpg"
                    if tile_path.exists():
                        try:
                            arr = np.array(Image.open(tile_path).convert("RGB"))
                            x = (col - col_min) * TILE_SIZE
                            strip[:, x:x + TILE_SIZE, :] = arr
                        except Exception as e:
                            print(f"  WARN: tile {row}_{col}: {e}")
                y = (row - row_min) * TILE_SIZE
                for b in range(out_bands):
                    # For grayscale services (bands=1), replicate channel 0
                    src_b = min(b, 2)
                    dst.write(strip[:, :, src_b], b + 1,
                              window=rasterio.windows.Window(0, y, total_w, TILE_SIZE))
                pbar.update(1)

    size_gb = out_path.stat().st_size / 1e9
    print(f"  Saved: {out_path.name}  ({size_gb:.2f} GB,  {out_bands} bands)")


# ── Per-year download pipeline ─────────────────────────────────────────────────

def run_year(year, svc, output_path):
    base_url = svc["url"]
    n_bands  = svc["bands"]

    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    with requests.Session() as session:
        session.headers.update(BROWSER_HEADERS)

        # 1. Detect max zoom from service JSON
        print(f"  Probing tile info...")
        zoom = detect_max_zoom(session, base_url, svc["zoom_hint"])

        # 2. Step down through zoom levels until we find actual tiles
        MIN_ZOOM = 17
        while zoom >= MIN_ZOOM:
            row_min, row_max, col_min, col_max = tile_bounds_for_extent(zoom)
            total_tiles = (row_max - row_min + 1) * (col_max - col_min + 1)
            if verify_tiles_exist(session, base_url, zoom,
                                  row_min, row_max, col_min, col_max):
                break
            print(f"  No tiles at zoom {zoom}, trying {zoom - 1}...")
            zoom -= 1
        else:
            print(f"  ERROR: No tiles found at any zoom level down to {MIN_ZOOM}!")
            return

        row_min, row_max, col_min, col_max = tile_bounds_for_extent(zoom)
        total_tiles = (row_max - row_min + 1) * (col_max - col_min + 1)

        res_m = 2 * EARTH / (2**zoom * TILE_SIZE)
        print(f"  Zoom: {zoom}  |  Resolution: {res_m:.4f} m/px")
        print(f"  Tile range: rows {row_min}-{row_max}, cols {col_min}-{col_max}")
        print(f"  Downloading {total_tiles:,} tiles...")

        # 3. Download tiles
        tiles = [(r, c) for r in range(row_min, row_max + 1)
                         for c in range(col_min, col_max + 1)]
        ok = skipped = no_tile = errors = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(download_tile, session, base_url,
                                zoom, r, c, TEMP_DIR): (r, c)
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

        print(f"  Download complete — {ok + skipped:,} tiles ready, "
              f"{no_tile:,} empty, {errors:,} errors.")

    # 4. Stitch
    stitch_tiles(TEMP_DIR, zoom, row_min, row_max, col_min, col_max,
                 n_bands, output_path)
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

    print("King County Aerial Imagery Downloader (Edmonds extent)")
    print(f"Years: {YEARS_TO_DOWNLOAD}")
    print(f"Extent (EPSG:3857): [{EXTENT_XMIN}, {EXTENT_YMIN}] "
          f"to [{EXTENT_XMAX}, {EXTENT_YMAX}]")
    print(f"Output: {OUTPUT_DIR}\n")

    for year in YEARS_TO_DOWNLOAD:
        if year not in SERVICES:
            print(f"WARN: No service registered for {year} — skipping.")
            continue

        svc = SERVICES[year]
        output_path = Path(OUTPUT_DIR) / f"kingco_{year}_image.tif"

        print(f"\n{'='*60}")
        print(f"  {year}  ({svc['bands']}-band,  zoom_hint={svc['zoom_hint']})")
        print(f"  {svc['url']}")
        print(f"{'='*60}")

        if output_path.exists():
            print(f"  Already exists — skipping.")
            continue

        try:
            run_year(year, svc, output_path)
        except Exception as e:
            print(f"  ERROR on {year}: {e}")
            if TEMP_DIR.exists():
                shutil.rmtree(TEMP_DIR)

    print(f"\nAll done.")


if __name__ == "__main__":
    main()
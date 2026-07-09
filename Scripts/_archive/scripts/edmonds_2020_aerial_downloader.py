#!/usr/bin/env python3
"""
Edmonds 2020 Aerial Imagery Downloader
=======================================
Downloads 4-band aerial imagery from the City of Edmonds 2020_Aerial_Cached
ImageServer as GeoTIFF chunks at zoom level 20, then merges into a single mosaic.

Source: https://maps.edmondswa.gov/gis/rest/services/Basemap/2020_Aerial_Cached/ImageServer

Service details (verified):
  - 4 bands (RGBN), U8, native pixel size 0.0762 m (~3 inches)
  - EPSG:3857 (Web Mercator) tile cache
  - Zoom 20 resolution: 0.14929 m/px
  - Max export size: 15,000 x 4,100 px
  - TIFF export confirmed working via exportImage endpoint
  - Extent: xmin=-13625876.42, ymin=6068463.62, xmax=-13614805.95, ymax=6084271.15

Strategy:
  Uses exportImage with format=tiff and 4,096x4,096 px chunks (well within
  the 15,000x4,100 server limit). Each chunk is a GeoTIFF with embedded
  spatial reference. Tiles are saved individually, then merged with GDAL.

Usage:
  pip install requests tqdm
  # GDAL must be installed for merge step (gdalbuildvrt + gdal_translate)

  # Test with a small area first
  python edmonds_2020_aerial_downloader.py --test

  # Full city download
  python edmonds_2020_aerial_downloader.py

  # Custom subset (EPSG:3857 coords)
  python edmonds_2020_aerial_downloader.py \\
      --xmin -13622000 --ymin 6074000 \\
      --xmax -13618000 --ymax 6078000

Author: Kam Eck / Edmonds CAB Tree Canopy Project
"""

import os
import sys
import math
import time
import logging
import argparse
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    sys.exit("ERROR: 'requests' is required. Install with: pip install requests")

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None
    print("NOTE: Install 'tqdm' for progress bars: pip install tqdm")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EXPORT_URL = (
    "https://maps.edmondswa.gov/gis/rest/services/Basemap/2020_Aerial_Cached"
    "/ImageServer/exportImage"
)

# EPSG:3857 full extent of the 2020 Edmonds imagery (from service metadata)
SERVICE_EXTENT = {
    "xmin": -13625876.424216248,
    "ymin": 6068463.620707856,
    "xmax": -13614805.954954829,
    "ymax": 6084271.15313839,
}

# A small test area in central Edmonds (~1 km²)
TEST_EXTENT = {
    "xmin": -13620500,
    "ymin": 6075500,
    "xmax": -13619500,
    "ymax": 6076500,
}

# Zoom 20 resolution in meters/pixel
ZOOM_20_RESOLUTION = 0.14929107082380833

# Export chunk size in pixels — comfortably under the 15,000 x 4,100 max
CHUNK_PX = 4096

# Derived: ground size of one chunk in meters
CHUNK_GROUND_M = CHUNK_PX * ZOOM_20_RESOLUTION  # ~611.5 m

# Request settings
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds base delay (multiplied by attempt number)
REQUEST_TIMEOUT = 120  # seconds
MAX_WORKERS = 4  # max concurrent downloads
DELAY_BETWEEN_REQUESTS = 0.5  # seconds — rate limiting

# Output defaults
DEFAULT_OUTPUT_DIR = "edmonds_2020_tiles"
DEFAULT_MOSAIC_NAME = "edmonds_2020_aerial_z20.tif"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Grid computation
# ---------------------------------------------------------------------------


def compute_grid(extent: dict, chunk_ground_m: float, chunk_px: int):
    """Compute the grid of export bounding boxes covering the extent."""
    xmin, ymin = extent["xmin"], extent["ymin"]
    xmax, ymax = extent["xmax"], extent["ymax"]

    width_m = xmax - xmin
    height_m = ymax - ymin

    n_cols = math.ceil(width_m / chunk_ground_m)
    n_rows = math.ceil(height_m / chunk_ground_m)

    log.info(
        f"Extent: {width_m:.1f} x {height_m:.1f} m  |  "
        f"Grid: {n_cols} cols x {n_rows} rows = {n_cols * n_rows} chunks  |  "
        f"Chunk: {chunk_px}x{chunk_px} px ({chunk_ground_m:.1f} m)"
    )

    tiles = []
    for row in range(n_rows):
        for col in range(n_cols):
            tile_xmin = xmin + col * chunk_ground_m
            tile_ymin = ymin + row * chunk_ground_m
            tile_xmax = min(tile_xmin + chunk_ground_m, xmax)
            tile_ymax = min(tile_ymin + chunk_ground_m, ymax)

            # Pixel dimensions (edge tiles may be smaller)
            px_w = round((tile_xmax - tile_xmin) / ZOOM_20_RESOLUTION)
            px_h = round((tile_ymax - tile_ymin) / ZOOM_20_RESOLUTION)

            # Clamp to server max
            px_w = min(px_w, 15000)
            px_h = min(px_h, 4100)

            tiles.append(
                {
                    "row": row,
                    "col": col,
                    "bbox": f"{tile_xmin},{tile_ymin},{tile_xmax},{tile_ymax}",
                    "size": f"{px_w},{px_h}",
                    "px_w": px_w,
                    "px_h": px_h,
                }
            )
    return tiles, n_cols, n_rows


# ---------------------------------------------------------------------------
# Downloading
# ---------------------------------------------------------------------------


def download_tile(tile: dict, output_dir: Path, session: requests.Session) -> dict:
    """Download a single export chunk as TIFF."""
    filename = f"tile_r{tile['row']:03d}_c{tile['col']:03d}.tif"
    filepath = output_dir / filename

    # Skip if already downloaded and reasonably sized
    if filepath.exists() and filepath.stat().st_size > 1000:
        return {"tile": tile, "path": filepath, "status": "skipped"}

    # Minimal params — confirmed working against this server
    params = {
        "bbox": tile["bbox"],
        "bboxSR": "102100",
        "imageSR": "102100",
        "size": tile["size"],
        "format": "tiff",
        "f": "image",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(
                EXPORT_URL, params=params, timeout=REQUEST_TIMEOUT, stream=True
            )
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")

            # Check for error responses (HTML or JSON instead of image)
            if "json" in content_type or "html" in content_type:
                error_body = resp.text[:500]
                log.warning(
                    f"Tile r{tile['row']} c{tile['col']} got non-image response "
                    f"(attempt {attempt}): {error_body}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                    continue
                return {
                    "tile": tile, "path": None,
                    "status": "error", "msg": error_body[:200],
                }

            # Write the TIFF
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)

            fsize = filepath.stat().st_size

            # Validate: TIFF header check
            with open(filepath, "rb") as f:
                magic = f.read(4)

            if magic[:2] not in (b"II", b"MM"):
                log.warning(
                    f"Tile r{tile['row']} c{tile['col']} not a valid TIFF "
                    f"(magic: {magic}), attempt {attempt}"
                )
                filepath.unlink(missing_ok=True)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                    continue
                return {
                    "tile": tile, "path": None,
                    "status": "error", "msg": "invalid TIFF header",
                }

            # Validate: suspiciously small files
            if fsize < 1000:
                log.warning(
                    f"Tile r{tile['row']} c{tile['col']} only {fsize} bytes, "
                    f"attempt {attempt}"
                )
                filepath.unlink(missing_ok=True)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                    continue
                return {
                    "tile": tile, "path": None,
                    "status": "error", "msg": f"tiny file ({fsize} bytes)",
                }

            log.debug(
                f"Tile r{tile['row']} c{tile['col']}: "
                f"{fsize / 1024:.0f} KB"
            )
            return {"tile": tile, "path": filepath, "status": "ok"}

        except requests.RequestException as e:
            log.warning(
                f"Tile r{tile['row']} c{tile['col']} request failed "
                f"(attempt {attempt}): {e}"
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
            else:
                return {
                    "tile": tile, "path": None,
                    "status": "error", "msg": str(e)[:200],
                }

    return {"tile": tile, "path": None, "status": "error", "msg": "exhausted retries"}


def download_all(tiles: list, output_dir: Path, workers: int):
    """Download all tiles with optional parallelism and rate limiting."""
    output_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "EdmondsCAB-TreeCanopy/1.0 (GIS research)",
            "Accept": "image/tiff, */*",
        }
    )

    results = []
    errors = []

    pbar = tqdm(total=len(tiles), desc="Downloading", unit="tile") if tqdm else None

    if workers <= 1:
        for tile in tiles:
            result = download_tile(tile, output_dir, session)
            results.append(result)
            if result["status"] == "error":
                errors.append(result)
            if pbar:
                pbar.update(1)
                pbar.set_postfix(
                    ok=sum(1 for r in results if r["status"] in ("ok", "skipped")),
                    err=len(errors),
                )
            time.sleep(DELAY_BETWEEN_REQUESTS)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {}
            for i, tile in enumerate(tiles):
                future = pool.submit(download_tile, tile, output_dir, session)
                future_map[future] = tile
                if i > 0 and i % workers == 0:
                    time.sleep(DELAY_BETWEEN_REQUESTS)

            for future in as_completed(future_map):
                result = future.result()
                results.append(result)
                if result["status"] == "error":
                    errors.append(result)
                if pbar:
                    pbar.update(1)
                    pbar.set_postfix(
                        ok=sum(1 for r in results if r["status"] in ("ok", "skipped")),
                        err=len(errors),
                    )

    if pbar:
        pbar.close()

    ok_count = sum(1 for r in results if r["status"] in ("ok", "skipped"))
    skip_count = sum(1 for r in results if r["status"] == "skipped")
    new_count = sum(1 for r in results if r["status"] == "ok")
    log.info(
        f"Download complete: {ok_count}/{len(tiles)} tiles OK "
        f"({new_count} new, {skip_count} cached), {len(errors)} errors"
    )

    if errors:
        log.warning("Failed tiles:")
        for e in errors:
            t = e["tile"]
            log.warning(f"  r{t['row']} c{t['col']}: {e.get('msg', 'unknown')}")

    return results


# ---------------------------------------------------------------------------
# Merge with GDAL
# ---------------------------------------------------------------------------


def merge_tiles(output_dir: Path, mosaic_name: str):
    """Merge individual TIFF tiles into a single GeoTIFF using GDAL."""
    tif_files = sorted(output_dir.glob("tile_r*_c*.tif"))
    if not tif_files:
        log.error("No tile files found to merge.")
        return None

    log.info(f"Merging {len(tif_files)} tiles into {mosaic_name}...")
    mosaic_path = output_dir / mosaic_name
    vrt_path = output_dir / "mosaic.vrt"
    filelist_path = output_dir / "tile_list.txt"

    with open(filelist_path, "w") as f:
        for tf in tif_files:
            f.write(str(tf) + "\n")

    cmd_vrt = [
        "gdalbuildvrt",
        "-input_file_list", str(filelist_path),
        str(vrt_path),
    ]

    cmd_translate = [
        "gdal_translate",
        "-of", "GTiff",
        "-co", "COMPRESS=LZW",
        "-co", "TILED=YES",
        "-co", "BLOCKXSIZE=512",
        "-co", "BLOCKYSIZE=512",
        "-co", "BIGTIFF=IF_SAFER",
        str(vrt_path),
        str(mosaic_path),
    ]

    try:
        log.info("  Building VRT...")
        r1 = subprocess.run(cmd_vrt, check=True, capture_output=True, text=True)
        if r1.stderr:
            log.debug(f"  VRT stderr: {r1.stderr.strip()}")

        log.info("  Translating to GeoTIFF (may take a while for large areas)...")
        r2 = subprocess.run(cmd_translate, check=True, capture_output=True, text=True)
        if r2.stderr:
            log.debug(f"  Translate stderr: {r2.stderr.strip()}")

        size_mb = mosaic_path.stat().st_size / (1024 ** 2)
        log.info(f"  Mosaic saved: {mosaic_path} ({size_mb:.1f} MB)")

        # Quick gdalinfo summary
        try:
            gi = subprocess.run(
                ["gdalinfo", "-stats", str(mosaic_path)],
                capture_output=True, text=True, timeout=30,
            )
            if gi.returncode == 0:
                log.info("  Mosaic info:")
                for line in gi.stdout.split("\n"):
                    line = line.strip()
                    if any(kw in line.lower() for kw in [
                        "size is", "coordinate system", "pixel size",
                        "band ", "type=", "origin",
                    ]):
                        log.info(f"    {line}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return mosaic_path

    except FileNotFoundError:
        log.error(
            "GDAL not found! Install with one of:\n"
            "  conda install -c conda-forge gdal\n"
            "  sudo apt install gdal-bin\n"
            "  pip install GDAL\n\n"
            "Tiles are saved individually and can be merged later:\n"
            f"  gdalbuildvrt mosaic.vrt {output_dir}/tile_r*_c*.tif\n"
            f"  gdal_translate -of GTiff -co COMPRESS=LZW -co BIGTIFF=IF_SAFER "
            f"mosaic.vrt {output_dir}/{mosaic_name}"
        )
        return None
    except subprocess.CalledProcessError as e:
        log.error(f"GDAL merge failed:\n  stdout: {e.stdout}\n  stderr: {e.stderr}")
        return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_sample(output_dir: Path):
    """Quick validation of a sample tile with gdalinfo."""
    sample = next(output_dir.glob("tile_r*_c*.tif"), None)
    if not sample:
        return

    try:
        result = subprocess.run(
            ["gdalinfo", str(sample)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            log.info(f"Sample tile validation ({sample.name}):")
            for line in result.stdout.split("\n"):
                line = line.strip()
                if any(kw in line.lower() for kw in [
                    "size is", "coordinate system", "pixel size",
                    "band", "type=", "origin",
                ]):
                    log.info(f"  {line}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        log.info(
            "gdalinfo not available — skipping validation. "
            "Tiles should still be valid GeoTIFFs."
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Download Edmonds 2020 4-band aerial imagery as GeoTIFF at zoom 20.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test — small area, ~4 tiles
  python edmonds_2020_aerial_downloader.py --test

  # Full city download (sequential, polite)
  python edmonds_2020_aerial_downloader.py

  # Faster with parallel workers
  python edmonds_2020_aerial_downloader.py --workers 4

  # Download only, skip merge
  python edmonds_2020_aerial_downloader.py --no-merge

  # Custom output directory
  python edmonds_2020_aerial_downloader.py -o /data/edmonds_2020

  # Custom extent subset (EPSG:3857 coordinates)
  python edmonds_2020_aerial_downloader.py \\
      --xmin -13622000 --ymin 6074000 \\
      --xmax -13618000 --ymax 6078000
        """,
    )

    parser.add_argument(
        "-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--mosaic-name", type=str, default=DEFAULT_MOSAIC_NAME,
        help=f"Merged GeoTIFF filename (default: {DEFAULT_MOSAIC_NAME})",
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Parallel download workers (default: 1 = sequential)",
    )
    parser.add_argument(
        "--no-merge", action="store_true",
        help="Skip merging tiles into a single GeoTIFF",
    )
    parser.add_argument(
        "--chunk-px", type=int, default=CHUNK_PX,
        help=f"Chunk size in pixels (default: {CHUNK_PX})",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Download a small test area (~1 km² in central Edmonds)",
    )

    # Custom extent overrides
    parser.add_argument("--xmin", type=float, default=None)
    parser.add_argument("--ymin", type=float, default=None)
    parser.add_argument("--xmax", type=float, default=None)
    parser.add_argument("--ymax", type=float, default=None)

    args = parser.parse_args()

    # Determine extent
    if args.test:
        extent = TEST_EXTENT.copy()
        log.info("TEST MODE: using small subset area")
    else:
        extent = SERVICE_EXTENT.copy()

    if args.xmin is not None:
        extent["xmin"] = args.xmin
    if args.ymin is not None:
        extent["ymin"] = args.ymin
    if args.xmax is not None:
        extent["xmax"] = args.xmax
    if args.ymax is not None:
        extent["ymax"] = args.ymax

    chunk_ground = args.chunk_px * ZOOM_20_RESOLUTION

    log.info("=" * 60)
    log.info("Edmonds 2020 Aerial Imagery Downloader")
    log.info("=" * 60)
    log.info(f"Source:     {EXPORT_URL}")
    log.info(f"Zoom:       20  ({ZOOM_20_RESOLUTION:.4f} m/px)")
    log.info(f"Bands:      4 (RGBN)  |  Format: GeoTIFF")
    log.info(f"Chunk:      {args.chunk_px}x{args.chunk_px} px ({chunk_ground:.1f} m)")
    log.info(f"Workers:    {args.workers}")
    log.info(f"Output:     {args.output_dir}")
    log.info(f"Extent:     xmin={extent['xmin']:.2f}  ymin={extent['ymin']:.2f}")
    log.info(f"            xmax={extent['xmax']:.2f}  ymax={extent['ymax']:.2f}")
    log.info("")

    # Compute grid
    tiles, n_cols, n_rows = compute_grid(extent, chunk_ground, args.chunk_px)

    if not tiles:
        log.error("No tiles to download — check extent coordinates.")
        return

    # Size estimate (rough: 4 bands * px * px * ~0.5 compression)
    est_bytes = 4 * args.chunk_px * args.chunk_px * 0.5
    est_total_mb = len(tiles) * est_bytes / (1024 ** 2)
    log.info(f"Estimated download: ~{est_total_mb:.0f} MB ({len(tiles)} tiles)")
    log.info("")

    # Download
    output_dir = Path(args.output_dir)
    results = download_all(tiles, output_dir, args.workers)

    # Validate
    validate_sample(output_dir)

    # Merge
    if not args.no_merge:
        merge_tiles(output_dir, args.mosaic_name)
    else:
        log.info("Merge skipped (--no-merge). Tiles saved individually.")

    log.info("Done!")


if __name__ == "__main__":
    main()
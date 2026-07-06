#!/usr/bin/env python3
"""
NAIP 4-Band Multi-Year Imagery Downloader — Edmonds, WA
=========================================================
Downloads all available 4-band (RGBN) NAIP imagery for the City of Edmonds
from the USGS National Map ImageServer, one GeoTIFF mosaic per year.

Source: https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer

Washington state NAIP 4-band availability (flown odd years):
  Year  Resolution   Bands  Status
  2013  1.0 m        4      Available
  2015  1.0 m        4      Available
  2017  1.0 m        4      Available
  2019  0.6 m        4      Available
  2021  0.6 m        4      Available
  2023  0.3 m        4      Available (15 cm native, served at 30 cm)
  2025  0.3/0.6 m    4      Acquisition planned — not yet available

The ImageServer mosaics everything to 0.3 m pixel size regardless of native
resolution. Older 1 m data will be upsampled by the server.

Service limits: max export 4,000 x 4,000 px per request.

Usage:
  pip install requests tqdm

  # Download ALL available years
  python naip_edmonds_downloader.py

  # Single year
  python naip_edmonds_downloader.py --year 2021

  # Multiple specific years
  python naip_edmonds_downloader.py --years 2019 2021 2023

  # Test mode (small area, one year)
  python naip_edmonds_downloader.py --test --year 2023

  # Skip merge (keep individual chunks)
  python naip_edmonds_downloader.py --no-merge

Author: Kam Eck / Edmonds CAB Tree Canopy Project
"""

import sys
import json
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
    sys.exit("ERROR: 'requests' required. Install: pip install requests")

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None
    print("NOTE: Install 'tqdm' for progress bars: pip install tqdm")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EXPORT_URL = (
    "https://imagery.nationalmap.gov/arcgis/rest/services"
    "/USGSNAIPImagery/ImageServer/exportImage"
)

# All WA NAIP 4-band years from 2013 onward
ALL_YEARS = [2013, 2015, 2017, 2019, 2021, 2023]

YEAR_INFO = {
    2013: "1.0 m (served upsampled to 0.3 m)",
    2015: "1.0 m (served upsampled to 0.3 m)",
    2017: "1.0 m (served upsampled to 0.3 m)",
    2019: "0.6 m (served at 0.3 m)",
    2021: "0.6 m (served at 0.3 m)",
    2023: "0.3 m native (15 cm GSD)",
}

# Edmonds extent in EPSG:3857
EDMONDS_EXTENT = {
    "xmin": -13625876.42,
    "ymin": 6068463.62,
    "xmax": -13614805.95,
    "ymax": 6084271.15,
}

TEST_EXTENT = {
    "xmin": -13620500,
    "ymin": 6075500,
    "xmax": -13619500,
    "ymax": 6076500,
}

# The ImageServer serves at 0.3 m regardless of native resolution
SERVICE_PIXEL_SIZE = 0.30
MAX_EXPORT_PX = 4000
CHUNK_PX = 4000
CHUNK_GROUND_M = CHUNK_PX * SERVICE_PIXEL_SIZE  # 1200 m

# Request settings
MAX_RETRIES = 3
RETRY_DELAY = 3
REQUEST_TIMEOUT = 180
DELAY_BETWEEN_REQUESTS = 1.0

DEFAULT_OUTPUT_DIR = "naip_edmonds"

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------

def compute_grid(extent: dict):
    xmin, ymin = extent["xmin"], extent["ymin"]
    xmax, ymax = extent["xmax"], extent["ymax"]

    n_cols = math.ceil((xmax - xmin) / CHUNK_GROUND_M)
    n_rows = math.ceil((ymax - ymin) / CHUNK_GROUND_M)

    tiles = []
    for row in range(n_rows):
        for col in range(n_cols):
            tx0 = xmin + col * CHUNK_GROUND_M
            ty0 = ymin + row * CHUNK_GROUND_M
            tx1 = min(tx0 + CHUNK_GROUND_M, xmax)
            ty1 = min(ty0 + CHUNK_GROUND_M, ymax)

            px_w = min(round((tx1 - tx0) / SERVICE_PIXEL_SIZE), MAX_EXPORT_PX)
            px_h = min(round((ty1 - ty0) / SERVICE_PIXEL_SIZE), MAX_EXPORT_PX)

            tiles.append({
                "row": row, "col": col,
                "bbox": f"{tx0},{ty0},{tx1},{ty1}",
                "size": f"{px_w},{px_h}",
            })
    return tiles, n_cols, n_rows


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def build_mosaic_rule(year: int):
    return json.dumps({
        "mosaicMethod": "esriMosaicAttribute",
        "sortField": "Year",
        "sortValue": "3000",
        "ascending": False,
        "mosaicOperation": "MT_FIRST",
        "where": f"State = 'WA' AND Year = {year}",
    })


def download_tile(tile, out_dir, session, year):
    fname = f"naip_{year}_r{tile['row']:03d}_c{tile['col']:03d}.tif"
    fpath = out_dir / fname

    if fpath.exists() and fpath.stat().st_size > 1000:
        return {"tile": tile, "path": fpath, "status": "skipped"}

    params = {
        "bbox": tile["bbox"],
        "bboxSR": "102100",
        "imageSR": "102100",
        "size": tile["size"],
        "format": "tiff",
        "renderingRule": json.dumps({"rasterFunction": "None"}),
        "mosaicRule": build_mosaic_rule(year),
        "f": "image",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(EXPORT_URL, params=params,
                               timeout=REQUEST_TIMEOUT, stream=True)
            resp.raise_for_status()

            ct = resp.headers.get("Content-Type", "")
            if "json" in ct or "html" in ct:
                body = resp.text[:300]
                log.warning(f"  [{year}] r{tile['row']}c{tile['col']} "
                            f"non-image (att {attempt})")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                    continue
                return {"tile": tile, "path": None, "status": "error",
                        "msg": body[:150]}

            with open(fpath, "wb") as f:
                for chunk in resp.iter_content(65536):
                    f.write(chunk)

            sz = fpath.stat().st_size
            with open(fpath, "rb") as f:
                magic = f.read(4)

            if magic[:2] not in (b"II", b"MM"):
                log.warning(f"  [{year}] r{tile['row']}c{tile['col']} "
                            f"bad TIFF (att {attempt})")
                fpath.unlink(missing_ok=True)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                    continue
                return {"tile": tile, "path": None, "status": "error",
                        "msg": "invalid TIFF"}

            if sz < 1000:
                fpath.unlink(missing_ok=True)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                    continue
                return {"tile": tile, "path": None, "status": "error",
                        "msg": f"tiny ({sz}B)"}

            return {"tile": tile, "path": fpath, "status": "ok"}

        except requests.RequestException as e:
            log.warning(f"  [{year}] r{tile['row']}c{tile['col']} "
                        f"failed (att {attempt}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
            else:
                return {"tile": tile, "path": None, "status": "error",
                        "msg": str(e)[:150]}

    return {"tile": tile, "path": None, "status": "error", "msg": "retries exhausted"}


def download_year(year, tiles, out_dir, workers):
    year_dir = out_dir / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "EdmondsCAB-TreeCanopy/1.0 (NAIP research)",
        "Accept": "image/tiff, */*",
    })

    results, errors = [], []
    pbar = tqdm(total=len(tiles), desc=f"  NAIP {year}",
                unit="tile") if tqdm else None

    if workers <= 1:
        for tile in tiles:
            r = download_tile(tile, year_dir, session, year)
            results.append(r)
            if r["status"] == "error":
                errors.append(r)
            if pbar:
                pbar.update(1)
                pbar.set_postfix(
                    ok=sum(1 for x in results if x["status"] in ("ok", "skipped")),
                    err=len(errors))
            time.sleep(DELAY_BETWEEN_REQUESTS)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {}
            for i, tile in enumerate(tiles):
                fut = pool.submit(download_tile, tile, year_dir, session, year)
                futs[fut] = tile
                if i > 0 and i % workers == 0:
                    time.sleep(DELAY_BETWEEN_REQUESTS)
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                if r["status"] == "error":
                    errors.append(r)
                if pbar:
                    pbar.update(1)
                    pbar.set_postfix(
                        ok=sum(1 for x in results if x["status"] in ("ok", "skipped")),
                        err=len(errors))

    if pbar:
        pbar.close()

    ok = sum(1 for r in results if r["status"] in ("ok", "skipped"))
    skip = sum(1 for r in results if r["status"] == "skipped")
    new = sum(1 for r in results if r["status"] == "ok")
    log.info(f"  {year}: {ok}/{len(tiles)} OK ({new} new, {skip} cached), "
             f"{len(errors)} errors")

    if errors:
        for e in errors:
            t = e["tile"]
            log.warning(f"    r{t['row']}c{t['col']}: {e.get('msg','?')}")

    return results


# ---------------------------------------------------------------------------
# GDAL merge
# ---------------------------------------------------------------------------

def merge_year(out_dir, year):
    year_dir = out_dir / str(year)
    tifs = sorted(year_dir.glob(f"naip_{year}_r*_c*.tif"))
    if not tifs:
        log.warning(f"  No tiles to merge for {year}")
        return None

    mosaic = out_dir / f"naip_{year}_edmonds_4band.tif"
    vrt = year_dir / "mosaic.vrt"
    flist = year_dir / "tile_list.txt"

    with open(flist, "w") as f:
        for t in tifs:
            f.write(str(t) + "\n")

    try:
        subprocess.run(
            ["gdalbuildvrt", "-input_file_list", str(flist), str(vrt)],
            check=True, capture_output=True, text=True)

        subprocess.run([
            "gdal_translate", "-of", "GTiff",
            "-co", "COMPRESS=LZW",
            "-co", "TILED=YES",
            "-co", "BLOCKXSIZE=512",
            "-co", "BLOCKYSIZE=512",
            "-co", "BIGTIFF=IF_SAFER",
            str(vrt), str(mosaic),
        ], check=True, capture_output=True, text=True)

        sz = mosaic.stat().st_size / (1024 ** 2)
        log.info(f"  {year} mosaic: {mosaic.name} ({sz:.1f} MB)")

        # Quick band check
        try:
            gi = subprocess.run(["gdalinfo", str(mosaic)],
                                capture_output=True, text=True, timeout=15)
            if gi.returncode == 0:
                for line in gi.stdout.split("\n"):
                    s = line.strip()
                    if any(k in s.lower() for k in ["size is", "band ", "pixel size"]):
                        log.info(f"    {s}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return mosaic

    except FileNotFoundError:
        log.error(
            "GDAL not found! Tiles saved individually. Merge later:\n"
            f"  gdalbuildvrt {vrt} {year_dir}/naip_{year}_r*_c*.tif\n"
            f"  gdal_translate -of GTiff -co COMPRESS=LZW -co BIGTIFF=IF_SAFER "
            f"{vrt} {mosaic}")
        return None
    except subprocess.CalledProcessError as e:
        log.error(f"GDAL merge failed for {year}: {e.stderr}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download NAIP 4-band imagery for Edmonds, WA (all years 2013–present).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python naip_edmonds_downloader.py                    # all years
  python naip_edmonds_downloader.py --year 2023        # single year
  python naip_edmonds_downloader.py --years 2019 2021  # specific years
  python naip_edmonds_downloader.py --test --year 2021 # test area
  python naip_edmonds_downloader.py --list-years       # show available years
  python naip_edmonds_downloader.py --workers 2        # parallel downloads
        """,
    )
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--year", type=int, default=None,
                        help="Single year to download")
    parser.add_argument("--years", type=int, nargs="+", default=None,
                        help="Multiple specific years")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--no-merge", action="store_true")
    parser.add_argument("--test", action="store_true",
                        help="Small test area (~1 km²)")
    parser.add_argument("--list-years", action="store_true",
                        help="List available years and exit")
    parser.add_argument("--xmin", type=float, default=None)
    parser.add_argument("--ymin", type=float, default=None)
    parser.add_argument("--xmax", type=float, default=None)
    parser.add_argument("--ymax", type=float, default=None)

    args = parser.parse_args()

    if args.list_years:
        print("\nAvailable WA NAIP 4-band years:")
        print(f"{'Year':<6} {'Native Resolution':<40}")
        print("-" * 46)
        for y in ALL_YEARS:
            print(f"{y:<6} {YEAR_INFO[y]}")
        print(f"\nAll served at {SERVICE_PIXEL_SIZE} m via the USGS ImageServer.")
        print("2025 acquisition planned but not yet available.\n")
        return

    # Determine years
    if args.year:
        years = [args.year]
    elif args.years:
        years = sorted(args.years)
    else:
        years = ALL_YEARS

    # Validate
    for y in years:
        if y not in ALL_YEARS:
            log.warning(f"Year {y} not in known list {ALL_YEARS}. "
                        f"Will attempt anyway (may fail if no data).")

    # Determine extent
    if args.test:
        extent = TEST_EXTENT.copy()
    else:
        extent = EDMONDS_EXTENT.copy()

    for attr in ("xmin", "ymin", "xmax", "ymax"):
        val = getattr(args, attr)
        if val is not None:
            extent[attr] = val

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("NAIP 4-Band Multi-Year Downloader — Edmonds, WA")
    log.info("=" * 60)
    log.info(f"Source:   USGS National Map NAIP ImageServer")
    log.info(f"Years:    {', '.join(str(y) for y in years)}")
    log.info(f"Bands:    4 (R, G, B, NIR)")
    log.info(f"Served:   {SERVICE_PIXEL_SIZE} m/px  |  Format: GeoTIFF")
    log.info(f"Chunk:    {CHUNK_PX}x{CHUNK_PX} px ({CHUNK_GROUND_M:.0f} m)")
    log.info(f"Workers:  {args.workers}")
    log.info(f"Output:   {out_dir}")
    log.info(f"Extent:   {extent['xmin']:.2f}, {extent['ymin']:.2f} → "
             f"{extent['xmax']:.2f}, {extent['ymax']:.2f}")
    if args.test:
        log.info("Mode:     TEST (small area)")
    log.info("")

    # Compute grid (same for all years — extent doesn't change)
    tiles, n_cols, n_rows = compute_grid(extent)
    total_tiles = len(tiles) * len(years)

    est_mb_per_tile = 4 * CHUNK_PX * CHUNK_PX * 0.5 / (1024 ** 2)
    est_total_mb = total_tiles * est_mb_per_tile
    log.info(f"Grid:     {n_cols} x {n_rows} = {len(tiles)} tiles/year")
    log.info(f"Total:    {total_tiles} tiles across {len(years)} years "
             f"(~{est_total_mb:.0f} MB est.)")
    log.info("")

    # Download each year
    for i, year in enumerate(years):
        log.info(f"[{i+1}/{len(years)}] Downloading NAIP {year} — "
                 f"{YEAR_INFO.get(year, 'unknown resolution')}")
        download_year(year, tiles, out_dir, args.workers)

        if not args.no_merge:
            merge_year(out_dir, year)

        if i < len(years) - 1:
            log.info("")

    # Summary
    log.info("")
    log.info("=" * 60)
    log.info("Summary")
    log.info("=" * 60)
    for year in years:
        mosaic = out_dir / f"naip_{year}_edmonds_4band.tif"
        if mosaic.exists():
            sz = mosaic.stat().st_size / (1024 ** 2)
            log.info(f"  {year}: {mosaic.name} ({sz:.1f} MB)")
        else:
            year_dir = out_dir / str(year)
            count = len(list(year_dir.glob("naip_*.tif"))) if year_dir.exists() else 0
            log.info(f"  {year}: {count} tiles (not merged)")

    log.info("")
    log.info("Done!")


if __name__ == "__main__":
    main()

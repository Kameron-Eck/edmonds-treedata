"""
clip_study_area.py — Extract study area clips from all pipeline imagery
========================================================================
Clips a small geographic window from each year's raw imagery for use
in co-registration testing. Run registration on clips first to validate
the pipeline works before committing to full-image processing.

USAGE (Colab cell):
-------------------
    %run /content/drive/MyDrive/treedata/Scripts/clip_study_area.py

OUTPUT:
-------
    /treedata/clips/{year}_edmonds_clip.tif   one per year
    All clips share the same CRS, resolution, and geographic extent.
    King County years are upsampled to 7.62 cm during clipping.
"""

import time
from pathlib import Path
import numpy as np
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────
DRIVE_BASE   = Path("/content/drive/MyDrive/treedata")
from pipeline_config import (
    DRIVE_BASE, IMAGERY_DIR, CLIPS_DIR,
    raw_path, registered_path, REFERENCE_YEAR,
)

REFERENCE_YEAR    = 2020
ALL_YEARS         = [2013, 2015, 2017, 2019, 2020, 2021, 2022, 2023, 2024]
KING_COUNTY_YEARS = {2013, 2015, 2019, 2021, 2023}

# Study area centre in EPSG:3857 (metres)
CENTRE_X = -13_623_156.8
CENTRE_Y =  6_074_415.6

# Buffer in metres — 1500 m = 3 km x 3 km clip
# Enough buildings for control point matching, small enough to be fast
BUFFER_M = 800


def clip_year(year, centre_x, centre_y, buffer_m, ref_res):
    import rasterio
    import rasterio.warp
    import rasterio.windows
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds

    src_path = raw_path(year)
    dst_path = CLIPS_DIR   / f"{year}_edmonds_clip.tif"

    if dst_path.exists():
        size_mb = dst_path.stat().st_size / 1e6
        print(f"  {year}: clip already exists ({size_mb:.0f} MB) — skipping")
        return dst_path

    if not src_path.exists():
        print(f"  {year}: source not found — {src_path.name}")
        return None

    x_min = centre_x - buffer_m
    x_max = centre_x + buffer_m
    y_min = centre_y - buffer_m
    y_max = centre_y + buffer_m

    out_w = int(round((x_max - x_min) / ref_res))
    out_h = int(round((y_max - y_min) / ref_res))
    out_transform = from_bounds(x_min, y_min, x_max, y_max, out_w, out_h)

    with rasterio.open(src_path) as src:
        src_res  = abs(src.transform.a)
        action   = f"upsample {src_res:.4f}m -> {ref_res:.4f}m" \
                   if src_res > ref_res + 0.001 else "native res"
        n_bands  = src.count
        src_size_mb = src_path.stat().st_size / 1e6

        print(f"  {year}: {out_w}x{out_h} px  [{action}]  "
              f"source={src_size_mb:.0f} MB")

        profile = src.profile.copy()
        profile.pop("photometric", None)
        profile.update(
            width      = out_w,
            height     = out_h,
            transform  = out_transform,
            compress   = "lzw",
            predictor  = 2,
            tiled      = True,
            blockxsize = 256,
            blockysize = 256,
            bigtiff    = "IF_SAFER",
        )

        t0 = time.time()
        with rasterio.open(dst_path, "w", **profile) as dst:
            for band_i in tqdm(range(1, n_bands + 1),
                               desc=f"    {year}",
                               unit="band",
                               ncols=60,
                               leave=True):
                band_t = time.time()
                rasterio.warp.reproject(
                    source        = rasterio.band(src, band_i),
                    destination   = rasterio.band(dst, band_i),
                    src_transform = src.transform,
                    src_crs       = src.crs,
                    dst_transform = out_transform,
                    dst_crs       = src.crs,
                    resampling    = Resampling.cubic,
                )
                print(f"    band {band_i}/{n_bands} done  "
                      f"({time.time()-band_t:.1f}s)", flush=True)

        elapsed  = time.time() - t0
        size_mb  = dst_path.stat().st_size / 1e6
        print(f"  {year}: written {dst_path.name}  "
              f"({size_mb:.0f} MB  {elapsed:.0f}s)")
        return dst_path


def run(centre_x=CENTRE_X, centre_y=CENTRE_Y, buffer_m=BUFFER_M):
    import rasterio

    print("=" * 60)
    print("  CLIP STUDY AREA")
    print("=" * 60)
    print(f"  Centre  : ({centre_x:.1f}, {centre_y:.1f}) EPSG:3857")
    print(f"  Buffer  : {buffer_m:.0f} m  ({2*buffer_m/1000:.1f} km x {2*buffer_m/1000:.1f} km)")
    print(f"  Output  : {CLIPS_DIR}")
    print()

    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    ref_path = raw_path(REFERENCE_YEAR)
    if not ref_path.exists():
        print(f"  Reference not found: {ref_path}")
        return

    with rasterio.open(ref_path) as src:
        ref_res = abs(src.transform.a)
    print(f"  Reference resolution: {ref_res:.4f} m/px")

    # Estimate output size per year
    out_px  = int(round(2 * buffer_m / ref_res))
    est_mb  = (out_px * out_px * 3) / 1e6   # uint8 uncompressed estimate
    print(f"  Estimated clip size : {out_px}x{out_px} px  "
          f"~{est_mb:.0f} MB uncompressed per year")
    print(f"  Years to clip       : {len(ALL_YEARS)}")
    print()

    t_total = time.time()
    results = []
    for i, year in enumerate(ALL_YEARS):
        print(f"[{i+1}/{len(ALL_YEARS)}] ── {year} ──────────────────────")
        t_year = time.time()
        dst = clip_year(year, centre_x, centre_y, buffer_m, ref_res)
        elapsed = time.time() - t_year
        results.append((year, dst, elapsed))
        print()

    total_elapsed = time.time() - t_total

    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    ok    = [(y, p, e) for y, p, e in results if p and p.exists()]
    fails = [(y, p, e) for y, p, e in results if not p or not p.exists()]

    for year, path, elapsed in ok:
        size_mb = path.stat().st_size / 1e6
        print(f"  {year}  OK  {size_mb:.0f} MB  {elapsed:.0f}s")
    for year, _, elapsed in fails:
        print(f"  {year}  MISSING")

    print(f"\n  {len(ok)}/{len(ALL_YEARS)} clips complete  "
          f"total time: {total_elapsed/60:.1f} min")
    print()
    print("  Next — run registration on clips:")
    print("    import sys")
    print("    sys.path.insert(0, '/content/drive/MyDrive/treedata/Scripts')")
    print("    import coregister_imagery")
    print("    coregister_imagery.run_clips()")


if __name__ == "__main__":
    import sys
    sys.argv = sys.argv[:1]
    run()
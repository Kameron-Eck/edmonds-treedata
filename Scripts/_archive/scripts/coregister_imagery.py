"""
Co-Registration Script — Edmonds Temporal Pipeline (Tiled)
===========================================================
Warps historical imagery into 2020 coordinate space using building
footprints as ground control anchors.

Handles two imagery sources with different native resolutions:
  City of Edmonds  — 0.0746 m (7.62 cm)  — 2017, 2020, 2022, 2024
  King County      — 0.1493 m (14.92 cm) — 2013, 2015, 2019, 2021, 2023

King County years are upsampled to 0.0746 m (bicubic) before control
point extraction so both sources share a common pixel grid. Upsampled
files are cached in UPSAMPLE_DIR and reused on subsequent runs.

Fully tiled — never loads a full image into memory.
Parallelised across 6 CPU cores for tile processing.
Designed for Colab Pro+ (52–170 GB RAM, 6 cores).

Peak RAM per worker : ~600 MB  (one 8192×8192 tile, 3-band uint8)
Total peak RAM      : ~4 GB    (6 workers simultaneously)
Expected runtime    : 20–40 min per year (after upsample)
Upsample time       : ~5–10 min per King County year

COLAB SETUP
-----------
    from google.colab import drive
    drive.mount('/content/drive')
    !pip install rasterio geopandas numpy scipy scikit-image opencv-python-headless tqdm -q

Then run:
    %run coregister_imagery.py              # all target years
    %run coregister_imagery.py --year 2017  # single year test
    %run coregister_imagery.py --year 2013 --skip-coreg  # upsample only, skip coreg

OUTPUT
------
    /upsample/{stem}_upsampled.tif             King County years resampled to 7.62 cm
    /registered/{year}_edmonds_registered.tif  warped imagery in 2020 space
    /registered/registration_log.csv           RMSE, transform, pass/fail per year

APPROACH
--------
Step 0 — Upsample (King County years only):
  Reproject from 0.1493 m to 0.0746 m using cubic resampling.
  Snaps to the reference pixel grid so tile windows align exactly.
  Skipped for City of Edmonds years (already at 0.0746 m).
  Cached — will not re-run if output already exists.

Phase A — Control point extraction (tiled, parallel):
  1. Divide city into TILE_SIZE x TILE_SIZE pixel tiles (~494 tiles)
  2. Per tile (6 workers in parallel):
     a. Load tile window from reference (2020) and target imagery
     b. Burn building footprints intersecting this tile → binary mask
     c. Canny edge detection on mask
     d. Harris corner detection on edges
     e. NCC patch matching within SEARCH_RADIUS pixels
     f. Return matched pairs in full-image pixel coordinates
  3. Aggregate pairs from all tiles → global control point set

Phase B — Transform fitting (global, fast):
  4. RANSAC affine on full control point set
  5. If RMSE > RMSE_AFFINE_ACCEPT: thin-plate spline fallback
  6. If RMSE > RMSE_TPS_ACCEPT: save affine fallback for QGIS inspection

Phase C — Warping (tiled, sequential):
  7. Open output GeoTIFF for incremental writing
  8. Per tile: read source window → apply inverse transform → write output
  9. Peak RAM during warp = 2 tiles (~1.2 GB)

NOTE: If ArcGIS inspection confirms imagery is already well-aligned,
use --skip-coreg to upsample only and copy directly to /registered/
without applying a warp transform.
"""

import argparse
import csv
import multiprocessing as mp
import shutil
import sys
import subprocess as _subprocess
import warnings
from pathlib import Path

import cv2
import geopandas as gpd
import numpy as np
import rasterio
import rasterio.features
import rasterio.warp
import rasterio.windows
from rasterio.enums import Resampling
from scipy.interpolate import RBFInterpolator
from skimage import feature, filters
from shapely.geometry import box as _shapely_box
from tqdm import tqdm

import psutil as _psutil
warnings.filterwarnings("ignore")


# ══════════════════════════════════════════════════════════════
# MEMORY TRACKING
# ══════════════════════════════════════════════════════════════

def mem(label: str = "") -> float:
    """
    Print current RAM usage with an optional label.
    Returns used GB for programmatic checks.
    """
    vm      = _psutil.virtual_memory()
    used_gb = vm.used  / 1e9
    total_gb= vm.total / 1e9
    pct     = vm.percent
    bar_len = 20
    filled  = int(bar_len * pct / 100)
    bar     = "█" * filled + "░" * (bar_len - filled)
    tag     = f"  [{label}]" if label else ""
    print(f"  MEM{tag}: {used_gb:.1f}/{total_gb:.1f} GB  "
          f"[{bar}] {pct:.1f}%", flush=True)
    return used_gb


# ══════════════════════════════════════════════════════════════
# PAGE CACHE MANAGEMENT
# ══════════════════════════════════════════════════════════════

import ctypes as _ctypes

def _drop_page_cache_file(path: Path):
    """Drop OS page cache for a specific file via posix_fadvise."""
    try:
        libc = _ctypes.CDLL("libc.so.6", use_errno=True)
        with open(path, "rb") as fh:
            libc.posix_fadvise(fh.fileno(), 0, 0, 4)  # POSIX_FADV_DONTNEED
    except Exception:
        pass

def drop_all_page_cache(silent: bool = False):
    """
    Drop all page cache system-wide.
    Colab runs as root — drop_caches frees buffer/cache immediately.
    silent=True skips sync (safe for in-loop calls — rasterio write calls
    already guarantee data integrity) and suppresses printed output.
    sync is only needed before the verbose end-of-band drop.
    """
    try:
        if not silent:
            _subprocess.run(["sync"], check=False, timeout=30)
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("1\n")   # 1 = page cache only (faster than 3)
        if not silent:
            vm = _psutil.virtual_memory()
            print(f"  Page cache dropped — RAM now: "
                  f"{vm.used/1e9:.1f}/{vm.total/1e9:.1f} GB ({vm.percent:.1f}%)",
                  flush=True)
    except Exception as e:
        if not silent:
            print(f"  Could not drop page cache: {e}", flush=True)


# ══════════════════════════════════════════════════════════════
# TIMING
# ══════════════════════════════════════════════════════════════

import time as _time_module

_TIMER_STACK: list = []   # stack of (label, t0) for nested timers
_TIMER_LOG:   list = []   # flat list of all completed intervals


def tick(label: str = "") -> float:
    t0 = _time_module.time()
    _TIMER_STACK.append((label, t0))
    return t0


def tock(label: str = "", unit: str = "auto") -> float:
    t1 = _time_module.time()
    if not _TIMER_STACK:
        print(f"  TIMER: tock() called with no matching tick()")
        return 0.0

    stored_label, t0 = _TIMER_STACK.pop()
    display_label    = label or stored_label or "unnamed"
    elapsed_s        = t1 - t0

    if unit == "auto":
        if elapsed_s < 1.0:
            disp = f"{elapsed_s*1000:.0f} ms"
        elif elapsed_s < 120:
            disp = f"{elapsed_s:.1f} s"
        else:
            disp = f"{elapsed_s/60:.1f} min"
    elif unit == "ms":
        disp = f"{elapsed_s*1000:.0f} ms"
    elif unit == "min":
        disp = f"{elapsed_s/60:.2f} min"
    else:
        disp = f"{elapsed_s:.2f} s"

    depth  = len(_TIMER_STACK)
    indent = "  " + "  " * depth
    bar_w  = 20
    filled = min(bar_w, int(bar_w * elapsed_s / 300))
    bar    = "▓" * filled + "░" * (bar_w - filled)

    print(f"{indent}⏱  {display_label:<40}  {disp:>10}  [{bar}]", flush=True)
    _TIMER_LOG.append({"label": display_label, "elapsed_s": elapsed_s})
    return elapsed_s


def timer_summary():
    """Print a sorted summary of all recorded intervals."""
    if not _TIMER_LOG:
        print("  No timer data recorded.")
        return
    sorted_log = sorted(_TIMER_LOG, key=lambda x: x["elapsed_s"], reverse=True)
    total = sum(x["elapsed_s"] for x in sorted_log)
    print("\n" + "═"*60)
    print(f"  TIMING SUMMARY  (total tracked: {total/60:.1f} min)")
    print("═"*60)
    for entry in sorted_log:
        e   = entry["elapsed_s"]
        pct = 100 * e / total if total > 0 else 0
        bar = "▓" * int(20 * pct / 100) + "░" * (20 - int(20 * pct / 100))
        if e < 1:
            disp = f"{e*1000:.0f} ms"
        elif e < 120:
            disp = f"{e:.1f} s"
        else:
            disp = f"{e/60:.1f} min"
        print(f"  {entry['label']:<42}  {disp:>8}  {pct:5.1f}%  [{bar}]")
    print("═"*60)


# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")
BUILDINGS_JSON = DRIVE_BASE / "building_footprints" / "data.json"
IMAGERY_DIR    = DRIVE_BASE / "Full_Image/Pipeline Imagery"
UPSAMPLE_DIR   = Path("/content/upsampled")
LOCAL_SRC_DIR  = Path("/content/source_imagery")
OUTPUT_DIR     = Path("/content/registered")
DRIVE_OUTPUT   = IMAGERY_DIR / "registered"
DRIVE_UPSAMPLE = IMAGERY_DIR / "upsample"
DRIVE_TEST_DIR = IMAGERY_DIR / "test_crops"
LOG_PATH            = OUTPUT_DIR / "registration_log.csv"
CONTROL_POINTS_DIR = Path("/content/control_points")
TEST_OUTPUT_DIR    = Path("/content/test_registered")
TEST_UPSAMPLE_DIR  = Path("/content/test_upsampled")
TEST_SRC_DIR       = Path("/content/test_source")

REFERENCE_YEAR = 2020

IMAGERY_CATALOG = {
    2013: "2013_king_rgb.tif",
    2015: "2015_king_rgb.tif",
    2017: "2017_coe_rgb.tif",
    2019: "2019_king_rgb.tif",
    2020: "2020_coe_rgb.tif",
    2021: "2021_king_rgb.tif",
    2022: "2022_coe_rgb.tif",
    2023: "2023_king_rgb.tif",
    2024: "2024_coe_rgb.tif",
    "2016*": "2016_snoh_rgbi.tif",
    "2019*": "2019_naip_rgbi.tif",
    "2021*": "2021_snoh_rgbi.tif",
    "2022*": "2022_naip_rgbi.tif",
}

TARGET_YEARS = [2013, 2015, 2017, 2019, 2021, 2022, 2023, 2024, ]

RESOLUTION_TOLERANCE = 0.005
_YEAR_RESOLUTION_CACHE: dict = {}


def get_year_resolution(year) -> float:
    if year in _YEAR_RESOLUTION_CACHE:
        return _YEAR_RESOLUTION_CACHE[year]
    path = raw_imagery_path(year)
    if not path.exists():
        raise FileNotFoundError(f"Source imagery not found: {path}")
    with rasterio.open(path) as src:
        res = abs(src.transform.a)
    _YEAR_RESOLUTION_CACHE[year] = res
    return res


def needs_upsample(year, ref_res: float = None) -> bool:
    if ref_res is None:
        ref_res = get_year_resolution(REFERENCE_YEAR)
    year_res = get_year_resolution(year)
    return year_res > ref_res + RESOLUTION_TOLERANCE

TILE_SIZE = 8192
N_WORKERS = 6

RMSE_AFFINE_ACCEPT = 0.5
RMSE_TPS_ACCEPT    = 0.75
MIN_MATCHES        = 15

MATCH_PARAMS = {
    "edmonds": dict(
        canny_sigma      = 1.5,
        harris_block     = 5,
        harris_ksize     = 3,
        harris_k         = 0.05,
        harris_threshold = 0.01,
        max_corners_tile = 500,
        patch_size       = 31,
        ncc_threshold    = 0.85,
        search_radius    = 40,   # 40px * 0.0746m = 3m — covers 2m misalignment with margin
    ),
    "king_county": dict(
        canny_sigma      = 1.5,
        harris_block     = 5,
        harris_ksize     = 3,
        harris_k         = 0.05,
        harris_threshold = 0.008,
        max_corners_tile = 500,
        patch_size       = 21,
        ncc_threshold    = 0.6,
        search_radius    = 40,   # same physical window — upsampled to same pixel grid
    ),
}


# ══════════════════════════════════════════════════════════════
# PATH HELPERS
# ══════════════════════════════════════════════════════════════

def _catalog_key(year):
    if year in IMAGERY_CATALOG:
        return year
    try:
        k = int(year)
        if k in IMAGERY_CATALOG:
            return k
    except (ValueError, TypeError):
        pass
    raise KeyError(
        f"Year {year!r} not in IMAGERY_CATALOG — "
        f"valid keys: {list(IMAGERY_CATALOG.keys())}"
    )


def raw_imagery_path(year) -> Path:
    return IMAGERY_DIR / IMAGERY_CATALOG[_catalog_key(year)]

def _stem(year) -> str:
    return IMAGERY_CATALOG[_catalog_key(year)].replace(".tif", "")

def upsampled_path(year) -> Path:
    return UPSAMPLE_DIR / f"{_stem(year)}_upsampled.tif"

def output_path(year) -> Path:
    return OUTPUT_DIR / f"{_stem(year)}_registered.tif"

def needs_upsample_cached(year) -> bool:
    try:
        return needs_upsample(year)
    except Exception:
        return False


def match_params(year) -> dict:
    return MATCH_PARAMS["king_county"] if needs_upsample_cached(year) \
           else MATCH_PARAMS["edmonds"]

def metres_per_pixel(transform) -> float:
    return abs(transform.a)


# ══════════════════════════════════════════════════════════════
# STEP 0 — UPSAMPLE
# ══════════════════════════════════════════════════════════════

UPSAMPLE_CHUNK_PX  = 4096
N_UPSAMPLE_WORKERS = 3

# Stall detection: if no chunk completes within this many seconds, abort.
WORKER_STALL_TIMEOUT_S = 180   # 3 minutes


# ── Batch size for worker calls ───────────────────────────────
# Each worker processes WORKER_BATCH_SIZE output chunks per call,
# keeping the source file open and GDAL's block cache warm across
# adjacent chunks. For a 6.7x upsample, adjacent output chunks in
# the same row map to overlapping source regions — batching means
# GDAL decompresses each source block once instead of once per chunk.
# Optimal value: 8–16. Higher = more cache reuse, larger IPC payload.
WORKER_BATCH_SIZE = 10

def _do_fullband_reproject(local_src, dst_local, src_count, src_dtype,
                           src_transform, src_crs, ref_profile, dst_crs,
                           year):
    """
    Reproject all bands sequentially using full-band rasterio.warp.reproject.
    No worker pool — GDAL handles threading internally.
    Faster than chunked pool for small scale factors (≤2.5x).
    """
    import gc
    from rasterio.transform import Affine
 
    profile = ref_profile.copy()
    profile.pop("photometric", None)
    profile.update(count=src_count, dtype=src_dtype,
                   compress="lzw", predictor=2, bigtiff="IF_SAFER",
                   tiled=True, blockxsize=512, blockysize=512)
 
    src_t = Affine(*src_transform) if isinstance(src_transform, tuple) \
            else src_transform
 
    try:
        with rasterio.open(dst_local, "w", **profile) as dst:
            for band_i in tqdm(range(1, src_count + 1),
                               desc=f"  Reprojecting {year} bands"):
                tick(f"fullband reproject: band {band_i}/{src_count}")
                with rasterio.open(str(local_src)) as src:
                    rasterio.warp.reproject(
                        source        = rasterio.band(src, band_i),
                        destination   = rasterio.band(dst, band_i),
                        src_transform = src_t,
                        src_crs       = src_crs,
                        dst_transform = ref_profile["transform"],
                        dst_crs       = ref_profile["crs"],
                        resampling    = Resampling.cubic,
                    )
                tock(f"fullband reproject: band {band_i}/{src_count}")
                gc.collect()
    except Exception as e:
        if dst_local.exists():
            dst_local.unlink()
            print(f"  Partial output deleted: {dst_local.name}", flush=True)
        raise
 
    # ── Validate ──────────────────────────────────────────────
    print(f"\n  Validating output...", flush=True)
    with rasterio.open(dst_local) as check:
        assert check.width  == ref_profile["width"],  \
            f"Width mismatch: {check.width} != {ref_profile['width']}"
        assert check.height == ref_profile["height"], \
            f"Height mismatch: {check.height} != {ref_profile['height']}"
        cx  = check.width  // 2
        cy  = check.height // 2
        win = rasterio.windows.Window(cx - 256, cy - 256, 512, 512)
        s   = check.read(1, window=win)
        assert s.max() > 0, "Centre sample all zeros — output corrupt"
        print(f"  Validation OK  "
              f"({check.width}x{check.height}  {check.count} bands  "
              f"centre max={int(s.max())})", flush=True)
 
    size_gb = dst_local.stat().st_size / 1e9
    print(f"  Output: {dst_local.name}  ({size_gb:.2f} GB)", flush=True)
    mem(f"{year} after fullband reproject")
 
    # ── Copy to Drive cache ───────────────────────────────────
    dst_drive = DRIVE_UPSAMPLE / dst_local.name
    DRIVE_UPSAMPLE.mkdir(parents=True, exist_ok=True)
    print(f"\n  Copying to Drive (~{size_gb:.0f} GB)...", flush=True)
    tick("copy: upsample → Drive cache")
    shutil.copy2(dst_local, dst_drive)
    tock("copy: upsample → Drive cache")
    print(f"  Drive cache: {dst_drive.name}  "
          f"({dst_drive.stat().st_size/1e9:.2f} GB)", flush=True)
    mem(f"{year} after Drive upsample copy")

def _reproject_chunk_batch(args):
    """
    Worker: reproject a BATCH of output chunks in one call.
    Opens the source file once per batch and keeps GDAL's internal
    block cache warm across all chunks in the batch.

    Returns list of per-chunk result tuples identical to the single-
    chunk version so the parent loop needs no structural changes.
    """
    import time as _t
    import os
    import numpy as _np
    import rasterio as _rio
    import rasterio.warp as _rwarp
    from rasterio.enums import Resampling as _R
    from rasterio.transform import Affine

    (src_path_str, band_i, chunk_list,
     src_transform_tuple, src_crs_wkt, dst_crs_wkt,
     src_dtype, gdal_cachemax) = args

    # Set GDAL cache in worker — spawn workers don't inherit parent env changes
    os.environ["GDAL_CACHEMAX"] = str(gdal_cachemax)

    worker_pid = os.getpid()
    results    = []

    # Open source file once for the entire batch
    try:
        src_f = _rio.open(src_path_str)
        src_open_ok = True
    except Exception as e:
        src_open_ok = False
        src_open_err = str(e)

    src_t = Affine(*src_transform_tuple)

    for (col_off, row_off, chunk_w, chunk_h, dst_transform_tuple) in chunk_list:
        t_start  = _t.time()
        dst_t    = Affine(*dst_transform_tuple)
        dst_arr  = _np.zeros((chunk_h, chunk_w), dtype=src_dtype)
        failed   = False
        error_msg = ""
        open_ms  = 0
        proj_ms  = 0

        if not src_open_ok:
            failed    = True
            error_msg = src_open_err
        else:
            try:
                t_proj = _t.time()
                _rwarp.reproject(
                    source        = _rio.band(src_f, band_i),
                    destination   = dst_arr,
                    src_transform = src_t,
                    src_crs       = src_crs_wkt,
                    dst_transform = dst_t,
                    dst_crs       = dst_crs_wkt,
                    resampling    = _R.cubic,
                )
                proj_ms = int((_t.time() - t_proj) * 1000)
            except Exception as e:
                dst_arr[:]  = 0
                failed      = True
                error_msg   = str(e)

        total_ms = int((_t.time() - t_start) * 1000)
        results.append((
            band_i, col_off, row_off, chunk_w, chunk_h,
            dst_arr, failed, error_msg,
            worker_pid, open_ms, proj_ms, total_ms,
        ))

    if src_open_ok:
        src_f.close()

    return results


def upsample_year_from_local(year, local_src: Path, ref_profile: dict) -> Path:
    """
    Upsample a year from a LOCAL source file.

    DIAGNOSTIC VERSION — emits detailed per-chunk timing, worker health
    checks, and stall detection with explicit error messages.

    Key changes from original:
      - Uses mp.get_context("spawn") to avoid GDAL fork-mutex deadlock
      - Stall detector: if no result arrives within WORKER_STALL_TIMEOUT_S,
        terminates pool and raises with full diagnostic context
      - Per-chunk timing logged for the first N_DIAG_CHUNKS chunks to
        identify slow source regions
      - Worker PID tracking to detect silent worker exits
      - Page cache drop after Drive copy and after each band
    """
    import gc
    import os
    from rasterio.transform import Affine

    N_DIAG_CHUNKS = 20    # log per-chunk detail for first N chunks per band

    dst_local = UPSAMPLE_DIR  / f"{_stem(year)}_upsampled.tif"
    dst_drive = DRIVE_UPSAMPLE / f"{_stem(year)}_upsampled.tif"

    print(f"\n  {'─'*56}", flush=True)
    print(f"  UPSAMPLE START: {year}  →  {dst_local.name}", flush=True)
    print(f"  Source         : {local_src}  "
          f"({local_src.stat().st_size/1e9:.2f} GB)", flush=True)
    print(f"  Spawn context  : mp.get_context('spawn')  "
          f"[avoids GDAL fork-mutex]", flush=True)
    print(f"  Stall timeout  : {WORKER_STALL_TIMEOUT_S}s per chunk", flush=True)
    mem(f"{year} upsample entry")

    # ── Drive cache check ─────────────────────────────────────
    if dst_drive.exists():
        try:
            with rasterio.open(dst_drive) as check:
                valid = (check.width  == ref_profile["width"] and
                         check.height == ref_profile["height"] and
                         check.count  >= 3)
                cx  = check.width  // 2
                cy  = check.height // 2
                win = rasterio.windows.Window(cx-256, cy-256, 512, 512)
                s   = check.read(1, window=win)
            if valid and s.max() > 0:
                print(f"  Drive cache valid — copying to local: "
                      f"{dst_drive.name}", flush=True)
                if not dst_local.exists():
                    UPSAMPLE_DIR.mkdir(parents=True, exist_ok=True)
                    tick("copy: Drive cache → local")
                    shutil.copy2(dst_drive, dst_local)
                    tock("copy: Drive cache → local")
                    drop_all_page_cache()
                return dst_local
            else:
                print(f"  Drive cache corrupt — rebuilding", flush=True)
                dst_drive.unlink()
        except Exception as e:
            print(f"  Drive cache unreadable ({e}) — rebuilding", flush=True)
            if dst_drive.exists():
                dst_drive.unlink()

    UPSAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    with rasterio.open(local_src) as src_f:
        src_res       = metres_per_pixel(src_f.transform)
        ref_res       = metres_per_pixel(ref_profile["transform"])
        src_count     = src_f.count
        src_dtype     = src_f.dtypes[0]
        src_crs       = src_f.crs.to_wkt()
        src_transform = tuple(src_f.transform)
        src_w         = src_f.width
        src_h         = src_f.height

    out_w         = ref_profile["width"]
    out_h         = ref_profile["height"]
    out_transform = ref_profile["transform"]
    dst_crs       = ref_profile["crs"].to_wkt() \
                    if hasattr(ref_profile["crs"], "to_wkt") \
                    else str(ref_profile["crs"])

    chunk_mb = UPSAMPLE_CHUNK_PX ** 2 * 2 / 1e6
    total_tasks = len(make_tile_windows(out_w, out_h, UPSAMPLE_CHUNK_PX)) * src_count

    print(f"\n  Source dims    : {src_w}x{src_h} px  "
          f"{src_count} bands  dtype={src_dtype}", flush=True)
    print(f"  Output dims    : {out_w}x{out_h} px", flush=True)
    print(f"  Scale factor   : {src_res:.4f}m → {ref_res:.4f}m  "
          f"(x{src_res/ref_res:.2f})", flush=True)
    print(f"  Chunk size     : {UPSAMPLE_CHUNK_PX}px  "
          f"(~{chunk_mb:.0f} MB each)", flush=True)
    print(f"  Workers        : {N_UPSAMPLE_WORKERS}  (spawn)", flush=True)
    print(f"  Total tasks    : {total_tasks:,}  "
          f"({total_tasks//src_count:,} tiles × {src_count} bands)", flush=True)

    profile = ref_profile.copy()
    profile.pop("photometric", None)
    profile.update(count=src_count, dtype=src_dtype, compress="lzw",
                   predictor=2, bigtiff="IF_SAFER", tiled=True,
                   blockxsize=512, blockysize=512)

    chunk_windows = make_tile_windows(out_w, out_h, UPSAMPLE_CHUNK_PX)
    n_chunks      = len(chunk_windows)
    print(f"  Chunk grid     : {n_chunks} chunks per band", flush=True)

    import ctypes
    def _trim():
        gc.collect()
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass

    os.environ["GDAL_CACHEMAX"] = "256"

    # ── Choose upsample strategy based on scale factor ───────
    # For small scale factors (<=2x): GDAL's internal threading on a
    # single full-band reproject is faster than a Python worker pool.
    # Pool overhead + inter-worker CPU contention costs more than it saves.
    # For large scale factors (>2x, e.g. 6.7x Snohomish): the pool wins
    # because each output chunk maps to a small source region and workers
    # can run truly in parallel without source-block contention.
    POOL_SCALE_THRESHOLD = 2

    if src_res / ref_res <= POOL_SCALE_THRESHOLD:
        print(f"\n  Scale {src_res/ref_res:.2f}x ≤ {POOL_SCALE_THRESHOLD}x — "
              f"using single-threaded full-band reproject "
              f"(faster than pool at low scale factors)", flush=True)
        _do_fullband_reproject(
            local_src, dst_local, src_count, src_dtype,
            src_transform, src_crs, ref_profile, dst_crs, year)
        return dst_local

    print(f"\n  Scale {src_res/ref_res:.2f}x > {POOL_SCALE_THRESHOLD}x — "
          f"using worker pool (parallel chunks)", flush=True)

    failed_chunks = 0
    band_timings  = []    # list of (band_i, elapsed_s, chunks_failed)

    # ── Diagnostic: verify source file readable before spawning workers ──
    print(f"\n  [DIAG] Pre-flight source file read check...", flush=True)
    try:
        with rasterio.open(local_src) as _src_check:
            _cx = _src_check.width  // 2
            _cy = _src_check.height // 2
            _win = rasterio.windows.Window(_cx - 256, _cy - 256, 512, 512)
            _sample = _src_check.read(1, window=_win)
            print(f"  [DIAG] Source centre sample OK  "
                  f"(max={int(_sample.max())}  "
                  f"min={int(_sample.min())}  "
                  f"nonzero={int((_sample > 0).sum())})", flush=True)
    except Exception as e:
        print(f"  [DIAG] WARNING — source read check failed: {e}", flush=True)
        print(f"  [DIAG] This may cause worker hangs — proceeding anyway",
              flush=True)

    # ── Verify spawn context is available ────────────────────
    print(f"\n  [DIAG] Testing spawn worker launch...", flush=True)
    try:
        _spawn_ctx = mp.get_context("spawn")
        _test_pool = _spawn_ctx.Pool(processes=1, maxtasksperchild=None)
        _test_pool.close()
        _test_pool.join()
        print(f"  [DIAG] Spawn context OK — workers will use fresh "
              f"Python interpreters (no GDAL mutex inheritance)", flush=True)
    except Exception as e:
        print(f"  [DIAG] Spawn context FAILED: {e}", flush=True)
        print(f"  [DIAG] Falling back to default (fork) — "
              f"GDAL deadlock risk remains", flush=True)
        _spawn_ctx = mp

    try:
        # ── Pre-allocate output file ──────────────────────────
        print(f"\n  Pre-allocating output file...", flush=True)
        with rasterio.open(dst_local, "w", **profile):
            pass
        print(f"  Output file created: {dst_local.name}  "
              f"(shell allocated — bands will be written sequentially)",
              flush=True)

        # ── Process one band at a time ────────────────────────
        for band_i in range(1, src_count + 1):
            print(f"\n  {'═'*56}", flush=True)
            print(f"  BAND {band_i}/{src_count}  —  year {year}", flush=True)
            print(f"  {'═'*56}", flush=True)
            mem(f"{year} band {band_i} start")

            band_tasks = []
            for win in chunk_windows:
                dst_t = tuple(rasterio.windows.transform(win, out_transform))
                band_tasks.append((
                    win.col_off, win.row_off, win.width, win.height, dst_t
                ))

            # Group into batches — worker opens source file once per batch
            band_batches = [
                band_tasks[i:i + WORKER_BATCH_SIZE]
                for i in range(0, len(band_tasks), WORKER_BATCH_SIZE)
            ]
            batch_args = [
                (str(local_src), band_i, batch,
                 src_transform, src_crs, dst_crs,
                 src_dtype, 512)   # 512 MB GDAL cache per worker
                for batch in band_batches
            ]

            print(f"  Tasks built    : {len(band_tasks):,}  "
                  f"→ {len(band_batches):,} batches "
                  f"of {WORKER_BATCH_SIZE}", flush=True)
            print(f"  First task     : "
                  f"col_off={band_tasks[0][0]}  row_off={band_tasks[0][1]}  "
                  f"w={band_tasks[0][2]}  h={band_tasks[0][3]}", flush=True)
            print(f"  Last task      : "
                  f"col_off={band_tasks[-1][0]}  row_off={band_tasks[-1][1]}  "
                  f"w={band_tasks[-1][2]}  h={band_tasks[-1][3]}", flush=True)

            completed_band  = 0
            band_failed     = 0
            seen_pids       = set()
            chunk_times_ms  = []      # per-chunk wall times for diagnostics
            last_progress_t = _time_module.time()
            band_t0         = _time_module.time()

            tick(f"band {band_i}/{src_count}")

            print(f"\n  Launching pool (spawn, {N_UPSAMPLE_WORKERS} workers, "
                  f"no recycle)...", flush=True)

            with rasterio.open(dst_local, "r+") as dst:
                with _spawn_ctx.Pool(
                        processes=N_UPSAMPLE_WORKERS,
                        maxtasksperchild=None) as pool:

                    print(f"  Pool launched — submitting {len(band_batches):,} "
                          f"batches via imap_unordered...", flush=True)

                    async_iter = pool.imap_unordered(
                        _reproject_chunk_batch, batch_args, chunksize=1)

                    pbar = tqdm(
                        total=len(band_tasks),
                        desc=f"  band {band_i} chunks",
                        mininterval=10,
                        miniters=50,
                    )

                    while completed_band < len(band_tasks):

                        # ── Stall detector ────────────────────
                        wait_s = _time_module.time() - last_progress_t
                        if wait_s > WORKER_STALL_TIMEOUT_S:
                            pool.terminate()
                            pool.join()
                            pbar.close()
                            print(f"\n  {'!'*60}", flush=True)
                            print(f"  STALL DETECTED — no result for "
                                  f"{wait_s:.0f}s", flush=True)
                            print(f"  Band            : {band_i}/{src_count}",
                                  flush=True)
                            print(f"  Progress        : "
                                  f"{completed_band}/{len(band_tasks)}  "
                                  f"({100*completed_band/len(band_tasks):.1f}%)",
                                  flush=True)
                            print(f"  Seen worker PIDs: {sorted(seen_pids)}",
                                  flush=True)
                            if chunk_times_ms:
                                first10 = chunk_times_ms[:10]
                                last10  = chunk_times_ms[-10:]
                                print(f"  First 10 chunks : "
                                      f"avg={sum(first10)//len(first10)}ms",
                                      flush=True)
                                print(f"  Last 10 chunks  : "
                                      f"avg={sum(last10)//len(last10)}ms",
                                      flush=True)
                            mem(f"{year} band {band_i} at stall")
                            print(f"  {'!'*60}", flush=True)
                            raise RuntimeError(
                                f"Upsample stalled for {year} band {band_i} "
                                f"at chunk {completed_band}/{len(band_tasks)} "
                                f"({100*completed_band/len(band_tasks):.1f}%)"
                            )

                        # ── Fetch next batch result ───────────
                        try:
                            batch_results = next(async_iter)
                        except StopIteration:
                            break
                        except Exception as fetch_err:
                            print(f"\n  [DIAG] imap_unordered raised: "
                                  f"{fetch_err}", flush=True)
                            completed_band += WORKER_BATCH_SIZE
                            band_failed    += WORKER_BATCH_SIZE
                            pbar.update(WORKER_BATCH_SIZE)
                            last_progress_t = _time_module.time()
                            continue

                        last_progress_t = _time_module.time()

                        # ── Process each chunk in the batch ───
                        for result in batch_results:
                            (b_i, col_off, row_off, cw, ch,
                             arr, failed, error_msg,
                             worker_pid, open_ms, proj_ms, total_ms) = result

                            seen_pids.add(worker_pid)
                            chunk_times_ms.append(total_ms)

                            # Per-chunk diag for first N chunks
                            if completed_band < N_DIAG_CHUNKS:
                                status = "FAIL" if failed else "ok"
                                print(f"  [DIAG] chunk {completed_band:>4}  "
                                      f"col={col_off:>6}  row={row_off:>6}  "
                                      f"pid={worker_pid}  "
                                      f"open={open_ms}ms  "
                                      f"proj={proj_ms}ms  "
                                      f"total={total_ms}ms  "
                                      f"[{status}]"
                                      + (f"  ERR: {error_msg}" if failed else ""),
                                      flush=True)
                            elif completed_band == N_DIAG_CHUNKS:
                                print(f"  [DIAG] Per-chunk logging ends at "
                                      f"chunk {N_DIAG_CHUNKS} — "
                                      f"slow chunks (>100ms) will still print, "
                                      f"summary every 200 chunks",
                                      flush=True)

                            # Log any slow chunk
                            if completed_band >= N_DIAG_CHUNKS and total_ms > 100:
                                print(f"  [SLOW] chunk {completed_band:>4}  "
                                      f"col={col_off:>6}  row={row_off:>6}  "
                                      f"pid={worker_pid}  "
                                      f"open={open_ms}ms  "
                                      f"proj={proj_ms}ms  "
                                      f"total={total_ms}ms",
                                      flush=True)

                            # 200-chunk summary with histogram
                            if completed_band > 0 and completed_band % 200 == 0:
                                elapsed = _time_module.time() - band_t0
                                rate    = completed_band / elapsed if elapsed > 0 else 0
                                eta_s   = (len(band_tasks) - completed_band) / rate \
                                          if rate > 0 else 0
                                recent  = chunk_times_ms[-200:]
                                avg_ms  = sum(recent) // len(recent) if recent else 0
                                max_ms  = max(recent) if recent else 0
                                buckets = {"<20ms": 0, "20-100ms": 0,
                                           "100ms-1s": 0, ">1s": 0}
                                for t in recent:
                                    if   t < 20:   buckets["<20ms"]     += 1
                                    elif t < 100:  buckets["20-100ms"]  += 1
                                    elif t < 1000: buckets["100ms-1s"]  += 1
                                    else:          buckets[">1s"]        += 1
                                hist_str = "  ".join(
                                    f"{k}:{v}" for k, v in buckets.items())
                                print(f"\n  [DIAG] Chunk {completed_band:>4}/"
                                      f"{len(band_tasks)}  "
                                      f"({100*completed_band/len(band_tasks):.1f}%)  "
                                      f"rate={rate:.1f}/s  "
                                      f"ETA={eta_s/60:.1f}min  "
                                      f"avg={avg_ms}ms  max={max_ms}ms  "
                                      f"workers={len(seen_pids)}  "
                                      f"failed={band_failed}",
                                      flush=True)
                                print(f"  [HIST] last 200: {hist_str}",
                                      flush=True)
                                mem(f"{year} band {band_i} chunk {completed_band}")

                            # Write chunk
                            win = rasterio.windows.Window(
                                col_off, row_off, cw, ch)
                            try:
                                dst.write(arr, band_i, window=win)
                            except Exception as write_err:
                                print(f"  [DIAG] WRITE ERROR chunk "
                                      f"{completed_band}: {write_err}",
                                      flush=True)
                                band_failed += 1

                            if failed:
                                band_failed += 1
                                if error_msg:
                                    print(f"  [DIAG] Worker error chunk "
                                          f"{completed_band}: {error_msg}",
                                          flush=True)

                            del arr
                            del result
                            completed_band += 1
                            pbar.update(1)
                            failed_chunks += band_failed

                        if completed_band % 100 == 0:
                            _trim()

                    pbar.close()

            # ── Band complete ─────────────────────────────────
            band_elapsed = tock(f"band {band_i}/{src_count}")
            band_timings.append((band_i, band_elapsed, band_failed))

            print(f"\n  Band {band_i} complete:", flush=True)
            print(f"    Chunks done   : {completed_band}/{len(band_tasks)}",
                  flush=True)
            print(f"    Failed chunks : {band_failed}", flush=True)
            print(f"    Elapsed       : {band_elapsed/60:.1f} min", flush=True)
            print(f"    Unique PIDs   : {len(seen_pids)}  "
                  f"({sorted(seen_pids)})", flush=True)
            if chunk_times_ms:
                print(f"    Chunk timing  : "
                      f"min={min(chunk_times_ms)}ms  "
                      f"max={max(chunk_times_ms)}ms  "
                      f"mean={sum(chunk_times_ms)//len(chunk_times_ms)}ms",
                      flush=True)
                # Slowdown detection: compare first and last quartile
                q = max(1, len(chunk_times_ms) // 4)
                q1_avg = sum(chunk_times_ms[:q]) // q
                q4_avg = sum(chunk_times_ms[-q:]) // q
                ratio  = q4_avg / q1_avg if q1_avg > 0 else 0
                print(f"    Q1 avg        : {q1_avg}ms", flush=True)
                print(f"    Q4 avg        : {q4_avg}ms  "
                      f"(ratio {ratio:.1f}x — "
                      + ("⚠ SLOWDOWN DETECTED" if ratio > 3.0 else "normal")
                      + ")", flush=True)

            # ── Drop page cache between bands ─────────────────
            # Note: /proc/sys/vm/drop_caches is read-only on Colab —
            # posix_fadvise on the output file still works and is sufficient.
            print(f"\n  Dropping page cache after band {band_i}...", flush=True)
            _drop_page_cache_file(dst_local)
            _trim()
            mem(f"{year} band {band_i} done")

        # ── All bands complete ────────────────────────────────
        print(f"\n  {'═'*56}", flush=True)
        print(f"  ALL BANDS COMPLETE — {year}", flush=True)
        print(f"  {'═'*56}", flush=True)
        print(f"  Band timing summary:", flush=True)
        for bi, be, bf in band_timings:
            print(f"    Band {bi}: {be/60:.1f} min  "
                  f"({bf} failed chunks)", flush=True)
        if failed_chunks > 0:
            n_total = n_chunks * src_count
            print(f"\n  Total failed chunks: {failed_chunks}/{n_total}  "
                  f"({100*failed_chunks/n_total:.1f}%)", flush=True)

    except Exception as e:
        if dst_local.exists():
            dst_local.unlink()
            print(f"  Partial output deleted: {dst_local.name}", flush=True)
        raise RuntimeError(f"Upsample failed for {year}: {e}") from e

    gc.collect()
    mem(f"{year} after pool gc")

    # ── Validate ──────────────────────────────────────────────
    print(f"\n  Validating output...", flush=True)
    with rasterio.open(dst_local) as check:
        assert check.width  == ref_profile["width"],  \
            f"Width mismatch: {check.width} != {ref_profile['width']}"
        assert check.height == ref_profile["height"], \
            f"Height mismatch: {check.height} != {ref_profile['height']}"
        cx  = check.width  // 2
        cy  = check.height // 2
        win = rasterio.windows.Window(cx-256, cy-256, 512, 512)
        s   = check.read(1, window=win)
        assert s.max() > 0, "Centre sample all zeros — output corrupt"
        print(f"  Validation OK  "
              f"({check.width}x{check.height}  {check.count} bands  "
              f"centre max={int(s.max())})", flush=True)

    size_gb = dst_local.stat().st_size / 1e9
    print(f"  Output: {dst_local.name}  ({size_gb:.2f} GB)", flush=True)
    mem(f"{year} after upsample validated")

    # ── Copy to Drive cache ───────────────────────────────────
    DRIVE_UPSAMPLE.mkdir(parents=True, exist_ok=True)
    print(f"\n  Copying to Drive (~{size_gb:.0f} GB)...", flush=True)
    tick("copy: upsample → Drive cache")
    shutil.copy2(dst_local, dst_drive)
    tock("copy: upsample → Drive cache")
    drop_all_page_cache()
    print(f"  Drive cache: {dst_drive.name}  "
          f"({dst_drive.stat().st_size/1e9:.2f} GB)", flush=True)
    mem(f"{year} after Drive upsample copy")

    return dst_local


def upsample_year(year, ref_profile: dict) -> Path:
    """
    Resample a King County year from 0.1493 m to the reference pixel
    grid (0.0746 m, EPSG:3857) using cubic resampling.
    """
    src_path = raw_imagery_path(year)
    dst_path = upsampled_path(year)

    if dst_path.exists():
        try:
            with rasterio.open(dst_path) as check:
                valid = (
                    check.width  == ref_profile["width"]  and
                    check.height == ref_profile["height"] and
                    check.count  >= 3
                )
            size_gb = dst_path.stat().st_size / 1e9
            import numpy as _np
            with rasterio.open(dst_path) as check:
                cx = check.width  // 2
                cy = check.height // 2
                win = rasterio.windows.Window(cx - 256, cy - 256, 512, 512)
                sample = check.read(1, window=win)
            data_ok = sample.max() > 0
            if valid and size_gb > 0.5 and data_ok:
                print(f"  Upsampled file valid — skipping: "
                      f"{dst_path.name}  ({size_gb:.2f} GB)", flush=True)
                return dst_path
            else:
                reason = "empty data" if not data_ok else f"size={size_gb:.2f} GB"
                print(f"  Upsampled file corrupt ({reason}) — rebuilding",
                      flush=True)
                dst_path.unlink()
        except Exception as e:
            print(f"  Upsampled file unreadable ({e}) — rebuilding", flush=True)
            dst_path.unlink()

    UPSAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    with rasterio.open(src_path) as src:
        src_res   = metres_per_pixel(src.transform)
        ref_res   = metres_per_pixel(ref_profile["transform"])
        src_count = src.count
        src_dtype = src.dtypes[0]
        src_crs   = src.crs
        src_transform = src.transform

    print(f"  Upsampling {year}: {src_res:.4f} m → {ref_res:.4f} m  "
          f"(scale x{src_res/ref_res:.2f})  cubic resampling", flush=True)

    profile = ref_profile.copy()
    profile.pop("photometric", None)
    profile.update(
        count      = src_count,
        dtype      = src_dtype,
        compress   = "lzw",
        predictor  = 2,
        bigtiff    = "IF_SAFER",
        tiled      = True,
        blockxsize = 512,
        blockysize = 512,
    )

    try:
        with rasterio.open(dst_path, "w", **profile) as dst:
            for band_i in tqdm(range(1, src_count + 1),
                               desc=f"  Upsampling {year} bands"):
                with rasterio.open(src_path) as src:
                    rasterio.warp.reproject(
                        source        = rasterio.band(src, band_i),
                        destination   = rasterio.band(dst, band_i),
                        src_transform = src_transform,
                        src_crs       = src_crs,
                        dst_transform = ref_profile["transform"],
                        dst_crs       = ref_profile["crs"],
                        resampling    = Resampling.cubic,
                    )
    except Exception as e:
        if dst_path.exists():
            dst_path.unlink()
            print(f"  Partial output deleted: {dst_path.name}", flush=True)
        raise RuntimeError(f"Upsample failed for {year}: {e}") from e

    with rasterio.open(dst_path) as check:
        assert check.width  == ref_profile["width"]
        assert check.height == ref_profile["height"]

    size_gb = dst_path.stat().st_size / 1e9
    assert size_gb > 0.5, f"Output too small: {size_gb:.2f} GB"
    print(f"  Upsampled and validated: {dst_path.name}  "
          f"({size_gb:.2f} GB)", flush=True)
    return dst_path


def copy_source_to_local(year) -> Path:
    """
    Copy the raw source TIF from Drive to local Colab disk before upsampling.
    Drops page cache after copy to prevent RAM inflation.
    """
    src_drive = raw_imagery_path(year)
    dst_local = LOCAL_SRC_DIR / IMAGERY_CATALOG[_catalog_key(year)]

    if dst_local.exists():
        size_gb = dst_local.stat().st_size / 1e9
        if size_gb > 1.0:
            print(f"  Source already local ({size_gb:.1f} GB) — "
                  f"skipping copy", flush=True)
            return dst_local
        else:
            print(f"  Local source incomplete — re-copying", flush=True)
            dst_local.unlink()

    LOCAL_SRC_DIR.mkdir(parents=True, exist_ok=True)
    size_gb = src_drive.stat().st_size / 1e9
    print(f"  Copying source to local disk: "
          f"{src_drive.name}  ({size_gb:.1f} GB)", flush=True)
    mem("before source copy")
    tick("copy: Drive → local SSD")
    shutil.copy2(src_drive, dst_local)
    tock("copy: Drive → local SSD")

    # Drop page cache inflated by the copy — without this psutil reports
    # RAM as 30–40 GB "used" which is just kernel buffer cache, and workers
    # then run under artificial memory pressure.
    print(f"  Dropping page cache inflated by Drive copy...", flush=True)
    drop_all_page_cache()

    print(f"  Source copy complete: {dst_local.name}  "
          f"({dst_local.stat().st_size/1e9:.1f} GB)", flush=True)
    mem("after source copy + cache drop")
    return dst_local


def get_target_path(year, ref_profile: dict) -> Path:
    if needs_upsample_cached(year):
        local_src = copy_source_to_local(year)
        return upsample_year_from_local(year, local_src, ref_profile)
    else:
        print(f"  City of Edmonds year — native 0.0746 m, "
              f"no upsample needed", flush=True)
        return raw_imagery_path(year)


# ══════════════════════════════════════════════════════════════
# TILE GRID
# ══════════════════════════════════════════════════════════════

def make_tile_windows(width: int, height: int, tile_size: int):
    windows = []
    for row_off in range(0, height, tile_size):
        for col_off in range(0, width, tile_size):
            w = min(tile_size, width  - col_off)
            h = min(tile_size, height - row_off)
            windows.append(rasterio.windows.Window(col_off, row_off, w, h))
    return windows


# ══════════════════════════════════════════════════════════════
# CONTROL POINT CACHE
# ══════════════════════════════════════════════════════════════

def _cp_cache_path(year) -> Path:
    return CONTROL_POINTS_DIR / f"cp_{year}_vs_{REFERENCE_YEAR}.npz"


def _save_control_points(year, ref_pts: np.ndarray,
                         tgt_pts: np.ndarray) -> None:
    CONTROL_POINTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _cp_cache_path(year)
    np.savez_compressed(path, ref_pts=ref_pts, tgt_pts=tgt_pts)
    size_kb = path.stat().st_size / 1e3
    print(f"  Control points saved: {path.name}  "
          f"({len(ref_pts):,} pairs, {size_kb:.0f} KB)", flush=True)


def _load_control_points(year):
    path = _cp_cache_path(year)
    if not path.exists():
        return None, None
    try:
        data    = np.load(path)
        ref_pts = data["ref_pts"]
        tgt_pts = data["tgt_pts"]
        size_kb = path.stat().st_size / 1e3
        print(f"  Control points loaded from cache: {path.name}  "
              f"({len(ref_pts):,} pairs, {size_kb:.0f} KB)", flush=True)
        return ref_pts, tgt_pts
    except Exception as e:
        print(f"  Control point cache unreadable ({e}) — will recompute",
              flush=True)
        path.unlink()
        return None, None


# ══════════════════════════════════════════════════════════════
# PER-TILE WORKER
# ══════════════════════════════════════════════════════════════

def process_tile(args) -> tuple:
    """
    Process one tile: detect and match building-edge corners between
    reference and target imagery windows.
    """
    import time as _t
    window, ref_path_str, tgt_path_str, buildings_wkt, params = args

    import numpy as _np
    from shapely import wkt as _swkt
    _rio  = rasterio
    _rif  = rasterio.features
    _feat = feature
    _filt = filters
    _cv2  = cv2

    col_off = window.col_off
    row_off = window.row_off
    w       = window.width
    h       = window.height

    CANNY_SIGMA      = params["canny_sigma"]
    HARRIS_BLOCK     = params["harris_block"]
    HARRIS_KSIZE     = params["harris_ksize"]
    HARRIS_K         = params["harris_k"]
    HARRIS_THRESHOLD = params["harris_threshold"]
    MAX_CORNERS_TILE = params["max_corners_tile"]
    PATCH_SIZE       = params["patch_size"]
    NCC_THRESHOLD    = params["ncc_threshold"]
    SEARCH_RADIUS    = params["search_radius"]

    T = {}

    try:
        t0 = _t.time()
        with _rio.open(ref_path_str) as src:
            ref_transform = src.window_transform(window)
            ref_gray      = src.read(1, window=window)
        with _rio.open(tgt_path_str) as src:
            tgt_transform = src.window_transform(window)
            tgt_gray      = src.read(1, window=window)
        T["1_read"] = _t.time() - t0

        if ref_gray.shape != tgt_gray.shape:
            return [], T

        t0 = _t.time()
        def burn(transform, shape, wkt_list):
            shapes = []
            for wkt in wkt_list:
                try:
                    shapes.append((_swkt.loads(wkt).__geo_interface__, 1))
                except Exception:
                    pass
            if not shapes:
                return _np.zeros(shape, dtype=_np.uint8)
            return _rif.rasterize(shapes, out_shape=shape,
                                  transform=transform, fill=0, dtype=_np.uint8)
        ref_mask = burn(ref_transform, (h, w), buildings_wkt)
        tgt_mask = burn(tgt_transform, (h, w), buildings_wkt)
        T["2_burn"] = _t.time() - t0

        if ref_mask.sum() < 100 or tgt_mask.sum() < 100:
            T["skipped"] = "no_buildings"
            return [], T

        t0 = _t.time()
        def edge_map(mask):
            ksize   = max(3, int(CANNY_SIGMA * 6) | 1)
            blurred = _cv2.GaussianBlur(
                mask.astype(_np.float32), (ksize, ksize), CANNY_SIGMA)
            blurred_u8 = (blurred * 255).astype(_np.uint8)
            return _cv2.Canny(blurred_u8, 50, 150)
        ref_edges = edge_map(ref_mask)
        tgt_edges = edge_map(tgt_mask)
        T["3_edges"] = _t.time() - t0

        if ref_edges.sum() < 50 or tgt_edges.sum() < 50:
            T["skipped"] = "no_edges"
            return [], T

        t0 = _t.time()
        def detect_corners(edges):
            ef32   = edges.astype(_np.float32)
            harris = _cv2.cornerHarris(ef32, HARRIS_BLOCK, HARRIS_KSIZE, HARRIS_K)
            harris = _cv2.dilate(harris, None)
            thresh = HARRIS_THRESHOLD * harris.max()
            coords = _np.argwhere(harris > thresh)
            if len(coords) > MAX_CORNERS_TILE:
                resp   = harris[coords[:, 0], coords[:, 1]]
                idx    = _np.argsort(resp)[::-1][:MAX_CORNERS_TILE]
                coords = coords[idx]
            return coords
        ref_corners = detect_corners(ref_edges)
        tgt_corners = detect_corners(tgt_edges)
        T["4_corners"] = _t.time() - t0
        T["4_n_ref_corners"] = len(ref_corners)
        T["4_n_tgt_corners"] = len(tgt_corners)

        if len(ref_corners) < 5 or len(tgt_corners) < 5:
            T["skipped"] = "no_corners"
            return [], T

        t0 = _t.time()
        half       = PATCH_SIZE // 2
        search_pad = SEARCH_RADIUS + half
        _bw_1d = _np.blackman(PATCH_SIZE).astype(_np.float32)
        _bw_2d = _np.outer(_bw_1d, _bw_1d).astype(_np.float32)
        tgt_f32 = tgt_gray.astype(_np.float32)

        matched_pairs = []
        for r_ref, c_ref in ref_corners:
            r0, r1 = r_ref - half, r_ref + half + 1
            c0, c1 = c_ref - half, c_ref + half + 1
            if (r0 < 0 or r1 > ref_gray.shape[0] or
                    c0 < 0 or c1 > ref_gray.shape[1]):
                continue
            ref_patch = ref_gray[r0:r1, c0:c1].astype(_np.float32) * _bw_2d
            sr0 = max(0, r_ref - search_pad)
            sr1 = min(tgt_f32.shape[0], r_ref + search_pad)
            sc0 = max(0, c_ref - search_pad)
            sc1 = min(tgt_f32.shape[1], c_ref + search_pad)
            search_region = tgt_f32[sr0:sr1, sc0:sc1]
            if (search_region.shape[0] < PATCH_SIZE or
                    search_region.shape[1] < PATCH_SIZE):
                continue
            result = _cv2.matchTemplate(
                search_region, ref_patch, _cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = _cv2.minMaxLoc(result)
            if max_val < NCC_THRESHOLD:
                continue
            tgt_r = sr0 + max_loc[1] + half
            tgt_c = sc0 + max_loc[0] + half
            matched_pairs.append((
                c_ref + col_off, r_ref + row_off,
                tgt_c + col_off, tgt_r + row_off,
            ))
        T["5_match"] = _t.time() - t0
        T["5_n_matched"] = len(matched_pairs)

        return matched_pairs, T

    except Exception as e:
        T["error"] = str(e)
        return [], T


# ══════════════════════════════════════════════════════════════
# PHASE A — EXTRACT CONTROL POINTS
# ══════════════════════════════════════════════════════════════

def extract_control_points(ref_path: Path, tgt_path: Path,
                            buildings: gpd.GeoDataFrame,
                            params: dict,
                            col_off: int = 0, row_off: int = 0,
                            col_end: int = None, row_end: int = None) -> tuple:
    with rasterio.open(ref_path) as src:
        width         = src.width
        height        = src.height
        img_transform = src.transform

    # Apply clip bounds if provided
    col_end = col_end if col_end is not None else width
    row_end = row_end if row_end is not None else height
    clip_w  = col_end - col_off
    clip_h  = row_end - row_off

    windows = make_tile_windows(clip_w, clip_h, TILE_SIZE)

    # Offset windows into full reference pixel space
    windows = [
        rasterio.windows.Window(
            w.col_off + col_off,
            w.row_off + row_off,
            w.width,
            w.height
        )
        for w in windows
    ]

    windows = make_tile_windows(width, height, TILE_SIZE)
    n_tiles = len(windows)
    print(f"  Grid: {n_tiles} tiles  ({TILE_SIZE}x{TILE_SIZE} px each)",
          flush=True)
    print(f"  Mode: sequential (no multiprocessing)", flush=True)
    print(f"  NCC threshold: {params['ncc_threshold']}  "
          f"patch size: {params['patch_size']} px", flush=True)

    buildings_sindex = buildings.sindex

    task_args = []
    for win in windows:
        tile_bounds = rasterio.transform.array_bounds(
            win.height, win.width,
            rasterio.windows.transform(win, img_transform),
        )
        candidate_idx = list(buildings_sindex.intersection(tile_bounds))
        if candidate_idx:
            tile_box = _shapely_box(*tile_bounds)
            tile_wkt = [
                buildings.geometry.iloc[i].wkt
                for i in candidate_idx
                if buildings.geometry.iloc[i].intersects(tile_box)
            ]
        else:
            tile_wkt = []
        task_args.append(
            (win, str(ref_path), str(tgt_path), tile_wkt, params)
        )

    all_pairs = []
    phase_totals = {
        "1_read": 0.0, "2_burn": 0.0, "3_edges": 0.0,
        "4_corners": 0.0, "5_match": 0.0,
    }
    skipped_counts = {"no_buildings": 0, "no_edges": 0,
                      "no_corners": 0, "error": 0}
    total_ref_corners = 0
    total_tgt_corners = 0
    active_tiles      = 0

    for args in tqdm(task_args, desc="  Tiles processed"):
        pairs, T = process_tile(args)
        all_pairs.extend(pairs)

        for phase in phase_totals:
            if phase in T:
                phase_totals[phase] += T[phase]

        if "skipped" in T:
            skipped_counts[T["skipped"]] = skipped_counts.get(T["skipped"], 0) + 1
        elif "error" in T:
            skipped_counts["error"] += 1
        else:
            active_tiles += 1

        total_ref_corners += T.get("4_n_ref_corners", 0)
        total_tgt_corners += T.get("4_n_tgt_corners", 0)

    total_active_s = sum(phase_totals.values())
    print(f"\n  Phase A tile breakdown  ({active_tiles} active tiles, "
          f"{sum(skipped_counts.values())} skipped):", flush=True)
    phase_labels = {
        "1_read":    "1. Read imagery",
        "2_burn":    "2. Burn buildings",
        "3_edges":   "3. Edge detection",
        "4_corners": "4. Harris corners",
        "5_match":   "5. matchTemplate NCC",
    }
    for key, label in phase_labels.items():
        s   = phase_totals[key]
        pct = 100 * s / total_active_s if total_active_s > 0 else 0
        bar = "▓" * int(20 * pct / 100) + "░" * (20 - int(20 * pct / 100))
        avg = s / active_tiles if active_tiles > 0 else 0
        print(f"    {label:<26}  {s:6.1f}s total  "
              f"{avg*1000:6.0f}ms/tile  {pct:5.1f}%  [{bar}]", flush=True)
    print(f"    {'Skipped tiles':<26}  "
          f"no_bldg={skipped_counts['no_buildings']}  "
          f"no_edge={skipped_counts['no_edges']}  "
          f"no_corner={skipped_counts['no_corners']}  "
          f"error={skipped_counts['error']}", flush=True)
    if active_tiles > 0:
        print(f"    Avg corners/tile: ref={total_ref_corners//active_tiles}  "
              f"tgt={total_tgt_corners//active_tiles}", flush=True)

    print(f"  Total matched pairs: {len(all_pairs):,}", flush=True)

    if len(all_pairs) < MIN_MATCHES:
        return np.empty((0, 2)), np.empty((0, 2))

    arr = np.array(all_pairs, dtype=np.float64)
    return arr[:, :2], arr[:, 2:]


# ══════════════════════════════════════════════════════════════
# PHASE B — FIT TRANSFORM
# ══════════════════════════════════════════════════════════════

def fit_affine_ransac(src_pts, dst_pts, res_m, thresh_m=1.0):
    thresh_px = thresh_m / res_m
    M, mask   = cv2.estimateAffine2D(
        src_pts.astype(np.float32), dst_pts.astype(np.float32),
        method=cv2.RANSAC, ransacReprojThreshold=thresh_px,
        maxIters=2000, confidence=0.999,
    )
    if M is None:
        return None, None, 0
    mask = mask.ravel().astype(bool)
    return M, mask, int(mask.sum())


def compute_rmse(src_pts, dst_pts, transform_fn, res_m):
    pred      = transform_fn(src_pts)
    residuals = np.linalg.norm(pred - dst_pts, axis=1)
    return float(np.sqrt(np.mean(residuals ** 2))) * res_m


def make_affine_fn(M):
    def fn(pts):
        ones = np.ones((len(pts), 1))
        return (M @ np.hstack([pts, ones]).T).T
    return fn


## ─── PATCH 3: fit_tps ────────────────────────────────────────
## Replace the existing fit_tps function.
##
## Changes:
##   1. Deduplicates src_pts (keeps first occurrence) — eliminates
##      the primary cause of singular matrices with building corners
##   2. Falls back to smoothing=1.0 if exact interpolation still fails
##   3. Logs dedup and fallback so you see what happened
##
## The singular matrix happens because multiple NCC matches land on
## the same building corner pixel. RBFInterpolator(smoothing=0.0)
## requires all input locations to be unique — duplicate rows make
## the kernel matrix rank-deficient.

def fit_tps(src_pts, dst_pts):
    """
    Fit a thin-plate spline mapping src_pts → dst_pts.
    Deduplicates coincident source points before fitting.
    Falls back to smoothing=1.0 if exact interpolation is singular.
    """
    # ── Deduplicate by source location ────────────────────────
    # Round to 0.1 px to catch near-duplicates from adjacent corners
    rounded  = np.round(src_pts * 10).astype(np.int64)
    _, idx   = np.unique(rounded, axis=0, return_index=True)
    idx      = np.sort(idx)  # preserve original ordering
    src_uniq = src_pts[idx]
    dst_uniq = dst_pts[idx]

    if len(src_uniq) < len(src_pts):
        print(f"  TPS: deduplicated {len(src_pts)} → {len(src_uniq)} points  "
              f"({len(src_pts) - len(src_uniq)} coincident removed)", flush=True)

    if len(src_uniq) < 10:
        raise RuntimeError(
            f"TPS needs ≥10 unique points after dedup, got {len(src_uniq)}")

    # ── Try exact interpolation first ─────────────────────────
    try:
        rbf_x = RBFInterpolator(src_uniq, dst_uniq[:, 0],
                                kernel="thin_plate_spline", smoothing=0.0)
        rbf_y = RBFInterpolator(src_uniq, dst_uniq[:, 1],
                                kernel="thin_plate_spline", smoothing=0.0)
        print(f"  TPS: exact interpolation OK  "
              f"({len(src_uniq)} points)", flush=True)
    except np.linalg.LinAlgError:
        # ── Fallback: smoothed TPS ────────────────────────────
        print(f"  TPS: exact interpolation singular — "
              f"retrying with smoothing=1.0", flush=True)
        try:
            rbf_x = RBFInterpolator(src_uniq, dst_uniq[:, 0],
                                    kernel="thin_plate_spline", smoothing=1.0)
            rbf_y = RBFInterpolator(src_uniq, dst_uniq[:, 1],
                                    kernel="thin_plate_spline", smoothing=1.0)
            print(f"  TPS: smoothed fit OK  "
                  f"({len(src_uniq)} points, smoothing=1.0)", flush=True)
        except np.linalg.LinAlgError as e:
            raise RuntimeError(
                f"TPS singular even with smoothing — {len(src_uniq)} unique pts "
                f"likely clustered or collinear. Inspect control point spatial "
                f"distribution."
            ) from e

    def fn(pts):
        return np.column_stack([rbf_x(pts), rbf_y(pts)])
    return fn


# ══════════════════════════════════════════════════════════════
# PHASE C — WARP (tiled, sequential)  [INSTRUMENTED]
# ══════════════════════════════════════════════════════════════
#
# Drop-in replacements for warp_affine_tiled() and warp_tps_tiled().
# Same signatures, same behavior — adds per-step timing breakdown
# matching the Phase A console style.
#
# After the tqdm bar completes you'll see:
#
#   Phase C tile breakdown  (245 active, 249 empty):
#     1. Build coord grid         12.3s total     50ms/tile    1.4%  [░░░░░░░░░░░░░░░░░░░░]
#     2. Inverse transform         8.7s total     36ms/tile    1.0%  [░░░░░░░░░░░░░░░░░░░░]
#     3. Read source window      387.2s total   1581ms/tile   43.8%  [▓▓▓▓▓▓▓▓░░░░░░░░░░░░]
#     4. cv2.remap (3 bands)     291.5s total   1190ms/tile   33.0%  [▓▓▓▓▓▓░░░░░░░░░░░░░░]
#     5. Write compressed tile   183.4s total    749ms/tile   20.8%  [▓▓▓▓░░░░░░░░░░░░░░░░]
#     Empty tiles (no src overlap)  249
#     Peak src read: 8502x8502 px  (avg 8196x8196)


def _print_phase_c_breakdown(T, active, empty, n_bands,
                              peak_sw, peak_sh, sum_sw, sum_sh):
    """Phase A-style summary for Phase C sub-steps."""
    total_s = sum(T.values())
    print(f"\n  Phase C tile breakdown  "
          f"({active} active, {empty} empty):", flush=True)

    labels = {
        "1_grid":      "1. Build coord grid",
        "2_transform": "2. Inverse transform",
        "3_read":      "3. Read source window",
        "4_remap":     f"4. cv2.remap ({n_bands} bands)",
        "5_write":     "5. Write compressed tile",
    }
    for key, label in labels.items():
        s   = T.get(key, 0.0)
        pct = 100 * s / total_s if total_s > 0 else 0
        bar = "▓" * int(20 * pct / 100) + "░" * (20 - int(20 * pct / 100))
        avg = s / active if active > 0 else 0
        print(f"    {label:<30}  {s:7.1f}s total  "
              f"{avg*1000:6.0f}ms/tile  {pct:5.1f}%  [{bar}]", flush=True)

    print(f"    {'Empty tiles (no src overlap)':<30}  {empty}", flush=True)

    if active > 0:
        avg_w = sum_sw // active
        avg_h = sum_sh // active
        print(f"    Peak src read: {peak_sw}x{peak_sh} px  "
              f"(avg {avg_w}x{avg_h})", flush=True)


def warp_affine_tiled(src_path, dst_path, ref_profile, M):
    """
    Warp source imagery using affine M (tgt → ref pixel mapping).
    Processes one tile at a time — peak RAM = 2 tiles (~1.2 GB).
    Instrumented with per-step timing breakdown.
    """
    M_inv   = cv2.invertAffineTransform(M)
    width   = ref_profile["width"]
    height  = ref_profile["height"]
    windows = make_tile_windows(width, height, TILE_SIZE)

    with rasterio.open(src_path) as _src_meta:
        src_count = _src_meta.count
        src_dtype = _src_meta.dtypes[0]

    profile = ref_profile.copy()
    profile.pop("photometric", None)
    profile.update(count=src_count, dtype=src_dtype,
                   compress="lzw", predictor=2, bigtiff="IF_SAFER",
                   tiled=True, blockxsize=512, blockysize=512)

    # ── Timing accumulators ───────────────────────────────────
    T = {"1_grid": 0.0, "2_transform": 0.0,
         "3_read": 0.0, "4_remap": 0.0, "5_write": 0.0}
    active = 0
    empty  = 0
    peak_sw = peak_sh = 0
    sum_sw  = sum_sh  = 0

    with rasterio.open(src_path) as src, \
         rasterio.open(dst_path, "w", **profile) as dst:

        for window in tqdm(windows, desc="  Warping tiles"):
            col_off = window.col_off
            row_off = window.row_off
            w       = window.width
            h       = window.height

            # ── 1. Build coordinate grid ──────────────────────
            _t0 = _time_module.time()
            cols = np.arange(col_off, col_off + w, dtype=np.float32)
            rows = np.arange(row_off, row_off + h, dtype=np.float32)
            cc, rr = np.meshgrid(cols, rows)
            ones   = np.ones_like(cc)
            T["1_grid"] += _time_module.time() - _t0

            # ── 2. Inverse affine → source coords ────────────
            _t0 = _time_module.time()
            src_x = (M_inv[0,0]*cc + M_inv[0,1]*rr + M_inv[0,2]*ones)
            src_y = (M_inv[1,0]*cc + M_inv[1,1]*rr + M_inv[1,2]*ones)

            x_min = max(0, int(src_x.min()) - 2)
            y_min = max(0, int(src_y.min()) - 2)
            x_max = min(src.width,  int(src_x.max()) + 3)
            y_max = min(src.height, int(src_y.max()) + 3)
            T["2_transform"] += _time_module.time() - _t0

            if x_max <= x_min or y_max <= y_min:
                _t0 = _time_module.time()
                dst.write(
                    np.zeros((profile["count"], h, w), dtype=profile["dtype"]),
                    window=window,
                )
                T["5_write"] += _time_module.time() - _t0
                empty += 1
                continue

            active += 1
            sw = x_max - x_min
            sh = y_max - y_min
            peak_sw = max(peak_sw, sw)
            peak_sh = max(peak_sh, sh)
            sum_sw += sw
            sum_sh += sh

            # ── 3. Read source window ─────────────────────────
            _t0 = _time_module.time()
            src_win  = rasterio.windows.Window(x_min, y_min, sw, sh)
            src_data = src.read(window=src_win)
            T["3_read"] += _time_module.time() - _t0

            # ── 4. cv2.remap per band ─────────────────────────
            _t0 = _time_module.time()
            map_x = (src_x - x_min).astype(np.float32)
            map_y = (src_y - y_min).astype(np.float32)

            out_bands = np.zeros((src.count, h, w), dtype=src_data.dtype)
            for b in range(src.count):
                out_bands[b] = cv2.remap(
                    src_data[b].astype(np.float32),
                    map_x, map_y,
                    interpolation=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=0,
                ).astype(src_data.dtype)
            T["4_remap"] += _time_module.time() - _t0

            # ── 5. Write output tile ──────────────────────────
            _t0 = _time_module.time()
            dst.write(out_bands, window=window)
            T["5_write"] += _time_module.time() - _t0

    _print_phase_c_breakdown(T, active, empty, src_count,
                             peak_sw, peak_sh, sum_sw, sum_sh)


def warp_tps_tiled(src_path, dst_path, ref_profile, tps_fn, step=256):
    """
    Warp source imagery using TPS. Evaluates TPS on a coarse grid per
    tile then upscales to full resolution via bilinear interpolation.
    Instrumented with per-step timing breakdown.
    """
    width   = ref_profile["width"]
    height  = ref_profile["height"]
    windows = make_tile_windows(width, height, TILE_SIZE)

    with rasterio.open(src_path) as _src_meta:
        src_count = _src_meta.count
        src_dtype = _src_meta.dtypes[0]

    profile = ref_profile.copy()
    profile.pop("photometric", None)
    profile.update(count=src_count, dtype=src_dtype,
                   compress="lzw", predictor=2, bigtiff="IF_SAFER",
                   tiled=True, blockxsize=512, blockysize=512)

    print("  TPS warping: evaluating displacement on coarse grid per tile...",
          flush=True)

    # ── Timing accumulators ───────────────────────────────────
    T = {"1_grid": 0.0, "2_transform": 0.0,
         "3_read": 0.0, "4_remap": 0.0, "5_write": 0.0}
    active = 0
    empty  = 0
    peak_sw = peak_sh = 0
    sum_sw  = sum_sh  = 0

    with rasterio.open(src_path) as src, \
         rasterio.open(dst_path, "w", **profile) as dst:

        for window in tqdm(windows, desc="  Warping tiles (TPS)"):
            col_off = window.col_off
            row_off = window.row_off
            w       = window.width
            h       = window.height

            # ── 1. Build coarse grid ──────────────────────────
            _t0 = _time_module.time()
            cols_s = np.arange(col_off, col_off + w, step)
            rows_s = np.arange(row_off, row_off + h, step)
            cc, rr = np.meshgrid(cols_s, rows_s)
            pts    = np.column_stack([cc.ravel(), rr.ravel()]).astype(np.float64)
            T["1_grid"] += _time_module.time() - _t0

            # ── 2. TPS eval + bilinear upscale ────────────────
            _t0 = _time_module.time()
            mapped   = tps_fn(pts)
            map_x_sp = mapped[:, 0].reshape(len(rows_s), len(cols_s)).astype(np.float32)
            map_y_sp = mapped[:, 1].reshape(len(rows_s), len(cols_s)).astype(np.float32)

            map_x = cv2.resize(map_x_sp, (w, h), interpolation=cv2.INTER_LINEAR)
            map_y = cv2.resize(map_y_sp, (w, h), interpolation=cv2.INTER_LINEAR)

            x_min = max(0, int(map_x.min()) - 2)
            y_min = max(0, int(map_y.min()) - 2)
            x_max = min(src.width,  int(map_x.max()) + 3)
            y_max = min(src.height, int(map_y.max()) + 3)
            T["2_transform"] += _time_module.time() - _t0

            if x_max <= x_min or y_max <= y_min:
                _t0 = _time_module.time()
                dst.write(
                    np.zeros((profile["count"], h, w), dtype=profile["dtype"]),
                    window=window,
                )
                T["5_write"] += _time_module.time() - _t0
                empty += 1
                continue

            active += 1
            sw = x_max - x_min
            sh = y_max - y_min
            peak_sw = max(peak_sw, sw)
            peak_sh = max(peak_sh, sh)
            sum_sw += sw
            sum_sh += sh

            # ── 3. Read source window ─────────────────────────
            _t0 = _time_module.time()
            src_win  = rasterio.windows.Window(x_min, y_min, sw, sh)
            src_data = src.read(window=src_win)
            T["3_read"] += _time_module.time() - _t0

            # ── 4. cv2.remap per band ─────────────────────────
            _t0 = _time_module.time()
            map_x_local = map_x - x_min
            map_y_local = map_y - y_min

            out_bands = np.zeros((src.count, h, w), dtype=src_data.dtype)
            for b in range(src.count):
                out_bands[b] = cv2.remap(
                    src_data[b].astype(np.float32),
                    map_x_local, map_y_local,
                    interpolation=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=0,
                ).astype(src_data.dtype)
            T["4_remap"] += _time_module.time() - _t0

            # ── 5. Write output tile ──────────────────────────
            _t0 = _time_module.time()
            dst.write(out_bands, window=window)
            T["5_write"] += _time_module.time() - _t0

    _print_phase_c_breakdown(T, active, empty, src_count,
                             peak_sw, peak_sh, sum_sw, sum_sh)

# ══════════════════════════════════════════════════════════════
# SKIP-COREG MODE
# ══════════════════════════════════════════════════════════════

def copy_as_registered(src_path: Path, dst_path: Path):
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Copying to registered (no warp): {dst_path.name}", flush=True)
    shutil.copy2(src_path, dst_path)
    print(f"  Done.", flush=True)


# ══════════════════════════════════════════════════════════════
# REGISTER ONE YEAR
# ══════════════════════════════════════════════════════════════

TEST_OUTPUT_DIR   = Path("/content/test_registered")
TEST_UPSAMPLE_DIR = Path("/content/test_upsampled")
TEST_SRC_DIR      = Path("/content/test_source")


def _make_test_crop(src_path: Path, out_path: Path,
                    test_fraction: float = 1/30) -> dict:
    DRIVE_CACHE_MAX_GB = 1.0
    CHUNK_ROWS         = 4096

    DRIVE_TEST_DIR.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    drive_crop = DRIVE_TEST_DIR / out_path.name

    if drive_crop.exists():
        size_mb = drive_crop.stat().st_size / 1e6
        print(f"  Test crop cached on Drive — copying to local: "
              f"{drive_crop.name}  ({size_mb:.0f} MB)", flush=True)
        tick("copy: Drive test crop → local")
        shutil.copy2(drive_crop, out_path)
        tock("copy: Drive test crop → local")
        with rasterio.open(out_path) as _c:
            profile = _c.profile.copy()
        n_tiles = len(make_tile_windows(
            profile["width"], profile["height"], TILE_SIZE))
        print(f"  Crop dims : {profile['width']}x{profile['height']} px  "
              f"{n_tiles} tiles", flush=True)
        return profile

    with rasterio.open(src_path) as src:
        full_w    = src.width
        full_h    = src.height
        src_count = src.count
        src_dtype = src.dtypes[0]
        src_crs   = src.crs

        scale   = test_fraction ** 0.5
        crop_w  = max(TILE_SIZE, int(full_w * scale))
        crop_h  = max(TILE_SIZE, int(full_h * scale))
        col_off = (full_w - crop_w) // 2
        row_off = (full_h - crop_h) // 2
        crop_tf = src.window_transform(
            rasterio.windows.Window(col_off, row_off, crop_w, crop_h))

    est_gb = crop_w * crop_h * src_count / 1e9
    print(f"  Cropping: {crop_w}x{crop_h} px  "
          f"~{est_gb:.1f} GB uncompressed", flush=True)

    profile = {
        "driver": "GTiff", "dtype": src_dtype,
        "width": crop_w, "height": crop_h, "count": src_count,
        "crs": src_crs, "transform": crop_tf,
        "compress": "lzw", "predictor": 2,
        "tiled": True, "blockxsize": 512, "blockysize": 512,
        "bigtiff": "IF_SAFER",
    }

    tick("crop: full image → test crop (chunked)")
    with rasterio.open(src_path) as src:
        with rasterio.open(out_path, "w", **profile) as dst:
            chunk_row = 0
            while chunk_row < crop_h:
                rows_this = min(CHUNK_ROWS, crop_h - chunk_row)
                win = rasterio.windows.Window(
                    col_off, row_off + chunk_row, crop_w, rows_this)
                chunk_data = src.read(window=win)
                out_win = rasterio.windows.Window(0, chunk_row, crop_w, rows_this)
                dst.write(chunk_data, window=out_win)
                chunk_row += rows_this
    tock("crop: full image → test crop (chunked)")

    size_mb = out_path.stat().st_size / 1e6
    size_gb = size_mb / 1e3
    n_tiles = len(make_tile_windows(crop_w, crop_h, TILE_SIZE))
    print(f"  Written: {out_path.name}  ({size_mb:.0f} MB)  "
          f"{n_tiles} tiles", flush=True)

    if size_gb <= DRIVE_CACHE_MAX_GB:
        tick("copy: test crop → Drive cache")
        shutil.copy2(out_path, drive_crop)
        tock("copy: test crop → Drive cache")

    return profile


def register_year(year, buildings, ref_profile,
                  skip_coreg: bool = False,
                  test_fraction: float = None) -> dict:

    log = {
        "year":           year,
        "source":         f"{get_year_resolution(year):.4f}m",
        "upsampled":      needs_upsample_cached(year),
        "n_raw_pairs":    0,
        "n_inliers":      0,
        "rmse_affine_m":  None,
        "rmse_tps_m":     None,
        "transform_used": None,
        "passed":         False,
        "notes":          "",
    }

    print(f"\n{chr(9472) * 60}", flush=True)
    print(f"  Registering {year}  →  reference {REFERENCE_YEAR}  "
          f"[{log['source']}]", flush=True)
    print(f"{chr(9472) * 60}", flush=True)

    raw_path = raw_imagery_path(year)
    if not raw_path.exists():
        log["notes"] = f"Raw imagery not found: {raw_path}"
        print(f"  ✗ {log['notes']}", flush=True)
        return log

    if test_fraction is not None:
        print(f"\n  [TEST MODE]  fraction={test_fraction:.4f}  "
              f"(1/{int(round(1/test_fraction))} area)", flush=True)

        TEST_SRC_DIR.mkdir(parents=True, exist_ok=True)

        ref_path_full = raw_imagery_path(REFERENCE_YEAR)
        ref_crop_path = TEST_SRC_DIR / f"{REFERENCE_YEAR}_ref_test_crop.tif"
        if not ref_crop_path.exists():
            print(f"  Cropping reference imagery...", flush=True)
            ref_profile = _make_test_crop(ref_path_full, ref_crop_path,
                                          test_fraction)
        else:
            with rasterio.open(ref_crop_path) as _rc:
                ref_profile = _rc.profile.copy()
            print(f"  Reference crop: {ref_crop_path.name}  "
                  f"({ref_profile['width']}x{ref_profile['height']} px)",
                  flush=True)
        _ref_for_phase_a = ref_crop_path

        src_crop_path = TEST_SRC_DIR / f"{_stem(year)}_test_crop.tif"
        if not src_crop_path.exists():
            print(f"  Cropping source imagery...", flush=True)
            _make_test_crop(raw_path, src_crop_path, test_fraction)
        else:
            size_mb = src_crop_path.stat().st_size / 1e6
            print(f"  Source crop: {src_crop_path.name}  "
                  f"({size_mb:.0f} MB)", flush=True)

        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = TEST_OUTPUT_DIR / f"{_stem(year)}_test_registered.tif"

        if needs_upsample_cached(year):
            up_path = TEST_UPSAMPLE_DIR / f"{_stem(year)}_test_upsampled.tif"
            TEST_UPSAMPLE_DIR.mkdir(parents=True, exist_ok=True)
            if not up_path.exists():
                print(f"  Upsampling test crop...", flush=True)
                tick("upsample: test crop")
                with rasterio.open(src_crop_path) as _src:
                    _up_profile = ref_profile.copy()
                    _up_profile.pop("photometric", None)
                    _up_profile.update(
                        count=_src.count, dtype=_src.dtypes[0],
                        compress="lzw", predictor=2,
                        tiled=True, blockxsize=512, blockysize=512,
                    )
                    with rasterio.open(up_path, "w", **_up_profile) as _dst:
                        for _b in range(1, _src.count + 1):
                            rasterio.warp.reproject(
                                source=rasterio.band(_src, _b),
                                destination=rasterio.band(_dst, _b),
                                src_transform=_src.transform,
                                src_crs=_src.crs,
                                dst_transform=ref_profile["transform"],
                                dst_crs=ref_profile["crs"],
                                resampling=Resampling.cubic,
                            )
                tock("upsample: test crop")
                size_mb = up_path.stat().st_size / 1e6
                print(f"  Test upsample: {up_path.name}  "
                      f"({size_mb:.0f} MB)", flush=True)
            else:
                print(f"  Test upsample cached: {up_path.name}", flush=True)
            tgt_path = up_path
        else:
            tgt_path = src_crop_path

        log["notes"] = f"TEST MODE fraction={test_fraction:.4f}"

    else:
        out_path         = output_path(year)
        _ref_for_phase_a = raw_imagery_path(REFERENCE_YEAR)

    res_m = metres_per_pixel(ref_profile["transform"])

    if test_fraction is None:
        print(f"\n  [Step 0] Resolution check", flush=True)
        try:
            tgt_path         = get_target_path(year, ref_profile)
            log["upsampled"] = needs_upsample_cached(year)
        except Exception as e:
            log["notes"] = f"Upsample failed: {e}"
            print(f"  ✗ {log['notes']}", flush=True)
            return log

    if skip_coreg:
        print(f"\n  [skip-coreg] Copying directly to registered/", flush=True)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        copy_as_registered(tgt_path, out_path)
        if test_fraction is None:
            DRIVE_OUTPUT.mkdir(parents=True, exist_ok=True)
            print(f"  Copying to Drive...", flush=True)
            shutil.copy2(out_path, DRIVE_OUTPUT / out_path.name)
            out_path.unlink()
            print(f"  ✓ Copied to Drive", flush=True)
        log["transform_used"] = "none (skip-coreg)"
        log["passed"]         = True
        log["notes"]          = ("TEST skip-coreg" if test_fraction
                                 else "Skipped — imagery confirmed aligned")
        return log

    mem(f"{year} before Phase A")
    tick("Phase A: control point extraction")
    print(f"\n  [Phase A] Extracting control points", flush=True)
    params = match_params(year)

    # ── Clip tile grid to source extent ──────────────────────
    with rasterio.open(tgt_path) as _tgt_meta:
        tgt_bounds = _tgt_meta.bounds
    with rasterio.open(_ref_for_phase_a) as _ref_meta:
        ref_bounds    = _ref_meta.bounds
        ref_transform = _ref_meta.transform

    intersect_left   = max(ref_bounds.left,   tgt_bounds.left)
    intersect_bottom = max(ref_bounds.bottom, tgt_bounds.bottom)
    intersect_right  = min(ref_bounds.right,  tgt_bounds.right)
    intersect_top    = min(ref_bounds.top,    tgt_bounds.top)

    if intersect_left >= intersect_right or intersect_bottom >= intersect_top:
        log["notes"] = "Source and reference extents do not overlap"
        print(f"  ✗ {log['notes']}", flush=True)
        return log

    col_off = max(0, int((intersect_left   - ref_bounds.left) / abs(ref_transform.a)))
    row_off = max(0, int((ref_bounds.top   - intersect_top)   / abs(ref_transform.e)))
    col_end = min(ref_profile["width"],  int((intersect_right  - ref_bounds.left) / abs(ref_transform.a)))
    row_end = min(ref_profile["height"], int((ref_bounds.top   - intersect_bottom) / abs(ref_transform.e)))
    clip_w  = col_end - col_off
    clip_h  = row_end - row_off

    print(f"  Source coverage clip: col={col_off}..{col_end}  row={row_off}..{row_end}  "
          f"({clip_w}x{clip_h} px)", flush=True)
    print(f"  Full reference grid would be {ref_profile['width']}x{ref_profile['height']} px — "
          f"clipping to {100*clip_w*clip_h/(ref_profile['width']*ref_profile['height']):.1f}% of tiles",
          flush=True)

    ref_pts, tgt_pts = _load_control_points(year)
    if ref_pts is None:
        try:
            ref_pts, tgt_pts = extract_control_points(
                _ref_for_phase_a, tgt_path, buildings, params,
                col_off=col_off, row_off=row_off,
                col_end=col_end, row_end=row_end
            )
        except Exception as e:
            log["notes"] = f"Phase A failed: {e}"
            print(f"  ✗ {log['notes']}", flush=True)
            return log
        if len(ref_pts) >= MIN_MATCHES:
            _save_control_points(year, ref_pts, tgt_pts)
    else:
        print(f"  Phase A skipped — using cached control points", flush=True)

    tock("Phase A: control point extraction")
    log["n_raw_pairs"] = len(ref_pts)
    mem(f"{year} after Phase A")

    if len(ref_pts) < MIN_MATCHES:
        log["notes"] = (f"Too few matched pairs ({len(ref_pts)}) — "
                        f"lower ncc_threshold or use skip_coreg=True")
        print(f"  ✗ {log['notes']}", flush=True)
        return log

    tick("Phase B: RANSAC + transform fit")
    print(f"\n  [Phase B] Fitting transform", flush=True)
    M, mask, n_inliers = fit_affine_ransac(tgt_pts, ref_pts, res_m)
    log["n_inliers"] = n_inliers
    print(f"  RANSAC inliers: {n_inliers} / {len(ref_pts)}", flush=True)

    if M is None or n_inliers < MIN_MATCHES:
        log["notes"] = f"RANSAC failed — {n_inliers} inliers (need {MIN_MATCHES})"
        print(f"  ✗ {log['notes']}", flush=True)
        return log

    src_in = tgt_pts[mask]
    dst_in = ref_pts[mask]

    rmse_affine = compute_rmse(src_in, dst_in, make_affine_fn(M), res_m)
    log["rmse_affine_m"] = round(rmse_affine, 4)
    tock("Phase B: RANSAC + transform fit")
    print(f"  Affine RMSE: {rmse_affine:.4f} m  "
          f"(accept if <= {RMSE_AFFINE_ACCEPT} m)", flush=True)

    mem(f"{year} before Phase C warp")
    tick("Phase C: warp imagery")
    print(f"\n  [Phase C] Warping imagery", flush=True)

    if rmse_affine <= RMSE_AFFINE_ACCEPT:
        warp_affine_tiled(tgt_path, out_path, ref_profile, M)
        log["transform_used"] = "affine"
        log["passed"]         = True
        mem(f"{year} after local warp write")
        print(f"  ✓ Written locally: {out_path.name}", flush=True)
        if test_fraction is None:
            drive_dst = DRIVE_OUTPUT / out_path.name
            DRIVE_OUTPUT.mkdir(parents=True, exist_ok=True)
            print(f"  Copying to Drive...", flush=True)
            tick("copy: registered → Drive")
            shutil.copy2(out_path, drive_dst)
            tock("copy: registered → Drive")
            out_path.unlink()
            mem(f"{year} after Drive registered copy")
            print(f"  ✓ Copied to Drive: {drive_dst.name}", flush=True)
        else:
            tock("Phase C: warp imagery")
            print(f"  [TEST MODE] Kept locally", flush=True)

    else:
        print(f"  Affine RMSE {rmse_affine:.4f} m exceeds threshold — "
              f"trying TPS...", flush=True)

        if n_inliers < 20:
            log["notes"] = f"Too few inliers ({n_inliers}) for reliable TPS"
            print(f"  ✗ {log['notes']}", flush=True)
            return log

        tps_fn   = fit_tps(src_in, dst_in)
        rmse_tps = compute_rmse(src_in, dst_in, tps_fn, res_m)
        log["rmse_tps_m"] = round(rmse_tps, 4)
        print(f"  TPS RMSE: {rmse_tps:.4f} m  "
              f"(accept if <= {RMSE_TPS_ACCEPT} m)", flush=True)

        if rmse_tps <= RMSE_TPS_ACCEPT:
            warp_tps_tiled(tgt_path, out_path, ref_profile, tps_fn)
            log["transform_used"] = "tps"
            log["passed"]         = True
            print(f"  ✓ Written locally: {out_path.name}", flush=True)
            if test_fraction is None:
                drive_dst = DRIVE_OUTPUT / out_path.name
                DRIVE_OUTPUT.mkdir(parents=True, exist_ok=True)
                print(f"  Copying to Drive...", flush=True)
                shutil.copy2(out_path, drive_dst)
                out_path.unlink()
                print(f"  ✓ Copied to Drive: {drive_dst.name}", flush=True)
            else:
                print(f"  [TEST MODE] Kept locally", flush=True)
        else:
            log["notes"] = (f"TPS RMSE {rmse_tps:.4f} m exceeds threshold — "
                            f"manual inspection required.")
            print(f"  ✗ {log['notes']}", flush=True)
            fallback = out_path.with_name(out_path.stem + "_affine_inspect.tif")
            print(f"  Saving affine result for QGIS → {fallback.name}",
                  flush=True)
            warp_affine_tiled(tgt_path, fallback, ref_profile, M)

    return log


# ══════════════════════════════════════════════════════════════
# LOAD BUILDINGS
# ══════════════════════════════════════════════════════════════

def load_buildings(target_crs) -> gpd.GeoDataFrame:
    print(f"\n── Loading building footprints ──", flush=True)
    if not BUILDINGS_JSON.exists():
        print(f"  ✗ Not found: {BUILDINGS_JSON}", flush=True)
        sys.exit(1)

    gdf = gpd.read_file(BUILDINGS_JSON)
    print(f"  Loaded {len(gdf):,} features  (CRS: {gdf.crs})", flush=True)

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    if gdf.crs != target_crs:
        print(f"  Reprojecting {gdf.crs} → {target_crs}", flush=True)
        gdf = gdf.to_crs(target_crs)

    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    gdf = gdf[gdf.geometry.is_valid]
    print(f"  ✓ {len(gdf):,} valid building polygons ready", flush=True)
    mem("after loading buildings")
    return gdf


# ══════════════════════════════════════════════════════════════
# LOG
# ══════════════════════════════════════════════════════════════

def write_log(logs: list):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["year", "source", "upsampled", "n_raw_pairs", "n_inliers",
              "rmse_affine_m", "rmse_tps_m", "transform_used", "passed", "notes"]
    with open(LOG_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(logs)
    DRIVE_OUTPUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LOG_PATH, DRIVE_OUTPUT / "registration_log.csv")
    print(f"\n✓ Log written: {LOG_PATH} and copied to Drive", flush=True)


# ══════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ══════════════════════════════════════════════════════════════

import gc as _gc
import time as _time

MIN_REGISTERED_GB = 10.0


def _verify_registered(year) -> tuple:
    out_path = DRIVE_OUTPUT / f"{_stem(year)}_registered.tif"

    if not out_path.exists():
        return False, f"Not found on Drive: {out_path.name}"

    size_gb = out_path.stat().st_size / 1e9
    if size_gb < MIN_REGISTERED_GB:
        return False, f"Too small: {size_gb:.2f} GB (min {MIN_REGISTERED_GB} GB)"

    try:
        with rasterio.open(out_path) as src:
            w, h   = src.width, src.height
            cx, cy = w // 2, h // 2
            win    = rasterio.windows.Window(cx - 256, cy - 256, 512, 512)
            sample = src.read(1, window=win)
            if sample.max() == 0:
                return False, "Centre sample all zeros — corrupt"
            bands = src.count
    except Exception as e:
        return False, f"Failed to open: {e}"

    return True, (f"OK — {size_gb:.1f} GB  {w}x{h} px  "
                  f"{bands} bands  centre max={int(sample.max())}")


def _clean_local(year):
    freed_gb = 0.0
    patterns = [
        (LOCAL_SRC_DIR,  IMAGERY_CATALOG.get(_catalog_key(year), f"{year}.tif")),
        (UPSAMPLE_DIR,   f"{_stem(year)}_upsampled.tif"),
        (OUTPUT_DIR,     f"{_stem(year)}_registered.tif"),
    ]
    for directory, filename in patterns:
        f = directory / filename
        if f.exists():
            size_gb = f.stat().st_size / 1e9
            f.unlink()
            freed_gb += size_gb
            print(f"    Deleted local: {filename}  ({size_gb:.1f} GB)",
                  flush=True)
    if freed_gb > 0:
        print(f"    Freed: {freed_gb:.1f} GB local disk", flush=True)
    else:
        print(f"    No local files for {year}", flush=True)
    _gc.collect()
    mem(f"{year} after cleanup")


def _disk_free_gb() -> float:
    _, _, free = shutil.disk_usage("/content")
    return free / 1e9


def _check_headroom(min_free_gb: float = 15.0):
    vm      = _psutil.virtual_memory()
    free_gb = vm.available / 1e9
    if free_gb < min_free_gb:
        print(f"  WARNING: only {free_gb:.1f} GB RAM available "
              f"(recommended >= {min_free_gb:.0f} GB)", flush=True)


def _print_summary(results):
    print(f"\n{'='*60}", flush=True)
    print(f"  SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)
    for year, status, msg in results:
        icon = "✓" if status in ("pass", "skipped") else \
               "⚠" if status == "warning" else "✗"
        print(f"  {icon} {year}  [{status.upper()}]  {msg}", flush=True)
    passed = sum(1 for _, s, _ in results if s in ("pass", "skipped"))
    warned = sum(1 for _, s, _ in results if s == "warning")
    print(f"\n  {passed}/{len(results)} years confirmed  "
          f"({warned} with Drive sync warnings)", flush=True)


def run(years: list = None, skip_coreg: bool = False,
        test_fraction: float = None):
    """
    Orchestrator — process years one at a time.
    """
    if years is None:
        years = TARGET_YEARS

    print("=" * 60, flush=True)
    if test_fraction is not None:
        print(f"  REGISTRATION ORCHESTRATOR  "
              f"[TEST MODE 1/{int(round(1/test_fraction))} area]", flush=True)
    else:
        print("  REGISTRATION ORCHESTRATOR  [PRODUCTION]", flush=True)
    print("=" * 60, flush=True)
    print(f"  Years      : {years}", flush=True)
    print(f"  Skip coreg : {skip_coreg}", flush=True)
    print(f"  Test mode  : "
          f"{f'1/{int(round(1/test_fraction))} area' if test_fraction else 'off'}",
          flush=True)
    print(f"  Drive out  : "
          f"{'[skipped in test mode]' if test_fraction else DRIVE_OUTPUT}",
          flush=True)

    # ── Spawn context diagnostic ──────────────────────────────
    print(f"\n  [DIAG] Multiprocessing start method check:", flush=True)
    print(f"    Default method : {mp.get_start_method()}", flush=True)
    try:
        _ctx = mp.get_context("spawn")
        print(f"    Spawn context  : available ✓", flush=True)
    except Exception as e:
        print(f"    Spawn context  : UNAVAILABLE — {e}", flush=True)
    print(f"    Python version : {sys.version}", flush=True)
    print(f"    CPU count      : {mp.cpu_count()}", flush=True)

    mem("startup")
    print(f"  DISK  [startup]: {_disk_free_gb():.0f} GB free", flush=True)
    print()

    for d in [LOCAL_SRC_DIR, UPSAMPLE_DIR, OUTPUT_DIR,
              DRIVE_OUTPUT, DRIVE_UPSAMPLE]:
        d.mkdir(parents=True, exist_ok=True)

    ref_path = raw_imagery_path(REFERENCE_YEAR)
    with rasterio.open(ref_path) as src:
        ref_crs     = src.crs
        ref_profile = src.profile.copy()

    buildings = load_buildings(ref_crs)
    _gc.collect()
    mem("after buildings load")

    results = []

    for i, year in enumerate(years):
        print(f"\n{'='*60}", flush=True)
        print(f"  YEAR {year}  ({i+1}/{len(years)})", flush=True)
        mem(f"{year} start")
        print(f"  DISK  [{year} start]: {_disk_free_gb():.0f} GB free",
              flush=True)
        print(f"{'='*60}", flush=True)

        _check_headroom(min_free_gb=15.0)

        passed, msg = _verify_registered(year)
        if passed:
            print(f"  Already on Drive — skipping", flush=True)
            print(f"  {msg}", flush=True)
            results.append((year, "skipped", msg))
            continue

        print(f"\n  Registering {year}...", flush=True)
        t0 = _time.time()

        try:
            log     = register_year(year, buildings, ref_profile,
                                    skip_coreg=skip_coreg,
                                    test_fraction=test_fraction)
            success = log["passed"]
        except Exception as e:
            import traceback
            print(f"\n  FATAL EXCEPTION on {year}:", flush=True)
            print(f"  {e}", flush=True)
            print(f"  Full traceback:", flush=True)
            traceback.print_exc()
            log     = {"passed": False, "notes": str(e)}
            success = False

        elapsed = _time.time() - t0
        print(f"\n  Finished in {elapsed/60:.1f} min", flush=True)
        mem(f"{year} after register_year")
        _gc.collect()
        mem(f"{year} after gc")

        if test_fraction is not None:
            local_out = TEST_OUTPUT_DIR / f"{_stem(year)}_test_registered.tif"
            if local_out.exists() and local_out.stat().st_size > 1e6:
                size_mb = local_out.stat().st_size / 1e6
                msg = f"TEST OK — {local_out.name}  ({size_mb:.0f} MB)"
                print(f"  {msg}", flush=True)
                results.append((year, "pass", msg))
            else:
                msg = f"TEST output not found or empty: {local_out.name}"
                print(f"  WARNING: {msg}", flush=True)
                print(f"  Drive may still be syncing — verify manually "
                      f"before re-running. Continuing with next year...",
                      flush=True)
                results.append((year, "warning", msg))
        else:
            print(f"\n  Verifying Drive output...", flush=True)
            _time.sleep(3)
            passed, msg = _verify_registered(year)
            if passed:
                print(f"  PASS: {msg}", flush=True)
                results.append((year, "pass", msg))
            else:
                print(f"  FAIL: {msg}", flush=True)
                print(f"  Halting — fix {year} before continuing", flush=True)
                results.append((year, "fail", msg))
                _print_summary(results)
                return results

        print(f"\n  Cleaning local scratch for {year}...", flush=True)
        _clean_local(year)
        print(f"  DISK  [{year} after cleanup]: {_disk_free_gb():.0f} GB free",
              flush=True)

    _print_summary(results)
    timer_summary()
    return results


# ══════════════════════════════════════════════════════════════
# CLIP-BASED REGISTRATION
# ══════════════════════════════════════════════════════════════

CLIPS_DIR = DRIVE_BASE / "clips"

def run_clips(skip_coreg: bool = False):
    clips_output = CLIPS_DIR / "registered"
    clips_output.mkdir(parents=True, exist_ok=True)

    ref_clip = CLIPS_DIR / f"{REFERENCE_YEAR}_edmonds_clip.tif"
    if not ref_clip.exists():
        print(f"Reference clip not found: {ref_clip}", flush=True)
        print("Run clip_study_area.run() first.", flush=True)
        return

    print("=" * 60, flush=True)
    print("  CO-REGISTRATION — clip test mode", flush=True)
    print("=" * 60, flush=True)

    with rasterio.open(ref_clip) as src:
        ref_crs     = src.crs
        ref_profile = src.profile.copy()
        n_tiles     = len(make_tile_windows(src.width, src.height, TILE_SIZE))

    print(f"  Clip dims  : {ref_profile['width']}x{ref_profile['height']} px",
          flush=True)
    print(f"  Tiles      : {n_tiles}", flush=True)

    buildings = load_buildings(ref_crs)

    def clip_raw_path(year):
        return CLIPS_DIR / f"{year}_edmonds_clip.tif"

    def clip_output_path(year):
        return clips_output / f"{year}_edmonds_clip_registered.tif"

    logs = []
    for year in TARGET_YEARS:
        src_clip = clip_raw_path(year)
        if not src_clip.exists():
            print(f"  {year}: clip not found — skipping", flush=True)
            logs.append({"year": year, "passed": False,
                         "notes": "Clip not found", "source": "",
                         "upsampled": False, "n_raw_pairs": 0,
                         "n_inliers": 0, "rmse_affine_m": None,
                         "rmse_tps_m": None, "transform_used": None})
            continue

        dst_clip = clip_output_path(year)
        if dst_clip.exists():
            print(f"  {year}: registered clip already exists — skipping",
                  flush=True)
            logs.append({"year": year, "passed": True,
                         "notes": "Cached", "source": "",
                         "upsampled": False, "n_raw_pairs": 0,
                         "n_inliers": 0, "rmse_affine_m": None,
                         "rmse_tps_m": None, "transform_used": "cached"})
            continue

        params  = match_params(year)
        res_m   = metres_per_pixel(ref_profile["transform"])

        try:
            ref_pts, tgt_pts = extract_control_points(
                ref_clip, src_clip, buildings, params)

            log = {
                "year": year,
                "source": "king_county" if needs_upsample_cached(year)
                          else "edmonds",
                "upsampled": False, "n_raw_pairs": len(ref_pts),
                "n_inliers": 0, "rmse_affine_m": None, "rmse_tps_m": None,
                "transform_used": None, "passed": False, "notes": "",
            }

            if len(ref_pts) < MIN_MATCHES:
                log["notes"] = f"Too few pairs: {len(ref_pts)}"
                print(f"  ✗ {log['notes']}", flush=True)
                logs.append(log)
                continue

            M, mask, n_inliers = fit_affine_ransac(tgt_pts, ref_pts, res_m)
            log["n_inliers"] = n_inliers

            if M is None or n_inliers < MIN_MATCHES:
                log["notes"] = f"RANSAC failed — {n_inliers} inliers"
                print(f"  ✗ {log['notes']}", flush=True)
                logs.append(log)
                continue

            src_in = tgt_pts[mask]
            dst_in = ref_pts[mask]
            rmse   = compute_rmse(src_in, dst_in, make_affine_fn(M), res_m)
            log["rmse_affine_m"] = round(rmse, 4)
            print(f"  Affine RMSE: {rmse:.4f} m", flush=True)

            if not skip_coreg:
                warp_affine_tiled(src_clip, dst_clip, ref_profile, M)
                log["transform_used"] = "affine"
                log["passed"]         = True
                print(f"  ✓ Written: {dst_clip.name}", flush=True)
            else:
                log["transform_used"] = "none (skip-coreg)"
                log["passed"]         = rmse <= RMSE_AFFINE_ACCEPT

        except Exception as e:
            log["notes"] = f"Error: {e}"
            print(f"  FATAL: {e}", flush=True)

        logs.append(log)

    print(f"\n{'=' * 60}", flush=True)
    print(f"  CLIP REGISTRATION SUMMARY", flush=True)
    print(f"{'=' * 60}", flush=True)
    for l in logs:
        status = "PASS" if l["passed"] else "FAIL"
        rmse   = l.get("rmse_affine_m") or "—"
        print(f"  {l['year']}  {status}  RMSE {rmse} m", flush=True)
        if l.get("notes"):
            print(f"        -> {l['notes']}", flush=True)

    passed = sum(1 for l in logs if l["passed"])
    print(f"\n  Passed: {passed} / {len(logs)}", flush=True)
    return logs


def run_full(year=None, skip_coreg: bool = False):
    years = [year] if year else TARGET_YEARS

    print("=" * 60, flush=True)
    print("  CO-REGISTRATION — full image mode", flush=True)
    print("=" * 60, flush=True)

    ref_path = raw_imagery_path(REFERENCE_YEAR)
    if not ref_path.exists():
        print(f"Reference not found: {ref_path}", flush=True)
        return

    with rasterio.open(ref_path) as src:
        ref_crs     = src.crs
        ref_profile = src.profile.copy()

    buildings = load_buildings(ref_crs)
    for d in [OUTPUT_DIR, UPSAMPLE_DIR, LOCAL_SRC_DIR,
              DRIVE_OUTPUT, DRIVE_UPSAMPLE]:
        d.mkdir(parents=True, exist_ok=True)

    logs = []
    for yr in years:
        drive_out = DRIVE_OUTPUT / f"{_stem(yr)}_registered.tif"
        if drive_out.exists():
            size_gb = drive_out.stat().st_size / 1e9
            print(f"\n  {yr}: already registered on Drive "
                  f"({size_gb:.2f} GB) — skipping", flush=True)
            logs.append({"year": yr, "passed": True,
                         "transform_used": "cached",
                         "notes": "Output exists", "source": "",
                         "upsampled": needs_upsample_cached(yr),
                         "n_raw_pairs": 0, "n_inliers": 0,
                         "rmse_affine_m": None, "rmse_tps_m": None})
            continue

        try:
            log = register_year(yr, buildings, ref_profile,
                                skip_coreg=skip_coreg)
        except Exception as e:
            import traceback
            print(f"  FATAL error on {yr}: {e}", flush=True)
            traceback.print_exc()
            log = {"year": yr, "source": "", "upsampled": False,
                   "n_raw_pairs": 0, "n_inliers": 0,
                   "rmse_affine_m": None, "rmse_tps_m": None,
                   "transform_used": None, "passed": False,
                   "notes": f"Unhandled exception: {e}"}
        logs.append(log)

    write_log(logs)

    print(f"\n{'=' * 60}", flush=True)
    print(f"  SUMMARY", flush=True)
    print(f"{'=' * 60}", flush=True)
    for l in logs:
        status = "PASS" if l["passed"] else "FAIL"
        rmse   = l.get("rmse_tps_m") or l.get("rmse_affine_m") or "—"
        tfm    = l.get("transform_used") or "—"
        print(f"  {l['year']}  {status}  RMSE {rmse} m  [{tfm}]", flush=True)
        if l.get("notes"):
            print(f"        -> {l['notes']}", flush=True)

    passed = sum(1 for l in logs if l["passed"])
    print(f"\n  Passed: {passed} / {len(years)}", flush=True)
    return logs


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not hasattr(sys.modules["__main__"], "__spec__"):
        sys.modules["__main__"].__spec__ = None
    mp.set_start_method("spawn", force=True)

    parser = argparse.ArgumentParser(
        description="Co-register Edmonds temporal imagery to 2020 reference")
    parser.add_argument(
        "--years", type=str, nargs="+", default=None,
        help="Years to process. Use integers for standard years (2013 2015) "
             "or quoted wildcard strings for Snohomish years (\"2016*\" \"2021*\")")
    parser.add_argument(
        "--skip-coreg", action="store_true",
        help="Upsample only — skip warp.")

    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    args = parser.parse_args(filtered)

    years = None
    if args.years:
        years = []
        for y in args.years:
            try:
                years.append(int(y))
            except ValueError:
                years.append(y)

    run(years=years, skip_coreg=args.skip_coreg)
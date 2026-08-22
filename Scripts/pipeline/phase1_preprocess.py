"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 1 — Pre-Processing (Multi-Year)
  Edmonds Temporal Active Learning Pipeline

  Spatial anchor : 2020 DDT crown detections (222,435 crowns)
  Imagery        : all 18 acquisitions (2000–2024)

  PIPELINE STEPS
  ──────────────
  Step 0  upsample    Reproject all imagery to 2020 reference grid
  Step 1  load        Load crowns, buildings, water
  Step 2  water       Within-water join
  Step 3  bldg_dist   Building distance
  Step 4  roof_score  Roof spectral scoring (2020 imagery)
  Step 5  roof_join   Roof score proximity join
  Step 6  spectral    Per-year raw spectral sampling
  Step 7  normalise   Within-year normalisation

  STATIC features (computed once — geometry does not change):
  ───────────────────────────────────────────────────────────
  bldg_dist_m        float   Distance from centroid to nearest building edge
  within_water       bool    Crown centroid falls within a water body
  roof_score_nearby  float   Max roof_spectral_score within 5m of crown

  PER-YEAR raw spectral features:
  ────────────────────────────────
  rgb_mean_r_{year}   float   Mean red channel under crown polygon
  rgb_mean_g_{year}   float   Mean green channel under crown polygon
  rgb_mean_b_{year}   float   Mean blue channel under crown polygon
  ndvi_proxy_{year}   float   (G-R)/(G+R)
  luminance_{year}    float   BT.601 luminance (0-255)
  season_alpha_{year} float   Prior quality weight

  PER-YEAR normalised features (camera-agnostic):
  ─────────────────────────────────────────────────
  ndvi_z_{year}       float   Z-score of ndvi_proxy within this year
  ndvi_pct_{year}     float   Percentile rank of ndvi_proxy [0-100]
  lum_z_{year}        float   Z-score of luminance within this year
  ndvi_vs_roof_{year} float   Crown ndvi minus mean ndvi of buildings
                              within 50m in the same year's imagery

  OUTPUTS
  ───────
  upsample/{stem}_upsampled.tif             Upsampled imagery (non-CoE)
  upsample/{stem}.tif                       CoE imagery (copied)
  phase1/edmonds_crowns_phase1.gpkg         All crowns + all features
  phase1/building_spectral_scores_2020.gpkg Roof scores (2020 imagery)

  USAGE
  ─────
  %run phase1_preprocess.py                    # full run, all years
  %run phase1_preprocess.py --year 2005        # single year (upsample + spectral)
  %run phase1_preprocess.py --upsample-only    # upsample all, stop before spectral
  %run phase1_preprocess.py --skip-upsample    # skip upsample, spectral only
  %run phase1_preprocess.py --skip-static      # skip bldg/water/roof
  %run phase1_preprocess.py --force-spectral   # re-sample spectral cols
  %run phase1_preprocess.py --normalise-only   # recompute norm cols only
  %run phase1_preprocess.py --force-upsample   # force rebuild of upsampled imagery
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import ctypes
import gc
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import psutil
import rasterio
import rasterio.warp
import rasterio.windows
from rasterio.enums import Resampling
from rasterio.mask import mask as rio_mask
from rasterio.transform import Affine
from shapely.geometry import box
from tqdm import tqdm

warnings.filterwarnings("ignore")


# ── Paths ─────────────────────────────────────────────────────────────────────

BASE         = Path("/content/drive/MyDrive/treedata")
IMAGERY_DIR  = BASE / "Full_Image/Pipeline Imagery"
UPSAMPLE_DIR = IMAGERY_DIR / "upsample"
CROWNS_IN    = BASE / "inference/edmonds_crowns_2020.gpkg"
BUILDINGS    = BASE / "building_footprints/data.json"
WATER        = BASE / "bathology/GDBA_HYDROGRAPHY__waterbody_snoco.shp"
OUT_DIR          = BASE / "phase1"
CROWNS_OUT       = OUT_DIR / "edmonds_crowns_phase1.gpkg"       # final GIS deliverable
CROWNS_PARQUET   = OUT_DIR / "edmonds_crowns_phase1.parquet"    # fast working checkpoint
BLDG_NDVI_CACHE  = OUT_DIR / "building_ndvi_cache.parquet"      # per-year building NDVI
BLDG_OUT         = OUT_DIR / "building_spectral_scores_2020.gpkg"

# Local scratch (Colab SSD) — fast I/O for parallel workers
LOCAL_SRC_DIR      = Path("/content/source_imagery")
LOCAL_OUT_DIR      = Path("/content/upsampled")
LOCAL_SPECTRAL_DIR = Path("/content/spectral_imagery")
LOCAL_CHECKPOINT   = Path("/content/crowns_checkpoint.parquet")

REFERENCE_YEAR = 2020
N_WORKERS      = 6

# ── Spectral sampling tuning ─────────────────────────────────────────────────
# Tile size (in 2020-grid pixels) used to bucket crowns by spatial locality
# before sampling. Larger = better OS page-cache reuse but bigger buckets.
SPECTRAL_TILE_PX = 2048

# Minimum free SSD space (GB) that must remain *after* a prefetch copy
# lands on local disk. This is in addition to whatever is already staged.
# Set conservatively: Colab SSD is ~200 GB, largest file is ~97 GB, and
# two large files + headroom must fit simultaneously.
PREFETCH_HEADROOM_GB = 40.0


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGERY CATALOGUE — All 18 acquisitions
#
#  key            Unique identifier (int or str with suffix)
#  label          Display label
#  file           Filename in UPSAMPLE_DIR (what spectral sampling reads)
#  native_file    Filename in IMAGERY_DIR  (raw source for upsampling)
#  needs_upsample True = reproject to 2020 grid; False = copy only (CoE)
#  season_alpha   Spectral quality weight (0–1)
# ══════════════════════════════════════════════════════════════════════════════

YEAR_CATALOG = [
    # ── Pre-2013: King County historical ──────────────────────────────────
    {"key": 2000,    "file": "2000_king_rgb_upsampled.tif",
     "native_file": "2000_king_rgb.tif",
     "needs_upsample": True,
     "label": "2000",    "season_alpha": 0.30},

    {"key": 2002,    "file": "2002_king_rgb_upsampled.tif",
     "native_file": "2002_king_rgb.tif",
     "needs_upsample": True,
     "label": "2002",    "season_alpha": 0.30},

    {"key": 2005,    "file": "2005_king_rgb_upsampled.tif",
     "native_file": "2005_king_rgb.tif",
     "needs_upsample": True,
     "label": "2005",    "season_alpha": 0.35},

    {"key": 2007,    "file": "2007_king_rgb_upsampled.tif",
     "native_file": "2007_king_rgb.tif",
     "needs_upsample": True,
     "label": "2007",    "season_alpha": 0.35},

    {"key": 2009,    "file": "2009_king_rgb_upsampled.tif",
     "native_file": "2009_king_rgb.tif",
     "needs_upsample": True,
     "label": "2009",    "season_alpha": 0.40},

    # ── 2013–2024: existing imagery ───────────────────────────────────────
    {"key": 2013,    "file": "2013_king_rgb_upsampled.tif",
     "native_file": "2013_king_rgb.tif",
     "needs_upsample": True,
     "label": "2013",    "season_alpha": 0.50},

    {"key": 2015,    "file": "2015_king_rgb_upsampled.tif",
     "native_file": "2015_king_rgb.tif",
     "needs_upsample": True,
     "label": "2015",    "season_alpha": 0.45},

    {"key": 2016,    "file": "2016_snoh_rgbi_upsampled.tif",
     "native_file": "2016_snoh_rgbi.tif",
     "needs_upsample": True,
     "label": "2016",    "season_alpha": 0.65},

    {"key": 2017,    "file": "2017_coe_rgb.tif",
     "native_file": "2017_coe_rgb.tif",
     "needs_upsample": False,
     "label": "2017",    "season_alpha": 0.65},

    {"key": 2019,    "file": "2019_king_rgb_upsampled.tif",
     "native_file": "2019_king_rgb.tif",
     "needs_upsample": True,
     "label": "2019",    "season_alpha": 0.80},

    {"key": "2019n", "file": "2019_naip_rgbi_upsampled.tif",
     "native_file": "2019_naip_rgbi.tif",
     "needs_upsample": True,
     "label": "2019n",   "season_alpha": 0.85},

    {"key": 2020,    "file": "2020_coe_rgb.tif",
     "native_file": "2020_coe_rgb.tif",
     "needs_upsample": False,
     "label": "2020",    "season_alpha": 1.00},

    {"key": 2021,    "file": "2021_king_rgb_upsampled.tif",
     "native_file": "2021_king_rgb.tif",
     "needs_upsample": True,
     "label": "2021",    "season_alpha": 0.70},

    {"key": "2021s", "file": "2021_snoh_rgbi_upsampled.tif",
     "native_file": "2021_snoh_rgbi.tif",
     "needs_upsample": True,
     "label": "2021s",   "season_alpha": 0.65},

    {"key": 2022,    "file": "2022_coe_rgb.tif",
     "native_file": "2022_coe_rgb.tif",
     "needs_upsample": False,
     "label": "2022",    "season_alpha": 0.90},

    {"key": "2023n", "file": "2023_naip_rgbi_upsampled.tif",
     "native_file": "2023_naip_rgbi.tif",
     "needs_upsample": True,
     "label": "2023n",   "season_alpha": 0.85},

    {"key": 2023,    "file": "2023_king_rgb_upsampled.tif",
     "native_file": "2023_king_rgb.tif",
     "needs_upsample": True,
     "label": "2023",    "season_alpha": 0.70},

    {"key": 2024,    "file": "2024_coe_rgb.tif",
     "native_file": "2024_coe_rgb.tif",
     "needs_upsample": False,
     "label": "2024",    "season_alpha": 0.90},
]


# ── Spectral thresholds ──────────────────────────────────────────────────────

NDVI_ROOF_MAX  =  0.10
NDVI_VEG_MIN   =  0.25
LUM_SHADOW_MAX =  30


# ── Upsample tuning ──────────────────────────────────────────────────────────

UPSAMPLE_CHUNK_PX      = 4096
N_UPSAMPLE_WORKERS     = 3
WORKER_BATCH_SIZE      = 10
WORKER_STALL_TIMEOUT_S = 180   # 3 min — if no chunk arrives, abort
POOL_SCALE_THRESHOLD   = 2     # scale factors ≤ this → single-threaded


# ── Column name helpers ───────────────────────────────────────────────────────

def _col(base: str, year_key) -> str:
    return f"{base}_{year_key}"


def raw_spectral_cols(year_key) -> list:
    return [
        _col("rgb_mean_r",   year_key),
        _col("rgb_mean_g",   year_key),
        _col("rgb_mean_b",   year_key),
        _col("ndvi_proxy",   year_key),
        _col("luminance",    year_key),
        _col("season_alpha", year_key),
    ]


def norm_spectral_cols(year_key) -> list:
    return [
        _col("ndvi_z",       year_key),
        _col("ndvi_pct",     year_key),
        _col("lum_z",        year_key),
        _col("ndvi_vs_roof", year_key),
    ]


# ═════════════════════════════════════════════════════════════════════════════
#  MEMORY / CACHE HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def mem(label: str = "") -> float:
    vm       = psutil.virtual_memory()
    used_gb  = vm.used  / 1e9
    total_gb = vm.total / 1e9
    pct      = vm.percent
    bar      = "█" * int(20 * pct / 100) + "░" * (20 - int(20 * pct / 100))
    tag      = f"  [{label}]" if label else ""
    print(f"  MEM{tag}: {used_gb:.1f}/{total_gb:.1f} GB  [{bar}] {pct:.1f}%",
          flush=True)
    return used_gb


def _trim():
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def _drop_page_cache_file(path: Path):
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        with open(path, "rb") as fh:
            libc.posix_fadvise(fh.fileno(), 0, 0, 4)
    except Exception:
        pass


def drop_all_page_cache(silent: bool = False):
    try:
        if not silent:
            subprocess.run(["sync"], check=False, timeout=30)
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("1\n")
        if not silent:
            vm = psutil.virtual_memory()
            print(f"  Page cache dropped — RAM now: "
                  f"{vm.used/1e9:.1f}/{vm.total/1e9:.1f} GB ({vm.percent:.1f}%)",
                  flush=True)
    except Exception as e:
        if not silent:
            print(f"  Could not drop page cache: {e}", flush=True)


# ═════════════════════════════════════════════════════════════════════════════
#  TIMING HELPERS
# ═════════════════════════════════════════════════════════════════════════════

_TIMER_STACK: list = []
_TIMER_LOG:   list = []


def tick(label: str = "") -> float:
    t0 = time.time()
    _TIMER_STACK.append((label, t0))
    return t0


def tock(label: str = "") -> float:
    t1 = time.time()
    if not _TIMER_STACK:
        return 0.0
    stored_label, t0 = _TIMER_STACK.pop()
    display_label    = label or stored_label or "unnamed"
    elapsed_s        = t1 - t0
    if elapsed_s < 1.0:
        disp = f"{elapsed_s*1000:.0f} ms"
    elif elapsed_s < 120:
        disp = f"{elapsed_s:.1f} s"
    else:
        disp = f"{elapsed_s/60:.1f} min"
    depth  = len(_TIMER_STACK)
    indent = "  " + "  " * depth
    bar    = ("▓" * min(20, int(20 * elapsed_s / 300))
              + "░" * max(0, 20 - int(20 * elapsed_s / 300)))
    print(f"{indent}⏱  {display_label:<40}  {disp:>10}  [{bar}]",
          flush=True)
    _TIMER_LOG.append({"label": display_label, "elapsed_s": elapsed_s})
    return elapsed_s


def timer_summary():
    if not _TIMER_LOG:
        return
    sorted_log = sorted(_TIMER_LOG,
                        key=lambda x: x["elapsed_s"], reverse=True)
    total = sum(x["elapsed_s"] for x in sorted_log)
    print("\n" + "═" * 60)
    print(f"  TIMING SUMMARY  (total: {total/60:.1f} min)")
    print("═" * 60)
    for entry in sorted_log:
        e   = entry["elapsed_s"]
        pct = 100 * e / total if total > 0 else 0
        bar = ("▓" * int(20 * pct / 100)
               + "░" * (20 - int(20 * pct / 100)))
        disp = (f"{e*1000:.0f} ms" if e < 1
                else f"{e:.1f} s" if e < 120
                else f"{e/60:.1f} min")
        print(f"  {entry['label']:<42}  {disp:>8}  "
              f"{pct:5.1f}%  [{bar}]")
    print("═" * 60)


# ═════════════════════════════════════════════════════════════════════════════
#  CHECKPOINT HELPERS
#
#  Working checkpoints use Parquet (columnar, memory-mapped, ~10-50x faster
#  to read than GPKG for wide numerical tables). GPKG is only written at the
#  very end as the final GIS deliverable.
#
#  Geometry is stored in Parquet as WKB bytes (the standard GeoParquet
#  convention) so geopandas can round-trip it cleanly.
#
#  Load priority: Parquet > GPKG  (Parquet is always newer if both exist)
# ═════════════════════════════════════════════════════════════════════════════

def save_checkpoint(crowns: gpd.GeoDataFrame, label: str = "") -> None:
    """
    Save crowns to Parquet via local SSD scratch then copy to Drive.

    Writing directly to Drive risks a corrupt/partial file if the session
    disconnects mid-write. Instead:
      1. Write to fast local SSD (LOCAL_CHECKPOINT)
      2. Validate by reading back just crown_id and checking row count
      3. Copy validated local file to Drive (CROWNS_PARQUET)
      4. Warn if file sizes don't match (Drive sync may be incomplete)
    """
    CROWNS_PARQUET.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: write to local SSD
    tick(f"{label}: parquet checkpoint")
    if LOCAL_CHECKPOINT.exists():
        LOCAL_CHECKPOINT.unlink()
    crowns.to_parquet(LOCAL_CHECKPOINT, index=False, compression="snappy")
    local_size_mb = LOCAL_CHECKPOINT.stat().st_size / 1e6
    print(f"  [CHECKPOINT] local write: {local_size_mb:.0f} MB", flush=True)

    # Step 2: validate local file
    try:
        check = gpd.read_parquet(LOCAL_CHECKPOINT, columns=["crown_id"])
        if len(check) != len(crowns):
            LOCAL_CHECKPOINT.unlink()
            raise RuntimeError(
                f"Parquet validation failed: wrote {len(crowns):,} rows "
                f"but read back {len(check):,}")
        print(f"  [CHECKPOINT] validated: {len(check):,} rows OK",
              flush=True)
    except Exception as e:
        if LOCAL_CHECKPOINT.exists():
            LOCAL_CHECKPOINT.unlink()
        raise RuntimeError(
            f"Parquet validation error ({label}): {e}") from e

    # Step 3: copy to Drive
    shutil.copy2(LOCAL_CHECKPOINT, CROWNS_PARQUET)
    tock(f"{label}: parquet checkpoint")

    # Step 4: size check
    drive_size_mb = CROWNS_PARQUET.stat().st_size / 1e6
    if abs(local_size_mb - drive_size_mb) > 1.0:
        print(f"  [CHECKPOINT] WARNING: size mismatch — "
              f"local={local_size_mb:.0f} MB  "
              f"drive={drive_size_mb:.0f} MB  "
              f"(Drive sync may be incomplete)", flush=True)
    else:
        print(f"  [CHECKPOINT] ✓ {CROWNS_PARQUET.name}  "
              f"({drive_size_mb:.0f} MB  {len(crowns):,} rows "
              f"× {len(crowns.columns)} cols)", flush=True)


def save_bldg_ndvi_cache(cache: dict) -> None:
    """
    Persist the building NDVI cache to a small Parquet sidecar.

    Schema: building_id (index) × one column per year key
    (ndvi_bldg_{year_key}). Loads in < 1s even with 18 years × 20k buildings.
    """
    if not cache:
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(cache)
    df.index.name = "building_idx"
    df.to_parquet(BLDG_NDVI_CACHE, index=True, compression="snappy")
    size_kb = BLDG_NDVI_CACHE.stat().st_size / 1e3
    print(f"  [BLDG CACHE] saved {len(cache)} year(s) → "
          f"{BLDG_NDVI_CACHE.name}  ({size_kb:.0f} KB)", flush=True)


def load_bldg_ndvi_cache() -> dict:
    """
    Load the building NDVI cache from disk.
    Returns empty dict if file doesn't exist.
    Each value is a pd.Series indexed like the buildings GeoDataFrame.
    """
    if not BLDG_NDVI_CACHE.exists():
        return {}
    df = pd.read_parquet(BLDG_NDVI_CACHE)
    cache = {col.replace("ndvi_bldg_", ""): df[col]
             for col in df.columns}
    # Re-key to match original year_key types (int where possible)
    typed_cache = {}
    for k, v in cache.items():
        try:
            typed_cache[int(k)] = v
        except ValueError:
            typed_cache[k] = v
    size_kb = BLDG_NDVI_CACHE.stat().st_size / 1e3
    print(f"  [BLDG CACHE] loaded {len(typed_cache)} year(s) from "
          f"{BLDG_NDVI_CACHE.name}  ({size_kb:.0f} KB)", flush=True)
    return typed_cache


def _bldg_cache_has(year_key, cache: dict) -> bool:
    """True if building NDVI for this year is already in the cache."""
    return year_key in cache and cache[year_key].notna().any()


def load_checkpoint() -> gpd.GeoDataFrame | None:
    """
    Load crowns from the fastest available checkpoint format.
    Returns None if no checkpoint exists.

    Priority: Parquet (fast) → GPKG (slow fallback if Parquet missing or corrupt)

    If the Parquet exists but throws any read error (e.g. ArrowInvalid from
    a partial Drive write), the timer stack is balanced, a warning is printed,
    and we fall back to the GPKG. The Parquet is then rebuilt from the GPKG
    via save_checkpoint so the next run is fast again.
    """
    if CROWNS_PARQUET.exists():
        size_mb = CROWNS_PARQUET.stat().st_size / 1e6
        print(f"  [CHECKPOINT] Loading Parquet: {CROWNS_PARQUET.name}  "
              f"({size_mb:.0f} MB)", flush=True)
        tick("load parquet checkpoint")
        try:
            crowns = gpd.read_parquet(CROWNS_PARQUET)
            tock("load parquet checkpoint")
            crs_str = (crowns.crs.to_epsg() if crowns.crs else "unknown")
            crs_display = f"EPSG:{crs_str}" if crs_str else str(crowns.crs)
            print(f"  [CHECKPOINT] Loaded {len(crowns):,} rows  "
                  f"× {len(crowns.columns)} cols  "
                  f"CRS={crs_display}", flush=True)
            return crowns
        except Exception as e:
            # Pop the timer so tick/tock stay balanced
            if _TIMER_STACK:
                _TIMER_STACK.pop()
            print(f"  [CHECKPOINT] WARNING: Parquet read failed "
                  f"({type(e).__name__}: {e})", flush=True)
            print(f"  [CHECKPOINT] Parquet is corrupt — deleting and "
                  f"falling back to GPKG", flush=True)
            try:
                CROWNS_PARQUET.unlink()
            except Exception:
                pass

    if CROWNS_OUT.exists():
        size_mb = CROWNS_OUT.stat().st_size / 1e6
        print(f"  [CHECKPOINT] Loading GPKG: {CROWNS_OUT.name}  "
              f"({size_mb:.0f} MB)", flush=True)
        print(f"  [CHECKPOINT] WARNING: GPKG load is slow (~10 min). "
              f"Parquet will be rebuilt after loading.",
              flush=True)
        tick("load GPKG checkpoint (slow — first time only)")
        with keepalive("GPKG load"):
            crowns = gpd.read_file(CROWNS_OUT)
        tock("load GPKG checkpoint (slow — first time only)")
        print(f"  [CHECKPOINT] Rebuilding Parquet from GPKG...",
              flush=True)
        save_checkpoint(crowns, label="rebuild GPKG→Parquet")
        return crowns

    return None


# ═════════════════════════════════════════════════════════════════════════════
#  COLAB KEEPALIVE
#
#  Colab's idle detector watches for output activity. During long blocking
#  operations (Drive → SSD copies, GPKG writes) the main thread produces no
#  output for many minutes, which triggers a disconnect even though the
#  process is actively running. This context manager runs a background thread
#  that prints a single heartbeat line every KEEPALIVE_INTERVAL_S seconds,
#  which is enough to satisfy Colab's idle check without polluting logs.
# ═════════════════════════════════════════════════════════════════════════════

import threading

KEEPALIVE_INTERVAL_S = 45   # seconds between heartbeat lines


class _KeepaliveThread(threading.Thread):
    def __init__(self, label: str = ""):
        super().__init__(daemon=True, name="keepalive")
        self._stop_event = threading.Event()
        self._label      = label
        self._t0         = time.time()

    def run(self):
        while not self._stop_event.wait(timeout=KEEPALIVE_INTERVAL_S):
            elapsed = (time.time() - self._t0) / 60
            vm      = psutil.virtual_memory()
            _, _, free_b = shutil.disk_usage("/content")
            print(f"  [KEEPALIVE] {self._label}  "
                  f"elapsed={elapsed:.1f}min  "
                  f"RAM={vm.used/1e9:.1f}/{vm.total/1e9:.1f}GB "
                  f"({vm.percent:.0f}%)  "
                  f"SSD_free={free_b/1e9:.1f}GB",
                  flush=True)

    def stop(self):
        self._stop_event.set()


class keepalive:
    """
    Context manager that keeps Colab alive during long blocking operations.

    Usage:
        with keepalive("staging 2015"):
            shutil.copy2(src, dst)
    """
    def __init__(self, label: str = ""):
        self._thread = _KeepaliveThread(label)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._thread.stop()
        self._thread.join(timeout=2)


# ═════════════════════════════════════════════════════════════════════════════
#  STEP 0 — UPSAMPLE IMAGERY
#
#  Reprojects all source imagery to the 2020 reference grid:
#    CRS        : EPSG:3857
#    Resolution : 0.0746 m (7.62 cm)
#    Dimensions : 148736 × 211968 px
#    Transform  : snapped to 2020 pixel grid
#
#  CoE years (2017, 2020, 2022, 2024) are already on the correct
#  grid — they are copied to the output folder unchanged.
#
#  All other years are reprojected using cubic resampling.
#  Upsampled files are cached on Drive and reused on subsequent runs.
# ═════════════════════════════════════════════════════════════════════════════

def _upsample_raw_path(entry: dict) -> Path:
    """Path to the native/raw source file for upsampling."""
    return IMAGERY_DIR / entry["native_file"]


def _upsample_drive_path(entry: dict) -> Path:
    """Path to the upsampled output on Drive."""
    return UPSAMPLE_DIR / entry["file"]


def _upsample_local_path(entry: dict) -> Path:
    """Path to the upsampled output on local SSD."""
    return LOCAL_OUT_DIR / entry["file"]


def metres_per_pixel(transform) -> float:
    return abs(transform.a)


def make_tile_windows(width: int, height: int, tile_size: int):
    windows = []
    for row_off in range(0, height, tile_size):
        for col_off in range(0, width, tile_size):
            w = min(tile_size, width  - col_off)
            h = min(tile_size, height - row_off)
            windows.append(
                rasterio.windows.Window(col_off, row_off, w, h))
    return windows


def _validate_upsample(path: Path, ref_profile: dict) -> tuple:
    """Return (valid, reason)."""
    if not path.exists():
        return False, "file not found"
    size_gb = path.stat().st_size / 1e9
    if size_gb < 0.5:
        return False, f"too small ({size_gb:.2f} GB)"
    try:
        with rasterio.open(path) as src:
            if src.width != ref_profile["width"]:
                return False, (f"width mismatch "
                               f"({src.width} != {ref_profile['width']})")
            if src.height != ref_profile["height"]:
                return False, (f"height mismatch "
                               f"({src.height} != {ref_profile['height']})")
            cx  = src.width  // 2
            cy  = src.height // 2
            win = rasterio.windows.Window(cx - 256, cy - 256, 512, 512)
            s   = src.read(1, window=win)
            if s.max() == 0:
                return False, "centre sample all zeros — corrupt"
    except Exception as e:
        return False, f"open failed: {e}"
    return True, f"OK  {size_gb:.1f} GB  {path.name}"


# ── Chunk reprojection worker (runs in spawned subprocess) ────────────────

def _reproject_chunk_batch(args):
    import time as _t
    import os as _os
    import numpy as _np
    import rasterio as _rio
    import rasterio.warp as _rwarp
    from rasterio.enums import Resampling as _R
    from rasterio.transform import Affine as _Affine

    (src_path_str, band_i, chunk_list,
     src_transform_tuple, src_crs_wkt, dst_crs_wkt,
     src_dtype, gdal_cachemax) = args

    _os.environ["GDAL_CACHEMAX"] = str(gdal_cachemax)
    results = []

    try:
        src_f = _rio.open(src_path_str)
        src_open_ok = True
    except Exception as e:
        src_open_ok  = False
        src_open_err = str(e)

    src_t = _Affine(*src_transform_tuple)

    for (col_off, row_off, chunk_w, chunk_h,
         dst_transform_tuple) in chunk_list:
        t_start   = _t.time()
        dst_t     = _Affine(*dst_transform_tuple)
        dst_arr   = _np.zeros((chunk_h, chunk_w), dtype=src_dtype)
        failed    = False
        error_msg = ""
        proj_ms   = 0

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
                dst_arr[:] = 0
                failed     = True
                error_msg  = str(e)

        total_ms = int((_t.time() - t_start) * 1000)
        results.append((
            band_i, col_off, row_off, chunk_w, chunk_h,
            dst_arr, failed, error_msg,
            _os.getpid(), 0, proj_ms, total_ms,
        ))

    if src_open_ok:
        src_f.close()
    return results


# ── Single-threaded full-band reproject ───────────────────────────────────

def _do_fullband_reproject(local_src, dst_local, src_count, src_dtype,
                           src_transform, src_crs, ref_profile,
                           dst_crs, year_label):
    profile = ref_profile.copy()
    profile.pop("photometric", None)
    profile.update(count=src_count, dtype=src_dtype,
                   compress="lzw", predictor=2, bigtiff="IF_SAFER",
                   tiled=True, blockxsize=512, blockysize=512)

    src_t = (Affine(*src_transform) if isinstance(src_transform, tuple)
             else src_transform)

    try:
        with rasterio.open(dst_local, "w", **profile) as dst:
            for band_i in tqdm(range(1, src_count + 1),
                               desc=f"  Reprojecting {year_label} bands"):
                tick(f"band {band_i}/{src_count}")
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
                tock(f"band {band_i}/{src_count}")
                gc.collect()
    except Exception:
        if dst_local.exists():
            dst_local.unlink()
            print(f"  Partial output deleted: {dst_local.name}",
                  flush=True)
        raise


# ── Parallel chunked reproject ────────────────────────────────────────────

def _do_chunked_reproject(local_src, dst_local, src_count, src_dtype,
                          src_transform, src_crs, ref_profile,
                          dst_crs, year_label):
    out_w         = ref_profile["width"]
    out_h         = ref_profile["height"]
    out_transform = ref_profile["transform"]

    profile = ref_profile.copy()
    profile.pop("photometric", None)
    profile.update(count=src_count, dtype=src_dtype,
                   compress="lzw", predictor=2, bigtiff="IF_SAFER",
                   tiled=True, blockxsize=512, blockysize=512)

    chunk_windows = make_tile_windows(out_w, out_h, UPSAMPLE_CHUNK_PX)
    n_chunks      = len(chunk_windows)
    N_DIAG_CHUNKS = 20
    failed_chunks = 0

    try:
        _spawn_ctx = mp.get_context("spawn")
    except Exception:
        _spawn_ctx = mp

    print(f"\n  Pre-allocating output file...", flush=True)
    with rasterio.open(dst_local, "w", **profile):
        pass

    for band_i in range(1, src_count + 1):
        print(f"\n  {'═'*50}", flush=True)
        print(f"  BAND {band_i}/{src_count}  —  year {year_label}",
              flush=True)
        mem(f"{year_label} band {band_i} start")

        band_tasks = [
            (win.col_off, win.row_off, win.width, win.height,
             tuple(rasterio.windows.transform(win, out_transform)))
            for win in chunk_windows
        ]
        band_batches = [
            band_tasks[i:i + WORKER_BATCH_SIZE]
            for i in range(0, len(band_tasks), WORKER_BATCH_SIZE)
        ]
        batch_args = [
            (str(local_src), band_i, batch,
             src_transform, src_crs, dst_crs,
             src_dtype, 512)
            for batch in band_batches
        ]

        completed   = 0
        band_failed = 0
        seen_pids   = set()
        times_ms    = []
        last_t      = time.time()
        band_t0     = time.time()

        tick(f"band {band_i}/{src_count}")

        with rasterio.open(dst_local, "r+") as dst:
            with _spawn_ctx.Pool(processes=N_UPSAMPLE_WORKERS,
                                 maxtasksperchild=None) as pool:

                async_iter = pool.imap_unordered(
                    _reproject_chunk_batch, batch_args, chunksize=1)

                pbar = tqdm(total=len(band_tasks),
                            desc=f"  band {band_i} chunks",
                            mininterval=10, miniters=50)

                while completed < len(band_tasks):
                    wait_s = time.time() - last_t
                    if wait_s > WORKER_STALL_TIMEOUT_S:
                        pool.terminate()
                        pool.join()
                        pbar.close()
                        raise RuntimeError(
                            f"Stalled for {wait_s:.0f}s at chunk "
                            f"{completed}/{len(band_tasks)} "
                            f"band {band_i} year {year_label}")

                    try:
                        batch_results = next(async_iter)
                    except StopIteration:
                        break
                    except Exception as e:
                        print(f"  [ERR] imap raised: {e}", flush=True)
                        completed   += WORKER_BATCH_SIZE
                        band_failed += WORKER_BATCH_SIZE
                        pbar.update(WORKER_BATCH_SIZE)
                        last_t = time.time()
                        continue

                    last_t = time.time()

                    for result in batch_results:
                        (b_i, col_off, row_off, cw, ch,
                         arr, failed, error_msg,
                         worker_pid, open_ms, proj_ms,
                         total_ms) = result

                        seen_pids.add(worker_pid)
                        times_ms.append(total_ms)

                        if completed < N_DIAG_CHUNKS:
                            status = "FAIL" if failed else "ok"
                            print(
                                f"  [DIAG] chunk {completed:>4}  "
                                f"col={col_off:>6}  row={row_off:>6}  "
                                f"pid={worker_pid}  "
                                f"proj={proj_ms}ms  total={total_ms}ms"
                                f"  [{status}]"
                                + (f"  ERR: {error_msg}"
                                   if failed else ""),
                                flush=True)

                        if completed > 0 and completed % 200 == 0:
                            elapsed = time.time() - band_t0
                            rate    = (completed / elapsed
                                       if elapsed > 0 else 0)
                            eta_s   = ((len(band_tasks) - completed)
                                       / rate if rate > 0 else 0)
                            recent  = times_ms[-200:]
                            avg_ms  = sum(recent) // len(recent)
                            print(
                                f"\n  [PROG] chunk "
                                f"{completed}/{len(band_tasks)}  "
                                f"({100*completed/len(band_tasks):.1f}%)  "
                                f"rate={rate:.1f}/s  "
                                f"ETA={eta_s/60:.1f}min  "
                                f"avg={avg_ms}ms  "
                                f"workers={len(seen_pids)}",
                                flush=True)
                            mem(f"{year_label} band {band_i} "
                                f"chunk {completed}")

                        win = rasterio.windows.Window(
                            col_off, row_off, cw, ch)
                        try:
                            dst.write(arr, band_i, window=win)
                        except Exception as we:
                            print(f"  [ERR] write chunk "
                                  f"{completed}: {we}", flush=True)
                            band_failed += 1

                        if failed:
                            band_failed += 1

                        del arr
                        del result
                        completed += 1
                        pbar.update(1)

                    if completed % 100 == 0:
                        _trim()

                pbar.close()

        tock(f"band {band_i}/{src_count}")
        failed_chunks += band_failed

        print(f"\n  Band {band_i}: "
              f"{(time.time() - band_t0)/60:.1f} min  "
              f"({band_failed} failed chunks)", flush=True)
        if times_ms:
            print(f"  Chunk timing: min={min(times_ms)}ms  "
                  f"max={max(times_ms)}ms  "
                  f"mean={sum(times_ms)//len(times_ms)}ms",
                  flush=True)

        _drop_page_cache_file(dst_local)
        _trim()

    if failed_chunks > 0:
        print(f"\n  Total failed chunks: "
              f"{failed_chunks}/{n_chunks * src_count}", flush=True)


# ── Upsample one year ────────────────────────────────────────────────────

def upsample_year(entry: dict, ref_profile: dict,
                  force: bool = False) -> Path:
    """
    Reproject one year to the 2020 reference grid.
    Returns the path to the Drive output file.
    CoE years (needs_upsample=False) are copied rather than reprojected.
    """
    year_label = entry["label"]
    src_path   = _upsample_raw_path(entry)
    drive_dst  = _upsample_drive_path(entry)
    local_dst  = _upsample_local_path(entry)

    print(f"\n  {'─'*56}", flush=True)
    print(f"  YEAR {year_label}  —  {src_path.name}", flush=True)
    print(f"  {'─'*56}", flush=True)

    if not src_path.exists():
        raise FileNotFoundError(f"Source not found: {src_path}")

    # ── CoE years: copy to upsample folder unchanged ──────────
    if not entry["needs_upsample"]:
        if drive_dst.exists() and not force:
            ok, msg = _validate_upsample(drive_dst, ref_profile)
            if ok:
                print(f"  Already in upsample folder — skipping: {msg}",
                      flush=True)
                return drive_dst
            else:
                print(f"  Existing file invalid ({msg}) — re-copying",
                      flush=True)

        print(f"  City of Edmonds year — copying to upsample folder",
              flush=True)
        tick("copy: CoE → upsample folder")
        shutil.copy2(src_path, drive_dst)
        tock("copy: CoE → upsample folder")
        print(f"  ✓ {drive_dst.name}  "
              f"({drive_dst.stat().st_size/1e9:.2f} GB)", flush=True)
        return drive_dst

    # ── Check Drive cache ─────────────────────────────────────
    if drive_dst.exists() and not force:
        ok, msg = _validate_upsample(drive_dst, ref_profile)
        if ok:
            print(f"  Drive cache valid — skipping: {msg}", flush=True)
            return drive_dst
        else:
            print(f"  Drive cache invalid ({msg}) — rebuilding",
                  flush=True)
            drive_dst.unlink()

    # ── Copy source to local disk ─────────────────────────────
    local_src = LOCAL_SRC_DIR / src_path.name
    if not local_src.exists() or local_src.stat().st_size < 1e9:
        LOCAL_SRC_DIR.mkdir(parents=True, exist_ok=True)
        size_gb = src_path.stat().st_size / 1e9
        print(f"  Copying source to local SSD: {src_path.name}  "
              f"({size_gb:.1f} GB)", flush=True)
        tick("copy: Drive → local SSD")
        shutil.copy2(src_path, local_src)
        tock("copy: Drive → local SSD")
        drop_all_page_cache()
        mem(f"{year_label} after source copy")
    else:
        print(f"  Source already local: {local_src.name}  "
              f"({local_src.stat().st_size/1e9:.1f} GB)", flush=True)

    # ── Read source metadata ──────────────────────────────────
    with rasterio.open(local_src) as src_f:
        src_res       = metres_per_pixel(src_f.transform)
        ref_res       = metres_per_pixel(ref_profile["transform"])
        scale_factor  = src_res / ref_res
        src_count     = src_f.count
        src_dtype     = src_f.dtypes[0]
        src_crs       = src_f.crs.to_wkt()
        src_transform = tuple(src_f.transform)
        src_w         = src_f.width
        src_h         = src_f.height

    print(f"  Source       : {src_w}x{src_h} px  "
          f"{src_count} bands  {src_dtype}", flush=True)
    print(f"  Scale factor : {src_res:.4f}m → {ref_res:.4f}m  "
          f"(x{scale_factor:.2f})", flush=True)
    print(f"  Output       : {ref_profile['width']}x"
          f"{ref_profile['height']} px", flush=True)

    LOCAL_OUT_DIR.mkdir(parents=True, exist_ok=True)
    dst_crs = (ref_profile["crs"].to_wkt()
               if hasattr(ref_profile["crs"], "to_wkt")
               else str(ref_profile["crs"]))

    os.environ["GDAL_CACHEMAX"] = "256"
    tick(f"upsample {year_label}")

    try:
        if scale_factor <= POOL_SCALE_THRESHOLD:
            print(f"  Strategy: single-threaded full-band reproject "
                  f"(scale {scale_factor:.2f}x "
                  f"≤ {POOL_SCALE_THRESHOLD}x)", flush=True)
            _do_fullband_reproject(
                local_src, local_dst,
                src_count, src_dtype, src_transform, src_crs,
                ref_profile, dst_crs, year_label)
        else:
            print(f"  Strategy: parallel chunked reproject "
                  f"(scale {scale_factor:.2f}x "
                  f"> {POOL_SCALE_THRESHOLD}x  "
                  f"{N_UPSAMPLE_WORKERS} workers)", flush=True)
            _do_chunked_reproject(
                local_src, local_dst,
                src_count, src_dtype, src_transform, src_crs,
                ref_profile, dst_crs, year_label)

    except Exception as e:
        if local_dst.exists():
            local_dst.unlink()
            print(f"  Partial output deleted: {local_dst.name}",
                  flush=True)
        raise RuntimeError(
            f"Upsample failed for {year_label}: {e}") from e

    tock(f"upsample {year_label}")

    # ── Validate ──────────────────────────────────────────────
    ok, msg = _validate_upsample(local_dst, ref_profile)
    if not ok:
        local_dst.unlink()
        raise RuntimeError(
            f"Validation failed for {year_label}: {msg}")
    print(f"  Validation: {msg}", flush=True)
    mem(f"{year_label} after upsample")

    # ── Copy to Drive ─────────────────────────────────────────
    UPSAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    size_gb = local_dst.stat().st_size / 1e9
    print(f"\n  Copying to Drive ({size_gb:.1f} GB)...", flush=True)
    tick("copy: local → Drive")
    shutil.copy2(local_dst, drive_dst)
    tock("copy: local → Drive")
    drop_all_page_cache()
    print(f"  ✓ Drive: {drive_dst.name}  "
          f"({drive_dst.stat().st_size/1e9:.2f} GB)", flush=True)

    return drive_dst


def _clean_local(entry: dict):
    """Remove local scratch files for one year."""
    freed = 0.0
    for path in [LOCAL_SRC_DIR / entry["native_file"],
                 _upsample_local_path(entry)]:
        if path.exists():
            size_gb = path.stat().st_size / 1e9
            path.unlink()
            freed += size_gb
            print(f"    Deleted: {path.name}  ({size_gb:.1f} GB)",
                  flush=True)
    if freed > 0:
        print(f"    Freed: {freed:.1f} GB", flush=True)
    _trim()
    mem(f"{entry['label']} after cleanup")


def step_upsample(year_entries: list, force: bool = False):
    """
    Step 0 — Upsample all requested years to the 2020 reference grid.
    Skips years whose upsampled file already exists and validates.
    """
    print(f"\n── Step 0: Upsample Imagery "
          f"({len(year_entries)} years) ──")

    mem("upsample startup")
    _, _, free = shutil.disk_usage("/content")
    print(f"  Local disk: {free/1e9:.0f} GB free", flush=True)

    for d in [LOCAL_SRC_DIR, LOCAL_OUT_DIR, UPSAMPLE_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Load reference profile from 2020 source
    ref_src = IMAGERY_DIR / "2020_coe_rgb.tif"
    if not ref_src.exists():
        print(f"\n  ERROR: Reference imagery not found: {ref_src}",
              flush=True)
        sys.exit(1)
    with rasterio.open(ref_src) as src:
        ref_profile = src.profile.copy()
    print(f"  Reference profile: "
          f"{ref_profile['width']}x{ref_profile['height']}  "
          f"{ref_profile['crs']}  "
          f"{metres_per_pixel(ref_profile['transform']):.4f} m/px",
          flush=True)

    results = []

    for i, entry in enumerate(year_entries):
        print(f"\n{'='*60}", flush=True)
        print(f"  YEAR {entry['label']}  ({i+1}/{len(year_entries)})",
              flush=True)
        print(f"{'='*60}", flush=True)

        t0 = time.time()
        try:
            out = upsample_year(entry, ref_profile, force=force)
            elapsed = time.time() - t0
            results.append(
                (entry["label"], "pass",
                 f"{out.name}  ({elapsed/60:.1f} min)"))
        except Exception as e:
            import traceback
            elapsed = time.time() - t0
            print(f"\n  FATAL: {e}", flush=True)
            traceback.print_exc()
            results.append((entry["label"], "fail", str(e)))

        gc.collect()
        mem(f"{entry['label']} after gc")

        if entry["needs_upsample"]:
            print(f"\n  Cleaning local scratch for "
                  f"{entry['label']}...", flush=True)
            _clean_local(entry)

    # Summary
    print(f"\n{'='*60}", flush=True)
    print(f"  UPSAMPLE SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)
    for label, status, msg in results:
        icon = "✓" if status == "pass" else "✗"
        print(f"  {icon} {label}  [{status.upper()}]  {msg}",
              flush=True)
    passed = sum(1 for _, s, _ in results if s == "pass")
    print(f"\n  {passed}/{len(results)} years complete", flush=True)
    print(f"  Output: {UPSAMPLE_DIR}", flush=True)

    timer_summary()
    return results


# ═════════════════════════════════════════════════════════════════════════════
#  SPECTRAL HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def sample_pixels(geom, src):
    """
    Sample all valid pixels under a polygon.
    Returns (R, G, B) float32 arrays or (None, None, None).
    Always uses bands 1-3 — handles 4-band RGBI automatically.
    """
    try:
        out_image, _ = rio_mask(src, [geom], crop=True,
                                all_touched=False, nodata=0, filled=True)
        valid = np.all(out_image[:3] > 0, axis=0)
        if valid.sum() == 0:
            return None, None, None
        r = out_image[0][valid].astype(np.float32)
        g = out_image[1][valid].astype(np.float32)
        b = out_image[2][valid].astype(np.float32)
        return r, g, b
    except Exception:
        return None, None, None


def ndvi_proxy_scalar(r_mean: float, g_mean: float) -> float:
    denom = g_mean + r_mean
    return float((g_mean - r_mean) / denom) if denom > 1e-6 else 0.0


def luminance_scalar(r_mean: float, g_mean: float,
                     b_mean: float) -> float:
    return float(0.299 * r_mean + 0.587 * g_mean + 0.114 * b_mean)


def ndvi_proxy_px(r, g):
    denom = g + r
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(denom > 0, (g - r) / denom, 0.0)


def luminance_px(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


# ── Multiprocessing worker ────────────────────────────────────────────────
#
# OPTIMISATION: the raster is opened ONCE per worker process (via the pool
# initializer) and reused across all crowns that worker handles. The old
# version did `rasterio.open(...)` for every single crown, which is millions
# of redundant header parses per year. Keeping the handle open is typically
# a 2–3x speedup on rio_mask-style workloads.
#
# INSTRUMENTATION: each worker tracks per-task timing and emits a stats
# line every WORKER_LOG_EVERY tasks. Stats include: tasks done, mean ms
# per crown, max ms (slowest crown seen), % returning None, total px
# sampled. Use this to spot uneven worker load and slow polygons.

WORKER_LOG_EVERY = 20000   # one log line per worker every N crowns (~once at ~50% for 222k crowns)

# Module-level handle populated by the pool initializer in each worker.
_WORKER_SRC      = None
_WORKER_PATH     = None
_WORKER_PID      = None
_WORKER_STATS    = None   # dict of running counters per worker


def _init_spectral_worker(imagery_path: str):
    """Pool initializer — open the raster once per worker process."""
    global _WORKER_SRC, _WORKER_PATH, _WORKER_PID, _WORKER_STATS
    _WORKER_PATH = imagery_path
    _WORKER_PID  = os.getpid()
    t0 = time.time()
    _WORKER_SRC = rasterio.open(imagery_path)
    elapsed_ms = (time.time() - t0) * 1000
    _WORKER_STATS = {
        "tasks":        0,
        "none_count":   0,
        "px_total":     0,
        "t_mask_ms":    0.0,
        "t_total_ms":   0.0,
        "max_ms":       0.0,
        "max_crown_id": None,
        "t_start":      time.time(),
        "t_last_log":   time.time(),
    }
    # Print one open line so we can see workers spin up
    print(f"  [WORKER pid={_WORKER_PID}] opened raster in "
          f"{elapsed_ms:.0f}ms  ({Path(imagery_path).name})",
          flush=True)


def _crown_spectral_worker(args):
    import shapely.wkt
    crown_id, geom_wkt, year_key, season_alpha = args

    t_task = time.time()
    geom = shapely.wkt.loads(geom_wkt)

    result = {"crown_id": crown_id}
    for c in raw_spectral_cols(year_key):
        result[c] = season_alpha if "season_alpha" in c else np.nan

    n_px = 0
    try:
        # Reuse the per-worker open handle instead of re-opening every call.
        t_mask = time.time()
        r, g, b = sample_pixels(geom, _WORKER_SRC)
        mask_ms = (time.time() - t_mask) * 1000

        if r is None:
            _WORKER_STATS["none_count"] += 1
        else:
            n_px = len(r)
            r_m = float(r.mean())
            g_m = float(g.mean())
            b_m = float(b.mean())
            result[_col("rgb_mean_r",   year_key)] = r_m
            result[_col("rgb_mean_g",   year_key)] = g_m
            result[_col("rgb_mean_b",   year_key)] = b_m
            result[_col("ndvi_proxy",   year_key)] = ndvi_proxy_scalar(r_m, g_m)
            result[_col("luminance",    year_key)] = luminance_scalar(r_m, g_m, b_m)

        _WORKER_STATS["t_mask_ms"] += mask_ms
    except Exception as e:
        _WORKER_STATS["none_count"] += 1
        # Surface the first few failures so silent breakage doesn't hide.
        if _WORKER_STATS["tasks"] < 3:
            print(f"  [WORKER pid={_WORKER_PID}] crown {crown_id} "
                  f"raised: {type(e).__name__}: {e}", flush=True)

    total_ms = (time.time() - t_task) * 1000
    s = _WORKER_STATS
    s["tasks"]      += 1
    s["px_total"]   += n_px
    s["t_total_ms"] += total_ms
    if total_ms > s["max_ms"]:
        s["max_ms"]       = total_ms
        s["max_crown_id"] = crown_id

    # Periodic per-worker stats line (cheap; only every N tasks)
    if s["tasks"] % WORKER_LOG_EVERY == 0:
        elapsed = time.time() - s["t_start"]
        rate    = s["tasks"] / elapsed if elapsed > 0 else 0
        mean_ms = s["t_total_ms"] / s["tasks"]
        mask_pct = (100 * s["t_mask_ms"] / s["t_total_ms"]
                    if s["t_total_ms"] > 0 else 0)
        avg_px  = s["px_total"] / max(1, s["tasks"] - s["none_count"])
        print(f"  [WORKER pid={_WORKER_PID}] {s['tasks']:>6} done  "
              f"rate={rate:5.0f}/s  "
              f"mean={mean_ms:5.1f}ms  "
              f"mask={mask_pct:4.1f}%  "
              f"none={s['none_count']:>4}  "
              f"avg_px={avg_px:6.0f}  "
              f"max={s['max_ms']:5.0f}ms (id={s['max_crown_id']})",
              flush=True)
        s["t_last_log"] = time.time()

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Step 1 — Load inputs
# ─────────────────────────────────────────────────────────────────────────────

def load_inputs():
    print("\n── Step 1: Loading inputs ──")

    ref_imagery = UPSAMPLE_DIR / "2020_coe_rgb.tif"
    with rasterio.open(ref_imagery) as src:
        img_crs  = src.crs
        b        = src.bounds
        img_bbox = box(b.left, b.bottom, b.right, b.top)
    print(f"  Reference CRS  : {img_crs}")

    crowns = gpd.read_file(CROWNS_IN)
    print(f"  Crowns loaded  : {len(crowns):,}  (CRS: {crowns.crs})")
    if crowns.crs != img_crs:
        crowns = crowns.to_crs(img_crs)

    buildings = gpd.read_file(BUILDINGS)
    print(f"  Buildings      : {len(buildings):,}  (CRS: {buildings.crs})")
    if buildings.crs != img_crs:
        buildings = buildings.to_crs(img_crs)
    buildings = (buildings[buildings.geometry.is_valid]
                 .reset_index(drop=True))
    buildings["building_id"] = buildings.index
    print(f"  Valid buildings: {len(buildings):,}")

    water = gpd.read_file(WATER)
    print(f"  Water bodies   : {len(water):,}  (CRS: {water.crs})")
    if water.crs != img_crs:
        water = water.to_crs(img_crs)
    water = water[water.geometry.is_valid]
    water = gpd.clip(water,
                     gpd.GeoDataFrame(geometry=[img_bbox], crs=img_crs))
    water = water[~water.geometry.is_empty].reset_index(drop=True)
    print(f"  Water (clipped): {len(water):,}")

    print(f"\n  Imagery files:")
    missing = []
    for entry in YEAR_CATALOG:
        path   = UPSAMPLE_DIR / entry["file"]
        status = "OK" if path.exists() else "MISSING"
        print(f"    {entry['label']:<10} {status}  {entry['file']}")
        if not path.exists():
            missing.append(entry["key"])
    if missing:
        print(f"\n  WARNING: {len(missing)} year(s) will be skipped: "
              f"{missing}")

    return crowns, buildings, water, img_crs


def _load_buildings(img_crs):
    """Load and reproject buildings — used when resuming from checkpoint."""
    buildings = gpd.read_file(BUILDINGS)
    if buildings.crs != img_crs:
        buildings = buildings.to_crs(img_crs)
    buildings = (buildings[buildings.geometry.is_valid]
                 .reset_index(drop=True))
    buildings["building_id"] = buildings.index
    return buildings


# ─────────────────────────────────────────────────────────────────────────────
#  Step 2 — Within-water join
# ─────────────────────────────────────────────────────────────────────────────

def compute_within_water(crowns: gpd.GeoDataFrame,
                         water:  gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    print("\n── Step 2: Within-water join ──")
    if len(water) == 0:
        crowns["within_water"] = False
        return crowns

    centroids = crowns.copy()
    centroids["geometry"] = crowns.geometry.centroid
    joined = gpd.sjoin(
        centroids[["crown_id", "geometry"]],
        water[["geometry"]],
        how="left", predicate="within")
    water_ids = set(joined[joined["index_right"].notna()]["crown_id"])
    crowns["within_water"] = crowns["crown_id"].isin(water_ids)
    n = crowns["within_water"].sum()
    print(f"  Crowns within water: {n:,}  ({100*n/len(crowns):.2f}%)")
    return crowns


# ─────────────────────────────────────────────────────────────────────────────
#  Step 3 — Building distance
# ─────────────────────────────────────────────────────────────────────────────

def compute_building_distance(crowns:    gpd.GeoDataFrame,
                               buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    print("\n── Step 3: Building distance ──")
    centroids = crowns.geometry.centroid
    sindex    = buildings.sindex
    bldg_dist = np.full(len(crowns), np.nan, dtype=np.float32)

    for start in tqdm(range(0, len(crowns), 5000),
                      desc="  bldg_dist_m", unit="chunk"):
        end = min(start + 5000, len(crowns))
        for i in range(start, end):
            pt         = centroids.iloc[i]
            candidates = list(sindex.query(pt.buffer(200)))
            if not candidates:
                nearest    = np.asarray(sindex.nearest(pt, return_all=False))
                candidates = (nearest[1].flatten().tolist()
                              if nearest.ndim == 2
                              else nearest.flatten().tolist())
            if candidates:
                dists        = buildings.iloc[candidates].geometry.distance(pt)
                bldg_dist[i] = float(dists.min())

    crowns["bldg_dist_m"] = bldg_dist
    print(f"  min: {np.nanmin(bldg_dist):.2f} m  "
          f"median: {np.nanmedian(bldg_dist):.2f} m  "
          f"max: {np.nanmax(bldg_dist):.2f} m")
    return crowns


# ─────────────────────────────────────────────────────────────────────────────
#  Step 4 — Roof spectral scoring
# ─────────────────────────────────────────────────────────────────────────────

def compute_roof_spectral_scores(
        buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    print("\n── Step 4: Roof spectral scoring (2020) ──")
    imagery_path = UPSAMPLE_DIR / "2020_coe_rgb.tif"

    # Stage to local SSD for faster sequential reads
    local_img = _stage_imagery_local(imagery_path)

    roof_px   = np.zeros(len(buildings), dtype=np.int32)
    veg_px    = np.zeros(len(buildings), dtype=np.int32)
    shadow_px = np.zeros(len(buildings), dtype=np.int32)
    total_px  = np.zeros(len(buildings), dtype=np.int32)
    scores    = np.full(len(buildings), np.nan, dtype=np.float32)

    with rasterio.open(local_img) as src:
        for i, row in tqdm(buildings.iterrows(),
                           total=len(buildings),
                           desc="  Scoring buildings"):
            r, g, b = sample_pixels(row.geometry, src)
            if r is None:
                continue
            n            = len(r)
            total_px[i]  = n
            lum          = luminance_px(r, g, b)
            ndvi         = ndvi_proxy_px(r, g)
            shadow_mask  = lum < LUM_SHADOW_MAX
            lit          = ~shadow_mask
            shadow_px[i] = int(shadow_mask.sum())
            roof_px[i]   = int((lit & (ndvi < NDVI_ROOF_MAX)).sum())
            veg_px[i]    = int((lit & (ndvi > NDVI_VEG_MIN)).sum())
            valid_denom  = n - shadow_px[i]
            if valid_denom > 0:
                scores[i] = roof_px[i] / valid_denom

    result = buildings[["building_id", "geometry"]].copy()
    result["year"]                = 2020
    result["roof_px_count"]       = roof_px
    result["veg_px_count"]        = veg_px
    result["shadow_px_count"]     = shadow_px
    result["total_px_count"]      = total_px
    result["roof_spectral_score"] = scores

    valid = result["roof_spectral_score"].dropna()
    print(f"  Valid: {len(valid):,} / {len(buildings):,}")
    for thresh, label in [
        (0.8, "≥ 0.8 (confident roof)"),
        (0.5, "0.5–0.8 (mixed)"),
        (0.0, "< 0.5 (likely canopy)"),
    ]:
        n = ((valid >= thresh) if thresh == 0.0
             else (valid >= thresh) if thresh == 0.8
             else ((valid >= 0.5) & (valid < 0.8))).sum()
        if thresh == 0.0:
            n = (valid < 0.5).sum()
        print(f"    {label}: {n:,}  ({100*n/len(valid):.1f}%)")

    _unstage_imagery_local(local_img)
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Step 5 — Roof score proximity join
# ─────────────────────────────────────────────────────────────────────────────

def join_roof_scores(crowns:      gpd.GeoDataFrame,
                     bldg_scores: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    print("\n── Step 5: Roof score proximity join ──")
    centroids = crowns.copy()
    centroids["geometry"] = crowns.geometry.centroid.buffer(5)

    joined = gpd.sjoin(
        centroids[["crown_id", "geometry"]],
        bldg_scores[["building_id", "geometry", "roof_spectral_score"]],
        how="left", predicate="intersects")

    roof_nearby = (joined
                   .groupby("crown_id")["roof_spectral_score"]
                   .max()
                   .rename("roof_score_nearby"))
    crowns = crowns.join(roof_nearby, on="crown_id")
    crowns["roof_score_nearby"] = crowns["roof_score_nearby"].fillna(0.0)

    high = (crowns["roof_score_nearby"] >= 0.8).sum()
    print(f"  Near confident roof (≥0.8): {high:,}  "
          f"({100*high/len(crowns):.1f}%)")
    return crowns


# ─────────────────────────────────────────────────────────────────────────────
#  Step 6 — Per-year raw spectral sampling
# ─────────────────────────────────────────────────────────────────────────────

def _copy_with_progress(src: Path, dst: Path,
                         chunk_mb: int = 64,
                         label: str = "") -> float:
    """
    Copy a file from src to dst in chunks, logging throughput every
    ~2 seconds. Returns total elapsed seconds.

    Use this instead of shutil.copy2 when you want visibility into long
    copies (e.g. Drive → SSD where the link is the bottleneck).
    """
    chunk = chunk_mb * 1024 * 1024
    total_size = src.stat().st_size
    total_gb = total_size / 1e9

    print(f"  [COPY] {label}: {src.name} → {dst.name}  "
          f"({total_gb:.2f} GB, {chunk_mb} MB chunks)", flush=True)

    copied = 0
    t_start = time.time()
    t_last = t_start
    bytes_since_last = 0
    last_copy_pct_logged = -1

    with keepalive(f"copy {src.stem}"), \
         open(src, "rb") as fin, open(dst, "wb") as fout:
        while True:
            buf = fin.read(chunk)
            if not buf:
                break
            fout.write(buf)
            copied           += len(buf)
            bytes_since_last += len(buf)

            now      = time.time()
            pct      = 100 * copied / total_size
            pct_bucket = int(pct // 10)
            if pct_bucket > last_copy_pct_logged:
                last_copy_pct_logged = pct_bucket
                inst_mbs = bytes_since_last / max(now - t_last, 1e-6) / 1e6
                avg_mbs  = copied / max(now - t_start, 1e-6) / 1e6
                eta      = ((total_size - copied) / (copied / max(now - t_start, 1e-6))
                            if copied else 0)
                print(f"    [COPY] {label}: {copied/1e9:5.2f}/"
                      f"{total_gb:.2f} GB  ({pct:5.1f}%)  "
                      f"inst={inst_mbs:6.1f} MB/s  "
                      f"avg={avg_mbs:6.1f} MB/s  "
                      f"ETA={eta:5.0f}s", flush=True)
                t_last = now
                bytes_since_last = 0

    elapsed = time.time() - t_start
    final_mbs = total_size / elapsed / 1e6 if elapsed > 0 else 0
    # Preserve mtime/permissions like shutil.copy2
    try:
        shutil.copystat(src, dst)
    except Exception:
        pass
    print(f"  [COPY] {label}: DONE  {total_gb:.2f} GB in "
          f"{elapsed:.1f}s  ({final_mbs:.1f} MB/s avg)", flush=True)
    return elapsed


def _stage_imagery_local(drive_path: Path) -> Path:
    """
    Copy an upsampled TIF from Drive to local SSD for fast parallel reads.
    Returns the local path. Skips if already staged.
    """
    LOCAL_SPECTRAL_DIR.mkdir(parents=True, exist_ok=True)
    local_path = LOCAL_SPECTRAL_DIR / drive_path.name

    if local_path.exists():
        # Validate: same size as Drive copy
        if local_path.stat().st_size == drive_path.stat().st_size:
            print(f"  [STAGE] already staged — {local_path.name}",
                  flush=True)
            return local_path
        else:
            print(f"  [STAGE] size mismatch — re-staging "
                  f"{local_path.name}", flush=True)
            local_path.unlink()

    size_gb = drive_path.stat().st_size / 1e9
    _, _, free_b = shutil.disk_usage("/content")
    print(f"  [STAGE] start: {drive_path.name}  ({size_gb:.1f} GB)  "
          f"free={free_b/1e9:.1f} GB", flush=True)
    tick("stage: Drive → local SSD")
    _copy_with_progress(drive_path, local_path,
                        label=f"stage {drive_path.stem}")
    tock("stage: Drive → local SSD")
    drop_all_page_cache(silent=True)
    _, _, free_after = shutil.disk_usage("/content")
    print(f"  [STAGE] done: {local_path.name}  "
          f"free now={free_after/1e9:.1f} GB", flush=True)
    return local_path


def _unstage_imagery_local(local_path: Path):
    """Remove a staged TIF from local SSD after use."""
    if local_path.exists() and str(local_path).startswith("/content/"):
        size_gb = local_path.stat().st_size / 1e9
        local_path.unlink()
        print(f"  Unstaged: {local_path.name}  ({size_gb:.1f} GB)",
              flush=True)
        _trim()


def _can_prefetch(next_entry: dict,
                  current_staged_path: Path = None) -> tuple:
    """
    Decide whether we have enough local SSD space AND RAM to prefetch the
    next year's imagery while the current year is still being sampled.

    Returns (ok, reason).

    The key fix vs the previous version: we subtract the size of the
    *currently staged* file from free space, because `shutil.disk_usage`
    reports free bytes but the staged file is already consuming SSD space
    that won't be freed until AFTER sampling completes. Without this,
    the check is optimistic and can allow a copy that fills the disk.
    """
    drive_path = UPSAMPLE_DIR / next_entry["file"]
    local_path = LOCAL_SPECTRAL_DIR / next_entry["file"]

    if local_path.exists():
        return False, "already staged"
    if not drive_path.exists():
        return False, "source missing"

    need_gb = drive_path.stat().st_size / 1e9

    # How much SSD is genuinely available?
    _, _, free_b = shutil.disk_usage("/content")
    free_gb = free_b / 1e9

    # Subtract the current staged file — it is on SSD right now and won't
    # be deleted until after sampling finishes (i.e. after the prefetch
    # would land). disk_usage already reflects it as "used", so this is
    # already baked in — but log it so the reason string is informative.
    current_gb = 0.0
    if current_staged_path and current_staged_path.exists():
        current_gb = current_staged_path.stat().st_size / 1e9

    margin = free_gb - need_gb
    if margin < PREFETCH_HEADROOM_GB:
        return False, (
            f"insufficient SSD space: need {need_gb:.1f} GB, "
            f"free {free_gb:.1f} GB (current staged={current_gb:.1f} GB), "
            f"would leave {margin:.1f} GB < "
            f"{PREFETCH_HEADROOM_GB:.0f} GB headroom")

    # RAM guard: prefetch thread + sampling workers both run concurrently.
    # If RAM is above 80% don't add more pressure.
    vm = psutil.virtual_memory()
    if vm.percent > 80:
        return False, (
            f"RAM too high ({vm.percent:.0f}% used) — "
            f"skipping prefetch to avoid OOM")

    return True, (f"SSD ok: need {need_gb:.1f} GB, "
                  f"free {free_gb:.1f} GB, "
                  f"margin {margin:.1f} GB  |  "
                  f"RAM {vm.percent:.0f}%")


def _sort_crowns_by_tile(crowns: gpd.GeoDataFrame,
                         imagery_path: Path,
                         tile_px: int = SPECTRAL_TILE_PX) -> pd.Index:
    """
    Return crown DataFrame indices sorted by raster tile (row-major), so
    workers consume crowns whose pixels live near each other in the file.
    This dramatically improves OS page-cache reuse — without it, workers
    jump randomly around a 148k×211k raster and thrash the cache.

    Uses centroid coordinates and the imagery transform.
    """
    with rasterio.open(imagery_path) as src:
        transform = src.transform

    # Vectorised centroid → tile bucket. Faster than .apply per-geom.
    cx = crowns.geometry.centroid.x.to_numpy()
    cy = crowns.geometry.centroid.y.to_numpy()
    inv = ~transform
    cols = inv.a * cx + inv.b * cy + inv.c
    rows = inv.d * cx + inv.e * cy + inv.f
    tile_row = (rows.astype(np.int64) // tile_px)
    tile_col = (cols.astype(np.int64) // tile_px)

    # Single sort key: row major. int64 keeps things cheap.
    sort_key = tile_row * np.int64(10**7) + tile_col
    order = np.argsort(sort_key, kind="stable")
    return crowns.index[order]


def compute_spectral_year(crowns:          gpd.GeoDataFrame,
                          entry:           dict,
                          buildings:       gpd.GeoDataFrame,
                          bldg_ndvi_cache: dict,
                          force:           bool = False,
                          local_img:       Path = None,
                          checkpoint:      bool = True) -> gpd.GeoDataFrame:
    """
    Sample raw spectral features for one year.

    Optimisations vs the original:
      • If `local_img` is provided (e.g. by a prefetcher thread), skip
        staging — the file is already on local SSD.
      • Crowns are sorted by raster-tile bucket so workers hit hot pages.
      • Pool uses an initializer to open the raster ONCE per worker.
      • Checkpoint to GPKG only when `checkpoint=True` (caller decides
        cadence). Big writes between every year add up to ~30+ min total.

    INSTRUMENTATION: every sub-phase is timed; main thread logs progress
    every PROGRESS_INTERVAL_S seconds with rate, ETA, RAM, and result
    backlog. Workers log their own stats every WORKER_LOG_EVERY tasks.
    """
    PROGRESS_INTERVAL_S = 5.0   # main-thread progress log cadence (kept as fallback)
    PROGRESS_INTERVAL_PCT = 10  # log every this many percent complete

    year_key     = entry["key"]
    label        = entry["label"]
    season_alpha = entry["season_alpha"]
    imagery_path = UPSAMPLE_DIR / entry["file"]
    cols         = raw_spectral_cols(year_key)

    if not force and all(c in crowns.columns for c in cols):
        mean = crowns[_col("ndvi_proxy", year_key)].mean()
        print(f"  [SKIP] {label:<10} already computed "
              f"(ndvi={mean:.3f})", flush=True)
        return crowns

    if not imagery_path.exists():
        print(f"  [MISSING] {label:<10} imagery not found — filling NaN",
              flush=True)
        for c in cols:
            crowns[c] = season_alpha if "season_alpha" in c else np.nan
        return crowns

    print(f"\n  {'═'*60}", flush=True)
    print(f"  ║  YEAR {label}  ({entry['file']})", flush=True)
    print(f"  {'═'*60}", flush=True)
    year_t0 = time.time()
    mem(f"{label} start")

    # ── PHASE 1: stage imagery ────────────────────────────────
    print(f"\n  [PHASE 1/5] Stage imagery to local SSD", flush=True)
    if local_img is None:
        local_img = _stage_imagery_local(imagery_path)
    else:
        size_gb = local_img.stat().st_size / 1e9
        print(f"  [STAGE] using prefetched: {local_img.name}  "
              f"({size_gb:.1f} GB) — saved sync wait!", flush=True)

    # ── PHASE 2: tile-sort ────────────────────────────────────
    print(f"\n  [PHASE 2/5] Tile-sort crowns for cache locality", flush=True)
    tick(f"{label}: tile-sort crowns")
    sorted_idx = _sort_crowns_by_tile(crowns, local_img)
    tock(f"{label}: tile-sort crowns")

    # Diagnostic: how clustered are the crowns? show the tile-bucket
    # distribution so we know whether sorting is even doing much.
    with rasterio.open(local_img) as _src:
        _t = _src.transform
    cx = crowns.geometry.centroid.x.to_numpy()
    cy = crowns.geometry.centroid.y.to_numpy()
    _inv = ~_t
    _rows = (_inv.d * cx + _inv.e * cy + _inv.f).astype(np.int64)
    _cols_px = (_inv.a * cx + _inv.b * cy + _inv.c).astype(np.int64)
    tile_ids = (_rows // SPECTRAL_TILE_PX) * 100000 + (_cols_px // SPECTRAL_TILE_PX)
    n_unique_tiles = len(np.unique(tile_ids))
    print(f"  [TILES] {len(crowns):,} crowns span "
          f"{n_unique_tiles:,} unique {SPECTRAL_TILE_PX}px tiles  "
          f"(avg {len(crowns)/max(1,n_unique_tiles):.1f} crowns/tile)",
          flush=True)

    # ── PHASE 3: build task list ──────────────────────────────
    print(f"\n  [PHASE 3/5] Serialise crown geometries for workers",
          flush=True)
    tick(f"{label}: build task list (WKT serialise)")
    tasks = [
        (crowns.at[i, "crown_id"], crowns.at[i, "geometry"].wkt,
         year_key, season_alpha)
        for i in sorted_idx
    ]
    tock(f"{label}: build task list (WKT serialise)")
    # Rough memory footprint: WKT strings can be hefty
    sample_wkt_bytes = sum(len(t[1]) for t in tasks[:100]) / 100
    est_total_mb = sample_wkt_bytes * len(tasks) / 1e6
    print(f"  [TASKS] {len(tasks):,} tasks  "
          f"~{sample_wkt_bytes:.0f} bytes/WKT  "
          f"~{est_total_mb:.0f} MB total task payload", flush=True)
    mem(f"{label} after task build")

    # ── PHASE 4: parallel sampling ────────────────────────────
    print(f"\n  [PHASE 4/5] Parallel sampling "
          f"({N_WORKERS} workers, chunksize=200)", flush=True)
    print(f"  [WORKERS] starting pool...", flush=True)

    results = []
    tick(f"{label}: parallel sampling")
    sample_t0 = time.time()
    last_log = sample_t0
    last_n = 0

    with mp.Pool(processes=N_WORKERS,
                 initializer=_init_spectral_worker,
                 initargs=(str(local_img),)) as pool:

        result_iter = pool.imap_unordered(
            _crown_spectral_worker, tasks, chunksize=200)

        last_pct_logged = -1

        for res in result_iter:
            results.append(res)
            now  = time.time()
            done = len(results)
            pct  = 100 * done / len(tasks)

            # Log at every 10% milestone (0%, 10%, 20%, ... 100%)
            pct_bucket = int(pct // PROGRESS_INTERVAL_PCT)
            if pct_bucket > last_pct_logged:
                last_pct_logged = pct_bucket
                interval_s = now - last_log
                window_n   = done - last_n
                inst_rate  = window_n / interval_s if interval_s > 0 else 0
                avg_rate   = done / (now - sample_t0)
                remaining  = len(tasks) - done
                eta_s      = remaining / inst_rate if inst_rate > 0 else 0
                vm         = psutil.virtual_memory()
                print(f"  [MAIN] {done:>7,}/{len(tasks):,} "
                      f"({pct:5.1f}%)  "
                      f"inst={inst_rate:5.0f}/s  "
                      f"avg={avg_rate:5.0f}/s  "
                      f"ETA={eta_s/60:5.1f}min  "
                      f"RAM={vm.used/1e9:.1f}/{vm.total/1e9:.1f}GB "
                      f"({vm.percent:.0f}%)", flush=True)
                last_log = now
                last_n   = done

    sample_elapsed = time.time() - sample_t0
    final_rate = len(tasks) / sample_elapsed if sample_elapsed > 0 else 0
    print(f"  [WORKERS] pool closed  "
          f"final_rate={final_rate:.0f}/s  "
          f"elapsed={sample_elapsed/60:.1f}min", flush=True)
    tock(f"{label}: parallel sampling")
    mem(f"{label} after sampling")

    # ── PHASE 5: merge + checkpoint ───────────────────────────
    print(f"\n  [PHASE 5/5] Merge results & checkpoint", flush=True)

    tick(f"{label}: build results DataFrame")
    df = pd.DataFrame(results).set_index("crown_id")
    tock(f"{label}: build results DataFrame")
    print(f"  [MERGE] results DataFrame: "
          f"{len(df):,} rows × {len(df.columns)} cols", flush=True)
    mem(f"{label} after results DataFrame")

    tick(f"{label}: merge columns into crowns")
    crowns = crowns.set_index("crown_id")
    for c in cols:
        crowns[c] = df[c]
    crowns = crowns.reset_index()
    tock(f"{label}: merge columns into crowns")
    # Free the per-year results frame ASAP
    del df, results
    _trim()
    mem(f"{label} after merge + gc")

    # ── Summary line ──────────────────────────────────────────
    valid = crowns[_col("ndvi_proxy", year_key)].notna().sum()
    mean  = crowns[_col("ndvi_proxy", year_key)].mean()
    lum   = crowns[_col("luminance",  year_key)].mean()
    n_none = len(crowns) - valid
    print(f"  [STATS] {label}: valid={valid:,}/{len(crowns):,}  "
          f"none={n_none:,}  "
          f"ndvi_mean={mean:.3f}  "
          f"lum_mean={lum:.1f}  "
          f"α={season_alpha:.2f}", flush=True)

    if checkpoint:
        ckpt_size_before = (CROWNS_PARQUET.stat().st_size / 1e6
                            if CROWNS_PARQUET.exists() else 0)
        print(f"  [CHECKPOINT] writing Parquet  "
              f"({len(crowns):,} rows × {len(crowns.columns)} cols, "
              f"prev size={ckpt_size_before:.0f} MB)", flush=True)
        with keepalive(f"Parquet write {label}"):
            save_checkpoint(crowns, label=label)
    else:
        print(f"  [CHECKPOINT] skipped (deferred to next cadence year)",
              flush=True)

    # ── PHASE 5b: sample buildings while imagery still staged ──
    # Skipped if this year's building NDVI is already in the on-disk cache
    # (e.g. from a previous run or an earlier session). This means even
    # when Step 6 skips crown sampling for already-computed years, we can
    # still rebuild the in-memory cache by re-running with --force-spectral,
    # OR the cache sidecar already has the data from a prior full run.
    if _bldg_cache_has(year_key, bldg_ndvi_cache):
        print(f"\n  [PHASE 5b] Building NDVI already cached for "
              f"{label} — skipping", flush=True)
    else:
        print(f"\n  [PHASE 5b] Sample building NDVI "
              f"(imagery still staged)", flush=True)
        bldg_series = sample_buildings_year(
            buildings, local_img, year_key)
        bldg_ndvi_cache[year_key] = bldg_series
        save_bldg_ndvi_cache(bldg_ndvi_cache)
        print(f"  [BLDG] year {label} cached and saved to disk "
              f"({len(bldg_series):,} buildings)", flush=True)

    # Free local SSD space
    print(f"\n  [CLEANUP] unstaging {local_img.name}", flush=True)
    _unstage_imagery_local(local_img)

    year_elapsed = time.time() - year_t0
    print(f"\n  {'═'*60}", flush=True)
    print(f"  ║  YEAR {label} COMPLETE  in {year_elapsed/60:.1f} min",
          flush=True)
    print(f"  {'═'*60}\n", flush=True)
    return crowns


# ─────────────────────────────────────────────────────────────────────────────
#  Step 7 — Within-year normalisation
# ─────────────────────────────────────────────────────────────────────────────

def _building_spectral_worker(args):
    """
    Worker for building NDVI sampling — mirrors _crown_spectral_worker
    but for building footprints. Reuses the same per-worker raster handle
    opened by _init_spectral_worker.
    """
    import shapely.wkt
    building_id, geom_wkt, year_key = args
    geom = shapely.wkt.loads(geom_wkt)
    ndvi_val = np.nan
    try:
        r, g, b = sample_pixels(geom, _WORKER_SRC)
        if r is not None:
            ndvi_val = ndvi_proxy_scalar(float(r.mean()), float(g.mean()))
    except Exception:
        pass
    return {"building_id": building_id, f"ndvi_bldg_{year_key}": ndvi_val}


def sample_buildings_year(buildings:  gpd.GeoDataFrame,
                           local_img:  Path,
                           year_key) -> pd.Series:
    """
    Sample per-building NDVI while imagery is already staged on local SSD.

    Called from compute_spectral_year immediately after crown sampling
    completes and before the imagery is unstaged. Uses the same worker
    pool pattern (initializer opens raster once per worker) so there is
    no per-building open/close overhead.

    Returns a Series indexed by building_id for use in compute_normalised_year.
    """
    print(f"\n  [BLDG] Sampling {len(buildings):,} buildings from "
          f"{local_img.name}...", flush=True)
    t0 = time.time()

    tasks = [
        (row.building_id, row.geometry.wkt, year_key)
        for row in buildings.itertuples()
    ]

    results = []
    # Reuse the same initializer — workers already know how to open the raster
    with mp.Pool(processes=N_WORKERS,
                 initializer=_init_spectral_worker,
                 initargs=(str(local_img),)) as pool:
        for res in pool.imap_unordered(
                _building_spectral_worker, tasks, chunksize=50):
            results.append(res)

    col = f"ndvi_bldg_{year_key}"
    df  = pd.DataFrame(results).set_index("building_id")
    series = df[col].reindex(buildings["building_id"].values)
    series.index = buildings.index

    valid = series.notna().sum()
    elapsed = time.time() - t0
    print(f"  [BLDG] done: {valid:,}/{len(buildings):,} valid  "
          f"mean_ndvi={series.mean():.3f}  "
          f"elapsed={elapsed:.1f}s", flush=True)
    return series


def compute_normalised_year(crowns:          gpd.GeoDataFrame,
                             buildings:       gpd.GeoDataFrame,
                             entry:           dict,
                             bldg_ndvi_cache: dict,
                             force:           bool = False) -> gpd.GeoDataFrame:
    """
    Compute within-year normalised features.

    ndvi_z, ndvi_pct, lum_z — pure pandas, no I/O.
    ndvi_vs_roof             — uses bldg_ndvi_cache populated during Step 6.
                               Falls back to restaging imagery only if the
                               cache entry is missing (e.g. resume after crash).
    """
    year_key     = entry["key"]
    label        = entry["label"]
    imagery_path = UPSAMPLE_DIR / entry["file"]
    ndvi_col     = _col("ndvi_proxy", year_key)
    lum_col      = _col("luminance",  year_key)
    ncols        = norm_spectral_cols(year_key)

    if not force and all(c in crowns.columns for c in ncols):
        print(f"  {label:<10} norm already computed — skipping")
        return crowns

    if ndvi_col not in crowns.columns:
        print(f"  {label:<10} raw spectral missing — skipping")
        return crowns

    t0 = time.time()
    print(f"  {label:<10}", end="  ", flush=True)

    # ── ndvi z-score ──────────────────────────────────────────
    vals    = crowns[ndvi_col].dropna()
    mu, sd  = vals.mean(), vals.std()
    crowns[_col("ndvi_z", year_key)] = (
        (crowns[ndvi_col] - mu) / sd if sd > 1e-6 else 0.0)
    print("ndvi_z", end="  ", flush=True)

    # ── ndvi percentile rank ──────────────────────────────────
    finite = crowns[ndvi_col].notna()
    ranks  = crowns.loc[finite, ndvi_col].rank(pct=True) * 100
    crowns[_col("ndvi_pct", year_key)] = np.nan
    crowns.loc[finite, _col("ndvi_pct", year_key)] = ranks
    print("ndvi_pct", end="  ", flush=True)

    # ── luminance z-score ─────────────────────────────────────
    lvals      = crowns[lum_col].dropna()
    mu_l, sd_l = lvals.mean(), lvals.std()
    crowns[_col("lum_z", year_key)] = (
        (crowns[lum_col] - mu_l) / sd_l if sd_l > 1e-6 else 0.0)
    print("lum_z", end="  ", flush=True)

    # ── ndvi vs nearby roofs ──────────────────────────────────
    if year_key in bldg_ndvi_cache:
        # Fast path: use pre-sampled building NDVI from Step 6 cache
        bldg_ndvi = bldg_ndvi_cache[year_key]
        print(f"ndvi_vs_roof (from cache)", end="  ", flush=True)
    elif imagery_path.exists():
        # Fallback: restage imagery and sample buildings now
        # (happens on resume after crash where cache was lost)
        print(f"\n  [WARN] {label} not in bldg cache — "
              f"restaging imagery as fallback", flush=True)
        local_img = _stage_imagery_local(imagery_path)
        bldg_ndvi = sample_buildings_year(buildings, local_img, year_key)
        bldg_ndvi_cache[year_key] = bldg_ndvi
        _unstage_imagery_local(local_img)
        print(f"ndvi_vs_roof (restaged)", end="  ", flush=True)
    else:
        crowns[_col("ndvi_vs_roof", year_key)] = np.nan
        elapsed = time.time() - t0
        print(f"ndvi_vs_roof skipped (no imagery)  ({elapsed:.1f}s)",
              flush=True)
        return crowns

    buildings_y = buildings.copy()
    buildings_y["_bndvi"] = bldg_ndvi.values

    crown_buf = crowns[["crown_id"]].copy()
    crown_buf["geometry"] = crowns.geometry.centroid.buffer(50)
    crown_buf = gpd.GeoDataFrame(
        crown_buf, geometry="geometry", crs=crowns.crs)

    joined = gpd.sjoin(
        crown_buf,
        buildings_y[["building_id", "geometry", "_bndvi"]],
        how="left", predicate="intersects")

    nearby = (joined
              .groupby("crown_id")["_bndvi"]
              .mean()
              .rename("_nearby"))
    crowns = crowns.join(nearby, on="crown_id")
    crowns[_col("ndvi_vs_roof", year_key)] = (
        crowns[ndvi_col] - crowns["_nearby"])
    crowns = crowns.drop(columns=["_nearby"])

    elapsed = time.time() - t0
    print(f"OK  ({elapsed:.1f}s total)", flush=True)
    return crowns


def compute_all_normalised(crowns:          gpd.GeoDataFrame,
                            buildings:       gpd.GeoDataFrame,
                            entries:         list,
                            bldg_ndvi_cache: dict,
                            force:           bool = False) -> gpd.GeoDataFrame:
    print(f"\n── Step 7: Within-year normalisation "
          f"({len(entries)} year(s)) ──")
    print(f"  ndvi_z · ndvi_pct · lum_z · ndvi_vs_roof  "
          f"[cache has {len(bldg_ndvi_cache)} year(s)]\n")
    for entry in entries:
        crowns = compute_normalised_year(
            crowns, buildings, entry,
            bldg_ndvi_cache=bldg_ndvi_cache,
            force=force)
    return crowns


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1 multi-year preprocessing")
    parser.add_argument("--year",            type=str,            default=None)
    parser.add_argument("--skip-static",     action="store_true")
    parser.add_argument("--force-spectral",  action="store_true")
    parser.add_argument("--normalise-only",  action="store_true",
                        help="Recompute normalised cols only — skip sampling")
    parser.add_argument("--skip-upsample",   action="store_true",
                        help="Skip upsample step — assume imagery ready")
    parser.add_argument("--upsample-only",   action="store_true",
                        help="Upsample only — stop before spectral")
    parser.add_argument("--force-upsample",  action="store_true",
                        help="Force rebuild of upsampled imagery")

    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    args = parser.parse_args(filtered)

    print("=" * 60)
    print("  PHASE 1 — Multi-Year Pre-Processing")
    print("  Edmonds Temporal Pipeline")
    print("=" * 60)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Resolve year list ──────────────────────────────────────
    if args.year:
        key = args.year
        try:
            key = int(key)
        except ValueError:
            pass
        year_entries = [e for e in YEAR_CATALOG if e["key"] == key]
        if not year_entries:
            print(f"  ERROR: '{args.year}' not in catalogue")
            sys.exit(1)
        print(f"  Mode: single year — {args.year}")
    else:
        year_entries = YEAR_CATALOG
        print(f"  Mode: all {len(year_entries)} years")

    print(f"  Skip static     : {args.skip_static}")
    print(f"  Force spectral  : {args.force_spectral}")
    print(f"  Normalise only  : {args.normalise_only}")
    print(f"  Skip upsample   : {args.skip_upsample}")
    print(f"  Upsample only   : {args.upsample_only}")
    print(f"  Force upsample  : {args.force_upsample}")

    # ── Step log (whole-run) ───────────────────────────────────
    from pipeline_log import StepLogger
    LOGS_DIR = BASE / "phase4" / "logs"
    SCRIPT_NAME = "phase1_preprocess"
    logger = StepLogger(SCRIPT_NAME, "preprocess", LOGS_DIR)
    logger.start()

    # ── Step 0: Upsample ───────────────────────────────────────
    if not args.skip_upsample and not args.normalise_only:
        step_upsample(year_entries, force=args.force_upsample)

    if args.upsample_only:
        print("\n  --upsample-only specified — stopping here")
        timer_summary()
        logger.finish(mode="upsample_only", years=len(year_entries), errors=0)
        return

    # ── Load or resume ─────────────────────────────────────────
    with rasterio.open(UPSAMPLE_DIR / "2020_coe_rgb.tif") as src:
        img_crs = src.crs

    if CROWNS_PARQUET.exists() or CROWNS_OUT.exists():
        crowns = load_checkpoint()
        buildings = _load_buildings(img_crs)
        bldg_ndvi_cache = load_bldg_ndvi_cache()
        print(f"  Rows: {len(crowns):,}  Columns: {len(crowns.columns)}")

        if (not args.skip_static and not args.normalise_only
                and "bldg_dist_m" not in crowns.columns):
            print("  Static features missing — running now")
            water = gpd.read_file(WATER)
            if water.crs != img_crs:
                water = water.to_crs(img_crs)
            crowns      = compute_within_water(crowns, water)
            crowns      = compute_building_distance(crowns, buildings)
            bldg_scores = compute_roof_spectral_scores(buildings)
            bldg_scores.to_file(BLDG_OUT, driver="GPKG")
            crowns = join_roof_scores(crowns, bldg_scores)
            save_checkpoint(crowns, label="static features")

    else:
        crowns, buildings, water, img_crs = load_inputs()
        bldg_ndvi_cache = load_bldg_ndvi_cache()

        if not args.skip_static:
            crowns = compute_within_water(crowns, water)
            crowns = compute_building_distance(crowns, buildings)

            bldg_scores = compute_roof_spectral_scores(buildings)
            bldg_scores.to_file(BLDG_OUT, driver="GPKG")
            print(f"\n  ✓ {BLDG_OUT.name}")

            crowns = join_roof_scores(crowns, bldg_scores)
            save_checkpoint(crowns, label="static features")
            print(f"  Static features saved → {CROWNS_PARQUET.name}")

    # ── Raw spectral sampling ──────────────────────────────────
    if not args.normalise_only:
        print(f"\n{'━'*60}")
        print(f"  STEP 6: RAW SPECTRAL SAMPLING")
        print(f"{'━'*60}")

        # Filter to years that actually need work (so prefetch targets the
        # right "next" year and we don't waste a copy on a skip).
        def _needs_work(entry):
            if args.force_spectral:
                return (UPSAMPLE_DIR / entry["file"]).exists()
            cols = raw_spectral_cols(entry["key"])
            return not all(c in crowns.columns for c in cols)

        pending = [e for e in year_entries if _needs_work(e)]
        already_done = [e for e in year_entries if not _needs_work(e)]
        for e in already_done:
            ndvi_col = _col("ndvi_proxy", e["key"])
            if ndvi_col in crowns.columns:
                print(f"  [SKIP] {e['label']:<10} already computed "
                      f"(ndvi={crowns[ndvi_col].mean():.3f})", flush=True)

        print(f"\n  [PLAN] {len(pending)} year(s) to process: "
              f"{[e['label'] for e in pending]}", flush=True)
        if not pending:
            print(f"  [PLAN] nothing to do — all years already sampled",
                  flush=True)
        else:
            # Estimate total Drive→SSD bytes for capacity planning
            total_stage_gb = sum(
                (UPSAMPLE_DIR / e["file"]).stat().st_size / 1e9
                for e in pending if (UPSAMPLE_DIR / e["file"]).exists())
            print(f"  [PLAN] total imagery to stage: "
                  f"~{total_stage_gb:.0f} GB across {len(pending)} years",
                  flush=True)

        # Checkpoint cadence: write GPKG every N years rather than every
        # single year. The GPKG write for 222k rows × growing column count
        # is non-trivial and we don't need it 18 times in a row.
        CHECKPOINT_EVERY = 3
        print(f"  [PLAN] GPKG checkpoint cadence: every "
              f"{CHECKPOINT_EVERY} years (+ final)", flush=True)

        spectral_start = time.time()
        prefetch_hits = 0
        prefetch_misses = 0
        bldg_ndvi_cache = {}   # populated during sampling, consumed by Step 7

        # Background prefetcher: while year N samples, copy year N+1 from
        # Drive to local SSD if we have headroom.
        with ThreadPoolExecutor(max_workers=1,
                                thread_name_prefix="prefetch") as prefetcher:
            next_future     = None
            next_local_path = None

            for i, entry in enumerate(pending):
                year_label = entry["label"]
                overall_pct = 100 * i / len(pending)
                elapsed_min = (time.time() - spectral_start) / 60
                print(f"\n{'▼'*60}")
                print(f"  OVERALL: year {i+1}/{len(pending)} "
                      f"({overall_pct:.0f}%)  "
                      f"elapsed={elapsed_min:.1f}min  "
                      f"prefetch_hits={prefetch_hits}  "
                      f"misses={prefetch_misses}")
                print(f"{'▼'*60}", flush=True)

                # Resolve current year's local image: either prefetched or
                # staged synchronously now.
                if next_future is not None:
                    if next_future.done():
                        print(f"  [PREFETCH] {year_label} already on SSD "
                              f"(hit) — zero wait", flush=True)
                        prefetch_hits += 1
                    else:
                        print(f"  [PREFETCH] {year_label} prefetch still "
                              f"in-flight — waiting...", flush=True)
                    tick(f"{year_label}: prefetch join")
                    local_img = next_future.result()
                    join_s = tock(f"{year_label}: prefetch join")
                    if join_s > 5.0:
                        # We actually had to wait — the prefetch didn't
                        # fully overlap. Note it.
                        print(f"  [PREFETCH] waited {join_s:.1f}s for "
                              f"{year_label} — sampling was faster than "
                              f"Drive copy", flush=True)
                    next_future     = None
                    next_local_path = None
                else:
                    print(f"  [PREFETCH] no prefetch available for "
                          f"{year_label} — staging synchronously",
                          flush=True)
                    prefetch_misses += 1
                    local_img = _stage_imagery_local(
                        UPSAMPLE_DIR / entry["file"])

                # Kick off prefetch of next year IF we have disk headroom.
                if i + 1 < len(pending):
                    next_entry = pending[i + 1]
                    ok, reason = _can_prefetch(next_entry,
                                               current_staged_path=local_img)
                    if ok:
                        print(f"  [PREFETCH] starting bg copy of "
                              f"{next_entry['label']}  ({reason})",
                              flush=True)
                        next_local_path = (
                            LOCAL_SPECTRAL_DIR / next_entry["file"])
                        next_future = prefetcher.submit(
                            _stage_imagery_local,
                            UPSAMPLE_DIR / next_entry["file"])
                    else:
                        print(f"  [PREFETCH] skipped for "
                              f"{next_entry['label']} — {reason}",
                              flush=True)
                else:
                    print(f"  [PREFETCH] last year — no further "
                          f"prefetch needed", flush=True)

                # Sample. Defer GPKG checkpoint to every Nth year.
                do_ckpt = ((i + 1) % CHECKPOINT_EVERY == 0
                           or (i + 1) == len(pending))
                crowns = compute_spectral_year(
                    crowns, entry,
                    buildings=buildings,
                    bldg_ndvi_cache=bldg_ndvi_cache,
                    force=args.force_spectral,
                    local_img=local_img,
                    checkpoint=do_ckpt)

        spectral_total = (time.time() - spectral_start) / 60
        print(f"\n{'━'*60}")
        print(f"  STEP 6 COMPLETE: {len(pending)} years in "
              f"{spectral_total:.1f} min")
        print(f"  Prefetch: {prefetch_hits} hits, "
              f"{prefetch_misses} misses (sync stages)")
        print(f"{'━'*60}", flush=True)

    # ── Within-year normalisation ──────────────────────────────
    if 'bldg_ndvi_cache' not in dir():
        bldg_ndvi_cache = load_bldg_ndvi_cache()

    # ── Building NDVI cache backfill ───────────────────────────
    # If any years are missing from the cache (e.g. all crown years
    # were skipped so Phase 5b never fired, or this is a resume after
    # a crash), stage each missing year's imagery and sample buildings
    # now — before Step 7 runs. This is the dedicated path that makes
    # the "sample buildings if missing" check actually work even when
    # Step 6 skips everything.
    missing_bldg = [
        e for e in year_entries
        if not _bldg_cache_has(e["key"], bldg_ndvi_cache)
        and (UPSAMPLE_DIR / e["file"]).exists()
    ]
    if missing_bldg:
        print(f"\n{'━'*60}")
        print(f"  STEP 6b: BUILDING NDVI BACKFILL")
        print(f"  {len(missing_bldg)} year(s) missing from cache: "
              f"{[e['label'] for e in missing_bldg]}")
        total_gb = sum((UPSAMPLE_DIR / e["file"]).stat().st_size / 1e9
                       for e in missing_bldg)
        print(f"  Total to stage: ~{total_gb:.0f} GB")
        print(f"{'━'*60}", flush=True)

        for i, entry in enumerate(missing_bldg):
            label = entry["label"]
            print(f"\n  [BACKFILL] {label}  ({i+1}/{len(missing_bldg)})",
                  flush=True)
            local_img = _stage_imagery_local(UPSAMPLE_DIR / entry["file"])
            bldg_series = sample_buildings_year(
                buildings, local_img, entry["key"])
            bldg_ndvi_cache[entry["key"]] = bldg_series
            save_bldg_ndvi_cache(bldg_ndvi_cache)
            _unstage_imagery_local(local_img)
            print(f"  [BACKFILL] {label} done — cache now has "
                  f"{len(bldg_ndvi_cache)} year(s)", flush=True)

        print(f"\n{'━'*60}")
        print(f"  STEP 6b COMPLETE — all years cached")
        print(f"{'━'*60}", flush=True)
    else:
        print(f"\n  [BLDG CACHE] all {len(year_entries)} year(s) already "
              f"cached — Step 7 needs no imagery I/O", flush=True)
    crowns = compute_all_normalised(
        crowns, buildings, year_entries,
        bldg_ndvi_cache=bldg_ndvi_cache,
        force=args.force_spectral or args.normalise_only)

    # ── Final write ────────────────────────────────────────────
    print(f"\n── Final output ──")
    # Parquet: fast, for any downstream Python work
    save_checkpoint(crowns, label="final")
    # GPKG: the proper GIS deliverable (written once, at the very end)
    print(f"  Writing final GPKG deliverable...", flush=True)
    tick("final GPKG write")
    with keepalive("final GPKG write"):
        crowns.to_file(CROWNS_OUT, driver="GPKG")
    tock("final GPKG write")
    print(f"  ✓ {CROWNS_OUT}  "
          f"({CROWNS_OUT.stat().st_size/1e9:.2f} GB)")
    print(f"  ✓ {CROWNS_PARQUET}  "
          f"({CROWNS_PARQUET.stat().st_size/1e6:.0f} MB)")
    print(f"  Rows: {len(crowns):,}  Columns: {len(crowns.columns)}")

    # ── Summary table ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Crowns: {len(crowns):,}")
    if "within_water" in crowns.columns:
        print(f"  Within water    : {crowns['within_water'].sum():,}")
    if "bldg_dist_m" in crowns.columns:
        print(f"  bldg_dist ≤ 2 m : "
              f"{(crowns['bldg_dist_m'] <= 2).sum():,}")
    if "roof_score_nearby" in crowns.columns:
        print(f"  Near roof ≥ 0.8 : "
              f"{(crowns['roof_score_nearby'] >= 0.8).sum():,}")

    print(f"\n  {'Year':<10} {'ndvi_mean':>10} {'ndvi_z_μ':>10} "
          f"{'ndvi_pct_med':>13} {'vs_roof_med':>12} {'α':>6}")
    print(f"  {'-'*63}")
    for entry in YEAR_CATALOG:
        nc = _col("ndvi_proxy",   entry["key"])
        zc = _col("ndvi_z",       entry["key"])
        pc = _col("ndvi_pct",     entry["key"])
        vc = _col("ndvi_vs_roof", entry["key"])
        if nc not in crowns.columns:
            print(f"  {entry['label']:<10} —")
            continue
        ndvi = crowns[nc].mean()
        z    = crowns[zc].mean()   if zc in crowns.columns else float("nan")
        pct  = crowns[pc].median() if pc in crowns.columns else float("nan")
        roof = crowns[vc].median() if vc in crowns.columns else float("nan")
        print(f"  {entry['label']:<10} {ndvi:>10.3f} {z:>10.3f} "
              f"{pct:>13.1f} {roof:>12.3f} {entry['season_alpha']:>6.2f}")

    print(f"\n  Output: {OUT_DIR}")
    print("=" * 60)

    logger.finish(
        rows=len(crowns),
        cols=len(crowns.columns),
        years=len(year_entries),
        normalise_only=args.normalise_only,
        errors=0,
    )
    timer_summary()


if __name__ == "__main__":
    mp.set_start_method("fork", force=True)
    main()
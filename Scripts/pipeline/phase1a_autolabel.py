"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 1A — Auto-Labeling
  Edmonds Temporal Active Learning Pipeline

  NOTE: dtm_peak values in the crown GeoPackage are terrain elevation
  (feet ASL) from the DDT watershed computation, not canopy height
  above ground. Height guards have been removed from all rules.
  Spectral and geometric signals are used exclusively.

  AUTO-FP RULES  (crown is definitely not a tree)
  ───────────────────────────────────────────────
  FP1  within_water = True
       Crown centroid falls within a mapped water body.

  FP2  impervious_frac >= IMP_FP_THRESH
       Crown polygon is mostly impervious surface.
       Catches road markings, parking lot artifacts, bare pavement.

  FP3  roof_score_nearby >= ROOF_FP_THRESH
       AND  median ndvi_vs_roof across high-alpha years <= ROOF_NDVI_MAX
       Crown is next to a confident rooftop AND looks no greener than
       that rooftop across multiple reliable imaging years.

  FP4  area_m2 < AREA_FP_MIN
       Sub-pixel detection — too small to be a real crown.

  AUTO-TP RULES  (crown is definitely a tree)
  ───────────────────────────────────────────
  TP1  within_water = False
       AND  bldg_dist_m >= BLDG_TP_MIN
       AND  impervious_frac < IMP_TP_MAX
       AND  n_veg_years >= N_VEG_YEARS_MIN
       Crown is away from structures, on pervious ground, and shows
       consistent vegetation signal across multiple reliable years.

  OUTPUT FIELDS ADDED
  ───────────────────
  auto_label        str    'fp', 'tp', or None (needs review)
  auto_fp_rule      str    FP rule that triggered (or None)
  auto_confidence   float  confidence in auto-label [0-1]
  impervious_frac   float  fraction of crown pixels that are impervious
  n_high_alpha      int    years with season_alpha >= HIGH_ALPHA_MIN
  n_veg_years       int    high-alpha years where ndvi_pct > 50
  median_vs_roof    float  median ndvi_vs_roof across high-alpha years

  USAGE
  ─────
  %run phase1a_autolabel.py            # run with default thresholds
  %run phase1a_autolabel.py --dry-run  # print stats, no file writes
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import shutil
import sys
import threading
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import rasterio.transform
from rasterio.features import geometry_mask
from shapely.geometry import mapping
from tqdm import tqdm

warnings.filterwarnings("ignore")


# ── Paths ─────────────────────────────────────────────────────────────────────

BASE        = Path("/content/drive/MyDrive/treedata")
CROWNS_PATH = BASE / "phase1/edmonds_crowns_phase1.gpkg"
CROWNS_PARQUET = BASE / "phase1/edmonds_crowns_phase1.parquet"
IMP_PATH    = BASE / "impervious/impervious_edmonds.tif"
OUT_DIR     = BASE / "phase1a"
SUMMARY_OUT = OUT_DIR / "auto_label_summary.csv"
CROWNS_OUT       = OUT_DIR / "edmonds_crowns_phase1a.gpkg"
CROWNS_OUT_LOCAL = Path("/content/phase1a_crowns.gpkg")
PARQUET_OUT      = OUT_DIR / "crowns_phase1a.parquet"


# ── Timing helpers (from phase1_preprocess.py) ────────────────────────────────

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


# ── Colab keepalive (from phase1_preprocess.py) ──────────────────────────────

KEEPALIVE_INTERVAL_S = 45


class _KeepaliveThread(threading.Thread):
    def __init__(self, label: str = ""):
        super().__init__(daemon=True, name="keepalive")
        self._stop_event = threading.Event()
        self._label      = label
        self._t0         = time.time()

    def run(self):
        while not self._stop_event.wait(timeout=KEEPALIVE_INTERVAL_S):
            elapsed = (time.time() - self._t0) / 60
            print(f"  [KEEPALIVE] {self._label}  "
                  f"elapsed={elapsed:.1f}min", flush=True)

    def stop(self):
        self._stop_event.set()


class keepalive:
    """Context manager that keeps Colab alive during long blocking ops."""
    def __init__(self, label: str = ""):
        self._label = label
        self._thread = None

    def __enter__(self):
        self._thread = _KeepaliveThread(self._label)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        if self._thread:
            self._thread.stop()
            self._thread.join(timeout=2)
        return False


# ── Year catalogue ────────────────────────────────────────────────────────────

YEAR_CATALOG = [
    {"key": 2013,    "season_alpha": 0.50},
    {"key": 2015,    "season_alpha": 0.45},
    {"key": 2016,    "season_alpha": 0.65},
    {"key": 2017,    "season_alpha": 0.65},
    {"key": 2019,    "season_alpha": 0.80},
    {"key": "2019n", "season_alpha": 0.85},
    {"key": 2020,    "season_alpha": 1.00},
    {"key": 2021,    "season_alpha": 0.70},
    {"key": "2021s", "season_alpha": 0.65},
    {"key": 2022,    "season_alpha": 0.90},
    {"key": "2023n", "season_alpha": 0.85},
    {"key": 2023,    "season_alpha": 0.70},
    {"key": 2024,    "season_alpha": 0.90},
]

HIGH_ALPHA_MIN   = 0.65
HIGH_ALPHA_YEARS = [e["key"] for e in YEAR_CATALOG
                    if e["season_alpha"] >= HIGH_ALPHA_MIN]


# ── Thresholds ────────────────────────────────────────────────────────────────
# dtm_peak is NOT used — values are terrain elevation, not canopy height.

# FP thresholds
IMP_FP_THRESH  = 0.80   # crown ≥80% impervious → FP
ROOF_FP_THRESH = 0.80   # nearby roof score ≥ 0.80
ROOF_NDVI_MAX  = 0.02   # median ndvi_vs_roof ≤ 0.02 across high-alpha years
AREA_FP_MIN    = 1.5    # crown area < 1.5 m² → sub-pixel noise

# TP thresholds
BLDG_TP_MIN     = 5.0   # centroid ≥ 5m from nearest building edge
IMP_TP_MAX      = 0.20  # crown ≤ 20% impervious
N_VEG_YEARS_MIN = 3     # ndvi_pct > 50 in ≥ 3 high-alpha years

# Confidence scores per rule
CONFIDENCE = {
    "FP1": 0.99,
    "FP2": 0.90,
    "FP3": 0.85,
    "FP4": 0.95,
    "TP1": 0.85,
}


# ─────────────────────────────────────────────────────────────────────────────
#  Impervious fraction — three strategies, fastest first
#
#  1. RASTERIZE (primary) — rasterize all crown_id polygons into a label
#     array matching the impervious raster grid, then compute per-crown
#     means with numpy bincount.  ~1-2 min for 222k crowns.
#
#  2. CHUNKED ZONAL_STATS (fallback) — rasterstats in 5k-crown batches
#     with tqdm progress bar.  ~15-20 min.
#
#  3. ROW-BY-ROW (last resort) — manual chip extraction per polygon.
#     ~2-3 hours.  Only if rasterstats is unavailable.
# ─────────────────────────────────────────────────────────────────────────────

IMP_CHUNK_SIZE = 5000   # crowns per rasterstats batch (fallback path)


def compute_impervious_fraction(crowns: gpd.GeoDataFrame) -> np.ndarray:
    print(f"\n── Computing impervious fraction ──")
    tick("impervious fraction")

    # Try fast rasterize path first
    imp_frac = _compute_impervious_rasterize(crowns)

    # Fall back to chunked zonal_stats, then row-by-row
    if imp_frac is None:
        try:
            from rasterstats import zonal_stats  # noqa: F401
            imp_frac = _compute_impervious_chunked(crowns)
        except ImportError:
            print(f"  rasterstats not available — falling back to row-by-row")
            imp_frac = _compute_impervious_rowwise(crowns)

    tock("impervious fraction")
    print(f"  Mean imp frac : {imp_frac.mean():.3f}")
    print(f"  Crowns > 0.50 : {(imp_frac > 0.50).sum():,}  "
          f"({100*(imp_frac > 0.50).mean():.1f}%)")
    print(f"  Crowns > 0.80 : {(imp_frac > 0.80).sum():,}  "
          f"({100*(imp_frac > 0.80).mean():.1f}%)")
    return imp_frac


def _compute_impervious_rasterize(crowns: gpd.GeoDataFrame):
    """
    Primary path: rasterize crown polygons into a label grid aligned to
    the impervious raster, then use numpy bincount for per-crown means.
    Returns None if rasterio.features.rasterize is unavailable or fails.
    """
    try:
        from rasterio.features import rasterize
    except ImportError:
        return None

    print(f"  Strategy: rasterize + bincount (fast)")

    with rasterio.open(IMP_PATH) as src:
        imp_array     = src.read(1).astype(np.float32)
        imp_transform = src.transform
        imp_shape     = imp_array.shape
        imp_crs       = src.crs
        imp_nodata    = src.nodata

    print(f"  Raster : {imp_shape[1]}×{imp_shape[0]} px  "
          f"({imp_array.nbytes/1e6:.0f} MB)")

    # Assign sequential integer IDs (1-based) to each crown
    n = len(crowns)
    crown_ids = np.arange(1, n + 1, dtype=np.int32)

    # Build (geometry, value) pairs for rasterize
    print(f"  Rasterizing {n:,} crown polygons …")
    tick("rasterize crowns")
    shapes = list(zip(
        (mapping(g) for g in crowns.geometry),
        crown_ids
    ))

    # Rasterize — each pixel gets the crown_id it falls within (0 = no crown)
    label_grid = rasterize(
        shapes,
        out_shape=imp_shape,
        transform=imp_transform,
        fill=0,
        dtype=np.int32,
        all_touched=False,
    )
    tock("rasterize crowns")

    # Mask nodata pixels in the impervious raster
    if imp_nodata is not None:
        nodata_mask = (imp_array == imp_nodata)
        label_grid[nodata_mask] = 0

    # Compute per-crown mean impervious using bincount
    tick("bincount means")
    flat_labels = label_grid.ravel()
    flat_values = imp_array.ravel()

    # Only process pixels that belong to a crown
    mask = flat_labels > 0
    labels_m = flat_labels[mask]
    values_m = flat_values[mask]

    sums   = np.bincount(labels_m, weights=values_m, minlength=n + 1)
    counts = np.bincount(labels_m, minlength=n + 1)

    imp_frac = np.zeros(n, dtype=np.float32)
    valid = counts[1:] > 0
    imp_frac[valid] = (sums[1:][valid] / counts[1:][valid]).astype(np.float32)
    tock("bincount means")

    no_pixels = (~valid).sum()
    if no_pixels > 0:
        print(f"  Note: {no_pixels:,} crowns had 0 raster pixels "
              f"(sub-pixel or outside raster extent)")

    return imp_frac


def _compute_impervious_chunked(crowns: gpd.GeoDataFrame) -> np.ndarray:
    """
    Fallback: rasterstats.zonal_stats in chunks with tqdm progress bar.
    """
    from rasterstats import zonal_stats

    n = len(crowns)
    n_chunks = int(np.ceil(n / IMP_CHUNK_SIZE))
    print(f"  Strategy: chunked zonal_stats "
          f"({IMP_CHUNK_SIZE}/batch, {n_chunks} batches)")

    imp_frac = np.zeros(n, dtype=np.float32)

    for i in tqdm(range(n_chunks),
                  desc="  Impervious sampling",
                  unit="chunk",
                  mininterval=2):
        start = i * IMP_CHUNK_SIZE
        end   = min(start + IMP_CHUNK_SIZE, n)
        stats = zonal_stats(
            crowns.geometry.iloc[start:end],
            str(IMP_PATH),
            stats=["mean"],
            all_touched=False,
            nodata=np.nan,
        )
        for j, s in enumerate(stats):
            imp_frac[start + j] = (s["mean"]
                                   if s["mean"] is not None
                                   else 0.0)

    return imp_frac


def _compute_impervious_rowwise(crowns: gpd.GeoDataFrame) -> np.ndarray:
    """Last resort: row-by-row raster chip extraction (slow)."""

    with rasterio.open(IMP_PATH) as src:
        imp_array     = src.read(1)
        imp_transform = src.transform
        imp_h, imp_w  = imp_array.shape
        imp_bounds    = src.bounds

    res = abs(imp_transform.a)
    print(f"  Strategy: row-by-row chip extraction (slow)")
    print(f"  Raster: {imp_w}×{imp_h} px  "
          f"res={res:.1f}m  ({imp_array.nbytes/1e6:.0f} MB)")

    imp_frac = np.zeros(len(crowns), dtype=np.float32)

    for i, row in tqdm(enumerate(crowns.itertuples()),
                       total=len(crowns),
                       desc="  Sampling impervious",
                       mininterval=5):
        geom = row.geometry
        minx, miny, maxx, maxy = geom.bounds

        col0 = max(0, int((minx - imp_bounds.left) / res) - 1)
        row0 = max(0, int((imp_bounds.top  - maxy) / res) - 1)
        col1 = min(imp_w, int((maxx - imp_bounds.left) / res) + 2)
        row1 = min(imp_h, int((imp_bounds.top - miny)  / res) + 2)

        if col1 <= col0 or row1 <= row0:
            continue

        chip = imp_array[row0:row1, col0:col1]
        if chip.size == 0:
            continue

        chip_transform = rasterio.transform.from_origin(
            imp_bounds.left + col0 * res,
            imp_bounds.top  - row0 * res,
            res, res)

        try:
            mask = geometry_mask(
                [mapping(geom)],
                out_shape=chip.shape,
                transform=chip_transform,
                invert=True,
                all_touched=False)
        except Exception:
            imp_frac[i] = float(chip.mean())
            continue

        n_crown = mask.sum()
        if n_crown > 0:
            imp_frac[i] = float(chip[mask].mean())

    return imp_frac


# ─────────────────────────────────────────────────────────────────────────────
#  Multi-year vegetation signal
# ─────────────────────────────────────────────────────────────────────────────

def compute_veg_year_counts(crowns: gpd.GeoDataFrame) -> tuple:
    print(f"\n── Computing multi-year vegetation signal ──")
    tick("veg year counts")
    print(f"  High-alpha years (α≥{HIGH_ALPHA_MIN}): "
          f"{[str(y) for y in HIGH_ALPHA_YEARS]}")

    ndvi_pct_cols = [f"ndvi_pct_{k}"     for k in HIGH_ALPHA_YEARS
                     if f"ndvi_pct_{k}"     in crowns.columns]
    vs_roof_cols  = [f"ndvi_vs_roof_{k}" for k in HIGH_ALPHA_YEARS
                     if f"ndvi_vs_roof_{k}" in crowns.columns]

    print(f"  ndvi_pct cols : {len(ndvi_pct_cols)}")
    print(f"  vs_roof cols  : {len(vs_roof_cols)}")

    ha_data      = crowns[ndvi_pct_cols]
    n_high_alpha = ha_data.notna().sum(axis=1).values.astype(np.int16)
    n_veg_years  = (ha_data > 50).sum(axis=1).values.astype(np.int16)

    median_vs_roof = (crowns[vs_roof_cols].median(axis=1).values
                      .astype(np.float32)
                      if vs_roof_cols
                      else np.zeros(len(crowns), dtype=np.float32))

    print(f"\n  n_veg_years distribution:")
    for v in sorted(set(n_veg_years)):
        n   = (n_veg_years == v).sum()
        bar = "▓" * int(30 * n / len(crowns))
        print(f"    {v:>2} yrs: {n:>7,}  ({100*n/len(crowns):5.1f}%)  {bar}")

    tock("veg year counts")
    return n_high_alpha, n_veg_years, median_vs_roof


# ─────────────────────────────────────────────────────────────────────────────
#  Load crowns — prefer Parquet for speed, fall back to GPKG
# ─────────────────────────────────────────────────────────────────────────────

def load_crowns() -> gpd.GeoDataFrame:
    """Load crowns from Parquet (fast) or GPKG (slow fallback)."""
    if CROWNS_PARQUET.exists():
        tick("load crowns (parquet)")
        crowns = gpd.read_parquet(CROWNS_PARQUET)
        tock("load crowns (parquet)")
        print(f"  Loaded from Parquet: {len(crowns):,} rows × "
              f"{len(crowns.columns)} cols")
        return crowns

    if not CROWNS_PATH.exists():
        print(f"  ERROR: {CROWNS_PATH} not found — run phase 1 first")
        sys.exit(1)
    tick("load crowns (gpkg)")
    with keepalive("GPKG load"):
        crowns = gpd.read_file(CROWNS_PATH)
    tock("load crowns (gpkg)")
    print(f"  Loaded from GPKG: {len(crowns):,} rows × "
          f"{len(crowns.columns)} cols")
    return crowns


# ─────────────────────────────────────────────────────────────────────────────
#  Apply rules
# ─────────────────────────────────────────────────────────────────────────────

def apply_rules(crowns:         gpd.GeoDataFrame,
                imp_frac:       np.ndarray,
                n_high_alpha:   np.ndarray,
                n_veg_years:    np.ndarray,
                median_vs_roof: np.ndarray) -> gpd.GeoDataFrame:
    print(f"\n── Applying auto-label rules ──")

    n = len(crowns)
    auto_label      = np.full(n, None,  dtype=object)
    auto_fp_rule    = np.full(n, None,  dtype=object)
    auto_confidence = np.zeros(n,       dtype=np.float32)

    within_water = crowns["within_water"].values.astype(bool)
    bldg_dist    = crowns["bldg_dist_m"].values.astype(float)
    roof_score   = crowns["roof_score_nearby"].values.astype(float)
    area_m2      = (crowns["area_m2"].values.astype(float)
                    if "area_m2" in crowns.columns
                    else np.full(n, 99.0))

    # ── FP1: water ────────────────────────────────────────────
    fp1 = within_water
    auto_label[fp1]      = "fp"
    auto_fp_rule[fp1]    = "FP1"
    auto_confidence[fp1] = CONFIDENCE["FP1"]
    print(f"  FP1 water              : {fp1.sum():>7,}  "
          f"(within_water=True)")

    # ── FP2: impervious ───────────────────────────────────────
    fp2 = (~fp1) & (imp_frac >= IMP_FP_THRESH)
    auto_label[fp2]      = "fp"
    auto_fp_rule[fp2]    = "FP2"
    auto_confidence[fp2] = CONFIDENCE["FP2"]
    print(f"  FP2 impervious         : {fp2.sum():>7,}  "
          f"(imp_frac≥{IMP_FP_THRESH})")

    # ── FP3: rooftop spectral match ───────────────────────────
    fp3 = (
        (~fp1) & (~fp2) &
        (roof_score     >= ROOF_FP_THRESH) &
        (median_vs_roof <= ROOF_NDVI_MAX)
    )
    auto_label[fp3]      = "fp"
    auto_fp_rule[fp3]    = "FP3"
    auto_confidence[fp3] = CONFIDENCE["FP3"]
    print(f"  FP3 rooftop spectral   : {fp3.sum():>7,}  "
          f"(roof≥{ROOF_FP_THRESH} & vs_roof≤{ROOF_NDVI_MAX})")

    # ── FP4: sub-pixel area ───────────────────────────────────
    fp4 = (~fp1) & (~fp2) & (~fp3) & (area_m2 < AREA_FP_MIN)
    auto_label[fp4]      = "fp"
    auto_fp_rule[fp4]    = "FP4"
    auto_confidence[fp4] = CONFIDENCE["FP4"]
    print(f"  FP4 sub-pixel area     : {fp4.sum():>7,}  "
          f"(area<{AREA_FP_MIN}m²)")

    any_fp = fp1 | fp2 | fp3 | fp4

    # ── TP1: confident tree ───────────────────────────────────
    tp1 = (
        (~any_fp) &
        (~within_water) &
        (bldg_dist   >= BLDG_TP_MIN) &
        (imp_frac    <  IMP_TP_MAX) &
        (n_veg_years >= N_VEG_YEARS_MIN)
    )
    auto_label[tp1]      = "tp"
    auto_confidence[tp1] = CONFIDENCE["TP1"]
    print(f"  TP1 confident tree     : {tp1.sum():>7,}  "
          f"(bldg≥{BLDG_TP_MIN}m & imp<{IMP_TP_MAX} & "
          f"veg_yrs≥{N_VEG_YEARS_MIN})")

    nr = (auto_label == None)
    print(f"\n  {'─'*40}")
    print(f"  Total FP       : {any_fp.sum():>7,}  ({100*any_fp.mean():.1f}%)")
    print(f"  Total TP       : {tp1.sum():>7,}  ({100*tp1.mean():.1f}%)")
    print(f"  Needs review   : {nr.sum():>7,}  ({100*nr.mean():.1f}%)")
    print(f"  Workload saved : {100*(1-nr.sum()/n):.1f}%")

    crowns = crowns.copy()
    crowns["auto_label"]      = auto_label
    crowns["auto_fp_rule"]    = auto_fp_rule
    crowns["auto_confidence"] = auto_confidence
    crowns["impervious_frac"] = imp_frac
    crowns["n_high_alpha"]    = n_high_alpha
    crowns["n_veg_years"]     = n_veg_years
    crowns["median_vs_roof"]  = median_vs_roof

    return crowns


# ─────────────────────────────────────────────────────────────────────────────
#  Summary CSV
# ─────────────────────────────────────────────────────────────────────────────

def write_summary(crowns: gpd.GeoDataFrame):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    for rule in ["FP1", "FP2", "FP3", "FP4"]:
        mask = crowns["auto_fp_rule"] == rule
        if mask.sum() == 0:
            continue
        sub = crowns[mask]
        rows.append({
            "label":        "fp",
            "rule":         rule,
            "count":        int(mask.sum()),
            "pct_total":    round(100 * float(mask.mean()), 2),
            "conf_mean":    round(float(sub["auto_confidence"].mean()), 3),
            "imp_frac_med": round(float(sub["impervious_frac"].median()), 3),
            "area_m2_med":  round(float(sub["area_m2"].median()), 2)
                            if "area_m2" in sub.columns else None,
            "bldg_dist_med":round(float(sub["bldg_dist_m"].median()), 1),
        })

    tp_mask = crowns["auto_label"] == "tp"
    if tp_mask.sum() > 0:
        sub = crowns[tp_mask]
        rows.append({
            "label":        "tp",
            "rule":         "TP1",
            "count":        int(tp_mask.sum()),
            "pct_total":    round(100 * float(tp_mask.mean()), 2),
            "conf_mean":    round(float(sub["auto_confidence"].mean()), 3),
            "imp_frac_med": round(float(sub["impervious_frac"].median()), 3),
            "area_m2_med":  round(float(sub["area_m2"].median()), 2)
                            if "area_m2" in sub.columns else None,
            "bldg_dist_med":round(float(sub["bldg_dist_m"].median()), 1),
        })

    nr_mask = crowns["auto_label"].isna()
    rows.append({
        "label":        "needs_review",
        "rule":         None,
        "count":        int(nr_mask.sum()),
        "pct_total":    round(100 * float(nr_mask.mean()), 2),
        "conf_mean":    None,
        "imp_frac_med": round(float(crowns.loc[nr_mask, "impervious_frac"].median()), 3),
        "area_m2_med":  round(float(crowns.loc[nr_mask, "area_m2"].median()), 2)
                        if "area_m2" in crowns.columns else None,
        "bldg_dist_med":round(float(crowns.loc[nr_mask, "bldg_dist_m"].median()), 1),
    })

    df = pd.DataFrame(rows)
    df.to_csv(SUMMARY_OUT, index=False)
    print(f"\n  ✓ Summary → {SUMMARY_OUT}")
    print(df.to_string(index=False))
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Phase 1A auto-labeling")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print stats without writing output.")
    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    args = parser.parse_args(filtered)

    print("=" * 60)
    print("  PHASE 1A — Auto-Labeling")
    print("  Edmonds Temporal Pipeline")
    print("=" * 60)
    if args.dry_run:
        print("  DRY RUN — no files will be written\n")

    print(f"\n  Thresholds:")
    print(f"    FP2: imp_frac ≥ {IMP_FP_THRESH}")
    print(f"    FP3: roof_score ≥ {ROOF_FP_THRESH}  "
          f"AND  median_vs_roof ≤ {ROOF_NDVI_MAX}")
    print(f"    FP4: area_m2 < {AREA_FP_MIN}")
    print(f"    TP1: bldg_dist ≥ {BLDG_TP_MIN}m  "
          f"AND  imp_frac < {IMP_TP_MAX}  "
          f"AND  n_veg_years ≥ {N_VEG_YEARS_MIN}")
    print(f"    Note: dtm_peak not used (terrain elevation, not canopy height)")

    from pipeline_log import StepLogger
    LOGS_DIR = BASE / "phase4" / "logs"
    SCRIPT_NAME = "phase1a_autolabel"

    # ── Load ───────────────────────────────────────────────────
    with StepLogger(SCRIPT_NAME, "load", LOGS_DIR) as log:
        print(f"\n── Loading crowns ──")
        crowns = load_crowns()

        for req in ["within_water", "bldg_dist_m", "roof_score_nearby"]:
            if req not in crowns.columns:
                print(f"  ERROR: missing column '{req}' — run phase 1 first")
                sys.exit(1)

        if not IMP_PATH.exists():
            print(f"  ERROR: impervious raster not found: {IMP_PATH}")
            sys.exit(1)
        log.finish(crowns=len(crowns), cols=len(crowns.columns), errors=0)

    # ── Compute features + apply rules ─────────────────────────
    with StepLogger(SCRIPT_NAME, "compute", LOGS_DIR) as log:
        imp_frac = compute_impervious_fraction(crowns)
        n_high_alpha, n_veg_years, median_vs_roof = compute_veg_year_counts(crowns)

        tick("apply rules")
        crowns = apply_rules(
            crowns, imp_frac, n_high_alpha, n_veg_years, median_vs_roof)
        tock("apply rules")
        log.finish(crowns=len(crowns), errors=0)

    if args.dry_run:
        print(f"\n  DRY RUN complete — no files written")
        print(f"  Re-run without --dry-run to apply and save labels")
        timer_summary()
        return

    # ── Write ──────────────────────────────────────────────────
    with StepLogger(SCRIPT_NAME, "write", LOGS_DIR) as log:
        print(f"\n── Writing output ──")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        write_summary(crowns)

        # Parquet: fast working checkpoint for downstream scripts
        tick("write parquet")
        crowns.to_parquet(PARQUET_OUT, index=False, compression="snappy")
        tock("write parquet")
        print(f"  ✓ {PARQUET_OUT.name}  "
              f"({PARQUET_OUT.stat().st_size/1e6:.0f} MB)")

        # GPKG: archival GIS deliverable — write local first, then atomic copy
        tick("write GPKG")
        with keepalive("GPKG write"):
            crowns.to_file(CROWNS_OUT_LOCAL, driver="GPKG")
        local_mb = CROWNS_OUT_LOCAL.stat().st_size / 1e6
        print(f"  ✓ Local write complete  ({local_mb:.0f} MB)")
        shutil.copy2(CROWNS_OUT_LOCAL, CROWNS_OUT)
        tock("write GPKG")
        print(f"  ✓ {CROWNS_OUT.name}  "
              f"({len(crowns):,} rows  {len(crowns.columns)} cols)")
        log.finish(rows=len(crowns), cols=len(crowns.columns),
                   parquet_mb=round(PARQUET_OUT.stat().st_size / 1e6, 1),
                   errors=0)

    print(f"\n  Output: {OUT_DIR}")
    print("=" * 60)
    timer_summary()


if __name__ == "__main__":
    main()
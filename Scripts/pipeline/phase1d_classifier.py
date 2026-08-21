"""
PHASE 1D — Correction Classifier
================================
Trains a LightGBM classifier on all labeled crowns and produces
calibrated probability scores for every crown in the dataset.

INPUTS
──────
  phase1a/edmonds_crowns_phase1a.gpkg  — 222,435 crowns with auto-labels
  phase1a/auto_label_summary.csv       — auto-label stats (optional, for logging)
  phase1c/reviews_live.csv             — human review labels from Crown Reviewer

LABEL SOURCES
─────────────
  Phase 1A auto-FP   : 16,998 crowns  → binary label 0 (not tree)
  Phase 1A auto-TP   : 144,166 crowns → binary label 1 (tree)
  Phase 1C manual    : N crowns from reviews_live.csv
    Tree       → 1
    Undersized → 1  (real tree, crown boundary issue only)
    Shrub      → 0
    FP         → 0

FEATURES
────────
  Camera-agnostic (primary):
    ndvi_vs_roof_{year}  ×13   within-year crown vs nearby roof ndvi
    ndvi_pct_{year}      ×13   within-year percentile rank [0-100]
    n_veg_years                count of high-alpha years crown is vegetated
    median_vs_roof             median ndvi_vs_roof across high-alpha years
    impervious_frac            fraction of crown pixels on impervious surface
    bldg_dist_m                distance to nearest building edge (m)
    roof_score_nearby          max roof spectral score within 5m
    area_m2                    crown area in square metres
    size_class_enc             ordinal-encoded small/medium/large

  Year-conditioned (raw but safe with year encoding):
    ndvi_proxy_{year}    ×13   raw (G-R)/(G+R) — year-controlled by model
    luminance_{year}     ×13   BT.601 luminance
    season_alpha_{year}  ×13   prior quality weight per year

  Excluded:
    rgb_mean_r/g/b       correlated with ndvi_proxy, adds nothing
    dtm_peak / dtm_mean  terrain elevation (feet ASL), not canopy height

OUTPUT
──────
  phase1d/edmonds_crowns_phase1d.gpkg
    — all 222,435 crowns with added columns:
        classifier_prob    float  calibrated P(tree) [0-1]
        classifier_label   int    1 if prob >= threshold, else 0
        label_source       str    manual / auto_spatial / classifier
        binary_label       int    ground truth used for training (where known)

  phase1d/model.pkl            — saved LightGBM + Platt scaler
  phase1d/feature_importance.csv
  phase1d/calibration_report.txt
  phase1d/phase1d_log.csv       — per-run metrics

USAGE
─────
  %run phase1d_classifier.py
  %run phase1d_classifier.py --threshold 0.75   # custom decision threshold
  %run phase1d_classifier.py --dry-run          # stats only, no model trained
"""

import argparse
import datetime
import json
import pickle
import shutil
import sys
import threading
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════
#  TIMING HELPERS (from phase1_preprocess.py)
# ══════════════════════════════════════════════════════════════

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


# ── Colab keepalive ──────────────────────────────────────────────────────────

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

# ══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════

DRIVE_BASE   = Path("/content/drive/MyDrive/treedata")
CROWNS_PATH  = DRIVE_BASE / "phase1a/edmonds_crowns_phase1a.gpkg"
CROWNS_PARQUET = DRIVE_BASE / "phase1a/crowns_phase1a.parquet"
REVIEWS_CSV  = DRIVE_BASE / "phase1c/reviews_live.csv"
OUT_DIR      = DRIVE_BASE / "phase1d"
OUT_GPKG       = OUT_DIR / "edmonds_crowns_phase1d.gpkg"
OUT_GPKG_LOCAL = Path("/content/phase1d_crowns.gpkg")   # write here first
PARQUET_OUT    = OUT_DIR / "crowns_phase1d.parquet"
MODEL_PATH   = OUT_DIR / "model.pkl"
FI_PATH      = OUT_DIR / "feature_importance.csv"
REPORT_PATH  = OUT_DIR / "calibration_report.txt"
LOG_PATH     = OUT_DIR / "phase1d_log.csv"

# Decision threshold for hard label (used in policy outputs)
DEFAULT_THRESHOLD = 0.75

# Year keys in the imagery stack
YEAR_KEYS = [
    "2013", "2015", "2016", "2017", "2019", "2019n",
    "2020", "2021", "2021s", "2022", "2022n", "2023", "2024"
]

# Label mapping from 4-class to binary
LABEL_MAP = {
    "tree":           1,
    "Tree":           1,
    "undersized":     1,   # real tree, boundary issue only
    "Undersized":     1,
    "shrub":          0,
    "Shrub":          0,
    "false_positive": 0,
    "FP":             0,
    "fp":             0,
}


# ══════════════════════════════════════════════════════════════
#  STEP 1 — INSTALL / IMPORT
# ══════════════════════════════════════════════════════════════

def ensure_deps():
    import subprocess
    pkgs = ["lightgbm", "scikit-learn"]
    for pkg in pkgs:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            print(f"  Installing {pkg}...")
            subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"],
                           capture_output=True)
    print("  ✓ Dependencies ready")


# ══════════════════════════════════════════════════════════════
#  STEP 2 — LOAD DATA
# ══════════════════════════════════════════════════════════════

def load_crowns() -> gpd.GeoDataFrame:
    print(f"\n── Loading crown data ──")

    # Prefer Parquet (10-50× faster than GPKG for 140+ cols)
    if CROWNS_PARQUET.exists():
        tick("load crowns (parquet)")
        gdf = gpd.read_parquet(CROWNS_PARQUET)
        tock("load crowns (parquet)")
        print(f"  Loaded from Parquet: {len(gdf):,} rows × "
              f"{len(gdf.columns)} cols")
        return gdf

    if not CROWNS_PATH.exists():
        print(f"  ERROR: {CROWNS_PATH} not found — run phase 1 first")
        sys.exit(1)
    tick("load crowns (gpkg)")
    with keepalive("GPKG load"):
        gdf = gpd.read_file(CROWNS_PATH)
    tock("load crowns (gpkg)")
    print(f"  Loaded from GPKG: {len(gdf):,} rows × "
          f"{len(gdf.columns)} cols")
    return gdf


def load_reviews() -> pd.DataFrame:
    """
    Load Phase 1C human reviews from reviews_live.csv.
    Handles duplicates (same crown reviewed twice):
      - Same label     → keep one row (merge)
      - Different label → mark conflict, exclude from training
    """
    print(f"\n── Loading Phase 1C reviews ──")

    if not REVIEWS_CSV.exists():
        print(f"  WARNING: {REVIEWS_CSV} not found")
        print(f"  Proceeding without manual labels "
              f"(auto-labels only)")
        return pd.DataFrame(columns=["crown_id", "label",
                                     "label_code", "conflict"])

    df = pd.read_csv(REVIEWS_CSV)
    # Drop undo rows
    df = df[df["label"] != "undo"].copy()
    print(f"  Raw rows (excl. undo): {len(df):,}")
    print(f"  Reviewers: "
          f"{df['reviewer'].nunique()}  "
          f"({', '.join(df['reviewer'].unique())})")

    # Per-crown: identify conflicts
    # Keep only the most recent non-conflict label per crown
    resolved = []
    conflicts = []
    for crown_id, group in df.groupby("crown_id"):
        group = group.sort_values("ts")
        non_conflict = group[group.get("conflict", "") != "conflict"]
        if len(non_conflict) == 0:
            conflicts.append(crown_id)
            continue
        # Use most recent label
        resolved.append(non_conflict.iloc[-1])

    reviews = pd.DataFrame(resolved)
    print(f"  Resolved labels  : {len(reviews):,}")
    print(f"  Conflict (excluded): {len(conflicts):,}")

    if len(reviews) == 0:
        return reviews

    # Label breakdown
    label_counts = reviews["label"].value_counts()
    for lbl, cnt in label_counts.items():
        binary = LABEL_MAP.get(lbl, "?")
        print(f"    {lbl:<20} {cnt:>7,}  → binary {binary}")

    return reviews[["crown_id", "label", "label_code"]].copy()


# ══════════════════════════════════════════════════════════════
#  STEP 3 — MERGE LABELS
# ══════════════════════════════════════════════════════════════

def merge_labels(gdf: gpd.GeoDataFrame,
                 reviews: pd.DataFrame) -> gpd.GeoDataFrame:
    """
    Combine auto-labels (Phase 1A) and manual labels (Phase 1C)
    into a single binary_label column.

    Priority: manual > auto_tp > auto_fp
    """
    print(f"\n── Merging labels ──")

    gdf = gdf.copy()
    gdf["binary_label"]  = np.nan
    gdf["label_source"]  = "unlabeled"
    gdf["manual_label"]  = ""

    # ── Phase 1A auto-FP ───────────────────────────────────────
    auto_fp_mask = gdf["auto_label"] == "fp"
    gdf.loc[auto_fp_mask, "binary_label"] = 0
    gdf.loc[auto_fp_mask, "label_source"] = "auto_spatial"
    print(f"  Auto-FP  : {auto_fp_mask.sum():>8,}")

    # ── Phase 1A auto-TP ───────────────────────────────────────
    auto_tp_mask = gdf["auto_label"] == "tp"
    gdf.loc[auto_tp_mask, "binary_label"] = 1
    gdf.loc[auto_tp_mask, "label_source"] = "auto_spatial"
    print(f"  Auto-TP  : {auto_tp_mask.sum():>8,}")

    # ── Phase 1C manual (override auto where present) ──────────
    if len(reviews) > 0:
        reviews["binary_label"] = reviews["label"].map(LABEL_MAP)
        # Drop rows where label not in map (shouldn't happen)
        reviews = reviews.dropna(subset=["binary_label"])
        reviews["binary_label"] = reviews["binary_label"].astype(int)

        review_map    = reviews.set_index("crown_id")["binary_label"].to_dict()
        label_map_raw = reviews.set_index("crown_id")["label"].to_dict()

        manual_ids = set(review_map.keys()) & set(gdf["crown_id"])
        idx = gdf["crown_id"].isin(manual_ids)
        gdf.loc[idx, "binary_label"] = gdf.loc[idx, "crown_id"].map(review_map)
        gdf.loc[idx, "label_source"] = "manual"
        gdf.loc[idx, "manual_label"] = gdf.loc[idx, "crown_id"].map(label_map_raw)
        print(f"  Manual   : {idx.sum():>8,}  "
              f"(overrides {(idx & (auto_fp_mask | auto_tp_mask)).sum():,} "
              f"auto-labels)")

    labeled   = gdf["binary_label"].notna()
    unlabeled = ~labeled
    print(f"  Total labeled  : {labeled.sum():>8,}  "
          f"({100*labeled.mean():.1f}%)")
    print(f"  Unlabeled      : {unlabeled.sum():>8,}  "
          f"({100*unlabeled.mean():.1f}%)")

    if labeled.sum() > 0:
        pos = (gdf.loc[labeled, "binary_label"] == 1).sum()
        neg = (gdf.loc[labeled, "binary_label"] == 0).sum()
        print(f"  Class balance  : {pos:,} tree  /  {neg:,} not-tree  "
              f"({100*pos/labeled.sum():.1f}% / "
              f"{100*neg/labeled.sum():.1f}%)")

    return gdf


# ══════════════════════════════════════════════════════════════
#  STEP 4 — BUILD FEATURE MATRIX
# ══════════════════════════════════════════════════════════════

def add_shape_and_colour_features(
        gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Compute crown shape and colour features not in the GeoPackage.

    Shape
    ─────
    circularity    4π·area / perimeter²  — 1.0 = perfect circle
                   Tree crowns ~0.5-0.9, roof artifacts ~0.2-0.5
    compact_ratio  area / convex_hull_area  — lower for jagged shapes
    perimeter_m    Crown perimeter in metres

    Colour (purple/reddish ornamental detection)
    ────────────────────────────────────────────
    rg_ratio_{yr}  rgb_mean_r / rgb_mean_g per year
                   Purple ornamentals: >1.1  Green trees: <1.0
    rg_max_summer  Max R/G across confirmed summer years
                   (2019n, 2022n, 2022, 2024)
    rg_circularity rg_max_summer × circularity  interaction term

    Background: Phase 4 found 9,442 crowns with rg_max_summer > 1.10
    that are spectrally invisible to ndvi (median ndvi_pct=2.1) but
    92.7% are geometrically tree-like. Without these features the
    classifier scores only 30.5% of them above 0.75.
    """
    gdf = gdf.copy()

    # Shape
    print(f"  Shape features...")
    gdf["perimeter_m"] = gdf.geometry.length
    gdf["circularity"] = (
        (4 * np.pi * gdf["area_m2"])
        / (gdf["perimeter_m"] ** 2 + 1e-6)
    )
    try:
        gdf["compact_ratio"] = (
            gdf["area_m2"] / (gdf.geometry.convex_hull.area + 1e-6))
    except Exception:
        gdf["compact_ratio"] = gdf["circularity"]

    # R/G ratio per year
    print(f"  Colour features...")
    summer_years = ["2019n", "2022n", "2022", "2024"]
    rg_summer    = []
    for yr in YEAR_KEYS:
        r = f"rgb_mean_r_{yr}"; g = f"rgb_mean_g_{yr}"
        if r in gdf.columns and g in gdf.columns:
            col = f"rg_ratio_{yr}"
            gdf[col] = gdf[r] / (gdf[g] + 1e-6)
            if yr in summer_years:
                rg_summer.append(col)

    gdf["rg_max_summer"] = (gdf[rg_summer].max(axis=1)
                             if rg_summer else 1.0)
    gdf["rg_circularity"] = gdf["rg_max_summer"] * gdf["circularity"]

    n_red = (gdf["rg_max_summer"] > 1.10).sum()
    print(f"  Reddish ornamentals (rg>1.10): {n_red:,}  "
          f"({100*n_red/len(gdf):.1f}%)")
    return gdf


def build_features(gdf: gpd.GeoDataFrame) -> tuple:
    """
    Returns (X, feature_names) where X is a numpy array of shape
    (n_crowns, n_features).
    """
    print(f"\n── Building feature matrix ──")

    feature_cols = []

    # ── Static geometric features ─────────────────────────────
    static = ["bldg_dist_m", "impervious_frac",
              "roof_score_nearby", "area_m2"]
    for col in static:
        if col in gdf.columns:
            feature_cols.append(col)
        else:
            print(f"  WARNING: missing column {col}")

    # within_water as binary int
    if "within_water" in gdf.columns:
        gdf["within_water_int"] = gdf["within_water"].astype(int)
        feature_cols.append("within_water_int")

    # size_class ordinal encoding
    if "size_class" in gdf.columns:
        size_map = {"small": 0, "medium": 1, "large": 2}
        gdf["size_class_enc"] = gdf["size_class"].map(size_map).fillna(1)
        feature_cols.append("size_class_enc")

    # ── Shape features ────────────────────────────────────────
    for col in ["circularity", "compact_ratio", "perimeter_m"]:
        if col in gdf.columns:
            feature_cols.append(col)

    # ── Colour features (purple ornamental detection) ──────────
    for col in ["rg_max_summer", "rg_circularity"]:
        if col in gdf.columns:
            feature_cols.append(col)
    for yr in YEAR_KEYS:
        col = f"rg_ratio_{yr}"
        if col in gdf.columns:
            feature_cols.append(col)

    # ── Aggregate temporal features ───────────────────────────
    for col in ["n_veg_years", "n_high_alpha", "median_vs_roof"]:
        if col in gdf.columns:
            feature_cols.append(col)

    # ── Per-year features ─────────────────────────────────────
    per_year_added = {"agnostic": 0, "conditioned": 0}
    for yr in YEAR_KEYS:
        # Camera-agnostic (primary)
        for prefix in ["ndvi_vs_roof_", "ndvi_pct_"]:
            col = f"{prefix}{yr}"
            if col in gdf.columns:
                feature_cols.append(col)
                per_year_added["agnostic"] += 1

        # Year-conditioned raw (safe with LightGBM tree splits)
        for prefix in ["ndvi_proxy_", "luminance_", "season_alpha_"]:
            col = f"{prefix}{yr}"
            if col in gdf.columns:
                feature_cols.append(col)
                per_year_added["conditioned"] += 1

    n_shape  = sum(1 for c in feature_cols if c in
                   ["circularity","compact_ratio","perimeter_m",
                    "rg_max_summer","rg_circularity"]
                   or c.startswith("rg_ratio_"))
    print(f"  Static geometric        : {len(static) + 3}")
    print(f"  Shape + colour          : {n_shape}")
    print(f"  Aggregate temporal      : 3")
    print(f"  Per-year camera-agnostic: {per_year_added['agnostic']}")
    print(f"  Per-year year-conditioned: {per_year_added['conditioned']}")
    print(f"  Total features          : {len(feature_cols)}")

    X = gdf[feature_cols].values.astype(np.float32)
    return X, feature_cols


# ══════════════════════════════════════════════════════════════
#  STEP 5 — TRAIN + CALIBRATE
# ══════════════════════════════════════════════════════════════

def train_classifier(gdf: gpd.GeoDataFrame,
                     X: np.ndarray,
                     feature_names: list,
                     threshold: float = DEFAULT_THRESHOLD):
    """
    Train LightGBM on labeled crowns, calibrate with Platt scaling,
    apply to all 222,435 crowns.
    Returns gdf with classifier_prob and classifier_label columns.
    """
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import (
        f1_score, precision_score, recall_score,
        roc_auc_score, brier_score_loss, classification_report
    )
    from sklearn.calibration import calibration_curve

    print(f"\n── Training classifier ──")

    # Labeled rows only
    labeled_mask = gdf["binary_label"].notna()
    X_lab  = X[labeled_mask]
    y_lab  = gdf.loc[labeled_mask, "binary_label"].values.astype(int)
    ids_lab = gdf.loc[labeled_mask, "crown_id"].values

    n_labeled = len(y_lab)
    n_pos     = y_lab.sum()
    n_neg     = n_labeled - n_pos
    print(f"  Labeled crowns : {n_labeled:,}  "
          f"({n_pos:,} tree / {n_neg:,} not-tree)")

    if n_labeled < 200:
        print(f"  WARNING: only {n_labeled} labeled crowns — "
              f"classifier may be unreliable. Continue anyway.")

    # ── Stratified train/val split (80/20) — single split with
    #    index tracking for sample weights ─────────────────────
    from sklearn.model_selection import train_test_split
    lab_idx = np.arange(n_labeled)
    tr_i, val_i = train_test_split(
        lab_idx, test_size=0.20,
        stratify=y_lab, random_state=42)

    X_tr  = X_lab[tr_i];  y_tr  = y_lab[tr_i]
    X_val = X_lab[val_i]; y_val = y_lab[val_i]

    # Sample weights: manual labels get 2× weight
    src_arr    = gdf["label_source"].values[labeled_mask]
    src_tr     = src_arr[tr_i]
    w_tr       = np.where(src_tr == "manual", 2.0, 1.0)

    print(f"  Train : {len(y_tr):,}  "
          f"(manual×2 weight: {(src_tr=='manual').sum():,})")
    print(f"  Val   : {len(y_val):,}")

    # ── Class imbalance ───────────────────────────────────────
    scale_pos = n_neg / max(n_pos, 1)
    print(f"  Scale pos weight: {scale_pos:.2f}")

    # ── LightGBM ──────────────────────────────────────────────
    params = {
        "objective":        "binary",
        "metric":           ["binary_logloss", "auc"],
        "n_estimators":     500,
        "learning_rate":    0.05,
        "num_leaves":       63,
        "max_depth":        -1,
        "min_child_samples":20,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq":     5,
        "scale_pos_weight": scale_pos,
        "n_jobs":           -1,
        "random_state":     42,
        "verbose":          -1,
    }

    model = lgb.LGBMClassifier(**params)
    model.fit(
        X_tr, y_tr,
        sample_weight=w_tr,
        eval_set=[(X_val, y_val)],
        callbacks=[
            lgb.early_stopping(50, verbose=False),
            lgb.log_evaluation(period=100)
        ]
    )
    print(f"  Best iteration : {model.best_iteration_}")

    # ── Raw val predictions ───────────────────────────────────
    raw_probs_val = model.predict_proba(X_val)[:, 1]
    raw_preds_val = (raw_probs_val >= threshold).astype(int)

    print(f"\n  Val metrics (raw, threshold={threshold}):")
    print(f"    AUC       : "
          f"{roc_auc_score(y_val, raw_probs_val):.4f}")
    print(f"    F1        : "
          f"{f1_score(y_val, raw_preds_val):.4f}")
    print(f"    Precision : "
          f"{precision_score(y_val, raw_preds_val):.4f}")
    print(f"    Recall    : "
          f"{recall_score(y_val, raw_preds_val):.4f}")
    print(f"    Brier     : "
          f"{brier_score_loss(y_val, raw_probs_val):.4f}")

    # ── Platt scaling calibration ─────────────────────────────
    print(f"\n── Calibrating with Platt scaling ──")
    platt = LogisticRegression(C=1.0, random_state=42)
    platt.fit(raw_probs_val.reshape(-1, 1), y_val)
    cal_probs_val = platt.predict_proba(
        raw_probs_val.reshape(-1, 1))[:, 1]

    print(f"  Brier after calibration : "
          f"{brier_score_loss(y_val, cal_probs_val):.4f}")

    # ── Apply to all 222,435 crowns ───────────────────────────
    print(f"\n── Scoring all {len(gdf):,} crowns ──")
    raw_all = model.predict_proba(X)[:, 1]
    cal_all = platt.predict_proba(
        raw_all.reshape(-1, 1))[:, 1]

    gdf["classifier_prob"]  = np.round(cal_all, 4)
    gdf["classifier_label"] = (cal_all >= threshold).astype(int)

    # For crowns with no label yet, set label_source = classifier
    no_label = gdf["label_source"] == "unlabeled"
    gdf.loc[no_label, "label_source"] = "classifier"

    # ── Feature importance ────────────────────────────────────
    fi = pd.DataFrame({
        "feature":    feature_names,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)

    print(f"\n  Top 20 features:")
    for _, row in fi.head(20).iterrows():
        print(f"    {row['feature']:<35} {row['importance']:>6.0f}")

    # ── Calibration report ────────────────────────────────────
    report_lines = [
        f"Phase 1D Correction Classifier — Calibration Report",
        f"Generated: {datetime.datetime.now().isoformat()}",
        f"",
        f"TRAINING DATA",
        f"  Labeled crowns : {n_labeled:,}",
        f"  Tree (1)       : {n_pos:,}  ({100*n_pos/n_labeled:.1f}%)",
        f"  Not-tree (0)   : {n_neg:,}  ({100*n_neg/n_labeled:.1f}%)",
        f"  Train split    : {len(y_tr):,}",
        f"  Val split      : {len(y_val):,}",
        f"",
        f"VALIDATION METRICS (threshold={threshold})",
        f"  AUC        : {roc_auc_score(y_val, raw_probs_val):.4f}",
        f"  F1         : {f1_score(y_val, raw_preds_val):.4f}",
        f"  Precision  : {precision_score(y_val, raw_preds_val):.4f}",
        f"  Recall     : {recall_score(y_val, raw_preds_val):.4f}",
        f"  Brier raw  : {brier_score_loss(y_val, raw_probs_val):.4f}",
        f"  Brier cal  : {brier_score_loss(y_val, cal_probs_val):.4f}",
        f"",
        f"SCORE DISTRIBUTION (all 222k crowns)",
        f"  Mean prob  : {cal_all.mean():.3f}",
        f"  Median prob: {np.median(cal_all):.3f}",
        f"  >= 0.50    : {(cal_all >= 0.50).sum():,}",
        f"  >= 0.75    : {(cal_all >= 0.75).sum():,}",
        f"  >= 0.90    : {(cal_all >= 0.90).sum():,}",
        f"",
        classification_report(y_val, raw_preds_val,
                               target_names=["not_tree", "tree"]),
    ]

    return gdf, model, platt, fi, "\n".join(report_lines)


# ══════════════════════════════════════════════════════════════
#  STEP 6 — SAVE OUTPUTS
# ══════════════════════════════════════════════════════════════

def save_outputs(gdf: gpd.GeoDataFrame,
                 model, platt,
                 fi: pd.DataFrame,
                 report: str):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n── Saving outputs ──")

    # Parquet: fast working checkpoint for downstream scripts (e.g. 1B)
    tick("write parquet")
    gdf.to_parquet(PARQUET_OUT, index=False, compression="snappy")
    tock("write parquet")
    print(f"  ✓ {PARQUET_OUT.name}  "
          f"({PARQUET_OUT.stat().st_size/1e6:.0f} MB)")

    # GeoPackage: archival GIS deliverable
    cols_to_drop = [c for c in gdf.columns
                    if c in ("within_water_int", "size_class_enc")]
    out_gdf = gdf.drop(columns=cols_to_drop, errors="ignore")
    # Write to local NVMe first to avoid Drive FUSE journal corruption
    # if the process is interrupted mid-write.
    tick("write GPKG")
    print(f"  Writing to local disk...")
    with keepalive("GPKG write"):
        out_gdf.to_file(OUT_GPKG_LOCAL, driver="GPKG")
    local_mb = OUT_GPKG_LOCAL.stat().st_size / 1e6
    print(f"  ✓ Local write complete  ({local_mb:.0f} MB)")

    # Atomic copy to Drive — interrupted copy leaves old file intact
    print(f"  Syncing to Drive...")
    shutil.copy2(OUT_GPKG_LOCAL, OUT_GPKG)
    tock("write GPKG")
    drive_mb = OUT_GPKG.stat().st_size / 1e6
    print(f"  ✓ {OUT_GPKG.name}  "
          f"({len(out_gdf):,} crowns  {len(out_gdf.columns)} cols  "
          f"{drive_mb:.0f} MB)")

    # Model bundle
    bundle = {"lgbm": model, "platt": platt}
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(bundle, f)
    print(f"  ✓ {MODEL_PATH.name}")

    # Feature importance
    fi.to_csv(FI_PATH, index=False)
    print(f"  ✓ {FI_PATH.name}")

    # Calibration report
    REPORT_PATH.write_text(report)
    print(f"  ✓ {REPORT_PATH.name}")
    print()
    print(report)

    # Run log
    log_row = {
        "ts":           datetime.datetime.now().isoformat(),
        "n_crowns":     len(gdf),
        "n_labeled":    int(gdf["binary_label"].notna().sum()),
        "n_manual":     int((gdf["label_source"] == "manual").sum()),
        "n_auto":       int((gdf["label_source"] == "auto_spatial").sum()),
        "n_classifier": int((gdf["label_source"] == "classifier").sum()),
        "prob_mean":    round(float(gdf["classifier_prob"].mean()), 4),
        "n_above_75":   int((gdf["classifier_prob"] >= 0.75).sum()),
    }
    log_df = pd.DataFrame([log_row])
    if LOG_PATH.exists():
        log_df = pd.concat([pd.read_csv(LOG_PATH), log_df], ignore_index=True)
    log_df.to_csv(LOG_PATH, index=False)
    print(f"  ✓ {LOG_PATH.name}")


# ══════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════

def print_summary(gdf: gpd.GeoDataFrame, threshold: float):
    print(f"\n{'=' * 60}")
    print(f"  PHASE 1D COMPLETE")
    print(f"{'=' * 60}")
    print(f"\n  Label sources:")
    for src, cnt in gdf["label_source"].value_counts().items():
        print(f"    {src:<20} {cnt:>8,}")

    print(f"\n  Classifier scores:")
    print(f"    Mean prob        : "
          f"{gdf['classifier_prob'].mean():.3f}")
    print(f"    >= 0.50          : "
          f"{(gdf['classifier_prob'] >= 0.50).sum():>8,}")
    print(f"    >= 0.75 (policy) : "
          f"{(gdf['classifier_prob'] >= 0.75).sum():>8,}")
    print(f"    >= 0.90          : "
          f"{(gdf['classifier_prob'] >= 0.90).sum():>8,}")

    print(f"\n  Classifier label (threshold={threshold}):")
    trees    = (gdf["classifier_label"] == 1).sum()
    not_tree = (gdf["classifier_label"] == 0).sum()
    print(f"    Tree (1)    : {trees:>8,}  "
          f"({100*trees/len(gdf):.1f}%)")
    print(f"    Not-tree (0): {not_tree:>8,}  "
          f"({100*not_tree/len(gdf):.1f}%)")

    print(f"\n  Output: {OUT_GPKG}")
    print(f"  Model : {MODEL_PATH}")
    print(f"{'=' * 60}")

    print(f"""
  NEXT STEPS
  ──────────
  Phase 2: Data Preparation on all 13 years
    %run phase2_data_prep.py

  Or check classifier performance first:
    import geopandas as gpd
    gdf = gpd.read_file("{OUT_GPKG}")
    print(gdf["classifier_prob"].describe())
    print(gdf[gdf["label_source"]=="manual"]["classifier_prob"].describe())
""")


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    parser = argparse.ArgumentParser(description="Phase 1D classifier")
    parser.add_argument("--threshold", type=float,
                        default=DEFAULT_THRESHOLD,
                        help="Decision threshold (default 0.75)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print stats without training")
    args = parser.parse_args(filtered)

    from pipeline_log import StepLogger
    LOGS_DIR = DRIVE_BASE / "phase4" / "logs"
    SCRIPT_NAME = "phase1d_classifier"

    print("=" * 60)
    print("  PHASE 1D — Correction Classifier")
    print("=" * 60)

    with StepLogger(SCRIPT_NAME, "load", LOGS_DIR) as log:
        ensure_deps()

        gdf     = load_crowns()
        reviews = load_reviews()
        tick("merge labels")
        gdf     = merge_labels(gdf, reviews)
        tock("merge labels")
        log.finish(crowns=len(gdf), reviews=len(reviews), errors=0)

    if args.dry_run:
        print(f"\n  DRY RUN — no model trained")
        print(f"\n── Computing shape + colour features ──")
        gdf = add_shape_and_colour_features(gdf)
        X, feature_names = build_features(gdf)
        print(f"  Feature matrix shape: {X.shape}")
        timer_summary()
        sys.exit(0)

    with StepLogger(SCRIPT_NAME, "train", LOGS_DIR) as log:
        print(f"\n── Computing shape + colour features ──")
        tick("shape + colour features")
        gdf = add_shape_and_colour_features(gdf)
        tock("shape + colour features")

        tick("build feature matrix")
        X, feature_names = build_features(gdf)
        tock("build feature matrix")

        tick("train classifier")
        gdf, model, platt, fi, report = train_classifier(
            gdf, X, feature_names, threshold=args.threshold)
        tock("train classifier")
        log.finish(crowns=len(gdf), n_features=len(feature_names),
                   threshold=args.threshold, errors=0)

    with StepLogger(SCRIPT_NAME, "write", LOGS_DIR) as log:
        save_outputs(gdf, model, platt, fi, report)
        print_summary(gdf, args.threshold)
        log.finish(crowns=len(gdf), errors=0)
    timer_summary()
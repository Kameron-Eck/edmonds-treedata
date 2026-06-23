"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — Per-Year Semantic Segmentation Fine-Tuning (17 years)
  Edmonds Temporal Active Learning Pipeline

  Takes the Phase 3 2020 semantic model (sem_best_2020.pt) and
  fine-tunes it INDEPENDENTLY onto each of the 17 remaining imagery
  acquisitions, at each year's NATIVE resolution (no upscaling), then
  runs full-city inference → binary canopy mask and per-year pixel
  validation (IoU / Dice) against the projected 2020 labels.

  This is the semantic counterpart to Phase 5 (instance fine-tuning) and
  is run for ALL coarser years as well, since semantic seg is the only
  segmentation produced below 14.9 cm (Method Pipeline v5.0).

  WHAT'S NEW vs PHASE 3
  ─────────────────────
  Phase 3 read pre-cropped 7.5 cm 2020 training-site photos. Phase 4
  must build year-specific labels: for each training site it crops that
  site's footprint out of the year's FULL-CITY native ortho, reprojects
  the 3,000 hand-traced crowns into the year's CRS, and rasterises the
  binary canopy mask on the native pixel grid. The model factory, the
  two-phase fine-tune, the evaluation metrics and the streaming
  inference are ported from Phase 3 and made year-/tier-parametric.

  RESOLUTION TIERS (drive tiling density — Method Pipeline Step 2)
  ────────────────────────────────────────────────────────────────
    fine    ≤ 15 cm   (7.5, 14.9)   stride 512   held-out test 0.20
    medium  29.9 cm                 stride 256   held-out test 0.20
    coarse  50–60 cm                stride 128   NO held-out test
                                                 → in-sample IoU (DG4)
  At coarse GSD a 512px tile covers ~307 m, so a training site yields
  only a handful of non-overlapping tiles; the stride reduction keeps
  enough tiles to fine-tune. Coarse-year IoU is reported in-sample and
  feeds Decision Gate 4 (include / exclude / flag low-confidence).

  PER-YEAR PIPELINE STEPS  (run end-to-end, one year at a time)
  ─────────────────────────────────────────────────────────────
  Step 1  labels      Crop site footprint from native ortho + reproject
                      crowns + rasterise binary mask at native GSD
  Step 2  tile        Tile RGB + mask → 512×512 patches (per-tier stride)
  Step 3  train       Fine-tune from Phase 3 ckpt: Phase A (frozen
                      encoder) + Phase B (full model)
  Step 4  evaluate    Pixel accuracy, IoU, Dice vs projected labels
  Step 5  inference   Streaming full-city native inference → prob raster
  Step 6  postproc    Threshold → morphology → polygonize → canopy mask
  CROSS   consistency (once, after all years) canopy-area trend + flags

  INPUTS
  ──────
  photos/     *_rgb.tif   Training-site footprints (bounds only; 2020 7.5cm)
  polygons/   *.shp       Matched crown polygons (EPSG:3857)
  phase3/sem_best_2020.pt Phase 3 semantic checkpoint (fine-tune start)
  Full_Image/Pipeline Imagery/native/{year}_*.tif  Per-year native orthos

  OUTPUTS
  ───────
  phase4/sites/{year}/{site}_{img,mask}.tif   Native-GSD site crops + labels
  phase4/tiles/{year}/...                      512×512 paired tiles + index
  phase4/models/sem_best_{year}.pt             Per-year fine-tuned model (×17)
  phase4/masks/edmonds_canopy_prob_{year}.tif  Full-city probability raster
  phase4/masks/edmonds_canopy_mask_{year}.tif  Binary canopy mask
  phase4/masks/edmonds_canopy_mask_{year}.gpkg Canopy polygons
  phase4/eval/semantic_eval_report.csv         Per-year IoU / Dice / etc.
  phase4/eval/cross_year_consistency.csv       Area trend + anomaly flags

  USAGE
  ─────
  %run phase4_semantic_finetune.py                      # all 17 years, full pipeline
  %run phase4_semantic_finetune.py --year 2017          # one year
  %run phase4_semantic_finetune.py --year 2005,2007,2009
  %run phase4_semantic_finetune.py --tier coarse        # one resolution tier
  %run phase4_semantic_finetune.py --step labels        # one step, all years
  %run phase4_semantic_finetune.py --year 2016 --step inference
  %run phase4_semantic_finetune.py --skip-training      # use existing per-year ckpts
  %run phase4_semantic_finetune.py --skip-inference     # stop after evaluate
  %run phase4_semantic_finetune.py --step consistency   # cross-year check only
  %run phase4_semantic_finetune.py --dry-run            # plan only, no writes
  %run phase4_semantic_finetune.py --ckpt <p3.pt>       # override fine-tune start
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import gc
import importlib
import multiprocessing
import os
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path


# ── Dependency bootstrap (Colab) ──────────────────────────────────────────────
# Same pattern as phase1/phase3: ensure non-stdlib CPU/geo deps are present so the
# script runs end-to-end via %run on a fresh runtime. torch is NOT auto-installed
# (Colab GPU runtimes ship a CUDA-matched build).

def _pip_install(spec):
    print(f"  • installing {spec} …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=True)


def _ensure_deps(deps):
    for import_name, pip_spec in deps:
        try:
            importlib.import_module(import_name)
        except ImportError:
            _pip_install(pip_spec)
            importlib.invalidate_caches()


_ensure_deps([
    ("geopandas", "geopandas"),
    ("rasterio",  "rasterio"),
    ("shapely",   "shapely"),
    ("fiona",     "fiona"),
    ("sklearn",   "scikit-learn"),
    ("scipy",     "scipy"),
    ("tqdm",      "tqdm"),
])

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import rasterio.transform
import rasterio.warp
import rasterio.windows
from rasterio.coords import BoundingBox
from rasterio.enums import Resampling
from shapely.geometry import box, mapping, shape
from sklearn.model_selection import train_test_split
from tqdm import tqdm

warnings.filterwarnings("ignore")


# ── Lazy torch imports (same as phase3) ───────────────────────────────────────

_torch_loaded = False


def _ensure_torch():
    global _torch_loaded
    if _torch_loaded:
        return
    _ensure_deps([
        ("segmentation_models_pytorch", "segmentation-models-pytorch"),
        ("albumentations",              "albumentations>=2.0,<3"),
    ])
    global torch, nn, Dataset, DataLoader, WeightedRandomSampler
    global smp, A, ToTensorV2
    import torch as _torch
    import torch.nn as _nn
    from torch.utils.data import (
        Dataset as _Dataset,
        DataLoader as _DataLoader,
        WeightedRandomSampler as _WeightedRandomSampler,
    )
    import segmentation_models_pytorch as _smp
    import albumentations as _A
    from albumentations.pytorch import ToTensorV2 as _ToTensorV2

    torch = _torch
    nn = _nn
    Dataset = _Dataset
    DataLoader = _DataLoader
    WeightedRandomSampler = _WeightedRandomSampler
    smp = _smp
    A = _A
    ToTensorV2 = _ToTensorV2
    _torch_loaded = True


# ── Timing helpers (same as phase1/phase3) ────────────────────────────────────

_timers = {}


def tick(label):
    _timers[label] = time.time()


def tock(label):
    if label in _timers:
        elapsed = time.time() - _timers.pop(label)
        print(f"  ⏱ {label}: {elapsed:.1f}s")
        return elapsed
    return 0.0


def timer_summary():
    if _timers:
        print(f"\n  Unclosed timers: {list(_timers.keys())}")


# ── Paths ─────────────────────────────────────────────────────────────────────

BASE          = Path("/content/drive/MyDrive/treedata")
PHOTOS_DIR    = BASE / "photos"                       # training-site footprints
POLYGONS_DIR  = BASE / "polygons"                     # training-site crown polygons

# Per-year native orthos. phase2 catalogues them under .../native/; older phase1
# code kept some at the "Pipeline Imagery" root. We resolve both.
IMAGERY_DIR   = BASE / "Full_Image/Pipeline Imagery"
NATIVE_DIR    = IMAGERY_DIR / "native"

# Phase 3 semantic checkpoint — the fine-tune starting point for every year.
P3_DIR        = BASE / "phase3"
PROB_2020     = P3_DIR / "edmonds_canopy_prob_2020.tif"  # full-city 2020 canopy prob
MASK_2020     = P3_DIR / "edmonds_canopy_mask_2020.tif"  # full-city 2020 BINARY canopy
                                                         # mask — coarse city-wide
                                                         # label source (Fix 3)
P3_CKPT_CANDIDATES = [
    P3_DIR / "sem_best_2020.pt",
    P3_DIR / "checkpoints" / "sem_best_2020.pt",
]

# phase2 coverage matrix (optional; consulted if present for partial-coverage years).
COVERAGE_CSV  = BASE / "phase2" / "training_site_coverage.csv"

# Phase 4 outputs
OUT_DIR       = BASE / "phase4"
SITE_DIR      = OUT_DIR / "sites"      # /{year}/{site}_img.tif, {site}_mask.tif
TILE_DIR      = OUT_DIR / "tiles"      # /{year}/{train,test}/{images,masks}/...
MODELS_DIR    = OUT_DIR / "models"     # sem_best_{year}.pt
MASKS_DIR     = OUT_DIR / "masks"      # prob/mask rasters + canopy gpkg
EVAL_DIR      = OUT_DIR / "eval"       # semantic_eval_report.csv + consistency
EVAL_CSV      = EVAL_DIR / "semantic_eval_report.csv"
CONSISTENCY_CSV = EVAL_DIR / "cross_year_consistency.csv"

# Local SSD scratch for staging large orthos (avoid Drive FUSE stalls).
LOCAL_SCRATCH = Path("/content/phase4_scratch")

CROWN_CRS     = "EPSG:3857"   # the hand-traced crowns / training photos live here


# ── Hyperparameters (Method Pipeline v5.0 "Fine-Tuning" block) ────────────────

ENCODER          = "resnet101"
DECODER_CHANNELS = (1024, 512, 256, 128, 64)
DECODER_DROPOUT  = 0.3

TILE_SIZE        = 512
NEGATIVE_SAMPLE_RATE = 0.15      # fine/medium; coarse overridden below
RANDOM_SEED      = 42

# Coarse-tier city-wide stratified tiling (Fix 3). For coarse years the default
# tiling path samples tiles across the whole city ortho (not just the 6 site
# footprints), labelled from the 2020 binary canopy mask, balanced across
# canopy-fraction bins so the set isn't all-forest or all-background.
COARSE_CITYWIDE_TILES     = 800  # total tile budget across canopy-fraction bins
CITYWIDE_CANDIDATE_STRIDE = 256  # candidate origin stride before stratification

# Green hard-negative mining (Fix B). Background (canopy_frac==0) tiles whose
# mean GRVI = (G-R)/(G+R) exceeds GREEN_GRVI_THRESHOLD are vegetated-but-non-
# canopy (grass, lawn, field) — the exact confusers driving false canopy. We
# reserve HARD_NEG_FRACTION of the background tile budget for them so the model
# sees the grass/canopy boundary.
GREEN_GRVI_THRESHOLD = 0.05
HARD_NEG_FRACTION    = 0.25

# Background share of the coarse city-wide tile budget (Fix C). Raised so
# negatives are well represented (equal 5-bin balancing gave background only
# ~1/5 ≈ 20%). The remaining budget is split among the canopy bins (1..4),
# balanced among themselves. Curated negative-site tiles are added on top and
# don't count against this fraction.
BACKGROUND_BUDGET_FRACTION = 0.35

# Spatially-blocked train/val/test split for coarse city-wide tiles (Fix 4).
# Whole geographic blocks are assigned to each split, then train tiles within
# CANOPY_AUTOCORR_M of any held-out tile are dropped so val/test are honestly
# separated. 520 m is the upper bound of the canopy spatial-autocorrelation
# range (250–520 m); the block edge is several × that so blocks aren't trivially
# small.
CANOPY_AUTOCORR_M    = 520.0
SPATIAL_BLOCK_SIZE_M = 1500.0
COARSE_VAL_FRAC      = 0.20
COARSE_TEST_FRAC     = 0.20

# Fine-tune schedule — identical values to Phase 3 / Method Pipeline.
EPOCHS_PHASE_A   = 20            # decoder only, encoder frozen
LR_PHASE_A       = 5e-5
EPOCHS_PHASE_B   = 30            # full model
LR_PHASE_B       = 5e-6
EARLY_STOP_PAT   = 15
BATCH_SIZE       = 10
NUM_WORKERS      = 16
SAVE_EVERY       = 5
SPATIAL_BUFFER_PX = 512          # see phase3 note; 512 keeps all non-val train tiles
L1_LAMBDA        = 1e-6

# Segmentation loss = BCE_WEIGHT * masked_BCE + DICE_WEIGHT * masked_Dice
# (Fix 1). Both terms are IGNORE-aware (255 pixels excluded exactly like
# _masked_bce). Dice supplies a region-overlap gradient that BCE alone lacks,
# which helps the compressed-probability coarse years. Tunable.
BCE_WEIGHT       = 0.5
DICE_WEIGHT      = 0.5
DICE_SMOOTH      = 1.0           # Laplace smoothing on the soft-Dice ratio

# BCE pos_weight for class imbalance (Fix 2). Applied to coarse + medium tiers
# only (fine tier stays at 1.0 / None). Clamped to this range so a canopy-scarce
# split can't blow up the gradient.
POS_WEIGHT_MIN   = 1.0
POS_WEIGHT_MAX   = 10.0

# Inference (same center-crop streaming as Phase 0 / Phase 3)
INFER_BATCH_SIZE = 160
INFER_STRIDE     = 256
INFER_PAD        = (TILE_SIZE - INFER_STRIDE) // 2

# Post-processing (Method Pipeline "Semantic Thresholding" block)
CANOPY_PROB_THRESHOLD = 0.5
MIN_CANOPY_PATCH      = 3.0      # m²
MORPH_KERNEL_SIZE     = 3
SIMPLIFY_TOLERANCE_M  = 0.5
POLYGON_CONNECTIVITY  = 8

# A pixel is treated as "no data" (outside coverage) if all three RGB bands are
# exactly the nodata fill (or exactly 0 when nodata is undefined). Used to blank
# the un-imaged 33% of Snohomish partial-coverage years in the canopy mask, and
# to skip uncovered training sites during label generation.
COVERAGE_NODATA_MAX = 0.95       # site skipped if >95% of its window is nodata
PROB_NODATA         = 255        # reserved sentinel in the uint8 prob raster

# Three-state training mask: 0 = background (reviewed non-canopy), 1 = canopy
# (approved crown valid for this year), 255 = IGNORE (unreviewed / imagery
# nodata) — excluded from the loss and from evaluation. Legacy masks contain
# only {0,1}, so all IGNORE-aware code is a no-op for years without review data.
IGNORE_LABEL        = 255

# ImageNet normalisation
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

# Vegetation-index input channels (parity with Phase 3 --vi). Default OFF: the
# deployed Phase 3 checkpoint is the 3-channel RGB model. IN_CHANNELS must match
# the checkpoint being fine-tuned, so only enable --vi if Phase 3 trained a VI
# model and you point --ckpt at it.
USE_VI      = False
VI_NAMES    = ("GCC", "GRVI", "ExG")
VI_MEAN     = [0.33, 0.00, 0.10]
VI_STD      = [0.10, 0.30, 0.25]
IN_CHANNELS = 3


# ══════════════════════════════════════════════════════════════════════════════
#  18-ENTRY IMAGERY CATALOG  (verbatim from phase2_data_prep.py — the authority)
# ══════════════════════════════════════════════════════════════════════════════

SEG_INSTANCE_SEMANTIC = "instance+semantic"
SEG_SEMANTIC_ONLY     = "semantic_only"

YEAR_CATALOG = [
    {"key": 2000, "label": "2000", "source": "King County", "gsd_cm": 59.7,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2000_king_rgb.tif"},
    {"key": 2002, "label": "2002", "source": "King County", "gsd_cm": 59.7,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2002_king_rgb.tif"},
    {"key": 2005, "label": "2005", "source": "King County", "gsd_cm": 29.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2005_king_rgb.tif"},
    {"key": 2007, "label": "2007", "source": "King County", "gsd_cm": 29.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2007_king_rgb.tif"},
    {"key": 2009, "label": "2009", "source": "King County", "gsd_cm": 29.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2009_king_rgb.tif"},
    {"key": 2013, "label": "2013", "source": "King County", "gsd_cm": 14.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2013_king_rgb.tif"},
    {"key": 2015, "label": "2015", "source": "King County", "gsd_cm": 14.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2015_king_rgb.tif"},
    {"key": 2016, "label": "2016", "source": "Snohomish Co.", "gsd_cm": 50.0,
     "bands": 4, "crs_epsg": 2285, "coverage": "67%",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2016_snoh_rgbi.tif"},
    {"key": 2017, "label": "2017", "source": "City of Edmonds", "gsd_cm": 7.5,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2017_coe_rgb.tif"},
    {"key": 2019, "label": "2019", "source": "King County", "gsd_cm": 14.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2019_king_rgb.tif"},
    {"key": "2019n", "label": "2019n", "source": "NAIP", "gsd_cm": 60.0,
     "bands": 4, "crs_epsg": 26910, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2019_naip_rgbi.tif"},
    {"key": 2020, "label": "2020", "source": "City of Edmonds", "gsd_cm": 7.5,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2020_coe_rgb.tif"},
    {"key": 2021, "label": "2021", "source": "King County", "gsd_cm": 14.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2021_king_rgb.tif"},
    {"key": "2021s", "label": "2021s", "source": "Snohomish Co.", "gsd_cm": 50.0,
     "bands": 4, "crs_epsg": 2285, "coverage": "67%",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2021_snoh_rgbi.tif"},
    {"key": 2022, "label": "2022", "source": "City of Edmonds", "gsd_cm": 7.5,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2022_coe_rgb.tif"},
    {"key": "2022n", "label": "2022n", "source": "NAIP", "gsd_cm": 60.0,
     "bands": 4, "crs_epsg": 26910, "coverage": "full",
     "seg_tier": SEG_SEMANTIC_ONLY, "native_file": "2022_naip_rgbi.tif"},
    {"key": 2023, "label": "2023", "source": "King County", "gsd_cm": 14.9,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2023_king_rgb.tif"},
    {"key": 2024, "label": "2024", "source": "City of Edmonds", "gsd_cm": 7.5,
     "bands": 3, "crs_epsg": 3857, "coverage": "full",
     "seg_tier": SEG_INSTANCE_SEMANTIC, "native_file": "2024_coe_rgb.tif"},
]

# 2020 is the anchor (already segmented in Phase 3); Phase 4 does the other 17.
ANCHOR_LABEL = "2020"


# ── Resolution-tier logic ─────────────────────────────────────────────────────
# Drives tiling density. Coarse years get no held-out test split (too few tiles);
# their IoU is reported in-sample and feeds Decision Gate 4.

def tier_of(gsd_cm):
    if gsd_cm <= 15.0:
        return "fine"      # 7.5, 14.9
    if gsd_cm <= 35.0:
        return "medium"    # 29.9
    return "coarse"        # 50.0, 59.7, 60.0


TIER_TILE_PARAMS = {
    #          stride  neg_rate  test_frac  has_test
    "fine":   dict(stride=512, neg_rate=0.15, test_frac=0.20, has_test=True),
    "medium": dict(stride=256, neg_rate=0.15, test_frac=0.20, has_test=True),
    # neg_rate raised 0.30→0.60 (Fix 3) to lift negative representation. Used only
    # by the legacy 6-site coarse path (--coarse-site-tiling); the default coarse
    # path is now city-wide stratified tiling, which balances negatives by bin.
    "coarse": dict(stride=128, neg_rate=0.60, test_frac=0.00, has_test=False),
}


def remaining_entries():
    """The 17 acquisitions Phase 4 fine-tunes (everything except the 2020 anchor)."""
    return [e for e in YEAR_CATALOG if e["label"] != ANCHOR_LABEL]


def entry_for(label):
    for e in YEAR_CATALOG:
        if e["label"] == str(label):
            return e
    raise KeyError(f"Unknown year label: {label!r}")


def resolve_native_path(entry):
    """Locate the year's native ortho, trying the phase2 native/ dir then root."""
    for d in (NATIVE_DIR, IMAGERY_DIR):
        p = d / entry["native_file"]
        if p.exists():
            return p
    # Return the canonical (native/) path even if missing, for clear error text.
    return NATIVE_DIR / entry["native_file"]


# ── Local SSD staging (phase1 pattern) ────────────────────────────────────────

def _stage_imagery_local(src_path):
    """Copy a Drive ortho to local NVMe; return the local path (or src on failure)."""
    src_path = Path(src_path)
    if not str(src_path).startswith("/content/drive"):
        return src_path  # already local
    LOCAL_SCRATCH.mkdir(parents=True, exist_ok=True)
    dst = LOCAL_SCRATCH / src_path.name
    try:
        if dst.exists() and dst.stat().st_size == src_path.stat().st_size:
            return dst
        tick(f"stage {src_path.name}")
        shutil.copy2(src_path, dst)
        tock(f"stage {src_path.name}")
        return dst
    except Exception as e:
        print(f"  WARNING: local staging failed ({e}); reading from Drive")
        return src_path


def _unstage_imagery_local(local_path):
    local_path = Path(local_path)
    try:
        if str(local_path).startswith(str(LOCAL_SCRATCH)) and local_path.exists():
            local_path.unlink()
    except Exception:
        pass


def _copy_to_drive(local_path, drive_path):
    """Local-then-copy write: ensures the heavy file is written to NVMe first."""
    drive_path = Path(drive_path)
    drive_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(local_path) == drive_path:
        return
    shutil.copy2(local_path, drive_path)


# ══════════════════════════════════════════════════════════════════════════════
#  Training-site discovery (footprints only — pixels come from per-year orthos)
# ══════════════════════════════════════════════════════════════════════════════

def discover_site_footprints(site_buffer=0.0):
    """Return [(site_label, bounds_3857, crowns_gdf_or_None)] for each training site.

    Footprint geometry is taken from the 2020 7.5 cm site photo's georeferenced
    bounds (cheap metadata read, no pixels). Sites without a crown shapefile are
    dedicated true negatives (kept as all-zero masks).

    site_buffer pads each footprint by N map units (EPSG:3857) on every side,
    enlarging the crop so more tiles fit. Pixels of the enlarged crop that fall
    outside the reviewed regions are IGNORE, so usable extra tiles only appear
    where the regions already reach (≈ the prep --buffer).
    """
    print("\n── Discovering training-site footprints ──")
    if site_buffer:
        print(f"  Site buffer: +{site_buffer:.0f} map units per side")
    photo_files = sorted(PHOTOS_DIR.glob("*_rgb.tif"))
    if not photo_files:
        raise FileNotFoundError(f"No *_rgb.tif training photos in {PHOTOS_DIR}")

    sites = []
    for photo in photo_files:
        label = photo.stem.replace("_rgb", "")
        with rasterio.open(photo) as src:
            b = src.bounds
            pcrs = src.crs
        # Photos are 2020 CoE 7.5 cm in EPSG:3857; reproject bounds if not.
        if pcrs is not None and pcrs.to_epsg() != 3857:
            b = BoundingBox(*rasterio.warp.transform_bounds(pcrs, CROWN_CRS, *b))

        crowns, is_review = load_site_crowns(label)
        sites.append((label, BoundingBox(b.left - site_buffer, b.bottom - site_buffer,
                                         b.right + site_buffer, b.top + site_buffer),
                      crowns))
        if crowns is None:
            tag = "— (true negative)"
        elif is_review:
            n_app = int((crowns["status"].astype(str).str.lower() == "approved").sum()) \
                if "status" in crowns.columns else len(crowns)
            tag = f"{len(crowns)} crowns [REVIEW: {n_app} approved, interval-tagged]"
        else:
            tag = f"{len(crowns)} crowns"
        print(f"  {label:<25} {tag}")

    n_pos = sum(c is not None for _, _, c in sites)
    print(f"\n  Sites: {len(sites)}  ({n_pos} positive / "
          f"{len(sites) - n_pos} true negative)")
    return sites


def load_site_crowns(site_label):
    """Return (crowns_gdf_or_None, is_review).

    Prefers a human-reviewed, interval-tagged crown file
    (``{site}_crowns_review.gpkg`` or ``.shp``) over the legacy
    ``{site}.shp``. Review files carry ``status`` / ``valid_from`` /
    ``valid_to`` columns; legacy files don't. Sites with no crown file are
    dedicated true negatives → (None, False).
    """
    review = (POLYGONS_DIR / f"{site_label}_crowns_review.gpkg")
    review_shp = (POLYGONS_DIR / f"{site_label}_crowns_review.shp")
    legacy = (POLYGONS_DIR / f"{site_label}.shp")
    if review.exists():
        return preprocess_crowns(review), True
    if review_shp.exists():
        return preprocess_crowns(review_shp), True
    if legacy.exists():
        return preprocess_crowns(legacy), False
    return None, False


def _load_review_regions(site_label, target_crs=CROWN_CRS):
    """Reviewed-extent polygons for a site, if present.

    Inside these polygons, non-crown pixels are confirmed *background* (0);
    outside them, pixels are IGNORE (255). Returns None when no regions file
    exists, in which case the whole site crop is treated as reviewed (legacy
    wall-to-wall behaviour).
    """
    for ext in ("_regions.gpkg", "_regions.shp"):
        p = POLYGONS_DIR / f"{site_label}{ext}"
        if p.exists():
            g = gpd.read_file(p)
            if g.crs is not None and g.crs.to_epsg() != 3857:
                g = g.to_crs(target_crs)
            g = g[~g.geometry.is_empty & g.geometry.is_valid].reset_index(drop=True)
            return g if len(g) else None
    return None


def _year_int(label):
    """Calendar year from a year label ('2000' → 2000, '2019n' → 2019)."""
    import re
    m = re.match(r"(\d{4})", str(label))
    return int(m.group(1)) if m else None


def preprocess_crowns(shp_path, target_crs=CROWN_CRS):
    """Load + clean crown polygons in EPSG:3857 (same cleaning as Phase 3).

    Preserves any extra attribute columns (e.g. the review fields
    ``status`` / ``valid_from`` / ``valid_to``) so interval filtering can
    happen at rasterise time.
    """
    gdf = gpd.read_file(shp_path)
    if gdf.crs is None:
        raise ValueError(f"{shp_path} has no CRS — set a .prj before running.")
    if gdf.crs.to_epsg() != 3857:
        gdf = gdf.to_crs(target_crs)

    if "MultiPolygon" in gdf.geometry.geom_type.unique():
        gdf = gdf.explode(index_parts=False).reset_index(drop=True)
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf["geometry"] = gdf.geometry.buffer(0)
        gdf = gdf[gdf.geometry.is_valid].reset_index(drop=True)
    if "MultiPolygon" in gdf.geometry.geom_type.unique():
        gdf = gdf.explode(index_parts=False).reset_index(drop=True)
    gdf = gdf[~gdf.geometry.is_empty].reset_index(drop=True)
    gdf["area_m2"] = gdf.geometry.area
    gdf = gdf[gdf["area_m2"] >= 0.5].reset_index(drop=True)
    return gdf


def _load_coverage_overrides():
    """Optional: phase2 site×year coverage matrix. Returns {(label,site): bool}."""
    if not COVERAGE_CSV.exists():
        return {}
    try:
        df = pd.read_csv(COVERAGE_CSV)
        # Tolerate a few likely column namings.
        ycol = next((c for c in df.columns if c.lower() in
                     ("year", "label", "year_label")), None)
        scol = next((c for c in df.columns if c.lower() in
                     ("site", "site_label")), None)
        ccol = next((c for c in df.columns if "cover" in c.lower()
                     or "include" in c.lower()), None)
        if not (ycol and scol and ccol):
            return {}
        out = {}
        for _, r in df.iterrows():
            val = str(r[ccol]).strip().lower()
            covered = val in ("1", "true", "yes", "include", "covered", "y", "t")
            out[(str(r[ycol]), str(r[scol]))] = covered
        return out
    except Exception as e:
        print(f"  (coverage CSV present but unreadable: {e})")
        return {}


# ══════════════════════════════════════════════════════════════════════════════
#  Step 1 — Label projection (crop native ortho + reproject crowns + rasterise)
# ══════════════════════════════════════════════════════════════════════════════

def read_rgb_window(src, window):
    """Read the first 3 bands (R,G,B) of a window. RGBI orthos drop NIR here —
    the semantic CNN takes 3-channel RGB (NIR is only used for spectral features
    in phase1/phase7)."""
    return src.read([1, 2, 3], window=window)


def _site_window(src, bounds_native):
    """Pixel window in src covering bounds_native, clamped to the raster extent."""
    win = rasterio.windows.from_bounds(
        bounds_native.left, bounds_native.bottom,
        bounds_native.right, bounds_native.top, transform=src.transform)
    win = win.round_offsets(op="floor").round_lengths(op="ceil")
    full = rasterio.windows.Window(0, 0, src.width, src.height)
    win = win.intersection(full)
    return win


def anchor_mask_from_2020(dst_crs, dst_transform, h, w, prob_hi, prob_lo):
    """Build a 0/1/255 training mask for one crop from the 2020 full-city canopy
    probability raster (phase3/edmonds_canopy_prob_2020.tif).

    The crop's geographic footprint is read from the 2020 prob raster (decimated
    on read so the ~110 GB source never lands in RAM), aligned to the crop grid,
    then thresholded:  p >= prob_hi -> canopy (1),  p <= prob_lo -> background
    (0),  in-between or no 2020 coverage -> IGNORE (255).
    """
    if not PROB_2020.exists():
        raise FileNotFoundError(
            f"2020 canopy prob raster not found: {PROB_2020}\n"
            f"  --anchor-labels needs phase3/edmonds_canopy_prob_2020.tif")
    ignore = np.full((h, w), IGNORE_LABEL, dtype=np.uint8)
    dst_bounds = rasterio.transform.array_bounds(h, w, dst_transform)  # l,b,r,t
    with rasterio.open(PROB_2020) as psrc:
        pcrs, pnod = psrc.crs, psrc.nodata
        pb = rasterio.warp.transform_bounds(dst_crs, pcrs, *dst_bounds)
        src_win = rasterio.windows.from_bounds(*pb, transform=psrc.transform)
        src_win = src_win.round_offsets(op="floor").round_lengths(op="ceil")
        src_win = src_win.intersection(
            rasterio.windows.Window(0, 0, psrc.width, psrc.height))
        if src_win.width <= 0 or src_win.height <= 0:
            return ignore                       # crop outside 2020 coverage
        out_h = max(1, min(int(src_win.height), h))
        out_w = max(1, min(int(src_win.width),  w))
        src = psrc.read(1, window=src_win, out_shape=(out_h, out_w),
                        resampling=Resampling.average).astype(np.float32)
        win_tf = psrc.window_transform(src_win)
        src_tf = win_tf * win_tf.scale(src_win.width / out_w,
                                       src_win.height / out_h)
    if pnod is not None:
        src[src == pnod] = np.nan
    prob = np.full((h, w), np.nan, dtype=np.float32)
    rasterio.warp.reproject(
        source=src, destination=prob,
        src_transform=src_tf, src_crs=pcrs,
        dst_transform=dst_transform, dst_crs=dst_crs,
        src_nodata=np.nan, dst_nodata=np.nan,
        resampling=Resampling.average)
    mask = np.full((h, w), IGNORE_LABEL, dtype=np.uint8)
    mask[prob <= prob_lo] = 0
    mask[prob >= prob_hi] = 1
    return mask


def canopy_label_from_2020_mask(msrc, dst_crs, dst_transform, h, w):
    """Reproject the OPEN Phase 3 2020 binary canopy mask (``msrc``) onto a crop
    grid. Used by the coarse city-wide tiler (Fix 3) — the 2020 canopy mask is
    the label source for coarse years.

    Returns a 0/1/255 uint8 label: 1 = 2020 canopy, 0 = 2020 background,
    255 = IGNORE (mask nodata or outside the 2020 footprint). Nearest-neighbour
    throughout because the mask is categorical; the fine 7.5 cm source is
    decimated toward the coarse crop size on read. ``msrc`` is passed in already
    open so the city-wide loop reuses one handle for thousands of crops.
    """
    out = np.full((h, w), IGNORE_LABEL, dtype=np.uint8)
    dst_bounds = rasterio.transform.array_bounds(h, w, dst_transform)  # l,b,r,t
    mcrs, mnod = msrc.crs, msrc.nodata
    mb = rasterio.warp.transform_bounds(dst_crs, mcrs, *dst_bounds)
    src_win = rasterio.windows.from_bounds(*mb, transform=msrc.transform)
    src_win = src_win.round_offsets(op="floor").round_lengths(op="ceil")
    src_win = src_win.intersection(
        rasterio.windows.Window(0, 0, msrc.width, msrc.height))
    if src_win.width <= 0 or src_win.height <= 0:
        return out                                   # crop outside 2020 coverage
    out_h = max(1, min(int(src_win.height), h))
    out_w = max(1, min(int(src_win.width),  w))
    raw = msrc.read(1, window=src_win, out_shape=(out_h, out_w),
                    resampling=Resampling.nearest).astype(np.uint8)
    win_tf = msrc.window_transform(src_win)
    src_tf = win_tf * win_tf.scale(src_win.width / out_w, src_win.height / out_h)
    dst_arr = np.full((h, w), 255, dtype=np.uint8)
    rasterio.warp.reproject(
        source=raw, destination=dst_arr,
        src_transform=src_tf, src_crs=mcrs,
        dst_transform=dst_transform, dst_crs=dst_crs,
        src_nodata=(mnod if mnod is not None else 255), dst_nodata=255,
        resampling=Resampling.nearest)
    out[dst_arr == 0] = 0
    out[dst_arr == 1] = 1
    return out


def project_and_rasterise_site(src, src_nodata, native_crs, label, site_label,
                               site_bounds_3857, crowns_3857, year_dir,
                               dry_run=False, anchor_labels=False,
                               prob_hi=0.6, prob_lo=0.4):
    """Crop one site from the year's native ortho and build its binary mask.

    Returns (img_path, mask_path, covered, canopy_frac) or (None, None, False, 0)
    if the site is not covered by this year's imagery.
    """
    # Reproject the site footprint into the ortho's native CRS.
    if native_crs is not None and native_crs.to_epsg() != 3857:
        bn = BoundingBox(*rasterio.warp.transform_bounds(
            CROWN_CRS, native_crs,
            site_bounds_3857.left, site_bounds_3857.bottom,
            site_bounds_3857.right, site_bounds_3857.top))
    else:
        bn = site_bounds_3857

    win = _site_window(src, bn)
    if win.width <= 0 or win.height <= 0:
        return None, None, False, 0.0  # footprint outside this ortho entirely

    rgb = read_rgb_window(src, win)                       # 3×h×w
    win_tf = rasterio.windows.transform(win, src.transform)

    # Coverage: a pixel is "no data" if all 3 bands equal the nodata fill (or 0).
    if src_nodata is not None:
        nod = np.all(rgb == src_nodata, axis=0)
    else:
        nod = np.all(rgb == 0, axis=0)
    nod_frac = float(nod.mean())
    if nod_frac > COVERAGE_NODATA_MAX:
        print(f"    {site_label:<22} not covered ({nod_frac*100:.0f}% nodata) — skip")
        return None, None, False, 0.0

    h, w = rgb.shape[1], rgb.shape[2]

    # ── Build the training mask: 0 = background, 1 = canopy, 255 = IGNORE ──────
    if anchor_labels:
        # Import labels from the 2020 full-city canopy probability raster
        # (labels the whole crop; crowns/regions are not used).
        mask = anchor_mask_from_2020(native_crs, win_tf, h, w, prob_hi, prob_lo)
        is_review = False
        regions = None
    else:
        # Review mode (interval-tagged crowns) vs legacy (all crowns = canopy).
        is_review = (crowns_3857 is not None and "status" in crowns_3857.columns)
        year_int  = _year_int(label)

        def _to_native(gdf):
            if gdf is None or len(gdf) == 0:
                return gdf
            return (gdf if (native_crs is None or native_crs.to_epsg() == 3857)
                    else gdf.to_crs(native_crs))

        # Which crowns to burn as canopy this year.
        if is_review:
            sel = crowns_3857
            st = sel["status"].astype(str).str.lower()
            sel = sel[st.eq("approved")]
            if "valid_from" in sel.columns and year_int is not None:
                vf = pd.to_numeric(sel["valid_from"], errors="coerce")
                sel = sel[vf.isna() | (vf <= year_int)]
            if "valid_to" in sel.columns and year_int is not None:
                vt = pd.to_numeric(sel["valid_to"], errors="coerce")
                sel = sel[vt.isna() | (vt >= year_int)]
            burn = sel
        else:
            burn = crowns_3857

        regions = _load_review_regions(site_label) if is_review else None

        def _rasterise(gdf):
            if gdf is None or len(gdf) == 0:
                return np.zeros((h, w), dtype=np.uint8)
            return rasterio.features.rasterize(
                ((g, 1) for g in _to_native(gdf).geometry),
                out_shape=(h, w), transform=win_tf, fill=0, dtype=np.uint8,
                all_touched=False)

        if regions is not None:
            # Outside the reviewed regions → IGNORE; inside → background, then canopy.
            mask = np.full((h, w), IGNORE_LABEL, dtype=np.uint8)
            mask[_rasterise(regions) == 1] = 0
            mask[_rasterise(burn) == 1] = 1
        else:
            # Legacy / true-negative / review-without-regions: whole crop reviewed.
            mask = _rasterise(burn)

    # Imagery nodata is never a valid label → mark it IGNORE (don't train "nodata
    # is background"). For fully-covered legacy years `nod` is empty → no change.
    mask[nod] = IGNORE_LABEL

    labeled      = mask != IGNORE_LABEL
    n_labeled    = int(labeled.sum())
    canopy_frac  = float((mask == 1).sum()) / n_labeled if n_labeled else 0.0
    labeled_frac = n_labeled / (h * w) if h * w else 0.0

    rev = (" [anchor2020]" if anchor_labels
           else (" [review]" if is_review or regions is not None else ""))
    lab = (f"  labeled {labeled_frac*100:4.1f}%"
           if (anchor_labels or is_review or regions is not None) else "")

    if dry_run:
        print(f"    {site_label:<22} {w}×{h}px  canopy {canopy_frac*100:4.1f}%{lab}{rev}  "
              f"(dry run)")
        return None, None, True, canopy_frac

    year_dir.mkdir(parents=True, exist_ok=True)
    img_path  = year_dir / f"{site_label.lower()}_img.tif"
    mask_path = year_dir / f"{site_label.lower()}_mask.tif"

    img_profile = {
        "driver": "GTiff", "dtype": "uint8", "count": 3,
        "width": w, "height": h, "crs": native_crs, "transform": win_tf,
        "compress": "lzw",
    }
    mask_profile = {
        "driver": "GTiff", "dtype": "uint8", "count": 1,
        "width": w, "height": h, "crs": native_crs, "transform": win_tf,
        "compress": "lzw", "nodata": 255,
    }
    with rasterio.open(img_path, "w", **img_profile) as dst:
        dst.write(rgb)
    with rasterio.open(mask_path, "w", **mask_profile) as dst:
        dst.write(mask, 1)

    print(f"    {site_label:<22} {w}×{h}px  canopy {canopy_frac*100:4.1f}%{lab}{rev}")
    return img_path, mask_path, True, canopy_frac


def step_labels(label, sites, dry_run=False, anchor_labels=False,
                prob_hi=0.6, prob_lo=0.4, citywide=False):
    """Step 1 for one year: build native-GSD site crops + binary masks."""
    entry = entry_for(label)
    tier  = tier_of(entry["gsd_cm"])
    if citywide:
        # Coarse city-wide path (Fix 3) builds its labels from the 2020 mask
        # during Step 2 (tiling), straight off the full ortho — no site crops.
        print(f"\n── [{label}] Step 1: Label projection — SKIPPED "
              f"(coarse city-wide tiling labels tiles from the 2020 mask in "
              f"Step 2) ──")
        return None
    print(f"\n── [{label}] Step 1: Label projection "
          f"({entry['gsd_cm']:.1f} cm, {tier}, EPSG:{entry['crs_epsg']}) ──")

    native = resolve_native_path(entry)
    if not native.exists():
        print(f"  ERROR: native ortho not found: {native}")
        return None

    overrides = _load_coverage_overrides()
    year_dir  = SITE_DIR / label
    local = _stage_imagery_local(native) if not dry_run else native

    cov_rows = []
    try:
        with rasterio.open(local) as src:
            native_crs = src.crs
            src_nodata = src.nodata
            print(f"  Ortho: {src.width}×{src.height}px  nodata={src_nodata}")
            for site_label, b3857, crowns in sites:
                # Honour an explicit phase2 exclusion if present.
                if overrides.get((label, site_label)) is False:
                    print(f"    {site_label:<22} excluded by phase2 coverage matrix")
                    cov_rows.append(dict(year=label, site=site_label,
                                         covered=False, canopy_frac=0.0))
                    continue
                ip, mp, covered, frac = project_and_rasterise_site(
                    src, src_nodata, native_crs, label, site_label, b3857,
                    crowns, year_dir, dry_run=dry_run,
                    anchor_labels=anchor_labels, prob_hi=prob_hi, prob_lo=prob_lo)
                cov_rows.append(dict(year=label, site=site_label,
                                     covered=covered, canopy_frac=round(frac, 4)))
    finally:
        if not dry_run:
            _unstage_imagery_local(local)

    n_cov = sum(r["covered"] for r in cov_rows)
    print(f"  Covered sites: {n_cov}/{len(cov_rows)}")
    if n_cov == 0:
        print(f"  WARNING: no covered training sites for {label} — cannot fine-tune.")
    return cov_rows


# ══════════════════════════════════════════════════════════════════════════════
#  Step 2 — Tiling (per-tier stride; reads the native-GSD site crops)
# ══════════════════════════════════════════════════════════════════════════════

def tile_site_native(site_label, img_path, mask_path, stride, neg_rate,
                     keep_all_empty=False):
    """512×512 paired tiles for one site crop at native resolution."""
    records = []
    with rasterio.open(img_path) as img_src, rasterio.open(mask_path) as msk_src:
        h, w = img_src.height, img_src.width
        assert (h, w) == (msk_src.height, msk_src.width), \
            f"dim mismatch {site_label}"
        img_tf, crs = img_src.transform, img_src.crs

        if h < TILE_SIZE or w < TILE_SIZE:
            # Site smaller than one tile (can happen at very coarse GSD): pad-read
            # a single TILE_SIZE window so the year still contributes a tile.
            row_starts, col_starts = [0], [0]
        else:
            row_starts = range(0, h - TILE_SIZE + 1, stride)
            col_starts = range(0, w - TILE_SIZE + 1, stride)

        accepted = rejected = 0
        for ro in row_starts:
            for co in col_starts:
                win = rasterio.windows.Window(co, ro, TILE_SIZE, TILE_SIZE)
                img_tile = img_src.read(window=win, boundless=True, fill_value=0)
                msk_tile = msk_src.read(1, window=win, boundless=True,
                                        fill_value=IGNORE_LABEL)
                labeled = msk_tile != IGNORE_LABEL
                n_lab = int(labeled.sum())
                if n_lab == 0:
                    rejected += 1            # entirely unreviewed → no signal
                    continue
                canopy_frac = float((msk_tile == 1).sum()) / n_lab

                if canopy_frac == 0.0:
                    if keep_all_empty or np.random.random() < neg_rate:
                        pass
                    else:
                        rejected += 1
                        continue

                records.append({
                    "tile_name": f"{site_label.lower()}_r{ro:05d}_c{co:05d}.tif",
                    "site": site_label, "row_off": ro, "col_off": co,
                    "canopy_frac": round(canopy_frac, 4),
                    "crs": crs,
                    "tile_transform": rasterio.windows.transform(win, img_tf),
                    "_img_tile": img_tile, "_mask_tile": msk_tile,
                })
                accepted += 1
        print(f"    {site_label:<22} {accepted} accepted / {rejected} rejected")
    return records


# ── Canopy-fraction stratification (Fix 3) ────────────────────────────────────

def _frac_bin(f):
    """5-bin index for a tile's canopy fraction. Bin 0 is exactly-background
    (hard negatives: roads, rooftops, water, parking)."""
    if f <= 0.0:
        return 0
    if f <= 0.25:
        return 1
    if f <= 0.50:
        return 2
    if f <= 0.75:
        return 3
    return 4


def _stratified_sample(records, budget, seed=RANDOM_SEED):
    """Sample ~balanced counts per canopy-fraction bin up to `budget` — NEVER
    first-N (the old cap took the first N canopy tiles and dropped every
    negative). Records flagged ``force_keep`` (true-negative-site tiles) are
    always retained; they count against the budget but not the per-bin balance.
    Returns a shuffled list. May exceed `budget` only if forced tiles alone do.
    """
    if budget is None or len(records) <= budget:
        return list(records)
    rng = np.random.RandomState(seed)
    forced = [r for r in records if r.get("force_keep")]
    pool   = [r for r in records if not r.get("force_keep")]
    remaining = max(0, budget - len(forced))
    bins = {}
    for r in pool:
        bins.setdefault(_frac_bin(r["canopy_frac"]), []).append(r)
    per = max(1, remaining // max(1, len(bins)))
    chosen, leftover = [], []
    for b in sorted(bins):
        rs = bins[b]
        rng.shuffle(rs)
        chosen.extend(rs[:per])
        leftover.extend(rs[per:])
    if len(chosen) < remaining:
        rng.shuffle(leftover)
        chosen.extend(leftover[:remaining - len(chosen)])
    out = forced + chosen[:remaining]
    rng.shuffle(out)
    return out


def _bin_histogram(records):
    """'b0:120 b1:80 …' canopy-fraction bin counts, for logging."""
    counts = {}
    for r in records:
        counts[_frac_bin(r["canopy_frac"])] = counts.get(_frac_bin(r["canopy_frac"]), 0) + 1
    return "  ".join(f"b{b}:{counts.get(b, 0)}" for b in range(5))


def _tile_grvi(img_tile, valid):
    """Mean GRVI = (G-R)/(G+R) over labeled pixels of an RGB tile (3×H×W uint8).
    Positive → vegetated; near-zero / negative → pavement, roof, bare, water.
    Used to flag green hard-negatives (Fix B)."""
    if int(valid.sum()) == 0:
        return 0.0
    r = img_tile[0].astype(np.float32)
    g = img_tile[1].astype(np.float32)
    grvi = (g - r) / (g + r + 1e-6)
    return float(grvi[valid].mean())


def _select_citywide_tiles(records, budget, seed=RANDOM_SEED):
    """City-wide coarse tile selection (Fix B).

    force_keep tiles (curated negative sites) are always retained and exempt
    from the budget caps. BACKGROUND_BUDGET_FRACTION of the remaining budget goes
    to background (bin 0), of which HARD_NEG_FRACTION is reserved for green
    hard-negatives (grass) so the grass/canopy boundary is represented; the rest
    of the budget is split among canopy bins (1..4), balanced among themselves
    (Fix B + Fix C). Returns (selected_records, stats_dict).
    """
    if budget is None or len(records) <= budget:
        return list(records), {"forced": sum(1 for r in records if r.get("force_keep")),
                               "background": sum(1 for r in records
                                                 if not r.get("force_keep")
                                                 and _frac_bin(r["canopy_frac"]) == 0),
                               "green_hardneg": sum(1 for r in records
                                                    if r.get("is_green_hardneg")),
                               "canopy": sum(1 for r in records
                                             if _frac_bin(r["canopy_frac"]) > 0)}
    rng = np.random.RandomState(seed)
    forced = [r for r in records if r.get("force_keep")]
    pool   = [r for r in records if not r.get("force_keep")]
    remaining = max(0, budget - len(forced))

    by_bin = {}
    for r in pool:
        by_bin.setdefault(_frac_bin(r["canopy_frac"]), []).append(r)

    # Background gets a fixed share of the budget (Fix C); canopy bins split the
    # rest. Carry any background shortfall over to canopy so the budget is used.
    bg = by_bin.get(0, [])
    n_bg = min(len(bg), int(round(BACKGROUND_BUDGET_FRACTION * remaining)))
    n_can_budget = remaining - n_bg

    # Background bin 0 with a reserved green-hard-negative slice (Fix B).
    green = [r for r in bg if r.get("is_green_hardneg")]
    plain = [r for r in bg if not r.get("is_green_hardneg")]
    rng.shuffle(green); rng.shuffle(plain)
    n_green = min(len(green), int(round(HARD_NEG_FRACTION * n_bg)))
    bg_sel = green[:n_green] + plain[:max(0, n_bg - n_green)]
    if len(bg_sel) < n_bg:                          # ran out of plain → more green
        bg_sel += green[n_green:n_green + (n_bg - len(bg_sel))]

    # Canopy bins 1..4 balanced among themselves.
    canopy_bins = [b for b in sorted(by_bin) if b != 0]
    per_can = max(1, n_can_budget // max(1, len(canopy_bins))) if canopy_bins else 0
    can_sel, leftover = [], []
    for b in canopy_bins:
        rs = by_bin[b]; rng.shuffle(rs)
        can_sel.extend(rs[:per_can]); leftover.extend(rs[per_can:])
    if len(can_sel) < n_can_budget:                 # top up to the canopy budget
        rng.shuffle(leftover)
        can_sel.extend(leftover[:n_can_budget - len(can_sel)])
    can_sel = can_sel[:n_can_budget]

    chosen = bg_sel + can_sel
    out = forced + chosen
    rng.shuffle(out)
    stats = dict(
        forced=len(forced),
        background=sum(1 for r in chosen if _frac_bin(r["canopy_frac"]) == 0),
        green_hardneg=sum(1 for r in chosen if r.get("is_green_hardneg")),
        canopy=sum(1 for r in chosen if _frac_bin(r["canopy_frac"]) > 0))
    return out, stats


def _is_negative_site(site_label, crowns):
    """A curated negative training site (Fix A). True for: a 'Negative_*' site,
    a site with no crown file (``crowns is None``), or a review site whose
    approved-crown count is zero.

    Negative_Parking carries a review gpkg with zero approved crowns, so the old
    ``crowns is None`` test misclassified it as a positive site and dropped it
    from the city-wide negative pool — the root of the precision problem.
    """
    if str(site_label).lower().startswith("negative"):
        return True
    if crowns is None:
        return True
    cols = getattr(crowns, "columns", [])
    if "status" in cols:
        return int((crowns["status"].astype(str).str.lower()
                    == "approved").sum()) == 0
    return False


def _negative_site_records(src, sites, src_nodata):
    """Explicit guaranteed-background tiles from curated negative sites (Fix A).

    Tiles each negative site's footprint straight from the year's ortho, in the
    ortho's pixel space (so block/split coordinates line up with the city-wide
    tiles), and labels every pixel background (0; IGNORE only where the imagery
    is nodata) — we do NOT trust the 2020 mask over a curated negative. Records
    are ``force_keep=True`` so they bypass the stratified cap and are pinned to
    train. This replaces the old overlap-based force-keep, which depended on a
    candidate tile happening to land on the footprint and missed Negative_Parking
    entirely.
    """
    out, seen = [], set()
    img_h, img_w, tf = src.height, src.width, src.transform
    for site_label, b3857, crowns in sites:
        if not _is_negative_site(site_label, crowns):
            continue
        if src.crs is not None and src.crs.to_epsg() != 3857:
            bn = BoundingBox(*rasterio.warp.transform_bounds(
                CROWN_CRS, src.crs, b3857.left, b3857.bottom,
                b3857.right, b3857.top))
        else:
            bn = b3857
        win = _site_window(src, bn)
        if win.width <= 0 or win.height <= 0:
            continue
        r0, c0 = int(win.row_off), int(win.col_off)
        rh, rw = int(win.height), int(win.width)
        rows = list(range(r0, r0 + max(1, rh - TILE_SIZE + 1), TILE_SIZE)) or [r0]
        cols = list(range(c0, c0 + max(1, rw - TILE_SIZE + 1), TILE_SIZE)) or [c0]
        kept = 0
        for ro in rows:
            for co in cols:
                ro2 = min(max(0, ro), max(0, img_h - TILE_SIZE))
                co2 = min(max(0, co), max(0, img_w - TILE_SIZE))
                if (ro2, co2) in seen:
                    continue
                seen.add((ro2, co2))
                win_t = rasterio.windows.Window(co2, ro2, TILE_SIZE, TILE_SIZE)
                img_tile = src.read([1, 2, 3], window=win_t,
                                    boundless=True, fill_value=0)
                if src_nodata is not None:
                    nod = np.all(img_tile == src_nodata, axis=0)
                else:
                    nod = np.all(img_tile == 0, axis=0)
                if float(nod.mean()) > COVERAGE_NODATA_MAX:
                    continue
                mask_tile = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.uint8)
                mask_tile[nod] = IGNORE_LABEL
                out.append({
                    "tile_name": f"neg_{site_label.lower()}_r{ro2:05d}_c{co2:05d}.tif",
                    "site": f"neg:{site_label}", "row_off": ro2, "col_off": co2,
                    "canopy_frac": 0.0, "crs": src.crs,
                    "tile_transform": rasterio.windows.transform(win_t, tf),
                    "_img_tile": img_tile, "_mask_tile": mask_tile,
                    "force_keep": True, "grvi": 0.0, "is_green_hardneg": False,
                })
                kept += 1
        if kept:
            print(f"    negative site {site_label:<22} +{kept} background tile(s)")
    return out


def _gather_citywide_coarse(label, sites, stride_override=None, dry_run=False):
    """Coarse-tier city-wide tiling (Fix 3).

    Sample 512px tiles across the FULL city ortho for this year, labelling each
    from the Phase 3 2020 binary canopy mask reprojected to the year's native
    grid. Curated negative sites are then explicitly tiled as guaranteed
    background and appended (force_keep=True, Fix A). Returns a list of tile
    records (same schema as ``tile_site_native``, plus a ``force_keep`` flag).
    """
    entry  = entry_for(label)
    native = resolve_native_path(entry)
    if not native.exists():
        print(f"  ERROR: native ortho not found: {native}")
        return []
    if not MASK_2020.exists():
        print(f"  ERROR: Phase 3 2020 canopy mask not found: {MASK_2020}\n"
              f"        coarse city-wide tiling needs it as the label source.")
        return []
    stride = int(stride_override) if stride_override else CITYWIDE_CANDIDATE_STRIDE

    local      = native    if dry_run else _stage_imagery_local(native)
    mask_local = MASK_2020  if dry_run else _stage_imagery_local(MASK_2020)
    records = []
    try:
        with rasterio.open(local) as src:
            native_crs, src_nodata = src.crs, src.nodata
            img_h, img_w, tf = src.height, src.width, src.transform
            print(f"  Ortho: {img_w}×{img_h}px  GSD≈{tf.a*100:.1f}cm  "
                  f"nodata={src_nodata}")
            rows = list(range(0, max(1, img_h - TILE_SIZE + 1), stride)) or [0]
            cols = list(range(0, max(1, img_w - TILE_SIZE + 1), stride)) or [0]
            origins = [(r, c) for r in rows for c in cols]
            print(f"  Candidate positions: {len(origins):,}  (stride={stride})")
            if dry_run:
                print("  Dry run — not reading tiles")
                return []
            with rasterio.open(mask_local) as msrc:
                for ro, co in tqdm(origins, desc="  City-wide scan",
                                   mininterval=2.0):
                    win = rasterio.windows.Window(co, ro, TILE_SIZE, TILE_SIZE)
                    img_tile = src.read(window=win, boundless=True, fill_value=0)
                    if src_nodata is not None:
                        nod = np.all(img_tile == src_nodata, axis=0)
                    else:
                        nod = np.all(img_tile == 0, axis=0)
                    if float(nod.mean()) > COVERAGE_NODATA_MAX:
                        continue                       # un-imaged tile
                    win_tf = rasterio.windows.transform(win, tf)
                    mask_tile = canopy_label_from_2020_mask(
                        msrc, native_crs, win_tf, TILE_SIZE, TILE_SIZE)
                    mask_tile[nod] = IGNORE_LABEL
                    n_lab = int((mask_tile != IGNORE_LABEL).sum())
                    if n_lab == 0:
                        continue                       # no 2020 label here
                    canopy_frac = float((mask_tile == 1).sum()) / n_lab
                    grvi = _tile_grvi(img_tile, mask_tile != IGNORE_LABEL)
                    records.append({
                        "tile_name": f"city_r{ro:05d}_c{co:05d}.tif",
                        "site": "city", "row_off": ro, "col_off": co,
                        "canopy_frac": round(canopy_frac, 4),
                        "crs": native_crs,
                        "tile_transform": win_tf,
                        "_img_tile": img_tile, "_mask_tile": mask_tile,
                        "force_keep": False, "grvi": round(grvi, 4),
                        "is_green_hardneg": (canopy_frac == 0.0
                                             and grvi >= GREEN_GRVI_THRESHOLD),
                    })
            # Curated negative sites → explicit guaranteed-background tiles (Fix A).
            records.extend(_negative_site_records(src, sites, src_nodata))
    finally:
        if not dry_run:
            if local != native:
                _unstage_imagery_local(local)
            if mask_local != MASK_2020:
                _unstage_imagery_local(mask_local)
    n_force = sum(1 for r in records if r.get("force_keep"))
    print(f"  Gathered {len(records)} labeled tiles "
          f"({n_force} force-kept negative-site)  bins[{_bin_histogram(records)}]")
    return records


def _assign_blocks(records, gsd_m, block_size_m=SPATIAL_BLOCK_SIZE_M):
    """Tag each record with a spatial block id (Fix 4). Block edge is
    `block_size_m` on the ground, never smaller than one tile."""
    block_px = max(TILE_SIZE, int(round(block_size_m / gsd_m)))
    for r in records:
        r["block"] = f"{r['row_off'] // block_px}_{r['col_off'] // block_px}"
    return block_px


def _block_partition(records, gsd_m, val_frac=COARSE_VAL_FRAC,
                     test_frac=COARSE_TEST_FRAC, buffer_m=CANOPY_AUTOCORR_M,
                     seed=RANDOM_SEED):
    """Geographically-blocked train/val/test split for city-wide coarse tiles
    (Fix 4). Whole spatial blocks go to test, val, or train; then train tiles
    within `buffer_m` of any val/test tile are dropped so the held-out sets are
    honestly separated (canopy autocorrelation range ≈ 250–520 m).

    Sets ``r['split']`` ∈ {train, val, test, drop} on each record. Falls back to
    a degraded split (no test, random val, nothing dropped) and flags it when
    blocking can't form non-empty val AND test (e.g. partial-coverage years with
    too few blocks). Returns a status dict for logging.
    """
    block_px = _assign_blocks(records, gsd_m)
    n = len(records)
    rng = np.random.RandomState(seed)
    status = {"blocks": 0, "block_px": block_px, "degraded": False,
              "train": 0, "val": 0, "test": 0}

    def _degraded():
        status["degraded"] = True
        idx = list(range(n)); rng.shuffle(idx)
        n_val = max(1, int(round(val_frac * n)))
        val_ids = set(idx[:n_val])
        for i, r in enumerate(records):
            r["split"] = "val" if i in val_ids else "train"
        status["train"] = sum(r["split"] == "train" for r in records)
        status["val"]   = sum(r["split"] == "val" for r in records)
        status["test"]  = 0
        return status

    blocks = sorted({r["block"] for r in records})
    rng.shuffle(blocks)
    status["blocks"] = len(blocks)
    if len(blocks) < 3 or n < 10:
        return _degraded()

    block_tiles = {b: [r for r in records if r["block"] == b] for b in blocks}
    test_blocks, val_blocks = set(), set()
    acc = 0
    for b in blocks:
        if acc >= test_frac * n:
            break
        test_blocks.add(b); acc += len(block_tiles[b])
    acc = 0
    for b in blocks:
        if b in test_blocks:
            continue
        if acc >= val_frac * n:
            break
        val_blocks.add(b); acc += len(block_tiles[b])

    for r in records:
        r["split"] = ("test" if r["block"] in test_blocks
                      else "val" if r["block"] in val_blocks else "train")

    # Buffer: drop train tiles within buffer_m (Chebyshev) of any held-out tile.
    buf_px = buffer_m / gsd_m
    held = [(r["row_off"], r["col_off"]) for r in records
            if r["split"] in ("val", "test")]
    if held:
        hp = np.asarray(held, dtype=np.float64)
        for r in records:
            if r["split"] != "train":
                continue
            d = np.maximum(np.abs(hp[:, 0] - r["row_off"]),
                           np.abs(hp[:, 1] - r["col_off"])).min()
            if d < buf_px:
                r["split"] = "drop"

    status["train"] = sum(r["split"] == "train" for r in records)
    status["val"]   = sum(r["split"] == "val" for r in records)
    status["test"]  = sum(r["split"] == "test" for r in records)
    if status["train"] == 0 or status["val"] == 0 or status["test"] == 0:
        return _degraded()           # partial coverage left a split empty
    return status


def step_tile(label, sites, dry_run=False, max_tiles=None, stride_override=None,
              citywide=False):
    """Step 2 for one year: tile site crops (or the full city for coarse) and
    write the per-year index.

    ``citywide`` (coarse default, Fix 3) samples tiles across the whole city
    ortho labelled from the 2020 mask, balanced by canopy fraction, instead of
    tiling the 6 site crops.
    """
    entry = entry_for(label)
    tier  = tier_of(entry["gsd_cm"])
    tp    = TIER_TILE_PARAMS[tier]
    stride = int(stride_override) if stride_override else tp["stride"]
    mode = "CITY-WIDE" if citywide else "6-site"
    print(f"\n── [{label}] Step 2: Tiling [{mode}] ({tier}: stride={stride}, "
          f"neg_rate={tp['neg_rate']}, test={'yes' if tp['has_test'] else 'no'}) ──")

    out_tile_dir  = TILE_DIR / label
    for split in ("train", "val", "test"):
        (out_tile_dir / split / "images").mkdir(parents=True, exist_ok=True)
        (out_tile_dir / split / "masks").mkdir(parents=True, exist_ok=True)

    np.random.seed(RANDOM_SEED)

    if citywide:
        all_records = _gather_citywide_coarse(
            label, sites, stride_override=stride_override, dry_run=dry_run)
        if dry_run:
            print("  Dry run — not writing tiles")
            return
        all_records, sel = _select_citywide_tiles(all_records, COARSE_CITYWIDE_TILES)
        tot = max(1, len(all_records))
        print(f"  Selected {len(all_records)} tiles: {sel['canopy']} canopy / "
              f"{sel['background']} background ({sel['green_hardneg']} green "
              f"hard-neg) + {sel['forced']} neg-site  "
              f"[bg target {BACKGROUND_BUDGET_FRACTION:.0%}, "
              f"actual {(sel['background'] + sel['forced']) / tot:.0%}]  "
              f"bins[{_bin_histogram(all_records)}]")
    else:
        year_site_dir  = SITE_DIR / label
        negative_sites = {s for s, _, c in sites if c is None}
        all_records = []
        for site_label, _, _ in sites:
            ip = year_site_dir / f"{site_label.lower()}_img.tif"
            mp = year_site_dir / f"{site_label.lower()}_mask.tif"
            if not (ip.exists() and mp.exists()):
                continue  # uncovered/skipped in step 1
            all_records.extend(tile_site_native(
                site_label, ip, mp, stride, tp["neg_rate"],
                keep_all_empty=(site_label in negative_sites)))

        print(f"  Total tiles: {len(all_records)}")

        # Optional cap for fast test runs — stratified by canopy fraction, NEVER
        # first-N (the old cap dropped all negatives).
        if max_tiles is not None and len(all_records) > max_tiles:
            all_records = _stratified_sample(all_records, max_tiles)
            n_pos = sum(1 for r in all_records if r["canopy_frac"] > 0)
            print(f"  Capped to {len(all_records)} tiles "
                  f"({n_pos} canopy / {len(all_records) - n_pos} background, "
                  f"stratified)  bins[{_bin_histogram(all_records)}]")

        if dry_run:
            print("  Dry run — not writing tiles")
            return

    if not all_records:
        print(f"  ERROR: no tiles for {label} — skipping (run step labels first).")
        return

    # Split assignment.
    if citywide:
        # Fix 4: geographically-blocked train/val/test over the SAMPLED city
        # tiles. Fix A: curated negative-site tiles (force_keep) are pinned to
        # train and never enter the held-out split — they are guaranteed
        # background, not test material.
        forced  = [r for r in all_records if r.get("force_keep")]
        sampled = [r for r in all_records if not r.get("force_keep")]
        st = _block_partition(sampled, gsd_m=entry["gsd_cm"] / 100.0)
        n_drop = sum(1 for r in sampled if r["split"] == "drop")
        sampled = [r for r in sampled if r["split"] != "drop"]
        for r in forced:                       # curated negatives → always train
            r["split"] = "train"
            r.setdefault("block", "neg")
        all_records = sampled + forced
        if st["degraded"]:
            print(f"  ⚠ blocked split DEGRADED (blocks={st['blocks']}): no held-out "
                  f"test, random val — partial coverage / too few blocks")
        print(f"  Blocked split: train {st['train']} (+{len(forced)} neg-site) / "
              f"val {st['val']} / test {st['test']}  (dropped {n_drop} buffer "
              f"tiles; block={st['block_px']}px, buffer={CANOPY_AUTOCORR_M:.0f}m)")
    else:
        # Train/test split. Coarse 6-site years have no held-out test → all train.
        tile_names = [r["tile_name"] for r in all_records]
        site_of    = [r["site"] for r in all_records]
        if tp["has_test"] and len(set(site_of)) > 1 and len(all_records) >= 20:
            np.random.seed(RANDOM_SEED)
            train_names, _ = train_test_split(
                tile_names, test_size=tp["test_frac"], stratify=site_of,
                random_state=RANDOM_SEED)
            train_set = set(train_names)
        else:
            if tp["has_test"]:
                print("  (too few tiles/sites for a stratified test split — all train)")
            train_set = set(tile_names)
        for r in all_records:
            r["split"] = "train" if r["tile_name"] in train_set else "test"

    img_base  = {"driver": "GTiff", "dtype": "uint8", "count": 3,
                 "width": TILE_SIZE, "height": TILE_SIZE, "compress": "lzw"}
    mask_base = {"driver": "GTiff", "dtype": "uint8", "count": 1,
                 "width": TILE_SIZE, "height": TILE_SIZE, "compress": "lzw",
                 "nodata": 255}

    index_rows = []
    for rec in tqdm(all_records, desc="  Writing tiles"):
        split = rec["split"]
        img_out  = out_tile_dir / split / "images" / rec["tile_name"]
        mask_out = out_tile_dir / split / "masks"  / rec["tile_name"]
        with rasterio.open(img_out, "w", **{**img_base, "crs": rec["crs"],
                           "transform": rec["tile_transform"]}) as dst:
            dst.write(rec["_img_tile"])
        with rasterio.open(mask_out, "w", **{**mask_base, "crs": rec["crs"],
                           "transform": rec["tile_transform"]}) as dst:
            dst.write(np.asarray(rec["_mask_tile"]).squeeze(), 1)
        index_rows.append({
            "tile_name": rec["tile_name"], "site": rec["site"], "split": split,
            "row_off": rec["row_off"], "col_off": rec["col_off"],
            "canopy_frac": rec["canopy_frac"], "block": rec.get("block", ""),
            "img_path": str(img_out), "mask_path": str(mask_out),
        })

    index_df = pd.DataFrame(index_rows)
    index_path = out_tile_dir / f"tile_index_{label}.csv"
    index_df.to_csv(index_path, index=False)
    n_tr = (index_df["split"] == "train").sum()
    n_va = (index_df["split"] == "val").sum()
    n_te = (index_df["split"] == "test").sum()
    print(f"  ✓ {len(index_rows)} tiles  (train {n_tr} / val {n_va} / "
          f"test {n_te})  → {index_path.name}")


# ══════════════════════════════════════════════════════════════════════════════
#  Augmentation / dataset / model (ported from Phase 3)
# ══════════════════════════════════════════════════════════════════════════════

def _make_spatial_transform():
    _ensure_torch()
    return A.Compose([
        A.HorizontalFlip(p=0.5), A.VerticalFlip(p=0.5), A.Transpose(p=0.5),
        A.RandomRotate90(p=0.5),
        A.Rotate(limit=45, border_mode=0, p=0.5),
        A.Affine(translate_percent=0.1, scale=(0.9, 1.1), rotate=0,
                 border_mode=0, p=0.5),
        A.GridDistortion(num_steps=5, distort_limit=0.3, p=0.4),
        A.ElasticTransform(alpha=50, sigma=5, p=0.3),
    ], additional_targets={"mask": "mask"})


def _make_pixel_transform():
    _ensure_torch()
    return A.Compose([
        A.OneOf([A.GaussianBlur(blur_limit=(3, 7), p=1.0),
                 A.MedianBlur(blur_limit=5, p=1.0)], p=0.5),
        A.RandomBrightnessContrast(0.3, 0.3, p=0.6),
        A.HueSaturationValue(15, 30, 15, p=0.5),
        A.RandomGamma(gamma_limit=(70, 130), p=0.4),
        A.RandomShadow(shadow_roi=(0, 0, 1, 1), num_shadows_limit=(1, 3),
                       shadow_dimension=5, p=0.4),
        A.RandomFog(fog_coef_range=(0.05, 0.2), p=0.3),
        A.Downscale(scale_range=(0.5, 0.75),
                    interpolation_pair={"downscale": 0, "upscale": 2}, p=0.3),
        A.CoarseDropout(num_holes_range=(2, 8), hole_height_range=(32, 96),
                        hole_width_range=(32, 96), fill=0, p=0.4),
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD, max_pixel_value=255.0),
        ToTensorV2(),
    ])


def _make_test_transform():
    _ensure_torch()
    return A.Compose([
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD, max_pixel_value=255.0),
        ToTensorV2(),
    ], additional_targets={"mask": "mask"})


def compute_vis(rgb01, eps=1e-6):
    R, G, B = rgb01[..., 0], rgb01[..., 1], rgb01[..., 2]
    s = R + G + B + eps
    return np.stack([G / s, (G - R) / (G + R + eps), 2.0 * G - R - B],
                    axis=-1).astype(np.float32)


def _input_norm():
    mean = list(IMAGENET_MEAN) + (VI_MEAN if USE_VI else [])
    std  = list(IMAGENET_STD)  + (VI_STD  if USE_VI else [])
    return np.asarray(mean, np.float32), np.asarray(std, np.float32)


def rgb_to_model_input(rgb_uint8):
    rgb01 = rgb_uint8.astype(np.float32) / 255.0
    arr = np.concatenate([rgb01, compute_vis(rgb01)], -1) if USE_VI else rgb01
    mean, std = _input_norm()
    arr = (arr - mean) / std
    return np.ascontiguousarray(arr.transpose(2, 0, 1))


def _make_pixel_transform_nonorm():
    _ensure_torch()
    return A.Compose([
        A.OneOf([A.GaussianBlur(blur_limit=(3, 7), p=1.0),
                 A.MedianBlur(blur_limit=5, p=1.0)], p=0.5),
        A.RandomBrightnessContrast(0.3, 0.3, p=0.6),
        A.HueSaturationValue(15, 30, 15, p=0.5),
        A.RandomGamma(gamma_limit=(70, 130), p=0.4),
        A.RandomShadow(shadow_roi=(0, 0, 1, 1), num_shadows_limit=(1, 3),
                       shadow_dimension=5, p=0.4),
        A.RandomFog(fog_coef_range=(0.05, 0.2), p=0.3),
        A.Downscale(scale_range=(0.5, 0.75),
                    interpolation_pair={"downscale": 0, "upscale": 2}, p=0.3),
        A.CoarseDropout(num_holes_range=(2, 8), hole_height_range=(32, 96),
                        hole_width_range=(32, 96), fill=0, p=0.4),
    ])


class SemanticDataset:
    """Paired RGB + binary canopy mask tiles (identical contract to Phase 3)."""

    def __init__(self, df, training=True):
        self.df = df.reset_index(drop=True)
        self.training = training
        if training:
            self.spatial_tf = _make_spatial_transform()
            self.pixel_tf = (_make_pixel_transform_nonorm() if USE_VI
                             else _make_pixel_transform())
        else:
            self.test_tf = _make_test_transform()

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        _ensure_torch()
        row = self.df.iloc[idx]
        with rasterio.open(row["img_path"]) as src:
            img = src.read().transpose(1, 2, 0)
        with rasterio.open(row["mask_path"]) as src:
            mask = src.read(1).astype(np.float32)

        if self.training:
            out = self.spatial_tf(image=img, mask=mask)
            img, mask = out["image"], out["mask"]
            if USE_VI:
                img = self.pixel_tf(image=img)["image"]
                img = torch.from_numpy(rgb_to_model_input(img))
            else:
                img = self.pixel_tf(image=img)["image"]
            mask = torch.from_numpy(mask).unsqueeze(0).float()
        else:
            if USE_VI:
                img = torch.from_numpy(rgb_to_model_input(img))
                mask = torch.from_numpy(mask).unsqueeze(0).float()
            else:
                out = self.test_tf(image=img, mask=mask)
                img, mask = out["image"], out["mask"]
                mask = mask.unsqueeze(0).float() if mask.dim() == 2 else mask.float()

        meta = {"tile_name": row["tile_name"], "site": row["site"]}
        return img, mask, meta


def _inject_dropout(module, p):
    for _, child in module.named_children():
        if isinstance(child, nn.Sequential):
            child.add_module("dropout", nn.Dropout2d(p=p))
        else:
            _inject_dropout(child, p)


def build_model(device, compile_model=True):
    """U-Net with logits head (BCEWithLogitsLoss). Dropout injected to match P3."""
    _ensure_torch()
    model = smp.Unet(encoder_name=ENCODER, encoder_weights=None,
                     decoder_channels=DECODER_CHANNELS, in_channels=IN_CHANNELS,
                     classes=1, activation=None)
    _inject_dropout(model.decoder, DECODER_DROPOUT)
    model = model.to(device)
    if compile_model:
        try:
            model = torch.compile(model)
        except Exception as e:
            print(f"  (torch.compile disabled: {e})")
    return model


def load_state_into(model, ckpt_path, device):
    """Load a checkpoint's model_state into model (handles torch.compile wrap)."""
    ckpt = torch.load(ckpt_path, map_location=device)
    state = ckpt["model_state"]
    tgt = model._orig_mod if hasattr(model, "_orig_mod") else model
    tgt.load_state_dict(state, strict=False)
    return ckpt


def resolve_p3_ckpt(override=None):
    if override:
        p = Path(override)
        if p.exists():
            return p
        print(f"  WARNING: --ckpt {p} not found; falling back to default Phase 3 ckpt")
    for c in P3_CKPT_CANDIDATES:
        if c.exists():
            return c
    return None


# ── spatial buffer split (ported from Phase 3) ────────────────────────────────

def make_spatial_buffer_splits(df, n_folds=5, buffer_px=512, seed=42):
    from scipy.spatial.distance import cdist
    rng = np.random.RandomState(seed)
    sites = sorted(df["site"].unique())
    fold_assign = np.full(len(df), -1, dtype=int)
    for site in sites:
        idx = np.where(df["site"] == site)[0]
        for i, j in enumerate(rng.permutation(idx)):
            fold_assign[j] = i % n_folds
    folds = []
    for fold in range(n_folds):
        val_idx, tr_idx = [], []
        for site in sites:
            g = np.where(df["site"] == site)[0]
            v = g[fold_assign[g] == fold]
            o = g[fold_assign[g] != fold]
            if len(v) == 0:
                tr_idx.extend(o.tolist()); continue
            val_idx.extend(v.tolist())
            if len(o) == 0:
                continue
            d = cdist(df.iloc[o][["row_off", "col_off"]].values,
                      df.iloc[v][["row_off", "col_off"]].values, metric="chebyshev")
            md = d.min(axis=1)
            for i, j in enumerate(o):
                if md[i] >= buffer_px:
                    tr_idx.append(j)
        folds.append((np.array(tr_idx), np.array(val_idx)))
    return folds


def _masked_bce(criterion_none, logits, masks):
    """Mean BCE over labeled pixels only (mask value 255 = IGNORE is excluded).

    `criterion_none` is a BCEWithLogitsLoss with reduction='none'. For legacy
    masks (values only {0,1}) every pixel is valid, so this equals the plain
    mean BCE — bit-for-bit identical to the previous behaviour.
    """
    valid  = (masks != IGNORE_LABEL).float()
    target = torch.where(masks == IGNORE_LABEL, torch.zeros_like(masks), masks)
    loss_map = criterion_none(logits, target)
    return (loss_map * valid).sum() / valid.sum().clamp(min=1.0)


def _masked_dice(logits, masks, smooth=DICE_SMOOTH):
    """Soft-Dice loss over labeled pixels only (255 = IGNORE excluded).

    IGNORE-aware exactly like `_masked_bce`: both the prediction probabilities
    and the target are zeroed at IGNORE pixels, so those pixels contribute
    nothing to the intersection or the denominator. Computed per-sample over the
    batch then averaged. For legacy {0,1} masks the IGNORE mask is empty, so this
    is a plain soft-Dice. All-background tiles → near-zero loss unless the model
    predicts false canopy (penalised via the denominator).
    """
    valid  = (masks != IGNORE_LABEL).float()
    target = torch.where(masks == IGNORE_LABEL, torch.zeros_like(masks), masks) * valid
    probs  = torch.sigmoid(logits) * valid
    dims   = tuple(range(1, probs.dim()))
    inter  = (probs * target).sum(dims)
    denom  = probs.sum(dims) + target.sum(dims)
    dice   = (2.0 * inter + smooth) / (denom + smooth)
    return (1.0 - dice).mean()


def _seg_loss(criterion_none, logits, masks):
    """Combined masked segmentation loss: BCE_WEIGHT*BCE + DICE_WEIGHT*Dice.

    Returns (combined, bce_component, dice_component) — all IGNORE-aware.
    """
    bce  = _masked_bce(criterion_none, logits, masks)
    dice = _masked_dice(logits, masks)
    return BCE_WEIGHT * bce + DICE_WEIGHT * dice, bce, dice


def _compute_pos_weight(df, lo=POS_WEIGHT_MIN, hi=POS_WEIGHT_MAX):
    """BCE ``pos_weight`` = (#background labeled px) / (#canopy labeled px) over
    the given tiles' label rasters, excluding IGNORE (255). Clamped to [lo, hi]
    so a canopy-scarce split can't destabilise training. Returns a float; falls
    back to ``lo`` (no-op weighting) when the split holds no canopy pixels.
    """
    pos = neg = 0
    for mp in df["mask_path"]:
        with rasterio.open(mp) as src:
            m = src.read(1)
        pos += int((m == 1).sum())
        neg += int((m == 0).sum())
    if pos == 0:
        return float(lo)
    return float(min(max(neg / pos, lo), hi))


def _train_one_epoch(model, loader, optimizer, scaler, criterion, device):
    model.train()
    loss_sum = seg_sum = 0.0       # seg_sum tracks the combined BCE+Dice (no L1)
    n = 0
    for imgs, masks, _ in loader:
        imgs = imgs.to(device, non_blocking=True)
        masks = masks.to(device, non_blocking=True)
        optimizer.zero_grad()
        with torch.amp.autocast("cuda"):
            logits = model(imgs)
            seg, _bce, _dice = _seg_loss(criterion, logits, masks)
        if L1_LAMBDA > 0:
            l1 = sum(p.abs().sum() for p in model.parameters() if p.requires_grad)
            loss = seg + L1_LAMBDA * l1
        else:
            loss = seg
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        scaler.step(optimizer)
        scaler.update()
        loss_sum += loss.item(); seg_sum += seg.item(); n += 1
    return loss_sum / max(n, 1), seg_sum / max(n, 1)


def _validate(model, loader, criterion, device):
    model.eval()
    seg_sum = iou_sum = 0.0        # seg_sum = combined BCE+Dice (early-stop signal)
    n = 0
    with torch.no_grad():
        for imgs, masks, _ in loader:
            imgs = imgs.to(device, non_blocking=True)
            masks = masks.to(device, non_blocking=True)
            with torch.amp.autocast("cuda"):
                logits = model(imgs)
                seg, _bce, _dice = _seg_loss(criterion, logits, masks)
            seg_sum += seg.item()
            # val_iou: unchanged — thresholded IoU at 0.5 for cross-run comparability.
            valid = (masks != IGNORE_LABEL).float()
            preds = (torch.sigmoid(logits) > 0.5).float() * valid
            tgt   = (masks == 1).float() * valid
            inter = (preds * tgt).sum()
            union = preds.sum() + tgt.sum() - inter
            iou_sum += (inter / (union + 1e-8)).item(); n += 1
    return seg_sum / max(n, 1), iou_sum / max(n, 1)


def _save_ckpt(phase, epoch, model, optim, sched, history, best_val, path):
    state = (model._orig_mod.state_dict() if hasattr(model, "_orig_mod")
             else model.state_dict())
    torch.save({"phase": phase, "epoch": epoch, "model_state": state,
                "optim_state": optim.state_dict(), "sched_state": sched.state_dict(),
                "history": history, "best_val": best_val}, path)


def _freeze_encoder(model):
    enc = model._orig_mod.encoder if hasattr(model, "_orig_mod") else model.encoder
    for p in enc.parameters():
        p.requires_grad = False


def _unfreeze_encoder(model):
    enc = model._orig_mod.encoder if hasattr(model, "_orig_mod") else model.encoder
    for p in enc.parameters():
        p.requires_grad = True


# ══════════════════════════════════════════════════════════════════════════════
#  Step 3 — Per-year fine-tune (Phase A frozen + Phase B full, from P3 ckpt)
# ══════════════════════════════════════════════════════════════════════════════

def step_train(label, batch_size=BATCH_SIZE, p3_ckpt=None, dry_run=False):
    _ensure_torch()
    entry = entry_for(label)
    tier  = tier_of(entry["gsd_cm"])
    print(f"\n── [{label}] Step 3: Fine-tune ({tier}) ──")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Device: {device}"
          + (f"  GPU: {torch.cuda.get_device_name(0)}" if device.type == "cuda" else ""))

    index_path = TILE_DIR / label / f"tile_index_{label}.csv"
    if not index_path.exists():
        print(f"  ERROR: {index_path} not found — run step tile first")
        return
    idx_df = pd.read_csv(index_path)
    train_df = idx_df[idx_df["split"] == "train"].reset_index(drop=True)
    test_df  = idx_df[idx_df["split"] == "test"].reset_index(drop=True)
    print(f"  Train tiles: {len(train_df)}  |  held-out test: {len(test_df)}")
    if len(train_df) == 0:
        print("  ERROR: no training tiles — skipping.")
        return
    if dry_run:
        print("  Dry run — not training")
        return

    # Train/val split for early stopping.
    #  • fine tier: tiles are non-overlapping (stride == TILE_SIZE), so the
    #    fixed-pixel spatial-buffer split gives clean separation (matches Phase 3).
    #  • medium/coarse: tiles OVERLAP (stride < TILE_SIZE) and sites are small,
    #    so a fixed 512px Chebyshev buffer prunes the entire training set (it did
    #    for 2000: train=0). Honest spatial CV isn't achievable at these GSDs —
    #    use a random split for early stopping only; the reported coarse metric
    #    is the in-sample IoU in step_evaluate, and Phase 6 cross-checks against
    #    2020 detections.
    tier_stride = TIER_TILE_PARAMS[tier]["stride"]
    ftr = fva = None

    # Fix 4: if a geographically-blocked val split was carved at tiling time
    # (coarse city-wide), use it directly — it is already >520 m from train, so
    # no random/neighbour val tiles are needed. Replaces the leaked random-15%
    # fallback for that path.
    val_df = idx_df[idx_df["split"] == "val"].reset_index(drop=True)
    if len(val_df) > 0:
        ftr = train_df.reset_index(drop=True)
        fva = val_df.reset_index(drop=True)
        print(f"  Val split: BLOCKED hold-out from tile index ({len(fva)} tiles)")

    if ftr is None and tier_stride >= TILE_SIZE and train_df["site"].nunique() > 1 and len(train_df) >= 25:
        folds = make_spatial_buffer_splits(
            train_df, n_folds=5, buffer_px=SPATIAL_BUFFER_PX, seed=42)
        tr_idx, val_idx = folds[0]
        if len(tr_idx) > 0 and len(val_idx) > 0:
            ftr = train_df.iloc[tr_idx].reset_index(drop=True)
            fva = train_df.iloc[val_idx].reset_index(drop=True)
        else:
            print("  (spatial-buffer split left an empty side — random split)")

    if ftr is None:
        if len(train_df) >= 7:
            # Stratify by site only when every site has ≥2 tiles (else sklearn errors).
            strat = (train_df["site"]
                     if train_df["site"].nunique() > 1
                     and train_df["site"].value_counts().min() >= 2 else None)
            ftr, fva = train_test_split(train_df, test_size=0.15,
                                        random_state=RANDOM_SEED, stratify=strat)
            ftr = ftr.reset_index(drop=True); fva = fva.reset_index(drop=True)
        else:
            # Too few tiles to hold any out — validate on the training set.
            ftr = train_df.copy(); fva = train_df.copy()

    print(f"  Train split: {len(ftr)}  |  Val split: {len(fva)}")
    if len(fva) == 0:           # degenerate — validate on train
        fva = ftr.copy()
    if len(ftr) == 0:
        print("  ERROR: no training tiles after split — skipping.")
        return

    pin = device.type == "cuda"
    counts = ftr["site"].value_counts().to_dict()
    weights = ftr["site"].map(lambda s: 1.0 / counts[s]).values.astype(np.float32)
    sampler = WeightedRandomSampler(torch.from_numpy(weights),
                                    num_samples=len(ftr), replacement=True)
    nw = min(NUM_WORKERS, max(2, len(ftr)))
    train_loader = DataLoader(SemanticDataset(ftr, True), batch_size=batch_size,
                              sampler=sampler, num_workers=nw, pin_memory=pin,
                              drop_last=len(ftr) >= batch_size,
                              persistent_workers=True, prefetch_factor=4)
    val_loader = DataLoader(SemanticDataset(fva, False), batch_size=batch_size,
                            shuffle=False, num_workers=nw, pin_memory=pin,
                            drop_last=False, persistent_workers=True, prefetch_factor=4)

    # Fine-tune START = Phase 3 2020 semantic checkpoint (every year, independently).
    p3 = resolve_p3_ckpt(p3_ckpt)
    if p3 is None:
        print("  ERROR: Phase 3 checkpoint (sem_best_2020.pt) not found — "
              "run Phase 3 first or pass --ckpt.")
        return
    model = build_model(device, compile_model=True)
    ck = load_state_into(model, p3, device)
    print(f"  ✓ Fine-tune start: {Path(p3).name}  "
          f"(P3 val_bce={ck.get('best_val', '?')})")

    # pos_weight for class imbalance (Fix 2): coarse + medium tiers only; fine
    # tier keeps 1.0 (None). Computed from the actual training split (ftr) so the
    # held-out val tiles don't leak into the statistic.
    pos_weight_t = None
    if tier in ("coarse", "medium"):
        pw = _compute_pos_weight(ftr)
        print(f"  pos_weight ({tier}): {pw:.3f}  "
              f"(clamped to [{POS_WEIGHT_MIN}, {POS_WEIGHT_MAX}])")
        pos_weight_t = torch.tensor([pw], device=device)
    else:
        print(f"  pos_weight (fine): 1.0 (disabled)")
    criterion = nn.BCEWithLogitsLoss(reduction="none", pos_weight=pos_weight_t)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    best_ckpt   = MODELS_DIR / f"sem_best_{label}.pt"
    latest_ckpt = MODELS_DIR / f"sem_latest_{label}.pt"
    best_val = float("inf")
    history = {"phase": [], "epoch": [], "train_bce": [], "val_bce": [], "val_iou": []}

    # ── Phase A: frozen encoder ──
    print(f"\n  PHASE A — frozen encoder | {EPOCHS_PHASE_A} ep | LR={LR_PHASE_A}")
    _freeze_encoder(model)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=LR_PHASE_A, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
        opt, mode="min", factor=0.5, patience=5, threshold=1e-4,
        cooldown=2, min_lr=1e-7)
    scaler = torch.amp.GradScaler("cuda")
    es = 0
    for ep in range(EPOCHS_PHASE_A):
        t0 = time.time()
        _, tr_bce = _train_one_epoch(model, train_loader, opt, scaler, criterion, device)
        v_bce, v_iou = _validate(model, val_loader, criterion, device)
        sched.step(v_bce)
        history["phase"].append("A"); history["epoch"].append(ep + 1)
        history["train_bce"].append(tr_bce); history["val_bce"].append(v_bce)
        history["val_iou"].append(v_iou)
        best = v_bce < best_val
        if best:
            best_val = v_bce; es = 0
            _save_ckpt("A", ep, model, opt, sched, history, best_val, best_ckpt)
        else:
            es += 1
        if (ep + 1) % SAVE_EVERY == 0 or ep == EPOCHS_PHASE_A - 1:
            _save_ckpt("A", ep, model, opt, sched, history, best_val, latest_ckpt)
        print(f"  A E{ep+1:>3}/{EPOCHS_PHASE_A} tr_bce={tr_bce:.4f} "
              f"val_bce={v_bce:.4f} val_iou={v_iou:.4f} "
              f"lr={opt.param_groups[0]['lr']:.2e} {time.time()-t0:.0f}s"
              f"{' ★' if best else f'  [{es}/{EARLY_STOP_PAT}]'}")
        if es >= EARLY_STOP_PAT:
            print("  Early stop — Phase A"); break
    print(f"  ✓ Phase A best val BCE: {best_val:.4f}")

    # ── Phase B: full model ──
    print(f"\n  PHASE B — full model | {EPOCHS_PHASE_B} ep | LR={LR_PHASE_B}")
    _unfreeze_encoder(model)
    opt = torch.optim.AdamW(model.parameters(), lr=LR_PHASE_B, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
        opt, mode="min", factor=0.5, patience=5, threshold=1e-4,
        cooldown=2, min_lr=1e-7)
    scaler = torch.amp.GradScaler("cuda")
    es = 0
    for ep in range(EPOCHS_PHASE_B):
        t0 = time.time()
        _, tr_bce = _train_one_epoch(model, train_loader, opt, scaler, criterion, device)
        v_bce, v_iou = _validate(model, val_loader, criterion, device)
        sched.step(v_bce)
        history["phase"].append("B"); history["epoch"].append(ep + 1)
        history["train_bce"].append(tr_bce); history["val_bce"].append(v_bce)
        history["val_iou"].append(v_iou)
        best = v_bce < best_val
        if best:
            best_val = v_bce; es = 0
            _save_ckpt("B", ep, model, opt, sched, history, best_val, best_ckpt)
        else:
            es += 1
        if (ep + 1) % SAVE_EVERY == 0 or ep == EPOCHS_PHASE_B - 1:
            _save_ckpt("B", ep, model, opt, sched, history, best_val, latest_ckpt)
        print(f"  B E{ep+1:>3}/{EPOCHS_PHASE_B} tr_bce={tr_bce:.4f} "
              f"val_bce={v_bce:.4f} val_iou={v_iou:.4f} "
              f"lr={opt.param_groups[0]['lr']:.2e} {time.time()-t0:.0f}s"
              f"{' ★' if best else f'  [{es}/{EARLY_STOP_PAT}]'}")
        if es >= EARLY_STOP_PAT:
            print("  Early stop — Phase B"); break

    print(f"  ✓ Phase B best val BCE: {best_val:.4f}  → {best_ckpt.name}")
    pd.DataFrame(history).to_csv(MODELS_DIR / f"sem_loss_history_{label}.csv",
                                 index=False)
    del model, opt, scaler
    if device.type == "cuda":
        torch.cuda.empty_cache()
    gc.collect()


# ══════════════════════════════════════════════════════════════════════════════
#  Step 4 — Per-year evaluation (pixel accuracy, IoU, Dice vs projected labels)
# ══════════════════════════════════════════════════════════════════════════════

def _metrics(tp, fp, fn, tn):
    total = tp + fp + fn + tn
    acc  = (tp + tn) / total if total else 0
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec  = tp / (tp + fn) if (tp + fn) else 0
    f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
    iou  = tp / (tp + fp + fn) if (tp + fp + fn) else 0
    dice = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0
    return dict(accuracy=round(acc, 4), precision=round(prec, 4),
                recall=round(rec, 4), f1=round(f1, 4), iou=round(iou, 4),
                dice=round(dice, 4), tp=tp, fp=fp, fn=fn, tn=tn)


# Cap on pooled pixels for the threshold-independent metrics (memory guard for
# fine years with many tiles). 40M float32+int8 ≈ 200 MB — comfortable.
TI_MAX_PIXELS = 40_000_000


def _threshold_independent_metrics(all_prob, all_gt, f1_at_default):
    """
    Pooled AUROC / average precision / log-loss / best-F1 threshold over all eval
    pixels. Judges the probability RANKING independent of the 0.5 cutoff — the key
    diagnostic for coarse years whose probabilities pile up near 0.5. Returns {} if
    sklearn is missing, a class is absent, or the pixel pool is degenerate.
    """
    if not all_prob:
        return {}
    try:
        import sklearn.metrics as skm
        y_prob = np.concatenate(all_prob)
        y_true = np.concatenate(all_gt).astype(np.int8)
        # Memory guard: subsample if the pool is very large.
        n = y_true.shape[0]
        if n > TI_MAX_PIXELS:
            rng = np.random.default_rng(42)
            sel = rng.choice(n, size=TI_MAX_PIXELS, replace=False)
            y_prob = y_prob[sel]
            y_true = y_true[sel]
        # AUROC / AP need both classes present.
        if y_true.min() == y_true.max():
            return {}
        ti = {
            "auroc":    float(skm.roc_auc_score(y_true, y_prob)),
            "ap":       float(skm.average_precision_score(y_true, y_prob)),
            "log_loss": float(skm.log_loss(y_true, y_prob, labels=[0, 1])),
        }
        prec_c, rec_c, thr_c = skm.precision_recall_curve(y_true, y_prob)
        f1_c = 2 * prec_c * rec_c / (prec_c + rec_c + 1e-12)
        bi = int(np.argmax(f1_c[:-1])) if len(thr_c) else 0
        ti["best_f1"]        = float(f1_c[bi])
        ti["best_f1_thresh"] = float(thr_c[bi]) if len(thr_c) else CANOPY_PROB_THRESHOLD
        return ti
    except Exception as e:
        print(f"  WARNING: threshold-independent metrics failed ({e})")
        return {}


def step_evaluate(label, dry_run=False):
    _ensure_torch()
    entry = entry_for(label)
    tier  = tier_of(entry["gsd_cm"])
    has_test = TIER_TILE_PARAMS[tier]["has_test"]
    print(f"\n── [{label}] Step 4: Evaluation ({tier}) ──")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    index_path = TILE_DIR / label / f"tile_index_{label}.csv"
    if not index_path.exists():
        print(f"  ERROR: {index_path} not found — run step tile first"); return
    idx_df = pd.read_csv(index_path)
    eval_df = idx_df[idx_df["split"] == "test"].reset_index(drop=True)
    eval_scope = "held-out test"
    if len(eval_df) == 0:
        # Coarse years have no held-out test → evaluate in-sample (DG4 number).
        eval_df = idx_df.reset_index(drop=True)
        eval_scope = "IN-SAMPLE (no held-out test at this GSD)"
    print(f"  Eval tiles: {len(eval_df)}  [{eval_scope}]")
    if dry_run or len(eval_df) == 0:
        if len(eval_df) == 0:
            print("  No tiles to evaluate."); 
        return

    ckpt = MODELS_DIR / f"sem_best_{label}.pt"
    if not ckpt.exists():
        print(f"  ERROR: {ckpt} not found — run step train first"); return
    model = build_model(device, compile_model=False)
    ck = load_state_into(model, ckpt, device)
    model.eval()
    print(f"  Model: {ckpt.name}  (phase={ck.get('phase','?')} "
          f"val_bce={ck.get('best_val','?')})")

    eval_tf = A.Compose([A.Normalize(IMAGENET_MEAN, IMAGENET_STD, max_pixel_value=255.0),
                         ToTensorV2()])
    tp = fp = fn = tn = 0
    site_cm = {}
    all_prob, all_gt = [], []   # pooled pixels for threshold-independent metrics
    with torch.no_grad():
        for _, row in tqdm(eval_df.iterrows(), total=len(eval_df), desc="  Eval"):
            with rasterio.open(row["img_path"]) as src:
                img = src.read().transpose(1, 2, 0)
            with rasterio.open(row["mask_path"]) as src:
                gt = src.read(1).astype(np.float32)
            if USE_VI:
                inp = torch.from_numpy(rgb_to_model_input(img)).unsqueeze(0).to(device)
            else:
                inp = eval_tf(image=img)["image"].unsqueeze(0).to(device)
            prob = 1.0 / (1.0 + np.exp(-model(inp).squeeze().cpu().numpy()))
            pred = (prob > CANOPY_PROB_THRESHOLD).astype(np.uint8)
            valid = gt != IGNORE_LABEL    # drop unreviewed/nodata pixels
            all_prob.append(prob[valid].ravel().astype(np.float32))
            all_gt.append(gt[valid].ravel().astype(np.int8))
            a = int(((pred == 1) & (gt == 1)).sum()); tp += a
            b = int(((pred == 1) & (gt == 0)).sum()); fp += b
            c = int(((pred == 0) & (gt == 1)).sum()); fn += c
            d = int(((pred == 0) & (gt == 0)).sum()); tn += d
            s = row["site"]
            sm = site_cm.setdefault(s, [0, 0, 0, 0])
            sm[0] += a; sm[1] += b; sm[2] += c; sm[3] += d

    overall = _metrics(tp, fp, fn, tn)

    # ── Threshold-independent metrics (pooled over all eval pixels) ───────────
    # These judge the model's probability RANKING, independent of the 0.5 cutoff —
    # critical for coarse years where the distribution piles up near 0.5 and the
    # fixed threshold is brutally sensitive. best_f1_thresh is the per-year
    # operating point to use instead of 0.5.
    ti = _threshold_independent_metrics(all_prob, all_gt, overall["f1"])
    del all_prob, all_gt

    print(f"  {'-'*52}")
    print(f"  IoU={overall['iou']:.4f}  Dice={overall['dice']:.4f}  "
          f"Acc={overall['accuracy']:.4f}  Prec={overall['precision']:.4f}  "
          f"Rec={overall['recall']:.4f}")
    if ti:
        print(f"  AUROC={ti['auroc']:.4f}  AP={ti['ap']:.4f}  "
              f"LogLoss={ti['log_loss']:.4f}")
        print(f"  Best-F1 @ thresh {ti['best_f1_thresh']:.3f}  "
              f"(F1={ti['best_f1']:.4f}  vs  {overall['f1']:.4f} @ {CANOPY_PROB_THRESHOLD:.2f})")

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for s in sorted(site_cm):
        m = _metrics(*site_cm[s])
        rows.append(dict(year=label, gsd_cm=entry["gsd_cm"], tier=tier,
                         eval_scope=eval_scope, scope="site", site=s, **m))
    overall_row = dict(year=label, gsd_cm=entry["gsd_cm"], tier=tier,
                       eval_scope=eval_scope, scope="OVERALL", site="ALL", **overall)
    overall_row.update(ti)   # auroc, ap, log_loss, best_f1, best_f1_thresh (if available)
    rows.append(overall_row)
    new = pd.DataFrame(rows)

    # Append/replace this year's rows in the cumulative report.
    if EVAL_CSV.exists():
        old = pd.read_csv(EVAL_CSV)
        old = old[old["year"].astype(str) != label]
        new = pd.concat([old, new], ignore_index=True)
    new.to_csv(EVAL_CSV, index=False)
    print(f"  ✓ Eval rows written → {EVAL_CSV.name}")

    if tier == "coarse":
        bf = f", best-F1 thresh={ti['best_f1_thresh']:.3f}" if ti else ""
        au = f", AUROC={ti['auroc']:.3f}" if ti else ""
        # Fix 4: coarse city-wide years now carry a blocked held-out test block,
        # so this is out-of-sample; legacy 6-site / degraded years stay in-sample.
        scope_txt = ("out-of-sample" if eval_scope == "held-out test"
                     else "in-sample")
        print(f"  ◆ DG2 note: {label} coarse-year IoU={overall['iou']:.3f} "
              f"({scope_txt}){au}{bf}.")
        if ti:
            print(f"    AUROC measures ranking independent of the 0.5 cutoff — use it "
                  f"(not in-sample IoU) to judge whether the year is usable; apply "
                  f"best-F1 thresh as the per-year operating point. Confirm with "
                  f"random-point photo-interpretation before DG2 include/exclude.")
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()


# ══════════════════════════════════════════════════════════════════════════════
#  Step 5 — Full-city native inference → probability raster
# ══════════════════════════════════════════════════════════════════════════════

def step_inference(label, batch_size=INFER_BATCH_SIZE, dry_run=False):
    _ensure_torch()
    entry = entry_for(label)
    print(f"\n── [{label}] Step 5: Full-city native inference ──")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    native = resolve_native_path(entry)
    if not native.exists():
        print(f"  ERROR: native ortho not found: {native}"); return
    ckpt = MODELS_DIR / f"sem_best_{label}.pt"
    if not ckpt.exists():
        print(f"  ERROR: {ckpt} not found — run step train first"); return

    MASKS_DIR.mkdir(parents=True, exist_ok=True)
    prob_out = MASKS_DIR / f"edmonds_canopy_prob_{label}.tif"

    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()

    local = native if dry_run else _stage_imagery_local(native)
    with rasterio.open(local) as src:
        img_h, img_w = src.height, src.width
        img_crs, img_tf = src.crs, src.transform
        src_nodata = src.nodata
        px = src.transform.a; py = abs(src.transform.e)
    print(f"  Ortho: {img_w}×{img_h}px  ({img_w*px/1000:.1f}×{img_h*py/1000:.1f} km)"
          f"  GSD≈{px*100:.1f}cm  nodata={src_nodata}")
    if dry_run:
        print("  Dry run — not running inference")
        _unstage_imagery_local(local) if local != native else None
        return

    model = build_model(device, compile_model=False)
    ck = load_state_into(model, ckpt, device)
    model.eval()
    print(f"  Model: {ckpt.name}  (val_bce={ck.get('best_val','?')})")

    tf = A.Compose([A.Normalize(IMAGENET_MEAN, IMAGENET_STD, max_pixel_value=255.0),
                    ToTensorV2()])
    stride, pad, cc = INFER_STRIDE, INFER_PAD, INFER_STRIDE

    origins = [(r, c) for r in range(0, img_h, stride) for c in range(0, img_w, stride)]
    if origins[-1][0] + stride < img_h:
        origins += [(img_h - TILE_SIZE, c) for c in range(0, img_w, stride)]
    if origins[-1][1] + stride < img_w:
        origins += [(r, img_w - TILE_SIZE) for r in range(0, img_h, stride)]
    origins.append((img_h - TILE_SIZE, img_w - TILE_SIZE))
    origins = sorted(set(origins))
    print(f"  Tile positions: {len(origins):,}  |  batch={batch_size}")

    # uint8 prob raster; 255 reserved as a nodata sentinel (blanks un-imaged areas
    # of partial-coverage years). Real probabilities clipped to 0–254.
    prob_profile = {"driver": "GTiff", "dtype": "uint8", "width": img_w,
                    "height": img_h, "count": 1, "crs": img_crs, "transform": img_tf,
                    "compress": "lzw", "BIGTIFF": "YES", "nodata": PROB_NODATA}

    batch_imgs, batch_meta = [], []

    def flush(dst):
        if not batch_imgs:
            return
        inp = torch.stack(batch_imgs).to(device)
        with torch.no_grad():
            logits = model(inp).squeeze(1).cpu().numpy()
        probs = 1.0 / (1.0 + np.exp(-logits))
        for k, (ro, co, valid) in enumerate(batch_meta):
            center = probs[k, pad:pad+cc, pad:pad+cc]
            cr_end = min(ro + cc, img_h); cc_end = min(co + cc, img_w)
            ch, cw = cr_end - ro, cc_end - co
            crop = (center[:ch, :cw] * 254.0).round().clip(0, 254).astype(np.uint8)
            if valid is not None:                       # blank no-data pixels
                crop[~valid[:ch, :cw]] = PROB_NODATA
            win = rasterio.windows.Window(co, ro, cw, ch)
            dst.write(crop[np.newaxis], window=win)

    tick("inference")
    with rasterio.open(prob_out, "w", **prob_profile) as dst:
        with rasterio.open(local) as src:
            pbar = tqdm(total=len(origins), desc="  Inference", unit="tile",
                        miniters=2000, mininterval=2.0)
            for ro, co in origins:
                r0, c0 = ro - pad, co - pad
                r1, c1 = r0 + TILE_SIZE, c0 + TILE_SIZE
                rr0, cc0 = max(0, r0), max(0, c0)
                rr1, cc1 = min(img_h, r1), min(img_w, c1)
                win = rasterio.windows.Window(cc0, rr0, cc1 - cc0, rr1 - rr0)
                tile = read_rgb_window(src, win).transpose(1, 2, 0)
                pt, pb = rr0 - r0, r1 - rr1
                pl, pr = cc0 - c0, c1 - cc1
                if any([pt, pb, pl, pr]):
                    tile = np.pad(tile, ((pt, pb), (pl, pr), (0, 0)), mode="reflect")

                # Validity for the center crop (skip-write for un-imaged pixels).
                center_rgb = tile[pad:pad+cc, pad:pad+cc, :]
                if src_nodata is not None:
                    valid = ~np.all(center_rgb == src_nodata, axis=-1)
                else:
                    valid = ~np.all(center_rgb == 0, axis=-1)
                if valid.all():
                    valid = None  # full-coverage tile, skip the masking work

                batch_imgs.append(tf(image=tile)["image"] if not USE_VI
                                  else torch.from_numpy(rgb_to_model_input(tile)))
                batch_meta.append((ro, co, valid))
                if len(batch_imgs) == batch_size:
                    flush(dst); batch_imgs.clear(); batch_meta.clear()
                pbar.update(1)
            pbar.close()
            flush(dst)
    tock("inference")
    print(f"  ✓ Probability raster: {prob_out.name} "
          f"({prob_out.stat().st_size/1e6:.0f} MB)")

    if local != native:
        _unstage_imagery_local(local)
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()


# ══════════════════════════════════════════════════════════════════════════════
#  Step 6 — Post-processing (threshold → morphology → polygonize)
# ══════════════════════════════════════════════════════════════════════════════

def _operating_threshold(label):
    """Per-year canopy probability operating threshold for post-processing.

    Reads ``best_f1_thresh`` for this year's OVERALL row from
    ``semantic_eval_report.csv`` (written by step_evaluate) and returns it as the
    binarisation threshold; falls back to CANOPY_PROB_THRESHOLD (0.5) if the
    report, the row, or the column is missing / NaN / out of (0,1).

    Returns (threshold_float, source_str).

    NOTE: step_evaluate currently computes best_f1_thresh IN-SAMPLE for coarse
    years (no held-out test), so it is an optimistic operating point. Once
    Fix 3/4 land a real held-out test block, this threshold should be recomputed
    on that out-of-sample data before it is trusted for the final masks.
    """
    if EVAL_CSV.exists():
        try:
            df = pd.read_csv(EVAL_CSV)
            sub = df[(df["year"].astype(str) == str(label)) &
                     (df["scope"] == "OVERALL")]
            if len(sub) and "best_f1_thresh" in sub.columns:
                val = pd.to_numeric(sub.iloc[0]["best_f1_thresh"], errors="coerce")
                if pd.notna(val) and 0.0 < float(val) < 1.0:
                    return float(val), "best_f1_thresh (semantic_eval_report.csv)"
        except Exception as e:
            print(f"  (could not read best_f1_thresh: {e}; "
                  f"using default {CANOPY_PROB_THRESHOLD})")
    return CANOPY_PROB_THRESHOLD, "default 0.5"


def step_postproc(label, dry_run=False):
    from scipy.ndimage import binary_opening, binary_closing
    print(f"\n── [{label}] Step 6: Post-processing ──")

    prob_out = MASKS_DIR / f"edmonds_canopy_prob_{label}.tif"
    mask_out = MASKS_DIR / f"edmonds_canopy_mask_{label}.tif"
    gpkg_out = MASKS_DIR / f"edmonds_canopy_mask_{label}.gpkg"
    if not prob_out.exists():
        print(f"  ERROR: {prob_out} not found — run inference first"); return

    with rasterio.open(prob_out) as src:
        img_h, img_w = src.height, src.width
        img_crs, img_tf = src.crs, src.transform
        px, py = src.transform.a, abs(src.transform.e)
    pixel_area = px * py
    min_px = int(np.ceil(MIN_CANOPY_PATCH / pixel_area))
    # Per-year operating threshold from step_evaluate (best-F1), not the fixed 0.5.
    thr, thr_src = _operating_threshold(label)
    thr_u8 = int(round(thr * 254))
    print(f"  threshold={thr:.3f} [{thr_src}] (u8≥{thr_u8})  "
          f"min_patch={MIN_CANOPY_PATCH}m²({min_px}px)  "
          f"morph={MORPH_KERNEL_SIZE}×{MORPH_KERNEL_SIZE}")
    if dry_run:
        print("  Dry run — not processing"); return

    tick("postproc")
    CHUNK = 4096
    kernel = np.ones((MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE), dtype=bool)
    mask_profile = {"driver": "GTiff", "dtype": "uint8", "width": img_w,
                    "height": img_h, "count": 1, "crs": img_crs, "transform": img_tf,
                    "compress": "lzw", "nodata": 255, "BIGTIFF": "YES"}
    canopy_px = valid_px = 0
    with rasterio.open(prob_out) as src, rasterio.open(mask_out, "w", **mask_profile) as dst:
        for r0 in tqdm(range(0, img_h, CHUNK), desc="  Threshold"):
            r1 = min(r0 + CHUNK, img_h)
            win = rasterio.windows.Window(0, r0, img_w, r1 - r0)
            prob = src.read(1, window=win)
            nod = prob == PROB_NODATA
            m = ((~nod) & (prob >= thr_u8)).astype(np.uint8)
            m = binary_opening(m, structure=kernel).astype(np.uint8)
            m = binary_closing(m, structure=kernel).astype(np.uint8)
            m[nod] = 255                       # carry no-data through to the mask
            canopy_px += int((m == 1).sum())
            valid_px  += int((~nod).sum())
            dst.write(m[np.newaxis], window=win)

    canopy_area = canopy_px * pixel_area
    pct = 100 * canopy_px / valid_px if valid_px else 0
    print(f"  ✓ Mask: {mask_out.name} ({mask_out.stat().st_size/1e6:.0f} MB)")
    print(f"  Canopy: {canopy_px:,}px = {canopy_area/1e4:.1f} ha "
          f"({pct:.1f}% of imaged area)")

    # ── Polygonize (sieve small components, simplify staircase) ──
    print("  Polygonizing…"); tick("polygonize")
    import fiona
    schema = {"geometry": "Polygon",
              "properties": {"canopy_id": "str", "area_m2": "float"}}
    with rasterio.open(mask_out) as src:
        data = src.read(1)
    clean = rasterio.features.sieve(np.where(data == 1, 1, 0).astype(np.uint8),
                                    size=min_px, connectivity=POLYGON_CONNECTIVITY)
    del data; gc.collect()
    shapes_gen = rasterio.features.shapes(clean, mask=(clean == 1), transform=img_tf,
                                          connectivity=POLYGON_CONNECTIVITY)
    n = 0
    with fiona.open(gpkg_out, "w", driver="GPKG", crs=img_crs.to_wkt(),
                    schema=schema) as dst:
        for geom, _ in tqdm(shapes_gen, desc="  Polygonize", mininterval=5.0):
            poly = shape(geom)
            if SIMPLIFY_TOLERANCE_M > 0:
                poly = poly.simplify(SIMPLIFY_TOLERANCE_M, preserve_topology=True)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            parts = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
            for part in parts:
                if part.area < MIN_CANOPY_PATCH:
                    continue
                dst.write({"geometry": mapping(part),
                           "properties": {"canopy_id": f"CAN_{label}_{n:07d}",
                                          "area_m2": round(part.area, 2)}})
                n += 1
    tock("polygonize")
    print(f"  ✓ Canopy GeoPackage: {gpkg_out.name}  ({n:,} polygons)")

    # Record a one-line area summary for the cross-year consistency step.
    _append_area_summary(label, entry_for(label), canopy_area, pct, valid_px,
                         pixel_area)
    tock("postproc")


def _append_area_summary(label, entry, canopy_area_m2, canopy_pct, valid_px,
                         pixel_area):
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    row = dict(year=label, gsd_cm=entry["gsd_cm"], tier=tier_of(entry["gsd_cm"]),
               coverage=entry["coverage"],
               canopy_ha=round(canopy_area_m2 / 1e4, 2),
               canopy_pct_of_imaged=round(canopy_pct, 2),
               imaged_ha=round(valid_px * pixel_area / 1e4, 2))
    path = EVAL_DIR / "_per_year_canopy_area.csv"
    if path.exists():
        df = pd.read_csv(path)
        df = df[df["year"].astype(str) != label]
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(path, index=False)


# ══════════════════════════════════════════════════════════════════════════════
#  Cross-year consistency (run once after all years)
# ══════════════════════════════════════════════════════════════════════════════

def _year_sort_key(label):
    """Sort chronologically; suffixed keys (2019n, 2021s) sit beside their year."""
    digits = "".join(ch for ch in str(label) if ch.isdigit())
    base = int(digits) if digits else 0
    suffix = "".join(ch for ch in str(label) if ch.isalpha())
    return (base, suffix)


def step_consistency(dry_run=False):
    print("\n── Cross-year consistency check ──")
    area_path = EVAL_DIR / "_per_year_canopy_area.csv"
    if not area_path.exists():
        print(f"  No per-year area summaries yet ({area_path.name}). "
              f"Run inference+postproc first."); return
    df = pd.read_csv(area_path)
    if df.empty:
        print("  No rows."); return

    # Full-coverage years only for the trend (partial-coverage 67% years aren't
    # directly comparable in absolute hectares).
    df["_full"] = df["coverage"].astype(str).str.lower().eq("full")
    df = df.sort_values(by="year", key=lambda s: s.map(_year_sort_key)).reset_index(drop=True)

    full = df[df["_full"]].reset_index(drop=True)
    # Median canopy across full-coverage years; flag years deviating > ±40%.
    flags = []
    if len(full) >= 3:
        med = float(np.median(full["canopy_ha"]))
        for _, r in full.iterrows():
            dev = (r["canopy_ha"] - med) / med if med else 0
            flag = ""
            if abs(dev) > 0.40:
                flag = "HIGH" if dev > 0 else "LOW"
            flags.append((r["year"], r["canopy_ha"], round(dev * 100, 1), flag))
        print(f"  Median full-coverage canopy: {med:.1f} ha")
        print(f"  {'Year':<8}{'Canopy ha':>11}{'Δ vs median':>13}  flag")
        print(f"  {'-'*8}{'-'*11}{'-'*13}  ----")
        for y, ha, dev, flag in flags:
            print(f"  {str(y):<8}{ha:>11.1f}{dev:>12.1f}%  {flag}")
    else:
        print("  <3 full-coverage years processed — trend check deferred.")

    if dry_run:
        return
    out = df.drop(columns=["_full"]).copy()
    if flags:
        fmap = {str(y): f for y, _, _, f in flags}
        dmap = {str(y): d for y, _, d, _ in flags}
        out["pct_dev_from_median"] = out["year"].astype(str).map(dmap)
        out["anomaly_flag"] = out["year"].astype(str).map(fmap).fillna("")
    out.to_csv(CONSISTENCY_CSV, index=False)
    print(f"  ✓ {CONSISTENCY_CSV.name}")
    print("  Note: large deviations may reflect real canopy change, seasonal/"
          "phenology differences, or model issues — confirm visually before "
          "trusting the trend (Method Pipeline 'Temporal Validity Check').")


# ══════════════════════════════════════════════════════════════════════════════
#  Summary + main
# ══════════════════════════════════════════════════════════════════════════════

PER_YEAR_STEPS = ["labels", "tile", "train", "evaluate", "inference", "postproc"]
ALL_STEPS = PER_YEAR_STEPS + ["consistency"]


def _resolve_years(args):
    if args.year:
        labels = [y.strip() for y in args.year.split(",") if y.strip()]
        for lab in labels:
            entry_for(lab)  # validate
        if ANCHOR_LABEL in labels:
            print(f"  (note: {ANCHOR_LABEL} is the Phase 3 anchor — already done)")
        return [entry_for(lab) for lab in labels]
    entries = remaining_entries()
    if args.tier:
        entries = [e for e in entries if tier_of(e["gsd_cm"]) == args.tier]
    return entries


def print_summary(entries):
    print(f"\n{'='*65}\n  PHASE 4 — Per-Year Semantic Fine-Tuning\n{'='*65}")
    print(f"\n  {'Year':<7}{'GSD':>7}{'Tier':>8}{'Model':>8}{'Mask':>7}{'IoU':>8}")
    print(f"  {'-'*7}{'-'*7}{'-'*8}{'-'*8}{'-'*7}{'-'*8}")
    eval_df = pd.read_csv(EVAL_CSV) if EVAL_CSV.exists() else pd.DataFrame()
    for e in entries:
        lab = e["label"]
        model_ok = (MODELS_DIR / f"sem_best_{lab}.pt").exists()
        mask_ok = (MASKS_DIR / f"edmonds_canopy_mask_{lab}.tif").exists()
        iou = ""
        if not eval_df.empty:
            sub = eval_df[(eval_df["year"].astype(str) == lab) &
                          (eval_df["scope"] == "OVERALL")]
            if len(sub):
                iou = f"{float(sub.iloc[0]['iou']):.3f}"
        print(f"  {lab:<7}{e['gsd_cm']:>6.1f}{tier_of(e['gsd_cm']):>8}"
              f"{'✓' if model_ok else '—':>8}{'✓' if mask_ok else '—':>7}{iou:>8}")
    print(f"""
  ◆ DECISION GATE 4 (Month 9):
    Do coarse-year masks (2000, 2002, and 50–60cm years) meet the
    minimum IoU? Coarse years tiled city-wide (the default) now report
    OUT-OF-SAMPLE IoU from a geographically-blocked held-out test block
    (>520 m from train); only legacy --coarse-site-tiling runs and
    partial-coverage years that fell back to a degraded split remain
    in-sample (see eval_scope in {EVAL_CSV.name}). For each coarse year
    decide: include in temporal analysis / exclude / flag low-confidence.

  NEXT: Phase 6 — temporal crown linking + per-crown canopy-fraction
        assessment projects the canonical crown layer onto these masks.
""")
    print(f"{'='*65}")


def main():
    filtered = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    p = argparse.ArgumentParser(
        description="Phase 4 — Per-Year Semantic Segmentation Fine-Tuning")
    p.add_argument("--year", type=str, default=None,
                   help="Comma-separated year labels (e.g. 2017 or 2005,2007,2009). "
                        "Default: all 17 remaining.")
    p.add_argument("--tier", choices=["fine", "medium", "coarse"], default=None,
                   help="Restrict to one resolution tier.")
    p.add_argument("--step", choices=ALL_STEPS, default=None,
                   help="Run a single step (default: full per-year pipeline + "
                        "consistency).")
    p.add_argument("--skip-training", action="store_true",
                   help="Skip fine-tuning — use existing per-year checkpoints.")
    p.add_argument("--skip-inference", action="store_true",
                   help="Stop after evaluation.")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    p.add_argument("--ckpt", type=str, default=None,
                   help="Override the Phase 3 fine-tune-start checkpoint.")
    p.add_argument("--vi", action="store_true",
                   help="Use 6-channel RGB+VI input (must match the Phase 3 ckpt).")
    p.add_argument("--dry-run", action="store_true",
                   help="Plan only — no writes.")
    p.add_argument("--max-tiles", type=int, default=None,
                   help="Cap each year's tile set to N (canopy tiles kept first, "
                        "then negatives). For fast test runs.")
    p.add_argument("--stride", type=int, default=None,
                   help="Override the per-tier tiling stride (smaller = more "
                        "overlapping tiles → more tiles).")
    p.add_argument("--site-buffer", type=float, default=0.0,
                   help="Pad each site footprint by N map units (EPSG:3857 ≈ m) "
                        "before cropping → larger crops → more tiles. Only the "
                        "part falling inside the reviewed regions becomes "
                        "labeled; beyond that is IGNORE. ~200 matches the prep "
                        "buffer.")
    p.add_argument("--coarse-site-tiling", action="store_true",
                   help="Coarse tier: use the legacy 6-site tiling instead of the "
                        "default city-wide stratified tiling (Fix 3). Ignored for "
                        "fine/medium tiers and when --anchor-labels is set.")
    p.add_argument("--anchor-labels", action="store_true",
                   help="Build masks from the 2020 full-city canopy prob raster "
                        "(phase3/edmonds_canopy_prob_2020.tif) instead of the "
                        "review crowns/regions — labels the whole crop, so the "
                        "expanded sites are fully usable.")
    p.add_argument("--prob-hi", type=float, default=0.6,
                   help="--anchor-labels: 2020 prob ≥ this → canopy (1).")
    p.add_argument("--prob-lo", type=float, default=0.4,
                   help="--anchor-labels: 2020 prob ≤ this → background (0); "
                        "values between prob-lo and prob-hi → IGNORE.")
    args = p.parse_args(filtered)

    from pipeline_log import StepLogger
    LOGS_DIR = BASE / "Scripts" / "logs"
    SCRIPT_NAME = "phase4_semantic_finetune"

    global USE_VI, IN_CHANNELS
    USE_VI = bool(args.vi)
    IN_CHANNELS = 3 + (len(VI_NAMES) if USE_VI else 0)

    print("=" * 65)
    print("  PHASE 4 — Per-Year Semantic Segmentation Fine-Tuning (17 years)")
    print("  Edmonds Temporal Active Learning Pipeline")
    print("=" * 65)

    entries = _resolve_years(args)
    labels = [e["label"] for e in entries]
    print(f"  Years ({len(labels)}): {', '.join(labels)}")
    if args.dry_run:
        print("  Dry run: True")

    # Which per-year steps to run.
    if args.step == "consistency":
        per_year = []
    elif args.step:
        per_year = [args.step]
    else:
        per_year = list(PER_YEAR_STEPS)
        if args.skip_training:
            per_year.remove("train")
        if args.skip_inference:
            per_year = [s for s in per_year if s not in ("inference", "postproc")]
    if per_year:
        print(f"  Steps: {', '.join(per_year)}")

    for d in (OUT_DIR, SITE_DIR, TILE_DIR, MODELS_DIR, MASKS_DIR, EVAL_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # Site footprints are shared across years — discover once.
    sites = None
    if any(s in per_year for s in ("labels", "tile")):
        sites = discover_site_footprints(site_buffer=args.site_buffer)

    p3 = resolve_p3_ckpt(args.ckpt)
    if "train" in per_year:
        print(f"  Fine-tune start: {p3 if p3 else 'NOT FOUND — train will abort'}")

    # Process each year end-to-end (so a crash leaves complete years behind).
    for e in entries:
        lab = e["label"]
        print(f"\n{'#'*65}\n#  YEAR {lab}  ({e['gsd_cm']:.1f} cm, "
              f"{tier_of(e['gsd_cm'])}, {e['source']}, {e['coverage']})\n{'#'*65}")
        # Coarse tier defaults to city-wide stratified tiling (Fix 3); opt out
        # with --coarse-site-tiling, and the 6-site anchor-label path takes
        # precedence when --anchor-labels is set.
        citywide = (tier_of(e["gsd_cm"]) == "coarse"
                    and not args.coarse_site_tiling
                    and not args.anchor_labels)
        if "labels" in per_year:
            with StepLogger(SCRIPT_NAME, f"labels_{lab}", LOGS_DIR) as log:
                r = step_labels(lab, sites, dry_run=args.dry_run,
                                anchor_labels=args.anchor_labels,
                                prob_hi=args.prob_hi, prob_lo=args.prob_lo,
                                citywide=citywide)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "tile" in per_year:
            with StepLogger(SCRIPT_NAME, f"tile_{lab}", LOGS_DIR) as log:
                r = step_tile(lab, sites, dry_run=args.dry_run,
                              max_tiles=args.max_tiles, stride_override=args.stride,
                              citywide=citywide)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "train" in per_year:
            with StepLogger(SCRIPT_NAME, f"train_{lab}", LOGS_DIR) as log:
                r = step_train(lab, batch_size=args.batch_size,
                               p3_ckpt=args.ckpt, dry_run=args.dry_run)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "evaluate" in per_year:
            with StepLogger(SCRIPT_NAME, f"evaluate_{lab}", LOGS_DIR) as log:
                r = step_evaluate(lab, dry_run=args.dry_run)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "inference" in per_year:
            with StepLogger(SCRIPT_NAME, f"inference_{lab}", LOGS_DIR) as log:
                r = step_inference(lab, batch_size=args.batch_size * 16
                                   if args.batch_size == BATCH_SIZE else args.batch_size,
                                   dry_run=args.dry_run)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)
        if "postproc" in per_year:
            with StepLogger(SCRIPT_NAME, f"postproc_{lab}", LOGS_DIR) as log:
                r = step_postproc(lab, dry_run=args.dry_run)
                _f = {"year": lab, "gsd_cm": e["gsd_cm"],
                      "dry_run": args.dry_run, "errors": 0}
                if isinstance(r, dict): _f.update(r)
                log.finish(**_f)

    # Cross-year consistency runs once (default pipeline, or --step consistency).
    if args.step in (None, "consistency"):
        with StepLogger(SCRIPT_NAME, "consistency", LOGS_DIR) as log:
            r = step_consistency(dry_run=args.dry_run)
            _f = {"dry_run": args.dry_run, "errors": 0}
            if isinstance(r, dict): _f.update(r)
            log.finish(**_f)

    print_summary(entries)
    timer_summary()


if __name__ == "__main__":
    multiprocessing.set_start_method("fork", force=True)
    main()
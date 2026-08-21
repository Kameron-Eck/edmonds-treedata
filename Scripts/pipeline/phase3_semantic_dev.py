"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 3 — Semantic Segmentation Model Development (2020)
  Edmonds Temporal Active Learning Pipeline

  Adapts the Phase 0 instance segmentation U-Net to produce a
  binary canopy/non-canopy probability map.  The encoder+decoder
  architecture is identical; only the final activation (sigmoid)
  and loss (BCEWithLogitsLoss) change.

  PIPELINE STEPS
  ──────────────
  Step 1  labels      Rasterise 3,000 hand-traced crowns → binary
                      canopy mask at 7.5 cm per training site
  Step 2  tile        Tile RGB + binary mask → 512×512 paired patches
  Step 3  train       Phase A (frozen encoder, 20 epochs) +
                      Phase B (full model, 30 epochs)
  Step 4  evaluate    Pixel accuracy, IoU, Dice on held-out test tiles
  Step 5  inference   Streaming full-city inference → probability raster
  Step 6  postproc    Threshold → morphology → polygonize
  Step 7  crossval    Compare semantic canopy mask vs Phase 0 instance
                      detection (area agreement check)

  INPUTS
  ──────
  photos/             *_rgb.tif       Training site 7.5 cm imagery
  polygons/           *.shp           Matched crown polygons
  checkpoints/        ddt_best_v7_global.pt   Phase 0 pretrained weights
  Full_Image/         edmonds_2020_image.tif  Full Edmonds 2020 ortho

  OUTPUTS
  ───────
  phase3/tiles/                   512×512 paired image/mask tiles
  phase3/sem_best_2020.pt         Best semantic model checkpoint
  phase3/edmonds_canopy_prob_2020.tif   Full-city probability raster
  phase3/edmonds_canopy_mask_2020.tif   Binary canopy mask (thresholded)
  phase3/edmonds_canopy_mask_2020.gpkg  Canopy polygons
  phase3/semantic_eval_report.csv       Pixel-level evaluation metrics
  phase3/crossval_report.csv            Instance vs semantic comparison

  USAGE
  ─────
  %run phase3_semantic_dev.py                     # full pipeline
  %run phase3_semantic_dev.py --step labels       # single step
  %run phase3_semantic_dev.py --step train        # train only
  %run phase3_semantic_dev.py --step evaluate     # evaluate only
  %run phase3_semantic_dev.py --step inference    # full-city inference
  %run phase3_semantic_dev.py --step postproc     # threshold + polygonize
  %run phase3_semantic_dev.py --step crossval     # vs Phase 0
  %run phase3_semantic_dev.py --skip-training     # skip to eval
  %run phase3_semantic_dev.py --skip-inference    # stop after eval
  %run phase3_semantic_dev.py --dry-run           # print stats, no writes
  %run phase3_semantic_dev.py --ckpt <path>       # use specific checkpoint
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import gc
import multiprocessing
import os
import shutil
import sys
import time
import warnings
from pathlib import Path

# ── Dependency bootstrap (Colab) ──────────────────────────────────────────────
# Ensure non-stdlib packages are present so the whole script runs end-to-end via
# `%run` in a fresh runtime, without a separate pip cell. Each entry is
# (import_name, pip_spec). Packages already installed are left untouched, so this
# is a fast no-op on a warm runtime and only prints when it actually installs.
# NOTE: torch is intentionally NOT auto-installed — Colab GPU runtimes ship a
# CUDA-matched build, and reinstalling it risks breaking that. If torch is
# missing, select a GPU runtime (Runtime → Change runtime type → GPU).

import importlib
import subprocess


def _pip_install(spec):
    print(f"  • installing {spec} …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec],
                   check=True)


def _ensure_deps(deps):
    for import_name, pip_spec in deps:
        try:
            importlib.import_module(import_name)
        except ImportError:
            _pip_install(pip_spec)
            importlib.invalidate_caches()


# Geospatial / CPU deps used at module load and in the geo steps:
_ensure_deps([
    ("geopandas",  "geopandas"),
    ("rasterio",   "rasterio"),
    ("shapely",    "shapely"),
    ("sklearn",    "scikit-learn"),
    ("scipy",      "scipy"),
    ("tqdm",       "tqdm"),
])

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import rasterio.transform
import rasterio.windows
from shapely.geometry import box, mapping, shape
from sklearn.model_selection import train_test_split
from tqdm import tqdm

warnings.filterwarnings("ignore")


# ── Lazy torch imports ────────────────────────────────────────────────────────

_torch_loaded = False


def _ensure_torch():
    global _torch_loaded
    if _torch_loaded:
        return
    # smp + albumentations are not preinstalled on Colab. Pin albumentations to
    # 2.x so the transform kwargs in _make_pixel_transform stay valid (the
    # RandomFog/Affine fixes target the 2.x API). torch/timm come via smp's deps
    # if absent, but Colab's preinstalled torch normally satisfies them.
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


# ── Timing helpers (same as phase1_preprocess.py) ─────────────────────────────

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
PHOTOS_DIR    = BASE / "photos"
POLYGONS_DIR  = BASE / "polygons"
CKPT_DIR_P0   = BASE / "checkpoints"
# Full-city 2020 ortho. Per phase1_preprocess.py, the imagery lives in
# "Full_Image/Pipeline Imagery/" and the 2020 reference image (CoE, not
# upsampled) is "2020_coe_rgb.tif". If phase1 step 0 was run, a copy also
# exists at "Full_Image/Pipeline Imagery/upsample/2020_coe_rgb.tif".
EDMONDS_IMG   = BASE / "Full_Image/Pipeline Imagery/2020_coe_rgb.tif"
BOUNDARY_PATH = BASE / "City Boundry/Edmonds Boundry.shp"

# Phase 0 instance outputs for cross-validation
INSTANCE_CROWNS = BASE / "inference/edmonds_crowns_2020.gpkg"

# Phase 3 output paths
OUT_DIR       = BASE / "phase3"
TILE_DIR      = OUT_DIR / "tiles"
CKPT_DIR      = OUT_DIR / "checkpoints"
LABEL_DIR     = OUT_DIR / "labels"

PROB_OUT      = OUT_DIR / "edmonds_canopy_prob_2020.tif"
MASK_OUT      = OUT_DIR / "edmonds_canopy_mask_2020.tif"
CANOPY_GPKG   = OUT_DIR / "edmonds_canopy_mask_2020.gpkg"
EVAL_CSV      = OUT_DIR / "semantic_eval_report.csv"
CROSSVAL_CSV  = OUT_DIR / "crossval_report.csv"

TARGET_CRS    = "EPSG:3857"


# ── Hyperparameters ──────────────────────────────────────────────────────────

# Model architecture (identical to Phase 0)
ENCODER              = "resnet101"
DECODER_CHANNELS     = (1024, 512, 256, 128, 64)
ENCODER_WEIGHTS      = "imagenet"
DECODER_DROPOUT      = 0.3

# Tiling (same as Phase 0)
TILE_SIZE            = 512
TILE_STRIDE          = 512
NEGATIVE_SAMPLE_RATE = 0.15
TEST_FRAC            = 0.20
RANDOM_SEED          = 42

# Training — Phase A (frozen encoder)
EPOCHS_PHASE_A       = 20
LR_PHASE_A           = 5e-5

# Training — Phase B (full model)
EPOCHS_PHASE_B       = 30
LR_PHASE_B           = 5e-6

# Training — shared
EARLY_STOP_PAT       = 15
BATCH_SIZE           = 10
NUM_WORKERS          = 16
SAVE_EVERY           = 5
# Spatial buffer between train/val tiles. Tiles are a non-overlapping 512px
# grid, so neighbors are exactly 512px apart and Chebyshev distances are
# multiples of 512. A value in (512,1024] drops every train tile in a val
# tile's 8-neighbor ring — with scattered val tiles that excluded ~59% of the
# training set. 512 keeps all non-val train tiles (no buffer). Raise toward
# 1024 only if you need strict spatial separation and have data to spare.
SPATIAL_BUFFER_PX    = 512
L1_LAMBDA            = 1e-6
WARMUP_EPOCHS        = 3

# Inference
INFER_BATCH_SIZE     = 160
INFER_STRIDE         = 256
INFER_PAD            = (TILE_SIZE - INFER_STRIDE) // 2

# Post-processing (from Method Pipeline)
CANOPY_PROB_THRESHOLD = 0.5
MIN_CANOPY_PATCH      = 3.0   # m²
MORPH_KERNEL_SIZE     = 3
SIMPLIFY_TOLERANCE_M  = 0.5   # Douglas–Peucker tolerance to drop pixel-staircase vertices (0 disables)
POLYGON_CONNECTIVITY  = 8     # 8 merges diagonally-touching canopy; 4 keeps them separate
CROWN_COMPLETENESS_SAMPLE = 3000  # crowns sampled for the under-segmentation report (crossval)

# ImageNet normalisation
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

# ── Experiment config (Problem A + B) ────────────────────────────────────────
# All default OFF so the existing labels/tile/train/evaluate/inference/postproc/
# crossval steps behave exactly as before. The LOSO step and any run with --vi /
# --unfreeze discriminative flip these via globals set in main().
USE_VI        = False                 # add vegetation-index input channels
VI_NAMES      = ("GCC", "GRVI", "ExG")
# Approximate standardisers for the VI channels (computed on RGB in [0,1]).
# Exact values aren't critical — the first conv + BN adapt — but centring to ~unit
# scale helps early optimisation. GCC≈0.33±0.1, GRVI≈0±0.3, ExG≈0.1±0.25.
VI_MEAN       = [0.33, 0.00, 0.10]
VI_STD        = [0.10, 0.30, 0.25]
IN_CHANNELS   = 3                     # 3 (RGB) or 6 (RGB+GCC+GRVI+ExG); set in main
UNFREEZE_MODE = "full"                # "full" (baseline Phase B) | "discriminative"

# Discriminative Phase-B learning rates (Howard & Ruder 2018; Zheng 2025). Both
# ≫ the 5e-6 full-unfreeze LR that barely moved the encoder. Only the input stem
# (conv1/bn1 — needed for the new VI channels) + late blocks (layer3/layer4) +
# decoder train; layer1/layer2 stay frozen.
LR_DECODER_B   = 2e-5
LR_ENC_LATE_B  = 1e-5

# LOSO (leave-one-site-out) — the honest spatial protocol (Problem B). Each fold
# tests on one held-out forest, validates on another, trains on the rest (+ all
# true-negative sites always in train). New checkpoints; never overwrites
# sem_best_2020.pt.
LOSO_CKPT_TMPL = "sem_ft_fold_{site}.pt"
LOSO_REPORT    = OUT_DIR / "loso_report.csv"


# ═════════════════════════════════════════════════════════════════════════════
#  Step 1 — Binary Label Generation
# ═════════════════════════════════════════════════════════════════════════════

def discover_sites():
    """Auto-discover training sites (same logic as Phase 0)."""
    print("\n── Discovering Training Sites ──")

    photo_files = sorted(PHOTOS_DIR.glob("*_rgb.tif"))
    if not photo_files:
        raise FileNotFoundError(f"No *_rgb.tif files found in {PHOTOS_DIR}")

    image_paths     = []
    shapefile_paths = []
    site_labels     = []

    for photo_path in photo_files:
        label    = photo_path.stem.replace("_rgb", "")
        shp_path = POLYGONS_DIR / f"{label}.shp"
        shp      = str(shp_path) if shp_path.exists() else None

        image_paths.append(str(photo_path))
        shapefile_paths.append(shp)
        site_labels.append(label)

        status = f"✓ {shp_path.name}" if shp else "— (true negative)"
        print(f"  {label:<25} {status}")

    print(f"\n  Total sites:    {len(site_labels)}")
    print(f"  Positive sites: {sum(s is not None for s in shapefile_paths)}")
    print(f"  True negatives: {sum(s is None for s in shapefile_paths)}")

    return image_paths, shapefile_paths, site_labels


def preprocess_crowns(shp_path, target_crs="EPSG:3857"):
    """Load and clean crown polygons (simplified from Phase 0 Step 3)."""
    gdf = gpd.read_file(shp_path)

    # Reproject if needed
    if gdf.crs is None:
        raise ValueError(
            f"{shp_path} has no defined CRS — cannot safely reproject. "
            f"Set the CRS on the shapefile (e.g. via a .prj) before tiling.")
    if gdf.crs.to_epsg() != 3857:
        gdf = gdf.to_crs(target_crs)

    # Explode MultiPolygons
    if "MultiPolygon" in gdf.geometry.geom_type.unique():
        gdf = gdf.explode(index_parts=False).reset_index(drop=True)

    # Fix invalid geometries
    invalid_mask = ~gdf.geometry.is_valid
    if invalid_mask.any():
        gdf["geometry"] = gdf.geometry.buffer(0)
        gdf = gdf[gdf.geometry.is_valid].reset_index(drop=True)

    # Second explode after buffer(0)
    if "MultiPolygon" in gdf.geometry.geom_type.unique():
        gdf = gdf.explode(index_parts=False).reset_index(drop=True)

    # Drop empties and slivers
    gdf = gdf[~gdf.geometry.is_empty].reset_index(drop=True)
    gdf["area_m2"] = gdf.geometry.area
    gdf = gdf[gdf["area_m2"] >= 0.5].reset_index(drop=True)

    return gdf


def generate_binary_mask(img_path, gdf, label):
    """
    Rasterise crown polygons into a binary canopy mask (1=canopy, 0=background)
    at the same resolution and extent as the training site imagery.
    """
    out_path = LABEL_DIR / f"{label.lower()}_canopy_mask.tif"

    with rasterio.open(img_path) as src:
        height    = src.height
        width     = src.width
        transform = src.transform
        crs       = src.crs

    # Crowns are reprojected to EPSG:3857 in preprocess_crowns, but the mask is
    # rasterised on the *image* grid below. If the image isn't 3857 the
    # geometries and raster grid won't align → wrong/empty masks. Fail loudly.
    if crs is None or crs.to_epsg() != 3857:
        raise ValueError(
            f"{label}: training image CRS is {crs} but crowns are rasterised "
            f"in EPSG:3857. Reproject the image to 3857 (or reproject the "
            f"raster grid here) before generating labels.")

    profile = {
        "driver": "GTiff", "dtype": "uint8",
        "width": width, "height": height, "count": 1,
        "crs": crs, "transform": transform,
        "compress": "lzw", "nodata": 255,
    }

    # True negative site — all zeros
    if len(gdf) == 0:
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(np.zeros((height, width), dtype=np.uint8), 1)
        print(f"  {label}: true negative mask ({width}×{height})")
        return out_path

    # Rasterise all crowns as 1 (dissolved — overlapping crowns merge)
    shapes = ((geom, 1) for geom in gdf.geometry)
    mask = rasterio.features.rasterize(
        shapes, out_shape=(height, width), transform=transform,
        fill=0, dtype=np.uint8, all_touched=False,
    )

    canopy_frac = mask.sum() / (height * width) * 100
    print(f"  {label}: {len(gdf)} crowns → {mask.sum():,} canopy px "
          f"({canopy_frac:.1f}% coverage)")

    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(mask, 1)

    return out_path


def step_labels(dry_run=False):
    """Step 1: Generate binary canopy masks for all training sites."""
    print("\n── Step 1: Binary Canopy Label Generation ──")

    LABEL_DIR.mkdir(parents=True, exist_ok=True)
    image_paths, shapefile_paths, site_labels = discover_sites()

    mask_paths = {}
    total_crowns = 0

    for img_path, shp_path, label in zip(
            image_paths, shapefile_paths, site_labels):

        if shp_path is not None:
            gdf = preprocess_crowns(shp_path)
            total_crowns += len(gdf)
        else:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:3857")

        if dry_run:
            print(f"  {label}: {len(gdf)} crowns (dry run)")
            continue

        mask_path = generate_binary_mask(img_path, gdf, label)
        mask_paths[label] = mask_path

    print(f"\n  Total crowns rasterised: {total_crowns:,}")
    print(f"  Mask files: {LABEL_DIR}")

    return image_paths, shapefile_paths, site_labels, mask_paths


# ═════════════════════════════════════════════════════════════════════════════
#  Step 2 — Tiling
# ═════════════════════════════════════════════════════════════════════════════

def tile_site_semantic(label, img_path, mask_path, keep_all_empty=False):
    """Generate 512×512 paired tiles (RGB + binary mask) for one site.

    keep_all_empty=True keeps every zero-canopy tile — used for dedicated
    true-negative sites (parking lots, water) where empty tiles are the whole
    point. When False, zero-canopy tiles are subsampled at NEGATIVE_SAMPLE_RATE
    so positive sites aren't padded out with trivial background.
    """
    records = []

    with rasterio.open(img_path) as img_src, \
         rasterio.open(mask_path) as mask_src:

        height, width = img_src.height, img_src.width
        assert (height, width) == (mask_src.height, mask_src.width), \
            f"Dimension mismatch for {label}"

        img_transform = img_src.transform
        crs           = img_src.crs

        row_starts = range(0, height - TILE_SIZE + 1, TILE_STRIDE)
        col_starts = range(0, width  - TILE_SIZE + 1, TILE_STRIDE)
        accepted = rejected = 0

        for row_off in tqdm(row_starts, desc=f"  {label}", leave=False):
            for col_off in col_starts:
                window = rasterio.windows.Window(
                    col_off=col_off, row_off=row_off,
                    width=TILE_SIZE, height=TILE_SIZE)
                img_tile  = img_src.read(window=window)
                mask_tile = mask_src.read(1, window=window)

                canopy_frac = float(mask_tile.sum()) / (TILE_SIZE * TILE_SIZE)

                # Keep tiles with any canopy. For empty tiles: keep all on
                # dedicated negative sites, else subsample at NEGATIVE_SAMPLE_RATE.
                if canopy_frac == 0.0:
                    if keep_all_empty or np.random.random() < NEGATIVE_SAMPLE_RATE:
                        pass  # keep as true negative
                    else:
                        rejected += 1
                        continue

                tile_name      = f"{label.lower()}_r{row_off:05d}_c{col_off:05d}.tif"
                tile_transform = rasterio.windows.transform(window, img_transform)

                records.append({
                    "tile_name":      tile_name,
                    "site":           label,
                    "row_off":        row_off,
                    "col_off":        col_off,
                    "canopy_frac":    round(float(canopy_frac), 4),
                    "img_path":       img_path,
                    "mask_path":      str(mask_path),
                    "tile_transform": tile_transform,
                    "crs":            crs,
                    "_img_tile":      img_tile,
                    "_mask_tile":     mask_tile,
                })
                accepted += 1

        print(f"  {label}: {accepted} accepted / {rejected} rejected")

    return records


def step_tile(image_paths=None, shapefile_paths=None,
              site_labels=None, mask_paths=None, dry_run=False):
    """Step 2: Tile all training sites into 512×512 patches."""
    print("\n── Step 2: Tiling for Semantic Training ──")

    TILE_DIR.mkdir(parents=True, exist_ok=True)
    for split in ["train", "test"]:
        (TILE_DIR / split / "images").mkdir(parents=True, exist_ok=True)
        (TILE_DIR / split / "masks").mkdir(parents=True, exist_ok=True)

    # Discover sites if not provided
    if image_paths is None:
        image_paths, shapefile_paths, site_labels = discover_sites()
    if shapefile_paths is None:
        # Recover the crown-shapefile mapping so we can identify dedicated
        # true-negative sites (those without a shapefile).
        _, shapefile_paths, _ = discover_sites()
    if mask_paths is None:
        mask_paths = {}
        for label in site_labels:
            mp = LABEL_DIR / f"{label.lower()}_canopy_mask.tif"
            if mp.exists():
                mask_paths[label] = mp

    # Dedicated true-negative sites (no crown shapefile): keep ALL their empty
    # tiles. The training sampler weights by 1/site_count, so this does not
    # change how often negatives are shown — only the variety of hard negatives.
    negative_sites = {
        lbl for lbl, shp in zip(site_labels, shapefile_paths) if shp is None
    }
    if negative_sites:
        print(f"  Keeping all tiles for true-negative sites: "
              f"{', '.join(sorted(negative_sites))}")

    # Seed before tiling so the incidental zero-canopy subsampling (and thus
    # the held-out test set) is reproducible across runs.
    np.random.seed(RANDOM_SEED)

    # Generate all tiles
    all_records = []
    for img_path, label in zip(image_paths, site_labels):
        if label not in mask_paths:
            print(f"  WARNING: No mask for {label} — skipping")
            continue
        records = tile_site_semantic(
            label, img_path, mask_paths[label],
            keep_all_empty=(label in negative_sites))
        all_records.extend(records)

    print(f"\n  Total tiles: {len(all_records)}")

    if dry_run:
        print("  Dry run — not writing tiles")
        return

    # Stratified train/test split
    np.random.seed(RANDOM_SEED)
    tile_names = [r["tile_name"] for r in all_records]
    sites      = [r["site"]      for r in all_records]

    train_names, test_names = train_test_split(
        tile_names, test_size=TEST_FRAC, stratify=sites,
        random_state=RANDOM_SEED)
    train_set = set(train_names)

    df_split = pd.DataFrame({"tile_name": tile_names, "site": sites})
    df_split["split"] = df_split["tile_name"].apply(
        lambda n: "train" if n in train_set else "test")

    print(f"\n  {'Site':<20} {'Train':>7} {'Test':>7}")
    print(f"  {'-'*20} {'-'*7} {'-'*7}")
    for site in sorted(set(sites)):
        sub  = df_split[df_split["site"] == site]
        n_tr = (sub["split"] == "train").sum()
        n_te = (sub["split"] == "test").sum()
        print(f"  {site:<20} {n_tr:>7} {n_te:>7}")
    print(f"  {'TOTAL':<20} {len(train_names):>7} {len(test_names):>7}")

    # Write tiles to disk
    img_profile_base = {
        "driver": "GTiff", "dtype": "uint8", "count": 3,
        "width": TILE_SIZE, "height": TILE_SIZE, "compress": "lzw",
    }
    mask_profile_base = {
        "driver": "GTiff", "dtype": "uint8", "count": 1,
        "width": TILE_SIZE, "height": TILE_SIZE, "compress": "lzw",
        "nodata": 255,
    }

    index_rows = []
    for rec in tqdm(all_records, desc="  Writing tiles"):
        split     = "train" if rec["tile_name"] in train_set else "test"
        tile_name = rec["tile_name"]

        img_out  = TILE_DIR / split / "images" / tile_name
        mask_out = TILE_DIR / split / "masks"  / tile_name

        with rasterio.open(img_out, "w", **{**img_profile_base,
                           "crs": rec["crs"],
                           "transform": rec["tile_transform"]}) as dst:
            dst.write(rec["_img_tile"])

        with rasterio.open(mask_out, "w", **{**mask_profile_base,
                           "crs": rec["crs"],
                           "transform": rec["tile_transform"]}) as dst:
            dst.write(np.asarray(rec["_mask_tile"]).squeeze(), 1)

        index_rows.append({
            "tile_name":   tile_name,
            "site":        rec["site"],
            "split":       split,
            "row_off":     rec["row_off"],
            "col_off":     rec["col_off"],
            "canopy_frac": rec["canopy_frac"],
            "img_path":    str(img_out),
            "mask_path":   str(mask_out),
        })

    index_df   = pd.DataFrame(index_rows)
    index_path = TILE_DIR / "tile_index_semantic.csv"
    index_df.to_csv(index_path, index=False)
    print(f"  ✓ {len(index_rows)} tiles written  |  index: {index_path.name}")


# ═════════════════════════════════════════════════════════════════════════════
#  Step 3 — Training
# ═════════════════════════════════════════════════════════════════════════════

# ── Augmentation (same spatial + pixel pipeline as Phase 0) ──────────────────

def _make_spatial_transform():
    _ensure_torch()
    return A.Compose([
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.5),
        A.Transpose(p=0.5),
        A.RandomRotate90(p=0.5),
        A.Rotate(limit=45, border_mode=0, p=0.5),
        A.Affine(translate_percent=0.1, scale=(0.9, 1.1),
                 rotate=0, border_mode=0, p=0.5),
        A.GridDistortion(num_steps=5, distort_limit=0.3, p=0.4),
        A.ElasticTransform(alpha=50, sigma=5, p=0.3),
    ], additional_targets={"mask": "mask"})


def _make_pixel_transform():
    _ensure_torch()
    return A.Compose([
        A.OneOf([
            A.GaussianBlur(blur_limit=(3, 7), p=1.0),
            A.MedianBlur(blur_limit=5, p=1.0),
        ], p=0.5),
        A.RandomBrightnessContrast(brightness_limit=0.3,
                                   contrast_limit=0.3, p=0.6),
        A.HueSaturationValue(hue_shift_limit=15, sat_shift_limit=30,
                             val_shift_limit=15, p=0.5),
        A.RandomGamma(gamma_limit=(70, 130), p=0.4),
        A.RandomShadow(shadow_roi=(0, 0, 1, 1),
                       num_shadows_limit=(1, 3),
                       shadow_dimension=5, p=0.4),
        A.RandomFog(fog_coef_range=(0.05, 0.2), p=0.3),
        A.Downscale(scale_range=(0.5, 0.75),
                    interpolation_pair={"downscale": 0, "upscale": 2},
                    p=0.3),
        A.CoarseDropout(num_holes_range=(2, 8),
                        hole_height_range=(32, 96),
                        hole_width_range=(32, 96), fill=0, p=0.4),
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD,
                    max_pixel_value=255.0),
        ToTensorV2(),
    ])


def _make_test_transform():
    _ensure_torch()
    return A.Compose([
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD,
                    max_pixel_value=255.0),
        ToTensorV2(),
    ], additional_targets={"mask": "mask"})


# ── Vegetation indices (Problem A) ───────────────────────────────────────────
# Computed on demand from RGB so no re-tiling is needed; the on-disk tiles stay
# 3-band. GCC normalises on total brightness (Zhang 2023) → robust to the
# shadowed-edge illumination that drives the under-segmentation. GRVI/ExG add
# green-excess cues (Motohka 2010; Meyer & Neto 2008).

def compute_vis(rgb01, eps=1e-6):
    """rgb01: H×W×3 float in [0,1] → H×W×3 float (GCC, GRVI, ExG)."""
    R = rgb01[..., 0]; G = rgb01[..., 1]; B = rgb01[..., 2]
    s    = R + G + B + eps
    gcc  = G / s                         # ~[0,1]
    grvi = (G - R) / (G + R + eps)       # [-1,1]
    exg  = 2.0 * G - R - B               # [-1,2]
    return np.stack([gcc, grvi, exg], axis=-1).astype(np.float32)


def _input_norm():
    """Per-channel (mean, std) for the active channel set, as float32 arrays."""
    mean = list(IMAGENET_MEAN) + (VI_MEAN if USE_VI else [])
    std  = list(IMAGENET_STD)  + (VI_STD  if USE_VI else [])
    return (np.asarray(mean, np.float32), np.asarray(std, np.float32))


def rgb_to_model_input(rgb_uint8):
    """H×W×3 uint8 → C×H×W float32, normalised, with VI channels if USE_VI.

    Numerically identical to the albumentations Normalize+ToTensorV2 path for the
    RGB channels (img/255 → (x-mean)/std), so the baseline (USE_VI=False) result
    is unchanged; it only adds the VI channels when enabled.
    """
    rgb01 = rgb_uint8.astype(np.float32) / 255.0
    arr   = np.concatenate([rgb01, compute_vis(rgb01)], -1) if USE_VI else rgb01
    mean, std = _input_norm()
    arr = (arr - mean) / std
    return np.ascontiguousarray(arr.transpose(2, 0, 1))   # C×H×W


def _make_pixel_transform_nonorm():
    """Pixel augmentations WITHOUT the trailing Normalize+ToTensor, so VI
    channels can be derived from the *augmented* RGB (teaching the indices the
    same brightness/shadow robustness) before normalisation."""
    _ensure_torch()
    return A.Compose([
        A.OneOf([
            A.GaussianBlur(blur_limit=(3, 7), p=1.0),
            A.MedianBlur(blur_limit=5, p=1.0),
        ], p=0.5),
        A.RandomBrightnessContrast(brightness_limit=0.3,
                                   contrast_limit=0.3, p=0.6),
        A.HueSaturationValue(hue_shift_limit=15, sat_shift_limit=30,
                             val_shift_limit=15, p=0.5),
        A.RandomGamma(gamma_limit=(70, 130), p=0.4),
        A.RandomShadow(shadow_roi=(0, 0, 1, 1),
                       num_shadows_limit=(1, 3),
                       shadow_dimension=5, p=0.4),
        A.RandomFog(fog_coef_range=(0.05, 0.2), p=0.3),
        A.Downscale(scale_range=(0.5, 0.75),
                    interpolation_pair={"downscale": 0, "upscale": 2},
                    p=0.3),
        A.CoarseDropout(num_holes_range=(2, 8),
                        hole_height_range=(32, 96),
                        hole_width_range=(32, 96), fill=0, p=0.4),
    ])


# ── Dataset ──────────────────────────────────────────────────────────────────

class SemanticDataset:
    """PyTorch Dataset for paired RGB + binary canopy mask tiles."""

    def __init__(self, df, training=True):
        self.df       = df.reset_index(drop=True)
        self.training = training
        if training:
            self.spatial_tf = _make_spatial_transform()
            if USE_VI:
                self.pixel_tf = _make_pixel_transform_nonorm()   # VI added after
            else:
                self.pixel_tf = _make_pixel_transform()
        else:
            self.test_tf = _make_test_transform()

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        _ensure_torch()
        row = self.df.iloc[idx]

        with rasterio.open(row["img_path"]) as src:
            img = src.read().transpose(1, 2, 0)   # H×W×3, uint8
        with rasterio.open(row["mask_path"]) as src:
            mask = src.read(1).astype(np.float32)  # H×W, 0/1

        if self.training:
            out  = self.spatial_tf(image=img, mask=mask)
            img  = out["image"]
            mask = out["mask"]
            if USE_VI:
                img = self.pixel_tf(image=img)["image"]          # aug RGB uint8
                img = torch.from_numpy(rgb_to_model_input(img))  # C×H×W float
            else:
                img = self.pixel_tf(image=img)["image"]
            mask = torch.from_numpy(mask).unsqueeze(0).float()
        else:
            if USE_VI:
                img  = torch.from_numpy(rgb_to_model_input(img))
                mask = torch.from_numpy(mask).unsqueeze(0).float()
            else:
                out  = self.test_tf(image=img, mask=mask)
                img  = out["image"]
                mask = out["mask"]
                if mask.dim() == 2:
                    mask = mask.unsqueeze(0).float()
                else:
                    mask = mask.float()

        meta = {"tile_name": row["tile_name"], "site": row["site"],
                "canopy_frac": float(row["canopy_frac"])}
        return img, mask, meta


# ── Model factory ────────────────────────────────────────────────────────────

def _inject_dropout(module, p):
    for name, child in module.named_children():
        if isinstance(child, nn.Sequential):
            child.add_module("dropout", nn.Dropout2d(p=p))
        else:
            _inject_dropout(child, p)


def build_semantic_model(device, pretrained_ckpt=None):
    """
    Build U-Net with sigmoid activation for binary canopy classification.
    Optionally initialise from Phase 0 DTM checkpoint (shared encoder+decoder).
    """
    _ensure_torch()

    # Build model with sigmoid activation (vs None for instance)
    model = smp.Unet(
        encoder_name=ENCODER,
        encoder_weights=ENCODER_WEIGHTS if pretrained_ckpt is None else None,
        decoder_channels=DECODER_CHANNELS,
        in_channels=IN_CHANNELS,
        classes=1,
        activation=None,  # We use BCEWithLogitsLoss so no sigmoid here
    )
    _inject_dropout(model.decoder, DECODER_DROPOUT)

    # Load Phase 0 pretrained weights if available
    if pretrained_ckpt is not None:
        ckpt_path = Path(pretrained_ckpt)
        if ckpt_path.exists():
            ckpt = torch.load(ckpt_path, map_location=device)
            state = ckpt["model_state"]

            # The final segmentation head shape is identical (1 class). With
            # IN_CHANNELS>3 the first conv shape differs, so strict=False skips
            # it (and we transplant it below); everything else loads.
            model.load_state_dict(state, strict=False)
            print(f"  ✓ Loaded Phase 0 weights: {ckpt_path.name}  "
                  f"(epoch={ckpt.get('epoch', '?')}  "
                  f"val={ckpt.get('best_val', '?')})")

            # Adapt the first conv to the extra VI channels: copy the pretrained
            # 3-channel RGB filters into channels 0–2, and initialise each extra
            # channel as the mean of the RGB filters (a sensible warm start that
            # the discriminative-unfreeze stem LR then refines). Without this the
            # Phase 0 first-conv prior would be lost to random init.
            if IN_CHANNELS != 3:
                w_key = "encoder.conv1.weight"
                if w_key in state:
                    src_w = state[w_key]                       # [64,3,7,7]
                    conv1 = model.encoder.conv1
                    if (src_w.shape[0] == conv1.weight.shape[0]
                            and src_w.shape[1] == 3
                            and conv1.weight.shape[1] == IN_CHANNELS):
                        with torch.no_grad():
                            conv1.weight[:, :3] = src_w
                            conv1.weight[:, 3:] = src_w.mean(dim=1, keepdim=True)
                        print(f"  ✓ Adapted conv1 3→{IN_CHANNELS} ch "
                              f"(RGB copied, {IN_CHANNELS-3} VI ch mean-init)")
                    else:
                        print(f"  WARNING: conv1 shape mismatch "
                              f"({tuple(src_w.shape)} vs "
                              f"{tuple(conv1.weight.shape)}) — VI channels random-init")
                else:
                    print(f"  WARNING: '{w_key}' not in checkpoint — "
                          f"VI channels random-init")
        else:
            print(f"  WARNING: {ckpt_path} not found — "
                  f"using ImageNet-only init")

    model = model.to(device)
    model = torch.compile(model)
    return model


# ── Spatial buffer splits (borrowed from Phase 0) ────────────────────────────

def make_spatial_buffer_splits(df, n_folds=5, buffer_px=1024, seed=42):
    """Create K-Fold splits with spatial buffering within each site."""
    from scipy.spatial.distance import cdist

    rng   = np.random.RandomState(seed)
    sites = sorted(df["site"].unique())

    fold_assignments = np.full(len(df), -1, dtype=int)
    for site in sites:
        site_indices = np.where(df["site"] == site)[0]
        shuffled = rng.permutation(site_indices)
        for i, idx in enumerate(shuffled):
            fold_assignments[idx] = i % n_folds

    folds = []
    for fold in range(n_folds):
        val_indices    = []
        train_indices  = []

        for site in sites:
            site_mask          = df["site"] == site
            site_global_indices = np.where(site_mask)[0]
            site_val_mask      = fold_assignments[site_global_indices] == fold
            site_val_idx       = site_global_indices[site_val_mask]
            site_other_idx     = site_global_indices[~site_val_mask]

            if len(site_val_idx) == 0:
                train_indices.extend(site_other_idx.tolist())
                continue

            val_indices.extend(site_val_idx.tolist())

            if len(site_other_idx) == 0:
                continue

            val_coords   = df.iloc[site_val_idx][["row_off", "col_off"]].values
            other_coords = df.iloc[site_other_idx][["row_off", "col_off"]].values
            dists        = cdist(other_coords, val_coords, metric="chebyshev")
            min_dist     = dists.min(axis=1)

            for i, idx in enumerate(site_other_idx):
                if min_dist[i] >= buffer_px:
                    train_indices.append(idx)
                # else: buffer zone — excluded from both train and val

        folds.append((np.array(train_indices), np.array(val_indices)))
    return folds


# ── Train / val helpers ──────────────────────────────────────────────────────

def _train_one_epoch(model, loader, optimizer, scaler, criterion, device):
    model.train()
    loss_sum = bce_sum = 0.0
    n = 0
    for imgs, masks, _ in loader:
        imgs  = imgs.to(device, non_blocking=True)
        masks = masks.to(device, non_blocking=True)

        optimizer.zero_grad()
        with torch.amp.autocast("cuda"):
            logits = model(imgs)
            bce    = criterion(logits, masks)

        # L1 penalty over *trainable* params only, computed outside autocast
        # in fp32. AdamW already applies weight_decay=1e-4, so this is a small
        # extra sparsity nudge (L1_LAMBDA=1e-6). Set L1_LAMBDA=0 to disable.
        if L1_LAMBDA > 0:
            l1   = sum(p.abs().sum() for p in model.parameters()
                       if p.requires_grad)
            loss = bce + L1_LAMBDA * l1
        else:
            loss = bce

        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        scaler.step(optimizer)
        scaler.update()

        loss_sum += loss.item()
        bce_sum  += bce.item()
        n += 1

    return loss_sum / n, bce_sum / n


def _validate(model, loader, criterion, device):
    model.eval()
    bce_sum = iou_sum = 0.0
    n = 0
    with torch.no_grad():
        for imgs, masks, _ in loader:
            imgs  = imgs.to(device, non_blocking=True)
            masks = masks.to(device, non_blocking=True)

            with torch.amp.autocast("cuda"):
                logits = model(imgs)
                bce    = criterion(logits, masks)

            bce_sum += bce.item()

            # Compute IoU for monitoring
            probs = torch.sigmoid(logits)
            preds = (probs > 0.5).float()
            inter = (preds * masks).sum()
            union = preds.sum() + masks.sum() - inter
            iou   = (inter / (union + 1e-8)).item()
            iou_sum += iou
            n += 1

    return bce_sum / n, iou_sum / n


# ── Checkpoint helpers ───────────────────────────────────────────────────────

def _save_checkpoint(phase_label, epoch, model, optimizer, scheduler,
                     history, best_val, path):
    model_state = (model._orig_mod.state_dict()
                   if hasattr(model, "_orig_mod") else model.state_dict())
    torch.save({
        "phase": phase_label,
        "epoch": epoch,
        "model_state": model_state,
        "optim_state": optimizer.state_dict(),
        "sched_state": scheduler.state_dict(),
        "history": history,
        "best_val": best_val,
    }, path)


def _load_checkpoint(path, model, optimizer, scheduler, device):
    ckpt = torch.load(path, map_location=device)
    if hasattr(model, "_orig_mod"):
        model._orig_mod.load_state_dict(ckpt["model_state"])
    else:
        model.load_state_dict(ckpt["model_state"])
    optimizer.load_state_dict(ckpt["optim_state"])
    scheduler.load_state_dict(ckpt["sched_state"])
    return ckpt.get("phase", "A"), ckpt["epoch"], ckpt["history"], ckpt["best_val"]


def _freeze_encoder(model):
    """Freeze all encoder parameters for Phase A training."""
    enc = model._orig_mod.encoder if hasattr(model, "_orig_mod") else model.encoder
    for param in enc.parameters():
        param.requires_grad = False
    n_frozen = sum(1 for p in enc.parameters() if not p.requires_grad)
    print(f"  Encoder frozen: {n_frozen} parameter tensors")


def _unfreeze_encoder(model):
    """Unfreeze encoder for Phase B training."""
    enc = model._orig_mod.encoder if hasattr(model, "_orig_mod") else model.encoder
    for param in enc.parameters():
        param.requires_grad = True
    print(f"  Encoder unfrozen — full model training")


# ── Main training loop ──────────────────────────────────────────────────────

def step_train(batch_size=BATCH_SIZE, ckpt_path=None, dry_run=False):
    """
    Two-phase training:
      Phase A — frozen encoder, train decoder only (20 epochs, lr=5e-5)
      Phase B — full model (30 epochs, lr=5e-6)
    No K-Fold CV — single train/val split (spatial buffer).
    """
    _ensure_torch()
    print("\n── Step 3: Semantic Model Training ──")

    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Device: {device}")
    if device.type == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")

    # Load tile index
    index_path = TILE_DIR / "tile_index_semantic.csv"
    if not index_path.exists():
        print(f"  ERROR: {index_path} not found — run step tile first")
        sys.exit(1)

    full_index_df = pd.read_csv(index_path)
    train_df = full_index_df[full_index_df["split"] == "train"].reset_index(drop=True)
    test_df  = full_index_df[full_index_df["split"] == "test"].reset_index(drop=True)
    print(f"  Train tiles: {len(train_df)}  |  "
          f"Test tiles (held out): {len(test_df)}")

    if dry_run:
        print("  Dry run — not training")
        return

    # Spatial buffer split (use fold 0 as the single val split)
    folds = make_spatial_buffer_splits(
        train_df, n_folds=5, buffer_px=SPATIAL_BUFFER_PX, seed=42)
    train_idx, val_idx = folds[0]  # Use first fold only

    fold_train_df = train_df.iloc[train_idx].reset_index(drop=True)
    fold_val_df   = train_df.iloc[val_idx].reset_index(drop=True)
    print(f"  Train split: {len(fold_train_df)}  |  "
          f"Val split: {len(fold_val_df)}  "
          f"(buffer excluded: "
          f"{len(train_df) - len(fold_train_df) - len(fold_val_df)})")

    # Weighted sampler for site balance
    pin_memory     = device.type == "cuda"
    site_counts    = fold_train_df["site"].value_counts().to_dict()
    sample_weights = fold_train_df["site"].map(
        lambda s: 1.0 / site_counts[s]).values.astype(np.float32)
    sampler = WeightedRandomSampler(
        weights=torch.from_numpy(sample_weights),
        num_samples=len(fold_train_df), replacement=True)

    train_ds = SemanticDataset(fold_train_df, training=True)
    val_ds   = SemanticDataset(fold_val_df,   training=False)

    train_loader = DataLoader(
        train_ds, batch_size=batch_size, sampler=sampler,
        num_workers=NUM_WORKERS, pin_memory=pin_memory,
        drop_last=True, persistent_workers=True, prefetch_factor=4)
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=pin_memory,
        drop_last=False, persistent_workers=True, prefetch_factor=4)

    # Resolve Phase 0 checkpoint for weight initialisation
    p0_ckpt = ckpt_path
    if p0_ckpt is None:
        p0_ckpt = CKPT_DIR_P0 / "ddt_best_v7_global.pt"
        if not p0_ckpt.exists():
            # Try fold checkpoints
            for fold in [3, 1, 2, 4, 5]:
                p = CKPT_DIR_P0 / f"ddt_best_v7_fold{fold}.pt"
                if p.exists():
                    p0_ckpt = p
                    break
    if p0_ckpt is not None and not Path(p0_ckpt).exists():
        p0_ckpt = None

    # Build model
    model = build_semantic_model(device, pretrained_ckpt=p0_ckpt)

    criterion = nn.BCEWithLogitsLoss()

    # Output paths
    best_ckpt   = CKPT_DIR / "sem_best_2020.pt"
    latest_ckpt = CKPT_DIR / "sem_latest_2020.pt"

    best_val    = float("inf")
    history     = {"phase": [], "epoch": [], "train_bce": [],
                   "val_bce": [], "val_iou": []}

    # ─── Phase A: frozen encoder ─────────────────────────────
    print(f"\n{'='*65}")
    print(f"  PHASE A — Frozen Encoder  |  {EPOCHS_PHASE_A} epochs  "
          f"|  LR={LR_PHASE_A}")
    print(f"{'='*65}")

    _freeze_encoder(model)

    # Only optimise parameters that require grad
    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer_a = torch.optim.AdamW(trainable_params, lr=LR_PHASE_A,
                                     weight_decay=1e-4)
    scheduler_a = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer_a, mode="min", factor=0.5, patience=5,
        threshold=1e-4, cooldown=2, min_lr=1e-7)
    scaler_a    = torch.amp.GradScaler("cuda")

    es_counter = 0

    for epoch in range(EPOCHS_PHASE_A):
        t0 = time.time()
        train_loss, train_bce = _train_one_epoch(
            model, train_loader, optimizer_a, scaler_a, criterion, device)
        val_bce, val_iou = _validate(model, val_loader, criterion, device)

        scheduler_a.step(val_bce)
        lr = optimizer_a.param_groups[0]["lr"]

        history["phase"].append("A")
        history["epoch"].append(epoch + 1)
        history["train_bce"].append(train_bce)
        history["val_bce"].append(val_bce)
        history["val_iou"].append(val_iou)

        is_best = val_bce < best_val
        if is_best:
            best_val   = val_bce
            es_counter = 0
            _save_checkpoint("A", epoch, model, optimizer_a,
                             scheduler_a, history, best_val, best_ckpt)
        else:
            es_counter += 1

        if (epoch + 1) % SAVE_EVERY == 0 or epoch == EPOCHS_PHASE_A - 1:
            _save_checkpoint("A", epoch, model, optimizer_a,
                             scheduler_a, history, best_val, latest_ckpt)

        elapsed = time.time() - t0
        bmark   = " ★" if is_best else ""
        es_info = (f"  [no improve: {es_counter}/{EARLY_STOP_PAT}]"
                   if not is_best else "")

        print(f"  A E{epoch+1:>3}/{EPOCHS_PHASE_A}  "
              f"tr_bce={train_bce:.4f}  val_bce={val_bce:.4f}  "
              f"val_iou={val_iou:.4f}  lr={lr:.2e}  "
              f"{elapsed:.0f}s{bmark}{es_info}")

        if es_counter >= EARLY_STOP_PAT:
            print(f"\n  Early stop — Phase A")
            break

    print(f"  ✓ Phase A best val BCE: {best_val:.4f}")

    # ─── Phase B: full model ─────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  PHASE B — Full Model  |  {EPOCHS_PHASE_B} epochs  "
          f"|  LR={LR_PHASE_B}")
    print(f"{'='*65}")

    _unfreeze_encoder(model)

    # New optimizer with lower LR for entire model
    optimizer_b = torch.optim.AdamW(model.parameters(), lr=LR_PHASE_B,
                                     weight_decay=1e-4)
    scheduler_b = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer_b, mode="min", factor=0.5, patience=5,
        threshold=1e-4, cooldown=2, min_lr=1e-7)
    scaler_b    = torch.amp.GradScaler("cuda")

    es_counter = 0

    for epoch in range(EPOCHS_PHASE_B):
        t0 = time.time()
        train_loss, train_bce = _train_one_epoch(
            model, train_loader, optimizer_b, scaler_b, criterion, device)
        val_bce, val_iou = _validate(model, val_loader, criterion, device)

        scheduler_b.step(val_bce)
        lr = optimizer_b.param_groups[0]["lr"]

        history["phase"].append("B")
        history["epoch"].append(epoch + 1)
        history["train_bce"].append(train_bce)
        history["val_bce"].append(val_bce)
        history["val_iou"].append(val_iou)

        is_best = val_bce < best_val
        if is_best:
            best_val   = val_bce
            es_counter = 0
            _save_checkpoint("B", epoch, model, optimizer_b,
                             scheduler_b, history, best_val, best_ckpt)
        else:
            es_counter += 1

        if (epoch + 1) % SAVE_EVERY == 0 or epoch == EPOCHS_PHASE_B - 1:
            _save_checkpoint("B", epoch, model, optimizer_b,
                             scheduler_b, history, best_val, latest_ckpt)

        elapsed = time.time() - t0
        bmark   = " ★" if is_best else ""
        es_info = (f"  [no improve: {es_counter}/{EARLY_STOP_PAT}]"
                   if not is_best else "")

        print(f"  B E{epoch+1:>3}/{EPOCHS_PHASE_B}  "
              f"tr_bce={train_bce:.4f}  val_bce={val_bce:.4f}  "
              f"val_iou={val_iou:.4f}  lr={lr:.2e}  "
              f"{elapsed:.0f}s{bmark}{es_info}")

        if es_counter >= EARLY_STOP_PAT:
            print(f"\n  Early stop — Phase B")
            break

    print(f"\n  ✓ Phase B best val BCE: {best_val:.4f}")
    print(f"  Best checkpoint: {best_ckpt}")

    # Save loss history
    pd.DataFrame(history).to_csv(
        CKPT_DIR / "sem_loss_history.csv", index=False)

    del model, optimizer_a, optimizer_b, scaler_a, scaler_b
    if device.type == "cuda":
        torch.cuda.empty_cache()


# ═════════════════════════════════════════════════════════════════════════════
#  Step 4 — Evaluation
# ═════════════════════════════════════════════════════════════════════════════

def step_evaluate(ckpt_path=None, dry_run=False):
    """Evaluate semantic model on held-out test tiles.
    Metrics: pixel accuracy, IoU, Dice, precision, recall."""
    _ensure_torch()
    print("\n── Step 4: Semantic Evaluation on Test Tiles ──")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    index_path = TILE_DIR / "tile_index_semantic.csv"
    if not index_path.exists():
        print(f"  ERROR: {index_path} not found — run step tile first")
        return
    index_df = pd.read_csv(index_path)
    test_df  = index_df[index_df["split"] == "test"].reset_index(drop=True)
    print(f"  Test tiles: {len(test_df)}")

    if dry_run:
        print("  Dry run — not evaluating")
        return

    # Load model
    if ckpt_path is None:
        ckpt_path = CKPT_DIR / "sem_best_2020.pt"
    if not Path(ckpt_path).exists():
        print(f"  ERROR: {ckpt_path} not found — run training first")
        return

    model = smp.Unet(
        encoder_name=ENCODER, encoder_weights=None,
        decoder_channels=DECODER_CHANNELS, in_channels=IN_CHANNELS,
        classes=1, activation=None)
    model = model.to(device)
    ckpt  = torch.load(ckpt_path, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    print(f"  Model: {Path(ckpt_path).name}  "
          f"(phase={ckpt.get('phase', '?')}  "
          f"epoch={ckpt.get('epoch', '?')+1}  "
          f"val={ckpt.get('best_val', '?'):.4f})  in_ch={IN_CHANNELS}")

    eval_tf = A.Compose([
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD,
                    max_pixel_value=255.0),
        ToTensorV2(),
    ])

    # Accumulate confusion matrix elements
    total_tp = total_fp = total_fn = total_tn = 0
    site_metrics = {}
    all_prob, all_gt = [], []   # for threshold-independent metrics

    with torch.no_grad():
        for _, row in tqdm(test_df.iterrows(), total=len(test_df),
                           desc="  Evaluating"):
            with rasterio.open(row["img_path"]) as src:
                img = src.read().transpose(1, 2, 0)
            with rasterio.open(row["mask_path"]) as src:
                gt = src.read(1).astype(np.float32)

            if USE_VI:
                inp = torch.from_numpy(rgb_to_model_input(img)).unsqueeze(0).to(device)
            else:
                inp = eval_tf(image=img)["image"].unsqueeze(0).to(device)
            logit = model(inp).squeeze().cpu().numpy()
            prob  = 1.0 / (1.0 + np.exp(-logit))  # sigmoid
            pred  = (prob > CANOPY_PROB_THRESHOLD).astype(np.uint8)

            all_prob.append(prob.ravel().astype(np.float32))
            all_gt.append(gt.ravel().astype(np.int8))

            # Confusion matrix
            tp = int(((pred == 1) & (gt == 1)).sum())
            fp = int(((pred == 1) & (gt == 0)).sum())
            fn = int(((pred == 0) & (gt == 1)).sum())
            tn = int(((pred == 0) & (gt == 0)).sum())

            total_tp += tp
            total_fp += fp
            total_fn += fn
            total_tn += tn

            site = row["site"]
            if site not in site_metrics:
                site_metrics[site] = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
            site_metrics[site]["tp"] += tp
            site_metrics[site]["fp"] += fp
            site_metrics[site]["fn"] += fn
            site_metrics[site]["tn"] += tn

    # Compute metrics
    def _metrics(tp, fp, fn, tn):
        total     = tp + fp + fn + tn
        accuracy  = (tp + tn) / total if total > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1        = (2 * precision * recall / (precision + recall)
                     if (precision + recall) > 0 else 0)
        iou       = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0
        dice      = 2 * tp / (2 * tp + fp + fn) if (2*tp + fp + fn) > 0 else 0
        return {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "iou": round(iou, 4),
            "dice": round(dice, 4),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        }

    overall = _metrics(total_tp, total_fp, total_fn, total_tn)

    # Threshold-independent metrics over all test pixels (compare models without
    # being hostage to the 0.5 cutoff; best-F1 threshold also flags over/under-
    # prediction at a glance).
    ti = {}
    try:
        import sklearn.metrics as skm
        y_prob = np.concatenate(all_prob)
        y_true = np.concatenate(all_gt)
        ti["auroc"]    = float(skm.roc_auc_score(y_true, y_prob))
        ti["ap"]       = float(skm.average_precision_score(y_true, y_prob))
        ti["log_loss"] = float(skm.log_loss(y_true, y_prob, labels=[0, 1]))
        prec_c, rec_c, thr_c = skm.precision_recall_curve(y_true, y_prob)
        f1_c = 2 * prec_c * rec_c / (prec_c + rec_c + 1e-12)
        bi = int(np.argmax(f1_c[:-1])) if len(thr_c) else 0
        ti["best_f1"]        = float(f1_c[bi])
        ti["best_f1_thresh"] = float(thr_c[bi]) if len(thr_c) else CANOPY_PROB_THRESHOLD
        del y_prob, y_true
    except Exception as e:
        print(f"  WARNING: threshold-independent metrics failed ({e})")

    print(f"\n{'='*62}")
    print(f"  SEMANTIC EVALUATION  (threshold={CANOPY_PROB_THRESHOLD})")
    print(f"{'='*62}")
    print(f"\n  {'Metric':<12} {'Value':>8}")
    print(f"  {'-'*12} {'-'*8}")
    for k in ["accuracy", "precision", "recall", "f1", "iou", "dice"]:
        print(f"  {k:<12} {overall[k]:>8.4f}")

    print(f"\n  Confusion matrix:")
    print(f"    TP={total_tp:>10,}  FP={total_fp:>10,}")
    print(f"    FN={total_fn:>10,}  TN={total_tn:>10,}")

    if ti:
        print(f"\n  Threshold-independent (all test pixels):")
        print(f"    AUROC            {ti['auroc']:.4f}")
        print(f"    Avg precision    {ti['ap']:.4f}")
        print(f"    Log-loss         {ti['log_loss']:.4f}")
        print(f"    Best-F1 @ thresh {ti['best_f1_thresh']:.3f}  "
              f"(F1={ti['best_f1']:.4f}  vs  {overall['f1']:.4f} @ 0.50)")

    # Per-site metrics
    print(f"\n  {'Site':<20} {'Acc':>7} {'IoU':>7} {'Dice':>7} "
          f"{'Prec':>7} {'Rec':>7}")
    print(f"  {'-'*20} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")

    report_rows = []
    for site in sorted(site_metrics):
        sm = site_metrics[site]
        m  = _metrics(sm["tp"], sm["fp"], sm["fn"], sm["tn"])
        print(f"  {site:<20} {m['accuracy']:>7.4f} {m['iou']:>7.4f} "
              f"{m['dice']:>7.4f} {m['precision']:>7.4f} {m['recall']:>7.4f}")
        report_rows.append({"site": site, **m})

    report_rows.append({"site": "OVERALL", **overall, **ti})
    eval_df = pd.DataFrame(report_rows)
    eval_df.to_csv(EVAL_CSV, index=False)
    print(f"\n  ✓ Report: {EVAL_CSV}")

    # Copy best checkpoint to phase3 root for convenience
    best_src = CKPT_DIR / "sem_best_2020.pt"
    best_dst = OUT_DIR / "sem_best_2020.pt"
    if best_src.exists() and not best_dst.exists():
        shutil.copy2(best_src, best_dst)
        print(f"  ✓ Copied best model → {best_dst}")

    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()


# ═════════════════════════════════════════════════════════════════════════════
#  Step 5 — Full-City Streaming Inference
# ═════════════════════════════════════════════════════════════════════════════

def step_inference(ckpt_path=None, batch_size=INFER_BATCH_SIZE, dry_run=False):
    """Streaming tiled inference over full Edmonds 2020 imagery.
    Outputs a canopy probability raster (float32, 0–1)."""
    _ensure_torch()
    print("\n── Step 5: Full-City Semantic Inference ──")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()

    if not EDMONDS_IMG.exists():
        print(f"  ERROR: {EDMONDS_IMG} not found")
        return

    with rasterio.open(EDMONDS_IMG) as src:
        img_h   = src.height
        img_w   = src.width
        img_crs = src.crs
        img_tf  = src.transform
        px_x    = src.transform.a
        px_y    = abs(src.transform.e)

    print(f"  Image: {img_w}×{img_h} px  "
          f"({img_w*px_x/1000:.1f}×{img_h*px_y/1000:.1f} km)")

    if dry_run:
        print("  Dry run — not running inference")
        return

    # Load model
    if ckpt_path is None:
        ckpt_path = CKPT_DIR / "sem_best_2020.pt"
        if not ckpt_path.exists():
            ckpt_path = OUT_DIR / "sem_best_2020.pt"
    if not Path(ckpt_path).exists():
        print(f"  ERROR: {ckpt_path} not found — run training first")
        return

    model = smp.Unet(
        encoder_name=ENCODER, encoder_weights=None,
        decoder_channels=DECODER_CHANNELS, in_channels=IN_CHANNELS,
        classes=1, activation=None)
    model = model.to(device)
    ckpt  = torch.load(ckpt_path, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    print(f"  Model: {Path(ckpt_path).name}  "
          f"(phase={ckpt.get('phase', '?')}  "
          f"val_bce={ckpt.get('best_val', '?'):.4f})")

    transform_fn = A.Compose([
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD,
                    max_pixel_value=255.0),
        ToTensorV2(),
    ])

    # Build tile origins (same pattern as Phase 0 Step 9)
    stride      = INFER_STRIDE
    pad         = INFER_PAD
    center_crop = stride

    tile_origins = [
        (r, c)
        for r in range(0, img_h, stride)
        for c in range(0, img_w, stride)
    ]
    # Edge coverage
    if tile_origins[-1][0] + stride < img_h:
        for c in range(0, img_w, stride):
            tile_origins.append((img_h - TILE_SIZE, c))
    if tile_origins[-1][1] + stride < img_w:
        for r in range(0, img_h, stride):
            tile_origins.append((r, img_w - TILE_SIZE))
    tile_origins.append((img_h - TILE_SIZE, img_w - TILE_SIZE))
    tile_origins = sorted(set(tile_origins))

    print(f"  Tile positions: {len(tile_origins):,}  |  batch={batch_size}")

    # Output: probability raster, quantised to uint8 (value/255 ↔ prob 0–1) to
    # keep the file ~4× smaller and far more compressible than float32. 1/255
    # resolution is invisible to a 0.5 threshold. No nodata: the tiling covers
    # every pixel and 255 is a valid probability.
    prob_profile = {
        "driver": "GTiff", "dtype": "uint8",
        "width": img_w, "height": img_h, "count": 1,
        "crs": img_crs, "transform": img_tf,
        "compress": "lzw", "BIGTIFF": "YES",
    }

    batch_imgs   = []
    batch_coords = []

    def flush(batch_imgs, batch_coords, dst):
        if not batch_imgs:
            return
        inp = torch.stack(batch_imgs).to(device)
        with torch.no_grad():
            logits = model(inp).squeeze(1).cpu().numpy()
        probs = 1.0 / (1.0 + np.exp(-logits))  # sigmoid

        for k, (ro, co) in enumerate(batch_coords):
            center = probs[k, pad:pad+center_crop, pad:pad+center_crop]
            cr_end = min(ro + center_crop, img_h)
            cc_end = min(co + center_crop, img_w)
            ch, cw = cr_end - ro, cc_end - co
            win    = rasterio.windows.Window(
                col_off=co, row_off=ro, width=cw, height=ch)
            crop = (center[:ch, :cw] * 255.0).round().clip(0, 255).astype(np.uint8)
            dst.write(crop[np.newaxis], window=win)

    tick("inference")

    with rasterio.open(PROB_OUT, "w", **prob_profile) as dst:
        with rasterio.open(EDMONDS_IMG) as src:
            pbar = tqdm(total=len(tile_origins), desc="  Inference",
                        unit="tile", miniters=3000, mininterval=2.0)

            for row_off, col_off in tile_origins:
                r_start = row_off - pad
                c_start = col_off - pad
                r_end   = r_start + TILE_SIZE
                c_end   = c_start + TILE_SIZE

                read_r0 = max(0, r_start)
                read_c0 = max(0, c_start)
                read_r1 = min(img_h, r_end)
                read_c1 = min(img_w, c_end)

                window = rasterio.windows.Window(
                    col_off=read_c0, row_off=read_r0,
                    width=read_c1-read_c0, height=read_r1-read_r0)
                tile = src.read([1, 2, 3], window=window).transpose(1, 2, 0)

                ph_top   = read_r0 - r_start
                ph_bot   = r_end   - read_r1
                pw_left  = read_c0 - c_start
                pw_right = c_end   - read_c1
                if any([ph_top, ph_bot, pw_left, pw_right]):
                    tile = np.pad(tile,
                                  ((ph_top, ph_bot),
                                   (pw_left, pw_right), (0, 0)),
                                  mode="reflect")

                aug = transform_fn(image=tile)
                if USE_VI:
                    batch_imgs.append(torch.from_numpy(rgb_to_model_input(tile)))
                else:
                    batch_imgs.append(aug["image"])
                batch_coords.append((row_off, col_off))

                if len(batch_imgs) == batch_size:
                    flush(batch_imgs, batch_coords, dst)
                    batch_imgs   = []
                    batch_coords = []

                pbar.update(1)
            pbar.close()

            flush(batch_imgs, batch_coords, dst)

    tock("inference")
    prob_mb = PROB_OUT.stat().st_size / 1e6
    print(f"\n  ✓ Probability raster: {PROB_OUT}  ({prob_mb:.0f} MB)")

    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()


# ═════════════════════════════════════════════════════════════════════════════
#  Step 6 — Post-Processing (threshold → morphology → polygonize)
# ═════════════════════════════════════════════════════════════════════════════

def step_postproc(dry_run=False):
    """Threshold probability raster → binary mask → morphology → GeoPackage."""
    from scipy.ndimage import binary_opening, binary_closing

    print("\n── Step 6: Post-Processing ──")

    if not PROB_OUT.exists():
        print(f"  ERROR: {PROB_OUT} not found — run inference first")
        return

    with rasterio.open(PROB_OUT) as src:
        img_h     = src.height
        img_w     = src.width
        img_crs   = src.crs
        img_tf    = src.transform
        px_x      = src.transform.a
        px_y      = abs(src.transform.e)
        pixel_area = px_x * px_y

    min_px = int(np.ceil(MIN_CANOPY_PATCH / pixel_area))
    print(f"  Threshold:       {CANOPY_PROB_THRESHOLD}")
    print(f"  Min patch:       {MIN_CANOPY_PATCH} m² ({min_px} px)")
    print(f"  Morph kernel:    {MORPH_KERNEL_SIZE}×{MORPH_KERNEL_SIZE}")
    print(f"  Raster:          {img_w}×{img_h} px")

    if dry_run:
        print("  Dry run — not processing")
        return

    tick("postproc")

    # Process in chunks to manage memory
    CHUNK_ROWS = 4096
    kernel = np.ones((MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE), dtype=bool)

    mask_profile = {
        "driver": "GTiff", "dtype": "uint8",
        "width": img_w, "height": img_h, "count": 1,
        "crs": img_crs, "transform": img_tf,
        "compress": "lzw", "nodata": 255, "BIGTIFF": "YES",
    }

    total_canopy_px = 0

    with rasterio.open(PROB_OUT) as src, \
         rasterio.open(MASK_OUT, "w", **mask_profile) as dst:

        for r0 in tqdm(range(0, img_h, CHUNK_ROWS), desc="  Thresholding"):
            r1 = min(r0 + CHUNK_ROWS, img_h)
            window = rasterio.windows.Window(
                col_off=0, row_off=r0, width=img_w, height=r1 - r0)
            prob_chunk = src.read(1, window=window)

            # Threshold. Prob raster is uint8 (value/255 ↔ 0–1), so scale cutoff.
            mask_chunk = (prob_chunk >= CANOPY_PROB_THRESHOLD * 255).astype(np.uint8)

            # Morphological opening (remove noise)
            mask_chunk = binary_opening(mask_chunk, structure=kernel).astype(np.uint8)
            # Morphological closing (fill small gaps)
            mask_chunk = binary_closing(mask_chunk, structure=kernel).astype(np.uint8)

            total_canopy_px += mask_chunk.sum()
            dst.write(mask_chunk[np.newaxis], window=window)

    total_px      = img_h * img_w
    canopy_area   = total_canopy_px * pixel_area
    canopy_pct    = 100 * total_canopy_px / total_px

    mask_mb = MASK_OUT.stat().st_size / 1e6
    print(f"\n  ✓ Binary mask: {MASK_OUT}  ({mask_mb:.0f} MB)")
    print(f"  Canopy pixels:  {total_canopy_px:,} / {total_px:,}  "
          f"({canopy_pct:.1f}%)")
    print(f"  Canopy area:    {canopy_area/1e4:.1f} ha  "
          f"({canopy_area/1e6:.3f} km²)")

    # ── Polygonize ───────────────────────────────────────────
    print(f"\n  Polygonizing canopy mask...")
    tick("polygonize")

    import fiona
    import fiona.crs

    schema = {
        "geometry": "Polygon",
        "properties": {
            "canopy_id": "str",
            "area_m2":   "float",
        },
    }

    n_polys = 0
    with rasterio.open(MASK_OUT) as src:
        mask_data = src.read(1)

    # Sieve: drop connected components smaller than the min-patch size (and fill
    # sub-threshold holes) at the raster level, on 8-connectivity so diagonally
    # touching canopy stays one component. Cleaner and far fewer polygons for
    # shapes() to walk than polygonizing every speckle and filtering after.
    clean = rasterio.features.sieve(
        mask_data, size=min_px, connectivity=POLYGON_CONNECTIVITY)
    del mask_data
    gc.collect()

    shapes_gen = rasterio.features.shapes(
        clean, mask=(clean == 1), transform=img_tf,
        connectivity=POLYGON_CONNECTIVITY)

    with fiona.open(CANOPY_GPKG, "w", driver="GPKG",
                    crs=img_crs.to_wkt(), schema=schema) as dst:
        for geom_dict, value in tqdm(shapes_gen, desc="  Polygonizing",
                                      mininterval=5.0):
            poly = shape(geom_dict)

            # Collapse the pixel staircase, then repair if simplify self-intersects.
            if SIMPLIFY_TOLERANCE_M > 0:
                poly = poly.simplify(SIMPLIFY_TOLERANCE_M,
                                     preserve_topology=True)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue

            # buffer(0) can yield a MultiPolygon — write each part separately
            # so the GeoPackage stays single-Polygon per the schema.
            parts = (list(poly.geoms)
                     if poly.geom_type == "MultiPolygon" else [poly])
            for part in parts:
                area = part.area
                if area < MIN_CANOPY_PATCH:
                    continue
                dst.write({
                    "geometry": mapping(part),
                    "properties": {
                        "canopy_id": f"CAN_{n_polys:07d}",
                        "area_m2":   round(area, 2),
                    },
                })
                n_polys += 1

    tock("polygonize")
    gpkg_mb = CANOPY_GPKG.stat().st_size / 1e6
    print(f"\n  ✓ Canopy GeoPackage: {CANOPY_GPKG}  ({gpkg_mb:.0f} MB)")
    print(f"  Canopy polygons: {n_polys:,}")

    tock("postproc")


# ═════════════════════════════════════════════════════════════════════════════
#  Step 7 — Cross-Validation (Semantic vs Instance)
# ═════════════════════════════════════════════════════════════════════════════

def _raster_crossval_overlap(instance_gdf, mask_path, chunk_rows=4096):
    """Dissolved-footprint overlap between Phase 0 instance crowns and the
    Phase 3 binary canopy mask, computed on the mask grid in row-band chunks.

    Replaces the vector unary_union/intersection/union path (single-threaded
    GEOS over the ~1 GB polygon layer, ~30 min with no progress output). The
    mask is already the dissolved semantic footprint; rasterizing every crown
    to value 1 dissolves the instance footprint the same way — so overlapping
    crowns are not double-counted. Returns dissolved areas (ha), the
    intersection area (ha), and the three overlap ratios.
    """
    with rasterio.open(mask_path) as src:
        img_h, img_w = src.height, src.width
        mask_tf      = src.transform
        mask_crs     = src.crs
    px_x       = mask_tf.a
    px_y       = abs(mask_tf.e)
    pixel_area = px_x * px_y

    # Crowns must sit on the mask CRS before bbox-querying / rasterizing.
    if instance_gdf.crs is not None and mask_crs is not None \
            and instance_gdf.crs != mask_crs:
        instance_gdf = instance_gdf.to_crs(mask_crs)
    _ = instance_gdf.sindex  # build spatial index once (used by .cx per chunk)

    inter_px = inst_px = sem_px = 0
    n_chunks = (img_h + chunk_rows - 1) // chunk_rows
    with rasterio.open(mask_path) as src:
        for r0 in tqdm(range(0, img_h, chunk_rows),
                       total=n_chunks, desc="  Overlap (raster)"):
            r1   = min(r0 + chunk_rows, img_h)
            rows = r1 - r0
            win  = rasterio.windows.Window(
                col_off=0, row_off=r0, width=img_w, height=rows)

            # Semantic footprint: mask == 1 (MASK_OUT is 0/1, nodata=255).
            sem = src.read(1, window=win) == 1

            # Instance footprint: rasterize only crowns whose bbox hits this
            # band; rasterize clips them to the window, so a crown spanning a
            # band boundary contributes its pixels to each band exactly once.
            left, bottom, right, top = rasterio.windows.bounds(win, mask_tf)
            sub = instance_gdf.cx[left:right, bottom:top]
            if len(sub):
                win_tf = rasterio.windows.transform(win, mask_tf)
                inst = rasterio.features.rasterize(
                    ((g, 1) for g in sub.geometry),
                    out_shape=(rows, img_w), transform=win_tf,
                    fill=0, dtype="uint8", all_touched=False).astype(bool)
            else:
                inst = np.zeros((rows, img_w), dtype=bool)

            inter_px += int((sem & inst).sum())
            inst_px  += int(inst.sum())
            sem_px   += int(sem.sum())

    union_px     = inst_px + sem_px - inter_px
    spatial_iou  = inter_px / union_px if union_px > 0 else 0.0
    inst_covered = inter_px / inst_px  if inst_px  > 0 else 0.0
    sem_in_inst  = inter_px / sem_px   if sem_px   > 0 else 0.0
    return {
        "instance_area_ha": inst_px  * pixel_area / 1e4,
        "semantic_area_ha": sem_px   * pixel_area / 1e4,
        "inter_area_ha":    inter_px * pixel_area / 1e4,
        "spatial_iou":      spatial_iou,
        "inst_covered":     inst_covered,
        "sem_in_inst":      sem_in_inst,
    }


def step_crossval(dry_run=False):
    """Compare semantic canopy mask vs Phase 0 instance detections.

    Spatial overlap is computed on the mask grid (see _raster_crossval_overlap),
    not via vector unary_union — minutes with a progress bar instead of ~30 min
    of silent GEOS. Areas/IoU are dissolved-footprint quantities, so they differ
    slightly from a polygon-area sum and from the old vector run when crowns
    overlap. The 1 GB semantic gpkg is no longer loaded for the overlap (the
    mask IS the semantic footprint); only its polygon count is read, from file
    metadata.
    """
    print("\n── Step 7: Cross-Validation (Semantic vs Instance) ──")

    if not CANOPY_GPKG.exists():
        print(f"  ERROR: {CANOPY_GPKG} not found — run postproc first")
        return
    if not INSTANCE_CROWNS.exists():
        print(f"  ERROR: {INSTANCE_CROWNS} not found — "
              f"need Phase 0 instance output")
        return
    if not MASK_OUT.exists():
        print(f"  ERROR: {MASK_OUT} not found — run postproc first")
        return

    if dry_run:
        print("  Dry run — not comparing")
        return

    tick("crossval")

    # Instance crowns: needed for the overlap raster + per-crown completeness.
    print(f"  Loading instance crowns...")
    instance_gdf = gpd.read_file(INSTANCE_CROWNS)
    n_instance   = len(instance_gdf)

    # Semantic polygon count only — read from file metadata so we never load /
    # unary_union the 1 GB gpkg. (-1 if neither engine is available.)
    print(f"  Reading semantic polygon count...")
    n_semantic = -1
    try:
        import pyogrio
        n_semantic = int(pyogrio.read_info(str(CANOPY_GPKG)).get("features", -1))
    except Exception:
        try:
            import fiona
            with fiona.open(CANOPY_GPKG) as col:
                n_semantic = len(col)
        except Exception as e:
            print(f"  (semantic polygon count skipped: {e})")

    # ── Raster overlap (replaces vector unary_union) ──────────
    print(f"  Computing spatial overlap on mask grid...")
    ov            = _raster_crossval_overlap(instance_gdf, MASK_OUT)
    instance_area = ov["instance_area_ha"] * 1e4   # m² (dissolved footprint)
    semantic_area = ov["semantic_area_ha"] * 1e4
    ratio         = semantic_area / instance_area if instance_area > 0 else 0
    spatial_iou   = ov["spatial_iou"]
    inst_covered  = ov["inst_covered"]
    sem_in_inst   = ov["sem_in_inst"]

    n_semantic_str = f"{n_semantic:,}" if n_semantic >= 0 else "n/a"
    print(f"\n{'='*62}")
    print(f"  CROSS-VALIDATION: Semantic vs Instance (2020)")
    print(f"  (areas/IoU = dissolved-footprint on mask grid)")
    print(f"{'='*62}")

    print(f"\n  Instance segmentation (Phase 0):")
    print(f"    Crown polygons:  {n_instance:>10,}")
    print(f"    Footprint area:  {instance_area/1e4:>10.1f} ha")

    print(f"\n  Semantic segmentation (Phase 3):")
    print(f"    Canopy polygons: {n_semantic_str:>10}")
    print(f"    Footprint area:  {semantic_area/1e4:>10.1f} ha")

    print(f"\n  Comparison:")
    print(f"    Area ratio (sem/inst): {ratio:.3f}")
    print(f"    Spatial IoU:           {spatial_iou:.4f}")
    print(f"    Instance covered:      {inst_covered:.4f}  "
          f"({100*inst_covered:.1f}%)")
    print(f"    Semantic in instance:  {sem_in_inst:.4f}  "
          f"({100*sem_in_inst:.1f}%)")

    # Per-crown completeness: fraction of each Phase 0 crown the semantic mask
    # actually covers. This is the under-segmentation tracker — clipped crowns
    # (like the shadowed-edge example) barely move pixel-IoU but show up here.
    # Sampled to stay fast over 200k+ crowns; reads small windows of MASK_OUT.
    print(f"\n  Per-crown completeness (semantic coverage of Phase 0 crowns):")
    try:
        from rasterio.features import rasterize as _rasterize
        from rasterio.windows import from_bounds as _from_bounds
        rng     = np.random.default_rng(RANDOM_SEED)
        n_total = len(instance_gdf)
        n_samp  = min(CROWN_COMPLETENESS_SAMPLE, n_total)
        sample  = instance_gdf.iloc[rng.choice(n_total, n_samp, replace=False)]

        covs = []
        with rasterio.open(MASK_OUT) as src:
            if sample.crs is not None and src.crs is not None \
                    and sample.crs != src.crs:
                sample = sample.to_crs(src.crs)
            for geom in sample.geometry:
                minx, miny, maxx, maxy = geom.bounds
                win = _from_bounds(minx, miny, maxx, maxy,
                                   src.transform).round_offsets().round_lengths()
                if win.width < 1 or win.height < 1:
                    continue
                m  = src.read(1, window=win, boundless=True, fill_value=0)
                wt = src.window_transform(win)
                crown = _rasterize([(geom, 1)], out_shape=m.shape,
                                   transform=wt, fill=0, dtype=np.uint8)
                denom = int(crown.sum())
                if denom == 0:
                    continue
                covs.append(float(((m == 1) & (crown == 1)).sum()) / denom)

        covs = np.asarray(covs)
        if len(covs):
            print(f"    Sampled crowns:   {len(covs):,} of {n_total:,}")
            print(f"    Mean coverage:    {covs.mean():.3f}")
            print(f"    Median coverage:  {np.median(covs):.3f}")
            print(f"    ≥90% covered:     {100*(covs >= 0.90).mean():.1f}%")
            print(f"    <50% covered:     {100*(covs <  0.50).mean():.1f}%"
                  f"  (badly under-segmented)")
    except Exception as e:
        print(f"  WARNING: per-crown completeness failed ({e})")

    # Interpretation
    if 0.85 <= ratio <= 1.25:
        verdict = "GOOD — area estimates agree within 25%"
    elif 0.70 <= ratio <= 1.50:
        verdict = "ACCEPTABLE — moderate disagreement, review edge cases"
    else:
        verdict = "INVESTIGATE — significant disagreement"
    print(f"\n  Verdict: {verdict}")

    # Save report
    report = pd.DataFrame([
        {"metric": "instance_n_crowns",    "value": n_instance},
        {"metric": "instance_area_ha",     "value": round(instance_area/1e4, 1)},
        {"metric": "semantic_n_polygons",  "value": n_semantic},
        {"metric": "semantic_area_ha",     "value": round(semantic_area/1e4, 1)},
        {"metric": "area_ratio_sem_inst",  "value": round(ratio, 4)},
        {"metric": "spatial_iou",          "value": round(spatial_iou, 4)},
        {"metric": "instance_covered",     "value": round(inst_covered, 4)},
        {"metric": "semantic_in_instance", "value": round(sem_in_inst, 4)},
    ])
    report.to_csv(CROSSVAL_CSV, index=False)
    print(f"\n  ✓ Report: {CROSSVAL_CSV}")

    tock("crossval")


# ═════════════════════════════════════════════════════════════════════════════
#  Step 8 — Spatial-Honesty Diagnostic  (Problem B: metric trust)
#
#  The held-out TEST split (step_tile) is a *random* stratified split: test
#  tiles are scattered through the same sites the model trained on, so a test
#  tile usually has a training tile as an immediate neighbour. Neighbouring
#  forest tiles are near-duplicates, so the model gets credit for "generalising"
#  to tiles that are effectively copies of ones it saw. Per Ploton 2020 /
#  Roberts 2017 / Valavi blockCV, this inflates IoU/AUROC vs a spatially
#  independent test set.
#
#  This is a DIAGNOSTIC, not a clean fix. A truly honest spatial test needs a
#  spatially-blocked split *and a retrain* (the current model has already seen
#  ~80% of every site's grid). Fold that into the model-experiment retrain:
#  carve the spatial test set first, train sem_best_2020_ft.pt on the rest.
#  Here we instead (1) estimate the spatial-autocorrelation RANGE — the
#  separation beyond which two tiles are ~independent, (2) quantify how badly
#  the random test set violates it, and (3) where independent test tiles exist,
#  report the honest metric beside the inflated one. The estimated range also
#  answers the open question of whether the train/val buffer (SPATIAL_BUFFER_PX
#  = 512 px ≈ 38 m) under-buffers.
# ═════════════════════════════════════════════════════════════════════════════

SPATIAL_EVAL_CSV     = OUT_DIR / "semantic_eval_spatial_report.csv"
SPATIAL_MIN_ISOLATED = 25   # min independent test tiles to bother reporting a metric


def _pixel_size_m(index_df=None):
    """Ground sample distance (m/px). Prefer the mask, fall back to a tile."""
    if MASK_OUT.exists():
        with rasterio.open(MASK_OUT) as src:
            return abs(src.transform.a)
    if index_df is not None and len(index_df):
        with rasterio.open(index_df.iloc[0]["img_path"]) as src:
            return abs(src.transform.a)
    return 0.075  # 7.5 cm fallback


def estimate_autocorr_range(index_df, pixel_size_m, n_bins=25):
    """Empirical semivariogram of per-tile canopy_frac, pooled within sites.

    Tile coordinates (row_off, col_off) are in px; lags are converted to metres.
    The range is the lag at which the semivariance first reaches 95% of the sill
    (≈ the field variance). Canopy structure is the standard surrogate for where
    model error becomes spatially independent (Roberts 2017).
    """
    dists, diffs = [], []
    z_all = []
    for site, sub in index_df.groupby("site"):
        if len(sub) < 3:
            continue
        coords = sub[["row_off", "col_off"]].to_numpy(dtype=float)
        z      = sub["canopy_frac"].to_numpy(dtype=float)
        z_all.append(z)
        iu = np.triu_indices(len(z), k=1)
        d  = np.sqrt(((coords[iu[0]] - coords[iu[1]]) ** 2).sum(axis=1))
        sd = (z[iu[0]] - z[iu[1]]) ** 2
        dists.append(d * pixel_size_m)
        diffs.append(sd)
    if not dists:
        return None
    dists = np.concatenate(dists)
    diffs = np.concatenate(diffs)
    sill  = float(np.var(np.concatenate(z_all)))

    max_lag = float(np.percentile(dists, 95))
    edges   = np.linspace(0, max_lag, n_bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    bin_idx = np.clip(np.digitize(dists, edges) - 1, 0, n_bins - 1)
    gamma   = np.full(n_bins, np.nan)
    counts  = np.zeros(n_bins, dtype=int)
    for b in range(n_bins):
        m = bin_idx == b
        if m.any():
            gamma[b] = 0.5 * diffs[m].mean()
            counts[b] = int(m.sum())

    thr = 0.95 * sill
    rng = None
    for c, g in zip(centers, gamma):
        if not np.isnan(g) and g >= thr:
            rng = float(c)
            break
    return {"centers": centers, "gamma": gamma, "counts": counts,
            "sill": sill, "range_m": rng, "max_lag_m": max_lag}


def _nearest_train_distance(index_df):
    """For each TEST tile: Chebyshev px distance to the nearest TRAIN tile in
    the same site (matches make_spatial_buffer_splits' metric). inf if the site
    has no train tiles."""
    from scipy.spatial.distance import cdist
    out = []
    for site, sub in index_df.groupby("site"):
        te = sub[sub["split"] == "test"]
        if len(te) == 0:
            continue
        tr = sub[sub["split"] == "train"][["row_off", "col_off"]].to_numpy(float)
        tec = te[["row_off", "col_off"]].to_numpy(float)
        if len(tr) == 0:
            d = np.full(len(te), np.inf)
        else:
            d = cdist(tec, tr, metric="chebyshev").min(axis=1)
        te = te.copy()
        te["nn_train_px"] = d
        out.append(te)
    return (pd.concat(out, ignore_index=True) if out
            else index_df[index_df["split"] == "test"].assign(nn_train_px=np.inf))


def _eval_tiles(tile_df, ckpt_path, device, collect_probs=False):
    """Inference + pooled confusion metrics over an arbitrary set of test tiles.
    Mirrors step_evaluate's per-tile logic. Returns the metrics dict or None.
    If collect_probs, also returns AUROC/AP over the pooled pixels."""
    _ensure_torch()
    model = smp.Unet(encoder_name=ENCODER, encoder_weights=None,
                     decoder_channels=DECODER_CHANNELS, in_channels=IN_CHANNELS,
                     classes=1, activation=None).to(device)
    model.load_state_dict(torch.load(ckpt_path, map_location=device)["model_state"])
    model.eval()
    tf = A.Compose([A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD,
                                max_pixel_value=255.0), ToTensorV2()])
    tp = fp = fn = tn = 0
    all_prob, all_gt = [], []
    with torch.no_grad():
        for _, row in tqdm(tile_df.iterrows(), total=len(tile_df),
                           desc="  Held-out eval"):
            with rasterio.open(row["img_path"]) as src:
                img = src.read().transpose(1, 2, 0)
            with rasterio.open(row["mask_path"]) as src:
                gt = src.read(1).astype(np.float32)
            if USE_VI:
                inp = torch.from_numpy(rgb_to_model_input(img)).unsqueeze(0).to(device)
            else:
                inp = tf(image=img)["image"].unsqueeze(0).to(device)
            prob = 1.0 / (1.0 + np.exp(-model(inp).squeeze().cpu().numpy()))
            pred = (prob > CANOPY_PROB_THRESHOLD).astype(np.uint8)
            tp += int(((pred == 1) & (gt == 1)).sum())
            fp += int(((pred == 1) & (gt == 0)).sum())
            fn += int(((pred == 0) & (gt == 1)).sum())
            tn += int(((pred == 0) & (gt == 0)).sum())
            if collect_probs:
                all_prob.append(prob.ravel().astype(np.float32))
                all_gt.append(gt.ravel().astype(np.int8))
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()
    total = tp + fp + fn + tn
    if total == 0:
        return None
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec  = tp / (tp + fn) if (tp + fn) else 0
    out = {
        "n_tiles":  len(tile_df),
        "accuracy": (tp + tn) / total,
        "precision": prec, "recall": rec,
        "f1":  (2 * prec * rec / (prec + rec)) if (prec + rec) else 0,
        "iou": tp / (tp + fp + fn) if (tp + fp + fn) else 0,
        "dice": 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0,
    }
    if collect_probs and all_gt:
        try:
            import sklearn.metrics as skm
            yp = np.concatenate(all_prob); yt = np.concatenate(all_gt)
            if yt.min() != yt.max():   # need both classes present
                out["auroc"] = float(skm.roc_auc_score(yt, yp))
                out["ap"]    = float(skm.average_precision_score(yt, yp))
            del yp, yt
        except Exception:
            pass
    return out


def step_spatialcheck(ckpt_path=None, dry_run=False):
    """Step 8: estimate the autocorrelation range, measure how spatially
    intermixed the test set is, and (where possible) report the honest metric on
    independent test tiles vs the inflated random-split metric."""
    print("\n── Step 8: Spatial-Honesty Diagnostic ──")

    index_path = TILE_DIR / "tile_index_semantic.csv"
    if not index_path.exists():
        print(f"  ERROR: {index_path} not found — run step tile first")
        return
    index_df = pd.read_csv(index_path)
    test_df  = index_df[index_df["split"] == "test"]
    print(f"  Tiles: {len(index_df)} total  |  {len(test_df)} test")

    px_m = _pixel_size_m(index_df)
    tile_m = TILE_STRIDE * px_m
    print(f"  Pixel size: {px_m*100:.2f} cm  |  tile spacing: {tile_m:.1f} m")

    # ── 1. Autocorrelation range ──────────────────────────────
    vg = estimate_autocorr_range(index_df, px_m)
    if vg is None:
        print("  Not enough tiles per site for a variogram — skipping.")
        return
    print(f"\n  Semivariogram of canopy_frac (sill≈{vg['sill']:.4f}):")
    print(f"    {'lag (m)':>9}  {'semivar':>8}  {'pairs':>8}")
    for c, g, n in zip(vg["centers"], vg["gamma"], vg["counts"]):
        if n > 0:
            bar = "█" * int(40 * (g / vg["sill"])) if vg["sill"] > 0 else ""
            print(f"    {c:>9.1f}  {g:>8.4f}  {n:>8,}  {bar}")
    if vg["range_m"] is not None:
        range_m  = vg["range_m"]
        range_px = range_m / px_m
        print(f"\n  Estimated autocorrelation range ≈ {range_m:.0f} m "
              f"({range_px:.0f} px ≈ {range_m/tile_m:.1f} tiles)")
    else:
        range_m  = vg["max_lag_m"]
        range_px = range_m / px_m
        print(f"\n  Semivariance never plateaus within {vg['max_lag_m']:.0f} m — "
              f"range ≥ {range_m:.0f} m (undersampled; treat as a lower bound)")
    if range_px > SPATIAL_BUFFER_PX:
        print(f"  ⚠ Train/val buffer SPATIAL_BUFFER_PX={SPATIAL_BUFFER_PX} px "
              f"(<{range_px:.0f} px) UNDER-buffers — val leaks into train.")
    else:
        print(f"  Train/val buffer SPATIAL_BUFFER_PX={SPATIAL_BUFFER_PX} px "
              f"≥ range — adequate.")

    # ── 2. How intermixed is the test set? ────────────────────
    tdist = _nearest_train_distance(index_df)
    nn    = tdist["nn_train_px"].to_numpy(float)
    n_test = len(nn)
    # Tiles sit on a TILE_STRIDE grid, so a test tile is at minimum one cell
    # (TILE_STRIDE px) from a train tile — "≥512 px" is therefore always ~100%
    # and meaningless. The first real isolation level is ≥2 cells: the entire
    # 8-neighbour ring is train-free.
    ring_clear_px = 2 * TILE_STRIDE
    print(f"\n  Test-tile separation from nearest TRAIN tile "
          f"(grid cell {TILE_STRIDE} px ≈ {tile_m:.0f} m):")
    for b_px, lbl in [(ring_clear_px, f"8-ring clear (≥{2*tile_m:.0f} m)"),
                      (range_px,       f"≥ range ({range_m:.0f} m)")]:
        n_l = int((nn >= b_px).sum())
        print(f"    {lbl:<26} {n_l:>4} / {n_test} ({100*n_l/n_test:.0f}%)")

    # Pick the LARGEST buffer (down to the 8-ring-clear floor) that still leaves
    # ≥ SPATIAL_MIN_ISOLATED tiles, so we report the most-independent metric the
    # split can actually support rather than just giving up.
    chosen_buffer = None
    for B in sorted({range_px, 0.75 * range_px, 0.5 * range_px, ring_clear_px},
                    reverse=True):
        if B >= ring_clear_px and int((nn >= B).sum()) >= SPATIAL_MIN_ISOLATED:
            chosen_buffer = B
            break
    iso   = (tdist[tdist["nn_train_px"] >= chosen_buffer]
             if chosen_buffer else tdist.iloc[0:0])
    n_iso = len(iso)
    fully_independent = chosen_buffer is not None and chosen_buffer >= range_px

    if dry_run:
        print("  Dry run — not running isolated-tile inference.")
        return

    # ── 3. Honest metric on independent test tiles (if enough) ─
    rows = []
    if chosen_buffer is None:
        print(f"\n  Fewer than {SPATIAL_MIN_ISOLATED} test tiles are even "
              f"8-ring-isolated — too few for any honest metric.")
        print(f"  CONCLUSION: the random split can't support a spatial test; "
              f"the reported IoU/AUROC are an upper bound. For a clean number, "
              f"carve a spatially-blocked test set and retrain (fold into the "
              f"sem_best_2020_ft.pt experiment).")
        rows.append({"set": "isolated_test", "n_tiles": 0, "note": "too_few"})
    else:
        if ckpt_path is None:
            ckpt_path = CKPT_DIR / "sem_best_2020.pt"
            if not Path(ckpt_path).exists():
                ckpt_path = OUT_DIR / "sem_best_2020.pt"
        if not Path(ckpt_path).exists():
            print(f"  ERROR: {ckpt_path} not found — run training first")
            return
        _ensure_torch()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        partial = "" if fully_independent else "  [< range: PARTIAL independence]"
        print(f"\n  Evaluating {n_iso} test tiles at buffer ≥ {chosen_buffer:.0f} px "
              f"({chosen_buffer*px_m:.0f} m){partial}...")
        iso_m = _eval_tiles(iso, str(ckpt_path), device)

        # Random-split number for comparison: reuse the existing report if present.
        full_m = None
        if EVAL_CSV.exists():
            ev  = pd.read_csv(EVAL_CSV)
            ovr = ev[ev["site"] == "OVERALL"]
            if len(ovr):
                full_m = {k: float(ovr.iloc[0][k])
                          for k in ["accuracy", "precision", "recall",
                                    "f1", "iou", "dice"] if k in ovr.columns}
                full_m["n_tiles"] = len(test_df)

        print(f"\n{'='*62}")
        print(f"  HONEST (spatial) vs RANDOM-SPLIT test metrics")
        print(f"{'='*62}")
        print(f"  {'metric':<10} {'random':>10} {'isolated':>10} {'Δ':>8}")
        print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*8}")
        for k in ["iou", "dice", "f1", "precision", "recall", "accuracy"]:
            iv = iso_m[k]
            if full_m and k in full_m:
                print(f"  {k:<10} {full_m[k]:>10.4f} {iv:>10.4f} "
                      f"{iv-full_m[k]:>+8.4f}")
            else:
                print(f"  {k:<10} {'n/a':>10} {iv:>10.4f} {'':>8}")
        print(f"\n  Tiles: random={len(test_df)}  isolated={n_iso}")
        if full_m and iso_m["iou"] < full_m.get("iou", iso_m["iou"]):
            print(f"  → Isolated IoU is lower: the random split was inflated by "
                  f"~{full_m['iou']-iso_m['iou']:.3f} IoU from train adjacency.")
        if not fully_independent:
            print(f"  NOTE: buffer {chosen_buffer*px_m:.0f} m < range "
                  f"{range_m:.0f} m, so even these tiles aren't fully "
                  f"independent — the true honest metric would be a bit lower.")
        rows.append({"set": "random_test",   **(full_m or {})})
        rows.append({"set": "isolated_test", **iso_m,
                     "buffer_px": round(chosen_buffer, 1),
                     "fully_independent": fully_independent})

    pd.DataFrame([{"metric": "autocorr_range_m",  "value": round(range_m, 1)},
                  {"metric": "autocorr_range_px",  "value": round(range_px, 1)},
                  {"metric": "sill",               "value": round(vg["sill"], 5)},
                  {"metric": "chosen_buffer_px",
                   "value": round(chosen_buffer, 1) if chosen_buffer else -1},
                  {"metric": "n_isolated_test",    "value": n_iso},
                  {"metric": "fully_independent",  "value": bool(fully_independent)},
                  {"metric": "trainval_buffer_adequate",
                   "value": bool(SPATIAL_BUFFER_PX >= range_px)}]
                 ).to_csv(SPATIAL_EVAL_CSV, index=False)
    if rows:
        pd.DataFrame(rows).to_csv(
            OUT_DIR / "semantic_eval_spatial_metrics.csv", index=False)
    print(f"\n  ✓ Report: {SPATIAL_EVAL_CSV}")


# ═════════════════════════════════════════════════════════════════════════════
#  Step 9 — Leave-One-Site-Out (LOSO) Training + Honest Evaluation
#
#  The spatial diagnostic (step 8) showed the canopy autocorrelation range
#  (~250–520 m) dwarfs the tile size, so the random train/test split can't give
#  an honest generalisation estimate — the only independent blocking unit is the
#  SITE. This step rotates through the positive (forest) sites: each fold trains
#  on the other forests (+ all true-negative sites), validates on one held-out
#  forest (for early stopping / model selection), and TESTS on a different
#  held-out forest the model never saw. The mean ± sd across folds is the
#  defensible 2020 number.
#
#  It runs under whatever architecture the flags set:
#    --vi                 add GCC/GRVI/ExG channels  (IN_CHANNELS=6)
#    --unfreeze discriminative   stem+layer3/4 + decoder, per-layer LRs, warmup
#  so a baseline LOSO run and an experiment LOSO run are directly comparable.
#
#  Never overwrites sem_best_2020.pt. Per-fold checkpoints: sem_ft_fold_<site>.pt.
#  `--fold ALL` instead trains ONE deployable model on every site (val = a held-
#  out forest for early stopping) → sem_best_2020_ft.pt, with no test fold.
# ═════════════════════════════════════════════════════════════════════════════


def _phase_b_optimizer(model, base):
    """Build the Phase-B optimizer + scheduler per UNFREEZE_MODE.

    discriminative: freeze the encoder, then unfreeze only the input stem
      (conv1/bn1 — required for the new VI channels) and the late blocks
      (layer3/layer4), plus the decoder/head. Two param groups with per-layer
      LRs (decoder ≫ late encoder), and a linear-warmup→cosine schedule
      (slanted-triangular; wires the previously-dead WARMUP_EPOCHS).
    full: the original behaviour — unfreeze everything at LR_PHASE_B with
      ReduceLROnPlateau.
    Returns (optimizer, scheduler, steps_on_val) where steps_on_val=True means
    scheduler.step(val_bce) (plateau) vs scheduler.step() (epoch schedule).
    """
    if UNFREEZE_MODE == "discriminative":
        enc = base.encoder
        for p in enc.parameters():
            p.requires_grad = False
        for nm in ("conv1", "bn1", "layer3", "layer4"):
            m = getattr(enc, nm, None)
            if m is not None:
                for p in m.parameters():
                    p.requires_grad = True
        dec_params = ([p for p in base.decoder.parameters()] +
                      [p for p in base.segmentation_head.parameters()])
        enc_params = [p for p in enc.parameters() if p.requires_grad]
        n_dec = sum(p.numel() for p in dec_params)
        n_enc = sum(p.numel() for p in enc_params)
        print(f"  Discriminative unfreeze: decoder/head {n_dec/1e6:.1f}M @ "
              f"{LR_DECODER_B:.0e}  +  stem+layer3/4 {n_enc/1e6:.1f}M @ "
              f"{LR_ENC_LATE_B:.0e}  (layer1/2 frozen)  warmup={WARMUP_EPOCHS}ep")
        opt = torch.optim.AdamW(
            [{"params": dec_params, "lr": LR_DECODER_B},
             {"params": enc_params, "lr": LR_ENC_LATE_B}], weight_decay=1e-4)

        def lr_lambda(e):
            if e < WARMUP_EPOCHS:
                return float(e + 1) / max(1, WARMUP_EPOCHS)
            prog = (e - WARMUP_EPOCHS) / max(1, EPOCHS_PHASE_B - WARMUP_EPOCHS)
            return float(0.5 * (1.0 + np.cos(np.pi * min(1.0, prog))))

        sch = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)
        return opt, sch, False
    else:
        _unfreeze_encoder(model)
        opt = torch.optim.AdamW(model.parameters(), lr=LR_PHASE_B,
                                weight_decay=1e-4)
        sch = torch.optim.lr_scheduler.ReduceLROnPlateau(
            opt, mode="min", factor=0.5, patience=5,
            threshold=1e-4, cooldown=2, min_lr=1e-7)
        return opt, sch, True


def _train_one_fold(train_df, val_df, out_ckpt, p0_ckpt, batch_size, device,
                    label):
    """Two-phase fine-tune for one LOSO fold (or the deployable ALL model).
    Saves the best (lowest val-BCE) checkpoint to out_ckpt. Returns best_val."""
    _ensure_torch()
    pin = device.type == "cuda"

    site_counts = train_df["site"].value_counts().to_dict()
    w = train_df["site"].map(lambda s: 1.0 / site_counts[s]).values.astype(np.float32)
    sampler = WeightedRandomSampler(torch.from_numpy(w), len(train_df),
                                    replacement=True)
    train_loader = DataLoader(
        SemanticDataset(train_df, training=True), batch_size=batch_size,
        sampler=sampler, num_workers=NUM_WORKERS, pin_memory=pin,
        drop_last=True, persistent_workers=True, prefetch_factor=4)
    val_loader = DataLoader(
        SemanticDataset(val_df, training=False), batch_size=batch_size,
        shuffle=False, num_workers=NUM_WORKERS, pin_memory=pin,
        drop_last=False, persistent_workers=True, prefetch_factor=4)

    model = build_semantic_model(device, pretrained_ckpt=p0_ckpt)
    base  = model._orig_mod if hasattr(model, "_orig_mod") else model
    criterion = nn.BCEWithLogitsLoss()
    best_val  = float("inf")
    history   = []

    # ── Phase A: frozen encoder, decoder only ─────────────────
    print(f"  [{label}] Phase A — frozen encoder, {EPOCHS_PHASE_A} ep @ {LR_PHASE_A:.0e}")
    _freeze_encoder(model)
    opt_a = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                              lr=LR_PHASE_A, weight_decay=1e-4)
    sch_a = torch.optim.lr_scheduler.ReduceLROnPlateau(
        opt_a, mode="min", factor=0.5, patience=5,
        threshold=1e-4, cooldown=2, min_lr=1e-7)
    scaler_a = torch.amp.GradScaler("cuda")
    es = 0
    for epoch in range(EPOCHS_PHASE_A):
        _, tr_bce = _train_one_epoch(model, train_loader, opt_a, scaler_a,
                                     criterion, device)
        val_bce, val_iou = _validate(model, val_loader, criterion, device)
        sch_a.step(val_bce)
        improved = val_bce < best_val
        if improved:
            best_val, es = val_bce, 0
            _save_checkpoint("A", epoch, model, opt_a, sch_a, history,
                             best_val, out_ckpt)
        else:
            es += 1
        print(f"    A E{epoch+1:>2}/{EPOCHS_PHASE_A}  val_bce={val_bce:.4f}  "
              f"val_iou={val_iou:.4f}{'  ★' if improved else ''}")
        if es >= EARLY_STOP_PAT:
            print("    early stop (A)"); break

    # ── Phase B: discriminative or full ───────────────────────
    print(f"  [{label}] Phase B — mode={UNFREEZE_MODE}, {EPOCHS_PHASE_B} ep")
    opt_b, sch_b, plateau = _phase_b_optimizer(model, base)
    scaler_b = torch.amp.GradScaler("cuda")
    es = 0
    for epoch in range(EPOCHS_PHASE_B):
        _, tr_bce = _train_one_epoch(model, train_loader, opt_b, scaler_b,
                                     criterion, device)
        val_bce, val_iou = _validate(model, val_loader, criterion, device)
        sch_b.step(val_bce) if plateau else sch_b.step()
        lr = opt_b.param_groups[0]["lr"]
        improved = val_bce < best_val
        if improved:
            best_val, es = val_bce, 0
            _save_checkpoint("B", epoch, model, opt_b, sch_b, history,
                             best_val, out_ckpt)
        else:
            es += 1
        print(f"    B E{epoch+1:>2}/{EPOCHS_PHASE_B}  val_bce={val_bce:.4f}  "
              f"val_iou={val_iou:.4f}  lr={lr:.2e}{'  ★' if improved else ''}")
        if es >= EARLY_STOP_PAT:
            print("    early stop (B)"); break

    del model, opt_a, opt_b, scaler_a, scaler_b
    if device.type == "cuda":
        torch.cuda.empty_cache()
    gc.collect()
    return best_val


def _site_completeness(site, test_df, ckpt_path, device):
    """Best-effort per-crown completeness on a held-out site: infer each test
    tile, rasterise that site's hand-traced crowns (id-labelled) into the tile,
    and accumulate covered/total px per crown across tiles. Returns summary stats
    or None. Guarded — a failure must not abort the fold."""
    shp = POLYGONS_DIR / f"{site}.shp"
    if not shp.exists():
        return None
    try:
        crowns = preprocess_crowns(str(shp))           # EPSG:3857, area≥0.5
        if len(crowns) == 0:
            return None
        crowns = crowns.reset_index(drop=True)
        crowns["cid"] = np.arange(1, len(crowns) + 1, dtype=np.int64)
        _ = crowns.sindex
        _ensure_torch()
        model = smp.Unet(encoder_name=ENCODER, encoder_weights=None,
                         decoder_channels=DECODER_CHANNELS, in_channels=IN_CHANNELS,
                         classes=1, activation=None).to(device)
        model.load_state_dict(torch.load(ckpt_path, map_location=device)["model_state"])
        model.eval()
        tf = A.Compose([A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD,
                                    max_pixel_value=255.0), ToTensorV2()])
        covered, total = {}, {}
        with torch.no_grad():
            for _, row in tqdm(test_df.iterrows(), total=len(test_df),
                               desc=f"    {site} completeness", leave=False):
                with rasterio.open(row["img_path"]) as src:
                    img = src.read().transpose(1, 2, 0)
                    H, W, tr, crs = src.height, src.width, src.transform, src.crs
                left, bottom, right, top = rasterio.windows.bounds(
                    rasterio.windows.Window(0, 0, W, H), tr)
                sub = crowns
                if crowns.crs is not None and crs is not None and crowns.crs != crs:
                    sub = crowns.to_crs(crs)
                sub = sub.cx[left:right, bottom:top]
                if len(sub) == 0:
                    continue
                label = rasterio.features.rasterize(
                    ((g, int(c)) for g, c in zip(sub.geometry, sub["cid"])),
                    out_shape=(H, W), transform=tr, fill=0, dtype="int32",
                    all_touched=False)
                if USE_VI:
                    inp = torch.from_numpy(rgb_to_model_input(img)).unsqueeze(0).to(device)
                else:
                    inp = tf(image=img)["image"].unsqueeze(0).to(device)
                pred = (1.0 / (1.0 + np.exp(-model(inp).squeeze().cpu().numpy()))
                        > CANOPY_PROB_THRESHOLD)
                ids = np.unique(label); ids = ids[ids > 0]
                for cid in ids:
                    m = label == cid
                    t = int(m.sum())
                    if t == 0:
                        continue
                    total[cid]   = total.get(cid, 0) + t
                    covered[cid] = covered.get(cid, 0) + int((m & pred).sum())
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()
        covs = np.array([covered[c] / total[c] for c in total if total[c] > 0],
                        dtype=float)
        if len(covs) == 0:
            return None
        return {"comp_n": int(len(covs)),
                "comp_mean": float(covs.mean()),
                "comp_median": float(np.median(covs)),
                "comp_ge90": float((covs >= 0.90).mean()),
                "comp_lt50": float((covs < 0.50).mean())}
    except Exception as e:
        print(f"    WARNING: completeness for {site} failed ({e})")
        return None


def _resolve_p0_ckpt(ckpt_path):
    if ckpt_path is not None and Path(ckpt_path).exists():
        return str(ckpt_path)
    p = CKPT_DIR_P0 / "ddt_best_v7_global.pt"
    if p.exists():
        return str(p)
    for fold in [3, 1, 2, 4, 5]:
        q = CKPT_DIR_P0 / f"ddt_best_v7_fold{fold}.pt"
        if q.exists():
            return str(q)
    return None


def step_loso(p0_ckpt=None, batch_size=BATCH_SIZE, only_fold=None, dry_run=False):
    """Step 9: LOSO honest training + evaluation (or `--fold ALL` deployable)."""
    _ensure_torch()
    print("\n── Step 9: Leave-One-Site-Out (LOSO) ──")
    CKPT_DIR.mkdir(parents=True, exist_ok=True)

    index_path = TILE_DIR / "tile_index_semantic.csv"
    if not index_path.exists():
        print(f"  ERROR: {index_path} not found — run step tile first")
        return
    df = pd.read_csv(index_path)

    # Classify sites from the tiles: positive = any canopy present.
    site_max  = df.groupby("site")["canopy_frac"].max()
    positives = sorted([s for s, v in site_max.items() if v > 0])
    negatives = sorted([s for s, v in site_max.items() if v <= 0])
    print(f"  Arch: in_channels={IN_CHANNELS} (VI={'on' if USE_VI else 'off'})  "
          f"unfreeze={UNFREEZE_MODE}")
    print(f"  Positive (forest) sites: {', '.join(positives)}")
    print(f"  Negative sites (always in train): {', '.join(negatives) or '—'}")
    if len(positives) < 3 and only_fold != "ALL":
        print(f"  ERROR: need ≥3 positive sites for LOSO (have {len(positives)}).")
        return

    p0 = _resolve_p0_ckpt(p0_ckpt)
    print(f"  Phase 0 init: {Path(p0).name if p0 else 'ImageNet only'}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Device: {device}")

    # ── Deployable model on ALL sites ─────────────────────────
    if only_fold == "ALL":
        val_site    = positives[0]                      # held-out for early stop
        train_sites = [s for s in positives if s != val_site] + negatives
        out_ckpt    = CKPT_DIR / "sem_best_2020_ft.pt"
        print(f"\n  DEPLOYABLE: train on {train_sites}  |  val (early-stop) "
              f"{val_site}  → {out_ckpt.name}")
        if dry_run:
            print("  Dry run — not training."); return
        bv = _train_one_fold(df[df["site"].isin(train_sites)],
                             df[df["site"] == val_site],
                             out_ckpt, p0, batch_size, device, "ALL")
        # Also drop a copy at phase3 root for eval/inference convenience.
        try:
            shutil.copy2(out_ckpt, OUT_DIR / "sem_best_2020_ft.pt")
        except Exception:
            pass
        print(f"\n  ✓ Deployable model: {out_ckpt}  (val_bce={bv:.4f})")
        print(f"  Run city inference/eval on it with: "
              f"--step inference --ckpt {out_ckpt} "
              f"{'--vi ' if USE_VI else ''}--unfreeze {UNFREEZE_MODE}")
        return

    # ── K-fold leave-one-site-out ─────────────────────────────
    folds = positives if only_fold is None else [only_fold]
    if only_fold is not None and only_fold not in positives:
        print(f"  ERROR: --fold {only_fold} is not a positive site.")
        return

    if dry_run:
        for ts in folds:
            vs = positives[(positives.index(ts) + 1) % len(positives)]
            trs = [s for s in positives if s not in (ts, vs)] + negatives
            print(f"  fold {ts}: test={ts}  val={vs}  train={trs}")
        return

    results = []
    for ts in folds:
        vs  = positives[(positives.index(ts) + 1) % len(positives)]
        trs = [s for s in positives if s not in (ts, vs)] + negatives
        train_df = df[df["site"].isin(trs)]
        val_df   = df[df["site"] == vs]
        test_df  = df[df["site"] == ts]
        out_ckpt = CKPT_DIR / LOSO_CKPT_TMPL.format(site=ts)
        print(f"\n{'='*62}")
        print(f"  FOLD: test={ts} ({len(test_df)} tiles)  val={vs} "
              f"({len(val_df)})  train={trs} ({len(train_df)})")
        print(f"{'='*62}")
        bv = _train_one_fold(train_df, val_df, out_ckpt, p0,
                            batch_size, device, ts)
        m  = _eval_tiles(test_df, str(out_ckpt), device, collect_probs=True)
        if m is None:
            print(f"  WARNING: no scorable pixels for {ts} — skipping fold.")
            continue
        comp = _site_completeness(ts, test_df, str(out_ckpt), device)
        row  = {"test_site": ts, "val_site": vs, "best_val_bce": round(bv, 4),
                **{k: round(v, 4) for k, v in m.items() if k != "n_tiles"},
                "n_test_tiles": m["n_tiles"]}
        if comp:
            row.update({k: round(v, 4) for k, v in comp.items()})
        results.append(row)
        print(f"  → {ts}: IoU={m['iou']:.4f}  Dice={m['dice']:.4f}  "
              f"F1={m['f1']:.4f}"
              + (f"  AUROC={m['auroc']:.4f}" if 'auroc' in m else "")
              + (f"  | crown <50%={comp['comp_lt50']*100:.1f}%  "
                 f"≥90%={comp['comp_ge90']*100:.1f}%" if comp else ""))

    if not results:
        print("\n  No folds completed."); return

    rep = pd.DataFrame(results)
    print(f"\n{'='*62}")
    print(f"  LOSO SUMMARY  (honest, spatially-independent)")
    print(f"  arch: in_ch={IN_CHANNELS} unfreeze={UNFREEZE_MODE}")
    print(f"{'='*62}")
    print(f"  {'test site':<16} {'IoU':>7} {'Dice':>7} {'F1':>7} "
          f"{'AUROC':>7} {'<50%':>7}")
    for _, r in rep.iterrows():
        print(f"  {r['test_site']:<16} {r.get('iou',float('nan')):>7.4f} "
              f"{r.get('dice',float('nan')):>7.4f} {r.get('f1',float('nan')):>7.4f} "
              f"{r.get('auroc',float('nan')):>7.4f} "
              f"{(r['comp_lt50']*100 if 'comp_lt50' in r and pd.notna(r.get('comp_lt50')) else float('nan')):>6.1f}%")
    def _ms(col):
        if col in rep and rep[col].notna().any():
            v = rep[col].dropna()
            return f"{v.mean():.4f} ± {v.std(ddof=0):.4f}"
        return "n/a"
    print(f"  {'-'*16}")
    print(f"  mean±sd  IoU  {_ms('iou')}   Dice {_ms('dice')}   F1 {_ms('f1')}")
    if "auroc" in rep:
        print(f"           AUROC {_ms('auroc')}   AP {_ms('ap')}")
    if "comp_lt50" in rep:
        print(f"  crown completeness: mean {_ms('comp_mean')}  "
              f"<50% {_ms('comp_lt50')}  ≥90% {_ms('comp_ge90')}")
    print(f"\n  Compare these to the inflated random-split numbers "
          f"(IoU 0.772 / AUROC 0.961). This mean is the DG1 number.")
    rep.to_csv(LOSO_REPORT, index=False)
    print(f"  ✓ Report: {LOSO_REPORT}")


# ═════════════════════════════════════════════════════════════════════════════
#  Summary
# ═════════════════════════════════════════════════════════════════════════════

def print_summary():
    print(f"\n{'='*65}")
    print(f"  PHASE 3 COMPLETE — Semantic Segmentation Development")
    print(f"{'='*65}")
    print(f"\n  Outputs:")
    for f in [EVAL_CSV, PROB_OUT, MASK_OUT, CANOPY_GPKG, CROSSVAL_CSV]:
        if f.exists():
            mb = f.stat().st_size / 1e6
            print(f"    ✓ {f.name}  ({mb:.0f} MB)")
        else:
            print(f"    ✗ {f.name}  (not yet created)")
    ckpt = CKPT_DIR / "sem_best_2020.pt"
    if ckpt.exists():
        mb = ckpt.stat().st_size / 1e6
        print(f"    ✓ {ckpt.name}  ({mb:.0f} MB)")

    print(f"""
  ◆ DECISION GATE 1 (DG1):
  ─────────────────────────
  Does the semantic model meet accuracy targets on 2020?
  Check semantic_eval_report.csv for IoU / Dice thresholds.
  If yes → proceed to Phase 4 (per-year semantic fine-tuning, uniform method)
  If no  → retrain with adjusted hyperparameters or architecture

  NEXT STEPS
  ──────────
  Phase 4: Per-Year Semantic Segmentation Fine-Tuning (uniform method)
    %run phase4_semantic_finetune.py

  Phase 5: Per-Year Instance Segmentation Fine-Tuning (9 high-res years)
    %run phase5_instance_finetune.py

  Or review semantic results first:
    import rasterio
    with rasterio.open("{PROB_OUT}") as src:
        prob = src.read(1)
        print(f"Prob range: {{prob.min():.3f}} – {{prob.max():.3f}}")
        print(f"Mean prob: {{prob[prob >= 0].mean():.3f}}")

    import geopandas as gpd
    canopy = gpd.read_file("{CANOPY_GPKG}")
    print(f"Canopy polygons: {{len(canopy):,}}")
    print(f"Total area: {{canopy.area.sum()/1e4:.1f}} ha")
""")
    print(f"{'='*65}")


# ═════════════════════════════════════════════════════════════════════════════
#  Main
# ═════════════════════════════════════════════════════════════════════════════

STEPS = ["labels", "tile", "train", "evaluate",
         "inference", "postproc", "crossval"]
# Diagnostic, run on demand only (not part of the default full pipeline).
EXTRA_STEPS = ["spatialcheck", "loso"]


def main():
    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]

    parser = argparse.ArgumentParser(
        description="Phase 3 — Semantic Segmentation Development (2020)")
    parser.add_argument("--step", type=str, default=None,
                        choices=STEPS + EXTRA_STEPS,
                        help="Run a single step (default: all pipeline steps; "
                             "'spatialcheck' is a standalone diagnostic)")
    parser.add_argument("--skip-training",  action="store_true",
                        help="Skip training — use existing checkpoint")
    parser.add_argument("--skip-inference", action="store_true",
                        help="Stop after evaluation")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--ckpt",       type=str, default=None,
                        help="Checkpoint path (Phase 0 for training, "
                             "Phase 3 for eval/inference)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print stats without writes")
    parser.add_argument("--vi", action="store_true",
                        help="Add GCC/GRVI/ExG vegetation-index input channels "
                             "(IN_CHANNELS=6). Use the same flag for train/eval/"
                             "inference/loso on a VI model.")
    parser.add_argument("--unfreeze", choices=["full", "discriminative"],
                        default="full",
                        help="Phase-B unfreezing: 'full' (baseline) or "
                             "'discriminative' (stem+layer3/4+decoder, warmup).")
    parser.add_argument("--fold", type=str, default=None,
                        help="LOSO: a positive site name to run one fold, or "
                             "'ALL' to train the deployable sem_best_2020_ft.pt.")

    args = parser.parse_args(filtered)

    from pipeline_log import StepLogger
    LOGS_DIR = BASE / "phase4" / "logs"
    SCRIPT_NAME = "phase3_semantic_dev"

    # Wire experiment flags into module globals (default off → baseline behavior).
    global USE_VI, IN_CHANNELS, UNFREEZE_MODE
    USE_VI        = bool(args.vi)
    IN_CHANNELS   = 3 + (len(VI_NAMES) if USE_VI else 0)
    UNFREEZE_MODE = args.unfreeze

    print("=" * 65)
    print("  PHASE 3 — Semantic Segmentation Development (2020)")
    print("  Edmonds Temporal Active Learning Pipeline")
    print("=" * 65)

    if args.step:
        steps_to_run = {args.step}
        print(f"  Mode: single step — {args.step}")
    else:
        steps_to_run = set(STEPS)
        if args.skip_training:
            steps_to_run.discard("train")
            print(f"  Skip training: True")
        if args.skip_inference:
            steps_to_run -= {"inference", "postproc", "crossval"}
            print(f"  Skip inference: True")
        print(f"  Steps: {', '.join(s for s in STEPS if s in steps_to_run)}")

    if args.dry_run:
        print(f"  Dry run: True")

    # Ensure output directories
    for d in [OUT_DIR, TILE_DIR, CKPT_DIR, LABEL_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    ckpt_path = Path(args.ckpt) if args.ckpt else None

    # ── Step 1: Binary labels ─────────────────────────────────
    image_paths = shapefile_paths = site_labels = mask_paths = None
    if "labels" in steps_to_run:
        with StepLogger(SCRIPT_NAME, "labels", LOGS_DIR) as log:
            image_paths, shapefile_paths, site_labels, mask_paths = \
                step_labels(dry_run=args.dry_run)
            log.finish(dry_run=args.dry_run, errors=0)

    # ── Step 2: Tiling ────────────────────────────────────────
    if "tile" in steps_to_run:
        with StepLogger(SCRIPT_NAME, "tile", LOGS_DIR) as log:
            step_tile(image_paths, shapefile_paths, site_labels,
                      mask_paths, dry_run=args.dry_run)
            log.finish(dry_run=args.dry_run, errors=0)

    # ── Step 3: Training ──────────────────────────────────────
    if "train" in steps_to_run:
        with StepLogger(SCRIPT_NAME, "train", LOGS_DIR) as log:
            step_train(batch_size=args.batch_size,
                       ckpt_path=str(ckpt_path) if ckpt_path else None,
                       dry_run=args.dry_run)
            log.finish(dry_run=args.dry_run, errors=0)

    # ── Step 4: Evaluation ────────────────────────────────────
    if "evaluate" in steps_to_run:
        with StepLogger(SCRIPT_NAME, "evaluate", LOGS_DIR) as log:
            eval_ckpt = ckpt_path
            if eval_ckpt is None or not eval_ckpt.exists():
                eval_ckpt = CKPT_DIR / "sem_best_2020.pt"
            step_evaluate(ckpt_path=str(eval_ckpt) if eval_ckpt else None,
                          dry_run=args.dry_run)
            log.finish(dry_run=args.dry_run, errors=0)

    # ── Step 5: Full-city inference ───────────────────────────
    if "inference" in steps_to_run:
        with StepLogger(SCRIPT_NAME, "inference", LOGS_DIR) as log:
            infer_ckpt = ckpt_path
            if infer_ckpt is None or not infer_ckpt.exists():
                infer_ckpt = CKPT_DIR / "sem_best_2020.pt"
            step_inference(
                ckpt_path=str(infer_ckpt) if infer_ckpt else None,
                batch_size=args.batch_size * 16 if args.batch_size == BATCH_SIZE
                           else args.batch_size,
                dry_run=args.dry_run)
            log.finish(dry_run=args.dry_run, errors=0)

    # ── Step 6: Post-processing ───────────────────────────────
    if "postproc" in steps_to_run:
        with StepLogger(SCRIPT_NAME, "postproc", LOGS_DIR) as log:
            step_postproc(dry_run=args.dry_run)
            log.finish(dry_run=args.dry_run, errors=0)

    # ── Step 7: Cross-validation ──────────────────────────────
    if "crossval" in steps_to_run:
        with StepLogger(SCRIPT_NAME, "crossval", LOGS_DIR) as log:
            step_crossval(dry_run=args.dry_run)
            log.finish(dry_run=args.dry_run, errors=0)

    # ── Step 8: Spatial-honesty diagnostic (on demand) ────────
    if "spatialcheck" in steps_to_run:
        with StepLogger(SCRIPT_NAME, "spatialcheck", LOGS_DIR) as log:
            step_spatialcheck(ckpt_path=str(ckpt_path) if ckpt_path else None,
                              dry_run=args.dry_run)
            log.finish(dry_run=args.dry_run, errors=0)

    # ── Step 9: LOSO honest training + eval (on demand) ───────
    if "loso" in steps_to_run:
        with StepLogger(SCRIPT_NAME, "loso", LOGS_DIR) as log:
            step_loso(p0_ckpt=str(ckpt_path) if ckpt_path else None,
                      batch_size=args.batch_size, only_fold=args.fold,
                      dry_run=args.dry_run)
            log.finish(dry_run=args.dry_run, fold=args.fold, errors=0)

    # ── Summary ───────────────────────────────────────────────
    print_summary()
    timer_summary()


if __name__ == "__main__":
    multiprocessing.set_start_method("fork", force=True)
    main()
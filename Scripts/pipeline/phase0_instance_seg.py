"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 0 — 2020 Anchored Instance Segmentation
  Edmonds Temporal Active Learning Pipeline

  Trains a U-Net (ResNet-101 encoder) to predict per-pixel Distance
  Transform Maps (DTMs) from 7.5 cm RGB ortho-imagery, then runs
  full-city streaming inference + watershed segmentation to produce
  the spatial anchor layer of 222 k+ individual crown polygons.

  PIPELINE STEPS
  ──────────────
  Step 1  discover     Discover training sites & pair photos ↔ shapefiles
  Step 2  inspect      Inspect raster/shapefile properties & validate
  Step 3  preprocess   Reproject, fix geometries, explode, drop slivers
  Step 4  dtm          Generate per-crown normalised distance transforms
  Step 5  tile         Tile RGB + DTM → 512×512 paired patches
  Step 6  train        K-Fold cross-validation with spatial buffer splits
  Step 7  evaluate     Evaluate on held-out test tiles (F1 by size class)
  Step 8  sweep        Joint DTM_THRESHOLD × MIN_DISTANCE parameter sweep
  Step 9  inference    Streaming full-city inference → DTM raster on disk
  Step 10 watershed    Chunked watershed → crown GeoPackage

  INPUTS
  ──────
  photos/     *_rgb.tif        Training site ortho-imagery (7.5 cm EPSG:3857)
  polygons/   *.shp            Matched crown polygon shapefiles (or omit for negatives)
  Full_Image/ edmonds_2020_image.tif   Full Edmonds 2020 RGB ortho

  OUTPUTS
  ───────
  labels/              Distance transform GeoTIFFs per training site
  tiles/               512×512 paired image/label tiles + tile_index.csv
  checkpoints/         Model weights (per-fold + global best)
  inference/           edmonds_dtm_2020.tif        Full-city DTM raster
                       edmonds_crowns_2020.gpkg    Crown polygon layer
                       edmonds_crown_stats_2020.csv  Summary statistics

  USAGE
  ─────
  %run phase0_instance_seg.py                      # full pipeline
  %run phase0_instance_seg.py --step discover      # single step
  %run phase0_instance_seg.py --skip-training      # skip training (use existing ckpt)
  %run phase0_instance_seg.py --skip-inference      # stop after evaluation
  %run phase0_instance_seg.py --epochs 50           # override epoch count
  %run phase0_instance_seg.py --batch-size 8        # override batch size
  %run phase0_instance_seg.py --folds 3             # fewer CV folds
  %run phase0_instance_seg.py --ckpt <path>         # resume from checkpoint
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import gc
import multiprocessing
import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import fiona
import fiona.crs
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import rasterio.transform
import rasterio.windows
from scipy.ndimage import label as scipy_label
from scipy.spatial.distance import cdist
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union
from shapely.validation import explain_validity
from skimage.feature import peak_local_max
from skimage.segmentation import watershed
from sklearn.model_selection import train_test_split
from tqdm import tqdm

warnings.filterwarnings("ignore")

# Lazy torch imports — only when needed
_torch_loaded = False


def _ensure_torch():
    global _torch_loaded
    if _torch_loaded:
        return

    import subprocess

    # FROZEN-LEGACY pins (phase 0 complete 2026-04): smp 0.3.4 / timm 0.9.7 conflict
    # with the live phase3/4 profile (see Scripts/requirements-colab.txt). Never run
    # phase0 in the same Colab session as phase3/phase4seg — use a fresh runtime.
    _deps = [
        ("torch",                        "torch"),
        ("segmentation_models_pytorch",  "segmentation-models-pytorch==0.3.4"),
        ("albumentations",               "albumentations"),
        ("timm",                         "timm==0.9.7"),
    ]
    for mod_name, pip_name in _deps:
        try:
            __import__(mod_name)
        except ImportError:
            print(f"  Installing {pip_name}...")
            subprocess.run([sys.executable, "-m", "pip", "install", pip_name, "-q"],
                           capture_output=True)
    print("  ✓ GPU dependencies ready")

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


# ── Paths ─────────────────────────────────────────────────────────────────────

BASE          = Path("/content/drive/MyDrive/treedata")
PHOTOS_DIR    = BASE / "photos"
POLYGONS_DIR  = BASE / "polygons"
LABEL_DIR     = BASE / "labels"
TILE_DIR      = BASE / "tiles"
CKPT_DIR      = BASE / "checkpoints"
OUT_DIR       = BASE / "inference"

EDMONDS_IMG   = BASE / "Full_Image/edmonds_2020_image.tif"
BOUNDARY_PATH = BASE / "City Boundry/Edmonds Boundry.shp"

DTM_OUT       = OUT_DIR / "edmonds_dtm_2020.tif"
CROWNS_OUT    = OUT_DIR / "edmonds_crowns_2020.gpkg"
STATS_OUT     = OUT_DIR / "edmonds_crown_stats_2020.csv"

TARGET_CRS    = "EPSG:3857"


# ── Hyperparameters ───────────────────────────────────────────────────────────

# Preprocessing
SMALL_AREA_THRESHOLD = 0.5      # m² — slivers dropped after explode

# Tiling
TILE_SIZE            = 512
TILE_STRIDE          = 512
MIN_CROWN_FRAC       = 0.00
NEGATIVE_SAMPLE_RATE = 0.15
TEST_FRAC            = 0.20
RANDOM_SEED          = 42

# Model architecture
ENCODER              = "resnet101"
DECODER_CHANNELS     = (1024, 512, 256, 128, 64)
ENCODER_WEIGHTS      = "imagenet"
DECODER_DROPOUT      = 0.3

# Training
K_FOLDS              = 5
EPOCHS               = 150
LR                   = 1e-4
LR_PATIENCE          = 8
LR_FACTOR            = 0.5
EARLY_STOP_PAT       = 50
L1_LAMBDA            = 1e-6
WARMUP_EPOCHS        = 5
BATCH_SIZE           = 10
NUM_WORKERS          = 16
SAVE_EVERY           = 10
SPATIAL_BUFFER_PX    = 1024

# Inference
INFER_BATCH_SIZE     = 160
INFER_STRIDE         = 256
INFER_PAD            = (TILE_SIZE - INFER_STRIDE) // 2

# Watershed
MIN_DISTANCE         = 30
DTM_THRESHOLD        = 10.0
MIN_CROWN_AREA       = 2.0
CHUNK_SIZE           = 2048
CHUNK_BORDER         = 300
N_WATERSHED_WORKERS  = 6

# Evaluation
IOU_THRESHOLD        = 0.5
SIZE_SMALL_MAX       = 4.9
SIZE_MEDIUM_MAX      = 15.9

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]


# ── Helpers ───────────────────────────────────────────────────────────────────

def size_class(area_m2):
    if area_m2 <= SIZE_SMALL_MAX:
        return "small"
    if area_m2 <= SIZE_MEDIUM_MAX:
        return "medium"
    return "large"


# ═════════════════════════════════════════════════════════════════════════════
#  Step 1 — Discover training sites
# ═════════════════════════════════════════════════════════════════════════════

def discover_sites():
    """
    Auto-discover all sites from the photos directory.
    Returns (image_paths, shapefile_paths, site_labels) in alphabetical order.
    """
    print("\n── Step 1: Site Discovery ──")

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


# ═════════════════════════════════════════════════════════════════════════════
#  Step 2 — Inspect rasters and shapefiles
# ═════════════════════════════════════════════════════════════════════════════

def inspect_raster(path, expected_res_cm=7.5):
    p = Path(path)
    print(f"\n{'='*60}")
    print(f"  FILE: {p.name}")
    print(f"{'='*60}")

    with rasterio.open(path) as src:
        print(f"  Dimensions:   {src.width} px (W) x {src.height} px (H)")
        print(f"  Bands:        {src.count}  →  {src.dtypes}")
        print(f"  CRS:          {src.crs}")
        print(f"  Resolution:   {src.res[0]:.4f} x {src.res[1]:.4f} (map units)")

        bounds = src.bounds
        width_m  = bounds.right - bounds.left
        height_m = bounds.top   - bounds.bottom
        print(f"  Ground Extent:  {width_m:.1f} m (W) x {height_m:.1f} m (H)")
        print(f"  Area:           {(width_m * height_m) / 1e6:.4f} km²")

        print(f"  Band Statistics (min / mean / max / std):")
        for i in range(1, src.count + 1):
            band = src.read(i).astype(np.float32)
            if src.nodata is not None:
                band = np.where(band == src.nodata, np.nan, band)
            print(f"    Band {i}: "
                  f"{np.nanmin(band):.1f} / {np.nanmean(band):.1f} / "
                  f"{np.nanmax(band):.1f} / {np.nanstd(band):.1f}")

        res_cm = src.res[0] * 100
        if abs(res_cm - expected_res_cm) > 1.0:
            print(f"\n  ⚠ Resolution is {res_cm:.2f} cm, expected ~{expected_res_cm} cm")
        else:
            print(f"  ✓ Resolution confirmed near {expected_res_cm} cm ({res_cm:.2f} cm)")

        epsg = src.crs.to_epsg() if src.crs else None
        if epsg == 3857:
            print(f"  ✓ CRS confirmed EPSG:3857")
        else:
            print(f"  ⚠ CRS is EPSG:{epsg} — verify before proceeding")


def inspect_shapefile(path):
    p = Path(path)
    print(f"\n{'='*60}")
    print(f"  FILE: {p.name}")
    print(f"{'='*60}")

    for ext in [".shp", ".dbf", ".shx"]:
        sidecar = p.with_suffix(ext)
        status  = "✓" if sidecar.exists() else "✗ MISSING"
        print(f"  {status}  {sidecar.name}")

    gdf  = gpd.read_file(path)
    epsg = gdf.crs.to_epsg() if gdf.crs else None

    print(f"\n  Feature Count:    {len(gdf)}")
    print(f"  Geometry Type:    {gdf.geometry.geom_type.unique().tolist()}")
    print(f"  CRS:              {gdf.crs}  (EPSG:{epsg})")

    invalid = (~gdf.geometry.is_valid).sum()
    empty   = gdf.geometry.is_empty.sum()
    print(f"  Invalid Geometries: {invalid}")
    print(f"  Empty Geometries:   {empty}")
    if invalid > 0:
        print(f"  ⚠ Will fix with buffer(0) during preprocessing")

    gdf["_area_m2"] = gdf.geometry.area
    print(f"\n  Crown Area Statistics (m²):")
    print(f"    Min:    {gdf['_area_m2'].min():.2f}")
    print(f"    Mean:   {gdf['_area_m2'].mean():.2f}")
    print(f"    Median: {gdf['_area_m2'].median():.2f}")
    print(f"    Max:    {gdf['_area_m2'].max():.2f}")

    small  = (gdf["_area_m2"] <= SIZE_SMALL_MAX).sum()
    medium = ((gdf["_area_m2"] > SIZE_SMALL_MAX)
              & (gdf["_area_m2"] <= SIZE_MEDIUM_MAX)).sum()
    large  = (gdf["_area_m2"] > SIZE_MEDIUM_MAX).sum()
    total  = len(gdf)
    print(f"\n  Size Classes:")
    print(f"    Small  (≤{SIZE_SMALL_MAX} m²):    {small:>4}  ({100*small/total:.1f}%)")
    print(f"    Medium ({SIZE_SMALL_MAX}–{SIZE_MEDIUM_MAX} m²): {medium:>4}  "
          f"({100*medium/total:.1f}%)")
    print(f"    Large  (>{SIZE_MEDIUM_MAX} m²):   {large:>4}  ({100*large/total:.1f}%)")

    return gdf


def inspect_all(image_paths, shapefile_paths, site_labels):
    print("\n── Step 2: Inspection ──")

    print("\n━━━ RASTERS ━━━")
    for path in image_paths:
        inspect_raster(path)

    print("\n━━━ SHAPEFILES ━━━")
    raw_gdfs = {}
    for path, label in zip(shapefile_paths, site_labels):
        if path is None:
            print(f"\n  ✓ {label}: skipped (true negative)")
            continue
        raw_gdfs[label] = inspect_shapefile(path)

    return raw_gdfs


# ═════════════════════════════════════════════════════════════════════════════
#  Step 3 — Preprocess & harmonise shapefiles
# ═════════════════════════════════════════════════════════════════════════════

def preprocess_shapefiles(raw_gdfs, site_labels):
    print("\n── Step 3: Preprocessing & Harmonization ──")

    gdfs = {}

    for label, gdf in raw_gdfs.items():
        print(f"\n{'='*60}")
        print(f"  Processing: {label}  ({len(gdf)} features)")
        print(f"{'='*60}")

        # Reproject
        if gdf.crs.to_epsg() != 3857:
            gdf = gdf.to_crs(TARGET_CRS)
            print(f"  ✓ Reprojected → EPSG:3857")
        else:
            print(f"  ✓ Already EPSG:3857")

        # Explode MultiPolygons
        if "MultiPolygon" in gdf.geometry.geom_type.unique():
            n_before = len(gdf)
            gdf = gdf.explode(index_parts=False).reset_index(drop=True)
            print(f"  ✓ Exploded MultiPolygons: {n_before} → {len(gdf)}")
        else:
            print(f"  ✓ No MultiPolygons")

        # Fix invalid geometries
        invalid_mask = ~gdf.geometry.is_valid
        n_invalid    = invalid_mask.sum()
        if n_invalid > 0:
            print(f"  ⚠ {n_invalid} invalid geometries — applying buffer(0)")
            for idx in gdf[invalid_mask].index[:3]:
                print(f"      Row {idx}: {explain_validity(gdf.loc[idx, 'geometry'])}")
            gdf["geometry"] = gdf.geometry.buffer(0)
            still_invalid   = (~gdf.geometry.is_valid).sum()
            if still_invalid > 0:
                gdf = gdf[gdf.geometry.is_valid].reset_index(drop=True)
                print(f"  ⚠ Dropped {still_invalid} still-invalid geometries")
            else:
                print(f"  ✓ All geometries now valid")
        else:
            print(f"  ✓ No invalid geometries")

        # Second explode after buffer(0) may create new MultiPolygons
        if "MultiPolygon" in gdf.geometry.geom_type.unique():
            n_before = len(gdf)
            gdf = gdf.explode(index_parts=False).reset_index(drop=True)
            print(f"  ✓ Second explode: {n_before} → {len(gdf)}")

        # Drop empties
        n_empty = gdf.geometry.is_empty.sum()
        if n_empty > 0:
            gdf = gdf[~gdf.geometry.is_empty].reset_index(drop=True)
            print(f"  ✓ Dropped {n_empty} empty geometries")

        # ── CRS-UNIT TRAP — `area_m2` HERE IS NOT TRUE m² (found 2026-08-27) ──
        # TARGET_CRS is EPSG:3857 (Web Mercator), which is conformal, not
        # equal-area: at Edmonds (47.81°N) areas are inflated 1/cos²(lat).
        # MEASURED on the shipped edmonds_crowns_2020.gpkg: stored area_m2 is
        # 2.2215x the true UTM-10N area (median 87.81 vs 39.53 m²). Same family
        # as the gsd_cm defect (WORKPLAN §1.5).
        #
        # NOT FIXED IN PLACE, deliberately: this value also drives the sliver
        # filter below AND size_class(), whose SMALL/MEDIUM cut-points were
        # calibrated against these inflated numbers. Converting here would
        # silently re-bucket every crown and change a phase1 feature, i.e. a
        # model input — a science decision, not a reporting fix. To correct:
        # convert with `.to_crs("EPSG:26910").area` and retune SIZE_SMALL_MAX /
        # SIZE_MEDIUM_MAX / SMALL_AREA_THRESHOLD together, then regenerate.
        # Anything QUOTING crown area in m²/ha must divide by 2.2215 first.
        # Drop slivers
        gdf["area_m2"] = gdf.geometry.area
        n_slivers      = (gdf["area_m2"] < SMALL_AREA_THRESHOLD).sum()
        if n_slivers > 0:
            gdf = gdf[gdf["area_m2"] >= SMALL_AREA_THRESHOLD].reset_index(drop=True)
            print(f"  ✓ Dropped {n_slivers} slivers below {SMALL_AREA_THRESHOLD} m²")

        # Standardise columns
        gdf["area_m2"]    = gdf.geometry.area
        gdf["crown_id"]   = [f"{label}_{i}" for i in range(len(gdf))]
        gdf["site"]       = label
        gdf["size_class"] = gdf["area_m2"].apply(size_class)
        gdf = gdf[["crown_id", "site", "area_m2", "size_class", "geometry"]].copy()

        gdfs[label] = gdf

        small  = (gdf["size_class"] == "small").sum()
        medium = (gdf["size_class"] == "medium").sum()
        large  = (gdf["size_class"] == "large").sum()
        total  = len(gdf)

        print(f"\n  Final count: {total}")
        print(f"    Small:  {small:>4}  ({100*small/total:.1f}%)")
        print(f"    Medium: {medium:>4}  ({100*medium/total:.1f}%)")
        print(f"    Large:  {large:>4}  ({100*large/total:.1f}%)")
        print(f"  Area (m²): min={gdf['area_m2'].min():.1f}  "
              f"median={gdf['area_m2'].median():.1f}  "
              f"max={gdf['area_m2'].max():.1f}")

    # Fill true negatives with empty GDFs
    for label in site_labels:
        if label not in gdfs:
            gdfs[label] = gpd.GeoDataFrame(
                columns=["crown_id", "site", "area_m2", "size_class", "geometry"],
                geometry="geometry",
            ).set_crs(TARGET_CRS)

    return gdfs


def validate_preprocessed(gdfs, image_paths, site_labels):
    print(f"\n── Validation Summary ──")
    all_clear = True

    for label, gdf in gdfs.items():
        issues = []

        if gdf.crs is None or gdf.crs.to_epsg() != 3857:
            issues.append(f"Wrong CRS: {gdf.crs}")

        if len(gdf) == 0:
            print(f"  ✓  {label}: true negative")
            continue

        if (~gdf.geometry.is_valid).sum() > 0:
            issues.append("invalid geometries remain")
        if gdf.geometry.is_empty.sum() > 0:
            issues.append("empty geometries remain")
        if "MultiPolygon" in gdf.geometry.geom_type.unique():
            issues.append("MultiPolygon geometries remain")
        if gdf["crown_id"].duplicated().any():
            issues.append("duplicate crown IDs")

        with rasterio.open(image_paths[site_labels.index(label)]) as src:
            img_box = box(*src.bounds)
        if not img_box.intersects(box(*gdf.total_bounds)):
            issues.append("no spatial overlap with image")

        if issues:
            all_clear = False
            print(f"  ✗  {label}: {' | '.join(issues)}")
        else:
            print(f"  ✓  {label}: {len(gdf)} polygons — clean")

    total = sum(len(g) for g in gdfs.values())
    print(f"\n  Total crowns: {total}")
    if not all_clear:
        print(f"  ⚠ Issues remain — resolve before proceeding")
    return all_clear


# ═════════════════════════════════════════════════════════════════════════════
#  Step 4 — Distance transform generation
# ═════════════════════════════════════════════════════════════════════════════

def generate_distance_transform(img_path, gdf, label):
    """Generate a normalised per-crown distance transform GeoTIFF."""
    out_path = LABEL_DIR / f"{label.lower()}_dtm.tif"

    with rasterio.open(img_path) as src:
        height    = src.height
        width     = src.width
        transform = src.transform
        crs       = src.crs
        res       = src.res[0]

    print(f"\n  {label}: {width}×{height} px  |  {len(gdf)} crowns  →  {out_path.name}")

    profile = {
        "driver": "GTiff", "dtype": "float32",
        "width": width, "height": height, "count": 1,
        "crs": crs, "transform": transform,
        "compress": "lzw", "nodata": 0.0,
    }

    # True negative — all-zero DTM
    if len(gdf) == 0:
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(np.zeros((height, width), dtype=np.float32), 1)
        file_mb = out_path.stat().st_size / 1e6
        print(f"       ✓ True negative DTM written ({file_mb:.1f} MB)")
        return out_path, {"label": label, "crowns_total": 0,
                          "crowns_processed": 0, "crowns_skipped": 0,
                          "crown_coverage": 0.0, "dtm_min": 0.0,
                          "dtm_max": 0.0, "file_mb": file_mb}

    dtm = np.zeros((height, width), dtype=np.float32)

    # Rasterize crown polygons
    gdf = gdf.copy().reset_index(drop=True)
    gdf["_int_id"] = gdf.index + 1
    shapes = ((geom, int_id) for geom, int_id in zip(gdf.geometry, gdf["_int_id"]))
    crown_mask = rasterio.features.rasterize(
        shapes, out_shape=(height, width), transform=transform,
        fill=0, dtype=np.int32, all_touched=False,
    )

    n_rasterized = np.unique(crown_mask[crown_mask > 0]).size
    print(f"       {n_rasterized}/{len(gdf)} crowns rasterized")

    # Per-crown distance transform
    skipped   = 0
    processed = 0

    for _, row in tqdm(gdf.iterrows(), total=len(gdf),
                       desc=f"       {label}", leave=False):
        int_id = int(row["_int_id"])
        crown_pixels = (crown_mask == int_id)
        if crown_pixels.sum() == 0:
            skipped += 1
            continue

        centroid       = row.geometry.centroid
        col_f = (centroid.x - transform.c) / transform.a
        row_f = (centroid.y - transform.f) / transform.e
        cx_px = int(np.clip(np.round(col_f), 0, width  - 1))
        cy_px = int(np.clip(np.round(row_f), 0, height - 1))

        rows_idx, cols_idx = np.where(crown_pixels)
        r_min, r_max = rows_idx.min(), rows_idx.max()
        c_min, c_max = cols_idx.min(), cols_idx.max()
        r_min_c = max(0, r_min - 1)
        r_max_c = min(height - 1, r_max + 1)
        c_min_c = max(0, c_min - 1)
        c_max_c = min(width  - 1, c_max + 1)

        crop_mask = crown_pixels[r_min_c:r_max_c+1, c_min_c:c_max_c+1]
        cy_rel = np.clip(cy_px - r_min_c, 0, crop_mask.shape[0] - 1)
        cx_rel = np.clip(cx_px - c_min_c, 0, crop_mask.shape[1] - 1)

        row_coords, col_coords = np.where(crop_mask)
        dist  = np.sqrt((row_coords - cy_rel)**2 + (col_coords - cx_rel)**2)
        d_max = dist.max()

        if d_max == 0:
            norm_dist = np.ones_like(dist, dtype=np.float32) * 100.0
        else:
            norm_dist = (1.0 - (dist / d_max)) * 99.0 + 1.0

        abs_rows = row_coords + r_min_c
        abs_cols = col_coords + c_min_c
        dtm[abs_rows, abs_cols] = norm_dist.astype(np.float32)
        processed += 1

    print(f"       Processed: {processed}  |  Skipped: {skipped}")

    # Validate
    crown_px = (dtm > 0).sum()
    coverage = 100 * crown_px / (height * width)
    print(f"       Coverage: {coverage:.1f}%  |  "
          f"Range: {dtm[dtm > 0].min():.2f}–{dtm.max():.2f}")

    # Write
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(dtm, 1)

    file_mb = out_path.stat().st_size / 1e6
    print(f"       ✓ Written ({file_mb:.1f} MB)")

    return out_path, {
        "label": label, "crowns_total": len(gdf),
        "crowns_processed": processed, "crowns_skipped": skipped,
        "crown_coverage": coverage,
        "dtm_min": float(dtm[dtm > 0].min()) if crown_px > 0 else 0.0,
        "dtm_max": float(dtm.max()), "file_mb": file_mb,
    }


def generate_all_dtms(gdfs, image_paths, site_labels):
    print("\n── Step 4: Distance Transform Generation ──")
    LABEL_DIR.mkdir(parents=True, exist_ok=True)

    image_paths_dict = {l: p for l, p in zip(site_labels, image_paths)}
    dtm_paths = {}
    all_stats = {}

    for label in site_labels:
        out_path, stats = generate_distance_transform(
            image_paths_dict[label], gdfs[label], label)
        dtm_paths[label] = out_path
        all_stats[label] = stats

    print(f"\n  {'Site':<20} {'Total':>7} {'Done':>6} {'Skip':>6} "
          f"{'Coverage':>10} {'Range':>14} {'MB':>7}")
    print(f"  {'-'*20} {'-'*7} {'-'*6} {'-'*6} "
          f"{'-'*10} {'-'*14} {'-'*7}")
    for label, s in all_stats.items():
        print(f"  {label:<20} {s['crowns_total']:>7} {s['crowns_processed']:>6} "
              f"{s['crowns_skipped']:>6} {s['crown_coverage']:>9.1f}% "
              f"  {s['dtm_min']:>5.1f}–{s['dtm_max']:>5.1f}  {s['file_mb']:>6.1f}")

    return dtm_paths, image_paths_dict


# ═════════════════════════════════════════════════════════════════════════════
#  Step 5 — Tiling
# ═════════════════════════════════════════════════════════════════════════════

def tile_site(label, img_path, dtm_path):
    """Generate 512×512 paired tiles for one site."""
    records = []

    with rasterio.open(img_path) as img_src, \
         rasterio.open(dtm_path) as dtm_src:

        height, width = img_src.height, img_src.width
        assert (height, width) == (dtm_src.height, dtm_src.width), \
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
                img_tile = img_src.read(window=window)
                dtm_tile = dtm_src.read(1, window=window)

                crown_frac = float((dtm_tile > 0).sum()) / (TILE_SIZE * TILE_SIZE)

                if crown_frac < MIN_CROWN_FRAC:
                    if crown_frac == 0.0 and np.random.random() < NEGATIVE_SAMPLE_RATE:
                        pass  # keep as true negative
                    else:
                        rejected += 1
                        continue

                tile_name      = f"{label.lower()}_r{row_off:05d}_c{col_off:05d}.tif"
                tile_transform = rasterio.windows.transform(window, img_transform)
                dtm_vals       = dtm_tile[dtm_tile > 0]

                records.append({
                    "tile_name":      tile_name,
                    "site":           label,
                    "row_off":        row_off,
                    "col_off":        col_off,
                    "crown_frac":     round(float(crown_frac), 4),
                    "dtm_mean":       round(float(dtm_vals.mean()), 2) if len(dtm_vals) > 0 else 0.0,
                    "dtm_max":        round(float(dtm_vals.max()),  2) if len(dtm_vals) > 0 else 0.0,
                    "img_path":       img_path,
                    "dtm_path":       str(dtm_path),
                    "tile_transform": tile_transform,
                    "crs":            crs,
                    "_img_tile":      img_tile,
                    "_dtm_tile":      dtm_tile,
                })
                accepted += 1

        print(f"  {label}: {accepted} accepted / {rejected} rejected")

    return records


def run_tiling(dtm_paths, image_paths_dict, site_labels):
    print("\n── Step 5: Tiling ──")

    for split in ["train", "test"]:
        (TILE_DIR / split / "images").mkdir(parents=True, exist_ok=True)
        (TILE_DIR / split / "labels").mkdir(parents=True, exist_ok=True)

    site_pairs = {l: (image_paths_dict[l], str(dtm_paths[l])) for l in site_labels}

    # Generate all tiles
    all_records = []
    for label, (img_p, dtm_p) in site_pairs.items():
        records = tile_site(label, img_p, dtm_p)
        all_records.extend(records)
    print(f"\n  Total tiles: {len(all_records)}")

    # Stratified train/test split
    tile_names = [r["tile_name"] for r in all_records]
    sites      = [r["site"]      for r in all_records]

    train_names, test_names = train_test_split(
        tile_names, test_size=TEST_FRAC, stratify=sites, random_state=RANDOM_SEED)
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
    dtm_profile_base = {
        "driver": "GTiff", "dtype": "float32", "count": 1,
        "width": TILE_SIZE, "height": TILE_SIZE, "compress": "lzw", "nodata": 0.0,
    }

    index_rows = []
    for rec in tqdm(all_records, desc="  Writing tiles"):
        split     = "train" if rec["tile_name"] in train_set else "test"
        tile_name = rec["tile_name"]

        img_out = TILE_DIR / split / "images" / tile_name
        dtm_out = TILE_DIR / split / "labels" / tile_name

        with rasterio.open(img_out, "w", **{**img_profile_base,
                           "crs": rec["crs"], "transform": rec["tile_transform"]}) as dst:
            dst.write(rec["_img_tile"])

        with rasterio.open(dtm_out, "w", **{**dtm_profile_base,
                           "crs": rec["crs"], "transform": rec["tile_transform"]}) as dst:
            dst.write(rec["_dtm_tile"], 1)

        index_rows.append({
            "tile_name": tile_name, "site": rec["site"], "split": split,
            "row_off": rec["row_off"], "col_off": rec["col_off"],
            "crown_frac": rec["crown_frac"], "dtm_mean": rec["dtm_mean"],
            "dtm_max": rec["dtm_max"],
            "img_path": str(img_out), "dtm_path": str(dtm_out),
        })

    index_df   = pd.DataFrame(index_rows)
    index_path = TILE_DIR / "tile_index.csv"
    index_df.to_csv(index_path, index=False)
    print(f"  ✓ {len(index_rows)} tiles written  |  index: {index_path.name}")


# ═════════════════════════════════════════════════════════════════════════════
#  Step 6 — K-Fold training with spatial buffer
# ═════════════════════════════════════════════════════════════════════════════

def make_spatial_buffer_splits(df, n_folds=5, buffer_px=1024, seed=42):
    """Create K-Fold splits with spatial buffering within each site."""
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
        buffer_indices = []

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
                if min_dist[i] < buffer_px:
                    buffer_indices.append(idx)
                else:
                    train_indices.append(idx)

        folds.append((np.array(train_indices), np.array(val_indices),
                      np.array(buffer_indices)))
    return folds


# ── Augmentation factories ────────────────────────────────────────────────────

def _make_spatial_transform():
    _ensure_torch()
    return A.Compose([
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.5),
        A.Transpose(p=0.5),
        A.RandomRotate90(p=0.5),
        A.Rotate(limit=45, border_mode=0, p=0.5),
        A.ShiftScaleRotate(shift_limit=0.1, scale_limit=0.1,
                           rotate_limit=0, border_mode=0, p=0.5),
        A.GridDistortion(num_steps=5, distort_limit=0.3, p=0.4),
        A.ElasticTransform(alpha=50, sigma=5, p=0.3),
    ], additional_targets={"label": "mask"})


def _make_pixel_transform():
    _ensure_torch()
    return A.Compose([
        A.OneOf([
            A.GaussianBlur(blur_limit=(3, 7), p=1.0),
            A.MedianBlur(blur_limit=5, p=1.0),
        ], p=0.5),
        A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.6),
        A.HueSaturationValue(hue_shift_limit=15, sat_shift_limit=30,
                             val_shift_limit=15, p=0.5),
        A.RandomGamma(gamma_limit=(70, 130), p=0.4),
        A.RandomShadow(shadow_roi=(0, 0, 1, 1),
                       num_shadows_limit=(1, 3), shadow_dimension=5, p=0.4),
        A.RandomFog(fog_coef_lower=0.05, fog_coef_upper=0.2, p=0.3),
        A.Downscale(scale_range=(0.5, 0.75),
                    interpolation_pair={"downscale": 0, "upscale": 2}, p=0.3),
        A.CoarseDropout(num_holes_range=(2, 8),
                        hole_height_range=(32, 96),
                        hole_width_range=(32, 96), fill=0, p=0.4),
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD, max_pixel_value=255.0),
        ToTensorV2(),
    ])


def _make_test_transform():
    _ensure_torch()
    return A.Compose([
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD, max_pixel_value=255.0),
        ToTensorV2(),
    ], additional_targets={"label": "mask"})


# ── Dataset ───────────────────────────────────────────────────────────────────

class TreeCrownDataset:
    """PyTorch Dataset for paired RGB/DTM tiles."""

    def __init__(self, df, training=True):
        self.df       = df.reset_index(drop=True)
        self.training = training
        if training:
            self.spatial_tf = _make_spatial_transform()
            self.pixel_tf   = _make_pixel_transform()
        else:
            self.test_tf = _make_test_transform()

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        _ensure_torch()
        row = self.df.iloc[idx]

        with rasterio.open(row["img_path"]) as src:
            img = src.read().transpose(1, 2, 0)
        with rasterio.open(row["dtm_path"]) as src:
            lbl = src.read(1).astype(np.float32)

        if self.training:
            out = self.spatial_tf(image=img, label=lbl)
            img, lbl = out["image"], out["label"]
            out = self.pixel_tf(image=img)
            img = out["image"]
            lbl = torch.from_numpy(lbl).unsqueeze(0)
        else:
            out = self.test_tf(image=img, label=lbl)
            img, lbl = out["image"], out["label"]
            if lbl.dim() == 2:
                lbl = lbl.unsqueeze(0)

        meta = {"tile_name": row["tile_name"], "site": row["site"],
                "crown_frac": float(row["crown_frac"])}
        return img, lbl, meta


# ── Model factory ─────────────────────────────────────────────────────────────

def _inject_dropout(module, p):
    for name, child in module.named_children():
        if isinstance(child, nn.Sequential):
            child.add_module("dropout", nn.Dropout2d(p=p))
        else:
            _inject_dropout(child, p)


def build_model(device):
    _ensure_torch()
    m = smp.Unet(
        encoder_name=ENCODER, encoder_weights=ENCODER_WEIGHTS,
        decoder_channels=DECODER_CHANNELS, in_channels=3,
        classes=1, activation=None)
    _inject_dropout(m.decoder, DECODER_DROPOUT)
    m = m.to(device)
    m = torch.compile(m)
    return m


# ── Train / val helpers ───────────────────────────────────────────────────────

def _train_one_epoch(model, loader, optimizer, scaler, criterion, device):
    model.train()
    total_sum = mae_sum = 0.0
    n = 0
    for imgs, lbls, _ in loader:
        imgs = imgs.to(device, non_blocking=True)
        lbls = lbls.to(device, non_blocking=True)
        optimizer.zero_grad()
        with torch.cuda.amp.autocast():
            preds = model(imgs)
            mae   = criterion(preds, lbls)
            l1    = sum(p.abs().sum() for p in model.parameters())
            loss  = mae + L1_LAMBDA * l1
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        scaler.step(optimizer)
        scaler.update()
        total_sum += loss.item()
        mae_sum   += mae.item()
        n += 1
    return total_sum / n, mae_sum / n


def _validate(model, loader, criterion, device):
    model.eval()
    mae_sum = 0.0
    n = 0
    with torch.no_grad():
        for imgs, lbls, _ in loader:
            imgs = imgs.to(device, non_blocking=True)
            lbls = lbls.to(device, non_blocking=True)
            with torch.cuda.amp.autocast():
                preds = model(imgs)
                mae   = criterion(preds, lbls)
            mae_sum += mae.item()
            n += 1
    return mae_sum / n


# ── Checkpoint helpers ────────────────────────────────────────────────────────

def _save_checkpoint(fold, epoch, model, optimizer, scheduler,
                     history, best_val, path):
    model_state = (model._orig_mod.state_dict()
                   if hasattr(model, "_orig_mod") else model.state_dict())
    torch.save({
        "fold": fold, "epoch": epoch, "model_state": model_state,
        "optim_state": optimizer.state_dict(),
        "sched_state": scheduler.state_dict(),
        "history": history, "best_val": best_val,
    }, path)


def _load_checkpoint(path, model, optimizer, scheduler, device):
    ckpt = torch.load(path, map_location=device)
    if hasattr(model, "_orig_mod"):
        model._orig_mod.load_state_dict(ckpt["model_state"])
    else:
        model.load_state_dict(ckpt["model_state"])
    optimizer.load_state_dict(ckpt["optim_state"])
    scheduler.load_state_dict(ckpt["sched_state"])
    return ckpt["fold"], ckpt["epoch"], ckpt["history"], ckpt["best_val"]


# ── Main training loop ───────────────────────────────────────────────────────

def run_training(epochs=EPOCHS, batch_size=BATCH_SIZE, n_folds=K_FOLDS):
    _ensure_torch()
    print("\n── Step 6: K-Fold Cross-Validation Training ──")

    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Device: {device}")
    if device.type == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")

    full_index_df = pd.read_csv(TILE_DIR / "tile_index.csv")
    train_df = full_index_df[full_index_df["split"] == "train"].reset_index(drop=True)
    test_df  = full_index_df[full_index_df["split"] == "test"].reset_index(drop=True)

    print(f"  Train tiles: {len(train_df)}  |  Test tiles (held out): {len(test_df)}")

    # Spatial buffer splits
    print(f"  Building spatial buffer splits (buffer={SPATIAL_BUFFER_PX}px)")
    folds = make_spatial_buffer_splits(
        train_df, n_folds=n_folds, buffer_px=SPATIAL_BUFFER_PX, seed=42)

    for i, (tr, va, buf) in enumerate(folds):
        print(f"    Fold {i+1}: train={len(tr)}  val={len(va)}  buffer={len(buf)}")

    pin_memory         = device.type == "cuda"
    criterion          = nn.L1Loss()
    global_best_val    = float("inf")
    global_best_ckpt   = CKPT_DIR / "ddt_best_global.pt"
    all_fold_histories = []

    print(f"\n{'='*65}")
    print(f"  {n_folds} folds  |  {epochs} epochs/fold  |  "
          f"Encoder: {ENCODER}  |  Batch: {batch_size}")
    print(f"{'='*65}")

    for fold_idx, (train_idx, val_idx, buffer_idx) in enumerate(folds):
        fold_num      = fold_idx + 1
        fold_train_df = train_df.iloc[train_idx].reset_index(drop=True)
        fold_val_df   = train_df.iloc[val_idx].reset_index(drop=True)

        print(f"\n{'─'*65}")
        print(f"  FOLD {fold_num}/{n_folds}  —  "
              f"train={len(fold_train_df)}  val={len(fold_val_df)}  "
              f"buffer={len(buffer_idx)}")
        print(f"{'─'*65}")

        # Weighted sampler
        site_counts    = fold_train_df["site"].value_counts().to_dict()
        sample_weights = fold_train_df["site"].map(
            lambda s: 1.0 / site_counts[s]).values.astype(np.float32)
        sampler = WeightedRandomSampler(
            weights=torch.from_numpy(sample_weights),
            num_samples=len(fold_train_df), replacement=True)

        train_ds = TreeCrownDataset(fold_train_df, training=True)
        val_ds   = TreeCrownDataset(fold_val_df,   training=False)

        train_loader = DataLoader(
            train_ds, batch_size=batch_size, sampler=sampler,
            num_workers=NUM_WORKERS, pin_memory=pin_memory,
            drop_last=True, persistent_workers=True, prefetch_factor=4)
        val_loader = DataLoader(
            val_ds, batch_size=batch_size, shuffle=False,
            num_workers=NUM_WORKERS, pin_memory=pin_memory,
            drop_last=False, persistent_workers=True, prefetch_factor=4)

        # Fresh model per fold
        model     = build_model(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
        warmup    = torch.optim.lr_scheduler.LambdaLR(
            optimizer,
            lr_lambda=lambda ep: (ep + 1) / WARMUP_EPOCHS if ep < WARMUP_EPOCHS else 1.0)
        plateau   = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="min", factor=LR_FACTOR, patience=LR_PATIENCE,
            threshold=1e-4, cooldown=5, min_lr=1e-6)
        scaler    = torch.cuda.amp.GradScaler()

        fold_latest = CKPT_DIR / f"ddt_latest_fold{fold_num}.pt"
        fold_best   = CKPT_DIR / f"ddt_best_fold{fold_num}.pt"

        start_epoch = 0
        history     = {"train_total": [], "train_mae": [], "val_mae": []}
        best_val    = float("inf")
        es_counter  = 0

        if fold_latest.exists():
            _, start_epoch, history, best_val = _load_checkpoint(
                fold_latest, model, optimizer, plateau, device)
            start_epoch += 1
            print(f"  Resuming at epoch {start_epoch}  (best val: {best_val:.4f})")

        for epoch in range(start_epoch, epochs):
            t0 = time.time()
            train_total, train_mae = _train_one_epoch(
                model, train_loader, optimizer, scaler, criterion, device)
            val_mae = _validate(model, val_loader, criterion, device)

            if epoch < WARMUP_EPOCHS:
                warmup.step()
            else:
                plateau.step(val_mae)

            lr = optimizer.param_groups[0]["lr"]
            history["train_total"].append(train_total)
            history["train_mae"].append(train_mae)
            history["val_mae"].append(val_mae)

            is_best = val_mae < best_val
            gmark   = ""

            if is_best:
                best_val   = val_mae
                es_counter = 0
                _save_checkpoint(fold_num, epoch, model, optimizer,
                                 plateau, history, best_val, fold_best)
                if best_val < global_best_val:
                    global_best_val = best_val
                    _save_checkpoint(fold_num, epoch, model, optimizer,
                                     plateau, history, best_val, global_best_ckpt)
                    gmark = " ◆GLOBAL"
            else:
                es_counter += 1

            if (epoch + 1) % SAVE_EVERY == 0 or epoch == epochs - 1:
                _save_checkpoint(fold_num, epoch, model, optimizer,
                                 plateau, history, best_val, fold_latest)

            elapsed = time.time() - t0
            bmark   = " ★" if is_best else ""
            es_info = (f"  [no improve: {es_counter}/{EARLY_STOP_PAT}]"
                       if not is_best else "")

            print(f"  F{fold_num} E{epoch+1:>3}/{epochs}  "
                  f"tr={train_mae:.4f}  val={val_mae:.4f}  "
                  f"lr={lr:.2e}  {elapsed:.0f}s{bmark}{gmark}{es_info}")

            if es_counter >= EARLY_STOP_PAT:
                print(f"\n  Early stop — fold {fold_num}")
                break

        print(f"  ✓ Fold {fold_num} best val MAE: {best_val:.4f}")
        all_fold_histories.append({
            "fold": fold_num, "best_val": best_val,
            "n_train": len(fold_train_df), "n_val": len(fold_val_df),
            "train_mae": history["train_mae"], "val_mae": history["val_mae"],
        })

        del model, optimizer, scaler
        torch.cuda.empty_cache()

    # Summary
    best_vals = [h["best_val"] for h in all_fold_histories]
    mean_val  = np.mean(best_vals)
    std_val   = np.std(best_vals)

    print(f"\n{'='*65}")
    print(f"  CV SUMMARY  —  mean val MAE: {mean_val:.4f} ± {std_val:.4f}")
    print(f"  Global best: {global_best_val:.4f}  →  {global_best_ckpt.name}")
    print(f"{'='*65}")

    # Save loss history
    rows = []
    for h in all_fold_histories:
        for ei, (tm, vm) in enumerate(zip(h["train_mae"], h["val_mae"]), 1):
            rows.append({"fold": h["fold"], "epoch": ei,
                         "train_mae": tm, "val_mae": vm})
    pd.DataFrame(rows).to_csv(CKPT_DIR / "loss_history.csv", index=False)


# ═════════════════════════════════════════════════════════════════════════════
#  Step 7 — Evaluation on held-out test tiles
# ═════════════════════════════════════════════════════════════════════════════

def _dtm_to_polygons(dtm, pixel_area, min_distance, threshold, min_area):
    """Watershed segmentation on a single-tile DTM, returns polygon dicts."""
    crown_mask = dtm >= threshold
    if crown_mask.sum() == 0:
        return []

    coords = peak_local_max(
        dtm, min_distance=min_distance,
        labels=crown_mask, threshold_abs=threshold)
    if len(coords) == 0:
        return []

    seed_mask = np.zeros(dtm.shape, dtype=bool)
    seed_mask[tuple(coords.T)] = True
    markers, _ = scipy_label(seed_mask)
    ws_labels  = watershed(-dtm, markers, mask=crown_mask)

    polygons = []
    for cid in np.unique(ws_labels):
        if cid == 0:
            continue
        px       = ws_labels == cid
        area_m2  = px.sum() * pixel_area
        if area_m2 < min_area:
            continue
        rows, cols = np.where(px)
        polygons.append({
            "row_min": int(rows.min()), "row_max": int(rows.max()),
            "col_min": int(cols.min()), "col_max": int(cols.max()),
            "area_m2": float(area_m2), "mask": px,
        })
    return polygons


def _mask_iou(a, b):
    inter = (a & b).sum()
    union = (a | b).sum()
    return inter / union if union > 0 else 0.0


def _evaluate_tile(pred_polys, gt_polys, iou_threshold):
    matched = set()
    TPs, FPs, FNs = [], [], []

    for gt in gt_polys:
        best_iou = best_idx = 0
        for pi, pred in enumerate(pred_polys):
            if pi in matched:
                continue
            if (pred["row_max"] < gt["row_min"] or pred["row_min"] > gt["row_max"] or
                pred["col_max"] < gt["col_min"] or pred["col_min"] > gt["col_max"]):
                continue
            iou = _mask_iou(pred["mask"], gt["mask"])
            if iou > best_iou:
                best_iou, best_idx = iou, pi
        if best_iou >= iou_threshold:
            TPs.append({"gt_area": gt["area_m2"],
                        "pred_area": pred_polys[best_idx]["area_m2"], "iou": best_iou})
            matched.add(best_idx)
        else:
            FNs.append({"gt_area": gt["area_m2"]})

    for pi, pred in enumerate(pred_polys):
        if pi not in matched:
            FPs.append({"pred_area": pred["area_m2"]})

    return TPs, FPs, FNs


def _compute_f1(TPs, FPs, FNs):
    tp, fp, fn = len(TPs), len(FPs), len(FNs)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1   = 2*prec*rec / (prec+rec) if (prec+rec) > 0 else 0.0
    return prec, rec, f1, tp, fp, fn


def run_evaluation(ckpt_path=None):
    _ensure_torch()
    print("\n── Step 7: Evaluation on Test Tiles ──")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    index_df = pd.read_csv(TILE_DIR / "tile_index.csv")
    test_df  = index_df[index_df["split"] == "test"].reset_index(drop=True)
    print(f"  Test tiles: {len(test_df)}")

    # Derive pixel area from transform
    with rasterio.open(test_df.iloc[0]["img_path"]) as src:
        px_x = src.transform.a
        px_y = abs(src.transform.e)
        pixel_area = px_x * px_y

    # Load model
    if ckpt_path is None:
        ckpt_path = CKPT_DIR / "ddt_best_global.pt"
    model = smp.Unet(
        encoder_name=ENCODER, encoder_weights=None,
        decoder_channels=DECODER_CHANNELS, in_channels=3,
        classes=1, activation=None)
    model = model.to(device)
    ckpt  = torch.load(ckpt_path, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    print(f"  Model loaded: {Path(ckpt_path).name}  "
          f"(fold={ckpt['fold']}  epoch={ckpt['epoch']+1}  "
          f"val={ckpt['best_val']:.4f})")

    eval_tf = A.Compose([
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD, max_pixel_value=255.0),
        ToTensorV2(),
    ])

    # Inference
    predictions   = {}
    ground_truths = {}
    with torch.no_grad():
        for _, row in tqdm(test_df.iterrows(), total=len(test_df),
                           desc="  Inference"):
            with rasterio.open(row["img_path"]) as src:
                img = src.read().transpose(1, 2, 0)
            with rasterio.open(row["dtm_path"]) as src:
                gt = src.read(1).astype(np.float32)

            inp = eval_tf(image=img)["image"].unsqueeze(0).to(device)
            pred = model(inp).squeeze().cpu().numpy()
            predictions[row["tile_name"]]   = np.clip(pred, 0, 100)
            ground_truths[row["tile_name"]] = gt

    # Watershed + matching
    all_TPs = {"overall": [], "small": [], "medium": [], "large": []}
    all_FPs = {"overall": [], "small": [], "medium": [], "large": []}
    all_FNs = {"overall": [], "small": [], "medium": [], "large": []}
    site_results = {}

    for _, row in test_df.iterrows():
        tn = row["tile_name"]
        pp = _dtm_to_polygons(predictions[tn], pixel_area,
                              MIN_DISTANCE, DTM_THRESHOLD, MIN_CROWN_AREA)
        gp = _dtm_to_polygons(ground_truths[tn], pixel_area,
                              MIN_DISTANCE, DTM_THRESHOLD, MIN_CROWN_AREA)
        TPs, FPs, FNs = _evaluate_tile(pp, gp, IOU_THRESHOLD)

        all_TPs["overall"].extend(TPs)
        all_FPs["overall"].extend(FPs)
        all_FNs["overall"].extend(FNs)

        for tp in TPs:
            all_TPs[size_class(tp["gt_area"])].append(tp)
        for fn in FNs:
            all_FNs[size_class(fn["gt_area"])].append(fn)
        for fp in FPs:
            all_FPs[size_class(fp["pred_area"])].append(fp)

        site = row["site"]
        if site not in site_results:
            site_results[site] = {"TPs": [], "FPs": [], "FNs": []}
        site_results[site]["TPs"].extend(TPs)
        site_results[site]["FPs"].extend(FPs)
        site_results[site]["FNs"].extend(FNs)

    # Print results
    print(f"\n{'='*62}")
    print(f"  EVALUATION  (IoU ≥ {IOU_THRESHOLD})")
    print(f"{'='*62}")

    print(f"\n  {'Class':<10} {'Prec':>7} {'Rec':>7} {'F1':>7} "
          f"{'TP':>6} {'FP':>6} {'FN':>6}")
    print(f"  {'-'*10} {'-'*7} {'-'*7} {'-'*7} {'-'*6} {'-'*6} {'-'*6}")

    for cls in ["small", "medium", "large", "overall"]:
        p, r, f1, tp, fp, fn = _compute_f1(all_TPs[cls], all_FPs[cls], all_FNs[cls])
        label = cls.capitalize() if cls != "overall" else "OVERALL"
        print(f"  {label:<10} {p:>7.3f} {r:>7.3f} {f1:>7.3f} "
              f"{tp:>6} {fp:>6} {fn:>6}")

    print(f"\n  {'Site':<20} {'Prec':>7} {'Rec':>7} {'F1':>7}")
    print(f"  {'-'*20} {'-'*7} {'-'*7} {'-'*7}")
    for site in sorted(site_results):
        p, r, f1, *_ = _compute_f1(
            site_results[site]["TPs"], site_results[site]["FPs"],
            site_results[site]["FNs"])
        print(f"  {site:<20} {p:>7.3f} {r:>7.3f} {f1:>7.3f}")

    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()

    return predictions, ground_truths


# ═════════════════════════════════════════════════════════════════════════════
#  Step 8 — Joint parameter sweep (DTM_THRESHOLD × MIN_DISTANCE)
# ═════════════════════════════════════════════════════════════════════════════

def run_parameter_sweep(ckpt_path=None):
    """Sweep DTM_THRESHOLD × MIN_DISTANCE on test tiles, return optimal params."""
    _ensure_torch()
    print("\n── Step 8: Parameter Sweep ──")

    device   = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    index_df = pd.read_csv(TILE_DIR / "tile_index.csv")
    test_df  = index_df[index_df["split"] == "test"].reset_index(drop=True)

    positive_sites = [s for s in test_df["site"].unique()
                      if not s.startswith("Negative")]
    test_pos = test_df[test_df["site"].isin(positive_sites)].reset_index(drop=True)
    print(f"  Positive test tiles: {len(test_pos)}")

    # Load model + predict — prefer global best, fall back to per-fold
    if ckpt_path is None:
        ckpt_path = CKPT_DIR / "ddt_best_global.pt"
        if not ckpt_path.exists():
            for fold in range(1, K_FOLDS + 1):
                p = CKPT_DIR / f"ddt_best_fold{fold}.pt"
                if p.exists():
                    ckpt_path = p
                    break

    model = smp.Unet(encoder_name=ENCODER, encoder_weights=None,
                     decoder_channels=DECODER_CHANNELS, in_channels=3,
                     classes=1, activation=None)
    model = model.to(device)
    ckpt  = torch.load(ckpt_path, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    print(f"  Model: {Path(ckpt_path).name}")

    eval_tf = A.Compose([
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD, max_pixel_value=255.0),
        ToTensorV2(),
    ])

    tile_data = []
    for _, row in tqdm(test_pos.iterrows(), total=len(test_pos),
                       desc="  Predicting"):
        with rasterio.open(row["img_path"]) as src:
            img = src.read().transpose(1, 2, 0)
            px_area = src.transform.a * abs(src.transform.e)
            bounds  = src.bounds
            px_x    = src.transform.a
            px_y    = abs(src.transform.e)
        with rasterio.open(row["dtm_path"]) as src:
            gt = src.read(1).astype(np.float32)

        inp  = eval_tf(image=img)["image"].unsqueeze(0).to(device)
        with torch.no_grad():
            pred = model(inp).squeeze().cpu().numpy()
        tile_data.append({
            "dtm_pred": np.clip(pred, 0, 100), "dtm_gt": gt,
            "pixel_area": px_area, "px_x": px_x, "px_y": px_y, "bounds": bounds,
        })

    del model, ckpt
    if device.type == "cuda":
        torch.cuda.empty_cache()

    # Pre-compute GT crowns (fixed params)
    gt_cache = {}
    for i, td in enumerate(tile_data):
        gt_crowns = _watershed_for_sweep(
            td["dtm_gt"], 1.0, 30, MIN_CROWN_AREA,
            td["pixel_area"], td["px_x"], td["px_y"], td["bounds"])
        gt_cache[i] = gt_crowns
    total_gt = sum(len(v) for v in gt_cache.values())
    print(f"  GT crowns: {total_gt}")

    # Sweep
    thresholds    = [5, 10, 15, 20, 25, 30, 35, 40]
    min_distances = [10, 15, 20, 25, 30, 40, 50]
    results       = []

    for thr in tqdm(thresholds, desc="  Sweep"):
        for md in min_distances:
            tp_tot = fp_tot = fn_tot = 0
            for i, td in enumerate(tile_data):
                pc = _watershed_for_sweep(
                    td["dtm_pred"], thr, md, MIN_CROWN_AREA,
                    td["pixel_area"], td["px_x"], td["px_y"], td["bounds"])
                tp, fp, fn = _match_crowns_geom(pc, gt_cache[i], IOU_THRESHOLD)
                tp_tot += tp; fp_tot += fp; fn_tot += fn

            prec = tp_tot / (tp_tot + fp_tot) if (tp_tot + fp_tot) > 0 else 0
            rec  = tp_tot / (tp_tot + fn_tot) if (tp_tot + fn_tot) > 0 else 0
            f1   = 2*prec*rec / (prec+rec) if (prec+rec) > 0 else 0
            results.append({"threshold": thr, "min_distance": md,
                            "f1": round(f1, 4), "precision": round(prec, 4),
                            "recall": round(rec, 4),
                            "tp": tp_tot, "fp": fp_tot, "fn": fn_tot})

    rdf  = pd.DataFrame(results)
    best = rdf.loc[rdf["f1"].idxmax()]
    rdf.to_csv(CKPT_DIR / "param_sweep_results.csv", index=False)

    print(f"\n{'='*60}")
    print(f"  OPTIMAL:  threshold={best['threshold']}  "
          f"min_dist={best['min_distance']}  F1={best['f1']:.4f}")
    print(f"  Precision={best['precision']:.4f}  Recall={best['recall']:.4f}")
    print(f"{'='*60}")

    return int(best["threshold"]), int(best["min_distance"])


def _watershed_for_sweep(dtm, threshold, min_distance, min_crown_area,
                         pixel_area, px_x, px_y, bounds):
    """Watershed returning (geom, area) tuples for IoU matching."""
    crown_mask = dtm >= threshold
    if crown_mask.sum() == 0:
        return []

    coords = peak_local_max(
        dtm, min_distance=min_distance,
        labels=crown_mask, threshold_abs=threshold)
    if len(coords) == 0:
        return []

    seed_mask = np.zeros(dtm.shape, dtype=bool)
    seed_mask[tuple(coords.T)] = True
    markers, _ = scipy_label(seed_mask)
    ws = watershed(-dtm, markers, mask=crown_mask)

    crowns = []
    for cid in np.unique(ws):
        if cid == 0:
            continue
        px   = ws == cid
        area = px.sum() * pixel_area
        if area < min_crown_area:
            continue

        rows, cols = np.where(px)
        r_min, r_max = int(rows.min()), int(rows.max())
        c_min, c_max = int(cols.min()), int(cols.max())
        local_h, local_w = r_max - r_min + 1, c_max - c_min + 1

        local_mask = np.zeros((local_h, local_w), dtype=np.uint8)
        local_mask[rows - r_min, cols - c_min] = 1

        local_tf = rasterio.transform.from_bounds(
            bounds.left + c_min * px_x,
            bounds.top  - (r_max + 1) * px_y,
            bounds.left + (c_max + 1) * px_x,
            bounds.top  - r_min * px_y,
            local_w, local_h)

        geom_list = [shape(g) for g, v in
                     rasterio.features.shapes(local_mask, transform=local_tf) if v == 1]
        if not geom_list:
            continue
        geom = geom_list[0] if len(geom_list) == 1 else unary_union(geom_list)
        crowns.append((geom, area))

    return crowns


def _match_crowns_geom(pred_crowns, gt_crowns, iou_threshold):
    """Match by polygon IoU, return (tp, fp, fn) counts."""
    if not gt_crowns and not pred_crowns:
        return 0, 0, 0
    if not gt_crowns:
        return 0, len(pred_crowns), 0
    if not pred_crowns:
        return 0, 0, len(gt_crowns)

    matched_gt = set()
    tp = fp = 0
    for pg, _ in pred_crowns:
        best_iou = best_gi = 0
        for gi, (gg, _) in enumerate(gt_crowns):
            if gi in matched_gt or not pg.intersects(gg):
                continue
            inter = pg.intersection(gg).area
            union = pg.area + gg.area - inter
            iou   = inter / union if union > 0 else 0
            if iou > best_iou:
                best_iou, best_gi = iou, gi
        if best_iou >= iou_threshold:
            tp += 1
            matched_gt.add(best_gi)
        else:
            fp += 1
    fn = len(gt_crowns) - len(matched_gt)
    return tp, fp, fn


# ═════════════════════════════════════════════════════════════════════════════
#  Step 9 — Full-city streaming inference
# ═════════════════════════════════════════════════════════════════════════════

def run_inference(ckpt_path=None, batch_size=INFER_BATCH_SIZE):
    _ensure_torch()
    print("\n── Step 9: Full-City Streaming Inference ──")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Clean GPU
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()

    with rasterio.open(EDMONDS_IMG) as src:
        img_h   = src.height
        img_w   = src.width
        img_crs = src.crs
        img_tf  = src.transform
        px_x    = src.transform.a
        px_y    = abs(src.transform.e)

    print(f"  Image: {img_w}×{img_h} px  "
          f"({img_w*px_x/1000:.1f}×{img_h*px_y/1000:.1f} km)")

    # Load model — prefer global best, fall back to per-fold
    if ckpt_path is None:
        ckpt_path = CKPT_DIR / "ddt_best_global.pt"
        if not ckpt_path.exists():
            for fold in range(1, K_FOLDS + 1):
                p = CKPT_DIR / f"ddt_best_fold{fold}.pt"
                if p.exists():
                    ckpt_path = p
                    break

    model = smp.Unet(encoder_name=ENCODER, encoder_weights=None,
                     decoder_channels=DECODER_CHANNELS, in_channels=3,
                     classes=1, activation=None)
    model = model.to(device)
    ckpt  = torch.load(ckpt_path, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    print(f"  Model: {Path(ckpt_path).name}  "
          f"(epoch={ckpt['epoch']+1}  val={ckpt['best_val']:.4f})")

    transform = A.Compose([
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD, max_pixel_value=255.0),
        ToTensorV2(),
    ])

    # Build tile origins (including edge tiles for full coverage)
    stride     = INFER_STRIDE
    pad        = INFER_PAD
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

    dtm_profile = {
        "driver": "GTiff", "dtype": "float32",
        "width": img_w, "height": img_h, "count": 1,
        "crs": img_crs, "transform": img_tf,
        "compress": "lzw", "nodata": 0.0, "BIGTIFF": "YES",
    }

    batch_imgs   = []
    batch_coords = []

    def flush(batch_imgs, batch_coords, dst):
        if not batch_imgs:
            return
        inp = torch.stack(batch_imgs).to(device)
        with torch.no_grad():
            pred = model(inp).squeeze(1).cpu().numpy()
        pred = np.clip(pred, 0, 100)

        for k, (ro, co) in enumerate(batch_coords):
            center   = pred[k, pad:pad+center_crop, pad:pad+center_crop]
            cr_end   = min(ro + center_crop, img_h)
            cc_end   = min(co + center_crop, img_w)
            ch, cw   = cr_end - ro, cc_end - co
            win      = rasterio.windows.Window(col_off=co, row_off=ro,
                                               width=cw, height=ch)
            dst.write(center[:ch, :cw][np.newaxis].astype(np.float32), window=win)

    with rasterio.open(DTM_OUT, "w", **dtm_profile) as dst:
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
                    tile = np.pad(tile, ((ph_top, ph_bot), (pw_left, pw_right), (0, 0)),
                                  mode="reflect")

                aug = transform(image=tile)
                batch_imgs.append(aug["image"])
                batch_coords.append((row_off, col_off))

                if len(batch_imgs) == batch_size:
                    flush(batch_imgs, batch_coords, dst)
                    batch_imgs   = []
                    batch_coords = []

                pbar.update(1)
            pbar.close()

            flush(batch_imgs, batch_coords, dst)

    dtm_mb = DTM_OUT.stat().st_size / 1e6
    print(f"\n  ✓ DTM written: {DTM_OUT}  ({dtm_mb:.0f} MB)")

    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()


# ═════════════════════════════════════════════════════════════════════════════
#  Step 10 — Chunked watershed → GeoPackage
# ═════════════════════════════════════════════════════════════════════════════

def _process_chunk(args):
    """Worker: run watershed on one chunk, return crown records."""
    (r0, c0, dtm_path, chunk_size, chunk_border,
     img_height, img_width, min_distance, dtm_threshold,
     min_crown_area, pixel_area, px_x, px_y, img_bounds) = args

    import rasterio
    import rasterio.windows
    import rasterio.features
    import numpy as np
    from scipy.ndimage import label as scipy_label
    from skimage.feature import peak_local_max
    from skimage.segmentation import watershed
    from shapely.geometry import shape, mapping

    r0b = max(0, r0 - chunk_border)
    c0b = max(0, c0 - chunk_border)
    r1b = min(img_height, r0 + chunk_size + chunk_border)
    c1b = min(img_width,  c0 + chunk_size + chunk_border)

    with rasterio.open(dtm_path) as src:
        win   = rasterio.windows.Window(col_off=c0b, row_off=r0b,
                                        width=c1b-c0b, height=r1b-r0b)
        chunk = src.read(1, window=win)

    crown_mask = chunk >= dtm_threshold
    if crown_mask.sum() == 0:
        return []

    coords = peak_local_max(
        chunk, min_distance=min_distance,
        labels=crown_mask, threshold_abs=dtm_threshold)
    if len(coords) == 0:
        return []

    seed_mask = np.zeros(chunk.shape, dtype=bool)
    seed_mask[tuple(coords.T)] = True
    markers, _ = scipy_label(seed_mask)
    ws = watershed(-chunk, markers, mask=crown_mask)

    records = []
    for cid in np.unique(ws):
        if cid == 0:
            continue
        px   = ws == cid
        area = px.sum() * pixel_area
        if area < min_crown_area:
            continue

        dtm_peak = float(chunk[px].max())
        dtm_mean = float(chunk[px].mean())

        rows, cols = np.where(px)
        abs_rows   = rows + r0b
        abs_cols   = cols + c0b

        cr, cc = int(abs_rows.mean()), int(abs_cols.mean())
        if cr < r0b + chunk_border and r0b > 0:
            continue
        if cr >= r1b - chunk_border and r1b < img_height:
            continue
        if cc < c0b + chunk_border and c0b > 0:
            continue
        if cc >= c1b - chunk_border and c1b < img_width:
            continue

        r_min, r_max = int(abs_rows.min()), int(abs_rows.max())
        c_min, c_max = int(abs_cols.min()), int(abs_cols.max())
        local_h, local_w = r_max - r_min + 1, c_max - c_min + 1

        local_mask = np.zeros((local_h, local_w), dtype=np.uint8)
        local_mask[abs_rows - r_min, abs_cols - c_min] = 1

        local_tf = rasterio.transform.from_bounds(
            img_bounds.left + c_min * px_x,
            img_bounds.top  - (r_max + 1) * px_y,
            img_bounds.left + (c_max + 1) * px_x,
            img_bounds.top  - r_min * px_y,
            local_w, local_h)

        geom_list = [shape(g) for g, v in
                     rasterio.features.shapes(local_mask, transform=local_tf) if v == 1]
        if not geom_list:
            continue

        geom = geom_list[0] if len(geom_list) == 1 else unary_union(geom_list)

        def _sc(a):
            if a <= 4.9: return "small"
            if a <= 15.9: return "medium"
            return "large"

        records.append({
            "geometry":   mapping(geom),
            "area_m2":    round(float(area), 2),
            "diameter_m": round(2 * (area / 3.14159) ** 0.5, 2),
            "size_class": _sc(area),
            "dtm_peak":   round(dtm_peak, 1),
            "dtm_mean":   round(dtm_mean, 1),
        })
    return records


def run_watershed(min_distance=MIN_DISTANCE, dtm_threshold=DTM_THRESHOLD):
    print(f"\n── Step 10: Chunked Watershed → {CROWNS_OUT.name} ──")

    os.environ["OMP_NUM_THREADS"]      = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"]      = "1"

    with rasterio.open(DTM_OUT) as src:
        img_h   = src.height
        img_w   = src.width
        img_crs = src.crs
        px_x    = src.transform.a
        px_y    = abs(src.transform.e)
        px_area = px_x * px_y
        bounds  = src.bounds

    n_workers = min(N_WATERSHED_WORKERS, multiprocessing.cpu_count())
    print(f"  Workers: {n_workers}  |  threshold={dtm_threshold}  "
          f"min_dist={min_distance}")

    schema = {
        "geometry": "Polygon",
        "properties": {
            "crown_id": "str", "area_m2": "float", "diameter_m": "float",
            "size_class": "str", "dtm_peak": "float", "dtm_mean": "float",
        },
    }

    chunk_args = [
        (r0, c0, str(DTM_OUT), CHUNK_SIZE, CHUNK_BORDER,
         img_h, img_w, min_distance, dtm_threshold,
         MIN_CROWN_AREA, px_area, px_x, px_y, bounds)
        for r0 in range(0, img_h, CHUNK_SIZE)
        for c0 in range(0, img_w, CHUNK_SIZE)
    ]
    print(f"  Chunks: {len(chunk_args)}")

    crown_counter = 0

    with fiona.open(CROWNS_OUT, "w", driver="GPKG",
                    crs=img_crs.to_wkt(), schema=schema) as dst:
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = {executor.submit(_process_chunk, a): a for a in chunk_args}
            with tqdm(total=len(chunk_args), desc="  Watershed",
                      mininterval=120.0) as pbar:
                for future in as_completed(futures):
                    records = future.result()
                    out_records = []
                    for rec in records:
                        out_records.append({
                            "geometry": rec["geometry"],
                            "properties": {
                                "crown_id":   f"EDM_{crown_counter:07d}",
                                "area_m2":    rec["area_m2"],
                                "diameter_m": rec["diameter_m"],
                                "size_class": rec["size_class"],
                                "dtm_peak":   rec["dtm_peak"],
                                "dtm_mean":   rec["dtm_mean"],
                            },
                        })
                        crown_counter += 1
                    dst.writerecords(out_records)
                    pbar.set_postfix({"crowns": f"{crown_counter:,}"})
                    pbar.update(1)

    gpkg_mb = CROWNS_OUT.stat().st_size / 1e6
    print(f"\n  ✓ Watershed complete")
    print(f"  Total crowns: {crown_counter:,}")
    print(f"  GeoPackage:   {CROWNS_OUT}  ({gpkg_mb:.0f} MB)")


# ═════════════════════════════════════════════════════════════════════════════
#  Main
# ═════════════════════════════════════════════════════════════════════════════

STEPS = [
    "discover", "inspect", "preprocess", "dtm", "tile",
    "train", "evaluate", "sweep", "inference", "watershed",
]


def main():
    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]

    parser = argparse.ArgumentParser(
        description="Phase 0 — 2020 anchored instance segmentation")
    parser.add_argument("--step", type=str, default=None,
                        choices=STEPS,
                        help="Run a single step (default: run all)")
    parser.add_argument("--skip-training",  action="store_true",
                        help="Skip training — use existing checkpoint")
    parser.add_argument("--skip-inference", action="store_true",
                        help="Stop after evaluation (no full-city inference)")
    parser.add_argument("--epochs",     type=int, default=EPOCHS)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--folds",      type=int, default=K_FOLDS)
    parser.add_argument("--ckpt",       type=str, default=None,
                        help="Checkpoint path for evaluation/inference")

    args = parser.parse_args(filtered)

    print("=" * 65)
    print("  PHASE 0 — 2020 Anchored Instance Segmentation")
    print("  Edmonds Temporal Active Learning Pipeline")
    print("=" * 65)

    # Resolve which steps to run
    if args.step:
        steps_to_run = {args.step}
        print(f"  Mode: single step — {args.step}")
    else:
        steps_to_run = set(STEPS)
        if args.skip_training:
            steps_to_run.discard("train")
            print(f"  Skip training: True")
        if args.skip_inference:
            steps_to_run -= {"inference", "watershed"}
            print(f"  Skip inference: True")
        print(f"  Steps: {', '.join(s for s in STEPS if s in steps_to_run)}")

    ckpt_path = Path(args.ckpt) if args.ckpt else None

    # Ensure output directories
    for d in [LABEL_DIR, TILE_DIR, CKPT_DIR, OUT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Discover ──────────────────────────────────────
    image_paths = shapefile_paths = site_labels = None
    if "discover" in steps_to_run or any(
            s in steps_to_run for s in
            ["inspect", "preprocess", "dtm", "tile"]):
        image_paths, shapefile_paths, site_labels = discover_sites()

    # ── Step 2: Inspect ───────────────────────────────────────
    raw_gdfs = {}
    if "inspect" in steps_to_run:
        raw_gdfs = inspect_all(image_paths, shapefile_paths, site_labels)
    elif any(s in steps_to_run for s in ["preprocess", "dtm", "tile"]):
        # Load shapefiles without full inspection
        for path, label in zip(shapefile_paths, site_labels):
            if path is not None:
                raw_gdfs[label] = gpd.read_file(path)

    # ── Step 3: Preprocess ────────────────────────────────────
    gdfs = {}
    if "preprocess" in steps_to_run and raw_gdfs:
        gdfs = preprocess_shapefiles(raw_gdfs, site_labels)
        validate_preprocessed(gdfs, image_paths, site_labels)
    elif any(s in steps_to_run for s in ["dtm", "tile"]) and raw_gdfs:
        gdfs = preprocess_shapefiles(raw_gdfs, site_labels)

    # ── Step 4: Distance transforms ───────────────────────────
    dtm_paths = image_paths_dict = None
    if "dtm" in steps_to_run and gdfs:
        dtm_paths, image_paths_dict = generate_all_dtms(
            gdfs, image_paths, site_labels)
    elif "tile" in steps_to_run:
        # DTMs must already exist
        image_paths_dict = {l: p for l, p in zip(site_labels, image_paths)}
        dtm_paths = {l: LABEL_DIR / f"{l.lower()}_dtm.tif" for l in site_labels}

    # ── Step 5: Tiling ────────────────────────────────────────
    if "tile" in steps_to_run and dtm_paths:
        run_tiling(dtm_paths, image_paths_dict, site_labels)

    # ── Step 6: Training ──────────────────────────────────────
    if "train" in steps_to_run:
        _ensure_torch()
        run_training(epochs=args.epochs, batch_size=args.batch_size,
                     n_folds=args.folds)

    # ── Step 7: Evaluation ────────────────────────────────────
    if "evaluate" in steps_to_run:
        _ensure_torch()
        run_evaluation(ckpt_path=ckpt_path)

    # ── Step 8: Parameter sweep ───────────────────────────────
    opt_thr = DTM_THRESHOLD
    opt_md  = MIN_DISTANCE
    if "sweep" in steps_to_run:
        _ensure_torch()
        opt_thr, opt_md = run_parameter_sweep(ckpt_path=ckpt_path)

    # ── Step 9: Full-city inference ───────────────────────────
    if "inference" in steps_to_run:
        _ensure_torch()
        run_inference(ckpt_path=ckpt_path, batch_size=INFER_BATCH_SIZE)

    # ── Step 10: Watershed ────────────────────────────────────
    if "watershed" in steps_to_run:
        run_watershed(min_distance=opt_md, dtm_threshold=opt_thr)

    # ── Done ──────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  PHASE 0 COMPLETE")
    print(f"{'='*65}")
    print(f"  Outputs:")
    if DTM_OUT.exists():
        print(f"    DTM:    {DTM_OUT}")
    if CROWNS_OUT.exists():
        print(f"    Crowns: {CROWNS_OUT}")
    if (CKPT_DIR / "ddt_best_global.pt").exists():
        print(f"    Model:  {CKPT_DIR / 'ddt_best_global.pt'}")
    print(f"\n  Next: run phase1_preprocess.py for multi-year feature extraction")


if __name__ == "__main__":
    multiprocessing.set_start_method("fork", force=True)
    main()
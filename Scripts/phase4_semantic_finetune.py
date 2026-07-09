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
  %run phase4_semantic_finetune.py --infer-batch 32     # inference memory (fits 24 GB; def 32)
  %run phase4_semantic_finetune.py --force-citywide     # uniform citywide recipe on ALL tiers
  %run phase4_semantic_finetune.py --run-tag rgbonly    # suffix outputs _rgbonly (no overwrite)
╚══════════════════════════════════════════════════════════════════╝
"""

import multiprocessing
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from phase4seg.cli import main


if __name__ == "__main__":
    multiprocessing.set_start_method("fork", force=True)
    main()

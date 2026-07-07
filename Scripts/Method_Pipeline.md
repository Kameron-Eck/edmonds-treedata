# Edmonds Tree Canopy Study — Multi-Temporal Segmentation Pipeline Methodology
## Study Overview
Individual tree crown detection and temporal monitoring across 24 years (2000–2024) for the City of Edmonds, Washington. The pipeline produces per-year semantic canopy masks (canopy/non-canopy classification) for all 18 imagery acquisitions at their native resolution. For the 9 acquisitions at 7.5cm and 14.9cm GSD — the only resolutions where individual crowns are reliably separable — the pipeline additionally produces individual crown polygons via instance segmentation using distance transform regression and watershed. A temporal tracking framework anchored to the 2020 detection links outputs across years.
---
## Imagery Stack
18 ortho-imagery acquisitions spanning 15 unique calendar years from 4 sources:
| Year | Source | GSD (cm) | Bands | CRS | Coverage | Seg Tier |
|------|--------|----------|-------|-----|----------|----------|
| 2000 | King County | 59.7 | RGB | EPSG:3857 | Full | Semantic only |
| 2002 | King County | 59.7 | RGB | EPSG:3857 | Full | Semantic only |
| 2005 | King County | 29.9 | RGB | EPSG:3857 | Full | Semantic only |
| 2007 | King County | 29.9 | RGB | EPSG:3857 | Full | Semantic only |
| 2009 | King County | 29.9 | RGB | EPSG:3857 | Full | Semantic only |
| 2013 | King County | 14.9 | RGB | EPSG:3857 | Full | Instance + Semantic |
| 2015 | King County | 14.9 | RGB | EPSG:3857 | Full | Instance + Semantic |
| 2016 | Snohomish Co. | 50.0 | RGBI | EPSG:2285 | 67% | Semantic only |
| 2017 | City of Edmonds | 7.5 | RGB | EPSG:3857 | Full | Instance + Semantic |
| 2019 | King County | 14.9 | RGB | EPSG:3857 | Full | Instance + Semantic |
| 2019n | NAIP | 60.0 | RGBI | EPSG:26910 | Full | Semantic only |
| 2020 | City of Edmonds | 7.5 | RGB | EPSG:3857 | Full | Instance + Semantic (anchor) |
| 2021 | King County | 14.9 | RGB | EPSG:3857 | Full | Instance + Semantic |
| 2021s | Snohomish Co. | 50.0 | RGBI | EPSG:2285 | 67% | Semantic only |
| 2022 | City of Edmonds | 7.5 | RGB | EPSG:3857 | Full | Instance + Semantic |
| 2022n | NAIP | 60.0 | RGBI | EPSG:26910 | Full | Semantic only |
| 2023 | King County | 14.9 | RGB | EPSG:3857 | Full | Instance + Semantic |
| 2024 | City of Edmonds | 7.5 | RGB | EPSG:3857 | Full | Instance + Semantic |
**Semantic segmentation (all 18 acquisitions, all resolutions):** Binary canopy mask and canopy polygons produced for every year at native GSD. No upscaling is applied; all imagery is processed at its original resolution.
**Instance segmentation (9 acquisitions at 7.5cm and 14.9cm only):** Individual crown polygons produced via DTM regression + watershed, in addition to the semantic mask. Instance segmentation is not applied to imagery coarser than 14.9cm because crown boundaries are not reliably separable at those resolutions (Qin et al., 2023). The 7 acquisitions at 29.9–60.0cm receive semantic segmentation only.
| Resolution | Years | Tile ground area | Outputs |
|------------|-------|-----------------|---------|
| 7.5cm (City of Edmonds) | 2017, 2020, 2022, 2024 | 38.4m × 38.4m | Instance crowns + semantic mask |
| 14.9cm (King County) | 2013, 2015, 2019, 2021, 2023 | 76.8m × 76.8m | Instance crowns + semantic mask |
| 29.9cm (King County) | 2005, 2007, 2009 | 153.6m × 153.6m | Semantic mask only |
| 50.0cm (Snohomish Co.) | 2016, 2021s | 307.2m × 307.2m | Semantic mask only (67% coverage) |
| 59.7cm (King County) | 2000, 2002 | 305.7m × 305.7m | Semantic mask only |
| 60.0cm (NAIP) | 2019n, 2022n | 307.2m × 307.2m | Semantic mask only |
---
## Training Data
- **3,000 hand-traced crown polygons** from 5 training sites on 2020 City of Edmonds 7.5cm RGB imagery
- These polygons serve as the single source of ground truth for all years
- Polygons are projected onto each year's imagery (reprojecting CRS as needed) to create year-specific training labels
- For instance segmentation: projected polygons are converted to per-crown normalised distance transform maps (DTM)
- For semantic segmentation: projected polygons are dissolved into a binary canopy/non-canopy mask
---
## Architecture
### Base Model (from Phase 0)
- **Architecture:** U-Net with ResNet-101 encoder (via segmentation_models_pytorch)
- **Encoder weights:** ImageNet pretrained, then trained on 2020 Edmonds data in Phase 0
- **Decoder channels:** (1024, 512, 256, 128, 64)
- **Decoder dropout:** 0.3
- **Input:** 3-channel RGB, 512×512 tiles, ImageNet normalised
- **Phase 0 checkpoint:** ddt_best_global.pt — trained on 2020 7.5cm imagery with L1 loss on DTM regression
### Instance Segmentation Head (7.5cm and 14.9cm imagery only)
- **Applies to:** 9 acquisitions — 2017, 2020, 2022, 2024 (7.5cm) and 2013, 2015, 2019, 2021, 2023 (14.9cm)
- **Output:** 1 channel, continuous DTM values (0–100), no activation
- **Loss:** L1 (MAE) on distance transform map
- **Post-processing:** Threshold DTM → peak_local_max → watershed → crown polygons
- **Label generation:** Per-crown normalised distance from centroid (1=boundary, 100=centroid)
- **Why these resolutions only:** At 7.5cm a typical 5m crown is ~2,100 pixels; at 14.9cm it is ~700 pixels. Both are above the ~800 pixel/crown threshold identified by Qin et al. (2023) for reliable instance detection. At 29.9cm the same crown is ~175 pixels — below the threshold and too coarse for the DTM gradient to support stable watershed separation.
### Semantic Segmentation Head (all 18 acquisitions, 7.5–60.0cm)
- **Applies to:** All 18 acquisitions at their native resolution — no upscaling applied
- **Output:** 1 channel, binary canopy probability, sigmoid activation
- **Loss:** BCEWithLogitsLoss (or BCE with sigmoid activation)
- **Post-processing:** Threshold probability map → binary canopy mask → polygonize (no watershed — semantic seg classifies pixels as canopy/non-canopy without separating individual crowns)
- **Label generation:** Binary rasterisation of projected 2020 crown polygons (1=canopy, 0=non-canopy)
Both heads share the same encoder and decoder architecture. The only difference is the final activation and loss function. The pretrained Phase 0 weights initialise both variants. For the 9 high-resolution acquisitions (7.5cm and 14.9cm), both heads are fine-tuned and run independently, producing two complementary outputs per year. For the 9 coarser acquisitions (29.9–60.0cm), only the semantic head is used.
---
## Per-Year Fine-Tuning Pipeline
For each of the 18 imagery acquisitions (except 2020 which is already done):
### Step 1: Label Projection
1. Load the 3,000 hand-traced crown polygons (EPSG:3857)
2. Reproject to the target year's CRS if needed (EPSG:2285 for Snohomish, EPSG:26910 for NAIP)
3. Verify which training sites fall within the year's coverage footprint (relevant for Snohomish 67% coverage years)
4. For instance seg: generate per-crown DTM at the target year's native resolution
5. For semantic seg: rasterise polygons into a binary canopy mask at the target year's native resolution
### Step 2: Tiling
1. For each training site with coverage in the target year:
   - Load the year's imagery and the projected labels (DTM or binary mask)
   - Tile into 512×512 patches at the year's native resolution
   - Apply the same tiling parameters as Phase 0 (stride=512, negative sampling rate=0.15, test fraction=0.20)
2. Note: at coarser resolutions, 512×512 tiles cover more ground area, so fewer tiles per training site
   - At 7.5cm: 512px = 38.4m → ~200 tiles per typical training site
   - At 15cm: 512px = 76.8m → ~50 tiles per site
   - At 30cm: 512px = 153.6m → ~12 tiles per site
   - At 60cm: 512px = 307.2m → ~3 tiles per site
3. For coarser resolution years with very few tiles, consider reducing tile stride to increase overlap, or using all tiles for training without a test split (validate against 2020 detections instead)
### Step 3: Fine-Tuning
1. Load the Phase 0 pretrained model (ddt_best_global.pt)
2. For semantic seg: replace the output activation and loss function
3. Fine-tuning strategy:
   - **Phase A (encoder frozen):** Train only the decoder for N epochs with learning rate LR_FINETUNE
   - **Phase B (full model):** Unfreeze encoder, train all parameters for M epochs with lower learning rate (LR_FINETUNE / 10)
   - Use ReduceLROnPlateau scheduler
   - Early stopping based on validation loss
4. Augmentation: use the same augmentation pipeline as Phase 0, including:
   - Spatial: flips, rotations, grid distortion, elastic transform
   - Pixel: blur, brightness/contrast, hue/saturation, shadow, fog
   - Downscale augmentation (simulates resolution degradation)
5. Save best checkpoint per year: ddt_best_{year}.pt and/or sem_best_{year}.pt
6. For the 9 acquisitions at 7.5cm and 14.9cm: fine-tune both the instance and semantic models separately
### Step 4: Full-City Inference
1. Load the year's fine-tuned model(s)
2. Streaming inference across the full city extent (same as Phase 0 Step 9):
   - Overlapping tiles with center-crop stitching
   - Stride = 256, pad = 128 (for 512 tile size)
   - Batch inference on GPU
3. Output: full-city DTM raster (instance) and/or probability raster (semantic)
### Step 5: Post-Processing
**Instance segmentation (9 acquisitions at 7.5cm and 14.9cm only):**
1. Chunked watershed segmentation (same as Phase 0 Step 10)
2. Peak local max → markers → watershed on negative DTM
3. Filter by minimum crown area (2.0 m²)
4. Output: crown polygon GeoPackage with crown_id, area_m2, diameter_m, size_class
**Semantic segmentation (all 18 acquisitions at native resolution — no watershed):**
1. Threshold probability map (e.g., p > 0.5)
2. Optional morphological operations (opening to remove noise, closing to fill small gaps)
3. Polygonize to canopy mask polygons
4. Output: canopy mask GeoPackage
---
## Temporal Crown Linking
The pipeline uses a hybrid anchor-and-discovery approach: 2020 serves as the primary anchor for the majority of stable trees, while independent detections from all other instance segmentation years are used to discover trees that the 2020 anchor would miss — specifically, trees planted after 2020 and trees removed before 2020. These change events are the most analytically valuable outputs of a 24-year temporal study.
After all years are processed:
### Step 1: Primary Anchor Matching (2020-Based)
- The 2020 crown polygons serve as the primary canonical ID layer (highest quality: trained directly on hand-annotated 2020 data at 7.5cm)
- For each other instance seg year (2013, 2015, 2017, 2019, 2021, 2022, 2023, 2024):
  - Spatial join that year's detected crowns to the 2020 crown layer using IoU or centroid containment
  - Crowns matching a 2020 polygon inherit its global crown_id
  - Crowns with no 2020 match are collected into an "unmatched" pool for that year
  - 2020 crowns with no match in year X are flagged as potential removals or detection failures in year X
### Step 2: Supplementary Discovery — Pre-2020 Removals
- Collect all unmatched crowns from pre-2020 instance seg years (2013, 2015, 2017, 2019)
- Spatially cluster unmatched crowns across these years: if an unmatched crown in year A overlaps spatially with an unmatched crown in year B (using IoU or centroid proximity), they are grouped as the same tree
- A tree detected as unmatched in multiple pre-2020 years (e.g., present in 2013 and 2015 but absent from 2020) is classified as a **pre-2020 removal**
- Assign new global crown_ids to these discovered removals, with lifecycle metadata:
  - First detected: earliest year with a detection
  - Last detected: latest year with a detection
  - Presumed removal window: between last detection and next instance seg year without detection
- Use the detection from the finest-resolution year as the canonical geometry for these crowns
### Step 3: Supplementary Discovery — Post-2020 Plantings
- Collect all unmatched crowns from post-2020 instance seg years (2021, 2022, 2023, 2024)
- Spatially cluster unmatched crowns across these years: recurring unmatched crowns in the same location across multiple post-2020 years are classified as **post-2020 plantings**
- A single-year unmatched crown that does not recur may be a detection artifact or a very recent planting — flag for review
- Assign new global crown_ids to confirmed new plantings, with lifecycle metadata:
  - First detected: earliest post-2020 year with a detection
  - Confirmed if detected in 2+ post-2020 years
### Step 4: Build the Complete Canonical Crown Layer
- Combine three sources into the final canonical crown layer:
  1. **2020 anchor crowns** (~90% of total): stable trees detected in 2020, with global IDs inherited from Phase 0
  2. **Discovered removals** (~5–10%): trees detected in pre-2020 years but absent from 2020, with new global IDs and removal lifecycle labels
  3. **Discovered plantings** (~1–5%): trees detected in post-2020 years but absent from 2020, with new global IDs and planting lifecycle labels
- This combined layer becomes the reference for all subsequent temporal analysis, including semantic year feature extraction
- Each crown carries a lifecycle classification: stable, removed (with estimated removal window), or planted (with first detection year)
### Step 5: Semantic Segmentation Year Assessment
- Project the complete canonical crown layer (not just 2020 crowns) onto each year's semantic canopy mask
- For each canonical crown polygon, compute the fraction of pixels classified as canopy in year X
- High canopy fraction (>70%) → tree likely present
- Low canopy fraction (<30%) → tree likely absent or significantly reduced
- Intermediate → uncertain, flag for review
- For discovered removals: the semantic assessment provides independent confirmation and may narrow the removal window (e.g., a tree detected by instance seg in 2015 shows 80% canopy fraction in the 2009 semantic mask and 15% in the 2016 semantic mask → removal likely occurred 2015–2016)
- For discovered plantings: backward semantic assessment may detect the planting earlier than instance seg (e.g., a tree first detected by instance seg in 2022 might show emerging canopy fraction in the 2019n NAIP semantic mask)
### Cross-Validation Between Instance and Semantic Outputs
- For the 9 acquisitions at 7.5cm and 14.9cm that produce both outputs, compare instance-derived canopy area against semantic mask area as a consistency check
- Significant disagreement indicates potential model issues: instance seg may miss small crowns that semantic seg captures, or semantic seg may merge adjacent crowns that instance seg separates
- Agreement between the two methods strengthens confidence in canopy estimates for those years
### Feature Extraction (All Years)
- For every 2020 crown polygon, extract spectral statistics under the polygon from each year's imagery:
  - Band means, standard deviations
  - Within-year z-scores and percentile ranks
  - GRVI = (G−R)/(G+R) as NDVI proxy (all years)
  - GCC = G/(R+G+B) as illumination-robust vegetation index (all years)
  - True NDVI where NIR available (2016, 2019n, 2021s, 2022n)
  - Building-relative normalised values (compare crown spectra to nearby building rooftops)
- These features feed the temporal active learning pipeline for canopy change classification
---
## Key Hyperparameters
### Fine-Tuning (to be validated per year)
| Parameter | Value | Notes |
|-----------|-------|-------|
| LR_FINETUNE (decoder) | 5e-5 | Phase A: encoder frozen |
| LR_FINETUNE (full) | 5e-6 | Phase B: all layers |
| EPOCHS_PHASE_A | 20 | Decoder-only training |
| EPOCHS_PHASE_B | 30 | Full model training |
| EARLY_STOP_PAT | 15 | Patience for early stopping |
| BATCH_SIZE | 10 | Same as Phase 0 (adjust for GPU memory) |
| TILE_SIZE | 512 | Same as Phase 0 |
### Watershed (7.5cm and 14.9cm Instance Seg Years Only)
| Parameter | Value | Notes |
|-----------|-------|-------|
| DTM_THRESHOLD | Optimised in Phase 0 sweep | May need per-year adjustment |
| MIN_DISTANCE | Optimised in Phase 0 sweep | May need per-year adjustment |
| MIN_CROWN_AREA | 2.0 m² | Same as Phase 0 |
### Semantic Thresholding (All Years)
| Parameter | Value | Notes |
|-----------|-------|-------|
| CANOPY_PROB_THRESHOLD | 0.5 | Binary threshold on sigmoid output |
| MIN_CANOPY_PATCH | 3.0 m² | Minimum patch size after thresholding |
| MORPH_KERNEL | 3×3 | For opening/closing operations |
---
## Validation Strategy
### Per-Year Validation
- **Instance seg years:** Compare detected crowns against projected 2020 annotations using IoU-based matching (same as Phase 0 Step 7). Report F1 by size class.
- **Semantic seg years:** Compare canopy mask against projected 2020 binary labels using pixel-level accuracy, IoU, and Dice.
- **Instance-semantic agreement (high-res years):** Compare total canopy area and spatial distribution between instance and semantic outputs. Report agreement metrics.
- **Cross-year consistency check:** For adjacent instance seg years (e.g., 2019 vs 2021), compare crown counts and total canopy area. Large discrepancies suggest model or labelling issues.
### Temporal Validity Check
- Visually inspect each training site in each year's imagery to verify that the projected 2020 annotations are spatially valid (trees actually present at those locations)
- For years far from 2020 (especially 2000–2009), expect some annotation noise from trees planted/removed between that year and 2020
- Document which training sites are excluded from which years due to land use change or coverage gaps
### Independent QC — NDVI + LiDAR-height reference (added 2026-07-05)
Per-year validation against the 2020 crown mask reprojected onto other years is **circular**:
real pre-2020 canopy change counts as model "error", so recall measured that way is not
trustworthy. A model-independent reference is built for the NIR-bearing years and used as the
honest accuracy instrument.
- **Reference definition.** For a year with a NIR band (2016 snoh, 2019n/2022n/2021s NAIP/snoh):
  `NDVI = (NIR − R)/(NIR + R)`. Raw NDVI counts **grass** as vegetation — which the model
  rejects on purpose — so the honest CANOPY reference is `canopy = (NDVI ≥ veg_thresh) AND
  (CHM height ≥ min_height)`, i.e. vegetation that is also tall. 2016 is the cleanest instrument:
  it carries its own NIR **and** is temporally matched to the 2016 LiDAR CHM. Defaults
  `veg_thresh = 0.2`, `min_height = 2 m` (both swept and reported — QC design choices, not model
  hyperparameters). Script: `phase4_qc_ndvi.py` → `phase4/qc/ndvi_ref_{year}.tif`
  (0 non-veg / 1 grass / 2 canopy / 255 nodata).
- **Scoring.** `phase4_qc_score.py` scores the model probability raster against the reference
  (recall, precision, grass-rejection, threshold sweep) → `phase4/qc/qc_report.csv`, kept
  **separate** from the circular `semantic_eval_report.csv`. The prob raster and reference share
  the year's grid for NIR years, so scoring is a direct pixel confusion.
- **Site attribution.** `phase4_qc_site.py` zooms a lat/lon window and cross-tabs the missed
  (FN) canopy by CHM height + NDVI to attribute misses (threshold vs stale-CHM suppression vs
  out-of-distribution spectral).
- **Baseline finding (2016).** Honest recall vs this reference = **0.60** (the circular number
  was 0.94) at precision **0.97** — the model is precise but under-predicts ~40% of real canopy.
  Lowering the operating threshold recovers only ~+2.6 pp, so the misses are structural, not a
  threshold artifact. The worst misses are tall (>5 m), green (NDVI ~0.48) **deciduous** crowns
  (e.g. Edmonds marsh) absent from the conifer-only fine-tune sites.
- **Principle: LiDAR informs, never vetoes.** The single 2016 CHM raises confidence for tall
  vegetation but must never zero out an otherwise-canopy pixel — using it as a hard gate
  suppresses real canopy in off-years where height changed. Height influence must be one-sided/soft.
- **No-NIR years (e.g. 2000).** Have no NDVI reference; the honest instrument there is stratified
  random **photo-interpretation** (Olofsson et al. 2014) with area-adjusted estimates and 95% CIs
  — never raw pixel counts or map-minus-map differencing.
### Independent QC — NOAA C-CAP land cover reference (added 2026-07-07)
The NDVI+CHM reference above is **shared-axis contaminated**: its canopy class is `NDVI ∧ CHM`,
and two of the models being ranked (CHM-input, aux-height) learn from that same CHM, so it cannot
rank those variants honestly. NOAA's **Coastal Change Analysis Program (C-CAP) High-Resolution
Land Cover** is fully independent — it never saw the model, the 2020 labels, or the project CHM.
It is the first non-circular yardstick (rigor ladder: circular proxy < C-CAP < human photo-interp).
- **EVALUATION ONLY — never training.** C-CAP is used solely to score; never a training/label
  source, so the pipeline stays reproducible where no C-CAP exists (training uses only aerial
  imagery + the 2020 labels). The scorer is therefore **reference-agnostic** — C-CAP for Edmonds,
  but equally hand-drawn validation polygons or photo-interp points elsewhere (`--ref-scheme binary`).
- **Reference product / data.** NOAA C-CAP High-Resolution Land Cover, 1 m, uint8, EPSG:26910
  (UTM 10N NAD83), clipped to the Edmonds AOI (7431×5952) and stored
  `Full_Image/Pipeline Imagery/ccap_{2016,2021}_hires_lc.tif` (+ D: mirror). **2016** = Snohomish
  County bulk `.img` (HFA), clipped via `/vsicurl` windowed range reads (never the 15.7 GB `.ige`
  spill). **2021** = Puget Sound V2 via the Digital Coast `CCAP_High_Resolution_Landcover`
  ImageServer `exportImage` (mosaic locked to OBJECTID 45), tiled 2×1 under the 4100-px height cap
  and mosaicked to the 2016 grid. (C-CAP 2016→2021 is itself an independent canopy-**change**
  reference for later.)
- **Hi-res legend quirks (handled).** The hi-res product collapses developed intensity (2016: all
  developed → 2 Impervious; 2021 V2 has 2 + 4) and codes forest as a single **11 Upland Forest**
  (no 9/10/11 deciduous/evergreen/mixed split). The scorer's baked C-CAP map absorbs both (2→
  developed, 11→forest; absent standard codes contribute 0 px). Full class→group map is printed on
  every run for audit.
- **Canopy definition.** The model targets tall canopy (deciduous or coniferous), sometimes
  forested wetland, so the **primary** recall reference is `forest ∪ wetland` (codes {11,13}).
  Two flanking definitions bracket sensitivity: `forest_only` and `forest ∪ wetland ∪ scrub`
  (scrub is short woody). Areal nesting is monotone (ref-canopy 29.2% ⊆ 29.5% ⊆ 32.0%); recall is
  NOT — adding scrub drops it (model rejects scrub, recall 0.25), which validates excluding it.
- **Scoring.** `phase4_qc_indep.py` reprojects the reference onto the year's model-prob grid
  (`WarpedVRT`, nearest — categorical-safe) and reports recall / precision / grass-rejection under
  the three canopy definitions, plus a **per-surface delineation**: each land-cover group's
  canopy-call rate is the model's *recall* for canopy groups and its *false-positive rate* for
  non-canopy groups (grass / developed / barren / water / emergent wetland) — attributing both
  under-prediction and false alarms by surface type. Outputs `phase4/qc/qc_indep_report.csv` +
  `qc_indep_surfaces_{year}.csv` + `qc_indep_{year}.txt`, separate from the circular
  `semantic_eval_report.csv`, the NDVI `qc_report.csv`, and `flicker_report.csv`. Scored at model
  resolution (mirrors `phase4_qc_score.py`); the effective independent sample is the reported
  1 m²-cell count (~31.3 M for 2016), not the raw 1.35 B valid pixels.
- **Baseline finding (2016 model vs C-CAP 2016, deployed thr 0.4615).** Primary recall **0.684**,
  precision **0.865**, grass-rejection **0.935**. Per surface: upland-forest recall **0.682** (the
  under-prediction, confirmed independently), forested-wetland recall **0.899** (the model recalls
  forested wetland *well* — the marsh confusion is mostly in **emergent/herbaceous wetland**, FP-rate
  0.34), scrub recall 0.255. False alarms are chiefly developed (FP-rate 0.033 over 32% of area) and
  grass (0.066); water is clean (0.006). The two independent instruments **bracket** the truth —
  NDVI+CHM 0.59/0.96 (harsher recall, softer precision) vs C-CAP 0.68/0.87 (softer recall, harsher
  precision) — report both, never a single number.
- **Caveat: land COVER, not a canopy mask.** C-CAP classes are areal (forest = trees ≥5 m over
  >20% of an area with a ~1 m MMU), so a forest polygon includes small canopy gaps and street trees
  over roads get labeled Impervious — a definitional-disagreement floor exists in both FN and FP.
  C-CAP is independent of the model's CHM axis, which makes it the trustworthy arbiter for **ranking**
  CHM-based variants (via `--prob <archived_variant.tif>`); treat the absolute recall/precision as
  bracketed by the two references, with human photo-interp (Olofsson) as the eventual tiebreaker.
- **Under-prediction autopsy — WHY forest is missed.** `phase4_qc_forest_misses.py` splits C-CAP
  upland-forest pixels into recalled (TP) vs missed (FN) and compares distributions (prob, RGB,
  brightness/saturation, NDVI, GRVI, CHM height), plus a coarse FN-density raster + a top-N
  missed-stand shortlist (lon/lat) for site staging. C-CAP only *locates* misses — never a label
  (portability). **2016 finding:** the misses are **not** a sensor/exposure artefact (Δbrightness
  +2 DN, saturation flat) — they are **spectral + structural**: 69% of misses have prob<0.12
  (confident / out-of-distribution, *not* a threshold fix), NDVI 0.35 vs 0.57 recalled (Δ−0.22,
  lower GRVI → deciduous/broadleaf the conifer-only training under-recognises), and height 11.8 m vs
  23.8 m (the model recalls tall dark conifers, misses shorter lighter deciduous — still real trees).
  The write-up framing is therefore a **conifer-biased spectral domain**, and the fix is to *teach*
  deciduous canopy (stage positive sites at the top-FN stands), not to lower the threshold.
### Deciduous / positive training coverage
The fine/medium per-year models take positive labels from per-site hand-traced crown polygons
(`polygons/{site}_crowns_review.gpkg`); a site **without** a crown file is demoted to a pure
negative. To teach out-of-distribution canopy (deciduous marsh), a positive site's crowns can be
**derived by polygonising the Phase-3 2020 canopy mask** inside the footprint (the 2020 anchor
already labels it), via `make_positive_site.py` (safe staged → `--commit`). Coarse years (≥50 cm,
e.g. 2016) instead train on the citywide 2020 mask and ignore curated positive sites, so their
deciduous recall is addressed by substituting the high-resolution 2015 flagship product.
---
## Literature Basis
This methodology is supported by:
- **DDT architecture:** Li et al. (2025), Freudenberg et al. (2022) — U-Net + distance transform + watershed for individual tree crown delineation
- **Fine-tuning with small local data:** Weinstein et al. (2020) — cross-site learning shows fine-tuning with small hand-labeled sets matches local models; Burmeister et al. (2025) — fine-tuning DeepForest with limited data and few epochs substantially improves performance
- **Frozen encoder strategy:** Howard & Ruder (2018) — gradual unfreezing and discriminative learning rates; Li et al. (2024) — frozen encoder transfer validated for U-Net in remote sensing
- **Catastrophic forgetting mitigation:** Yang et al. (2024) — comprehensive survey showing forgetting increases with aggressive fine-tuning; Zheng et al. (2025) — selective low-rank adaptation preserves pretrained features
- **Object-based robustness to misregistration:** Chen et al. (2019), Wang et al. (2021) — OBIA absorbs small registration errors; Stow et al. (2013) — county ortho products achieve pixel to sub-pixel co-registration
- **Multi-resolution U-Net for urban canopy:** Wang & Fan (2021) — U-Net performs well for canopy mapping from 16cm to 100cm; Qin et al. (2023) — crown resolution concept defining optimal detection range
- **Large-scale instance mapping:** Brandt et al. (2020), Ventura et al. (2024) — U-Net scales to city/state/continental individual tree inventories
- **Sparse annotation fine-tuning:** Giannetti et al. (2025) — CNN-based models outperform transformers in low-data regimes
- **Spatial cross-validation:** Roberts et al. (2017), Ploton et al. (2020) — spatial autocorrelation inflates standard CV accuracy estimates; validates 77m spatial buffer in training splits
- **RGB vegetation indices:** Motohka et al. (2010) — GRVI as site-independent phenological indicator; Sonnentag et al. (2012) — GCC as illumination-robust alternative; Zhang et al. (2023) — GCC outperforms GRVI at canopy scale
- **Radiometric normalization:** Hessel et al. (2020) — automatic PIF-based normalization for long multi-sensor time series
- **Comparable temporal studies:** Velasquez-Camacho et al. (2025) — 18-year urban tree monitoring with deep learning; Healy et al. (2022) — 62-year UTC analysis using aerial photos
---
## Output Summary
| Year | GSD | Instance Output | Semantic Output |
|------|-----|-----------------|-----------------|
| 2000 | 59.7cm | — | Canopy mask + polygons |
| 2002 | 59.7cm | — | Canopy mask + polygons |
| 2005 | 29.9cm | — | Canopy mask + polygons |
| 2007 | 29.9cm | — | Canopy mask + polygons |
| 2009 | 29.9cm | — | Canopy mask + polygons |
| 2013 | 14.9cm | Crown polygons + attributes | Canopy mask + polygons |
| 2015 | 14.9cm | Crown polygons + attributes | Canopy mask + polygons |
| 2016 | 50.0cm | — | Canopy mask + polygons (67%) |
| 2017 | 7.5cm | Crown polygons + attributes | Canopy mask + polygons |
| 2019 | 14.9cm | Crown polygons + attributes | Canopy mask + polygons |
| 2019n | 60.0cm | — | Canopy mask + polygons |
| 2020 | 7.5cm | Crown polygons + attributes (anchor) | Canopy mask + polygons |
| 2021 | 14.9cm | Crown polygons + attributes | Canopy mask + polygons |
| 2021s | 50.0cm | — | Canopy mask + polygons (67%) |
| 2022 | 7.5cm | Crown polygons + attributes | Canopy mask + polygons |
| 2022n | 60.0cm | — | Canopy mask + polygons |
| 2023 | 14.9cm | Crown polygons + attributes | Canopy mask + polygons |
| 2024 | 7.5cm | Crown polygons + attributes | Canopy mask + polygons |
All outputs are GeoPackage format with CRS matching the source imagery.
---
*Document Version: 4.0 — May 22, 2026*
*Based on literature review of 68 papers across 8 search phases*
# Edmonds Tree Canopy Study — Multi-Temporal Segmentation Pipeline Methodology
## Study Overview
**Canopy cover assessment for the City of Edmonds, Washington: a binary canopy mask per
aerial acquisition, at native resolution, across the whole archive. Semantic segmentation
only.**

Per-crown temporal validity intervals are derived afterwards by scoring the **fixed 2020
crown layer** against each year's semantic mask (`qc/build_validity_intervals.py`) — not
by detecting crowns per year.

**Instance segmentation is DEFERRED, not cancelled** (Kam, 2026-08-29). Phase 0 produced
the 222,435-crown layer once, from 2020, and is frozen. The instance method is documented
below because it is real and will be revisited; it is **not** a current output, and
nothing in the Phase 4 path runs it.

> **Counts, GSD span and band splits are NOT restated here.** They live in
> `pipeline/phase4seg/config.py: YEAR_CATALOG` and are generated into
> [`STATUS.md`](STATUS.md), which CI regenerates and diffs. Restating them in prose is
> what produced the drift corrected on 2026-08-29, when this file and `CLAUDE.md` both
> described an archive that had not existed for weeks.
---
## Imagery Stack
The measured imagery characterisation (rasters, sources, resolution, coverage, colour
comparability) lives in one home: `Scripts/IMAGERY_FACTS.md`. The counts, GSD span and
band splits are generated into [`STATUS.md`](STATUS.md) from `YEAR_CATALOG`.

This section used to carry a resolution table. It has been removed rather than
corrected, and the reason is the point: it was a hand-copy of the catalog, and it
drifted three separate ways at once — an acquisition count that had not been right for
weeks, PRE-CORRECTION GSD values (7.5 / 14.9 / 29.9 / 50.0 / 59.7 cm, superseded
2026-08-18 when the numbers were found to be CRS units rather than ground centimetres),
and a row keyed on `2022n`, an acquisition renamed to `2023n` in `5a12da5`. A reader
chasing that year looked for a file nothing writes.

The irony is instructive and is left on the record: the paragraph above this one has
said since 2026-08-19 that a table was removed for being "stale twice over" — and the
replacement table went stale in the same three ways.

**Semantic segmentation, every acquisition, all resolutions.** Binary canopy mask +
polygonised GPKG for every year at native GSD. No upscaling: all imagery is processed at
its original resolution.

**Instance segmentation — DEFERRED, not a current output.** The method is preserved
under Architecture below. It was scoped to the finest tiers only, on the ground that a
crown needs roughly 800+ pixels for reliable separation (Qin et al., 2023); at the coarse
end of this archive a crown is 5-15 pixels across, which is two orders of magnitude
below that.
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
### Instance Segmentation Head — **DEFERRED (Kam, 2026-08-29). Not a current output.**

> Preserved because instance is deferred, not cancelled, and this method is real work
> that will be revisited. **Nothing in the Phase 4 path runs it**; Phase 0 produced the
> 222,435-crown layer once, from 2020, and is frozen on `smp==0.3.4` (never load it in a
> phase3/4 runtime). The GSD figures below are the PRE-2026-08-18 values and are left
> as-written because they are what the scoping decision was made on — re-derive current
> resolutions from `YEAR_CATALOG`, not from this section.

- **Applied to (as scoped then):** 9 acquisitions — 2017, 2020, 2022, 2024 (7.5cm) and 2013, 2015, 2019, 2021, 2023 (14.9cm)
- **Output:** 1 channel, continuous DTM values (0–100), no activation
- **Loss:** L1 (MAE) on distance transform map
- **Post-processing:** Threshold DTM → peak_local_max → watershed → crown polygons
- **Label generation:** Per-crown normalised distance from centroid (1=boundary, 100=centroid)
- **Why these resolutions only:** At 7.5cm a typical 5m crown is ~2,100 pixels; at 14.9cm it is ~700 pixels. Both are above the ~800 pixel/crown threshold identified by Qin et al. (2023) for reliable instance detection. At 29.9cm the same crown is ~175 pixels — below the threshold and too coarse for the DTM gradient to support stable watershed separation.
### Semantic Segmentation Head — **THE current pipeline**
- **Applies to:** every acquisition, at native resolution — no upscaling. Counts and the
  GSD span are in [`STATUS.md`](STATUS.md); the archive spans a 20× resolution range, so
  no single figure describes it.
- **Output:** 1 channel (`classes=1`), binary canopy probability, sigmoid at inference
- **Loss:** masked **BCE + Dice**, `BCE_WEIGHT` 0.5 / `DICE_WEIGHT` 0.5 (`config.py`),
  selected per tier by `TIER_LOSS_MODE` — currently `bce_dice` on all three. `focal_dice`
  is available via `--loss-mode`. Pure Dice is `--bce-weight 0`.
  A signed-distance **boundary term** (Kervadec) exists behind `--boundary-weight`,
  **off by default**, applied in Phase B only.
- **All loss terms are IGNORE-aware.** Masks are three-state — 0 background, 1 canopy,
  **255 IGNORE** — and 255 is excluded from every term. Any new term must do the same or
  it silently trains on unlabelled pixels.
- **Post-processing:** threshold the probability map → binary canopy mask → polygonise to
  GPKG (`step_postproc`). No watershed: semantic segmentation classifies pixels, it does
  not separate individual crowns.
- **Label generation:** the citywide 2020 mask projected onto the target year
  (`--force-citywide`, which every queue job passes). Two other label sources exist in
  the engine — per-site crown polygons and `--anchor-labels` — see "Label Projection".

The semantic head is the deployed model. It shares the encoder and decoder with the
deferred instance head; they differ in the final activation and the loss.
---
## Per-Year Fine-Tuning Pipeline
For every acquisition except the 2020 anchor (already done):
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
**Semantic segmentation (every acquisition, native resolution, no watershed):**
1. Threshold probability map (e.g., p > 0.5)
2. Optional morphological operations (opening to remove noise, closing to fill small gaps)
3. Polygonize to canopy mask polygons
4. Output: canopy mask GeoPackage
---
## Temporal Crown Linking — **DEFERRED WITH INSTANCE. Read the current method first.**

> **What actually happens today**, and it is much simpler than the five steps below.
> There are no per-year crown detections, so there is nothing to link. Instead
> `qc/build_validity_intervals.py` takes the **fixed 2020 crown layer** and scores each
> crown against each year's **semantic mask**:
>
>     cover >= --present-hi (0.5)   PRESENT
>     cover <= --absent-lo  (0.15)  ABSENT
>     between                       UNSURE      (never assigned to a class)
>     NaN                           UNOBSERVED  (outside the scored footprint; never 0)
>
> and derives `valid_to` = latest PRESENT year, `valid_from` = earliest PRESENT year with
> no ABSENT between it and `valid_to`. Same three-state discipline as the masks. One arm
> family per run — mixing recipes inside a crown's time series would attribute recipe
> differences to the tree.
>
> **The consequence worth stating plainly:** with a fixed 2020 crown layer, the pipeline
> can say a 2020 tree was *absent* earlier, but it cannot discover a crown that existed
> in 2005 and was gone by 2020, nor one planted after 2020 — there is no per-year
> detector to find them. The anchor-and-discovery design below exists precisely to
> recover those, and recovering them is what instance segmentation is deferred *for*.

The design below is preserved for when instance is picked up again. It assumes per-year
instance detections, which the current pipeline does not produce.

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
  - True NDVI where NIR is available — the NIR-bearing labels are generated into
    [`STATUS.md`](STATUS.md); do not hand-list them, that list has been wrong twice
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

### Operating-point protocol (THE home for how a threshold is chosen; 2026-08-27)

**Measured problem.** Five identical repeats of the 2021s fine-tune (same recipe,
same seed, same A100 — `noise_r1..r5`) selected best-F1 thresholds of **.440 .499
.499 .490 .457** while their F1 differed by ~.001 across that span: the F1 curve
has a flat plateau, so its argmax is unstable even when the model is not. Scored
honestly vs C-CAP those repeats span **recall .6402–.6685 (sd .0100)** and
**precision .8181–.8325 (sd .0052)** — see the noise-floor entry in `CHATLOG.md`
(2026-08-27) and `qc_indep_report.csv` rows tagged `noise_r*`.

**Rules.**
1. **Model quality is judged on curve-level metrics** (AUROC, and PR-AUC where
   canopy prevalence matters), never on a single thresholded recall/precision.
   A thresholded pair describes a *product*, not a model.
2. **Best-F1 is NOT the deployment rule.** It is reported, never deployed alone —
   its argmax moved ±.03 for a .001 F1 gain, which then moves recall by ~2σ.
3. **Deployment picks ONE of two stable rules, stated per campaign:**
   - **fixed 0.5** — used when years must be comparable and no per-year deployed
     threshold exists. This is what the 2026-08-27 PoC used (its `evaluate` step
     was seeded-skipped, so no per-year operating point was ever produced).
   - **precision-floor** — the lowest threshold meeting a fixed precision target.
     Preferred when years must mean the same thing rather than use the same
     number; the eval already computes a precision-floor point.
4. **Repeat years: ensemble-then-threshold.** Averaging same-recipe repeats does
   NOT raise accuracy (their errors are correlated: mean-of-5 for 2021s scored at
   or slightly above the singles' mean at matched precision, below it at fixed
   threshold) but it replaces a .028-recall lottery with one deterministic
   artifact. If an ensemble is deployed, **re-select its threshold on the
   ensemble's own curve** — the mean raster's curve is shifted relative to its
   members'.
5. **Comparability rails.** Two numbers may be compared only if they share the
   reference raster, the canopy definition, AND the scored footprint (a citywide
   row vs a sector-AOI row is not a comparison — different land composition).
   Any reported difference smaller than the measured σ is stated as
   indistinguishable, not as a winner.
6. **Provenance.** Every deployed threshold has exactly one home:
   `phase4/qc/qc_indep_report.csv`, `live=1 primary=1`. Scoring tools never
   invent one; borrowing another arm's threshold is explicit and recorded
   (`phase4_golden_gate.py --threshold-from`).

**Open.** The sigma above is a **lower bound** — same seed, so it measures
hardware nondeterminism plus threshold selection only. True retrain sigma needs
a `--seed` flag (not built). Until it exists, no A/B smaller than ~2σ recall
(~.02) is worth GPU time.

### MEASURED 2026-08-29 — matched-precision recall is ~3x noisier than the curve metrics

The `--seed` flag landed and the first seed-varied pair was run (2009, identical
recipe, identical tiles, **only the training seed differs**):

| | AUROC | PR-AUC | recall @ matched precision |
|---|---|---|---|
| seed 42 | .9210 | .8632 | **.6989** |
| seed 1234 | .9194 | .8620 | **.6680** |

**Three points of recall from a seed change** — 3x the banked .0100 floor — while
AUROC moved **.0016** and PR-AUC **.0012**. The instability is not in the model;
it is in the *metric*. Matched-precision recall requires solving for a threshold
that hits a target precision, so any small shift in the probability distribution
moves that threshold and swings recall. A curve metric has no threshold to move.

**Consequences, and rule 1 above already implied them — this section exists because
I wrote that rule and then read every verdict off the noisy instrument anyway:**

1. **AUROC and PR-AUC are the VERDICT metrics.** Report matched-precision recall as
   a product characteristic, never as the evidence that one arm beat another.
2. **Re-read on curve metrics before quoting any A/B from before this date.** Doing
   so on the 2026-08-28/29 arms *strengthened* Node C (AUROC +.0116 = 7x the seed
   spread), *weakened* the damage curve's recall headline (5.5 pp = 1.8x), and turned
   the chm2 result from a clean null into genuinely mixed (AUROC −.0057, PR-AUC +.0022).
3. **n=1 pair is not a sigma.** A third seed is running; treat 3 pp as an order of
   magnitude, not a measured spread.
4. Still unmeasured and probably larger: **split variance**. Tiling binds its seed at
   import, so `--seed` holds the train/val/test partition fixed by design.

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
- **Reference definition.** For a year with a NIR band (see [`STATUS.md`](STATUS.md)
  for the current list):
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
e.g. 2016) instead train on the citywide 2020 mask and ignore curated positive sites. (The
2015-flagship substitution once suggested here was KILLED — CHATLOG 2026-08.)

#### Label provenance (E06, 2026-08-25)
What each year's model was actually taught from, and where that fact is recorded:

| Label source | Years / condition |
|---|---|
| Citywide 2020 mask (projected model prediction — the borrowed-label caveat, CLAUDE.md Gotchas) | every queue job today (`--force-citywide`) |
| + corrected-label ADD-only overlay `canopy_additions_{y}.tif` | only when `--add-canopy-mask` is passed — **no live run to date** (0 of 56 manifests) |
| Per-site crown polygons | fine/medium recipe when citywide is NOT forced (currently unused — see Gotchas) |

Run-level provenance lives in **`phase4/runs/{run_id}/manifest.json`** (`labels` block: source
mask path+size, overlay path/size/mtime, force_citywide) and nowhere else; the overlay artifact
carries its own `*.lineage.json` sidecar (params, pixel counts, sha256, build date).
Contamination status of the deployed numbers: **no `live=1` row in `qc_indep_report.csv` is
known to be overlay-trained** — the 2016 live row (rec .5937 / prec .9593, 2026-07-06) is
consistent with the pre-overlay baseline (.605/.970, CHATLOG:633) and the corrected run's
inference died before producing a scorable raster (CHATLOG:530-541); stated as a
reconstruction, since manifests postdate those July runs. Circularity mechanics live in
`litwatch_robustness.md:1050`; the one-home caveat in CLAUDE.md ("only 2020 has real hand
labels").
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
**Per acquisition**, `step_postproc` writes two artifacts to `phase4/masks/`:

  edmonds_canopy_mask_{label}{_tag}.tif    binary canopy raster
  edmonds_canopy_mask_{label}{_tag}.gpkg   polygonised canopy

plus `edmonds_canopy_prob_{label}{_tag}.tif` from `step_inference`.

The per-year table that stood here has been removed. It was the THIRD hand-copy of
`YEAR_CATALOG` in this file, and it carried the same three defects as the other two:
pre-2026-08-18 GSD values, a row for `2022n` which no longer exists under that name,
and an Instance Output column describing a
product that is not produced. Which years exist, at what GSD, and which have been
scored is generated into [`STATUS.md`](STATUS.md) — that table is regenerated and
diffed by CI, so it cannot drift the way these three did.

All outputs are GeoPackage format with CRS matching the source imagery.
---
*Document Version: 4.0 — May 22, 2026*
*Based on literature review of 68 papers across 8 search phases*
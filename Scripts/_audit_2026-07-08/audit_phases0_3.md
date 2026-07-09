# Code Audit — Phases 0–3 (Edmonds Temporal Active Learning Pipeline)

Auditor: rigorous correctness/crash + inefficiency pass. Every finding cites `file:line`
read directly from source. Domain invariants (3-state masks, native-res, Colab `-f` filter,
local-then-copy, LOSO-honesty, torch-Colab-only) treated as INTENTIONAL, not flagged.

Scripts audited: phase0_instance_seg.py, phase1_preprocess.py, phase1a_autolabel.py,
phase1b_sampling.py, phase1c_review.py, phase1d_classifier.py, phase2_data_prep.py,
phase3_semantic_dev.py, phase3_make_segmentation_png.py.

---

## CRITICAL

### C1 — phase0_instance_seg.py:1823-1824 — `.union(*geom_list[1:])` crashes full-city watershed on ≥3-shape crowns
- Severity: CRITICAL | Category: bug | Confidence: high
- `geom = geom_list[0].union(*geom_list[1:])`. Shapely `BaseGeometry.union` accepts exactly ONE
  positional geometry. Works by accident when `geom_list` has 2 items; raises
  `TypeError: union() takes from 2 to 3 positional arguments but N were given` whenever a
  watershed component decomposes into 3+ disjoint polygons from `rasterio.features.shapes()`
  (plausible: `shapes()` is 4-connected while the labeled region can be effectively 8-connected
  via diagonal touches).
- Why real: this is `_process_chunk`, the Step 10 worker that generates the 222k-crown city GPKG.
  `future.result()` at line 1888 has no try/except, so ONE bad chunk aborts the entire multi-hour
  city run. The sibling `_watershed_for_sweep` (line 1546) correctly uses `unary_union(geom_list)`
  for the identical situation — proving this is an inconsistency/bug, not a deliberate shortcut
  (`_process_chunk`'s local imports don't even pull in `unary_union`).
- Fix: replace with `unary_union(geom_list)` (add `from shapely.ops import unary_union` to the
  worker's local imports); wrap `future.result()` in try/except to log-and-skip a failed chunk.

---

## HIGH

### H1 — phase3_make_segmentation_png.py:310-311 — IoU counts IGNORE (255) as ground-truth canopy
- Severity: HIGH | Category: bug | Confidence: medium
- `iou = ((pred & (gt>0.5)).sum() / max(1, (pred | (gt>0.5)).sum()))`. `gt` loaded at line 243 as
  `src.read(1).astype(np.float32)` with no 255 handling. `gt>0.5` is True for canopy(1) AND
  IGNORE(255), so IGNORE pixels are counted as GT-positive in both intersection and union,
  corrupting the displayed IoU on any tile containing IGNORE. This is the project's headline
  proof-of-concept figure, so the wrong number is user-visible.
- Fix: `valid = gt != 255; iou = ((pred & (gt>0.5) & valid).sum() / max(1, ((pred|(gt>0.5)) & valid).sum()))`.

### H2 — phase2_data_prep.py:254 — `step_overlay` builds window from site bounds without reprojecting into raster CRS
- Severity: HIGH | Category: bug | Confidence: high
- `w = rasterio.windows.from_bounds(*sb, transform=src.transform)` with `sb = site["bounds"]`
  (site photo CRS, typically EPSG:3857, set line 88). `src` is opened from
  `ip = ap if ap.exists() else np_` (line 244) — when the aligned 3857 file is missing and it
  falls back to the native file, `src.crs` can be EPSG:2285 or EPSG:26910. Unlike `step_coverage`
  (lines 203-204) which correctly reprojects site bounds into the raster CRS first, `step_overlay`
  never does. The script itself flags aligned files can be missing (step_catalog, 105-108), so this
  path is reachable. Result: garbage/degenerate crop window for non-3857 native sources.
- Fix: reproject `sb` (or `box(*sb)`) into `src.crs` before `from_bounds`, matching `step_coverage`.

### H3 — phase1a_autolabel.py:290 — impervious-raster CRS fetched but never validated/reprojected before rasterizing crowns
- Severity: HIGH | Category: bug | Confidence: medium
- `_compute_impervious_rasterize()` captures `imp_crs = src.crs` (290) then rasterizes
  `crowns.geometry` against `imp_transform` (296-316) with no `crowns.crs != imp_crs` check —
  though every other loader in the codebase does this check. If CRS differ, `rasterize()` silently
  produces wrong per-pixel crown assignments → wrong `imp_frac` → corrupts FP2 (`imp_frac>=0.80`)
  and TP1 (`imp_frac<0.20`) auto-label rules that bootstrap the whole active-learning loop.
- Fix: `if crowns.crs != imp_crs: crowns = crowns.to_crs(imp_crs)` before building shapes.

### H4 — phase0_instance_seg.py:731-732 — Step 5 held-out test split is random per-tile (site-stratified), not spatially buffered / LOSO
- Severity: HIGH | Category: bug (evaluation honesty) | Confidence: medium
- `train_test_split(tile_names, stratify=sites, ...)` puts all 5 sites in both train and test with
  no spatial buffer — unlike `make_spatial_buffer_splits` (SPATIAL_BUFFER_PX=1024) used for K-fold CV.
  Step 7/8 "held-out test" F1 comes from tiles that can sit immediately adjacent to training tiles
  (same stand) → the spatial-autocorrelation inflation CLAUDE.md Rule #5 exists to prevent. Worse,
  Step 8's DTM_THRESHOLD/MIN_DISTANCE sweep is tuned against this same non-independent set and baked
  in as the Step 10 full-city default.
- Fix: apply spatial-buffer (or true LOSO) when carving the Step 5 test set, not only within K-fold.

---

## MEDIUM

### M1 — phase1d_classifier.py:642-650 — Platt calibration fit and scored on the SAME validation split (circular)
- Severity: MED-HIGH | Category: bug | Confidence: high
- `platt.fit(raw_probs_val, y_val)` (645) then `brier_score_loss(y_val, cal_probs_val)` (650) reports
  "Brier after calibration" on the same `y_val` used to fit the calibrator → in-sample, optimistic.
  Violates Rule #5. Fix: 3-way train/calib/test split or `CalibratedClassifierCV` (CV-based).

### M2 — phase3_semantic_dev.py:1545-1558 — dead/miscomputed "edge coverage" tiling block in step_inference
- Severity: MED | Category: bug + inefficiency | Confidence: high
- Main grid `range(0,img_h,stride)`×`range(0,img_w,stride)` already fully covers the raster (each
  center-crop write clipped via `min(ro+center_crop,img_h)`, center_crop==stride). The extra edge
  tiles are positioned at `img_h - TILE_SIZE`/`img_w - TILE_SIZE` (512) instead of `- stride` (256),
  so they land 256px short of the true edge, overwriting already-correct predictions (last-write-wins,
  no blending) → wasted inference + minor non-deterministic seams, zero useful edge work.
- Fix: delete the block, or use `stride` not `TILE_SIZE`.

### M3 — phase3_make_segmentation_png.py:299,314 — GT colormap renders IGNORE(255) as the canopy color
- Severity: MED | Category: bug | Confidence: medium
- `gt_cmap = ListedColormap([(0,0,0,0),(0.11,0.62,0.46,1.0)])` + `imshow(gt, vmin=0, vmax=1)`.
  Matplotlib clips out-of-range to the last colormap entry, so `gt==255` renders as the same teal as
  real canopy in the Ground-truth panel — visually indistinguishable. Same root cause as H1.
- Fix: `np.ma.masked_where(gt==255, gt)` (or set_bad/transparent) before display.

### M4 — phase1c_review.py:229-251 — `_check_conflict()` linear-scans the entire reviews CSV on every /label POST
- Severity: MED | Category: inefficiency/bottleneck | Confidence: high
- Each label submission re-reads/re-parses the whole `reviews_live.csv` (`for r in csv.DictReader(f)`).
  Toward the 14–61k-crown target this is O(n) per POST, O(n²) per session, degrading reviewer UI over time.
- Fix: keep an in-memory `{crown_id: last_row}` dict updated incrementally.

### M5 — phase1_preprocess.py:1465-1491 — `compute_building_distance` per-row Python loop over 222k crowns
- Severity: MED | Category: inefficiency | Confidence: high
- `for i in range(start,end): pt=centroids.iloc[i]; sindex.query(pt.buffer(200)); ...distance(pt)` —
  chunking is only for tqdm, not vectorization. Shapely 2.0 `sindex.nearest(centroids.geometry,
  return_distance=True)` does all 222k at once, likely ~10× faster.
- Fix: vectorized `sindex.nearest`.

### M6 — phase1b_sampling.py:224-229 — `assign_strata` runs `crowns.apply(rule, axis=1)` five times (row-wise)
- Severity: MED | Category: inefficiency | Confidence: high
- Each STRATUM_DEFS rule is `lambda r: r["col"] < x` applied via `apply(..., axis=1)` (pandas' slowest
  path), repeated per stratum, though every rule touches a single column → trivially vectorizable
  (`crowns["bldg_dist_m"] < 5.0`).
- Fix: replace with direct boolean masks.

### M7 — phase1_preprocess.py:1426-1434, 468-489, 2153-2154 — building-NDVI cache keyed by positional index
- Severity: MED | Category: bug (silent data-integrity risk) | Confidence: medium
- `sample_buildings_year()` returns a Series indexed 0..N-1 from that run's building load; persisted to
  `building_ndvi_cache.parquet` and reloaded, then reassigned positionally
  (`buildings_y["_bndvi"] = bldg_ndvi.values`). If the buildings source is ever
  regenerated/reordered/filtered between runs, cached NDVI silently attaches to wrong buildings → wrong
  `ndvi_vs_roof_{year}` features, no error.
- Fix: key the cache by a stable building_id (merge/reindex on ID, not positional `.values`).

### M8 — phase0_instance_seg.py:1644-1651 — dead "edge coverage" branch in run_inference (always False)
- Severity: MED | Category: bug (dead code) | Confidence: high
- `if tile_origins[-1][0] + stride < img_h:` — the last value `L` from `range(0,img_h,stride)` always
  satisfies `L+stride >= img_h`, so the condition is algebraically always False; same for width. Never
  executes. Harmless only because `flush()` clips write windows (1676-1677), but signals a
  misunderstanding that edge coverage is being explicitly handled.
- Fix: remove, or replace with assertion/comment noting flush()'s clip guarantees edge coverage.

### M9 — phase0_instance_seg.py:664-665 — non-overlapping training tile grid drops last <512px strip of each site
- Severity: MED | Category: bug | Confidence: medium
- `range(0, height-TILE_SIZE+1, TILE_STRIDE)` with stride==tile==512 and no remainder handling drops up
  to 511px along bottom/right of any site not an exact multiple of 512 → labeled crowns in that strip
  never seen at tile time. Small hand-labeled sites make this a non-trivial fraction.
- Fix: pad site raster to a 512 multiple, or add a final tile anchored at `height-TILE_SIZE`.

### M10 — phase2_data_prep.py:140-141 — `coverage_pct` uses bbox intersection, not the raster's valid-data footprint
- Severity: MED | Category: bug | Confidence: low
- `boundary_geom.intersection(box(*src.bounds))` overstates true coverage for non-rectangular valid-data
  footprints; catalog hardcodes real figures (e.g. 67% for 2016/2021s) a bbox check could contradict.
- Fix (if desired): rasterize/sample the nodata mask, or document as a rough upper bound.

---

## LOW

### L1 — phase1a_autolabel.py:464-467 & 544-549 — FP3 silently changes meaning when `ndvi_vs_roof_*` columns absent
- Severity: LOW-MED | Category: bug (fragility) | Confidence: medium
- `compute_veg_year_counts()` defaults `median_vs_roof` to all-zeros when no `vs_roof_cols` exist, and
  FP3 fires on `median_vs_roof <= ROOF_NDVI_MAX(0.02)` — with the zero-fallback every crown trivially
  satisfies that half, turning FP3 from "spectrally roof-like" into "roof_score alone" with no warning.
- Fix: hard-fail or warn when expected per-year columns are missing.

### L2 — phase1c_review.py:552-556, 683, 212-219 — concurrent /label POSTs append to CSV with no lock
- Severity: LOW-MED | Category: bug (concurrency race) | Confidence: low-medium
- `ThreadingTCPServer` (683) + documented multi-reviewer scenario; `_write_csv_row()` opens/writes/closes
  per call with no lock. Concurrent writes can interleave/corrupt CSV rows.
- Fix: `threading.Lock()` around the write path.

### L3 — phase1c_review.py:362-363 — crop center uses truncating int() instead of round()
- Severity: LOW | Category: bug (minor) | Confidence: low
- `col = int((cx - transform.c)/transform.a)` truncates → up to ~1px systematic offset between centroid
  and crop/outline center. Cosmetic at ~7.6cm. Fix: `round(...)`.

### L4 — phase3_semantic_dev.py:971-974 & phase0_instance_seg.py:969 — per-batch Python-loop L1 penalty
- Severity: LOW | Category: inefficiency | Confidence: medium
- `sum(p.abs().sum() for p in model.parameters() ...)` launches one small CUDA kernel per param tensor
  every training batch across folds×epochs×batches. L1_LAMBDA tiny so correctness fine; overhead avoidable.
- Fix: `torch._foreach_abs`/flattened param view.

### L5 — phase3_semantic_dev.py:898 + _train_one_fold — torch.compile recompiles from scratch every LOSO fold
- Severity: LOW | Category: bottleneck | Confidence: medium
- Fresh model + `torch.compile` per fold pays full graph-compile (1-2+ min) every fold + the ALL run, no
  cache reuse — real avoidable cost on the honest eval path meant to run repeatedly.

### L6 — phase3_make_segmentation_png.py:238 — reads all bands then uses only first 3
- Severity: LOW | Category: inefficiency | Confidence: high
- `src.read().transpose(1,2,0)` then `img[...,:3]`; for 4-band tiles reads an unused band.
  Fix: `src.read([1,2,3])`.

### L7 — phase3_make_segmentation_png.py:178-179 — `np.argwhere(mask)` computed twice in no-peaks fallback
- Severity: LOW | Category: inefficiency | Confidence: high
- Redundant; harmless at POC scale.

### L8 — phase3_semantic_dev.py:2728 — hardcoded random-split comparison numbers in LOSO summary print
- Severity: LOW | Category: bug (maintenance) | Confidence: low
- Literal `"IoU 0.772 / AUROC 0.961"` not read from EVAL_CSV; goes stale on retrain (violates
  "one fact, one home"). Not a runtime bug.

---

## Clean areas (verified, not padded)
- phase3_semantic_dev.py: unusually clean — no bare except, all rasterio via `with`, LOSO site sets
  disjoint (no leakage), BCEWithLogitsLoss on logits + sigmoid only at eval + scaler.unscale_ before
  clip_grad_norm_ (textbook), albumentations applies nearest to mask (float32 0/1) so no interpolation
  corruption, CRS fails loud on ≠3857.
- phase0: no bare except, all rasterio via `with`, CRS reproject→explode→fix→re-explode ordering correct,
  chunked-watershed centroid dedup boundary-ownership inequality verified correct, north-up georef math correct.
- phase1_preprocess: upsample/reproject windowing + worker-pool spectral sampling correct and already
  well-optimized (per-process raster handle reuse, tile-sorted tasks).
- phase1d: LightGBM scale_pos_weight direction correct.
- phase2/phase3_png: rasterio via `with`, Colab `-f`/`.json` filters present where needed.

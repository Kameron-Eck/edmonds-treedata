# Pipeline Audit — 2026-07-08

Full-codebase audit by 5 parallel non-Fable subagents (1 Opus on the live engine, 4 Sonnet
across the rest) + 1 classification pass. Per-file detail lives beside this file
(`audit_engine.md`, `audit_phases0_3.md`, `audit_qc.md`, `audit_infra.md`, `audit_viz.md`,
`dormant_classification.md`). Findings verified against source where marked ✓.

Severity: CRITICAL / HIGH / MED / LOW. Confidence: hi / med / lo.

---

## 0. Housekeeping done (committed)

- **53 dormant pre-Phase-0 scripts → `_archive/scripts/`** (imagery acquisition/discovery/
  registration era, complete). Verified by full import/`%run` grep that no active script
  references any moved file. Root scripts: 82 → 29. Commit `e7ee743`.

## 1. Fixes APPLIED this pass (verified, output-safe, committed)

| File:line | Fix | Why safe |
|---|---|---|
| ✓ phase0_instance_seg.py:1823 | `.union(*geom_list[1:])` → `unary_union(geom_list)` | Latent crash on 3+ shape crowns; anchor run never hit it → zero impact on existing outputs. Matches the already-correct sibling at :1546. |
| ✓ phase4_semantic_finetune.py:3415 | `np.where(data==1,1,0)` → `(data==1).astype(uint8)` | Killed a full-city **int64** temp (8 B/px) in postproc → the fine-year OOM. **Byte-identical output.** Unblocks `--force-citywide` on fine years. |

## 2. NEEDS YOUR DECISION — measurement / numerics / recipe (NOT auto-applied)

These change reported numbers, model weights, or in-flight-study behavior. Left untouched on purpose.

| Pri | File:line | Issue | Impact |
|---|---|---|---|
| ★1 | ✓ phase4_qc_ndvi.py:169,191 | CHM-nodata (`NaN`) forced to −1 via `nan_to_num` → every vegetated pixel in the ~40% of city w/o CHM is written **grass(1), never canopy(2)** in the honest reference | **Biases your headline honest recall/precision** (.60/.97). Sibling `build_corrected_labels.py` gates on CHM coverage correctly. Fix: set no-CHM veg → 255/IGNORE. |
| ★2 | phase4_semantic_finetune.py:3342 | `_operating_threshold` filters eval CSV by `(year,OVERALL)` only — ignores channels/run-tag; eval rows key `(year,channels)` | In multi-arm / `--run-tag` studies a **wrong arm's best-F1 threshold can be deployed** → silently corrupts a scientific output. Most dangerous non-crash item. |
| ★3 | phase4_semantic_finetune.py:3413 | polygonize does `src.read(1)` of the whole full-city uint8 mask (~31 GB @7.5 cm) into RAM | Fine-year OOM/bottleneck (undoes the chunked threshold pass just above). Needs chunked polygonize — a real refactor. |
| 4 | phase0_instance_seg.py:731 | Step-5 test split is random site-stratified (no spatial buffer/LOSO); Step-8 sweep tuned on it → baked into city default | Violates Rule #5 (honest eval). Optimistic params. Methodology, not a quick patch. |
| 5 | phase1a_autolabel.py:290 | impervious raster CRS fetched but never reprojected before rasterizing crowns | CRS mismatch silently corrupts `imp_frac` → FP2/TP1 autolabel rules (phase1 already run on this). |
| 6 | phase2_data_prep.py:254 | `step_overlay` builds crop window from 3857 site bounds without reprojecting into `src.crs` | Garbage window for non-3857 native sources when aligned file missing. |
| 7 | make_positive_site.py:146 | crown `area_m2` computed in EPSG:3857 (`CROWN_CRS`) → ~2.2× inflated at lat 47.8° | `--min-area-m2` filter looser than documented; printed hectares wrong. Affects the active positive-site staging. ✓ CROWN_CRS confirmed 3857. |
| 8 | phase3_make_segmentation_png.py:310 | `gt > 0.5` counts IGNORE(255) as GT canopy → inflated POC IoU (med-conf; verify `gt` domain) | Corrupts a reported POC metric only. |

## 3. Robustness / correctness — safe to fix, lower urgency (proposed)

- **pipeline_log.py** (shared infra; I did NOT touch mid-study): `:233` `write_step_log` calls
  `_write` bypassing `finish()`'s try/except (crashes caller — currently dead code); `:178`
  `{key:<11}` glues keys ≥11 chars to values (`manifest items14476` fires today); `:139` non-ASCII
  glyph in the error-fallback print can itself raise `UnicodeEncodeError` on non-UTF8 Windows stdout.
- **phase4_qa_overlay.py:156** — "same grid" check compares (w,h) only, never transform/CRS; silently
  drops overlay on mismatch (reads as "no canopy"). :223 resamples 255-sentinel prob with `average` not `nearest`.
- **phase4_sentinel_snap.py:219** — default `--thresh 0.4615` is a fixed cross-year comparison constant,
  not any year's deployed best-F1; never looks up the eval CSV → wrong operating threshold on unlabeled runs.
- **phase4_label_review.py:296 vs :603** — `compile` recomputes `crown_id` from raw gpkg row order, not
  the persisted manifest id → re-running prep between review and compile silently desyncs decisions.
  Also :151 unlocked CSV writes under ThreadingTCPServer.
- **phase4_qc_score.py:109** — grid guard checks w/h/crs, never the affine transform (offset rasters pass silently).
- **phase4_qc_site.py:109** — CHM force-fit via naive index resize instead of `WarpedVRT` → possible misregistration.
- **phase4_qc_indep.py:263** — nodata masking only fires for sentinel in [0,255]; out-of-range sentinel scored as real.
- **fetch_build_chm.py:143** — `--max-height` is a no-op above 50.6 m (U8 DN packing caps at 254). Low impact (p99=44.6 m).
- **phase1d_classifier.py:642** — Platt calibrator fit AND Brier-scored on same `y_val` (circular calibration metric).
- **phase3_semantic_dev.py:1545** — dead/miscomputed edge-tile block (uses TILE_SIZE not stride); overwrites correct preds.
- **phase1_preprocess.py:1426** — building-NDVI cache keyed by positional index (reorder → wrong building).
- **phase1c_review.py:229** — `_check_conflict` linear-scans full CSV per POST → O(n²) over a review session.

## 4. Inefficiencies / bottlenecks (perf only)

- engine: worker RNG duplicated under `fork` (no `worker_init_fn`, :2701) → correlated augs; eval-pool
  double-concat (:3056); tile-cache signature omits adaptive scan stride & `CITYWIDE_CANDIDATE_TARGET`
  (:1800) → stale-tile risk; per-strip morphology seams every 4096 rows (:3389); numpy sigmoid overflow
  (:3025, prefer `expit`).
- viz: `phase4_viz.py` runs inference twice per panel; `phase4_sentinel_snap.py` reopens big rasters per site.
- phases: per-row Python loops (phase1_preprocess building-distance, phase1b strata apply).

---

**Clean bill (checked specifically, no issue):** masked-loss IGNORE handling, the historic
`1/count[site]` sampler bug, the uint8/float augmentation-cast bug, AMP order, CRS/window math in the
engine, NDVI band order (R,G,B,NIR — no swap anywhere), CHM DN↔metres round-trip, categorical
`nearest` resampling in qc_indep/forest_misses, `phase3_semantic_dev.py` loss/sigmoid/AMP/LOSO folds.
No CRITICAL silent-corruption bug in the live engine — the two HIGH engine items are memory/OOM.

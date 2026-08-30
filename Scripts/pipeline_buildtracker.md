# Edmonds Pipeline — Build Tracker

*Created: 2026-05-23 · Last updated: **2026-08-30**.*
*References: `Method_Pipeline.md`. **Live state lives in [`WORKPLAN.md`](WORKPLAN.md)**
(intent) and [`STATUS.md`](STATUS.md) (facts, generated) — not in `CHATLOG.md` STATE,
which is now append-only history. This file tracks structural build status only.
(Doc map: `../README.md`.)*

> This file went eleven days without an update while being the designated home for
> "what's built vs pending", and in that time it acquired no row for the sector
> campaign, the damage curve, the harness rebuild or the boundary loss — the four
> things the project was actually doing. Counts below are **not** restated from the
> catalog; read `STATUS.md` for those.

---

## Phase scheme (current)

**Phase 4 = SEMANTIC per-year fine-tune, every acquisition. This is the whole current
pipeline.** Phases 0/1/1A–1D/2/3 are complete; 5–8 are not built.

**Phase 5 was scoped as per-year INSTANCE fine-tune. Instance is DEFERRED, not
cancelled** (Kam, 2026-08-29) — the scope summary below is kept for when it is picked
up. Phase 0 produced the 222,435-crown layer once, from 2020, and it is used as a fixed
lookup geometry, not regenerated per year.

(This numbering is swapped from the original scheme — the old
`Scripts/_archive/Tree Project Work Plan.xlsx` shows Phase 4 = instance and is
**superseded**.)

| Phase | Script | Status |
|-------|--------|--------|
| 0 | `phase0_instance_seg.py` | ✅ Complete — 222,435 crowns, `edmonds_crowns_2020.gpkg` |
| 1 | `phase1_preprocess.py` | ✅ Complete — spectral features over the acquisitions catalogued at the time (18); the catalog has since grown, see `STATUS.md`. `edmonds_crowns_phase1.parquet` (568 MB) |
| 1A–1D | `phase1a…1d_*.py` | ✅ Complete — active-learning QA loop (auto-label → sample → review → classifier) |
| 2 | `phase2_data_prep.py` | ✅ Complete — imagery validation, coverage matrix, overlay QA |
| 3 | `phase3_semantic_dev.py` | ✅ Complete — 2020 base semantic model; LOSO IoU 0.7299 / AUROC 0.9396; **passed DG1** |
| **4** | `phase4_semantic_finetune.py` (shim) → `phase4seg/` | 🔄 **Active** — live version + state in `CHATLOG.md` STATE (see below) |
| 5 | `phase5_instance_finetune.py` | 🔲 Not built — deferred until Phase 4 masks validated |
| 6 | `phase6_temporal_linking.py` | 🔲 Not built |
| 7 | `phase7_feature_extraction.py` | 🔲 Not built |
| 8 | `phase8_temporal_analysis.py` | 🔲 Not built |

---

## Phase 4 — per-year semantic fine-tune (ACTIVE)

The engine fine-tunes the Phase-3 2020 checkpoint independently onto
each of the 17 other years. **What's built diverged from the original workplan** (which
described a single scale-robust model + i-Tree validation) — record the reality here.

### Built
- **Per-tier handling retained** (not a single scale-robust model): fine ≤15 cm / medium
  29.9 cm / coarse 50–60 cm, with tier-specific tiling stride, early-stop metric, and
  label source. Coarse years train on the citywide 2020 mask; fine/medium on per-site
  crown polygons.
- **Two-phase fine-tune** (A: decoder-only frozen encoder → B: full model), from
  `phase3/sem_best_2020.pt`.
- **LiDAR canopy-height 4th channel** (`lidar_snoh_chm.tif`, USGS 3DEP HAG, ~2016) —
  added to kill grass false-positives (grass was ~64% of FPs). `fetch_build_chm.py`
  builds it; `--hs-source chm`, `HS_DROPOUT` keeps an RGB-only pathway. **This is a
  scope addition** beyond the original "RGB-only, not LiDAR" boundary.
- **Sampler/metric fixes (v039)** — resolved the 2016 "collapse" (a `1/count[site]`
  sampler bug + a `val_iou@0.5` metric artifact, not a training failure). 2016 RGB+CHM
  now beats the RGB baseline on held-out test (IoU 0.7725 vs 0.7245).
- **Independent QC instrument** — `phase4_qc_ndvi.py` / `_score.py` / `_site.py`: builds
  an NDVI+CHM canopy reference for the NIR-bearing years (4 when this was written; see
  `STATUS.md` for the current list) and scores the model against it. The
  standing read: precise but **under-predicting** — live numbers in the active plan's
  baseline table, not here.
- **Corrected-label workstream (v042)** — `phase4_build_corrected_labels.py` inverts the
  QC instrument to *label* the misses: `canopy_additions_2016.tif` (ADD-ONLY: NDVI≥0.3 &
  CHM≥3 m → canopy). `--add-canopy-mask` layers it on the coarse 2020-mask path; one file
  serves 2016 and 2000.
- **Curated negative/positive sites** — `make_grass_negatives.py` (turf hard-negatives),
  `make_positive_site.py` (positive sites with crowns derived from the 2020 mask).
- **Engine modularized 2026-07-08** — the monolith split into the `phase4seg/` package
  (`config` / `common` / `labels` / `tiling` / `core` [all torch] / `postproc` / `cli`);
  `phase4_semantic_finetune.py` is now a ~97-line shim that preserves the existing
  `%run ... --args` call. Behavior-preserving (AST-verified). Local validation gained
  `phase4seg_preflight.py` (static) and `phase4seg_smoke.py` (CPU runtime).
- **Second independent reference (C-CAP)** — `phase4_qc_indep.py` scores against NOAA
  C-CAP hi-res 1 m land cover (EVAL-ONLY, never trained on), so no-NIR years get an
  honest number too. `phase4_qc_forest_misses.py` / `phase4_miss_examples.py` /
  `phase4_qc_flicker.py` are the autopsy tools. Current honest numbers live in the
  active plan's baseline table — not restated here.

### Measurement & honest-evaluation stack (built 2026-08-17→18)
A separate **measurement workstream** (plan: `honest-measurement-overhaul.md`; assessment:
`Reports/Measurement_Validity_Assessment_2026-08-18.md`) was run because the model's
accuracy claims rested on references that disagree. Its phases **P1, P2 and P4 are
COMPLETE**; **P3 (human photo-interpretation) is TOOLED BUT NOT RUN**. Structural status
only here — every number lives in `CHATLOG.md` STATE, which now carries eleven numbered
results. What matters structurally:

- **The instruments exist and are validated**, so honest evaluation is no longer
  ad-hoc: reference-agreement partitioning, recall-by-height, latent-class accuracy with
  no gold standard, design power simulation, crown edge-vs-interior decomposition, and
  two CHM-validity checks.
- **The blocker moved.** It is no longer "we cannot measure" — it is **U1, the written
  canopy definition**, which is a human judgment call. `canopy_definition_PROPOSAL.md`
  puts six decisions up for sign-off; nothing in it is adopted. P3 cannot start without it,
  because a sample can only reproduce a definition it has been given.
- **Sample size is NOT the constraint** (it was believed to be): the real stratified design
  separates the candidate definitions at n=250. Interpreter fidelity is what binds.

### Pending / open
- **Honest validation not finished.** The 14,476-crown human review was **never
  completed** (labels are accept-all test data). The independent recall number for
  no-NIR years (2000) still needs Olofsson stratified photo-interpretation — **this is
  the DG2 gate** and the real credibility bottleneck. The harness for it is now BUILT
  (`phase4_accuracy_sample.py`, samples drawn for 2016 / 2000 and for the acquisition
then labelled 2022n, since renamed 2023n) and gated on U1.
- **2016 corrected-label model: EVALUATED, NOT DEPLOYED.** The retrain ran; it trades
  recall up for precision down, and the entire question lives in the contested zone where
  the two references disagree. Latent-class analysis was shown to be **inadmissible** for
  this decision (the corrected model descends from the NDVI reference, so it is not an
  independent third test). P3 under a written definition decides it. Do not deploy on the
  strength of either reference alone.
- **Three levers on under-prediction, each now evidenced** (structural note; numbers in
  STATE): height-conditioned training, crown-boundary handling, and the operating point.
  A fourth — radiometric normalization — now has a *specification* (per-image saturation
  and channel balance, not brightness matching) where it previously had none.
- **Deferred option:** NIR+height as auxiliary supervision *targets* (RGB-only inference)
  if label-augmentation doesn't close the recall gap.
- **The remaining years** after 2016/2000 are validated (15 when this was written).

### Key outputs
`phase4/models/sem_best_{year}.pt` · `phase4/masks/edmonds_canopy_{prob,mask}_{year}.tif`
· `phase4/eval/semantic_eval_report.csv` (circular metrics) · `phase4/qc/qc_report.csv`
(honest metrics) · `phase4/labels_corrected/canopy_additions_{year}.tif`

---

## Supporting tooling

| Script | Role |
|--------|------|
| `fetch_build_chm.py` | Build `lidar_snoh_chm.tif` (3DEP HAG height) |
| `phase4_qc_ndvi.py` / `_score.py` / `_site.py` | Independent NDVI+CHM reference, scoring, FN attribution |
| `phase4_build_corrected_labels.py` | ADD-ONLY corrected-label overlay from NIR+CHM |
| `make_grass_negatives.py` / `make_positive_site.py` | Stage curated negative / positive training sites |
| `phase4_qc_indep.py` | Score vs an INDEPENDENT reference (C-CAP), reference-agnostic |
| `phase4_qc_forest_misses.py` / `phase4_miss_examples.py` | Under-prediction autopsy + visual miss chips |
| `phase4_qc_flicker.py` | Temporal-stability (flicker) test on stable parcels |
| `phase4_ref_agreement.py` | P2: partition pixels by whether the two references AGREE — the basis for never scoring contested ground |
| `phase4_qc_height_by_agreement.py` | Recall by CHM band *within* each agreement partition (the U3 confound test) |
| `phase4_qc_latent_class.py` (+`_test`, `_adversarial`) | Latent-class sens/spec for C-CAP × NDVI-ref × model with NO gold standard (Foody 2022). The two companions are a synthetic-recovery test and an adversarial-dependence test — **run them before trusting a change to the estimator** |
| `phase4_qc_edge_vs_interior.py` | Splits misses into crown INTERIOR vs EDGE by erosion; also reports miss depth + CHM per part |
| `phase4_qc_chm_gap.py` | Bounds how much canopy the no-lidar zone could hide (answer: it is water) |
| `phase4_qc_chm_noise.py` | U6: null test that height-binning cannot manufacture a curve, + attenuation under simulated CHM error |
| `phase4_accuracy_sample.py` | P3 harness: stratified sample design → browser photo-interpreter (`--step serve`) → Olofsson area-adjusted estimate. **Not yet run by a human** |
| `phase4_qc_design_power.py` | Simulates the ACTUAL stratified design's CI and its power to separate two candidate canopy definitions |
| `phase4_sentinel_qc_overlay.py` | Sentinel windows as RGB \| agreement partition \| TP/FN/FP, scored only where the references agree |
| `phase4_ccap_sample.py` | C-CAP-stratified FIXED tile locations for cross-sensor runs (locate-only) |
| `phase4_sentinel_snap.py` / `sentinel_sites.json` | Fixed-site visual progress snapshots |
| `phase4seg_preflight.py` / `phase4seg_smoke.py` | Local static + CPU-runtime validation before a Colab round-trip |
| `phase4_viz.py` / `phase4_qa_overlay.py` / `phase4_threshold_diagnostic.py` | Diagnostics / QA overlays |
| `phase4_label_review.py` / `_prep.py` | Crown-review web tool (review never completed) |
| `pipeline_config.py` / `pipeline_log.py` | Shared paths (catalog FROZEN legacy — see `phase4seg/config.py:YEAR_CATALOG`) / step logging |
| `version_script.py` | RETIRED — git replaced it (kept as a frozen pre-git archive) |

---

## Known gaps & risks (durable)

- **Ground truth is the bottleneck**, not the model. The 2020 citywide mask is a *model
  prediction*, not hand truth (hand labels = 5 conifer sites); the crown review was never
  finished. An honest, independent validation set (photo-interp) unblocks DG2.
- **Sources of truth were centralized 2026-07-06** — handoffs retired, the duplicate
  Admin workplan archived, and one home per kind of info (map in `../README.md`; live
  state in `CHATLOG.md` STATE). Keep it that way: one fact, one home.
- **Versioning is git** since 2026-07-06. **The working tree is `D:\edmonds-pipeline	reedata`
  and GitHub is the live mirror** — the old arrangement described here (working tree = the
  Drive folder, DB at `treedata.git`) ended with the 2026-08-20 re-plumb and was the last
  surviving description of it in a live doc. `version_script.py` / `.versions/` are a frozen
  pre-git archive — full history was imported as backdated commits v001–v044.
- **Run records lag the runs.** `run_registry.csv` was 7 Colab runs behind until the
  2026-08-17 backfill; logs are the only durable record and they do NOT stamp the engine
  version, so a backfilled row cannot state one. Write the row when the run lands.

---

## Phases 5–8 (not built — scope summary)

- **5 · Instance fine-tune** — **DEFERRED, not cancelled.** Label projection → per-year
  DTM → fine-tune from Phase 0 → watershed → `phase5/crowns/edmonds_crowns_{year}.gpkg`.
  DG3/DG4. Note: three QC scripts still read a `phase5/` path, but those are fallbacks
  across the phase5→phase4 *rename* and are unrelated to this scope.
- **6 · Temporal linking**: anchor-match instance years to 2020, discover removals/
  plantings, build canonical crown layer + canopy-fraction matrix.
- **7 · Feature extraction**: spectral stats + VIs (GCC/GRVI all years, true NDVI for NIR
  years) under the canonical crown set.
- **8 · Temporal analysis & deliverables**: change classification, per-year canopy
  statistics, lifecycle analysis, maps, city handoff package.

---

*Structural tracker. Live state → `CHATLOG.md` STATE. Active plan → whichever file
CHATLOG STATE names (do not restate the name here — it rots).*

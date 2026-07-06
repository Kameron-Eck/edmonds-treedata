# Edmonds Pipeline — Build Tracker

*Created: 2026-05-23 · Last updated: 2026-07-06*
*References: `Method_Pipeline.md`, `edmonds_combined_workplan.xlsx`. **Live day-to-day
state (current model version, active workstream, next Colab step) lives in the
`CHATLOG.md` STATE block** — this file tracks structural build status, not the daily
state. (Doc map: `../README.md`.)*

---

## Phase scheme (current)

Phase 4 = **semantic** per-year fine-tune (17 years); Phase 5 = **instance** per-year
fine-tune (9 high-res years). (This is swapped from the original scheme — the old
`Admin/Tree Project Work Plan.xlsx` still shows Phase 4 = instance and is
**superseded**; `edmonds_combined_workplan.xlsx` is canonical.) Phases 0/1/1A–1D/2/3
are complete; 6–8 not yet built.

| Phase | Script | Status |
|-------|--------|--------|
| 0 | `phase0_instance_seg.py` | ✅ Complete — 222,435 crowns, `edmonds_crowns_2020.gpkg` |
| 1 | `phase1_preprocess.py` | ✅ Complete — 18-year spectral features, `edmonds_crowns_phase1.parquet` (568 MB) |
| 1A–1D | `phase1a…1d_*.py` | ✅ Complete — active-learning QA loop (auto-label → sample → review → classifier) |
| 2 | `phase2_data_prep.py` | ✅ Complete — imagery validation, coverage matrix, overlay QA |
| 3 | `phase3_semantic_dev.py` | ✅ Complete — 2020 base semantic model; LOSO IoU 0.7299 / AUROC 0.9396; **passed DG1** |
| **4** | `phase4_semantic_finetune.py` | 🔄 **Active — live v042** (see below) |
| 5 | `phase5_instance_finetune.py` | 🔲 Not built — deferred until Phase 4 masks validated |
| 6 | `phase6_temporal_linking.py` | 🔲 Not built |
| 7 | `phase7_feature_extraction.py` | 🔲 Not built |
| 8 | `phase8_temporal_analysis.py` | 🔲 Not built |

---

## Phase 4 — per-year semantic fine-tune (ACTIVE)

`phase4_semantic_finetune.py` fine-tunes the Phase-3 2020 checkpoint independently onto
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
  an NDVI+CHM canopy reference for the 4 NIR years and scores the model against it.
  Honest 2016 recall = **0.60** at precision **0.97** (vs the circular 0.94) → the model
  is precise but **under-predicts** ~40% of real canopy (tall green deciduous stands).
- **Corrected-label workstream (v042)** — `phase4_build_corrected_labels.py` inverts the
  QC instrument to *label* the misses: `canopy_additions_2016.tif` (ADD-ONLY: NDVI≥0.3 &
  CHM≥3 m → canopy). `--add-canopy-mask` layers it on the coarse 2020-mask path; one file
  serves 2016 and 2000.
- **Curated negative/positive sites** — `make_grass_negatives.py` (turf hard-negatives),
  `make_positive_site.py` (positive sites with crowns derived from the 2020 mask).

### Pending / open
- **Honest validation not finished.** The 14,476-crown human review was **never
  completed** (labels are accept-all test data). The independent recall number for
  no-NIR years (2000) still needs Olofsson stratified photo-interpretation — **this is
  the DG2 gate** and the real credibility bottleneck.
- **Corrected-label retrain** (Colab): retile+retrain 2016 & 2000 with `--add-canopy-mask`,
  score vs the NDVI reference, **precision guard** (grass-rejection ~0.98, precision not
  down) — see the active plan `drifting-swinging-dolphin.md`.
- **Deferred option:** NIR+height as auxiliary supervision *targets* (RGB-only inference)
  if label-augmentation doesn't close the recall gap.
- **Remaining 15 years** after 2016/2000 are validated.

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
| `phase4_viz.py` / `phase4_qa_overlay.py` / `phase4_threshold_diagnostic.py` | Diagnostics / QA overlays |
| `phase4_label_review.py` / `_prep.py` | Crown-review web tool (review never completed) |
| `version_script.py` / `pipeline_log.py` | Script versioning / step logging |

---

## Known gaps & risks (durable)

- **Ground truth is the bottleneck**, not the model. The 2020 citywide mask is a *model
  prediction*, not hand truth (hand labels = 5 conifer sites); the crown review was never
  finished. An honest, independent validation set (photo-interp) unblocks DG2.
- **Sources of truth were centralized 2026-07-06** — handoffs retired, the duplicate
  Admin workplan archived, and one home per kind of info (map in `../README.md`; live
  state in `CHATLOG.md` STATE). Keep it that way: one fact, one home.
- **No git** — history/rollback rely on `.versions/` snapshots only.

---

## Phases 5–8 (not built — scope summary)

- **5 · Instance fine-tune** (9 high-res years): label projection → per-year DTM →
  fine-tune from Phase 0 → watershed → `phase5/crowns/edmonds_crowns_{year}.gpkg`. DG3/DG4.
- **6 · Temporal linking**: anchor-match instance years to 2020, discover removals/
  plantings, build canonical crown layer + canopy-fraction matrix.
- **7 · Feature extraction**: spectral stats + VIs (GCC/GRVI all years, true NDVI for NIR
  years) under the canonical crown set.
- **8 · Temporal analysis & deliverables**: change classification, per-year canopy
  statistics, lifecycle analysis, maps, city handoff package.

---

*Structural tracker. Live state → `CHATLOG.md` STATE. Active plan
→ named in CHATLOG STATE (currently `drifting-swinging-dolphin.md`).*

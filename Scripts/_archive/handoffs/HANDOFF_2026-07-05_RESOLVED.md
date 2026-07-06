# HANDOFF 2026-07-05 (v2) — CHM "collapse" RESOLVED; 2016 validated; pivot to Phase 4

**Supersedes `HANDOFF_2026-07-05.md`** (that one described the collapse as an open
problem — it's now solved). Read this, then `CHATLOG.md` (STATE + top 2 entries).
Plan file: `D:\tools\claude-config\plans\synchronous-hatching-kahan.md`.

Scripts live on the mounted Drive `G:\My Drive\treedata\Scripts\` — edit in place
(syncs to Colab). Run on Colab via `%run /content/drive/MyDrive/treedata/Scripts/
{script}.py --args`. Local has NO torch/rasterio (rasterio/geopandas/sklearn DO
pip-install locally on import; torch does NOT) → training/inference is Colab-only.
`py -3.12 -m py_compile` (PYTHONUTF8=1) BEFORE writing any edit. Version every change
to `.versions/phase4_semantic_finetune/vNNN_DATE_desc.py`. Log milestones to
`CHATLOG.md` (caveman style, STATE edited in place).

---

## TL;DR — what happened

The 2016 CHM "training collapse" that this project chased for ~6 runs was **two
stacked bugs, neither of them the CHM channel, class balance, Dice, or BatchNorm**
(all empirically eliminated). Root cause found via a fresh code audit:

1. **THE BUG — the training sampler.** `step_train` built a `WeightedRandomSampler`
   weighting each tile by `1/count[SITE]`. In citywide-coarse there is ONE `city`
   site (holds ALL canopy tiles) + several tiny curated pure-negative sites
   (grass/water/fields). Inverse-site weighting gives every site EQUAL total mass, so
   batches ran **~83% pure background** → recall crash + train/test prior shift +
   probability scale dragged far below 0.5. Silently introduced in v030 when the
   negative sites were added (before that `city` was the only site → sampler was a
   no-op; this is exactly why v029/struct was stable and v030+ "collapsed").
2. **The metric artifact.** The coarse tier early-stopped / selected checkpoints on
   `val_iou@0.5`, which misread the below-0.5 probability drift as a collapse and
   froze the checkpoint at an undertrained epoch.

**Result after the fix: 2016 CHM now BEATS the RGB baseline on the held-out test.**

| Metric | RGB baseline | Broken CHM (v030) | **Fixed CHM (v039/40)** |
|---|---|---|---|
| IoU | 0.7245 | 0.49 | **0.7725** |
| AUROC | 0.9293 | 0.784 | **0.9380** |
| AP | 0.856 | 0.602 | **0.8834** |
| Precision | 0.773 | — | **0.8226** |
| Recall | 0.921 | 0.581 | **0.9270** |

Operating threshold back to a healthy 0.377 (was drifting to ~0.2). Recall fully
recovered. Precision UP (0.773→0.823) = the grass-FP-reduction signal the CHM height
channel was added for. **The CHM channel HELPS once the sampler is honest** — the
earlier "CHM makes it worse" conclusion was entirely an artifact of the sampler bug.

---

## Live version: `phase4_semantic_finetune.py` = v040

**v039 (research-backed Round 1 = plan Phases 1+2), 8 fixes:**
- (1) Sampler: citywide-coarse → natural/shuffle (preserves true ~40% canopy prior);
  6-site path keeps per-site weighting. `:~2417`.
- (2) `FREEZE_ENCODER_BN` default **True** (`--no-freeze-encoder-bn` to disable). `:~340`.
- (3) Phase B resumes from the BEST Phase-A ckpt, not last-epoch weights (`_run_phase_b`,
  reloads via `load_state_into`). Phase B now actually improves (was a no-op).
- (4) `COARSE_USE_POS_WEIGHT=False` → the frequency-invariant Dice term owns balance
  (single rebalancing channel, now that the sampler is natural). `:~392`.
- (5) `_validate` pools inter/union GLOBALLY across the val set (was per-batch mean
  that scored empty batches 0 and biased selection).
- (6) Eval reports confusion metrics at the DEPLOYED operating threshold (`*_op`
  columns + `op_thresh` in `semantic_eval_report.csv`) with AP as the headline —
  read these, NOT IoU@0.5.
- (7) Augmentation borders fill the MASK with IGNORE (255), not background (0)
  (`_make_spatial_transform`, albumentations 2.x `fill_mask`).
- (8) Medium/fine random-split leakage now flagged in `eval_scope` (those tiers use a
  random tile-level split on overlapping tiles → leaky; coarse-citywide is properly
  spatially blocked, clean).

**v040:** postproc polygonize VECTORIZED — shapely 2.x `simplify`/`make_valid`/`area`
as C ufuncs over the whole array + `fiona.writerecords` batch write (was a per-polygon
Python loop with `simplify(preserve_topology=True)`, slow on 100k+ city crowns).
Fallback to the old loop if shapely < 2. `preserve_topology=False` now (make_valid
repairs). Prints `(vectorized shapely 2.x polygonize)` when active.

Also live from earlier this session: v038 (coarse selects on `val_iou_bt` =
best-threshold IoU), v037 (per-epoch `iou_bt@thr` diagnostic in the loss history),
v036 (`--freeze-encoder-bn` flag + `_set_encoder_bn_eval`), v035 (IDEMPOTENT TILING —
citywide `step_tile` skips the ~20-min scan when a complete tile set for the current
sampling constants already exists; `--force-retile` to rebuild; sidecar
`tile_index_*.meta.json`), v034 (`--epochs-phase-a/-b` flags; `=0` skips Phase B →
fast ~4-min diagnostic runs), v033 (`--bce-weight/--dice-weight`), v031
(`--coarse-pos-weight-max/--lr-phase-a`).

**Run conventions now:** `--freeze-encoder-bn` is DEFAULT (don't pass it). Tiles are
cached — re-tile only when SAMPLING constants change (`HARD_NEG_FRACTION`,
`BACKGROUND_BUDGET_FRACTION`, etc.); everything else is train-only. Fast diagnostic =
`--step train --epochs-phase-a 8 --epochs-phase-b 0`.

---

## Immediate next steps (in order)

1. **Confirm grass-FP reduction on 2016.** Need the inference mask first (also
   exercises the v040 polygonize speedup):
   ```
   %run .../phase4_semantic_finetune.py --year 2016 --step inference
   %run .../phase4_semantic_finetune.py --year 2016 --step postproc
   %run .../phase4_viz.py --year 2016
   ```
   Read `phase4/eval/viz_2016/grass_metrics.txt`. Want grass-FP rate well below the
   old 27–29.5% with recall held. WEIGHT the committed negative sites + lawn/field
   tiles over forest tiles (forest "grass-FP" partly counts 2020-label disagreement).
2. **Carry the EXACT v040 config to 2000** (temporal-drift stress test — a ~2016
   height prior on 2000 imagery). Full per-year chain; tile step needed (2000 tiles
   predate the current sampling? — verify: if the sidecar signature matches it will
   REUSE; else it re-tiles once). Confirm band-4 log reads `source=chm`. Compare test
   AUROC/AP to 2016 and to the rgb-2000 anchor. Expect some drift; `HS_DROPOUT 0.25` +
   the RGB pathway are the mitigations.
3. **THEN pivot to Phase 4 — the REAL deliverable (user-confirmed priority).**

## Phase 4 — the real deliverable (NOT YET STARTED)

User goal = a **defensible multi-decade canopy-CHANGE series**, so honest validation
outranks squeezing model accuracy. Every metric to date is measured against the 2020
canopy mask reprojected onto other years → partly CIRCULAR (real pre-2020 change
counts as "error"; grass-FP on forest tiles partly counts label disagreement). Build,
per plan Phase 4 (all backed by a 4-agent literature review this session):
- **Honest validation set** — stratified random photo-interpretation per **Olofsson et
  al. 2014** ("Good practices for estimating area and assessing accuracy of land
  change", RSE): strata {stable-canopy, stable-non-canopy, gain, loss}, ~500–1000
  points, OVERSAMPLE the rare change classes, interpret each point INDEPENDENTLY of the
  model/2020 mask, report **area-adjusted canopy with 95% CIs** (never raw pixel
  counts, never map-minus-map). This is the DG2 gate.
- **Radiometric normalization across years** (pseudo-invariant-feature relative
  normalization) before inference + **test-time BatchNorm adaptation** per year (cheap
  first-line domain adaptation for the GSD/sensor/color drift across 2000–2018).
- **Stop training/validating on circular labels** — mask 2020-vs-year disagreement
  zones out of the loss; seed per-year training from temporally stable pixels only.

## Phase 3 — DEFERRED (only if grass-FP/accuracy still needs it)

Literature strongly favors height as a **supervision target**, not an input: Meta/WRI
(Tolan et al. 2024), California/Amazon sub-meter U-Nets, DeepForest all regress height
from RGB and infer RGB-only. Recommended if pursued: an **auxiliary CHM-regression
head** trained only on 2016 tiles (encoder learns height-aware features; inference
stays RGB-only across all 18 years → dissolves the 2016-only temporal mismatch). BUT
CHM-as-input now already beats baseline, so this is optional, not urgent.

---

## Key research findings (4-agent lit review this session — preserve these)

- **Prior shift is textbook.** Undertrained-beats-trained (AUROC 0.89 > 0.78) was the
  fingerprint of train/test class-prior mismatch (Kang et al., *Decoupling
  Representation and Classifier*, ICLR 2020): fix imbalance in the LOSS, keep the
  sampler at the true prior. (This is exactly what the sampler fix did.)
- **Select on threshold-free metrics** (AP/PR-AUC), never IoU@0.5, for imbalanced
  segmentation (*Metrics Reloaded*, Nature Methods 2024). AUROC is optimistic under
  heavy negative dominance → prefer AP.
- **Frozen-encoder BN** must be in `.eval()` (done).
- **Circular labels** are the #1 credibility killer for a change series (Olofsson
  2014; USFS/i-Tree cautions against differencing maps built with different methods).
- Height-as-target > height-as-input (see Phase 3).

## Don't redo / already correct

- `lidar_snoh_chm.tif` (3DEP HAG, U8, `HS_STATS['chm']=([.2306],[.2305])`) — correct,
  normalized. The "raw metres" concern does NOT apply (it's U8-scaled + z-scored).
- The 3 grass negative sites, the nodata neutral-fill, idempotent tiling — all correct.
- The sampler / metric / BN / Phase-B / loss fixes are validated — don't revert.
- Don't re-run the collapse hypotheses (class balance / pos_weight / Dice / channel /
  BN) — all empirically eliminated; the bug was the sampler.

## Files touched this session
`phase4_semantic_finetune.py` v030→v040 (all .versions-snapshotted). Backups:
`sem_loss_history_2016_v030chm_COLLAPSED.csv`, `..._runB_pw28.csv`, etc.;
`semantic_eval_report_pre-v031-retrain_2026-07-04.csv`. Current `sem_best_2016.pt` =
the validated v039 model (val_iou_bt 0.7385, test AUROC 0.938).

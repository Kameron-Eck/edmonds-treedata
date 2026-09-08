# WORKPLAN — the one living document

**This file holds INTENT: what we are doing, what is done, what is next, and what is
waiting on Kam. It does not hold facts about the archive or the results — those are
generated into [`STATUS.md`](STATUS.md) from the code and the data lake, because facts
restated by hand drift and these ones did.**

Read order for a new session: `CLAUDE.md` (rules + roadmap) → this file (state) →
`STATUS.md` (numbers). `CHATLOG.md` is append-only history and is **no longer read for
state**; its STATE block is superseded by this file.

*Updated by hand at each landed milestone. If it disagrees with `STATUS.md`, `STATUS.md`
is right about numbers and this file is right about intent.*

---

## The goal

**A tree canopy assessment for Edmonds, WA: a binary canopy mask per aerial acquisition,
across the whole archive. Semantic segmentation only.**

Instance segmentation is **deferred, not cancelled**. Phase 0's 222,435 crown polygons
are a fixed lookup geometry for `pipeline/builders/build_validity_intervals.py`, not a per-year target.

**The one constraint behind every difficulty:** only 2020 has hand labels. Every other
year is supervised by projecting the 2020 mask onto it, so growth, removal and — measured
2026-08-29 — **seasonal difference** all enter as label error.

---

## Where we are

Active plan: **the ACCURACY CAMPAIGN board below** (Tier 1 complete 2026-09-03;
its plan doc `TIER1_SCIENCE_SAMPLE_PLAN_2026-09-02.md` is now historical reference;
verdicts + data live in `experiments/tier1_science_sample.yaml` and
`phase4/qc/tier1_results.csv`). Prior: `SEMANTIC_OVERHAUL_PLAN_2026-08-29.md`
(architecture direction), executed through the repo overhaul agreed 2026-08-30.
Branch `work/20260906-healing-tool` (since 2026-09-06; prior `work/20260824-sectors`).

**EPOCH 3 (2026-09-01): every deliverable mask is cut at 3.0 m² TRUE** — the sieve
re-baselined (`postproc.sieve_min_px`), all 20 champion+pilot arms regenerated on
parallel zero-cost CPU runtimes, UTM years reproducing their EPOCH 2 polygon counts
exactly. The statistics floor is `docs/STATS_CHECKLIST.md` (6 of 10 hardened/measured;
open: co-registration table, Olofsson area estimation). The imagery's measured truth:
`phase4/qc/imagery_geometry.csv` + `acquisition_passport.csv` (one row per
acquisition, five homes joined, gated) — rendered on the Pipeline Atlas artifact.
The agentic loop: `experiments/*.yaml` → `qc/experiment_queue.py` → `vm_ops launch`
→ `pilot_gate --experiment` → `qc/landed.py`; `qc/check.py` is the definition of done.

**The full-repo refactor is COMPLETE (2026-09-01).** Tracked files 883 -> 477; one
editable install (`pip install -e .`) replaces the path-hack era; layout is
`pipeline/` (+`builders/`, `frozen/`) and `qc/` (+`instruments/`); everything removed
lives on branch `archive/2026-08-pre-refactor` (map: `docs/ARCHIVE_INDEX.md`).
Canary 1 proved the layout on a real VM — inference+postproc reproduced the pilot
raster stat-identically — and `pilot_gate.py` still reads 3/3 PASS from the lake.

**The drift gate covers nine documents** and grows as each is brought in line:
`CLAUDE.md`, `WORKPLAN.md`, `STATUS.md`, the active plan, `Method_Pipeline.md`,
`README.md`, `IMAGERY_FACTS.md`, `pipeline_buildtracker.md`,
`litreview_phase4_prompt.md`. Adding a doc to `GATED_DOCS` is how the cleanup is
made permanent — an ungated doc can drift again.

**SPEEDUP + RECORDING + LEDGER RECOVERY (2026-09-07/08).** The A100 was measured idle
82% of paid time; attributing it per step (`Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md`
§7) found tile and postproc blocked on Drive per-file latency with every counter at zero.
Four changes landed, refereed and gated (checkpoint diet, postproc stage-then-read, step
markers + iowait in `hw_*.csv` v2, the attribution/timing/session harvests), then ONE
already-run acquisition was re-run under the same recipe split across free CPU runtimes
and an A100: verdict in `experiments/offload_pilot_2017k.yaml`, table
`phase4/qc/offload_pilot_2017k.csv` (§9 of the report is the one-line summary). Standing
result: **labels+tile run on free CPU runtimes by default**; postproc stays on the GPU box.
The same day's forensics found the queue ledger had been erasing itself since 08-31
(`e499355`; snapshots and the rebuilt candidate in `phase4/qc/ledger_recovery/`, restored to
the lake as an additive merge file) and that the VM bootstrap had never installed the
requirements file (`3f60b0f`). Every launch now prints its start-up scan cost (`94cb8df`,
unvalidated until the next launch). Runtime facts, phases and throughput are harvested by
`qc/landed.py`; contracts in `docs/SCHEMAS.md`.

### The board

| stage | what | state |
|---|---|---|
| **U1** | `_pid_alive` could TerminateProcess on Windows | **done** `b939b34` |
| **U2** | one discovery rule for the status ledger | **done** `dcdb4b9` |
| **U3** | `postproc` — the deliverable step — was not in the queue | **done** `b939b34` |
| **0.1** | `WORKPLAN.md` — this file | **done** |
| **0.2** | `STATUS.md` generated from code + lake | **done** `37be4ab` |
| **0.3** | drift gate wired into `ci.yml` | **done** `37be4ab` |
| **0.4** | `EPOCH` re-baseline marker | **done** |
| **1** | documentation — 5 class-A docs rewritten, 4 banners applied | **done** `e232be5` `46812d8` `5d91657` `9fe99f7` |
| **2** | code shaped for retired goals — label-source guard, inert flags, dangling refs, fail-loud loads | **done** `dfe4c42` `91cf30d` `9faab4c` |
| **3.1** | the twins — one `names.py`, stdlib-only, importable from both planes | **done** `b939b34` |
| **3.2** | `config.py` protection made precise — 17 of 129 constants force a re-tile | **done** `37be4ab` |
| **3.3** | cite symbols, not lines — 30 pointers, gated | **done** `c9ce071` |
| **3.4** | the status ledger — one state vocabulary so oversight can see failure | **done** `b260212`; the 4 row keys / 4 filename parsers still have no owning module |
| **3.5** | `core.py` split — losses increment | **DONE 2026-08-31** for the losses cluster: `phase4seg/losses.py`, 213 lines moved, core.py 2,833 -> 2,621. Facade re-export keeps every `core.X` call site working (identity-checked, not copies). **My two recorded preconditions were BOTH wrong.** I wrote that laziness is "gated twice" — it is gated once; preflight only PRINTS `torch stayed unloaded` and asserts nothing. And the `ensure_torch(globals())` rework I boarded was rejected on design grounds: it would impose a per-module call-ordering obligation whose failure mode is a NameError at call time in training. **Function-local `import torch` in the five functions that need it**, exactly as `sdm_for_mask` already does for scipy — mutation-tested, hoisting them to module level fails two tests. `"losses"` added to `phase4seg_preflight.MODULES` in the same commit, and a test now derives that list from the package so no future module can be silently ungated. **This does NOT board the other clusters:** steps and ckpt-select carry monkeypatch surface (`test_select_smooth` patches `core._train_one_epoch`) and a test that hardcodes `step_evaluate` living in core.py. |
| **3.6** | per-run attribution of eval metrics in the registry | **done** `724f105` + this. The writer half was ALREADY built — `step_evaluate` stamps `run_tag`/`run_id`/`written_utc` (D6, 2026-08-29), including the note that the (year, channels) replace key is deliberately NOT extended because that would move which threshold real masks are cut at. It landed after the last evaluate ran, so the live report still carries none of those columns; they appear on the first evaluate from here. `held_out_metrics` now spans both eras — exact run_tag join when present (superseded archive included), year-level label when not — so no change is needed when they arrive. |
| **4.1a** | boundary loss — the signed-distance term itself | **done** `7c8a385` |
| **4.1b** | the SDM off the training step | **done.** NOT the cache the plan called for — that premise was false. The training augmentation (Rotate 45 + Affine scale + GridDistortion + Elastic, p = .5/.5/.4/.3) warps **89.5%** of tiles non-isometrically, so a field precomputed per tile describes a different shape than the mask the logits are scored against. Computed in the DataLoader worker AFTER augmentation instead: **446 ms -> 4.7 ms per batch of 10** off the critical path, measured. Total CPU work unchanged — it is parallelised, not eliminated. |
| **4.1c** | the boundary term vs perimeter exclusion on historical years | **open.** They cannot both apply to the same pixels; that is a decision, not a refactor. |
| **4.2** | training-only HR auxiliary branch | **UN-DROPPED 2026-08-31 — Kam unblocked degradation synthesis.** It was dropped hours earlier because its premise ("the archive supplies paired supervision free") depended on a workstream parked since 2026-08-27. That dependency is gone. The premise is still only HALF right and the board should not forget which half: the supervision is now AVAILABLE, but it is not FREE — making the LR half is a synthesis step with its own cost, and its PSF/blur component stays approximate (the measured R2 tables cover only the radiometric half). Sequence it BEHIND 4.5, not in front of it. |
| **4.5** | degradation synthesis — **UNBLOCKED (Kam, 2026-08-31)** | **inputs verified — after I got the verification itself wrong twice. Read `qc/instruments/radiometry_norm.py`'s docstring before touching this; it is unusually careful and answers most of it.** R2 EXISTS: that script is self-titled "R2 — RADIOMETRY NORMALIZATION". I claimed it did not because I searched only IMAGERY_FACTS and CHATLOG, never `qc/`. The fit is `DN_reference ≈ gain * DN_acquisition + offset`, so synthesis genuinely needs the INVERSE, as the plan said. The fit uses **6 points** (2 targets × 3 quantiles, OLS, 4 residual DOF) — I read `n_targets=2` and wrongly called it an exact solution; `fit_quality` IS a real RMS residual and `pre_rms` in the same row is the uncorrected baseline (e.g. 2000/R: 47.4 → 5.75). **What actually stands:** (a) the reference is `2020s`, not `2020` — the anchor is in the table as a transformed acquisition, so source from 2020s or compose 2020→2020s→Y; (b) NIR is referenced to `2019s` because 2020s is RGB-only, and two acquisitions get NO NIR coefficient at all (lifted black point, `excluded_reason` says so rather than emitting a number); (c) **"perfect masks" is false** — no gold hand labels exist; the 2020 mask is a model prediction and `polygons/` holds accept-all test data. **THE TRAP THE DOCSTRING FLAGS AND THE PLAN DOES NOT:** the offset is not a physical black point. Much of the ~+70 DN red offset on coarse years is the REFERENCE's sharpness — at 7.6 cm a hardscape pixel is pure, at 60 cm it mixes shaded canopy edge. So applying the inverse offset AND downsampling **double-counts the same mixing effect**. Phase A must resample first and fit the radiometry to the resampled result, or skip the offset and carry gain only. Also respect the published domain (`fit_x_min`/`fit_x_max`): outside it the map is extrapolation. |
| **4.6** | the object-ratio diagnostic | **DONE 2026-08-31, zero GPU — `qc/instruments/tile_object_ratio.py`.** Crown size MEASURED (20,000 Phase-0 crowns, true EPSG:26910 areas, median 6.46 m equivalent diameter); GSD is the measured `effective_cm`. One fixed 512 px tile spans **33–745 m (22.4x)** across the archive — not the ~7x the 2026-08-27 note estimated, which used nominal 15 cm–1 m. The 106 px ERF covers **2.07 / 6.60 / 15.60 crown-widths** (fine / medium / coarse). **Two corrections. (1) The three findings no longer disagree.** The 2026-08-27 note predicted COARSE-year underperformance from the object ratio; in fact coarse gets 7.5x MORE context per prediction than fine, so the pilot measuring coarse beating medium is what these numbers predict and the note is backwards. **(2) "The ERF is smaller than one crown at fine GSD" is FALSE for every real acquisition** — the minimum is 1.07 (2022, 6.5 cm effective), and dropping below 1.0 needs under 6.09 cm effective while the finest measured is 6.5 cm. Fine is context-POOREST, which survives and still orders Stage 4; it is not context-STARVED, which is what the plan and I both said. |
| **4.3** | DeepLabV3+ | **TABLED (Kam, 2026-08-31): "Let's scrap the deep lab. table it."** The plumbing is built and INERT — `ARCH` defaults to `unet`, so nothing runs it unless asked. Measured before tabling, so the record is complete: **2.44x faster** (620 -> 254 ms/batch, T2000, batch 4 @ 512 px), 45.7M vs 92.7M params — Kam's speed reason checked out. Cost: decoder is **stride 4** vs U-Net's full resolution, i.e. 52 cm/cell at the fine tier and 3.3 m at coarse, wider than half a 6.46 m crown, against a pipeline whose measured failure IS crown perimeters. **What stays and is worth keeping regardless of DeepLab:** the architecture stamp in the checkpoint and manifest. Nothing recorded which architecture produced a run before this, and U-Net/DeepLabV3+ share 626 of 685 keys, so a cross-load is a silent 91% partial load. That guard is provenance, not DeepLab. |
| **4.4** | resolution effect | **SUPPORT-MATCHED RESCORE DONE 2026-08-31, zero GPU — `qc/instruments/support_matched_rescore.py`. The gap is NOT a measurement artifact.** Both pilot arms aggregated onto one EPSG:26910 grid over the common extent, 255 masked before aggregation, each thresholded at its OWN operating cut, scored as per-cell area fraction. coarse-minus-medium recall: **+0.0584 native, +0.0564 @1 m, +0.0577 @2 m, +0.0571 @4 m** — flat across a 4x range of support, and the precision gap widens slightly (+0.0127 -> +0.0144). Each arm's own numbers also barely move, and the 1 m result reproduces the independent qc_indep numbers (2019s 0.6354 vs 0.6331; 2019n 0.6917 vs 0.6915) — two scoring paths agreeing. **So support is eliminated as the explanation.** What remains: the coarser arm genuinely scores better against C-CAP, and the live confound is now PROGRAM/SENSOR (Snohomish HXIP vs USDA NAIP), not measurement. That is still not a resolution result — settling it needs a within-acquisition test (one year at 1x/2x/4x), which needs GPU. The struck claims stand: '+9.2 OA' has no source in this repo, and 'a tiling parameter, not a retrain' is backwards. Do NOT super-resolve the coarse end. |
| **5** | pilot slice — 2019 / 2019s / 2019n | **LAUNCHED 2026-08-31 00:44-00:53Z**, three parallel arms, one queue file each (`pipeline/pilot_2019_{fine,medium,coarse}.yaml`). `pilotfine` + `pilotmed` on A100; `pilotcoarse` on **L4** because A100 assignment is CONCURRENCY-capped at 2 for this account (TooManyAssignments x6, not scarcity — see COLAB_AUTONOMY_SETUP.md). All three bootstrapped with ZERO engine diff between their commits, so the 2019s-vs-2019n pair is uncontaminated by code. **CORRECTION, then a CORRECTION OF THE CORRECTION (Kam, 2026-08-31).** I said the pair was "same DATE, not same flight, two programs". WRONG — `qc/imagery_pixelsize_and_date.csv` records 2019s as the *"same Hexagon flight as NAIP 2019"*. I read the `source` column (two download URLs) and never read `date_shot`. It is **ONE FLIGHT, TWO DELIVERED PRODUCTS**: the WA consortium 1-ft product and the USDA NAIP 60 cm product. Pixels agree — correlation peaks at EXACTLY zero shift (perfect registration, same flight), yet residual after a best-fit linear map is 14-27 DN, far too large for one to be a downsample of the other (a downsample leaves 1-2 DN). So sun angle, atmosphere, phenology and sensor HARDWARE are all identical; what differs is delivered GSD plus the PROCESSING CHAIN. **That makes the confound much narrower than I claimed and the resolution result correspondingly stronger** — it is not sensor-vs-sensor, it is one flight processed two ways. **3/3 GATE PASS as of 04:36Z** (every arm: mask GPKG, independent score, manifest with EPOCH, and all six steps OK unattended). The coarse runtime died TWICE and was resumed from the ledger both times, inheriting a verified checkpoint rather than redoing ~89 min. **The pilot gate is MET** — the go-condition for the 36-year run, which needs Kam. Numbers live in `phase4/qc/qc_indep_report.csv` (`live=1` rows) — not restated here. Run `py -3.12 qc/pilot_gate.py`. **U3 confirmed on all three tiers**: each ran labels→tile→train→evaluate→inference→postproc with no hand-typed step. |
| **6** | hard-year pilot + recipe audit — the LAST gates before the 36-run | **BOTH DONE 2026-09-01.** Pilot: recipe hypothesis CONFIRMED (2011s 0.756, 2006s 0.707 UNDETERMINED-by-0.013) — verdict + rule in `experiments/hard_year_pilot.yaml`. Then Kam's reflection question ("are we leaving anything obvious on the table like sieve") → full recipe audit, `Reports/RECIPE_AUDIT_2026-09-01.md` + `phase4/qc/postproc_variant_scores.csv` (instrument: `qc/instruments/postproc_variant_score.py`, validated by a pixel-identical anchor vs the shipped 2011s mask). Findings: **threshold is the ONLY large postproc knob** (23 recall pts + 54% canopy-AREA swing on 2011s; circular best-F1 selection is unguarded, fleet spans 0.332–0.643); morphology + sieve measured NEUTRAL even at the 3 m-kernel extreme; GPKG `area_m2` is CRS-unit area on ~30/36 years (attribute bug, mask unaffected); labels assert hard 0/1 on the 5.2%-of-valid band where the 2020 model was itself unsure (`--anchor-labels` machinery exists unused — candidate A/B, not a blocker). **Threshold policy DECIDED: C (Kam, 2026-09-01).** Machinery landed same day: dense u8 sweep (`phase4_qc_indep._write_dense_sweep`), selector (`qc/instruments/select_indep_threshold.py`) → `phase4/qc/indep_thresholds.csv`, engine untouched (`--infer-thresh` deploys). Pre-registered: `experiments/full_archive_e3.yaml` (status queued, 34 arms + 2 adopted pilot arms). **Remaining before launch: the GPU-gate ask** (2×A100, ~65–70 A100-hr). All other fixes post-GPU: masks re-derive from prob rasters on free CPU. |
| **7** | **TIER 1 — the science sample (COMPLETE 2026-09-03)** | **Verdicts written and gated (`experiments/tier1_science_sample.yaml`, status complete; data `phase4/qc/tier1_results.csv`): LIDAR-INPUT CONFIRMED (3/3 years beyond the .0085 replicate floor, both epochs); LIDAR-ADDER NOT CONFIRMED (1/3 — 2006s_add16 epoch-mismatch kill, -.503); NIR CONFIRMED (2016 AND 2019n); corruption <=10% inside floor (projection error binds, not noise). 27/28 arms scored (2011s_cor02 never produced a checkpoint). GPU all reaped; next: verdicts rewrite the full_archive_e3 recipe (Kam's 36-run gate).** Original spec kept below for provenance: | **Kam declined the full 36 (2026-09-02): "groups of high priority runs that will tell us a lot of info … a sub sample of the full imagery … representative … appropriate for training and validation." Rationale: postproc is free to redo, labels and bands are NOT — they invalidate trained models, so they get settled on a sample first. Plan: `TIER1_SCIENCE_SAMPLE_PLAN_2026-09-02.md`; 28-run matrix + decision rules pre-registered in `experiments/tier1_science_sample.yaml` (status queued). Years 2006s/2011s/2016/2020 + 2019n; factors: lidar-as-label (2005 + 2016 epochs), lidar-as-input, NIR on two sensors; seed replicates = measured noise floor; crown-structured label-corruption doses = calibration curve. Phase 0 (free: sample builder, CHM additions + contradiction kill-test, sample-vs-city calibration) precedes any GPU; Phase B ≈ 11–13 A100-hr on 2×A100, utilization measured ≥0.85 target. `full_archive_e3.yaml` stays queued as the Tier-2/3 vehicle and inherits Tier 1's recipe.** |

### Decisions taken (Kam, 2026-08-30)

- **Scope:** docs + cleanup + architecture. The full overhaul.
- **Baselines:** declare a new epoch and re-baseline. `EPOCH = 2`; pre-overhaul artifacts
  carry no marker, which means 1. **Do not backfill them.**
- **Target:** machinery + a pilot slice before any 36-acquisition run.
- **Source of truth:** this file for intent, `STATUS.md` generated for facts.
- **Architecture:** keep the U-Net and **resnet101**; change the loss, not the backbone.

---

## What is waiting on Kam

| | what | why it needs you |
|---|---|---|
| **main** | `main` is behind `work/20260824-sectors` (147 commits as of `c9ce071`; a hand-written count, so read it as a stamp, not a live number — `git rev-list --count main..HEAD` is the live one) | pushing/merging/tagging `main` is a hard DENY for Claude by design |
| **GPU** | the pilot slice (Stage 5) and any A/B | every first launch of a queue needs explicit approval — queue file, tier, runtime count, wall-clock, rough cost |
| **tag** | `git tag pre-refactor-2026-08-31 46a340e` + push it — a `git tag` deny in your global Claude settings blocks Claude; branches (work + archive) are already pushed and Canary 1 PASSED on the refactored layout | your deny rule, your call |
| **tidy-up** | move `train_queue_status.CONTAMINATED-BY-TEST-20260829.csv` out of `phase4/qc/` | no longer required for correctness (the discovery rule now excludes it) — just tidier |

Open questions recorded but not blocking:

- **Boundary loss vs perimeter exclusion.** The boundary term makes the model snap *to*
  the 2020 label edge; Stage 2 of the architecture plan wants perimeters *excluded* on
  historical years because a 2020 edge projected onto 2002 is not that tree's edge. They
  cannot both apply to the same pixels. Intended resolution: boundary term where labels
  are trustworthy, perimeters as IGNORE on distant years. **Untested.**
- **Synthetic degradation** for the empty leaf-off × coarse cell — touches the parked
  synthetic-imagery decision.
- **Phase-A learning rate** — the proposal says 1e-3, the repo uses 5e-5, a 20× gap. One
  flag, but a real scientific choice.

---

## Standing constraints

- **`main` is Kam's alone.** Claude pushes `work/…` and `fix/…` only.
- **`config.py` is pure-move protected** — append only; comments are safe, constants can
  force a ~20 min/year re-tile. Only ~17 of its 128 constants actually feed
  `_tile_signature` (Stage 3.2 will mark which).
- **GPU spend gate** on every first launch of a queue.
- **Honest evaluation:** LOSO is the only honest split; metrics against the 2020 mask
  reprojected onto another year are circular. If an effect is smaller than the measured
  noise floor, report **UNDETERMINED**, not "no difference".
- **Three-state masks:** 0 / 1 / 255 IGNORE. Any new loss term must be IGNORE-aware.
- **Never invent** hyperparameters or numbers. If it is not in the source, ask.

---

## What this file replaces

`WORKPLAN_2026-08-19.md` (still designated the tiebreaker by three other docs, but written
before both the 36-acquisition catalog and the semantic pivot), the `CHATLOG.md` STATE
block (which its own header admits "has become a TRANSCRIPT, not a reference" and which
carried four mutually exclusive "ACTIVE plan" claims), and the per-campaign `*_PLAN_*.md`
files as a place to look for current state.

Those files are not deleted — they are dated records of what was planned when. Stage 1.4
applies supersession banners so they stop reading as live.

---

## MASTER BOARD — everything done, everything remaining (refreshed 2026-09-08)

THE rule: if a task is not on this board, it is not planned work. Done work carries a
pointer to its verdict/artifact, never a restated number (one fact, one home).

### DONE — the completed campaigns (chronological)
| Campaign | Verdict pointer |
|---|---|
| Phase 0-3 + repo refactor + pilot slice (3/3 gate) | `WORKPLAN` §history, `experiments/pilot_2019.yaml` |
| Policy-C threshold selection (recipe audit) | `docs/SCHEMAS.md` indep_thresholds; `Reports/RECIPE_AUDIT_2026-09-01.md` |
| **Tier-1 science sample** (28 arms): LIDAR-INPUT confirmed, ADDER not, NIR 2016-only, corruption flat | `experiments/tier1_science_sample.yaml`; `phase4/qc/tier1_results.csv` + bootstrap CIs |
| Adversarial review + corrections (era-rescore fix, floors, footnotes) | `Reports/FINDINGS_LEDGER_2026-09-03.docx` |
| Accuracy instruments: sampler repair/redraws, U1 any-arm estimate, E2 covariates, certified-flat, C1 lidar anchors, C2/C2b edge tolerance, C3 same-flight floor | `phase4/qc/` (certified_flat_scores, metric_tolerance_scores, sameflight_consistency…) |
| Greenness gradient RESOLVED: delivery radiometry, not phenology (Kam's catch) | `Reports/GREENNESS_GRADIENT_CORRECTION_2026-09-03.md` |
| **Direction campaign / Panel A**: −2.21pp 2016→2024, CI ±1.10, 5 measured controls (blur, drift, verify, duplicates, capture) | `phase4/qc/panel_a_estimate.txt`; instrument `qc/instruments/panel_a_paired_change.py` |
| Lidar leg revived (decimation null: density can't fake loss): net GAIN 2005→2016 | `phase4/qc/lidar_decimation_null.csv`, `certified_change_cells.csv` |
| **trend8 8-year map series** + operating-point attack + recalibration: delivered cuts retracted, matched cuts PASS the sign test; 41/42 loss corroboration; flicker honest negative | `experiments/trend8_uniform_rgb.yaml` verdict; `phase4/qc/trend8_*` |
| **overlap_floor** (floor 0.15pp; factorial decomposed: op-point 6.5 + 1m-info 3.5 + season ~0; EagleView endpoints agree with Panel A) | `experiments/overlap_floor.yaml` verdict; `overlap_factorial_read.csv`, `eagleview_sign_test.csv` |
| Canopy DEFINITION review (four questions answered; draft definition §6) | `Reports/CANOPY_COVER_DEFINITION_REVIEW_2026-09-05.md` |
| Literature: 4 papers read+reasoned; families 3/4/5 deep-dive; sawtooth lit map | CHATLOG 2026-09-05/06 |
| **Overnight literature HUNT complete** (1,359 queries, 132 full reads): NO segmentation twin exists (gap claim now hunted); Roman/Nix/Healy = the peer-reviewed Panel-A lineage; PACC honestly refused; two-reader audit | `Reports/LIT_HUNT_DIGEST_2026-09-06.md` (+ FINAL/MASTER) |
| Change-detector design + adversarial review (step-shape certifier wins; shipped persist filter = recall tax; bounded temporal backfill formalized) | `Reports/CHANGE_DETECTOR_DESIGN_2026-09-06.md` |
| Flicker-program items 1, 2, 5, 6, 7 (parcels, floor, EagleView, census, factorial) | verdicts above |
| **Context retrieval built** — `qc/ask.py` answers any subject in ~40 lines instead of 115k tokens of CSV; coverage map makes the archive's holes a fact (13 never tiled, 9 never scored); failure registry turns 22 dead runs into 8 diagnosed causes | `py -3.12 qc/ask.py <subject>` · `--gaps`; `phase4/qc/{coverage_map.md,failure_registry.csv}`; `qc/known_failures.yaml` |
| **Run-context layer built** — tile sets have IDs and tracked tile lists, 535 manifests become a passport, every precision/recall carries its cut + population, PR curves tracked, per-year scoreboard at a held point | `phase4/qc/{tileset_registry,run_passport,arm_metrics,year_scoreboard.md}`; contracts in `docs/SCHEMAS.md` |
| **Speedup pilot (offload_pilot_2017k)** — tile offload PROMOTED (identical tileset from a CPU runtime; A100-bearing span cut 40%), checkpoint diet validated, postproc offload NOT promoted (2-vCPU compute penalty), same model at both ends | `experiments/offload_pilot_2017k.yaml` verdict; `phase4/qc/offload_pilot_2017k.csv`; `Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md` §7–9 |
| **Recording layer** — step markers with launching/verifying phases, iowait column, runtime facts, VERIFY minutes, attribution/timing/session harvests; first MEASURED Drive throughput and start-up/idle-tail accounting | `phase4/qc/{hw_step_attribution,timing_events,runtime_sessions}.csv`; `docs/SCHEMAS.md` hw sections; `qc/landed.py` rungs |
| **Queue ledger recovery** — six days of status rows erased by a module-identity bug (fixed, verified on the next launch); 25 snapshots preserved, 496-row candidate rebuilt from snapshots + logs (per-launch keyed, start-of-step ts) and restored to the lake additively | `phase4/qc/ledger_recovery/README.md` + `recovery_report.md`; `qc/instruments/rebuild_queue_ledger.py`; commits `e499355`, `8667378` |
| **Experiment registry built** — every campaign the project has run is now one machine-readable entry (43), joined to the measured homes and drift-gated; the .docx ledger becomes a Sep-3 snapshot, not the source | **`experiments/INDEX.md`** (start here); schema `experiments/README.md`; sweep audit `experiments/BACKFILL_RECONCILIATION.md` |

### RUNNING (external)
(none — the literature hunt completed 2026-09-06; angle-10 relaunch is QUEUED)

### AWAITING KAM — the decision stack (nothing moves without these)

**The decisions live in [`decisions.yaml`](decisions.yaml)** — one entry each, with
owner, dependency edges, why it matters and what to read first. Query them:

```bash
py -3.12 qc/ask.py --decisions        # the stack, ready-first
py -3.12 qc/ask.py <decision-id>      # one decision in full
```

They are NOT restated here: two homes for one stack is how the board and the ledger
drifted apart before. Gated by `qc/test_decisions.py` (ids resolve, the graph is
acyclic, a decided entry says what was decided).

### QUEUED (agreed or natural next, blocked or waiting a slot)
| Task | Blocker |
|---|---|
| Flicker item 3: Landsat per-flight-window phenology covariate (arbiter role; also dates 2011s) | satellite minimal-reopen nod (Kam) |
| Flicker item 4: 2024 degradation ladder (~5 A100-h) — GSD transfer function | Kam GPU nod |
| Flicker item 8: calibrated HMM on the prob stack (emissions from Panel A + parcels) — atlas smoothing, gated | items done; needs a design pass + kill criteria |
| SAM boundary-refinement pilot (C2b-gap kill criterion pre-written) | Kam nod; ~1 GPU-h |
| Free tests from the lit pile: map-loss UA spot check (~60 cells, Kam); ALCC-style change-count comparison; 30m-stability refutation | Kam minutes / CPU |
| Panel B (2005→2016 paired points, ~1 Kam-day) — would upgrade the lidar leg to human evidence | Kam's day + drift/blur controls port |
| 2020-Aug consortium fetch (phenology ladder completion) | ~1h, anytime |
| **Second-reader duplicate campaign** (~2,550 duplicates; interpreter error 3.6% is comparable to the effect and unpropagated) | Kam labeling day + a second reader |
| **Stable-stratum re-interpretation** (N≈2,070, date-blinded, order-randomized → ±1.5pp; certifies PACC + de-circularizes the kill test) | Kam ~1-2.5h |
| Change-detector build: gold-set freeze → step-shape certifier port (3 audit fixes) → tiered output → bounded temporal backfill | Kam go; 1-2 days CPU |
| Angle-10 relaunch (replacement-aware detection; spec+seeds ready in LIT_HUNT_MASTER) | engine budgets reset (after midnight UTC) |
| Port as instruments: smoothing-trap reproduction; edge-band anisotropy probe (13.2pp); sigma_chain MDC-floor publication | CPU, small |
| Truth-document F-number annotations (superseded by our own recalibration) + Literature_Tracker fixes | doc pass |
| Open-leads pass: unfired OpenAlex sweep, Scholar cited-by x12, Stehman texts, 42 UNREADABLEs via library | next research session |
| **Tile-bundle handoff** — one archive per tileset_id so train/evaluate/inference stage a set in one sequential transfer (measured today: 228 s per train for 1,264 files at 5.5 files/s) | workflow in flight 2026-09-08; verify on the next launch |
| **Ortho scratch cache with LRU** (Reports §2 row 2) — the same 11.5 GB ortho was staged four times across the pilot's two runs at 37–133 MB/s (`phase4/qc/timing_events.csv`) | after the tile-bundle lands (same files); capacity-aware, never three deleted lines |
| **Per-epoch train profiler** — train is GPU-busy ~20% and CPU>90% ~40% of its own time on the marker basis; `NUM_WORKERS=16` on 12 vCPUs; per-epoch data/compute/val/save split is unrecorded | engine change in `core.py`; canary on L4; after the tile-bundle lands |
| `common.py::_publish_replace` aside-rename guard (same defect `c5dc91c` fixed in the ledger, on the CHECKPOINT publish path) | after the tile-bundle lands (file ownership) |
| Ledger consolidation rung in `qc/landed.py` — per-launch status files grow one per launch and the start-up scan grows with them; fold old files into one archive, never sweep the lake while `ledger_recovery` originals sit there | design pass; small |
| Rebuild-instrument: session/window-aware suppression so a reused tag's later successful run is recovered (of2017k2's labels/tile rows, its 113-min span) | agent in flight 2026-09-08; then re-copy the candidate to the lake |
| Postproc on a CPU tier with more than 2 vCPUs (R3 failed on compute, not staging: polygonize 653 vs 436 s) | one free launch on a high-RAM/multi-core CPU tier, if the account offers one |
| Validate `94cb8df` (queue start-up bulk fetch: 359 s → ~14 s EXTRAPOLATED) and `3f60b0f` (bootstrap installs requirements) from the `startup:` line and the absence of `* installing` on the next launch | next launch, any queue |
| Evaluate's un-instrumented extra minute (2.1 vs 1.0 min engine time, tiles already local both runs) | tick/tock inside evaluate; small |
| **Concurrency cap raise** — still the only lever that divides wall-clock (Reports §3; per-acquisition GPU-bearing time now ~64 min measured) | Kam: account quota request |
| Ops debt: exec-handle retry loop in vm_ops; launch-time VM-side input preflight; heartbeat rename mirror-flap fix; pr_curves cwd-write; --only job-id friendliness; resume-credit root fix; mailbox stem collision | machinery grant, batchable |

### TABLED (parked with re-open conditions)
Instance segmentation (after semantic archive ships) · synthetic degradation training
(pre-2000 focus) · S2 fraction series (after Landsat covariate reports) · self-training
loop (after 36-run; one guarded iteration only) · object-kind decomposition (needs
sub-30-block resolution) · Shoreline transfer test (post-36-run paper polish)

### DEAD (adversarially killed — do not re-propose without NEW evidence)
Shadow masks/channel · uncertainty-weighted loss · KC/Shoreline pre-36-run ·
naive temporal smoothing as trend fix · label inheritance for trend · LandTrendr/CCDC
on uncalibrated aerial · leaf-off IGNORE experiment (premise was radiometry) ·
"uncorrectable 10pp delivery bias" (killed by the operating-point attack) ·
delivered-cut map fractions as a trend series (retracted) · more corruption doses ·
DeepLab · 5-band fusion · stability mining · model-confidence photo-interp strata


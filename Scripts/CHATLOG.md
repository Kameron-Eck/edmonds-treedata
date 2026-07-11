# Edmonds Pipeline — Chat / Progress Log

Running log of work sessions. Newest first. Open this → read STATE + top entries →
caught up. **This STATE block + the active plan ARE the handoff** (per-session
`HANDOFF_*.md` retired 2026-07-06 → `_archive/`). Doc map: `../README.md`.

════════════════ HOW TO LOG  (read before appending) ════════════════

STYLE — caveman, "full" level  (github.com/JuliusBrussee/caveman)
- Drop: articles (a/an/the), filler (just/really/basically/simply/actually),
  pleasantries (sure/happy to), hedging. Fragments OK. Short synonyms
  (big not extensive; fix not "implement a solution for").
- Pattern: "[thing] [action] [reason]. [next]."
- KEEP EXACT (never compress): code, file names, identifiers, numbers, flags,
  quoted errors, version tags. Well-known acronyms OK (DB/API/CRS); never coin
  abbreviations the reader can't decode.
- SUSPEND caveman (write plainly) for: irreversible-action / security warnings,
  and multi-step sequences where dropped conjunctions risk a misread. (skill's
  own auto-clarity rule). This HOW-TO block is instructional → kept plain.

SCALE — one block per SESSION or per landed MILESTONE (decision made / feature
landed / direction changed). NOT per message. Append when a unit of work closes.

ENTRY SCHEMA — fixed fields, omit empty ones:
    ## YYYY-MM-DD  <slug>
    goal:    why this session existed
    did:     what landed — DELTAS only
    decided: key decisions + 1-word why
    killed:  dead-ends / reversals — 1 line each, so we don't retry them
    files:   paths / version tags touched — reference, don't restate
    next:    open threads

SPACE RULES — keep always-loaded context low for continuous logging:
  1. Reference, don't repeat — link version/handoff/file; don't re-explain (see v025).
  2. Deltas not full-state — log what CHANGED; current full state lives in STATE.
  3. Outcomes not tool-noise — no command-by-command narration.
  4. Rolling compaction — keep newest ~6 entries full; older → 1 line each under
     "ARCHIVE (1-liners)". Compact when full entries exceed ~6.
  5. STATE edited IN PLACE (not appended) — always current, small.

════════════════ STATE  (current — edit in place) ════════════════

proj:    Edmonds temporal canopy pipeline, phase 4 (per-year semantic seg, 18 imagery yrs).
live:    ENGINE MODULARIZED 2026-07-08 → phase4seg/ package (config/common/labels/tiling/core[all torch]/
         postproc/cli) + 97L phase4_semantic_finetune.py SHIM (preserves `%run ... --args`). Behavior =
         v048, BYTE-IDENTICAL (AST-verified: 89/89 defs, 106/106 consts; py_compile+torch-free-import OK).
         NOT yet Colab-smoke-tested — GATE: `%run phase4_semantic_finetune.py --year 2000 --step tile`;
         revert = git revert df08f89. Tag v049 after smoke passes.
         phase4_semantic_finetune.py = v048. v048 = FIX: --force-citywide crashed on FINE years —
         the citywide candidate scan used a fixed 256px stride → a fine ortho (74k×106k @14.9cm) =
         119,770 candidates = ~2h scan → Colab timeout/OOM (just to pick 800 tiles). Now the scan
         stride ADAPTS to ortho size (CITYWIDE_CANDIDATE_TARGET=8000; floor 256), so fine 2013 = 8,025
         candidates (~few min) and COARSE IS UNCHANGED (2002 still 7,592 @ stride 256). --stride
         override still honoured. This unblocks the --force-citywide cross-sensor run.
         v047 = GPU-MEM + RECIPE-UNIFY + NO-OVERWRITE (Kam):
         (1) --infer-batch [def 32] replaces the old BATCH_SIZE*16=160 fp32 inference batch (the
         ~76GB spike → 80GB-only); inference forward now torch.amp.autocast + logits .float() before
         sigmoid. Output batch-invariant → pure memory knob → fits a 24GB L4 (~2-3x cheaper). Training
         ALREADY had AMP (autocast+GradScaler) → untouched. (2) --force-citywide: forces the citywide
         2020-mask coarse recipe on ALL tiers; keyed SAMPLER[already]/SELECTION-METRIC/pos_weight on
         use_blocked_val (the POOL) not gsd-tier → fully unifies + behavior-preserving. Removes the
         tier-recipe confound. Tile signature has citywide → auto-retiles; fine years scan full ortho
         (slower — test one first). (3) --run-tag TAG: suffixes model/prob/mask/gpkg _TAG so runs SAVE
         not OVERWRITE (_tag_sfx() + RUN_TAG global). py_compiled; run on Colab (torch). 
         v046 = AUX-HEIGHT BUGFIX (2016 aux run crashed): (1)
         RGB was upcast to float32 by the height-stack in __getitem__ → colour augs (uint8-
         assuming) corrupted it → training DIVERGED (val_bce→8-10); fix = cast RGB back to uint8
         before pixel_tf. (2) 4th forward site in step_evaluate not tuple-unpacked → 'tuple has no
         squeeze'; fix = unpack seg. RE-RUN 2016 --aux-height on v046. Ablation BASELINE (v045
         --no-hillshade, RGB-only no height) landed: honest rec .626 / prec .952 / GRASS-REJECTION
         .891 (RGB-only floor; CHM-input was .98) — that's the gap the height head must close.
         v045 = AUX-HEIGHT REFRAME (teach height, don't feed
         it), flag-gated (default OFF = identical to v044). --aux-height: RGB-only input + a 2nd
         output head that PREDICTS canopy height from RGB (UnetWithHeight subclass of smp.Unet,
         keeps encoder/decoder/segmentation_head keys → P3 ckpt loads strict=False; forward →
         (seg, height)). Height TARGET = CHM DN sidecar per tile (masked-L1, _masked_l1;
         _height_to_target normalizes (DN-1)*.2/40, -1 sentinel), written only for CHM_CREDIBLE_
         YEARS {2015,2016,2017,2020}; other years → aux loss auto-zeros. Wired: build_model,
         3 forward sites (tuple-safe), SemanticDataset.__getitem__ (height stacked thru
         spatial_tf then split), train/val loop unpack, tile sidecar + _tile_signature (forces
         retile) + _save_ckpt aux_height_head flag. --height-lambda [0.2], --emit-height
         (reserved). PHASE3 base NOT yet mirrored (next step for full transfer) — but the
         existing sem_best_2020.pt is already 3-ch RGB, so phase4 --aux-height fine-tunes fit
         from it directly (height head trains during the 2016 fine-tune) → the 2016 ablation
         runs NOW without touching phase3. py_compiled. plan = drifting-swinging-dolphin.md.
         v044 = INFERENCE OOM FIX: gc+empty_cache before
         inference (frees train/eval mem in the same process) + OOM-resilient flush (_forward
         auto-halves the batch on CUDA OOM). 2026-07-06 run: corrected labels APPLIED (overlay
         printed, full retile, 566/800 canopy tiles), train great (val_iou_bt .8829) but
         inference OOM'd at batch=160 (34GB + ~5GB train leftover > 40GB A100) → prob raster
         empty → qc_score returned 0 valid px (NO honest number yet). circular eval IoU .82 is
         INFLATED (test tiles now carry corrected labels) — ignore it; qc_score vs NDVI is the
         test. NEXT: fresh runtime → --step inference → postproc → phase4_qc_score.
         v043 = FIX: _tile_signature now includes
         --add-canopy-mask (path+size+mtime) so the corrected-label overlay invalidates
         cached tiles. v042 BUG: idempotent tiling (v035) reused stale tiles → the 2026-07-06
         2016 run REUSED 685 old tiles, corrected labels NEVER applied (eval ≈ v039 baseline
         IoU .7695). Overlay baked at tile time → MUST retile. Key only present when overlay
         set (no spurious retile for other years). RE-RUN 2016 --add-canopy-mask (auto-retiles
         now) → qc_score vs NDVI is the real test, NOT the circular eval.
         v042 = --add-canopy-mask: ADD-ONLY corrected-
         label overlay (canopy_additions_{year}.tif from phase4_build_corrected_labels.py)
         on the coarse 2020-mask label path. additions_from_mask (reproject onto crop) +
         apply_additions (code 1→canopy, 2→IGNORE, NEVER canopy→bg), applied in
         _gather_citywide_coarse after canopy_label_from_2020_mask. one file (2016 grid)
         serves 2016 AND 2000 (reprojected; outside strip → plain 2020 mask). NEEDS RETILE.
         v041 = --infer-thresh: explicit postproc
         op-threshold override in (0,1); bypasses eval-CSV best_f1 lookup. LOWERS an
         off-yr thresh (e.g. 2000 .513→.30) to recover CHM-suppressed stands. blunt —
         honest ref pending Phase 1/5. (_operating_threshold top + argparse + global).
         v039 (RESEARCH-BACKED ROUND 1, Phases 1+2):
         P0 fixes: (1) SAMPLER — citywide-coarse now natural/shuffle (was inverse-
         SITE weighting → gave each pure-neg site = "city" mass → batches ~83% bg;
         THE underperformance bug); (2) FREEZE_ENCODER_BN default True (+--no-
         freeze-encoder-bn); (3) Phase B resumes from BEST ckpt not last-epoch;
         (4) COARSE_USE_POS_WEIGHT=False → Dice owns balance (single channel, natural
         sampler). Validity: (5) _validate pools global IoU (was per-batch mean);
         (6) eval reports *_op metrics at deployed op-thresh + AP headline; (7) aug
         borders fill_mask=IGNORE not bg; (8) medium/fine random-split leakage
         caveat in eval_scope. v038 = coarse select val_iou→val_iou_bt. RUN with
         --freeze-encoder-bn now DEFAULT.
         v040 = postproc polygonize VECTORIZED (shapely 2.x simplify/make_valid/
         area C ufuncs over whole array + fiona.writerecords batch; was per-polygon
         Python loop w/ simplify preserve_topology=True — slow on 100k+ city
         crowns). Fallback to old loop if shapely<2. preserve_topology now False.
         pins frozen-encoder BN to pretrained running stats in Phase A [def OFF].
         PRIME SUSPECT for the fixed-epoch E6 cliff — BN drift under trainable
         input-conv + off-dist pool. _set_encoder_bn_eval re-applied after every
         model.train()). v035 = IDEMPOTENT TILING: citywide
         step_tile skips the ~20-min scan when a complete tile set matching the
         sampling signature already exists on Drive [sidecar tile_index_*.
         meta.json]; --force-retile overrides. Re-running full pipeline after a
         lost Colab session now reuses tiles. 2016 sidecar pre-seeded).
         v034 = flags --epochs-phase-a [def 20] / --epochs-phase-b [def 30]; =0
         skips Phase B → fast diagnostic runs. Phase B → _run_phase_b helper.
         v033 = flags --bce-weight/
         --dice-weight [def .5/.5] to isolate the dice term; train-only. v032 =
         SOFTENED SAMPLING HARD_NEG_FRACTION .30→.15, BACKGROUND_BUDGET_FRACTION
         .30→.22 (needs retile; DID NOT fix cliff). v031 = flags
         --coarse-pos-weight-max [def 1.3] / --lr-phase-a [def 5e-5]. v030 =
         (RGB+CHM 4ch; --hs-source chm default
         [was struct]; grass hard-negs RE-ENABLED HARD_NEG_FRAC .30 / GRVI .08 /
         bg-frac .30; no-coverage band4 → neutral fill; --hs-dropout 0.25; v029
         Phase-A trainable inflated stem). HS_STATS['chm'] :445 = ([.2306],[.2305])
         pasted (real, from fetch_build_chm.py).
data:    Full_Image/Pipeline Imagery/: lidar_snoh_hillshade_fr.tif, _be.tif,
         lidar_snoh_structure.tif = clip(fr-be+127,1,254) [TEXTURE not height,
         weak, AUC~.70], all EPSG:3857 1m ~2016 3DEP QL1 same grid. struct stats
         /255 nonzero: mean .3867 std .2175. NEW lidar_snoh_chm.tif = REAL canopy
         height (3DEP HAG metres, U8-scaled 0.2m/DN, 0=nodata). BUILT 2026-07-04:
         coverage 59.8% (~= struct 57%; same lidar footprint — rest is Puget Sound
         W edge + S margin = water, no canopy). height p50 6.7m p90 30.9m p99 44.6m.
         stats /255 nonzero mean .2306 std .2305. HAG includes buildings (fine —
         RGB flags non-green).
open:    (0) [2026-07-10 ACTIVE — plan = cozy-skipping-jellyfish.md + AMENDMENT 2026-07-10 at top]
         TWO-STREAM, ONE SHARED RGB BACKBONE, LABELS-FIRST, INSTANCE-ON-FINE FIRST. 3-agent architecture
         review (instance-first champ / semantic-unified champ / adversarial referee) synthesis:
         DELIVERABLE = ALL urban trees incl. yard/street/ornamental (3-30-300/equity). VISUAL GROUNDING:
         8/8 missed stands (2 top-fn + 6 mid-fn 0.50-0.66) = SUBURBAN (houses+lawns+ornamental yard trees,
         many purple-leaf LOW-NDVI), ZERO deciduous forest. So the ~0.68 honest-recall gap splits into
         (a) C-CAP definitionally OVER-counting leafy suburbs as "Upland Forest" (NOT a model error — counts
         lawns/roofs between yard trees) + (b) the model genuinely under-detecting SCATTERED suburban/
         ornamental (incl. non-green) trees. → Phase B target CHANGES from "deciduous forest stands" to
         "suburban/ornamental crowns in representative neighborhoods". 3 CONSENSUS FINDINGS (settled):
         (a) augmentation bridges RESOLUTION only, NOT sensor/contractor/radiometry — "one model spans all
         yrs via aug" is HALF-true (spans 8x GSD, NOT the King-contractor change / NAIP / Snoh); King-2019
         != King-2000 radiometrically. (b) the residual miss needs REAL labels — norm/aug can't reach
         low-NDVI ornamentals. (c) King 2000/02 = HARD FLOOR: unfalsifiable (no labeled sibling post-
         contractor-change, no NIR, C-CAP starts 2016, CHM stale) → un-trainable AND un-measurable from
         2020 labels; give them own labels + in-yr Olofsson, or ship LOW-CONFIDENCE. ARCH: one shared
         U-Net ResNet-101 RGB backbone, TWO heads — instance (DTM→watershed, ≤14.9cm only, Qin 2023) +
         semantic (BCE, all 18 yr); crowns dissolve→semantic FREE at fine res (& better: ornamental = a
         discrete DTM object vs a greenness-keyed BCE pixel). SEQUENCING = fine-res INSTANCE-FIRST *after*
         the label-bias fix (else you master a biased detector), coarse semantic 2nd w/ per-(sensor×era)
         anchors + radiometric normalization. LABEL RULE: instance where ≤14.9cm, semantic where coarse.
         ANNOTATION PLAN (merged, priority; 1-4 committed): 1) 2020 CoE 7.5cm INSTANCE +3-5 suburban/
         ornamental/low-NDVI sites ~1-3k crowns (root fix, both heads); 2) 2015/2013 King 14.9cm INSTANCE
         2-4 stands (anchors 5-yr King cluster); 3) 2016 Snoh 50cm SEMANTIC top-FN stands (best-
         instrumented coarse yr); 4) 2000/2002 King 60cm SEMANTIC + in-yr Olofsson pts; 5) NAIP 2019n/22n
         MEASURE first (C-CAP2021+NDVI), label only if gap. Olofsson harness GATES any pre-2016 number.
         NEXT: stage item-1 package (2020 suburban/ornamental sites + Phase-0 crown draft to correct);
         reconcile Method_Pipeline/buildtracker/xlsx to TWO-STREAM. SUPERSEDES the base plan's "semantic-
         only, labels-at-≥2-res" framing (now: two-stream, labels-per-domain).
         (0-old) [2026-07-05 SUPERSEDED] CORRECTED-LABEL workstream (supersedes 2015-flagship +
         deciduous-positive-site idea). user reframe: we have 2020 labels + CHM yet miss
         deciduous marsh → INVERT the QC instrument: use 2016 NIR+CHM to LABEL the misses,
         not just measure. NEW phase4_build_corrected_labels.py → canopy_additions_2016.tif
         (ADD-ONLY: NDVI>=.3 & CHM>=3m → canopy; green 2-3m → IGNORE; 31.97% of strip =
         hiconf canopy). v042 --add-canopy-mask layers it on coarse 2020-mask path. trees
         static → same file serves 2000. honest-recall baseline still .605 rec / .970 prec
         vs NDVI+CHM (phase4_qc_*). plan = drifting-swinging-dolphin.md. principle: lidar
         informs, never vetoes. NEXT (Colab): retile+retrain 2016 w/ overlay → qc_score vs
         NDVI; PRECISION GUARD (grass-reject ~.98, precision not down) or reject/tighten to
         .35/4m. then 2000 same overlay. measurement: NDVI now spent on labels → use
         --holdout-frac strip or build photo-interp (open item 2).
         (1) [FABLE — RESOLVED 2026-07-05] 2016 chm "collapse" root cause was the
         SAMPLER (1/count[site] → citywide batches ~83% bg) + val_iou@0.5 metric
         artifact. v039 fixed both + 6 more (see live). 2016 chm now BEATS rgb on
         held-out TEST: IoU .7725 / AUROC .938 / AP .883 / Prec .823 / Rec .927
         (vs rgb .7245/.929/.856/.773/.921; broken chm was .49/.784/.58). recall
         recovered, precision UP (grass-FP signal). CHM helps once sampler honest.
         NEXT: phase4_viz grass-FP confirm → carry config to 2000 → then Phase 4.
         (2) [NOW THE PRIORITY per user] honest-accuracy INDEPENDENT yardstick.
         RIGOR LADDER: circular proxy < C-CAP < human photo-interp. RUNG 1 DONE
         2026-07-07 = phase4_qc_indep.py + NOAA C-CAP hi-res 1m acquired (ccap_{2016,
         2021}_hires_lc.tif, EVAL-ONLY). FIRST non-circular number IN: 2016 model
         recall .684 / prec .865 / grass-rej .935 (vs NDVI+CHM .59/.96 — the two refs
         BRACKET truth). STILL PENDING = the variant RANKING (Colab-gated: only the
         current prob_2016.tif on disk; regen aux/CHM/RGB variant rasters → --prob
         each). RUNG 2 (deliverable-grade arbiter) = random-point photo-interp
         (Olofsson 2014 stratified + area-adjusted CIs) — still unbuilt. (3) radiometric normalization +
         test-time BN across years (temporal domain shift) — unbuilt. (4) coarse
         labels from 2020 mask → label-circularity ceiling until (2) exists.
blocked: none.
docs:    SOURCES OF TRUTH CENTRALIZED 2026-07-06. HANDOFFS RETIRED (5 old ones →
         Scripts/_archive/handoffs/) — this STATE + the active plan ARE the handoff now.
         Front-door doc map = treedata/README.md. To resume: read this STATE + top ~4 LOG
         entries + the active plan (D:\tools\claude-config\plans\cozy-skipping-jellyfish.md). Do NOT create a new
         HANDOFF. one-fact-one-home: live state here, method=Method_Pipeline.md, build
         status=pipeline_buildtracker.md, schedule=edmonds_combined_workplan.xlsx.
gotcha:  scripts Colab-only for torch (rasterio+geopandas+fiona+sklearn now pip-
         installed local — module import auto-installs). polygons/ overwritten w/
         accept-all test data; 14,476-crown human review never finished.

════════════════ LOG  (newest first) ════════════════

## 2026-07-10  3-agent architecture review → two-stream, instance-on-fine first, per-domain labels
goal:    Kam: single model for all imagery forces the question — with only 2020 instance labels + King
         contractor changes (2019 King != 2000 King radiometry) + instance dead below 14.9cm, is it
         instance-first or semantic-first? spin up 3 architecture reasoning agents. deliverable = all trees.
did:     Visual grounding first: side-by-side LEARNED (Forest_2/4 + hand crowns) vs MISSED stands, then 6
         mid-fn (0.50-0.66) stands → ALL suburban (houses/lawns/ornamental yard trees, many purple-leaf
         low-NDVI), ZERO deciduous forest. So "forest under-prediction" = C-CAP over-counting leafy suburbs
         + genuine under-detection of scattered suburban/ornamental trees, NOT missed deciduous forest.
         3 opus agents (instance-first champ / semantic-unified champ / adversarial referee) → synthesis.
decided: TWO-STREAM one shared RGB backbone (instance ≤14.9cm + semantic all-18); fine-res INSTANCE-FIRST
         after the label-bias fix, coarse semantic 2nd w/ per-(sensor×era) anchors + radiometric norm.
         instance where ≤14.9cm, semantic where coarse. deliverable = ALL trees incl ornamentals. 3
         consensus: aug bridges RESOLUTION not SENSOR; residual miss needs REAL labels; King 2000/02 =
         unfalsifiable hard floor. merged annotation plan: 2020 suburban INSTANCE > King-14.9 INSTANCE >
         Snoh-2016 SEMANTIC > 2000/02 SEMANTIC+Olofsson > NAIP measure-first.
killed:  "instance-first is a dead-end" (referee) — REJECTED as stated: a sequencing point not a veto (fine
         instance gives free+better semantic; coarse semantic just DEFERRED, still needs own labels).
         "one model spans all yrs via multi-scale aug" (base-plan pillar) — DEMOTED to half-true (GSD only);
         per-domain real-label anchors now required or sensors fail silently.
         "hand-trace deciduous FOREST stands" (base-plan Phase B target) — WRONG target; the miss is
         suburban ornamental → trace suburban/ornamental crowns instead.
files:   plan cozy-skipping-jellyfish.md (AMENDMENT 2026-07-10 appended at top); CHATLOG STATE open(0)
         rewritten; photos/_reduced/compare_learned_vs_missed.png + mid_fn_missed_stands.png (evidence).
next:    stage item-1 annotation package (2020 suburban/ornamental sites + Phase-0 crown draft to correct);
         reconcile Method_Pipeline/buildtracker/xlsx to two-stream; build Olofsson harness.

## 2026-07-10  STRATEGIC RESET → one scale-robust model, labels-first (plan cozy-skipping-jellyfish.md)
goal:    Kam: stop spinning in circles; synthesize everything into a plan for a really robust semantic
         model; the deliverable must apply one method to all resolutions; open to hand-annotating; update workplan.
did:     3 research subagents (history / real numbers / data+label landscape) + Method_Pipeline read →
         PLAN D:\tools\claude-config\plans\cozy-skipping-jellyfish.md. Findings: labels are THE bottleneck
         (only 2020 hand-labeled, all conifer/high-NDVI); deciduous under-prediction ≈ 94% of error and
         STRUCTURAL; CHM = biggest lever but disqualified as a model INPUT (stale snapshot) → CHM/NDVI in
         LABELS only; ONE RGB model spans 7.5-60cm via multi-scale aug + real labels @≥2 res (Wang&Fan;
         2000≡2002 @common thresh). PHASE A LANDED: (1) Forest_4 EMPIRICAL — its 2016 canopy NDVI 0.611 ≈
         the other conifer sites (0.59-0.62), far from the missed 0.42 → F4 does NOT cover the blind spot,
         Phase B (add low-NDVI deciduous) confirmed. (2) fixed 2 audit measurement bugs (a63e208):
         phase4_qc_ndvi CHM-nodata→grass (now IGNORE); postproc _operating_threshold mis-key (now filters
         the current (year,channels) arm).
decided: REJECT "coarse & fine need different models" — the apparent gap is the tier-recipe confound
         (fine 2015 swings 0.26→0.62 recall on IDENTICAL data by recipe). Deliverable = ONE documented
         method for all 18 years. Cross-sensor work demoted to validation-later, not the build path.
next:    Phase B — stage + HAND-TRACE the top-FN deciduous stands (forest_miss_stands_{2016,2015}.csv) at
         2016 (coarse, NIR-verifiable) + a fine year; keep a C-CAP eval split. Then Phase C unified train.
         Also quarantine the broken 2022 (rec .004) / 2017 (qc 0 valid px) runs.
files:   plan cozy-skipping-jellyfish.md; phase4_qc_ndvi.py; phase4seg/postproc.py. commit a63e208.

## 2026-07-08  Phase-4 engine modularized → phase4seg/ package; POC notebook cleaned; experiments/ split out
goal:    Kam: turn phase4 into modules; separate experimental data-science from the POC pipeline.
did:     phase4_semantic_finetune.py (3953L monolith) SPLIT → phase4seg/ package: config, common, labels,
         tiling, core (ALL torch code), postproc, cli + 97L shim (preserves `%run phase4_semantic_finetune.py
         --args`). 20 runtime-mutated globals → config.NAME namespace; torch handles stay in core (lazy
         _ensure_torch intact); geo bootstrap in common (acyclic import graph). VERIFIED byte-identical:
         py_compile all; torch-free modules import w/o torch; AST-equivalence vs pre-split original =
         89/89 defs+classes + 106/106 module consts logic-identical, 0 drops/mismatches (only allowed deltas
         = config.-prefix + removed `global` stmts). ALSO cleaned TreeCrownInventory.ipynb (POC notebook,
         git-UNTRACKED): backed up → TreeCrownInventory.BACKUP-2026-07-08.ipynb (95 cells, byte-identical),
         rewrote 95→34 cells (dropped superseded phase0 prototype cells 3-51 + dead drivers 52-64; kept
         drive-mount + current-pipeline launchers; stripped outputs 1.9MB→45KB). NEW experiments/ at repo
         root (git-ignored per /* allowlist) + README + archive/phase0_prototype_from_notebook.py (cells
         3-51 source w/ provenance).
decided: pragmatic split (torch core cohesive) over full split — 20-global + lazy-torch coupling makes a
         full split need a shared-runtime rewrite = higher risk mid-study. pkg = phase4seg (NOT phase4:
         avoids treedata/phase4 data-dir collision; Scripts/ is git-whitelisted so pkg is tracked).
open:    (SMOKE GATE) engine NOT run on Colab yet — CANNOT run locally (forces mp start_method 'fork').
         Kam: run `--year 2000 --step tile` before any real study run; revert = git revert df08f89. Tag v049
         after smoke passes. experiments/ tracking: say the word to whitelist in .gitignore (data still
         excluded). NOTE: a few retained notebook launcher cells %run now-archived scripts
         (proof_of_concept_colab.py, temporal_overlay.py → _archive/scripts/) — stale paths, scratch only.
files:   phase4seg/* , phase4_semantic_finetune.py (shim), TreeCrownInventory.ipynb (+ .BACKUP-2026-07-08),
         experiments/*. commit df08f89.
next:    Kam Colab smoke-test the split → tag v049; decide experiments/ git-tracking; triage audit SUMMARY.md §2.

## 2026-07-08  Full-codebase audit (6 subagents) + declutter + 2 output-safe fixes
goal:    Kam: find bugs/inefficiencies/bottlenecks; move dead scripts out; delegate heavy read to non-Fable models.
did:     6 parallel subagents (1 Opus on live engine, 4 Sonnet, 1 classify) audited every active script.
         Report → _audit_2026-07-08/ (SUMMARY.md + 6 detail md, git-tracked). Archived 53 dormant pre-Phase-0
         acquisition/discovery/registration scripts → _archive/scripts/ (root .py 82→29; grep-verified NO
         active import/%run references any). 2 VERIFIED fixes APPLIED: phase0_instance_seg.py:1823
         .union(*geom_list[1:])→unary_union (latent crash on 3+shape crowns; anchor run never hit it, so no
         output change); phase4_semantic_finetune.py:3415 np.where(data==1,1,0) int64 temp→(data==1).astype
         (uint8) (BYTE-IDENTICAL, kills the fine-year postproc OOM). both py_compiled.
decided: applied ONLY output-safe fixes. measurement/numerics/recipe changes LEFT for Kam (SUMMARY.md §2).
         engine fix byte-identical → NOT version-bumped; Kam may tag v049.
open:    top review items — qc_ndvi.py:169 CHM-nodata forced to grass → biases honest recall/prec; engine:3342
         operating-threshold mis-keys on run-tag/channels (silent wrong-arm threshold). full list SUMMARY.md.
files:   _audit_2026-07-08/*, _archive/scripts/* (53), phase0_instance_seg.py, phase4_semantic_finetune.py.
         commits e7ee743 (archive), 3c981cb (fixes), 631810f (audit docs).
next:    Kam triage SUMMARY.md §2 (needs-decision) → greenlight measurement/numerics fixes.

## 2026-07-07  v048 FIX: --force-citywide crashed on fine years (citywide scan candidate blow-up)
goal:    Kam's --force-citywide --run-tag citywide_rgb run crashed SILENTLY twice, both in 2013's
         city-wide TILING scan (not inference — this run already ran --infer-batch default 32).
cause:   the citywide candidate scan used a FIXED 256px stride. On a fine ortho (2013 = 74496×105984
         @14.9cm) that = 119,770 candidate positions → ~2h scan (log: 49% in 18min, ETA 1:41) → Colab
         idle/runtime timeout or host OOM. Coarse orthos are ~15x smaller so it never bit them (2002 =
         7,592). Just to select COARSE_CITYWIDE_TILES=800.
did:     _gather_citywide_coarse now ADAPTS the scan stride to ortho size AFTER opening it:
         stride = max(CITYWIDE_CANDIDATE_STRIDE, round(sqrt(H*W / CITYWIDE_CANDIDATE_TARGET))), target
         8000. Verified: coarse 2002 → stride 256 / 7,592 candidates (UNCHANGED, floor holds); fine
         2013 → stride 993 / 8,025 candidates (~few-min scan); 7.5cm → 1987 / 8,025. --stride override
         still exact. py_compiled.
decided: bound the SCAN not the budget — 8000 candidates (10x the 800 budget) keeps bin-stratification
         diversity while making the scan GSD-independent. Behavior-preserving for every existing coarse
         run (stride floored at 256).
files:   phase4_semantic_finetune.py (v048; CITYWIDE_CANDIDATE_TARGET const + adaptive stride in
         _gather_citywide_coarse).
next:    Kam RE-RUN the same command — `--year 2013,2015,2017,2022 --no-hillshade --force-citywide
         --run-tag citywide_rgb` (fine citywide tiling now feasible). Tiles are tagged-independent, so
         completed years persist. Then the local --years autopsy on the _citywide_rgb rasters.

## 2026-07-07  Cross-sensor forest-miss autopsy — FIRST CUT (2000/2002/2013, RGB-only, PRE-force-citywide)
goal:    read where/why upland forest is missed across sensors (phase4_qc_forest_misses.py --years) on
         the first inference rasters off the --no-hillshade run, before the full set lands.
did:     scored 2000,2002,2013 vs C-CAP-2016 forest, ∩C-CAP-2021 stable-forest filter — first at each
         year's DEPLOYED threshold, then re-run at a FIXED 0.4615.
found:   (1) THRESHOLD CONFOUND is real: @deployed 2000 .649 vs 2002 .582 (6.7pp gap) → @fixed 0.4615
         both = .680 / .683 (0.2pp). Adjacent King-60cm years are IDENTICAL at a common threshold →
         temporal stability confirmed; the gap was per-year op-thresholds, NOT sensor/change. LESSON:
         always compare years at a COMMON threshold or threshold drift masquerades as canopy change.
         (2) BRIGHTNESS = the coarse-King failure mode, threshold-robust: missed forest is +28/+17 DN
         brighter at 60cm (2000/2002) vs +1 at 15cm (2013); conf-miss (prob<.12) 19-24% @60cm vs 9%
         @15cm. Coarse pixels mix canopy+bright understory/gaps + older-ortho radiometry. (Contrast
         2016 snoh, where misses were spectral/less-green, not bright — different sensors fail
         differently.) (3) HEIGHT bias UNIVERSAL: missed ~14m vs recalled ~25m on EVERY sensor (tall
         recalled, shorter missed) → structural, resolution-independent.
caveat:  the GSD→recall lift (15cm .733 vs 60cm ~.68) is RESOLUTION+RECIPE confounded (2013 = fine
         6-site recipe; 2000/2002 = coarse citywide) → NOT clean until --force-citywide rasters. Also
         2000/2002 recall is a LOWER bound (14-16yr of pre-C-CAP-2016 growth reads as "miss"). These
         rasters are PRE-v047 (--no-hillshade only, per-tier recipe).
files:   phase4/qc/forest_miss_sensor_compare.{txt,csv}; forest_miss_{2000,2002,2013}.{txt,csv,png},
         forest_miss_density_{year}.tif, forest_miss_stands_{year}.csv.
next:    re-run `--years` at a fixed threshold AFTER the --force-citywide rasters land (uniform recipe
         → isolates the pure resolution axis); expand to the naip/snoh sensors as those years finish.

## 2026-07-07  v047: infer-batch + inference AMP (GPU↓) + --force-citywide + --run-tag
goal:    (Kam) cut inference VRAM to run a cheaper GPU; unify the per-tier training recipe for the
         cross-sensor study; stop overwriting Colab outputs.
did:     phase4_semantic_finetune.py v047 — 3 features:
         (1) GPU MEM. --infer-batch [def 32] replaces the old BATCH_SIZE*16=160 fp32 inference batch
         (the ~76GB spike, 80GB-only). Inference forward now under torch.amp.autocast + logits cast
         .float() before the numpy sigmoid. Batch is a pure memory/speed knob (eval/no_grad/running-BN
         → output batch-invariant). Training ALREADY used AMP (autocast+GradScaler in _train_one_epoch/
         _validate) → left untouched. Net: fits a 24GB L4 (~2-3x cheaper than the A100).
         (2) --force-citywide. Forces the citywide 2020-mask COARSE recipe on EVERY tier: main citywide
         decision `or args.force_citywide`, and keyed the SAMPLER (already), SELECTION-METRIC, and
         pos_weight on use_blocked_val (the POOL) instead of the GSD tier → fully unified AND
         behavior-preserving for existing coarse/medium/fine runs. Removes the tier-recipe confound Kam
         flagged (coarse = citywide-mask + natural sampler + val_iou_bt vs fine = 6-site crowns +
         per-site sampler + val_bce). Tile signature already includes citywide → auto-retiles. Fine
         years scan the full ortho (slower) — test ONE first.
         (3) --run-tag TAG. Suffixes model/prob/mask/gpkg with _TAG so successive runs SAVE not
         OVERWRITE (variants/recipes for later analysis). _tag_sfx() helper + RUN_TAG global (matches
         the AUX_HEIGHT config-global pattern). Eval CSV stays label-keyed (threshold lookup unaffected).
decided: recipe keyed on POOL (use_blocked_val) not GSD tier — unifies force-citywide while preserving
         every existing path. AMP dtype = default fp16 (matches training).
files:   phase4_semantic_finetune.py (v047; +USAGE lines). py_compiled OK; NOT run locally (torch=Colab).
next:    Kam: for the cheap-GPU run add --infer-batch 32 (fits L4 24GB). For the consistent cross-sensor
         set use --force-citywide (test ONE fine year first — new combo) + --run-tag <recipe>. Then the
         local autopsy/qc tools score via --prob on the tagged rasters.

## 2026-07-07  BUILT phase4_qc_forest_misses.py — under-prediction autopsy + finding
goal:    understand WHY C-CAP upland-forest (recall .68) is missed → locate stands to stage as
         positive sites + get writeup stats on the misses (Kam: explain the "sensor issue").
did:     NEW phase4_qc_forest_misses.py (local, torch-free). Over C-CAP forest px {9,10,11}, splits
         recalled(TP) vs missed(FN), streams mean/std + histograms of prob / RGB / brightness /
         saturation / NDVI / GRVI / CHM height. Outputs forest_miss_2016.{txt,csv,png} + coarse
         FN-density raster (forest_miss_density_2016.tif, ~39m cells) + TOP-12 missed-stand shortlist
         (lon/lat → forest_miss_stands_2016.csv) for site staging. imagery+prob share the EPSG:2285
         grid; C-CAP + CHM reproject via WarpedVRT nearest. Auto-diagnosis built in.
         EXTENDED (later same day): --years CROSS-SENSOR compare mode (per-year row + table,
         forest_miss_sensor_compare.csv) + --stable-with (forest must be forest in BOTH C-CAP vintages
         → isolates sensor from real change) + --prob-suffix (score --run-tag'd rasters) + full 18-yr
         IMG_CATALOG/GSD/sensor. Stable-forest control on 2016: recall .682→.762 (change noise removed).
found:   misses are NOT a sensor/exposure problem (Δbrightness +2 DN, saturation flat). SPECTRAL +
         STRUCTURAL: (1) 69% of misses prob<0.12 = CONFIDENT / out-of-distribution, NOT a threshold
         fix; (2) NDVI .349 vs .568 recalled (Δ-.219), lower GRVI, more R/B less G = DECIDUOUS /
         broadleaf the conifer-only training never taught; (3) height 11.8m vs 23.8m — model recalls
         tall dark conifers, misses shorter lighter deciduous (still real trees, not scrub). Writeup
         story = "conifer-biased spectral domain", not bad imagery.
decided: fix = TEACH deciduous (stage POSITIVE forest sites at the top-FN stands), NOT lower threshold
         (misses are confident). Several stands are fn_frac=1.00 (entirely missed) e.g. -122.325/
         47.805 cluster. C-CAP only LOCATES stands — never labels (portability preserved).
files:   phase4_qc_forest_misses.py (NEW); phase4/qc/forest_miss_{2016.txt,2016.csv,2016.png,
         density_2016.tif,stands_2016.csv}; Method_Pipeline.md (+autopsy note); CLAUDE.md (script row).
next:    stage top-N stands via make_positive_site.py (crowns derived from the 2020 mask; C-CAP-located)
         → Colab retrain → re-score forest recall on C-CAP held-out stands. Keep C-CAP train/eval split.

## 2026-07-07  C-CAP acquired (2016+2021) + FIRST non-circular numbers
goal:    get the independent-yardstick raster + produce the first non-circular score (Kam: download
         2016 AND 2021, put on Drive + local like the imagery).
did:     DOWNLOADED NOAA C-CAP hi-res 1m land cover, clipped to Edmonds AOI, EPSG:26910 →
         Full_Image/Pipeline Imagery/ccap_{2016,2021}_hires_lc.tif (+ D: mirror). 2016 = Snohomish
         County bulk .img via /vsicurl windowed range-reads (dodged the 15.7GB .ige spill); 2021 =
         Puget Sound V2 via CCAP_High_Resolution_Landcover ImageServer exportImage (mosaic lockRaster
         OBJECTID 45), tiled 2x1 under the 4100px height cap, mosaicked to the 2016 grid. Hi-res
         legend quirk: forest = single 11 Upland Forest (no 9/10/11 split), developed collapsed
         (2016 all→2 Impervious; 2021 V2 has 2+4) — the baked ccap map absorbs both. Codes verified
         vs the actual rasters.
result:  2016 model vs C-CAP 2016 @thr .4615 = FIRST non-circular score. PRIMARY (forest_wetland)
         recall .684 / precision .865 / grass-rej .935. Per-surface delineation: upland-forest recall
         .682 (UNDER-PREDICTION confirmed independently), forested-WETLAND recall .899 (model recalls
         it WELL — the marsh confusion is EMERGENT/herbaceous wetland, FP-rate .34, NOT forested
         wetland), scrub recall .255 (correctly rejected → validates excluding scrub from primary).
         FP sources: developed .033 (×32% of area) + grass .066; water clean .006. TWO independent
         refs BRACKET the truth: NDVI+CHM .59/.96 (harsher recall) vs C-CAP .68/.87 (harsher
         precision) — report both, never one number.
decided: C-CAP EVAL-ONLY (portability); independent of the model CHM axis → the arbiter for ranking
         CHM-based variants. CAVEAT logged: C-CAP = areal land COVER not a canopy mask (forest =
         ≥5m over >20%, ~1m MMU; street trees → Impervious) → a definitional-disagreement floor in
         both FN and FP; human photo-interp (Olofsson) is the eventual tiebreaker.
fixed:   phase4_qc_indep.py indep-1m-cell count treated EPSG:2285 US-survey-FEET as metres (10.8x
         inflation) → now converts via pyproj CRS unit factor (2016 ≈ 31.3M independent cells).
files:   Full_Image/Pipeline Imagery/ccap_{2016,2021}_hires_lc.tif (+D:); phase4/qc/qc_indep_{report.csv,
         surfaces_2016.csv,2016.txt}; Method_Pipeline.md (+C-CAP subsection); CLAUDE.md (layout+facts+
         script row); phase4_qc_indep.py (unit fix).
next:    RANKING is COLAB-GATED — only edmonds_canopy_prob_2016.tif is on disk; the aux-height/CHM-
         input/RGB-only variant prob rasters were overwritten. Regen each variant (Colab inference) →
         `phase4_qc_indep.py --year 2016 --prob <variant.tif>` → the first non-circular RANKING. 2021
         C-CAP staged for a future 2021/2022 model + as an independent canopy-CHANGE reference.

## 2026-07-07  BUILT phase4_qc_indep.py — reference-agnostic independent scorer (first non-circular yardstick)
goal:    give the model ranking a NON-circular reference. NOAA C-CAP 2016 1m land cover = free
         stand-in for hand-drawn validation polys. C-CAP is EVAL-ONLY (never a train/label source →
         pipeline stays portable to jurisdictions w/ no C-CAP; training = imagery + 2020 labels only).
did:     NEW phase4_qc_indep.py (local, torch-free, mirrors phase4_qc_score.py). reference-AGNOSTIC:
         --ref <raster> + --ref-scheme ccap|binary + --ref-map JSON override. Reprojects ref onto the
         year's prob grid (WarpedVRT nearest = categorical-safe; qc_score assumed same-grid — this is
         the one real diff). Scores 3 NESTED canopy defs (forest_only ⊆ forest_wetland[PRIMARY] ⊆
         forest_wetland_scrub) + a PER-SURFACE breakout: canopy-call rate = RECALL for canopy groups,
         FP-RATE for grass/cropland/developed/barren/emergent_wetland/water → attributes both misses
         AND false alarms by land cover (Kam ask: "evaluate grass + other surfaces too"). --prob
         override scores archived variants. Outputs qc_indep_report.csv + qc_indep_surfaces_{year}.csv
         + qc_indep_{year}.txt (never collide w/ qc_report / semantic_eval / flicker).
decided: primary canopy = forest+forested-wetland (model targets tall canopy, deciduous or coniferous,
         sometimes in wetland — Kam). Score at MODEL grid (mirror qc_score) + report ≈independent-1m-
         cell count so pixel-inflation stays auditable. Default NOAA C-CAP 25-class map baked in +
         PRINTED every run (VERIFY vs shipped legend) + fully overridable via --ref-map.
valid:   VALIDATED against ndvi_ref_2016.tif (--ref-map canopy={2}/grass={1}, ref_nodata 255→ignore) →
         recall .5937 / prec .9593 / grass-rej .9119 / TP 302,167,379 / FN 206,790,325 / full sweep =
         EXACT match to phase4_qc_score.py → reproject+confusion path proven before real C-CAP lands.
files:   Scripts/phase4_qc_indep.py (NEW). plan = cosmic-snacking-goblet.md.
next:    Kam supplies C-CAP raster + legend → run --ref <ccap.tif> --year 2016; confirm printed map vs
         legend; sanity ref_canopy_pct; then --prob each ARCHIVED 2016 variant → the FIRST non-circular
         ranking. (prob_2016.tif is overwritten per run → only variants Kam saved are scorable.)

## 2026-07-07  DECISION (multi-agent review): STOP grass iteration; flicker-gate phase3
goal:    user "hire agents to review" the phase3-base-mirror decision. 4-lens Workflow review.
did:     review verdict (3 of 4 = validate-first; the pro-build lens defers to a cheap probe, not
         the full build). KILLER FACTS: grass = ~2% of error, under-prediction = ~94% (@thr .4615
         FN 206.8M vs FP_grass 4.9M); aux-height made recall WORSE (.626→.594); the +2pp is scored
         at INCONSISTENT thresholds + on a CONTAMINATED proxy (ref IS NDVI∧CHM) → below the noise
         floor. CHM-input's .98 DISQUALIFIED for the temporal deliverable (stale-2016-snapshot =
         error correlated w/ the change signal). single-year grass = WRONG yardstick for a CHANGE
         series (what matters = year-to-year FP STABILITY, never measured).
decided: DON'T build phase3 now. SHIP aux-height v046 (RGB-only, no stale snapshot) as provisional.
         STOP grass iteration (stop rule: <5% of error). gate phase3 behind a cheap FLICKER test;
         redirect to the 94% (under-pred) + the Olofsson yardstick. reopen phase3 only on a PARETO
         win (grass ≥.96 AND recall ≥.626). plan rewritten = drifting-swinging-dolphin.md.
         BUILT phase4_qc_flicker.py (local, torch-free): false-canopy % on known-stable non-tree
         parcels (Negative_* footprints) across years → per-parcel flicker(std) + fine/coarse
         resolution step + verdict (static <3pp = ship/kill-phase3; flicker >5pp = ceiling probe).
         smoke-test 2000+2016 (old masks) OK — but CAVEAT: Cemetery/Stadium footprint bboxes
         include REAL trees (35-58% "FP" = real canopy) → NOT valid stable parcels; clean ones
         (Civic_Field/Parking/Water) ~0-2%. real test needs tight turf-only polygons.
files:   NEW Scripts/phase4_qc_flicker.py (committed). plan drifting-swinging-dolphin.md rewritten.
next:    USER Colab: run RGB-only (--no-hillshade) on 2000,2013,2015,2017,2022 → masks. then local
         phase4_qc_flicker.py (with tight turf parcels). STATIC → ship v046, kill phase3. FLICKER →
         2020 ceiling probe. parallel: Olofsson pilot (other session). phase3 shelved (git v045/v046).

## 2026-07-07  aux-height 2016 result (v046): mechanism WORKS but WEAK (grass-rej +2pp only)
goal:    re-run 2016 --aux-height on v046 (bugs fixed). does the height head close the grass gap?
did:     training STABLE now (RGB dtype fix held; no divergence; val_iou_bt .7176), eval ran (tuple
         fix held), full pipeline + qc clean. reused the aux tiles (height sidecars from the crashed
         run; sig match). RESULT vs NDVI @thr .4615: RGB-only+aux-height rec .594 / prec .959 /
         GRASS-REJECTION .912. vs baseline (RGB-only no height) .626/.952/.891. So the head lifted
         grass-rejection +2.1pp (right direction, mechanism confirmed) but far short of the CHM-
         INPUT .98; recall -3pp (slightly more conservative).
decided: aux-height WORKS but WEAK in this test — expected, because this is the no-base-pretraining
         version and 2016 is coarse 50cm (RGB→height hard). the head learned height only from 2016's
         own tiles. the DECISIVE test is the phase3 base mirror: pretrain the height head on 7.5cm
         2020 imagery (a strong, high-res RGB→height signal) so every year inherits a height-aware
         encoder. CAVEAT: RGB-predicted height is inherently lossy, so the ceiling MAY sit below
         CHM-input's .98 — +2pp is a hint the ceiling could be modest. Also untested: --height-lambda
         higher (stronger shaping, risks recall/stability).
files:   run_registry.csv +1 row. no script change (v046 stays live).
next:    DECISION for user: build phase3 base mirror (the real test) vs the modest +2pp says the
         RGB-only-height ceiling may be low → reconsider (e.g. keep CHM-input for grass + fix
         corrected-label grass via two-sided negatives). recommend: do phase3 (it's the honest test
         of the reframe; mechanism already moves the needle).

## 2026-07-06  aux-height 2016 ablation: baseline OK, aux run CRASHED → v046 2 bugfixes
goal:    run the 2016 aux-height ablation (RGB-only baseline vs --aux-height). read logs.
did:     BASELINE (--no-hillshade, RGB-only, no height, no CHM) ran clean: train val_iou_bt .7179,
         eval IoU .758; HONEST qc vs NDVI: rec .626 / prec .952 / GRASS-REJECTION .891. So the
         pure-RGB floor is grass-rej .891 (vs CHM-input .98) — the head must close ~9pp.
         --aux-height arm: tiling OK ("+ aux-height sidecars: ON", height sidecars written), BUT
         TRAINING DIVERGED (Phase A val_iou .56→.05, val_bce spiking; Phase B val_bce 8-10; early
         stop; ckpt frozen at undertrained E8) THEN step_evaluate CRASHED: AttributeError 'tuple'
         object has no attribute 'squeeze'. qc at end = stale baseline raster (aux never inferred).
         ROOT CAUSE (2 of MY bugs): (1) __getitem__ AUX path np.concatenate([uint8 rgb, float32
         height]) UPCASTS rgb→float32; pixel_tf colour augs (HSV/brightness) assume uint8 → garbage
         RGB → divergence. (2) step_evaluate has a 4TH forward site (reads eval_df directly, not via
         loader) I missed → model(inp) returns (seg,height) tuple → .squeeze() fails.
decided: FIX v046: (1) cast stacked[...,:3].astype(uint8) before pixel_tf; (2) tuple-unpack seg in
         step_evaluate. py_compiled. training collapse expected to resolve once RGB uncorrupted;
         if it still destabilizes, lower --height-lambda or add a head activation.
files:   phase4_semantic_finetune.py v045→v046 (commit+tag v046). run_registry.csv +2 rows
         (baseline, crashed aux).
next:    USER Colab RE-RUN 2016 --aux-height on v046 → evaluate + qc_score. success = grass
         rejection lifts from the .891 RGB floor toward ~.98 with recall/precision held. then
         phase3 base mirror. keep one session editing phase4 at a time.

## 2026-07-06  aux-height reframe CODED in phase4 (v045) — teach height, don't feed it
goal:    implement the approved plan (drifting-swinging-dolphin.md): height as an auxiliary
         SUPERVISION TARGET (RGB-only inference), not a 4th input channel — the structural fix
         for recurring grass FPs. Planned + coded HERE (2 Explore agents mapped both files).
did:     phase4 v045, flag-gated (--aux-height default OFF = bit-identical to v044). UnetWithHeight
         (subclass smp.Unet → keeps encoder/decoder/segmentation_head keys, adds height_head
         Conv2d(64,1); forward→(seg,height)). RGB-only input forced (USE_HILLSHADE off, IN_CH=3).
         Height target = per-tile CHM-DN sidecar via read_hillshade_chip, written only for
         CHM_CREDIBLE_YEARS {2015,2016,2017,2020}; _height_to_target normalizes (DN-1)*.2/40 w/
         -1 invalid sentinel; _masked_l1 (loss zero where no sidecar). Wired all touch points:
         build_model, 3 forward sites (tuple-safe isinstance unpack), __getitem__ (height rides
         spatial_tf as 4th channel then split before colour aug), train/val loop unpack,
         _tile_signature (aux_height key → forces retile), _save_ckpt (aux_height_head).
         py_compiled clean at each step.
decided: KEY realization — sem_best_2020.pt is already 3-ch RGB (phase3 never used CHM input),
         so phase4 --aux-height fine-tunes load it cleanly (strict=False, height_head random) and
         the height head trains DURING the 2016 fine-tune. So the decisive 2016 ablation (RGB-only
         with vs without --aux-height) runs NOW without touching phase3. phase3 base-pretraining
         (stronger prior + transfer to non-NIR yrs) = the remaining step.
files:   phase4_semantic_finetune.py v044→v045 (.versions v045). phase3 versioned v002 but NOT
         yet edited (mirror pending).
next:    (a) USER Colab 2016 ablation: fine-tune 2016 twice from the current base — RGB-only
         plain vs --aux-height — evaluate + qc_score each; success = grass rejection back to
         ~.98 with precision held, WITHOUT corrected labels. (b) then mirror into phase3 (base
         height head) for full transfer. Coordinate: one session edits phase4 at a time.

## 2026-07-06  git adopted — version_script retired, full snapshot history imported
goal:    replace homegrown .versions/ snapshots w/ real local git. private, NO remote.
did:     repo LIVE. working tree = G:\My Drive\treedata (edit-in-place unchanged), git DB =
         D:\edmonds-pipeline\treedata.git (--separate-git-dir → off FUSE mount, immune to
         Drive-sync corruption; only tiny .git pointer file on Drive). whitelist .gitignore:
         code+docs+2 xlsx only, 96 tracked files, git status 0.08s, zero data files. all 62
         .versions snapshots replayed as backdated commits (2026-06-22→) + tags v001–v044.
         OFF-BY-ONE handled: version_script saved PRE-edit → tag vN paired w/ snapshot
         v(N+1) content. verified byte-exact (v039 blob == snap v040) + rollback drill passed.
         CLAUDE.md rules 1+9 + drive layout rewritten for git flow.
decided: .versions/ FROZEN on disk as git-ignored archive (not deleted); version_script.py
         retired. git ops from local Windows ONLY, never Colab. Plainly, for safety: pause
         Google Drive sync before any command that rewrites working files (restore, checkout,
         reset --hard, stash pop); plain commits/status/log are safe anytime.
killed:  clean-start-no-import — user wanted pre-git history carried over.
         caveat: replayed history = snapshotted edits only; docs + never-snapshotted scripts
         enter history at the 2026-07-06 "current state" commit.
files:   .gitignore .gitattributes  D:\edmonds-pipeline\treedata.git  plan=local-git-setup.md
         run_registry.csv (backfilled v039–v044)  sentinel_sites.json (12 windows)
         phase4_sentinel_snap.py (+--filmstrip)  phase4/runs/{run_id}/sentinels/
did+:    Part B landed same session. sentinel backfill v039 vs v044 marsh filmstrip WORKS:
         marsh 41.9→56.4% canopy (recall recovery VISIBLE); grass negs light up v044
         (cemetery 54→75%, stadium 57→67%) = grass-guard regression VISIBLE. forest_2
         outside 2016 imagery extent (skipped). v039 backfill forest_3 0.0% — old D: mirror
         mask likely coverage gap there, backfill artifact only.
gotcha:  stray EMPTY C:\content\drive\MyDrive\treedata dir on local machine fools the
         _COLAB_BASE.exists() check in pipeline scripts run locally (qc_site etc.) —
         sentinel_snap now checks (_COLAB_BASE/"Scripts").exists(). Delete C:\content
         manually to fix for all scripts (sandbox blocked removal).
next:    per-run flow live: after each Colab run → registry row + sentinel snap + filmstrip.

## 2026-07-06  CORRECTED-LABEL RESULT: recall .60→.85, but grass-rejection guard tripped
goal:    full 2016 run (v044, fresh runtime) → honest qc_score vs NDVI. did the corrected
         labels lift recall without wrecking precision?
did:     ran clean end-to-end (v044 OOM fix WORKED: inference 21,501 tiles in 13:52 @25.8
         tile/s, no OOM; A100-80GB this time). tiles REUSED (corrected, v043 sig match), train
         val_iou_bt .8820, prob raster 587MB, 33,369 canopy polys. HONEST qc_score vs NDVI+CHM
         @thr .4615: recall .605→.848 (+24pp!), precision .970→.925, GRASS-REJECTION .981→.842
         (-14pp — GUARD TRIPPED), model canopy 23.5→34.6% (ref 37.7; gap +14.2→+3.1pp), F1
         .745→.885. threshold sweep: precision .90-.93 across .20-.50 → grass NOT threshold-
         fixable, it's in the labels. FN 77.5M, FP_grass 8.8M, FP_nonveg 26.4M.
decided: recall win is real + large, but grass-FP regression = the exact thing CHM was added
         to fix, partially back. TWO open concerns: (a) grass guard tripped; (b) CIRCULARITY —
         labels built from NDVI+CHM, recall scored vs NDVI+CHM → recall .85 partly circular
         (we spent the yardstick). Fable's lean: one tightening pass (additions .35/4m + re-
         emphasize grass negs) to recover grass while holding recall. LAUNCHED multi-agent
         review (4 lenses: measurement-integrity / canopy-domain / ml-methodology / decision-
         pragmatics + synthesis) for perspective before deciding.
files:   phase4/qc/qc_report.csv + qc_score_2016.txt (the result); sem_best_2016.pt,
         edmonds_canopy_{prob,mask}_2016.tif (corrected). semantic_eval_report.csv (circular
         IoU .82 — INFLATED, test tiles carry corrected labels; ignore for lift).
next:    read multi-agent synthesis → decide accept / tighten / build-photo-interp-first /
         supervision-reframe. likely: photo-interp is the only non-circular arbiter (2000
         especially). precision guard on grass is the live blocker.

## 2026-07-06  corrected labels APPLIED (v043) but inference OOM'd → v044 hardening
goal:    user re-ran 2016 --add-canopy-mask (v043, single-line cmd). read the log.
did:     CONFIRMED corrected labels applied: "+ corrected-label overlay (ADD-ONLY)", full
         retile (20,910 scan, 566/800 canopy tiles vs old 685 reuse). train HEALTHY, val_iou_bt
         .8829 (up from .73). BUT: (1) circular eval IoU .82 / AUROC .983 is INFLATED — the
         held-out test tiles now carry the corrected labels, so it's not comparable to the old
         .77; the honest test is qc_score vs NDVI. (2) INFERENCE OOM'd: batch=160 (args.batch*16)
         at 512² = ~34GB, + ~5GB left from train/eval in the same process > 40GB A100. crashed
         at tile 159 in flush; also 28s/tile = near-OOM thrash. prob raster left empty → the
         end-of-run qc_score got 0 valid px (all nan) → NO honest number yet, and it clobbered
         the prior good prob raster.
         FIX v044: gc.collect()+torch.cuda.empty_cache() after model.eval() in step_inference
         (frees train mem); _forward() OOM-resilient — on "out of memory" halves the batch and
         retries recursively (version-agnostic: catches RuntimeError w/ "out of memory").
decided: don't trust the circular eval for corrected-label lift; need a COMPLETED inference →
         qc_score. re-run inference-only in a fresh runtime (cleanest) — model sem_best_2016.pt
         is saved; --add-canopy-mask NOT needed for inference (labels irrelevant at inference).
files:   phase4_semantic_finetune.py v043→v044 (.versions v044; py_compiled).
next:    USER fresh runtime: --step inference → --step postproc → phase4_qc_score.py --year 2016.
         v044 auto-recovers from OOM; --batch-size 64 optional for headroom. THAT qc_score
         (recall vs NDVI, from .60) + precision guard is the real corrected-label result.

## 2026-07-06  v042 corrected-label run REUSED stale tiles → v043 tile-signature fix
goal:    user ran 2016 --add-canopy-mask on Colab. read the log.
did:     CAUGHT: Step 2 "REUSED 685 existing tiles (sampling signature unchanged)" → overlay
         NEVER applied (baked at tile time; no "+ corrected-label overlay" print). eval ≈ the
         pre-correction v039 baseline (IoU .7695 vs .7725, AUROC .936 vs .938, Rec .922 vs
         .927) = same tiles retrained, corrected labels absent. ROOT CAUSE: v035 _tile_
         signature omits ADD_CANOPY_MASK → adding --add-canopy-mask didn't invalidate the
         cache. FIX v043: _add_canopy_mask_sig() (path+size+mtime) added to the signature,
         only when the overlay is set (no spurious retile for other years). training itself
         HEALTHY (val_iou_bt .7362, Phase B improved, no collapse — v039 config holds).
decided: the circular held-out eval (IoU .77) is NOT the corrected-label test — recall vs the
         2016 NDVI reference (phase4_qc_score.py) is. re-run needed.
files:   phase4_semantic_finetune.py v042→v043 (.versions v043; py_compiled).
next:    USER Colab (v043 synced): --year 2016 --step tile train evaluate inference postproc
         --add-canopy-mask <canopy_additions_2016.tif> (auto-retiles now; watch for the
         "+ corrected-label overlay (ADD-ONLY)" print + canopy_frac rising). THEN
         phase4_qc_score.py --year 2016 → honest recall vs NDVI; PRECISION GUARD.

## 2026-07-06  centralize sources of truth — retire handoffs, add README front door
goal:    ~7 overlapping state docs drifted + contradicted (buildtracker said phase3 "not
         started"; two workplans had phase4/5 SWAPPED; 5 handoffs multiplying). one home per
         kind of info + anti-drift rules. plan = centralize-sources-of-truth.md.
did:     ARCHIVED (moved, not deleted → Scripts/_archive/): 5 HANDOFF_*.md → _archive/handoffs/;
         Admin/Tree Project Work Plan.xlsx (old phase4=instance scheme) + the dated workplan
         backup. superseded Edmonds plan files (enchanted-orbiting-lecun, synchronous-hatching-
         kahan, velvety-meandering-diffie, drifting-*-agent-*) → plans/_archive/. NEW
         treedata/README.md = single front door + doc-map table (one home per kind).
         _archive/README.md warns "not current". CLAUDE.md: dropped the HANDOFF read-dep +
         Authoritative-References table → points to README; added one-fact-one-home rule +
         session-end checklist (edit STATE in place + 1 LOG entry, NO new handoff). trimmed
         auto-memory to pointer. earlier this session: rewrote pipeline_buildtracker.md (cruft
         removed + current), updated canonical workplan (phase3 complete, phase4 = actual
         LiDAR/CHM method), published ops-guide artifact.
decided: HANDOFFS RETIRED (user pick) — STATE + active plan cover the narrative. AI memory
         stores in scope: auto-memory trimmed; Claude.ai project memory → user pastes trimmed
         pointer text (Claude can't edit web UI). canonical workplan = edmonds_combined_
         workplan.xlsx (NOT the Admin one).
files:   NEW treedata/README.md, Scripts/_archive/README.md. Scripts/_archive/{handoffs/*,
         old workplan+backup}. plans/_archive/*. edited CLAUDE.md, CHATLOG (this),
         pipeline_buildtracker.md, edmonds_combined_workplan.xlsx.
next:    USER: paste the trimmed Claude.ai project-memory text (drafted in chat). optional:
         git init + lit-tracker gaps (Olofsson/canopy-height/eval papers) — separate tasks.
         then back to the Colab corrected-label retrain (open item 0).

## 2026-07-05  corrected labels from NIR+CHM — invert QC to LABEL the misses (v042)
goal:    user reframe: we have 2020 labels + a CHM yet still miss the deciduous marsh. use
         2016 NIR+CHM (the honest QC signal) to LABEL missed canopy, not just measure it. no
         cross-year map substitution. planning session → approved plan drifting-swinging-
         dolphin.md.
did:     root-cause (2 Explore agents + read): under-pred = (1) labels teach CONIFER only —
         fine yrs = 5 conifer sites, coarse = citywide 2020 mask which is itself the phase3
         PREDICTION (same blind spot), marsh labeled but rare; (2) CHM = 1 soft input outvoted
         by 3 RGB + HS_DROPOUT .25 → tall doesn't rescue a confident RGB reject; (3) every
         recent fix pushed PRECISION (grass negs / CHM / hi op-thresh) → recall was the bill.
         .97 prec / .60 recall = tuned-conservative, NOT broken.
         BUILT Scripts/phase4_build_corrected_labels.py (local, torch-free): reads 2016 RGBI
         band4 + CHM (WarpedVRT) → canopy_additions_2016.tif on the 2016 grid (0 nochange /
         1 ADD canopy / 2 IGNORE / 255 nodata). ADD = NDVI>=.3 AND height>=3m (TIGHTER than
         QC .2/2m to protect precision); IGNORE = green & 2-3m; ADD-ONLY (never canopy→bg);
         --holdout-frac carves an uncorrected strip for honest scoring. ran 2016: 31.97% of
         imaged strip = hiconf canopy, IGNORE 1.25%. marsh preview: green traces forest +
         street/yard trees + the tall marsh stand, roads+roofs punched out (NDVI gate) →
         mechanism correct; green extensive in suburb → watch precision.
         WIRED v042 --add-canopy-mask: additions_from_mask (reproject onto crop, mirrors
         canopy_label_from_2020_mask) + apply_additions (1→1, 2→255 unless 1), applied in
         _gather_citywide_coarse after the 2020-mask label, before nod-ignore. one file
         (2016 grid) serves 2016 AND 2000 (reproject; outside 2016 strip → plain 2020 mask).
decided: label-augmentation FIRST — low risk, keeps the working architecture — over the
         supervision-head reframe (aux NDVI+height targets, RGB-only inference), which stays a
         later option if the recall gap persists. true cross-year NIR transfer needs an
         NIR-aware SHARED BASE (2020 has no NIR); deferred with the supervision reframe.
killed:  2015-flagship-stands-in-for-2016 substitution (user: no other years supporting other
         years). marsh positive site (2020-mask-derived) superseded by NIR+CHM-derived labels
         (independent → catch exactly what the 2020 mask missed).
files:   NEW Scripts/phase4_build_corrected_labels.py (py_compiled). phase4_semantic_finetune
         v041→v042 (.versions v042; py_compiled). phase4/labels_corrected/canopy_additions_
         2016.tif(+.txt), phase4/eval/corrected_labels_preview_2016.png, logs/. plans:
         drifting-swinging-dolphin.md (active); enchanted-orbiting-lecun.md (prior).
next:    USER Colab: --year 2016 --step tile --add-canopy-mask <path> → train --hs-source chm
         → inference postproc evaluate → phase4_qc_score.py vs 2016 NDVI. PRECISION GUARD:
         grass-reject ~.98 + precision-vs-NDVI not down, else tighten (.35/4m) or reject. then
         2000 same overlay (--year 2000, same file). pick measurement: --holdout-frac strip
         vs photo-interp harness (open item 2).

## 2026-07-05  honest recall instrument (NDVI+CHM) → 2016 recall .60 not .94; thresh NOT the lever
goal:    build model-independent recall reference. user: precision good, model UNDER-predicts
         2000/2016. measure honestly (2020 labels circular). auto mode.
did:     2016 has OWN nir band (band4 confirmed B4 119.7 >> R 73.2). NEW phase4_qc_ndvi.py:
         NDVI=(NIR-R)/(NIR+R), canopy ref = NDVI>=.2 AND CHM height>=2m (grass EXCLUDED via
         CHM). 2016 prob raster SAME grid as 2016 imagery (EPSG:2285 43893x31965) → zero-
         reproject scoring. ref = 37.7% of imaged strip is canopy (matches known ~40% prior →
         ref calibrated not inflated; grass only 4.1%). NEW phase4_qc_score.py (torch-free,
         reads op-thresh from eval CSV): 2016 @thr .3767 → HONEST recall .6049 (circular 2020
         recall was .94!), precision-vs-NDVI .970, grass-reject .981. model canopy 23.5% vs
         ref 37.7% = +14.2pp UNDER-pred, FN=201M px. THRESHOLD SWEEP recall .20→.631 /
         .50→.578 = lowering thresh barely helps (+2.6pp for big drop).
decided: 2016 under-pred is STRUCTURAL (OOD/deciduous canopy), NOT threshold — sweep refutes
         threshold-tuning as the 2016 fix. confirms plan levers: 2015 full-city coverage +
         deciduous training coverage. QC instrument = the measuring stick now. PRINCIPLE
         (user): lidar INFORMS older years, never a hard veto (stale-CHM suppression = the
         2000 driver).
         A3 MARSH diagnostic (NEW phase4_qc_site.py, lat/lon window + FN cross-tab):
         2016 marsh recall .696, precision .978. MISSED-canopy = TALL+GREEN: 60.2% of FN
         px >5m tall, mean NDVI .47-.51 across ALL height bins → real trees model
         confidently rejects = OOD/DECIDUOUS, not ref noise / not threshold / not coverage
         (marsh inside strip, CHM matched+tall). 2000 marsh (prob-only, 2016-CHM proxy):
         59.6% of tall px not called canopy @thr .513 (mixes OOD + RGB drift + real change).
decided: 2016 marsh miss = deciduous OOD → fix = deciduous TRAINING coverage (plan B2), NOT
         threshold/coverage/CHM. 2000 muddier (temporal) → needs photo-interp instrument.
files:   NEW Scripts/phase4_qc_ndvi.py, phase4_qc_score.py, phase4_qc_site.py (py_compiled).
         phase4/qc/ndvi_ref_2016.tif(+txt), qc_report.csv, qc_score_2016.txt,
         sites/marsh_{2016,2000}.{png,txt}. logs/ written. plan enchanted-orbiting-lecun.md.
next:    2019n/2022n NDVI refs (full-city recall on recent yrs). Phase B = 2015 flagship run
         (Colab) scored vs 2016 NDVI. Phase B2 = cut marsh-deciduous training site. Phase D
         = photo-interp harness for 2000.

## 2026-07-05  marsh deciduous positive site STAGED (labels from 2020 mask) + QC artifact
goal:    act on QC finding — deciduous OOD miss. cut marsh positive training site. auto mode.
did:     MECHANISM audit (agent): positive site is NOT drop-in — no crown file → code DEMOTES
         to negative & burns real canopy as bg (harmful). 2016=COARSE → trains on citywide
         2020 mask (marsh labeled but rare), curated positives IGNORED. 2015=FINE → per-site
         crown polys (only conifer Forest_* → marsh absent). ⇒ marsh site helps FINE years
         incl 2015 flagship (the ~2016 stand-in). NEW make_positive_site.py: DERIVES crown
         polys by polygonizing phase3 2020 mask inside footprint (schema matches Forest_*_
         crowns_review.gpkg: EPSG:3857, status=approved, valid_from/to). SAFE staged→--commit
         flow (mirrors make_grass_negatives). STAGED Positive_Marsh: 700m box @-122.3837
         47.8027, 333 crowns 19.8ha from 2015 imagery. preview verified: outlines match real
         canopy (deciduous+conifer), avoid houses/roads. 2015 imagery is LEAF-OFF → deciduous
         read brown = 2nd miss mechanism (phenology, not just species). NOT committed.
         Also QC ARTIFACT published (honest recall .60 vs .94, thresh-sweep, marsh attribution).
decided: marsh labels auto-derived from 2020 mask (anchor GT; trees stable 2015-2020) not
         hand-traced. commit + retrain GATED on user preview review. 2016-coarse deciduous
         handled via 2015-flagship substitution, not curated positive (coarse ignores them).
files:   NEW Scripts/make_positive_site.py (py_compiled). photos/_positive_staging/
         Positive_Marsh_rgb.tif, polygons/_positive_staging/Positive_Marsh_crowns_review.gpkg,
         phase4/eval/positive_site_preview_Positive_Marsh.png. artifact cd2a1bbd.
next:    USER review preview → make_positive_site.py --commit → Colab: 2015 --step labels→tile
         →train→inference→postproc→evaluate → phase4_qc_score vs 2016 NDVI (recall lift?).
         local todo: phase4_qc_photointerp.py (2000 Olofsson), Method_Pipeline QC section.

## 2026-07-05  under-pred diagnosis → 3 causes; v041 --infer-thresh; multi-yr plan
goal:    user: 2000/2016 "miss large tree patches". find why, plan fix. mind tokens.
did:     read-only diag (prob rasters + NDVI/CHM cross-tab, LOCAL rasterio, no Colab).
         2016 NOT broken: tall+green (CHM≥126,NDVI>.3) 97% detected mean-prob .73;
         grass (green,CHM≤1) 99.5% REJECTED = CHM doing its job. under-pred = 3
         SEPARATE causes: (1) 2000 op-thresh .513 too high (2016=.377); (2) stale
         2016 CHM SUPPRESSES canopy changed since 2016 — user 2 pts: P2 forest
         (122.3208W 47.8305N) OUTSIDE 2016 extent, on 2000 median-prob .323 just
         under .513 + CHM reads short→suppressed; P1 marsh (122.3837W 47.8027N) 2016
         75% / 2000 41% despite CHM=98 → RGB radiometric DRIFT not thresh; (3) off-yr
         RGB domain shift. 2000 thresh sweep: .513→P2 39%, .30→59%, .20→66%; city
         +5.5pp canopy @.30, green-precision ~flat (weak GRVI proxy). DATA INVENTORY:
         snoh 2016/21 NIR = NARROW mid-strip ONLY (why P2 uncov); NAIP 2019/22 =
         only FULL-CITY NIR (independent veg ref); ~285GB total.
decided: user picked THRESHOLD-ONLY interim (Phase 2 CHM de-weight/height-as-target
         DEFERRED). plan = 6 phases (copy imagery→NAIP-NDVI ref→[CHM deferred]→
         radiometric+TTA-BN→honest thresh→Olofsson). imagery Tier1+2 (~100GB) →
         D:\edmonds-pipeline\Imagery (robocopy bg, no COE/upsampled).
killed:  retrain-to-lift-recall (re-adds grass FP); blunt global thresh-lower is
         risky (grass) but user chose as interim.
files:   phase4_semantic_finetune.py v040→v041 (+--infer-thresh override in
         _operating_threshold + argparse + global; py_compile OK). plan
         velvety-meandering-diffie.md. D: imagery copy + tasks #1-6.
next:    USER Colab: --year 2000 --step postproc --infer-thresh 0.30 → phase4_viz
         --year 2000; confirm P2/marsh recovery + grass didn't balloon. then Phase 1
         NAIP-NDVI honest ref (the real deliverable path).

## 2026-07-05  v039 VALIDATED — 2016 chm BEATS rgb baseline on held-out test
goal:    validate v039 Round-1 fixes on 2016.
did:     diagnostic (8ep phaseA): val_iou climbed smooth to .72, NO cliff, op-
         threshold pinned 0.5 (val_iou@.5 == iou_bt) = properly calibrated. full
         run: Phase A → .7294, Phase B RESUMED from best (Fix 3 confirmed print
         "resumed from best Phase-A checkpoint") + IMPROVED to .7385 (was a no-op
         before). eval on held-out TEST: IoU .7725 / Dice .872 / AUROC .938 / AP
         .883 / Prec .823 / Rec .927, op-thresh .377. BEATS rgb baseline
         .7245/.929/.856/.773/.921 on EVERY metric. recall recovered .58→.93,
         precision UP .773→.823 (= grass-FP reduction signal). log lines confirmed
         sampler "natural/shuffle", pos_weight DISABLED, BN pinned 104 layers.
decided: root cause = sampler (verified). CHM channel HELPS once sampler honest —
         reverses the "chm makes it worse" conclusion entirely. 2016 validated.
files:   semantic_eval_report.csv rgb+chm row now .938 AUROC; sem_best_2016.pt.
next:    phase4_viz.py --year 2016 grass-FP confirm (need inference+postproc first
         — also exercises v040 vectorized polygonize). then carry EXACT config to
         2000 (temporal drift). then PIVOT to Phase 4 validation rebuild (Olofsson
         reference set) = the real deliverable.

## 2026-07-05  research (4 agents) + code audit → real root cause + v039 Round 1
goal:    "this is ridiculous, use superpowers": lit review + code audit to find
         how this is done + fix.
did:     4 parallel agents (RGB+CHM fusion / imbalance+calibration / temporal+
         validation / codebase audit). AUDIT FOUND THE BUG: sampler weights
         1/count[SITE] → in citywide-coarse the one "city" site (all canopy) and
         each tiny pure-neg site get EQUAL mass → ~83% background batches. verified
         :2418. this (not pool/chm/dice/BN) is the real recall-crash / low-AUROC
         cause; explains v029(no neg sites=sampler no-op, stable) vs v030(neg sites
         →bug active). LIT: (a) height belongs in SUPERVISION not input — Meta/WRI
         Tolan, Cal/Amazon U-Nets, DeepForest all RGB-in height-target, RGB-only
         inference (dissolves 2016-only temporal mismatch); (b) neg-heavy sampling
         = textbook train/test PRIOR SHIFT (Kang decoupling ICLR20) — undertrained
         .89 > trained .78 is the signature; fix balance in LOSS not prior, select
         on AP not IoU@.5 (Metrics Reloaded); (c) circular 2020-mask labels =
         credibility killer; need Olofsson-2014 stratified photo-interp + area-
         adjusted CIs; radiometric normalization + test-time BN across years.
decided: user goal = DEFENSIBLE CHANGE SERIES → Phase 4 (validation rebuild) is
         the true priority; Round 1 = Phases 1+2 (v039, above). CHM redesign
         (height-as-target) deferred. plan file written.
files:   phase4_semantic_finetune.py v038→v039 (8 fixes, .versions snapshotted).
next:    USER validate v039 on 2016 (tiles cached, train-only, --freeze-encoder-bn
         now default): diagnostic --epochs-phase-a 8 --epochs-phase-b 0 then full
         run + --step evaluate. WANT: op-thresh near ~0.5, recall recovered ~.85+,
         AUROC/AP toward rgb .929/.856, Phase B improving. then 2000. then pivot
         to Phase 4 validation rebuild.

## 2026-07-05  v038 validation: metric fix WORKS but chm model underperforms
                (pool overfit suspected)
goal:    full 2016 run w/ v038 (val_iou_bt select) + --freeze-encoder-bn, eval.
did:     TRAINING STABLE — no false cliff. Phase A iou_bt climbed .51→.638 (best
         E18, ckpt NOT frozen). BUT Phase B added nothing (best B-E1 .6389, drift
         + early-stop E16). eval on sem_best_2016.pt (best_val .6389 = new ckpt,
         confirmed via file mtime 9:10 + history CSV w/ iou_bt cols): TEST AUROC
         .7835 / best_f1 .811 @ thr .241 / AP .6017. (iou/recall cols ~0 = 0.5-vs-
         0.2 thresh mismatch, ignore.) verified NOT stale: CSV mtime 9:20 = eval
         time, tp/fp integer counts = fresh compute.
decided: metric-artifact diagnosis CONFIRMED + fixed (stable training, honest
         ckpt). BUT honest chm eval UNDERPERFORMS: AUROC .784 << rgb .929 / struct
         .928. KEY overfitting signal: undertrained E5 (handoff .894) > fully-
         trained (.784) → MORE training = WORSE test. prime suspect = aggressive
         neg-heavy/canopy-scarce POOL (raw pw 1.50 old→2.99 now; canopy px 40%→
         25%), confounded w/ channel (struct/rgb anchors were OLD pool).
files:   phase4_semantic_finetune.py v038 (unchanged); semantic_eval_report.csv
         rgb+chm row = AUROC .784.
next:    USER disambiguate channel-vs-pool (no retile): RGB-equiv on CURRENT pool
         = --hs-dropout 1.0 --freeze-encoder-bn, then evaluate. ~.78 ⇒ POOL is
         culprit (retile toward v029 composition, re-add chm). ~.90 ⇒ CHANNEL
         hurts. THEN decide grass-FP tradeoff / 2000.

## 2026-07-05  ROOT CAUSE FOUND: not a collapse, a metric artifact (v038 fix)
goal:    run F = v037 best-threshold-IoU diagnostic, settle calibration-vs-
         degradation.
did:     DEFINITIVE. E5 iou@.5=.590 iou_bt=.590@0.5. E6 iou@.5=.454 iou_bt=.510@
         0.4. E7 iou@.5=.0036 (false "collapse") but iou_bt=.581@0.4. E8 iou@.5=
         .020 iou_bt=.580@0.3. best threshold DRIFTS DOWN 0.5→0.4→0.4→0.3 while
         iou_bt HOLDS ~.58. model NEVER degraded — prob scale slid below 0.5
         (BCE calibrates to low base rate on canopy-scarce pool w/ clamped
         pos_weight). the whole 5-run "collapse" saga = val_iou@0.5 (coarse
         select metric) misreading the drift + freezing ckpt at undertrained
         epoch. explains EVERYTHING: fixed epoch, loss-invariance, tr_bce↓,
         val_bce bounded, E5-eval AUROC .89.
decided: ROOT FIX v038 = TIER_EARLYSTOP['coarse'] val_iou→val_iou_bt (best-thresh
         IoU; == val_iou@0.5 when 0.5 optimal, robust when not). inference already
         best_f1 → train+deploy agree. keep --freeze-encoder-bn (helps Phase-A
         floor, standard practice). es_maximize/es_val handle val_iou_bt.
killed:  ALL training-stability hypotheses (class-bal/chm/dice/BN/LR) — there was
         no training bug. the metric was lying.
files:   phase4_semantic_finetune.py v037→v038 (.versions snapshotted).
next:    USER validation run (full, ~15-20min, tiles cached): --step train
         --freeze-encoder-bn. WANT: best_val (now iou_bt) climbs, Phase B improves
         past ~.58 toward rgb .72, no false cliff. then --step evaluate → compare
         IoU/recall/AUROC vs rgb .7245/.921/.9293. then grass-FP + 2000.

## 2026-07-05  run E: BN freeze changed shape but val_iou@.5 still cliffs →
                reframe: likely CALIBRATION artifact not collapse
goal:    run E = --freeze-encoder-bn fast diag, test BN-drift fix.
did:     BN pinned (104 layers). E1-E5 climbed to val_iou .5605 (E5, healthier
         floor, E1 .50 vs prior .34). E6 DIFFERENT: val_bce SPIKED 2.34 (prior
         cliffs stayed bounded ~.7) then E7/E8 val_bce RECOVERED to .72/.67 — but
         val_iou@.5 stayed ~.005-.015. KEY: E8 val_bce .6711 < E5 .6941, tr_bce
         monotonic ↓1.13→.89 — model BETTER by BCE at E8 than E5, yet val_iou@.5
         near 0. ⇒ NOT collapse — prob scale drifted below .5 threshold; model
         still discriminates (E5 eval AUROC .89). "collapse" likely a MEASUREMENT
         artifact: val_iou@.5 is threshold-sensitive + coarse early-stops/selects
         on it → freezes ckpt at undertrained E5 while model trains fine under.
decided: BN freeze NOT the full fix but improved early dynamics (keep it, cheap).
         BEFORE changing fix direction, PROVE calibration-vs-degradation: v037
         adds per-epoch best-threshold IoU (sweep .1-.8, same per-batch-mean as
         val_iou@.5) → iou_bt@thr logged every epoch. if iou_bt HOLDS through
         E6-E8 while iou@.5 cliffs = calibration (fix = selection metric +
         operating thresh, model ~fine). if iou_bt ALSO cliffs = real degrade
         (fix = LR/conv1). early-stop UNCHANGED (pure measurement, single var).
files:   phase4_semantic_finetune.py v036→v037 (.versions snapshotted).
next:    USER run F (fast, ~4min): --step train --freeze-encoder-bn
         --epochs-phase-a 8 --epochs-phase-b 0. READ iou_bt@thr E5→E8. holds ⇒
         calibration confirmed. drops ⇒ real. decides entire fix direction.

## 2026-07-05  run D: DICE exonerated → BN-drift is the cliff (v036 fix)
goal:    run D = pure BCE (dice 0) fast diag (8ep phase A, no phase B), isolate
         dice. idempotent tiling REUSED 685 tiles (worked — no re-tile).
did:     run D STILL CLIFFED: peak val_iou .5197 E5 → .0234 E6 → .0011 E7, pure
         BCE (BCE 1.0 DICE 0.0). dice EXONERATED. cliff now invariant to: channel
         (A), pos_weight (B), pool (C), loss composition (D) — always E5→E6 at
         constant LR. ⇒ NOT loss — a TRAINING-DYNAMICS drift that tips at fixed
         epoch. root cause found in code: _freeze_encoder sets requires_grad=False
         but model.train() (every epoch) flips frozen-encoder BN back to TRAIN
         mode → BN tracks batch stats. trainable input-conv shifts input +
         canopy-scarce/neg-heavy pool (24 water tiles!) → batch stats far from
         2020 → encoder BN running stats DRIFT → frozen deeper weights get OOD
         normalized features → eval collapse at fixed epoch. explains ALL: fixed
         E6, loss-invariant, tr_bce fine (train=batch stats), val_bce bounded,
         only val_iou@.5 cliffs. ALSO explains v029/struct stability (that pool
         ~ 2020 → BN barely drifts).
decided: v036 --freeze-encoder-bn: _set_encoder_bn_eval pins encoder BN to
         pretrained running stats, re-applied after each model.train(); decoder
         BN stays trainable. standard transfer-learning practice. def OFF (single-
         variable test). NOT lowering LR (would only delay) or freezing conv1
         (kills 4th-channel learning) — BN freeze fixes cause w/o those tradeoffs.
killed:  dice-term-is-the-cause (run D pure BCE refutes).
files:   phase4_semantic_finetune.py v035→v036 (.versions snapshotted).
next:    USER run E (fast, train-only, ~4min): --step train --freeze-encoder-bn
         --epochs-phase-a 8 --epochs-phase-b 0  (else default: dice .5/.5, pw 1.3,
         chm). stable past E6 ⇒ BN drift CONFIRMED → full run w/ phase B + eval.
         still cliffs ⇒ pivot --lr-phase-a 2e-5 / freeze conv1 RGB channels.

## 2026-07-05  idempotent tiling — stop paying 20-min re-tile on session loss
goal:    user lost Colab runtime, re-ran full pipeline → re-tiled 20min, killed
         it mid-write. recurring pain. make tiling not re-run needlessly.
did:     verified interrupted re-tile did NOT corrupt tiles — selection is
         deterministic (seeded), re-tile produced byte-identical files; index
         untouched (written last). checked Drive: 685 indexed tiles all present,
         4-band, 0 missing (dirs hold orphan tiles from old tilings — harmless,
         loaders read index only). v035 IDEMPOTENT TILING: _tile_signature()
         captures every selection-affecting constant (hs_source, hard_neg_frac,
         bg_frac, grvi, val/test frac, block/autocorr m, stride, tiles budget,
         seed); citywide step_tile skips scan+write if sidecar meta.json matches
         sig AND all tiles exist; else re-tile. sidecar written LAST (interrupt-
         safe). --force-retile overrides. pre-seeded 2016 sidecar to match live
         v032 constants so next full-pipeline run REUSES (no one-time re-tile).
         added import json.
decided: reuse-by-default not opt-in — a re-run after session loss should be
         cheap. over-capture sig (re-tile when unsure) > stale reuse. 6-site
         tiling not cached (fast; inputs are per-year crops).
files:   phase4_semantic_finetune.py v034→v035 (.versions snapshotted);
         phase4/tiles/2016/tile_index_2016.meta.json (pre-seeded).
next:    UNCHANGED — run D still pending (dice isolation, train-only, ~5min):
         --step train --dice-weight 0.0 --bce-weight 1.0 --epochs-phase-a 8
         --epochs-phase-b 0. tiles verified intact, no re-tile needed.

## 2026-07-05  run C: softened pool DID NOT fix cliff → dice term prime suspect
goal:    retile v032 pool (bg .30→.22) + retrain 2016 (run C), expect cliff gone.
did:     retile OK: bg tiles 36%→29% (target 22% + 74 forced neg-sites on top),
         train 372 tiles. retrain STILL CLIFFED: peak val_iou .4588 E5 → .0312 E6
         → ~0, Phase B stuck, ckpt frozen E5. raw pos_weight rose 2.774→2.987
         (pixel-bg went UP even as tile-bg went down). class-balance hypothesis
         REFUTED — cliff now invariant to channel (run A), pos_weight (run B),
         AND pool (run C).
decided: re-read signature: tr_bce smooth ↓1.5→.70, val_bce BOUNDED .68-1.26 (NOT
         all-bg — that'd blow up BCE on 25% canopy px), only val_iou@0.5 cliffs;
         prior eval AUROC .89 = ranking FINE. ⇒ NOT a learning collapse — the
         PROB SCALE drifts below .5 after E6 (canopy px .55→.4: BCE shrugs,
         val_iou@.5 → 0, ckpt frozen at undertrained E5). Only unvaried term that
         pushes prob scale down on bg-heavy PIXEL dist = soft-DICE. v033: flags
         --bce-weight/--dice-weight to isolate it. Decisive test = pure BCE
         (dice 0) on EXISTING v032 tiles (dice train-only, no retile).
killed:  class-balance-is-the-cause (3 runs refute). softening pool as the fix.
files:   phase4_semantic_finetune.py v032→v033 (.versions snapshotted); run C log
         in chat.
next:    USER: run D = --dice-weight 0.0 --bce-weight 1.0, existing tiles. cliff
         gone ⇒ dice confirmed, dial intermediate (.2-.3). still cliffs ⇒ dice
         exonerated, pivot to trainable conv1 / phase-A LR / BN. Fable reads log.

## 2026-07-04  round-1 result: NOT chm, NOT pos_weight → dice cliff on empty
                tiles; v032 softens sampling
goal:    run round-1 disambiguation (runs A+B), find collapse cause.
did:     run A (--hs-dropout 1.0 = rgb-equiv, pw clamp 1.3): peak val_iou .5947
         E5 → CLIFF .0632 E6 → ~0. run B (chm, --coarse-pos-weight-max 2.8, pw
         raw 2.774 UNCLAMPED): peak .6028 E5 → CLIFF .0077 E6. THREE runs (incl.
         v030 original) cliff at EXACTLY E6 under different channels + loss
         weights → channel + pos_weight ELIMINATED. inspected tile_index_2016:
         train 408 tiles, 44% canopy_frac<5% (164 pure-zero); all 74 neg-site
         tiles in train; mean canopy_frac .262 ↔ raw pw 2.774 checks out.
         MECHANISM: _masked_dice per-sample — empty-tile dice = 1-1/(P+1), grad
         ∝ 1/(P+1)² GROWS as prob mass P shrinks → snowball on 44% of samples →
         global canopy suppression = cliff. timing data-driven → explains E6
         invariance. val_bce ~.9-1.2 fits probs compressed ~.3 (below .5 thresh),
         not literal all-zero.
decided: fix = pool composition not loss code (v029 SAME dice was stable at bg
         ~21% → proven config). v032: HARD_NEG_FRACTION .30→.15,
         BACKGROUND_BUDGET_FRACTION .30→.22. GRVI stays .08, neg sites stay.
         pos_weight clamp back at default 1.3 (historically stable). fallback if
         run C still cliffs: per-batch dice (train-only edit).
killed:  raising pos_weight as the fix (run B: no effect on cliff). --no-hillshade
         retile disambiguation (superseded by --hs-dropout 1.0 trick, 2 retiles
         saved).
files:   phase4_semantic_finetune.py v031→v032 (.versions snapshotted); runs A/B
         logs in chat (history CSVs: A none — user interrupted phase B, fine;
         B = sem_loss_history_2016_runB_pw28.csv if copied).
next:    USER: retile + retrain 2016 (run C, commands in chat). Fable: verify new
         pool composition + watch for cliff → then evaluate/viz per plan step 4.

## 2026-07-04  fable-takeover: v031 flags + round-1 disambiguation plan
goal:    take over collapse fix per HANDOFF_2026-07-05.md — verify claims, make
         levers flag-driven, launch cheapest disambiguation.
did:     verified handoff vs code — all claims hold (constants :296/:307/:360/:373;
         Phase A trains decoder + FULL inflated conv1 at LR 5e-5; coarse =
         bce_dice, early-stop val_iou). re-read collapse curve firsthand: tr_bce
         smooth 1.44→.66 while val_iou cliffs E5 .515→E6 .039 = class-balance
         signature, not NaN/data. KEY FIND: --hs-dropout 1.0 = exact RGB-equivalent
         on EXISTING 4-band tiles (conv4 zero-init + zero input → zero grad →
         weights stay 0; val chm passes dead weights) — replaces --no-hillshade
         disambiguation, saves 2 retiles. v031: flags --coarse-pos-weight-max
         (def 1.3) + --lr-phase-a (def 5e-5), defaults reproduce v030 bit-for-bit;
         py_compiled. backups: semantic_eval_report_pre-v031-retrain_2026-07-04.csv,
         sem_loss_history_2016_v030chm_COLLAPSED.csv.
decided: round 1 = 2 train-only runs on existing tiles, single variable each:
         (A) --hs-dropout 1.0 → collapse means class balance, stable means chm
         channel dynamics. (B) --coarse-pos-weight-max 2.8 (≈raw 2.774) → BCE sees
         balanced classes at bg-36% pool. eval only for winner. retile 0.15/0.22
         ONLY if B fails.
files:   phase4_semantic_finetune.py v030→v031 (.versions snapshotted).
next:    USER runs round-1 Colab block (in chat). Fable reads history CSVs →
         decision matrix → step 3/4 per plan.

## 2026-07-05  chm-2016-train-COLLAPSE → handoff to Fable
goal:    first real test of the chm height channel — train 2016 on chm tiles.
did:     ran labels→tile→train→eval→infer→postproc 2016 --hs-source chm. band 4
         confirmed = chm (log "source=chm"). TRAINING COLLAPSED: val_iou .366→.515
         by Phase-A E5 (★) then CLIFF to ~.01, never recovered (Phase B stuck
         .005-.02); saved ckpt = undertrained E5. eval rgb+chm: IoU .4911 AUROC
         .8941 Prec .760 Rec .5814 — big regression vs rgb baseline
         .7245/.9293/.773/.921, recall CRASHED .92→.58 (under-predicts). grass-FP
         27.1% (no gain). pos_weight raw 2.774 (was 1.501 in stable v029 struct)
         → clamped 1.3 = canopy starved. inference→mask ran on the bad ckpt (43.5%
         canopy, likely low).
decided: CHM raster is CORRECT (visually great crowns/ground, height p50 6.7m) —
         NOT the problem. collapse = v030 training deltas: class-balance overshoot
         (HARD_NEG .30 + bg .36 + pos_weight clamp 1.3 → all-background basin),
         maybe compounded by strong chm channel + trainable inflated input-conv at
         LR_PHASE_A 5e-5. hand to Fable to stabilize + rebalance.
files:   HANDOFF_2026-07-05.md (full diagnosis, levers w/ line#, experiment order);
         semantic_eval_report.csv (2016 rgb+chm row); phase4/models/sem_best_2016.pt
         (collapsed — overwrite on retrain); edmonds_canopy_{prob,mask}_2016.tif.
next:    [FABLE] (a) disambiguate: 2016 --no-hillshade under v030 sampling —
         collapse? = class-balance; stable? = channel. (b) rebalance HARD_NEG→.15,
         bg→.22, raise COARSE_POS_WEIGHT_MAX or COARSE_USE_POS_WEIGHT=False;
         retile+retrain --hs-source chm; want val_iou past .55, Phase B improving,
         recall ~.85. (c) then phase4_viz grass-FP, then 2000.

## 2026-07-04  chm-height-channel-grass-fp-fix
goal:    kill grass false-positives — grass = 64% of all FPs, 29.5% grass-FP rate
         on 2000 (aggregate IoU hides it). fix via REAL height, keep recall.
did:     root cause: struct = hillshade(fr) - hillshade(be) is TEXTURE not HEIGHT
         (flat 20m roof → ~127 like grass; AUC ~.70; dead-0 on ~43% of city).
         (1) new fetch_build_chm.py: USGS 3DEP Height-Above-Ground via MPC STAC
         3dep-lidar-hag (item USGS_LPC_WA_Western_North_2016, metres, 2m COG) →
         lidar_snoh_chm.tif on fr grid, U8 DN=1+round(clip(h,0,50.6)/0.2) (0=nodata,
         DN1=0m grass, DN254=50.6m). (2) wired chm → v030: HS_PATHS/HS_STATS['chm'],
         --hs-source default struct→chm. (3) FIXED no-coverage bug — raw-0 band4
         normalized to -1.78 EXTREME not neutral; rgb_to_model_input now blanks
         no-coverage px to 0 (=mean), matches HS_DROPOUT. (4) re-enabled grass
         negs: HARD_NEG_FRACTION 0.0→.30, GREEN_GRVI_THRESHOLD .10→.08,
         BACKGROUND_BUDGET_FRACTION .20→.30. (5) new make_grass_negatives.py —
         stages Negative_*_rgb.tif (cemetery/civic/stadium/fields) from 2020 ortho
         → preview montage → --commit verified turf-only into photos/.
decided: HAG > DSM-DTM (1 product, no subtract) > county services (no DSM elev,
         hillshade only). keep recall = best_f1 thresh (not prec-floor). U8-scale
         CHM to reuse 4th-ch plumbing (no retile churn). HS_STATS['chm'] left
         PLACEHOLDER — MUST paste fetch_build_chm.py output before train.
files:   Scripts/fetch_build_chm.py v001; phase4_semantic_finetune.py v029→v030
         (.versions/ snapshotted); Scripts/make_grass_negatives.py v001;
         Scripts/phase4_viz.py (grass diagnostic). all py_compiled + on G:.
next:    ON COLAB in order: (a) fetch_build_chm.py → paste HS_STATS['chm'] :445.
         (b) make_grass_negatives.py → verify montage → --commit turf-only.
         (c) retile+train+eval 2016 (clean/on-yr) + 2000 w/ --hs-source chm.
         (d) phase4_viz.py 2016/2000 → grass_metrics.txt; want grass-FP <29.5%,
         recall/IoU held. (e) ablation rgb/struct/chm on 2016. label-circularity
         ceiling unchanged — photo-interp still the DG2 gate.

## 2026-07-03c  yr2000-struct-first-valid-test
goal:    first valid structure-channel test (v029 live stem), yr 2000 vs rgb baseline.
did:     2000 rgb+struct tile/train/eval, v029 confirmed ('inflated 4ch input conv
         kept trainable in Phase A'). held-out test: IoU .4677 AUROC .8692 AP .6426
         Rec .7982 vs rgb baseline .4634/.8638/.6392/.7733. ALL metrics move +,
         but small (~.4-.5pp IoU/AUROC, +2.5pp recall) — single seed, not proven.
decided: eval instrument is biased AGAINST the channel — labels = 2020 mask from
         phase-3 RGB teacher → struct fixing RGB grass/tree errors gets counted
         WRONG. small consistent + movement despite that = weakly encouraging,
         not decisive. random-point photo-interp (open item, needed for DG2
         anyway) is the only instrument that can settle it.
files:   phase4/eval/semantic_eval_report.csv (+2000 rgb+struct rows);
         phase4/models/sem_best_2000.pt (now 4ch struct).
next:    build photo-interp harness; til then keep --hs-source struct default
         (no harm shown, theory + AUC 0.732 standalone + consistent small gains).
goal:    3-way 2016 ablation (struct/fr/rgb) on Colab; interpret.
did:     (1) ablation ran, held-out test 158 tiles, same blocked split:
         rgb IoU .7245 AUROC .9293 / struct .7176 .9278 / fr .7120 .9242 —
         NO gain from 4th channel, spread ~.012 ≈ seed noise. (2) found WHY:
         _freeze_encoder froze inflated conv1 (encoder param) in Phase A →
         zero-init structure weights stuck at 0 for 20 ep, then LR 5e-6 from
         scratch in B → channel effectively dead all runs. struct/fr results
         are NOT valid tests of the channel. fix = v029: keep enc.conv1
         trainable in Phase A when IN_CHANNELS>3 (RGB start unchanged — extra
         ch is zero). (3) eval CSV race: fr eval ran v027 (Drive sync lag) →
         wiped struct rows; v028 dedupe then mislabeled+removed fr rows.
         Repaired CSV from logs: 2016 rows now rgb+struct/.7176, rgb+fr/.7120,
         rgb/.7245, chronological order (thresh reader takes last = matches
         on-disk rgb ckpt). fr tp/fp/fn/tn unrecoverable (4dp log only).
decided: don't judge structure channel on pre-v029 runs — mechanically dead.
         2016 also worst-case demo yr: rgb strong + labels derive from 2020
         mask (circular ceiling). real test = v029 re-run + early yr vs
         2000/2002 rgb baselines (.463/.484).
files:   phase4_semantic_finetune.py v028(eval channels col)→v029(stem fix);
         phase4/eval/semantic_eval_report.csv (repaired).
next:    re-tile+train+eval 2016 struct under v029 (expect '(inflated 4ch input
         conv kept trainable in Phase A)' print). then yr 2000 or 2002 struct
         arm — biggest expected payoff, direct rgb baseline exists.

## 2026-07-03  struct-channel-+-hs-dropout
goal:    strengthen single-yr(2016) LIDAR channel — grass blends into trees; harden
         vs snapshot staleness in distant yrs.
did:     (1) fetched county bare-earth hillshade on exact fr grid (same 6-strip
         exportImage pattern, server gis.snoco.org/img/rest/services/Topography)
         → lidar_snoh_hillshade_be.tif. (2) built lidar_snoh_structure.tif =
         clip(fr-be+127,1,254), 0=nodata — terrain shading cancels (fixed 315° sun),
         grass→flat ~127, canopy texture kept, flat roofs suppressed. (3) v027:
         --hs-source {fr,struct} (default struct) picks band-4 raster + per-source
         norm stats; HS_SOURCE stamped as GeoTIFF tag on tiles at tile time,
         train/eval adopt tag, ckpt records it, inference adopts ckpt → no
         flag/tile/ckpt mismatch possible (untagged 4band tiles → fr). (4)
         --hs-dropout 0.25: train-only, blanks normalized structure band to mean
         per-sample via torch RNG → keeps pure-RGB pathway for stale-snapshot yrs.
         (5) validated local vs phase3 2020 canopy mask, ~97M px, 40 windows:
         |struct-127| separates canopy/bg AUC 0.732 (canopy dev 71.5 vs bg 36.1);
         same test raw fr AUC 0.646 → terrain-cancel wins. plumbing tests all pass
         (tag round-trip, stats-follow-source, chip reads 94% land coverage).
decided: struct default > fr — higher standalone AUC, kills north-slope illum
         confound. dropout mean-fill not raw-0 — goal is RGB-pathway strength,
         raw-0 already means nodata. be raster staged too (reproduce/debug).
         fetch script SAVED to Scripts/ this time (fetch_lidar.py loss lesson).
files:   phase4_semantic_finetune.py v026(pre-edit snap)→v027(live);
         Scripts/fetch_be_build_struct.py; lidar_snoh_hillshade_be.tif,
         lidar_snoh_structure.tif (Full_Image/Pipeline Imagery/).
next:    Colab smoke test: --year 2016 --step tile (expect "+ LIDAR hillshade band 4
         ... source=struct" + tag) → --step train (expect "Input channels: 4
         (RGB+structure[struct]) hs-dropout=0.25"). Ablation now 3-way:
         --no-hillshade / --hs-source fr / struct (re-tile between). torch dropout
         line untested locally (no torch) — watch first train batch.

## 2026-07-02  chat-logging-setup
goal:    persistent progress log — low context, resume-friendly.
did:     made this CHATLOG.md. caveman "full" for entries + fixed schema + STATE
         block + rolling-compaction rule.
decided: caveman-full for entries (~65-75% fewer tokens, tech-accurate); STATE+LOG
         split + deltas + reference-not-repeat + compaction to bound size; log per
         session/milestone not per-msg (per-msg balloons context, buries signal).
files:   Scripts/CHATLOG.md (new).
next:    optional Stop-hook to auto-remind logging at session end (not built; offer).

## 2026-06-29  lidar-hillshade-+-4band-imagery
goal:    fix 4-band imagery crash; add LIDAR to help model split grass vs trees.
did:     (1) fixed RGBI tiling crash — city-wide read now [1,2,3] (was reading 4
         bands into count=3 profile → ValueError). (2) built full per-year RGB+NIR
         4ch model → SCRAPPED. (3) downloaded county LIDAR first-return hillshade,
         clipped to union extent of all orthos, mosaicked → lidar_snoh_hillshade_fr.tif
         (11441x16052, EPSG:3857, 1m, ~117MB); every ortho footprint covered.
         (4) found acquisition date: USGS/WADNR "Western Washington 3DEP" QL1,
         flown Mar2016-Jun2017 mostly 2016 (service "2013-16" abstract is stale).
         (5) wired hillshade as uniform 4th channel, all years → v025. Validated
         local: reproj co-registers across CRS/GSD, 4-band tile write/read round-
         trip, numpy logic (order [R,G,B,HS], HS stats mean0.58 std0.26, zero-init).
decided: hillshade > NIR — uniform all yrs, real structure signal, single tile-write
         inject point. zero-init new conv channel (preserve pretrained RGB). model
         auto-matches tile band count (no flag/tile mismatch). --hillshade default on.
killed:  NIR 4th band (v023) — per-year variable channels too messy, Kam scrapped.
         Preserved in .versions/ if ever revisited.
files:   phase4_semantic_finetune.py v022→v023(NIR,dead)→v024(RGB fix)→v025(hillshade);
         HANDOFF_2026-06-29.md; lidar_snoh_hillshade_fr.tif.
next:    Colab smoke-test 2016; ablation --hillshade vs --no-hillshade for IoU/AUROC.
         Temporal caveat: hillshade ~2016 → strong for 2015-17, weak for 2000-2012.

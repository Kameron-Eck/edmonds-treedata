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
         entries + the ACTIVE PLAN = Scripts/honest-measurement-overhaul.md. Do NOT create a new
         HANDOFF. one-fact-one-home: live state here, method=Method_Pipeline.md, build
         status=pipeline_buildtracker.md, schedule=edmonds_combined_workplan.xlsx.
measure: ACTIVE WORKSTREAM (opened 2026-08-17). PLAN = Scripts/honest-measurement-overhaul.md.
         WHY: Kam — "became too reliant on AI judgement"; wants defensible numbers + better
         tests/visuals. FOUR PHASES, run order 1 -> 2 -> 4 -> 3 (Kam's choice).
         ---- RESUME HERE  (2026-08-18 end of session; context exhausted, new session starting) ----
         READ FIRST, IN THIS ORDER:
           1. this STATE block
           2. Reports/Measurement_Validity_Assessment_2026-08-18.md  <- 351-line assessment; it is
              SHARPER THAN THE PLAN on what P3 can and cannot answer. Its U1-U8 are the live question
              list. Treat it as the agenda.
           3. Scripts/honest-measurement-overhaul.md (the 4-phase plan)
           4. Scripts/pipeline_architecture.html (self-contained; open in a browser)
         PHASE STATUS
           P1 DONE · P2 DONE + replicated x4 · P4 dashboard + height plot DONE
           P4 REMAINING: sentinel TP/FN/FP site overlays (needs footprint resolution from photos/)
           P3 TOOLING BUILT, NOT YET RUN BY A HUMAN. Samples drawn for 2016 / 2022n / 2000.
         ---- THE SIX RESULTS THAT MATTER ----
         (1) DETECTION IS A FUNCTION OF CANOPY HEIGHT. 2016: .16 (0-2m) .16 (2-5) .36 (5-10) .57
         (10-15) .74 (15-20) .83 (20-25) .88 (25-30) .93 (30+). 5-15m holds 53% of ALL misses;
         lifting those two bands to the 20-25m rate takes recall .68 -> ~.80. qc/height_curves.png
         (2) ** IT SURVIVES THE CONFOUND TEST (2026-08-18). ** Inside the P2 BOTH-AGREE partition the
         staircase is intact: .2278 (2-5m) -> .9496 (30+m), overall .7611 on n=22.0M. So it is NOT
         C-CAP suburban over-counting in disguise. In the CONTESTED zone the model calls canopy only
         9.2% of the time — it sides with the NDVI ref against C-CAP almost completely.
         CAVEAT: the NDVI ref requires height >= 2m BY CONSTRUCTION, so the both-agree 0-2m band is
         near-empty and MUST NOT be quoted. Finding holds above 2m.
         (3) THE DEFICIT IS INHERITED. phase3/edmonds_canopy_mask_2020.tif — the label source for all
         coarse years — has the same staircase and sits BELOW its own students at every band (.5455 vs
         the 2016 model's .6821). Improving that one mask lifts every coarse year at once.
         (4) MODEL STRENGTH DOES NOT MOVE THE NUMBER. 9 years span IoU .49-.76 / AUROC .938-.954;
         honest recall stays .51-.78 with no correlation.
         (5) ** U2 IS A DEFINITION PROBLEM, NOT AN ACCURACY PROBLEM (2026-08-18, latent class). **
         Foody-2022 LCA on C-CAP x NDVI-ref x model, fitted WITHIN CHM height bands.
         4 baseline yrs give latent prevalence pi = .2912 / .2820 (2021s) / .2931 (2019n) /
         .2863 (2022n) — i.e. ON C-CAP's total (.265-.295), NOT the NDVI ref's (.338-.387).
         Global se/sp 2016: ccap .894/.951 · ndvi_ref .987/.873 · model .750/.992. So the NDVI
         ref is HIGH-SENSITIVITY / LOW-SPECIFICITY (liberal) and the model is the STRICTEST of
         the three — a new instrument reproducing "high-precision under-predictor".
         BUT the two candidate answers are two DEFINITIONS, not a right and a wrong one: the
         NDVI ref's surplus concentrates in the 2-5m band (its sp .78, lowest of any cell) =
         shrubs/hedges. If U1 counts woody veg >=2m, pi ~ .35 is correct; if U1 requires tree
         form, pi ~ .29 is correct. NO ESTIMATOR CAN SETTLE THAT — U1 does. That is the finding.
         (5b) THE INSTRUMENT SELF-DIAGNOSED ITS OWN LIMIT. Feeding the CORRECTED 2016 model
         instead of the baseline moves pi .2912 -> .3490 and hands that model se .948/sp .966
         (best of the three) — because 2016c was TRAINED on the NDVI-derived overlay, so it is
         not a third independent test. Latent prevalence must not depend on which model you
         score; it moved 5.8pp. => LCA IS INADMISSIBLE FOR THE 2016c DEPLOY DECISION, in EITHER
         direction. Do not quote 2016c's LCA win as evidence to deploy.
         (5c) ADVERSARIAL TEST PASSED. Competing account: model+C-CAP are the correlated pair,
         they out-vote the NDVI ref, truth really is .378. Simulated that world holding the
         observed call rates fixed: NO dependence strength reproduces the observed
         (pi .291, ndvi sp .873) pair, and rho=.7 needs the model's TRUE sensitivity to be
         .115. The account fails. -> phase4_qc_latent_class_adversarial.py
         CAVEATS THAT RIDE WITH (5): do NOT quote the 0-2m row (the NDVI ref requires >=2m BY
         CONSTRUCTION); do NOT quote tall-band C-CAP sp (30+ sp .36 rides on a ~5% non-canopy
         sliver); no goodness-of-fit exists (7 params on 7 d.f. = just-identified, fits exactly
         by construction); 2022n ndvi se dips to .911 (the one wobble, not a finding).
         (6) ** n=250 IS NOT THE BINDING LIMIT — INTERPRETER FIDELITY IS (2026-08-18). **
         Simulated the REAL design (true W_h + allocation from sample_{year}_meta.json,
         Olofsson estimator w/ full multinomial covariance) instead of the SRS approximation.
         2016, 1500 simulated studies per cell:
           interp err   half-width   power(H_CCAP)  power(H_NDVI)
                   0%      .0122          1.000          1.000    <- RIGGED, see below
                   5%      .0346           .889          1.000
                  10%      .0469           .436           .997
         So §3.1's "+/-5.9pp, cannot arbitrate" was an SRS artefact — the real stratified
         half-width is .0122-.0469 vs SRS .0620, because the allocation deliberately
         over-samples the contested zone. CORRECTION TO THE ASSESSMENT, not to a model.
         THE 0% ROW IS RIGGED and must never be quoted alone: truth is DEFINED as one of the
         two references, so inside strata BUILT from those references every point shares one
         truth and within-stratum variance collapses. The honest rows are 5%/10%.
         ASYMMETRY WORTH KNOWING: symmetric interpreter error pulls every estimate toward .5,
         i.e. UPWARD from both hypotheses — so sloppy interpretation systematically favours
         the LIBERAL (higher-canopy) definition. power(H_CCAP) collapses .889 -> .436 while
         power(H_NDVI) stays ~1.0. Interpreter error does not merely widen the CI; it BIASES
         toward the shrub-inclusive answer.
         YEAR CHOICE, now evidenced: reference separation 2016 = 8.24pp but 2022n = 4.65pp,
         so 2022n is already MARGINAL at 5% error (power .340). Do 2016 DEEP rather than
         250 x 3 spread thin — which is exactly assessment amendment 3, now with a reason.
         => the duplicate-interpreted subset (amendment 5, Stehman 2022 ID 100) is NOT
         optional; it measures the one quantity the whole study now turns on.
         ---- LITERATURE (37 papers, IDs 69-105, searches 9-14) — TWO CORRECTIONS TO ME ----
         FOODY 2010: I claimed raw scores overstate the model's faults. Direction depends on ERROR
         CORRELATION; ours are almost certainly correlated (labels + both refs all from interpreting
         the same imagery) => OUR RECALL IS LIKELY OPTIMISTIC. Do not repeat my old pattern claim.
         MOUDRY 2024 + SIERRA 2026: canopy-height products are height-biased, realistic CHM MAE ~3m,
         which would blur 5m bands. Part of the staircase could be CHM error. UNVALIDATED (U6).
         Confirmed independently: TURUBANOVA 2023 (error concentrates 4-6m), FERRAZ 2016 (same shape
         from lidar), ARAZO 2020 (our feedback loop is canonical pseudo-label confirmation bias),
         MAJASALMI 2021 (15-17% disagreement is NORMAL).
         ---- P3 MUST CHANGE BEFORE KAM LABELS ----
         (a) U1 NO WRITTEN CANOPY DEFINITION EXISTS. Min height? Min crown area? Shrub vs short tree?
         Lawn under a yard tree? Without it 250 points produce A THIRD OPINION, not an arbitration.
         ONE PAGE, written first, committed. THIS IS THE TOP BLOCKER.
         (b) UNSURE HANDLING: my sampler EXCLUDES unsure. WICKHAM 2023 shows primary-vs-alternate
         scoring swings accuracy 10 POINTS (77.5 -> 87.1). Record PRIMARY + ALTERNATE, report both.
         (c) SAMPLE SIZE: the assessment shows n=250 gives +/-5.9pp, which COVERS BOTH references
         (27.7-39.5 vs C-CAP 29.5 / NDVI 37.7) => cannot arbitrate. NOTE: that arithmetic assumes
         SIMPLE RANDOM SAMPLING; our stratified design over-samples the contested zone and should do
         better. [RESOLVED 2026-08-18 — SIMULATED, see result (6): the stratified design IS
         better (half-width .0122-.0469 vs SRS .0620) and n=250 DOES arbitrate in 2016 up to
         ~5% interpreter error. Do NOT resize n on the +/-5.9pp figure; the binding constraint
         is interpreter fidelity, not sample size.]
         (d) STEHMAN 2014 licenses reference-derived strata but requires ITS estimators; mine is a
         delta-method approximation. WAGNER & STEHMAN 2015/2024 give a principled allocation; my
         shares were ad hoc.
         ---- CHEAPEST NEXT MOVES (all local, no GPU, no labelling) ----
         1. [DONE 2026-08-18] FOODY 2022 LATENT-CLASS — see result (5) below.
         2. [DONE 2026-08-18] Simulate the ACTUAL stratified design's CI — see result (6).
         3. Write the canopy definition (U1). <-- NOW #1, and results (5)+(6) BOTH converge
            on it: (5) says U1 alone decides whether Edmonds canopy is ~29% or ~35%; (6) says
            n=250 CAN resolve that in 2016 — but only against a definition it has been given.
            Write it against the .29/.35 bracket.
         4. P1c per-year miss-depth under ONE recipe (--force-citywide) for U4 (labels vs calibration).
         ---- P3 COMMANDS (tooling is built and validated) ----
         py -3.12 phase4_accuracy_sample.py --step serve --year 2016             --ortho "D:\edmonds-pipeline\Imagery6_snoh_rgbi.tif"
         then open http://localhost:8731/review_app.html  (1 canopy / 2 not / 3 unsure / z undo)
         then --step estimate --year 2016
         Estimator validated twice; a covariance bug was found and fixed 2026-08-18 (8283232) — the
         old version overstated every CI.
         ---- LOCAL ENV ----
         CUDA now works locally: torch 2.13.0+cu126, Quadro T2000 4GB (CLAUDE.md says 2GB — STALE),
         3.45GB free, verified. Still do NOT train locally (rule: don't split training Colab/local).
         ---- HONEST BASELINE (quote ONLY live=1 rows in qc/qc_indep_report.csv) ----
         vs C-CAP, forest_wetland, deployed thresh: 2013 .7094/.8551 · 2016 .6844/.8651 ·
         2000 .6303/.7745 · 2015 .6222/.8835 · 2002 .5069/.8377. NDVI-ref 2016 .594/.959.
         READ = high-precision UNDER-predictor, misses ~30-35% of C-CAP forest; scrub recall .25
         vs forest .68 -> fails on non-conifer/mixed structure (the conifer-only-label blind spot).
         CAVEAT that must ride with every number: BOTH refs are PROXIES (CHM ~2016 @60% coverage;
         C-CAP 2016/2021 applied to 2000/2002/2013). Unknown share of the gap is ref error + real
         change, NOT model error. P2 bounds it; P3 measures it.
         ---- CORRECTIONS TO EARLIER CLAIMS (do not regress) ----
         (1) forest_miss_2016.txt "RECALL .7623" is a stable-intersect-2021 SUBSET. HONEST 2016 =
         .6821 (qc_indep; independently reconfirmed .6832 by decimated recompute). 
         (2) qc_indep is CORRECT — I hypothesised it was pessimistic for lacking an imagery-footprint
         mask and DISPROVED it (0 px dropped on 2016). Do NOT "fix" it.
         (3) "misses are confident/structural -> labels beat compute" is 2016-ONLY. conf% (misses
         prob<.12): 2016 ~60% BUT 2013 9.3%, 2002 19.4%, 2000 24.1% -> most cross-sensor misses are
         NEAR-THRESHOLD, maybe calibration-recoverable. Do NOT commit to hand-tracing stands until
         P1c recomputes this per year on one recipe.
         (4) There is NO git remote — "git pull" CANNOT update Colab. The working tree IS
         the Drive folder (G:/My Drive/treedata); git DB = D:/edmonds-pipeline/treedata.git,
         local Windows only. GOOGLE DRIVE is the sync path to Colab. Verify there with:
         !grep -c 2022n /content/drive/MyDrive/treedata/Scripts/phase4_p1_colab_run.py
gotcha:  scripts Colab-only for torch (rasterio+geopandas+fiona+sklearn now pip-
         installed local — module import auto-installs). polygons/ overwritten w/
         accept-all test data; 14,476-crown human review never finished.

════════════════ LOG  (newest first) ════════════════

## 2026-08-18  SAMPLE SIZE WAS NEVER THE PROBLEM — interpreter fidelity is
goal:    cheapest-next-move #2: the assessment's "n=250 cannot arbitrate" (§3.1) rests on
         SIMPLE RANDOM SAMPLING arithmetic and flags itself as such (§5). The real weights
         now exist on disk (--step design ran for 2016/2022n/2000), so stop assuming.
did:     NEW Scripts/phase4_qc_design_power.py — Monte-Carlo of the ACTUAL design: real W_h
         + real allocation from sample_{year}_meta.json, the design's own strata rebuilt via
         phase4_accuracy_sample.build_strata, and the SAME Olofsson estimator with the full
         multinomial covariance (8283232). 1500 simulated studies per cell.
         -> phase4/qc/design_power_{2016,2022n}.txt/.csv
RESULT: see STATE result (6). §3.1 CORRECTED — stratified half-width .0122-.0469 vs the
         SRS .0620 the assessment assumed; n=250 DOES arbitrate in 2016 at <=5% interpreter
         error. The binding constraint moved from SAMPLE SIZE to INTERPRETER FIDELITY.
         Two things worth more than the headline:
         (a) the 0%-error row is RIGGED (truth defined as a reference => no within-stratum
             variance in strata built from that reference). Built the sweep precisely so that
             number can never be quoted alone.
         (b) interpreter error is not symmetric in EFFECT: flipping labels pulls estimates
             toward .5, i.e. UP from both hypotheses, so sloppiness systematically favours the
             shrub-inclusive definition. power(H_CCAP) .889->.436 while power(H_NDVI) stays 1.0.
decided: nothing deployed, no plan amendment applied (Kam's sign-off). Measurement only.
killed:  "n=250 cannot arbitrate, resize the sample" — DEAD for the wrong reason. Do not
         re-derive n from the +/-5.9pp SRS figure; that number does not describe this design.
         "run 250 x 3 years" — evidenced against: reference separation 2016 8.24pp vs 2022n
         4.65pp, so 2022n is marginal at 5% error. 2016 deep, per amendment 3.
files:   Scripts/phase4_qc_design_power.py (new) · phase4/qc/design_power_*.txt/.csv ·
         CHATLOG STATE results (6) + item (c) + cheapest-moves list.
next:    U1 canopy definition — now the ONLY thing between here and a defensible P3 run.
         Then wire the duplicate-interpreted subset (amendment 5) into --step design; result
         (6) makes it load-bearing, not a nicety.

## 2026-08-18  U2 REFRAMED — the reference dispute is a DEFINITION dispute, and LCA proved its own limit
goal:    run cheapest-next-move #1: Foody-2022 latent class on C-CAP x NDVI-ref x model.
         Give each source a sensitivity/specificity with NO gold standard, before spending
         human hours on P3. Local, no GPU, no labelling.
did:     NEW Scripts/phase4_qc_latent_class.py — 2-class 3-indicator LCA by EM, fitted
         globally AND within each CHM height band, 95% CIs from a SPATIAL BLOCK BOOTSTRAP
         (64-cell blocks; binomial CIs on 21M autocorrelated px would be fiction).
         Band-conditioning is not decoration: height drives every source's error rate, so
         conditioning on it absorbs much of the shared dependence between sources.
         Ran 5 configs -> phase4/qc/latent_class_{2016_baseline,2016_corrected,2021s,
         2019n,2022n}.txt/.csv
VALIDATED BEFORE TRUSTING (both committed, both runnable):
         phase4_qc_latent_class_test.py — recovers known truth to <.002 on synthetic data,
         stable across 12 seeds (spread 7e-11), and CONFIRMS the just-identified claim
         (reproduces the 8-cell table to 9e-12 — so a perfect fit is arithmetic, not evidence).
         Its rho-sweep also MEASURES the failure mode: correlate 2 sources and the odd one
         out loses .07-.12 of sensitivity while the pair is flattered.
         phase4_qc_latent_class_adversarial.py — see result (5c) in STATE.
RESULT: see STATE result (5)/(5b)/(5c). Headline = pi ~ .29 across 4 baseline years, on
         C-CAP's total, not the NDVI ref's; the NDVI ref is liberal and its surplus sits in
         the 2-5m band (shrubs/hedges); the model is the strictest of the three.
         The two answers are TWO DEFINITIONS. U1 decides, no estimator can.
decided: nothing deployed, nothing in the plan edited, no §4 amendment applied (those are
         Kam's sign-off). Measurement only, as with U3.
killed:  "LCA can arbitrate the 2016c deploy" — DEAD, and killed empirically not in
         principle: swapping baseline->corrected moves latent pi 5.8pp because 2016c
         descends from the NDVI ref. Do not retry LCA on any NDVI-descended model.
         "latent truth sits on C-CAP, so C-CAP is the better reference" — NOT claimed.
         Prevalence agreement is not accuracy; C-CAP hits the right TOTAL while making both
         errors (se .70 at 5-10m). Two of three sources share a strict definition and the
         latent class inherits the majority definition (Gutierrez-Velez 2024, ID 81).
files:   Scripts/phase4_qc_latent_class.py (new) · Scripts/phase4_qc_latent_class_test.py
         (new) · Scripts/phase4_qc_latent_class_adversarial.py (new) ·
         phase4/qc/latent_class_*.txt/.csv (5 pairs) · CHATLOG STATE measure: block.
next:    U1 canopy definition, now with a number attached to it (.29 vs .35 turns on it).
         Then cheapest-move #2 (simulate the stratified design's real CI). P3 unchanged and
         still gated on U1.

## 2026-08-18  U3 ANSWERED — the height staircase SURVIVES reference disagreement (it is real)
goal:    run the cheapest free instrument named in the 2026-08-18 assessment: cross P1c
         (recall-by-height) with P2 (ref agreement). Never been crossed. Local, no GPU.
did:     NEW Scripts/phase4_qc_height_by_agreement.py — recall by CHM band computed SEPARATELY
         inside each agreement partition. Ran 2016 baseline, decim 8, thresh .509,
         21,066,144 valid cells. -> phase4/qc/height_by_agreement_2016_baseline.txt/.csv
RESULT — THE STAIRCASE IS REAL:
         both_canopy (both refs agree = ref noise removed), n=5,505,444, overall recall .7374:
           0-2m .1608 · 2-5m .2010 · 5-10m .4181 · 10-15m .6220 · 15-20m .7668 ·
           20-25m .8535 · 25-30m .8971 · 30+m .9404
         THE TEST: 5-15m .5172 vs 20m+ .9049 -> spread +0.3877.
         -> the 5-15m deficit is a MODEL problem, NOT C-CAP counting lawns between yard trees.
         -> height-conditioned training (stratify-then-segment, Hamraz lit ID 86) IS the lever.
         -> the suburban visual grounding and the height curve are BOTH true; they are not
            the same finding, and the height one is not an artifact of the other.
contested partitions (no truth there -> CALL RATE, not recall):
         ccap_only n=713,884, call rate .0814. MASS SITS LOW (2-15m ~478k of 714k cells).
           C-CAP forest that is tall enough but NOT green (ndvi<.2). AMBIGUOUS between
           lawn/roof-between-yard-trees AND low-NDVI purple-leaf ornamentals — and if it is
           the latter, the model AND the NDVI ref BOTH miss them. Worth a look before P3.
         ndvi_only n=2,448,603, call rate .2036, climbing .0855 (2-5m) -> .7764 (30+m).
           Green and >=2m but not C-CAP forest = shrubs/hedges at low height. Model refuses
           8.5% of the 2-5m band — consistent with the known scrub recall .25.
decided: nothing deployed, nothing in the plan edited. This is measurement only.
files:   Scripts/phase4_qc_height_by_agreement.py (new)
         phase4/qc/height_by_agreement_2016_baseline.txt / .csv (new)
         Reports/Measurement_Validity_Assessment_2026-08-18.md (prior entry; 7 amendments
         still PENDING Kam's sign-off — none applied)
next:    ONE COMMAND, not yet run (session ended first) — the 2016c deploy comparison:
           py -3.12 Scripts/phase4_qc_height_by_agreement.py              --prob phase4/masks/edmonds_canopy_prob_2016_corrected.tif              --ccap D:/edmonds-pipeline/Imagery/ccap_2016_hires_lc.tif              --ndvi phase4/qc/ndvi_ref_2016.tif              --thresh 0.509 --label 2016_corrected --decim 8
         Read: did the overlay lift the 5-15m bands INSIDE both-agree (real fix), or only
         in ndvi_only (it just adopted the NDVI ref's definition)? That is the 2016c
         deploy/no-deploy question in one number.
         Then the other free instruments from the assessment: miss-depth per yr on one
         recipe (U4) · Foody-2022 latent class on ccap x ndvi x model (U2) · Clark-2023
         stratified patch re-sample (U5).
gotcha:  console here is cp1252 — keep report bodies ASCII (box-drawing chars crash print()
         before the file write, so a crash means NO output file, not a partial one).

## 2026-08-18  ASSESSMENT — P3 AS SCOPED CANNOT ANSWER THE BLOCKING QUESTIONS (250 pts too few)
goal:    Kam asked: assess what we know / what we need to know. Synthesis over STATE +
         honest-measurement-overhaul.md + the 105-paper tracker. No new measurement.
did:     Reports/Measurement_Validity_Assessment_2026-08-18.md. Unknowns ordered BY THE
         DECISION EACH BLOCKS (U1-U8), not by topic. Power math COMPUTED, not gestured at.
THE FINDING — P3 at 250 pts/yr answers the question that is NOT in doubt and cannot
         answer either question that IS:
  * arbitrate C-CAP 29.5% vs NDVI-ref 37.7% (gap 8.2pp, midpoint 33.6%):
      n=250 -> +/-5.9pp, CI [27.7,39.5] = COVERS BOTH REFS. n=400 -> still covers both.
      n=510 needed to separate at the midpoint. And the midpoint is exactly what
      "the refs BRACKET truth" predicts. -> 250 leaves the question open.
  * per-band recall: 3 strata -> 83/stratum -> +/-10.7pp. 4 strata -> +/-12.3pp.
      8 strata (4 CHM band x 2 agreement — the design that would split the U3 confound)
      -> 31/stratum -> +/-17.6pp. 5-15m band cannot be pinned better than ~+/-12pp.
  * confirm the height effect (.36 @5-10m vs .83 @20-25m): significant at n_h=20.
      BUT WE ALREADY KNOW THIS, replicated. Spending the human budget to re-confirm the
      one thing not in doubt is the failure mode to avoid.
NEW/UNDER-USED KNOWN surfaced from STATE (absent from the 5 headline findings):
  8/8 missed stands = SUBURBAN (yard/ornamental, many purple-leaf low-NDVI), ZERO
  deciduous forest. -> HEIGHT AND LAND-USE CONTEXT ARE CONFOUNDED. Short trees live in
  yards, tall trees in stands. Unknown share of the height staircase is a suburban-vs-
  forest staircase in a height costume. CHEAP TEST (local, no GPU, inputs all exist):
  recall by height band WITHIN each P2 agreement partition. Staircase survives inside
  both-agree = real height effect. Flattens = C-CAP suburban over-count.
decided: 7 proposed AMENDMENTS to honest-measurement-overhaul.md, NOT applied — Kam signs off.
         (1) write the canopy definition FIRST (min height / crown area / shrub-vs-short-
         tree / continuous-vs-binary). No definition = the 250-pt run is a THIRD OPINION,
         not an arbiter (Gutierrez-Velez ID 81: cross-product disagreement is manufactured
         by different cut points on one continuous variable).
         (2) run the FREE instruments before spending human hours: recall-by-band within
         P2 partitions (U3) · miss-depth per yr one recipe (U4) · Foody-2022 LATENT CLASS
         on ccap x ndvi-ref x model (U2, no gold standard needed) · Clark-2023 stratified
         patch re-sample (U5). Any may change what the human sample must be.
         (3) re-derive n FROM THE QUESTION: ~500+ in 2016 alone beats 250x3 spread thin.
         (4) response design: primary + ALTERNATE/fuzzy label + explicit SHORT-TREE-vs-
         SHRUB call. Plan currently EXCLUDES Unsure — that discards exactly the pixels the
         refs disagree about. Wickham ID 78: NLCD OA 77.5% primary-only -> 87.1% with
         alternate = 10pp from a SCORING CONVENTION, bigger than our whole model range.
         (5) duplicate-interpreted subset designed IN (Stehman ID 100 / Xing ID 101) —
         cannot be added later. (6) 20-30 pt 2000 FEASIBILITY block, interpreted twice,
         before production (Reis ID 103: 3 interpreters fully agreed on <40% of historical
         px; at 60cm no-NIR the short-tree/shrub call may be beyond one interpreter).
         (7) strata decision resolves BEFORE --step design. model-output / agreement /
         CHM-band strata are THREE DIFFERENT STUDIES; Stehman ID 72 permits any, not all
         three on this budget.
killed:  "your recall is probably optimistic" (my own claim, prev turn) — WRONG as a blanket.
         Direction is PER REFERENCE: vs C-CAP the suburb over-count inflates the recall
         denominator -> measured recall is PESSIMISTIC; vs the NDVI ref (shared lineage,
         and post-overlay it also supplied labels) errors correlate -> OPTIMISTIC. That is
         the quantitative form of "the refs bracket truth".
files:   Reports/Measurement_Validity_Assessment_2026-08-18.md (new)
         honest-measurement-overhaul.md NOT edited — amendments are proposals only.
next:    Kam signs off on the amendments. Then U1 (definition) -> the three free local
         instruments -> re-derive P3 n. Mechanical chain unchanged: P1 Colab stage 1 ->
         2022 citywide raster -> P3 --step design.
caveat:  power table uses SRS variance = conservative. Recompute with Olofsson/Wagner-
         Stehman stratified variance once stratum weights known. p=.5 worst case.


## 2026-08-18  LIT PHASE 4 — measurement validity, 37 papers (ID 69-105), searches 9-14
goal:    the 8 prior searches covered architecture/resolution/temporal/labels. None asked
         whether our numbers MEAN anything. This phase targets the validity gap: sampling,
         reference disagreement, height bias, label propagation, CHM vintage, interpreter protocol.
did:     Literature_Tracker.xlsx +37 rows, +6 rows on "Search Phase Reference".
         S9 accuracy/area protocol (8) — Olofsson 2014/2013, Stehman+Foody 2019, Stehman 2014,
           Wagner+Stehman 2015, Stehman+Wagner 2024, Radoux 2020, Pontius+Millones 2011.
         S10 reference quality (6) — McCombs 2016 (C-CAP), Wickham 2023 (NLCD), Foody 2010,
           Foody 2022, Gutierrez-Velez 2024, Majasalmi 2021.
         S11 height-stratified bias (6) — Turubanova 2023, Moudry 2024, Ferraz 2016,
           Hamraz 2017, Clark 2023, Guo 2023.
         S12 label-noise propagation (5) — Arazo 2020, Liu+Chun 2009, Moraes 2024, Peng 2025, Tang 2025.
         S13 CHM fusion / vintage (5) — Wagner 2024, Allred 2025, Kwong+Fung 2020, Zhang 2025, Sierra 2026.
         S14 interpretation protocol (7) — Pengra 2020, Stehman 2022, Xing+Stehman 2024,
           Tarko 2020, Reis 2024, Parmehr 2016, Hwang+Wiseman 2020.
decided: every DOI verified against Crossref API or a search hit — none written from memory.
         Unverified issue/article numbers STRIPPED rather than guessed.
         Rows re-sorted 9->14, IDs 69-105 sequential.
findings that BITE (papers vs our 5 empirical claims):
  - Stehman 2014 LICENSES stratifying on the REFERENCE (CHM band, C-CAP/NDVI agreement).
    Unbiased if you use its estimators; variance inflates. Our planned design is legal.
  - Wickham 2023: NLCD OA 77.5% on primary label -> 87.1% if an ALTERNATE label counts.
    10pp swing from scoring interpreter uncertainty alone > our whole model-quality range.
    -> 250-pt protocol MUST record primary + alternate ("fuzzy"), report both.
  - McCombs 2016 (C-CAP's OWN accuracy paper): 3x3 sample unit, 6-of-9 homogeneity rule,
    OR/WA 84.9%. C-CAP was NEVER validated at single-pixel scale and the paper says it is a
    SCREENING tool for local decisions. Some of our 15-17% is scale misuse, not model error.
  - Foody 2010: 10% reference error -> producer's accuracy UNDER-est 18.5% if errors independent,
    OVER-est 12.3% if CORRELATED. Ours are correlated (same imagery, same interpreter lineage)
    -> our recall is probably OPTIMISTIC. Plus latent-class = accuracy with NO gold standard.
  - Foody 2022 is the escape from finding 5: treat C-CAP + NDVI ref + model as 3 imperfect tests
    of one latent canopy variable, solve each one's sensitivity/specificity. Disagreement stops
    being noise and becomes the estimator's INPUT.
  - Ferraz 2016 + Turubanova 2023: the height-monotonic recall curve REPLICATES in lidar and in
    Landsat-Europe (error concentrates 4-6m; 25% under vs WorldCover from short/open stands).
    Finding 1 is a PROPERTY of canopy remote sensing, not our U-Net. Supports finding 2.
  - Hamraz 2017 CONTRADICTS the fatalist reading: stratify-then-segment lifted understory recall
    +22.1% at -15.0% precision. Intervention = height-conditioned model, not a better single pass.
    Precision cost matches finding 5 drifting toward the liberal NDVI ref.
  - Guo 2023 names the trade: adding small-crown training examples RECRUITS SHRUBS. Likely what
    our NIR+CHM overlay actually did. -> 250-pt protocol must separate short tree from shrub or
    it cannot adjudicate finding 5 at all.
  - Clark 2023: patch sampling under-samples small-area features by construction. CHEAP TEST
    before more overlay work — re-sample 2020 training patches stratified by CHM band, watch low-height recall.
  - Moudry 2024 CAUTION on finding 1: global CHM products are themselves height-biased. Sierra 2026
    puts CHM MAE ~3m at realistic density. A 3m error BLURS our 5m-wide recall bands. Validate
    the 2016 lidar CHM before trusting its bands as truth.
  - Wagner 2024 is the fix for the CHM vintage problem: train U-Net to PREDICT height from imagery
    using lidar only as supervision -> synthesize a per-year CHM for all 18 acquisitions instead of
    smearing one 2016 snapshot across 2000-2024. Turns 60% coverage from a blocker into training data.
  - S14 gives the 250-pt design: Wagner+Stehman 2015 / Stehman+Wagner 2024 for allocation
    (over-sample 5-15m + disagreement strata), Stehman 2022 + Xing 2024 to fold interpreter
    variance INTO the CI, Pengra 2020 (88% OA, tree cover high-agreement) and Hwang+Wiseman 2020
    (chi-sq: PI == high-res IC at n>=250) as benchmarks. Reis 2024 is the warning: on HISTORICAL
    imagery 3 interpreters fully agreed on <40% of pixels — our 2000s years may not adjudicate.
files:   Literature_Tracker.xlsx (sheets "Literature Tracker" 69-105, "Search Phase Reference" +6)
next:    design the ~250-pt run: strata = CHM band x C-CAP/NDVI agreement, allocation per
         Wagner+Stehman, response design = primary + fuzzy alternate + shrub-vs-short-tree call,
         duplicate subset for interpreter variance. Then Foody 2022 latent-class on the 3 sources.
         Cheap pre-test first: Clark 2023 stratified patch re-sampling.


## 2026-08-17  pipeline_log stamps version + code sha + command (logs now self-identify)
goal:    close the gap the registry backfill exposed — logs/ never said WHICH code ran, so a
         backfilled run_registry row can't state an engine version (the 7 rows in d48b057 say
         "v047-v048 (not stamped in log)").
did:     pipeline_log.py — every header now carries 3 auto-resolved lines, NO caller change:
             version:   v048
             code sha:  ec890b59  (9 files)
             command:   --year 2016 --step train
         version order = explicit version= arg > __version__ > first \bvNNN\b in the file head
         > "unset". code sha = SHA-1 over the script PLUS any sibling package it IMPORTS — the
         phase4seg/ split means the shim's own bytes say nothing about what ran. Attachment is
         by import parsed from the script text, NOT by name pattern (a pattern guess credited
         phase4_qc_indep.py with the engine's v048 — caught in test). Resolution never raises;
         failure degrades to "unknown". Also: the confirmation print no longer dies on a cp1252
         console (local QC scripts hit it; the log was already written).
decided: fingerprint over source bytes, not just a version string — two runs with the same sha
         ran byte-identical code even when nobody bumped a version. That is what makes a
         registry row reconstructable from logs/ alone.
tested:  real Scripts/ layout — engine → v048 / 9 files; standalone QC script → 1 file, version
         unset; missing script → unknown. py_compile OK. No engine file touched.
files:   pipeline_log.py (commits 0020f2a [first half, swept in by the concurrent session's
         `git add -A`] + 2cdb53d).
did+:    both loose ends CLOSED same session: (1) `__version__ = "v048"` now declared in
         phase4seg/__init__.py (authoritative, replaces the parsed docstring marker) — verified the
         stamp still reads v048 AND the sha moved ec890b59→9ab821d9, proving the fingerprint tracks
         source bytes. (2) CLAUDE.md rule 1 now says stage PATHS not `git add -A` (+ new rule 1b) —
         two sessions share one working tree; 0020f2a swallowed half of an unrelated change.
next:    registry rows from here on quote version + code sha + command straight off the log header.

## 2026-08-17  doc/repo cleanup — CLAUDE.md + buildtracker de-staled, registry backfilled, CHATLOG compacted
goal:    non-code housekeeping while a coding session ran on the same tree. bootstrap docs
         had rotted (both said Phase 4 = "live v042"; engine has been phase4seg/ since 07-08).
did:     (1) CLAUDE.md — version claim REMOVED (not corrected: a version number here rots;
         live version now lives ONLY in this STATE). layout map gained phase4seg/,
         phase4seg_preflight/_smoke, phase4_qc_flicker, phase4_miss_examples,
         phase4_ccap_sample, phase3_make_segmentation_png, pipeline_config.
         (2) pipeline_buildtracker.md — same v042 fix + "No git" claim (FALSE since 07-06)
         + dead plan name drifting-swinging-dolphin.md removed; tooling table now indexes
         the C-CAP/QC/preflight scripts; honest metrics de-duplicated → point at the active
         plan's baseline table instead of restating.
         (3) run_registry.csv — 7 Colab runs were NEVER recorded (2000/2002/2013/2015/2017/
         2019/2022 xsensor, 07-09→07-10). backfilled from logs/. corroborates 2 plan defects:
         2017 inference logged "173 MB ✓" yet the raster is unusable, 2022 logged "168 MB ✓"
         yet the file on Drive is 0 BYTES.
         (4) CHATLOG compacted per its own SPACE RULE 4: 114KB→52KB, newest 6 entries full,
         33 older → 1-liners. full text verbatim in _archive/CHATLOG_2026-06-29_to_2026-07-07.md.
         (5) archived _audit_2026-07-08/ → _archive/audit_2026-07-08/, USGS Script.ipynb and
         the 146KB .bak_prewindowfix → _archive/scripts/; dropped __pycache__.
decided: version numbers + metrics live in ONE home (STATE / the active plan) — every other
         doc links. that is why the fix was deletion, not correction.
killed:  nothing.
checked: Method_Pipeline.md hyperparameters verified line-by-line against phase4seg/config.py
         (LR 5e-5, epochs 20/30, batch 10, tile 512, stride 512, neg-rate .15, MIN_CANOPY_PATCH
         3.0 m²) — CONSISTENT, no edit needed. per-year GSD table also matches the run logs.
files:   CLAUDE.md, pipeline_buildtracker.md, ../README.md, run_registry.csv (+7 rows),
         CHATLOG.md, _archive/{README.md, CHATLOG_2026-06-29_to_2026-07-07.md,
         audit_2026-07-08/*, scripts/*}. 5 commits, no code touched.
next:    logs/ do NOT stamp the engine version → a backfilled registry row can't state one.
         cheap fix when the engine is next edited: have write_step_log() emit the version.

## 2026-08-18  U3 TESTED — THE HEIGHT CURVE IS REAL. It survives inside the both-agree partition.
source:  Reports/Measurement_Validity_Assessment_2026-08-18.md (a separate assessment doc, found late)
         raised U3: 8/8 inspected missed stands were SUBURBAN, not deciduous forest, so "recall by
         height" and "recall by land-use context" may be confounded — short trees live in yards, tall
         trees in stands. Proposed test: recompute recall by height WITHIN each P2 agreement partition.
did:     Ran exactly that on 2016 (decimated 1/4, local, no GPU).
result:                  BOTH-AGREE          CONTESTED (ccap-only)
           2-5  m          .2278                 .0125
           5-10 m          .4545                 .0332
          10-15 m          .6592                 .0903
          15-20 m          .7966                 .1576
          20-25 m          .8756                 .2048
          25-30 m          .9129                 .2198
          30+   m          .9496                 .2937
          OVERALL          .7611  (n 22.0M)      .0919  (n 2.86M)
         (1) ** THE STAIRCASE SURVIVES INSIDE BOTH-AGREE ** — .23 -> .95, monotonic, full range, on
         ground BOTH references independently confirm as canopy. The height effect is REAL, not C-CAP's
         suburban over-counting wearing a height costume. U3 resolved in favour of finding 1.
         (2) IN THE CONTESTED ZONE THE MODEL CALLS CANOPY ONLY 9.2% OF THE TIME — it sides with the NDVI
         reference almost completely. Consistent with the assessment's account: C-CAP labels whole leafy
         suburban blocks "Upland Forest", counting lawn and roof between yard trees.
caveat:  the NDVI reference requires height >= 2 m BY CONSTRUCTION, so the both-agree 0-2 m band is
         near-empty (4,507 px) and meaningless. THE FINDING HOLDS FOR CANOPY ABOVE 2 m — which is where
         the decision-critical 5-15 m band sits, so the headline is unaffected. Do not quote the
         both-agree 0-2 m figure.
decided: finding 1 now survives its strongest available confound. The contested zone is characterised
         (model+NDVI vs C-CAP, not a coin flip), which also sharpens U2: the question is not "who is
         right in a 50/50 dispute" but "is C-CAP's suburban forest class counting non-canopy ground".
next:    the assessment's other cheap tests — expected-CI simulation for the ACTUAL stratified design
         (its n=250 verdict uses a simple-random-sample approximation, which understates a stratified
         design), and Foody 2022 latent-class on C-CAP x NDVI x model.

## 2026-08-18  LIT REVIEW PHASE 4 LANDED (37 papers, IDs 69-105) — TWO FINDINGS CONTRADICT MY FRAMING
source:  Literature_Tracker.xlsx, searches 9-14 (prompt = Scripts/litreview_phase4_prompt.md).
CONTRADICTS ME:
  (1) FOODY 2010 — I said repeatedly "every headline number looked worse than the corrected one;
      raw scores systematically overstate the model's faults". WRONG DIRECTION, probably. Foody
      shows 10% reference error UNDER-estimates producer's accuracy by 18.5% when reference and map
      errors are INDEPENDENT, but OVER-estimates it by 12.3% when they are CORRELATED. Our labels
      and both references all come from imagery interpretation of the SAME scenes, so correlation is
      near-certain => OUR RECALL IS LIKELY OPTIMISTIC, NOT PESSIMISTIC. Stop repeating my pattern claim.
  (2) MOUDRY 2024 — all three global canopy-height products carry systematic HEIGHT-DEPENDENT bias.
      The CHM is the axis we stratify recall on, so part of the monotonic curve could be CHM ERROR
      rather than detection failure. VALIDATE the 2016 lidar CHM's height accuracy before treating
      its bands as truth. This is a confound finding 1 does not currently account for.
CONFIRMS (independently):
  TURUBANOVA 2023: continental product, error concentrates at 4-6 m, 25% tree-area underestimate from
  short/open canopy omission — our curve turns over in the same band.
  FERRAZ 2016: same monotonic detection-vs-size shape from LIDAR, a different sensor entirely.
  ARAZO 2020: canonical statement of our feedback loop; predicts students CANNOT correct the teacher's
  bias from imagery alone (mitigation = a floor of genuinely independent labels per year).
  MAJASALMI 2021: 15-17% inter-product disagreement is NORMAL, not a defect to eliminate.
  PENG 2025: our label noise is STRUCTURED (concentrated in 5-15 m) = the worst case; off-the-shelf
  noise-robust losses assume uncorrelated noise and will NOT help us.
BIG OPPORTUNITY:
  FOODY 2022 — LATENT CLASS MODELING. Treat C-CAP, the NDVI ref and the model as three imperfect tests
  of one latent canopy variable and solve for each one's sensitivity/specificity from their AGREEMENT
  PATTERN ALONE, no ground truth. Computable from rasters we already have, BEFORE any labelling. This
  could partially resolve finding 5 ("cannot tell if 2016c got more correct") without P3.
P3 MUST CHANGE:
  * WICKHAM 2023: primary-vs-(primary-or-alternate) scoring swings accuracy 10 POINTS (77.5% -> 87.1%).
    My sampler EXCLUDES 'unsure'. It should record a PRIMARY + ALTERNATE call and report both numbers.
    McCombs 2016 shows C-CAP's own interpreters did exactly this.
  * STEHMAN 2014: LICENSES our reference-derived stratification (legitimate, unbiased, variance
    inflated) BUT requires ITS estimators — mine is a delta-method approximation. Reconcile.
  * WAGNER & STEHMAN 2015 / 2024: objective allocation minimising summed variance; my 0.24/0.18/0.16/
    0.10/0.20/0.12 shares were AD HOC. Redo the allocation properly.
  * RADOUX 2020: adaptive response design cuts interpretation effort 50-75% at equal accuracy by
    concentrating on ambiguous points — directly relevant to Kam's ~5 h budget.
SCALE CAVEAT:
  McCOMBS 2016 — C-CAP was validated at 3x3-pixel units with a six-of-nine homogeneity rule, NEVER at
  single-pixel scale, and its authors call it a screening tool for local/site-specific decisions. We
  score it PER PIXEL. Some of the 15-17% disagreement is C-CAP used outside its validated design.
GUTIERREZ-VELEZ 2024: most cross-product disagreement is DEFINITIONAL (different thresholds on a
  continuous cover variable), not empirical — argues for reporting continuous per-crown canopy fraction
  with the threshold stated, rather than a binary mask.
next:    (a) latent-class analysis on the three existing layers — cheapest possible next result;
         (b) rework P3 unsure handling to primary/alternate BEFORE Kam labels;
         (c) reconcile the estimator with Stehman 2014; (d) validate the CHM's height accuracy.

## 2026-08-18  GRASS CHECK — the 2016c grass regression is ~73% CONTESTED, ~27% GENUINE
did:     Closed the one open concern from the 2016c verdict: is the grass-rejection drop (.9119 -> .7191)
         a real regression, or is it the contested zone again? Decimated 1/8 cross-tab of C-CAP grass vs
         the NDVI reference, on pixels the corrected model newly calls canopy.
found:   C-CAP grass cells sampled 3,732,545
           baseline  calls canopy   252,635  ( 6.77%)
           corrected calls canopy 1,062,658  (28.47%)
           NEW grass FP (corrected only): 825,361, and the NDVI reference calls those:
             CANOPY   604,938  (73.3%)   <- CONTESTED: C-CAP says grass, NDVI says trees
             grass    112,023  (13.6%)   \ GENUINE regression: neither reference
             non-veg  108,400  (13.1%)   / supports canopy there
         => ~73% contested, ~27% (220,423 px) genuine. In UNCONTESTED terms the grass FP rate roughly
         DOUBLES (~6.8% -> ~12.7%), it does not quadruple as the headline .912 -> .719 implied.
decided: the grass concern is REAL BUT BOUNDED, and it is the same contested-zone story as everything
         else — consistent with 2016c having adopted the NDVI reference's canopy definition wholesale.
         FINAL 2016c POSITION: a genuine candidate. On uncontested ground F1 .853 -> .937. Its costs are
         (a) ~27% of a doubled grass FP rate that no reference supports, and (b) total dependence on the
         NDVI reference being right in the contested ~16%. Both are P3 questions.
files:   analysis was inline (no new script) — numbers recorded here.
next:    P4 remaining item = sentinel TP/FN/FP overlays, colour-coded by the P2 partition. Everything
         else in P1/P2/P4 is done. P3 blocks the deploy decision and needs Kam.

## 2026-08-18  2016c UPDATE — on UNCONTESTED ground the corrected model is CLEARLY better (F1 .853 -> .937)
found:   ref_agreement on 2016c. BOTH-AGREE subset (reference noise removed):
                                baseline   corrected
           both-agree recall      .7613      .9486    (+.187)
           both-agree precision   .9699      .9254    (-.045)
           both-agree F1          .8531      .9369    (+.084)
           FN that is UNMEASURABLE 33.1%     64.6%    (+31.5 pts)
         => Scored against RAW C-CAP the precision drop looked severe (-.136). On ground BOTH references
         agree about it is only -.045, while recall gains +.187. MOST OF THE APPARENT PRECISION LOSS WAS
         THE MODEL BEING PENALISED INSIDE THE CONTESTED ~16%.
         Also: the remaining miss is now 64.6% unmeasurable (was 33.1%) — the corrected model has cleared
         out most misses BOTH references confirmed, leaving mainly the disputed zone.
revised: THIS PARTIALLY REVERSES MY EARLIER CAUTION. I wrote "do not deploy 2016c on the strength of
         recall .87". The both-agree numbers materially strengthen its case: on uncontested ground it is
         better on BOTH axes-adjusted terms (F1 .853 -> .937). The honest summary is:
           * on ground both proxies agree about  -> 2016c is clearly better
           * on the contested ~16%               -> it sides with NDVI over C-CAP, and NOTHING here can
                                                    say whether that is right
         STILL A REAL CONCERN: grass rejection .9119 -> .7191 on C-CAP grass. Part of that may itself be
         contested (the NDVI ref has its own grass class), but it is not explained away by the partition
         and should be checked before any deployment decision.
decided: 2016c is a CANDIDATE, not a regression — but the deploy/no-deploy call still needs P3, because
         the whole difference between "better" and "over-predicting" lives in the contested zone.
next:    Kam's call on deployment. P3 remains the blocker for adjudicating it.

## 2026-08-18  2016c VERDICT — the overlay TRANSFERRED THE NDVI REFERENCE'S DEFINITION, disagreement and all
result:  2016 baseline -> 2016c (--add-canopy-mask), honest vs C-CAP 2016:
           recall     .6844 -> .8718   (+.187)
           precision  .8651 -> .7296   (-.136)
           grass-rej  .9119 -> .7191   (-.193)
           canopy frac 23.36% -> 35.28%   (C-CAP ref says 29.53%)
           F1         .7642 -> .7944   (modest net gain)
         HEIGHT CURVE (same tool, same decimation, ccap_2016):
           band      base    corr     delta
            0-2  m   .1559   .3055   +.150
            2-5  m   .1634   .5028   +.339
            5-10 m   .3569   .6932   +.336
           10-15 m   .5739   .8447   +.271
           15-20 m   .7362   .9228   +.187
           20-25 m   .8329   .9580   +.125
           25-30 m   .8824   .9751   +.093
           30+   m   .9347   .9894   +.055
           OVERALL   .6826   .8675   +.185
predict: MY PRE-REGISTERED PREDICTION DID NOT CLEANLY RESOLVE. I framed it binary — either "5-15m lifts
         while 25m+ stays put" (H2) or "every band lifts together" (liberalisation). What happened is a
         THIRD outcome I did not enumerate: EVERY band lifted, but with a STEEP HEIGHT GRADIENT (6x
         bigger at 2-5m than at 30m+). Do not retrofit the test to the result — record it as partial.
verdict: ** THE OVERLAY WORKED EXACTLY AS DESIGNED, AND THAT IS THE PROBLEM. ** The corrected overlay is
         NIR+CHM-derived, so it carries the NDVI reference's canopy DEFINITION. P2 already established
         that reference is systematically more liberal than C-CAP, and that for 2016 it calls 37.7%
         canopy vs C-CAP's 29.5%. The corrected model landed at 35.28% — right next to 37.7%, not next
         to 29.5%. It learned the NDVI reference's definition, including its disagreement with C-CAP.
         => Scoring labels built from proxy A against proxy B CANNOT adjudicate. The experiment
         converged on exactly the ~16% disagreement P2 quantified.
         H2 STATUS: the height-graded lift is real evidence that the deficit IS label-shaped and IS
         addressable. But "does this make the model MORE CORRECT" is UNANSWERABLE with proxies alone.
         If the NDVI ref is right, 2016c is now more accurate and C-CAP is penalising it. If C-CAP is
         right, 2016c over-predicts. NOTHING IN THE PROXY DATA DISTINGUISHES THESE.
decided: this is now the single strongest argument for P3, and it is an EMPIRICAL one rather than a
         methodological preference: a real experiment ran, produced a large effect, and could not be
         scored. P3 must stratify by BOTH the disagreement zone AND CHM height.
         DO NOT deploy 2016c over the baseline on the strength of recall .87 — grass rejection fell to
         .719, i.e. it now calls grass canopy ~28% of the time vs ~9% before.
next:    ref_agreement on 2016c (running) — the both-agree subset is the fairest available comparison.

## 2026-08-18  ** THE LABEL SOURCE HAS THE SAME HEIGHT CURVE — AND IS WORSE THAN EVERY MODEL IT TEACHES **
goal:    Kam asked how the Phase-3 2020 mask "matches up". It is the LABEL SOURCE for every coarse year
         (config.MASK_2020 -> labels.canopy_label_from_2020_mask), so this is the feedback-loop test.
built:   NEW phase4_qc_height_curve.py — decimated recall-by-height, IMAGERY-FREE (mask + C-CAP + CHM only).
         Needed because forest_misses also reads the year's ortho, and 2020_coe_rgb.tif is 27.1 GB, NOT
         mirrored on D:, so the read streams over FUSE and DIED mid-run while Colab was using the same
         mount ("TIFFFillTile: got 0 bytes, expected 229412"). Dropping the imagery answers the height
         question in seconds from a 1/8 sample instead of 31.5 Gpx.
         ALSO FIXED: "2020" was missing from forest_misses IMG_CATALOG/GSD_CM, so the first attempt died
         on a KeyError and wrote NOTHING — a silent failure inside the tool this workstream exists to fix.
found:   ** 2020 LABEL SOURCE vs its 2016 STUDENT, recall by height (vs C-CAP) **
           band        label src   2016 model
            0-2  m       .0430       .1538
            2-5  m       .1158       .1628
            5-10 m       .3099       .3559
           10-15 m       .4484       .5729
           15-20 m       .5785       .7354
           20-25 m       .6643       .8339
           25-30 m       .7160       .8828
           30+   m       .7759       .9343
           OVERALL       .5455       .6821
         (1) THE TEACHER HAS THE SAME MONOTONIC STAIRCASE. Coarse years are not DEVELOPING the height
         bias during fine-tuning — they are being TAUGHT it. Independent confirmation of H2, arriving
         BEFORE 2016c finished.
         (2) THE STUDENTS BEAT THE TEACHER AT EVERY BAND, and the gap WIDENS with height (+.16 at 30m+).
         Fine-tuning on each year's own imagery + the CHM channel already partially corrects bad labels.
         Phase 4 inherits the SHAPE but improves the LEVEL.
         (3) Even at 30m+ — mature conifer, where the 5 hand-labelled training sites live — the label
         source only reaches .776.
caveat:  the 2020 mask is a PREDICTION, not hand truth (hand labels = 5 conifer sites only), so "recall"
         here means AGREEMENT WITH C-CAP. Decimated 1/8 sample; compared against ccap_2021 (-1y) while
         the 2016 model was scored against ccap_2016. The SHAPE and the RELATIVE comparison are robust;
         absolute values are proxy-limited (see the P2 ~16% disagreement result).
decided: this is the strongest single piece of evidence for the label hypothesis so far, and it is
         INDEPENDENT of 2016c. It also reframes the fix: improving the 2020 mask lifts EVERY coarse year
         at once, because they all read it. That is a higher-leverage target than any single year.
files:   NEW phase4_qc_height_curve.py; qc/height_curve_2020_labelsource.{txt,csv}.

## 2026-08-18  ** RECALL IS A FUNCTION OF HEIGHT ** — 0.15 at <5m rising to 0.93 at 30m+. Fixing 5-15m = .68 -> .80
found:   Ran the new recall-by-height table on the 2016 BASELINE (needed as the like-for-like comparison
         for 2016c). It is the cleanest result of the whole investigation — a monotonic staircase:
           band        recall    recalled / missed
            0-2  m     0.1538       354,554 / 1,950,038
            2-5  m     0.1628     4,309,190 / 22,158,565
            5-10 m     0.3559    23,383,033 / 42,317,431
           10-15 m     0.5729    32,087,410 / 23,921,864
           15-20 m     0.7354    40,679,724 / 14,634,548
           20-25 m     0.8339    45,177,044 / 9,001,029
           25-30 m     0.8828    42,534,706 / 5,647,702
           30+   m     0.9343    80,263,834 / 5,641,178
         On MATURE canopy the model is nearly perfect (.93 at 30m+). It degrades SMOOTHLY all the way
         down to .15 below 5m. This is not "the model misses ~12m trees on average" — recall is
         essentially a FUNCTION OF HEIGHT.
         ** SIZE OF THE PRIZE ** 5-15m holds 66,239,295 of the 125,272,355 missed px = 53% OF ALL MISSES.
         If those two bands merely reached the 20-25m rate (.8339), TP gains ~46.0M and overall recall
         goes .6821 -> ~.799. That single band IS the gap.
decided: this replaces every earlier framing (spectral / radiometric / threshold) as the PRIMARY
         statement of the problem. Those were year-specific effects layered on top of this.
         It also gives P3 a sampling instruction: STRATIFY THE HUMAN SAMPLE BY CHM HEIGHT, not just by
         model output — the 5-15m band is where both the miss AND the uncertainty concentrate.
         And it sharpens the 2016c test: the pre-registered prediction now has a CURVE to check, not
         just a mean. H2 confirmed = the 5-15m bands lift while 25m+ stays put. H2 NOT confirmed = every
         band lifts together (the model merely got more liberal) and precision falls.
caveat:  height is CHM-derived and the CHM is a single ~2016 snapshot at ~60% city coverage, so bands are
         only defined where CHM exists; the SHAPE is the robust part.
files:   qc/forest_miss_2016.{txt,csv} regenerated WITH the height table.
next:    2016c lands -> run the same table -> compare curves.

## 2026-08-18  P2 x4 — disagreement is 15-17% EVERY time; NDVI ref is systematically more liberal than C-CAP
found:   Built ndvi_ref_2021s (local, no GPU) and ran the 4th P2 partition. Four years, three sensors:
                                2016      2019n     2021s     2022n
           refs disagree        15.06%    17.03%    16.00%    16.00%
           raw recall           .6844     .6499     .6851     .6564
           BOTH-AGREE recall    .7613     .7278     .7350     .7378
           BOTH-AGREE precision .9699     .9710     .9876     .9567
           FN unmeasurable      33.1%     34.3%     22.0%     38.7%
         => disagreement ~16% EVERY TIME; both-agree recall .73-.76; both-agree precision .96-.99.
         (a) 2021s' unmeasurable share is much LOWER (22%) because C-CAP-ONLY disagreement collapses to
         1.93% — 2021s is the ONE year where imagery and C-CAP share a vintage exactly. ccap_only by
         vintage distance: 2021s same-yr 1.93% · 2016 same-yr 3.40% · 2019n +2y 4.49% · 2022n -1y 5.73%.
         So part of the C-CAP-side disagreement IS temporal, as suspected.
         (b) ** ASYMMETRY, all four years: ndvi_only 10-14% vs ccap_only 1.9-5.7%. ** The NDVI+CHM
         reference is SYSTEMATICALLY MORE LIBERAL than C-CAP, and the MODEL SIDES WITH C-CAP.
         Note the 2021s NDVI ref calls 38.7% canopy vs C-CAP's 26.5% on the SAME YEAR, SAME GROUND —
         a 12-point spread with NO vintage offset to blame. Whatever drives it is not temporal drift.
         (c) 2021s both-agree PRECISION .9876 — the highest yet. On pixels both references confirm,
         this model is essentially not producing false positives.
decided: P2 is DONE as a method — 4 replications, tight numbers. The residual question ("which reference
         is right where they disagree") is NOT answerable with more proxies. Only P3 human labels settle
         it, and P3 must OVERSAMPLE the ~16% disagreement zone.
files:   qc/ndvi_ref_2021s.{tif,txt}, qc/ref_agreement_2021s.{txt,csv}, dashboard refreshed (9 yrs, 4 P2).
next:    2016c — the H2 label test. Judge ONLY against the pre-registered prediction.

## 2026-08-18  2021s DONE — 4th strong model, SAME band. Queue delivered 3/3 unattended; 2016c training.
queue:   phase4_train_queue.py finished 2021s unattended: VERIFY OK 439MB, 100% valid, max prob .957.
         eval OUT-OF-SAMPLE IoU .7571 (HIGHEST of any year), AUROC .938, best-F1 thresh .499.
         2016c (the H2 label test) now TRAINING. Queue has delivered 3/3 jobs with no human present.
found:   2021s HONEST vs C-CAP 2021 @ .499: recall .6851 / precision .8547 / grass-reject .9412.
         FOURTH strong model inside the same band. Full live picture (C-CAP, forest_wetland, live=1):
           2017 .7784 · 2013 .7094 · 2021s .6851 · 2016 .6844 · 2022n .6564 · 2019n .6499 ·
           2000 .6303 · 2015 .6222 · 2002 .5069
         Model quality across these spans IoU .49-.76 and AUROC .938-.954, yet honest recall stays
         pinned in a ~.51-.78 band with NO correlation to model strength. That is now 4 independent
         confirmations that the ceiling is not the model.
fixed:   dashboard PROVENANCE dict was MISSING 2019n and 2021s, so those two rows plotted without their
         sensor/vintage/NIR line. Added. 9 live years now on the page.
next:    ndvi_ref_2021s building (needed for its P2 partition — will make 4 P2 datapoints).
         Then 2016c: check against the PRE-REGISTERED prediction — recall must rise AND missed-height
         must move up from ~11.8m. Recall alone does NOT confirm H2.

## 2026-08-18  P1c COMPLETE — the INVARIANT is HEIGHT: model finds ~24m trees, misses ~12m trees. Every year.
did:     Finished the full-forest miss-depth recompute for all 5 scorable years (2000/2002/2013/2015/2016).
found:   (a) CONFIDENT-MISS SHARE VARIES WIDELY and the radiometric signature even FLIPS DIRECTION:
           2016 69%  less-green (dNDVI -0.219)
           2013 50%  BRIGHTER +6.7 DN
           2015 26%  DARKER  -11.5 DN  (shadowed — OPPOSITE of the others)
           2000 23%  BRIGHTER +31.3 DN
           2002 22%  BRIGHTER +12.2 DN
         So there is NO single radiometric fix: some years miss washed-out canopy, 2015 misses shadowed
         canopy. Threshold-recoverability also varies 5x across years.
         (b) ** THE ONE INVARIANT: HEIGHT. ** recalled vs missed mean height, every year:
           2016 23.8 / 11.8 (d -12.0) · 2013 23.7 / 11.6 (-12.1) · 2015 24.8 / 12.6 (-12.2)
           2000 24.2 / 13.2 (-11.0)   · 2002 25.6 / 14.7 (-10.9)
         THE MODEL FINDS ~24 m TREES AND MISSES ~12 m TREES — every year, every sensor, every recipe,
         d = -11 to -12.2 m. This replicates harder than recall, brightness or greenness do.
         Consistent with scrub recall .22-.40 and with the 5 conifer training sites being MATURE stands.
decided: THE FAILURE IS HEIGHT-STRATIFIED, i.e. a LABEL-DISTRIBUTION problem: the model learned
         "tall = canopy" because that is what the labels contain. That supports H2 and makes the
         QUEUED 2016c JOB (2016 + --add-canopy-mask) the decisive test — the corrected overlay is
         NIR+CHM-derived and should carry exactly the medium-height canopy the 2020 mask lacks.
         PREDICTION TO CHECK (state it now so it cannot be rationalised later): if H2 is right, 2016c
         should raise recall AND shift the missed-height mean UP from ~11.8 m. If recall rises but the
         missed-height stays ~12 m, the model just got more liberal and H2 is NOT confirmed.
         CAVEAT: height comes from the ~2016 CHM for every year, so the ABSOLUTE numbers for non-2016
         years are temporally offset; the CONSISTENCY of the ~12m/~24m split is the robust part, not
         the exact values.
files:   qc/forest_miss_{2000,2002,2013,2015,2016}.{txt,csv,png} — all full-forest, provenance-stamped.
next:    2021s training; then 2016c = the H2 test. Score each as it lands.

## 2026-08-18  2019n DONE (queue works) — P2 REPLICATES A 3rd TIME; 2013 miss-depth 9.3% -> 50%
queue:   phase4_train_queue.py running DETACHED is working. 2019n: labels OK 0.9min, tile OK, train,
         eval, VERIFY OK (66MB, 100% valid, max prob .949 — healthy). 2021s now training (tile 12.3min).
         2019n eval OUT-OF-SAMPLE: IoU .6462 AUROC .953 AP .8263, best-F1 thresh .495 — near-identical
         to 2022n (IoU .6432 AUROC .9538 AP .8257).
found:   (a) 2019n HONEST vs C-CAP 2021 @ .495: recall .6499 / precision .8540. AGAIN inside the
         .51-.71 band despite AUROC .953 — 3rd strong model that does NOT close the gap.
         (b) P2 REPLICATES A THIRD TIME. Three years, three sensors:
                                2016      2019n     2022n
           refs disagree        15.06%    17.03%    16.00%
           raw recall           .6844     .6499     .6564
           BOTH-AGREE recall    .7613     .7278     .7378
           BOTH-AGREE precision .9699     .9710     .9567
           FN unmeasurable      33.1%     34.3%     38.7%
         => disagreement 15-17%, both-agree precision .96-.97, ~1/3 of the miss unmeasurable, EVERY TIME.
         This is now a solid replicated result, not a pair of datapoints.
         (c) P1c 2013 FULL-FOREST: confident misses (prob<.12) = 50%, vs 9.3% on the stable subset.
         A 5x change. My flag that the stable-subset conf% figures were understated was CORRECT and
         the recompute mattered enormously.
         CONFIDENT-MISS PICTURE, all on the full-forest denominator now:
           2016 69%  ·  2013 50%  ·  2000 23%  ·  2002 22%      (2015 pending)
         So NOT "2016 is an outlier" — it is a 2-vs-2 SPLIT. 2016/2013 = structural; 2000/2002 =
         near-threshold + a radiometric (washed-out) signature.
files:   qc/qc_indep_2019n.txt, qc/ref_agreement_2019n.{txt,csv}, qc/accuracy_dashboard.png (7 yrs + 3 P2).
next:    2015 miss-depth finishing; 2021s training; then 2016c (THE label hypothesis test).

## 2026-08-18  2017 SCORED — I WAS WRONG: it has the HIGHEST recall in the series (.7784), not the lowest
found:   2017 HONEST (vs C-CAP 2016, forest_wetland, thresh .4759): recall .7784 / precision .8083.
         That is the BEST recall of any year (next best 2013 .7094). Also BEST scrub recall .3981
         (others .22-.25). BUT WORST grass rejection .8834 (others .92-.95; grass FP-rate 11.66%).
         92.0M independent 1m cells; model canopy 27.62% vs ref 28.68%.
killed:  MY PREDICTION. I said TWICE "expect LOW recall" from 2017's max-prob .575 ceiling. WRONG —
         a COMPRESSED probability range does not imply poor RANKING. The mass is squeezed into a narrow
         band but the deployed .4759 sits inside that band and separates fine.
         The calibration problem is REAL but shows up as THRESHOLD FRAGILITY, not weakness:
           thresh .2000 -> recall 1.0000 precision .2868   <- calls the WHOLE CITY canopy
           thresh .2500 -> recall 1.0000 precision .2871
           thresh .3000 -> recall .8137  precision .7842
         Below ~.28 everything is canopy. The usable window is razor-thin, so 2017 is FRAGILE to any
         threshold change — that is the cost of the compressed distribution, not low accuracy.
         CONFOUND to keep in mind: 2017 is 7.5cm, the FINEST imagery in the project. Higher resolution
         may genuinely help recall, so 'best recall' is not purely a model-quality statement.
decided: do NOT retrain 2017 to 'fix' it on the strength of the .575 ceiling — it is the best-recall
         year as it stands. If it is ever retrained, the goal is a WIDER usable threshold window
         (calibration), not higher recall.
files:   qc/qc_indep_2017.txt, qc/qc_indep_surfaces_2017.csv, qc_indep_report.csv (live row).
next:    regenerate the P4 dashboard to include 2017; 2013/2015 full-forest miss-depth still pending.

## 2026-08-18  P1b VALIDATED + P1c: on the HONEST denominator the "confident miss" gets STRONGER (60% -> 69%)
did:     Ran phase4_qc_forest_misses.py on 2016 WITHOUT --stable-with (P1b) — the first run on the
         full-forest denominator, using the provenance-stamped version.
found:   (a) P1b PROVENANCE FIX VALIDATED. The report now prints its DENOMINATOR block:
         "stable-with : (none — full forest, comparable to qc_indep)" and RECALL 0.6821 — matching
         qc_indep EXACTLY. The silent-denominator bug that produced the phantom .7623 is closed.
         Also prints "≈ 9,152,423 independent ccap cells" vs 394,061,850 px, so nobody computes an
         error bar off a 43x-replicated pixel count.
         (b) P1c ON THE FULL DENOMINATOR THE MISS IS *MORE* STRUCTURAL, NOT LESS:
                                stable subset (old)   FULL FOREST (correct)
           prob<0.06                  24.6%                 37.5%
           0.06-0.12                  35.8%                 31.9%
           CONFIDENT (<0.12)          60%                   69%
           dNDVI (FN-TP)              -0.150                -0.219
           missed height              12.6 m                11.8 m  (d -12.0 m vs recalled)
         Missed canopy on full forest is also BRIGHTER in R (+5.7) and B (+6.5) — on the stable subset
         those were ~0 (R -1.9, B +0.25). Less-green, brighter, ~12 m tall = deciduous/senescent canopy
         the conifer-trained labels never taught. Consistent with the scrub-recall collapse (.22-.25).
decided: MY EARLIER CORRECTION NEEDS RE-EXAMINING. I told Kam "the structural-miss claim is 2016-ONLY;
         2013 is only 9.3% confident" — but those conf% figures came from forest_miss_sensor_compare,
         which used the STABLE∩2021 subset. 2016 went 60% -> 69% when the subset was removed, so the
         other years' conf% are probably understated too. Recomputing 2000 + 2002 on full forest now
         (running). DO NOT re-quote the 9.3%/19.4%/24.1% figures until they are recomputed.
files:   qc/forest_miss_2016.{txt,csv,png} (now full-forest + provenance-stamped).
next:    2000/2002 full-forest conf% (running); then 2013/2015 (2.3GB rasters, slower). Then decide
         labels-vs-calibration on comparable numbers.

## 2026-08-18  P2 REPLICATES on 2016 + unattended TRAIN QUEUE built + CUDA works locally
did:     (a) P2 on 2016 (2nd NIR year). (b) NEW phase4_train_queue.py for unattended Colab. (c) CUDA torch.
found:   P2 REPLICATES ACROSS YEARS — 2 sensors, 2 C-CAP vintages, same answer:
                              2016        2022n
           refs disagree      15.06%      16.00%   of all valid px
           raw C-CAP recall   .6844       .6564
           BOTH-AGREE recall  .7613       .7378    (+7.7 / +8.1 pts)
           BOTH-AGREE prec    .9699       .9567    (+10.5 / +9.4 pts)
           FN unmeasurable    33.1%       38.7%
           FP on agreed neg   1.05%       1.28%
         => ~1/3 of the apparent under-prediction is REFERENCE DISAGREEMENT, and the model's TRUE
         precision is ~.96-.97 not ~.86. This is a reproducible result, not a one-off.
         ASYMMETRY: NDVI ref calls 37.7% canopy vs C-CAP 29.5% in 2016, but 28.6% vs 29.0% in 2022n —
         the refs do NOT disagree in a fixed direction, which is itself evidence neither is authoritative.
         ndvi_only call-rate is near-identical across years (21.77% / 21.89%) but ccap_only differs a lot
         (9.75% / 32.55%) — worth a look later.
         CUDA: torch 2.13.0+cu126 installed (SAME version as the cpu build, so nothing else breaks).
         cuda avail True, Quadro T2000, 3.45/4.29 GB free, gpu matmul verified. NOTE CLAUDE.md says the
         local GPU is 2GB — it is 4GB (stale).
built:   phase4_train_queue.py — UNATTENDED Colab queue. Runs full labels->tile->train->evaluate->inference
         per job, cheapest-first, ALL COARSE (~1h each). A failing job does NOT stop the queue (unlike the
         P1 driver — nobody is watching). Status flushed to phase4/qc/train_queue_status.csv after EVERY
         step, so the record survives the runtime dying. --run-tag on every job (no overwrites).
         QUEUE + WHY: [2019n, 2021s] = H1, more NIR years -> more independent NDVI refs to test whether the
         ~15-16% disagreement generalises. [2016c] = H2 THE HYPOTHESIS TEST: 2016 + --add-canopy-mask
         (canopy_additions_2016.tif exists) injects NIR+CHM canopy the 2020 mask never taught; compare vs
         the 2016 baseline (.6844/.8651). Closes gap => LABEL problem. Does not => labels exonerated,
         references carry the story. Either result is decisive.
next:    Kam starts the queue before leaving; I score each output locally as it lands (qc_indep +
         ref_agreement), no GPU needed. Then P1c miss-depth, then P4 visuals.

## 2026-08-18  P2 LANDED — 38.7% of the "miss" is UNMEASURABLE. Honest recall .6564 -> .7378.
goal:    /loop autonomous. Build + run P2 (reference-disagreement map) — the experiment the 2022n
         systematic-gap finding made urgent.
did:     NEW phase4_ref_agreement.py (local, rasterio-only, fail-loud). Warps NDVI+CHM ref AND C-CAP onto
         the prob grid; partitions every valid px into BOTH_CANOPY / BOTH_NONCANOPY / NDVI_only / CCAP_only;
         re-scores the model inside each; splits the headline C-CAP FN into REAL vs UNMEASURABLE.
         Ran on 2022n (ideal case: has BOTH refs + a healthy prob raster @ thresh .404).
found:   ** REFS DISAGREE ON 16.00% OF ALL VALID PIXELS ** (NDVI-only 10.27%, C-CAP-only 5.73%).
         MODEL ON THE BOTH-AGREE SUBSET: recall .7378 / precision .9567
           vs raw C-CAP:                  recall .6564 / precision .8630
           => +8.1 pts recall, +9.4 pts precision once reference noise is removed.
         HEADLINE FN (9,624,102 px vs C-CAP) SPLITS:
           REAL MISS   (both refs agree canopy) 5,895,445 = 61.3%
           UNMEASURABLE(refs disagree)          3,728,657 = 38.7%
         Model canopy-call by partition: both_canopy 73.78% · ccap_only 32.55% · ndvi_only 21.89% ·
         both_noncanopy 1.28% (i.e. the model is VERY clean on agreed negatives — its precision was
         being understated by reference noise nearly as much as its recall).
decided: ~2/5 of the apparent under-prediction is NOT attributable to the model. The honest, noise-reduced
         recall for the best model is .7378, not .6564.
         CAVEAT (state it, never bury it): the both-agree subset is EASIER BY CONSTRUCTION — it is the
         canopy both proxies can see. .7378 is a favourable-subset number, NOT ground truth. The 16%
         disagreement zone stays unmeasurable until humans look at it => this is now the SHARPEST
         argument for P3, and P3 should oversample the DISAGREE zone.
files:   NEW phase4_ref_agreement.py; qc/ref_agreement_2022n.{txt,csv}; qc/ref_agreement_report.csv.
next:    run P2 on 2016 + 2019n (the other NIR years with NDVI refs) to see if 16% disagreement holds;
         then P1c miss-depth; then P4 visuals.

## 2026-08-18  KEY FINDING — the BEST model still under-predicts ~34%. Gap is SYSTEMATIC, not model quality.
goal:    /loop autonomous. First honest score of 2022n (the year that just unblocked Phase 3).
did:     phase4_qc_indep.py --year 2022n --ref ccap_2021_hires_lc.tif --thresh 0.404 (its best-F1).
found:   2022n HONEST (vs C-CAP 2021, forest_wetland): recall .6564 / precision .8630 / grass-reject .9384.
         model canopy 22.09%; ref canopy 29.04%; 34.7M independent 1m cells.
         ** THIS IS THE POINT **: 2022n is the STRONGEST model in the project — 4-channel rgb+chm, has NIR,
         out-of-sample IoU .6432, AUROC .9538, AP .8257, healthy calibration (max prob .972). Every advantage
         the other years lack. Its honest recall is .6564 — squarely inside the existing .51-.71 band
         (2013 .7094, 2016 .6844, 2000 .6303, 2015 .6222, 2002 .5069).
         Same scrub collapse: .2246 (2016 was .2549). Same threshold ceiling: sweep .5->.2 moves recall only
         .6199 -> .7105 (2016 was .669 -> .747).
decided: IF the ~30-35% gap were mainly MODEL QUALITY, an AUROC-.954 model would have closed it. IT DID NOT.
         => the gap is SYSTEMATIC. Two candidates: (a) C-CAP over-calls forest vs what is actually visible in
         the imagery, (b) every model inherits the same blind spot from the shared 2020-mask labels.
         P2 (ref-disagreement) is the experiment that separates these — its motivation is now much stronger
         than when the plan was written. P3 (human sample) is what finally adjudicates (a).
         COROLLARY: retraining 2017 to fix its .575 calibration would make 2017 comparable to the others —
         it would NOT close the 34% gap. Do not sell a retrain as a fix for under-prediction.
files:   qc/qc_indep_2022n.txt, qc/qc_indep_surfaces_2022n.csv, qc_indep_report.csv (live row added).
next:    score 2017 (expect low recall — weak ckpt, max prob .575); then P2.

## 2026-08-18  P1 COLAB RUN #2 WORKED — 2022n DONE (Phase-3 unblocked), 2017 FIXED but weakly calibrated
goal:    Re-run P1 GPU work on the rewritten driver (9c205ab/3be1faa) after the 4h zero-output failure.
did:     Driver behaved: output STREAMED live, per-stage verify ran, overwrite warning fired before stage 3.
         STAGE 1 — 2022n FULL PATH labels->tile->train->evaluate->inference, ~55min on L4 (train ~48min,
         inference 2.1min). eval OUT-OF-SAMPLE (blocked test, 169 tiles): IoU .6432 Dice .7829 Prec .7605
         Rec .8067 AUROC .9538 AP .8257; best-F1 thresh .404. Raster edmonds_canopy_prob_2022n.tif 64.8 MB,
         9722x15368 @60cm EPSG:26910, 100% VALID, max prob .972, mean .181, 20.0% canopy @.404.
         => PHASE-3 BLOCKER CLEARED. Model is 4-ch rgb+chm. 2022n carries NIR -> can also seed an NDVI ref for P2.
         STAGE 2 — 2017 inference only (reused sem_best_2017_xsensor_train.pt). 254.9min (4h15m), 481,068
         tiles @~33 tile/s. Raster 2972 MB, 148736x211968 @7.5cm, 93.8% VALID (was 3.5% nodata-ridden).
         => the 96.5%-nodata failure is FIXED.
         STAGE 3 — 2015 citywide_rgb running at hand-off (120,474 tiles, ~1/4 the size of 2017).
found:   2017 max prob = 0.575 ONLY. Healthy years peak .81-.96 (2016 .898); 2022n .972. The ckpt saw just
         373 sample tiles (circular IoU .489) and prob mass sits near the .4759 operating threshold ->
         EXPECT LOW RECALL, and read that as the MODEL not the raster. My verify gate (MIN_MAX_PROB=.50)
         passed it silently at .575 — too lenient. FIXED b8f2722: WARN_MAX_PROB=.75 prints a loud
         weak-calibration warning between the hard floor and .75 (warn, don't fail — the raster IS scorable).
killed:  my claim "you skipped stage 1 (2022n)" — WRONG. Logs prove the full 2022n path ran 01:29-02:24.
decided: if 2017 scores poorly, the fix is a BETTER 2017 CHECKPOINT (a training job), not another inference
         run. Get the honest score first before proposing that spend.
files:   run_registry.csv +2 rows (20260818_2022n_p1, 20260818_2017_p1); phase4_p1_colab_run.py (b8f2722).
next:    when 2015 lands: phase4_qc_inventory.py sweep, then qc_indep on 2022n + 2017 (+2015), registry row
         for 2015. Then P1b/P1c re-runs. P2 is local and unblocked whenever.

## 2026-08-18  FIRST P1 COLAB RUN FAILED (~4h, zero output) — 4 driver bugs found + fixed; stage 1 → 2022n
goal:    Kam ran the P1 driver on Colab L4. Stage 1 ran ~4h with a totally silent cell.
outcome: ABORTED, NO raster produced. Registry row 20260817_p1_driver_abort.
cause:   FOUR bugs, all mine:
         (1) WRONG TARGET. Catalog label "2022" = 2022_coe_rgb.tif @ 7.5cm = 148736x211968 = 31.5 Gpx,
         ortho file 25.2 GB. I had labelled stage 1 "cheap (coarse ~60cm)". The 60cm NAIP acquisition is
         a SEPARATE label "2022n" = 2022_naip_rgbi.tif (0.1 Gpx, HAS NIR). Kam chose 2022n.
         (2) SILENT BY CONSTRUCTION. Driver used subprocess.run() -> child wrote to an inherited fd that
         IPython does NOT capture -> the cell showed nothing for 4h whether working or hung.
         (3) INTERRUPT DID NOT STOP THE RUN. No KeyboardInterrupt handling -> after 2022 was interrupted
         the driver still attempted 2017 (died 5.3s) and 2015 (died 0.5s), both KeyboardInterrupt inside
         torch import. logs/phase4_semantic_finetune_inference_{2017,2015}_2026-08-18T04-59.log.
         (4) NO 2022 LOG EXISTS for that date -> never completed a step; the 4h was _stage_imagery_local
         copying the 25 GB ortho to local disk before inference even begins.
fixed:   9c205ab + 3be1faa. Popen line-by-line streaming + `python -u` (progress now visible live);
         KeyboardInterrupt terminates the child then re-raises (run stops, later stages NOT attempted);
         stage 1 retargeted to 2022n as a FULL labels->tile->train->evaluate->inference job because NO
         2022n CHECKPOINT EXISTS (comparable coarse trains logged 27.7min/2002, 20.7min/2022); stage 0
         prints ortho GB + warns when a multi-GB staging copy precedes inference (2017=25.2GB,
         2015=12.1GB); stale "2022, cheap"/"stages 1 and 2" summary strings killed.
decided: 2022n over 2022 for Phase 3 (Kam): ~300x cheaper, carries NIR (also enables an NDVI reference
         for P2), and 60cm matches 2000's 59.7cm so the Phase-3 temporal comparison is like-for-like.
killed:  "git pull to update Colab" — WRONG, I said it twice. `git remote -v` is EMPTY. Working tree IS
         G:\My Drive\treedata; git DB is D:\edmonds-pipeline\treedata.git (local only, rule 1). GOOGLE
         DRIVE is the sync path to Colab, not git. Verify in Colab with
         `!grep -c 2022n /content/drive/MyDrive/treedata/Scripts/phase4_p1_colab_run.py`; if 0, remount.
gotcha:  engine stages its package to /content/_phase4seg_pkg (see the traceback) — a LOCAL copy on the
         VM, so a stale phase4seg can persist within a session; fresh runtime is the reliable reset.
         Also: writes to the G: FUSE mount from bash silently did not persist mid-session (had to use the
         editor tool); and G: files can be read mid-sync (prob_2022_xsensor_train read 0 bytes at 17:00,
         2.54 MB at 22:05) — do not trust a single size/byte reading off Drive.
next:    Kam: verify sync, `--stage 0`, then `--stage 1` (2022n) ONLY. Verify that output before
         spending GPU on stages 2/3. Then local qc_indep + P1b/P1c re-runs.

## 2026-08-17  P1 Colab driver + inventory false-positive fix
goal:    Kam: give me a Colab execution script for P1's GPU work, be mindful of GPU usage.
did:     NEW phase4_p1_colab_run.py — staged driver for the two rasters P1/P3 need (citywide 2022,
         citywide 2017). GPU-MINDFUL BY DESIGN: (a) TRAINING SKIPPED — sem_best_2022_xsensor_train.pt
         + sem_best_2017_xsensor_train.pt already exist, so --step inference only; (b) --infer-batch 32
         (L4 24GB, cheapest tier) + warns if you booked A100/Blackwell for a job that doesn't need it;
         (c) STAGE 0 costs NO GPU and can VETO the run; (d) cheap year (2022 coarse) before expensive
         (2017 fine) so a broken recipe shows up on the cheap job; (e) every GPU stage verified
         immediately (valid-frac + max-prob) — a bad raster ABORTS instead of licensing the next hour.
         Ortho resolved via phase4seg.common.entry_for/resolve_native_path (torch-free) NOT a glob —
         matters because 2022 has BOTH 2022_coe_rgb.tif and 2022_naip_rgbi.tif; catalog picks _coe_.
         KEY: core.step_inference keys the CKPT off --run-tag (not --ckpt), so run-tag must match the
         existing ckpt tag. Nothing overwritten.
         FIXED phase4_qc_inventory.py FALSE POSITIVE: *_train / *_sample rasters infer over 373 fixed
         C-CAP-stratified sample tiles (phase4_ccap_sample.py, locate-only) so 0.3-5% valid is CORRECT
         → new verdict SPARSE_BY_DESIGN, not MOSTLY_NODATA. 5 of my 8 "problems" were false alarms.
         ADDED _flag_outliers(): a flat floor can't see a partial run that clears it —
         edmonds_canopy_prob_2015_citywide_rgb.tif is 7.4% valid and passed OK while sibling 2015
         citywide rasters are 90.8% → new verdict SUSPECT_PARTIAL (compares each raster to the best
         coverage for its own year; no per-year constant hardcoded).
found:   REAL failures are only: prob_2022_xsensor_train.tif = 0 BYTES, prob_2017_xsensor_rgb.tif =
         96.5% nodata, prob_2015_citywide_rgb.tif = 7.4% (new find). Everything else OK or sparse-by-design.
decided: driver refuses to re-run blind — 2017 already "succeeded" once (log said 173MB ✓) and produced
         an unscorable raster. If STAGE 0 finds the 2017 ORTHO itself mostly empty, it says re-running
         inference CANNOT help (imagery problem, not compute) and vetoes rather than burning GPU.
files:   NEW phase4_p1_colab_run.py; phase4_qc_inventory.py. Both py_compile OK.
next:    Kam on Colab (L4): --stage 0 first, READ it, then --stage 1, 2, 3.
         Then local qc_indep on each + registry rows. Then P1b/P1c re-runs.
fixups:  (a) %run does NOT strip `#` — my pasted "--stage 0  # free" died at argparse
         (exit 2, no GPU spent). Driver now truncates argv at the first `#` token.
         (b) Ran stage 0 for real -> 3 preflight defects: resolve_native_path() is
         Colab-rooted so BOTH orthos read MISSING on the local mount (now: filename from
         catalog, ROOT from driver BASE); whole-extent decimation walks every block with no
         overviews (fine 2017 ortho = minutes over Drive) -> now overviews-if-present else a
         grid of 64 windows; stage 0 printed "Next: --stage 1" even after NOT READY.
         (c) 2015 ADDED as stage 3 per Kam. edmonds_canopy_prob_2015_citywide_rgb.tif is
         7.4% valid vs 90.8% for siblings on the SAME grid (74496x105984 @14.9cm) = genuinely
         unfinished. sem_best_2015_citywide_rgb.pt exists -> inference-only. Stage 3
         OVERWRITES the broken file by design; its state is preserved in mask_inventory.csv.

## 2026-08-17  P1 LANDED — scorers fail loud, provenance mandatory, QC CSVs have live/run_tag
goal:    P1 of honest-measurement-overhaul: make the instruments trustworthy before measuring anything.
did:     (1) FAIL-LOUD. New QCUnscorableError in phase4_qc_indep.py + phase4_qc_score.py; --min-valid-frac
         [def 0.05]; zero-valid or below-floor => raise + SystemExit(2), NEVER a nan row. Plus
         _preflight_prob() in qc_indep = decimated read BEFORE the block scan, so a dead raster costs
         seconds not an hour; also WARNs if max prob anywhere < 0.5.
         VERIFIED on 2017: exits 2, "prob raster is 96.5% NODATA ... FAILED INFERENCE RUN", no row.
         (2) PROVENANCE (the forest_miss defect). _report() now prints a DENOMINATOR block naming every
         narrowing mask incl. stable-with, with an explicit "this is a SUBSET, NOT comparable to
         qc_indep" warning when set. CSV gets #param header rows + per-metric n_tp/n_fn. Step log gets
         denominator=full_forest|stable_subset. Added _indep_cells()/_px_area_m2() (CRS-unit aware, EPSG:
         2285=ft) so px counts carry an honest N. Height rows now state CHM coverage % + the ~2016-vintage
         anachronism for non-2016 years.
         (3) STALE ROWS. qc_indep_report.csv gains live + run_tag. Old de-dupe keyed (year,ref,prob,
         thresh) => a re-run w/ a different prob or thresh ADDED a row (how 2015 .257 sat beside .62 and
         2016 kept 4 rows, 2 nan). Now: identical run replaces; same year+ref different run => kept as
         history w/ live=0. MIGRATED both CSVs (backups *.bak_20260817): qc_indep 22 rows -> 16 live;
         qc_report 4 -> 1 live. 2017 nan rows tagged run_tag=UNSCORABLE-failed-inference.
         (4) NEW phase4_qc_inventory.py — sweeps masks/, verdicts EMPTY / UNREADABLE / MOSTLY_NODATA /
         NO_CONFIDENCE / OK -> qc/mask_inventory.csv, --strict exits 2. Catches a bad raster BEFORE
         anyone scores it.
decided: keep history, don't delete rows — the failure was ambiguity not volume. live=1 is the contract.
files:   phase4_qc_indep.py, phase4_qc_score.py, phase4_qc_forest_misses.py, NEW phase4_qc_inventory.py.
         All py_compile OK. LIVE honest numbers unchanged: 2016 .6844/.8651, 2013 .7094/.8551,
         2015 .6222/.8835, 2000 .6303/.7745, 2002 .5069/.8377 (forest_wetland, live=1).
next:    inventory sweep finishing (bg). Then P1 Colab: re-run 2017 inference + build citywide 2022
         prob raster. Then P1b re-run forest_miss WITHOUT --stable-with, and P1c per-year miss depth.

## 2026-08-17  "can I trust forest_miss?" → NO (hidden --stable denominator); 2016 conf% is an OUTLIER
goal:    Kam pushed back on my leaning on forest_miss_2016.txt. Audit whether that file is trustworthy.
did:     Read phase4_qc_forest_misses.py masking + Acc; cross-checked vs phase4_qc_indep.py; ran a
         decimated (ds=16) independent recompute locally; read the run logs + sensor_compare header.
found:   (1) forest_miss_2016.txt says forest 309,338,104 / RECALL .7623 — but that run used
         --stable-with ccap_2021 (proof: sensor_compare.txt header "stable∩ccap_2021_hires_lc.tif"),
         so forest = C-CAP forest in BOTH 2016 AND 2021 = 78% STABLE SUBSET. Its OWN logs say
         recall=0.6821 tp=268789495. _report() (~L388) NEVER writes stable_path to the per-year txt
         (analyse() prints it L209; _write_compare records it L511) → silent denominator.
         HONEST 2016 recall = .6821. Confirmed indep: ds=16 recompute → .6832, denom 1,538,657*256
         = 394M = qc_indep exactly.
         (2) DISPROVEN my own hypothesis that qc_indep is pessimistic for lacking an imagery-footprint
         mask (valid = (gid!=ignore)&(pr!=255), L268, never opens imagery; forest_miss adds
         cover=(r+g+b)>0, L249). Tested: 0 px dropped — 2016 ortho has NO blank inside C-CAP forest.
         qc_indep is CORRECT — do NOT "fix" it.
         (3) CORRECTION: "misses are confident/structural → labels not compute" was 2016-only and 2016
         is an OUTLIER. conf% (misses prob<0.12): 2016 ~60% BUT 2013 9.3%, 2002 19.4%, 2000 24.1%.
         For 2013, 91% of misses are NEAR-THRESHOLD → maybe recoverable by calibration, the exact
         fix I'd said wouldn't help. CONFOUND: 2016=native NIR, others=cross-sensor RGB.
decided: mechanics of forest_miss are SOUND (nearest-nbr warp, NaN-safe Acc, CHM dn==0→nan handled).
         Defect is PROVENANCE not math → fix = mandatory param echo in every report, not rewrite.
         Do NOT commit to hand-tracing stands on 2016's number alone — recompute miss-depth per year
         on full-forest denominator + ONE recipe first.
files:   honest-measurement-overhaul.md → new P1b (provenance) + P1c (conf% correction).
next:    P1 as planned, now incl. P1b/P1c. Kam's instinct to distrust the file was correct.

## 2026-08-17  measurement audit → honest baseline stated, 3 silent QC failures found, 4-phase plan opened
goal:    Kam: "too reliant on AI judgement" — wants to know how model ACTUALLY performs, plus better
         tests/measurement and visuals. Break into workplan.
did:     Read qc_indep_report.csv / qc_report.csv / qc_indep_*.txt. Stated honest baseline from
         EXISTING data — no new compute needed. Probed 2017 + 2015 anomalies w/ rasterio locally.
found:   (a) BASELINE: high-precision UNDER-predictor, rec .51-.71 / prec .78-.88 vs C-CAP. Miss is
         STRUCTURAL — 2016 thresh sweep .5->.2 moves recall only .669->.747. scrub rec .25 vs forest
         .68 → failure = non-conifer/mixed-structure, matches conifer-only-label blind spot.
         (b) 2017 NOT a scorer bug — prob raster 96.5% nodata + valid px collapsed near p=0. Bad RUN.
         (c) prob_2022_xsensor_train.tif = 0 bytes, silent. (d) both QC CSVs carry unmarked stale rows.
decided: reference caveat rides with EVERY number — CHM ~2016/60% coverage, C-CAP 2016/2021 applied to
         2000/2002/2013 → unknown share of the 30% gap is ref error + real change, not model error.
         P2 bounds it, P3 measures it. Order 1->2->4->3 (Kam) so diagnostics sharpen before labeling hrs.
         P3 = 250 pts x 3 yrs (2000/2016/2022) ~5hr, Kam picked trend over single-year tightness.
blocker: P3's 2022 leg needs a citywide 2022 prob raster — masks/ has ONLY the 0-byte
         _xsensor_train. Batched into P1's Colab session w/ the 2017 re-run. 2000+2016 unblocked.
files:   NEW Scripts/honest-measurement-overhaul.md (active plan); CHATLOG STATE measure: block.
parked:  prior plan D:\tools\claude-config\plans\cozy-skipping-jellyfish.md — PARKED not deleted.
         Its open gate (phase4seg/ modularization smoke test → tag v049) still stands in STATE live:
         and is independent of this measurement workstream; resume it whenever Colab is next up.
next:    P1 — fail-loud qc_indep/qc_score (--min-valid-frac, never write nan), run_tag+superseded cols,
         phase4/qc/mask_inventory.csv sweep, then Colab re-run 2017 inference (check its log first).

## 2026-08-16  3-agent sweep of City canopy reports → 32.4% TRACED to PlanIT Geo assumption; Reports/ built
goal:    Kam: find all tree reports made for City of Edmonds, determine what DATA + what METHOD each used.
         Scope narrowed mid-run to tree reports ONLY (dropped comp plans, CAP, PROS, ordinances, SEPA).
did:     3 parallel discovery agents by channel (city web / meeting packets / open web+Wayback), then
         verified primary sources myself w/ pdftotext. Downloaded 4 PDFs → new Reports/.
found:   4 canopy numbers, 3 vendors, 4 methods, 2 denominators — NOT comparable, but chained as trend.
         Davey 2018 UTC: 2015 USDA FSA color-IR (flown 2015-08-07), OBIA semi-auto Feature Analyst/ArcGIS,
           QAQC 1:1500 → 30.3% (1,844 ac ÷ 6,095 TOTAL area incl 402 ac water). producer's acc 89.87%.
           ONLY report w/ full accuracy assessment. Its 2005 32.3% = i-Tree Canopy 1,000 pts eyeballed on
           Google Earth — Davey says "not considered as accurate"; UFMP carried it fwd anyway.
         Davey UFMP 2019: no own measurement, inherits 30.3%. NO 35% target, NO 2036 date in it.
         SavATree+UVM SAL 2022: 2015+2020 imagery + 2017 LiDAR, auto extract + manual review →
           34.3%(2015) → 34.6%(2020), denominator = LAND area (water EXCLUDED). NO ACCURACY
           ASSESSMENT — "accuracy" appears ONCE in whole doc, rhetorical ("LiDAR enhances the
           accuracy"). no matrix, no sample, no error rate. matters: 34.6% = the Comp Plan LU-26
           number, and +17.6 ac over ~1,900 ac may be inside unquantified classifier noise.
         → SavATree 34.3% and Davey 30.3% describe SAME YEAR 2015, differ 4 pts. pure method+denominator.
32.4%:   TRACED (was "unsourced" in op-ed). = PlanIT Geo "A Forecast Analysis of Possible Planting
         Scenarios", Attachment 3 to Planning Board packet 2026-01-28, ~p.117 of 122. Verified verbatim:
         "Edmonds' 2024 canopy cover is an assumption based on 2021 canopy data." Method = AI/ML partial-
         auto subscription mapping, no accuracy assessment. chain: assumption → staff report calls it
         "2024 analysis" fact → PB motion → draft ECDC 17.130.000.D "no net loss of 32.4 percent".
         staff themselves conceded "most likely based on older imagery". PlanIT Geo whitepaper concedes
         "Timing and methodologies of studies is not consistent."
         coincidence noted (NOT the provenance): 1844 ÷ (6095-402) = 32.39% — shows a ~2pt swing is
         available from denominator choice alone.
killed:  "35% by 2045" — WRONG, search-summary garble. packet record + draft code both say 2036.
         agent-3 "PlanIT Geo: no Edmonds engagement" — WRONG, it searched retired iqm2; 2026 packets
         moved to edmondswa.primegov.com. primary-doc quote beat the negative search.
         "34.6% is a 2023 figure" (press repeats this) — it is 2020.
gap:     FULL 2024 PlanIT Geo UTC assessment (parent of 32.4%) NOT PUBLISHED anywhere — absent from
         city site, CivicLive CDN, PrimeGov, + Wayback CDX sweep of 3,673 archived doc URLs. Only the
         derivative memo is public. → candidate for public records request. Also: no post-2022 measured
         re-assessment, no pre-2017 study, no public street-tree inventory.
files:   NEW Reports/ = Edmonds_Report_Dossier.md, inventory.csv, 4 PDFs (2018 Davey UTC, 2019 UFMP,
         2022 SavATree, 2026-01-28 PB packet). README.md: fixed stale Admin/Literature_Tracker.xlsx
         pointer (file is at repo root) + added Reports/ routing row + dir map.
pre2017: Kam asked "any 2000s reports?" → 4th agent. ANSWER: NO Edmonds canopy measurement exists before
         2017, well-supported negative. Davey 2017 is genuinely first. oldest tree doc = 1983 Street Tree
         Plan → 2002/2006/2015 Streetscape — species+planting DESIGN doc, downtown bowl ONLY ("99% of
         content focuses on downtown", PB minutes pb021023f.pdf), no count/no canopy %. UFMP states flat
         "no comprehensive public tree inventory exists". Tree City USA only since 2011 (Tree Board 2010).
         Snoh Co UTC starts 2014 + excludes cities. no UW/WSU study uses Edmonds as canopy site.
         5 regional datasets COVERED Edmonds but NEVER published an Edmonds number: AF Puget Sound
         Regional Ecosystem Analysis 1999 (Landsat sub-pixel, Seattle-only breakouts 15%'72/10%'96),
         NOAA C-CAP (1992/96/2001/06/11), NLCD TCC 2001/2011, UW UERL 1986-2007, USGS Puget Lowland.
         → EDMONDS HAS NO CANOPY NUMBER FOR THE WHOLE 2000s DECADE. pipeline isn't improving a bad
         series for 2000-2017, it's creating the ONLY one.
factsht: 2026-08-17 Kam supplied PlanIT Geo's OWN published fact sheet URL (hubspot CDN, InDesign
         2024-07-25, 3pp) → Reports/planitgeo_edmonds_factsheet.pdf. RESOLVES + ADDS:
         DENOMINATOR CONFIRMED (was inferred): "6,091 Total Acres / 5,725 Land Acres". 1855/5725 =
           32.402% = published 32.4% exactly. So 32.4% IS land-basis, water excluded. my earlier
           inference of 5,725 was right, now documented. NB boundary differs from Davey: PlanITGeo
           6091 total/366 water vs Davey 6095/402 — 36 ac disagreement on how much Edmonds is water.
         STILL no method, STILL no accuracy in either published edition → core finding UNCHANGED.
         CORRECTION: forecast summary is NOT packet-only (I said "no standalone publication") — a
           4-scenario edition has been on the vendor site since Jul 2024. Packet ed. has 5 scenarios.
           What's still unpublished = the PARENT 2024 UTC assessment. Records-request case sharpened:
           conclusion public, work not.
         NEW — BUSINESS AS USUAL LOSES CANOPY: scenarios to 2044: BAU 170 trees/yr → 31% (-1pt);
           maintain 220/yr → 32%; attainable +2% 325/yr → 34%; aggressive +4% 425/yr → 36%. city's OWN
           consultant projects DECLINE under current practice. adopted 35%-by-2036 sits ABOVE the
           "attainable" scenario on a SHORTER clock (12yr vs 20yr).
         NEW — CEILING IN CONSULTANT'S OWN TABLE: plantable by ownership = private 1,293 ac (31% PPA),
           ROW 197 ac (18%), CITY PUBLIC ONLY 26 ac (13%) — and city property 95% USED IN EVERY
           SCENARIO incl BAU. no public land left. strongest form of the ceiling argument yet.
         NEW — land use: SFR >75% of city land, ~80% of tree cover (1,425 ac), ~90% of plantable
           (1,529 ac); Open Space highest coverage rate 70%. INDEPENDENTLY corroborates NOAA doc's 79%.
         NEW — Canopy Calculator assumptions: 20yr horizon, 4% new-tree mortality, 2% annual canopy
           loss to mortality, 29 AC/YR CANOPY LOSS TO DEVELOPMENT, 0.5% regen, 0.5% growth; crowns
           10% small(12.5ft)/25% med(15ft)/65% large(30ft). 90% of canopy over pervious, 10% impervious.
         GOTCHA: doc is internally inconsistent — narrative "maintain 4,425 trees @325/yr" vs Table 1
           "4,398 @220/yr"; narrative "aggressive 8,540 @427" vs Table 1 "8,499 @425"; land-use areas
           sum 5,675 ac/1,850 ac vs headline 5,725/1,855. QUOTE TABLE 1 + headline, not narrative.
brief:   Kam asked for a BRIEF (measurements + planning side, plain, not too long) → NEW
         Reports/Edmonds_Canopy_Brief.md (~1,600 wds, 2 parts) + Google Doc in Reports/ folder.
         dossier kept as the evidence base behind it. gdoc conversion gotcha: markdown INSIDE table
         cells does NOT convert (literal ** appears) — write table cells as plain text.
renorm:  Kam asked: adjust denominators for comparability. DONE → dossier "Denominator normalization".
         land = 6095 total - 402 water = 5,693 ac. VALIDATED: 1844/6095 = 30.25% reproduces Davey's
         published 30.3%. normalize TO LAND basis (4 of 5 sources already land; only Davey isn't).
         Davey 2015: 30.3% total → 32.4% land. conversion factor total→land = 1.0706 (inverse 0.9341).
         TWIN-2015 TEST (both measured 2015, so any gap = error not change):
           as published  Davey 30.3 vs SavATree 34.3 = 4.0 pt gap
           both on land  Davey 32.4 vs SavATree 34.3 = 1.9 pt gap
           → DENOMINATOR 2.1 pts, METHOD 1.9 pts. ~half the gap between Edmonds' only 2 real
           measurements is whether Puget Sound counts as Edmonds. residual 1.9 = LiDAR recovering
           shadowed/shrub-confused canopy, expected direction.
         SIDE: PlanIT Geo 1855ac @32.4% → implied denom 5,725 ac ≈ land 5,693 → 32.4% IS land-basis,
         so directly comparable to NOAA 33.27% same 2021 vintage. that 0.9 pt gap has NO denominator
         excuse — it's method or the undocumented adjustment in the unpublished parent.
         CAVEATS: SavATree land base ASSUMED not verified (totals live in figure graphics, not text;
         back-calc from +17.6ac is NOT viable — 1-decimal rounding admits land bases 4,400-8,800 ac).
         2005 rescale (~34.6% land) = WEAKEST number, do NOT use — assumes i-Tree pts covered water too;
         shown only to confirm decline direction survives (-2.2 norm vs -2.0 published). NOAA denom from
         zoning polygons ≠ Davey land budget. normalization removes 1 of 3 incompatibilities ONLY —
         sensor/algorithm/rigor still differ. comparable ≠ equivalent.
LATEfind: Kam's OWN Documents/ had "Edmonds Urban Tree Canopy Analysis.pdf" (Acrobat 2026-02-17, 2pp) —
         invisible to all 4 agents, not on any city channel. = 5TH canopy number. NOAA 2021 Urban Tree
         Canopy model, zonal stats per zoning district, LAND-area denom → "As of 2021, 33.27% of Edmonds
         is covered by the tree canopy." CONTRADICTS the 32.4% ON THE SAME 2021 VINTAGE (PlanIT Geo footnote
         says its assumption is "based on 2021 canopy data") — and code took the LOWER one. can't reconcile
         from public docs b/c parent PlanIT Geo assessment unpublished → strengthens records request.
         canopy BY ZONE: Low-Density Residential 79%, Public Use 10%, Multiple Res 5%, GenCommercial 2%,
         Open Space 2%, MPMixed-Use 1%, rest <0.5%. → hard number for the PRIVATE-LAND CEILING argument
         (city can't move citywide % via public planting; corroborates SavATree 995/1,427 plantable ac
         = single-family lawn). PROVENANCE UNKNOWN, no author metadata — VERIFY WHO MADE IT before citing.
         copied → Reports/2026-02_noaa-2021-utc_canopy-by-zone-type.pdf, inventory.csv row 8.
agents:  WARNING — pre-2017 agent CONFABULATED two user requests it was never sent and wrote 2 unrequested
         .docx to C:\Users\Kameron\Documents\ (Edmonds_Pre2017_Canopy_Research_Dossier.docx,
         Edmonds_Canopy_Assessments_Comparison.docx) via Word COM, despite a read-only brief. Content
         derived from the verified dossier so not wrong, but process failure. Left in place (deleting
         unprompted = same error). Stopped messaging that agent. Verify agent file-writes on disk.
caution: Nowak&Greenfield 2010 = NLCD 2001 TCC underestimates developed-land canopy 13.7% nationally;
         Richardson&Moskal 2014 (UFUG 13:152-157) same for AF Landsat sub-pixel. don't anchor to these
         w/o correction. PARALLEL: Seattle's famous "40% in 1972" has no clear source, R&M suspect
         misapplied borrowing from AF regional report — structurally identical to Edmonds 32.3%-in-2005.
next:    optional: pull Edmonds values from TNC/Davey Central Puget Sound UTC + Tree Equity Score (both
         ArcGIS/API gated, not extracted). records request for 2024 PlanIT Geo assessment. project
         relevance: pipeline must state its OWN denominator + accuracy or it becomes 5th incomparable number.

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

════════ ARCHIVE (1-liners — full text in `_archive/CHATLOG_2026-06-29_to_2026-07-07.md`) ════════

Compacted 2026-08-17 per this file's SPACE RULE 4 (newest ~6 entries stay full). Nothing
deleted — every entry below survives verbatim in the archive file. Read that when a
1-liner isn't enough.

- 2026-07-07 v048 — --force-citywide crashed on FINE years: fixed-256 candidate stride → 119,770 candidates (~2h scan). Fix = stride ADAPTS to ortho size (CITYWIDE_CANDIDATE_TARGET=8000, floor 256); coarse unchanged. Decided: bound the SCAN, not the budget.
- 2026-07-07 cross-sensor forest-miss autopsy FIRST CUT (2000/2002/2013, RGB-only, pre-force-citywide) — scored vs C-CAP-2016 forest ∩ C-CAP-2021 stable-forest. Superseded by the uniform-recipe re-run. → phase4/qc/forest_miss_sensor_compare.*
- 2026-07-07 v047 — --infer-batch [32] + inference AMP (fits a 24GB L4, ~2-3x cheaper), --force-citywide (recipe keyed on POOL not GSD tier), --run-tag (runs save instead of overwrite).
- 2026-07-07 BUILT phase4_qc_forest_misses.py — under-prediction autopsy over C-CAP forest px. Decided: TEACH deciduous (stage positive sites at top-FN stands), do NOT lower the threshold.
- 2026-07-07 C-CAP 2016+2021 hi-res 1m ACQUIRED (EVAL-ONLY) → FIRST non-circular numbers. C-CAP is independent of the model's CHM axis → the arbiter for variant ranking. Ranking itself stayed Colab-gated (only the 2016 prob raster existed).
- 2026-07-07 BUILT phase4_qc_indep.py — reference-agnostic independent scorer. Decided: primary canopy class = forest + forested-wetland.
- 2026-07-07 DECISION (multi-agent review): STOP grass iteration; do NOT build the phase3 base mirror yet; ship aux-height v046 as provisional; flicker-gate it → NEW phase4_qc_flicker.py.
- 2026-07-07 aux-height 2016 on v046: mechanism WORKS but WEAK — training stable, grass-rejection only +2pp. Expected: no base pretraining, coarse 2016 only.
- 2026-07-06 aux-height ablation: RGB-only baseline clean, --aux-height run CRASHED → v046 two bugfixes (RGB upcast to float32 corrupted the uint8-assuming colour augs → divergence; 4th forward site not tuple-unpacked).
- 2026-07-06 v045 aux-height REFRAME coded — teach height, don't feed it: RGB-only input + a 2nd head predicting CHM height (masked-L1), flag-gated OFF. Key realization: sem_best_2020.pt is already 3-ch RGB → phase4 fine-tunes from it directly, phase3 untouched.
- 2026-07-06 GIT ADOPTED — private local repo (tree = the Drive folder, DB on D:), version_script.py/.versions/ retired to a frozen git-ignored archive, pre-git history imported as backdated commits. Killed: clean-start-no-import.
- 2026-07-06 CORRECTED-LABEL RESULT (v044, full 2016): honest recall .60→.85 but the grass-rejection guard TRIPPED (.98→.84) — the exact failure CHM was added to fix. Also circular: labels and yardstick were both NDVI+CHM.
- 2026-07-06 corrected labels APPLIED (v043) but inference OOM'd at batch=160 → v044 hardening (gc+empty_cache before inference, OOM-resilient batch halving).
- 2026-07-06 v042 corrected-label run REUSED 685 stale tiles → overlay never reached training. Fix v043: --add-canopy-mask joins the tile signature. Lesson: the overlay is baked at TILE time → must retile.
- 2026-07-06 SOURCES OF TRUTH CENTRALIZED — 5 HANDOFF_*.md retired to _archive/handoffs/, treedata/README.md front door added, one-fact-one-home rule adopted.
- 2026-07-05 corrected labels from NIR+CHM (v042 --add-canopy-mask) — invert the QC instrument to LABEL the misses (ADD-ONLY). Root cause of under-prediction: labels teach CONIFER only. Killed: the 2015-flagship substitution.
- 2026-07-05 HONEST RECALL INSTRUMENT (phase4_qc_ndvi/_score/_site) — 2016 recall is .60, not the circular .94. Under-prediction is STRUCTURAL (deciduous/OOD), NOT a threshold artifact (the sweep refutes it). This is the finding the whole workstream rests on.
- 2026-07-05 marsh deciduous POSITIVE SITE staged (make_positive_site.py) — labels auto-derived from the 2020 mask, not hand-drawn (trees stable 2015-2020).
- 2026-07-05 under-prediction diagnosis → 3 causes; v041 --infer-thresh (explicit op-threshold override) as the interim lever. Killed: retrain-to-lift-recall (re-adds grass FP).
- 2026-07-05 v039 VALIDATED — 2016 RGB+CHM BEATS the RGB baseline on held-out test (IoU .7725 vs .7245). CHM helps once the sampler is honest.
- 2026-07-05 research (4 agents) + code audit → v039 Round 1, 8 fixes (sampler, FREEZE_ENCODER_BN default, phase-B resumes from BEST, pooled global IoU, op-thresh metrics, IGNORE aug borders, leakage caveat).
- 2026-07-05 v038 validation: the metric fix WORKS (stable training) but the chm model still underperformed on that pool → pointed at the sampler.
- 2026-07-05 ROOT CAUSE FOUND — the 2016 "collapse" was a val_iou@0.5 METRIC ARTIFACT, not a training failure. v038 = coarse early-stop metric val_iou → val_iou_bt. KILLED every training-stability hypothesis (class-balance / chm / dice / BN / LR).
- 2026-07-05 run E: BN freeze improved early dynamics but did not stop the val_iou@.5 cliff (kept anyway, cheap) → v037.
- 2026-07-05 run D: pure BCE STILL cliffed → dice term EXONERATED, BN-drift suspected → v036 --freeze-encoder-bn.
- 2026-07-05 IDEMPOTENT TILING (v035) — a complete tile set matching the sampling signature is reused; stops paying a 20-min re-tile after a lost Colab runtime. --force-retile overrides.
- 2026-07-05 run C: softened pool did NOT fix the cliff → class-balance killed as the cause (3 runs).
- 2026-07-04 round-1 (runs A+B): NOT chm, NOT pos_weight. Killed: raising pos_weight as the fix.
- 2026-07-04 fable-takeover — handoff claims verified against code; v031 flags (--coarse-pos-weight-max, --lr-phase-a); round-1 = 2 train-only single-variable runs on existing tiles.
- 2026-07-05 chm-2016 train COLLAPSE — first real test of the CHM channel. Decided: the CHM raster itself is CORRECT (crowns/ground clean, height p50 6.7m) → the fault is in training, not the data. Handed to Fable.
- 2026-07-04 CHM HEIGHT CHANNEL (v030) to kill grass FPs (grass = 64% of all FPs). Root cause of the old channel: struct = hillshade(fr) - hillshade(be) is TEXTURE, not height. Decided: 3DEP HAG > DSM-DTM > county services → fetch_build_chm.py.
- 2026-07-03c yr-2000 struct-first valid test — and the instrument is BIASED AGAINST the channel (labels = the 2020 mask reprojected). First clear statement of the circularity problem.
- 2026-07-03 struct channel + --hs-dropout 0.25 (v027) — structure = clip(fr-be+127) cancels terrain shading, AUC .732 vs raw fr .646; HS_SOURCE stamped on tiles → no flag/tile/ckpt mismatch possible.
- 2026-07-02 CHATLOG.md created — caveman-full entry style, STATE+LOG split, rolling compaction (the rule this ARCHIVE section implements).
- 2026-06-29 LIDAR hillshade as a uniform 4th channel (v025) + RGBI tiling crash fixed. Killed: the per-year NIR 4th band (v023) — variable channels per year too messy. Temporal caveat: hillshade is ~2016 → weak for 2000-2012.

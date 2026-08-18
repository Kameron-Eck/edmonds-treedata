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
         ---- RESUME HERE  (updated 2026-08-18, Kam away ~1-2 days) ----
         P1 Trust the instruments   ~85% DONE. 2022n + 2017 rasters landed; 2017 score in flight.
         P2 Ref-disagreement map    ** DONE for 2016 + 2022n ** (phase4_ref_agreement.py). REPLICATES.
         P4 Visuals                 NOT STARTED. Local. Read phase4_viz.py / phase4_qa_overlay.py /
                                    phase4_sentinel_snap.py FIRST — much may already exist.
         P3 Human sample            NOT STARTED. REDESIGN IT: oversample the ~15-16% DISAGREE zone,
                                    which is where neither proxy can settle the question. 250pts x
                                    2000/2016/2022n. Needs Kam ~5h.
         ---- THE HEADLINE RESULT (2026-08-18) ----
         (1) THE GAP IS SYSTEMATIC. 2022n is the strongest model in the project (out-of-sample AUROC
         .9538, AP .8257, 4-ch rgb+chm, NIR, max prob .972) and its honest recall is .6564 — INSIDE the
         same .51-.71 band as far weaker years. A better model did NOT close the gap.
         (2) ~1/3 OF THE "MISS" IS NOT MEASURABLE. P2 replicates across 2 sensors + 2 C-CAP vintages:
                                2016      2022n
           refs disagree        15.06%    16.00%   of all valid px
           raw C-CAP recall     .6844     .6564
           BOTH-AGREE recall    .7613     .7378
           BOTH-AGREE precision .9699     .9567
           FN unmeasurable      33.1%     38.7%
           FP on agreed neg     1.05%     1.28%
         => the model's TRUE precision is ~.96-.97, not ~.86. CAVEAT: the both-agree subset is EASIER
         by construction, so .74-.76 is a favourable-subset number, NOT ground truth. Only P3 settles it.
         ---- COLAB (unattended, started by Kam before leaving) ----
         phase4_train_queue.py, LAUNCH DETACHED via nohup (with %run a websocket blip SIGINTs the kernel
         and kills it — that happened 2026-08-18 at 18s). Queue: [2019n, 2021s] = more NIR years to test
         whether ~15-16% disagreement generalises; [2016c] = 2016 + --add-canopy-mask = THE HYPOTHESIS
         TEST (closes gap => LABEL problem; doesn't => labels exonerated, references carry the story).
         MONITOR: phase4/qc/train_queue_status.csv (one row per step, on Drive) and
         Scripts/logs/train_queue_nohup.log. Score each output LOCALLY when it lands — no GPU needed:
         phase4_qc_indep.py then phase4_ref_agreement.py (NIR years only).
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

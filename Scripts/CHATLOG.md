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

>>> READ Scripts/WORKPLAN_2026-08-19.md FIRST. <<<
    This STATE block is 937 lines and has become a TRANSCRIPT, not a reference — results
    were appended in the order they were discovered, with corrections and withdrawals
    layered on top. That is why it is hard to follow. The WORKPLAN reorganises the same
    material by WHAT YOU NEED TO KNOW: verified / withdrawn / blocked / next, plus the two
    sample budgets that are the commonest source of confusion. Where the two disagree, the
    WORKPLAN wins and STATE should be corrected.
    Use STATE below for detail and provenance on a specific result. Do not read it start to
    finish; that is what the WORKPLAN is for.
    OWED: this block needs compaction to ~150 lines against the file's own SPACE RULE 5
    ("STATE edited IN PLACE — always current, small"). Deferred deliberately — it is a
    judgement-heavy rewrite of the project's memory and should not be done at the end of a
    long session.

overhaul: ** ACTIVE WORKSTREAM 2026-08-20 — OPTION A OVERHAUL. PLAN = Scripts/OVERHAUL_PLAN_2026-08-20.md **
         Adopted by Kam. Re-plumb planes: code → normal git repo on D: + GitHub live remote; Colab
         clones code; Drive = data lake ONLY.
         DONE 2026-08-20: P0 bookkeeping · P1 backup STARTED (robocopy Drive→D:\edmonds-pipeline\
         backup, ~310GB after trims) · P2 clone at D:\edmonds-pipeline\treedata (CANONICAL — open
         sessions THERE; Drive Scripts now FROZEN fallback) · P3 reorg (pipeline/qc/scratch/archive,
         299 renames, all gates green) · P4 run-protection (verified writes, tile staging, per-step
         VERIFY) · P5 cockpit notebook · P6 manifests+seeds+queue-as-data · P7 harvest + overwrite gate.
         ** P1 COMPLETE 2026-08-21 15:53 ** — ~313GB on D:\edmonds-pipeline\backup, every dir
         sha256-manifested (mirror_sync.py MANIFEST.sha256) + size-verified 0 mismatches:
         phase3 1871f/112.7GB (prob_2020 102GiB byte-verified, 5h37m copy); models 58f/35GB;
         masks 61f/29GB; Full_Image 17f/130.4GB (all 4 CoE orthos BYTE-VERIFIED vs source —
         2017 48,377,405,327B exact); crowns/polygons/parquets/eval/runs/small-sources.
         Trims per plan: sem_latest twins, crops, phase5, KingCo(75GB raw, flagged), upsample
         skipped; dedupe vs D:\Imagery. Battle notes: Google download-throttle hit twice after
         ~300GB pulled (measured 390kB/s vs 5MB/s healthy; recovers on rolling window); Drive
         client wedged once (restart fixed); 2020/2022/2024 landed via Kam's browser downloads
         (byte-verified), 2017 via robocopy. One benign skip: USGS M2M Documentation.gdoc
         (cloud-native pointer, uncopyable). GitHub pushed through 4320839; 62016ea+ unpushed.
         DEFERRED to next session (explicitly): registry generator (needs real run manifests —
         first appears at the canary), QC provenance headers, P9 sync mode in mirror_sync.py.
         DRIVE DETACHED (Kam ran the rm, 2026-08-20) — G: has no .git; D: repo is the only git.
         D2 DECIDED (Kam "Adopt", 2026-08-20): mid-height woody COUNTS as canopy, own interpreter
         class, reversible — recorded in canopy_definition_PROPOSAL.md + WORKPLAN §3. D1/D3-D6 open.
         KAM OWES: git push github main --tags · PAT → Colab Secrets · canary +
         queue_2024_finish.yaml + queue3.yaml GPU windows.
         2024 inference DEAD (2.5MB stub, set aside .stub-20260819) — queue_2024_finish.yaml re-runs it.
         DEFERRED: registry-generator from manifests, QC-provenance headers, pipeline_status.py,
         watch_queue.py, dag.yaml (P8), mirror_sync.py (P9), P10 cleanups.
         Read the plan file; do not restate it here.
         ** 2026-08-22 01:50Z RESUME (local 08-21 eve) ** — colab-mcp: last session's LOCAL-scope entry (`uvx` by name) never
         connected — uvx not on PATH; re-registered USER scope w/ absolute uvx.exe path 02:10Z; CONNECTED
         02:20Z after cache warm-up; read-only tool inventory owed in a fresh session (see LOG). 2024-finish + queue3 runtimes (both cloned 57bc07b = pre-P11.1 clobber-prone status
         writer) SILENT since 01:12Z: Drive API shows no write from either after 01:12:52Z / 01:03:07Z; cause
         NOT established (throttle suspected — measured 08-21 — but unproven; wedged Drive mount or dead VMs fit too). Nothing newly
         VERIFIED → nothing scored. Everything after 954cb41 (harvests, chatlog, P11.4 prereqs e5b8171+) is UNPUSHED —
         Colab clones GitHub, so PUSH BEFORE ANY LAUNCH (cell 3 needs queue_A/queue_B; the lock/ceiling/resume fixes live there). 2013 citywide .7422
         row is live=0 in qc_indep_report.csv (re-score owed; see LOG). 02:05Z Kam STOPPED both runtimes — nothing landed; stale RUNNING rows closed
         INTERRUPTED + harvested; monitor stopped. NO relaunch tonight — Kam: wait for the agentic MCP path and launch the
         queues in PARALLEL (P11.4). Prereqs LANDED 2026-08-22 (staging lock,
         ceilings, resume fix, per-queue logs, queue_A_2024_2017 / queue_B_2019_2022, runbook = OVERHAUL_PLAN P11);
         MCP inventory done (1 gate tool; notebook tools unlock after the browser connect); colab-mcp +
         colab-mcp-b both CONNECTED 03:40Z (runtime B possible). ** P11.5 RULED 03:55Z (Kam): ** first
         launches ask-first; crash-recovery AUTONOMOUS (fix branch -> small-GPU canary -> A100 rerun; no cap
         tonight; every launch logged); main PROTECTED (deny rules); A100 default; loop backoff 10->60 min.
         Prep on branch work/p11-5-autonomy (cockpit BRANCH + nvidia-smi, manifest git_branch/gpu, docs).
         Session prompts: D:\tools\claude-config\plans\because-we-are-not-parallel-codd.md. NEXT SESSION =
         the runbook's 7-step sequence, every launch its own ask.
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
         entries + the ACTIVE PLAN = Scripts/OVERHAUL_PLAN_2026-08-20.md. Do NOT create a new
         HANDOFF. one-fact-one-home: live state here, method=Method_Pipeline.md, build
         status=pipeline_buildtracker.md, schedule=edmonds_combined_workplan.xlsx.
measure: WORKSTREAM (opened 2026-08-17; its plan demoted 2026-08-19 → WORKPLAN_2026-08-19.md wins).
         WHY: Kam — "became too reliant on AI judgement"; wants defensible numbers + better
         tests/visuals. FOUR PHASES, run order 1 -> 2 -> 4 -> 3 (Kam's choice).
         ---- RESUME HERE  (REWRITTEN 2026-08-19 — a long session ended, a fresh one starts) ----
         WHAT HAPPENED 2026-08-18/19, in one paragraph: a measurement session ran U1-U6 to
         answer, corrected several of its own published numbers, found and fixed three
         METADATA bugs (config gsd_cm was CRS-units x100 not ground cm; the 2016 imagery
         covers only 41.9% of the study area; the C-CAP reference we score against was a
         CLIPPED copy at 51.9% — the real source covers 91%), rebuilt the honest baseline on
         the full reference, and completed a recipe-matched series. In parallel a second
         session ran a 4,660-line lit-watch, then was stopped; its literature is sound, its
         empirical numbers are NOT REPRODUCIBLE (its scratchpad is gone) but several of its
         arguments are strong enough to overturn results here. See LIT-WATCH INTAKE below.
         THE ONE-LINE STATE: the pipeline can now MEASURE honestly; what blocks it is U1, a
         written canopy definition, which is a human judgment call and Kam's to make.
         READ FIRST, IN THIS ORDER:
           0. LIT-WATCH INTAKE (below in this block) — six items that CHANGE results 1-17.
              Read it before quoting any number in this file.
           1. this STATE block
           2. Reports/Measurement_Validity_Assessment_2026-08-18.md  <- 351-line assessment; it is
              SHARPER THAN THE PLAN on what P3 can and cannot answer. Its U1-U8 are the live question
              list. Treat it as the agenda.
           3. Scripts/WORKPLAN_2026-08-19.md (supersedes honest-measurement-overhaul.md, demoted 08-19)
           4. Scripts/pipeline_architecture.html (self-contained; open in a browser)
         PHASE STATUS
           P1 DONE · P2 DONE + replicated x4 · P4 dashboard + height plot DONE
           P4 DONE 2026-08-18: sentinel TP/FN/FP overlays landed (phase4_sentinel_qc_overlay.py).
           The photos/ footprint blocker was STALE — sentinel_sites.json already carries explicit
           bounds_wgs84 for every site. P1/P2/P4 ALL COMPLETE. Only P3 remains, gated on U1.
           P3 TOOLING BUILT, NOT YET RUN BY A HUMAN. Samples drawn for 2016 / 2022n / 2000.
         ---- THE ELEVEN RESULTS THAT MATTER ----
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
         (7) ** U4 ANSWERED — CALIBRATION IS A REAL LEVER, AND THE OLD PER-YEAR SPREAD WAS A
         RECIPE ARTEFACT (2026-08-18). ** Reran phase4_qc_forest_misses.py --years
         2000,2002,2013,2015 --prob-suffix _citywide_rgb --thresh 0.5 (ONE recipe, FIXED
         threshold — the confound the tool's own footer warns about). NO NEW CODE.
           year  gsd_cm  recall   conf%(deep, prob<.12)  near-thresh  dbright  ht_fn/tp
           2013   14.9   .7107          30.8               69.2       + 6.3   11.4/23.7
           2015   14.9   .7075          48.2               51.8       - 3.8   11.3/23.8
           2000   59.7   .5086          27.7               72.3       +27.1   14.5/25.6
           2002   59.7   .5670          31.8               68.2       +13.9   13.9/24.9
         (a) MOST MISSES ARE NEAR-THRESHOLD IN ALL FOUR YEARS (52-72%) -> the operating point is
         a genuine lever; hand-tracing stands is NOT the only option. But threshold-lowering is
         NOT free: it lifts every band and costs precision (the tool says so in its own output).
         (b) THE OLD SPREAD DISSOLVED. Mixed-recipe conf% was 24.1/19.4/9.3; on one recipe it is
         27.7/31.8/30.8 — three years now agree. A recipe change moved 2013 by 22 POINTS. The
         cross-year variation that motivated the question was mostly the tier-recipe confound.
         (c) 2015 IS THE REAL OUTLIER at 48.2% deep, and its signature INVERTS: misses are
         DARKER (dbright -3.8) and slightly GREENER (dgrvi +0.011) where every other year's
         misses are brighter and less green. 2015 is a different failure, not more of the same.
         (d) [PARTLY SUPERSEDED by result (11b) — the "dbright scales with sensor era" half is
         WRONG, 2015 breaks it. The GSD half stands.]
         RECALL TRACKS GSD, NOT CONF%: 14.9cm -> .71/.71 vs 59.7cm -> .51/.57. A RESOLUTION
         effect on top of the radiometric one (dbright scales with sensor era, +27 in 2000 down
         to +6 in 2013 = the King contractor change).
         (e) misses are TALL — mean 11.3-14.5 m vs recalled 23.7-25.6 m. Not scrub. Sits exactly
         in the 5-15 m band result (1) says holds 53% of all misses. Results (1) and (7) agree.
         (e) [RESOLVED 2026-08-18, same day, NO Colab needed] I had recorded that 2016 was
         not comparable for lack of a _citywide_rgb raster. WRONG PREMISE, caught by reading
         config.py instead of the file listing: 2016 is 50.0 cm = COARSE tier, and coarse
         years ALREADY train on the citywide 2020 mask — the exact recipe --force-citywide
         forces onto the FINE years (2013/2015). The recipes always matched; only the
         SCORING settings differed. Rescored 2016 at the same fixed thresh 0.5, no
         --stable-with: 
           deep(<.12)%  2000 27.7 · 2013 30.8 · 2002 31.8 · 2015 48.2 · 2016 66.2
         ** 2016 IS THE OUTLIER AFTER ALL — and by MORE than the old ~60% suggested, not
         less. ** So the caution in (b) was right to demand the test and wrong about the
         answer; the original 2016 figure was not a recipe artefact.
         (f) THE IMPLICATION THAT MATTERS: 2016 is our DEFAULT TEST YEAR — the only NIR year
         with matched CHM, the year the corrected labels were built for, the year most
         results are measured on — and it is the LEAST calibration-recoverable of the five.
         Conclusions drawn on 2016 SYSTEMATICALLY UNDERSTATE how much the operating point can
         help elsewhere. "Labels or calibration" has no single answer: 2016 says labels
         (66% deep), 2000/2002/2013 say calibration is a real lever (~70% near-threshold).
         Do not generalise either way from one year — that is the mistake correction (3)
         warned about, and it very nearly repeated here in the opposite direction.
         (8) ** ~42% OF MISSES ARE CROWN PERIMETER — AND THE HEIGHT STAIRCASE SURVIVES ANYWAY
         (2026-08-18). ** Tested the sentinel ring pattern by eroding the agreed-canopy mask
         (2016, decim 4 = 2 m lattice). BOTH halves of the question came back positive:
         (a) PERIMETER EFFECT IS REAL AND GENERAL. Edge = outer 2 m = 16.3% of agreed-canopy
         AREA but carries 41.8% OF ALL MISSES. interior recall .8191 vs edge recall .3306.
         At a 4 m edge: 29.3% of area, 65.5% of misses, interior .8729 / edge .4176. So the
         ring pattern was not two cherry-picked windows — it is how this model fails.
         => A SECOND LEVER exists that is not labels and not the threshold: boundary/soft-label
         handling. Suburban recall .575 is substantially UNDER-SEGMENTATION, not blindness.
         (b) BUT IT DOES NOT EXPLAIN AWAY RESULT (1). Inside crown INTERIORS the staircase is
         intact: 5-15 m .6218 -> 20 m+ .9333, spread +0.3115 — essentially IDENTICAL to the
         edge spread +0.3105. The two effects are INDEPENDENT AND ADDITIVE, not a confound.
         Robustness: at a 4 m edge the interior spread is still +0.2528, so a modest part of
         the staircase is edge-associated but HEIGHT DOMINATES. Result (1) STANDS; U3 reinforced.
         (c) THE CAVEAT IS NOW BOUNDED, AND THE LOSS IS ONLY PARTLY CHEAP. Added a miss-depth
         + CHM diagnostic to the same tool:
           part       deep<.06  .06-.12  .12-thr   CHM miss  CHM hit  miss>=3m
           interior      .148     .314     .538      13.4 m   24.5 m    .980
           edge          .329     .345     .326      11.6 m   18.4 m    .954
         * 95% OF EDGE MISSES CARRY CHM >= 3 m -> they are REAL CANOPY the model lost, NOT the
           reference bleeding onto bare ground. The reference-error caveat is bounded, not fatal.
         * BUT only ~33% of edge misses are near-threshold vs 54% of interior misses, and edge
           misses are TWICE as often DEEP (.329 vs .148). The model is MORE CONFIDENTLY WRONG at
           crown boundaries than inside them. So the operating point recovers roughly a third of
           the perimeter loss; the rest needs BOUNDARY-AWARE SUPERVISION (soft//distance-weighted
           edge labels), which is a real engineering item, not a threshold tweak.
         REMAINING CAVEAT: reference disagreement still concentrates at boundaries; CHM>=3m
         bounds how much of that is ground-bleed but cannot rule out mis-registration.
         (d) REPLICATED ON 2021s (different year, sensor, C-CAP epoch). Three of the four
         findings replicate almost exactly; ONE DOES NOT:
           edge share of area/misses  2016 16.3%/41.8%  ·  2021s 16.1%/42.8%   REPLICATES
           interior staircase spread  2016 +.3115      ·  2021s +.3900         REPLICATES
           edge misses w/ CHM>=3m     2016 .954        ·  2021s .928           REPLICATES
           edge misses DEEP (<.06)    2016 .329        ·  2021s .633           DOES NOT
         => the SIZE and REALITY of the perimeter loss are stable properties of the model;
         HOW RECOVERABLE it is is YEAR-SPECIFIC. Do not quote a single "x% is threshold-
         recoverable" number across years — 2016 says a third, 2021s says a fifth.
         (Interior recall reads .8191 in BOTH years — a coincidence in that one aggregate;
         the per-band tables differ substantially. Not a bug, but do not read meaning into it.)
         (9) ** THE DEFINITION SWEEP ALREADY EXISTED, AND IT CORRECTS RESULT (5)'s FRAMING
         (2026-08-18). ** phase4_qc_ndvi.py has ALWAYS written a (NDVI x height) canopy-%
         table; it sits in phase4/qc/ndvi_ref_2016.txt and nobody had read it as the U1
         instrument it is. Canopy % of imaged 2016 px:
                        h>=1m   h>=2m   h>=3m   h>=5m
           NDVI>=0.10   45.08   43.26   40.97   35.06
           NDVI>=0.20   39.00   37.74   36.07   31.59     <- 37.74 = the NDVI ref
           NDVI>=0.30   34.15   33.22   31.97   28.50     <- 31.97 = corrected labels
         (a) THE GREENNESS CUT MOVES THE NUMBER AS MUCH AS HEIGHT DOES: at h>=2m, NDVI
         .10->.30 costs 10.0 pp; at NDVI>=.20, h 1->5 m costs 7.4 pp. Every doc quotes a
         HEIGHT and almost none quote the NDVI cut — so half of the definition has been
         invisible. U1 is TWO thresholds, not one.
         (b) h 2->3 m is CHEAP (1.7 pp at NDVI>=.20) -> the 2-3 m IGNORE band buys honesty
         about the contested zone for very little area. Good trade.
         (c) ** CORRECTS (5). ** NO cell reproduces the latent ~.29 except the strictest
         corner (.30/5m = 28.50); the recommended .30/3m lands at 31.97, ~3 pp ABOVE. So
         C-CAP's total is probably NOT reachable by ANY threshold pair, and the "two
         definitions, pick one" framing in (5) is INCOMPLETE: C-CAP forest is STAND-BASED and
         drops isolated crowns BY KIND (McCombs 2016 ID 77 — 3x3 unit, 6-of-9 rule). The gap
         is part threshold (ours to choose) + part unit-of-analysis (not ours). Do not keep
         saying a threshold choice reconciles the two references.
         (d) CAVEAT ON ALL OF IT — RAISED AND THEN CLOSED THE SAME DAY. The rule needs a CHM,
         so no-CHM pixels are FORCED non-canopy: 17,587,495 / 21,066,144 valid cells have CHM
         -> 16.5% of the analysis area decided by ABSENCE OF LIDAR. STATE had always ASSERTED
         that strip is Puget Sound + S margin; NEW phase4_qc_chm_gap.py CHECKED it:
           no-CHM zone : NDVI p50 -0.357 · 99.8% NEGATIVE NDVI · 0.1% green at any cut
           has-CHM zone: NDVI p50 +0.211 · 19.6% negative · 43.8% green at NDVI>=.30
         It is OPEN WATER. Counting EVERY green no-CHM px as canopy adds +0.02 pp. So the D1
         table is a lower bound in principle and EXACT in practice — DO NOT apply a coverage
         correction. STATE's assumption is now verified, not assumed. -> qc/chm_gap_2016.txt
         What survives: a lidar-dependent definition CANNOT be applied pre-2016 (no coverage),
         and this says nothing about CHM ACCURACY where it exists (that is U6, still open).
         Also note the "~60% CHM coverage" figure in CLAUDE.md is of the RASTER; over the
         IMAGED/analysis area it is 83.5%, and the remainder is water. Both true, different
         denominators — quote the 83.5% when talking about the analysis area.
         (10) ** U6 ANSWERED — CHM ERROR CANNOT HAVE MADE THE STAIRCASE; IT BARELY DENTS IT
         (2026-08-18). ** NEW phase4_qc_chm_noise.py, 2016 agreed-canopy px, decim 8.
         (a) NULL TEST (the one that validates the whole method): shuffle each pixel's
         detection outcome to be INDEPENDENT of height at the same overall rate -> spread
         +0.0001. Binning by height CANNOT manufacture a staircase. Every height result in
         this project rests on that and it had never been checked.
         (b) ATTENUATION: add Gaussian error to the BINNING variable and re-bin —
             sigma   0m      1m      2m      3m      5m
             spread  .3877   .3833   .3790   .3697   .3400
             ratio   1.00    .99     .98     .95     .88
         The literature's ~3 m MAE (Moudry 2024 ID 82) costs only 5% of the spread, because
         the headline contrast (5-15 m vs 20 m+) spans a WIDE, well-separated gap that 3 m of
         noise rarely crosses.
         (c) THE DIRECTION IS THE POINT: error in a STRATIFICATION variable attenuates —
         regression dilution — it flattens a real curve and cannot build one from a flat
         truth. So the observed .3877 is an ATTENUATED copy; true spread plausibly ~.4065.
         RESULT (1) IS SAFE AND IF ANYTHING CONSERVATIVE. U6 closed for the headline claim.
         (d) WHAT CHM ERROR *DOES* BREAK: individual 5 m BAND EDGES. At ~3 m error a pixel
         binned 5-10 m often belongs in 2-5 or 10-15. Do NOT quote one band's recall as if
         its boundary were sharp, and do NOT design a height-conditioned model around a hard
         5 m cut without allowing for the smearing (bears on Hamraz ID 86 stratify-then-
         segment: pick wide strata, not 5 m ones).
         CAVEAT: added error is Gaussian/homoscedastic; real CHM error is height-dependent and
         biased, so this brackets attenuation rather than modelling it. And if CHM error and
         detection failure share a cause (both worse in dense mixed stands) the correction in
         (c) is optimistic.
         (11) ** THE 2015 OUTLIER EXPLAINED — AND IT CORRECTS (7d). MISSES ARE DEFINED BY
         LOSS OF COLOUR CONTRAST, NOT BY BRIGHTNESS (2026-08-18). ** No new code: re-read the
         per-channel tables already in forest_miss_{2000,2002,2013,2015}.txt.
           year   dR      dG      dB     blue-excess*  d_sat    d_bright   deep%
           2000  +25.5   +23.2   +32.4     +8.1       -0.075    +27.1      27.7
           2002  +18.6   +11.9   +15.8     +0.6       -0.048    +15.4      31.8
           2013   +6.6    -0.9   +13.3    +10.4       -0.090     +6.3      30.8
           2015   -6.4    -6.4    +1.6     +8.0       -0.006     -3.8      48.2
           *blue-excess = dB - mean(dR,dG); all deltas are missed MINUS recalled.
         (a) CORRECTION TO (7d). I wrote "missed forest is BRIGHTER, and dbright scales with
         sensor era (+27 in 2000 -> +6 in 2013 = the King contractor change)". 2015 BREAKS
         that: its misses are DARKER (-3.8) and it sits BETWEEN 2013 and 2016 in time. The
         era-scaling story was pattern-matching on three points. Do not repeat it.
         (b) WHAT IS ACTUALLY INVARIANT: SATURATION FALLS IN ALL FOUR YEARS (misses are
         greyer/flatter) and BLUE-EXCESS IS POSITIVE IN ALL FOUR. Missed crowns have LOW
         COLOUR CONTRAST — washed toward grey-blue — whether they got there by haze/
         over-exposure (2000/2002/2013, brighter) or by SHADOW (2015, darker; R and G drop
         while B rises = the classic skylight-shadow signature). Two mechanisms, ONE
         appearance, and the model keys on the appearance.
         (c) WHY 2015 IS ALSO THE DEEP-MISS OUTLIER (48.2% vs ~30%): shadowed crowns are not
         near-threshold, they are confidently rejected — a shadowed crown looks like nothing
         the conifer training sites contain. Consistent with (a): the deep/near split tracks
         the MECHANISM, not the year.
         (d) ACTIONABLE: this re-specifies open item (3) radiometric normalization. A
         BRIGHTNESS-matching normalization would do nothing for 2015 (its dbright is -3.8 and
         small) — normalize per-image SATURATION + CHANNEL BALANCE instead. That is now a
         concrete target rather than "radiometric normalization, unbuilt".
         CAVEAT: 2002's blue-excess is +0.6 = essentially nil, so "all four" is carried by
         saturation, not by blue. And these are FN-vs-TP contrasts within a year, which
         confound illumination with WHAT KIND OF STAND gets missed.
         (12) ** KAM WAS RIGHT: 2016 DOES NOT COVER EDMONDS. AND config.py's gsd_cm IS WRONG
         FOR EVERY NON-UTM YEAR (2026-08-18). ** Kam: "I believe 2016 doesn't fit the whole
         extent of edmonds". Checked against the project's OWN study area (phase3 2020 mask,
         7.46 x 10.55 km). Metadata only, no raster scan.
         (a) FOOTPRINT — coverage of the 2020-mask bbox:
             2000 · 2013 · 2015 · CHM   100%
             2019n · 2022n               69.2%
             C-CAP 2016                  53.1%   (missing 3.49 km at the NORTH)
             2016 · 2021s                41.9%   (missing N 3.99 km, S 1.59 km, E 0.82 km)
         2016 covers a CENTRAL/COASTAL BAND (lat 47.7830-47.8280), not the city. This is why
         phase4_sentinel_qc_overlay printed "forest_2: outside 2016 imagery extent" —
         forest_2 sits at 47.8294, just north of the edge. I saw that line and moved on.
         (b) WHAT IT INVALIDATES — every "city" number derived from 2016 is really that
         41.9% band: the D1 threshold sweep ("city canopy 31.97%" in canopy_definition_
         PROPOSAL.md), latent-class prevalence pi~.29, the chm_gap "no-CHM zone is water"
         result, and the 2016 rows of the height/edge work. They are not WRONG, they are
         MIS-SCOPED — relabel, do not rerun.
         (c) WHAT IT PARTLY CONFOUNDS: cross-year scores. Scoring intersects with C-CAP, so
         2000/2013/2015 are scored on ~C-CAP's 53.1% while 2016 is scored on its own 41.9%
         SUBSET of that. So result (7e)'s "2016 is the outlier at 66.2% deep" compares a
         central band against a larger band. A plausible mechanism: 2016's band excludes the
         northern forest and is proportionally more suburban = the known blind spot = more
         STRUCTURAL misses. UNTESTED — the honest statement is that the 66.2% is partly
         geographic. Do not quote it as a pure model property.
         (d) SEPARATE BUG — gsd_cm IS CRS-UNITS x 100, NOT GROUND cm:
             year        config   TRUE ground   why
             2016/2021s   50.0 cm   15.4 cm     EPSG:2285 is US SURVEY FEET, not metres
             2000/2002    59.7 cm   40.1 cm     EPSG:3857 inflates by 1/cos(47.8) = 1.49
             2013/2015    14.9 cm   10.0 cm     same Web-Mercator inflation
             2019n/2022n  60.0 cm   60.7 cm     EPSG:26910 is metres -> CORRECT
         TIER IS DERIVED FROM THIS (cli.py:357 `tier_of(e["gsd_cm"]) == "coarse"`), so 2016
         is trained as COARSE (citywide 2020-mask labels, coarse stride) while its imagery is
         actually ~15 cm. Two consequences: (i) result (7e)'s recipe-comparability claim
         SURVIVES — the engine really did use the citywide recipe for 2016 — but the REASON I
         gave ("2016 is 50 cm coarse imagery") is wrong; (ii) a 512 px tile on 2016 covers
         79 m of ground, not the 256 m the coarse settings assume.
         (e) RESULT (7d) SURVIVES WITH BETTER LABELS. On TRUE gsd the recall-vs-resolution
         trend is intact and cleaner: 10 cm -> .7107/.7075 · 15 cm -> .6844 · 40 cm ->
         .5670/.5086. The finding was right; the axis was mislabelled.
         NOT FIXED HERE: config.py is untouched — changing gsd_cm changes TIER and would
         silently re-recipe every year. That is a deliberate decision for Kam, not a typo fix.
         (13) ** OUR C-CAP WAS A BADLY CLIPPED COPY. THE REAL ONE COVERS 91%. AND A DEDICATED
         CANOPY PRODUCT EXISTS (2026-08-18, Kam). ** Kam: "ccap data should encompass the
         entire area, check my arcgis folder" — RIGHT ON BOTH COUNTS.
         SOURCE: C:\Users\Kameron\Documents\ArcGIS\NOAA\{Land Cover,Tree Canopy,Impervious,Water}
         (a) COVERAGE. Over the study-area grid, DATA cells:
             ccap_2016_hires_lc.tif  (what we score against today)  51.9%
             "2016 land cover snohomish.tif"  (the real source)     91.0%   <- SAME class
             scheme (forest 9/10/11 = 25.81% of data cells vs the clipped copy's 28.19%).
         So the "C-CAP only covers ~53%" ceiling — which I recorded as a hard limit in
         result (12) — is an ARTEFACT OF OUR CLIP, not a property of C-CAP. Re-clipping lifts
         every C-CAP-scored number to ~91% of the city for the full-coverage years.
         (b) ** A DEDICATED TREE-CANOPY LAYER EXISTS AND WE NEVER USED IT. **
         wa_2021_ccap_v2_hires_canopy.tif — statewide WA, EPSG:5070, ~1.14 m, 3.07 GB,
         100% of the study bbox. Values 0/1/2 with STATISTICS_VALID_PERCENT=100, so 0 is a
         real "not canopy", NOT nodata. Canopy (1|2) = 26.0% of the study grid; over LAND
         (excluding the ~9% that is Puget Sound) ~28.6%.
         WHY THIS MATTERS FOR U2/U1: every C-CAP number in this project scores against FOREST
         LAND-COVER CLASSES, which are stand-based and drop isolated crowns BY KIND — the
         exact objection in result (9c). A purpose-built CANOPY product does not have that
         defect, and it lands at ~26-29%, i.e. NEXT TO the latent-class pi ~.29 and C-CAP
         forest 25.8%, and FAR from the NDVI ref's 37.7%. That is a THIRD, independent,
         definitionally-appropriate estimate agreeing with the low number.
         CAVEAT: it is 2021 vintage and a different product generation (v2), so it is a
         cross-check for the NIR years, not a drop-in reference for 2000/2013/2016.
         (c) ALSO SURFACED: imagery years on disk that are NOT in the catalog — 1936, 1998,
         2005, 2007, 2009, 2012, 2017, 2019, 2021, 2023 king_rgb. Unassessed.
         (14) ** METADATA MANAGEMENT — NEW phase4_data_inventory.py (Kam asked for it). **
         Three metadata bugs surfaced in one day (12a footprint, 12d gsd_cm units, 13a clipped
         reference) and none were hard to detect — nothing was looking. The inventory opens
         every raster HEADER and records role · CRS · CRS LINEAR UNIT · px in CRS units ·
         TRUE GROUND GSD (derived from the WGS84 span / pixel count, so feet-vs-metres and
         Web-Mercator inflation cannot fool it) · bounds · % of study area · dtype · nodata.
         FIRST RUN FLAGS: 50 rasters where px*100 misstates ground resolution — EVERY
         EPSG:3857 file by 1.49x and EVERY EPSG:2285 file by 3.24x, i.e. the error is
         SYSTEMATIC AND CRS-DETERMINED, not a typo — and 12 rasters not covering the study
         area (2016/2021s 41.9%, C-CAP 53.1%, NAIP 69.2%).
         RULE IT ENFORCES: true GSD and coverage are MEASURED from the file, never copied
         from a config. A config value is a claim; this is a measurement.
         (15) ** CONFIG CORRECTED + FULL-COVERAGE REF + THE CANOPY PRODUCT READ (2026-08-18,
         Kam: "Change the config. Yes to all 3"). **
         (a) phase4seg/config.py gsd_cm NOW TRUE GROUND cm (was CRS units x 100):
             2000/2002 59.7->40.1 · 2005/07/09 29.9->20.1 · King fine 14.9->10.0 ·
             CoE 7.5->5.0 · NAIP 60.0->60.7 · SNOH 50.0->15.4
         TIER IS UNCHANGED FOR EVERY YEAR. Re-deriving tier from the true numbers moves ONLY
         2016/2021s coarse->medium, and that is NOT harmless: `citywide = (tier=="coarse" or
         --force-citywide)`, so medium would switch them off the citywide 2020-mask labels
         onto the CROWN POLYGONS — the ones CLAUDE.md records as overwritten with accept-all
         test data — and would invalidate every 2016 result here. So those two carry an
         explicit "tier":"coarse", read by a NEW config.tier_for(entry) which prefers an
         explicit tier over tier_of(gsd_cm). cli.py's 4 call sites now use tier_for.
         => metadata TRUE, behaviour UNCHANGED, re-tiering is now a deliberate 1-line edit.
         "coverage" also corrected to MEASURED values (snoh 42%, NAIP 69%).
         phase4seg_preflight.py PASSES (compile · undefined-name sweep · torch-free import ·
         argparse). NOT yet Colab-smoke-tested.
         (b) FULL-COVERAGE C-CAP: FIRST LOOK, THEN A CORRECTION TO MY OWN TEST.
         2013 vs the un-clipped ccap_2016_hires_lc_snohfull.tif (91% vs 51.9% of the study
         area) read recall .7094 -> .7422, precision .8551 -> .8672.
         ** THAT COMPARISON WAS CONFOUNDED — I changed THREE things at once: the reference
         (clipped -> full), the prob raster (_xsensor_rgb -> _citywide_rgb) and the threshold
         (.5209 -> .5000). It cannot attribute the movement to the reference. ** Do not quote
         the +3.3 pp. Re-running properly (same prob, same deployed threshold as each live
         row, ONLY the reference swapped) for 2000 .5133 · 2002 .57 · 2013 .5209 · 2015 .576.
         The DIRECTION is still expected to be favourable — the clipped half is not
         representative — but the size is unmeasured until those land.
         (c) ** THE CANOPY PRODUCT SEPARATES TREE FROM SHRUB — AND HEIGHT DOES NOT. **
         Kam: "1 and 2 mean shrub or tree, cant recall". Settled with our own CHM:
             class 1 = TREE   24.79% of grid · median 21.6 m · 97.6% >=3 m
             class 2 = SHRUB   1.25% of grid · median  4.0 m · 65.6% >=3 m
         A HEIGHT CUT IS A POOR PROXY FOR THE TREE/SHRUB CALL: >=3 m keeps 97.6% of tree but
         ALSO 65.6% of shrub; >=5 m still keeps 38.1% of shrub while losing 6.6% of tree.
         D1/D2 in canopy_definition_PROPOSAL.md both assume height can stand in for form.
         IT CANNOT, cleanly — that assumption needs stating as a limitation.
         AND THE STAKES SHRINK: I framed shrub-vs-tree as worth ~6 pp of canopy. On NOAA's
         accounting shrub is 1.25% of the grid, so it is worth ~1 pp. The .29-vs-.35 gap is
         therefore NOT mostly shrubs — which weakens result (5)'s "2-5 m band = shrubs and
         hedges" reading and re-opens what the NDVI ref's surplus actually is.
         CAVEAT: NOAA's shrub class may simply be conservative; 2021 vintage; and its 24.79%
         tree share is over the FULL study grid (incl. ~9% water) whereas our 31.97% is over
         2016's 41.9% band — DIFFERENT DENOMINATORS, do not subtract them.
         (16) ** ANSWERED: WHAT THE NDVI REF OVER-CALLS IS MID-HEIGHT WOODY VEG, NOT SHRUBS —
         AND A HEIGHT CUT CANNOT SETTLE IT (2026-08-18). ** NEW phase4_qc_ndvi_vs_tree.py.
         VINTAGE-MATCHED: ndvi_ref_2021s vs the 2021 NOAA canopy product, so canopy CHANGE
         cannot explain any of it. 2 m grid, 8.1M valid cells.
           NDVI ref canopy 38.61% · NOAA tree 26.20% · NOAA tree+shrub 27.75%
           of NDVI-ref canopy:  63.84% NOAA TREE (CHM p50 20.6 m, 98.9% >=3 m)
                                 2.87% NOAA SHRUB (p50 4.8 m)
                                33.28% NOAA NEITHER (p50 6.0 m, 88.7% >=3 m, 61.1% >=5 m)
         (a) ** CORRECTS RESULT (5). ** I read the ~8 pp surplus as "shrubs and hedges in the
         2-5 m band" because the NDVI ref's specificity was lowest there. WRONG on both
         halves: only 2.87% of NDVI canopy is NOAA shrub, and the disputed population's
         MEDIAN is 6.0 m with p90 18.4 m — mid-height, not 2-5 m. Do not repeat the shrub
         reading.
         (b) THE GAP IS ONE POPULATION. 38.61 - 26.20 = 12.4 pp, and the disputed cell is
         12.85% of the grid. So essentially the WHOLE .29-vs-.38 disagreement is this single
         mid-height class, not a scatter of small definitional differences.
         (c) ** THIS BREAKS D1 AS POSED. ** canopy_definition_PROPOSAL.md frames the decision
         as a MINIMUM HEIGHT. But 88.7% of the disputed population is >=3 m and 61.1% is
         >=5 m, so NO plausible height cut removes it: the recommended >=3 m rule KEEPS ~89%
         of it and therefore lands near the NDVI ref's number, NOT near .29. Combined with
         (15c) — height is also a poor proxy for tree-vs-shrub — the real U1 decision is
         about CROWN FORM / MINIMUM CROWN SIZE, not height. D1 must be re-posed.
         (d) WHAT THE DISPUTED CLASS PROBABLY IS: young/ornamental crowns, hedgerows,
         understory and yard trees — i.e. exactly the SUBURBAN population the 8/8 visual
         grounding found, and exactly what a stand-based product declines to call "tree".
         WHICH SIDE IS RIGHT IS STILL UNDECIDED: NOAA canopy is a MODEL PRODUCT, not truth.
         P3 photo-interpretation against a written definition is still what settles it — but
         it now has a SPECIFIC population to rule on rather than a vague 8 pp.
         (17) ** 2015 IS A LEAF-OFF ACQUISITION — TWO SESSIONS, TWO INSTRUMENTS, SAME YEAR
         (2026-08-19). ** Cross-checked the stopped session's leaf-off sweep (committed
         58ee67c, its numbers otherwise UNVERIFIED per the audit) against result (11), which
         this session derived independently from per-channel forest-miss statistics.
         LOW-GREENNESS FRACTION (GRVI<0.02) over 2020-mask canopy pixels:
             2015 31.22% · 2013 22.46% · 2000 16.86% · 2002 13.58% · 2005 10.98% ·
             2022n(NAIP, leaf-on BY SPEC) 5.23% · 2016 1.95%
         ** [WITHDRAWN 2026-08-19, SAME DAY — see LIT-WATCH INTAKE item 1 below.] ** The
         cross-year GRVI ranking this result rests on IS NOT SAFE. litwatch_robustness.md
         proves it with an unarguable pair: 2019 KING reads frac(GRVI>.02)=0.1146 and 2019
         NAIP reads 0.8919 — SAME YEAR, SAME GROUND, SAME SEASON, differing by 0.78. That is
         sensor/processing colour balance, not vegetation. The King series also drifts
         monotonically .80 (2000) -> .11 (2019). So "2015 is the most leaf-off year" is NOT
         established: 2015 King vs 2016 Snoh is a CROSS-SENSOR comparison and the index
         itself moves more than any leaf-on/off effect.
         WHAT SURVIVES: (i) the 2015 ANOMALY itself — 48.2% deep misses, misses darker and
         relatively bluer — because result (11) measured that WITHIN each year (missed vs
         recalled forest in the SAME image), and a global colour cast cancels in a
         within-year contrast. That is exactly the use litwatch says is unaffected.
         (ii) the reasoning that leaf-off and low sun angle co-occur.
         WHAT FALLS: the attribution of 2015's anomaly TO leaf-off via the cross-year
         ranking. 2015 may still be leaf-off — it is no longer EVIDENCE that it is.
         LESSON FOR THE NEXT SESSION: I cross-checked two instruments and treated agreement
         as confirmation without checking whether the second instrument was comparable
         across the axis I was comparing on. Agreement between two contaminated readings is
         not corroboration.

         (a) THE CONVERGENCE [now withdrawn, see above]. 2015 is the MOST leaf-off year in the series, and 2015 is the
         year result (11) singled out on completely different evidence: 48.2% DEEP misses vs
         ~30% elsewhere, with misses DARKER and relatively BLUER — which I read as shadow.
         Leaf-off flights fly at LOW SUN ANGLE, so bare crowns and long shadows arrive
         together. So the better account of 2015 is: BARE DECIDUOUS CROWNS the green-trained
         model confidently rejects, with shadow as a CORRELATE rather than the cause.
         That explains why 2015's misses are deep rather than near-threshold: a leafless
         crown is not a marginal call, it looks like nothing in the training set.
         (b) ** IT DOES NOT GENERALISE, AND 2016 KILLS ANY SIMPLE RULE. ** 2016 is the most
         LEAF-ON year measured (1.95%) and yet has the HIGHEST deep-miss share in the project
         (66.2%, result 7e). 2013 is 2nd most leaf-off (22.46%) but sits at an ordinary 30.8%
         deep. So phenology explains 2015 SPECIFICALLY; it is NOT the axis behind the series.
         Do not build a leaf-off correction for the whole record on this.
         (c) STATUS OF THE SOURCE: this raises confidence in the leaf-off SCRIPT (its output
         agrees with an independent instrument on the one year both cover) WITHOUT rescuing
         the stopped session's headline entry, whose code is gone. Corroboration of one claim
         is not reproducibility of the rest.
         CAVEAT: the sweep samples pixels the 2020 MASK calls canopy, so it inherits that
         mask's conifer bias — which biases AGAINST detecting leaf-off, making 2015's 31.22%
         a floor rather than an estimate.
         ════ LIT-WATCH THREAD CLOSED — 2026-08-19 ════
         Scripts/litwatch_robustness.md now carries a CLOSED banner. Closed because its queue
         is dominated by MEASUREMENT and ENGINEERING items, not reading: the last searches
         confirmed existing choices rather than changing them. FOUR of four re-run claims
         reproduced EXACTLY (cast2 / q138b / overhang / q136), so the empirical work is sound
         where checked.
         ** THE ONE FIX WORTH ADOPTING (Q136, verified by re-run today): the AREA NUMBER. **
         Map-count area — counting thresholded pixels, phase3_semantic_dev.py:1722 — is
         THRESHOLD-SENSITIVE BY 17.3 pp (33.56% @ .30 down to 16.24% @ .70) and sits -5.71 pp
         at the deployed .5, measured on 162,786 points in 2013 against C-CAP at 35.97%.
         THE EDMONDS POLICY DEBATE TURNS ON 2.6 pp (32.4% baseline vs 35% goal). The
         estimator's bias is MORE THAN TWICE THE ENTIRE POLICY GAP, and it moves with a
         parameter calibrated separately per year. The Olofsson stratified reference-sample
         estimator is threshold-free and unbiased in simulation. ADOPTION IS KAM'S CALL.
         NOT claimed: that published percentages are wrong by 5.71 pp (different thresholds,
         different footprints, and C-CAP is not truth). Claimed: the estimator in use is
         threshold-sensitive by up to 17 pp and a threshold-free alternative already exists.
         ** THE JOINT SAMPLE-SIZE ANSWER — neither session had this alone, and the two
         budgets differ 5x: **
           arbitrating the REFERENCE DEFINITIONS (8.24 pp gap) -> n=250 SUFFICES, power ~1.0
             at <=5% interpreter error  [my result (6), phase4_qc_design_power.py]
           estimating the POLICY NUMBER (2.6 pp gap)          -> n=250 FAILS, +/-4.42 pp
             cannot separate 32.4% from 35%; ~1,221 pts/yr for +/-2.0 pp, and year-to-year
             CHANGE needs more  [their Q136]
         Both verified. DO NOT quote one budget as though it settled the other. This also
         re-frames U1/P3: the definition question is cheap, the deliverable number is not.
         STILL OPEN, carried forward: Q1=U1 canopy definition (Kam) · Q139 is the softness
         OURS (EPSG:3857 reprojection blur — 2000 2.8x, 2005 4.0x oversampled; cheap to
         check, could recover detail no retraining can) · Q140 the 2000/2002 deficit
         (3 explanations failed — stop guessing, look at the imagery) · channel ablation (GPU).

         ════ SCRATCHPAD RECOVERED AND THREE CLAIMS RE-RUN — 2026-08-19 ════
         The lit-watch session was NOT stopped after all; Kam had it commit its scratchpad.
         229 files now at Scripts/litwatch_scratch/ (commit d88a36b). I amended that commit
         to drop pts.npz + rg_cache.npz — 13 of its 14 MB, both regenerable caches
         (sampler.build_points is a deterministic np.linspace grid, no randomness despite its
         seed arg). Repo stays 1.33 MiB packed. SUGGEST adding *.npz to .gitignore beside the
         existing *.tif/*.pt/*.parquet "must never sneak in" list.
         ** I RE-RAN THREE CLAIMS FROM THE RECOVERED CODE. ALL THREE REPRODUCE EXACTLY. **
           cast2.py    GRVI cross-sensor cast — every figure matches, incl. the decisive pair
                       2019 KING -0.0182 / frac .1146 vs 2019 NAIP +0.1779 / .8919, and the
                       King drift .8027 (2000) -> .3463 (2013) -> .1146 (2019). Also confirms
                       1936 is a single-band constant (mean 253.0) and 1998 single-band.
           q138b.py    effective resolution — all 11 rows match: 1998 244.7 cm (6.10x),
                       2005 80.7 (4.02x), 2000 110.8 (2.76x), the other 8 at 1.26-1.42 px.
           overhang.py on-building split — 23,666 buildings, 12,271 cells, AT-roof 29.77%,
                       ABOVE-roof 68.43%, median delta +2.10 m. Exact.
         => ** UPGRADE THE AUDIT. ** My earlier "treat every figure as unverified" was right
         WHEN THE CODE WAS MISSING and is now too harsh: for the three highest-value claims
         the code exists and reproduces to the digit. Remaining figures are UNRE-RUN, not
         unreproducible — the scripts are there, so anything can be checked before use.
         CONSEQUENCES FOR MY OWN RESULTS:
         (a) The result-(17) WITHDRAWAL IS CONFIRMED CORRECT. The GRVI cast is real and
             measured, so the cross-year leaf-off ranking genuinely could not carry it.
         (b) MY RESOLUTION FINDING NEEDS QUALIFYING, not withdrawing. Recall vs EFFECTIVE
             resolution: 13.7cm .7422 · 12.9 .7401 · 25.5 .6605 · 26.1 .6048 · 57.1 .6136 ·
             80.7 .6346 · 110.8 .5480. The EXTREMES still separate (~19 pp from 13 cm to
             111 cm) but the MIDDLE IS NOT MONOTONE — 2005 at 80.7 cm beats 2009 at 26.1 cm.
             So nominal tiers made the trend look cleaner than it is. Resolution is real at
             the extremes; the mechanism in the middle is unexplained (their three attempts —
             nominal GSD, spectral sharpness, effective resolution — all failed).
         (c) OPERATIONAL, AND IT EXPLAINS MY SLOW NIGHT: cast2.py's docstring records that
             NOTHING in this project has overviews, so a decimated whole-raster read silently
             reads the entire multi-GB file. That is why my qc_indep rescores took 30-60 min
             each. BUILDING OVERVIEWS (gdaladdo) would speed every full-raster QC tool here.
         (d) NOT verified: the headline 88-93% "real miss". overhang.py reproduces the
             ON-BUILDING SPLIT that feeds it, not the whole chain. Re-run the rest before
             quoting that number.
         DO NOT RUN upd*.py / chat*.py / entry*.py / append.py — they are WRITERS that append
         to litwatch_robustness.md, CHATLOG.md and Literature_Tracker.xlsx. Re-running them
         duplicates entries. Superseded buggy versions are kept on purpose: q138.py has the
         np.interp monotonicity bug, cast.py predates the windowed rewrite, q121/q121b predate
         the streaming rewrite. Use q138b / cast2 / q121c.

         ════ LIT-WATCH INTAKE (2026-08-19) — READ THIS BEFORE TRUSTING RESULTS 1-17 ════
         SOURCE: Scripts/litwatch_robustness.md, 4,660 lines, searches 15-45+, IDs 106-178+,
         written by the now-STOPPED parallel session. STATUS OF ITS NUMBERS: the empirical
         sections were computed with the same scratchpad that no longer exists, so treat
         every FIGURE as unverified. Treat the REASONING as usable — several items below
         carry their own internal proof and need no code to be persuasive.
         SIX ITEMS THAT CHANGE WHAT THIS FILE ALREADY SAYS:
         1. ** GRVI IS NOT COMPARABLE ACROSS SENSORS. ** 2019 King frac(GRVI>.02)=0.1146 vs
            2019 NAIP 0.8919 — same year, same ground, same season. King drifts .80->.11
            across 2000->2019. ANY cross-year GRVI diagnostic reports a large steady canopy
            decline that is pure processing artefact. WITHIN-year use is unaffected.
            -> WITHDRAWS result (17); see the note on it. Also means the leaf-off sweep's
            cross-year table must not be quoted.
         2. ** EFFECTIVE RESOLUTION != NOMINAL GSD, by up to 6x. ** Edge-spread measurement,
            12 fixed sites, 11 years: 1998 nominal 40 cm resolves at 245 cm (6.1x); 2005
            nominal 20 cm resolves at 81 cm (4.0x) — COARSER THAN 2000's nominal 40; 2000
            resolves at 111 cm (2.8x). The other 8 years are properly sampled at 1.26-1.42 px.
            -> QUALIFIES my "resolution is worth ~16 pp" (result 15/recipe-matched table).
            The nominal tiering happened to give a clean trend, but 2005 sits at 81 cm
            effective and still scores .6346, near 2007/2009 at ~26 cm. Effective resolution
            REORDERS the years and does NOT reproduce the trend, so the mechanism is not
            settled. Their own words: three attempts to explain the 2000/2002 deficit have
            failed (nominal GSD, spectral sharpness, effective resolution).
            -> ALSO: my gsd_cm fix corrected UNITS (CRS->ground) but tier is still keyed to
            a number that is wrong by up to 6x as a measure of real detail. Worth revisiting
            tier_for() with effective resolution if 2005/2000 are ever retrained.
            -> AND A LEAD WORTH CHASING: every King file is EPSG:3857, and reprojection to
            Web Mercator is itself a blurring resample. The softness may be OURS, introduced
            by mosaicking, not the original acquisition. If so, re-deriving early years from
            native-projection sources recovers detail no retraining can.
         3. ** THE CONTESTED BAND IS MOSTLY REAL MISS, NOT REFERENCE DISAGREEMENT. ** Against
            rasterised per-building heights, canopy over roofs: 88-93% of the tall contested
            band is genuine model failure under both a liberal and a conservative reading of
            the building heights. P2 implied ~35%. -> This attacks the "38.7% is unmeasurable"
            framing that results (5) and (12) lean on. If it holds, the honest recall numbers
            are TOO KIND, not too harsh. HIGH PRIORITY TO RE-DERIVE with tracked code.
         4. ** RECALL HALVES ON CANOPY OVER IMPERVIOUS ** (Q116) and two independent deficits
            COMPOUND (Q118). Consistent with my edge/perimeter result (8) — overhang above
            roofs and driveways is exactly perimeter canopy.
         5. ** SHADOW REFUTED AS THE OVERHANG MECHANISM ** (Q122) — bears on result (11)'s
            shadow reading; their test is of overhang specifically, mine was of 2015's
            per-channel signature, so these are not the same claim, but do not merge them.
         6. ** INVENTORY DEFECTS: ** 1936_king_rgb.tif is an EMPTY SHELL (uniform 253/0 fill —
            King County survey does not reach into Snohomish); 1998 and 1936 are SINGLE-BAND
            despite _rgb filenames; there are TWO DIFFERENT 2017 ACQUISITIONS; no acquisition
            metadata exists in any raster. -> Cross-check against my phase4_data_inventory.py,
            which measures geometry but NOT band count or fill — worth extending.
         WHAT IT DOES NOT TOUCH: the literature itself, which is the durable asset — DOIs
         verified against Crossref, explicit inclusion bar, covered/queued discipline.
         ---- LITERATURE (37 papers, IDs 69-105, searches 9-14) — TWO CORRECTIONS TO ME ----
         FOODY 2010: I claimed raw scores overstate the model's faults. Direction depends on ERROR
         CORRELATION; ours are almost certainly correlated (labels + both refs all from interpreting
         the same imagery) => OUR RECALL IS LIKELY OPTIMISTIC. Do not repeat my old pattern claim.
         MOUDRY 2024 + SIERRA 2026: canopy-height products are height-biased, realistic CHM MAE ~3m,
         [U6 RESOLVED 2026-08-18 — see result (10). The ~3m error costs only 5% of the height
         spread and can only ATTENUATE, never create it. Band EDGES stay smeared.]
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
         4. [DONE 2026-08-18] P1c per-year miss-depth under ONE recipe — see result (7).
         5. NEW: rerun 2016 forest-miss on the _citywide_rgb recipe so its ~60%-deep figure
            becomes comparable (needs a 2016 --force-citywide inference on Colab).
         ---- P3 COMMANDS (tooling is built and validated) ----
         py -3.12 phase4_accuracy_sample.py --step serve --year 2016             --ortho "D:\edmonds-pipeline\Imagery\2016_snoh_rgbi.tif"
         then open http://localhost:8731/review_app.html  (1 canopy / 2 not / 3 unsure / z undo)
         then --step estimate --year 2016
         Estimator validated twice; a covariance bug was found and fixed 2026-08-18 (8283232) — the
         old version overstated every CI.
         ---- LOCAL ENV ----
         CUDA now works locally: torch 2.13.0+cu126, Quadro T2000 4GB (CLAUDE.md says 2GB — STALE),
         3.45GB free, verified. Still do NOT train locally (rule: don't split training Colab/local).
         ---- HONEST BASELINE — RESTATED 2026-08-18 ON THE FULL-COVERAGE REFERENCE ----
         The old table was scored against ccap_2016_hires_lc.tif, a CLIPPED copy covering
         51.9% of the study area (result 13a). Rescored against the un-clipped source
         ccap_2016_hires_lc_snohfull.tif (91.0%), changing ONLY the reference — same prob
         raster, same deployed threshold, forest_wetland:
             year   clipped ref     FULL ref        d recall   imagery coverage
             2000   .6303/.7745  -> .6749/.7975      +4.5 pp   100%
             2002   .5069/.8377  -> .5580/.8563      +5.1 pp   100%
             2013   .7094/.8551  -> .7395/.8666      +3.0 pp   100%
             2015   .6222/.8835  -> .6629/.8989      +4.1 pp   100%
             2017   .7784/.8083  -> .7986/.8274      +2.0 pp   100%
             2016   .6844/.8651  -> .6636/.8736      -2.1 pp    41.9%
         ---- 2021 SAME-YEAR CROSS-SENSOR PAIR — CANNOT BE READ YET (2026-08-19) ----
         The job queued specifically to isolate the sensor effect, because real canopy change
         between two 2021 acquisitions is ~zero:
             2021s  Snohomish 15.4 cm  p2nir recipe    thresh .499   .6851 / .8547
             2021k  King      10.0 cm  citywide recipe thresh .4013  .6059 / .8778
         Naively: the COARSER sensor wins recall by 7.9 pp, which would contradict the
         recipe-matched resolution trend above (10 cm ~.741). ** DO NOT READ IT THAT WAY. **
         TWO uncontrolled confounds:
           (1) TILING PARAMS — 2021s is coarse tier, 2021k is fine, so stride / neg-rate /
               test-split differ (TIER_TILE_PARAMS).
           (2) FOOTPRINT — 2021s covers 41.9% of the study area, 2021k 100%, so they are
               scored on different ground (result 12c).
         ** CORRECTION 2026-08-19 to what I first wrote here. ** I said the two used
         DIFFERENT LABEL RECIPES (p2nir vs citywide) and that a retrain would settle it.
         WRONG on both counts, found by reading cli.py rather than the run tags: "p2nir" is
         only a RUN TAG. 2021s is COARSE tier, and coarse years take the citywide 2020-mask
         label path BY DEFAULT — the same path --force-citywide gave 2021k. Their LABEL
         SOURCE already matches; what differs is the TIER TILING PARAMETERS.
         AND THAT CANNOT BE RETRAINED AWAY: tiling params are keyed to tier, tier is keyed to
         resolution, so "sensor" and "tiling regime" are entangled BY DESIGN. There is no
         Colab job that isolates the sensor here. DO NOT SPEND A 5 cm RUN ON IT — the earlier
         entry proposing exactly that is withdrawn.
         Recorded as OPEN AND PROBABLY NOT ANSWERABLE by retraining. A real answer needs a
         deliberate ablation (same year, same footprint, tiling params forced equal), which
         is an engine change, not a queue entry.

         ---- QUEUE 2 (Colab, overnight 2026-08-18/19) — FIRST TWO YEARS SCORED ----
         2005 and 2007 trained + inferred OK (VERIFY 100% valid). Scored vs the FULL-coverage
         ref, forest_wetland, tool-chosen threshold:
             2005  thresh .4659   recall .6346   precision .9166   <- HIGHEST precision in
             2007  thresh .5026   recall .6605   precision .8813      the whole project
         ** THE max-prob WARNING WAS AGAIN A RED HERRING. ** Their inference max-prob was
         .843/.882, well under 2019n .949 / 2021s .957, i.e. the same COMPRESSED RANGE that
         made a previous session predict low recall for 2017 TWICE — wrongly, 2017 is the
         series high. I withheld the prediction this time and the numbers are mid-series.
         A compressed probability range means THRESHOLD FRAGILITY, not weak ranking. This is
         now 2-for-2; treat it as settled.
         ** RECIPE CAVEAT — DO NOT RANK THESE AGAINST THE TABLE BELOW. ** 2005/2007 are
         _citywide_rgb; the 2000/2002/2013/2015 rows below are _xsensor_rgb. Result (7b)
         measured that a recipe change moved 2013 by 22 points, so a mixed-recipe ranking is
         not interpretable. To compare, re-score the older years' _citywide_rgb rasters
         (they exist) on this same reference.
         ---- RECIPE-MATCHED SERIES (2026-08-19) — ONE RECIPE, ONE REFERENCE ----
         Ran the re-score rather than writing the reversal claim. ALL _citywide_rgb, ALL vs
         the FULL-coverage ref, forest_wetland, tool-chosen threshold:
             year  TRUE gsd  recall  precision
             2000    40.1cm  .5480     .8534
             2002    40.1cm  .6136     .8372
             2005    20.1cm  .6346     .9166
             2007    20.1cm  .6605     .8813
             2009    20.1cm  .6048     .9177   <- highest precision in the project
             2013    10.0cm  .7422     .8672
             2015    10.0cm  .7401     .8823
         ** RESULT (7d) IS VINDICATED, NOT REVERSED. ** Once recipe is held constant the
         trend is clean and the within-tier agreement is tight:
             40 cm  .5480 .6136          mean .581
             20 cm  .6346 .6605 .6048    mean .633
             10 cm  .7422 .7401          mean .741   <- 0.2 pp apart, different sensors/years
         Resolution is a REAL driver worth ~16 pp of recall across 40->10 cm, and the 10 cm
         pair agreeing to 0.2 pp across two different years is the strongest within-tier
         replication in the project. The apparent reversal in the
         mixed-recipe table WAS the confound, exactly as suspected — which is why the rule
         is to re-score rather than to reason about it.
         ** AND THE RECIPE EFFECT IS LARGE AND YEAR-SPECIFIC: ** same year, same reference,
         only the training recipe differs —
             2000  xsensor .6749  vs  citywide .5480   -> xsensor BETTER by 12.7 pp
             2002  xsensor .5580  vs  citywide .6136   -> citywide BETTER by  5.6 pp
         Opposite directions. So there is NO globally better recipe, and no cross-year table
         mixing them means anything. This is the third independent measurement of the same
         hazard (7b moved 2013 by 22 pp; this moves 2000 by 12.7 pp in the other direction).
         2015 also swings by recipe: xsensor .6629 vs citywide .7401 = citywide better by
         7.7 pp — a THIRD direction-and-magnitude, reinforcing that recipe is year-specific.
         ** QUOTE THE FULL-REF COLUMN. ** Precision rose in ALL SIX years. Complete.
         ** THE ASYMMETRY IS THE FINDING, AND IT IS NOW 5-FOR-5: ** every year with 100%
         imagery coverage got BETTER (2000 +4.5, 2002 +5.1, 2013 +3.0, 2015 +4.1, 2017
         +2.0); 2016 — the ONLY one at 41.9% — got WORSE. Coverage, not year or sensor,
         predicts the sign. 2017 remains the highest recall in the series at .7986. So the clipped reference was
         FLATTERING 2016 specifically and PENALISING the full-coverage years. That matters
         because 2016 is the most-cited year in the project (the only NIR year with a
         matched CHM, and the year the corrected labels were built for).
         ** 2016 HONEST RECALL IS NOW .6636, NOT .6844. ** Anywhere this file or a report
         says "2016 recall .6844" against C-CAP, it is superseded — including the framing
         in results (3) and (5). The DIRECTION of every finding is unchanged; the level is.
         UNAFFECTED: NDVI-ref 2016 .594/.959 (different reference entirely). STILL TRUE:
         every 2016-derived analysis remains bounded by the 41.9% footprint no matter which
         C-CAP is used (result 12b) — a fuller reference does not widen the imagery.
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
         [SUPERSEDED 2026-08-18 by result (7) — recomputed on ONE recipe. The near-threshold
         conclusion HOLDS, but every per-year conf% above was a RECIPE ARTEFACT and must not be
         re-quoted: 2013 moved 9.3% -> 30.8%. Use the result-(7) table.]
         (4) There is NO git remote — "git pull" CANNOT update Colab. The working tree IS
         the Drive folder (G:/My Drive/treedata); git DB = D:/edmonds-pipeline/treedata.git,
         local Windows only. GOOGLE DRIVE is the sync path to Colab. Verify there with:
         !grep -c 2022n /content/drive/MyDrive/treedata/Scripts/phase4_p1_colab_run.py
gotcha:  scripts Colab-only for torch (rasterio+geopandas+fiona+sklearn now pip-
         installed local — module import auto-installs). polygons/ overwritten w/
         accept-all test data; 14,476-crown human review never finished.

════════════════ LOG  (newest first) ════════════════

## 2026-08-22  P11.5 RULED — crash-recovery autonomy, A100 default, branch workflow; prep landed on work/p11-5-autonomy
goal:    Kam: "we can coordinate GPUs and runtimes now" — larger GPU to dodge runtime limits; if a run crashes
         Claude may pull, fix, test on a smaller GPU and rerun on the larger GPU without asking; nothing to
         main without approval; work branches free; a permissions prompt; a mega prompt for next session.
did:     Plan + prompts -> D:\tools\claude-config\plans\because-we-are-not-parallel-codd.md (session-start
         mega prompt, /loop prompt, permission-approval prompt). Kam's answers: first launch of each queue
         ask-first; NO spend cap tonight ("we are learning") but loop intervals back off 10->60 min; A100 40 GB
         for real runs, L4/T4 for canaries. Explore agent facts: cockpit clone is --depth 1 = single-branch
         (checkout of a work branch fails on a reused runtime); manifest records no branch/GPU; the repo's
         .gitignore whitelists Scripts/ so a Scripts/.claude/settings.json would be TRACKED -> permission
         rules live in user settings only. STEP 0 (this branch): OVERHAUL_PLAN P11.5 (ruling, canary
         definition, branch rule, GPU tiers, loop pacing, allowlist JSON), rule 3 + open rulings + P11 header
         amended, runbook steps 3-5 (A100, BRANCH, no-ask relaunch); CLAUDE.md spend gate + rule 1c; cockpit
         cell 1 BRANCH (clone --branch; fetch --depth 1 + checkout -B FETCH_HEAD on re-run), cell 0/6 A100 +
         branch text, cell 2 nvidia-smi; manifest git_branch/gpu/gpu_mem_gb (torch-free nvidia-smi);
         queue header GPU line; queue YAML hours on A100.
decided: permissions = user settings only (repo would track them); deny rules protect main regardless of
         prompt wording; canary = smallest job exercising the fix (<= ~1.5 h) on L4/T4.
files:   OVERHAUL_PLAN_2026-08-20.md, CLAUDE.md, pipeline/colab_launch.ipynb, pipeline/phase4seg/cli.py,
         pipeline/phase4_train_queue.py, pipeline/queue_A_2024_2017.yaml, pipeline/queue_B_2019_2022.yaml,
         CHATLOG.md — all on work/p11-5-autonomy (NOT main).
next:    Kam: paste the permission prompt (plan file, prompt A) -> user settings; merge/push
         work/p11-5-autonomy to main when the diff is approved (or run next session from the branch:
         cockpit BRANCH = 'work/p11-5-autonomy'). Next session = the mega prompt, Step 1 onward.

## 2026-08-22  P11.4 PREREQS LANDED — staging lock, ceilings, resume fix, per-queue logs, balanced queues; MCP inventory done
goal:    Kam: no hand launches; get everything in place so the next session runs the agentic two-runtime workflow.
did:     MCP INVENTORY (read-only stdio probe; server tools load only at session start): ColabMCP (colab_mcp 1.0.1,
         FastMCP 2.14.5) exposes ONE tool cold — open_colab_browser_connection. It opens the browser at
         colab.research.google.com/notebooks/empty.ipynb#mcpProxyToken=..&mcpProxyPort=..; the Colab page connects
         back over a localhost websocket and the server PROXIES the Colab frontend's notebook tools (listChanged).
         One tab = one session = one runtime per connection; tools not enumerable until attached; no Google auth in
         the package — the browser tab is the credential. Nothing called.
         CODE (gates green: py_compile; preflight 2024/inference + 2019/tile; CPU smoke PASSED; --dry-run both
         queues; 6-case local unit test of the lock):
         (1) phase4seg/common.py _StagingLock — per-claimant files in phase4/locks/ (NO O_EXCL: Drive is not
             POSIX), oldest live claim holds, 60 s heartbeat, 15 min stale-break, dead-pid check, 60 min max-wait
             then proceed unlocked + warn, >= 1 GiB copies only; core.py tile staging same lock, stat pass outside
             it; guard tests the real mount (config.BASE is the Colab path everywhere). REWRITTEN after review
             (first version used O_EXCL + 240 min max-wait + unbounded continue paths + raised out of __enter__);
             v3 after REVIEW-2: confirm-after-60 s second listing, in-place re-stamp (no rename-over), one-poll
             hysteresis on a vanished claim, reader-clock liveness (skew-immune), fail-closed stat, claim kept on
             max-wait fallthrough, queue sweeps a killed engine's claim, labels ceiling 45->120, malformed-JSON
             guard, .tmp sweep. Residual (documented): propagation lag > 60 s or a wedged mount; lost races are
             logged by the holder's heartbeat.
         (2) phase4_train_queue.py STEP_TIMEOUT_MIN inference 240->480, tile 90->180, train 240->300: 2017's
             CoE-grid inference took 254.9 min, so the old ceiling would have killed every 2024/2017/2022
             inference 15 min short (audit finding; ~4 h GPU would have burned tonight had staging completed).
         (3) resume (_completed_steps) drops (job,step) whose latest VERIFY:{step} hard-failed — a step that exits
             0 without its artifact is no longer skipped on relaunch (audit finding).
         (4) per-queue nohup logs train_queue_nohup_{queue}_{ts}.log (cockpit cell 3; cell 4 merges all status
             files; cell 6 updated) — the shared path lost queue3's stdout tonight.
         (5) queue_A_2024_2017.yaml (~10 h L4) + queue_B_2019_2022.yaml (~8 h L4): balanced two-runtime split;
             merged-reader resume skips 2024 labels/tile/train/evaluate + 2019 labels (verified locally).
         (6) OVERHAUL_PLAN P11 runbook: mechanism, prereqs, 7-step next-session sequence (every launch its own ask).
         AUDIT (4-agent workflow, refuted where wrong): pre-P11.1 clobber semantics confirmed (last writer wins;
         both tonight's runtimes ran 57bc07b). SCORING PRE-STAGED: --prob is MANDATORY (resolve_prob is
         suffix-blind); deployed_threshold takes the rgb+chm OVERALL row of semantic_eval_report.csv, which for
         2019/2017/2022 does NOT exist until the queue's evaluate step lands — today it would silently use the
         stale July rgb rows .5003/.4997/.4822, so the scorer console MUST say channels=rgb+chm; 2024's row exists
         (.5043). Refs: 2024/2019/2022 vs D:\edmonds-pipeline\Imagery\ccap_2021_hires_lc.tif (T3 clipped);
         2017 vs ccap_2016_hires_lc_snohfull.tif (full; demotes the xsensor .7986 row — intended). Each score =
         two full passes over a Drive raster: ~20 min (2019), ~50-60 min (CoE years); run sequentially.
         CORRECTION (Kam 02:50Z, "not proven"): every "stalled under the throttle" statement reworded to "went
         silent; cause not established" — CHATLOG, plan, queues, notebook, code comments, status rows, memory.
decided: lock = precaution against ONE candidate cause, not the fix; ceilings sized for a foreign staging wait;
         A/B balance 2024+2017 / 2019+2022 (10 h / 8 h) over 2024+2019 / 2017+2022 (7 h / 11 h).
killed:  editing files through bash heredoc python with double backslashes (the tool transport collapses them) and
         without CRLF handling (common.py, train_queue.py, CHATLOG are CRLF) — write the script to a file instead.
files:   pipeline/phase4seg/common.py, pipeline/phase4seg/core.py, pipeline/phase4_train_queue.py,
         pipeline/colab_launch.ipynb, pipeline/queue_A_2024_2017.yaml, pipeline/queue_B_2019_2022.yaml,
         OVERHAUL_PLAN_2026-08-20.md, CHATLOG.md; scratch unit test test_staging_lock.py (session scratchpad only).
         REVIEW (3-lens adversarial workflow, 33 verified): 29 confirmed / 4 refuted -> all 29 addressed:
         lock rewritten (above); lock dir pre-created on Drive + at queue launch + cockpit cell 1 (two VMs racing
         mkdir = two same-named folders); resume also revokes on later FAIL/TIMEOUT/INTERRUPTED/RUNNING and job-end
         VERIFY; footer/utcnow nits; cockpit cell 2 dry-runs the launch YAML; cell 4 guards empty; docs: 214 s ->
         12-26 min, 7.5 cm -> 5 cm true GSD (IMAGERY_FACTS), "~10 min into" -> "~10 min apart", ONE SERVER
         INSTANCE = ONE COLAB TAB (websocket_server.py:113-118 rejects a 2nd socket) -> 2nd runtime needs a 2nd
         mcp entry colab-mcp-b (command in the runbook), P11.1/2/3/4 text reconciled, CLAUDE.md spend-gate wording.
         REVIEW-2 (lock only, 2 lenses, 22 verified): 19 confirmed / 3 refuted -> lock v3 above; the unit test grew
         a two-view lagged-propagation simulation (exclusion must hold for lag < confirm; FIFO after release) —
         the harness that proved v2 lost exclusion whenever drivefs lag exceeded the 10 s settle. A Drive-file
         lock is best-effort by nature; v3 bounds the exposure and LOGS every lost race. No third round.
next:    NEXT SESSION = OVERHAUL_PLAN P11 runbook: claude mcp list -> open_colab_browser_connection (Kam's yes) ->
         tool inventory -> cells 1-2 on a CPU runtime -> propose launch A (queue_A, L4, 1 runtime, ~10 h) ->
         launch B via colab-mcp-b (registered + connected 03:40Z; >= 2 min after A) -> monitor ARTIFACTS -> score (threshold gate) ->
         harvest -> registry rows. Kam: git push github main --tags after this session's commits.

## 2026-08-21  RESUME on D: — colab-mcp NOT registered; 2024-finish + queue3 SILENT since 01:12Z; nothing new to score
goal:    resume after P11: verify colab-mcp read-only; locate GPU work from ARTIFACTS; score newly-VERIFIED years;
         harvest; re-arm watch.
did:     colab-mcp: first read "not registered" was WRONG IN DETAIL — I scanned ~/.claude.json but this install's
         config is D:\tools\claude-config\.claude.json. Truth: last session registered it at LOCAL scope
         (project G:\My Drive\treedata\Scripts, command `uvx` by name); it never connected because
         Python312\Scripts is on neither user nor machine PATH (uv 0.12.5 installed 18:33 local). Tonight
         (Kam's commands, 02:00-02:12Z): user-scope entry with absolute uvx.exe path; local duplicate removed;
         first health check timed out at 30 s (uvx building from git); MCP_TIMEOUT=240000 claude mcp list ->
         ✔ Connected 02:20Z (11 s, cache warm). Read-only tool inventory owed — server tools load at session
         start. Nothing launched.
         GPU state from artifacts (Drive API, server-side mtimes — not local sync): train_queue_status.csv
         01:12:36Z, train_queue_nohup.log 01:12:52Z, 2000-canary manifest 01:29:11Z (cell-5 re-run, no status
         row). queue3 runtime: NOTHING after its 2019 tile manifest 01:03:07Z — tiles write straight to Drive
         (tiling.py rasterio.open(img_out,"w")), so a live tile step leaves files; tiles/2019 = 668 July files,
         unchanged 47 min. 2024 runtime: nohup ends at the "Step 5" header; next print is the staging ⏱ tock
         (core.py step_inference → _stage_imagery_local); none after 36 min. CORRECTED 03:10Z: I wrote "214 s"
         for 2017's staging — the logs show 12-26 min (six stagings) and 19.1 min for 2024, so A's silence was
         only MILDLY anomalous; B's 55 min (King orthos stage in <= 2.5 min) clearly was. The stagings began ~10 min apart (11.7 GB 2019 @01:03Z, 26.9 GB 2024 @01:12Z) and each runtime
         went silent seconds after its own began; a cell-5 canary started 01:29:11Z on one of them wrote its manifest but never its
         step log (a 0-s step) — that VM's Drive writes stopped too. CAUSE NOT ESTABLISHED (Kam, 02:50Z:
         'not proven'): download throttle during parallel staging (measured 08-21) is one candidate;
         a wedged Drive mount or VM death fit the evidence equally. Staging lock = precaution against
         the first only.
         No new VERIFY row, no new prob raster → nothing scorable tonight. Sizes: 2024 ortho = same 31.53 Gpx
         grid as 2017 → inference ≈ 4h15m L4 AFTER staging; queue3 ≈ 13.5 h L4 (2019 ~2.5 h, 2017/2022 ~5.5 h
         each) → two windows.
         Harvest: train_queue_status.csv (01:00–01:12Z rows) → f4601c4. Monitor armed: new status rows / run
         dirs / 2024-2019-2017-2022 prob+mask rasters / tile counts / STALE alerts at 120-600 min.
         FOUND: 2013 citywide_rgb .7422/.8672 (quoted in CHATLOG recipe-matched table AND WORKPLAN §1.3) is
         live=0 in qc_indep_report.csv line 40 — superseded by the 2013 xsensor re-score 19:57Z same ref (live
         flag keyed (year, ref) cannot hold two series), and scored at fallback thresh 0.5, not tool-chosen.
         Quote .7422 with footnote until re-scored (WORKPLAN wins). Scoring 2017 citywide will likewise demote
         the xsensor .7986 row — INTENDED (queue3 exists to replace it), not data loss.
decided: report "both silent, cause unknown" — A's missing stage tock is evidence of silence, not of a throttle.
         Fix 2013 by re-score (newest → live=1), no scorer change tonight.
files:   phase4/qc/train_queue_status.csv (f4601c4), CHATLOG.md (STATE + this entry)
next:    KAM (in order): (1) `git push github main --tags` — d038f34 (P11.1) + f4601c4 + this commit are
         UNPUSHED; every runtime tonight cloned 57bc07b; any relaunch must clone HEAD. (2) DONE: Kam
         stopped both runtimes ~02:05Z (silent 55+ min; cause unproven). Rows closed INTERRUPTED + harvested.
         Relaunch = NEW ask, proposed: queue_2024_finish.yaml, 1 runtime, L4, ~4.5 h (stage ~4 min healthy +
         ~255 min inference per the 2017 precedent); then queue3.yaml in its own window (~13.5 h: 2019 2.5 h,
         2017/2022 5.5 h each). Never stage two orthos at once. A new VM clones HEAD -> per-queue status files.
         KAM 02:15Z: NOT relaunching by hand — waiting for the agentic MCP path to launch queues in PARALLEL.
         Prereqs before that trial: (a) fresh session, colab-mcp read-only inventory (auth step expected);
         (b) engine staging LOCK (Drive lock file + stale timeout) so concurrent runtimes serialize ortho
         staging — removes the throttle candidate (account-wide quota; two stagings overlapped tonight); (c) per-
         runtime nohup log (cell 3 path is shared; queue3's stdout was lost when 2024 relaunched with >);
         (d) split queue3+2024 into two balanced queue files (~9 h each: 2024+2019 / 2017+2022).
         (3) DONE 02:20Z: colab-mcp registered USER scope, absolute uvx.exe path, ✔ Connected. Owed: read-only
         tool inventory in a fresh session (README documents no auth flow — expect a browser step).
         CLAUDE when rasters land: qc_indep 2024 + 2019 vs clipped ccap_2021_hires_lc.tif (T3 footing), 2017
         vs ccap_2016_hires_lc_snohfull.tif, 2022 vs clipped ccap_2021 (2021-epoch); re-score 2013 citywide;
         harvest --commit; registry rows from manifests (generator still deferred).

## 2026-08-21  P11 ADOPTED — Kam hands Claude the GPU keys, ask-first ALWAYS; status clobber fixed
goal:    Kam ruling: Claude may drive Colab via MCP server; MUST ask permission before EVERY
         launch (queue, tier, runtime count, cost); cap 2 concurrent runtimes.
did:     P11.1 landed: per-launch status files train_queue_status_{queue}_{ts}.csv (concurrent
         queues clobbered the single CSV — observed 2026-08-22 01:00-01:03Z when 2024-finish +
         queue3 ran together); readers merge all train_queue_status*.csv (resume, pipeline_status,
         watch_queue). CLAUDE.md spend-gate rewritten; OVERHAUL_PLAN updated w/ P11 + status.
         Windows: canary DONE (manifest 20260822T005611Z, git 57bc07b — provenance LIVE);
         2024 inference relaunched cleanly after 2nd runtime death (verified writes = NO stub
         this time); queue3 to follow. P1 backup COMPLETE earlier today.
decided: keys-with-permission > human-paste (Kam). One queue per runtime. 2-runtime cap until
         Drive-throttle interplay measured (account throttle hit 2x on 2026-08-21).
next:    Kam connects Colab MCP server → Claude verifies read-only → two-runtime trial on next
         real workload (per-launch yes). Deferred still: registry generator, QC provenance,
         P9 sync, P10 cleanups.

## 2026-08-20  OVERHAUL P1–P7 EXECUTED — code moved home, engine hardened, Colab cutover staged
goal:    execute OVERHAUL_PLAN_2026-08-20.md same session as adoption.
did:     P1: robocopy Drive→D:\edmonds-pipeline\backup launched (prob_2020 102GiB solo /Z first,
         then models[sem_best]/masks/gpkg/parquet/phase3/CoE-orthos legs; ~310GB after trims:
         skip sem_latest twins, crops [3.6GB, regenerable], phase5, KingCo 75GB raw [flagged],
         upsample [skip, regenerable]; dedupe vs D:\Imagery). P2: git clone --no-hardlinks →
         D:\edmonds-pipeline\treedata, remotes github+drive-mirror, 48 tags, identity set.
         P3: reorg pipeline(20)/qc(38+html)/scratch/_archive, 299 renames, zero untracked
         (gitignore whitelist admits Scripts subtree — no edit needed); path fixes: LOGS_DIR→
         phase4/logs (35 files), SCRIPTS→__file__ (train_queue/p1 — clone runs CLONED code),
         sentinel probe→Full_Image, pipeline_log provenance re-anchored __file__ (was hashing
         Drive copy), viz/smoke/catalog_check/latent_adversarial path fixes, queue false-MISSING
         fix, docstrings→clone paths; requirements-colab/local.txt (phase0 pins frozen-legacy);
         CLAUDE.md REWRITTEN (two-planes), README git section, doc path refs. VERIFIED: 66
         py_compile, catalog 18/18, preflight, smoke CPU end-to-end, dry-run, data_inventory.
         P4: (1) _copy_to_drive resurrected w/ size+sha256+retry; prob/mask/gpkg full-sha,
         ckpt size-verify — 2022-0-byte/2017-nodata/2024-stub class dies loudly; (2)
         _stage_tiles_local — epochs read NVMe not FUSE (tile_index abs paths rewritten);
         (3) per-step VERIFY:{step} rows, hard-fail aborts job before next GPU dollar.
         P5: colab_launch.ipynb cockpit (clone via GH_TOKEN secret, check cells, nohup launch,
         monitor). P6: run manifests phase4/runs/{run_id}/manifest.json (git sha+dirty, pip
         freeze, seed, argv, resolved imagery), run_id in log fields; training seeded (cudnn/
         AMP nondeterminism accepted); --queue YAML (queue3.yaml, queue_2024_finish.yaml);
         loss-history tagged; area CSV keyed (year,run_tag); tile signature + ortho name+size
         (mtime excluded — phantom-M lesson; legacy caches grandfathered). P7: harvest_results.py
         (first harvest: 3 files) + untagged-overwrite gate (--allow-overwrite).
decided: gates green per commit (preflight+smoke each engine change). mtime NEVER in signatures.
         Ckpt verify = size-only (per-epoch cost); rasters = full sha.
killed:  running engine cli locally for manifest test — would recreate stray C:\content dir.
files:   commits af28526..505b9ab on main (D: repo). Key: 2b622f2 reorg, a052f52 verified
         writes, 5acf16d tile staging, 3e615c9 per-step VERIFY, abf6d96 manifests+seeds,
         04f535a queue-as-data, 2b2edb0 harvest, 505b9ab overwrite gate.
next:    Kam: .git pointer delete, push, PAT, D2, canary → queue_2024_finish → queue3 windows.
         Claude next session: P1 sha manifests+verify (if not done), registry generator,
         QC provenance, pipeline_status.py, watch_queue.py, dag.yaml, mirror_sync.py.

## 2026-08-20  OPTION A OVERHAUL adopted — master plan landed; P0 bookkeeping done
goal:    Kam adopted Option A (re-plumb planes) after 4-env audit. Make plan + decisions durable.
did:     OVERHAUL_PLAN_2026-08-20.md written (phases P0-P10 + verified ground truth from 3-agent
         familiarization sweep: docs, engine, data/infra). 2024 inference found DEAD not RUNNING:
         prob raster = 2.5MB truncated stub (3rd unverified-write failure after 2022 0-byte, 2017
         96.5%-nodata). Stub set aside .stub-20260819; status CSV row closed FAIL; registry
         backfilled 6 rows for the 08-19 QUEUE2 runs (2005/2007/2009/2021k/2023 + 2024 partial).
         STATE active-plan pointers fixed (still named honest-measurement-overhaul.md, demoted 08-19).
decided: Option A adopted (Kam). B declined — no scheduler reaches a human-launched Colab. C later.
         No forwarding shims. Backup trims: skip sem_latest twins/crops/phase5, dedupe vs D:\Imagery.
         D2 polarity NOT recorded — awaits Kam confirmation (adopted ruling reverses draft rec).
files:   Scripts/OVERHAUL_PLAN_2026-08-20.md (new), run_registry.csv, WORKPLAN_2026-08-19.md,
         phase4/qc/train_queue_status.csv, phase4/masks/*2024*.stub-20260819, CHATLOG.md
next:    P1 backup robocopy (measure-first) → P2 clone to D: + detach Drive → P3 reorg.

## 2026-08-20  phase2 gpkg copy DELETED after measured review — cleanup's last pending row closed
goal:    the 1.5 GB phase2/"Copy of edmonds_crowns_phase1.gpkg" was the last
         disposition-pending item; "duplicate" was a guess (sizes differed).
did:     MEASURED, not assumed: same layer, same 222,435 features as the phase1
         original; copy had 148 cols vs original 191, but 7 copy-only cols
         (auto_label, auto_confidence, auto_fp_rule, impervious_frac,
         median_vs_roof, n_high_alpha, n_veg_years) — ALL present in
         phase1a/edmonds_crowns_phase1a.gpkg (198 cols, the superset). Copy was
         an intermediate state fully contained in the phase1a deliverable ->
         deleted. Also this session: BOTH mirror pushes ran (Kam added
         Bash(git push:*) + Bash(rm:*) allow rules via /permissions) — full
         history now on drive-mirror AND github, first offsite copies ever.
decided: verify containment before deleting a "duplicate" — the size mismatch
         would have made a checksum comparison lie; column-set containment was
         the right test.
files:   README.md (phase2 row) · CHATLOG.md (this entry)
next:    cleanup COMPLETE except: _backup_accept_all (held until U1 + 2016c
         close) and the owed CHATLOG STATE compaction (fresh session).

## 2026-08-19  verify-tier dispositions DECIDED by Kam — 3 more deletes, 3 keeps, README updated
goal:    close the "disposition pending" rows the cleanup left open.
did:     DELETED (Kam approved): tiles/ (phase-0/3 tile cache), impervious/impervious.tif
         (1.48 GB statewide source, re-downloadable; the edmonds clip stays and is the
         only file scripts read), Full_Image/temp/ (empty), stale empty bare mirror
         G:\My Drive\_treedata_git_mirror.git (0 refs, never armed). MOVED:
         Full_Image/Image_Scripts/ (4 March-era acquisition notebooks + arcgis_agent.py)
         -> Scripts/_archive/Image_Scripts/, now git-tracked (commit 1dcdecb).
         KEPT (Kam decided): inference/ DTM tifs (112 GB) — "readily access those for
         analysis"; labels/ (346 MB) — per-site distance-transform GeoTIFFs, phase-0
         training targets derived from polygons/, regenerable but kept. checkpoints/ v7
         kept (provenance for the 222k-crown deliverable). _backup_accept_all/ still
         HELD (recommend: keep until U1 + 2016c decisions close, then delete).
decided: labels/ are NOT hand labels — phase0_instance_seg.py header confirms
         "Distance transform GeoTIFFs per training site"; the hand-made assets are
         polygons/, photos/, and the 2020 mask. My permission layer blocked the labels/
         delete twice before Kam decided to keep it anyway.
files:   README.md (4 rows + cleanup line -> ~37 GB) · CHATLOG.md (this entry)
next:    phase2/"Copy of edmonds_crowns_phase1.gpkg" review still pending — layer-count
         comparison vs phase1 original was running in the background when this landed.

## 2026-08-19  README.md rewritten — full ecosystem map, every top-level item has a line
goal:    Kam must be able to walk a stranger through the whole tree and say what each
         thing does. Old README's directory map covered 8 of 51 top-level items;
         ~155 GB (inference/, phase3/, Full_Image/, checkpoints/, phase5/, labels/,
         tiles/, _backup_accept_all/ ...) was undocumented.
did:     Rewrote README as the map. New sections: entry-point chain (WORKPLAN_2026-08-19
         wins -> CHATLOG STATE live log -> README map; retired the "STATE is the single
         source of live truth" line), git architecture (tree on G:, DB on D:, tags
         v001-v048, whitelist .gitignore => everything else has NO git safety net, both
         remotes drive-mirror + github, Kam pushes --mirror himself), top-level map as
         3 tables LIVE / ARCHIVAL / HELD (name | size | status | what it is), data-flow
         prose imagery+labels -> Colab phase4seg -> masks -> QC vs independent refs ->
         Reports -> city deliverable, plus D:\edmonds-pipeline\Imagery 83GB mirror.
         Doc map now lists all 12 Scripts/*.md + 2 HTMLs + workplan xlsx + Reports/*.md
         + _archive/README with one-line purposes. Kept "Rule of the repo" one-home
         paragraph near top. Sizes flagged approximate (du on FUSE is slow).
         One cleanup line notes ~35 GB removed 2026-08-19; deleted items NOT in the map.
decided: load-bearing misspellings `City Boundry/` and `bathology/` documented as
         intentional (scripts reference the paths) instead of quietly renamed.
files:   README.md · CHATLOG.md (this entry)
next:    STALE, out of this worktree's write scope: CLAUDE.md rule 1c still names the
         mirror `G:\My Drive\_treedata_git_mirror.git` and says "no remote" - actual is
         `drive-mirror -> G:/My Drive/edmonds-git-mirror.git` + `github`. Also CLAUDE.md
         Drive-Layout ASCII still lists deleted phase6/.

## 2026-08-19  litwatch_scratch/README.md — new, documents INSTRUMENTS vs WRITERS split
goal:    litwatch_scratch/ (recovered lit-watch scratchpad) had no README - risk of
         someone re-running a one-shot ledger appender and duplicating entries.
did:     New README.md. Two populations: INSTRUMENTS (29 analysis scripts, safe to
         run, several verified/cited by project docs - buildings, cast, cast2*,
         chk1936, cr, height_by_surface, hist, overcount, overhang*, overhang_recall,
         q119, q121, q121b, q121c, q122, q128, q131, q131b, q134, q135, q136*, q137,
         q137b, q138, q138b*, refcompare, rescore, sampler*, unmeasurable - * = re-run
         and verified 2026-08-19); WRITERS (77 one-shot ledger appenders, NEVER
         RE-RUN - upd11-upd80 append to litwatch_robustness.md, chat69/chat72/chat77,
         entry3/4/5, append.py appends rows to Literature_Tracker.xlsx w/ auto-
         incrementing IDs - non-idempotent by design, output is the authoritative
         artifact). Also notes *.json = cached search results, *.out = captured
         outputs, *.npz = regenerable caches (git-ignored per this session's
         .gitignore commit).
         COUNT CORRECTION: task spec said 229 files; `find litwatch_scratch -type f`
         measured 227. Used the measured number per this project's honest-measurement
         rule rather than transcribing the unverified figure.
files:   litwatch_scratch/README.md (NEW)
next:    -

## 2026-08-19  Method_Pipeline.md imagery-stack table replaced with IMAGERY_FACTS.md pointer
goal:    stop Method_Pipeline.md's Imagery Stack table drifting from measured reality.
did:     Table listed 18 acquisitions with nominal GSDs - stale twice over (19 in-scope
         rasters on Drive, nominal GSDs wrong by up to 6x, per IMAGERY_FACTS.md).
         Replaced the table's content with a pointer to Scripts/IMAGERY_FACTS.md (one
         home, updated 2026-08-19) plus a one-line summary: 19 rasters, 2000-2024, 4
         sources (King County, City of Edmonds, Snohomish Co., NAIP). Rest of the file
         (tier logic, hyperparameters, etc.) untouched.
files:   Method_Pipeline.md
next:    -

## 2026-08-19  two stale-claim fixes — Reports/ tracking status, work-plan xlsx path
goal:    fix two outdated pointers found during the doc pass.
did:     canopy_definition_PROPOSAL.md said Reports/ is git-ignored so
         Measurement_Validity_Assessment_2026-08-18.md is NOT version-controlled -
         outdated since 2026-08-18, when Reports/*.md and *.csv started being tracked.
         Fixed the sentence to say it IS tracked.
         pipeline_buildtracker.md pointed at `Admin/Tree Project Work Plan.xlsx` -
         that file now lives at `Scripts/_archive/Tree Project Work Plan.xlsx`. Fixed
         the path.
files:   canopy_definition_PROPOSAL.md · pipeline_buildtracker.md
next:    -

## 2026-08-19  honest-measurement-overhaul.md demoted — superseded by WORKPLAN
goal:    stop honest-measurement-overhaul.md reading as live when WORKPLAN_2026-08-19.md
         already superseded it.
did:     Added SUPERSEDED 2026-08-19 banner under the title, pointing to
         WORKPLAN_2026-08-19.md (wins on disagreement; this file kept for provenance).
         Status line changed ACTIVE -> SUPERSEDED. §0 baseline table's 2016 recall
         0.684 (used the clipped reference) got an inline correction note - honest
         figure is .6636 per WORKPLAN §1.1 - number left as originally measured, not
         silently rewritten.
files:   honest-measurement-overhaul.md
next:    -

## 2026-08-19  CLAUDE.md entry-point chain fixed — WORKPLAN first, phase5/6 annotated
goal:    fix stale routing in Scripts/CLAUDE.md - it still pointed readers at CHATLOG
         STATE as "the single source of live truth", but WORKPLAN_2026-08-19.md and
         CHATLOG STATE itself have since agreed WORKPLAN is the entry point and wins
         on disagreement.
did:     Updated the top blockquote and the "Sources of truth" bullets to: read
         WORKPLAN_2026-08-19.md FIRST (entry point, wins on disagreement), then
         CHATLOG STATE for live log/state. Surgical - routing sentences only.
         Phase table: 5-8 row said "Not yet built" with no context. Annotated -
         phase5/ (3.8GB, model.pkl) and the now-deleted phase6/ were abandoned
         forward-experiments (Kam confirmed 2026-08-19); phase5/ stays because
         phase4_qc_score.py, phase4_qc_indep.py, phase4_threshold_diagnostic.py still
         read its outputs.
files:   CLAUDE.md
next:    Drive-Layout ASCII tree (line ~109) still says "phase5/…phase8/ not yet built"
         and lists phase6/ (now deleted) - same stale claim, different section, not
         in scope here.

## 2026-08-19  .gitignore fixes — Literature_Tracker whitelist bug + npz caches
goal:    close two .gitignore gaps found during the cleanup pass.
did:     whitelist bug: `!/Admin/Literature_Tracker.xlsx` matched nothing - the file
         lives at REPO ROOT (README.md line ~31), not Admin/. Result: the 68-paper
         tracker, actively used, modified 2026-08-19, was NEVER version-controlled.
         Added `!/Literature_Tracker.xlsx` at root, kept the old Admin rule as-is.
         Added `*.npz` to the Scripts binary-data excludes (alongside *.tif/*.pt/
         *.pth/*.parquet/*.gpkg) - covers the regenerable caches in litwatch_scratch/.
files:   .gitignore
next:    -

## 2026-08-19  ecosystem cleanup — GitHub connected, worktrees pruned, ~35 GB legacy deleted
goal:    repo hygiene pass (worktree worktree-ecosystem-cleanup) — GitHub backup, dead
         worktrees, orphan dirs, safe-tier legacy bloat.
did:     GITHUB: gh CLI 2.97.0 installed, authed as Kameron-Eck. Private repo
         github.com/Kameron-Eck/edmonds-treedata created. Remotes added: `drive-mirror`
         -> G:\My Drive\edmonds-git-mirror.git (NEW bare repo, Drive-synced) and `github`.
         Kam runs `git push --mirror` to both himself.
         WORKTREES: 12 merged worktrees + their worktree-* branches pruned. All verified
         merged into main first; `git branch -d` succeeded on every one (refuses on
         unmerged) - nothing lost.
         ORPHANS: C:\content Colab-path gotcha dir removed (verified 0 bytes first).
         D:\edmonds-pipeline\treedata orphan dir removed; its version_script.py variant
         (a blob not in git history) archived to
         Scripts/_archive/orphans/version_script_D-orphan-variant.py rather than deleted.
         SAFE-TIER DELETE (~35 GB, zero live references, Kam approved each category):
         temporal_results/ 8.8GB, phase6/ 3.6GB (abandoned experiment, Kam confirmed),
         clips/ 3.7GB, near_infrared/ 2.9GB, Temp/ 2.1GB, pipeline/ 940MB, Scripts_v2/
         (zero refs, its own text says Scripts/ is canonical), checkpoints/Temp/ ~13GB
         (superseded v5 generation; v7 root files kept), 0-byte stubs
         checkpoints/{ddt_best_global,test}.pt, Untitled0.ipynb,
         TreeCrownInventory.BACKUP-2026-07-08.ipynb (its extra code cells = the documented
         phase0_instance_seg.py extraction; outputs were only streams/errors/2 PNGs), 4
         empty dirs (NDVI, phase1c, review_data, .ipynb_checkpoints), stale ArcGIS
         *.sr.lock files in City Boundry/.
         PHANTOM-M: files on main showing modified with empty diffs (Drive mtime noise)
         cleared per-file after `git diff --quiet` verification; train_queue_status.csv
         left dirty on purpose (Colab 2024 inference RUNNING, real state).
decided: HELD BACK for Kam's explicit call: _backup_accept_all/ (1.9GB, sole pre-accept-all
         model snapshot) - not deleted, needs his sign-off.
         Verify-tier left untouched, dispositions pending: inference/ 108GB, checkpoints/
         v7 ~14GB, labels/, tiles/, impervious statewide tif, phase2 Copy-of gpkg.
files:   (repo-level ops; see git log / gh repo view for detail)
next:    Kam call on _backup_accept_all/. Verify-tier disposition pass.

## 2026-08-19  ** 1936 IS REAL IMAGERY ** + catalog conflict resolved (IMAGERY_PLAN A1/A3/A5)
goal:    execute IMAGERY_PLAN.md order-of-work 1-2 (A1 catalog conflict, A2/A3 orphans).
** RETRACTION **  1936 IS NOT AN EMPTY SHELL. Entry "GRVI IS NOT COMPARABLE ACROSS SENSORS
         + 1936 is an empty file" said "CONTAINS NO IMAGE DATA OVER EDMONDS", from 9 constant
         probe windows. WRONG. Full-extent decimated read: 89.9% fill (253/0/255), 10.1% REAL
         panchromatic photography in the SOUTHERN QUARTER. Content band starts 74.8% down the
         file (row 20094 of 26880) - below every probe. Rendered it: shoreline, street grid,
         forest stands, lake, field boundaries. Content bbox = 24.4% OF STUDY AREA,
         lat 47.768-47.792. Prize is 1936, not 1998 - 64 yrs before current earliest year.
         METHOD RULE: a scattered-window probe proves content EXISTS, never that it is ABSENT.
         Answer "nothing here" -> render whole extent before believing it. Second time this bit.
did:     A1 catalog conflict RESOLVED. phase4seg/config.py:YEAR_CATALOG authoritative.
         pipeline_config.py DEMOTED - docstring rewritten, IMAGERY_CATALOG frozen+labelled
         (2013+ only, its KeyError on raw_path(2000) was the bug). Only importers are
         _archive/scripts/, they still parse. Pointers fixed in CLAUDE.md + buildtracker.
         NEW phase4_catalog_check.py - resolves every entry thru the one resolution order,
         opens it, asserts on-disk BAND COUNT + EPSG vs catalog, lists ortho orphans, probes
         constant fill. 18/18 PASS. exit 1 on failure so it can gate a run.
         A5 ONE HOME: config.imagery_roots() defines root order, common.resolve_native_path()
         reads it. Colab order UNCHANGED (native/ -> root); local = D: mirror -> Drive.
         A3 renamed on D: 1936_king_rgb.tif -> 1936_king_pan.tif, 1998_king_rgb.tif ->
         1998_king_pan.tif. Single-band despite _rgb. Nothing referenced either name.
** NEW DEFECT **  D: MIRROR IS PARTIAL - holds King/Snoh/NAIP years, NONE of the 4 CoE orthos
         (2017/2020/2022/2024, ~127 GB). phase4_data_inventory.py scans ONLY D:. So the CoE
         acquisitions - INCLUDING 2020, THE ONE LABELLED YEAR - have NEVER been characterised
         by the inventory. Every "measured from the file" number for those 4 needs re-checking.
         ALSO: native/ does not exist at all (not empty - absent). Every lookup always fell
         through to the root.
decided: keep 1936 (real data). quarantine nothing - measurement beat assumption.
killed:  "1936 is an empty shell / delete it" - refuted, see RETRACTION.
files:   phase4seg/config.py (imagery_roots) · phase4seg/common.py (resolve_native_path) ·
         pipeline_config.py (demoted) · phase4_catalog_check.py (NEW) · CLAUDE.md ·
         pipeline_buildtracker.md · IMAGERY_PLAN.md (A1/A3 done, A2 table corrected)
next:    IMAGERY_PLAN order 3 (B2 overviews - use gdaladdo -ro, external .ovr, do NOT mutate
         Drive originals) then 4 (B1 merged inventory - MUST cover both roots, not just D:).
         Open: A2 disposition for 2012_king + 2017_king; A4 dates (external).

## 2026-08-19  ** THE MODEL IS BETTER THAN ITS NUMBERS ** - calibration, not capability, is binding
** [AUDIT 2026-08-19 by the other session — READ BEFORE QUOTING ANY NUMBER BELOW] **
** THE CODE BEHIND THIS ENTRY NO LONGER EXISTS AND ITS NUMBERS CANNOT BE REPRODUCED. **
         The entry's own files: line names q121c.py, q131b.py, q134.py, q135.py, sampler.py
         (the 162,829-pt grid), cast2.py, chk1936.py as a "scratchpad, all READ-ONLY". Those
         live OUTSIDE the repo and vanished when the session was stopped. `find` over the
         whole tree returns none of them. So the 61% spread-reduction, the AUC-vs-proxy table
         and the matched-call-rate recalls have NO surviving derivation.
         STATUS: treat every number in this entry as UNVERIFIED. Not wrong — UNCHECKABLE.
         Do not cite it as established, and do not build a decision on it. To promote any of
         it, re-derive with a tracked script.
         WHAT DOES SURVIVE, and is committed (58ee67c): the four QC scripts
         (phase4_qc_leafoff / _turnover / _domain_cluster / phase4_build_ccap_city) and their
         outputs. Those compile and their logic reads sound. Known defects, none fatal:
         phase4_qc_leafoff.sample() computes `bounds` and never uses it; it rebuilds a
         WarpedVRT over the whole ortho inside the window loop; and `can = m > 0` counts
         255=IGNORE as canopy, which violates rule 6 but is HARMLESS on
         edmonds_canopy_mask_2020.tif specifically because that raster holds only 0 and 1
         (checked). It would silently corrupt any mask that does carry IGNORE.
         ALSO CORRECTED: this session repeated the "61% reduction" figure in conversation as
         if it were established, before checking it was reproducible. It was not.
         The LITERATURE side is a different matter and is NOT in question — DOIs verified
         against Crossref, an explicit inclusion bar, covered/queued discipline. Use
         litwatch_robustness.md for its literature; do not inherit its measurements.
scope:   loop iterations 73-77. Measurement + code reading. Nothing deployed, no plan edit.
** FINDING 1 - MOST OF THE CROSS-YEAR RECALL WANDER IS THE OPERATING POINT (Q121). **
         One recipe (_citywide_rgb), one reference (C-CAP), one footprint (161,052 pts, 98.9%),
         8 years. Only the operating point is varied.
           recall spread @ FIXED thr 0.5      0.1827
           recall spread @ MATCHED call .30   0.0721      = 61% REDUCTION
         Mechanism: thr 0.5 calls 22.0%-30.5% of the city depending on year. A fixed threshold
         is NOT a fixed operating point.
         RESIDUAL IS INTERPRETABLE where finding 3's 0.28 wander was not:
           2000 .6454 · 2002 .6541          <- the two coarsest (~40 cm true GSD)
           2005-2021 .6974 .7052 .7069 .7174 .7155 .7086   <- ALL WITHIN 0.020
         across 16 years, 3 providers and a 4x resolution change.
         CREDIT: the 2026-08-18 recipe-controlled run is column two here. This adds the SECOND
         control, not the first. The two together account for most of finding 3.
         ANOMALY: 2007 gives IDENTICAL recall at cr .20 and .25 (.6189) -> degenerate/saturated
         raster. DO NOT quote the cr=.20 row until understood (Q133).
** FINDING 2 - THE MODEL DOES NOT RELY ON COLOUR, AND IS MORE STABLE THAN ITS INPUTS (Q135). **
           year  AUCmodel  AUCbright  AUCgrvi  gain   corr(m,grvi)
           2000    .8760     .6333     .5927  +.2427     +.1882
           2005    .9134     .7170     .6941  +.1964     +.4737
           2009    .9195     .6847     .7061  +.2348     +.4745
           2013    .9125     .6881     .7273  +.2243     +.5428
           2021    .9150     .6662     .5453  +.2488     +.0755
           RANGE   0.044     0.084     0.182
         MODEL AUC VARIES 4x LESS THAN THE COLOUR STATISTICS OF ITS OWN INPUTS. Threshold-free,
         so no calibration choice is doing the work.
         2021 IS DECISIVE: worst GRVI of any year AND lowest model-GRVI correlation (+.0755,
         ~zero), yet model AUC .9150 - its second best. With 2000 (colour saturated, model still
         .8760) that is TWO independent extreme cases, not an inference from correlations.
         ONLY DIP IS 2000 = THE COARSEST YEAR. 2021's colour is worse and does not dip.
         => RESOLUTION separates the years, COLOUR DOES NOT. Same asymmetry finding 1 found.
** FINDING 3 - THE REFRAMING NUMBER: AUC .876-.920 vs MATCHED RECALL .645-.717. **
         The model's RANKING is strong and stable; only WHERE THE LINE IS DRAWN is weak.
         Q132 PREMISE CONFIRMED IN CODE: phase3_semantic_dev.py:1722
           canopy_area = total_canopy_px * pixel_area
         The AREA SERIES - the deliverable - is MAP-COUNT off a thresholded mask, with
         binary_closing applied first, which inflates it further by a threshold-dependent amount.
         phase4_qc_score.py:83 already calls its threshold source "the (circular) eval CSV".
         THREE INDEPENDENT LINES CONVERGE (GRVI drift it.72, operating point it.73, AUC gap
         it.76/77): THIS PROJECT'S MODEL IS BETTER THAN ITS NUMBERS, AND THE NUMBERS ARE
         DOMINATED BY CALIBRATION AND A MAP-COUNT ESTIMATOR.
decided: nothing deployed. Highest-value fix identified (Q136): estimate area from a REFERENCE
         SAMPLE, not by counting thresholded pixels. NOT new research - the Olofsson/CEOS
         machinery is already in the tracker and P3's sample design already exists.
         Colour-comparability problems (it.72/74/75) are REAL BUT NOT BINDING - the model
         already largely ignores the channel they damage.
lit:     +6 papers, IDs 204-209, searches 59-60, DOI/arXiv verified.
           204 Canty & Nielsen 2008 RSE - IR-MAD, invariant to gain/offset
           205 Ryadi 2023 Sensors - cross-sensor relaxation-based normalisation
           206 Chen 2023 Appl.Sci - pseudo-invariant POLYGONS (we have roofs + impervious)
           207 Geirhos 2019 ICLR - CNNs texture-biased. Unifies transfer-vs-resolution asymmetry.
           208 arXiv 2509.20234 (2025) - DIRECTLY CONTRADICTS 207. Read BEFORE leaning on it.
           209 arXiv 2509.11355 (2025) - frequency regularisation for shape bias (conditional)
         NOTE Q130/Q134 ANSWERED NEGATIVE BY MEASUREMENT: AUC is invariant under ANY monotone
         transform, so IR-MAD/histogram matching CANNOT rescue GRVI where AUC ~ 0.5 - and that
         is 2000 (.5927), 2019 King (.5835) and 2021 King (.5453). Normalisation is still worth
         doing for cross-year THRESHOLD comparability, but NOT to make greenness work.
files:   Scripts/litwatch_robustness.md (it.73-77 + Q131-Q136)
         Literature_Tracker.xlsx (210 papers, 60 searches)
         scratchpad, all READ-ONLY: sampler.py (162,829-pt grid), q121c.py, q131b.py, q134.py,
         q135.py, cast2.py, chk1936.py
next:    Q136 area-from-reference-sample. Then channel ablation (needs GPU) for Q98.
gotcha:  NO RASTER IN THIS PROJECT HAS OVERVIEWS (ovr=[] everywhere) and the prob rasters are
         ROW-STRIPED (block=(1,18944)), so every out_shape/decimated read silently reads the
         WHOLE file. Two runs stalled ~40 min at 3.5 GB before this was found. Use
         scratchpad/sampler.py point sampling instead - seconds, not tens of minutes.
         Building overviews would speed every future QC run but writes GB of sidecars on G:,
         so that is Kam's call.

## 2026-08-19  ** GRVI IS NOT COMPARABLE ACROSS SENSORS ** + 1936 is an empty file
scope:   loop iterations 70-72. Measurement + inventory. Nothing deployed, no plan edit.
** THE FINDING **  GRVI over the SAME GROUND in every acquisition, 2400 px window:
           frac>.02 = share of pixels a naive GRVI vegetation test calls green
           2000 King .8027 | 2002 .5029 | 2005 .4782 | 2007 .4016 | 2009 .6237
           2012 .6268 | 2013 .3463 | 2015 .2745 | 2017 .1877 | 2019 .1146
           2021 .1344 | 2023 .1541 | 2016 Snoh .6928 | 2019 NAIP .8919 | 2022 NAIP .7822
         DECISIVE PAIR: 2019 King .1146 vs 2019 NAIP .8919. SAME YEAR, SAME GROUND, SAME
         SEASON, differing by 0.78. Cannot be vegetation, phenology, growth or loss. It is
         sensor + processing colour balance and nothing else.
         AND THE KING SERIES DRIFTS MONOTONICALLY: .80 (2000) -> .35 (2013) -> .11 (2019),
         GRVI mean crossing positive-to-negative around 2017. ANY cross-year GRVI diagnostic
         on this series reports a large steady CANOPY DECLINE THAT IS PURE ARTEFACT.
         DAMAGES OUR OWN WORK: the leaf-off / canopy-rendering signature compared low-
         greenness fractions BETWEEN years. Those comparisons are NOT SAFE. The WITHIN-year
         use (canopy-masked pixels vs the rest of the same image) survives, because the cast
         is global. That distinction is the whole of what is left standing.
killed:  cross-year GRVI comparisons. Do not re-quote them (Q129 = trace what used them).
** CORRECTION **  1936_king_rgb.tif CONTAINS NO IMAGE DATA OVER EDMONDS.
         I reported it in it.71 as "clipped at the bright end, bright detail destroyed".
         WRONG. Nine probe windows across the city are ALL CONSTANT: mean 253.0 std 0.00
         min=max=253 in the south/centre, 0.0 in the north. A georeferenced EMPTY SHELL.
         The "p99=255 clipping" was fill value in a whole-raster downsample.
         WHY: these are KING COUNTY mosaics and EDMONDS IS IN SNOHOMISH COUNTY. A 1936 King
         survey does not reach this far north. INDEPENDENT BONUS: 2000's northern probes are
         also all-zero, so the known north-coverage gap is A COUNTY LINE, not a footprint quirk.
         1998 IS REAL (std 29-44 at all nine probes, whole city) and single-band, on the
         IDENTICAL grid to 2000 -> still the clean panchromatic pilot with a near-
         contemporaneous RGB control. Prize is 2 extra years, not 60.
did:     also (it.71) 1936/1998 are SINGLE-BAND despite _king_rgb names; every other
         _king_rgb is 3-band and phase1_preprocess.py assumes it. Dormant only because grep
         finds 1936/1998 in NO config. They share the 2000 grid exactly (18944x26880) so
         co-registration looks already done - but their GSD is INHERITED FROM THAT GRID, not
         measured from film. Do not quote grid spacing as resolution.
         (it.70) RELIEF DISPLACEMENT, 0 of 197 papers covered it. A conventional ortho is
         rectified on a BARE-EARTH DTM, so only the BASE of a tree lands correctly; everything
         above ground is displaced radially PROPORTIONAL TO HEIGHT. d=(h/H)*r -> a 20 m crown
         500 m off nadir at 3 km = 3.3 m = 33 px at King's true 10 cm GSD. Runs along the SAME
         axis as our staircase but CUTS AGAINST it (tall-band recall is our highest, .9421), so
         it cannot be manufacturing the staircase. BIGGER RISK IS THE DELIVERABLE: 17
         acquisitions = 17 frame layouts = 17 displacement fields -> SPURIOUS CHANGE on tall
         crowns near buildings (Q125).
** INFRASTRUCTURE **  NO RASTER IN THIS PROJECT HAS OVERVIEWS (ovr=[] on every file checked),
         so every out_shape / decimated read silently reads the ENTIRE file. The prob rasters
         are also ROW-STRIPED, block=(1,18944), not tiled. Two QC runs stalled at 3.5-3.7 GB
         for ~40 min before I found this. FIX ADOPTED: scratchpad/sampler.py builds a 162,829-
         point systematic grid inside the city and samples rasters at points - seconds, not
         tens of minutes. Building overviews would help every future QC run but creates GB of
         sidecar files on G:, so that is Kam's call, not mine.
lit:     +9 papers, IDs 195-203, Phase 6 searches 56-58, all DOI-verified via Crossref.
           195 Techapinyawat 2024 CACAIE - retrieves CANOPY-COVERED IMPERVIOUS SURFACES
           196 Liu 2023 RS 15:519 - U-Net specifically suffers SHADOW omission (tested, refuted)
           197 Yoo 2026 RS 18:1899 - transferable NAIP canopy framework (NAIP = our 2019n/2022n)
           198 Gharibi 2018 RS 10:581 - true ortho from frames + LiDAR; names the DTM defect
           199 Wagner 2024 RSE 302:114099 - U-Net regression, 60 cm NAIP -> LiDAR CHM, statewide.
               This is our v045/v046 aux-height experiment ALREADY DONE at scale.
           200 Chen 2014 ISPRS XL-3:67 - double-mapping; spurious multitemporal change
           201 Mboga 2020 ISPRS J 167:385 - FCN land cover from PANCHROMATIC historical frames
           202 Tian 2025 ISPRS Ann X-G:885 - NO method works on panchromatic alone; uses DL
               COLORIZATION as the bridge. Absent from all 200 prior rows.
           203 Kostrzewa 2025 PE&RS - CNN LULC from historical aerial (provisional, abstract unread)
files:   Scripts/litwatch_robustness.md (it.70, 70c, 71, 72 + Q123-Q130)
         Literature_Tracker.xlsx (204 papers, 58 searches)
         scratchpad only, all READ-ONLY: sampler.py, cast2.py, chk1936.py, q119.py, q122.py,
         height_by_surface.py, q121c.py, q128.py
next:    Q121 running (cross-year recall at MATCHED CALL RATE, point-sampled). Then Q128 -
         model DISAGREEMENT as a label-free reliability proxy: 2000/2002/2013/2015 each carry
         4-5 independently trained variants, and Baek 2022 (ID 153) says mutual agreement
         estimates OOD accuracy. Validate against measured recall before trusting it.
gotcha:  a substring match on a filename is NOT evidence - EDM_0001936.jpg is crown 0001936,
         not the year 1936, and I briefly claimed 1936 crops existed on that basis.
         piping a background job through grep BUFFERS all output until exit; use `py -3 -u
         script.py > out.txt 2>&1` instead so partial progress is readable.
         `python` is not on PATH, only `py -3`.

## 2026-08-19  TWO REFUTATIONS AND A DEPLOY WARNING - what is NOT causing the overhang gap
scope:   loop iterations 67-69, all measurement, nothing deployed, no plan file edited.
did:     (1) Q118 HEIGHT AND OVERHANG ARE INDEPENDENT, NOT THE SAME THING.
           Recall by CHM band split by surface beneath, 2016 vs C-CAP city.
           staircase SURVIVES on pervious alone: 0-2m .1206 -> 30+m .9421, spread +.8215
           staircase on impervious:              2-5m .0282 -> 30+m .7509, spread +.7227
           impervious penalty is roughly CONSTANT above 5 m (-.19 to -.29), so the two
           deficits are ~ADDITIVE. Both need fixing separately.
           WORST CELL: 2-5 m OVER IMPERVIOUS = .0282. Model finds under 3% of it. That is
           street/yard trees beside driveways - the canopy a tree ordinance is about.
           And the impervious penalty is NOT a short-tree artefact: -.19 even above 30 m.
         (2) Q119 THE CORRECTED MODEL'S OVERHANG GAIN IS AN OPERATING-POINT ARTEFACT.
           prob_2016 vs prob_2016_corrected, COMMON footprint, 321,651 C-CAP canopy cells.
           at thr .509      recall .6279 -> .8533   over-imp .3183 -> .5612   LOOKS GREAT
             but call rate on C-CAP non-canopy .0493 -> .1725  (TRIPLES)
           at MATCHED overall recall (thr .835)
                            recall .6279 -> .6296   over-imp .3183 -> .3070   GAIN REVERSES
             gap -.3739 -> -.3895 (WIDER); worst cell .0282 -> .0366 (nothing)
             matched gap WORSE where it matters: -.076 at 2-5m, -.050 at 5-10m
           IT MOVED ITS OPERATING POINT, IT DID NOT LEARN OVERHANG.
           CAVEAT STATED, not buried: corrected from NIR+CHM but scored against C-CAP, so
           this is an AGREEMENT statement not a TRUTH statement. Q120 settles it.
         (3) Q122 SHADOW REFUTED AS THE MECHANISM.
           Liu 2023 RS 15:519 says U-Net specifically suffers shadow omission - our arch,
           our symptom. Shadow falls NORTH, contrast is isotropic -> separable by geometry.
           bearing from nearest building, 2016:  N-S = +.0354 (10m) / +.0221 (20m)
           north is BETTER. Holds within matched geometry: faces N .5071 vs S .4401,
           corners +.020, E-W control flat. SIGN ERROR against the hypothesis.
           FLAGGED NOT READ INTO: cardinal .44-.51 vs diagonal .58-.61, spread .123 = 5x
           the N-S effect. Axis-aligned footprints, wall faces vs corner wedges. Artefact.
decided: nothing deployed. RADIOMETRIC FIXES RULED OUT (shadow compensation, histogram
         matching, illumination normalisation). With corrected labels also ruled out, the
         candidate list is down to HEIGHT CHANNEL or NIR BAND - v045/v046 aux-height on the
         impervious split is now the leading untested experiment.
lit:     +3 papers, IDs 195-197, Phase 6 Search 56, all DOI-verified via Crossref:
           195 Techapinyawat 2024 CACAIE 10.1111/mice.13277 - retrieves CANOPY-COVERED
               IMPERVIOUS SURFACES by post-classification. Exact inverse of our failure mode.
           196 Liu 2023 RS 15(2):519 10.3390/rs15020519 - the U-Net shadow claim above.
           197 Yoo 2026 RS 18(12):1899 10.3390/rs18121899 - transferable NAIP canopy
               framework. NAIP is our 2019n/2022n. External benchmark we currently lack.
files:   Scripts/litwatch_robustness.md (it.67-69 + Q120-Q123)
         Literature_Tracker.xlsx (197 papers, 56 searches)
         scratchpad only: height_by_surface.py, q119.py, q122.py - all READ-ONLY, none
         write to phase4/qc
next:    Q123 RELIEF DISPLACEMENT - a genuine blind spot. Ortho displaces elevated objects
         radially from nadir AND THE DISPLACEMENT SCALES WITH HEIGHT, which is the exact
         axis our staircase runs along. C-CAP is stereo-DSM derived and may be nearer
         true-ortho, so mask and reference may be misregistered AS A FUNCTION OF HEIGHT.
         Tracker search for off-nadir / view angle / BRDF / orthorectif returns 0 of 197.
         Then Q121 (running): re-score the cross-year series at MATCHED CALL RATE. Finding
         3's .50-.78 wander has never been checked against the it.68 artefact.
gotcha:  Q121 EVERY per-year threshold is calibrated separately, so ANY cross-year recall
         comparison in this pipeline is confounded until re-scored at matched operating
         point. it.68 shows the size of the effect: +0.225 of pure nothing.
         `python` is not on PATH here, only `py -3` - a heredoc starting `python -` fails
         silently mid-chain and the NEXT command still runs, so check for the alias error.
         Crossref titles carry U+2010; console is cp1252; sanitize to ASCII before print.

## 2026-08-19  ** LEAF-OFF ** - the acquisition SPEC may explain the conifer-only blind spot
goal:    lit-watch loop, iteration 45. Standing top action was "recover acquisition dates".
         Found something better: the published acquisition SPECIFICATIONS.
did:     Searched King County / Puget Sound consortium and NAIP acquisition specs.
         -> Literature_Tracker ID 194. Re-read the iteration-18 GRVI screen against them.
THE TWO SPECS ARE OPPOSITE:
  * PUGET SOUND REGIONAL ORTHOPHOTO CONSORTIUM (88 participants, King County lead manager -
    the source of our King imagery): "acquisition was to occur during LEAF-OFF season while
    ground conditions were free of snow and smoke". 2012 flown March-May "with the intent of
    representing leaf-off conditions". 2015 acquired "in the spring".
  * NAIP: flown "during the agricultural growing season, or LEAF-ON conditions".
  -> OUR ARCHIVE MIXES LEAF-OFF AND LEAF-ON AND NOTHING IN THE PIPELINE ACCOUNTS FOR IT.
IF 2020 CoE FOLLOWED REGIONAL PRACTICE (not yet confirmed), our ONE hand-labelled year was
labelled on imagery where DECIDUOUS CROWNS ARE BARE. Physical explanation for findings we have
treated as modelling defects:
  * "conifer-only-label blind spot" -> deciduous crowns not in the labelling imagery at all
  * scrub recall .25 vs forest .68  -> deciduous scrub bare, conifer forest visible
  * recall .16 (0-5m) -> .93 (30m+) -> short crowns skew deciduous yard/ornamental
  * 8/8 missed stands suburban, "purple-leaf LOW-NDVI" -> purple-leaf = deciduous = bare in spring
  * FINDING 3 IS THE TELL: 9 years span IoU .49-.76 yet recall stays pinned .51-.78. That is
    what you see when the limit is WHAT THE IMAGERY CONTAINS, not the model.
INDEPENDENT SUPPORT - iteration-18 GRVI screen re-read: both NAIP years (spec LEAF-ON) rank
  top-5 of 17 by green-excess; the bottom SIX are all King County or City of Edmonds
  (consortium, spec LEAF-OFF); 2020 is 4th LOWEST of 17.
NOT PROVEN: confirmed = the consortium SPEC, and that KC 2012/2015 were spring flights.
         NOT confirmed = that 2020 CoE followed it, nor the season of Snoh 2016/2021s.
         GRVI stays confounded with colour balance (iteration-18 caveat stands).
         RECOVERABLE: King County photo-centre index carries per-exposure ACQ_DATE + UTC_TIME.
IF IT HOLDS, IT REORDERS THE PROJECT:
  * blind spot is a DATA problem not a model problem - no architecture, augmentation, domain
    generalization or foundation model recovers deciduous crowns from leaf-off pixels.
  * right fix = LABELS ON LEAF-ON IMAGERY (NAIP years, or Snoh if leaf-on), NOT better training
    on 2020.
  * any cross-era comparison mixing leaf-off with leaf-on measures PHENOLOGY, not canopy.
  * the height curve may be substantially a DECIDUOUS-FRACTION curve.
also this session (lit-watch iterations 43-44), NEW Scripts/phase4_qc_turnover.py:
  * C-CAP 2016 vs 2021: discordance 11.16%, net -1.72pp LOSS, implied 5.33%/yr canopy loss -
    which EXCEEDS published street-tree mortality, so most of it is product revision not trees.
  * NDVI ref 2016 vs 2021s (same source, same sensor): discordance 11.14%, net +2.45pp GAIN.
  * -> THE TWO REFERENCES DISAGREE ON THE SIGN OF CHANGE. Neither can say whether Edmonds
    gained or lost canopy 2016-2021. C-CAP dominated by vintage revision, NDVI by phenology
    (its CHM is static across both dates, so the whole signal is greenness).
  * BUG FOUND+FIXED in that script: 0 = nodata in C-CAP but NON-VEGETATED in the NDVI refs.
    First run gave a false 0.97% discordance / 90.6% stable-canopy. --zero-is-data flag added.
files:   Scripts/litwatch_robustness.md (iterations 43-45) - Literature_Tracker.xlsx ID 194
         Scripts/phase4_qc_turnover.py - phase4/qc/turnover_{ccap_2016_2021,ndvi_2016_2021s}.txt
next:    (1) CONFIRM THE 2020 SEASON - photo-centre index, ortho metadata, or ask the City.
         Everything else is downstream. (2) season-label all 18 acquisitions. (3) recall-by-height
         on a LEAF-ON year (2019n/2022n, rasters already scored) vs a leaf-off year.
gotcha:  leaf-off flights are also LOW SUN ANGLE, so the shadow axis and the phenology axis are
         CORRELATED, not independent. Do not treat them as separate confounds.

## 2026-08-18  EDGE TEST — the perimeter hypothesis is TRUE, and the height staircase survives it
goal:    test the crown-perimeter hypothesis raised by the sentinel overlays, BEFORE it could
         reach the annotation plan. It threatened result (1), so it had to be measured.
did:     NEW Scripts/phase4_qc_edge_vs_interior.py — erodes the agreed-canopy mask (numpy-only
         8-connected erosion, no scipy) to split misses into crown INTERIOR vs EDGE, then
         recomputes recall by height band for each. Ran 2016 at decim 4 (2 m lattice), erosion
         1 and 2 cells. -> phase4/qc/edge_vs_interior_{2016_baseline,2016_erode2}.txt/.csv
RESULT: BOTH halves positive — see STATE result (8).
         (a) edge (outer 2 m) = 16.3% of agreed-canopy AREA but 41.8% OF ALL MISSES;
             interior recall .8191 vs edge .3306. At 4 m: 29.3% area / 65.5% misses.
             The sentinel ring pattern GENERALISES. Suburban recall .575 is substantially
             UNDER-SEGMENTATION, not blindness => a second lever: boundary/soft-label handling.
         (b) the staircase SURVIVES inside crowns: interior 5-15 m .6218 -> 20 m+ .9333,
             spread +.3115 vs edge +.3105 — the two effects are INDEPENDENT AND ADDITIVE.
             Robust at 4 m erosion (interior spread still +.2528).
decided: nothing deployed. Result (1) stands unchanged; the new finding is ADDITIVE to it,
         not a replacement. Two distinct levers now on the table (height-conditioned training,
         boundary handling) plus the operating point from result (7).
killed:  "the height staircase might be crown geometry" — TESTED AND REJECTED. Do not re-raise
         without new evidence; the interior-only spread is the number that settles it.
files:   Scripts/phase4_qc_edge_vs_interior.py (new) · phase4/qc/edge_vs_interior_*.txt/.csv ·
         CHATLOG STATE result (8).
next:    [both done same session] replicated on 2021s + bounded the reference-error caveat
         via CHM — see result (8c)/(8d). U1 (Kam) is now the only blocker; remaining local
         work is thin.

## 2026-08-18  P4 CLOSED — sentinel error overlays, and a NEW hypothesis: the misses are CROWN EDGES
goal:    last open P4 item = sentinel TP/FN/FP overlays colour-coded by the P2 partition.
did:     NEW Scripts/phase4_sentinel_qc_overlay.py — 3 panels per fixed sentinel window:
         RGB | P2 agreement partition | model outcome. Imports phase4_sentinel_snap for the
         window/bounds helpers so a site here is the SAME rectangle as there (cross-run
         comparability preserved; the existing script is untouched).
         DESIGN POINT: TP/FN/FP are drawn ONLY on ground where both references agree.
         Contested pixels get their own colour and are NEVER scored — scoring them is the
         single most common way this project has misled itself.
         Ran all 11 sites for 2016 -> phase4/qc/sentinel_overlays/*.png +
         sentinel_overlays_2016.csv
         NOTE: the "needs footprint resolution from photos/" blocker in STATE was STALE —
         sentinel_sites.json already had explicit bounds_wgs84 for every site.
RESULT — recall on AGREED ground (not comparable to citywide qc_indep, which includes
         contested px): forest_6 .955 · forest_1 .826 · forest_4 .825 · marsh_deciduous .786 ·
         forest_3 .750 · residential_mixed .575. Precision .92-.998 EVERYWHERE.
         The conifer-training -> mixed -> suburban gradient is now VISIBLE, not just tabular.
** NEW HYPOTHESIS (visual, NOT yet measured) — THE FN ARE CROWN PERIMETERS. **
         In residential_mixed and marsh_deciduous the red FN forms RINGS around the green TP
         cores: the model finds each tree clump and loses its EDGE. If that generalises,
         recall .575 there is largely a PERIMETER loss, not whole missed trees — a different
         diagnosis from "the model cannot see yard trees", and it would need a different fix
         (boundary/soft-label handling or the operating point, not new crown labels).
         IT ALSO TOUCHES RESULT (1): crown edges have LOWER CHM than crown centres, so the
         5-15 m band may be over-populated by EDGE pixels of tall trees rather than by short
         trees. That would make part of the height staircase a geometry artefact.
         TEST BEFORE BELIEVING ANY OF THIS: split FN into interior vs edge (binary erosion of
         the agreed-canopy mask) and recompute recall by height band for each. Local, cheap.
         Do NOT let this into the annotation plan until that runs — it is one look at two
         windows.
decided: nothing deployed. P1/P2/P4 now all complete; P3 is the only phase left and is gated
         on U1, which is Kam's call.
files:   Scripts/phase4_sentinel_qc_overlay.py (new) · phase4/qc/sentinel_overlays_2016.csv ·
         phase4/qc/sentinel_overlays/*.png (NOT tracked — figures, per the rasters rule) ·
         CHATLOG STATE PHASE STATUS.
next:    the edge-vs-interior FN test above. Then U1 (Kam).

## 2026-08-18  U4 ANSWERED — calibration is a real lever, and the old per-year spread was a recipe artefact
goal:    cheapest-next-move #4 / STATE correction (3): recompute miss-depth PER YEAR on ONE
         recipe, so the "labels vs calibration" call stops resting on 2016 alone.
did:     NO NEW CODE — phase4_qc_forest_misses.py already takes --years + --prob-suffix, and
         its own footer says to compare within one recipe (--force-citywide) to avoid the
         tier-recipe confound. Ran --years 2000,2002,2013,2015 --prob-suffix _citywide_rgb
         --thresh 0.5 (fixed threshold = the fair cross-sensor choice). ~55 min, local, no GPU.
         -> forest_miss_{2000,2002,2013,2015}.txt/.csv + forest_miss_sensor_compare.txt/.csv
RESULT: see STATE result (7). Headline = 52-72% of missed forest sits NEAR THRESHOLD in all
         four years, so the operating point is a genuine lever and hand-tracing is not the only
         option — but lowering it lifts every band and costs precision, so it is not free.
         THE FINDING BEHIND THE FINDING: the per-year spread that motivated the question
         (24.1/19.4/9.3) DISSOLVED on one recipe (27.7/31.8/30.8). A recipe change moved 2013
         by 22 POINTS. Most of that "cross-year variation" was never about the year.
decided: nothing deployed, no plan edit, no annotation commitment. Measurement only.
killed:  every per-year conf% in STATE correction (3) — recipe artefacts, do not re-quote.
         "2016 is the outlier at ~60% deep" — NOT ESTABLISHED. 2016 has no _citywide_rgb
         raster, so it was never measured on this recipe; after (b) that comparison is
         unsafe. Do not build an annotation plan on it.
files:   phase4/qc/forest_miss_{2000,2002,2013,2015}.txt/.csv (updated) ·
         forest_miss_sensor_compare.txt/.csv · forest_miss_stands_*.csv ·
         CHATLOG STATE result (7) + correction (3) marked SUPERSEDED + cheapest-moves list.
next:    U1 still the blocker. New queued item: 2016 --force-citywide inference on Colab so
         its miss-depth becomes comparable — that is the one number that would decide whether
         2016 genuinely differs or just had a different recipe.

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

## 2026-08-18  [CONSOLIDATED] ASSESSMENT + LIT PHASE 4 — what our numbers can and cannot support
scope:   folds 2 full entries + 1 duplicate. FULL TEXT: Reports/Measurement_Validity_
         Assessment_2026-08-18.md (now git-tracked) + Admin/Literature_Tracker.xlsx.
did:     37 papers (IDs 69-105, searches 9-14) targeting the VALIDITY gap the first 8
         searches never asked about. Then an assessment ordering unknowns U1-U8 BY THE
         DECISION EACH BLOCKS, with the power math COMPUTED not gestured at.
THE FINDING: P3 at 250 pts/yr answers the question NOT in doubt and cannot answer either
         question that IS. Arbitrating C-CAP 29.5% vs NDVI-ref 37.7% (gap 8.2pp) needs
         n=510; n=250 -> +/-5.9pp = CI [27.7,39.5] COVERS BOTH. Per-band recall at 8 strata
         -> +/-17.6pp. Confirming the height effect needs only n_h=20 — and we already know it.
         [LATER OVERTURNED — see STATE result (6): that power math assumed SIMPLE RANDOM
         SAMPLING. The REAL stratified design separates the two at n=250. Sample size was
         never the constraint; interpreter fidelity is.]
         7 amendments proposed, NONE applied (Kam signs off): canopy definition FIRST ·
         free instruments before human hours · re-derive n · primary+ALTERNATE response
         design (Wickham ID 78: 77.5% -> 87.1%, 10pp from a SCORING CONVENTION) ·
         duplicate-interpreted subset designed in (ID 100/101) · 2000 feasibility block
         (Reis ID 103: 3 interpreters fully agreed on <40% of historical px) · strata
         decision before --step design (ID 72 permits any ONE, not all three).
killed:  "your recall is probably optimistic" (my own blanket claim) — WRONG as stated.
         Direction is PER REFERENCE: vs C-CAP the suburb over-count inflates the recall
         DENOMINATOR -> measured recall is PESSIMISTIC; vs the NDVI ref (shared lineage,
         and post-overlay it also supplied labels) errors CORRELATE -> OPTIMISTIC. That is
         the quantitative form of "the refs bracket truth".

## 2026-08-18  [CONSOLIDATED] 2016c CORRECTED-LABEL VERDICT — better where it can be judged, undecidable elsewhere
scope:   folds 3 full entries (verdict / uncontested-ground update / grass check).
did:     scored the corrected-label 2016 model against both references and inside the P2
         partitions. recall .6844 -> .8718 but precision .8651 -> .7296.
RESULT:  on BOTH-AGREE ground (reference noise removed) it is CLEARLY better: F1 .853 ->
         .937, both-agree recall .7613 -> .9486. The grass-rejection alarm (.912 -> .719)
         is ~73% CONTESTED (the NDVI ref calls those px canopy) and ~27% GENUINE — in
         uncontested terms the grass FP rate roughly DOUBLES (~6.8% -> ~12.7%), it does not
         quadruple as the headline implied.
decided: 2016c is a GENUINE CANDIDATE, not deployed. It adopted the NDVI reference's canopy
         DEFINITION wholesale, so its costs are (a) ~27% of a doubled grass FP rate no
         reference supports and (b) total dependence on the NDVI ref being right in the
         contested ~16%. Both are P3 questions. [Later reinforced by STATE (5b): latent
         class is INADMISSIBLE for this decision — 2016c descends from the NDVI ref.]

## 2026-08-18  [CONSOLIDATED] P1c — HEIGHT IS THE INVARIANT, and the LABEL SOURCE has the same curve
scope:   folds 4 full entries. Live form = STATE results (1) and (3).
RESULT:  recall is a monotonic function of canopy height in EVERY year: ~.15 below 5 m
         rising to .93 above 30 m; the model finds ~24 m trees and misses ~12 m trees.
         5-15 m holds 53% of ALL misses; lifting those two bands to the 20-25 m rate takes
         recall .68 -> ~.80. On the honest (full-forest) denominator the "confident miss"
         gets STRONGER, 60% -> 69%.
         AND THE DEFICIT IS INHERITED: phase3/edmonds_canopy_mask_2020.tif — the label
         source for every coarse year — has the SAME staircase and sits BELOW its own
         students at every band (.5455 vs the 2016 model's .6821). Improving that one mask
         lifts every coarse year at once.
killed:  "misses are confident/structural everywhere" — 2016-only; see STATE (7).

## 2026-08-18  [CONSOLIDATED] P2 — reference disagreement is 15-17%, every year, replicated x4
scope:   folds 3 full entries. Live form = STATE, and the instrument = phase4_ref_agreement.py.
RESULT:  38.7% of the apparent "miss" is UNMEASURABLE — it sits where the two references
         disagree, so no truth exists there. Honest recall on measurable ground .6564 ->
         .7378. Disagreement is 15-17% on EVERY year tested (x4), and the NDVI reference is
         systematically MORE LIBERAL than C-CAP. This partition is the basis of the standing
         rule: NEVER score contested ground.
also:    unattended TRAIN QUEUE built (delivered 3/3); CUDA confirmed working locally
         (torch 2.13.0+cu126, Quadro T2000 4 GB) — but training stays on Colab (rule).

## 2026-08-18  [CONSOLIDATED] P1 — nine years scored on ONE honest instrument
scope:   folds 6 full entries (Colab runs, per-year scoring, the queue).
RESULT:  9 years span IoU .49-.76 / AUROC .938-.954 while honest recall stays .51-.78 with
         NO correlation -> MODEL STRENGTH DOES NOT MOVE THE NUMBER (STATE result 4). The
         gap is SYSTEMATIC, not model quality: the best model still under-predicts ~34%.
         2013 miss-depth moved 9.3% -> 50% under a changed denominator (later resolved as a
         RECIPE artefact, STATE result 7b).
killed:  MY PREDICTION on 2017. I said TWICE "expect LOW recall" from its max-prob .575
         ceiling. WRONG — 2017 has the HIGHEST recall in the series (.7784). A COMPRESSED
         probability range does not imply poor RANKING; the deployed .4759 sits inside that
         band and separates fine. The real problem is THRESHOLD FRAGILITY, not weakness
         (thresh .2000 -> recall 1.0000 / precision .2868 = calls the whole city canopy).
killed:  my claim "you skipped stage 1 (2022n)" — WRONG, logs prove 2022n ran 01:29-02:24.
killed:  "git pull to update Colab" — WRONG, said twice. `git remote -v` is EMPTY. The
         working tree IS G:\My Drive\treedata; the git DB is D:\edmonds-pipeline\treedata.git
         (local only). GOOGLE DRIVE is the sync path to Colab, not git. Verify in Colab with
         `!grep -c 2022n /content/drive/MyDrive/treedata/Scripts/phase4_p1_colab_run.py`.

## 2026-08-17  [CONSOLIDATED] measurement overhaul OPENED; QC instruments hardened
scope:   folds 6 full entries (audit, scorer fixes, Colab driver, logging, doc cleanup).
why:     Kam — "became too reliant on AI judgement"; wants defensible numbers, better tests
         and visuals. -> the 4-phase plan in honest-measurement-overhaul.md.
did:     3 SILENT QC failures found and fixed; scorers now FAIL LOUD; provenance mandatory;
         QC CSVs carry live/run_tag so superseded rows cannot be quoted by accident;
         pipeline_log stamps version + code sha + command so logs self-identify;
         run_registry backfilled (+7 rows); CLAUDE.md + buildtracker de-staled.
killed:  "can I trust forest_miss?" -> NO as it stood: a HIDDEN --stable-with denominator
         made 2016's conf% an outlier. Denominators are now printed in every report.
killed:  nothing else — Method_Pipeline hyperparameters were verified line-by-line against
         phase4seg/config.py (LR 5e-5, epochs 20/30, batch 10, tile 512, stride 512,
         neg-rate .15, MIN_CANOPY_PATCH 3.0 m2) and were already CONSISTENT.

════════ ARCHIVE (1-liners — full text in `_archive/CHATLOG_2026-06-29_to_2026-07-07.md`) ════════

Compacted 2026-08-17 and again 2026-08-18 per this file's SPACE RULE 4 (newest ~6 entries
stay full). Nothing is lost, but WHERE the full text lives now depends on the date:

  * entries up to 2026-07-07  -> verbatim in `_archive/CHATLOG_2026-06-29_to_2026-07-07.md`
  * entries 2026-07-08 onward -> GIT HISTORY ONLY (`git show <sha>:Scripts/CHATLOG.md`).
    The 2026-08-18 pass folded 31 full entries into the six [CONSOLIDATED] blocks above
    and the five newest 1-liners below; the pre-compaction file is the parent of the
    commit titled "compact the LOG per the file's own space rules".

A strict 1-liner was judged TOO STRICT for the 2026-08 measurement campaign: those entries
carry numbers and `killed:` lines, and `killed:` is the content with no other home — STATE
holds the findings, but nothing else records which hypotheses are already dead. So every
`killed:` from the folded entries was carried up into the [CONSOLIDATED] blocks verbatim in
substance, and only the narrative around them was compressed.

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
- 2026-08-16 3-agent sweep of every published City canopy report -> the headline 32.4% TRACED to a PlanIT Geo modelling assumption; Reports/ dossier + brief built. Killed: "35% by 2045" (garble — the record says 2036), "PlanIT Geo has no Edmonds engagement" (the agent searched retired iqm2; 2026 packets are on edmondswa.primegov.com), "34.6% is a 2023 figure" (it is 2020). GAP: the full 2024 PlanIT Geo UTC assessment behind 32.4% is NOT PUBLISHED anywhere.
- 2026-07-10 3-agent architecture review -> TWO-STREAM (one shared RGB backbone, instance + semantic heads), instance-on-fine FIRST, labels per domain. Killed: "instance-first is a dead-end" (rejected — a sequencing point, not a veto); "one model spans all years via multi-scale aug" (DEMOTED to half-true — spans 8x GSD, NOT the King contractor change / NAIP / Snoh); "hand-trace deciduous FOREST stands" (WRONG target — the miss is suburban/ornamental, 8/8 inspected stands).
- 2026-07-10 STRATEGIC RESET -> one scale-robust model, labels-first (plan cozy-skipping-jellyfish.md, later superseded by the two-stream review above).
- 2026-07-08 Phase-4 engine MODULARIZED -> phase4seg/ package (config/common/labels/tiling/core[torch]/postproc/cli) + a ~97-line phase4_semantic_finetune.py shim preserving `%run ... --args`. Behaviour-preserving, AST-verified (89/89 defs, 106/106 consts). POC notebook cleaned, experiments/ split out.
- 2026-07-08 full-codebase audit (6 subagents) + declutter + 2 output-safe fixes -> _archive/audit_2026-07-08/ (NOT current).

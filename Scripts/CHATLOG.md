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


════════════════ STATE ════════════════

STATE lives in `WORKPLAN.md` (decision 2026-08-30; this block was 1,489 lines of
transcript before rotation). Read order: `CLAUDE.md` → `WORKPLAN.md` → `STATUS.md`.

════════════════ LOG  (newest first — append new entries directly below this line) ════════════════

## 2026-09-02  HANDLE-FREE CONTROL CERTIFIED — 4 fire drills, 4 real bugs, ALL PASS (Fable 5)

goal:    Kam: prevent/regain runtime control after CLI-handle death (all 3
         Phase-A staging handles died mid-flight while VMs kept working);
         "iterate through this drill again. We need it work flawlessly."
did:     control plane moved OFF handles: `vm_ops sessions` (account census,
         wraps `colab sessions`), babysitter RULE 4 Drive mailbox
         (status|stop, nonce-once, no-arbitrary-code) + `vm_ops cmd`, browser
         attach URL persisted at launch. Fire drill = repo instrument
         `qc/instruments/vm_control_drill.py` (--yes, one T4, 10 asserted
         stages incl. INDUCED handle death via sessions.json strip). Four
         drills run, each caught a real defect: (1) mailbox status leaked
         ANOTHER session's queue log (shared logs dir bare glob) -> queue-stem
         scoping; (2) census lags unassign ~15 min (watchdog fired ON schedule;
         observation channel slow) -> breadcrumb-first reap detection;
         (3) THE BIG ONE: every RULE-1 beacon resurrection self-diverted to a
         __conflict heartbeat (collision guard could not tell same-VM dead
         predecessor from foreign runtime) — telemetry silently maimed since
         the feature landed; drill 1's "Drive debris" attribution CORRECTED
         -> same-host takeover in name_is_ours + NO_CONFLICT_DIVERSION drill
         stage; (4) registry gate flickered on mirror-lagged heartbeats ->
         60 min campaign window. DRILL 4: ALL PASS 10/10. Commits 52fa08e,
         7aa26e5, 63715a3, 48efdfb, d1beda8, 5ba530b.
killed:  "conflict copies are Drive sync debris" (drill 3 proved otherwise);
         fixed 45 s resurrection wait (raced the 30 s poll boundary).
next:    Phase A staging: A done 7/7; B+C alive (census+heartbeats), ledgers
         mirror-lagged. When staged: Phase B on 2xA100 (queue steps
         train,evaluate then inference w/ --infer-aoi) — VMs get the full
         certified control stack. check.py pytest rung still shows a rare
         pass-on-retry flicker beyond the registry gate; source unidentified.

## 2026-09-01  POLICY C LANDED — dense sweep, plateau selector, pilot masks re-cut (Fable 5)

goal:    Kam: "Let's go with C." Build per-year independent threshold selection,
         prove it end-to-end on pilot arms, pre-register 36-run.
did:     dense u8 sweep in `phase4_qc_indep._write_dense_sweep` — 2x 256-bin
         histograms -> EXACT curve at all 254 cuts, one scan. Immediately
         earned keep: F1 peak ~0.14, FAR below coarse sweep's 0.40 floor, on
         plateau flat within 0.005 across 3x range. Selector
         `qc/instruments/select_indep_threshold.py`: criterion
         f1_plateau_hi_d005 (highest k within 0.005 of peak — precision end of
         metric-indifferent plateau; strict argmax = sloppy recall edge).
         Registry `phase4/qc/indep_thresholds.csv`. Selected (after review fix
         below): 2011s k=81 (0.3189, rec .7625/prec .7552; was rec .499
         @0.643); 2006s k=86 (0.3386, rec .7195/prec .6848; old 0.4743 sat on
         probability CLIFF — recall .68->.42 across 0.45->0.50).
         Ref-sensitivity vs 2016 C-CAP: 0.05-0.10.
review:  13-agent adversarial workflow on the two new code paths — every fix a
         CONFIRMED reproduced finding (commit fce0162). Load-bearing: float64
         plateau compare excluded the row exactly 0.005 below peak (fired 3/4
         sweeps, picks were k=80/85 — one step recall-ward of the rule);
         tick-exact compare now. Also: sweep thresh column floored; nodata
         masked pre-clip; truncated-sweep refusal; atomic registry write.
         Masks re-cut AGAIN at corrected picks (recutC2, free CPU);
         EQUIVALENCE PASS both rounds.
         Masks re-cut on free CPU VM (recutC, registry-read thresholds, never
         hand-typed); EQUIVALENCE PASS (mask within 0.001 of registry rows).
         Quantization fix: floor-truncate thresh (rounded 6dp crossed u8
         boundary — scorer cut k+1 while production cut k). Ledger live rows
         now policy-C. Engine UNTOUCHED (--infer-thresh deploys). Overlay
         delivered (overlay_2011s_policyC.png). Commits 5088ad9, fd70834.
decided: plateau-high criterion (measured rationale in selector docstring);
         36-run = 34 arms + ADOPT 2 pilot arms (~4-6 A100-hr saved) —
         `experiments/full_archive_e3.yaml` status queued.
files:   qc/phase4_qc_indep.py, qc/instruments/select_indep_threshold.py,
         docs/SCHEMAS.md (2 new contracts), experiments/full_archive_e3.yaml,
         phase4/qc/indep_thresholds.csv, run_registry (2 recut rows).
next:    KAM: 36-run launch (GPU gate ask pending: 2xA100, ~65-70 A100-hr).
         Adversarial review workflow on selector code in flight. Post-GPU
         cleanups queued (kernel units, GPKG area_m2). --anchor-labels A/B
         candidate experiment.

## 2026-09-01  RECIPE DEEP-DIVE — threshold only large knob; morph/sieve NEUTRAL (Fable 5)

goal:    Kam: "are we leaving anything obvious on the table like sieve that has
         a large impact?" Audit every recipe stage before 36-run spend.
did:     new instrument `qc/instruments/postproc_variant_score.py` — scores
         production mask semantics (real `threshold_and_clean` + sieve) vs C-CAP,
         ledger-safe. Validated: shipped 2011s mask scored PIXEL-IDENTICAL to
         replica (tp=60,497,713). Measured: threshold sweep 2011s 23 recall pts
         (0.643 chosen circular vs 0.45; canopy AREA 1264 vs 1942 ha = 54% swing);
         morphology NEUTRAL both years incl. 3 m-kernel 2006s (+0.31/-0.17);
         sieve moves 0.016% px. 2020-label uncertainty band measured: 5.2% of
         valid px in model's own 0.4-0.6 band, recipe asserts hard 0/1 on all.
         CSV `phase4/qc/postproc_variant_scores.csv`; narrative
         `Reports/RECIPE_AUDIT_2026-09-01.md`. Commit `aca79eb`.
decided: no postproc edits before Kam's threshold call (provenance); ledger line
         for instrument's one path-insert (precedent: phase4_sector_poststrat).
killed:  "3 m morphology eraser" framing — measured neutral, open+close cancel.
         Sieve suspicion — clean post-EPOCH-3, and mask raster never sieved anyway.
files:   Reports/RECIPE_AUDIT_2026-09-01.md, phase4/qc/postproc_variant_scores.csv,
         qc/instruments/postproc_variant_score.py, qc/test_status_discovery.py,
         WORKPLAN.md row 6.
next:    KAM: threshold policy A/B/C (C recommended) — the ONE gate left before
         36-run. Post-GPU cleanups queued: kernel ground-units, GPKG area_m2
         CRS-unit bug (~30/36 years), redundant vector filter, stale comment.
         Candidate experiment: --anchor-labels A/B on 2011s (~2-3 A100-hr).
         Full ladder (not --fast) before any Colab push.

## 2026-09-01  HARD-YEAR PILOT COMPLETE — recipe hypothesis confirmed (Fable 5)

goal:    the pre-spend gate before the 36-run: are the worst years bad recipe or
         bad imagery? Two arms, rule pre-registered before launch.
did:     2011s 0.471 -> 0.756 f.5 (ABOVE the 0.72 line — recipe CONFIRMED);
         2006s 0.470 -> 0.707 (UNDETERMINED band per rule; residual matches its
         three measured strikes). Verdict in experiments/hard_year_pilot.yaml;
         spent generated queue deleted; mining refreshed with the fresh arms.
         The RIDE was the other experiment: 4 A100 launches survived a FUSE-race
         evaluate crash (tile valid seconds later), 3 beacon deaths (queues kept
         working — beacon bug, cosmetic), 1 guard/split collision (my surgery vs
         the duplicate-tag guard: ~2h idle A100, owned), 1 unverified-checkpoint
         resume denial (safe-by-design re-train). ZERO corrupt artifacts, zero
         silent errors. Reliability answer built the same night: vm_babysitter
         (Tier 1, NO model per Kam) + campaign-aware registry gate + vm_ops
         --queue-args. RECOMMENDATION to Kam: GO for the 36-run, 2006s flagged
         low-confidence + first for degradation synthesis. Decision is Kam's.
next:    Kam: 36-run go/no-go (the ladder's final gate is passed). CU balance
         after-read settles the measured rate on whichever launch he approves.

## 2026-09-01  EPOCH 3 MASKS REGENERATED — 4 parallel free CPU VMs, 19+1 arms

goal:    regenerate every champion + pilot mask under the 3.0 m² TRUE sieve.
did:     Kam's correction applied ("parallel CPU runtimes") -> 20 pairs sliced
         across epoch3/b/c/d (CPU tier = 0 compute units), heavies split. Serial
         attempt first found a LIVE bug on pair 1: step_postproc read `nod` after
         the threshold_and_clean extraction moved it — NameError reachable only
         by real postproc; fixed `e471773` + static scope gate; failed attempts
         kept in registry as provenance. Parallel run: 19/20 OK in ~2.5 h wall
         (2022 65.9 min the pole). 20th = 2023n untagged champion: the engine's
         untagged-overwrite guard REFUSED correctly; re-run --allow-overwrite on
         a fresh VM. min_patch printed 3.0 m² everywhere (9 px NAIP -> 1,194 px
         5 cm Mercator; foot years 48 -> 299 px = the ft² bug's 6.2x, gone).
         FREE regression proof: 2019n pilot_e2_coarse reproduced EXACTLY 12,682
         polygons — UTM years were always right, so EPOCH 3 changed them not at
         all. landed.py absorbed 20 manifest rows. All VMs self-stopped.
         2023n RETRY OK (2.4 min, --allow-overwrite, epoch3g) -> 20/20. EPOCH 3
         COMPLETE: every champion + pilot mask cut at 3.0 m² true. Lesson kept:
         the grep-chained exec on epoch3f hid a failure AND stopped the VM early —
         same swallowed-evidence class as tail'd pipes; capture full exec output.
next:    (none for EPOCH 3.) Open science items: co-registration table, the
         Olofsson area-estimation campaign (needs Kam's photo-interpretation).

## 2026-09-01  EPOCH 3 — sieve re-baselined to 3.0 m² TRUE (Kam: "lets do 3m^2")

goal:    kill the 11.6x minimum-mapping-unit spread (0.279-3.24 m² by CRS family —
         "3.0 m²" read as ft² on 15 survey-foot years).
did:     `01b1de7`. sieve_min_px divides by TRUE-m² pixel area; MMU spread now
         integer-px quantisation only (3.0-3.999 m²). EPOCH 2 -> 3 (not in
         _tile_signature — no re-tile). Geometry table + passport columns
         regenerated; parity gate follows the live function. Census Class-B entry
         struck RESOLVED (history kept) + census correction: _crs_unit_m DOES
         handle 3857 (cos-lat) — reported hectares were already ground-true.
         STATS_CHECKLIST item 7 -> RE-BASELINED. Local postproc canary hit the
         documented fork/Windows wall -> batch rides a CPU Colab runtime (ZERO
         compute units, the one sourced-free tier): vm_ops gained a CPU choice;
         20 (year, tag) pairs = 17 champions + 3 pilot arms, nohup-detached,
         log epoch3_postproc_batch_*.log, watchdog self-stops.
next:    verify batch DONE ok=20; then landed.py (registry rows for the re-runs
         come from manifests). Pilot Atlas mmu column already shows EPOCH 3.

## 2026-09-01  IMAGERY GEOMETRY MEASURED — 4 CRS families, 17 files in FEET (Fable 5)

goal:    Kam: authentic imagery facts, stored so future contexts find them; wrong
         projections "drove stats" before. Items 1-4 approved.
did:     `87bbb76`. imagery_geometry.py -> phase4/qc/imagery_geometry.csv (36 rows,
         rasterio-measured): CRS, unit, naive-vs-TRUE-GROUND pixel size, origin
         alignment, extent, bands, nodata, catalog flags. Instrument's FIRST RUN
         re-derived the founding trap (+48.9% naive on all 13 EPSG:3857 files =
         1/cos(lat)) -> both numbers are now columns. MEASURED: 4 CRS families;
         2285 x15 + 2926 x2 (US SURVEY FEET, 17/36); 3857 x13; 26910 x6 (only
         honest metres). Catalog: ZERO disagreements. nodata declared on 6/36
         only. config.ANALYSIS_GRID_EPSG=26910 appended (declaration, not
         resampling — 3.7 stands) + gates. docs/CRS_CENSUS.md (gated): every
         stats-bearing CRS site by symbol, incl. the two BY-DESIGN exceptions
         (MIN_CANOPY_PATCH sieve, inflated phase-0 crown areas). CLAUDE.md 3.4b:
         the measurement contract (instrument -> measured CSV -> gated finding).
         IMAGERY_FACTS 14 = the finding; SCHEMAS.md = the table contract.
         Also: colab CU balance anchor MEASURED via Kam's browser (173.39 CU
         @ 03:45Z, verbatim in colab_rates.csv) — next launch settles a rate.
next:    grid-congruence arithmetic on the 2019s/2019n class is now one query;
         Kam's calls unchanged (main, tag).

## 2026-09-01  AGENTIC WORKFLOW 7/7 — lifecycle as code, checklist as command (Fable 5)

goal:    Kam: "what remains a problem for agentic workflow... go for all 7"
         (billable time granted).
did:     7 `0deb3d0` lake.read_retry — ONE home for retry-the-answer, pilot_gate
         delegates (3/3 live). 5 same commit: bench covers evaluate/postproc —
         postproc.threshold_and_clean EXTRACTED pure so the bench regresses real
         code; +6 metrics; MATCH x2. 2 `7976cc5` qc/landed.py — 3.12 is a command;
         my own 2 hand-typed canary rows had INVENTED run_ids, replaced by
         manifest-derived; gate asks the tool its own question (0 new). 4 `a727bce`
         qc/experiment_queue.py — queue yamls GENERATE from experiment files,
         drift-gated. 1 `f94fba6` pipeline/vm_ops.py — launch/exec/status/stop
         with the CLI lock, three-state signature verify, token cleanup,
         backoff; PROVEN LIVE on T4 (~4 min): all signatures, heartbeat, clean
         stop. 3 `4c546a7` queue split 1,629 -> 973: queue_verify.py 478 +
         queue_ledger.py ~300, q-context routing preserves all 52 monkeypatches
         (3 subtleties caught by the suite: patched intra-cluster call, shared
         _MERGE_DEFECTS list, q.io module-object patch surface). 6 BLOCKED ON
         EVIDENCE by colab_rates.csv's own correct rules — procedure documented
         there; Kam reads CU balance before/after any launch to settle a
         MEASURED row.
decided: queue guards cluster stays in the queue (main's own surface). vm_ops
         prints 3.4 policy reminders, never bypasses them.
killed:  committed once over a red ladder (tail'd pipe, again) — pipefail now in
         every ladder chain; it caught the very next stray import.
files:   vm_ops.py queue_verify.py queue_ledger.py landed.py experiment_queue.py
         bench.py lake.py + tests
next:    Kam: main merge + tag + one CU-balance read. The repo's agentic loop is
         now: experiments/x.yaml -> experiment_queue -> vm_ops launch -> pilot_gate
         --experiment -> landed.py.

## 2026-09-01  R&D FLEXIBILITY — six agentic-workflow seams landed (Fable 5)

goal:    Kam: "flexible for research and development... what if I wanted to
         implement a different architecture." All six proposals approved; order
         mine (seam -> substrate -> consumers -> protection).
did:     `448b881` ARCH seam: ckpt.ARCHS registry + contract test parametrized
         over it (new arch = one builder + one dict line + check.py; 11 arch
         tests). `ad2c2e7` STATUS.json via pipeline_status --json + anti-rot gate
         (agents query, never parse markdown). `3271caa` docs/SCHEMAS.md — every
         data contract, writers cited BY SYMBOL, gated. `7276f59` experiments/
         one yaml per experiment (hypothesis/arms/decision rule BEFORE results/
         verdict); pilot_gate --experiment gates ANY of them (pilot re-verified
         3/3 through the new loader); schema gate incl. registry provenance for
         complete experiments; seeded with pilot_2019, deeplab_arm (tabled),
         degradation_synth_2000 + resolution_1x2x4 (queued, rules pre-registered).
         `94f22a2` qc/bench.py deterministic micro-benchmark — hermetic synthetic
         tiles through REAL dataset/train/validate, rtol 1e-4 vs stored reference;
         3 nondeterminism sources measured+pinned (CPU threads, algorithms,
         albumentations 2.x seeding from OS entropy ignoring global seeds);
         mutation-tested (DICE_WEIGHT x1.25 diverges every metric). `59cdc02`
         --overrides YAML overlays, manifest-recorded, tile-signature guard
         DERIVED from _tile_signature AST; bench MATCH on the commit touching
         cli/config — its first real assignment.
decided: bench regresses ENGINE math on resnet18, not the shipping arch (that has
         its own registry contract). Overrides never CREATE constants.
files:   phase4seg/{ckpt,overrides}.py, qc/{bench,check,pilot_gate,test_*}.py,
         experiments/, docs/SCHEMAS.md, STATUS.json
next:    Kam: main merge + tag still pending. Queue split (phase4_train_queue
         1,600 L) is the remaining big-file target.

## 2026-09-01  TOOLING + CORE SPLIT — ruff found 7 live bugs; core 2,666 -> 1,579 (Fable 5)

goal:    Kam: "improve the repo to improve the ability of claude code to create
         better code" — approved items: ruff gate, check.py ladder, nested
         CLAUDE.mds, then the core.py split.
did:     `59a3d71` ruff F-gate (F821/F401/F811 only, no style; config.py + frozen/
         excluded) — FIRST RUN caught 7 live bugs: 5 clean_argv imports sitting
         INSIDE module docstrings (py_compile-legal, NameError at main), a
         guaranteed NameError in cost_report's blocked-cost path (`m.group` with
         no m — the path EVERY launch takes), and core's `del model` deleting a
         name _forward closes over (post-cleanup call = NameError; canary-safe by
         call order only). +121 dead imports pruned across 73 files.
         qc/check.py = definition of done: ruff/compile/pytest/preflight/smoke,
         one command, ~75 s; CLAUDE.md 3.1 points at it; CI runs same rungs.
         Nested CLAUDE.mds in phase4seg/ + qc/instruments/ put rules at the edit.
         CORE SPLIT `048b9c5` + `0650782`: splits.py 281 + staging.py 161 (torch-
         free, measured) then ckpt.py 320 (function-local torch after lazy
         _ensure_torch — losses pattern) + select.py 455 (torch-free; MODELS_DIR/
         OUT_DIR read from core AT RUN TIME because tests patch core.X — the
         freeze trap fired in-suite and was fixed, not suppressed). Facade
         re-exports keep every core.X call site + monkeypatch. core.py 1,579 L.
decided: facade contract covers WRITES (dir constants) not just calls. train_test_split
         is facade surface (test_val_split's reference implementation).
killed:  nothing — every gate that fired (preflight module list, citations, F401
         on the facade) was fixed at the source, not suppressed.
files:   phase4seg/{ckpt,select,splits,staging}.py NEW; core.py; check.py NEW;
         pyproject [tool.ruff]; ci.yml; 2 nested CLAUDE.mds; ~80 files import-pruned.
next:    steps/dataset stay in core BY DESIGN (the _ensure_torch injection
         coupling; 3.5 rejected per-module injection). Kam: main merge + tag.

## 2026-09-01  REFACTOR COMPLETE — Stages 4+5 landed, repo is the target tree (Fable 5)

goal:    finish the approved full-repo refactor: tier moves + ingestion docs.
did:     4a `ae6aa63` shared trio qc->pipeline as installed py-modules; 5 reverse
         inserts died. 4b `8dad590` 18 builders -> pipeline/builders/, all anchors
         re-derived, dag+checklist+5 gated docs updated. 4c `d6db126` 70 instruments
         -> qc/instruments/ (qc root 98 -> 29); measured first: NO stayer imports a
         mover; 5 inserts died, ledger rewritten; 49 files of refs. 4d `1f2a59e`
         phase0-3 + label_review pair -> pipeline/frozen/ (zero importers, zero
         anchors, 3 refs). Stage 5: CLAUDE.md tree + install step, README layout
         row. EXIT CHECKS: pilot_gate re-read 3/3 PASS from the lake on the moved
         layout; CI green through 4c (4d in flight); 464 tests + preflight + smoke
         at every commit. Tracked files 883 -> 477 (-46%); pipeline root 88 -> 19;
         qc root 160 -> 29. config.py comments untouched (append-only) — its two
         stale builder refs are deliberate historical record.
decided: phase4_catalog_check STAYS at qc/ root (CLAUDE.md test command + suite
         import). No-op bootstrap sanity rides the NEXT queue launch, not a
         dedicated VM (canary already proved bootstrap+install at 1dbe158; no
         queue-path file moved since).
files:   see the four commits; STATUS.md regenerated each move.
next:    Kam: the tag (git tag deny is his), 36-year run go/no-go, label_review
         archive question, Class-B resolver repairs. Queued: degradation-synthesis
         A/B on 2000 (GPU), 4.4 within-acquisition 1x/2x/4x (GPU).

## 2026-08-31  CANARY 1 PASSED — refactor proven on real Colab, one live catch (Fable 5)

goal:    gate refactor Stages 2+3 on a real VM before Stage 4 tier moves.
did:     L4 VM `canary3b`, ~60 min total. Bootstrap: WRITE_CANARY PASS,
         EDITABLE_INSTALL OK, BOOTSTRAP_READY at branch tip, heartbeat 60 s cadence.
         Steps: inference (6.9 min, 3,501 positions) + postproc (12,682 polygons) on
         pilot-coarse checkpoint+tiles, exit 0 both. REGRESSION MATCH — new prob
         raster stats identical to pilot (mean 50.066, frac_ge128 0.17462); pilot
         originals backed up to masks/_prerefactor_backup/ first. Injection proven:
         KERNEL_ARGV showed colab_kernel_launcher.py -f kernel-*.json; qc suite
         parsed clean through clean_argv. Self-stop FIRED per spec: drain clear
         23:59:17Z, unassign ~10 min after last engine process. Registry: 2 rows.
         LIVE CATCH -> `1dbe158`: kernel-exec'd qc files (imagery_qc_suite,
         phase4_qc_indep) could not import phase4seg — pip -e works via .pth,
         site.py reads .pth at interpreter STARTUP only, so a running kernel never
         sees a mid-session install; subprocesses do. Insert restored to BOTH with
         mechanism comment + ledger lines. 464 green.
decided: kernel-exec keep is a permanent ledger class, not 4c debt.
killed:  v1 qc-suite wrapper printed OK over a swallowed %run traceback — run_cell
         + .success now; also --only matches FILENAMES not labels (2019 not 2019n).
files:   qc/imagery_qc_suite.py qc/phase4_qc_indep.py qc/test_status_discovery.py
         run_registry.csv
next:    Stage 4 tier moves 4a-4d, then Stage 5 ingestion docs. Tag still Kam's
         (git tag deny in his global settings).

## 2026-08-31  REFACTOR 0-3B — repo installable, path hacks dead (Fable 5)

goal:    Kam: "refactor my entire repo... centralize functions, definitions". Approved
         plan: full restructure, history to archive branch.
did:     Stage 0 hygiene. Stage 1 archive split — 883 -> 474 tracked files, branch
         `archive/2026-08-pre-refactor` local, CHATLOG rotated 4,015 -> ~120 lines,
         docs/ARCHIVE_INDEX.md maps it. Stage 2 centralization — shared homes
         names.py/deps.py/lake.py/pipeline_log.py + config.resolve_imagery; clean_argv
         pair filter replaced 96 broken one-liners. Stage 3A `12bcb01` pyproject +
         editable install, all 3 planes (local, ci.yml, VM bootstrap FATAL-on-fail).
         3B `a7dfe6c` path-hack sweep 79 -> 39 sys.path.insert sites; survivors on
         ledger gate test_path_insert_ledger (unlisted insert fails, growth fails,
         removal free). 463 green main env + preflight + smoke; fresh venv (only
         `pip install -e . -r requirements-local.txt pytest`) 402 pass + 5 skip =
         exactly the torch modules requirements-local excludes by design.
decided: preflight/smoke KEEP self-inserts — gate must validate engine sitting next to
         it, not whatever tree the venv install points at. finetune shim untouched.
killed:  first fresh-venv "green" — tail'd pipe swallowed "No module named pytest";
         pytest's number is the gate, never the pipe's exit.
files:   pyproject.toml, .gitignore, ~103 under qc/ + pipeline/, test_status_discovery.py
next:    BLOCKED: session permission mode denies `git push` (tried twice). Canary 1
         clones github (gen_vm_bootstrap.py:60) so it needs the branch pushed.
         Kam: push work/20260824-sectors (+ archive branch + tag when ready).
         Then CANARY 1 -> Stage 4 tier moves (4a-4d) -> Stage 5 ingestion docs.

## 2026-08-31  OVERHAUL EXECUTED + PILOT 3/3 — and 8 plan claims were false (Fable 5, all-night)

goal:    Kam: repo overhaul, then "move forward with the rest of the plan", GPU +
         parallel granted, "only assume 2 gpu run times", "unblock degradation synthesis".
did:     PILOT PASSED 3/3. 2019/2019s/2019n each produced a mask GPKG, a live independent
         score, a manifest carrying epoch=2, and all six steps OK unattended. U3 proven on
         three tiers: postproc had NEVER run under a queue before (it was absent from
         STEPS, so --skip-postproc skipped a step that was never going to happen).
         Gate met -> the 36-year run is unblocked and is KAM'S call, not inferred from
         "the rest of the plan" (the plan scoped itself to machinery + pilot).
         indep: 2019 rec .6492 prec .8365 | 2019s .6331/.7735 | 2019n .6915/.7858.
         COARSE BEAT MEDIUM on the same date, and support-matched rescore at 1/2/4 m
         KILLED the measurement-artifact explanation: gap flat (+.0564/+.0577/+.0571 vs
         +.0584 native), precision gap widens. Live confound is now PROGRAM/SENSOR
         (Snoh HXIP vs NAIP), not the ruler. 1 m result independently reproduces
         qc_indep to .002 — two scoring paths agreeing.
killed:  EIGHT plan/board claims, each checked against source, several my own:
         "+9.2 OA, the largest measured lever" — appears ONCE in this repo, in the
         sentence asserting it. No source anywhere. "A tiling parameter, not a retrain"
         — backwards; tiles ARE the training input.
         "The SDM depends only on the fixed mask, so cache it" — augmentation warps
         89.5% of tiles NON-isometrically; the cache would have been a silent
         correctness bug. Moved into the DataLoader instead: 446 -> 4.7 ms/batch.
         "The ERF is smaller than one crown at fine GSD" — false for EVERY acquisition
         (min 1.07 at 2022/6.5cm; needs <6.09 cm effective, finest measured is 6.5).
         Fine is context-POOREST (2.07 crown-widths vs coarse 15.60), not starved.
         The 2026-08-27 object-ratio note predicted COARSE underperformance — backwards:
         coarse gets 7.5x MORE context per prediction. Tile span is 22.4x, not ~7x.
         "3.6 not started" — step_evaluate had stamped run_tag since D6, a day earlier.
         "2019s/2019n is a same-flight pair" — same DATE, two programs (HXIP vs NAIP).
         "core.py split needs an ensure_torch(globals()) rework, laziness gated twice" —
         gated ONCE (preflight only PRINTS it); function-local imports work, as
         sdm_for_mask already does for scipy. Losses split landed, 2833 -> 2621 lines.
         "There is no R2 radiometry table" (MINE, wrong) — qc/instruments/radiometry_norm.py is
         self-titled R2; I asserted a negative from two .md files without grepping qc/.
         "n_targets=2, so zero residual DOF" (MINE, wrong) — n_points is 6, 4 DOF.
found:   --aux-height BROKEN since 50006ce (my own fail-loud-loads commit): allow_missing
         passed "aux_height_head." but the real keys are "height_head.". Four tests
         passed VACUOUSLY because the fixture was named after the bug, and smoke
         hard-sets AUX_HEIGHT=False so no local gate reached it.
         A dead run credited with a rerun's success in run_registry: the attempt bound
         keyed on a next-RUNNING row, but a launch UPDATES its row in place, so a
         finished rerun erases the marker the bound depends on.
         Leakage that would have made the synthesis A/B report a phantom gain: synthetic
         tiles cover the SAME GROUND as the target year, and ground is partitioned by
         block, so a tile from a val/test block puts that ground into training with
         better labels. Documented before any data existed to be contaminated.
ops:     A100 is CONCURRENCY-capped at 2 (TooManyAssignments, not scarcity; L4 assigned
         in 14 s with both busy). `cmd | tee log` hides the launcher's exit code.
         The G: mirror BLINKS files in and out. I declared a working runtime dead once —
         three signals agreed and all three were wrong; what separates the cases is the
         step's own median/max and the queue's OWN STEP_TIMEOUT_MIN ceiling.
built:   names.py (one status vocabulary, row key, filename parser+formatter, symbol
         locators), test_docs_match_code + test_citations_resolve + pilot_gate +
         tile_object_ratio + support_matched_rescore + degrade_synth (Phase A, two-pass
         Real-ESRGAN chain, deterministic, self-describing). 441 tests, CI green.
next:    KAM'S CALL: the 36-year run; 4.1c (boundary vs perimeter — a science decision);
         4.3 (DeepLabV3+ CONTRADICTS "keep the U-Net and resnet101" recorded in this same
         plan). GPU-ready: 4.4's within-acquisition resolution test (the last confound),
         4.5's synthetic A/B on 2000 (best-fit weak year: red RMS 5.75 vs 47.37).


════════ ROTATED 2026-08-31 (ingestibility refactor, Stage 1) ════════

Everything below this file's newest entry — the full 1,489-line STATE transcript and every
LOG entry from 2026-06-29 through 2026-08-29 — is preserved byte-identical on the archive
branch:

    git show archive/2026-08-pre-refactor:Scripts/CHATLOG.md

The older `_archive/CHATLOG_2026-06-29_to_2026-07-07.md` compaction lives there too. This
stub stays the valid append target required by CLAUDE.md §3.12; the HOW-TO block above is
the unchanged spec for new entries.

## 2026-09-03  tier1-verdicts
goal:    finish tier1 GPU tail, score all arms, write pre-registered verdicts
did:     t1gpuF ran final 9 inference arms then self-stopped via watchdog (0 runtimes left).
         conveyor scored 27/28 (cor02 has no ckpt). built qc/instruments/build_tier1_results.py
         -> phase4/qc/tier1_results.csv. floor .0085 from 2011s replicates. verdicts in
         experiments/tier1_science_sample.yaml: LIDAR-INPUT CONFIRMED 3/3 yrs; ADDER NOT
         CONFIRMED 1/3 (2006s_add16 -.503 epoch poison); NIR CONFIRMED both yrs; corruption
         <=10pct flat. conveyor timeout death fixed (1200->3600s, 2020 scores are 167M cells).
files:   experiments/tier1_science_sample.yaml, qc/instruments/build_tier1_results.py,
         phase4/qc/tier1_results.csv, run_registry.csv, STATUS.*
next:    perf writeup (ledger sync pending), cor02 fate, verdicts -> full_archive_e3 recipe (Kam)

## 2026-09-04  accuracy-batch-overnight
goal:    Kam's approved 8-item CPU batch (reference error + boundary accounting)
did:     sampler repaired (chm2 strata, undo bug) + 2016/2023n REDRAWN (K1 unblocked,
         design-power +/-1.87pp). U1: estimate scores ANY arm at the labelled points.
         E2 covariates joined. certified-flat scoring: C-CAP 2016 over-calls 0.30% of
         physically-empty ground (2021: <=1.17% incl growth); lidar-input slashes
         empty-ground FP (2020 base .256->in16 .037); add16 poison visible (.375).
         C2: ~2-3pt recall / ~2.4pt precision is 1px edge accounting at 1m years.
         C3: same flight two deliveries = 1.3pt citywide area gap, IoU .738 -- the
         trend's consistency floor. C1 lidar anchors (2016_base .751/.712 CLEAN;
         in16-vs-chm2 flagged CIRCULAR). tile-signature anchor-key gap closed +
         tripwire. E1 histograms KILLED the leaf-off premise: gradient is DELIVERY
         RADIOMETRY (2015 Feb bimodal+unharmed; 2019 Apr whole-shift -0.02).
         hybrid_v1 PR closed (AUROC .8946). X6 provenance. MVV-0 epoch-decay record.
files:   qc/instruments/{phase4_accuracy_sample,build_sample_covariates,
         certified_flat_scoring,tier1_block_bootstrap,tier1_buffer_tolerant,
         sameflight_consistency,phase4_qc_leafoff,phase4_arm_pr_curves}.py,
         phase4seg/tiling.py, phase4/qc/*.csv, Reports/{GREENNESS,EPOCH_DECAY}*.md
next:    K1 (Kam labels 250, ~15min), K4 confirmation of the whole documented block,
         radiometric-normalization pilot design, 2016_base reseed (GPU, Kam)

## 2026-09-04  direction-campaign-panel-a
goal:    tell the city the direction of the canopy
did:     direction workflow (5 agents): no sign survives the old instruments; paired-
         change design instead. power gate: 250 FAILS, 1250 GO (hw 1.03pp). decimation
         null REVIVED lidar 2005->2016 net-gain (artifact gain 1.50km2, artifact loss
         ~0 - density cannot fake loss). Panel A built (locators eroded 48->18% share,
         N raised 1000->1250 for power .81), Kam labeled 1250 pairs + 61-call verify
         pass vs leaf-on Oct-2023 (2024 flew Mar-May leaf-off - Kam caught it).
         RESULT: -2.21pp 2016->2024, CI [-3.31,-1.11], DOWN. 42/54 losses real,
         6/7 gains fake. blur 0/30, capture 2/97. C2b metric tolerance: 2020 strict
         score was pixel-harshness (at 2m tolerance 2020 is BEST year .920).
files:   qc/instruments/{panel_a_paired_change,paired_change_power,
         lidar_decimation_null,tier1_metric_tolerance}.py, phase4/qc/panel_a_*,
         metric_tolerance_scores.csv, lidar_decimation_null.csv, paired_change_power.csv
next:    city statement doc (two-leg story: lidar up 2005-2016, human-measured down
         2016-2024); Panel B (2005->2016 paired) decision; Bayesian anchor optional

## 2026-09-05  trend8-verdict-overlap-launch
goal:    8-year map series verdicts + flicker program items 1-8 (Kam approved)
did:     trend8 DONE both A100s one session (16 masks). raw fractions sawtooth
         +-3-6pp; 2m harmonization NULL (detection-time bias); map 2016->2024 +4.2pp
         OPPOSITE Panel A -2.21 - maps disqualified from trend, Panel A stands.
         hot spots: 115ha loss, dispersed (max cluster 0.41ha), 34/42 of Kam's
         verified losses corroborated. lit families 3/4/5 workflow -> ranked program.
         item1 flicker parcels: hard negatives ~0 FP flat (no hallucinated canopy).
         2017k promoted (Kam item-7 approval): catalog append, gsd corrected to
         MEASURED 10.0 (Mercator flag), geometry/coreg/passport regen, pins 36->37
         26->27, coreg 2017k median .01/.21m. overlap_floor pre-registered
         (items 2+5+7: floor kill >1.3pp, factorial, EagleView triple sign test).
files:   experiments/{trend8_uniform_rgb,overlap_floor}.yaml, config.py append,
         qc/instruments/trend8_*.py, phase4/qc/trend8_*, coregistration.csv,
         imagery_geometry.csv, passport, test pins
next:    launch overlap_floor 2xA100; items 3 (Landsat covariate), 4 (degradation
         ladder), 6 (2m stack census); 2020-Aug consortium fetch

## 2026-09-05  housecleaning
goal:    repo hygiene after the week
did:     pr-curves outputs homed to phase4/qc (root pollution from the 4c-move bug,
         instrument still writes cwd - debt). QUARANTINED four 2023n sidecars holding
         2022n byte-copy content (qc_indep/leafoff-control/design_power x2; dot-suffix
         rename + README_2023N_QUARANTINE; sample_2023n itself was already redrawn
         2026-09-03). landed.py absorbed 28 registry rows (trend8+overlap manifests).
         FIXED landed.py CHATLOG gate: re.search took the FIRST ## date (oldest in
         the rotated stub) as "newest" and nagged past entries; now max(findall).
         lit pile complete: 4 papers read+reasoned (MURTreeFormer, JPSL irrational-
         transitions, GeoAI inheritance, ALCC ensemble) - all confirm the diagnosis,
         none validates change vs blind human truth; 3 free tests queued.
files:   qc/landed.py, phase4/qc/arm_pr_curves*, CHATLOG.md, run_registry.csv,
         lake: 2023n quarantine renames + README
next:    overlap GPUs finishing -> floor/factorial/EagleView reads; then the
         synthesis session (Kam). Search budget exhausted this session - skeptic
         hunt brief for a fresh session.

## 2026-09-06  recalibration-campaign-complete
goal:    finish the operating-point recalibration + all overlap reads
did:     14/14 sweeps (3 free CPU VMs + sweep4 + recut2 relays; handle mortality
         worked around; recut1 died on corrupt staged tif -> lake-side logs +
         scratch cleanup fix -> recut2 8/8). VERDICTS WRITTEN, both experiments
         complete: overlap_floor - floor 0.15pp PASS, quartet 10.1->3.55pp with
         residual entirely the 1m arm, season ~0, <=30cm deliveries interchangeable
         (0.15pp); EagleView endpoints -0.94pp/4yr agree with Panel A sign+pace,
         interior wobble = single-year steps unreadable. trend8 - delivered cuts
         RETRACTED, matched cuts flip the sign test to PASS (-3.5 to -5.6pp
         2016->2024), two-leg story reproduced, 41/42 loss corroboration, flicker
         did NOT collapse (47.8%) = pixel noise real, maps need persistence.
         2017k promoted+trained (VERIFY OK) after 2 imagery-visibility failures.
files:   experiments/{trend8_uniform_rgb,overlap_floor}.yaml (verdicts), queues
         removed, phase4/qc/{trend8_policy_cuts,overlap_factorial_read,
         eagleview_sign_test,trend8_*}.csv, hotspot map, payloads
next:    Kam synthesis session (all evidence final); K4 sign-offs; city statement

## 2026-09-06  experiment-registry-built
goal:    Kam: one machine-readable source for every experiment - inputs, outputs,
         variables, imagery, sample size, provenance - always in reach for agents
did:     Diagnosed the .docx ledger's four bottlenecks (unsearchable binary; no
         regeneration path; frozen 09-03 so the recalibration silently superseded
         parts of it; nothing gated it) -> two-layer design. AUTHORED layer =
         experiments/*.yaml extended additively: kind (experiment /
         measurement-campaign / instrument-finding, so Panel A + the lit hunt fit
         without inventing arms), retrospective (gate-enforced: a backfilled
         decision_rule is a reconstruction and must say so, or the registry
         fabricates pre-registration), pinned n/n_source, imagery as catalog keys,
         supersession links, instruments/inputs/outputs. GENERATED layer =
         qc/experiments_index.py joins all entries against run_registry,
         qc_indep_report(live=1), tier1_results, champion_arms, YEAR_CATALOG and
         writes INDEX.md + index.json with RESOLVED values; test_index_is_fresh
         regenerates + byte-compares so it cannot rot the way the doc did.
         Backfill: 6 extract agents + 6 adversarial verifiers (Opus; the Fable
         fleet hit its usage limit first try, zero files written, relaunched).
         32 entries written, 7 errors fixed in place by the verifiers (a 5cm GSD
         that is 30.5, a quote attributed to the wrong file, a date read off a
         checkout mtime, a mis-cited decision leg), 15 substantive findings
         escalated and then applied under a second fix+recheck pass. Biggest
         catch: imagery_qc_suite_2026_08_24 had the grading mechanism INVERTED -
         credited peak ratio with deciding trustworthiness when the instrument
         says confidence comes from site agreement and gating on peak ratio once
         threw away 54 of 100 measurements. recipe_audit's "identical to 4dp"
         disproved by its own CSV -> UNDETERMINED per 3.5. Gate bug found by real
         data: tag ownership keyed on tag alone, but the engine's unit is
         (year,tag) - tiles/{year}__{tag}/ - so one recipe across two years looked
         like a conflict; fixed. 43 entries: 34 complete, 5 needs-kam (verdict
         null - documented but unsigned, or output not in the tracked record),
         3 queued, 1 tabled. check.py all five rungs, 482 tests.
files:   experiments/{INDEX.md,index.json,README.md,BACKFILL_RECONCILIATION.md} +
         32 new *.yaml, qc/experiments_index.py, qc/test_experiments.py,
         CLAUDE.md roadmap row, WORKPLAN DONE row
next:    Kam synthesis session (open INDEX.md first); K4 sign-offs incl. the 5
         needs-kam entries; the docx stays as the audited 09-03 snapshot

## 2026-09-06  run-context-layer-built
goal:    Kam: centralize as much data per run as possible - best performance per
         year, steady points on the curve for objective comparison, tile counts,
         WHICH tiles trained, and a unique ID per tile SET
did:     Five phases, each its own commit. (1) TILE SET IDENTITY: the engine already
         DEFINED it - _tile_signature is the dict deciding cache reuse - but it lived
         only in a lake sidecar. tiling.tileset_id() reduces the STORED dict (not a
         recomputation: _existing_tiles_valid grandfathers old caches by dropping
         keys, so live config can differ from disk) to 12 hex. 81 tile dirs -> 71
         distinct sets, 41,856 tiles. Tile LISTS tracked in full (924 KB pruned to
         row_off/col_off/split/block) because a re-tile overwrites its lake dir in
         place and takes the old answer with it. Immediately showed 4 sets shared by
         >1 arm - the seed replicates, so those noise floors really did hold tiles
         constant. (2) RUN PASSPORT: 535 manifests -> 240 KB tracked CSV, pip_freeze
         hashed to env_sha (37 distinct environments). join_basis declares its own
         weakness: historical runs are inferred_current forever because a manifest
         never recorded its tile set. Found 16 manifests with no run_registry row.
         (3) METRICS: 87 PR sweeps tracked whole (1.15 MB) + arm_metrics.csv, one row
         per (curve, policy) with thresh, counts, population, pr_auc. Policy is a
         closed gated set: best_f1 (what shipped, never valid cross-arm), matched
         p50/p75/p90 (the steady points), scored_live. PR-AUC not AUROC - no tn in a
         sweep, and at 650x skew AUROC flatters everything. (4) ENGINE stamps
         tilesets into the manifest AFTER the step loop (writing it at manifest time
         would stamp a re-tiling run with its PREDECESSOR's set); signature untouched,
         test_tile_signature_scope still green. (5) YEAR SCOREBOARD at a held cut,
         grouped by (ref, eval_scope) so a coverage gap never reads as a skill gap.
bugs:    MY OWN curve_id ignored the evaluation POPULATION - the LOSO
         sample-selection/sample-test halves collided, 87 sweeps became 58, one
         silently dropped. That is exactly the sin the module exists to prevent,
         committed by its own key. eval_scope now keys the curve; halves differ
         materially (2006s_add05 .5215 vs .5676). Also: every pr_auc read nan because
         a sweep's extreme cut has tp=fp=0 -> precision 0/0, and one such point
         poisons the integral; non-finite now parses as ABSENT. Also: the tag
         ownership gate keyed on tag alone when the engine's unit is (year,tag).
files:   qc/instruments/harvest_{tilesets,run_passport,arm_metrics}.py,
         qc/year_scoreboard.py, qc/test_run_context.py (20 gates),
         pipeline/phase4seg/{tiling,cli}.py, qc/experiments_index.py,
         phase4/qc/{tileset_registry,run_passport,arm_metrics}.csv +
         tilesets/ (71) + curves/ (87) + year_scoreboard.md, docs/SCHEMAS.md,
         .gitignore, CLAUDE.md roadmap, WORKPLAN DONE row
next:    re-harvest after each Colab campaign (command in CLAUDE.md 2.2); new runs
         earn join_basis=manifest; Kam synthesis session

## 2026-09-06  context-retrieval-built
goal:    Kam: what is missing that would reduce the bottleneck of getting science
         into context. Measured it instead of guessing, then built the top three.
did:     MEASURED THE BOTTLENECK FIRST: cold-start read order is ~14.7k tokens across
         4 docs, but the context layer built earlier today is ~115k tokens of CSV read
         raw - so capture had stopped being the problem and RETRIEVAL had become it.
         (1) qc/ask.py - one subject, one answer, ~40 lines. Detects whether the
         subject is an acquisition, arm tag, registry entry or tileset id; joins every
         tracked home; names the home each block came from so answers are checkable.
         --gaps and --list. Reads only tracked files: bare checkout, no lake, no GPU.
         (2) qc/coverage_map.py -> phase4/qc/coverage_map.md, per-acquisition matrix.
         Surfaced numbers nobody had: of 37 acquisitions 13 never tiled, 9 NEVER
         SCORED (2002s 2007s 2009s 2013s 2015n 2015s 2021n 2022s 2024s), 21 with no
         matched-cut read, 21 with no champion. Deliberately refuses to imply a
         backlog - blank = no record, not should-have-been-done; gate pins the caveat.
         (3) failure registry: harvest_failures.py counts SYMPTOMS from 863 step logs
         (22 with errors>0 -> 8 distinct failures, normalised signatures so one bug is
         one row); qc/known_failures.yaml is the AUTHORED cause+fix matched by regex.
         All 8 diagnosed from the tracebacks. THREE ARE ONE MECHANISM: Drive FUSE
         dropping I/O under sustained small-file reads (EIO on train, mkdir ENOENT on
         tile, truncated tile -> unsupported-format) = rule 3.9 seen from the read
         side. Undiagnosed rows carry an empty cause BY CONTRACT and surface in
         ask.py --gaps, so "never worked out why" is a to-do not a silence.
files:   qc/{ask,coverage_map,known_failures.yaml}, qc/instruments/harvest_failures.py,
         qc/test_run_context.py (25 gates), phase4/qc/{coverage_map.md,
         failure_registry.csv}, docs/SCHEMAS.md, CLAUDE.md roadmap (ask.py is now the
         FIRST row), WORKPLAN DONE row
next:    still missing per my own assessment: bidirectional claim<->evidence links,
         a decision registry for the AWAITING KAM stack, and automatic re-harvest as
         a landed.py rung (today the harvests are manual and can silently drift)

## 2026-09-06  decisions-claims-autoharvest
goal:    build the three gaps I named in my own assessment last turn
did:     (1) AUTO RE-HARVEST as landed.py rungs - the harvests were manual, so a
         campaign landing without them left every context table describing the
         PREVIOUS lake state (the .docx failure mode, faster). Ten rungs now, docstring
         updated to match. (2) DECISIONS: decisions.yaml, 10 entries, owner + why +
         evidence + blocks/blocked_by edges; ask.py --decisions sorts ready-first
         (5 ready, 5 waiting). WORKPLAN now POINTS instead of restating. The symmetry
         gate caught two one-sided edges in the file I had just written. (3) CLAIMS:
         claims.yaml + qc/claims.py resolver (superset of the n_source grammar: adds
         csv:<col>@<filters> single-cell, regex:, dir_csv_count) + verify_claims.py
         (exit 1 on drift) + test_claims.py. Seven claims seeded, all OK. A drifted
         claim is REPORTED not auto-corrected - which side is wrong is a judgement.
         Mutation-tested all three failure modes (moved value -> drifted; missing file
         -> unresolved; ambiguous selector -> error) before trusting the gate.
         Also answered Kam on how Claude uses ask.py: it is now the FIRST roadmap row
         in CLAUDE.md, so orientation is CLAUDE.md + WORKPLAN + ask.py per subject
         rather than reading four docs and guessing which of ten artifacts to open.
files:   decisions.yaml, claims.yaml, qc/{claims,verify_claims,ask,landed}.py,
         qc/test_{claims,decisions}.py, qc/test_status_discovery.py ledger,
         docs/SCHEMAS.md, CLAUDE.md roadmap, WORKPLAN AWAITING-KAM section
next:    still open from the assessment: nothing. Next real work is Kam's decision
         stack - 5 decisions are READY NOW with nothing above them

## 2026-09-08  speedup-pilot-recording-ledger-recovery
goal:    Kam: "fix bottle necks", "test run on a year we have already run so you can
         compare", "improved record and metric collection", "don't defer to me for
         permissions". Orchestrator + Opus agents; every change refereed (3.4c).
did:     (1) MEASURED where the A100 idles: per-step attribution redone twice — cross-VM
         contamination (29% samples ambiguous) and net TX missing from the dead test.
         Result: tile 71% / postproc 96% of own time with EVERY counter zero = blocked on
         Drive per-file latency; vm_hwlogger counted iowait as idle. Reports §7.
         (2) LANDED, refereed, gate green: checkpoint diet (optim/sched state never read
         back; 1113.1 -> 371.4 MB measured on production arch, Reports §8); postproc
         stage-then-read; step marker + iowait column in hw telemetry (v2, 15 cols);
         harvest_hw_attribution, harvest_timing_events (first MEASURED Drive throughput:
         39.7 MB/s median over 145 large files, p10-p90 7-87), harvest_runtime_sessions;
         queue-side launching/verifying phases + VERIFY minutes; hw_meta runtime facts.
         (3) PILOT offload_pilot_2017k RAN (spdc1 CPU / spdg A100 / spdc2 CPU), verdict
         in experiments/offload_pilot_2017k.yaml from phase4/qc/offload_pilot_2017k.csv:
         K2 PASS tileset a36d6772e88b identical from CPU; R1 PROMOTE A100 span 113.0 ->
         67.3 min; R2 PASS 371.4 MB; R3 FAIL postproc 26.9 vs 18.0 (staging ENGAGED, 2.4 GB
         in 114 s; polygonize 653 vs 436 s on 2 vCPU); R5 same model AP .4338/.4275.
         Unplanned: same recipe retrain moved canopy 19.6% -> 19.1% (threshold .558 ->
         .594) = single-seed noise sample; tile copy 228 s/train (1,264 files, 5.5/s);
         same 11.5 GB ortho staged 4x at 37-133 MB/s; queue start-up 359 s merging 76
         status files over FUSE (fixed 94cb8df, unvalidated); hwlogger lost 26-30% of
         samples to its own flush (fixed e8dec13).
         (4) LEDGER ERASURE FOUND: since 4c546a7 (08-31) queue_ledger._q imported the queue
         a second time under python script start; STATUS_OUT None on the copy -> every
         launch REPLACED the shared train_queue_status.csv with its own rows. Six days
         erased. Fixed e499355 (verified: spdc2 wrote its per-launch file). 25 orphan
         snapshots preserved phase4/qc/ledger_recovery/ (252 rows); rebuild instrument
         -> 450-row candidate; RESTORED to lake as additive train_queue_status_recovered_
         20260901_20260907.csv (Kam delegated). Bootstrap never installed
         requirements-colab.txt since 08-26 (fixed 3f60b0f).
decided: labels+tile -> free CPU runtimes by default (K2+R1). postproc stays on GPU box
         (2 vCPU 1.5x slower; bigger CPU tier untested). Restore recovered ledger to lake:
         additive, readers merge, one free re-run risk accepted. Hand-split queue files
         carry no GENERATED header (drift test would fail) — split is a launch concern.
killed:  "dup-guard opens 72 heartbeat files" — refuted, stat-first, 0 s. "labels VERIFY
         took 7 min" — misread, queue ts = step START; VERIFY 3 s, 6.8 min was engine
         start-up doing 0.0 s of work. "pip installs per step" — per VM, ~13 s A100.
         "891.8 MB checkpoint" — no such file; archive bimodal 773.0 / 1113.2 MB.
         My own gating: two chains continued past failing checks (pipe masked exit code)
         — commits went out with failures; fixed after; set -o pipefail from then on.
files:   Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md §7-9; experiments/offload_pilot_
         2017k.yaml; pipeline/{pilot_offload_2017k_cpu1,gpu,cpu2}.yaml; phase4seg/{ckpt,
         select,postproc,names}.py; pipeline/{pipeline_log,vm_hwlogger,queue_ledger,
         queue_verify,phase4_train_queue,gen_vm_bootstrap}.py; qc/instruments/{harvest_hw_
         attribution,harvest_timing_events,harvest_runtime_sessions,offload_pilot_compare,
         rebuild_queue_ledger}.py + tests; phase4/qc/{hw_step_attribution,timing_events,
         runtime_sessions,offload_pilot_2017k}.csv; phase4/qc/ledger_recovery/; docs/SCHEMAS.md
         (many sections); memory queue-ledger-erasure-recovery. Branch work/20260906-healing-tool.
next:    tile-bundle handoff (workflow in flight: one archive per tileset_id, ~13 s vs
         228 s); rebuild instrument session-aware suppression (agent in flight); then
         ortho scratch cache (P3, now measured 4x re-stage), common.py::_publish_replace
         aside guard, per-epoch train profiler (train GPU-busy 20%, CPU>90% 40%, 16
         workers on 12 vCPU), evaluate's un-instrumented +1 min, ledger consolidation
         rung. Validate 94cb8df startup line on next launch. Concurrency cap raise still
         #1 wall-clock lever (Kam).

## 2026-09-08  bundle-validation-run-and-ledger-rebuild-2
goal:    validate five post-pilot machinery changes on a real run (3.4c), close the
         ledger rebuild's two limits, land the follow-ups the pilot exposed.
did:     (1) VALIDATION RAN: experiments/bundle_validation_2017k.yaml (spdvc1 CPU
         labels+tile, spdvg A100 train, PHASE4SEG_TILE_BUNDLE=1 via new `vm_ops launch
         --env`), referee-scored from named files. K1/K2 PASS. R1 FAIL: bundle read
         123.7 s vs 60 s bar (1.85x faster than 228.2 per-file; >= 86 s zero-traffic
         stall, one vCPU in D-state; rclone upload of same files 1302 vs 522 s same
         window; comparator wrong at 0.3 GB size class). Flag stays OFF. R2 PASS startup
         merge 5.1/5.9 s (was 359). R3 PASS 0 installs (was 3). R4 PASS 0 gaps 0 torn
         (was 15-24% lost). R5 PASS phases + VERIFY minutes on every step.
         (2) LANDED: tile-bundle handoff dd71417 (design duel: minimal design's guards
         all inert against same-signature re-tile; robust design sweeps every bundle on
         write); vm_ops --env 961abb0; site-discovery skip under citywide 6276207 (labels
         9.4 min of nothing; tile's cost moved inside step - needs sites for negative
         records); coverage_map/science_digest/ask.py tile SET vs DIRECTORY census
         ee5be4d 271f804 (2017k read 1264 for 632); claims split 71 sets / 83 dirs;
         cpu_model/mhz/bogomips in hw_meta 8bd256c (two "2 vCPU" hosts: 21.0 vs 39.1
         min same tile step, cause UNDETERMINED); rebuild per-LAUNCH suppression +
         start-of-step ts af60d97 (of2017k2 rows back; 496 rows replace 450 on lake).
         (3) FOUND, untimed: saving epochs 58 s vs 24 s non-saving = 11-13 min per
         train step in torch.save / sha256 read-back / publish / verify, A100 idle;
         timed copy 2.5 s of it. 4x the bundle's whole saving.
decided: bundle flag not promoted (pre-registered bar). Recovered ledger on lake
         REPLACED with 496-row version (superset, better ts). Row-count claims
         (tileset-directories) refresh at landed.py - drift expected by design.
killed:  "39.1 MB/s is the bar for a 0.5 GB read" - size-class conditioned: p10 7.5,
         16/82 under 10 at 0.01-0.33 GB. "bundle shortened training" - only 104.5 s of
         240 s delta is the staging line; rest is one fewer save. My "19.7/33.5 min
         tile compute" derivation - sampled minutes are 21.0/39.1 (ratio holds).
files:   experiments/bundle_validation_2017k.yaml; pipeline/bundle_validation_2017k_
         {cpu1,gpu}.yaml; phase4seg/{staging,tiling,cli,common}.py; pipeline/vm_ops.py;
         qc/{coverage_map,science_digest,ask}.py; qc/instruments/{rebuild_queue_ledger,
         harvest_runtime_sessions}.py; pipeline/vm_hwlogger.py; claims.yaml;
         docs/SCHEMAS.md; WORKPLAN board rows.
next:    engine workflow in flight (ortho scratch cache design duel, common.py::
         _publish_replace guard, per-epoch phase timing, evaluate ticks) - commit on
         landing. Probe: re-read aged bundle on a fresh runtime with chunked timing
         (agent writing qc/instruments/probe_bundle_read.py) - settles window vs
         structural. Then chunked copy w/ floor + rclone escape if structural. Ticks
         around torch.save/_sha256/verify_on_drive. Ledger consolidation rung.
         Concurrency cap raise (Kam) still #1 wall-clock lever.

## 2026-09-08  engine-cache-profiler-bounded-read-landed
goal:    land the engine follow-ups the pilot and validation exposed; settle the bundle
         stall question; close the session with every rung clean.
did:     (1) ENGINE 83d1169 (design duel + referees, ladder incl. bench = BENCH MATCH):
         ortho scratch cache phase4seg/scratchcache.py - entries keyed by the existing
         full-path hash, source compared on every hit, journal `copying` BEFORE the copy,
         .part + os.replace, pins per (entry, pid) under flock before validation/open,
         LRU eviction inside cache namespace only, prob raster ADOPTED after verified
         Drive copy (under the queue POSTPROC_FOLLOWS is always False - every step its
         own process - so postproc re-staged 2.4-6.7 GB every time); hit emits NO timing
         row (would fabricate the saving). Residuals closed: pre-clear stale payload
         under flock; eviction ladder never empties cache, never evicts the entry being
         made room for. common.py::_publish_replace aside guard = ledger's (OSError +
         re-probe). Per-epoch phase rows data/gpu(sync at epoch end)/val/save/other +
         evaluate spans; SCHEMAS overlap rule (sum within family). Saving UNVALIDATED
         until a same-VM tile+inference job shows the inference stage row gone.
         (2) PROBE 5aa99e1 (qc/instruments/probe_bundle_read.py, detached, log mirrored
         30 s; first attempt via exec channel timed out on a silent copy): same aged
         bundle 10.6 s copy / 18.0 s end-to-end; chunked re-read stalled 33 s once; aged
         control 66.9 MB/s no stall -> stalls intermittent on any read, not freshness.
         (3) BOUNDED READ a5e58b4: FLOOR_MBPS 6.0 (p5.3 of 0.10-0.33 GB stage rows;
         4.30 trips, 7.50/48.3 don't), MAX_STALL_S 60 (33.3 passes, >=86 fails), escape
         to rclone path; honest limit in source: on the measured trace the gate fires at
         ~101 s then fallback costs ~228 s - protects against never-returning stalls,
         saves nothing on the one seen. Verdict comparator band corrected 0.01->0.10 GB.
         (4) landed.py all mechanical rungs clean; STATUS regenerated; harvests settled.
decided: PHASE4SEG_TILE_BUNDLE stays OFF (R1 FAIL stands); re-validate on next
         campaign train now that the read is bounded. Cache lands OFF nothing - it is
         transparent; first same-VM campaign validates it.
killed:  "stall = fresh object" as sole cause (B's 33 s on a re-read). "bound saves
         time" (it bounds worst case). Exec channel for long silent VM work (times out
         waiting for output; detach + mirror instead).
files:   phase4seg/{scratchcache,common,core,labels,postproc,staging,tiling}.py,
         phase4seg_preflight.py, queue_ledger.py docstring, qc/test_{scratch_cache,
         train_timing,tile_bundle,verified_write,postproc_source}.py,
         qc/instruments/probe_bundle_read.py, phase4/qc/probe_bundle_read_2026*.txt,
         docs/SCHEMAS.md, experiments/bundle_validation_2017k.yaml extra.probe_result,
         STATUS.md/json, WORKPLAN board.
next:    finer save split (torch.save / sha256 read-back / publish / verify are ONE
         `save` bucket today; 11-13 min/train, A100 idle); validate cache + bounded
         bundle on the next campaign (heal_infill queue is ready, ~8 A100-h + 1.2 h
         tile on CPU); ledger consolidation rung; postproc on a >2-vCPU CPU tier;
         concurrency cap raise (Kam) still #1 wall-clock lever.

## 2026-09-08  healing-literature-tests-run
goal:    turn the lit review's three first tests into instruments and run the two that
         need no labels; record what they say about the healer we have.
did:     lit review landed (experiments/lit_healing_analogues.yaml; Reports/LIT_HEALING_
         ANALOGUES_2026-09-08.md; 72 mechanisms, 26 adjudicated): NO field has a measured
         laundering rate for a one-directional temporal fill; convergent formula needs
         gamma_conditional the panel cannot supply. Reasoning §14 maps it onto our design.
         INSTRUMENTS: heal_gap_spectrum (test 2): laundered_at_risk = 0 in EVERY bucket -
         a verified loss's terminal absence runs to series end, a both-sides fill can never
         touch it; 0/42 has NO POWER. heal_infill rule AMENDED on record (22d3a9c): fill-
         side audit + impossible triples are the operative tests. heal_fill_audit_sample
         (test 1): 300 fills + 300 controls drawn, 220 lidar-adjudicable; REVIEW tier has
         zero population on 8 epochs; control = one-sided absences (literal control pop is
         0 by the operator's definition). heal_fill_odds: formula licenses every fill under
         panel gamma; ~20:1 FILL under gamma_rule; inert as predicted. heal_closing_
         baseline: tier-matched closing == healer pre-floor candidate set TO THE CELL
         (449,663) - all shifts round to 0 cells at 2 m, landmark transform inert on this
         grid; healer - closing = the size floor alone (-28.9% cells, -10 triple fixes);
         floor gain UNDETERMINED. Reasoning §15 records all four.
decided: hold the 3-arm heal launch until the 2017 training divergence is refereed
         (Phase B never improved; probabilities compressed; WEAK_CALIBRATION on the
         raster; suspect window is today's engine commit).
killed:  "0 of 42 laundered" as a bound (vacuous for both-sides rules, measured).
         "the landmark transform buys placement accuracy for the healer" at 2 m (inert).
files:   qc/instruments/heal_{gap_spectrum,fill_audit_sample,fill_odds,closing_baseline}.py
         + tests; phase4/qc/heal_*.csv, heal_fill_audit_design.txt; experiments/
         heal_infill_2017_2023.yaml amendment; Reports/HEALING_TOOL_REASONING §14-15;
         docs/SCHEMAS.md; WORKPLAN rows.
next:    Kam reader session on the 300+300 (design note has the power); gamma_conditional
         from adjudicated triples once 12 epochs exist; regression referee verdict ->
         launch 2020/2022/2023 or bisect on GPU; ledger consolidation rung.

## 2026-09-08  harvester-heal2017-score-stack-generalised
goal:    answer "precision/recall of the current recipe per year" honestly; use the
         campaign's idle hours on the healer's next dependency (a stack that is not
         fixed at eight epochs).
did:     TABLE from arm_metrics at matched_p75 vs C-CAP 2021, 14 acquisitions; found
         the tracked qc_indep_report.csv had ZERO rows for any recipe arm — 285 rows /
         9 days behind the lake, hand-copied, no rung. harvest_qc_indep.py LANDED
         (1279019): byte copy + three gates (shrink / header / double-live), each
         shown to fire; landed.py rung 7. heal_2017 SCORED vs C-CAP 2021 locally
         (torch-free, 70 min): R 0.796 / P 0.753 at the held cut beside of_2017's
         0.788 / 0.753 — UNDETERMINED; sweep shows the WEAK_CALIBRATION cliff
         (recall 0.70 at u8 124 = the delivered cut, 0.32 two steps up). heal_2023
         landed on healD (BE12, held-out F1 0.813), healD stopped; heal_2020 trained
         clean (AE11, F1 0.954 at 0.50 — the 2017 divergence did not recur).
         STACK GENERALISED (b7ee58c, Opus workflow + referee PASS): heal_stack_build.py,
         census warp extracted (2009+2011s rebuilt cellwise identical), --stack/--out
         on four instruments, every default cmp IDENTICAL. 10-EPOCH TRIAL on real data
         (scratch only): BLIND 0; no-change triples 124->220, healer removes 173;
         closing launders 7/12 in-interval where the healer launders 0.
decided: 10-epoch numbers are PROVISIONAL and untracked; the experiment's verdict waits
         for the 12-epoch build (heal_2020 postproc + heal_2022 on healC).
killed:  "the delivered-cut rows do not exist for recipe arms" (they did — the tracked
         copy was stale; harvested now).
bugs:    heal_closing_baseline: laundered_in_interval (13-14) exceeds
         n_eligible_in_interval (12) on the 10-epoch stack — count and denominator are
         not the same unit; invisible on 8 epochs where both read 4. heal_gap_spectrum's
         crosscheck and crown columns read the TRACKED 8-epoch heal_vs_gold / crown
         rasters regardless of --stack (MISMATCH printed; needs --heal-vs-gold plumbing).
files:   qc/instruments/{harvest_qc_indep,heal_stack_build}.py + tests; census,
         temporal_heal, heal_vs_gold, heal_gap_spectrum, heal_closing_baseline;
         phase4/qc/qc_indep_* (503->506 rows), curves/efb2813b8a46.csv, arm_metrics,
         year_scoreboard; claims.yaml (72/86/88); landed regens; WORKPLAN rows.
next:    referee + fix the two instrument defects; 12-epoch build; rebuild
         heal_vs_gold / closing / spectrum / fill-audit on it; arm verdicts in
         experiments/heal_infill_2017_2023.yaml (carry WEAK_CALIBRATION for 2017);
         Kam: reader session on the 300+300, the two registered decisions.

## 2026-09-08  healer-closed-out-and-tabled
goal:    Kam: "bring today's healer work to a close, then table it so we can improve the
         system so work like this can move faster"; then "any runtime that is almost
         finished can continue; don't start any new epochs."
did:     DEFECTS FIXED (802a0c8, Opus workflow + referee): closing baseline's
         laundered_in_interval counted (point, epoch) fill EVENTS against a per-point
         denominator (13 of 12 on 10 epochs; both read 4 on 8, so invisible) — both per
         point now, build() refuses any count above its denominator, mutation-tested
         (old code 4 vs 2); the same unit error in laundered_terminal fixed (inert).
         Spectrum given --heal-vs-gold and an explicit crown SKIP with EMPTY cells.
         Every default byte-identical to the tracked CSVs. healD stopped after
         heal_2023 landed (BE12, F1 0.813). heal_2020 landed on healC (AE11, F1
         0.954; VERIFY:postproc OK 19:28Z); heal_2022 NEVER STARTED — healC idled with
         its exec channel lost (404); stopped via the Drive mailbox (queue+engine
         SIGTERMed, watchdog ended the VM; 0 active runtimes). Experiment set
         status: tabled with an explicit NO VERDICT + per-arm notes (2017
         WEAK_CALIBRATION + C-CAP score; 2020 clean; 2023 clean; 2022 not run);
         generated queue retired (regenerates on resumption). ELEVEN-EPOCH STACK
         cached at D:\edmonds-pipeline\heal_stack_2m.npz (8 trend8 + heal_2017/2020/
         2023, date-ordered; parity: 8 shared epochs identical to the published
         cache; 6.6 MB). landed.py: registry +1, harvests, STATUS; ordering fix —
         the experiment index is regenerated BEFORE the consistency gate (it went
         red on every landed run that added registry rows, twice today).
         WORKPLAN: healer TABLED row + SYSTEM WORK queued in leverage order.
decided: (Kam) no new GPU runs; healer science paused until the system work lands:
         (1) measured-file registry gated in the suite, (2) synthetic rehearsal lake
         of non-default shape every instrument must run on, (3) append-only lake
         writes + harvest-on-land, (4) versioned object storage when decided.
killed:  nothing scientific — the decision rule was NOT evaluated; the 10-epoch
         scratch numbers stay provisional and untracked.
files:   qc/instruments/heal_closing_baseline.py, heal_gap_spectrum.py + tests;
         docs/SCHEMAS.md; experiments/heal_infill_2017_2023.yaml + INDEX;
         pipeline/queue_heal_infill_2017_2023.yaml (removed); qc/landed.py;
         WORKPLAN.md; run_registry + harvests + STATUS; memory note
         close-out-then-table-for-system-work.
next:    the system work above (next session); on resumption: regenerate the queue,
         run heal_2022, rebuild the stack to 12, then heal_vs_gold / closing /
         spectrum / fill-audit for the experiment's verdict; Kam: reader session on
         the 300+300, the two registered decisions (augmentation seeding, selection
         metric).

## 2026-09-08  logging-blocks-fixed
goal:    Kam, after scrapping the redesign: "precise fixes to ensure our logging works
         appropriately ... targeted fixes that we have identified as blocks today."
did:     FOUND THE STALL: healC's nohup log (mirrored late) shows heal_2020 VERIFY:postproc
         OK at 19:28Z then silence; the job-level verify() re-opened the 4.1 GB prob
         raster through FUSE with no announcement and no bound (the 2018s_fx class).
         verify() now reuses this launch's VERIFY:inference verdict on a size match
         (postproc never touches the prob raster) and announces the slow path before any
         read. queue_ledger._status_write: shared-ledger fallback REMOVED (refuses out
         loud when STATUS_OUT is unset — the erasure mechanism itself). landed.py: an
         unmounted lake FAILS unless --no-lake is passed on purpose. heal_stack_build
         progress lines flush. qc/test_queue_logging_fixes.py pins all four, each fired
         on the input that slipped. Full ladder green (59f6e8f).
decided: Kam: the repo redesign is SCRAPPED ("I got carried away ... we have a decent
         system going"); overhaul branch deleted; system-work rows in WORKPLAN are
         optional hardening, not a mandate. Appending CSVs on Drive is fine as a
         convention for small laptop-side tables; it closes only the erasure class.
files:   pipeline/phase4_train_queue.py, pipeline/queue_ledger.py, qc/landed.py,
         qc/instruments/heal_stack_build.py, qc/test_queue_logging_fixes.py,
         qc/test_status_discovery.py.
next:    nothing queued; healer stays tabled; the reused-verdict path validates itself
         on the next campaign launch (watch for "reusing VERIFY:inference" in the log).

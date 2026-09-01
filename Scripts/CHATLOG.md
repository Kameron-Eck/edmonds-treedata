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

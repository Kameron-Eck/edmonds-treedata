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
         "There is no R2 radiometry table" (MINE, wrong) — qc/radiometry_norm.py is
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

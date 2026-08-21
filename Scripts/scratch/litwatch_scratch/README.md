# litwatch_scratch — recovered lit-watch scratchpad

227 files (measured 2026-08-19 via `find -type f`), two populations. Do not treat them
the same.

## 1. INSTRUMENTS — safe to run

29 analysis scripts. Several verified and cited by the project docs; `*` = re-run and
verified 2026-08-19:

buildings, cast, cast2*, chk1936, cr, height_by_surface, hist, overcount, overhang*,
overhang_recall, q119, q121, q121b, q121c, q122, q128, q131, q131b, q134, q135, q136*,
q137, q137b, q138, q138b*, refcompare, rescore, sampler*, unmeasurable

## 2. WRITERS — NEVER RE-RUN THESE

77 one-shot ledger appenders. Running one again duplicates ledger entries — this is
non-idempotent by design. Their OUTPUT is the authoritative artifact, not the script:

- `upd11`–`upd80` — append blocks to `Scripts/litwatch_robustness.md`
- `chat69`, `chat72`, `chat77`
- `entry3`, `entry4`, `entry5`
- `append.py` — appends rows to `Literature_Tracker.xlsx` with auto-incrementing IDs

## Other file types in this folder

- `*.json` — cached search results
- `*.out` — captured outputs
- `*.npz` — regenerable caches (git-ignored)

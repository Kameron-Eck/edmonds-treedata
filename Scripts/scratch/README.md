# scratch/ — one-shot territory

This directory held 243 files of one-shot builders, probes and the litwatch scratchpad
(106 scripts, 77 of them non-idempotent writers that must NEVER re-run). All of it was
archived on 2026-08-31 to make an accidental re-run impossible:

    git show archive/2026-08-pre-refactor:Scripts/scratch/<name>

Index: `Scripts/docs/ARCHIVE_INDEX.md`.

THE CONVENTION IS UNCHANGED: new one-shot or exploratory work goes here, clearly named,
and an instrument (safe to re-run) is distinguished from a writer (appends to a ledger —
run once) in its header. CI compile-sweeps this directory, so anything here must at least
parse.

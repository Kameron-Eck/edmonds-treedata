# litkb P3 — Migration + exports, 2026-09-15

Branch `work/20260913-literature-kb`, worktree `D:\edmonds-pipeline\treedata-litkb`.
Design: `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §4.6, §9.1, §10, §13, §14 P3 row.
Decisions: `Scripts/decisions.yaml` `litkb-p0-foundation`, "P3 load (Kam, 2026-09-14)".

**Status of this evidence (CLAUDE.md 3.4c):** every number below was produced by the author of
the code. No independent referee has re-run the loaders, the gate or the mutations. The gate is
an instrument whose output is a tracked CSV, so a referee can re-run it without re-running the
load; the load itself is idempotent, so a referee can re-run that too and must see nothing new.

*(numbers filled in from the live run — see the sections below)*

## What was built

| Piece | Home |
|---|---|
| `discrepancies` + the token-checked `record_discrepancy`, its only writer | `pipeline/litkb/db/migrations/0015_discrepancies.sql` |
| The case table: what a legacy row's identity is, and therefore how it is admitted | `pipeline/litkb/migrate_legacy/plan.py` |
| The loaders (tracker, manifest), through `admit.front`, never a direct insert | `pipeline/litkb/migrate_legacy/run.py` |
| Reading the legacy files, read-only | `pipeline/litkb/migrate_legacy/sources.py` |
| How a work is PRINTED — one home, shared by the export and the comparison | `pipeline/litkb/migrate_legacy/export_shape.py` |
| `litkb export tracker\|manifest\|all [--diff]` | `pipeline/litkb/export.py`, `pipeline/litkb/commands.py` |
| The gate | `qc/instruments/litkb_p3_diff.py` → `phase4/qc/litkb_p3_diff.csv` |
| Kills and guards | `qc/test_litkb_p3.py` |
| Mutation rows | `qc/instruments/litkb_p2_mutations.py` (P1a–P1e, P2a–P2b, P3b, P4a, P5a, P6a–P6f) |
| The convention, rewritten | `Scripts/docs/LITERATURE_CONVENTION.md` |

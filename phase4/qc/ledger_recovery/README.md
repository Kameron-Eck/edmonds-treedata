# ledger_recovery/ — the only surviving copies of six days of queue history

**What these are.** Byte-for-byte copies (`cp -p`, 2026-09-07 22:46Z) of every
`train_queue_status.csv.part.*` and `.prev.*` orphan found in the lake's `phase4/qc/`,
plus the shared `train_queue_status.csv` as it stood at copy time. Nothing on the lake
was moved or deleted.

**Why they matter.** Commit `e499355` explains the defect: from 2026-09-01 (refactor
`4c546a7`) until that fix, every queue launch wrote its rows to the SHARED
`train_queue_status.csv` instead of its own per-launch file, replacing the whole file
on every flush. Each launch erased its predecessors from the lake ledger. The orphans
are temp files that a failed publish left behind — each one a complete snapshot of one
launch's rows at that moment. Together they hold **252 distinct rows spanning
2026-09-01 21:21:39 to 2026-09-07 21:58:49** across the trend8, overlap-floor, Tier-1
and pilot campaigns. `part.26537e81ea` is session spdc1's final snapshot (the offload
pilot's CPU-1 slice).

**What was NOT lost.** Step logs and run manifests on the lake are intact; the registry
derives from manifests, never from these rows. What the rows carry that nothing else
does: queue-level outcome per step, queue minutes, VERIFY verdict text, session, host.

**Recovery status: RESTORED (2026-09-08, on Kam's delegation).** The candidate built by
`qc/instruments/rebuild_queue_ledger.py` (which never writes to the lake itself) was copied
to the lake as `train_queue_status_recovered_20260901_20260907.csv`, an additive file every
reader merges (resume credit, cost_report, registry_from_manifests, pilot_gate). Two
versions have been placed: 450 rows (252 snapshot + 198 synthesised, keyed on
(year, tag, step)) and then 496 rows (252 + 244, keyed per LAUNCH so a reused tag's later
successful run is recovered; `ts` on start-of-step where the block's run_id allows, the
row's `detail` prefix says which rung). `recovery_report.md` carries the per-campaign
coverage and the one known residual (trend8_2024/postproc's only surviving row is RUNNING).

**Do not sweep `phase4/qc/` on the lake** until recovery is decided; the orphans there
are the originals of these copies.

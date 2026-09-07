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

**Recovery status: NOT DONE — Kam's call.** Restoring means placing a merged
`train_queue_status_recovered_*.csv` beside the others on the lake, which every reader
would merge (resume credit, cost_report, registry_from_manifests, pilot_gate). That
alters the audit trail and the resume ledger; it is not an autonomous action. The
instrument `qc/instruments/rebuild_queue_ledger.py` (if present) produces the merged
candidate INTO THIS REPO for review and never writes to the lake.

**Do not sweep `phase4/qc/` on the lake** until recovery is decided; the orphans there
are the originals of these copies.

# litkb agent base brief (read fully before starting; the launch prompt gives only the delta)

## Environment
- PostgreSQL 18 at localhost:5433. Live DB `litkb`; tests on `litkb_test` or a worker DB `litkb_test_wN`
  named in your delta (never one another agent is using). Logins come from `%APPDATA%\postgresql\pgpass.conf`
  automatically (`psql -w`); promoter/ingest passfiles live in `D:\edmonds-pipeline\secrets\`.
- Package runs with `PYTHONPATH=Scripts/pipeline` from `<worktree>\Scripts`; `py -3.12`.
- Design: `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md`. Decisions: `Scripts/decisions.yaml` entry
  `litkb-p0-foundation` (authoritative; never stage that file). Rules: `Scripts/CLAUDE.md` §3.1, §3.2,
  §3.4c. Convention: `Scripts/docs/LITERATURE_CONVENTION.md`.
- GROBID runs in WSL Ubuntu via `Scripts/pipeline/litkb/extract/grobid.sh` (pool 4; keep a `wsl.exe`
  client open while it runs; stop it after). Docling: `D:\edmonds-pipeline\venv-docling` (CPU) or
  `venv-docling-cuda` (T2000 GPU). Never read `D:\edmonds-pipeline\secrets\obuntu.txt`.

## Hard rules
- Never print, cat, copy or log: passfiles, passwords, workstream tokens (`.litkb-workstream`), the
  Anna's Archive key, service-account keys. Tools read secrets by path; you never do.
- Never delete, move or rename anything under `D:\edmonds-pipeline\Literture\`. New files land only in
  `_litkb_staging\`; rejects go to `_quarantine\` via the tool.
- Work only in the worktree named in your delta. Never touch `main` or other worktrees.
- Commit by explicit paths (never `git add -A`). Sign commits:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` and
  `Claude-Session: <the session URL in your launch context>`.
  Push the work branch to remote `github` (there is no `origin`); if the push is refused, say so —
  the orchestrator pushes.
- Never end your turn while a job you started still runs. Poll in the FOREGROUND with a bounded
  until-loop (≤10 min per call, repeat); no completion notification will come.
- Every guard you add gets a mutation row in the harness (`qc/instruments/litkb_p2_mutations.py`):
  break it, show the whole test set fails, restore, prove by sha256. One row per CALL SITE.
- Numbers come only from commands you ran; label anything else INFERRED or UNCONFIRMED.
- `check.py --fast`: `cd Scripts && PYTHONUTF8=1 py -3.12 qc/check.py --fast` under
  `LITKB_TEST_DB=<your worker>`. Known failure: `crown_state_model`. The two inventory census pins
  are FIXED (the frozen-list fix merged with the stage-0 work, 2026-09-15). Anything else is yours.

## Known hazards
- Subagent `git push` is often refused by the permission classifier; not a git error.
- `acquire --from-file` on a `*.pdf` under the literature root dedupes against itself (fix in flight):
  pass a `.download` path. `acquire` stops at the first `duplicate-held`. `not-in-archive` is a DEAD
  status (`--retry-dead` to retry). Quarantined files block re-binding (fix in flight).
- Two archive jobs on one account confuse the counter; run one at a time.
- Migration numbers: check every open branch before choosing the next number. A number another branch
  has claimed but not landed goes in `pipeline/litkb/db/migrations/_reserved.txt`, one line per number,
  deleted by the merge that lands the file. Two branches replacing the SAME function is the harder
  case and `_reserved.txt` will not catch it: `CREATE OR REPLACE` is decided by APPLY order, not by
  number, so a database that already holds one ends up with a different body from one built from
  scratch. 0018 vs 0020 did exactly that; `0021_feeds_validator_final.sql` is what it cost to undo.
- WSL stops GROBID when the last `wsl.exe` client exits.

## Report schema (return this; nothing else)
1. Commit hash(es) and whether pushed.
2. Numbers table: what you measured, with the command or file it came from.
3. Defects/kills table: id, what, evidence, fired? (yes/no).
4. "Did NOT test": one line per thing you skipped or could not exercise.
5. Blockers for the next step, one line each.
Under 250 words unless the delta says otherwise.

---

*This file is the standing half of every litkb agent launch; the launch prompt carries only the
delta. It is tracked here (rather than pasted into each prompt from a scratchpad) so that a change
to the standing rules is a diff somebody reviews. Added to the repository 2026-09-16 with the P8
merge.*

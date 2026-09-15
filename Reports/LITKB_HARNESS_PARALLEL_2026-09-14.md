# litkb mutation harness: parallel workers (2026-09-14)

Branch `work/20260914-harness-parallel`, worktree `D:\edmonds-pipeline\treedata-harness`, branched from the
litkb branch at f918900. Kam's expectation (2026-09-14): "We are organizing the work schedule to compliment the
quality of the build" — when a quality mechanism becomes the schedule's bottleneck, make it faster in its own
sub-project without weakening it. This is the first instance.

**Who did what.** The main session forked a Fable sub-orchestrator for this; the fork's harness rules forbid it
spawning subagents, so the fork built and measured this itself. Under CLAUDE.md 3.4c that means the numbers
below are the AUTHOR's; the independent referee the brief asked for has NOT run. The litkb branch should have
an Opus referee re-run §4 before adopting this.

## 1. What changed

| File | Change |
|---|---|
| `Scripts/pipeline/litkb/db/connect.py` | `DB_TEST` can be overridden by `LITKB_TEST_DB`, only to a plain identifier starting with `litkb_test` (module refuses anything else); `is_test_db()` |
| `Scripts/pipeline/litkb/db/migrate.py` | `reset()` refuses any database that is not the configured test DB AND a `litkb_test*` name (marked guard) |
| `Scripts/pipeline/litkb/db/provision.py` | `--workers N` creates `litkb_test_w1..wN` (owner `litkb_test`, tablespace `litkb_d`, CONNECT for `litkb_test` only, same extensions); `--drop-workers N` |
| `Scripts/qc/instruments/litkb_p2_mutations.py` | `--workers N [--worker-root DIR]`: N private copies of `Scripts/` + `Reports/` (+ `.gitignore`, empty git repo) under `D:\edmonds-pipeline\_litkb_harness_workers\w<i>`, rows partitioned round-robin, each worker is this same script run inside its copy with `--only <its rows>` and `LITKB_TEST_DB=litkb_test_w<i>`; the parent reads back only the worker's own `FIRED` / `DID NOT FIRE` lines and baseline verdict, and a row with no verdict counts as a failure. `--plant-equivalent`: the harness's own kill check. `_edit()` tolerates a CRLF checkout (`core.autocrlf=true` gave this fresh worktree one CRLF file, `acquire/store.py`, and row B5 could not find its target) |
| `Scripts/qc/test_litkb_harness_parallel.py` | 5 tests, no Postgres: the env override refuses `litkb`, `postgres`, `litkb;drop`, `LITKB_TEST`, `litkb_tes`; `reset()` refuses `litkb`, `litkb_test_w2` (not the configured one), `postgres` and issues no DROP; log read-back; headroom; the worker copy is a standalone checkout |

Nothing about a ROW changed: same edit, same whole test set (P2+annas, or P1+P2+annas where the row says so),
baselines before and after in every worker, sha256 restore proof per file. `default_workers()` = 80 % of the
threads (Kam's headroom rule) = 9 on this laptop.

## 2. Measured (commands, this laptop, 2026-09-14 evening)

| Run | Rows | Workers | Wall-clock | Result |
|---|---|---|---|---|
| Full harness, parallel | 106 | 9 | **21.0 min** (19:37:44 → 19:58:43; per-worker 19.3–21.0 min, 11–12 rows each) | **106/106 fired, all 9 workers' baselines passed, rc 0** |
| Serial sample, same machine idle, one worker DB | 6 (A3b, B6, T18, A8, S12, S16) | 1 | 7 min 25 s incl. 4 baselines (2:55) → **≈45 s per row** | 6/6 fired |
| Serial full pass, litkb worktree, earlier today (author: the E3f fixer, contended by its own other work) | 106 | 1 | ≈5.5 h (started 17:43) | 106/106 |

Reading these honestly: on an idle machine a serial pass projects to roughly 106 × 45 s + baselines ≈ 85 min,
not 5.5 h — most of the earlier pass's time was contention, not the rows. The parallel pass is 21 min against
that 85-min projection (≈4×), and against the 5.5 h actually observed (≈15×). Per-worker throughput under
9-way load is ≈1.6 min per row (CPU and one Postgres server shared), so 9 workers do not give 9×; a wider
machine or a second Postgres instance would. Target "well under an hour" is met by workers alone.

## 3. The harness's own kill (3.4c)

`--plant-equivalent` adds row ZZ0: a docstring-only edit in `textnorm.py` that cannot change behaviour.

```
py -3.12 qc/instruments/litkb_p2_mutations.py --workers 2 --only B6 --plant-equivalent
B6   FIRED
ZZ0  DID NOT FIRE  PLANTED EQUIVALENT: a comment-only edit; the harness must report it DID NOT FIRE
1/2 mutations fired; baselines passed; exit 1
```

The first attempt of this check exposed a real defect in my first draft: the parent did not pass the flag to the
workers, the worker rejected the unknown id, and ZZ0 came back as "DID NOT FIRE" only because it had NO result
(`NO RESULT for ['ZZ0']`, worker rc 1, baselines FAILED). Fixed (`--worker` marker; the flag is forwarded); the
run above is after the fix, and a missing verdict is still reported separately from a genuine survivor.

## 4. What the litkb branch must do to adopt this

1. Merge this branch (5 files; no migration).
2. `py -3.12 -m litkb.db.provision --workers 9` once (the nine `litkb_test_w*` databases already exist on this
   machine from this run; they hold nothing and can be dropped with `--drop-workers 9`).
3. Run the harness as `--workers 9`; keep the serial mode for `--only` spot checks.
4. **Referee first (3.4c):** an Opus referee re-runs `--workers 9` and `--plant-equivalent`, and confirms
   106/106 and the ZZ0 survivor, before the litkb branch trusts a parallel pass.
5. The P1 harness (`litkb_p1_mutations.py`) was not touched; the same `run_workers` can be lifted into it.
6. `test_gate_extensions_and_tablespace` (P1) only inspects `litkb` and `litkb_test`, so worker databases do not
   disturb it; the git-ignore test needs the copy to be a checkout, which `make_worker_copy` provides.

## 5. Not done (scope stated, not silently dropped)

- **Targeted reruns (plan step 2)** and **cheaper races (step 3)**: not built. Workers alone met the target;
  both remain available if a wider harness (P3's) needs them. Targeted reruns carry a correctness risk (a row
  whose targeted set misses the asserting test would be a false survivor) that needs its own referee.
- **Independent referee**: not run, see the top of this report.
- Worker copies under `D:\edmonds-pipeline\_litkb_harness_workers\` (10 MB each, plus logs) are left in place.

## 6. Checks

- `ruff --select F` on the five files: clean. `secrets_check.py`: clean (1183 files). `--sites`: 35 sites,
  34 covered, 1 equivalent, unchanged. `qc/test_litkb_harness_parallel.py` + `test_litkb_harness_sites.py`:
  8 passed.
- `qc/check.py --fast` was NOT run on this branch (the litkb branch's ladder will run on merge; the only
  expected failure there is the pre-existing `crown_state_model` pointer).

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

---

## 7. Fixes after referee (2026-09-14)

Against `Reports/LITKB_HARNESS_PARALLEL_REFEREE_2026-09-14.md` (ADOPT WITH FIXES). Every guard added below was
mutated, shown to FAIL its test, and restored with a sha256 comparison — the same standard the harness holds its
subjects to (CLAUDE.md 3.4c). Mutation script: scratchpad, one break per guard, file restored in a `finally`.

| # | Fix | Where | Mutation proof (guard broken -> its test) |
|---|---|---|---|
| **D-1** | the `sys.path.insert` is gone: the harness module loads by path with `importlib` (the fixture `test_litkb_harness_sites.py` already uses), and the `_connect_with` subprocess payload relies on the `PYTHONPATH` it already sets | `qc/test_litkb_harness_parallel.py` | `test_path_insert_ledger` passes; the file now contains zero occurrences of the literal |
| **D-2** | `tree_manifest()` / `manifest_diff()`; the parent hashes the source tree ONCE into `source.manifest.json` before any copy, passes `--manifest`; each worker re-hashes its own copy before baselines and before any row. A mismatch prints `STALE COPY:` and exits 2 with **no verdict**. `COPY_IGNORE` is now one constant shared by `copytree` and the manifest | `litkb_p2_mutations.py` | broken -> `test_a_stale_worker_copy_aborts_without_reporting_a_verdict` FAILS |
| **D-3** | `parse_worker_log()` extracted from `run_workers`; the test asserts it against a committed hand-written fixture `qc/fixtures/litkb_worker_log.txt` (which deliberately contains restore-proof, `-> 1 failed` and summary lines that must NOT read as verdicts). The old test re-implemented the regex inline | both | regex narrowed to `FIRED` only -> the fixture test FAILS |
| **D-4** | `qc/test_litkb_ops.py` took the database from `connect.DB_TEST` instead of the literal `"litkb_test"` (`_db()`/`_stamp()`); the LOGIN stays the `litkb_test` role and the `litkb_test*` restriction is untouched. `nightly_dump` itself had no hard-coded name | `qc/test_litkb_ops.py` | `LITKB_TEST_DB=litkb_test_w1 pytest qc/test_litkb_ops.py`: **31 passed** (was 9 failed / 22 passed) |
| **Kill (C) / D-5** | `partition()` drops empty parts; `check_partition()` names any dropped or duplicated row and refuses an empty partition; both run before the pool. `--only` given empty is a `SystemExit`, and `--worker` without `--only` is too — a worker can no longer fall through to all 106 rows. `results.get()` replaces the `KeyError` | `litkb_p2_mutations.py` | each of the three broken in turn -> `test_a_dropped_row_is_reported_by_name` / `test_an_empty_partition_is_an_error_not_a_silent_run_of_everything` FAIL |
| **D-6** | verdicts are tri-state (`True` / `False` / `None`); `verdict_label()` prints `NO RESULT` in the row list, so a missing verdict is never printed as a survivor — which matters more now that D-2's abort produces exactly that state | `litkb_p2_mutations.py` | broken -> `test_a_row_without_a_verdict_is_never_printed_as_a_survivor` FAILS |
| **D-7** | `--workers` above `default_workers()` is refused unless `--allow-oversubscribe`; the headroom test now asserts hand-written numbers (12->9, 8->6, 4->3, 2->1, 1->1, no cpu_count->3) with `os.cpu_count` monkeypatched, instead of the formula against itself | both | broken -> `test_workers_above_the_headroom_rule_is_refused_unless_overridden` FAILS |

The stale-copy kill, live on a planted stale copy (a worker tree whose `qc/test_litkb_p2.py` was replaced by a
stub — the referee's Break B, which previously produced a FALSE SURVIVOR with passing baselines):

```
rc 2
STALE COPY: 1 file(s) differ from the source tree, e.g. Scripts/qc/test_litkb_p2.py CHANGED
this worker reports NO verdict: a stale copy produces false survivors (referee D-2)
```

### The pass after the fixes

```
--workers 9 (106 rows)                      106/106 FIRED, all 9 workers' baselines passed, rc 0, 25.1 min
                                            12 rows x7 workers + 11 x2; per-worker 23.3-25.1 min
--workers 2 --only B6 --plant-equivalent    B6 FIRED | ZZ0 DID NOT FIRE | 1/2 fired; baselines passed, rc 1
```

25.1 min against the referee's 23.3 min for the same 106 rows: the stale-copy manifest hashes ~470 files per
worker at startup, and this pass shared the machine with nothing else either. The referee's ~3.8x-over-serial
figure stands; the extra ~2 min is the cost of the D-2 check.

`qc/check.py --fast` on this branch (as `LITKB_TEST_DB=litkb_test_w1`): **1 failed, 2416 passed, 5 skipped,
1 xfailed** — the single failure is the allowed pre-existing `test_experiments.py::test_pointer_paths_resolve
[crown_state_model]`. The branch-introduced `test_path_insert_ledger` failure (D-1) and the nine
`test_litkb_ops.py` failures (D-4) are both gone.

**Not measured:** `test_litkb_ops.py` without the override (`litkb_test` was in use by another agent all
session), so its behaviour on the plain `litkb_test` name is reasoned from `connect.DB_TEST` defaulting to
exactly that string, not observed — the same caveat as the referee's §8.

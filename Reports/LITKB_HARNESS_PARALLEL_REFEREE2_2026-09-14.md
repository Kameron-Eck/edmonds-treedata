# Referee 2: the fixes to the parallel litkb mutation harness (2026-09-14)

Second independent referee under CLAUDE.md 3.4c, over `a3fd03a..ed0df58` on
`work/20260914-harness-parallel` (worktree `D:\edmonds-pipeline\treedata-harness`). The subject is the
"Fixes after referee" section of `Reports/LITKB_HARNESS_PARALLEL_2026-09-14.md`, which answers D-1..D-7 and
breaks A/B/C of `Reports/LITKB_HARNESS_PARALLEL_REFEREE_2026-09-14.md`. Nothing below is read from the
author's report: every number was re-produced here, on real data, against the real PostgreSQL 18 server on
`localhost:5433`, using only worker databases `litkb_test_w1..w9`. The proposer did not score this.

**Verdict: ADOPT.** All seven defects are closed by code, not by assertion. The two kills that did not exist
before (stale copy, partition cover) were each shown to FIRE on a known-bad input AND to be *necessary* —
with the guard mutated out, the same input produced exactly the old false result. Every one of five breaks
was reported; none produced a passing run. One defect remains, **E-1**, and it is a one-line test fix, not a
harness fault: it changes no verdict and cannot hide a survivor.

## 1. The predecessor's three breaks, re-run against the fixed harness

Each break was a temporary patch applied by a driver that restores the file in a `finally` and prints a
sha256 before/after (`restored: true` in every case). The tracked files are byte-identical to `ed0df58` at
the end of this review (§5).

| Break | Injection | Before (referee 1) | Now |
|---|---|---|---|
| **A** — worker never writes a verdict | `if a.worker: sys.exit(0)` | reported, but the row list printed `DID NOT FIRE` | **Reported, correctly named.** `worker 1/2: 0 fired, baselines FAILED, rc 0, NO RESULT for ['A1']/['B6']`; the row list now prints `A1 NO RESULT`, `B6 NO RESULT`; `0/2 fired; baselines FAILED`, rc 1. D-6 closed. |
| **B** — stale worker copy | `make_worker_copy` returns the existing copy; `w1` pre-seeded with a stub `qc/test_litkb_p2.py` | **false survivor**: `B6 DID NOT FIRE`, baselines *passed* | **Killed before any row ran.** `worker 1: rc 2 … STALE COPY: 2 file(s) differ …, e.g. Scripts/qc/instruments/litkb_p2_mutations.py CHANGED; Scripts/qc/test_litkb_p2.py CHANGED`; both rows `NO RESULT`; rc 1 in 0.1 min. D-2 closed. |
| **C** — a row dropped by the split | `parts[0] = parts[0][1:]` | `KeyError: 'A1'` | **Named, before the pool starts.** `RuntimeError: partition does not cover the chosen rows: dropped=['A1'] duplicated=[]`, rc 1. D-5 closed. |

Break B is the load-bearing one: the guard kills the copy *and* names the file. Note what it also revealed —
the stale-copy check lives inside the worker's own copy of the harness, so a copy that is stale in
`litkb_p2_mutations.py` itself can disable its own guard. I hit that case by accident (the copies left over
from Break A held the Break-A harness): both workers exited 0 in 0.0 min with no output, and the parent still
reported `NO RESULT` for both rows, rc 1. Conservative, and the parent's `missing` check is the backstop.

## 2. Two breaks of my own

**D — a duplicated row** (`parts[0] = parts[0] + parts[-1][:1]`): a row assigned to two workers, which would
let one worker's verdict silently overwrite the other's in `results[...]`.
**Reported:** `RuntimeError: partition does not cover the chosen rows: dropped=[] duplicated=['B6']`, rc 1,
before any worker launched. `check_partition` covers both directions, not only the dropped one.

**E — staleness in a file the manifest does not cover.** The brief suggested a file under `COPY_IGNORE`;
that turns out to be unreachable (`__pycache__`, `.pytest_cache`, `*.pyc`, `_litkb_ws`, `.litkb-workstream`
are excluded from `copytree` as well, so no such file exists in a copy to *be* stale, and no tracked source
file matches those patterns). The reachable version of the same hole is the **repo-root `.gitignore`**:
`make_worker_copy` copies it after `copytree`, but `tree_manifest` walks only `COPY_DIRS = ("Scripts",
"Reports")`, so it is copied and never hashed.

Measured: a worker copy whose root `.gitignore` had its `.litkb-workstream` line removed gave
`manifest_diff(source, copy) == []` — **the stale-copy kill does not see it**. Running row `E3f` (a
P1+P2+annas row) in that copy for real:

```
baseline (unmutated) (p1 + p2 + annas): 1 failed, 389 passed …
        qc/test_litkb_p1.py::test_workstream_token_file_is_git_ignored
E3f  FIRED   …    -> 3 failed, 387 passed …
1/1 mutations fired; baselines FAILED
```

So the backstop held — the baseline caught it and the worker reported `baselines FAILED` — but only because a
P1 test happens to assert on that file, and only for the 37 rows that run the P1 set. **E-2 (low):** add the
two `.gitignore` paths to the manifest; the guard's domain should equal the copy's domain, one line.

## 3. Mutating each new guard (3.4c: a gate that has never fired is not known to work)

Each guard was broken in turn and the suite run; the file was restored and sha256-compared every time
(all `restored: true`, all against `44cf4580705a850e…` for `litkb_p2_mutations.py`).

| Guard | Mutation | Result |
|---|---|---|
| manifest / stale copy | `if bad:` → `if False and bad:` | `test_a_stale_worker_copy_aborts_without_reporting_a_verdict` **FAILS** — and the stale copy went back to reporting `baseline … 82 passed` and `0/1 mutations fired; baselines passed`, i.e. **the exact false survivor of Break B**. The guard is necessary, not decorative. |
| partition cover | `if dropped or dup:` → `if False and (…)` | `test_a_dropped_row_is_reported_by_name` **FAILS** |
| tri-state verdict | `verdict_label` returns only `FIRED`/`DID NOT FIRE` | `test_a_row_without_a_verdict_is_never_printed_as_a_survivor` **FAILS** |
| oversubscribe refusal | the `a.workers > default_workers()` check disabled | `test_workers_above_the_headroom_rule_is_refused_unless_overridden` **FAILS** (and `--workers 17` then ran for real) |
| log parser | regex narrowed to `FIRED` only | `test_parse_worker_log_against_the_committed_fixture` **FAILS** |
| the fixture itself | the `B6 DID NOT FIRE` line deleted from `qc/fixtures/litkb_worker_log.txt` | the same test **FAILS** — the committed fixture is load-bearing, not decoration (D-3 closed: the old test asserted the regex against a copy of itself) |
| empty `--only` | the refusal disabled | `test_an_empty_partition_is_an_error_not_a_silent_run_of_everything` **FAILS**; the run became `0/0 mutations fired`, rc 0 — note the `a.only is not None` change means the old "silently runs all 106" path is closed twice over |
| `--worker` requires `--only` | the refusal disabled | the worker **fell straight through to all 106 rows, serially, in the shared worktree** — I killed it, and it left a live mutation behind in `Scripts/pipeline/litkb/db/migrations/0014_referee_p2_fixes.sql` (10 lines of the check-2 duplicate guard deleted), restored here with `git checkout` and sha256-verified. That is the guard's whole point, demonstrated. |

**E-3 (low, test design):** because that last break makes the test run the full 106-row set before it can
fail, its failure mode is a ~80-minute hang rather than a red test. Give `_run_worker` a `timeout=`.

## 4. The full pass and the planted-equivalent kill

```
py -3.12 qc/instruments/litkb_p2_mutations.py --workers 9
23:04:19 → 23:30:48 PDT  (26.5 min)   106/106 mutations fired; baselines passed; rc 0
  12 rows × 7 workers + 11 × 2; per-worker 24.5–26.4 min; every worker rc 0, baselines passed
```

```
py -3.12 … --workers 3 --only B6,S18 --plant-equivalent      23:31:00 → 23:34:49 (3.8 min)
B6   FIRED | S18  FIRED | ZZ0  DID NOT FIRE  (PLANTED EQUIVALENT)
2/3 mutations fired; baselines passed; rc 1
```

The survivor prints `DID NOT FIRE`, not `NO RESULT` — the tri-state does not blur the two in the direction
that matters either. 26.5 min against the author's 25.1 and referee 1's 23.3 for the same 106 rows: another
agent's **serial** P2 harness run (its own worktree, `litkb_test`, rows including `RD1..RD18`) was live on
this laptop and this Postgres server throughout my pass. The timing is therefore an upper bound under
contention, and the three figures are consistent. The shared worktree was clean (`git status --short` empty
but for this report) before, during and after.

## 5. Ladder, path-insert ledger, secrets

- **No `sys.path.insert` added.** `git diff a3fd03a..ed0df58 | grep '^+.*sys\.path\.insert'` → the only hit
  is prose inside the report. Two were **removed** (the module import and the `_connect_with` payload).
  `test_status_discovery.py::test_path_insert_ledger` passes. D-1 closed.
- **`cd Scripts && PYTHONUTF8=1 py -3.12 qc/check.py --fast` with `LITKB_TEST_DB=litkb_test_w2`:
  2 failed, 2415 passed, 5 skipped, 1 xfailed (521 s).** One is the allowed pre-existing
  `test_experiments.py::test_pointer_paths_resolve[crown_state_model]`. The other is **E-1**, below.
- Same suite under `LITKB_TEST_DB=litkb_test_w3`: **1 failed, 2416 passed** — only the allowed one. So the
  branch introduces no ladder failure except under one specific database name.
- **`git log -p a3fd03a..ed0df58`: no secrets.** Two keyword hits, both benign and both unchanged context —
  a docstring line naming `test_planted_secrets_are_refused` and one naming `pgpass`.

**E-1 (medium, the one defect).** `qc/test_litkb_harness_parallel.py:72` hard-codes `litkb_test_w2` as its
example of "a database that is **not** the configured test DB":

```python
for name in ("litkb", "litkb_test_w2", "postgres"):
```

Under `LITKB_TEST_DB=litkb_test_w2` that name *is* the configured one, `migrate.reset()` correctly permits
it, and the test fails: `Failed: DID NOT RAISE MigrationError`. Measured across four settings —
`litkb_test_w1` 13 passed, **`litkb_test_w2` 1 failed / 12 passed**, `litkb_test_w3` 13 passed, unset 13
passed. It is inherited from `11308b5`, not introduced by these fixes, and referee 1 missed it by choosing
`w1`. It is a test that reads the ambient environment — the same class as D-3/D-7. Fix: pick the foreign
name at runtime (any `litkb_test_w*` that is not `connect.DB_TEST`), or use a name no worker ever holds.

## 6. Merge risks against the litkb branch

`work/20260913-literature-kb` is at `4256e4e`, one `decisions.yaml` commit ahead of the fork point `f918900`,
so a merge **today** is textually clean (I verified the ranges by ref, without entering that worktree). The
risks are against what that branch is about to commit — its redaction closure, whose rows `RD1..RD18` I
observed running there live.

1. **`litkb_p2_mutations.py` is edited by both.** The redaction work appends rows to `M` (roughly lines
   100–450); this branch rewrites the tail (540+) and `main()`. Conflict is likely only if the redaction work
   also touches `main()`'s argument handling. Merge the tail from this branch and the rows from litkb.
2. **"106/106" expires on merge.** Nothing pins the row count, so nothing breaks — but `RD1..RD18` makes it
   ~124/124, and the acceptance claim must be **re-measured**, never carried across. Referee 1's and my
   numbers describe 106 rows.
3. **A skipped test fails every worker's baseline.** `baselines()` fails on any of
   `failed | skipped | error | errors | xpassed` (line 772). The current P2 set yields `5 deselected,
   1 xfailed` and no skips; the repo-wide suite already has 5 skips. If any *new* redaction test skips
   (pdftotext missing, network) inside `qc/test_litkb_p2.py` or `qc/test_litkb_annas.py`, **all nine workers
   report `baselines FAILED` and the whole pass goes red** with no row at fault. Highest-probability
   merge break.
4. **The copy domain is `Scripts` + `Reports` only.** A new test that reads any repo path outside those two
   (`phase4/qc/…`, `pyproject.toml`, a new top-level fixture dir) passes in the source tree and fails in
   every worker copy. Add the directory to `COPY_DIRS` — and, per E-2, to the manifest at the same time.
5. **`test_litkb_ops.py` was rewritten here** (`_db()`/`_stamp()`), so any redaction-side edit to the same
   tests conflicts. Its behaviour on the plain `litkb_test` name is still **unmeasured on both branches** —
   reasoned from `connect.DB_TEST` defaulting to that string.
6. **E-1 bites the merged branch's ladder** the moment anyone runs `check.py` with `LITKB_TEST_DB=litkb_test_w2`
   — the natural thing to do while a worker DB is free. Fix E-1 before merge; it is one line.
7. **Adoption step, not a code risk:** `py -3.12 -m litkb.db.provision --workers 9` must have run on the
   machine. The nine databases exist here.

## 7. What this referee did NOT verify

- I did not re-run any row serially; equivalence between modes rests on referee 1's 12-row sample.
- The `--plant-equivalent` kill was exercised on 2 real rows + ZZ0, not on all 106.
- `test_litkb_ops.py` without the `LITKB_TEST_DB` override was not run (`litkb_test` belongs to another
  agent this session) — the same gap referee 1 declared.
- E-2's blast radius was measured on one P1 row; I did not enumerate every file copied outside the manifest
  beyond the two `.gitignore` paths in `make_worker_copy`.
- Resource headroom during my pass was not sampled; another agent's serial run shared the machine, so any
  reading would have described both.

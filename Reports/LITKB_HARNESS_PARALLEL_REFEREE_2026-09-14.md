# Referee: the parallel litkb mutation harness (2026-09-14)

Independent referee under CLAUDE.md 3.4c for `work/20260914-harness-parallel` (worktree
`D:\edmonds-pipeline\treedata-harness`, HEAD 11308b5, range f918900..11308b5). The author built and measured
this alone and said so; nothing below is read from the author's report — every number was re-produced here on
real data, on the same laptop (12 threads, 63.8 GB).

**Verdict: ADOPT WITH FIXES.** The parallel path is equivalent to serial on the rows tested, isolation is real
and demonstrated mid-run, the planted-equivalent kill fires in both modes, and every way I broke the kill was
reported rather than passed — no break produced a green run. Three fixes are required first; one of them
(D-1) is a `qc/check.py` failure the branch introduces, which the author's §6 states was never run.

## 1. Equivalence

| Run | Rows | Workers | Wall-clock | Result |
|---|---|---|---|---|
| Full parallel | 106 | 9 | **23.3 min** (1399 s; per-worker 22.3–23.3 min, 11–12 rows each) | **106/106 FIRED**, all 9 workers' baselines passed, rc 0 |
| Serial sample | 12 | 1 (serial mode) | **12.75 min** (765 s, incl. 188 s of four baselines) | **12/12 FIRED**, baselines passed, rc 0 |

Sample: `random.Random(20260914).sample(ids, 12)` over the 106 ids in source order —
`A1,B13,R9,C5,C12,E3,S3,S4,S9,S18,S19,S28`. **All 12 verdicts MATCH between modes.**

Deviation to state: the serial pass ran with `LITKB_TEST_DB=litkb_test_w1`, because `litkb_test` is in use by
another agent and was out of bounds. That exercises the override rather than weakening the test — the row
mechanics are unchanged.

Equivalence on FIRED rows alone never compares a negative verdict across modes, so I also ran the planted
equivalent **serially** (the author only ran it parallel): `--only B6 --plant-equivalent` serial gives
`B6 FIRED` / `ZZ0 DID NOT FIRE`, rc 1 — byte-identical verdicts to the parallel run below. Both polarities now
agree across modes.

Serial rows cost ≈48 s each here (765 s − 188 s baselines, ÷12), so a 106-row serial pass on an idle machine
projects to ≈88 min. Parallel is **≈3.8× faster**, not 9× — nine pytest processes share one Postgres server and
12 threads. The author's "≈4× against the 85-min projection" is confirmed; the "≈15×" figure is against a
contended serial run and should not be quoted.

## 2. The kill, and three ways of breaking it

`--plant-equivalent` (row ZZ0, a docstring-only edit in `textnorm.py`) reports a survivor and exits non-zero in
**both** modes:

```
--workers 2 --only B6 --plant-equivalent     B6 FIRED | ZZ0 DID NOT FIRE | 1/2 fired; baselines passed  rc 1
--only B6 --plant-equivalent  (serial)       B6 FIRED | ZZ0 DID NOT FIRE | 1/2 fired; baselines passed  rc 1
```

I then broke the kill three ways. Each break was a temporary patch to
`qc/instruments/litkb_p2_mutations.py`, reverted immediately; the file is byte-identical to HEAD (§3).

| Break | Injection | What the harness did |
|---|---|---|
| **A — a worker that never writes a verdict** | `if a.worker: sys.exit(0)` after argparse | **Reported.** `worker 1: 0 fired, baselines FAILED, rc 0, NO RESULT for ['A1']` (same for w2); `0/2 fired; baselines FAILED`, rc 1. Missing verdicts are separated from survivors in the worker line — but see D-3. |
| **B — a stale worker copy** | `make_worker_copy` returns an existing copy instead of refreshing it; `w1` pre-seeded with a tree whose `qc/test_litkb_p2.py` is a stub | **Reported, misdiagnosed.** `B6 DID NOT FIRE`, `baselines passed`, rc 1 — a **false survivor**. The worker baselined **82 passed** where a correct copy baselines **241**; nothing compares the copy to the source, and nothing floors the baseline test count. Direction is conservative (a false survivor, never a false pass), so the run still fails. |
| **C — a row silently dropped by the split** | `parts[0] = parts[0][1:]` in `run_workers` | **Reported, but by crashing.** `KeyError: 'A1'` out of `results[m["id"]]`, rc 1. The row never reaches a worker, so the `missing` check (which is per-worker) cannot see it: there is no "every chosen row was assigned to exactly one worker" check. Worse variant found by accident: with 2 rows over 2 workers, the dropped partition becomes empty, `--only ""` is falsy in the worker, and **that worker silently runs all 106 rows** instead of none. |

Net: no break turned into a passing run. Two were reported with the wrong diagnosis.

## 3. Isolation

- **Mid-run, measured.** During the 9-worker pass, `w3`'s copy had `admit/binding.py` mutated
  (`lo, hi = max(0, i - AUTHOR_NEAR_LINES), ... → lo, hi = 0, len(lines)`) while the shared worktree was clean
  (`git status --short` empty).
- **Fingerprints.** sha256 over all 469 tracked files under `Scripts/` (excluding `__pycache__`/`*.pyc`) is
  **identical** before the parallel pass, after it, after the 12-row serial pass, after a force-killed worker,
  and at the end of this review.
- **`LITKB_TEST_DB` cannot leave the sandbox.** Refused live: `litkb`, `postgres`, `template1`, `litkb;drop`,
  `LITKB_TEST`, `litkb_tes`, `litkb_testX`, `litkb_test"`. Accepted: `litkb_test`, `litkb_test_w7`.
- **Second lock proved against a real server**, not a mock: connected to `litkb_test_w2` with
  `LITKB_TEST_DB=litkb_test_w3` and called `migrate.reset()` →
  `MigrationError: reset refused: only litkb_test_w3 may be reset, this is litkb_test_w2`, no DROP issued.
  Worker-to-worker damage is blocked, not just worker-to-`litkb`.

## 4. Restore proof, and a crash mid-row

The sha256 proof in `run_one` is real in the sense that matters: `before` is taken from the bytes read
**before** the mutated bytes are written, the restore is compared **after** `_pytest` returns (in a `finally`),
and a mismatch raises. It is *not* a copy-vs-source check — see D-2.

Crash test: I force-killed a worker mid-row (`taskkill` on the `w1` python during the Break-C run). Result —
the shared tree's fingerprint was unchanged, and the damage was confined to the disposable copy, which was
left holding a mutated `acquire/annas.py`. The next `make_worker_copy` rmtrees it. This is the design working.

## 5. Resource rule

56 samples at 20 s, spanning the parallel pass.

| Measure | Peak | Mean | Kam's 20 % headroom |
|---|---|---|---|
| System RAM in use | **27.9 GB of 63.8** (43.7 %) | 27.5 GB | **Met**, with 36 GB free |
| CPU (`_Total`) | 97 % instantaneous (2 of 56 samples > 90 %) | **39.5 %** | **Met on sustained load**; brief full-core spikes occur |
| Worker count | 9 of 12 threads (75 %) | — | **Met** |

9 workers respect the rule on all three readings. Note `default_workers()` (= 9 here) is **advisory only**:
`--workers` defaults to 0 and nothing stops `--workers 32`.

## 6. Hygiene

- `git log -p f918900..11308b5` (463 lines): **no secrets**. Two keyword hits, both benign — a doc line naming
  `secrets_check.py`, and an unchanged context line of a comment about the promoter's passfile.
- `qc/check.py --fast` on this branch (run as `LITKB_TEST_DB=litkb_test_w1`): **11 failed, 2398 passed**.
  - 1 allowed: `test_experiments.py::test_pointer_paths_resolve[crown_state_model]`.
  - 1 **branch-introduced**: `test_status_discovery.py::test_path_insert_ledger` — see D-1.
  - 9 in `test_litkb_ops.py` — an artifact of my `LITKB_TEST_DB` override, not of the harness rows, and itself
    a finding: see D-4.

## 7. Defects

| # | Severity | Defect | Evidence | Fix |
|---|---|---|---|---|
| **D-1** | **Blocking** | `qc/test_litkb_harness_parallel.py` does `sys.path.insert(0, .../qc/instruments)`, which is outside the closed ledger (CLAUDE.md §2.4). `check.py --fast` fails: `unlisted=['qc/test_litkb_harness_parallel.py (2)']` | §6 | Add the ledger line with its justification, or import the harness through the editable install |
| **D-2** | **High** | No copy-vs-source check. A stale worker copy yields a **false survivor** with passing baselines; a 3.4c kill criterion for staleness does not exist | Break B: 82 baseline tests vs 241, `B6 DID NOT FIRE` | Parent hashes its source tree and each copy after `copytree`; and/or assert the worker's baseline test count equals the parent's |
| **D-3** | **Medium** | `test_worker_log_is_read_back_exactly` never calls the harness — it re-implements `run_workers`' regex inline and asserts against itself. It cannot fail if the harness's parser changes. Same class as the design it is meant to police (3.4c) | the test body | Extract `parse_worker_log(text)` from `run_workers` and test *that* |
| **D-4** | **Medium** | `LITKB_TEST_DB` is only half-wired: `litkb.ops` dump/restore still targets `litkb_test` by name, so under the override the fixture's schema and `pg_dump`'s database disagree (`pg_dump: error: no matching schemas were found`) | §6, 9 failures | Route `litkb.ops` through `_c.DB_TEST`, or document the override as harness-only and gate the ops tests on it |
| **D-5** | **Medium** | A row lost between `chosen` and the partitions is caught only by a `KeyError`; an empty partition makes a worker run **all 106 rows** (`--only ""` is falsy) | Break C | Assert `sorted(flatten(parts)) == sorted(ids)` before launching; drop empty partitions; make an empty `--only` an error |
| **D-6** | **Low** | Break A's per-row line prints `DID NOT FIRE` for a row that produced **no** verdict, conflating "missing" with "survivor" in the row list (the worker line and the exit code are correct) | Break A | Print `NO RESULT` in the row list too |
| **D-7** | **Low** | `test_default_workers_keeps_kam_s_headroom` asserts the formula against itself; `default_workers()` is never enforced on `--workers` | §5 | Clamp `--workers` to `default_workers()` unless overridden explicitly |

None of D-2…D-7 can turn a surviving mutant into a passing run; every failure mode observed here is
conservative. D-1 is a ladder failure and must be fixed before merge.

## 8. What this referee did NOT verify

- Only 12 of 106 rows were re-run serially; the other 94 are equivalent on the parallel run's evidence alone.
- The nine `test_litkb_ops.py` failures were not re-run without the `LITKB_TEST_DB` override (`litkb_test` was
  off-limits this session), so their pre-existing state on `main` is **assumed**, not measured.
- Targeted reruns and cheaper races (the author's §5) were not built and were not reviewed.

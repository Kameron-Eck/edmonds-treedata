# litkb P1: independent acceptance verification, 2026-09-13

Subject: branch `work/20260913-literature-kb` at `3422c82`. Scope: confirm that the third referee's defects
(`LITKB_P1_REFEREE3_2026-09-13.md`, mutations Z1-Z15) are now caught by `Scripts/qc/test_litkb_p1.py`, as claimed in
`LITKB_P1_REPORT_2026-09-13.md` "Fixes after third referee". This verifier wrote none of the code, the tests or
the builder's harness (CLAUDE.md 3.4c). The builder's harness (`qc/instruments/litkb_p1_mutations.py`) was not used.
Every result below comes from the verifier's own driver, kept in the session scratchpad and not committed. The
driver applies each mutation as an exact string replacement (each `old` string asserted to occur exactly once),
runs the whole test file, then restores the original bytes and compares their sha256.

## Verdict: P1 ACCEPTED

- All 9 referee mutations named for re-test FIRED on the whole test file.
- The verifier's 5 new mutations against the 0012 guards and the F-7 fix also FIRED.
- In every case the failing test is a guard test, not a migration-apply failure.
- Both baselines passed, every file was restored byte-identical, and `litkb` is at 12 migrations with 0 direct-write
  offenders.

## Integrity

- **Fingerprint:** sha256 of 21 files, taken before any run: every file under `Scripts/pipeline/litkb/` except
  `__pycache__`, plus `Scripts/qc/test_litkb_p1.py`. After all runs, `sha256sum -c` gave 21 OK. Each mutation's
  restore was also sha-checked on its own (`restored_sha_match: true` ×14).
- **Baseline before:** `149 passed`; `litkb Postgres tests: 129 passed`. The Postgres tests ran and were not
  skipped.
- **Baseline after:** `149 passed`; `litkb Postgres tests: 129 passed`.
- **Tree:** `git status --short` was empty after the runs.
- **Database:** every run was against `litkb_test` only. The suite resets and migrates it from the files on disk.
  No grants or views were created by hand: Z5-Z10 are appended to 0011, so they exist only in the reset
  `litkb_test` and were removed by the next reset.

Command, from `Scripts/`: `PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 -m pytest qc/test_litkb_p1.py -q -p no:cacheprovider`.

## Referee mutations (whole file)

None of the targeted bodies was replaced by 0012. 0012 replaces only `abandon_workstream` and
`add_use_embedding`, and no mutation below touches either. So every row applies to live code, not dead code. Where
the referee's table elides with "…", the full statement was written out.

| ID | Mutation (file) | Applied | Result | Failing tests |
|---|---|---|---|---|
| Z1 | token := sha256(slug) (0010 `open_workstream`) | as written | **FIRED** (1 failed) | `test_workstream_token_is_not_derived_from_the_slug_or_id` |
| Z2 | `IF coalesce(p_token,'x') <> '' AND NOT …` (0010 `_require_ws_token`) | as written | **FIRED** (7) | `test_every_workstream_write_requires_its_token[*-empty]` ×7 functions |
| Z5 | view over `workstream_tokens`, SELECT to reader and writer (end of 0011) | elision filled | **FIRED** (1) | `test_no_agent_role_reads_token_hashes_through_any_relation` |
| Z6 | `ws_notes` with `workstream_id` and no FK, INSERT to writer (0011) | as written | **FIRED** (2) | `test_no_agent_role_holds_a_direct_write_on_a_workstream_table`, `test_role_privilege_matrix` |
| Z7 | `evidence_notes` referencing `use_evidence`, INSERT to writer (0011) | elision filled | **FIRED** (2) | same two |
| Z8 | view `use_versions_inbox`, INSERT to writer (0011) | as written | **FIRED** (2) | same two |
| Z9 | `GRANT UPDATE (text) ON blocks TO litkb_writer` (0011) | as written | **FIRED** (1) | `test_role_privilege_matrix` |
| Z10 | EXECUTE on `add_candidate` and `add_use_embedding` to ingest, full signatures (0011) | signatures filled | **FIRED** (1) | `test_role_privilege_matrix` |
| Z12 | rebase evidence copy joins `blocks bb`/`files ff`, `AND e.run_id = ff.current_run_id` (0010 `promote_rebase`) | join filled | **FIRED** (1) | `test_rebase_copies_head_evidence_whose_run_was_superseded` |

The failure counts equal the builder's reported counts (Z1 1, Z2 7, Z5 1, Z6 2, Z7 2, Z8 2, Z9 1, Z10 1, Z12 1).
That agreement is incidental: the counts were measured here independently.

## Verifier's own mutations (not tried before)

| ID | Target | Mutation | Result | Failing tests |
|---|---|---|---|---|
| N1 | 0012 `abandon_workstream`, abandon during a prepared promotion | Move the `FOR UPDATE` row lock to AFTER the prepared-promotion check (check-then-lock). The sequential guard is unchanged. | **FIRED** (1) | `test_abandon_waits_for_a_prepare_in_flight_and_is_refused` |
| N2a | 0012 `add_use_embedding`, lock | `ws.state = 'open' FOR SHARE` → `ws.state = 'open'`. The state check stays; only the lock is dropped. | **FIRED** (1) | `test_add_use_embedding_waits_for_a_commit_in_flight_and_is_refused` |
| N2b | 0012 `add_use_embedding`, version state | `IF v.st IS DISTINCT FROM 'proposed'` → `IF v.st = 'promoted'`, so prepared and rebased versions pass. | **FIRED** (1) | `test_add_use_embedding_refuses_a_promoted_or_prepared_version` |
| N3a | `workstream.py`, token-file atomicity | `O_WRONLY \| O_CREAT \| O_EXCL` → `O_WRONLY \| O_CREAT \| O_TRUNC` | **FIRED** (2) | `test_open_workstream_race_in_one_directory_leaves_no_orphan`, `test_workstream_module_writes_the_token_file_once` |
| N3b | `workstream.py`, token-file atomicity | `with conn.transaction():` → `with open(os.devnull):`. The database open then autocommits before the file write. | **FIRED** (1) | `test_open_workstream_failure_leaves_no_workstream_and_no_file` |

**N1 and N2a are the subtle cases.** Each test is a single-shot race, and it passed on both baselines.

- **Why they fail.** Each mutated body still has its lock or its check. Only the order or the lock mode changes. So
  only the race tests can see them, and those tests did.
- **What is inferred, not measured.** Two things were not separately recorded:
  - whether the embedding call in N2a was observed as `blocked`;
  - how often these race tests would flake. They were run once per state.
- **On N2a.** The failing assertion is the refusal code. The test asserts the sqlstate before it asserts `blocked`.

## Read-only probes on `litkb`

Connection: `connect_admin(litkb, postgres)`, with `default_transaction_read_only = on` set before any query. A
`CREATE TEMP TABLE` probe was refused with `25006`, which shows the session was read-only by construction.

| Probe | Result |
|---|---|
| `litkb_meta.schema_migrations` rows (max version) | **12** (12) |
| Guarded relations (`_GUARDED_RELATIONS`, imported from the test file) | 31 |
| `_direct_write_offenders`: agent logins reader, writer, promoter, ingest and test; roles reachable by MEMBER/SET/USAGE; ACL grantees; PUBLIC | **[] (0 offenders)** |
| EXECUTE set per role (reader, writer, promoter, ingest, PUBLIC) vs `_EXPECTED_EXECUTE` | all equal |
| `abandon_workstream` | SECURITY DEFINER; owner `litkb_owner`; `search_path=litkb, public, pg_temp`; ACL owner and writer only; body contains `FOR UPDATE` and the prepared check (the 0012 body is live) |
| `add_use_embedding` | SECURITY DEFINER; owner `litkb_owner`; same `search_path`; ACL owner and writer only; body contains `FOR SHARE` (the 0012 body is live) |
| `litkb.workstreams` | 0 rows |
| `litkb_test` CONNECT on `litkb` | f |

## Secrets (`git log -p 568d1b0..3422c82`, 1,272 lines, one commit)

- Added lines containing a 64-hex string: **0**.
- pgpass-shaped `host:5433:db:user:value` strings: **0**.
- `password`, `PGPASSWORD`, `passwd`, `token_urlsafe`: 3 hits, all harmless:
  - an added comment in `connect.py`: "Their passwords stay in the shared pgpass file";
  - a hunk header and a context line in `provision.py` (`_append_pgpass(path, role, password)`, and a comment);
  - none carries a value.
- `pgpass` on added lines: the two prose lines above (report and `connect.py`).
- **Files changed in the range:** the P1 report, the design doc, `connect.py`, `migrate.py`, 0012, `provision.py`,
  `workstream.py`, the harness and the test file. No `.litkb-workstream`, passfile or `secrets/` path.
- No passfile, password or token was read out or printed during this verification.

## Not done

- Z3, Z4, Z11, Z13, Z14 and Z15 were not re-run. Z3, Z4 and Z15 fired for the referee. Z11, Z13 and Z14 were judged
  harmless because a second lock catches them.
- The builder's F2a-F9b harness rows were not re-run. N1-N3b cover the same guards with different mutations.
- The cluster-level "agent reaches the owner or a superuser" branch and foreign tables were not exercised. Creating
  either needs a cluster-wide role grant or a superuser-only foreign-data wrapper. This is the builder's own open item.
- F-9 remains convention by Kam's accepted risk. It was not re-assessed.

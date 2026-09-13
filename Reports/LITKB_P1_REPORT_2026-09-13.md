# litkb P1 "Foundation" — build report, 2026-09-13

Design: `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §14 P1 row. Decisions:
`Scripts/decisions.yaml` `litkb-p0-foundation`. Branch `work/20260913-literature-kb`.

**Status of this evidence (CLAUDE.md 3.4c):** every result below was produced by the author of
the code. The mutations show the kill tests CAN fail; an independent referee has not yet
re-run them. No literature data was loaded.

## What was built

| Item (§14 P1) | Where |
|---|---|
| Migration runner (ordered SQL files, sha256 ledger over LF-normalised bytes, advisory lock, refuses edited/missing applied files, `--reset` only on `litkb_test`) | `Scripts/pipeline/litkb/db/migrate.py` |
| Provisioning: 5 LOGIN roles with random passwords appended to pgpass, DBs `litkb` / `litkb_test` in tablespace `litkb_d`, CONNECT revoked from PUBLIC, `vector`/`pg_trgm`/`fuzzystrmatch` | `Scripts/pipeline/litkb/db/provision.py` |
| Schema: §4.1–§4.6 tables, identity rows with `current_version_id`, append-only `*_versions`, `ws_heads`, text/embedding tables (`halfvec`) | migrations `0001_core.sql`, `0002_text.sql` |
| Compare-and-set writes (`write_fact`, `write_proposal`, internal `_write_version`), `set_current_run`, `open_workstream` / `abandon_workstream`, `norm_identifier`, `quote_verified` trigger | `0003_write_functions.sql` |
| Views: `main_*`, `ws_*`, `use_evidence_status` | `0004_views.sql` |
| `promote_prepare()` / `promote_commit()` / `promote_abandon()` (chains, dependency hold, version-set hash, CAS per chain) | `0005_promotion.sql`; git side `Scripts/pipeline/litkb/promote.py` |
| Role privileges | `0006_grants.sql` |
| Test role confined by the server; `requires_litkb_pg` marker with printed skip count | `provision.py`; `Scripts/qc/conftest.py` hooks |
| Tests (gate + kills) | `Scripts/qc/test_litkb_p1.py` |
| Mutation harness | `Scripts/qc/instruments/litkb_p1_mutations.py` |
| Driver kept out of `pyproject.toml` dependencies | `Scripts/requirements-litkb.txt` (`psycopg[binary]==3.3.5`) |

## Gate

| Gate | Command | Output |
|---|---|---|
| `uuidv7()` answers | `psql … -c "select uuidv7()"` | `01a09cdd-94c1-7ef4-ad41-3a6242d00d2a`; also `test_gate_uuidv7_answers` (version nibble 7) |
| Provisioning | `PYTHONPATH=pipeline py -3.12 -m litkb.db.provision` | 5 roles created; both DBs created in `litkb_d`; extensions `fuzzystrmatch 1.2, pg_trgm 1.6, vector 0.8.6` in both; `litkb_test CONNECT on litkb: false` |
| Migrations apply to `litkb` | `PYTHONPATH=pipeline py -3.12 -m litkb.db.migrate --db litkb` | `applied 6 (0001_core.sql … 0006_grants.sql); 6 recorded` |
| Migrations apply to an empty `litkb_test` | session fixture: `reset` then `apply` | `test_gate_migrations_apply_cleanly_to_an_empty_database` passed |
| Test suite green | `py -3.12 -m pytest qc/test_litkb_p1.py -q` | `23 passed in 6.00s`; `litkb Postgres tests: 21 passed` |
| Skip path when Postgres is absent | same, `LITKB_PGPORT=5999` | `2 passed, 21 skipped`; summary line `litkb Postgres tests: 21 skipped <- 21 SKIPPED: … those guards were NOT tested` |

## Kills — each shown to fire

`PYTHONUTF8=1 py -3.12 qc/instruments/litkb_p1_mutations.py`. The unmutated kill tests passed
before (`9 passed in 4.17s`) and after (`9 passed in 4.19s`). Source mutations were restored
and sha256-verified; cluster mutations were reverted and `has_database_privilege('litkb_test',
'litkb','CONNECT')` re-checked `f`. Result: **10/10 fired**.

| # | Kill (§14 P1) | Mutation | Test result under mutation |
|---|---|---|---|
| M1 | writer UPDATE on a version table is refused | `GRANT UPDATE, DELETE ON use_versions TO litkb_writer` | 1 failed — `DID NOT RAISE InsufficientPrivilege` |
| M2a | second writer on the same base refused — fact table | base predicate dropped from the fact pointer UPDATE | 1 failed — `DID NOT RAISE SerializationFailure` |
| M2b | … — proposal | base predicate dropped from the `ws_heads` UPDATE | 1 failed — `DID NOT RAISE SerializationFailure` |
| M3 | client `quote_verified = true` on a non-matching quote stored false | the `CREATE TRIGGER` removed | 1 failed — `a client-supplied quote_verified=true on a non-matching quote survived` |
| M4a | `litkb_test` → `litkb` refused by the server | `GRANT litkb_writer TO litkb_test WITH INHERIT TRUE` | 1 failed — `DID NOT RAISE OperationalError` |
| M4b | same | `GRANT CONNECT ON DATABASE litkb TO litkb_test` | 1 failed — `DID NOT RAISE OperationalError` |
| M5 | `promote commit` with a merge commit not reachable from `main` refused | is-ancestor-of-main check removed from `verify_merge` | 1 failed — `DID NOT RAISE PromotionRefused` |
| M6a | conflicting gap chain not promoted, nor its dependent (commit) | dependency hold removed from `promote_commit` | 1 failed — `the use depending on the held gap chain was promoted` |
| M6b | same, at prepare | dependency-hold fixpoint removed from `promote_prepare` | 1 failed — `the dependent of a conflicting chain was prepared` |
| M7 | (runner) an edited applied migration is refused | checksum comparison removed from `migrate.apply` | 1 failed — `DID NOT RAISE MigrationError` |

The unmutated server refusal message the M4 test asserts on is `permission denied for database`
(the test role's pgpass line uses database `*`, so the connection is authenticated and then
refused by the CONNECT check, not by a missing password).

## Ladder

`PYTHONUTF8=1 py -3.12 qc/check.py --fast`: ruff PASS, compile PASS, pytest
`1 failed, 1973 passed, 74 warnings in 377.07s`. The one failure is the known pre-existing
`qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]`. The ladder stops at
its first failing rung, so preflight was run on its own: `[PASSED] pre-flight clean`.

## Judgement calls

1. **Git reachability is checked in Python, not in the database.** The database cannot run
   git. `litkb.promote.commit` refuses before calling `promote_commit()` unless the merge
   commit is an ancestor of (fetched) `main` and the prepared commit is an ancestor of the
   merge. The database enforces the rest: the version-set hash, per-chain CAS, dependency
   holds, and EXECUTE only for `litkb_promoter`. Someone holding promoter credentials could call
   the SQL function directly and skip the git check.
2. **Test isolation by SET ROLE, not per-role credentials.** The suite logs in only as
   `litkb_test`, which owns `litkb_test` and is a member of reader/writer/promoter `WITH INHERIT
   FALSE, SET TRUE`. The suite therefore holds no credential that reaches `litkb`. M4a shows
   that INHERIT TRUE would break the confinement.
3. **`litkb_test` DB owned by `litkb_test`**, not `litkb_owner`, so the test role cannot alter or
   drop `litkb` through ownership.
4. **Credentials are in `%APPDATA%\postgresql\pgpass.conf`** (the brief), not
   `D:\edmonds-pipeline\secrets\` (design §4.7).
5. **Server confinement covers `litkb` only.** `postgres`, `template1` and `postgis_36_sample`
   still grant CONNECT to PUBLIC. Changing that would alter databases outside litkb.
6. **Immutable identity fields sit on identity rows** (`works.key`, `identifiers.scheme` /
   `value_norm`, `files.sha256`, `gaps.slug`, `uses.work_id` / `gap_id`). `identifiers.active`
   mirrors the current version's status, is written only by `_refresh_mirrors`, and exists so the
   partial unique index can enforce check 2.
7. **`write_fact` refuses to create facts.** Creation is reserved for P2 admission, which runs
   on the owner-only `_write_version`.
8. **Writer direct INSERT only on proposal version tables** (`gap_versions`, `use_versions`,
   minus state and promotion columns), per "INSERT into proposals". Fact version tables are
   function-only. A direct insert moves no pointer, and chains are walked from `ws_heads`.
9. **Names and values the design left open:** `gap_versions.state` renamed to `gap_state`;
   `extraction_runs.status` ∈ {ok, failed}; `file_checks.check_kind` / `verdict`;
   identifier `status` ∈ {active, retracted}; `acquisition_attempts.status` closed to the five
   named values; `admissions.state` defaults to `proposed`; `extraction_runs` unique key
   includes `pipeline_version`; `works.key` regex taken from `LITERATURE_CONVENTION.md`.
10. **Prepare checks:** feeds tokens must match the three named forms. The "no positional
    references" check is not implemented, because the design does not define it. The
    near-duplicate flag is "same work and gap", with no similarity threshold.
11. **After commit, held chains stay `prepared`** and the workstream is marked `merged`.
12. **`vector` is created by provisioning**, as superuser, because it is not a trusted extension.
13. **No editable reinstall.** The venv's install points at `D:\edmonds-pipeline\treedata`.
    Until it is reinstalled from a tree containing litkb, run with `PYTHONPATH=Scripts/pipeline`;
    tests import through the existing `conftest.py` path entry.

## Not built / open before P2

- **Nightly `pg_dump`** (in scope per the decision, not in the P1 row). It needs a scheduled task
  on this machine.
- Admission checks 1–4, the approve flow, and the ±1-year rule are P2. The P1 schema carries the
  admitter ≠ approver constraint (`test_admitter_cannot_approve_own_manual_admission`) and the
  normalised-identifier index (`test_identifier_case_variants_collide`).
- The §10 ladder check that fails when a key, `.env` or pgpass file is staged.
- Independent referee re-run of the mutations (3.4c).

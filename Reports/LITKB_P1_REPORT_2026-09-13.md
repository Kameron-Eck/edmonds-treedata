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

14. **`ws_heads.version_id` has no foreign key.** It points into five different version tables. This is
    a known gap in check 5; the chain walk stops at a head it cannot resolve.
15. **A chain held at commit cannot be re-promoted in P1.** Its workstream is `merged`, and
    `promote_prepare` requires `open`. This is a §5 gap for P8 or Kam, not a P2 blocker.

## Addendum — production `litkb` re-checked after commit `428e194`

- After the mutation runs and the commit,
  `PYTHONPATH=pipeline py -3.12 -m litkb.db.migrate --db litkb` printed
  `applied 0 (none pending); 6 recorded`, so the recorded hashes match the committed files.
- On `litkb` itself (owner `litkb_owner`), a probe as postgres printed `f|f|f|f|t|t` for:
  - writer UPDATE on `use_versions`
  - writer EXECUTE on `_write_version`
  - writer INSERT on `use_evidence.quote_verified`
  - `litkb_test` CONNECT on `litkb`
  - writer EXECUTE on `write_proposal` (control)
  - promoter EXECUTE on `promote_commit` (control)

## Not built / open before P2

- **Nightly `pg_dump`** (in scope per the decision, not in the P1 row). It needs a scheduled task
  on this machine.
- Admission checks 1–4, the approve flow, and the ±1-year rule are P2. The P1 schema carries the
  admitter ≠ approver constraint (`test_admitter_cannot_approve_own_manual_admission`) and the
  normalised-identifier index (`test_identifier_case_variants_collide`).
- The §10 ladder check that fails when a key, `.env` or pgpass file is staged.
- Independent referee re-run of the mutations (3.4c).

## Fixes after referee

Referee: `Reports/LITKB_P1_REFEREE_2026-09-13.md`. D-2, D-3, D-4, D-9 and D-10 are **not touched**. D-2/D-3/D-4/D-9 are
Kam's decisions; D-10 was not in the brief.
**Status of this evidence (3.4c):** the fixer wrote the code, the tests and the mutations below, so this is
author-produced evidence. The referee has not re-run it.

All code fixes are in the new migration `0007_referee_fixes.sql`. Applied migrations are checksum-locked, so 0007
`CREATE OR REPLACE`s `_write_version`, `set_current_run` and `_use_evidence_verify`. **The 0003 bodies of those
three are now history.** For that reason the harness rows M2a/M2b were re-pointed at 0007: mutating 0003 would be
dead code.

| Defect | Fix (0007) | Test (`qc/test_litkb_p1.py`) | Mutation → result |
|---|---|---|---|
| D-1 | `_write_version` locks the workstream row `FOR SHARE`. That lock conflicts with prepare's and commit's `FOR UPDATE`. A writer that waited behind a commit re-reads the row as `merged` and is refused (22023) | `test_write_blocked_behind_promote_commit_is_refused`: promoter tx holds `promote_commit`; writer thread seen blocked (`pg_blocking_pids`); commit → writer 22023, 0 heads left | D1 drop `FOR SHARE` → FIRED (writer got `ok`) |
| D-5 | evidence goes only through the new SECURITY DEFINER `add_evidence(ws, use_version, …)`. It locks the workstream `FOR SHARE` and requires it open. The version must belong to that workstream (no owner column exists, so "ownership" means the named ws) and be `proposed`, and the ws must have no prepared promotion. `quote_verified` still comes from the trigger. `REVOKE INSERT ON use_evidence FROM litkb_writer`. `set_current_run` accepts only an existing `ok` run of that file | `test_writer_has_no_direct_evidence_insert`, `test_evidence_guard_{workstream_must_be_open, version_must_belong_to_named_workstream, version_must_be_proposed, refused_while_promotion_prepared}`, `test_set_current_run_refuses_foreign_or_null_run` | D5a–D5g, one per guard → all FIRED. D5g fired because the FK then refuses with a different error; the FK stays as the second lock |
| D-5 bypasses | — | referee D1: `test_referee_bypass_d1_…` (evidence on another ws's prepared version refused, both by function and by direct INSERT; the victim's commit still commits 1). D2: `test_referee_bypass_d2_…` (promoted main version refused, 0 evidence rows). D5: `test_referee_bypass_d5_…` (failed run refused; promotable stays 1) | covered by D5a/D5d/D5f |
| D-6 | — (guards were correct) | R2 `test_writer_cannot_insert_version_state_columns`; R4 `test_first_head_proposal_must_be_based_on_main`; R6 `test_quote_verified_checks_offsets_not_presence`; R7 `test_use_whose_gap_is_absent_is_held_at_prepare` | R2, R4, R6, R7 (the referee's mutations) → all FIRED |
| D-7 | trigger raises 23514 when `char_end > length(text)` (refused, not stored false) | `test_quote_char_end_beyond_text_is_refused` | D7 remove check → FIRED |
| D-8 | identity-row `FOR UPDATE` kept, now commented as load-bearing | `test_losing_concurrent_writer_gets_40001[fact|proposal]`: A's tx open, B seen blocked, A commits → B `sqlstate == 40001` | D8 drop `FOR UPDATE` → FIRED (B got `UniqueViolation`) |
| hygiene | `.gitignore`: `.env`, `*.env`. `git ls-files -ci --exclude-standard` returns the same two pre-existing files before and after, so no tracked file is affected. `Scripts/.env` and `Scripts/pipeline/.env` now match `*.env` | — | — |

**Harness** (`PYTHONUTF8=1 py -3.12 qc/instruments/litkb_p1_mutations.py`): baseline `23 passed`; **24/24 mutations fired**
(the original 10 plus 14 new); restored baseline `23 passed`. The harness checks each restore byte-for-byte. It was
also checked independently: `sha256sum -c` against a fingerprint of all 7 migrations, `promote.py` and `migrate.py`
taken before the run printed OK for all 9 files. Full suite: `40 passed`; `litkb Postgres tests: 38 passed`.

**Applied:** `litkb_test` (and the per-session reset). On `litkb`, the output was `applied 1 (0007_referee_fixes.sql);
7 recorded`. Probe on `litkb` as postgres, `f|f|t|f|t|f`:
- writer INSERT on `use_evidence`: f
- writer INSERT on `use_evidence.quote`: f
- writer EXECUTE `add_evidence`: t
- reader EXECUTE `add_evidence`: f
- `add_evidence` is SECURITY DEFINER, pinned path, owned by `litkb_owner`: t
- `litkb_test` CONNECT on `litkb`: f

**Ladder:** `PYTHONUTF8=1 py -3.12 qc/check.py --fast`: ruff PASS, compile PASS, pytest `1 failed, 1990 passed, 74
warnings in 388.16s`. The one failure is the known pre-existing
`qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]`. The ladder stops there, so preflight was run on its own: `[PASSED] pre-flight clean`.

**Judgement calls (fixer):**
1. `set_current_run` now also refuses `NULL`. Clearing the pointer un-promotes evidence exactly as a failed run did.
2. The prepared-promotion guard goes beyond the referee's text. A held chain stays `proposed` after prepare, so
   evidence on it would change the version-set hash and block the prepared commit (D1 by another route).
3. D-7 raises instead of storing `false`, following the brief's word "refuses".

**Residual, not fixed:**
- A writer can still insert an `ok` extraction run for any file and make it current. That also un-promotes that
  file's evidence. The referee's "limited to the ingest path" needs a role or ingest design that does not exist yet.
- The workstream a caller names is not authenticated: any writer can name any open workstream. Tying callers to
  workstreams is design work.
- The writer's column INSERT on `gap_versions` / `use_versions` is unchanged. The referee noted it as noise, not a
  bypass.

## Kam's decisions implemented

Authority: `Scripts/decisions.yaml` `litkb-p0-foundation`, "After the P1 referee" (D-2, D-3, D-4, D-9).
**Status of this evidence (3.4c):** the implementer wrote the code, the tests and the mutations below. This is
author-produced evidence, and no referee has re-run it.

All database changes are in `0008_kam_referee_decisions.sql`. Every harness row targets 0008 or live Python, never
the replaced 0001 constraint text.

| Decision | Implementation | Test (`qc/test_litkb_p1.py`) | Mutation → result |
|---|---|---|---|
| D-2 rebase held chains | `promote_rebase(source_ws, target_ws, onto, agent, session)`, SECURITY DEFINER, EXECUTE for `litkb_promoter` only. The source must be `merged`. Its remaining `ws_heads` are exactly the chains held at prepare or at commit. `onto` must name every held chain with main's current version, checked by compare-and-set under the identity-row lock (a stale name is refused with 40001). The target must be open, have no prepared promotion, and have no head for the entity. Each chain gets one new version in the target, carrying the head's content, with `based_on` = main's current and `rebased_from_version_id` = the old head. Old versions are marked `rebased` (new state value), never deleted. Evidence rows are copied and re-verified by the trigger. Each rebase is recorded in `litkb.rebases`. Base rule relaxed: a rebased copy may have no base, since a never-promoted entity has none. Python: `promote.held_chains`, `promote.rebase` | `test_held_chain_is_rebased_and_promotes` replays 22023 → 55000 → 22023 → 22023, then rebases, prepares 2/2 and commits 2. Kill: `test_kill_rebase_onto_stale_main_is_refused`. Guards: `test_rebase_guard_*` ×4, `test_rebase_carries_evidence` | K2a–K2h all FIRED. K2e fired through the `ws_heads` primary key, which is the second lock |
| D-3 promoter credential | Reader and writer have no EXECUTE on prepare, commit, abandon or rebase. `connect.connect()` refuses the promoter login. `promote.connect()` is the only path, using its own passfile `connect.promoter_passfile()` (default `D:\edmonds-pipeline\secrets\litkb_promoter.pgpass`). Provision now writes the promoter's line there. The wording "the database refuses" is changed to "the promote tool refuses" in decisions, design §5, §15.7 and §4.7 | `test_agent_roles_cannot_call_promotion_functions[*]` (8, each with a promoter control), `test_connect_refuses_the_promoter_login` | K3a, K3b, K3c FIRED |
| D-4 different session suffices | `admissions_second_session_signs_off` compares sessions only | `test_admission_approver_must_be_another_session[*]`: same/same refused, other agent + same session refused (R1), same agent + other session allowed (R1b), other/other allowed | K4a (drop session clause), K4b (re-add agent clause) FIRED |
| D-9 | Design §9 and §4.7 reworded. The existing server-refusal test is kept | `test_kill_test_role_is_refused_by_the_server_on_litkb` | M4a/M4b FIRED |

**Not done, on purpose:** provisioning was not re-run and the pgpass files were not touched. Reading them was
refused to this session. As built, P1 provisioning wrote the promoter's line into the shared
`%APPDATA%\postgresql\pgpass.conf`; this is inferred from the code, not measured. **Until Kam re-runs
`py -3.12 -m litkb.db.provision`, the promoter password stays in the shared file.** The re-run resets that
password and writes it to the promoter's own file. The stale shared line can then be deleted by hand.
`promote.connect()` against `litkb` is therefore untested. The tests reach the promoter only through
`SET ROLE` on `litkb_test`.

**Harness:** baseline 35 passed; **37/37 mutations fired**; restored baseline 35 passed. A separate
`sha256sum -c` against a fingerprint of all 8 migrations, `promote.py`, `migrate.py` and `connect.py`, taken before
the run, printed OK for all 11 files. Suite: `59 passed`; `litkb Postgres tests: 56 passed`.

**Applied:** `litkb_test` (session reset). On `litkb`: `applied 1 (0008_kam_referee_decisions.sql); 8 recorded`.
A read-only probe on `litkb` printed `f|f|t|f|1|f`:
- writer EXECUTE `promote_rebase`: f
- reader EXECUTE `promote_rebase`: f
- promoter EXECUTE `promote_rebase`: t
- reader EXECUTE `promote_commit`: f
- new admissions constraint present: 1
- `litkb_test` CONNECT on `litkb`: f

**Ladder:** `check.py --fast`: ruff and compile PASS; pytest `1 failed, 2009 passed`. The one failure is the known
`test_pointer_paths_resolve[crown_state_model]`. The ladder stops there, so preflight was run on its own:
`[PASSED] pre-flight clean`.

**Residual gaps (assessed; none fixed, all need design):**
1. *Writer inserts an `ok` run and makes it current.* This un-promotes that file's evidence. Proposal: a
   `litkb_ingest` role owning INSERT on the extraction tables and EXECUTE on `set_current_run`, used only by the
   local ingest CLI. The writer loses both. Design §4.7 currently gives extraction tables to the writer, so this is
   a design change.
2. *A named workstream isn't checked against the caller.* Proposal: `open_workstream` returns a random token;
   the database stores only its hash; the token goes into the git-ignored `.litkb-workstream` file; every write
   function takes the token and compares the hash. Like session labels, this stops mistakes, not an agent that
   reads another worktree's file.
3. *Writer column INSERT on `gap_versions` / `use_versions`.* Design §4.6 check 5 and §4.7 grant agents INSERT on
   proposals, so revoking it contradicts the design. The concrete noise path: a directly inserted `proposed` use
   version in the writer's own workstream is accepted by `add_evidence`, though no chain reaches it. A direct
   insert can also take the next `version_no` and make a concurrent `write_proposal` fail with 23505 instead of
   40001. Proposal: revoke the INSERT; proposals go only through `write_proposal`. Re-point harness row R2 at the
   revoke.

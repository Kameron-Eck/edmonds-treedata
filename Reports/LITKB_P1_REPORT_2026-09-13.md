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

## Fixes after second referee

Referee: `Reports/LITKB_P1_REFEREE2_2026-09-13.md` (E-1 to E-8, mutations X1 to X9). **E-5 is not touched**, and neither
are X5/X6: Kam is deciding the rebase evidence semantics. The three residual permission gaps and the secrets folder
ACL are not touched either.
**Status of this evidence (3.4c):** the fixer wrote the code, the tests and the harness rows below, so this is
author-produced evidence. The referee has not re-run it. The mutation strings for X1 to X4, X8 and X9 are the
referee's, quoted verbatim.

Code changes: migration `0009_referee2_fixes.sql` (E-4 only) and `pipeline/litkb/db/connect.py` (E-8). E-1, E-2, E-3,
E-6 and E-7 are test-only: the guards were already correct.

| Defect | Fix | Test (`qc/test_litkb_p1.py`) | Referee mutation, whole test file |
|---|---|---|---|
| E-1 | none (test gap) | `test_commit_waits_for_a_write_in_flight_and_is_refused`: the writer's write of a NEW gap is held open, then `promote_commit` runs on a second connection. The commit is seen waiting, the writer commits, and the commit gets `40001`. The workstream stays `open` with 2 heads | X9 (with the commit-qualified string `w.id = p.workstream_id AND w.state = 'open' FOR UPDATE;`, because the bare string occurs twice in 0005) → `1 failed, 81 passed`. The commit returned `committed: 1` |
| E-2 (a) | none | `test_concurrent_rebases_of_one_workstream_make_one_copy`: the first rebase is held open, the second waits, then gets `22023 holds no chain`. `rebases` = 2 rows; the second target has 0 heads | X2 → `1 failed, 81 passed`. The second rebase returned ok |
| E-2 (b) | none | `test_rebase_during_a_commit_that_moves_main_is_refused`: ws4's commit (main g2b → g3) is held open, then a rebase runs, waits, and gets `40001`. It makes 0 copies and leaves the 2 source heads in place | X3 → `1 failed, 81 passed`. The rebase returned ok |
| E-3 | none | `test_rebase_onto_must_name_exactly_the_held_chains[missing_key, extra_key]`, fresh world per case. The missing key is the use chain whose main pointer is NULL | X4 → `2 failed, 80 passed` |
| E-4 | 0009 replaces `admissions_second_session_signs_off` and 0001's admitter checks. **Choice: labels are compared trimmed, case-sensitive, on both sides.** "Trimmed" strips space, tab, LF, CR, FF and VT, because `btrim(x)` alone strips only spaces and `' \t'` survived it (measured: the first run of the new test failed on `blank_approver_agent`). Admitter and approver agent/session must be non-blank after trim, and the approver session must differ from the admitter's after trim. `IS NOT NULL` is kept | `test_admission_approver_must_be_another_session[*]`, 13 rows: the 4 existing rows plus NULL, `''`, `'   '`, trailing space (approver side and admitter side), empty agent, `' \t'` agent, blank admitter session, blank admitter agent | X7 on the live 0009 constraint → `1 failed, 81 passed`. **The referee's literal X7 on 0008 now passes the suite (`82 passed`), because 0009 drops that constraint and 0008's text is dead code.** This is the same situation as M2a/M2b vs 0003. The harness rows X7, K4a and K4b now target 0009; before the re-point, K4a and K4b on 0008 measured DID NOT FIRE |
| E-6 | none | `test_add_evidence_waits_for_a_prepare_in_flight_and_is_refused`: prepare is held open, then `add_evidence` waits and gets `55000` with 0 rows. The prepared promotion then commits 1 | X1 → `1 failed, 81 passed`. The evidence landed |
| E-7 | none | `test_set_current_run_refuses_a_stale_expected_run`: the file is moved to run 2, then a caller still expecting run 1 gets `40001`, and the pointer stays at run 2 | X8 → `1 failed, 81 passed` |
| E-8 | `conninfo()` builds the string with `psycopg.conninfo.make_conninfo`, which quotes every value. `connect()` refuses (`LoginRefused`) any `user` or `dbname` that is not a plain lower-case identifier, before building anything. It then parses the string with `conninfo_to_dict` and refuses when the parsed, stripped `user` is the promoter (`PromoterLoginRefused`, a subclass). The plain `user == litkb_promoter` refusal runs before psycopg is imported, so the no-server tests
need no driver (a follow-up after the first commit; the first version imported the driver before refusing). The
post-parse compare sits in the same guard block as a second lock. psycopg is still imported only inside the
functions (import-weight test passes) | `test_connect_refuses_promoter_login_bypasses[*]`, with `_open` patched to fail if reached: keyword injection `litkb_writer user=litkb_promoter passfile=…`, trailing space, leading space, trailing tab, injection through `dbname`, and an empty user (libpq would fall back to `PGUSER`). `test_conninfo_quotes_values`: the parsed user is the whole injected string, and a passfile path with a space and a quote round-trips | no referee X row; new rows E8a (drop the identifier check) → `3 failed`; E8b (unquoted conninfo, the pre-fix form) → `1 failed` |

**Race tests:** each uses two separate connections and a real thread, through one helper, `_race`. The holder's
transaction stays open until the waiter is observed in `pg_blocking_pids`, or until the waiter's thread has finished
without ever blocking (the mutated case). Only then does the holder commit. No test relies on a sleep for
ordering; the sleep is only a 50 ms poll interval. Each test asserts the outcome first and `blocked` last. Under X2
and X9 the waiter still blocks, on a different lock, so the outcome is what discriminates. Under X1 and X3 it does
not block at all.

**E-8, what stays convention-only:** `connect()` now refuses every bypass the referee used through it. It cannot stop a
caller that calls `litkb.db.connect._open(...)` or `psycopg.connect(...)` directly with the promoter passfile, or
that imports `litkb.promote.connect`. Python has no private functions, and those paths need only the file. The
referee's D-3 section stands: the credential is protected by where the file is kept (and by its ACL, which is Kam's
call), not by this module.

**Harness** (`qc/instruments/litkb_p1_mutations.py`): new rows X1, X2, X3, X4a, X4b, X7, X8, X9, E4a to E4e, E8a,
E8b; K4a/K4b re-pointed at 0009. New flags: `--only ID,…` and `--whole-file`, which runs the whole test file under
each mutation, as the referee did. Each source restore prints its sha256 match. Runs, all against `litkb_test`:
- `--whole-file --only X1,X2,X3,X4a,X7,X8,X9`: baseline `82 passed`, **7/7 fired**, restored baseline `82 passed`.
- `--whole-file --only E4a,…,E4e,E8a,E8b`: **7/7 fired**, both baselines `82 passed`.
- Targeted run of every non-cluster row (M4a/M4b excluded, because they change grants on `litkb`): 48/50 fired. The
  two that did not were K4a and K4b, still pointed at the dead 0008 text. After the re-point: `--only K4a,K4b`
  2/2 fired.
- Independent `sha256sum -c` against a fingerprint of 9 migrations, `connect.py`, `migrate.py`, `promote.py` and the
  test file, taken before any mutation: 13/13 OK after all runs.

**Applied:** `litkb_test` (session reset). On `litkb`: `applied 1 (0009_referee2_fixes.sql); 9 recorded`. A read-only
probe on `litkb` found `admissions_admitter_not_blank` present, `admissions_second_session_signs_off` defined with
`btrim(approver_session…`, and 0 admission rows.

Suite: `82 passed`; `litkb Postgres tests: 72 passed`.

**Ladder:** `PYTHONUTF8=1 py -3.12 qc/check.py --fast`: ruff and compile PASS; pytest `1 failed, 2032 passed, 74 warnings
in 392.29s` (`litkb Postgres tests: 72 passed`), and the same `1 failed, 2032 passed` in 409.04s after the
driver-free follow-up (plus E8a/E8b/K3c re-run whole-file: 3/3 fired, restored baseline `82 passed`). The one failure is the known
`qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]`. The ladder stops there, so preflight was run on
its own: `[PASSED] pre-flight clean`.

## Second-referee decisions implemented

Authority: `Scripts/decisions.yaml` `litkb-p0-foundation`, "After the second P1 referee" (E-5; residual gaps 1 and 2;
secrets folder ACL accepted as is and not touched). **Status of this evidence (3.4c):** the implementer wrote the code,
the tests and the mutations below. This is author-produced evidence, and no referee has re-run it.

All database changes are in `0010_referee2_decisions.sql`. 0010 **replaces** `promote_rebase` (0008), `add_evidence`
(0007) and `write_fact`, `write_proposal`, `open_workstream`, `abandon_workstream` (0003). Those earlier bodies are now
history, so the harness rows that targeted them (D5b–D5e, X1 on 0007; K2a–K2h, X2, X3, X4a, X4b on 0008) were
re-pointed at 0010, which carries the same strings and guard markers. That the old text is now dead code is inferred
from the replacement, the same way as M2a/M2b and K4a/K4b; it was not measured this round. `_write_version` and
`set_current_run` are not replaced (set_current_run's grants change), so D1, D8, M2a, M2b, R4, D5f, D5g and X8 stay on 0007.

| Decision | Implementation | Tests (`qc/test_litkb_p1.py`) | Mutations, whole test file |
|---|---|---|---|
| E-5 rebase evidence matches promotion | the copy reads `e.use_version_id = c.head`. The earlier `= ANY (c.version_ids)` flattened every chain version's rows onto the new head. Promotion never does that: main's current version is the head, and `use_evidence_status` is keyed by version. The block, run, page, quote, offsets and stance are copied from the source. `quote_verified` is not copied; the trigger recomputes it | `test_rebase_copies_only_the_head_versions_evidence`: v1 carries a `refutes` row on page 7, and the head v2 carries none. The copy has 0 rows, `evidence_copied` = 0, and v1's row stays. `test_rebase_carries_evidence` (rewritten): the head carries a supports row on p1, a refutes row on p7 and an unverified context row on p2. The copy is equal to the source on all 8 columns, including `quote_verified`, both True and False | **X5** (back to `= ANY (c.version_ids)`) → `1 failed, 101 passed`; **X6** (page → 1, stance → `'supports'`) → `1 failed`; new **E5a** (`char_start + 1`) → `1 failed` |
| Workstream token | `open_workstream()` now returns `(workstream_id, token)`. The token is 64 hex characters from two server-side `gen_random_uuid()`, 122 random bits each. Only `encode(sha256(token))` is stored, in the new `workstream_tokens` table. REVOKE ALL is run on it for PUBLIC, reader, writer, promoter and ingest. `_require_ws_token()` refuses with 42501 "workstream token refused for workstream <id>", and the message never names the token. A NULL token counts as refused (`coalesce(v_ok, false)`; the E-4 lesson). It is called first in `write_fact`, `write_proposal`, `add_evidence` and `abandon_workstream`. The old token-less signatures are **dropped**, because a CREATE with an added parameter would leave the old overload callable with its old grant. `_write_version` (owner only) and the promotion functions take no token. Python: `litkb.workstream.open_workstream` writes `{workstream_id, token}` to `<worktree>/.litkb-workstream` with O_EXCL, never overwrites it and never prints the token; `load()` reads it back. `.gitignore`: `.litkb-workstream`, unanchored | `test_referee_cross_session_evidence_insert_is_refused`: session B names A's workstream with B's token, with no token, and with a made-up token. All three are refused, the message does not contain the token, and 0 rows are written. A with its own token is accepted. `test_every_workstream_write_requires_its_token[4 ops × {missing, another_workstreams_token}]`: each is refused with no side effect, and the workstream's own token is accepted. `test_open_workstream_returns_a_token_stored_only_as_its_hash`: the stored value is `hashlib.sha256(token)`. No row in any `litkb`/`litkb_meta` table contains the token text. Reader, writer, promoter and ingest are all refused SELECT on `workstream_tokens`. `test_token_functions_have_exactly_one_signature`. `test_workstream_token_file_is_git_ignored` (`git check-ignore --no-index` at the root, under `Scripts/` and under `Scripts/pipeline/litkb/`). `test_workstream_module_writes_the_token_file_once` (capsys: token not in stdout/stderr; a second open is refused and no row is created) | **T1** (`IF NOT v_ok`, NULL let through) → `5 failed`; **T2** write_proposal check removed → `2 failed`; **T3** write_fact → `2 failed`; **T4** add_evidence (the referee's cross-session insert) → `3 failed`; **T5** abandon_workstream → `2 failed`; **T6** store the token itself → `53 failed`; **T7** writer SELECT on `workstream_tokens` → `1 failed`; **T8** keep the old write_proposal signature → `1 failed`; **T9** remove the `.gitignore` line → `1 failed` |
| Ingest role | New LOGIN role `litkb_ingest`, created by `litkb.db.provision` (added to `ROLES`, CONNECT on `litkb`, and the test role's `SET TRUE, INHERIT FALSE` memberships). 0010 refuses to apply without it. It gets USAGE, SELECT on all tables that existed before `workstream_tokens`, INSERT on the extraction tables (`extraction_runs`, `file_checks`, `pages`, `blocks`, `tables`, `figures`, `equations`, `references`, `citation_mentions`, `chunks`, `embeddings`) and EXECUTE on `set_current_run`. The writer loses all of those. **Beyond the brief's two rights:** the writer also loses INSERT on the derived text tables, because a block the writer inserted, with text equal to its quote, in the file's current run, would verify any quote. Credential: its own passfile, `D:\edmonds-pipeline\secrets\litkb_ingest.pgpass` (`connect.ingest_passfile()`, env `LITKB_INGEST_PASSFILE`), opened only by the new `litkb.ingest.connect()`. `connect.connect()` refuses the ingest login by name, before any driver import (`IngestLoginRefused`). The post-parse check now refuses both tool logins (`TOOL_LOGINS`) | `test_writer_cannot_install_a_run_or_make_it_current`, the referee's case: the writer's `ok` run INSERT is 42501. So is the writer's `set_current_run` onto a run that ingest inserted, and the pointer is unchanged. A writer block INSERT is 42501. `test_ingest_installs_a_run_and_makes_it_current`. `test_ingest_cannot_write_knowledge`: write_proposal (gap, use), add_evidence, open_workstream, abandon_workstream, and direct INSERT on gap_versions, use_versions and use_evidence are all 42501. `test_connect_refuses_the_ingest_login`, run with `psycopg` blocked in `sys.modules`. `test_connect_refuses_promoter_login_bypasses` gains two ingest rows. Three existing tests moved their runs and `set_current_run` from the writer to an ingest session | **I1** (keep the writer's INSERT on extraction tables) → `1 failed`; **I2** (keep the writer's EXECUTE on set_current_run) → `1 failed`; **I3** (drop the ingest INSERT grant) → `5 failed`; **I4** (drop the ingest EXECUTE) → `4 failed`; **I5** (grant ingest EXECUTE on write_proposal) → `1 failed`; **I6** (drop the ingest refusal in connect()) → `1 failed` |

**Found while building:** splitting the refusal in `connect()` into a promoter block and an ingest block put the
post-parse check outside the promoter block. The existing K3c mutation (remove the promoter block) would then have been
caught by that second check, and so would have survived. `test_connect_refuses_the_promoter_login` now runs its refusal
with the driver blocked in `sys.modules`, which pins "refused before any driver import". K3c fired on the whole file (below).

**Harness** (`qc/instruments/litkb_p1_mutations.py`): new rows X5, X6, E5a, T1–T9, I1–I6, and the 17 re-pointed rows
above. T9 targets `../.gitignore`, whose working copy is CRLF. One run,
`--whole-file --only <every row except the cluster rows M4a/M4b>`, all against `litkb_test`: baseline `102 passed`,
**68/68 fired**, restored baseline `102 passed`, and 68 `restored … sha256 … match: True` lines. Before the run, a separate
`sha256sum` fingerprint was taken of all 10 migrations, `connect.py`, `migrate.py`, `promote.py`, the test file and
`.gitignore`. After the run, `sha256sum -c` printed OK for 15/15. M4a/M4b were not run: they change grants on `litkb`.

**Applied:** `litkb_test` through the session reset. `litkb` was provisioned first (`role litkb_ingest: created, pgpass
line appended`; the other five roles `exists, pgpass line present`, so no password was reset), then migrated:
`applied 1 (0010_referee2_decisions.sql); 10 recorded`. After the mutation run: `applied 0 (none pending); 10 recorded`.
A read-only probe on `litkb` as postgres printed `f|t|f|t|f|f|t|5|f|f`:
- writer EXECUTE `set_current_run`: f
- ingest EXECUTE `set_current_run`: t
- writer INSERT `extraction_runs`: f
- ingest INSERT `extraction_runs`: t
- writer INSERT `blocks`: f
- writer SELECT `workstream_tokens`: f
- writer EXECUTE the new `add_evidence`: t
- 5 functions across the five token-touched names, so no overload remains
- ingest EXECUTE `write_proposal`: f
- `litkb_test` CONNECT on `litkb`: f

`litkb.ingest.connect()` against `litkb`, read-only: `current_user = litkb_ingest`, EXECUTE `set_current_run` t,
INSERT `use_versions` f. Passfiles, read by field count and the first four fields only:
- `litkb_ingest.pgpass`: 1 line, `localhost:5433:litkb:litkb_ingest`
- the shared `pgpass.conf`: 5 lines, none for ingest or promoter

**Token and logs:** the server settings are `log_statement = none`, `log_min_error_statement = error` and
`log_parameter_max_length_on_error = 0`. psycopg binds parameters server-side, so a refused call's statement text can
reach the server log with `$n` placeholders but without the token. That is inferred from the settings; the server log
was not read. No code written in this round logs or prints the token (tested for `litkb.workstream`).

Suite: `102 passed`; `litkb Postgres tests: 88 passed`.

**Ladder:** `PYTHONUTF8=1 py -3.12 qc/check.py --fast`: ruff and compile PASS; pytest `1 failed, 2054 passed, 74 warnings
in 405.29s` (`litkb Postgres tests: 88 passed`). The one failure is the known
`qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]`. The ladder stops there, so preflight was run on
its own: `[PASSED] pre-flight clean`.

**Judgement calls:**
1. The token table is separate from `workstreams` and is readable by no agent role. A column would have been readable
   under `GRANT SELECT ON ALL TABLES`.
2. `abandon_workstream` takes the token too, because a writer abandoning another session's workstream is the same class
   of cross-session write.
3. The ingest role takes all extraction tables, not only `extraction_runs` (the block-forgery reason above). The writer
   keeps `use_embeddings`, which is knowledge-side and not extraction.
4. Existing workstreams need no backfill: `litkb` had 0 workstream rows, and a workstream without a token row is
   refused by every token-checked function.

**Residual, not fixed (outside this decision):**
- Direct column INSERTs that carry a `workstream_id` are not token-checked: `gap_versions`/`use_versions` (gap 3, ranked
  last by the referee), `candidates`, `admissions` and `acquisition_attempts`. They move no pointer. A direct version
  insert can still take the next `version_no` in another workstream's entity and turn that session's next write into
  23505. Closing this means revoking the proposal INSERTs, which is design §4.6 check 5 and Kam's call.
- The token stops mistakes, not a process that reads another worktree's `.litkb-workstream` (same Windows user). The
  same holds for the ingest and promoter passfiles, whose folder ACL Kam accepted.
- No `litkb ws open` CLI exists yet; `litkb.workstream.open_workstream` is the library call it will wrap.

## Token bypass closed

Authority: `Scripts/decisions.yaml` `litkb-p0-foundation`, "After the second P1 referee" (each workstream's session
presents its token). **Status of this evidence (3.4c):** the implementer wrote the migration, the tests and the
mutations below. This is author-produced evidence, and no referee has re-run it.

**Enumerated (catalog, before 0011, `litkb` and `litkb_test` identical).** `has_table_privilege` for
INSERT/UPDATE/DELETE/TRUNCATE plus `has_column_privilege` for INSERT/UPDATE, roles reader, writer, promoter, ingest,
on every table in `litkb`, `litkb_meta` and `public`. Table-level checks alone show nothing, because the writer's
grants were column-level. Result: reader and promoter held no write right anywhere. Ingest held INSERT on the 11
extraction tables only. The writer held column INSERT on six tables, all workstream-bearing:

| Table | Why it belongs to a workstream | Writer path after 0011 |
|---|---|---|
| `gap_versions`, `use_versions` | `workstream_id` column | `write_proposal` (0010) |
| `candidates` | `workstream_id` column | new `add_candidate` |
| `acquisition_attempts` | `workstream_id` column | new `record_acquisition_attempt` |
| `use_embeddings` | FK to `use_versions` (one hop) | new `add_use_embedding` |
| `admissions` | `workstream_id` column | none in P1 (judgement call 2) |

**Rule for "workstream-bearing"** (built from the catalog by the new test): a table with a foreign key to
`litkb.workstreams`, or `workstreams` itself, or a table with a foreign key to such a table that has a `workstream_id`
column. The extraction tables stay out. They reference `files` and `extraction_runs`, and `files.created_in_ws` is
creation provenance on a main-owned identity row, not a workstream's view.

**Migration `0011_token_bypass_closed.sql`:** `REVOKE INSERT … FROM litkb_writer` on the six tables, one guard block
per table. A table-level REVOKE also removes the 0006 column grants, so 0006's column lists are now dead code. It
adds three SECURITY DEFINER functions, each with a pinned `search_path`, EXECUTE revoked from PUBLIC and granted to
the writer, and each calling `_require_ws_token` first:
- `add_candidate` writes `workstream_id` from the checked argument. It does not accept `state`, `state_reason` or
  `admitted_work_id`.
- `record_acquisition_attempt` also writes `workstream_id` from the checked argument.
- `add_use_embedding` also refuses (42501) a use version written in another workstream, the `add_evidence`
  ownership rule.

**Tests** (`qc/test_litkb_p1.py`):
- `test_writer_has_no_direct_write_on_workstream_tables[6 tables]`: the writer's INSERT of an otherwise-valid row is
  42501, and the owner's identical statement lands.
- `test_every_workstream_write_requires_its_token` gains the three functions × {missing, another workstream's
  token}. Each is refused with no side effect and accepted with its own token.
- `test_add_use_embedding_version_must_belong_to_named_workstream`.
- `test_no_agent_role_holds_a_direct_write_on_a_workstream_table`:
  - It builds the table set and the role set (every `litkb%` role and PUBLIC, minus each table's owner and
    superusers) from the catalog, then checks table- and column-level INSERT/UPDATE/DELETE/TRUNCATE.
  - It asserts the set contains the six tables plus `use_evidence`, `ws_heads`, `workstream_tokens` and `rebases`,
    and excludes `blocks`, `extraction_runs`, `pages` and `chunks`, so the rule is neither vacuous nor all-matching.
- `test_writer_cannot_insert_version_state_columns` was rewritten. The writer's formerly granted `agent` column is
  now refused too, and its NotNullViolation control runs as the owner.
- `test_token_functions_have_exactly_one_signature` covers the new names.
- Suite: `116 passed`; `litkb Postgres tests: 102 passed`.

**Harness** (`--whole-file`, all against `litkb_test`):
- New rows: W1–W6 (keep each revoke's grant), W7–W9 (remove each token check), W10 (remove the embedding ownership
  check). W11–W13 are grants that no per-table test names, so only the catalog test can catch them: INSERT on
  `rebases` to the promoter (FK-to-workstreams branch), column UPDATE on `use_embeddings.model` to the reader
  (one-hop, column-level branch), and DELETE on `admissions` to ingest (table-level branch).
- R2 re-pointed at 0011's `use_versions` revoke, because its 0006 target is dead code now.
- Run `--only W1..W13,R2`: baseline `116 passed`, **14/14 fired**, restored baseline `116 passed`, 14
  `restored … sha256 … match: True` lines.
- **Found in that run:** W4 fired only through the catalog test (`1 failed`). The per-table admissions row named
  `state`, which 0006 never granted, so the writer was refused whatever 0011 did. The row no longer names `state`.
  W4 re-run: `2 failed, 114 passed`, and both baselines `116 passed`.
- A separate `sha256sum` fingerprint of all 11 migrations, `connect.py`, `migrate.py`, `promote.py`, the test file,
  the harness and `.gitignore`, taken before that re-run, printed OK for 17/17 after it.
- The 68 earlier rows were not re-run. Only R2 targeted text that 0011 supersedes, and the whole-file baseline
  passes.

**Applied:** `litkb_test` through the session reset. On `litkb`: `applied 1 (0011_token_bypass_closed.sql); 11 recorded`,
run before any mutation touched the file. A read-only probe on `litkb` as postgres found:
- no INSERT/UPDATE/DELETE/TRUNCATE at table or column level for reader, writer or promoter on any table;
- ingest INSERT on the 11 extraction tables only;
- writer EXECUTE on `add_candidate`, `record_acquisition_attempt` and `add_use_embedding` (ACL). A second read-only
  query on `pg_proc` showed each one with `prosecdef` t, `proowner` `litkb_owner` and
  `proconfig` `search_path=litkb, public, pg_temp`;
- `litkb_test` CONNECT on `litkb` f, 0 workstreams, 11 migrations recorded.

**Design:** §4.6 check 5, §4.7 (writer row, token paragraph), §5 step 1 and §9 (MCP write tools) no longer say the
writer can INSERT into version tables, candidates, admissions or attempts.

**Ladder:** `PYTHONUTF8=1 py -3.12 qc/check.py --fast`: ruff and compile PASS; pytest `1 failed, 2068 passed, 74 warnings
in 418.43s` (`litkb Postgres tests: 102 passed`). The one failure is the known
`qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]`. The ladder stops there, so preflight was run on
its own: `[PASSED] pre-flight clean`.

**Judgement calls:**
1. Revoked INSERT only, the one right held. UPDATE/DELETE/TRUNCATE were never granted, and the catalog test fails if
   any appears. A blanket catalog-driven REVOKE in the migration would have masked every per-table mutation.
2. **No `admissions` function.** Design §4.6 makes admission one owner-side transaction (checks 1–4, `works`,
   `identifiers`, `files`, the admission row), so a writer-only admission INSERT cannot complete an admission, and
   a direct `registry` row could claim one that never ran. `write_fact` already refuses creation "reserved for P2
   admission". P2's `admit` must take the token.
3. The new functions do not require the workstream to be `open`. The token is the decision's whole requirement, and
   these rows are not in any version-set hash. Refusing closed workstreams would be one more guard, with a test and
   a mutation.
4. The token-less `workstream_id IS NULL` path is gone for the writer. Candidates from citations (design §7 stage 6)
   will need an ingest-side or P6 function; ingest has never held INSERT on `candidates`.

**Residual, not fixed:** `add_use_embedding` checks that the version belongs to the workstream, but not the version's
state. A session with its own token can therefore attach an embedding to one of its versions that is already
prepared or promoted. Embeddings are not in the version-set hash, so no promotion is disturbed. This has not been
tested. (Closed by F-3 below.)

## Fixes after third referee

Authority: `Reports/LITKB_P1_REFEREE3_2026-09-13.md` (F-1 to F-9, mutations Z1–Z15) and `Scripts/decisions.yaml`
`litkb-p0-foundation`. **Status of this evidence (3.4c):** the implementer wrote the fixes, the tests and the harness
rows. This is author-produced evidence, and no referee has re-run it.

| ID | Fix | Tests (`qc/test_litkb_p1.py`) | Referee mutation |
|---|---|---|---|
| F-1 | Catalog guard rewritten (`_GUARDED_RELATIONS`, `_direct_write_offenders`). The relation set covers relkinds `r p v m f`: `workstreams`, every relation with a `workstream_id` column (with or without a foreign key) or a foreign key to `workstreams`, and every view and materialized view, plus the foreign-key closure at any depth. The closure does not descend through tables with a `created_in_ws` column (judgement call 1). The role set is every role an agent login (reader, writer, promoter, ingest, test) can reach by `pg_has_role` MEMBER/SET/USAGE, plus PUBLIC and every ACL grantee, whatever its name; owners and superusers are exempt. An agent that can reach an owner or a superuser is itself an offender. Checked: table-level INSERT/UPDATE/DELETE/TRUNCATE/TRIGGER/MAINTAIN, column-level INSERT/UPDATE | `test_no_agent_role_holds_a_direct_write_on_a_workstream_table`; `test_catalog_guard_fires_on_new_workstream_bearing_relations` creates, grants and rolls back inside `litkb_test`: a no-FK `workstream_id` table, tables 2 and 3 hops below `use_evidence`, a view without `workstream_id`, a matview, a partitioned table granted to PUBLIC, and a TRUNCATE held by ingest that is found only through litkb_test's `INHERIT FALSE, SET TRUE` membership. Negative control: a child of `blocks` is not guarded | Z6, Z7, Z8 FIRED |
| F-2 | 0012 `abandon_workstream`: token, then `FOR UPDATE` on the workstream row, then 55000 while a promotion is prepared | `test_abandon_refused_while_promotion_prepared`; `test_abandon_waits_for_a_prepare_in_flight_and_is_refused` (R5 ordering: blocked, 55000, ws open, commit ok) | new rows F2a, F2b FIRED |
| F-3 | 0012 `add_use_embedding`: token, `FOR SHARE` on an open workstream (22023), version owned (42501) and `proposed` (55000) | `test_add_use_embedding_refuses_a_closed_workstreams_token` (merged ws with its held version still proposed; abandoned ws); `…_refuses_a_promoted_or_prepared_version`; `…_waits_for_a_commit_in_flight_and_is_refused` (R4: blocked, 22023, 0 rows) | new rows F3a–F3c FIRED |
| F-4 | tests only | `test_every_workstream_write_requires_its_token` gains `empty` and `upper_cased_own` (×7 functions); `test_workstream_token_is_not_derived_from_the_slug_or_id` (same slug re-opened: another token; not sha256/md5 of slug or id). `_refused_by_token` no longer searches the message for `''` | Z1, Z2 FIRED |
| F-5 | Tests only. The current grants allow neither Z9 nor Z10 (measured: the matrix passes on `litkb_test`, and the probe below on `litkb`), so nothing was revoked | `test_role_privilege_matrix`: per role, effective table and column write rights on every relation in litkb/litkb_meta/public, EXECUTE on every litkb/litkb_meta function, schema CREATE and database CREATE/TEMP, each equal to §4.7; the test login owns everything and inherits no agent role. `test_no_agent_role_reads_token_hashes_through_any_relation` (views depending on `workstream_tokens` at any depth, or any `token_hash` column) | Z9, Z10, Z5 FIRED |
| F-6 | tests only | `test_rebase_copies_head_evidence_whose_run_was_superseded` (ingest moves the file's run after the evidence was added; copied 1, run_id = source) | Z12 FIRED |
| F-7 | `litkb.workstream.open_workstream`: claim the file with `O_EXCL` first, then open the workstream inside a transaction, write and fsync the token, commit; any failure rolls back and unlinks. Refuses a connection already inside a transaction | `test_open_workstream_race_in_one_directory_leaves_no_orphan` (10 rounds × 2 threads: one ok, one `WorkstreamFileExists`, exactly one open ws, the file's); `test_open_workstream_failure_leaves_no_workstream_and_no_file` (injected write failure) | new rows F7a, F7b FIRED |
| F-8 | Rule written in `workstream.py` and design §4.7: the token is sent only as a bound parameter. No shipped litkb client sends a token today; the tests' calls bind it | `test_token_is_bound_never_visible_in_pg_stat_activity`: a `write_proposal` waiting behind an owner `FOR UPDATE` shows `write_proposal` and no token in its `pg_stat_activity.query`, and no row in the view contains the token. Control: an inlined marker literal IS visible to the same viewer | none (the in-test control is the known-bad input) |
| F-9 | `connect()` refuses `postgres` and `litkb_owner` (`AdminLoginRefused`, before the driver; a second lock on the parsed user). New `connect_admin()` opens only those two. `migrate.runner_connect` (owner for `litkb`) and `provision` use it | `test_connect_refuses_the_admin_logins[postgres, litkb_owner]`; `test_admin_logins_open_only_through_connect_admin` (refuses every agent login, `'postgres '` and `''`; migrate and provision reach the driver as owner and postgres, never through `connect()`); three new bypass params | new rows F9a, F9b FIRED |

**Harness** (`qc/instruments/litkb_p1_mutations.py --whole-file`, `litkb_test` only):
- New rows: Z1, Z2, Z5–Z10 and Z12 as the referee quoted them. Where the referee's table elides with "…", the row
  writes out the full statement: Z5's and Z7's GRANT names the created relation, Z10 names both full signatures, and
  Z12 joins `blocks bb` and `files ff`. Also new: F2a, F2b, F3a–F3c, F7a, F7b, F9a, F9b.
- T5, W9 and W10 were re-pointed to 0012, because 0012 replaces their 0010/0011 bodies, which are now dead code.
- Run of 37 rows (the new rows, T5, W1–W13 because the catalog test changed, and E8a, E8b, K3c, I6, M7 because
  connect.py and migrate.py changed): baseline `149 passed`, **37/37 fired**, restored baseline `149 passed`, and 37
  `restored … match: True` lines. Before the run, a `sha256sum` fingerprint was taken of 23 files: the 12 migrations,
  connect/migrate/provision/promote/ingest/workstream, both `__init__.py`, the test file, the harness and
  `.gitignore`. After the run it gave **23/23 OK**.
- Whole-file failure counts: Z1 1, Z2 7, Z5 1, Z6 2, Z7 2, Z8 2, Z9 1, Z10 1, Z12 1.
- The other harness rows were not re-run. None of them targets text that 0012 or the changed Python supersedes.

**Suite:** `149 passed; litkb Postgres tests: 129 passed` (was 116/102).

**Applied:**
- On `litkb`, as `litkb_owner` through `connect_admin`: `applied 1 (0012_referee3_fixes.sql); 12 recorded`. This ran
  before any mutation touched a file. Re-running both runners after the restore check gave `applied 0; 12 recorded`
  on `litkb` and on `litkb_test`, and the runner's immutability check compared the recorded checksums with the
  restored files.
- A read-only probe on `litkb` (`default_transaction_read_only`) found:
  - 0 offenders from `_direct_write_offenders` over 31 guarded relations, for reader, writer, promoter and ingest;
  - every role's EXECUTE set equal to `_EXPECTED_EXECUTE`;
  - `abandon_workstream` and `add_use_embedding`: `prosecdef` t, owner `litkb_owner`,
    `search_path=litkb, public, pg_temp`, ACL `litkb_writer=X`;
  - 0 workstreams, and `litkb_test` CONNECT f.

**Judgement calls:**
1. **Where the closure stops.** A literal transitive FK closure from `workstreams` covers every extraction table
   (`uses.current_version_id → use_versions`, then `blocks → files`, and so on), which would make ingest's §4.7
   INSERTs offenders. The closure therefore checks identity tables (`created_in_ws`: works, identifiers, files, gaps,
   uses) but does not descend through them. A future table below an identity table is outside the rule unless it has
   a `workstream_id` column or is a view.
2. **Every view is guarded**, whatever its columns. Today the 11 views hold no agent write.
3. **Foreign tables** are in the relkind set but were not exercised: creating one needs a foreign-data wrapper,
   which is superuser-only.
4. **Not exercised at cluster level:** an agent login that can reach an owner or a superuser. It needs a role grant
   made as postgres, which would touch `litkb`'s roles. The SET-only membership branch is exercised in-database.
5. **The test login's matrix row** asserts ownership and no inherited agent role. In `litkb_test` it owns every object,
   so its privileges are ownership's. The property that counts is the server's CONNECT refusal on `litkb`, which is
   already tested.
6. **F-9 is convention, not enforcement**, like the tool-login refusals. A process that reads the shared pgpass file
   still reaches both logins (Kam's accepted risk).

**Ladder:** `PYTHONUTF8=1 py -3.12 qc/check.py --fast`: ruff PASS, compile PASS; pytest `1 failed, 2101 passed, 74 warnings
in 423.20s` (`litkb Postgres tests: 129 passed`). The one failure is the known
`qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]`. The ladder stops there, so preflight was run on
its own: `[PASSED] pre-flight clean`.

**Open:** F-9 remains convention, as Kam's accepted risk. The cluster-level "agent can SET ROLE to the owner" branch
and foreign tables are not exercised. No shipped client sends a token yet, so F-8 binds future CLI and MCP code by
the written rule and this test pattern. No referee has re-run this section.

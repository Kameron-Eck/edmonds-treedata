# litkb P1: third independent referee (after 0009, 0010, 0011), 2026-09-13

Subject: branch `work/20260913-literature-kb` at `72825b2`, review range `69c08d8..72825b2`. Authority:
`Scripts/decisions.yaml` `litkb-p0-foundation`. Prior referees: `LITKB_P1_REFEREE_2026-09-13.md` (D-1 to D-10) and
`LITKB_P1_REFEREE2_2026-09-13.md` (E-1 to E-8). The builder's claims are in `LITKB_P1_REPORT_2026-09-13.md`, sections
"Second-referee decisions implemented" and "Token bypass closed".

This referee is not the author (CLAUDE.md 3.4c). The builder's harness was read but not used as evidence. Every
result below comes from scripts this referee wrote, kept in the session scratchpad and not committed:
- `r3mut.py`: the mutations;
- `r3probes.py`, `r3p7.py`, `r3p7b.py`: the probes;
- `r3races.py`: the races;
- `probe.sql`: the catalog probe.

The mutation strings are quoted below so that each row can be re-run. World-building reused the suite's setup
helpers (`_PG`, `_evidence_world`, `_absent_gap_use`, `_hold_and_rebase`, `_run`). Every check is the referee's own.

## Verdict: ACCEPTED WITH FIXES

**On the unmutated code, nothing measured breaks a guard the builder claims.**
- Every token check refused `NULL`, `''`, `' '`, `'\t'`, 64 zeros, the upper-cased own token and another
  workstream's token.
- The bypass hunt on `litkb` found no path round the token: no view, sequence, rule, TRUNCATE or column grant, and
  no token-less definer function.
- Every race held its invariant.

**The guards are weaker than "every guard fires" claims:**
- **12 of the 15 referee mutations survived the whole test file (116 passed each time).** Three of those (Z11,
  Z13, Z14) are harmless because a second lock still refuses. **Nine survived and opened a real path.**
- The catalog-driven guard, whose stated purpose is to catch *future* direct writes, misses three shapes:
  auto-updatable views, tables that carry `workstream_id` without a foreign key, and tables two hops away.
  Through one of them (Z8), a writer with no token inserted a forged version into another workstream's use chain.
- One design gap exists on the unmutated code (F-2): `abandon_workstream` lacks the "no prepared promotion" guard,
  and it strands a chain Kam has merged.

The guards that exist hold. Two paths on the unmutated code have no guard at all: F-2 above, and F-7, where two
sessions opening in one directory leave an orphan workstream. None of this needs to block P2 data entry. Fix F-1
before P2's first migration adds a table or view. Fix F-2 before the first real prepare → merge → commit cycle.

Not independently mutated this round:
- a column-level grant on a workstream-bearing table (the builder's W12 covers it; Z9 is column-level on an
  extraction table);
- a grant through role membership (analytic only, F-1(d));
- the 0009 trim constraint (referee 2's X7 and the builder's E4a–E4e stand).

## Defects

| ID | Sev | What | Evidence (measured) | Fix |
|---|---|---|---|---|
| F-1 | Med | **The catalog guard `test_no_agent_role_holds_a_direct_write_on_a_workstream_table` misses three shapes.** (a) Its relation set comes only from `contype='f'` constraints, so it never includes views. An auto-updatable view runs with its owner's rights, so INSERT on the view is a direct write that skips the token. (b) It misses a table with a `workstream_id` column but no foreign key. (c) It misses a table two foreign-key hops away (for example, a child of `use_evidence`). (d) Role membership, analytic, not mutated (roles are cluster-wide): `has_table_privilege` follows INHERIT memberships only. A role granted to an agent `WITH INHERIT FALSE, SET TRUE`, or any grantee outside the `litkb%` name filter, would not be seen, and the agent could `SET ROLE` to it. | Z8: suite 116 passed. On the mutated `litkb_test`, a writer ran `INSERT INTO litkb.use_versions_inbox (...)` naming another session's `use_id`, `version_no+1` and `workstream_id`, **with no token**: `ok`, 1 forged row. Z6 (`ws_notes`, `workstream_id` column, no FK): passed, and the writer's INSERT succeeded. Z7 (`evidence_notes REFERENCES use_evidence`): passed, and the INSERT succeeded. Today on `litkb`, all 11 views have `is_insertable_into = NO`, there are 0 rules and 0 sequences, and `pg_auth_members` shows only `litkb_test` → reader/writer/promoter/ingest (inherit f, set t). | Take every relkind (`r`, `p`, `v`, `m`, `f`) into the relation set, and fail on any agent INSERT/UPDATE/DELETE on a view. Build the set as the transitive foreign-key closure from `workstreams`, plus every table with a `workstream_id` column. Also flag roles for which `pg_has_role(agent, g, 'SET')` is true, and every grantee that is not the owner or a superuser, whatever its name. One mutation per branch (Z6, Z7, Z8) |
| F-2 | Med | **`abandon_workstream` accepts a workstream with a prepared promotion.** The prepared report is already on the branch Kam reviews. Once the session abandons its workstream, `promote_commit` is refused, rebase is refused because the source is not `merged`, and the only exit is `promote_abandon`. That puts the versions back to `proposed` inside an abandoned workstream. A fresh workstream could not continue the entity: its first write hit the base rule. This is the D-2 stranding by another door. It predates 0010, which kept the missing guard when it re-created the function with the token. `add_evidence` and `promote_rebase` both have this guard. | P3 (sequential): prepare → uv `prepared`; abandon with own token `ok`; `promote_commit` → `55000 workstream … is not open`; `promote_rebase` → `22023 … is not merged`; `promote_abandon` `ok` → uv `proposed`, 1 head left in the abandoned ws; `write_proposal` on that use in a fresh ws → `23514 use_versions_base_rule`. R5 (prepare held open → abandon): abandon blocked, then `ok`; ws `abandoned`, promotion `prepared`, commit → `55000`. The lock serialises the two calls, but nothing in `abandon_workstream` refuses the prepared state | In `abandon_workstream`, after the token check, lock the workstream row `FOR UPDATE` and refuse `55000` while `promotions.state = 'prepared'`. Add a test (sequential, plus the R5 ordering) and a mutation |
| F-3 | Low-Med | **The open item: `add_use_embedding` checks neither the version's state nor that the workstream is open.** A session holding its own token can write an unreviewed vector onto main's current promoted version, also after its workstream is merged or abandoned. `use_embeddings` has primary key `(use_version_id, model)`, and no agent role holds UPDATE or DELETE on it. The first vector written under a model name therefore occupies that slot on main, and the indexer's later write fails. It changes no version-set hash, pointer or promotion. | P2/P2b: the token of an abandoned ws and of a merged ws, `add_use_embedding` → `ok`, and the embedding sat on the uv that `uses.current_version_id` points to. P4: embedding on a `prepared` uv `ok`, then commit `committed 1` (unaffected). An owner INSERT with the same model on the promoted uv → `23505 use_embeddings_pkey`. An embedding on a `rebased` original, using the merged source's token → `ok`. R4 (commit held open → add_use_embedding): not blocked, `ok`, landed on the version as it became `promoted` | Mirror `add_evidence`: lock the workstream `FOR SHARE`, require `open`, and require `state = 'proposed'`. Or remove the function from the writer, since embedding is index-stage work (§8) and could belong to ingest. Add a test and a mutation |
| F-4 | Low | **Token-value guards with no test.** The suite checks `NULL` and another workstream's token only. | Z1 (token := sha256 of the slug, readable by every role): suite passed; a second writer session computed the token from the slug and `add_candidate` → `ok`. Z2 (`''` accepted): suite passed; `add_candidate(ws, '')` → `ok`. Unmutated: all rejected (P1) | Add `''` and the upper-cased own token to `test_every_workstream_write_requires_its_token`. Add a test that re-opens the same slug after abandoning it (the unique index is partial) and asserts a different token, and that the token is not the sha256 or md5 of the slug or id |
| F-5 | Low | **No role × privilege matrix for extraction tables or for functions.** The catalog guard excludes extraction tables, and the ingest tests are hand lists. | Z9 (writer `UPDATE (text)` on `blocks`): suite passed; on the mutated DB the writer rewrote a block's text and `add_evidence` of that text stored `verified=True`. This is the block-forgery path that 0010 closed for INSERT only. Z10 (ingest EXECUTE on `add_candidate`, `add_use_embedding`): suite passed; ingest with a writer's token → `ok` | Add one catalog test that compares table, column and function privileges per role with the §4.7 table (ingest: INSERT on 11 tables and EXECUTE on `set_current_run` / `norm_identifier`, nothing more; writer: the 8 functions, no write on any table) |
| F-6 | Low | **E-5's copy is not tested against a superseded run.** The suite's evidence world has one run, so a rebase that drops head evidence whose run is no longer current passes. | Z12 (filter `e.run_id = ff.current_run_id`): suite passed; `evidence_copied` 0. Unmutated reference P6: 1 | A rebase test in which the file's current run moved after the evidence was added (copy count 1, run_id = source) |
| F-7 | Low | **`litkb.workstream.open_workstream` races with itself.** It checks `path.exists()`, then opens in the database with autocommit, then creates the file with `O_EXCL`. A second caller that passed `exists()` makes a database workstream whose token lands in no file, so no session can write or abandon it. A failed file write leaves the same orphan. | P5: two threads, one directory, ×10 → every round `['FileExistsError', 'ok']`, **10 orphan open workstreams**, 1 file per round | Create the file with `O_EXCL` first. Then open the workstream inside a transaction, write the token, and commit. On failure, roll back and unlink |
| F-8 | Info | The token is secret only while clients bind it as a parameter. Another `litkb_writer` login reads a same-role session's `pg_stat_activity.query`. | P7b on `litkb`, read-only, with a dummy marker (not a token): inlined literal visible = True; bound parameter visible = False. (On `litkb_test` nothing was visible, so P7 is inconclusive by construction. There, after `SET ROLE` the viewer's current_user is `litkb_writer`, but the watched session's backend user is `litkb_test`, and pg_stat_activity shows query text only to a role that has that role's privileges) | State it in §5 and in the future CLI and MCP: always pass the token as a bound parameter; never as a psql literal |
| F-9 | Info | The shared pgpass file holds `postgres` and `litkb_owner` lines, and `connect()` refuses neither. Both logins are strictly stronger than the promoter and ingest logins that got their own passfiles. This is consistent with Kam's accepted-risk decision, but the "own passfile + refusal" convention is uneven. | This session ran `psql -w -U postgres` with no password prompt (the probes). Line count from referee 2 (5 lines); the file was not read this round | Kam's call. Either move owner (and `postgres` use) to the same pattern, or record that the convention covers only the two tool logins |

## Referee mutations (whole `qc/test_litkb_p1.py`, `litkb_test` only)

Each row is one exact string replacement in the file named, applied as bytes and restored as bytes. After each
restore, the sha256 matched the pre-mutation bytes. The post-probe ran on the mutated `litkb_test` before the next
session reset. Before any mutation, a fingerprint was taken of 22 files: the 11 migrations, `connect.py`,
`migrate.py`, `provision.py`, `promote.py`, `ingest.py`, `workstream.py`, `__init__.py` ×2, the test file, the
harness and `.gitignore`. After all runs, `sha256sum -c` gave **22 OK**, and `git status --short` was clean.

| ID | File: `old` → `new` | Whole file | Post-probe on mutated DB |
|---|---|---|---|
| Z1 | 0010: `token := replace(gen_random_uuid()::text \|\| gen_random_uuid()::text, '-', '');` → `token := encode(sha256(convert_to(p_slug, 'UTF8')), 'hex');` | DID NOT FIRE (116 passed) | token guessed from slug accepted |
| Z2 | 0010: `IF NOT coalesce(v_ok, false) THEN` → `IF coalesce(p_token, 'x') <> '' AND NOT coalesce(v_ok, false) THEN` | DID NOT FIRE | `''` accepted |
| Z3 | 0010: `FROM workstream_tokens t WHERE t.workstream_id = p_ws);` → `… WHERE t.token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex') LIMIT 1);` (control) | **FIRED** (8 failed) | n/a |
| Z4 | 0010: `WHERE w.id = p_workstream AND w.state = 'open';` → `WHERE w.id = p_workstream;` | **FIRED** (1 failed: `test_held_chain_is_rebased_and_promotes`) | abandoning a merged ws also hits the `workstreams_merged_iff_commit` CHECK (a second lock) |
| Z5 | 0011: before `-- end of 0011` add `CREATE VIEW litkb.workstream_token_hashes AS SELECT * FROM litkb.workstream_tokens; GRANT SELECT … TO litkb_reader, litkb_writer;` | DID NOT FIRE | writer reads the hashes (brute force infeasible for 244-bit tokens; matters with Z1) |
| Z6 | 0011: add `CREATE TABLE litkb.ws_notes (id uuid PRIMARY KEY DEFAULT uuidv7(), workstream_id uuid NOT NULL, note text); GRANT INSERT ON litkb.ws_notes TO litkb_writer;` | DID NOT FIRE | writer INSERT `ok` |
| Z7 | 0011: add `CREATE TABLE litkb.evidence_notes (id uuid PRIMARY KEY DEFAULT uuidv7(), evidence_id uuid REFERENCES litkb.use_evidence (id), note text); GRANT INSERT … TO litkb_writer;` | DID NOT FIRE | writer INSERT `ok` |
| Z8 | 0011: add `CREATE VIEW litkb.use_versions_inbox AS SELECT * FROM litkb.use_versions; GRANT INSERT ON litkb.use_versions_inbox TO litkb_writer;` | DID NOT FIRE | **forged version in another ws's chain with no token: `ok`, 1 row** |
| Z9 | 0011: add `GRANT UPDATE (text) ON litkb.blocks TO litkb_writer;` | DID NOT FIRE | block text rewritten, forged quote `verified=True` |
| Z10 | 0011: add `GRANT EXECUTE ON FUNCTION litkb.add_candidate(…), litkb.add_use_embedding(…) TO litkb_ingest;` | DID NOT FIRE | ingest `add_candidate` with a writer token `ok` |
| Z11 | 0010: `REVOKE EXECUTE ON FUNCTION litkb._require_ws_token(uuid, text) FROM PUBLIC;` → `GRANT … TO PUBLIC;` | DID NOT FIRE | harmless: the function is not SECURITY DEFINER, so reader → `42501 permission denied for table workstream_tokens` |
| Z12 | 0010: `FROM use_evidence e WHERE e.use_version_id = c.head ORDER BY e.id;` → join `blocks`/`files`, add `AND e.run_id = ff.current_run_id` | DID NOT FIRE | `evidence_copied` 0 (unmutated: 1) |
| Z13 | connect.py: `_NAME = re.compile(r"[a-z_][a-z0-9_]*")` → `r"\s*[a-z_][a-z0-9_]*\s*"` | DID NOT FIRE | harmless: the post-parse strip refuses `' litkb_promoter'`, `'litkb_ingest '` and `'litkb_ingest\t'` |
| Z14 | connect.py: `if parsed in TOOL_LOGINS:` → `if parsed == PROMOTER:` | DID NOT FIRE | harmless: the identifier check refuses first (each lock covers the other) |
| Z15 | connect.py: `for what, value in (("user", user), ("dbname", dbname)):` → `(("user", user),)` | **FIRED** (`injection_through_dbname`) | the driver was reached, but the value is quoted by `make_conninfo` |

Caught: Z3, Z4, Z15. Survived and harmless because of a second lock: Z11, Z13, Z14. Survived and a real gap: Z1, Z2,
Z5 to Z10, Z12 (F-1, F-4, F-5, F-6).

## Bypass hunt on `litkb` (as postgres, `default_transaction_read_only = on`)

- **Write rights:** table-level INSERT/UPDATE/DELETE/TRUNCATE/TRIGGER/REFERENCES/MAINTAIN, across every relkind
  in `litkb`, `litkb_meta` and `public`, for reader, writer, promoter, ingest, test and PUBLIC. The only rights
  found are ingest's INSERT on the 11 extraction tables. Column-level INSERT/UPDATE: the same 11 tables, ingest only.
- **Views, sequences, rules:** all 11 views have `is_updatable = NO` and `is_insertable_into = NO`. No view
  references `workstream_tokens`. There are 0 rules other than `_RETURN` and 0 sequences.
- **`workstream_tokens`:** `relacl = {litkb_owner=arwdDxtm/litkb_owner}`. Table and column SELECT is f for all
  five agent roles and PUBLIC.
- **Functions:** all 23 functions in `litkb` are owned by `litkb_owner`. All 14 SECURITY DEFINER functions pin
  `search_path=litkb, public, pg_temp`. Only `_feeds_token_ok` and `norm_identifier` are unpinned, and both are
  non-definer (as referees 1 and 2 found).
  - Writer EXECUTE: `open_workstream`, `norm_identifier`, and the 7 token-taking functions. Every one of the 7
    contains `_require_ws_token`.
  - Ingest EXECUTE: `set_current_run` and `norm_identifier`.
  - Promoter EXECUTE: the four `promote_*` functions and `norm_identifier`.
  - PUBLIC and `litkb_test`: nothing. No SECURITY DEFINER function exists in `public`.
- **Dropped signatures:** `to_regprocedure` returns NULL for the old token-less `abandon_workstream(uuid)`,
  `write_fact(8 args)`, `write_proposal(9)` and `add_evidence(9)`. Each of the 8 token names has exactly one
  signature.
- **Schema and database rights:** no agent role has CREATE on `litkb`, `litkb_meta` or `public`. On `litkb`, TEMP
  and CREATE are f for every agent role, so no temp-table shadowing is possible. `litkb_test` CONNECT on `litkb` is f.
- **Memberships:** no agent role is a member of `pg_write_all_data`, `pg_read_all_data`, `pg_*_server_files`,
  `pg_execute_server_program`, `pg_read_all_stats` or another litkb role. COPY FROM needs INSERT, which no agent
  role holds on a workstream table, and COPY TO/FROM a file or program needs those predefined roles.
- **Other:** 0 event triggers, 0 RLS tables and 0 large objects. `pg_hba` uses scram-sha-256 on every line.
  `litkb` has 11 migrations recorded and 0 workstreams.
- **Server settings:** `log_statement = none`, `log_min_duration_statement = -1`,
  `log_parameter_max_length_on_error = 0`, no preload libraries. A bound token is therefore not logged; this is
  inferred from the settings, and the log file was not read.

## Concurrency (unmutated, `litkb_test`, separate connections, real threads)

| Race | Result | Invariant |
|---|---|---|
| R1 abandon held open → `add_evidence` | blocked, `22023 not open`, 0 rows | holds |
| R2 abandon held open → `write_proposal` (new gap) | blocked, `22023`, 0 heads | holds |
| R3 abandon held open → `add_candidate` | **not blocked**, `ok`, ws `abandoned` | as designed (judgement call 3); the 0011 functions take no workstream lock |
| R4 `promote_commit` held open → `add_use_embedding` | **not blocked**, `ok`, the embedding sits on the now-`promoted` uv | F-3 |
| R5 `promote_prepare` held open → abandon | blocked, then `ok`; ws `abandoned`, promotion `prepared`, commit `55000` | **F-2** |
| R6 abandon of the rebase target held open → `promote_rebase` | blocked, `22023 target not open`; 1 source head left | holds |
| R7 barrier ×20: `open_workstream`, same slug, two writers | 20/20: one `ok` and one `23505`, 1 workstream, 1 token row | holds |
| R8 barrier ×20: abandon vs `add_evidence` | 13× (ok, ok, 1 row), 7× (ok, 22023, 0 rows); 0 cases where the reported success and the rows disagree | holds |
| P5 `litkb.workstream.open_workstream` ×10, two threads, one directory | 10/10 orphan workstreams | **F-7** |

## `add_use_embedding` severity (the builder's open item)

**Low-Med, fix before P2 writes embeddings.** Measured: it accepts a prepared, promoted or rebased version, and the
token of a merged or abandoned workstream, and it does not wait for a commit in flight. What it cannot do: change a
pointer, the version-set hash or a promotion, or write without that workstream's own token. What it can do: put an
unreviewed vector on main's current version, and occupy the `(use_version_id, model)` primary key there, so that
the indexer's correct vector is refused with `23505` and only the owner can repair it. The harm is to retrieval,
not to recorded knowledge. It becomes real as soon as P2 or later has a writer path that embeds. The fix and test
are in F-3.

## Secrets

- `git log -p 69c08d8..72825b2`: 3,094 lines, grepped.
  - Added lines shaped like a real pgpass entry (`localhost:5433:<db>:<user>:<value>` with a non-placeholder value): 0.
  - 64-hex literals: 0. `token_urlsafe`, `PGPASSWORD`, `passwd`: 0.
  - `password`: 2 hits, both report prose. `pgpass`: 16 hits, all paths, docstrings or the test's fake
    `passfile=promoter.pgpass`. The only 4-field form is the report's `localhost:5433:litkb:litkb_ingest`, which
    has no password field.
- `git ls-files` shows no `.litkb-workstream`, pgpass, `.env` or `secrets/` path, and
  `git log --all --name-only` shows none ever committed.
- `git check-ignore -v --no-index` matches `.gitignore:136:.litkb-workstream` at the root, `Scripts/`,
  `Scripts/pipeline/litkb/` and `Reports/`. No `.litkb-workstream` file exists in either worktree.
- No passfile, password or token was printed. Probe output names workstream ids only.

## Tests

From `Scripts/`: `PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 -m pytest qc/test_litkb_p1.py -q -p no:cacheprovider`
gave `116 passed in 24.95s; litkb Postgres tests: 102 passed` before the mutations, and `116 passed in 24.25s`
(102 Postgres) on the restored tree after them. That last run also reset `litkb_test` to the real schema.

## Measured vs not

**Measured:** every row above cites a run or probe from this session.

**Inferred:**
- F-1(d), the membership gap, from `has_table_privilege`'s documented INHERIT semantics. It was not mutated,
  because role grants are cluster-wide and would touch `litkb`'s roles.
- The log-safety note, from server settings.
- The severity rankings.

**Not done:**
- The builder's harness rows were not re-run.
- Nothing was written to `litkb` except the read-only probes: `default_transaction_read_only`, one writer-pair
  `pg_sleep` probe.
- No role or grant was changed; the pgpass files and the server log were not read.

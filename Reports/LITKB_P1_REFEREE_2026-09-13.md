# litkb P1 "Foundation" — independent referee, 2026-09-13

Subject: branch `work/20260913-literature-kb` at `4648a3d`; builder report
`Reports/LITKB_P1_REPORT_2026-09-13.md`; design `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §4, §5, §9,
§14 P1; decision `litkb-p0-foundation`. Referee is not the author (CLAUDE.md 3.4c). The builder's
mutation harness was read, not re-used as evidence; every result below comes from referee-written
scripts run against `litkb_test` only (plus read-only catalog probes on `litkb`).

## Verdict: PASS WITH FIXES

Every §14 P1 kill has a test, and the ones the referee mutated fired. Two same-base writers under real
concurrency were refused correctly in 90/90 rounds, and so were two promoters (10/10). Nothing below
corrupts main's pointers. But one race silently strands a write (D-1). Held chains can never be
recovered (D-2). The git rule is not where decision §15.7 says it is (D-3). A writer can disrupt other
workstreams' promotions (D-5). And four correct guards have no test that would notice their removal
(D-4, D-6). D-1 through D-5 should be settled before P2 writes real data.

## Defects

| ID | Sev | What | Evidence (measured) | Fix |
|---|---|---|---|---|
| D-1 | Med | **A write concurrent with `promote_commit` lands in the merged workstream and is stranded, with success returned.** `_write_version` checks `workstreams.state = 'open'` without a lock, so a writer that passed the check before the commit waits on the row lock, then inserts after the workstream is `merged`. Its version can never be prepared or promoted, and nobody is told. | race C4: promoter tx holds `promote_commit`; writer `write_proposal` on the chain's entity waits on a lock (observed in `pg_stat_activity`), promoter commits → writer `ok`, ws `merged`, 1 head left in ws. C4b (new gap): same. A *sequential* write to the merged ws is refused (22023), so no existing test can see this | `_write_version`: `PERFORM 1 FROM workstreams WHERE id = p_workstream AND state = 'open' FOR SHARE` (conflicts with commit's `FOR UPDATE`; re-checked on the new row after the wait). Add a two-connection test |
| D-2 | Med | **A chain held at commit is unrecoverable.** Its versions stay `prepared` with the committed promotion's id, and the workstream is `merged`. Every exit is refused. That is the normal outcome whenever two workstreams touch one gap (the M6a scenario), and the merged git report then describes a chain that is not in main. | H1 (loser of race C5): version state `prepared`; `promote_prepare` → 22023; `promote_abandon` → 55000; `write_proposal` on held head → 22023; `abandon_workstream` → 22023 | A rebase path: release held versions (state back to `proposed` / `rejected` with a reason) and let a new workstream re-propose on current main; or allow prepare on a merged ws's residual chains. Kam's call before P2 (the builder filed this as "P8 or Kam") |
| D-3 | Med | **Decision mismatch.** `litkb-p0-foundation` §15.7: "*the database* refuses a commit that is not reachable from main". The DB accepts any 40-hex string; the check lives only in `litkb/promote.py`. The §14 kill ("`promote commit` … is refused") is met by the CLI, but the decision text is not met. | D4: as `litkb_promoter` in `litkb_test`, `SELECT litkb.promote_commit(pid, 'deadbeef'×5)` → committed 1 | Kam either amends §15.7 to "the promote CLI refuses", or accepts a compensating control (e.g. promoter credential held only by the orchestrator, `promote_commit` recording the verifying host/sha for audit) |
| D-4 | Med | **Admitter ≠ approver test cannot tell the constraint's clauses apart.** It tests only (same agent, same session). Also, the `AND` form refuses a *different session* of the *same agent name* — if every agent records as one name, no manual admission can ever be approved; §15.13 says "a second agent session". | R1 (session clause deleted) and R1b (`AND`→`OR`): **did not fire**, 23 passed | Tests for (same agent, other session) and (other agent, same session); Kam/P2 decide whether session alone suffices |
| D-5 | Med | **Writer can disrupt promotions it does not own.** Evidence INSERT and `set_current_run` have no workstream or state check. The referee confirmed three ways in: (a) evidence added to another ws's prepared use version blocks that commit; (b) evidence added to a *promoted* main version enters main with no review; (c) a writer can insert a `failed` run and make it any file's current run, which un-promotes all evidence on that file. Integrity holds (the hash guard fires), but availability and review do not. | D1: insert `ok`; that ws's commit → 40001 "version set … changed". D2: insert `ok`, 1 unreviewed evidence row on main's current version. D5: `set_current_run` `ok`, promotable evidence 1 → 0 | Evidence only via a SECURITY DEFINER function that requires the use version to be `proposed` in the caller's workstream; `set_current_run` refuses `status <> 'ok'` runs and is limited to the ingest path |
| D-6 | Low | **Guards that are correct but untested** (mutation survives the whole file): writer INSERT on version `state`; the base check on a proposal's *first* head in a workstream (the kill covers only the existing-head path); quote offsets (verification by "quote anywhere in block" passes); a use whose gap is in neither main nor this promotion. | R2, R4, R6, R7: **did not fire**, 23 passed each | One test per guard, each shown to fire on the same mutation |
| D-7 | Low | `char_end` beyond the block text still verifies (substring truncates). | D3: `char_start=0, char_end=1000000`, full-text quote → `quote_verified = true` | Trigger: `AND NEW.char_end <= length(b.text)` |
| D-8 | Low | The identity-row `FOR UPDATE` in `_write_version` is load-bearing for the *error class*, and no test pins it. Without it the loser is still refused, but with 23505 (version_no unique) instead of the retryable 40001 the design promises. The sequential kill tests cannot see this. | R9 (lock removed) + race: C1/C2/C3 30/30 each `UniqueViolation:23505`; C5 unchanged | Keep the two-connection race as a test asserting SQLSTATE 40001 |
| D-9 | Low | Test-role confinement is narrower than §9's text "CONNECT to `litkb_test` and nothing else": `litkb_test` can CONNECT to `postgres`, `postgis_36_sample`, `template1` (PUBLIC grants; builder call 5). It still cannot reach `litkb`. | probe: `has_database_privilege('litkb_test', …, 'CONNECT')` = t for those three | Amend §9 wording, or revoke PUBLIC CONNECT on those DBs (touches non-litkb DBs → Kam) |
| D-10 | Info | R8 (search_path pin removed from `write_proposal`) "fired" only because the unqualified `_write_version` call stopped resolving. Nothing tests the pin itself. No bypass exists today (see below). | R8: 7 failed, all "function does not exist"-type breakage | Catalog test: every `prosecdef` function in `litkb` has a `search_path` in `proconfig`; no agent role has CREATE on any schema in that path |

## Coverage: §14 P1 kills → tests

| Kill | Test | Referee assessment |
|---|---|---|
| writer UPDATE on a version table refused | `test_kill_writer_cannot_update_or_delete_version_rows` ×5 tables | Adequate. Catalog probe on `litkb`: writer has no UPDATE/DELETE/TRUNCATE/TRIGGER on any litkb table |
| second writer, same base — fact | `test_kill_fact_second_writer_on_same_base_is_refused` | Sequential only. Confirmed under concurrency (C1, C1d). R5 fired |
| … — proposal | `test_kill_proposal_second_writer_on_same_base_is_refused` | Sequential, existing-head path only (R4 untested). Concurrency confirmed for both paths (C2, C3) |
| client `quote_verified = true` stored false | `test_kill_client_quote_verified_is_overwritten` + `test_writer_cannot_name_quote_verified` | Offsets untested (R6, D-7). R3 fired |
| `litkb_test` → `litkb` refused by server | `test_kill_test_role_is_refused_by_the_server_on_litkb` | Adequate. Asserts the server message; pg_hba is `scram-sha-256` for all rows (not `trust`), so the password is really checked. See D-9 |
| promote commit, merge not on main | `test_kill_promote_commit_refuses_merge_not_on_main` | Python layer only (D-3) |
| conflicting gap chain + dependent not promoted | `…_holds_its_dependent_at_commit` / `…_at_prepare` | Depth-one gap→use conflict only. The absent-gap branch is untested (R7). Held chains then unrecoverable (D-2) |

## Referee mutations (all restored; sha256 of every edited file matched the pre-mutation fingerprint)

| ID | Mutation | Result |
|---|---|---|
| R1 | admissions CHECK: drop `approver_session <> admitter_session` | DID NOT FIRE |
| R1b | admissions CHECK: agent/session clauses `AND` → `OR` | DID NOT FIRE |
| R2 | 0006: writer gets INSERT on version `state` | DID NOT FIRE |
| R3 | 0006: writer gets INSERT on `quote_verified` | FIRED (`test_writer_cannot_name_quote_verified`) |
| R4 | 0003: drop `WHERE p_based_on IS NOT DISTINCT FROM v_main` on first ws_heads insert | DID NOT FIRE |
| R5 | 0003: fact CAS compares against the locked read `v_main`, not the client base | FIRED (fact kill) |
| R6 | 0003: `quote_verified := position(quote IN text) > 0` | DID NOT FIRE |
| R7 | 0005: drop "gap neither promoted nor in this promotion" problem | DID NOT FIRE |
| R8 | 0003: drop pinned `search_path` from `write_proposal` | FIRED by breakage only (D-10) |
| R9 | 0003: drop identity-row `FOR UPDATE` (judged by the race script) | loser refused with 23505, not 40001 (D-8) |

Final suite on the restored tree: `23 passed in 5.72s; litkb Postgres tests: 21 passed`. `git status` clean
before the report was written.

## Concurrency (two+ separate connections, `threading.Barrier`, `litkb_test`)

- C1 fact `write_fact` same base, ×30: exactly one `ok` + one 40001, pointer = winner, 2 versions — 30/30.
- C1d deterministic: A's tx open; B observed waiting on `Lock`; A commits → B 40001; pointer = A.
- C2 proposal, existing head, ×30 and C3 proposal, first head in ws, ×30: one `ok` + one 40001, head = winner — 60/60.
- C5 two promoters, two workstreams, one gap base, ×10: one chain committed, other held — 10/10.
- C4/C4b writer vs promote_commit: **defect D-1**.

## Bypass paths (read-only probes on `litkb` as postgres, `default_transaction_read_only`)

- All 9 SECURITY DEFINER functions are owned by `litkb_owner`, each with `search_path=litkb, public, pg_temp`.
  The non-definer helpers are EXECUTE-owner-only, except `norm_identifier`. `_feeds_token_ok` and
  `norm_identifier` have no pinned path, but they call only pg_catalog objects, which are searched first.
- No CREATE for reader/writer/promoter/test on `litkb`, `public` or `litkb_meta` → no search-path hijack.
- Writer: no EXECUTE on `_write_version`, `_create_identity`, `_refresh_mirrors`, `_ws_chains`, `promote_*`;
  no INSERT/UPDATE on `works`/`gaps`/`uses`/`files`/`identifiers` (pointers), `ws_heads`, `promotions`,
  `workstreams`; no column INSERT on `state`/`promoted_at`/`promotion_id`/`quote_verified`/approver fields.
  Promoter: no UPDATE on pointers, no INSERT on `ws_heads`.
- Writer *does* hold column INSERT on `gap_versions`/`use_versions` `based_on_version_id` and `workstream_id`
  (builder call 8). Such rows are unreachable from any head, so chains are unaffected; they feed D-5-style noise.
- `dblink`/`postgres_fdw` not installed. Default ACL for `litkb_owner` revokes function EXECUTE from PUBLIC.

## Secrets and hygiene

- `git log -p 428e194^..4648a3d` (2,687 lines) grepped for `password|passwd|pgpass|secret|token_urlsafe|PGPASSWORD|localhost:5433:`:
  hits are doc text and code identifiers only. There is no password literal and no pgpass content. The
  43-character token-shaped matches are test function names.
- `git log --all --name-only`: no `.env`, `pgpass` or `secrets/` path ever committed. `.gitignore` covers `.env`
  and `.litkb-workstream`. `D:\edmonds-pipeline\secrets` is outside the repository.
- Server `log_statement = none`; provision also sets `log_min_error_statement = panic` for its session. The
  server log files themselves were **not** inspected.

## Builder judgement calls

1. **Git reachability in Python only.** This is acceptable for the §14 kill, but it contradicts the recorded
   §15.7 wording (D-3). Kam must see it as a decision change, not a footnote.
2. **Held-at-commit chain never re-promotable.** This is not a P8 nicety. It is the default outcome of any
   concurrent edit to one gap, and the stuck versions cannot even be withdrawn (D-2).
3. **pgpass `*` database for `litkb_test`.** Sound: it makes the M4 refusal come from the server's CONNECT
   check, and it cannot produce a false pass (without it the test would fail on "no password", not pass).
   The side effect is that the role authenticates to the three PUBLIC-connect databases (D-9).
4. Others (SET ROLE isolation with INHERIT FALSE, `litkb_test` owning its DB, `write_fact` refusing creation)
   were checked in the catalog and hold as described.

## Measured vs not

Measured: every row above cites a run or probe from this session. Inferred: the D-1 mechanism (the lock
ordering explanation) follows from the observed outcome plus the READ COMMITTED semantics. Not done: the
builder's M1–M7 were not re-run; the server log was not read; `litkb` was not mutated.

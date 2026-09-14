# litkb P1 — second independent referee (after 0007 fixes and 0008 Kam decisions), 2026-09-13

Subject: branch `work/20260913-literature-kb` at `1cb9f00`. Prior referee: `Reports/LITKB_P1_REFEREE_2026-09-13.md`
(D-1 to D-10). Builder claims: `Reports/LITKB_P1_REPORT_2026-09-13.md` "Fixes after referee" and "Kam's decisions
implemented" (37/37 mutations fire). Authority for D-2/D-3/D-4/D-9: `Scripts/decisions.yaml` `litkb-p0-foundation`,
"After the P1 referee". The referee is not the author (CLAUDE.md 3.4c). The builder's harness was read and not
reused as evidence. Every result below comes from scripts the referee wrote, run against `litkb_test`, plus
read-only probes on `litkb`. Those scripts were kept in the session scratchpad and not committed. The mutation
strings are quoted exactly below, so each row can be rerun.

## Verdict: ACCEPTED WITH FIXES

The 37 builder mutations fire as claimed, but that is not the same as the new guards being covered. **All 9
referee mutations survived the whole test file (59 passed each time).** All 9 were then caught by referee
two-connection races or probes. X4 was caught only after its probe was fixed to build a fresh world per case.
Four of them are locks, and the suite cannot see a lock because every new test is sequential or holds a whole
function open.

Nothing measured corrupts main without detection when the code is unmutated. Every race on the real code held
its invariant. The fixes that matter are tests. The one schema fix is a hole in the D-4 constraint.

## Defects

| ID | Sev | What | Evidence (measured) | Fix |
|---|---|---|---|---|
| E-1 | Med | **The D-1 fix depends on `promote_commit`'s `FOR UPDATE` on the workstream row (0005), and no test pins it.** The builder's D-1 test holds the *whole* commit open, so its final `UPDATE workstreams` already blocks the writer. If commit's early lock is removed, a writer that took its `FOR SHARE` first finishes, and the commit then promotes and marks the workstream `merged` over the new head. That is the original D-1 stranding. | X9 (drop that `FOR UPDATE`): suite 59 passed. Race e2 (writer's write held open → commit starts → writer commits): `commit=ok ws=merged heads left=1`, STRANDED. Unmutated e2: commit blocked, `40001`, ws `open` | Add the e2 ordering as a test, asserting commit `40001` and ws `open` |
| E-2 | Med | **`promote_rebase`'s two row locks are untested.** (a) Source `FOR UPDATE` removed: two concurrent rebases of one merged workstream **both succeed**, so every held chain gets two proposed copies in two workstreams. (b) Identity-row `FOR UPDATE` removed: a rebase running while another workstream's commit moves main passes the onto-CAS against the pre-commit pointer. The D-2 kill "rebase onto stale main is refused" is then bypassed under concurrency. The copy is still held later at prepare, so the damage is detected, not silent. | X2: suite passed; race b1 `second=ok rebases rows=4 heads in second target=2`; barrier b2 `(ok, ok) rebases=4` 10/10. Unmutated b1/b2: second `22023` 11/11, `rebases=2`. X3: suite passed; race a1 `rebase blocked=False rebase=ok rebased-copy=based_on=g2b(stale)`. Unmutated a1: blocked, `40001`, no copy | Two-connection tests b1 and a1 |
| E-3 | Low-Med | **The rebase guard "onto names exactly the held chains" is untested.** Without it, a chain left out of `onto` whose main pointer is NULL (a use created in that workstream) is rebased without being reviewed, and an `onto` that names an unheld chain is accepted. | X4: suite passed; probe (fresh world) `onto omits the held use chain → ACCEPTED rebased=2 chains=[gap, use]`; extra key `ACCEPTED`. Unmutated: both `22023` | Test with one missing key and one extra key |
| E-4 | Low-Med | **D-4 constraint: the approver session may be empty or blank.** `admitter_session` has `CHECK (<> '')`; `approver_session` has none. `''` and `'   '` pass `approver_session <> admitter_session`, and so do `'SESSA'` and `'sessA '` against `sessA`. `approver_agent = ''` also passes. The `IS NOT NULL` clause is load-bearing (`NULL <> x` is NULL, so CHECK passes) and untested. | Probe, unmutated: `''` ACCEPTED, `'   '` ACCEPTED, agent `''` ACCEPTED, `SESSA` ACCEPTED, `sessA ` ACCEPTED; NULL session refused 23514. X7 (drop `approver_session IS NOT NULL`): suite passed; NULL session ACCEPTED | `CHECK (btrim(approver_session) <> '' AND btrim(approver_agent) <> '')`; compare `btrim` values; add a NULL-session row and a blank-session row to the parametrized test |
| E-5 | Low | **Rebase evidence copy is under-tested, and its semantics are unstated.** (a) The copied `stance`/`page` are not checked: the only test uses `supports`, page 1. (b) Evidence is copied from *every* chain version onto the new head. A quote the author attached to v1 and dropped by writing v2 is re-attached to the head: a `refutes` row lands on a version that had none. | X6 (`page`→1, `stance`→`'supports'`): suite passed; probe row became `(1, 'supports', …)` where the original was `(7, 'refutes', …)`. X5 (head evidence only): suite passed. Unmutated probe: head v2 had 0 rows; rebased head has 1 `(7, 'refutes', 4, 20, True)` | Assert every copied column, including a `refutes` row. Kam/design: say whether chain-wide copy is intended. `_ws_chains` already treats evidence as chain-level, so it is defensible, but it should be written down |
| E-6 | Low | `add_evidence`'s `FOR SHARE` is untested. Without it, evidence lands while a prepare is in flight and the victim's commit fails `40001`. This is the referee-1 D1 disruption by a race path. An availability issue only, because the hash detects it. | X1: suite passed; race d (prepare held open) `add_evidence blocked=False ok, evidence rows landed=1, victim commit=40001`. Unmutated: blocked, `55000`, 0 rows, victim commit ok | Test d |
| E-7 | Low | `set_current_run`'s compare-and-set (now in 0007) is untested. | X8: suite passed; probe stale expected run ACCEPTED. Unmutated: `40001` | One test with a stale expected run |
| E-8 | Low | **The D-3 `connect()` refusal is a string compare over an unquoted conninfo.** `connect(db, "litkb_writer user=litkb_promoter passfile=<promoter file>")` connects as the promoter, because the later keyword wins. So does `"litkb_promoter "` (trailing space) with `PGPASSFILE` set, and so does `c._open(...)`. The promoter passfile's inherited ACL gives `Authenticated Users:(M)` and `BUILTIN\Users:(RX)`. | Read-only probes on `litkb`, each `SET default_transaction_read_only`: injection → `connected as litkb_promoter`; trailing space + PGPASSFILE → same; `_open` → same; plain `psql` with `PGPASSFILE` → same. `icacls` on the file and the folder | Build conninfo with `psycopg.conninfo.make_conninfo` (quotes values); reject whitespace in role names. Kam's call: tighten the secrets folder ACL. Report states: it stops mistakes, not a same-user process (see D-3 below) |

Info: the brief assumed the writer "cannot reach the `rebases` table". 0008 grants SELECT on it to reader,
writer and promoter by design. Measured on `litkb`: SELECT t for all three; INSERT/UPDATE/DELETE/TRUNCATE/TRIGGER/REFERENCES f.

## Referee mutations

Each mutation was one exact string replacement in a real source file. The whole `qc/test_litkb_p1.py` ran against
it (session reset re-applies migrations from disk), then the targeted race or probe ran. The file was restored,
and the restore was sha256-checked (`restored sha256 match: True` for all 9). A final `sha256sum -c` against a
fingerprint taken before any mutation printed OK for all 12 files (8 migrations, `promote.py`, `connect.py`,
`migrate.py`, the test file). `git status --short` was clean.

| ID | Aim | File: `old` → `new` | Whole suite | Referee check |
|---|---|---|---|---|
| X1 | D-1/D-5 | 0007: `ws.state = 'open' FOR SHARE;` → `ws.state = 'open';` | DID NOT FIRE | FIRED (race d) |
| X2 | D-2 | 0008: `w.id = p_source_ws AND w.state = 'merged' FOR UPDATE;` → without `FOR UPDATE` | DID NOT FIRE | FIRED (b1, b2 10/10) |
| X3 | D-2 | 0008: `'SELECT current_version_id FROM %s WHERE id = $1 FOR UPDATE'` → without `FOR UPDATE` | DID NOT FIRE | FIRED (a1). a2/a3 unchanged |
| X4 | D-2 | 0008: delete the `IF … jsonb_object_keys(p_onto) … IS DISTINCT FROM v_keys … END IF;` block | DID NOT FIRE | FIRED (onto probe, fresh world per case) |
| X5 | D-2 | 0008: `e.use_version_id = ANY (c.version_ids)` → `= c.head` | DID NOT FIRE | FIRED (evcopy: 1 → 0 rows) |
| X6 | D-2 | 0008: copy `e.page, …, e.stance` → `1, …, 'supports'` | DID NOT FIRE | FIRED (evcopy row altered) |
| X7 | D-4 | 0008: drop `approver_session IS NOT NULL AND` | DID NOT FIRE | FIRED (NULL session accepted) |
| X8 | D-5 | 0007: `WHERE f.id = p_file AND f.current_run_id IS NOT DISTINCT FROM p_expected_run;` → `WHERE f.id = p_file;` | DID NOT FIRE | FIRED (stale CAS accepted) |
| X9 | D-1 | 0005 `promote_commit`: `… w.state = 'open' FOR UPDATE;` → without `FOR UPDATE` | DID NOT FIRE | FIRED (e2 STRANDED) |

The builder's 37 were not re-run as evidence. Their targets and tests were read, and each pairs one guard with
one test that is plausibly sensitive to it. The claim "37/37 fire" is not contradicted. The gap is the 9 guards above.

## Concurrency (unmutated, separate connections, `litkb_test`)

"Held open" means the first transaction ran and did not commit. The second was observed waiting through
`pg_blocking_pids`, then the first committed. "Barrier" means both started on a `threading.Barrier`.

| Race | Result | Invariant |
|---|---|---|
| a1 commit (moves gap main) held open → rebase | rebase blocked, `40001`, no copy, main = g3 | holds |
| a2 rebase held open → commit | commit blocked, then `ok`, main = g3; ws3 prepare holds the rebased gap chain as conflict (2 held) | holds (detected, not silent) |
| a3 rebase vs commit, barrier ×12 | 12/12 commit won, rebase `40001`, no copy | holds; ordering biased, a2 covers the other |
| b1 double rebase, first held open | second blocked, `22023` "holds no chain", `rebases` = 2 rows | holds |
| b2 double rebase, barrier ×10 | 10/10 one `ok` + one `22023`, 2 rows | holds |
| c1 writer on target entity held open → rebase | rebase blocked, `22023` "already has a chain"; 1 head, 1 version | holds |
| c1 rebase held open → writer | writer blocked, `40001`; 1 head, 1 version | holds |
| c2 writer vs rebase, barrier ×12 | 12/12 rebase `ok`, writer `40001`, 1 version | holds; biased |
| d add_evidence vs prepare held open | blocked, `55000`, 0 rows; victim commit ok | holds |
| d add_evidence vs commit held open | blocked, `22023`, 0 rows | holds |
| e writer (new entity) vs commit, barrier ×30 | 30/30 writer `ok`, commit `40001`, ws `open` | holds (no stranding); biased |
| e2 writer held open → commit | commit blocked, `40001`, ws `open` | holds |

## Bypass probes on `litkb` (as postgres, `default_transaction_read_only=on`)

- All 19 `litkb` functions are owned by `litkb_owner`. All 11 SECURITY DEFINER functions, including `add_evidence`
  and `promote_rebase`, pin `search_path=litkb, public, pg_temp`. Only `_feeds_token_ok` and `norm_identifier`
  are unpinned; both are non-definer and use only pg_catalog objects.
- EXECUTE on `promote_prepare/commit/abandon/rebase`: reader f, writer f, litkb_test f, promoter t. `add_evidence`:
  writer t, others f. `_write_version`: nobody but the owner.
- No reader/writer/promoter/test role is a member of `litkb_promoter` (`pg_has_role` f). No agent role has CREATE
  on `litkb`, `public` or `litkb_meta`.
- Writer on `use_evidence`: INSERT/UPDATE/DELETE all f. No UPDATE/DELETE/TRUNCATE on any `litkb` table for reader,
  writer or promoter (0 tables). Column INSERT on the new `rebased_from_version_id`: f on all five version tables,
  because it was added after 0006's column grants.
- Default ACL for `litkb_owner` revokes function EXECUTE from PUBLIC. `litkb_test` CONNECT on `litkb`: f.
  `litkb_meta.schema_migrations` holds 8 rows.

## D-3: enforced vs conventional

**Enforced by the server:** reader and writer cannot EXECUTE any promotion function, and are not members of the
promoter role. The shared `%APPDATA%\postgresql\pgpass.conf` holds no promoter line: its roles are `postgres`,
`litkb_owner`, `litkb_reader`, `litkb_writer` and `litkb_test`, 5 lines. So `psql -w -U litkb_promoter -d litkb`
fails `fe_sendauth: no password supplied`. `promote.connect()` works through its own passfile:
`current_user = litkb_promoter`, EXECUTE `promote_commit` = t. That file has 1 line, `localhost:5433:litkb:litkb_promoter`.

**Conventional, not enforced:** everything that keeps an agent process from using that passfile.
`connect()`'s refusal can be bypassed by conninfo injection, whitespace + `PGPASSFILE`, `_open`, or by
importing `litkb.promote.connect` itself. `LITKB_PROMOTER_PASSFILE` only relocates the file. The file sits
outside the repository, but its inherited NTFS ACL lets any authenticated local user modify it and any user
read it. Agents run as the same Windows user (`kameron`) anyway. The git-reachability rule still lives only in
`promote.commit`; the database accepts any 40-hex merge sha from a promoter session. That is as decided (D-3).

## Residual gaps (builder's three), ranked by what P2 real data would expose first

1. **A named workstream is not authenticated (gap 2).** Workstream ids are SELECTable by every role. Probe: a
   second writer connection named another workstream's id and `add_evidence` was ACCEPTED. The first P2 session
   with two agents in parallel exposes it. The proposed token-hash only stops mistakes; that is the realistic goal.
2. **The writer installs its own `ok` run and makes it current (gap 1).** Probe: ACCEPTED. Re-extracting a file
   is a normal ingest event, and each one silently un-promotes that file's evidence. It becomes visible as soon
   as any file is extracted twice. Prepare holds the evidence, so nothing wrong enters main.
3. **Writer column INSERT on `gap_versions`/`use_versions` (gap 3).** Probe: `add_evidence` onto a superseded,
   non-head `proposed` version was ACCEPTED; no chain reaches that evidence. This is noise plus the `23505`-vs-`40001`
   error class, and it needs a misbehaving client. Last.

The ranking is inferred from the probes plus the P2 scope. It is not measured on P2 data, which does not exist yet.

## Secrets

`git log -p 24aba35^..1cb9f00` (1,895 lines) was grepped. Hits on added lines: `password` 7, `pgpass` 13,
`localhost:5433:` 2, `secrets` 6, `PGPASSWORD`/`passwd`/`token_urlsafe` 0. Every hit is prose, a path constant,
or the templated `localhost:5433:litkb:<role>:<pw>` docstring. No line has the shape `host:port:db:user:secret`.
The token-shaped strings of 28+ characters are identifiers and paths. No password or passfile content was found.
Neither passfile was printed; only field counts and the first four fields of each line were read.

## Tests

`cd Scripts && PYTHONUTF8=1 py -3.12 -m pytest qc/test_litkb_p1.py -q`: `59 passed in 15.29s; litkb Postgres
tests: 56 passed` before the mutations. The same result (`59 passed in 15.95s`) on the restored tree after them.

## Measured vs not

Measured: every row cites a run or probe from this session. Inferred: the lock-ordering explanations for E-1/E-2,
read from the observed blocking plus READ COMMITTED semantics, and the residual-gap ranking. Not done: the builder's
37 mutations were not re-run; `litkb` was not written; provisioning was not re-run; the server log was not read.

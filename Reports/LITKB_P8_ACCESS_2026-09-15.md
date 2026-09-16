# litkb P8 — the access layer

Branch `work/20260915-access-layer`, from `work/20260913-literature-kb` at `af57ebb`. Nothing was
merged into this branch and nothing was pushed to `main`.

Design: `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §5, §8, §9, §9.1, §10, §14 P8.
Decisions: `Scripts/decisions.yaml` `litkb-p0-foundation`, §15.13 (D-4), §15.17.
Convention: `Scripts/docs/LITERATURE_CONVENTION.md` (the hunt protocol, rewritten at P3).

**Status of this evidence (CLAUDE.md 3.4c).** Every number below was produced by the author of the
code, and has since been **re-run by an independent agent** against its own throwaway database
(`litkb_test_w3`) — §2.1. Every total reproduced; it found **no discrepancy** with this report, and
added one caveat of its own (§6 item 10). It is not a full referee: it re-ran the author's tests, it
did not write gold, and the two things this report already calls unproven — the unexercised
librarian and the uninstalled hook — it could only confirm as unproven.

---

## 1. What was built

| Piece | Home |
|---|---|
| The MCP server: nine tools, stdio | `Scripts/pipeline/litkb/mcp/server.py` (`litkb/mcp/__init__.py` is deliberately empty) |
| `promote prepare` / `promote commit` at the CLI (the server shells out to `prepare`; `commit` has no tool) | `Scripts/pipeline/litkb/commands.py` `cmd_promote`, parser `promote` |
| The promoter login against a throwaway database (`SET ROLE`, never a passfile) | `Scripts/pipeline/litkb/promote.py` `connect()` |
| The skill — the procedure, in steps | `.claude/skills/literature/SKILL.md` |
| The librarian subagent | `.claude/agents/librarian.md` |
| The hook, **staged, not installed** | `.claude/hooks/litkb_guard.py` |
| Tests: protocol round-trip, refusals, redaction, the mini-hunt, the two kills, the hook | `Scripts/qc/test_litkb_p8.py` (28 tests) |
| Recorded registry responses, so the hunt admits real DOIs offline | `Scripts/qc/testdata/litkb_p8/registry_cache.json` |
| Mutation rows X1–X6 | `Scripts/qc/instruments/litkb_p2_mutations.py` |
| `mcp==2.1.1` pin; `litkb.mcp` added to the install | `Scripts/requirements-litkb.txt`, `pyproject.toml` |
| `.claude/{skills,agents,hooks}` un-ignored; settings files deliberately still ignored | `.gitignore` |

### The tools

| Tool | Role | What it does |
|---|---|---|
| `litkb_search` | reader | hybrid lexical over blocks and uses — Postgres full-text and trigram, fused by reciprocal rank. Returns work key, page, section path and `block_id` |
| `litkb_work` | reader | one work by DOI or key: identifiers, files, uses, discrepancies |
| `litkb_candidates` | reader | what this workstream found, admitted, or did not |
| `litkb_ws_status` | reader | state, candidates, admissions, attempts, proposed versions, promotions |
| `litkb_ws_open` | writer | opens a workstream; returns the **id only** |
| `litkb_admit` | writer | DOI / arXiv admission through the five checks |
| `litkb_acquire` | writer | open access → archive → Sci-Hub; every attempt logged |
| `litkb_record_use` | writer | a use plus evidence; `quote_verified` computed by the database |
| `litkb_propose_promotion` | (subprocess) | `promote prepare` only |

**Absent on purpose:** `promote commit` (Kam's, after his merge) and `approve` (a *second* session's,
§15.13 D-4 — a tool on this server would make it this one). `test_promote_commit_and_approve_are_not_tools`
asserts the absence on the live tool list, not in prose.

### Four properties the server keeps

1. **The token is never a tool parameter.** A parameter is written into the model's transcript. The
   token is read from `<worktree>/.litkb-workstream` and reaches the database only as a bound query
   parameter (design §5, third P1 referee F-8). A write tool called where there is no token file is
   refused `no-workstream` before any connection opens.
2. **One output boundary.** Every tool returns `_out(...)`, whose single `redact()` call is the only
   thing between a route's own words and the model. `_session()` arms it with `add_secret(token)`.
   The module has no `print` and writes to no stream — on stdio, stdout *is* the protocol.
3. **No promoter and no ingest credential in the server process.** `litkb_propose_promotion` runs
   `py -3.12 -m litkb promote prepare` as a subprocess. Its own logins are reader and writer only.
4. **Reader reads, writer writes.** The writer holds no direct INSERT on any workstream-owned table
   (§4.7), so no tool can write round the token even if this file were wrong.

### Deviation from design §9, stated plainly

§9 says "`approve`, `promote prepare` and `promote commit` are not exposed to agents, and neither is
`ingest`: the MCP server never holds the promoter or ingest credential." The brief for this phase
asks for `litkb_propose_promotion` (prepare only). **Both are honoured in the part that matters —
the server holds no promoter credential — but prepare IS now reachable from an agent**, through a
subprocess. A referee should decide whether that satisfies §9 or amends it. It is a real change to
the access surface and is not hidden in the code.

---

## 2. The gate (§14 P8) and the kills

Run as: `LITKB_LIVE=1 LITKB_TEST_DB=litkb_test_w2 PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 -m pytest qc/test_litkb_p8.py -q`
→ **28 passed** (25 of them need no Postgres and no network).

### 2.1 Reproduced by an independent agent — output verbatim

An agent that did not write any of this re-ran the three commands against `litkb_test_w3`:

```
............................                                             [100%]
litkb Postgres tests: 3 passed
28 passed in 24.96s

69 call sites, 66 covered by a row, 3 equivalent
16 sinks, 2 redacted, 14 allowed        (no PROBLEM line)

6/6 mutations fired; baselines passed
baseline again (restored) (qc/test_litkb_p8.py): 25 passed, 3 deselected in 10.08s
```

It also read the code for four properties and answered each against file and line:

- the token is **never** a tool parameter and appears in no tool result; there is **exactly one**
  `redact()` (server.py:71) and **exactly one** `add_secret()` (server.py:146);
- `_propose_promotion` subprocesses the CLI; the server's own `_role()` resolves only
  `litkb_reader` / `litkb_writer`, and the ingest login appears nowhere in the file;
- every git call in the commit test is `git -C <pytest tmp_path>`; with `--no-fetch`,
  `promote.fetch_main()` — the only network call in `promote.py` — is never reached, and the module
  contains no `push`;
- the hook returns 0 on every path, emits only `additionalContext`, and is registered nowhere: that
  `.claude/` holds `agents/`, `hooks/`, `skills/` and **no settings file at all**.

Its verdict: no discrepancy with §2 or §3. Its one addition is §6 item 10.

### 2.2 `check.py --fast` on the whole tree

`LITKB_TEST_DB=litkb_test_w2 … py -3.12 qc/check.py --fast`, 33m46s (the machine was running
several other worktrees' suites at the time):

```
[PASS] secrets · [PASS] ruff · [PASS] compile
3 failed, 2698 passed, 25 skipped, 2 xfailed in 2026.18s
litkb Postgres tests: 261 passed, 3 skipped
```

The three failures, each named rather than aggregated:

| Failure | Mine? | What it is |
|---|---|---|
| `test_experiments.py::test_pointer_paths_resolve[crown_state_model]` | no | the one pre-existing failure this branch is allowed to carry |
| `test_status_discovery.py::test_path_insert_ledger` | **YES — FIXED** | this suite reached P2's PDF builder with `sys.path.insert`, which that ledger closes. It now loads the sibling module by file path through `importlib`, and the ledger test passes |
| `test_litkb_inventory.py::test_the_frame_reader_reproduces_the_committed_corpus_census` | no | `assert 234 == 224` — the census counts PDFs on disk under `Literture\`, and ten more have landed since it was committed. Nothing in this branch touches inventory (`git diff --name-only af57ebb..HEAD`), and the number is about the corpus, not the code. It belongs to whoever re-pins that census |

After the fix: `qc/test_litkb_p8.py` + the ledger test → **29 passed**.

### The mini-hunt — PASSES

`test_the_mini_hunt_runs_end_to_end_through_the_mcp_tools`, one MCP client session, five tool calls:

`litkb_ws_open` → `litkb_admit` (DOI `10.1016/j.laa.2010.04.007`, Higham & Lin 2011, through the
five admission checks against a **recorded** Crossref record) → `litkb_acquire` (binds the PDF; the
`acquisition_attempts` row is asserted, whatever the outcome) → `litkb_record_use` (quote located by
the server, **verified by the database**) → `litkb_propose_promotion` → the promotion row is
`prepared`.

**The substitution, stated (3.4c):** the design's gate names an *extract* step. P5 has not run
against this throwaway database, so the test inserts one extraction run and one block directly
(`_seed_block`) and `set_current_run`s it. What P8 gates is the ACCESS layer; the extractor is P4/P5.
A referee who wants the unsubstituted gate has to run stage 0–5 into `litkb_test_w2` first.

**Unvalidated by design (3.4c):** the librarian subagent definition is **not exercised** by anything
here. It is a file. Nothing in this branch has run a librarian agent through the MCP server, because
the server is not registered (§4 below) and a subagent cannot be given tools that do not resolve.
The mini-hunt drives the *tools* the librarian would call, which is a weaker claim, and I make only
that one.

### Kill 1 — an unverifiable quote is refused at prepare — FIRES

`test_kill_an_unverifiable_quote_is_refused_at_prepare`, in two layers:

- the server locates the quote in the block and refuses one that is not there (`quote-not-in-block`),
  so an honest caller cannot record an unverifiable use at all;
- a caller that supplies offsets itself gets past that. The database recomputes `quote_verified` in
  a trigger the writer role cannot name and stores **false**; `promote prepare` then **holds** that
  chain (§5: all-or-nothing *per chain*, so the offer as a whole still succeeds) and the use version
  stays `proposed`.

**With a positive control in the same prepare**: a second use, same workstream, verified quote,
reaches `prepared`. Without it "the chain was not prepared" would also be satisfied by a prepare
that prepared nothing, and the kill would say nothing about the quote.

### Kill 2 — a tool call without a token is refused — FIRES

`test_a_tool_without_a_workstream_token_is_refused`, parametrised over all six workstream tools.
Refusal code `no-workstream`, message names `litkb_ws_open`.

### Kill 3 — a planted secret in a tool result is redacted — FIRES

`test_a_planted_secret_is_redacted_in_a_tool_result`. The token is armed by an ordinary tool call
reaching `_session()`, and the boundary is then checked against that same token.

### `promote commit` — exercised only against a scratch repository

`test_promote_commit_runs_only_against_a_scratch_repository` builds a git repo in `tmp_path`, makes
a work branch, and **merges its own main**. `--no-fetch` means no remote is contacted. It shows P1's
kill through the CLI path the tool would use: a merge commit not reachable from main is refused;
after the test's own merge, commit succeeds and the promotion reads `committed`. The real
repository's `main` is never named, fetched or moved.

### Mutation rows — 6 of 6 FIRED

`LITKB_TEST_DB=litkb_test_w2 py -3.12 qc/instruments/litkb_p2_mutations.py --only X1,X2,X3,X4,X5,X6`
→ `6/6 mutations fired; baselines passed`, each file restored sha256-equal.

| Row | Guard removed | Answered by |
|---|---|---|
| X1 | `_out` stops redacting | the planted-secret test |
| X2 | `_session` stops arming redaction | the same test (the other half) |
| X3 | MCP labels keep invisible characters | the three invisible-label cases |
| X4/X5/X6 | `litkb_admit` / `litkb_acquire` / `litkb_record_use` invent labels | the three no-labels cases |

`--sites`: **69 call sites, 66 covered by a row, 3 equivalent; 16 sinks, 2 redacted, 14 allowed — no
problems.** No new `SINK_ALLOW` entry was needed: the server has no `print` and no stream write. One
redundant call was removed rather than allowlisted — `_work` no longer calls
`textnorm.normalize_doi` before handing the value to `litkb.norm_identifier('doi', …)`, its own
database twin, in the same statement.

---

## 3. The hook — staged, not installed

`.claude/hooks/litkb_guard.py`. Design §9.1: the hooks come **after** P8's gate, because "before the
MCP tools exist, a blocking hook would leave agents no route to literature at all." So it **warns and
never blocks**: `hookSpecificOutput.additionalContext`, no `permissionDecision`, exit 0 always.

It fires only when the working directory (or a parent) has **no** `.litkb-workstream`, on:

- `mcp__paper-search-mcp__download_*` / `read_*_paper` — the *search* tools are deliberately not
  matched: looking to see what exists is not pulling a paper into the project, and warning on a
  search trains the agent to ignore the warning;
- `Read` of a `.pdf` under the literature root;
- `Bash`/`PowerShell` naming `aa_fetch`, Sci-Hub or the archive.

Four tests drive it with synthetic PreToolUse payloads: it warns on each route outside a workstream,
is silent inside one, ignores unrelated calls, and `test_the_hook_is_staged_and_not_installed` fails
if any settings file ever registers it without this report being updated.

**Installation (Kam's, after the gate is accepted).** Add to `.claude/settings.json` — note
`Scripts/.claude/` is gitignored on purpose, so this goes at the repository root or in user settings:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "mcp__paper-search-mcp__.*",
        "hooks": [{ "type": "command",
                    "command": "py -3.12 ${CLAUDE_PROJECT_DIR}/.claude/hooks/litkb_guard.py" }] },
      { "matcher": "Read|Bash|PowerShell",
        "hooks": [{ "type": "command",
                    "command": "py -3.12 ${CLAUDE_PROJECT_DIR}/.claude/hooks/litkb_guard.py" }] }
    ]
  }
}
```

A matcher containing a `.` or `*` is an unanchored regex; one of only word characters, `_`, `-` and
`|` is an exact string or a pipe-separated list. **The hook's own kill (design §9.1) — "with the hook
installed, a paper-search call in a worktree with no `.litkb-workstream` is flagged; with the hook
entry removed, it is not" — has NOT been shown in a live session**, because the hook is not
installed. What is shown is the script's behaviour on the documented payload shape. That gap is real
and belongs to whoever installs it.

---

## 4. Registration line, for Kam (user scope) — NOT run here

```
claude mcp add -s user -e LITKB_AGENT=claude -e LITKB_SESSION=default -e PYTHONPATH=<a checkout that contains litkb>\Scripts\pipeline --transport stdio litkb -- py -3.12 -m litkb.mcp.server
```

Notes a registrar needs:

- `PYTHONPATH` is required **today**, and it must name a checkout that HAS `litkb`. It is not
  `D:\edmonds-pipeline\treedata\Scripts\pipeline` right now: that worktree is on
  `work/20260906-healing-tool`, where `Scripts/pipeline/litkb` does not exist. `py -3.12 -c "import
  litkb"` fails for the same reason — the editable install was made from a tree without it.
  `pyproject.toml` now lists `litkb.mcp`, so after `py -3.12 -m pip install -e .` from a tree that
  has `litkb`, the `-e PYTHONPATH=…` can be dropped and the path question goes away.
- Put at least one option (here `--transport stdio`) between the last `-e` and the server name, or
  the name is parsed as another `KEY=value`.
- `LITKB_AGENT` / `LITKB_SESSION` must be set or every write tool refuses `no-labels`. **A user-scope
  `LITKB_SESSION=default` makes every session the same session** — and the manual-admission sign-off
  compares session labels (§15.13 D-4), so with `default` a session could approve its own admission.
  Either set it per project, or keep manual admissions on the CLI (`--session`), where it is real.
- The server finds `.litkb-workstream` by `LITKB_WORKTREE`, else `git rev-parse --show-toplevel`
  from its cwd, else the cwd — the same order the CLI uses, so both halves agree on the worktree
  whatever directory Claude Code launched the server in.
- Resulting tool ids: `mcp__litkb__litkb_search`, `mcp__litkb__litkb_admit`, … The librarian's
  `tools:` list uses the server-wide form `mcp__litkb`.
- **Not registered by this branch**, per the brief.

---

## 5. CLAUDE.md rule text, for Kam's merge — NOT edited here

CLAUDE.md §3.1 says `main` is Kam's, and design §9.1 puts the final rule at P8 for him to merge. The
proposed final form, replacing P3's interim text (narrowed to claim-supporting uses, §15.17):

> **Literature.** A paper is found, admitted, acquired, read and cited through the literature
> knowledge base whenever it supports a claim in the project (`decisions.yaml` §15.17); ad-hoc
> reading is not governed by this rule. The procedure is the `literature` skill
> (`.claude/skills/literature/SKILL.md`), which drives the `litkb` MCP tools; the tracker, the
> xlsx and every `manifest.csv` are generated exports — never hand-edit them.

And one roadmap row for §2.1:

> | **Any literature question — what we hold, what a paper was used for, how to admit one** | the `literature` skill → the `litkb` MCP tools; procedure in `Scripts/docs/LITERATURE_CONVENTION.md` |

It restates no procedure: CLAUDE.md is "a ROADMAP and a RULEBOOK … deliberately NOT a facts store",
and anything restated there rots.

---

## 6. What blocks a referee — and what blocks acceptance

1. **The reproduction in §2.1 is not a full referee pass.** An independent agent re-ran the author's
   commands and read the code; nobody has written gold for this phase, nobody has argued that the
   tests test the right things, and the proposer still chose every assertion. A referee can
   reproduce the numbers in one command:
   `LITKB_LIVE=1 LITKB_TEST_DB=litkb_test_w2 PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 -m pytest qc/test_litkb_p8.py -q`,
   and the mutation table with
   `LITKB_TEST_DB=litkb_test_w2 … litkb_p2_mutations.py --only X1,X2,X3,X4,X5,X6`.
   Needs: PostgreSQL on `localhost:5433`, the `litkb_test` role, `litkb_test_w2` provisioned
   (`py -3.12 -m litkb.db.provision --workers 2`), and `mcp==2.1.1`.
2. **The librarian definition is unexercised** (§2). To exercise it, the server must be registered
   (§4) and a librarian agent actually run — which cannot happen inside this branch.
3. **The hook's own kill has not fired in a live session** (§3), because the hook is not installed.
   Design §9.1 puts that after this gate, so it is in order, not skipped — but it is not yet shown.
4. **The mini-hunt substitutes a seeded block for the extract step** (§2). Stated, not hidden.
5. **`litkb_search` has no index and no vector leg.** `to_tsvector` and `similarity` are computed
   per row at query time — correct, and fine at the current corpus size, but its cost has **not been
   measured** and no GIN/trigram index was added. The vector leg is wired behind
   `LITKB_VECTOR_SEARCH` and is inert until P7; every result says so in words, so a caller cannot
   mistake lexical recall for semantic recall.
6. **`promote prepare` reachable from an agent is a deviation from §9** (§1). A referee, not the
   author, should rule on it.
7. **`.gitignore` now un-ignores `/.claude/skills/`, `/agents/`, `/hooks/`** — three new tracked
   subtrees at the repository root, which reach every session on Kam's merge. `settings.json` and
   `settings.local.json` are still ignored, so no permission or hook registration can be swept into
   a commit. **Side effect to expect at the merge:** the main worktree already holds an untracked
   `.claude/skills/paper-search/SKILL.md`. Once this `.gitignore` lands it stops being ignored and
   will show up as untracked-and-committable in every `git status`. It should be either committed
   deliberately or ignored by name — not swept in with something else.
8. **`promote.connect()` gained a test-database branch** that logs in as `litkb_test` and `SET ROLE
   litkb_promoter`. `is_test_db()` keys on the `litkb_test` prefix and is never true for `litkb`, so
   it cannot be aimed at the real database — but it is a new path to the promoter's rights, and a
   referee should read it with that in mind.
9. **The workstream `p8-*` rows live only in `litkb_test_w2` and `litkb_test_w3`.** Nothing in this phase wrote to
   `litkb`, and no promotion was committed against the real repository.
10. **`--sites` reporting "no problems" rests partly on authored prose** (the reproducing agent's
    own caveat, and it is right). 14 of the 16 sinks are cleared by a `SINK_ALLOW` entry — a human's
    argument that the values interpolated there carry no secret — with a call COUNT so the argument
    has to be re-made when a sink is added. Two are cleared mechanically, by passing through a
    redactor. The census is an assertion under review, not a measurement. The server adds nothing to
    it: it has no sink at all.

---

## 7. The referee's findings, fixed (2026-09-15, after `b787fa0`)

`Reports/LITKB_P8_REFEREE_2026-09-15.md` returned **READY WITH FIXES**: five findings, plus two
convention errors it confirmed by running and a list of guards that had no mutation row. Each is
below with the kill that shows it fires. `litkb` was never opened in this pass; every measurement
below ran against `litkb_test_w2`.

### 7.1 F-4 — the boundary redacts credential SHAPES, not only registered strings

`netutil.redact()` is `str.replace` over what `add_secret()` armed, so a pgpass line planted in a
block came back through `litkb_search` verbatim: no process here had ever held that password, and
none could have registered it. `_out()` now runs `redact_shapes()` over the OBJECT before
`json.dumps`, then `redact()` over the JSON as before.

Over the object, not the text, because by the time `json.dumps` has run a block's text is one JSON
string with escaped newlines and a line-anchored rule can never match inside it. The pgpass and
assigned-64-hex rules are **loaded from `qc/secrets_check.py`** — the ladder rung that already
refuses these shapes in git's index — so there is one definition of what a pgpass line looks like
(`test_the_shape_rules_are_the_secrets_rung_s_own` asserts the compiled patterns are the rung's own,
not a copy). Added at the boundary only: URL query `key=` / `token=` / `password=`, an exact list of
JSON field names, and PEM blocks.

**The decision the referee asked for, and its control.** A bare 64-hex value is **not** masked: a
sha256 is 64 hex and every file record carries one. The rung's own rule is that 64 hex is a secret
only when ASSIGNED to a token-like NAME (`token=`, `secret:`, `password=`), and that is the rule
reused. A field called `key` is not masked either — in this database `key` is the WORK key, and
`work_key` is on every search hit; `key=` is masked only inside a URL query, where the archive's
download key is what actually leaks.

* **KILL** `test_a_planted_credential_shape_is_masked_in_a_tool_result`: a pgpass line with prose
  before and after it, inside a block hit inside a list, comes back
  `localhost:5433:litkb:litkb_writer:<KEY>` with the block's own sentences intact — and the same
  result's URL key, JSON `password` field and PEM body are masked too. Re-run live through a real
  MCP session against a seeded corpus: the planted block was returned by `litkb_search` with the
  password masked.
* **CONTROL** `test_a_work_shaped_result_is_returned_byte_for_byte`: a `litkb_work` record — work
  key, `work_key`, authors, a 64-hex `sha256`, a DOI — passes the boundary unchanged. A sha256 in a
  file record still shows.
* Harness rows **X7** (the `redact_shapes` call in `_out`) and **X17** (its recursion, the twin of
  RD15 — every search hit is inside a list of dicts).

### 7.2 F-1 — read tools present the workstream token

`litkb_ws_status` and `litkb_candidates` called `_session()` for the id and then queried
`WHERE workstream_id = %s`, presenting nothing. A `.litkb-workstream` naming a **published**
workstream id with 64 zeros as its token read that workstream's whole status.

The token stays out of the tool signature — a parameter is written into the transcript (rule 1), and
`test_a_tool_without_a_workstream_token_is_refused` pins both read tools to `no-workstream` when the
file is absent. So "an optional token" is implemented where a token can actually come from: the
file. If it is there it must VERIFY, through `litkb.check_ws_token` (migration 0018, a SECURITY
DEFINER boolean — `_require_ws_token` is revoked from every agent role and RAISEs, which is the
wrong shape for a tool that must refuse having written nothing). A database without 0018 fails
CLOSED: `no-token-check`, naming the migration, never the workstream's internals.

* **KILL** `test_a_forged_token_reads_nothing_and_a_real_one_reads_its_own_workstream`: forged ->
  `bad-token`, and the result carries no slug, state, candidates, admissions or promotions. Both
  directions in one test, because "refuses everything" would satisfy the kill just as well.
* **KILL** `test_a_write_with_a_forged_token_reaches_the_model_as_bad_token`: the write path's
  refusal was always the database's, but it reached the model as `refused: "error"` with a raw
  psycopg message and a `CONTEXT: PL/pgSQL function _require_ws_token(uuid,text) line 1`. It is now
  `bad-token` with the same sentence as the read tools, matched on the database's own words rather
  than on SQLSTATE alone (42501 is also a missing GRANT).
* **A third tool had the same hole, and a worse one — found here, not by the referee.**
  `litkb_propose_promotion` discarded the token too, and `promote prepare` takes NO token at all:
  `litkb.promote_prepare(ws, branch_head, report_path)` is authorised by the PROMOTER credential.
  So a crafted `.litkb-workstream` naming a published workstream id would have prepared THAT
  workstream's proposals, written its chain report into the attacker's worktree, and — one prepared
  promotion per workstream — blocked its owner's own prepare. It is now checked before the
  subprocess runs; `test_the_offer_tool_refuses_a_forged_token_before_it_runs_anything` asserts the
  refusal AND the absence of the side effects (no `_derived/`, no promotion row). Harness row
  **X18**.
* Harness rows **X8**, **X9**.
* **Found by running it, not by reading:** `litkb_candidates` selected a column `identifiers` that
  the schema does not have (it is `ids`, `0001_core.sql`), so with a real workstream it had NEVER
  returned a row — the gate only ever called it with no workstream, and `_guarded` turned the
  `UndefinedColumn` into a generic `error` that reads like an empty answer. The referee's "same for
  `litkb_candidates` **by construction**" was right about the leak and could not see this. Fixed,
  and the test above asserts the tool returns its own workstream's rows.

### 7.3 Section 3.6 / 4.1 — a use with no verified evidence is HELD at prepare

Confirmed live before the fix: a use with zero `use_evidence` rows reached `prepared` in the same
promotion as five others, because the check counted rows that were NOT promotable and zero rows is
zero bad rows. Migration **0019** counts the PROMOTABLE rows instead — one clause covering both "no
evidence at all" and "every row unverified" — and the reason word is `no-verified-evidence`.

* **KILL** `test_a_use_with_no_verified_evidence_is_held_at_prepare_and_the_report_says_why`: the
  zero-evidence use stays `proposed` while a verified control in the SAME prepare reaches
  `prepared`. Harness row **X15** removes the clause; with it removed the zero-evidence use is
  prepared again, which is the referee's finding reproduced as a mutation.
* **What it invalidates, stated:** every use written before stage 5 exists carries no evidence row,
  the 15 the linkage review wrote included. They are not deleted and not altered — they stop being
  promotable until a verified quote is attached, which is what the convention always claimed was
  already true. This is fix (a) of the referee's 4.2, not (b). Kam can still choose (b), and the
  cost of that choice is now a migration to revert rather than a sentence to write.

### 7.4 F-3 — the `feeds` vocabulary is the convention's seven forms

`0005:17` enforced three of the seven the convention names, so a session following `SKILL.md`
step 4 wrote a use that would not promote and found out at step 5. The validator is P2's SQL, so the
fix is migration **0018** (`_feeds_token_ok`), and `SKILL.md` now prints the whole table with the
depth rules (`framework §N[.N]` one sub-level, `narrative §N` integer only, `review §N[.N…]` any
depth).

* **KILL** each token on its own: `test_every_feeds_token_the_convention_names_is_accepted`
  (7 cases) and `test_a_feeds_token_outside_the_vocabulary_is_still_refused` (7 cases — a bare
  `§16.2`, a two-level `framework §13.1.1`, `decision Bad-Slug`, a `report` token with no `#§loc`).
  Widening a validator must not turn it off. Harness row **X12**.
* Live: a use carrying **all seven** tokens at once reached `prepared` through the MCP tool.

### 7.5 F-5 — prepare writes the promotion report

Measured by the referee: prepare recorded `promotions.report_path` and wrote no file, while the
report and `SKILL.md` both said it wrote one onto the work branch. `promote.render_report` /
`write_report` now build it and `cmd_promote prepare` writes it; `litkb_propose_promotion` returns
`report_written`, plus `prepared` and `held` (each held chain with the database's own reason).

Default path `_derived/promotions/<promotion_id>.md` in the worktree. **`promotions.report_path`
still records only what the caller named AT prepare** — the promotion id does not exist until
prepare returns — so the default is reported in the payload, not in the row. Making the database
record it would need another migration; it is flagged here rather than invented. `SKILL.md` step 5
now says what actually happens: prepare WRITES the file, it does not stage or commit it, so **commit
it with the branch**.

* **KILL** the assertions in 7.3's test: the file exists at `_derived/promotions/<id>.md`, carries
  `## Prepared` and `## Held`, and names `no-verified-evidence` against the held chain. Harness row
  **X16**.
* The chain rows come from `litkb.promotion_chains` (0018), a SECURITY DEFINER view of `_ws_chains`
  granted to `litkb_promoter` ONLY. A GRANT on `_ws_chains` alone is not enough — it calls
  `_entity_tables`, revoked too — and widening a helper chain one function at a time grants more
  than the caller needs. No agent role can call either.

### 7.6 Section 3.7 — the librarian and the credential files

`Read`, `Grep` and `Glob` can open a passfile, and nothing told the librarian not to. Two controls,
neither of them the enforcement:

* the brief now names the four shapes in the librarian's own words (`**/pgpass*`, `**/secrets/**`,
  `**/.litkb-workstream`, `**/*.env`) and says why: a credential read is a credential written into a
  log that outlives the session;
* `.claude/hooks/litkb_guard.py` gained a credential rule, and the librarian's frontmatter carries a
  `PreToolUse` hook entry pointing at it — per-agent, so it runs only while the librarian is active
  (code.claude.com/docs/en/sub-agents, "Hooks in subagent frontmatter"). It WARNS; it emits no
  `permissionDecision`.

The credential rule fires **inside a workstream too**, unlike the literature rules: a workstream is a
reason to reach literature through litkb, never a reason to read a passfile, and
`.litkb-workstream` is itself the secret that is always present there.

* **KILL** `test_the_hook_warns_on_a_credential_file_even_inside_a_workstream` — six payloads
  (`secrets/`, `pgpass.conf`, the token file, a Grep at a `.pgpass`, a `**/*.env` glob, a shell
  `type` of a passfile), each with a token file planted in `cwd`; plus the negative control
  `test_the_hook_says_nothing_about_an_ordinary_file`.
* **Not enforcement, and this report does not claim it is.** Frontmatter hooks are ignored for
  plugin subagents, skipped by `disableAllHooks`, and not loaded in a folder that has not been
  trusted. The durable control is a `permissions.deny` block in `settings.json`, which applies to
  subagents too — **Kam's install**, since no settings file is tracked. Anchor those patterns at the
  filesystem root (`Read(//**/pgpass*)`); `Read(**/pgpass*)` resolves relative to the settings file
  and never reaches `~/.pgpass`. For Grep and Glob the documentation calls Read deny rules
  best-effort, which is exactly why the rule is also in the brief.

### 7.7 Section 2.4 — the Q3 miss, and which half of the fix actually did the work

Two changes, and the honest measurement is that they are not equally load-bearing.

1. **`litkb.norm_search_text`** (0018) — U+FFFD and soft hyphens dropped, line-break hyphenation
   joined, whitespace collapsed — applied to the block text and the query **in the same statement**,
   so the two cannot drift (the twin-drift rule migration 0014 D1 was written against). One SQL
   function, no Python half.
2. **`litkb.any_term_query`** (0018) — a second lexical leg that ORs the query's lexemes and ranks by
   `ts_rank`. `plainto_tsquery` ANDs every term, so ONE word the extractor mangled drops a passage
   however well the rest of it matches.

**Scored on the referee's frozen gold** (`Reports/gold/p8_gold_2026-09-15.json`, sha256
`77fb53a1…`), re-seeding all three `.txt` extracts into `litkb_test_w2` the way his 2.3 describes —
**1,938 blocks** here against his 1,457, because this pass split paragraphs slightly differently; a
larger denominator makes the ranks below harder, not easier. Rank of the gold block, same queries,
same corpus, before and after:

| gold | before (the shipped statement) | after |
|---|---|---|
| Q1 | 1 | **1** |
| Q2 | 2 | **1** |
| Q3 | **not returned — MISS** | **3** |

**The normaliser alone does not move Q3.** Measured directly: with normalisation on both sides and
all-terms matching, Q3 is still a miss; with the any-term leg and NO normalisation, Q3 is rank 1.
The gold passage says "NEs" where the question says "naive estimators", and that gap is not
mojibake — it is an abbreviation, which no normaliser repairs. The normaliser earns its place on the
other queries and on the trigram leg (Q2 moved from 2-of-2 to 1, and `misclassi cation` now reaches
`misclassification` by trigram), and it has its own kill rather than riding on Q3's:
`test_search_reads_the_text_through_the_normaliser` (row **X13**) uses a word the PDF broke across a
line, which tokenises as two words and is too short to reach the trigram threshold.
`test_search_finds_a_block_the_extractor_mangled` (row **X14**) is the any-term leg's.

Two further consequences, both the referee's observations:

* **the trigram leg is now a leg.** His 3.5 was right that it was not one: both "legs" were built
  from the SAME all-terms result set, ordered twice, so a block only trigram could find, below the
  lexical cut, was never retrieved. There are now three statements, each with its own `WHERE`,
  `ORDER BY` and `LIMIT`, fused by reciprocal rank. `legs` in every result says so.
* **the search now has indexes** (section 6 item 5 above): a GIN expression index for the normalised
  tsvector and a GIN trigram index for the normalised text. `blocks` carried neither before — the
  trigram leg had always been a sequential scan.

**The real fix is upstream and is NOT this.** The block still stores `misclassi<FFFD>cation`, because
that is what the PDF's text layer rendered; this repairs RETRIEVAL. P4/P5 own the text layer, and
until their bulk pass runs, **the real `litkb` holds 0 rows in `blocks`** — so `litkb_search`'s block
leg answers nothing there today, whatever it scores here. `SKILL.md` section 0 now says that in the
skill, where a caller will meet it.

### 7.8 Mutation rows, and the two failures that are not ours

The referee's 6.1: "a guard with no row is a guard not yet shown to be load-bearing, and two of P8's
four best properties are in that position." Twelve rows were added — **X7–X18** — covering the shape
redactor and its recursion, the read-tool token check at both call sites, the offer tool's, the
`work-mismatch` guard (his 3.3, the property with no row), the four database guards of 0018, 0019's
evidence clause, and the report write. Every one is answered by a test in `qc/test_litkb_p8.py` that
does **not** carry the `litkb_live` mark, because the harness deselects live tests — a row answered
only by a live test reports DID NOT FIRE.

`--sites` passes at **74 call sites, 71 covered by a row, 3 equivalent**, with `redact_shapes` and
`_require_token` added to `HELPERS` so the per-call-site rule reaches them. The self-check caught the
`redact_shapes` recursion site with no row, which is exactly what it is for.

All twelve FIRE: `X7–X13, X15–X18` in one batch (`11/12 mutations fired; baselines passed`) and
`X14` after the fix below (`1/1 mutations fired`).

**Three of the rows had to be rewritten, and why is worth keeping.** X11/X13/X14 first deleted the
`CREATE FUNCTION` block outright. That left the `COMMENT` and the `GRANT` behind, migration 0018
failed to apply, and every Postgres test ERRORED — and this harness counts failures, not errors, so
all three reported **DID NOT FIRE**. A row that breaks the FILE proves the file is load-bearing; only
a row that breaks the RULE proves the rule is. Each now leaves a valid migration whose function does
the wrong thing: `check_ws_token` returns true for any token, `norm_search_text` stops repairing the
extractor's damage, `any_term_query` returns nothing so search is all-terms again. (The harness's
blindness to `errors` is itself worth a look by whoever owns it next; it is not this branch's to
change mid-pass.)

**And one row failed honestly, which improved a test.** X14 — the any-term leg switched off — first
reported DID NOT FIRE, because `test_search_finds_a_block_the_extractor_mangled` seeded a single
SENTENCE: the trigram leg compares the whole block with the whole query, and at sentence length a
query of similar length is similar enough to be returned by trigram alone. The test passed with the
leg it was testing removed. The block is now a paragraph, trigram similarity falls below the
threshold, and only the any-term leg can reach it — X14 fires. A mutation row that reports DID NOT
FIRE is not noise; twice in this pass it named a test that was not testing what it said.

**`check.py --fast` under `litkb_test_w2`, run after every fix above** — 32m51s:

```
[PASS] secrets 9.4s · [PASS] ruff 0.3s · [PASS] compile 0.8s
[FAIL] pytest  1975.8s
3 failed, 2730 passed, 25 skipped, 2 xfailed, 74 warnings in 1971.69s
litkb Postgres tests: 282 passed, 3 skipped
```

The same three failures the referee carried, and **no new one**: `test_experiments.py::
test_pointer_paths_resolve[crown_state_model]`, and the two in `test_litkb_inventory.py`. The litkb
Postgres count rises from his 261 to 282 — the twenty-one new tests — with no regression in P1, P2,
P3 or the reconciliation suite (all four were also run on their own after 0019 landed: **444 passed,
5 skipped, 1 xfailed**).

The two `test_litkb_inventory.py` failures (`234 != 224`, and the boundary-pin test beside it) are
**corpus growth, and unrelated to this branch** — the census counts PDFs on disk under `Literture\`, more have landed since it was
pinned, and the branch's diff touches nothing under inventory. They are a re-pin for whoever owns
that census, not a P8 defect. `test_experiments.py::test_pointer_paths_resolve[crown_state_model]`
is the one pre-existing failure this branch is allowed to carry.

### 7.9 What `litkb` must apply at the merge

This branch wrote two migrations and applied them to the worker database `litkb_test_w2` **only**.
`litkb` itself is untouched, and `litkb.db.migrate` requires migrations numbered 1..N without gaps,
so the numbering assumption is stated: **no ref in this repository holds an `0018_*`** (checked
across every branch and tag), and these take 0018 and 0019.

| at the merge | what it does | if it is not applied |
|---|---|---|
| `0018_access_layer.sql` | `check_ws_token`, `promotion_chains`, the seven-form `_feeds_token_ok`, `norm_search_text`, `any_term_query`, two GIN indexes on `blocks` | the read tools fail CLOSED with `no-token-check` (they answer nothing, which is the safe half); four of the seven feeds forms stay invalid; `litkb_search` and prepare's report raise `UndefinedFunction` |
| `0019_prepare_requires_evidence.sql` | `_ws_chains` holds a use with no promotable evidence row | a use with no quote at all prepares clean again |

`py -3.12 -m litkb.db.migrate --db litkb` is the command, and it is Kam's to run. Both are additive:
0018 creates new functions and replaces one validator; 0019 replaces one function body. Neither
touches a table, and neither rewrites a row.

### 7.10 What 0019 broke, and what breaking it found

Migration 0019 is the one change here with reach outside the access layer, and it had it immediately:
**23 of P1's 149 tests failed** the first time the suite ran under it. Not a defect in the migration —
those tests write a use with no evidence row at all and then promote it, which is the convention the
referee proved false. Each of them is about something else (the rebase guards, the embedding guards,
a write in flight, a dependency between a use and its gap), so each gets what it always implied it
had: `_make_promotable(pg, w)` attaches ONE verified quote to the world's own use, and the test's
own subject is untouched.

Two places needed more care, and both are stated because they are the kind of edit that can quietly
weaken a suite:

* `_evidence_world` itself stays **evidence-free**. Three tests assert `count(*) = 0` on its use to
  show that a REFUSED write wrote nothing, and a fixture row would have made "nothing was written"
  unprovable. The two that now start with a row assert the count did not CHANGE (`== 1`), and say so.
* `test_rebase_copies_head_evidence_whose_run_was_superseded` supersedes the file's run, which makes
  evidence anchored in the old run unpromotable — correctly. Its quote is attached in the NEW run,
  so the chain the test is about is still the only one held.

**And the suite found a real defect in 0018.** `test_ingest_installs_a_run_and_makes_it_current`
failed with `permission denied for function norm_search_text` when `litkb_ingest` inserted a block:
the new expression index calls the normaliser, and an index expression is evaluated as the role
doing the INSERT. Stage 5's ingest would have stopped writing blocks the moment 0018 landed. The
GRANT is in the migration and the role census names it. Nobody read that; a test did.

`test_role_privilege_matrix` — the design's own §4.7 census — is updated with the four new grants
(`check_ws_token`, `norm_search_text`, `any_term_query` to reader and writer; `norm_search_text` also
to ingest; `promotion_chains` to the promoter alone). That test exists so that a new grant cannot
arrive unnoticed, and it did its job.

### 7.11 What this pass did NOT do

* The librarian is still **unrun** (section 6 item 2), and the hook is still **not installed
  session-wide** (item 3) — the frontmatter entry is scoped to one agent, not a settings
  registration.
* 0013's promotion chain guard is still **read, not fired** (referee 3.4): it needs a manual
  admission that passes check 4, i.e. a born-digital PDF.
* The extract step is still **substituted** (referee 2.3). The Q3 scoring above re-seeds the same
  way, from the same `.txt` extracts, so it inherits that substitution: the seeded blocks are what a
  paragraph extractor WOULD produce, not what stage 0–5 DID produce.
* `commands.py::_default_connect` still hardcodes `litkb_writer` while the server honours
  `LITKB_READER_ROLE` / `LITKB_WRITER_ROLE` (referee 3.4). Untouched here.
* Design section 9's amendment still needs **Kam's line in `decisions.yaml`**, not a builder's or a
  referee's paragraph. Nothing in this session staged `decisions.yaml`.

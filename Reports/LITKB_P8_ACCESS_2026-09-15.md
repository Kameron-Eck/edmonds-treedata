# litkb P8 — the access layer

Branch `work/20260915-access-layer`, from `work/20260913-literature-kb` at `af57ebb`. Nothing was
merged into this branch and nothing was pushed to `main`.

Design: `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §5, §8, §9, §9.1, §10, §14 P8.
Decisions: `Scripts/decisions.yaml` `litkb-p0-foundation`, §15.13 (D-4), §15.17.
Convention: `Scripts/docs/LITERATURE_CONVENTION.md` (the hunt protocol, rewritten at P3).

**Status of this evidence (CLAUDE.md 3.4c): every number and every verdict below was produced by
the author of the code. No independent referee has run any of it.** What a referee has to do to
break it is listed at the end, and the mini-hunt's one substitution is stated rather than buried.

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
claude mcp add -s user -e LITKB_AGENT=claude -e LITKB_SESSION=default -e PYTHONPATH=D:\edmonds-pipeline\treedata\Scripts\pipeline --transport stdio litkb -- py -3.12 -m litkb.mcp.server
```

Notes a registrar needs:

- `PYTHONPATH` is required **today**: `litkb` is not importable from the installed package —
  `py -3.12 -c "import litkb"` fails, because the editable install was made from a tree whose
  `Scripts/pipeline` has no `litkb`. `pyproject.toml` now lists `litkb.mcp`, so after
  `py -3.12 -m pip install -e .` from a tree that has it, the `-e PYTHONPATH=…` can be dropped.
- Put at least one option (here `--transport stdio`) between the last `-e` and the server name, or
  the name is parsed as another `KEY=value`.
- `LITKB_AGENT` / `LITKB_SESSION` must be set or every write tool refuses `no-labels`. A session
  label that is genuinely per-session is better than `default`; the CLI takes `--session`.
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

1. **No independent referee has run any of this.** Everything above is the author's own measurement
   (3.4c). A referee can reproduce it in one command:
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
   a commit.
8. **`promote.connect()` gained a test-database branch** that logs in as `litkb_test` and `SET ROLE
   litkb_promoter`. `is_test_db()` keys on the `litkb_test` prefix and is never true for `litkb`, so
   it cannot be aimed at the real database — but it is a new path to the promoter's rights, and a
   referee should read it with that in mind.
9. **The workstream `p8-*` rows live only in `litkb_test_w2`.** Nothing in this phase wrote to
   `litkb`, and no promotion was committed against the real repository.

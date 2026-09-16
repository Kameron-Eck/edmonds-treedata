# litkb P8 — independent referee

**Branch** `work/20260915-access-layer`, worktree `D:\edmonds-pipeline\treedata-access`, refereed at
`ab06bd2`. **Referee** Claude Opus 5, a session that wrote none of P8. **Not Kam's sign-off.**
Under review: `Reports/LITKB_P8_ACCESS_2026-09-15.md` (the builder's report and its §6 list of ten
open items), and `Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md` §8 (a real agent's friction list from
the first end-to-end use).

## Verdict — **P8 READY WITH FIXES**

The privilege model holds under every attack I could make on it: no tool reaches the promoter or
ingest credential, a write with a forged token is refused by the database, evidence cannot be
attached to a work the block does not belong to, and a work chain cannot enter main through a
promotion at all. What is not ready is smaller and specific: **read tools do not check the
workstream token**, **the output boundary redacts only registered secrets**, and **three of the
five things the skill tells a reader to do are wrong about the machinery** — every one of them
confirmed by running, not by reading.

| # | Fix | Where | Why it blocks |
|---|---|---|---|
| F-1 | `_candidates` and `_ws_status` must present the token, as every write does | `mcp/server.py:319`, `:332` | a crafted `.litkb-workstream` naming any workstream id reads that workstream's candidates, admissions, attempts and promotions (§3.2) |
| F-2 | The skill's step-2 example `litkb_admit(doi="10.…")` always fails | `.claude/skills/literature/SKILL.md:56` | measured: refused at `check1_study_exists` (§2.2). Print the call that works |
| F-3 | The skill's step-4 `feeds` token `report <FILE>#§<loc>` is rejected by the database | `SKILL.md:102` vs `0005:17` | measured: the use stayed `proposed` with `feeds: invalid tokens` while five others prepared (§3.5) |
| F-4 | `redact()` replaces registered strings only; add the credential *shapes* at the one boundary | `litkb/netutil.py:32` | measured: a pgpass line planted in a block came back verbatim in a search result (§3.1) |
| F-5 | "writes the promotion report onto the work branch" — it does not; prepare records the path and writes nothing | report §1, `SKILL.md:117` | measured (§5): no file appeared. Either write it or stop saying it |

None of the five needs a migration. F-1 and F-4 are a few lines each; F-2 and F-3 are edits to one
markdown file (F-3 alternatively a migration, if the richer vocabulary is wanted — Kam's call, §4.6).

---

## 1. Gold, frozen first

`Reports/gold/p8_gold_2026-09-15.json`, committed at `b2fef5a` **before any tool ran, any block was
seeded, or any test was executed**.

**sha256 `77fb53a1d52eac9c34c0c7c6cc5d760c869453da4959a8cdb1870a76c2930949`**

Three real questions from `Reports/FRAMEWORK_GAPS_SPATIOTEMPORAL_CONSISTENCY_2026-09-11.md` — gap
ledger rows 4, 17 and 18 — each with the work that answers it and the verbatim passage, located by
grep over the `.txt` extracts under `D:\edmonds-pipeline\Literture\Validation` and nothing else. The
file also carries the skill's prescribed tool sequence copied as written, and **four predictions
recorded before running** (P1–P4), so that what follows can be scored rather than narrated.

One check on the honesty of the seeding, made before choosing: the **real `litkb` holds 0 rows in
`blocks` and 0 in `extraction_runs`** (read-only, as `litkb_reader`). No search result could have
informed the gold, and — the more important consequence — `litkb_search`'s block leg returns nothing
at all in production today. P8's value is bounded by P4/P5, which have not run into the live base.

Quotes preserve the extract's own mojibake (Bellettini's `χ_C` renders as `wC`, Rosychuk's `fi` as a
replacement character). A quote tidied up by the referee would not be verifiable against the block
the pipeline actually stores, and §2.4 below is what that decision bought.

---

## 2. The skill run as a user would run it

Through a real MCP `ClientSession` over the SDK's transport — the same `initialize` handshake and
`call_tool` envelope a registered stdio server gets — against `litkb_test_w2`, in a throwaway git
worktree under `%TEMP%`. Nothing was written to `litkb`. Seeding is stated in §2.3.

### 2.1 Steps 1–3: open, admit, acquire — all three works, first attempt

`litkb_ws_open` → three × `litkb_admit` (DOI + title + authors + year) → three × `litkb_acquire`
binding the real PDF from `Literture\Validation`:

| gold | DOI | admit | acquire |
|---|---|---|---|
| Q1 Bellettini 2002 | `10.1006/jdeq.2001.4150` | `admitted`, key `Bellettini_2002_total-variation-flow-rn` | `ok` |
| Q2 Jackson 2011 | `10.18637/jss.v038.i08` | `admitted`, key `Jackson_2011_multi-state-models-panel` | `ok` |
| Q3 Rosychuk 2003 | `10.1002/sim.1473` | `admitted`, key `Rosychuk_2003_bias-correction-two-state` | `ok` |

Worth recording against the machinery: Bellettini's PDF is the one the tracker (row 357) flags as
having an "UNREADABLE" text layer, and the first-page title binding passed on it. The tracker's word
is too strong — the prose extracts fine, it is the Greek and the ligatures that come out as
replacement characters. That is the same defect §2.4 turns into a search miss, not a loose binder.

### 2.2 Prediction P4 — the skill's own step-2 shape fails. CONFIRMED

`litkb_admit(doi="10.1006/jdeq.2001.4150")`, exactly as `SKILL.md:56` prints it:

```
"outcome": "refused", "refused_at": "check1_study_exists",
"reasons": ["doi 10.1006/jdeq.2001.4150: no claimed record to compare with the registry and no bound file",
            "registry admission: no doi, arxiv or isbn identifier was confirmed by a registry"]
```

The rule is right (a DOI alone proves only that *some* work exists). The skill is wrong, and so is
the CLI's advertised `--doi`: the linkage review met this as §8.5 and P8 reproduces it on the MCP
surface. The remedy — add `--title`, `--authors`, `--year` — is still not in the message. **F-2.**

### 2.3 The substitution, stated (3.4c)

P5 has not run into `litkb_test_w2`, so I seeded the blocks myself, from the **full `.txt` extract of
each work**: split on blank lines, wrapped lines joined by one space, no cleaning of the PDF's own
mojibake — 872 / 310 / 275 blocks. That is what a paragraph extractor would produce and it is the
honest denominator for a top-5 claim; seeding only the gold passages would have made §2.4 circular.
It is still a substitution, and the unsubstituted gate needs stage 0–5 run into a throwaway base.

### 2.4 The three questions

| gold | `litkb_search` for the frozen query | rank of the gold passage | `record_use` (gold quote) | `record_use` (paraphrase) |
|---|---|---|---|---|
| Q1 | `does not deform its boundary but only decreases its height` | **1 of 1** | `quote_verified: true` | refused `quote-not-in-block` |
| Q2 | `product of probabilities of transition between observed states` | **1 of 2** | `quote_verified: true` | refused `quote-not-in-block` |
| Q3 | `naive estimators overestimate the transition probabilities misclassification` | **not in the top 5 — MISS** | `quote_verified: true` (after re-query) | refused `quote-not-in-block` |

Refusal message, verbatim, for every paraphrase:

> the quote is not in that block's text. A use is evidenced by a quote the database can find at the
> offsets recorded — paraphrase in the statement, never in the quote.

**The Q3 miss is not the server's fault, and that is the point.** The block holds
`misclassi<FFFD>cation` and `this overesti- mate increases`, because that is what the PDF's text
layer renders. The query used the framework's own spelling. Probed against the same index:

| probe | rank of the gold block |
|---|---|
| `The NEs overestimate the transition probabilities` | 3 of 5 |
| `misclassification probabilities increase` | not returned |
| `misclassi cation probabilities increase` | 2 of 5 |
| `naive estimators on average overestimate` | not returned |

So the passage is reachable **only** by a caller who already knows how the extractor mangled the
word. The skill's advice — "try the author's own wording" — is exactly the advice that fails here,
because the author's word is not what is stored. With the vector leg off there is no recovery path.
This is measured evidence for §6 item 5 being more than a performance note, and it is the strongest
argument that P8's usefulness is capped by P4/P5 and P7, not by P8.

---

## 3. Breaking it

### 3.1 A secret in a search result — **NOT held (F-4)**

A block containing `localhost:5433:litkb:litkb_writer:<a password>` was planted in the seeded corpus
and returned by `litkb_search` at rank 5. **The pgpass line came back verbatim; no `<KEY>` appeared.**

Mechanism: `netutil.redact` (line 32) is `str.replace` over `_SECRETS`, a list populated by
`add_secret`. `_session()` arms it with the workstream token and with nothing else, so the boundary
is a *token* redactor, not a credential redactor. The builder's kill 3 is true as stated — it plants
the armed token — and passes; it simply does not test this. The server docstring's "the one thing between
a route's own words … and the model's context" reads wider than what the function does.

Cheap fix, at the boundary that already exists: give `redact` the pgpass shape, `password=` /
`PGPASSWORD=`, and long hex runs. One function, already mutation-covered by X1/X2.

### 3.2 A read tool with another workstream's token — **NOT held (F-1)**

A `.litkb-workstream` was written in a scratch directory naming the **real** workstream id with a
**forged** token (64 zeros), and `LITKB_WORKTREE` pointed at it.

- `litkb_ws_status` → **`ok: true`**, full status returned. Same for `litkb_candidates` by
  construction: both call `_session()` for the id and then query `WHERE workstream_id = %s`, never
  presenting the token.
- `litkb_record_use` with the same forged token → refused. The database is what refuses it:
  `InsufficientPrivilege: litkb: workstream token refused for workstream 01a0a7da-…`.
- With the file deleted → `no-workstream`, naming `litkb_ws_open`, for every write tool.

So writes are safe and reads are not. **Workstream ids are not secret** — `LITKB_LINKAGE_REVIEW_2026-09-15.md`
prints its own on line 4 of a tracked report, and `litkb_ws_open` returns the id by design. So the
attack needs no secret at all: a file naming a published id and any string as its token reads that
workstream's candidates, admissions, acquisition attempts and promotions. Design §5's whole premise
is that the token is what authorises the workstream. One `SELECT litkb._require_ws_token(%s, %s)`
before the two read queries closes it.

A second, smaller thing came out of the same call: the write refusal reached the model as
`refused: "error"` with a raw psycopg message and a `CONTEXT: PL/pgSQL function
_require_ws_token(uuid,text) line 1` line. `_guarded`'s catch-all is doing its job, but the one
refusal the design most wants stated well arrives as an opaque `error`. Mapping `InsufficientPrivilege`
on that path to a `bad-token` code is a two-line change.

### 3.3 Evidence from a different work — **HELD**

Two attempts, both against a Jackson block while the use was about Rosychuk:

- naming the other work → refused **`work-mismatch`**: "the block belongs to
  `Jackson_2011_multi-state-models-panel`, not `Rosychuk_2003_bias-correction-two-state`: evidence
  must come from the work the use is about."
- naming **nothing** (the skill's own signature has no `work_key`) → accepted, and the use was
  recorded against **Jackson**, the block's work. There is no path by which a quote from B evidences
  a claim about A, because the use's work is *derived from the block* and never taken from the
  caller. This is the strongest single property in the file and it is not stated in the builder's
  report; it should be.

### 3.4 An unapproved manual admission through promotion — **first layer fired; second layer only read**

`litkb.write_proposal('work', …)` is refused outright by the writer role: *"litkb: write_proposal
takes gap or use (got work)"*. A work, identifier or file chain cannot be created that way at all.

I then tried the real route, `admit.admit_manual` as `litkb_test` against `litkb_test_w2` with a
scanned paper under a scratch literature root. It was **refused at `check4_manual`** — no proposed
work chain was ever created, and `_ws_chains` shows no `work` / `identifier` / `file` chain to test
the guard against. That is the same binder mechanism the linkage review met as §8.4, reproduced here
on a real scanned PDF rather than saved HTML: a first-page text layer is required and a scan has none.

So, stated exactly: **0013's chain guard** — "a work, identifier or file enters main only through
`litkb.approve_admission`, never through promotion" — **was read in the migration, not fired.** What
was fired is the layer in front of it. A referee who wants the guard itself shown needs a manual
admission that passes check 4, i.e. a born-digital PDF, and should run it on a worker other than the
one `check.py` is using.

One reason this was awkward is itself a finding: **`commands.py::_default_connect` hardcodes
`litkb_writer`** while the MCP server honours `LITKB_READER_ROLE` / `LITKB_WRITER_ROLE`. The two
halves of the access layer do not agree on how they are pointed at a throwaway database, so the CLI
half of the skill (manual admission, approval) cannot be driven without the writer passfile.

### 3.5 The vector flag with no vectors — **HONEST**

`LITKB_VECTOR_SEARCH=1` against an empty `embeddings` table returns
`legs: ["lexical", "trigram"]` and

> `REQUESTED but NOT RUN: the embeddings table holds 0 rows and the vector leg lands with P7. These hits are lexical.`

It counts the rows rather than asserting, and it never claims a leg it did not run. Kept.

One thing the flag conceals, found by reading `_search`: the **trigram leg is not an independent
retrieval leg**. Both legs are built from the *same* SQL result, ordered `lex DESC, trg DESC` and cut
at `LIMIT n`, so reciprocal-rank fusion re-ranks a lexical candidate set. A block that only trigram
would find, below the lexical cut, is never retrieved. Harmless at 1,457 blocks; worth stating before
"fused by reciprocal rank" is quoted as two-leg recall.

### 3.6 Predictions P2 and P3, run

One `litkb_propose_promotion` over six uses and three gaps; `outcome: prepared`,
`promotion_id 01a0a7dd-…`, `heads {gap: 3, use: 6}`.

| use | evidence rows | feeds | state after prepare |
|---|---|---|---|
| gold Q1 | 1 | `gap row 4` | **prepared** |
| gold Q2 | 1 | `gap row 17` | **prepared** |
| gold Q3 | 1 | `gap row 18` | **prepared** |
| cross-work control | 1 | — | **prepared** |
| **a use with no quote at all** | **0** | — | **prepared** |
| **the skill's own feeds token** | 1 | `report LITKB_P8_REFEREE_2026-09-15.md#§2` | **proposed — HELD** |

**P3 confirmed.** A use with zero `use_evidence` rows prepares clean. `_ws_chains` counts rows that
are `NOT promotable`; zero rows is zero bad rows (`0005:78-85`, unchanged in `0013:575-582`). See §4.2.

**P2 confirmed.** The chain problem, verbatim: `feeds: invalid tokens {"report
LITKB_P8_REFEREE_2026-09-15.md#§2"}`. A session that follows `SKILL.md` step 4 as printed writes a
use that will not promote, and finds out at step 5. **F-3.**

### 3.7 The librarian's reach — **bounded, with one edge**

`tools: mcp__litkb, Read, Grep, Glob`. Checked against the subagent documentation: `mcp__<server>` is
a valid server-wide grant; `mcpServers:` is a recognised key; a `tools:` list is an **allowlist**, so
the librarian inherits no `Bash`, no `WebFetch`/`WebSearch`, no paper-search server, and no
user-scope MCP server it does not name. It cannot reach a fetcher. The definition matches its own
prose.

The edge: `Read`, `Grep` and `Glob` can open `.litkb-workstream` and any `*.pgpass` the user can
read. Nothing in the librarian's brief tells it not to, and no hook stops it. It is not a privilege
escalation — the token is already in its worktree — but combined with §3.1 (the boundary does not
redact credential *shapes*) it is the one way a credential could reach a transcript through the
librarian. A line in the brief, or removing `Read`/`Grep`/`Glob` (it answers from the base, by its
own rules), closes it.

Still unexercised, as the builder says: no librarian agent has been run, because the server is not
registered. I did not register it.

---

## 4. The friction list, classified

| § | What | Class | Cheapest fix |
|---|---|---|---|
| 8.1 | steps 4 and 5 have no CLI | **P3 defect, largely closed by P8** | the MCP tools now *are* steps 4 and 5. Remaining gap is a non-MCP session: add `litkb use record` to `commands.py` mirroring `_record_use`. The promoter credential for prepare is correct by design, and P8 hides it behind a subprocess |
| 8.2 | "a use with no verifiable quote is refused at prepare" | **convention error — CONFIRMED by running** (§3.6) | see §4.2 |
| 8.3 | a verified quote needs stage 5 | **P4/P5 defect**, and the binding constraint on P8 | a per-file `litkb extract` driving stage 0→5 from a bound PDF. Until then `litkb` holds 0 blocks and `litkb_search` can only answer nothing |
| 8.4 | documentation cannot be admitted | **P2 vs convention — Kam's call** | either delete the convention's promise, or a `--manual --url` route that binds saved HTML against a text check instead of a PDF first page. Do not paper over it by generating a PDF |
| 8.5 | `admit --doi` alone fails, message unhelpful | **P2 message defect + P8 skill defect** (§2.2) | one sentence in the refusal naming `--title/--authors/--year`; correct `SKILL.md:56`. **F-2** |
| 8.6 | `feeds`: 3 tokens enforced, 7 documented | **P8 skill defect + convention error — CONFIRMED** (§3.6) | cheapest is to cut the skill and convention to the three forms. But that permanently loses "what was this used for" for report-level uses — which is the field's purpose — so the better fix is a migration extending `_feeds_token_ok`. Kam's call; the skill edit is the cheap one, the migration the right one. **F-3** |
| 8.7 | open-access route missed 16 of 24 | **P2 acquire defect** | a DOI→arXiv lookup and an `arxiv` identifier fallback; that alone recovers S2AND and Enamorado by the review's own list |
| 8.8 | Anna's Archive unused | not a defect | the counter guard is simply unexercised |
| 8.9 | one `rm` inside `Literture\` | not a P8 matter | recorded by the author against himself; the right response is the rule, not a code change |

### 4.1 §8.2, confirmed against migration 0005 — and by running

Read: `_feeds_token_ok` and `_ws_chains` are defined in `0005_promotion.sql`; `_ws_chains` is
redefined in `0013_admission.sql` and the evidence clause is unchanged:

```sql
SELECT count(*) INTO v_bad FROM use_evidence_status s
 WHERE s.use_version_id = ANY (v_ids) AND NOT s.promotable;
IF v_bad > 0 THEN … 'evidence: %s row(s) unverified …'
```

Run: a use with no `use_evidence` row reached `prepared` (§3.6). **The convention's sentence is
false, exactly as the linkage review says.** The reviewer's reading is confirmed on both legs.

### 4.2 Which way to fix it is not the referee's call

Two coherent positions. (a) A use with no quote is a *claim without evidence* and should never
promote — add `IF cardinality(v_ev) = 0 THEN problems := … 'evidence: none'`. That invalidates all 15
uses the linkage review wrote and every use written before stage 5 exists, which is most of them.
(b) A use with no quote is a weaker but legitimate record, and the convention should say
"a use whose quote the database *cannot verify* is refused; a use with no quote carries no evidence
and is marked as such." That is one sentence and no migration. Kam decides; (b) is what the machinery
already means.

---

## 5. Design §9 — amend it

§9: "`approve`, `promote prepare` and `promote commit` are not exposed to agents … the MCP server
never holds the promoter or ingest credential." P8 exposes `litkb_propose_promotion`.

**Recommendation: AMEND §9 to permit prepare from an agent, under three conditions.** The reasons are
measured, not argued:

- **The credential clause is kept exactly.** `_propose_promotion` runs `py -3.12 -m litkb promote
  prepare` as a subprocess; the server's `_role()` resolves only `litkb_reader` / `litkb_writer`, and
  the promoter passfile is opened by a process that exits.
- **Prepare mutates no git.** `promote.prepare` records a branch-head sha and a report path; the only
  `git fetch` in `promote.py` is inside `commit()`, and the module has no `push`. Verified: after a
  successful prepare through the tool, the test worktree's `git log` was unchanged at its single base
  commit.
- **Nothing enters main.** Prepare moves the workstream's own proposed versions to `prepared`. Work,
  identifier and file chains cannot even be created by the writer (§3.4), and `promote commit` and
  `approve` are absent from the tool list.
- **The `repo` parameter is bounded.** Pointed at an unrelated git repository, prepare refused: *"no
  `.litkb-workstream` in …; run `litkb ws open <slug>` first."* An agent cannot aim it elsewhere.

Conditions on the amendment: (i) `report_path` is agent-controlled, but measured: **prepare writes no
file**. It stores the path in `promotions.report_path` and `cmd_promote` reads it straight back out;
after a successful prepare naming `<worktree>/promotion.md`, no such file existed. So the parameter
is a recorded string, not a write primitive — which also means the builder's "writes the promotion
report **onto the work branch**" (report §1, and `SKILL.md` step 5) is not what happens, and one of
those two sentences should change. (ii) `commit` and `approve` remain absent, and the reason is written in §9 rather
than inferred. (iii) The amendment is recorded in `decisions.yaml` at Kam's merge, because it changes
the access surface, not just the code.

The alternative — prepare only at the CLI — buys nothing: the same agent runs the same CLI through
Bash, with a worse record. What P8 does is make the step legible and logged.

---

## 6. Reproduction, gates, and the tree

### 6.1 Mutation rows X1–X6 — 6 of 6 fired, in my words

`LITKB_TEST_DB=litkb_test_w2 … litkb_p2_mutations.py --only X1,X2,X3,X4,X5,X6` →
**`6/6 mutations fired; baselines passed`**, every file restored sha256-equal, and
`git status --short` clean in this worktree afterwards.

| row | the guard I removed | what broke, and which test noticed |
|---|---|---|
| X1 | the `redact()` call inside `_out` | the armed token comes back whole in a refusal result; the planted-secret test fails |
| X2 | the `add_secret()` inside `_session` | redaction still runs but with an empty secret list, so the same test fails from the other side — this is the row that proves the boundary is *armed*, not merely present |
| X3 | label normalisation stops stripping invisible characters | a label made only of zero-width characters is no longer blank, so a write records an agent/session pair no later comparison can match; three cases fail |
| X4–X6 | `litkb_admit` / `litkb_acquire` / `litkb_record_use` invent labels instead of demanding them | each write goes through with no real agent or session; the matching parametrised refusal test fails |

**What the rows do not cover**, and I think this matters more than the six that do: there is no
mutation row for the workstream-token check on read tools (§3.2 shows it is absent — a mutation row
would have had nothing to remove), none for the `work-mismatch` check (§3.3, the strongest property
in the file), and none for the `feeds` validator. A guard with no row is a guard not yet shown to be
load-bearing; two of P8's four best properties are in that position.

### 6.2 `check.py --fast` under `litkb_test_w2`

`LITKB_TEST_DB=litkb_test_w2 PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/check.py --fast`,
30m36s on a machine also running other worktrees' suites:

```
[PASS] secrets 9.9s · [PASS] ruff 0.3s · [PASS] compile 0.8s
[FAIL] pytest  1841.0s
3 failed, 2698 passed, 25 skipped, 2 xfailed, 74 warnings in 1836.63s
litkb Postgres tests: 261 passed, 3 skipped
```

Three failures, each named:

| failure | mine? | what it is |
|---|---|---|
| `test_experiments.py::test_pointer_paths_resolve[crown_state_model]` | no | the one pre-existing failure this branch is allowed to carry |
| `test_litkb_inventory.py::…reproduces_the_committed_corpus_census` | no | `234 != 224` — the census counts PDFs on disk under `Literture\`; more have landed since it was pinned |
| `test_litkb_inventory.py::test_the_boundary_pins_really_are_the_nearest_pages` | no | **the builder's run reported only one inventory failure; this is a second.** Same module, same corpus. I did not chase its cause beyond establishing that `git diff --name-only af57ebb..ab06bd2` touches nothing under inventory, so it is not this branch — but it is one more row for whoever re-pins that census, and the builder's report should not be read as saying there is only one |

`test_status_discovery.py::test_path_insert_ledger` **passes** — the builder's fix at `ab06bd2` holds.

Two honest qualifications on this run. **I did not set `LITKB_LIVE=1`**, so the three live P8 tests
(the mini-hunt, the quote kill's database half, `promote commit` against a scratch repository) were
deselected here; I exercised all three by hand instead, through the MCP client (§2, §3.6). And the
suite's own line says it: `261 passed, 3 skipped — 3 SKIPPED: litkb server/role/psycopg absent, so
those guards were NOT tested`. A green ladder is not a claim about those three.



### 6.3 The hook — installed, fired live, and §9.1's kill is now shown

Hand-fed the documented `PreToolUse` payload, `litkb_guard.py` behaves as §3 says: a `Read` of a PDF
under the (env-redirected) literature root emits `hookSpecificOutput.additionalContext` naming the
file and the skill; the identical payload with a `.litkb-workstream` present in `cwd` produces
nothing.

Then installed for real, in a scratch Claude Code project under `%TEMP%` — never the user's config —
with `.claude/hooks/litkb_guard.py`, a fake `Literture\Validation\` tree holding a one-page PDF, and
`.claude/settings.json` carrying §3's `Read|Bash|PowerShell` matcher with §3's command **verbatim**
(`py -3.12 ${CLAUDE_PROJECT_DIR}/.claude/hooks/litkb_guard.py`), `LITKB_LITERATURE_ROOT` set in the
launching shell. Three live `claude -p` sessions, each reading that PDF:

| state | result |
|---|---|
| hook entry present, no `.litkb-workstream` | **warned** — the session repeated the guard's sentence verbatim, `litkb: `Fake_2026_paper.pdf` is being read straight off disk…` |
| hook entry removed | **NONE** |
| hook entry present, `.litkb-workstream` in the project root | **NONE** |

**That is design §9.1's kill, fired in a live session, with its negative control and its
inside-a-workstream control.** It closes the builder's §6 item 3. The scratch project was deleted;
`~/.claude/settings.json` contains no litkb entry (checked before and after).

One installation fact worth putting in §3, because it cost me a false negative first time round: a
`.bat` wrapper in the `command` field is **not** executed by the hook runner — with the wrapper in
place nothing ran at all, and a marker write inside it never fired. §3's literal `py -3.12 <path>`
form is the one that works, and the guard reads `LITKB_LITERATURE_ROOT` from the inherited
environment rather than needing a wrapper to set it.

### 6.4 Tracking and secrets

`git ls-files .claude` → exactly three files: `agents/librarian.md`, `hooks/litkb_guard.py`,
`skills/literature/SKILL.md`. **No settings file is tracked**, and the `.gitignore` block that
un-ignores those three subtrees keeps `/.claude/*` ignored otherwise, so a `/permissions` write or a
hook registration cannot be swept into a commit. `.litkb-workstream` is ignored (`.gitignore:154`).

`git log -p` over `96a5556..HEAD`: every hit for `passfile` / `password` is prose or a symbol
(`promoter_passfile()`), no pgpass-shaped line, no long hex value, no token literal. The registry
cache is recorded Crossref metadata.

The builder's §6 item 7 side effect stands and is worth repeating at the merge: the main worktree
holds an untracked `.claude/skills/paper-search/SKILL.md` which stops being ignored when this
`.gitignore` lands. Commit it deliberately or ignore it by name.

### 6.5 What I did not touch

`litkb` was opened once, read-only, as `litkb_reader`, to count `blocks` and `extraction_runs`. Every
write went to `litkb_test_w2`. No other worktree, no branch but this one, no file under
`D:\edmonds-pipeline\Literture\` created, moved or deleted. The MCP server was not registered in any
Claude Code config. No token was printed.

---

## 7. What still blocks acceptance, after this pass

1. **F-1 and F-4** — the two code fixes above. Neither is deep; both are properties the report claims.
2. **The librarian remains unrun** (§3.7). The definition is valid; that is all this pass can say.
3. **0013's promotion guard is still only read, not fired** (§3.4) — it needs a manual admission that
   passes check 4.
4. **The extract step is still substituted** (§2.3) — and §2.4 shows the substitution is where the
   interesting failure lives. Running stage 0–5 into a throwaway base and re-scoring this gold is the
   single most informative thing left to do.
5. **Mutation coverage of the access-layer guards** (§6.1), not just the label and redaction guards.
6. **§9's amendment** needs Kam's line in `decisions.yaml`, not a referee's paragraph (§5).

---

*Referee: Claude Opus 5 — session https://claude.ai/code/session_015MUcyGTfX2koRdYAjW5kED.
Gold `Reports/gold/p8_gold_2026-09-15.json`, sha256
`77fb53a1d52eac9c34c0c7c6cc5d760c869453da4959a8cdb1870a76c2930949`, committed at `b2fef5a` before
any of the above was run.*

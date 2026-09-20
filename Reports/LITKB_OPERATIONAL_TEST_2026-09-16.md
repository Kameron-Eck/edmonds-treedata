# litkb — the operational test: a research session, through the MCP server, on the live corpus

Worktree `D:\edmonds-pipeline\treedata-access`, branch `work/20260915-access-layer`, HEAD
`fd59bc3`. Database: **live `litkb`** — 102,008 blocks, 242 extraction runs, 447 works
(`select count(*)` as `litkb_reader`, 2026-09-16). Migrations 0018 and 0019 are applied
(`check_ws_token`, `promotion_chains`, `norm_search_text`, `any_term_query` present;
`_ws_chains` contains `no-verified-evidence`).

This is not a referee pass on P8's code. It is the other question: **can a session do a
literature task through this system today?** I acted as the user — read
`.claude/skills/literature/SKILL.md` and followed it — and fixed nothing.

**How the tools were driven.** The server was run as a **real stdio subprocess**
(`py -3.12 -m litkb.mcp.server`, cwd = the worktree, `PYTHONPATH=<worktree>\Scripts\pipeline`,
`LITKB_WORKTREE=<worktree>`, `LITKB_AGENT=optest`, `LITKB_SESSION=optest-1`, `LITKB_DB=litkb`,
`PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`), driven by `mcp.client.stdio.stdio_client` +
`ClientSession` — the client pattern of `qc/test_litkb_p8.py::mcp_roundtrip`, but over a pipe
rather than the in-memory stream pair, because a pipe is what a registered server gets. The
handshake returned `server: litkb, version: 0.1.0` and exactly the nine tools; the first call,
`litkb_work({})`, returned `{"ok": false, "refused": "no-selector", …}`, which proves the
transport before anything was written.

Workstream **`op-test-1`**, id `01a0aa5c-382d-7990-ad7b-b7bd5cd5bb0a`, opened through
`litkb_ws_open` and **left OPEN** for the referee. `.litkb-workstream` was never read and is
ignored by `.gitignore:154`.

**Which numbers came from where.** Every rank, refusal code and use id below is `litkb_search`
/ `litkb_record_use` output. `psql` was used twice, and only as diagnosis: to read the live
block text before choosing a quote, and to establish *why* `litkb_work` fails. Both are
labelled where they appear.

---

## 1. The three P8 gold questions, on the real corpus

Gold: `Reports/gold/p8_gold_2026-09-15.json` (frozen; not edited). `litkb_search` at the tool's
**default `limit=10`**, `scope="all"` — the call a session actually makes. Gold's own PASS bar
is "in its top 5".

| gold | framework § / gap row | search rank of the gold block | work, page, block |
|---|---|---|---|
| Q1 | §16.2 / row 4 | **1** | `Bellettini_2002_total-variation-flow-rn` p3, `01a0aa23-e991-7c39-a3a6-07e7cc057479` |
| Q2 | §19.1 / row 17 | **2** | `Jackson_2011_multi-state-models-panel` p3, `01a0aa25-a961-7f42-b039-742c4f5931ff` |
| Q3 | §19.1 / row 18 | **2** (also 3 and 6 — same sentence, three blocks) | `Rosychuk_2003_bias-correction-two-state` p16, `01a0aa27-2f48-7361-bbff-ee8496805098` |

**The baseline, stated carefully**, because it is easy to cite the wrong column. P8 report §7.7
scores the same three gold queries on a re-seed of the `.txt` extracts into `litkb_test_w2` —
**1,938 blocks, the P8 author's own pass** (the referee's was 1,457, and the referee's ranks are
not in anything read here). Its table has two columns: **before** the P8 fixes, 1 / 2 / MISS;
**after** them, **1 / 1 / 3**. The code tested here is `fd59bc3`, which is the *after* column. So
the comparison that means anything is **seeded post-fix 1 / 1 / 3 → live 1 / 2 / 2**: Q2 loses a
rank, Q3 gains one, and all three clear gold's top-5 bar on a corpus 53× larger. Q1 and Q2 each returned their work's own neighbouring
pages in the next slots; Q3 returned the Rosychuk passage three times, once per extraction of
the same page.

### 1.1 The gold quote is refused — and the reason is neither the system nor the gold

`litkb_record_use` with the gold `verbatim_passage` and the gold block, for all three:

```
{"ok": false, "refused": "quote-not-in-block",
 "message": "the quote is not in that block's text. A use is evidenced by a quote the database
  can find at the offsets recorded — paraphrase in the statement, never in the quote.",
 "block_id": "…", "work_key": "…"}
```

The gold was authored by grep over the `.txt` extracts under `Literture\Validation`, and its
`_quote_rule` deliberately preserves **that extractor's** mojibake. The live blocks came from
stage 0–5 (`extractor` = `docling` / `grobid`), whose text layer renders the same characters
differently. Character for character (live text read by `psql`):

| gold | gold says | the live block says |
|---|---|---|
| Q1 | `u0 � wO`, single spaces at the line breaks | `u0 ¼ wO`, `\r\n` at the line breaks |
| Q2 | `… observed states, over all individuals …` | `… observed states,\r\nover all individuals …` |
| Q3 | `overesti- mate`, `misclassi�cation` | `overestimate`, `misclassiÿcation` |

`_record_use` locates the quote with a literal `text.find(quote)` (`server.py:592`) — no
whitespace or unicode normalisation, unlike `litkb_search`, which reads both sides through
`litkb.norm_search_text`. So a quote that is right about the **paper** and wrong about the
**block** is refused. That is the correct behaviour for evidence integrity: the offsets the
database re-checks have to be offsets into the stored text. The operational consequence is a
rule the skill does not state — **copy the quote out of the search result's `text` field, never
out of a PDF, a rendered view, or another extraction.**

### 1.2 The live quote verifies; the paraphrase is refused

So each gold question was recorded twice more: once with the block's own bytes, once with the
gold's `paraphrase_that_must_be_refused`.

| gold | live verbatim quote (copied from the `litkb_search` result) | result |
|---|---|---|
| Q1 | `In Section 8, we characterize all bounded connected subsets O of R2 for` ⏎ `which the solution of (1) and (2) with u0 ¼ wO does not deform its boundary` ⏎ `but only decreases its height.` | `quote_verified: true`, chars 652–832, use **`01a0aa5d-45a4-76ff-b555-5c22bfabecce`** |
| Q2 | `The full likelihood is then the product of probabilities of transition between observed states,` ⏎ `over all individuals i and observation times j:` | `quote_verified: true`, chars 0–144, use **`01a0aa5d-477b-7ccd-b587-f002d555513b`** |
| Q3 | `The NEs overestimate the transition probabilities and this overestimate increases as the misclassiÿcation probabilities increase.` | `quote_verified: true`, chars 1170–1299, use **`01a0aa5d-485c-7dbc-94f5-cd006bd553ed`** |

All three **paraphrases were refused**, with the same `quote-not-in-block` code and message as
above, naming the quote. Gold's `paraphrase_refuse` criterion: PASS ×3.

Refusals wrote nothing: **twelve** `litkb_record_use` calls across §1 and §2 (three gold quotes,
three live quotes, three paraphrases, three fresh), **six refused**, and `litkb_ws_status`
afterwards reported `use: 6`, not 12.

`feeds` used: `framework §16.2; gap row 4` (Q1), `framework §19.1; gap row 17; narrative §4`
(Q2), `framework §19.1; gap row 18; narrative §3` (Q3). All accepted — the 0018 seven-form
vocabulary is live in `litkb`.

---

## 2. Three fresh questions the framework actually raises

Each is a question in the open half of the framework, searched cold and answered from a held
paper. Sources are `D:\edmonds-pipeline\treedata-litkb\Reports\`.

### F1 — framework §19.6, gap ledger row 20 (the dependence half)

> Our per-cell canopy chain has first-order dependence. Can the Bernoulli CUSUM of §2.2 be kept
> by adjusting its control limits for autocorrelation, or does dependence require a different
> chart?

§19.6 asserts that adjusting limits is "not an efficient approach" and that this "retires the
§19.3 compromise". That is a claim the layer's detector design rests on, so it needs the
passage.

* **Search** `Markov binary CUSUM chart log-likelihood ratio statistic two-state Markov chain first-order dependence` — Mousavi_2009 took ranks **1, 2, 3, 5, 6** of 10. Chosen block: **rank 2**.
* **Passage**, `Mousavi_2009_cusum-chart-monitoring-proportion`, **page 2**, block `01a0aa26-6bae-73e0-97fa-8bf3eb8df88c`:

  > It is shown that both the Shewhart p-chart and the most efficient chart for independent
  > observations, the Bernoulli CUSUM chart, are not robust to autocorrelation, and that
  > adjusting the control ⏎ limits of these traditional charts to account for the autocorrelation
  > is not an efficient approach.

* **Verification:** `quote_verified: true`, chars 326–621. Use **`01a0aa62-343e-79d5-875e-f35e332bcb7b`**, kind `negative result`, feeds `framework §19.6; gap row 20; narrative §7`.

### F2 — framework §19.2, gap ledger row 19

> In fitting the development kernel `D_k(τ)·R(d)` as a distributed-lag regression, what does the
> choice of the lag basis matrix `C` actually impose on the fitted lag curve?

The answer decides whether §17.4's histogram kernel and §14.6's two-term family are rival
estimators or nested models — i.e. whether row 19's one-vs-two-term test is a legitimate
comparison.

* **Search** `the choice of the basis to derive C can be considered as the application of a constraint to the shape of the distributed lag curve` — **rank 1**.
* **Passage**, `Gasparrini_2010_distributed-lag-non-linear`, **page 3**, block `01a0aa25-193c-7138-9840-f194da3ca4bf`:

  > e choice of the basis to derive C can be considered as the application of a constraint to the
  > shape of the ⏎ distributed lag curve described by bˆ

* **Verification:** `quote_verified: true`, chars 0–145. Use **`01a0aa62-34f7-7baf-b380-58757b756807`**, kind `method`, feeds `framework §19.2; gap row 19; narrative §5`.
* **The quote starts mid-word.** The extractor's block boundary cut "The" to "e", and this is the
  *only* block in the corpus carrying that sentence (checked by `psql` over every
  Gasparrini_2010 block matching `%choice of the basis%` — one row). Friction item 7.

### F3 — framework §5.1 and narrative §8, gap ledger row 6

> §5.1 scores the layer on the certified strata as apparent error plus a per-cell covariance
> penalty `Ω`. What is the quantity that penalty estimates, and in which direction does the
> unpenalised number err?

Row 6's whole argument — sum `Ω` per stratum, never citywide — depends on the sign.

* **Search** `expected optimism of the apparent error rate downward bias covariance penalty` — Efron_1986 took ranks **1–8**. Chosen block: **rank 4**.
* **Passage**, `Efron_1986_how-biased-apparent-error`, **page 3**, block `01a0aa24-e846-765f-9fe0-4e95bb8c105a`:

  > This section considers estimating the expected optimism of ⏎ the apparent error rate, in other
  > words the downward bias of ⏎ err as an estimate of the true error rate.

* **Verification:** `quote_verified: true`, chars 0–166. Use **`01a0aa62-3555-7177-bcb5-4c7c65f946ef`**, kind `theorem`, feeds `framework §5.1; gap row 6; narrative §8`.
* Ranks 4 and 6 of that query are the **same passage twice**, from `docling` and from `grobid`,
  both flagged `canonical`. Friction item 8.

### 2.1 Three more the framework raises that NO held paper could answer

Searched, not answered. Nothing was fetched — no archive, no Sci-Hub, no web (the skill's hunt
step was not the natural next move inside a test of the access layer, and this report is the
recorded gap instead).

| question | framework § / row | what search returned | why |
|---|---|---|---|
| Across millions of cells, is the false-alarm rate a per-cell `α` or a global constraint over the population? | §19.3 / row 20, multiplicity half | `Xie_2013` (which *cites* Mei), `Reynolds_2000`, `Steiner_2000` — no Mei | `Mei_2010_efficient-scalable-schemes-monitoring` **is admitted in main and holds 0 blocks** (`psql`: held, unextracted) |
| What condition identifies emission accuracy from unlabeled data? | §19.4 / row 16 | `Parisi_2014` at rank 2 — a *related* result (rank-one off-diagonal covariance), not the three-approximations condition | `Platanios_2014_…` and `Platanios_2016_…` exist in `litkb.works`, are **not in main's view**, and hold 0 blocks. `litkb_work(key=…)` returns `found: false` with the correct hint. I did not substitute Parisi for Platanios |
| Is the σ composition of §14.7 the Law of Propagation of Errors? | §17.2 | `Gros_2021`, `Leung_2004a`, `Olofsson_2013` — nothing metrological | no GUM/JCGM document appears to be held |

The first two are the skill's §0 case exactly — "not extracted yet", not "not held". Diagnosing
them needed `psql`, because the tool the skill names for it is broken (friction item 1).

---

## 3. The promotion

`litkb_propose_promotion()`, once, after every use was recorded.

```
promotion_id  01a0aa62-7229-790c-ae84-08f3e0b41d71
branch_head   fd59bc32697b22c14a0296829d43dbccc47655e1
state         prepared          returncode 0    stderr ""
prepared      12 chains  (6 gap, 6 use — each use with 1 evidence row)
held          []
report_written  D:\edmonds-pipeline\treedata-access\_derived\promotions\01a0aa62-7229-790c-ae84-08f3e0b41d71.md
report_path     null
```

**Nothing was held.** Every use carried a quote the database verified, and every `feeds` token
validated. Three forms were exercised: `framework §N.N`, `gap row N` — the two that 0005 already
admitted — and **`narrative §N`, one of the four migration 0018 added**. `gated-plan gate N`,
`review §N…` and `report <FILE>#§<loc>` were **not** exercised here; the P8 gate's own live test
covers all seven at once, and this session does not re-measure it. `report_path: null` with a real `report_written` is
the P8 report's own §7.5 caveat showing on live data: the row records only what the caller named
at prepare, and the default is reported in the payload.

The workstream is **still open**. `promote commit` was not run and is not a tool.

---

## 4. Friction log — verbatim

**1. `litkb_work` cannot return any work that exists. Both selectors. This is the headline.**

```
{"ok": false, "refused": "error",
 "message": "UndefinedColumn: column \"container\" does not exist\nLINE 1: SELECT type, title, authors, year, container, publisher, wor...\n                                           ^",
 "tool": "_work"}
```

Reproduced on `key=Mei_2010_efficient-scalable-schemes-monitoring`,
`key=Mousavi_2009_cusum-chart-monitoring-proportion`, `key=Efron_1986_how-biased-apparent-error`,
`key=Jackson_2011_multi-state-models-panel`, and `doi=10.1002/sim.3940`. `server.py:421` selects
`container`; `litkb.main_works` has **`venue`** (`\d litkb.main_works`). Both branches reach that
statement, so the tool succeeds only on the *miss* path — which is why it looks alive: a work it
does not hold answers cleanly, a work it holds crashes.

This is the same defect class as `_candidates`'s `identifiers`-vs-`ids`, which `server.py:450–455`
describes in a comment written *this branch*: a column name the schema does not have, invisible
for the same reason. Measured, not inferred — `grep -n litkb_work Scripts/qc/test_litkb_p8.py`
returns four lines, and **the suite calls the tool exactly once**, at line 136, as
`one("litkb_work", {})`, asserting `no-selector`. The only test whose name says otherwise,
`test_a_work_shaped_result_is_returned_byte_for_byte` (line 312), builds a work record **by hand
in Python** and hands it to `server._out()`; it never opens a connection. So no test has ever
called `litkb_work` on a work the database holds. It blocks the skill's
step 0 ("check `litkb_work(doi=…)` before concluding the work is absent") and this test's
read-back step. The refusal also reaches the model as `refused: "error"` with a raw psycopg
message — the shape the referee's F-1 fix replaced on the token path, still present here.

What `litkb_work` was supposed to show, read by `psql` instead: `Efron_1986` — 1 identifier,
1 file; `Jackson_2011` — 3 identifiers, 1 file; `Gasparrini_2010` — 3, 1;
`Mousavi_2009` — 3, 1.

**2. An agent cannot read back its own uses.** `litkb_ws_status` returns
`"proposed_versions": {"gap": 6, "use": 6}` — counts, no statements, no quotes, no work keys.
`litkb_work` reads `litkb.main_uses`, which holds **0** of the six (`psql`: they stay `proposed`
until Kam merges and `promote commit` runs), so even with item 1 fixed it would not show them.
The only place this session's own work is legible is the promotion report file it wrote.

**3. The promotion report the skill says to commit is gitignored.** `git check-ignore -v` on it:

```
.gitignore:2:/*	_derived/promotions/01a0aa62-7229-790c-ae84-08f3e0b41d71.md
```

`SKILL.md` step 5: "**Commit it with the branch** — that is how it reaches Kam inside the merge
he reviews". A session that does `git add <that path>` stages nothing and is told nothing. It
needs `git add -f`, which the skill does not mention.

**4. The `quote-not-in-block` message mis-diagnoses the commonest cause.** "…paraphrase in the
statement, never in the quote" is the right advice for a paraphrase and the wrong advice for what
actually happened three times here: a verbatim quote from a *different extraction of the same
page*. The refusal already knows the block; echoing its first ~200 characters would turn a
guessing game into a diff.

**5. `SKILL.md` §0 is now false, in the direction that costs recall.** It says "**The base holds
almost no blocks yet.** P4/P5's bulk extraction has not run into `litkb`, so `litkb_search`'s
block leg can currently return nothing at all." `litkb` holds **102,008** blocks and search
answered every question put to it. A session reading the skill would under-trust the tool and
reach for a web search sooner than it should.

**6. `litkb_candidates` returned `{"ok": true, "workstream_id": …, "candidates": []}`** — correct
here (nothing was admitted this session), but with no admissions to distinguish it from, it is
indistinguishable from the failure mode `server.py:450–455` documents. Not a defect observed;
an observation that cannot be made.

**7. Block boundaries cut mid-word (F2).** The only block carrying §19.2's sentence begins
`e choice of the basis…`. The citation is verbatim and verified and still reads as damaged.

**8. Duplicate canonical blocks consume rank slots.** The same Efron passage is stored twice
(`docling` `01a0aa24-e845-…`, `grobid` `01a0aa24-e846-…`), both `canonical = true`, returned at
ranks 4 and 6 of one query. Three of Q3's top six were the same Rosychuk sentence. Effective
top-10 recall is smaller than 10.

**What did not need a workaround**, which is the other half of an honest log: the stdio handshake,
the nine-tool list, `litkb_ws_open` and its never-printed token, `litkb_search` on every query
tried, `litkb_record_use`'s locate-and-verify, the paraphrase refusals, the seven-form `feeds`
vocabulary, and `litkb_propose_promotion` writing a real report — all worked first time, exactly
as `SKILL.md` describes them.

---

## 5. Verdict

**Yes — a session can do a literature task through this system today, with one tool broken and
one rule missing from the skill.**

What was actually achieved, cold, in one session: six real questions from the project's own
framework, six passages found by search (ranks 1, 2, 2, 2, 1, 4), six quotes the database
verified against the stored text, three paraphrases refused, three further questions recorded as
gaps rather than answered from memory, and twelve chains prepared with none held. None of it
required reading a PDF, and none of it could have been faked: every quote is a byte range in a
block a third party can re-read.

What stopped it from being clean, in order of cost:

1. **`litkb_work` is dead for every held work** (friction 1). The skill's own instruction for
   deciding "absent, or just unextracted?" points at it, and I had to answer that question with
   `psql` twice — which a research session should not have to do, and which a session without
   database access could not do at all. One column name.
2. **Recording a use and reading it back are different systems** (friction 2). Nothing in the tool
   surface shows a session what it wrote.
3. **The skill's §0 understates the corpus by five orders of magnitude** (friction 5), and its
   step 5 asks for a commit `git add` will not make (friction 3).

None of the three touches the property the system exists for. The quote gate held: it verified
what was verbatim, refused what was not, and refused the gold's own quotes rather than accept a
plausible near-miss — which is the behaviour you want from it and the reason the test found the
extractor mismatch at all.

---

## 6. What this test did NOT exercise

* `litkb_admit` and `litkb_acquire` — nothing was admitted or fetched by design (no archive
  downloads in this test), so the five admission checks and the acquisition ladder are untouched
  here.
* The **librarian subagent** — still unrun (P8 report §6 item 2 stands). This session drove the
  tools directly.
* The **hook** — still not installed; not exercised.
* `promote commit` and `approve` — absent from the tool list, as designed; not run.
* The vector leg — off (`LITKB_VECTOR_SEARCH` unset); every search result says so in words, and
  every query here was lexically close to its target. A paraphrase-only query was not tried
  against a held paper.
* Search **cost** — not measured. P8 §6 item 5 stands, though 0018's two GIN indexes are now
  live in `litkb` and no query here felt slow.
* Four of the seven `feeds` forms (`gated-plan`, `review`, `report`, and the bare-`framework §N`
  depth case) — not written by any use here; see §3.
* `qc/check.py` — not run. This commit changes no code and adds no test; the ladder would
  measure the branch it inherited, not this work.

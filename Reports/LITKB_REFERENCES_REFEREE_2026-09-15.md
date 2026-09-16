# litkb P6 — independent referee report

**Branch** `work/20260915-references` · **HEAD** `bfc4208` · **Date** 2026-09-15
**Referee** Claude Opus 5 (1M context) — independent of the build (CLAUDE.md 3.4c: the proposer never
scores its own proposal). **Subject** `Reports/LITKB_REFERENCES_2026-09-15.md`.

## Verdict: **P6 READY WITH FIXES**

Nothing found here invalidates the stage. The resolution path, the DOI-first kill, the breaker and the
Crossref gate all hold up under independent re-running. Two claims in the builder's report are wrong
and must be corrected before the numbers are quoted onward; both are reporting defects, not code
defects, and neither changes a resolution.

| # | fix | severity |
|---|---|---|
| F1 | **"1,386 in-text citation mentions" is a bounding-box row count, not a mention count.** The true `<ref type="bibr">` element count is **1,182**, of which **201 carry no target**. 139 of 658 reference rows carry an inflated `mention_count`; "Morgenroth 2017 cited 12 times" is **8**, and the §3 top-10 re-orders and loses a member when recounted. | must fix — it is a headline number and it changes the top-uncited ranking |
| F2 | **"the 12 `doi_title_mismatch` are truncated GROBID titles rather than bad DOIs" is true for 10 of 12, false for 2.** Steenberg `b5` and `b22` print genuinely wrong DOIs. | must fix — the report tells a future reader the cause is always a parse artefact |
| F3 | `Reports/litkb_p6_per_paper_2026-09-15.csv` carries a bare `resolved_rate` column with no Crossref-only label. | minor |

Everything below is measured in this session on this HEAD. Where the builder's own files are read for
comparison they are named as **the builder's JSONL**.

---

## 1. Reproduction — 6 of 18, seeded

Selection, fixed before any result was looked at:
`random.Random(20260915).sample(sorted(<the 18 'ok' stems>), 6)` →
**Benedek_2015, Chrisman_1982, Walton_2008, Page_1954, Burnicki_2011, Guo_2018**.

**GROBID re-run.** All six PDFs re-processed through `grobid.process_pdf(..., include_raw_citations=True)`
(GROBID 0.9.1 CRF under WSL, same params, client stopped afterwards). TEI bytes differ only in the
header timestamp; **`biblStruct` count, `<ref type="bibr">` count and every parsed reference title are
identical on all six**. The parse is reproducible.

**Re-resolution**, through `references.process_tei` with a fresh `CachedClient` on the on-disk cache:

| stem | refs | mention rows | resolved | amb | unres | edges | cands |
|---|--:|--:|--:|--:|--:|--:|--:|
| Benedek_2015 | 64 | 178 | 50 | 1 | 13 | 6 | 58 |
| Chrisman_1982 | 15 | 26 | 2 | 0 | 13 | 0 | 15 |
| Walton_2008 | 12 | 30 | 6 | 0 | 6 | 0 | 12 |
| Page_1954 | 25 | 31 | 0 | 0 | 25 | 0 | 25 |
| Burnicki_2011 | 62 | 114 | 30 | 1 | 31 | 1 | 61 |
| Guo_2018 | 57 | 108 | 39 | 0 | 18 | 2 | 55 |
| **total** | **235** | **487** | **127** | **2** | **106** | **9** | **226** |

Every cell matches `Reports/litkb_p6_per_paper_2026-09-15.csv`. Row by row against the builder's JSONL
on `(resolution, resolved_doi)`: **0 mismatches in 235 references.** That diff covers the state and the
DOI, **not** the reason string; the causes below are read from the builder's JSONL, not re-derived.
Counted there, the six papers' unresolved rows break down as §2 of the builder's report predicts —
Page 1954 **19 of 25** `no_title_or_author` (the rest `best=<stage>:<ratio>`), Guo 2018 nine
`doi_title_mismatch` and two `no_title_or_author`, Chrisman and Burnicki two each. My run tripped
`semanticscholar` and `arxiv` on 429 exactly as the builder's `summary.json` records, and spent 292 s
for 10 network calls against 210 cache hits.

**The count the reproduction does not confirm.** I counted the TEI myself with my own XPath, no litkb
code. Corpus-wide: `back//listBibl/biblStruct` = **658** (agrees), zero missing `xml:id`, zero
duplicate ids, zero dangling `target`s. But `<ref type="bibr">` in `<body>` = **1,182**, not 1,386.
`citation_mentions()` emits one row per `coords` box (`for i, (pg, …) in enumerate(parse_coords(…))`),
and 204 mentions are line-wrapped across two boxes. A further **201 elements carry an empty `target`**
and cannot be linked to any reference at all, so the verifiable mention count is **981**. This
propagates: `counts[m["target"]]` is incremented per box, so **139 of 658 reference rows** overstate
`mention_count` (worst: Laurance `b18` 15→11, Guo `b36` 12→8, Benedek `b54` 12→10). Every entry in the
§3 top-10 is cited by exactly two papers, so mention count is that table's *only* ordering key.
Recomputed on element counts the table **re-orders and changes membership**:
`10.1016/j.rse.2007.11.013` takes first place, `10.48044/jauf.2008.048` falls from 5th to 8th,
`10.1007/s00267-014-0310-2` drops out and `10.1109/36.843009` enters. → **F1**. The concrete fix is one
line — `counts` should increment only on `box_index == 0`; the per-box mention rows are correct as
geometry and only the aggregate is wrong. (Recommendation; I changed nothing.)

## 2. Crossref, entry by entry

Deposited lists fetched from `works/{doi}` (all three cache hits, 0 network calls). Matching, in order:
normalised DOI on both sides → title ratio ≥ 0.85 against `article-title`/`volume-title` → GROBID title
contained in `unstructured`, or author family + year + first page for structured-only entries. Precision
= matched / GROBID references; recall = matched / deposited entries.

| paper | GROBID | deposited | matched | precision | recall |
|---|--:|--:|--:|--:|--:|
| Besag 1974 | 49 | 49 | 49 | **1.000** | **1.000** |
| Benedek 2015 | 64 | 64 | 63 | **0.984** | **0.984** |
| Alwan 1988 | 14 | 14 | 12 | **0.857** | **0.857** |

**The count agreement is not hiding a misparse on any of the three.** Besag — the paper the count gate
was most likely to flatter, 49=49 on only 8 resolved — matches perfectly entry for entry. Benedek's one
miss is a matched pair my rule refused: GROBID lost a space, parsing Patra 2007's title as
"Unsupervised change detection in **remotesensing** images…", so the entry is present on both sides
and the true figure is 64/64.
Alwan's two are the same class in reverse: both sides hold the two *Seasonal Analysis of Economic Time
Series* conference chapters, Crossref depositing the volume title and GROBID the chapter title.

**A warning for anyone reusing this gate.** Matching on `article-title` alone scores Alwan **5/14**.
Six of its fourteen deposits are DOI-only (`{"key": "CIT0002", "DOI": …}`) and two more are
`volume-title`+author+year with no title at all. A future entry-level check must expand DOI-only
deposits (one `confirm_doi` each) or it will report a parse failure that is a deposit format.

## 3. My own near-miss kills

Ten alterations, none of them the builder's, run Crossref-only with `semanticscholar` and `arxiv`
pre-tripped, against references the builder resolved.

| alteration | n | resolves to the original | resolves elsewhere | fires |
|---|--:|--:|--:|--:|
| co-author (not first) swapped for "Nakamura" | 3 (2 effective) | 3 | 0 | 0 |
| journal replaced | 2 | 2 | 0 | 0 |
| volume + pages replaced | 2 | 2 | 0 | 0 |
| **first** author swapped | 1 | 0 | 0 | **1** |
| DOI, two digits transposed | 2 | 0 | 0 | **2** |

The seven that survive are **the rule working as written, not a hole**: `judge_candidate` uses title,
first-author family and year, and the search leg queries on title only. Journal, volume, page and
non-first authors are not inputs to any decision, so altering them cannot change one. That is worth
stating plainly in the design, because a reader of §5 could take "near-miss" to mean any altered field.
(One caveat on my own arm: Bellettini `b30` parsed a single author, so its "co-author swap" was a no-op
and that arm is really n = 2, not 3.)
The two DOI mutants both went to `doi_not_registered` (Crossref 404 + DataCite 404) — the DOI-first rule
never reached a title search.

### Title tolerance — how many words must change

Twenty references (seeded `random.Random(20260915)`, resolved, no DOI, title ≥ 6 words), words replaced
with a fixed nonsense token in a per-reference shuffled order, k = 1, 2, 3 … until the reference stops
resolving to its original DOI. 55 mutations, Crossref-only.

| words changed before resolution fails | references |
|---|--:|
| 1 | 3 |
| 2 | 4 |
| 3 | 10 |
| 4 | 3 |
| ≥ 5 | 0 |

Median **3 words**, ≈ 22 % of the title's words. Seventeen of twenty survive a one-word change — the
builder's 17/20 at 0.80–0.94, reproduced independently on a different sample.

**Judgement: a tolerance to record, not a defect to escalate — but state the limit of my evidence.**
Across all 55 of my mutations **not one resolved to a different work**: every failure was `unresolved`
and every survival was the correct DOI. That is a real result about one failure mode and not about the
other. My substitution token is a nonsense word, which no real title can contain, so my run can only
test *nonsense* corruption. The builder's own §5 records the mode I could not reach: two mutants that
**resolved elsewhere** — a `year−3` mutant landing on the 1998 sibling of a 2002 paper, and a
title-word mutant landing on a different ecology paper. Those are plausible-sibling collisions, and what
bounds them is the first-author-family and year-equal-or-±1 gates, not the ratio.

So the conclusion holds, with the reason stated correctly: the 0.85 rule alone tolerates roughly a fifth
of a title, the ratio is not what makes the decision safe, and the two gates behind it are. Raising 0.85
would not close the sibling mode (both builder cases cleared 0.85 on a genuinely similar title) and
would cost the 10 truncation cases of §4. No escalation — but the design should say that the ratio is a
filter and the author+year rules are the discriminator, rather than quoting 0.85 as the guarantee.

## 4. The twelve `doi_title_mismatch`

Read raw against parsed against registry title, all twelve.

**Ten are parse artefacts, as the builder says.** Nine are Guo 2018, where GROBID either truncated the
title at a comma ("…Homogenization of Tree Cover" for "…Tree Cover in Baltimore, MD, and Raleigh, NC")
or ran the journal name onto the end of it ("…tree planting and removal. Urban Forestry and Urban
Greening"). The tenth is Steenberg `b9`, where an unclosed quotation mark in the printed reference
swallowed the journal. In all ten the printed DOI is correct.

**Two are not.** They are the Averkov class the guard exists for, and the guard caught them:

Registry fields below are read from the cached `confirm_doi` record, not inferred from the title.

| row | printed DOI | registry record for it | what the reference actually is | ratio |
|---|---|---|---|--:|
| Steenberg `b5` | `10.1080/19463138.2010.513772` | Boone, **2010**, *Environmental justice, sustainability and vulnerability* | Boone 2010, *Landscape, Vegetation Characteristics… Why the 60s Matter*, Urban Ecosystems 13 | 0.245 |
| Steenberg `b22` | `10.1177/1078087406290729` | Heynen, **2006**, *The Political Ecology of Uneven Urban Green Space* | Heynen & Lindsey 2003, *Correlates of Urban Forest Canopy Cover*, PWM&P 8 | 0.323 |

Both are wrong DOIs printed in the published paper (b22's raw string even carries the tell: `doi: 10.1177/ 1078087406290729`). Calling all twelve a parse artefact would tell the next reader to trust a
DOI the source got wrong. → **F2**.

**And `b5` exposes a reachable weak spot worth one line in the design.** Its registry record is *Boone,
2010* and the parsed reference is *Boone, 2010* — same surname, same year. The title ratio of 0.245 is
the only thing that refused it. `resolve_by_doi`'s other branch, taken when GROBID parses **no** title,
judges on surname and year alone: had this reference lost its title in parsing, that branch would have
**accepted** the wrong DOI. (`b22` would still have failed there, on 2006 vs 2003.) The branch is a
deliberate, documented compromise and I am not proposing to remove it — but it should be named in the
design as the one place where the Averkov class can get through, and the `no_title_or_author`
population (50 rows) is exactly where it lives.

**Is the refusal losing real citations?** Measured, not estimated: of the twelve, **one** has a DOI in the
corpus index — Guo 2018 → Nowak & Greenfield 2012 (`10.1016/j.ufug.2011.11.005`, parsed title carried
the journal, ratio 0.73). So the conservative refusal costs **one in-corpus edge out of 13, and eleven
candidate rows that are leads rather than nothing.** (For scale: one more edge is lost in the 19
`ambiguous` rows.)

**Recommendation — do not change the threshold; change the label.** Containment, after normalising
whitespace and the Unicode quote/dash forms, separates the two populations with no crossover: it holds
for **exactly the 10 parse artefacts and fails for exactly the 2 wrong DOIs**. That makes it a safe
*discriminator*, and an unsafe *acceptance rule* — accepting on containment alone would let a
three-word generic parsed title ("Introduction", "Discussion") match any registry title that contains
it. So:

> Keep `RESOLVE_TITLE_RATIO = 0.85` and keep these rows **unresolved**. Add a distinct terminal reason
> `doi_title_contained` (alongside `doi_title_mismatch`) when the parsed and registry titles are in a
> containment relation **and** the shorter is ≥ 5 words and ≥ 60 % of the longer's length. P5's ingest
> can then triage a parse artefact from a bad DOI without the resolver deciding to trust either. The
> guard `p6 a reference DOI must resolve to the reference's own work` is untouched, so the P6-G2 kill
> still fires.

That is a recommendation, not a change; no source file in this branch was modified by me.

## 5. Mentions — 20 each, two papers

Twenty target-bearing mentions sampled (seed 20260915) from Guo 2018 (author–year markers) and
Benedek 2015 (numeric markers), each checked against the reference its `target` names:

**40 of 40 correct.** Every Guo marker names the first author or the year of the reference it points at;
every Benedek numeric marker equals the ordinal of its `biblStruct`. No mis-targeting found.

Rendering the same 40 boxes out of the PDFs (PyMuPDF, clip = the stored bbox + 1 pt) recovers the full
marker string in 26 and a fragment of the correct marker in the other 14 — the 14 are line-wrapped or
tight-clipped boxes that also pull in neighbouring text. **The link is exact; the box geometry is
approximate.** Usable for highlighting a citation in a viewer, not for cropping one.

## 6. The stage breaker and the floor label

- **Trips are recorded, never silent.** `summary.json → summary.stages_tripped` holds
  `{"arxiv": "arxiv status 429", "semanticscholar": "semanticscholar status 429"}`, and **209 reference
  rows** carry `skipped=semanticscholar,arxiv (rate-limited)` in their own reason. My independent run
  tripped both stages the same way. Only 2 search-path rows lack the tag — the references processed
  before the second consecutive 429, which is correct.
- **The `" 0"` substring test in `StageBreaker.record` is sound.** I enumerated every error string the
  search functions can return: `"<source> status <st>"` and `"arxiv atom unparseable"`. `" 0"` can only
  arise from `status 0`, a dead connection — no 4xx/5xx code can produce it. No false trip is reachable.
- **One untested path.** `resolve_by_search`'s `except Exception` returns `registry_error` *before*
  `breaker.record`, and also before the remaining stages are tried. Zero rows hit it in the live run, so
  it is unexercised — worth a stub test, not a blocker.
- **Floor labelling.** Carried in the report §2 ("THIS IS A CROSSREF-ONLY RATE"), §7.1, and in the
  `d909cfa` commit message. **Absent** from `Reports/litkb_p6_per_paper_2026-09-15.csv`, whose
  `resolved_rate` column travels with no stage context. → **F3**, a header comment or a
  `stages_tripped` column.

## 7. Gates re-run in my own hands

**Six harness rows, weakened by me** (not by re-running `litkb_p6_mutations.py`) directly in
`pipeline/litkb/extract/references.py` and `pipeline/litkb/admit/resolver.py`, `qc/test_litkb_references.py`
run after each, file restored from git and the tree re-verified:

| row | weakening applied | tests failed | report claims |
|---|---|--:|--:|
| P6-G1 | DOI-first block deleted | **7** | 7 |
| P6-G2 | DOI/own-work block deleted | 2 | 2 |
| P6-G3 | ambiguity block deleted | 1 | 1 |
| P6-G4 | cacheable-status block deleted | 4 | 4 |
| P6-G5 | candidate written `admitted` | 1 | 1 |
| P6-R1 | `RESOLVE_TITLE_RATIO` 0.85 → 0.60 | 1 | 1 |

Baseline 38 passed before and after; `git status --short` clean at the end and both files byte-identical
to HEAD modulo the working tree's CRLF. (My shell reproduction of the sha256 restore check reported a
false failure for this reason; the harness itself uses `read_bytes`/`write_bytes` and is byte-exact, so
its own sha256 claim is sound.)

**`qc/check.py --fast`** under `LITKB_TEST_DB=litkb_test_w8`, on this HEAD:
**2,488 passed, 19 skipped, 1 xfailed, 1 failed in 927 s** — the failure is
`test_experiments.py::test_pointer_paths_resolve[crown_state_model]` and nothing else. Matches the
builder's §6 exactly.

**Secrets.** `git log -p 8f985e5..bfc4208` (2,169 lines) scanned for `obuntu`, password/passwd, api key,
secret, token, bearer, private-key headers, AWS/GitHub/Slack token shapes and long base64/hex runs:
**nothing but commit SHAs and repo paths.** No credential, no host, no path outside the repo and the
declared derived root.

**Push.** `git push github work/20260915-references` was **refused by the session's permission
classifier** (Out-of-Place Publication), not by the remote. This commit is local to the worktree at
`D:\edmonds-pipeline\treedata-references` and needs a human push.

## 8. What I did not test

The 55.5 % with a Semantic Scholar key (no key available here) — the floor stands unchallenged and
untightened. The 50 `no_title_or_author` pre-1990 references: how many are recoverable is still
unmeasured. The near-miss year arm re-defined against registry years (builder's §7.5) — I did not run it;
the builder's explanation of the one non-firing `year+3` mutant reads correctly against the code, but it
is unverified by me. Nor did I reproduce the builder's two `resolved_elsewhere` cases (see §3) — my
nonsense-token ladder cannot reach that failure mode, and I take those two on the builder's record.

---

*Referee: Claude Opus 5 (1M context) · session https://claude.ai/code/session_015MUcyGTfX2koRdYAjW5kED*

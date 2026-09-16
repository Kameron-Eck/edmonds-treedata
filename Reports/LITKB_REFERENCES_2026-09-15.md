# litkb P6 — Citations: references, resolution, the citation graph

**Branch** `work/20260915-references` · **Date** 2026-09-15 · **Design** `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md`
§7 stage 6, §4.3–§4.4, §14 P6 · **Author** Claude (builder).
**Refereed** — `Reports/LITKB_REFERENCES_REFEREE_2026-09-15.md`, verdict *READY WITH FIXES*.
**Corrected 2026-09-15 against that referee**; every number below is the corrected one, and §8
lists what changed and what the correction itself measured. Two of the referee's own claims did not
reproduce and are named there rather than copied in.

| | |
|---|---|
| Module | `Scripts/pipeline/litkb/extract/references.py` |
| Instrument | `Scripts/qc/instruments/litkb_p6_references.py` |
| Tests | `Scripts/qc/test_litkb_references.py` (38, no DB, no network) |
| Mutation harness | `Scripts/qc/instruments/litkb_p6_mutations.py` (rows registered into the shared P2 self-check) |
| Measured tables | `Reports/litkb_p6_per_paper_2026-09-15.csv`, `…_crossref_lists_…`, `…_near_miss_…`, `…_top_uncited_…` |
| JSONL for P5 ingest | `D:\edmonds-pipeline\litkb_derived\p6\{references,citation_mentions,edges,candidates}.jsonl` |

DB-free, as the task required: nothing here opens a connection. The four JSONL files are what P5's
ingest persists into `references`, `citation_mentions` and `candidates`; the citation-graph columns
are applied at merge.

---

## 1. What was run

**The paper set is derived, not remembered** (`paper_set()` recomputes it every run): the five P4
hard-paper shapes that carry a text layer, then the manifest's stems ranked by how often the
project's own tracked prose names them, to twenty. The 688-page book of the P4 set is **out**: it
carries 1,276 `<biblStruct>` on its own and at 1 registry request/s would dominate every rate here.
The set spans 1954–2018 and includes Benedek 2015, Alwan 1988, the equation paper
(Bellettini 2002), seven pre-1990 papers, and the five the project cites most
(Efron 2004, Conley 1999, Chrisman 1982, Foody 2010, Besag 1974).

GROBID 0.9.1 CRF under WSL, `includeRawCitations=1` (new opt-in kwarg on `process_pdf`; default off
so P4's params hash is unchanged). **18 of 20 papers extracted**; two were refused by the existing
zero-block gate — `Anderson_1957` and `Hudson_1978`, both JSTOR-type scans whose only text layer is
the cover boilerplate. That gate firing on real inputs is the correct outcome, not a loss.

## 2. Counts and rates (measured)

| | n | share |
|---|--:|--:|
| papers with TEI | 18 of 20 | |
| **references parsed** | **658** | |
| **in-text citation mentions** (`<ref type="bibr">` elements) | **1,182** | |
| … of which carry no `target` and link to no reference | 201 | 17.0 % |
| … **verifiable** mentions (element AND target) | **981** | |
| mention ROWS written (one per bounding box, geometry) | 1,386 | |
| **resolved** | **365** | **55.5 %** |
| **ambiguous** | **19** | 2.9 % |
| **unresolved** | **274** | 41.6 % |
| in-corpus citation edges | 13 | |
| candidate rows (never admitted) | 645 | |
| distinct resolved works NOT in the corpus | 50 | |

Per paper: `Reports/litkb_p6_per_paper_2026-09-15.csv`. Spread is wide and explainable —
Steenberg 2017 84 %, Foody 2010 79 %, Guo 2018 68 %, against Page 1954 0/25 and
Goodchild 2004 0/4.

**Why the 274 unresolved, by cause** (the reason bucket travels on every row):

| cause | n | what it is |
|---|--:|---|
| `no_title_or_author` | 50 | GROBID parsed no title or no first author — nothing to search on. Concentrated in the pre-1990 papers, whose footnote-style reference lists it does not segment into fields |
| `doi_title_contained` | 9 | the DOI is registered and the two titles are in a CONTAINMENT relation — GROBID truncated the title at a comma, or ran the journal name onto the end of it. A parse artefact, still refused (see §5) |
| `doi_title_mismatch` | 3 | registered, not contained, and below 0.85. **Two are genuinely wrong DOIs printed in the published paper** — Steenberg `b5` and `b22`; the third (Guo `b39`) is a parse artefact the length filter refuses (see §5) |
| `doi_not_registered` | 1 | DOI resolves at neither Crossref nor DataCite |
| `best=<stage>:<ratio>` | 211 | searched and refused, with the best candidate and its ratio recorded |

**THIS IS A CROSSREF-ONLY RATE, and must not be quoted as anything else.** Measured, unauthenticated,
from this laptop: `api.semanticscholar.org` answers **429 in 0.1 s** and `export.arxiv.org` **429 in
0.4 s**, on the first request, at any pace. The resolver's back-off ladders then spend 10 s and
15 + 30 s per reference for nothing — **~82 s per reference** over the first eleven references of the
first live run, against ~1 s for the Crossref leg. A `StageBreaker` therefore trips a stage after two
consecutive rate-limit answers and skips it for the rest of the run; `summary.json` records
`stages_tripped`, and every affected row's reason names the skipped stages. Crossref never tripped.
With an S2 key, or from another network, the rate would be **at least** 55.5 % and this number is a
floor, not an estimate of the ceiling.

## 3. The citation graph

13 edges among the 18 papers (`edges.jsonl`), e.g. Benedek 2015 → Benedek 2009, Hoberg 2015,
Kolmogorov 2004, Liu 2008, Melgani 2003, Solberg 1996; Guo 2018 → Morgenroth 2017 (cited **8** times
in text) and Steenberg 2018; Burnicki 2011 → Burnicki 2007. The join is the **normalised DOI**
against the manifest and the two bibliography CSVs (192 DOI-keyed works).

*A defect found and fixed in this build:* the first graph run produced edges whose cited work was
`"14"` and `"34"` — the bibliography CSV's `id` is a row number, and the index had accepted it as a
key. `KEY_COLUMNS` now takes only stem-shaped columns and a row with no stem is not indexed
(`test_a_row_whose_only_key_column_is_a_row_number_is_not_indexed`).

**Top 10 cited works not in the corpus** (ranked by citing papers in the set, then in-text mentions;
full table `Reports/litkb_p6_top_uncited_2026-09-15.csv`). Each is cited by 2 of the 18:

| mentions | DOI | work |
|--:|---|---|
| 5 | 10.1007/s10021-006-0116-z | Characterization of Households and Its Implications for the Vegetation… |
| 5 | 10.1016/j.rse.2007.11.013 | Some challenges in global land cover mapping |
| 5 | 10.1016/j.ufug.2012.09.002 | Predictors of the distribution of street and backyard vegetation |
| 5 | 10.1080/01431160500057848 | Improving land cover change estimates by accounting for classification error |
| 5 | 10.1559/152304006777681706 | Can error explain map differences over time? |
| 4 | 10.1016/j.ufug.2013.11.004 | Individual households and their trees |
| 3 | 10.1016/j.jenvman.2015.08.008 | Neighbourhood-scale urban forest ecosystem classification |
| 3 | 10.1073/pnas.0401545101 | Developing a science of land change |
| 3 | 10.48044/jauf.2008.048 | A ground-based method of assessing urban forest structure |
| 2 | 10.1007/s00267-014-0310-2 | An Ecology of Prestige in New York City |

**Read the ORDER of this table with care.** Counted on elements rather than boxes the spread
collapses: five entries tie at 5 and three at 3, and within a tie the instrument orders by DOI
string. The rank-10 / rank-11 boundary is itself a tie at 2 mentions broken that way
(`10.1007/s00267-014-0310-2` over `10.1016/j.rse.2006.10.012`), so the tenth row is not a measured
margin over the eleventh. **Membership is unchanged from the box-counted table — the same ten
works, re-ordered.** (The referee predicted a membership change, with `10.1109/36.843009` entering;
recomputed under the instrument's own sort key it does not. §8.)

**Caveat that limits this list:** only references that RESOLVED to a DOI can be ranked. The 274
unresolved have no stable key, so a work cited only through unparsed pre-1990 references cannot
appear here at all. The list is a floor on the citation-chase candidates, not a census.

## 4. The §14 P6 gate — Crossref-deposited reference lists

`Reports/litkb_p6_crossref_lists_2026-09-15.csv`. 17 of the 18 papers have a DOI; **14 have a
deposited reference list** (three publishers deposited none — `reference-count` 0 means *unknown*,
not zero, and those are excluded rather than counted against the parse).

**Exact count agreement on 7 of the 14**, well past the three the gate asks for, and on the widest
shapes in the set: Benedek 2015 **64 = 64**, Foody 2010 **110 = 110**, Besag 1974 **49 = 49**,
Bellettini 2002 **38 = 38**, Conley 1999 **37 = 37**, Abercrombie 2016 **40 = 40**,
Alwan 1988 **14 = 14**.

The seven that differ are small and one-sided in both directions: Hall 1985 −1, Walton 2008 −2,
Steenberg 2017 −2, Guo 2018 −4, Burnicki 2011 +3, Laurance 1998 +12, Efron 2004 +9 against a
deposit of only 5. The large deltas are deposits that are *partial* (Efron's publisher deposited 5
of 14), not parse failures — that is an inference from the deposit size, **not measured**; matching
entry-by-entry rather than by count is the obvious next measurement and was not done.

## 5. The kills (§14 P6) — `Reports/litkb_p6_near_miss_2026-09-15.csv`

**Selection rule, stated before the run:** the first 10 resolved references in (stem, reference
index) order carrying a title and a four-digit year, plus the first 10 resolved references that
carry a DOI — without that second list the `doi-digit` arm never runs at all, because only two of
the eighteen papers print DOIs in their reference lists and they sort late. Nothing was chosen to
make a kill fire.

| mutation | fired | note |
|---|--:|---|
| `doi-digit` (one digit changed) | **10 / 10** | **the phase's headline kill** |
| `title-wrong` (real author + year, wholly different title) | **20 / 20** | |
| `year−3` | **20 / 20** | |
| `year+3` | **19 / 20** | see below |
| fabricated reference | fired | sanity |
| DOI resolving to a different title → `unresolved` | 12 live cases in the corpus | §2 table; 9 `doi_title_contained`, 3 `doi_title_mismatch` |

**The mechanism behind the DOI kill, because it is the whole design.** A DOI one digit off usually
still points at a *real* work. If a failed DOI check fell back to a title search, the registry would
hand back the intended paper and the corrupted DOI would be reported `resolved` — confidently wrong.
So **the DOI decides**: a reference that carries a DOI is resolved by that DOI alone, and there is no
title fallback from there. Mutation `P6-G1` removes exactly that rule and turns seven tests red.

**The one non-firing mutant is the ±1 year rule working as decided, not a hole.** Guo 2018 ref `b4`
prints year 2015; Crossref's issued year for that work is 2017; the `year+3` mutant is 2018, which is
within ±1 of 2017 and is accepted (decisions.yaml §15.15). The mutation is defined relative to the
*printed* year, so on a paper whose print and online-first years differ it can land inside the rule.
A stricter test would mutate relative to the registry's year; that is a change to the harness, and it
is not made here by the code it would grade.

**THE RATIO IS A FILTER; THE FIRST AUTHOR AND THE YEAR ARE THE DISCRIMINATOR.** This is the design
statement the referee asked for, and it is now in the design itself (§7, stage 6). Measured
tolerance, on the referee's independent sample of 20 resolved title-only references with words
replaced one at a time by a nonsense token: the **median reference survives 3 words changed (≈22 %
of the title) and none survives 5** (1 word: 3 references stop resolving, 2: 4, 3: 10, 4: 3, ≥5: 0).
So 0.85 is not what keeps a near-miss out — it screens obvious non-matches cheaply, and the
first-author family plus the year (equal, or ±1 only when title AND author already match,
decisions.yaml §15.15) are what decide. Raising 0.85 would not close the mode that matters: both
`resolved_elsewhere` mutants below cleared it on a genuinely similar sibling title. It would,
however, cost the nine truncated parses of §2.

**A measured tolerance, reported and NOT counted as a kill.** Swapping ONE word of a title leaves
17 of 20 references resolving to the original, at difflib ratios **0.80–0.94** against the 0.85 rule.
That is what a typo-tolerant title rule *is*; the 0.85 threshold was calibrated in P2
(`Reports/litkb_title_threshold_2026-09-14.csv`) and is not touched here. Calling this a kill, or
quietly raising the threshold to make it one, would be the design scoring itself (CLAUDE.md 3.4c).
The §14 wording — "real author + year, wrong title" — is covered by `title-wrong`, which fires 20/20.
(Every `title-wrong` mutant substitutes one fixed real title, Laurance 1998's. None of the twenty
references is Laurance-authored, so no mutant is accidentally correct; a referee reusing the harness
on a set that includes Laurance should change that constant.)

**Two mutants resolved to a DIFFERENT work** (the kill held — neither is the original) and are
flagged `resolved_elsewhere`: a `year−3` mutant landed on the 1998 paper that shares a title stem
with the 2002 original, and a `title-word` mutant landed on a different ecology paper. Both are the
same lesson: a near-miss reference does not merely fail, it can succeed at the wrong work.

## 6. Guards and the harness

`qc/instruments/litkb_p6_mutations.py`, re-run after the referee corrections: **17 of 17 mutations
fired**, both baselines green (47 tests), every file restored and the restore checked by sha256.

| row | guard weakened | effect |
|---|---|---|
| P6-G1 | DOI-first decision removed | 7 tests fail — **the kill** |
| P6-G2 | DOI may resolve to a different title | 2 fail (Averkov class) |
| P6-G3 | two accepted works collapse to the first | 1 fail |
| P6-G4 | a 429 / dead connection is cached | 4 fail |
| P6-G5 | a citation candidate is written `admitted` | 1 fail |
| P6-G6 | a DOI on a title-less reference is accepted on the DOI alone | 4 fail |
| P6-G7 | `doi_title_contained` collapses back into `doi_title_mismatch` | 1 fail |
| P6-M1 | a mention is counted per bounding BOX again | 2 fail |
| P6-R1/R2/R3 | the shared ratio / surname / year rules | 1, 2, 2 fail |
| P6-S1…S6 | `normalize_doi` not applied, per call site | 1 each |

The six new `normalize_doi` call sites are registered into the **shared** per-call-site table, so
`qc/test_litkb_harness_sites.py` inside `qc/check.py` covers the whole package: 41 call sites, 40
with a row, 1 declared equivalent, no problems.

`cd Scripts && PYTHONUTF8=1 py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w8`,
re-run on `d909cfa` after the commit: **2,488 passed, 19 skipped, 1 xfailed, 1 failed** —
`test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, the pre-existing failure this
task allows, untouched by this branch. (Both this and the harness above were first run on a tree one
edit older; they are restated here from the re-run on the committed bytes, per the quote gate.)

## 7. What a referee should attack

1. **The 55.5 % is Crossref-only.** Reproduce it with a Semantic Scholar key and say what the rate
   becomes; the breaker is per-run state, so a keyed run starts closed.
2. ~~**The 12 `doi_title_mismatch` are, on inspection, not wrong DOIs.**~~ **ANSWERED AND WRONG AS
   WRITTEN (§8).** Ten of the twelve are parse artefacts; **two — Steenberg `b5` and `b22` — print
   genuinely wrong DOIs**, and telling a future reader the cause is always a parse artefact would
   have taught them to trust a DOI the published paper got wrong. Containment is now a distinct
   terminal reason (`doi_title_contained`, 9 rows) and the threshold is untouched at 0.85; nothing
   is resolved on containment.
3. **The Crossref agreement is by COUNT.** Entry-by-entry DOI matching against the deposited lists is
   the stronger gate and was not run.
4. **`no_title_or_author` (50) is a GROBID segmentation limit on pre-1990 footnote references**, not
   a resolver limit. Nothing here measures how many of those 50 are recoverable.
5. **The near-miss year arm is defined against the printed year**, which let one mutant land inside
   the ±1 rule legitimately. Re-run it against registry years.
6. **Derived-artifact location.** Design §15.6 is still *Open* and this session held
   `D:\edmonds-pipeline\Literture\` read-only, so the cache and JSONL live under
   `D:\edmonds-pipeline\litkb_derived\` (`$LITKB_DERIVED`). When §15.6 is decided, change
   `references.DERIVED_ROOT`'s default and nothing else.

---

## 8. Corrections after the referee (2026-09-15)

Three of the referee's findings are fixed in code and the artifacts regenerated. `qc/check.py
--fast` is re-run at the foot of this section.

### 8.1 F1 — a mention is an ELEMENT, not a bounding box

`citation_mentions()` writes one row per `coords` box, which is right as geometry: a marker that
wraps across a line occupies two boxes and both are needed to highlight it. `process_tei` was
counting those rows, so a wrapped marker counted twice. Counting `<ref type="bibr">` elements
instead (`box_index == 0`):

| | was | is |
|---|--:|--:|
| in-text mentions | 1,386 | **1,182** (204 wrapped markers) |
| … with no `target` | not reported | **201** |
| … verifiable | not reported | **981** |
| reference rows with an inflated `mention_count` | — | **139 of 658** |

Worst cases: Laurance `b18` 15 → 11, Guo `b36` (Morgenroth 2017) 12 → **8**, Benedek `b54` 12 → 10.
The mention ROWS are unchanged — only the aggregate is. `mention_elements`,
`mentions_without_target` and the box-row count are now three named columns
(`R.mention_totals`), in `summary.json` and in the per-paper CSV, so one can never be quoted for
another. Guard: **P6-M1**.

**What did NOT change: the top-10 membership.** The same ten works, re-ordered — and the order is
now mostly ties (five at 5 mentions, three at 3), broken by DOI string. The referee predicted a
membership change (`10.1007/s00267-014-0310-2` out, `10.1109/36.843009` in); recomputed under the
instrument's own sort key it does not happen, and the rank-10/11 boundary is a 2-mention tie. That
is stated in §3 rather than carried forward.

### 8.2 The `resolve_by_doi` no-parsed-title branch

The branch that runs when GROBID parses no title reached its decision through `judge_candidate`,
handed the registry's own title as the reference's — a self-comparison scoring 1.00, which unlocked
the ±1 year arm that decisions.yaml §15.15 grants only when the title AND the first author match.
It now checks the first-author family and an **exact** year directly, refusing with
**`doi_unverifiable`** (was `doi_unconfirmable`), and an acceptance says `basis=author+year (no
parsed title)` rather than a ratio of 0.00. Guard: **P6-G6**, four tests.

**How many of the 50 `no_title_or_author` rows moved: none — and the honest reason is that they
cannot.** `no_title_or_author` is raised by the SEARCH path, which is only reached when the
reference carries no DOI. Measured on the run: **0 of those 50 rows carry a DOI**, and **0 of the
658's 77 DOI-bearing references lack a parsed title**. So this branch is *unexercised on the P6
corpus*; the tests are the only place it runs. Its live shape was measured on Steenberg `b5`, whose
printed DOI is registered to a different Boone 2010 — in the corpus the title ratio of 0.245 refuses
it, and with the title stripped (the test fixture) first author and year both agree and it
**resolves**. That is the hole, pinned by a test and named in design §7 stage 6, not closed.

### 8.3 F2 — the twelve were not twelve parse artefacts

Ten are (truncated at a comma, or the journal name run onto the end); **two print genuinely wrong
DOIs** — Steenberg `b5` (registered to Boone 2010, *Environmental justice…*) and `b22` (registered
to Heynen 2006, against a Heynen & Lindsey 2003 reference). §7.2 said the cause was always a parse
artefact; it is corrected in place.

Containment is now its own terminal reason, **never an acceptance**: `RESOLVE_TITLE_RATIO` stays
0.85 and every one of these rows stays `unresolved`. The rule, `references.title_containment`: one
normalised title contains the other, the shorter is ≥ 5 words, and the shorter is ≥ 60 % of the
longer's length. Measured on the twelve: **9 `doi_title_contained`, 3 `doi_title_mismatch`.**

**The 60 % filter, not containment, is what splits 9 from 10** — worth recording, because the
referee's "exactly 10 and exactly 2" was measured on containment alone. Containment does separate
10 from 2 exactly. The length filter then refuses one true parse artefact, Guo `b39` (*Tree and
impervious cover change in U.S. cities* + the journal name) at **0.575**. Guo `b1` is the mirror
image at 0.644 by characters but 0.571 by words — this population straddles 60 % and the unit
decides, partly because the shared `_norm_text` splits "U.S." into two tokens. The referee wrote
"length", so characters it is, and the threshold was not tuned to recover b39: refusing it is the
safe direction (it stays unresolved either way, and P5 loses a label, not an edge), and tuning a
threshold to hit a predicted count is exactly what §5 refused to do with 0.85. Guard: **P6-G7**.
One more measured detail: containment needs the curly-apostrophe fold, because `_norm_text` strips
`string.punctuation`, which does not contain U+2019 — without it Guo `b5` reads as a wrong DOI.

### 8.4 F3 — the bare `resolved_rate`

`Reports/litkb_p6_per_paper_2026-09-15.csv` now carries a `stages_tripped` column beside
`resolved_rate`, so the Crossref-only condition travels with the number.

### 8.5 The regenerated artifacts, diffed against the pre-correction run

`--resolve` re-run over the cached TEI (24 network calls, 609 cache hits). Keyed on
(stem, `ref_key`), all 658 rows present on both sides:

- **0 changes in `(resolution, resolved_doi)`** — totals identical: 365 resolved / 19 ambiguous /
  274 unresolved, 55.5 %, 13 edges, 645 candidates. No resolution moved.
- **139 `mention_count` changes**, all downward — §8.1.
- **15 reason strings changed**: the 9 relabelled `doi_title_contained`, plus 6 Benedek rows that
  differ only in whether the `skipped=` tail names arXiv. That last is run-to-run timing, not code:
  the arXiv breaker tripped one reference later this time. It is a reminder that the `skipped=` tail
  records when a stage tripped, not a property of the reference.
- **The per-paper CSV's ROW ORDER changed and the paper set did not.** Same 18 papers.
  `paper_set()` ranks the manifest's stems by how often the project's own tracked prose names them,
  and the referee report — committed between the two runs — names Guo, Steenberg and Benedek more
  than the earlier corpus did. A derived set that reads the reports is a set that moves when the
  reports do; worth knowing before reading a CSV diff as evidence of drift.
- (No element in the corpus spans more than two boxes: `box_index` is 0 on 1,182 rows and 1 on 204,
  so "204 wrapped markers" is exact and not a lower bound.)

`cd Scripts && PYTHONUTF8=1 py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w8`, on the
corrected tree: **2,497 passed, 19 skipped, 1 xfailed, 1 failed in 539 s** (2,488 + the 9 new P6
tests) —
`test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, the same pre-existing failure,
untouched by this branch.

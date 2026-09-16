# OpenCitations ref-matcher, head to head with our reference resolver

**2026-09-15 · branch `work/20260915-refmatcher` (from the references branch at `e176707`)
· worktree `D:\edmonds-pipeline\treedata-refmatch` · venv `D:\edmonds-pipeline\venv-refmatch`**

Kam's direction: **adopt where someone else measured better; the registry-confirmation gate
stays regardless.** This report answers the first half with numbers and the second half with
a mechanism, and it corrects three premises the brief carried before it gets to either.

Instruments: `Scripts/qc/instruments/litkb_refmatcher_eval.py` (runs the arms),
`Scripts/qc/instruments/litkb_refmatcher_score.py` (scores them), tests in
`Scripts/qc/test_litkb_refmatcher.py`. Gold: `Reports/litkb_splink_gold_2026-09-15.json`,
copied byte-identically from `work/20260915-splink`, sha256 `d6dbbac3…`, **not altered and
not added to**. Every registry answer is cached under `D:\edmonds-pipeline\litkb_derived\refmatch\`
keyed on the exact query text, so a referee can re-score the whole report at zero wire.

---

## 1. Three premises the brief carried that the code does not support

**1.1 ref-matcher does not match against Crossref. It matches against OpenCitations Meta.**
The brief says "run it … against Crossref (cached where possible)". The tool's own
`script/requirements.txt` lists `aiohttp` under the comment *"Async HTTP client for
OpenCitations queries"*, and every one of its six query builders emits SPARQL against an
OpenCitations Meta endpoint. Crossref JSON is an **input format** it parses, not the registry
it searches. This is not a detail: it means the head-to-head is not "their matcher vs our
matcher on the same registry" but **their matcher on their registry vs our matcher on
Crossref**, and registry coverage is a confound that has to be measured rather than assumed.
It is measured in §5.

**1.2 The Crossref numbers in the brief are wrong.** The brief cites *"F1 84.5% vs 52.9%
parsing; recall 79% vs 42%"*. Crossref's published comparison — Dominika Tkaczyk,
*"Reference matching: for real this time"*, <https://www.crossref.org/blog/reference-matching-for-real-this-time/>
— reports the opposite magnitudes:

| | precision | recall | F1 |
|---|--:|--:|--:|
| legacy, parsing-based | 98.95 % | 86.85 % | **92.51 %** |
| search-based (best variant, SBMV) | 98.09 % | 94.56 % | **96.29 %** |

Search-based does beat parsing-based, which is the shape the brief had; the gap is **3.8 F1
points, not 31.6**, and neither method is anywhere near 52.9 %. Its gold is **2,000
unstructured reference strings** sampled from 100,000 random Crossref records, ground truth
assigned by hand. The post states its own limit: these numbers *"still don't reflect the
overall precision and recall of the current links in the Crossref metadata"* — the set is
unstructured references only, excluding references deposited with DOIs. It is a bounded gold,
not a claim about matching in general, and it is **not our corpus**: 658 references from 18
papers, a third of them pre-1990 footnote style.

**1.3 The tool as shipped matches nothing against the live endpoint.** Its default endpoint,
`sparql-stg.opencitations.net`, **does not resolve** — NXDOMAIN via Google DoH, confirmed
against a control (`api.crossref.org` resolves and answers 200). Production
`sparql.opencitations.net` is up and answers in ~0.9 s. Against production the shipped queries
return **zero rows for every query type**, because OpenCitations' Virtuoso stores the join-key
literals as `xsd:string` and the tool emits **plain** literals, which Virtuoso will not join.
Measured, not argued: a DOI the endpoint itself had just returned could not be found by the
tool's own query shape, and became findable the moment `^^xsd:string` was added.

The repository carries three different endpoint URLs — `sparql-stg.opencitations.net`
(the runtime default in `ReferenceProcessor.__init__` and `OpenCitationsMatcherThreadSafe`),
`opencitations.net/meta/sparql` (the default of `evaluation.OpenCitationsDOIMatcher`), and
`sparql.opencitations.net` (commented out beside it). That is endpoint drift, and it is
why the "as shipped" arm is reported on its own line in §5 rather than folded into a verdict
about the scoring.

---

## 2. What ref-matcher is, and what I adopted from it

`github.com/opencitations/ref-matcher` at commit `dfb0e7c0` (last commit **2025-11-19**,
14 commits, 1 star, 0 forks, **ISC licence**, authors Matteo Guenci, Ivan Heibi, Chiara
Parravicini, Silvio Peroni, Marta Soricetti — an official OpenCitations effort, but a small
and lightly-exercised one). It is a **script repository**: no package, no PyPI release
(`pypi.org/pypi/ref-matcher` and `/refmatcher` both 404), run as
`python ReferenceMatchingTool.py <input> --threshold 26 [--use-grobid …]`.

**Adopted, and used unmodified:**

1. **The 48-point weighted score**, verified field-for-field against the source rather than
   the README: DOI exact **15**, title tiered **14 / 13 / 13 / 12 / 11 / 10** at
   100/95/90/85/80/75 % and **0** below 75, any exact author surname **7**, year exact **1**
   (year-adjacent is explicitly **0**), volume **3**, first-or-last page **8**. 15+14+7+1+3+8
   = 48. The brief's description of the scheme is accurate.
2. **The default threshold 26/48 (54.5 %) and its dynamic adjustment** — a best score at or
   above 90 % of the threshold (23.4) is admitted. Both left at their defaults; this arm is
   the tool's verdict, not a re-tuned one.
3. **The six query strategies and their order, with early stopping** —
   `year_and_doi → doi_title → author_title → year_author_page → year_volume_page →
   year_author_volume`. The instrument drives the tool's own `process_reference`, so the
   ladder, the early stop, the GROBID fallback hook and the no-year retry are all theirs.
4. **Its `--no-doi` mode**, exposed as `--no-doi`, for the question of whether a matcher is
   being handed the answer in its input.
5. **The worked scoring examples in the README** (48/48, 31/48, 12/48). These were used as an
   independent check on my own arithmetic: README example 3 is title-80 % + year-exact = 12,
   and the first reference I traced by hand came back from the live endpoint at **exactly 12**
   for the same reason. That agreement is what told me the scorer was wired up correctly.
6. **The DOI-level set arithmetic of `script/evaluation.py`** — `TP = PRED ∩ POS`,
   `FP = PRED ∩ NEG`, `FN = POS − PRED`, with a negative set drawn from the tool's own
   "unmatched" output. Our must-not-link entries play the NEG role.

**Not adopted, and why:** their evaluation has no **ungraded** category — every predicted DOI
is scored against a POS/NEG partition that is assumed complete. Ours is not: on the 293 hard
references the gold labels 5 right answers and 7 wrong ones and says nothing about the rest.
A DOI no gold entry covers is counted as `ungraded` here and is never folded into a
"resolves N more" headline (§5). Their `--batch` / checkpoint machinery is also unused: 658
references is one pass.

**GROBID fallback:** present (`--use-grobid`, `GrobidProcessor.process_unstructured_reference`),
and it is the tool's **only** route from a raw string to a match — see §3.

---

## 3. What the arms are, and the one that did not run

ref-matcher has **no search-based mode**. All six query types are structured field lookups;
the only path from an unstructured string to a candidate is GROBID → fields → SPARQL. So the
brief's two arms ("raw strings AND the GROBID-parsed fields") are not two arms of this tool —
one of them is the tool, and the other is GROBID in front of the tool.

| arm | what it is | status |
|---|---|---|
| **parsed** | ref-matcher (patched) on the GROBID-parsed fields already in `references.jsonl`, against OC Meta | run, 658 refs |
| **parsed-unpatched** | the same, tool exactly as shipped | run, **n = 100** — the "as distributed" measurement, stopped once the result was flat (§5) |
| **mutants / mutants-noauthor** | ref-matcher on the 90 gold mutants, with the author term at 7 and at 0 | run |
| **raw-crossref** | raw strings → Crossref `works?query.bibliographic=`, top hit | run, 658 refs — **labelled CROSSREF-SBM, it is not ref-matcher** |
| **raw → ref-matcher via `--use-grobid`** | the tool's own raw-string path | **NOT RUN** |

**Why the GROBID arm did not run.** GROBID here is a WSL2 systemd service
(`Scripts/pipeline/litkb/extract/grobid.sh`, `systemctl restart grobid`). It was stopped, and
starting it needs root: `sudo -n` reports *"interactive authentication is required"*, and the
`configure` rung fails earlier still on a write into `/opt/grobid-0.9.1/grobid-home/config`.
This session cannot start it without Kam's password, and does not ask for one. **The arm is
not run, not approximated.** Everything below that would depend on it is marked accordingly,
and the recommendation in §9 says so where it matters.

---

## 4. Method

658 references from 18 papers (`litkb_derived/p6/references.jsonl`), each carrying both the
raw citation string and GROBID's parsed fields, plus our resolver's own outcome. The gold
supplies 365 positives (`ref_id → gold_doi`), 77 must-not-link entries — **7 real** (3 book
reviews, 4 sibling editions) and **70 synthetic mutants** (year ±3, title-wrong, DOI-digit) —
20 near-positive one-word title corruptions, and 5 lost-genuine resolutions.

Our side is read from files, never retyped: the P6 state from `references.jsonl`, and the
`before` / `after` / `confirmed` arms on the 293 hard references from the tracked
`Reports/litkb_s2_rows_2026-09-15.csv` (880 rows = 293 × 3). The 20 / 23 / 250 of
`LITKB_S2_BATCHING_2026-09-15.md` §8.1 is **derived** from that CSV by the scorer.

DOIs are compared through the same normalisation on both sides. Pacing is 1 request/second
per registry; requests, 429s and wall-clock are recorded per arm in each result file's
`_meta`. Two adapter defects were found and fixed before any number was taken, both now
pinned by tests; they are described in the commit message and in §8, because each of them
would have produced a confidently wrong headline.

---

## 5. Arm by arm, against the frozen gold

Generated by `litkb_refmatcher_score.py` into `litkb_derived/refmatch/score.md`; the numbers
below are that file, not a retyping of a console summary.

| arm | registry | positives correct / wrong / miss (365) | hard-293 right / wrong / **ungraded** / none | must-not-link real (7) |
|---|---|---|---|---|
| **ours (P6 + confirm)** | crossref | 365 / – / 293 *(P6 state)* | 0 / 0 / 20 / 250 (+23 amb) | **0 returned** |
| **parsed** (ref-matcher, patched) | OC Meta | **293 / 3 / 69** | 2 / 0 / 56 / 235 | 0 returned, 6 refused, 1 absent-from-registry |
| **parsed-unpatched** (as shipped, n=100) | OC Meta | **0 / 0 / 63** | 0 / 0 / 0 / 37 | 0 returned, 0 refused, 1 absent |
| **raw-crossref** (CROSSREF-SBM) | crossref | **355 / 10 / 0** | 5 / 2 / **286** / 0 | 2 returned, 0 refused |

Wire cost: parsed **1,106 requests, 3 errors (500), 0 × 429, 35.6 min**; raw-crossref **658
requests, 0 errors, 0 × 429, 19.1 min**; parsed-unpatched 163 requests, 2.8 min; presence probe
12 requests. All 1-per-second, all cached.

**The "as shipped" line is the headline for adoption.** Run exactly as distributed against the
live endpoint, ref-matcher matched **0 of 100** references — no errors, no 429s, 163 clean
HTTP 200s that all returned zero rows. It is not that the tool scores badly; it never gets a
candidate to score. Everything else in the `parsed` row exists only because of the
`^^xsd:string` patch in §1.3.

**Reading the two working arms.** They fail in opposite directions:

* **ref-matcher is conservative.** 293 of 365 correct and only 3 wrong — but **69 misses**,
  and on the 293 hard references it declines to answer 235 times. Of its 293 correct, **59 came
  from a DOI already present in the reference string** (the `year_and_doi` / `doi_title` rungs);
  on the references it actually had to find, it is **234 correct / 2 wrong / 65 miss**.
* **Crossref SBM never abstains.** 355 of 365 correct, but **0 misses anywhere** — it returns a
  top hit for every query, including all 293 hard references and all 50 unparsed footnotes.
  Its 286 ungraded answers on the hard set are not 286 gains; §7 measures what a sample of them
  are actually worth.

**The 286 ungraded is the number most likely to be misread, so it is stated plainly:** the gold
does not say whether those DOIs are right, and the one stratum of them that *was* checked by
hand (the 50 footnotes, §7) ran at **10 of 15 correct with reviews as the modal error**. The
hard set is not a pile of free resolutions.

**The 3 wrong that ref-matcher does make, and the 10 that Crossref SBM makes, are the same
class.** Four of Crossref's ten are chapter-versus-book or sibling-edition — `10.1090/ulect/022/02`
for `…/022`, `10.1007/978-1-4612-4620-6_2` for `…-6`, `_37` for Efron's `_38` — which is exactly
the `edition_mismatch` rung `confirm_s2_candidate` already carries.

**Registry coverage is not the confound it could have been.** All 5 lost-genuine DOIs and 6 of
the 7 must-not-link bad DOIs are present in OC Meta (probe: `results_presence.jsonl`, 12
queries). The one absent — `10.2307/1269348`, the Alwan book review — is scored
`bad_absent_from_registry`, never as a refusal, because a gate that never sees the record is
not a gate.

**Limitation, disclosed:** 3 of parsed's 1,106 queries returned HTTP 500 and were cached as
empty results by the version of the transport then running. A failure stored as `[]` is a
permanent miss on a zero-wire re-score. The caching of failures is fixed (commit `db4c885`);
the 3 affected queries remain in `cache_oc_patched.jsonl` and could each mask at most one
candidate list.

---

## 6. The kills

Both required by CLAUDE.md 3.4c: a gate that has never been shown to fire is not known to work.

| kill arm | mutants returning the ORIGINAL DOI (70 must-not-link) | near-positive returning the original (20) |
|---|---|---|
| **mutants** (author term at its default 7) | **37 of 70** (other DOI 4, no answer 29) | **14 of 20** |
| **mutants-noauthor** (author term zeroed) | **0 of 70** (other DOI 4, no answer 66) | **0 of 20** |

**The author-term kill fires, and it fires all the way.** Zeroing 7 of 48 points takes the tool
from 37 false accepts to **zero accepts of any kind** — it loses every true match too. That is
the real finding: this is not a discriminating author check, it is a scoring system whose whole
working range sits inside 7 points of its own threshold. The measured score distribution of the
354 accepted matches says the same thing — **288 of them score 24 or 25**, against an adjusted
threshold of 23.4. The margin between accepting and refusing is two or three points.

**What the kill does NOT show, stated rather than glossed:** the author surname is also a
*retrieval* filter, not only a score term — 290 of the 354 matches were retrieved through
`author_title` (276) or `year_author_volume` (14). Zeroing the weight changes scoring only, so
this kill measures the score term alone. The collapse is a scoring effect, not evidence that
author matching discriminates.

**The year result is the one that bears directly on our rule.** A ±3-year mutation still
resolves to the original work **30 times out of 40** (year+3: 15/20, year−3: 15/20), because an
exact year is worth **1 point of 48** and an adjacent year is worth **0**. A wrong year simply
cannot move this score across a threshold. Our resolver refuses a year gap greater than 1
outright (`decisions.yaml` §15.15, and the `crossref_year_mismatch` / `edition_mismatch` rungs
of `confirm_s2_candidate`). Measured on the same gold, on the same references: **ref-matcher's
scoring cannot express the constraint our year rule enforces categorically.** The title-wrong
mutation, by contrast, is caught 19 times in 20 — title is 14 of the 48 points, so the score is
title-dominated, and it discriminates on exactly the field it weights.

The 20 near-positive one-word corruptions ("bicycles" swapped into the title) come back to the
original 14 times in 20. The gold does not settle whether that is robustness or
under-discrimination, and this report does not either; it is reported as a number under both
readings.

---

## 7. The 50 unparsed footnote references — the search-based claim in practice

These are the references GROBID left with **no title or no first author**: 33 of the 50 sit in
the two pre-1990 footnote-style papers (`Page_1954` 19, `Besag_1974` 14), which is exactly the
class `LITKB_REFERENCES_2026-09-15.md` §65 named as a segmentation limit. Our resolver has
nothing to search on and resolves **0 of 50**. The raw strings themselves are intact — median
84 characters, none empty — so this is a real test of search-based matching, not a test of
whether a string exists.

**ref-matcher cannot be run on them at all**, because its only raw-string path is GROBID, and
GROBID is exactly what already failed on these (§3 — and the isolated-string `processCitation`
path, which might have done better, could not be started; the arm is NOT RUN).

**Crossref SBM returned a DOI for all 50 of 50.** It never abstains. So the only question that
matters is whether the DOIs are right, and that has to be answered by hand.

**15 hand-checked**, chosen deterministically — the 50 sorted by `ref_id`, first 15 with a DOI.
Each was compared against the **citing paper's own reference line**, taken from the
`<note type="raw_reference">` element of its TEI, not from GROBID's parse of it; the submitted
string was verified byte-equal to that line in all 15.

| # | reference (as the paper prints it) | Crossref returned | verdict |
|---|---|---|---|
| 1 | Abercrombie b29 — hidden Markov models and phenology… | `10.1109/amtrsi.2005.1469877` | **right** |
| 2 | Abercrombie b34 — *Project PRODES*, INPE technical report, 2012 | `10.18605/2175-7275/cereus.v10n2p193-210` — a Portuguese paper on MPI shared memory | **wrong**, unrelated |
| 3 | Bellettini b15 — Brezis, *Operateurs Maximaux Monotones*, North-Holland 1973 (a BOOK) | `10.1016/s0304-0208(08)72383-1` — "Chapitre II" of it | **wrong**, a chapter for the book |
| 4 | Bellettini b18 — Cohen/Dahmen/Daubechies/DeVore, preprint 2000 | `10.4171/rmi/345` — the published version | **right** |
| 5 | Besag b10 — Biometrika **59**, 43–48 | `10.1093/biomet/59.1.43` | **right** |
| 6 | Besag b11 — *nearest-neighbour systems*, Eur. Meeting of Statisticians, Budapest 1972 | `10.2307/2345225` — **a review of the proceedings volume** | **wrong**, review |
| 7 | Besag b17 — Appl. Statist. **21**, 113–120 | `10.2307/2346482` | **right** |
| 8 | Besag b2 — JRSS A **130**, 457–477 | `10.2307/2982519` | **right** |
| 9 | Besag b20 — Gleaves, unpublished PhD thesis, Liverpool 1973 | `10.1177/0725513608093282` — **a book review** that mentions Liverpool | **wrong**, review |
| 10 | Besag b25 — Biometrika **42**, 316–326 | `10.1093/biomet/42.3-4.316` | **right** |
| 11 | Besag b3 — JRSS A **131**, 579–580 | `10.2307/2343725` | **right** |
| 12 | Besag b30 — Biometrics **23**, 189–205 | `10.2307/2528155` | **right** |
| 13 | Besag b31 — J. Ecol. **56**, 35–45 | `10.2307/2258065` | **right** |
| 14 | Besag b32 — *Statistical Ecology* **Vol. 2**, 13–32, Penn State UP | `10.1126/science.176.4031.156.a` — **a Science review of *Statistical Ecology* Vol. 1** | **wrong**, review |
| 15 | Besag b35 — J. Appl. Prob. **10**, 605–612 | `10.1017/s0021900200118479` | **right** |

**10 of 15 right, 5 wrong.** Every one of the ten correct answers is a journal article with a
volume and a page range in the string — the cases where a bibliographic search has enough to
go on. Every one of the five errors is a reference to something that is **not a journal
article**: a technical report, a book, a conference proceedings, a PhD thesis, a book chapter.

**Three of the five errors are reviews of the cited work** — the identical defect class
`LITKB_S2_BATCHING_2026-09-15.md` §8 was written to close, arriving here by a different route.
That is the single most important number in this report for the gate question, and §8 takes it
up.

Extrapolated at the hand-checked rate, 50 footnote references would yield roughly 33 correct
DOIs and 17 wrong ones, three-fifths of the errors being reviews. **Unscreened, that is a net
loss**: it would put ~17 wrong works into the corpus to gain ~33 right ones, and the corpus has
no mechanism for noticing afterwards.

---

## 8. Thin records, reviews, and whether our gate is still needed

**The five lost-genuine resolutions** — correct DOIs our confirmation rule refuses because
Crossref's record is thin (`LITKB_S2_BATCHING_2026-09-15.md` §8.2). All five are present in OC
Meta, so both arms could in principle recover them.

| lost-genuine | our refusal | ref-matcher (parsed) | Crossref SBM |
|---|---|---|---|
| `10.1109/tsmc.1978.4309889` Abercrombie b16 | `crossref_no_author` | miss (best 10) | **right** |
| `10.1201/b12612-12` Burnicki b12 | `crossref_no_author` | miss | **right** |
| `10.1093/oxfordjournals.aje.a120609` Foody b14 | `crossref_title_ratio` | **right** (25) | **right** |
| `10.1093/oxfordjournals.aje.a120610` Foody b38 | `crossref_title_ratio` | **wrong** — returns `…a120609`, conflating parts I and II | **right** |
| `10.14358/pers.69.3.289` Burnicki b43 | `crossref_title_ratio` | **right** (25) | **right** |

**Crossref SBM recovers all five. ref-matcher recovers two, misses two, and gets one wrong** in
precisely the way our own report predicted — it cannot separate the Buck-and-Gart 1966 part I
from part II either. So on the specific failure the brief asked about, the search-based
approach genuinely does better, and the structured matcher does not.

### 8.1 The planted book-review test

**ref-matcher refuses all three reviews — but not by detecting a review.** Measured scores:
Hall b10 **21**, and the four editions 21–22, every one of them below the 23.4 adjusted
threshold. The mechanism is arithmetic, not discrimination: a book reference carries **no volume
and no pages**, so 3 + 8 = 11 of the 48 points are unreachable, and OC Meta's record for
`10.2307/2531038` carries **no author** (another 7 unreachable) under the *book's own title*
("Image Analysis And Mathematical Morphology."). Title similarity alone cannot clear the bar.

That is a refusal for the wrong reason, and it is fragile in a specific, checkable way: **had
the same review been cited with a volume and a page number, it would have scored 21 + 3 + 8 = 32
and been accepted.** The refusal depends on the *reference* being metadata-poor, not on anything
about the *record*. (Predicted-vs-measured: from the published weights I predicted 13 for Hall
b10 against a measured 21. The 8-point gap is not reconciled here; both numbers sit far below
threshold, so the direction of the finding does not turn on it.)

**Crossref SBM fails the test outright — and worse than the exact-DOI score shows.** Scored on
DOI equality it "returns the bad DOI" only 2 of 7 times. But the gold names *one specific* bad
DOI because that is what S2 proposed, and on the book reviews Crossref SBM returned **a review
every time** — just a different one twice:

| reference (a BOOK) | Crossref SBM returned | our gate's verdict |
|---|---|---|
| Wadsworth, *Modern Methods for Quality Control* | `10.1002/qre.4680020420` — a *QREI* review | **`type_mismatch`** |
| Getis, *Models of Spatial Processes* | `10.2307/214811` — the gold's named review | **`review_record`** |
| Serra, *Image Analysis and Mathematical Morphology* | `10.1002/cyto.990040213` — a *Cytometry* review | **`type_mismatch`** |

**3 of 3.** Two of those would have been scored "avoided the trap" by DOI equality alone. This
is why §5's must-not-link column understates, and why this report runs the returned records
through our own rule instead of stopping at the DOI string.

### 8.2 Our gate, run over the other proposer's output

`confirm_s2_candidate`'s rungs — review signature, review hint, book-vs-journal type, title
ratio, edition, first author, year — applied to the Crossref record the arm actually returned
for each of the 7 must-not-link references:

| verdict | n | which |
|---|--:|---|
| `type_mismatch` | 2 | the two book reviews Crossref files as journal articles |
| `review_record` | 1 | Getis, caught by the author-count signature (`['semple','getis','boots']`) |
| `crossref_title_ratio` | 2 | Efron `…_37` at 0.84, Foody b76 at 0.53 |
| `crossref_year_unknown` | 1 | Goodchild `…_chapter_one`, the gold's named bad DOI |
| `passes_our_gate` | 1 | `10.4135/9781412986311.n10`, ratio 1.00, year 2004 |

**Six of the seven wrong answers are refused by a gate the proposer knows nothing about.** The
seventh is the SAGE Handbook chapter Magidson 2004 actually cites — the gold's bad DOI for that
row is the *2010* Elsevier record, which Crossref SBM did not return; our gate passing it looks
correct rather than lenient.

**So: yes, the registry-confirmation gate is still needed, and the measurement says why.**
Neither matcher contains anything equivalent. ref-matcher's refusals of this class are a side
effect of sparse book metadata that a volume number would undo; Crossref SBM has no type or
review reasoning at all and returned a review 3 times in 3. The gate is the only component in
either pipeline that asks *what kind of record this is*, and it is proposer-independent: it was
written against S2's candidates and it fires unchanged on Crossref's.

### 8.3 The score is not a confidence signal

Crossref's relevance score does **not** separate right from wrong on our corpus. Across the 365
positives the correct answers run min 56.0 / median 120.1 / max 180.6, and the ten wrong ones run
63.1 to **197.4** — the highest-scoring answer in the wrong set outscores the median correct one.
No cut helps: at 60 it drops 2 correct and 0 wrong; at 80 it drops 15 correct and only 2 wrong.
(On the 15 hand-checked footnotes alone, a cut at 40 would have dropped 3 of the 5 errors and
none of the 10 correct — but that is post hoc on n=15 and is contradicted by the full 365, so it
is **not** a recommendation.) A threshold on Crossref's score cannot substitute for the gate.

---

## 9. Recommendation

**Keep ours. Do not adopt ref-matcher. Add Crossref search-based matching as a second
*proposer*, for the unparsed references only, behind `confirm_s2_candidate` unchanged.**

**Which case Kam's rule puts us in.** "Adopt where someone else measured better" presumes
someone else measured. Run as distributed against the live registry, ref-matcher measures
**0 of 100** — a dead default endpoint, and plain literals its own registry's Virtuoso will not
join. Everything good in its column required a patch I wrote. That is not a tool that measured
better; it is a tool that does not run, and adopting it would mean adopting my patch to somebody
else's unreleased script as a dependency. Three further reasons, kept separate from the scoring
because they are maintenance facts rather than measurements: it targets **OpenCitations Meta,
not our registry**; it has **no search-based mode**, which is the capability we actually lack;
and it is a 14-commit, 1-star, single-maintainer script repo, last commit 2025-11-19, with no
PyPI release, a `requirements.txt` missing `requests`, and three different endpoint URLs across
two files. Where it does work it is also **worse than what we have on our own hard cases**: 2 of
5 lost-genuine recovered, one of them resolved to the wrong half of a two-part paper.

**What did measure better, and is worth taking.** Crossref search-based matching on raw strings:
**355 of 365 positives, all 5 lost-genuine recovered, and a DOI for all 50 footnote references
our parser cannot touch** — the one capability gap we actually have. But it never abstains, and
unscreened it is a **net loss** on the footnotes: roughly 33 right against 17 wrong, three-fifths
of the errors being reviews of the cited work. It is a good proposer and a bad decider.

**Integration point, named, not implemented.** In `pipeline/litkb/admit/resolver.py` the S2 leg
calls `confirm_s2_candidate(cand, ref, client, pacer)` from inside `resolve_by_search` — S2
proposes, Crossref confirms. Add the bibliographic-search leg as a **second proposer into that
same call**: build a candidate from the top `works?query.bibliographic=<raw>` hit and hand it to
the **unchanged** `confirm_s2_candidate`, so every refusal keeps its existing reason name and the
histograms continue to join. Gate it to references where there is nothing else to try — no title
or no first author, i.e. the 50 — so it cannot dilute the 608 the current path already handles.
`confirm_s2_candidate` therefore sits **exactly where it sits today** and does not move in either
option; what changes is only who is allowed to propose to it.

**Two things to settle before it ships, both measured here, neither solved here.** First, the
confirmation rule needs the reference's own parsed fields to judge a candidate — title ratio,
first author, year — and on these 50 GROBID produced none of them; the rungs that fire on
Crossref SBM's output in §8.2 did so using fields from references that *were* parsed. Screening
the 50 therefore needs either the raw string parsed by something (the untested GROBID
`processCitation` path, §3 — the arm that did not run) or a rule that works from the raw string.
Second, Crossref's relevance score is not usable as the confidence input (§8.3).

**A/B before adoption**, on the frozen gold, per 3.4c: the 50 with the search leg enabled against
the 50 without, scored by hand as in §7, with the kill being that the planted book review must
still be refused. Until that runs, this report's recommendation is an argument for a design, not
an adopted design.

---

## 10. Reproducing this

```bash
# every arm re-scores at ZERO wire from the caches in litkb_derived/refmatch/
py -3.12 qc/instruments/litkb_refmatcher_score.py \
    --gold ../Reports/litkb_splink_gold_2026-09-15.json \
    --s2-rows ../Reports/litkb_s2_rows_2026-09-15.csv
```

Tests: `qc/test_litkb_refmatcher.py`, 30 passing — the typed-literal patch (including a
**ratchet** that re-scans upstream for a fourth plain-literal predicate), the below-threshold
non-match, the SPARQL binding shape, the CRLF-safe gold pin, the ungraded column, and the
never-cache-a-failure rule.

**The gate: `py -3.12 qc/check.py --fast` with `LITKB_PGPORT=1`.** Stated because it changes
what ran — 216 litkb Postgres tests skip under that port, so those guards were *not* exercised.

* `secrets` PASS · `ruff` PASS · `compile` PASS.
* `pytest qc`: **2,368 passed, 235 skipped, 1 failed** — the single failure is
  `test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, the expected
  pre-existing one. Two failures this work introduced were found and fixed before the run
  was recorded: a line-number citation in the instrument (banned in this repo because line
  numbers rot — now cited by symbol), and the literal string `sys.path.insert` sitting inside
  a comment that explained why the instrument deliberately *appends* instead, which the
  ledger ratchet matches as though it were a call site.
* **One test could not be run to completion and was deselected, rather than counted as a
  pass:** `test_registry_attribution.py::test_registry_covers_every_finished_manifest`. It
  shells out to `registry_from_manifests --dry-run` across `phase4/runs` on the Drive mount
  and had not returned after 15 minutes — the documented Drive-stall behaviour, unrelated to
  anything here (no registry or phase4 code is touched). The suite takes 33 minutes without it.

Tool clone: `opencitations/ref-matcher` @ `dfb0e7c06f2cc1495c1045ee69d22dc1fddbc96b`, ISC licence.
The `^^xsd:string` patch is applied at runtime by `type_literals()`; the upstream checkout is
never modified.

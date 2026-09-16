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
(the runtime default), `opencitations.net/meta/sparql` (`script/evaluation.py:11`), and
`sparql.opencitations.net` (the same line, commented out). That is endpoint drift, and it is
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
| **parsed-unpatched** | the same, tool exactly as shipped | run — the "as distributed" measurement |
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

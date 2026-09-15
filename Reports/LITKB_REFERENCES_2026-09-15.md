# litkb P6 — Citations: references, resolution, the citation graph

**Branch** `work/20260915-references` · **Date** 2026-09-15 · **Design** `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md`
§7 stage 6, §4.3–§4.4, §14 P6 · **Author** Claude (builder). **Not refereed.**

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
| in-text citation mentions | 1,386 | |
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
| `doi_title_mismatch` | 12 | the reference's DOI is registered but its registry title did not clear 0.85 against the parsed title (see §5) |
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
Kolmogorov 2004, Liu 2008, Melgani 2003, Solberg 1996; Guo 2018 → Morgenroth 2017 (cited 12 times
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
| 7 | 10.1559/152304006777681706 | Can error explain map differences over time? |
| 6 | 10.1016/j.rse.2007.11.013 | Some challenges in global land cover mapping |
| 6 | 10.1080/01431160500057848 | Improving land cover change estimates by accounting for classification error |
| 5 | 10.1007/s10021-006-0116-z | Characterization of Households and Its Implications for the Vegetation… |
| 5 | 10.1016/j.ufug.2012.09.002 | Predictors of the distribution of street and backyard vegetation |
| 5 | 10.1016/j.ufug.2013.11.004 | Individual households and their trees |
| 5 | 10.48044/jauf.2008.048 | A ground-based method of assessing urban forest structure |
| 4 | 10.1007/s00267-014-0310-2 | An Ecology of Prestige in New York City |
| 4 | 10.1073/pnas.0401545101 | Developing a science of land change |
| 3 | 10.1016/j.jenvman.2015.08.008 | Neighbourhood-scale urban forest ecosystem classification |

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
| DOI resolving to a different title → `unresolved` | 12 live cases in the corpus | §2 table |

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

**A measured tolerance, reported and NOT counted as a kill.** Swapping ONE word of a title leaves
17 of 20 references resolving to the original, at difflib ratios **0.80–0.94** against the 0.85 rule.
That is what a typo-tolerant title rule *is*; the 0.85 threshold was calibrated in P2
(`Reports/litkb_title_threshold_2026-09-14.csv`) and is not touched here. Calling this a kill, or
quietly raising the threshold to make it one, would be the design scoring itself (CLAUDE.md 3.4c).
The §14 wording — "real author + year, wrong title" — is covered by `title-wrong`, which fires 20/20.

**Two mutants resolved to a DIFFERENT work** (the kill held — neither is the original) and are
flagged `resolved_elsewhere`: a `year−3` mutant landed on the 1998 paper that shares a title stem
with the 2002 original, and a `title-word` mutant landed on a different ecology paper. Both are the
same lesson: a near-miss reference does not merely fail, it can succeed at the wrong work.

## 6. Guards and the harness

`qc/instruments/litkb_p6_mutations.py`, run 2026-09-15: **14 of 14 mutations fired**, both baselines
green, every file restored and the restore checked by sha256.

| row | guard weakened | effect |
|---|---|---|
| P6-G1 | DOI-first decision removed | 7 tests fail — **the kill** |
| P6-G2 | DOI may resolve to a different title | 2 fail (Averkov class) |
| P6-G3 | two accepted works collapse to the first | 1 fail |
| P6-G4 | a 429 / dead connection is cached | 4 fail |
| P6-G5 | a citation candidate is written `admitted` | 1 fail |
| P6-R1/R2/R3 | the shared ratio / surname / year rules | 1, 2, 2 fail |
| P6-S1…S6 | `normalize_doi` not applied, per call site | 1 each |

The six new `normalize_doi` call sites are registered into the **shared** per-call-site table, so
`qc/test_litkb_harness_sites.py` inside `qc/check.py` covers the whole package: 41 call sites, 40
with a row, 1 declared equivalent, no problems.

`cd Scripts && PYTHONUTF8=1 py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w8`:
2,487 passed, 1 failed — `test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, the
pre-existing failure this task allows, untouched by this branch.

## 7. What a referee should attack

1. **The 55.5 % is Crossref-only.** Reproduce it with a Semantic Scholar key and say what the rate
   becomes; the breaker is per-run state, so a keyed run starts closed.
2. **The 12 `doi_title_mismatch` are, on inspection, not wrong DOIs** — they are truncated or
   extended GROBID titles ("…Milwaukee, WI, USA. U" against "…Milwaukee, WI, USA"). The conservative
   refusal is right (no wrong edge is created), but the *cause* is a parse artefact, not a bad DOI,
   and the label says otherwise. Whether a containment rule belongs in the title check is a
   threshold decision for someone other than this build.
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

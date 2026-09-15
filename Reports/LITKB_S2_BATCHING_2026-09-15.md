# litkb — the Semantic Scholar leg: batched, paced, backed off, cached, counted

**Branch** `work/20260915-references` · **Date** 2026-09-15 · **Author** Claude (builder).
Follows `Reports/LITKB_REFERENCES_2026-09-15.md` (P6), whose 55.5 % resolution rate is a
**Crossref-only floor** because the Semantic Scholar and arXiv stages were rate-limited out of that
run. Kam's decision: **no API key**, on the vendor's own statement that the endpoints are public.

| | |
|---|---|
| Module | `Scripts/pipeline/litkb/admit/s2.py` (new) |
| Wiring | `Scripts/pipeline/litkb/extract/references.py` — `registry_stages`, `resolve_reference(…, s2=)` |
| Shared-client fix | `Scripts/pipeline/litkb/netutil.py` — a caller's `Content-Type` survives a body |
| Tests | `Scripts/qc/test_litkb_s2.py` (34; no DB, no network, no real sleep) |
| Mutation rows | `Scripts/qc/instruments/litkb_s2_mutations.py` (P7-G1…G7, P7-S1/S2 → the shared P2 table) |
| Instrument | `Scripts/qc/instruments/litkb_s2_batching.py` |
| Measured tables | `Reports/litkb_s2_arms_2026-09-15.csv`, `…_rows_…`, `…_verify_…` |

---

## 1. The premise, and what it actually buys

The vendor's statement, verbatim, fetched 2026-09-15 from
<https://www.semanticscholar.org/product/api>:

> "rate-limited to 1000 requests per second shared among all unauthenticated users"

P6's measured fact against that: **429 in 0.1 s on the first request, at any pace**. Both are true —
the pool is public and it is frequently exhausted, so there is no pace one can meter into it. The
only lever left is to ask less, and to wait properly when the answer is "not now".

**What batching can and cannot buy, stated before any number.** The batch endpoint keys on
IDENTIFIERS; it cannot take titles. A reference that reaches the S2 leg at all is, by construction of
`resolve_reference`, one with **no DOI** — the DOI decides when there is one. So on this corpus the
batchable population is tiny and the rest is one title per request, which no amount of batching
moves. Measured below: **0 batch calls — not one reference of the 293 was batchable** — against
**211 title-match calls**. (The first run made one batch call for 13 identifiers, then threw every
answer away: those were DOI-bearing references, which are decided above this leg and never consult
the prefill. The pre-pass now sends only references that can reach the leg, which on this corpus is
none of them.) The batch path is built, tested and kill-tested for the corpora that will have
identifiers (the 1,276-reference book P6 excluded); on THIS corpus its leverage is **zero, measured**,
and the table says so rather than implying otherwise.

The real reductions are elsewhere, which is the honest shape of this result:
`/paper/search?query=…&limit=3` (three candidates, four field groups) becomes
`/paper/search/match` (one candidate, the same four fields); a 429 is waited out on a jittered ladder
instead of being retried once and then tripping the stage out of the whole run; the leg is **paced**
like every other registry leg, which measurably halves the 429 share (§3); and every settled answer
is on disk, so a re-run costs nothing (verified: the suspect row in §4 was re-fetched at **0
requests, 1 cache hit**).

## 2. Patterns harvested, and the licence

Read, not run or installed: <https://github.com/spideryzarc/smart-semantic-scholar-mcp>
(`src/smart_semantic_scholar_mcp/server.py`, 1,025 lines, cloned 2026-09-15).

**HARVESTED from that repo** — the `POST /paper/batch` shape with ids in the JSON body and `fields`
in the query string; 500-id chunking (`for i in range(0, len(missing_ids), 500)`); the `DOI:` /
`ARXIV:` identifier prefixes; the index-aligned response walked with a null-tolerant guard
(`if paper and "paperId" in paper`); the "fetch only what the cache lacks" pre-pass; and an
exponential 429 back-off (`await asyncio.sleep(5 * (2 ** attempt))`, three retries).

**FROM THE DOCS** — the rate-limit sentence quoted above, and
"some endpoints have a corresponding batch or bulk endpoint"
(<https://www.semanticscholar.org/product/api/tutorial>). The endpoint reference at
`api.semanticscholar.org/api-docs/graph` is a JavaScript application that serves no prose to a
fetcher, so **the 500-id cap and the prefix spellings are harvested, not quoted from the vendor** —
which is why the client verifies the response length rather than trusting the shape (§5).

**OURS** — jitter, the `Retry-After` honour, the versioned cache key, the length-mismatch kill, the
request accounting, and the conversion into the shared candidate shape so that
`admit.resolver.judge_candidate` decides exactly as before.

**One harvested pattern deliberately NOT adopted**, and why it is named rather than silently
dropped: the repo paces its unauthenticated client at one request per 4 s (`AsyncLimiter(1, 4)`) with
a concurrency of 1. This leg is paced at **1 s**, matching `resolver.REGISTRY_MIN_INTERVAL` — this
pipeline's own registry cadence, already in use for Crossref — rather than a figure chosen for an
interactive tool. §3 measures what pacing bought at that interval; whether 4 s would buy more is not
measured here.

**LICENCE.** The repo's README shows an MIT badge and links a `LICENSE` file; **the repository ships
no LICENSE file** — the clone has none. So nothing was copied: `s2.py` is written from these ideas,
which are the endpoint's documented shape rather than authorship, and the repo is cited for the
patterns. If Kam wants the stricter reading, nothing needs re-doing — this already is the
reimplementation.

## 3. Before and after, same 293 references

Input: every P6 reference whose resolution was `unresolved` or `ambiguous` — **274 + 19 = 293** —
read from that run's own `references.jsonl`, same rows, same order, both arms. The acceptance rules
are byte-identical between arms (DOI-first, 0.85 ratio filter, first-author family, decisions.yaml
§15.15 ±1 year). Crossref answered from the P6 disk cache in both arms — **0 Crossref network
requests on either side** — so the wall clock below is the S2 and arXiv legs and nothing else.

| | before (P6 resolver) | after, unpaced | **after, paced (the result)** |
|---|--:|--:|--:|
| references | 293 | 293 | 293 |
| **wire requests to S2** | **4** | 163 | **127** (+107 cache hits) |
| … of them rate-limited (429) | 4 (100 %) | 60 (**37 %**) | 23 (**18 %**) |
| … answered 200 | 0 | 68 | 65 |
| … answered 404 ("no match") | 0 | 35 | 39 |
| title-match questions asked | 0 | 107 | **211 (all of them)** |
| batch calls / ids | 0 | 1 / 13 | **0 / 0** |
| requests to arXiv | 6 | 9 | 9 |
| requests to Crossref | 0 | 0 | 0 |
| **wall clock** | **261 s** | 1,092 s | **468 s** |
| of that, sleeping in the ladder | — | 712 s | 159 s |
| **resolved** | **0** | 20 | **33** |
| ambiguous | 19 | 19 | 19 |
| unresolved | 274 | 254 | **241** |
| stages tripped | arxiv, **semanticscholar** | arxiv, **semanticscholar** | **arxiv only** |

**The middle column is kept because it is the evidence for the pacing.** The first `after` run had no
minimum interval between wire requests: it burst at a pool this project has measured as exhausted and
took **37 % rate-limited answers**, spent 712 s waiting them out, and still had the stage tripped out
from under it after 107 of the 211 titles. Adding the same 1 s pacing the other registry legs use
(`resolver.REGISTRY_MIN_INTERVAL`) halved the 429 share to 18 %, **asked every one of the 211 titles**,
and finished in 43 % of the wall clock. Some of those 60 429s were the client's own doing; a rate
measured by unpaced code measures the code.

**The paced run is WARM** — 107 of its questions were answered from the disk cache written by the
unpaced run, so a cold paced run would put roughly 234 requests on the wire rather than 127. The
429 share, the resolution counts and the fact that the stage never tripped are unaffected by that;
the request total is.

**The `before` arm reproduces P6 exactly** — 274 unresolved, 19 ambiguous, 0 resolved, the same
reason histogram — which is what makes the comparison a comparison.

**Read the request column the right way round, because the headline is not "fewer requests".** The
old leg made 4 requests, got 4 × 429, tripped after two and then asked nothing at all for 291
references. The new leg made 127 and got **104 real answers**. The total went UP; what went down is
the cost per *question* — one candidate instead of three, one request per distinct title, every
settled answer on disk, and a wait instead of a retry-then-quit. Anyone quoting "fewer requests" from
this work is quoting the design intent, not the measurement. What the design actually bought is that
**the stage stayed alive**: 211 titles asked where the old arm asked 4.

**The pool 429s, and it also answers.** P6 measured "429 in 0.1 s, at any pace" and concluded the
stage was unusable. Measured here: **18 % rate-limited when paced**, 82 % answered. The pool is
**intermittent, not closed**, and that is the correction this phase makes to P6 §2. **`Retry-After`
was never sent** (`retry_after_seen: 0` over 23 rate-limit answers) — the honour is implemented and
unit-tested, but on this endpoint it has never fired in the wild.

**The lift over the 55.5 % floor.** 33 of the 658 P6 references move to `resolved`:
**365 → 398, 55.5 % → 60.5 %.** Of the 293 that reached this measurement, 11.3 % moved. **Four of the
33 are wrong or doubtful (§4), so the defensible lift is 29 — 365 → 394, 59.9 %.** The remaining 241
are §6.

## 4. Where the 33 came from, checked independently — and the class this found

Every one of the 33 is `via=semanticscholar` at ratio ≥ 0.93. Each DOI was then re-fetched **from
Crossref — not from S2** — and compared against the parsed reference with the same shared rules
(`litkb_s2_batching.py --verify`, table `Reports/litkb_s2_verify_2026-09-15.csv`). A registry
confirming its own answer is not a check.

**23 of 33 pass that check outright; the ten that do not split three ways.**

*Six are the check's own limits, not the resolution's* — Crossref carries **no author** for
`10.1109/tsmc.1978.4309889` and `10.1201/b12612-12`; parses Fleiss as `D.` for `10.2307/2529186`;
serves the Buck and Gart 1966 pair under one **truncated** title (ratios 0.72 / 0.70) where S2
separated part I from part II correctly; and truncates `10.14358/pers.69.3.289` at its subtitle
(0.56, same first author, same year). Titles otherwise match exactly.

***Three are genuinely the wrong work, and they are one class:* a JSTOR-type DOI for a REVIEW of the
book the reference cites.**

| reference | accepted DOI | what Crossref says that DOI is (measured, from the cached `/works/{doi}` bodies — 0 network) |
|---|---|---|
| Alwan 1988 `b13` — Wadsworth, *Modern Methods for Quality Control and Improvement* | `10.2307/1269348` | `journal-article` in **Technometrics**, 1987, authors **`['Sylwester', 'Wadsworth', 'Stephens']`** |
| Burnicki 2011 `b23` — Getis, *Models of Spatial Processes* | `10.2307/214811` | `journal-article` in **Geographical Review**, 1979, authors **`['Semple', 'Getis', 'Boots']`** |
| Hall 1985 `b10` — Serra, *Image Analysis and Mathematical Morphology* | `10.2307/2531038` | `journal-article` in **Biometrics**, 1983, authors **`['Diggle', 'Serra']`** |

**"Book review" is an inference; the author list is the measurement.** Each of these is a journal
article in a journal other than the book's publisher, carrying the book's exact title, and its author
list is *the reviewer followed by the book's authors* — which is how Crossref encodes a review of a
book. That is the strongest evidence available without reading the articles, and it is stated as the
inference it is. What does not depend on the inference: **the accepted DOI's first author is not the
reference's first author**, under an identical title. That alone makes it a different work.

**The mechanism, because it is the finding.** A review carries the reviewed book's exact title. S2's
record for such a DOI carries the title AND the BOOK's authorship — its record for
`10.2307/1269348` returns `"family": "H. Wadsworth", "year": 1986`, verbatim from the cached
response. So all three of the resolver's rules agree: ratio 1.00, first author Wadsworth, year 1986.
**The rules did not fail. The registry merged a book with its review, and the DOI it then offers is
the review's.** Crossref, asked the same DOI, names the reviewer — which is exactly why the check
must go to a different registry. This is P6 §5's `resolved_elsewhere` class arriving through a new
door: a fuzzier registry has more of them, and a book-heavy reference list is where they live.

*One more is doubtful* — Foody 2010 `b58`, *Latent class models*: the reference is Magidson 2004;
Crossref says the DOI is a `book-chapter` in the **International Encyclopedia of Education**, 2010,
author `['Vermunt']` (measured, same cached bodies). Same pair of authors in the literature, different
volume and year; a sibling, probably not the cited one.

**Measured rate of the wrong-work class: 3 certain and 1 doubtful in 33, ~9–12 %.** It is recorded,
not patched: the obvious rule (refuse a DOI whose Crossref record disagrees with S2 about the first
author) would be a rule change proposed and scored by the same session, which CLAUDE.md 3.4c forbids.
It was the first item a referee should take, §6 carried it forward, and §8 is the rule that closed it.

## 5. The kills (CLAUDE.md 3.4c — each shown firing on a known-bad input)

`qc/instruments/litkb_s2_mutations.py`: **9 of 9 fired**, baselines green before and after, each file
restored and the restore checked by sha256.

| row | guard weakened | effect |
|---|---|---|
| **P7-G1** | the batch length check | **the batching kill** — a short response is zipped anyway and every record after the gap attaches to the WRONG id (1 test fails) |
| P7-G2 | only-a-settled-answer caching | a 429 or an error body is cached as a permanent phantom miss (12 fail) |
| P7-G3 | the schema version in the cache key | a body written for an older parser is served to a newer one (2 fail) |
| P7-G4 | the back-off ladder emptied | the first 429 ends the request with no wait and no retry (2 fail) |
| P7-G5 | a failed batch fills the prefill | one transport error answers a whole chunk "not found", unasked (1 fail) |
| P7-G6 | the reachability filter on the pre-pass | a DOI-bearing reference takes a batch slot, spending a shared-pool request on an answer nothing reads |
| P7-G7 | the pacer | requests go to the exhausted pool back to back, so the client causes the 429s it then waits out |
| P7-S1/S2 | `normalize_doi` per call site | one work takes two batch identifiers / a candidate DOI is returned as the registry spelled it (1 each) |

**A kill that had to be sharpened, and how it was caught.** P7-G4 (empty ladder) first fired on only
ONE test: the 429-storm test asserted `len(calls) == len(BACKOFFS) + 1` and `sleeps == list(BACKOFFS)`
— arithmetic that an empty ladder satisfies trivially. A test written against a constant goes quiet
when the mutant changes the constant. It now pins the concrete numbers (5 requests; 5, 10, 20, 40 s;
75 s total) and P7-G4 fires on two. This is the same lesson as the P6 `year+3` mutant: a mutation
defined relative to the thing it mutates can land inside the rule.

**The P6 kills still fire with the S2 leg on** (`qc/test_litkb_s2.py`): a reference carrying a DOI
never reaches this leg (the §14 P6 headline kill — a corrupted DOI cannot be rescued by a title match
here, and `match_calls` is asserted to be 0); a wrong title, a wrong first author and a year three
out from S2 are all refused; two accepted works from S2 are `ambiguous`, not a resolution.
**These are STUB-FED, so as evidence about the archive they are UNVALIDATED in the 3.4c sense** —
they test the code, not the claim. The live counterpart is §4, which is the same question asked of
real registry answers, and it found a class the stubs could not: the stubs never invented a review
DOI carrying a book's authorship.

## 6. What remains a floor, and why

**60.5 % is still a floor, and the arXiv stage is still shut** — arXiv tripped in both arms (9 × 429,
0 answers). The S2 stage did not trip in the paced run: all 211 titles were asked. The 241 that
remain unresolved are, by reason:

| cause | n | can this leg reach it? |
|---|--:|---|
| `no_title_or_author` | 50 | **No.** GROBID parsed no title or no first author; there is nothing to send to a title-match endpoint. A parse problem, not a registry one |
| `best=<stage>:<ratio>` (asked and refused) | 152 | Asked. These are the real refusals — the rules saw a candidate and said no |
| `accepted at semanticscholar but the candidate carries no DOI` | **27** | **New reason, and the largest recoverable group this phase found.** S2 matched the work and all three rules agreed, but its record carries no DOI, so there is no key. Keying such a work by S2's `paperId` is a design question for P5, not a resolver change |
| `doi_title_contained` / `doi_title_mismatch` / `doi_not_registered` | 12 | No — the DOI decides, by design |

Plus the 19 `ambiguous`, untouched: they are decided at Crossref before this leg runs.

**What a referee should attack, in the order I would.**
1. **Three of the 33 new resolutions are a review of the cited book, not the book** (§4), and one
   more is a sibling — a 9–12 % wrong-work rate in the material this phase adds. It is named, not
   fixed. The candidate rule (refuse when Crossref and S2 disagree about the first author) must be
   built and scored by someone other than this session, and measured on a corpus with enough books
   to count the class properly. **CLOSED 2026-09-15 by a later session — see §8.** **Until that was done, the 33 were to be read as 29 defensible plus 4
   to check by hand.**
2. **The request count went up**: 127 wire requests (≈234 cold) for 33 resolutions, 468 s against
   261 s. Argue that the old arm's 4 requests were the honest budget. The counter-argument is in the
   table — 104 answers against 0 — but the trade is real and grows with the corpus.
3. **The 27 DOI-less S2 matches** are the largest recoverable group here and nothing was done with
   them.
4. **One laptop, one afternoon, a warm cache.** 18 % rate-limited is not a property of the pool.
   Re-run cold, and at another hour; the breaker's trip point (2 consecutive) now sits behind a
   5-request ladder and that product is unmeasured.
5. **The batch path is unexercised by this corpus** — measured leverage zero. Tested and
   kill-tested, never yet measured on real traffic.
6. **The stub-fed near-miss kills** (§5) should be re-run through the live leg on the P6 near-miss
   sample now that the stage stays open.

## 7. The ladder

`cd Scripts && PYTHONUTF8=1 py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w8`:
secrets PASS, ruff PASS, compile PASS, then
**1 failed, 2,534 passed, 20 skipped, 1 xfailed in 451 s** (2,497 at the P6 commit + the 34 new S2
tests + the rest of the branch), litkb Postgres tests 215 passed. The single failure is
`test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, the pre-existing one this task
allows, untouched by this branch.

The mutation campaign (§5) and the two measurement arms (§3) were run on the same tree; the arms'
inputs are the P6 JSONL, which this branch does not write.


---

## 8. The rule that closes the class: S2 proposes, Crossref confirms (2026-09-15, later session)

§4 named the wrong-work class and deliberately did not patch it, because a design may not be
accepted on numbers it produced about itself (CLAUDE.md 3.4c). This section is the rule, built and
measured against the same 293 references.

**THE RULE.** A Semantic Scholar candidate never resolves on S2 data alone. Its DOI is looked up at
Crossref (cached, paced 1/s) and the CROSSREF record must pass the existing 0.85 ratio filter and
the existing first-author + year discriminator against the reference — so an S2 authorship merge
cannot carry a resolution. The record must additionally be TYPE-COMPATIBLE, and every refusal keeps
its own name:

| reason | when | state |
|---|---|---|
| `review_record` | a `journal-article` whose title begins with a review marker, or whose container is a review section, or — the signature that fires on all three measured cases — whose author list begins with someone who is NOT the reference's first author while the reference's first author appears LATER in it (the reviewer, then the work) | unresolved |
| `type_mismatch` | the reference presents as a book (a publisher and no journal, or an edition cue) and Crossref says `journal-article` | unresolved |
| `edition_mismatch` | same title, shared authorship, Crossref year more than ±1 from the reference's | **ambiguous** |
| `crossref_not_registered` / `crossref_title_ratio` / `crossref_no_author` / `crossref_author_mismatch` / `crossref_year_mismatch` / `crossref_year_unknown` | the shared rules, applied to the Crossref record | unresolved |

Two doors, not one: `extract.references.resolve_by_search` (stage 6) and `admit.resolver.resolve_doi`
(gate 0, the acquisition path, where the returned DOI is handed straight to the fetcher and an
unconfirmed one would download the review). One function, `resolver.confirm_s2_candidate`.

**ONE STATED WIDENING and ONE STATED HOLE.** The brief's sibling-edition test is "same title + first
author"; what is implemented also accepts "the Crossref record's first author appears anywhere in the
reference's parsed author list", because the measured case (Foody b58) is Magidson & Vermunt 2004
offered as Vermunt 2010 — first author differs, and a narrower test would have filed it under author
mismatch. The hole: for a candidate whose DOI is the `10.48550/arXiv.` form, Crossref is not the
registry, so it passes through UNCONFIRMED under a reason that says so
(`s2_arxiv_doi_unconfirmed`). It is marked `archive_ok=False` and never fetched, and the class being
closed here — a journal's review of a cited book — cannot occur on a preprint.

### 8.1 Measured, same 293 references, same input rows

`qc/instruments/litkb_s2_batching.py --arm confirmed`, then `--report`. **0 wire requests to
Semantic Scholar and 0 to Crossref**: every answer came from the P6 and §4 disk caches, so this arm
re-scores exactly the material §3 and §4 are written from.

| | before (P6 resolver) | after (§3, the paced S2 leg) | **confirmed (this rule)** |
|---|--:|--:|--:|
| references | 293 | 293 | 293 |
| **resolved** | 0 | 33 | **20** |
| ambiguous | 19 | 19 | **23** |
| unresolved | 274 | 241 | **250** |
| requests to S2 / Crossref | 4 / 0 | 127 / 0 | **0 / 0** (fully cached) |

**One reason was RENAMED, so the histograms join.** P6's
`accepted at semanticscholar but the candidate carries no DOI` (27 rows) now reads
`s2_candidate_has_no_doi (nothing to confirm)` — the same 27 references, refused at the same point,
before any Crossref lookup is spent on a candidate that has no DOI to look up.

Refusal reasons in the confirmed arm, for the 13 rows that moved:

| reason | n | rows |
|---|--:|---|
| `review_record` | 3 | Alwan b13 `10.2307/1269348`; Burnicki b23 `10.2307/214811`; Hall b10 `10.2307/2531038` |
| `type_mismatch` | 1 | Chrisman b6 `10.2307/2529186` (Fleiss's book against a Biometrics `journal-article`) |
| `edition_mismatch` | 4 | Foody b58 `10.1016/b978-0-08-044894-7.01340-3` (2010 vs 2004); Efron b0 `10.1007/978-1-4612-0919-5_38` (1992 vs 1973); Foody b76 `10.1142/9789814329804_0014` (2011 vs 2002); Goodchild b1 `10.4324/9780203303245_chapter_one` (2010 vs 2004) |
| `crossref_title_ratio` | 3 | Burnicki b43 (0.56); Foody b14 (0.72); Foody b38 (0.70) |
| `crossref_no_author` | 2 | Abercrombie b16 `10.1109/tsmc.1978.4309889`; Burnicki b12 `10.1201/b12612-12` |

**The four cases §4 named are all refused, each under its own name** — the three reviews as
`review_record`, the sibling edition as `edition_mismatch` (ambiguous, not resolved).

### 8.2 What the rule costs, named row by row

**Five of the 13 are genuine resolutions lost, and they are five of the SIX the §4 verify rung had
already marked as the check's own limits** (the sixth, Chrisman b6, is refused on a measurement
rather than on Crossref's thinness — see below):

  * `10.1109/tsmc.1978.4309889` (Abercrombie b16) and `10.1201/b12612-12` (Burnicki b12) — Crossref
    carries **no author at all** for these records, so the discriminator cannot run. Correct
    resolutions, refused. `crossref_no_author`.
  * `10.1093/oxfordjournals.aje.a120609` / `a120610` (Foody b14, b38) — Crossref serves the Buck and
    Gart 1966 pair under one TRUNCATED title (ratios 0.72 / 0.70) where S2 separated part I from
    part II correctly. Correct resolutions, refused. `crossref_title_ratio`.
  * `10.14358/pers.69.3.289` (Burnicki b43) — Crossref truncates at the subtitle (0.56). Correct
    resolution, refused. `crossref_title_ratio`.

That is the honest price: **the rule is only as good as Crossref's record**, and where Crossref's
record is thin it refuses work S2 had right. 5 genuine resolutions traded for 3 certainly-wrong ones
and 4 newly-flagged siblings.

**Chrisman b6 is refused, and what is measured about it is the TYPE, not a review.** §4 filed
`10.2307/2529186` under "the check's own limits" because Crossref's first author for it comes back
as the family name `D.` — one letter. What that one letter is cannot be read off the record: a
truncated surname and a given name in the family slot are indistinguishable there, and this report
does not guess. Measured: the reference is a Wiley BOOK (publisher, no journal) and the Crossref
record is a `journal-article` in *Biometrics*, so the type test refuses it as `type_mismatch`. The
review detector deliberately does not claim it — a one-letter family has the exact shape of a
prepended reviewer and is not evidence of one, so the detector requires a prefix of at least three
characters. Whether this row is a genuine resolution lost therefore stays OPEN; it is not counted
among the five.

**Three of the 23 rows the §4 verify rung passed are now `edition_mismatch`** (Efron b0, Foody b76,
Goodchild b1). They are not a regression in the check: **the verify rung tested ratio and first
author only — it never tested the year**, so a reprint of Akaike 1973 in a 1992 Springer volume
passed it. Under the resolver's own year rule they were never acceptable.

### 8.3 The kills (CLAUDE.md 3.4c)

`qc/instruments/litkb_s2_mutations.py --only P7-S3,P7-C1,P7-C2,P7-C3`: **4 of 4 fired**, baselines
green before and after, every file restored and the restore checked by sha256.

| row | weakened | effect |
|---|---|---|
| **P7-C1** | the confirmation guard in stage 6 | the review DOI resolves again as the book (1 test fails) |
| **P7-C2** | the same guard at gate 0 | the acquisition path resolves the review and would fetch it (2 fail) |
| **P7-C3** | the review DETECTOR alone | the three cases are still refused — as `crossref_author_mismatch` — so the row fires ONLY because the tests pin the reason by name (4 fail). A kill for a class that is invisible in the outcome has to be asserted on the name; this is the P7-G4 lesson again |
| P7-S3 | `normalize_doi` at the new call site | one work costs two Crossref lookups and two cache entries (1 fail) |

The unit kills replay the **real cached Crossref bodies** of the four cases (trimmed to the fields
`parse_crossref` reads, 0 network), not stubs invented for the test — which is what makes them
evidence about the archive rather than about the test. The control is in the same file: a genuine S2
proposal that Crossref confirms (`10.1109/cvpr.2005.177`, Dalal & Triggs) still resolves, end to end
through `resolve_by_search`.

### 8.4 The rate, restated

§3's headline was 365 → 398, 55.5 % → 60.5 %, with §4 warning that 4 of the 33 were wrong or
doubtful and the defensible figure was 29 (59.9 %). Measured under the rule: **20 resolutions, 365 →
385, 58.5 %** — and this one is defensible by construction rather than by hand-checking, because
every one of the 20 has been confirmed at a registry other than the one that proposed it. The 5
genuine losses of §8.2 are the gap between the two numbers and are named row by row above; recovering
them means a better Crossref record, not a weaker rule.

### 8.5 The ladder, at this commit

`cd Scripts && PYTHONUTF8=1 py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w8`:
secrets PASS, ruff PASS, compile PASS, then **1 failed, 2,546 passed, 19 skipped, 1 xfailed in
1,319 s**, litkb Postgres tests 215 passed. The single failure is
`test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, the pre-existing one this task
allows, untouched by this work. The per-call-site self-check is green: 45 call sites, 44 covered by a
row, 1 equivalent — the new `confirm_s2_candidate::normalize_doi` site is row P7-S3.

The full P7 mutation campaign was re-run after the test file changed, not just the four new rows:
**13 of 13 fired**, baselines green before and after, every file restored and the restore checked by
sha256.

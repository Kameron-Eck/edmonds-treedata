# litkb — the Semantic Scholar leg: fewer requests, batched, backed off, counted

**Branch** `work/20260915-references` · **Date** 2026-09-15 · **Author** Claude (builder).
Follows `Reports/LITKB_REFERENCES_2026-09-15.md` (P6), whose 55.5 % resolution rate is a
**Crossref-only floor** because the Semantic Scholar and arXiv stages were rate-limited out of that
run. Kam's decision: **no API key**, on the vendor's own statement that the endpoints are public.

| | |
|---|---|
| Module | `Scripts/pipeline/litkb/admit/s2.py` (new) |
| Wiring | `Scripts/pipeline/litkb/extract/references.py` — `registry_stages`, `resolve_reference(…, s2=)` |
| Shared-client fix | `Scripts/pipeline/litkb/netutil.py` — a caller's `Content-Type` survives a body |
| Tests | `Scripts/qc/test_litkb_s2.py` (31; no DB, no network, no real sleep) |
| Mutation rows | `Scripts/qc/instruments/litkb_s2_mutations.py` (P7-G1…G5, P7-S1/S2 → the shared P2 table) |
| Instrument | `Scripts/qc/instruments/litkb_s2_batching.py` |
| Measured tables | `Reports/litkb_s2_arms_2026-09-15.csv`, `Reports/litkb_s2_rows_2026-09-15.csv` |

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
moves. Measured below: **1 batch call carrying 13 identifiers, 0 of which reached the leg**, against
**107 title-match calls**. The batch path is built, tested and kill-tested for the corpora that will
have identifiers (the 1,276-reference book P6 excluded); on THIS corpus its leverage is zero and the
table says so.

The real reductions are elsewhere and they are small, which is the honest shape of this result:
`/paper/search?query=…&limit=3` (three candidates, four field groups) becomes
`/paper/search/match` (one candidate, the same four fields); a 429 is waited out on a jittered ladder
instead of being retried once and then tripping the stage out of the whole run; and every settled
answer is on disk, so a re-run costs nothing (verified: the suspect row in §4 was re-fetched at
**0 requests, 1 cache hit**).

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

| | before (P6 resolver) | after (batched S2 leg) |
|---|--:|--:|
| references | 293 | 293 |
| **requests to S2** | **4** | **163** |
| … of them rate-limited (429) | 4 (100 %) | 60 (37 %) |
| … answered 200 | 0 | 68 |
| … answered 404 ("no match") | 0 | 35 |
| requests to arXiv | 6 | 9 |
| requests to Crossref | 0 | 0 |
| **wall clock** | **261 s** | **1,092 s** |
| of that, sleeping in the S2 ladder | — | 712 s |
| **resolved** | **0** | **20** |
| ambiguous | 19 | 19 |
| unresolved | 274 | 254 |
| stages tripped | arxiv, semanticscholar | arxiv, semanticscholar |

**The `before` arm reproduces P6 exactly** — 274 unresolved, 19 ambiguous, 0 resolved, the same
reason histogram — which is what makes the comparison a comparison.

**Read the request column the right way round.** Asking less per question bought the ability to ask
at all: the old leg made 4 requests, got 4 × 429, tripped after two and then asked nothing for 291
references. The new leg made 163 and got **103 real answers**. The count went UP because the ladder
kept the stage alive; the count per *question* went down (one candidate instead of three, one request
per distinct title, cached). Anyone quoting "fewer requests" from this work is quoting the design
intent, not the measurement.

**The pool 429s, and it also answers.** 60 of 163. P6 measured "429 in 0.1 s, at any pace" and
concluded the stage was unusable; the measurement here says the pool is **intermittent**, not closed,
and a client that waits gets through 63 % of the time. That is the correction this phase makes to
P6's §2. **`Retry-After` was never sent** (`retry_after_seen: 0` over 60 rate-limit answers) — the
honour is implemented and unit-tested, but on this endpoint it has never fired in the wild.

**The lift over the 55.5 % floor.** 20 of the 658 P6 references move to `resolved`:
**365 → 385, 55.5 % → 58.5 %.** Of the 293 that reached this measurement, 6.8 % moved. That is the
measured lift; the remaining 254 are §6.

## 4. Where the 20 came from, checked independently

Every one of the 20 is `via=semanticscholar` at ratio ≥ 0.93, and every DOI was re-fetched **from
Crossref** — not from S2 — and compared against the parsed reference (`scratchpad/verify20.py`
pattern; the check is the shared `title_match_ratio` + `family_matches`). **19 of 20 verify.** Five
tripped the crude check and four of those five are the check's own limits, not the resolution's:
Crossref carries no author for `10.1109/tsmc.1978.4309889`; parses Fleiss as `D.` for
`10.2307/2529186`; and serves both halves of the Buck & Gart 1966 pair under one truncated title,
where S2 separated part I from part II correctly (`a120609` / `a120610`).

**The one that does not verify, and the mechanism.** Alwan 1988 `b13` — the reference is the
Wadsworth, Stephens & Godfrey book *Modern Methods for Quality Control and Improvement*; the DOI
`10.2307/1269348` is a **Technometrics review** of that book, whose Crossref first author is the
reviewer (Sylwester), not Wadsworth. S2's record for that DOI carries the title and
`"family": "H. Wadsworth", "year": 1986`, so the reference's own rules — ratio 1.00, first author
Wadsworth, year 1986 — accept it. **The rules did not fail; the registry's metadata attaches a book's
authorship to its review's DOI.** This is the `resolved_elsewhere` class P6 §5 named, arriving through
a new door: a fuzzier registry is a registry with more of them. It is recorded here rather than
patched, because the fix would be a rule change scored by the code that proposed it (CLAUDE.md 3.4c).
Rate of the class as measured: **1 in 20**.

## 5. The kills (CLAUDE.md 3.4c — each shown firing on a known-bad input)

`qc/instruments/litkb_s2_mutations.py`: **7 of 7 fired**, baselines green before and after, each file
restored and the restore checked by sha256.

| row | guard weakened | effect |
|---|---|---|
| **P7-G1** | the batch length check | **the batching kill** — a short response is zipped anyway and every record after the gap attaches to the WRONG id (1 test fails) |
| P7-G2 | only-a-settled-answer caching | a 429 or an error body is cached as a permanent phantom miss (12 fail) |
| P7-G3 | the schema version in the cache key | a body written for an older parser is served to a newer one (2 fail) |
| P7-G4 | the back-off ladder emptied | the first 429 ends the request with no wait and no retry (2 fail) |
| P7-G5 | a failed batch fills the prefill | one transport error answers a whole chunk "not found", unasked (1 fail) |
| P7-S1/S2 | `normalize_doi` per call site | one work takes two batch identifiers / a candidate DOI is returned as the registry spelled it (1 each) |

**A kill that had to be sharpened, and how it was caught.** P7-G4 (empty ladder) first fired on only
ONE test: the 429-storm test asserted `len(calls) == len(BACKOFFS) + 1` and `sleeps == list(BACKOFFS)`
— arithmetic that an empty ladder satisfies trivially. A test written against a constant goes quiet
when the mutant changes the constant. It now pins the concrete numbers (5 requests; 5, 10, 20, 40 s;
75 s total) and P7-G4 fires on two. This is the same lesson as the P6 `year+3` mutant: a mutation
defined relative to the thing it mutates can land inside the rule.

**The P6 kills still fire with the S2 leg on**, tested directly rather than assumed
(`qc/test_litkb_s2.py`): a reference carrying a DOI never reaches this leg (the §14 P6 headline kill
— a corrupted DOI cannot be rescued by a title match here, and `match_calls` is asserted to be 0); a
wrong title, a wrong first author and a year three out from S2 are all refused; two accepted works
from S2 are `ambiguous`, not a resolution.

## 6. What remains a floor, and why

**58.5 % is still a floor, and the arXiv stage is still shut.** The breaker tripped both stages in
both arms. The 254 that remain unresolved are, by reason:

| cause | n | can this leg reach it? |
|---|--:|---|
| `no_title_or_author` | 50 | **No.** GROBID parsed no title or no first author; there is nothing to send to a title-match endpoint. A parse problem, not a registry one |
| `best=<stage>:<ratio>` (searched, refused) | 180 | Partly — 107 titles were asked, the rest were behind the breaker when it tripped |
| `accepted at semanticscholar but the candidate carries no DOI` | **12** | **New reason, new opportunity.** S2 matched the work and agreed with all three rules, but its record carries no DOI. These are real matches this pipeline cannot key. Keying a work by S2's `paperId` where no DOI exists is a design question for P5, not a resolver change |
| `doi_title_contained` / `doi_title_mismatch` / `doi_not_registered` | 12 | No — the DOI decides, by design |

Plus the 19 `ambiguous`, untouched: they are decided at Crossref before this leg runs.

**What a referee should attack.**
1. **The request count went up.** Argue that the old arm's 4 requests were the honest budget and this
   one spends 163 for 20 resolutions. The counter-argument is in the table (103 answers vs 0) but the
   trade — 1,092 s against 261 s for 293 references — is real and is not free at corpus scale.
2. **Re-run when the pool is busier.** 37 % rate-limited is one laptop, one afternoon. The breaker's
   trip point (2 consecutive) now interacts with a 5-request ladder; whether that is the right
   product is unmeasured.
3. **The 12 DOI-less S2 matches** are the largest single recoverable group this phase found and it
   did nothing with them.
4. **One resolution in 20 landed on a review of the work, not the work** (§4). Measure that class on
   a corpus where it can be counted properly.
5. **The batch path is unexercised by this corpus** — 13 identifiers, 0 reaching the leg. It is
   tested and kill-tested, and it is not yet measured on real traffic.

## 7. The ladder

`cd Scripts && PYTHONUTF8=1 py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w8`:
secrets PASS, ruff PASS, compile PASS, then
**1 failed, 2,531 passed, 20 skipped, 1 xfailed in 443 s** (2,497 at the P6 commit + the 31 new S2
tests + the rest of the branch), litkb Postgres tests 215 passed. The single failure is
`test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, the pre-existing one this task
allows, untouched by this branch.

The mutation campaign (§5) and the two measurement arms (§3) were run on the same tree; the arms'
inputs are the P6 JSONL, which this branch does not write.

# litkb P6 "Citations" — referee, round 2

**Branch** `work/20260915-references` · HEAD `e11068d` · range `9addcee..e11068d` · **Date** 2026-09-15
**Referee** Claude Opus 5 (independent of the builder and of round 1).
Under review: the round-1 referee fixes (mention count, title-less DOI, containment label), the
Semantic Scholar batching client, and the "S2 proposes, Crossref confirms" rule (§8 of
`Reports/LITKB_S2_BATCHING_2026-09-15.md`).

**VERDICT: READY TO MERGE WITH FIXES.** Every measured number in the review range reproduces, all
20 confirmed resolutions are the right works, the five "lost" resolutions are genuinely
unconfirmable and not rule bugs, and 3 of 4 of my own batch-client kills fire (the fourth is not a
gap — §6). The fixes are **two false sentences in the reports and one named hole in the review
detector**; none of them changes a number, and none is a reason to hold the branch if they are
corrected. The rule itself is sound: I could not make it accept a wrong work that it is designed to
catch, and I could not make it refuse a right one that Crossref knows properly.

Everything below was measured on this tree. Where I ran the builder's own instrument, I say so and
say what I compared it against. **0 Semantic Scholar and 0 Crossref requests went on the wire for
any of it.**

---

## 1. The 293-reference table reproduces

`qc/instruments/litkb_s2_batching.py --arm confirmed`, re-run by me from the disk cache:

| | §8.1 claims | I measure |
|---|--:|--:|
| references | 293 | **293** |
| resolved | 20 | **20** |
| ambiguous | 23 | **23** |
| unresolved | 250 | **250** |
| S2 wire requests / Crossref wire requests | 0 / 0 | **0 / 0** (211 S2 answers, all cache hits) |
| rows that moved `after` → `confirmed` | 13 | **13** |

The 13 moved rows and their reasons are **byte-for-byte the §8.1 table** — 3 `review_record`
(Alwan b13, Burnicki b23, Hall b10), 1 `type_mismatch` (Chrisman b6), 4 `edition_mismatch` (Foody
b58, Efron b0, Foody b76, Goodchild b1), 3 `crossref_title_ratio` (Burnicki b43 0.56, Foody b14
0.72, Foody b38 0.70), 2 `crossref_no_author` (Abercrombie b16, Burnicki b12). The four cases §4
named are each refused under their own name, as claimed.

**Two things the report should say and does not.**

* **The run is not fully cached.** It put **46 requests on export.arxiv.org, 5 of them 429s**.
  §8.1's "every answer came from the P6 and §4 disk caches" is true of S2 and Crossref — the two
  registries the claim is about — and false of arXiv. My run and the committed `confirmed.json`
  differ in **42 of 293 rows**, every difference a `; skipped=arxiv (rate-limited)` tail present in
  one and absent in the other, plus one row (`Burnicki b54`) whose losing `best=` candidate changed
  because the arXiv stage stayed open for me. **No state and no DOI changed anywhere.** The
  headline is reproducible; the reason strings are not byte-stable across runs, and a reader
  diffing the CSV should know that.
* **A quote has drifted.** §8.1 lists `Goodchild b1 … (2010 vs 2004)`. The reason string the code
  emits, then and now, is *"crossref 2010 vs reference **2002**"*. The row is right; the year in
  the prose is not.

## 2. All 20 confirmed resolutions are the right works

I checked every one of the 20 against the **cached Crossref record** (type, container-title, author
list, year) and against the **raw reference text as the citing paper printed it**, read out of
`references.jsonl`. Not one is wrong.

The 20 span the shapes that would break a weaker rule and do not break this one: proceedings
articles cited as conference papers (Dalal & Triggs, Kato, `10.1109/cvpr.2005.177`,
`10.1109/icpr.2002.1044836`), LNCS chapters cited as ECCV papers (Kim & Zabih, Szeliski et al.),
two genuine books (James et al. *ISL*, Congalton & Green), and eleven journal articles. Title
ratios run 0.93–1.00 and every first author and year agrees.

Two I looked at hardest, because they are the ones a sceptic would pick:

* **Kato b35** — the accepted record's `container-title` is *"Object recognition supported by user
  interaction for service robots"*, which is not the venue the reference names. That is Crossref's
  own mangled container for the ICPR 2002 volume; the title, the three authors and the year match
  the reference exactly. Right work, ugly metadata.
* **Congalton b17** — reference says 1999, Crossref says 1998, inside the ±1 arm. The DOI
  `10.1201/9781420048568` is the first edition, which is the edition the reference cites; the 2009
  second edition has a different DOI. Right work, and the ±1 arm is doing what §15.15 grants it.

The class this rule structurally cannot catch — a same-title sibling at the same venue within ±1
year — did not occur in these 20. That is a measurement about this corpus, not a guarantee.

## 3. The five "lost" resolutions are genuinely unconfirmable

§8.2 says the rule refuses five correct resolutions because Crossref's record is thin. The
suspicion worth testing is that one or more is a **parser** problem dressed up as a registry
problem. I read the raw cached `/works/{doi}` bodies for all six rows §4 had flagged. It is not.

* **`crossref_title_ratio` × 3.** The obvious hypothesis is that Crossref stores the subtitle in a
  separate field and the parser drops it. **It does not drop it**: `admit/registry.py:39-40` reads
  `subtitle` and builds a `"title: subtitle"` form into `titles`, and `confirm_s2_candidate` takes
  the **max** ratio over that list. Measured in the bodies: `10.14358/pers.69.3.289`,
  `10.1093/oxfordjournals.aje.a120609` and `…a120610` each carry `"subtitle": []` and
  `"original-title": []`. There is no second title anywhere in the record. Crossref's stored title
  really is short. **Not a rule bug; not a parser bug.**
* **`crossref_no_author` × 2.** The second hypothesis is that the authors are filed under `editor`
  for these two (one is a CRC book chapter, exactly where that happens). Measured:
  `10.1109/tsmc.1978.4309889` and `10.1201/b12612-12` both carry `"author": null` **and**
  `"editor": null`, with no `contributor`-shaped key of any kind. An editor fallback would recover
  neither. **Not a rule bug.**
* **Chrisman b6** stays OPEN, exactly as §8.2 says it does. The record is a *Biometrics*
  `journal-article` whose first author parses as family `"D."`, given `"F. N."`. I agree with the
  report that one letter cannot be read as either a truncated surname or a prepended reviewer, and
  I agree the honest name for the refusal is the type test. I will note for the record that *"F. N.
  D."* is the initials shape of a Biometrics book-review byline, which makes a review the more
  likely reading — but that is an inference and §8.2 is right not to count it.

**Conclusion: 5 of 5 are Crossref's record being thin, not the rule mis-firing.** §8.2's framing is
accurate and, if anything, understated — recovering them needs a better registry record, and no
threshold change reaches them.

## 4. The type tests: one hole, and it is real

I planted three cases against `confirm_s2_candidate` with a stubbed Crossref record.

| plant | outcome | verdict |
|---|---|---|
| a genuine **book chapter** cited as a chapter, Crossref `book-chapter`, same author and year | **`confirmed`** | **Correct.** `reference_is_book` only refuses a `journal-article`, so a chapter cited as a chapter is untouched. This was the obvious over-reach and the rule does not have it |
| a **review whose reviewer's surname equals the book's first author**, reference carries a publisher and no journal | `refused` — **`type_mismatch`** | Caught, but by the type test, not the review detector. Right outcome, weaker name |
| the same review, reference with **no publisher and no journal parsed** | **`confirmed`** | **THE HOLE.** The review resolves as the book |

**The mechanism.** `review_signature` fires only when the record's first author is *not* the
reference's first author (`not family_matches(fams[0], want)`). A review written by someone who
shares the surname of the book's author — or, far more commonly, a Crossref record that repeats the
first author at the head of the list — is invisible to it. The only remaining net is
`reference_is_book`, which needs a parsed publisher with no journal, or an edition cue in the raw
string. **Measured on this corpus: 61 of the 658 P6 references (9.3 %) have neither a parsed
journal nor a publisher**, so for roughly one reference in eleven the type test is blind and the
review detector is the only guard — the one this plant walks past.

A fourth plant, a **two-letter reviewer surname** ("Li" ahead of "Wang"), is refused as
`crossref_author_mismatch`: the detector's `len(fams[0]) >= 3` floor, written for the one-letter
Fleiss case, also excludes every genuine two-letter surname. Right outcome, wrong name — and the
§8 table's promise that each refusal "keeps its own name" does not hold for that shape.

**This is a fix, not a blocker.** The class §8 set out to close — a JSTOR review whose author list
is *reviewer, then the book's authors* — is closed for the three measured cases and for every
different-surname reviewer. What is open is the same-surname variant, and it should be named in §8
the way the arXiv hole is named, rather than left to be discovered.

## 5. The `10.48550` passthrough claim is false at gate 0

§8 says of the arXiv-DOI passthrough: *"It is marked `archive_ok=False` and never fetched."*
Measured, with a stub S2 stage returning `10.48550/arXiv.1706.03762`:

* **Stage 6** (`extract.references.resolve_by_search`) → `resolved`, `archive_ok=False`. **True.**
* **Gate 0** (`admit.resolver.resolve_doi`) → returns `('10.48550/arXiv.1706.03762',
  'semanticscholar', 'via=semanticscholar; ratio=1.00; year=2017')`. There is no `archive_ok` on
  that return at all, and its **only** caller — `acquire/annas.py:1113-1127` — assigns
  `doi, meta = rdoi, …` and hands it straight to `fetch_one`. **No arXiv filter anywhere on that
  path.**

The offending line (`resolver.py`, `if source == "arxiv" or not normalize_doi(...)`) is
**pre-existing and unchanged in this range** — an arXiv DOI passes `normalize_doi` truthy, so it
was always returned. This is therefore not a regression. But §8 makes a **new** claim about that
path, in the section that exists precisely because gate 0 hands DOIs to a fetcher, and the claim is
wrong. Either correct the sentence to "stage 6 marks it `archive_ok=False`; gate 0 has no such
flag and would fetch it", or add the filter. The referee's preference is the filter, since §8's own
argument for the exposure being acceptable rests on the DOI never being fetched.

**One smaller honesty gap, same family.** `resolve_by_search`'s `edition_mismatch` return carries
only the edition's reason and drops any sibling candidates' refusals, under a comment reading
"Every refusal is carried, never silently dropped." Unreachable today — `/paper/search/match`
returns one candidate — and the code says so two lines above. Worth a word, not a change.

## 6. The batch client: my own kills

Four mutants of my own, distinct from the P7 rows, each applied to `s2.py`, tests run, file
restored and the restore checked by sha256. Tree verified clean afterwards.

| mutant | what it breaks | result |
|---|---|---|
| **R1** walk the response the harvested repo's way — drop the nulls, then `enumerate` | a null **mid-batch** shifts every later record onto the wrong id | **FIRED** — `test_a_missing_id_in_a_batch_marks_that_id_and_shifts_nothing` |
| **R3** `if False:` over the `Retry-After` assignment | the server's stated wait is discarded for the ladder's | **FIRED** — `test_a_retry_after_header_is_honoured_instead_of_the_ladder` |
| **R4** `uniq[start:start + BATCH_MAX + 1]` | a 501st id rides along in a 500-id call | **FIRED** — `test_more_than_the_maximum_is_chunked` |
| **R2** bump `CACHE_SCHEMA` `"s2-1"` → `"s2-2"` | — | **survived, and should have** |

**R2 is not a gap.** Bumping the constant moves the write and the read together, so a hit inside one
process is the correct outcome of a bump. The property that matters — *an entry written under an
older schema is never served to a newer parser* — is tested by monkeypatching the constant **between**
the write and the read (`test_the_cache_does_not_serve_an_entry_written_under_an_older_schema`,
which asserts `cache_hits == 0` and both versions on disk), and P7-G3 kills it. I record R2 because
a referee should say which of his own kills failed to land and why, not only the ones that did.

**One observation on "honoured".** `delay = ra` is followed by `delay *= (1.0 + JITTER *
jitter())`, so a `Retry-After: 60` waits up to 75 s. That is a floor, not the header value, and
`RETRY_AFTER_CAP` is checked before the jitter is applied. Defensible — jittering a header every
client received simultaneously is the point — but "honoured" should read "honoured as a floor,
jittered". It has never fired in the wild anyway (`retry_after_seen: 0` over 23 rate-limit answers).

## 7. The round-1 fixes hold

**Mention counts.** On `Foody_2010_assessing-accuracy-land-cover-change.tei.xml`, counted
independently with a regex over `<ref … type="bibr">` in the raw TEI rather than through the
module: **213 elements, 12 untargeted**, against `mention_totals`'s
`{box_rows: 256, elements: 213, without_target: 12, verifiable: 201}` — identical, and identical
**per target** for every one of the 90-odd targets. 37 references had an inflated box-row count.
I then read the source text around all **10** `b46` markers ("Hui & Zhou, 1998"): ten distinct
in-text citations, and the one that carries two boxes is a single marker wrapped across a line, with
two `coords` pairs. The element is the right unit for "cited n times"; the fix is correct.

**The title-less DOI branch.** Planted a record (Boone, 2010) against references claiming 2010,
2011, 2009 and 2013:

    2010 (exact) -> resolved    via=doi; basis=author+year (no parsed title)
    2011 (+1)    -> unresolved  doi_unverifiable (… exact match required with no title, 15.15)
    2009 (-1)    -> unresolved  doi_unverifiable (…)
    2013 (+3)    -> unresolved  doi_unverifiable (…)

and, as a control, the same record **with** the title present at +1 still resolves. The ±1 arm is
granted by the title match and withheld without it, which is what decisions.yaml §15.15 says. The
design's claim that the branch is unexercised on this corpus also checks out: **77 of 658
references carry a DOI and 0 of those lack a parsed title.**

## 8. Licence

**No code was copied.** A line-level similarity scan of all 367 lines of `s2.py` against all 1,025
of `spideryzarc/smart-semantic-scholar-mcp`'s `src/smart_semantic_scholar_mcp/server.py` (comments
and blanks stripped, SequenceMatcher ≥ 0.65) finds **zero runs of two consecutive similar lines**,
therefore no block of three. The 17 isolated single-line matches are unavoidable API shape or
Python idiom: the `graph/v1` base URL, `.get("externalIds") or {}`, `data.get("data") or []`,
`for … in range(0, len(x), 500)`, `for attempt in range(… + 1)`. No shared function body, no shared
comment text, no shared constant name. The two are structurally unalike — async httpx + FastMCP +
sqlite there, sync urllib + injected client and cache + a class here.

**The licence facts check out as the report states them.** The clone's root is `.gitignore`,
`README.md`, `pyproject.toml`, `requirements.txt`, `src/`, `tests/` — **no LICENSE, LICENCE or
COPYING**, and no `license` field in `pyproject.toml`. The README carries an MIT badge
(`README.md:5`) and, at `README.md:230-231`, "licensed under the [MIT License](LICENSE)" — a link
to a file the repository does not ship. §2's wording is exact.

**Every harvested claim is real, and every "OURS" claim is real.** `server.py:429`
`for i in range(0, len(missing_ids), 500)`; `:988` `if paper and "paperId" in paper`; `:92`
`await asyncio.sleep(5 * (2 ** attempt))` under `max_retries = 3` at `:83`; `:50`
`AsyncLimiter(1, 4)` on the unauthenticated branch; `:218` the comment "Semantic Scholar bulk
endpoint is limited to 500 IDs at a time", which is what `s2.py:63-65` attributes to it. On the
other side, `server.py` contains **no** jitter, **no** `Retry-After` handling, **no** version in its
cache key (`:99`/`:111` key on a bare `paperId`), and **no** length check on the batch response —
`:986` enumerates it and indexes `chunk_keys[idx]`, which is exactly the misalignment my R1 mutant
reproduces and `s2.py:292-296` kills. Attribution is accurate in both directions.

## 9. Harness rows, the ladder, and secrets

**Six harness rows re-applied by me**, in my own words for what each is supposed to prove:

| row | what I expected to break | result |
|---|---|---|
| P7-G1 | a short batch response is zipped anyway and later records attach to the wrong id | FIRED |
| P7-G4 | an emptied ladder ends a 429 with no wait and no retry | FIRED |
| P7-G6 | a DOI-bearing reference takes a batch slot for an answer nothing reads | FIRED (4 tests) |
| P7-C1 | stage 6 resolves on S2's own record, so the three reviews come back as the books | FIRED |
| P7-C2 | gate 0 does the same and hands the fetcher the review's DOI | FIRED (2 tests, both in the annas suite) |
| P7-C3 | the review detector alone removed — cases still refused, so only the reason-by-name assertions catch it | FIRED (4 tests) |

**6 of 6 fired**, baselines green before and after, every file restored and the restore checked by
sha256. C3 is the interesting one and the builder is right about why: a kill whose class is
invisible in the outcome has to be asserted on the reason string.

**The ladder.** `PYTHONUTF8=1 py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w8`, run
by me on the clean tree: secrets PASS, ruff PASS, compile PASS, **1 failed, 2,546 passed, 19
skipped, 1 xfailed in 572 s**, litkb Postgres tests 215 passed. The one failure is
`test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, the pre-existing one this task
allows. §8.5's numbers reproduce exactly.

**Secrets.** `git log -p 9addcee..e11068d` scanned for keys, tokens, bearer headers, credentials,
connection strings and `.env` content: **five matches, all prose, all false positives** — the word
"token" in the mutation-testing description and the word "secrets" in the name of the gate rung. No
credential file is added in the range and none is tracked in the worktree. The S2 leg is
deliberately unauthenticated, so there is no key for it to leak. `netutil.redact` is applied at the
one new site that can embed response bytes in an error (`s2.py:253`); every other error string in
`s2.py` is built from status codes and list lengths.

## 10. The fixes, in the order I would take them

1. **Correct the `10.48550` claim in §8**, or add the arXiv filter at gate 0. As written the report
   asserts a safety property the acquisition path does not have (§5).
2. **Name the same-surname reviewer hole in §8**, next to the arXiv hole, with the 9.3 % figure for
   how often the type test is blind — and consider whether the review detector should also fire on
   an author list that is the reference's list *prefixed by a repeat of its own first author* (§4).
3. **Fix the two prose slips**: Goodchild b1 is "2010 vs **2002**" (§1); "`Retry-After` honoured"
   is honoured-as-a-floor-then-jittered (§6).
4. **Say that the `confirmed` arm is not a zero-wire run** — 46 arXiv requests — and that reason
   strings carry a run-dependent `skipped=arxiv` tail, so a CSV diff is not row-stable (§1).
5. Optional: give the two-letter surname its own name rather than `crossref_author_mismatch`, and
   carry the dropped refusals on the `edition_mismatch` return (§4, §5).

None of these changes a measured number. **P6 merges once 1–3 are written down.**

---

## 11. Closed (builder, 2026-09-15, after this review)

All five taken, 1 and 2 as CODE rather than as prose, which is what §10.1 said the referee preferred.

1. **The `10.48550` passthrough.** `resolve_doi` now returns **no DOI** for that form whichever stage
   proposed it — the identifier travels in the evidence as `arxiv_record_only=…; archive_ok=False` —
   and `annas.fetch_one` refuses the form before any request is made. Two mutation rows because one
   test through `run_jobs` would let either half mask the other: **P7-C5** (gate 0) and **P7-C6**
   (the fetcher), both FIRED, each on its own test.
2. **The same-surname reviewer hole.** `review_signature` no longer asks whether the reviewer's
   surname differs from the reference's first author. The load-bearing signal is now the
   author-count SHAPE — the record's list exactly one longer than the reference's own, containing it
   as a suffix — plus Crossref's own `type`/`subtype` (`registry.parse_crossref` now carries
   `raw_subtype`). For the 9.3 % type-blind class — neither journal nor publisher parsed — a second,
   broader net refuses under its own name, `review_suspected`, so the reason histogram still says
   which test spoke. **The two kills:** the planted same-surname review is refused
   `review_record (… exactly one extra name …)`; a same-surname GENUINE article by the same authors
   is still `confirmed`. **P7-C4** removes the name-independent half and FIRES. The Fleiss parse
   artefact (`['d', 'fleiss']`) is held off by a two-letter floor on the extra name: it is still NOT
   called a review, which is what §4 required — it refuses as `type_mismatch`, the name that asserts
   only what was measured. The same floor gives the referee's two-letter "Li" reviewer the review
   name it should have had (§10.5, first half).
3. **Both prose slips fixed** in `LITKB_S2_BATCHING_2026-09-15.md`: Goodchild b1 reads "2010 vs
   2002"; the `Retry-After` honour is stated as a floor, then jittered, with the 60→60–75 s worked
   example.
4. **The non-zero-wire fact is written into §8.1**, with the 46 arXiv requests and 5 429s. The
   run-dependent `skipped=` tail is now **removed from the persisted reason** rather than merely
   disclaimed: it moved to `Resolution.transient`, which `asdict()` excludes and the instrument
   prints. A reason-column diff of the artefact is row-stable again; `best=` can still move when the
   arXiv stage's breaker differs between runs, which is a property of the wire and is said so.
5. The dropped `edition_mismatch` sibling refusals are **not** carried — still unreachable, still
   commented two lines above, and a change there could not be tested against anything real.

Two shapes the round-2 fix could have broken and does not, each asserted as its own control test:
a genuine article whose authors share the reviewer's surname is still `confirmed`; and a paper by
**two authors of the same surname** — Crossref `['wang', 'wang']`, the reference's first author at
position 1, which is exactly the shape the broad net looks for — is still `confirmed`, because that
net counts PEOPLE (there must be an extra one for there to be a reviewer) rather than comparing
names. That control matters most at gate 0, whose reference dict is `{title, first_author, year}` and
therefore always type-blind; the code now says so where the net is defined.

**The table after, re-run from cache:** 293 references, **20 resolved / 23 ambiguous / 250
unresolved** — unchanged. The **13 moved rows were read individually**, not inferred from the
summary histogram (which truncates at 12 names and would hide a small bucket): they are the same 13
references under the same reason names as §8.1 — 3 `review_record` (Alwan b13, Burnicki b23,
Hall b10), 1 `type_mismatch` (Chrisman b6), 4 `edition_mismatch` (Efron b0, Foody b58, Foody b76,
Goodchild b1 — whose reason string reads **2010 vs reference 2002**, the year §1 caught the prose
getting wrong), 3 `crossref_title_ratio` (Foody b14 0.72, Foody b38 0.70, Burnicki b43 0.56) and
2 `crossref_no_author` (Abercrombie b16, Burnicki b12). Counted over all 293 persisted rows:
`review_suspected` appears **0 times** — the new net adds no refusal on this corpus; it closes a hole
this corpus did not happen to contain — and `skipped=` appears **0 times**, which is fix 4 measured
rather than asserted. 0 Semantic Scholar and 0 Crossref wire requests, 211 S2 cache hits, and **1**
arXiv request rather than 46: the referee's own run warmed that cache, which is precisely the
run-dependence §1 named.

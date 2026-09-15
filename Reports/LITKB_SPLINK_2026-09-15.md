# litkb — Splink as a candidate-SCORING layer, evaluated against frozen gold

**Branch** `work/20260915-splink` · worktree `D:\edmonds-pipeline\treedata-splink` · **Date** 2026-09-15
**Asked by** Kam. **Author** Claude (builder). **Not refereed.**

| | |
|---|---|
| Candidate | [Splink 4.0.17](https://github.com/moj-analytical-services/splink) — MIT, DuckDB backend, Fellegi–Sunter with EM |
| Venv | `D:\edmonds-pipeline\venv-splink` · `Scripts/requirements-litkb-link.txt` (**not** a pipeline dependency; nothing under `Scripts/pipeline` imports splink) |
| Gold builder | `Scripts/qc/instruments/litkb_splink_gold.py` |
| **Frozen gold** | `Reports/litkb_splink_gold_2026-09-15.json` · **sha256 `d6dbbac3e0e8fc473e431568cfb77ebdfaff0c687647e69e3ef2274d974846a0`** · committed at `c9bbd6c`, **before** the first Splink run |
| Evaluator | `Scripts/qc/instruments/litkb_splink_eval.py` |
| Measured tables | `Reports/litkb_splink_2026-09-15.json`, `Reports/litkb_splink_vs_resolver_2026-09-15.csv` (658 rows) |
| Trained model | `Reports/litkb_splink_model_2026-09-15.json` |
| Tests | `Scripts/qc/test_litkb_splink.py` (23; no DB, no network) |

**Splink would PROPOSE. The registry still CONFIRMS.** Nothing here changes
`resolver.confirm_s2_candidate`, and the recommendation below is explicit that it must not.
"S2 proposes, Crossref confirms" stands; this is a question about what sits *in front* of it.

**Nothing in this evaluation opened a database or a socket.** The right-hand candidate pool is
read directly out of the already-cached registry bodies under `litkb_derived/registry/`, as
files, rather than through `admit.registry` — so there is no code path here that *could* reach
the wire. `litkb_test_w9` was opened read-only once, and it is an empty mutation-harness scratch
database with no `works` table; the 348 works come from the tracked exports instead (below).

---

## 1. Three numbers in the brief do not survive contact with the files

Stated plainly, because the gold is built from the measured files and not from the brief.

| brief said | files say | where |
|---|---|---|
| 385 confirmed resolutions | **365** | `litkb_derived/p6/references.jsonl`, `resolution == "resolved"`. `LITKB_REFERENCES_2026-09-15.md` §2 also says 365 / 55.5 % |
| 40 near-miss mutations | **90 mutations, of which 70 are true kills** | `litkb_derived/p6/kills.json`. The other 20 are `title-word` mutations that are deliberately still the same paper — they are near-**positives**, and the gold carries them as such |
| the edition case (one) | **four** | `LITKB_S2_BATCHING_2026-09-15.md` §8: Foody b58, Efron b0, Foody b76, Goodchild b1 |
| 348 works, from `litkb_test_w9` | **348 works, reproduced exactly** — but from the tracked exports | distinct `litkb_key` over `litkb_state == admitted` in `treedata-litkb/Reports/litkb_export/{literature_tracker,manifest}.csv`: 346 ∪ 169 = **348** |

The 3 book-review cases and the 5 "lost genuine" rows are as the brief describes them, and each
gold row carries the report line that names it.

---

## 2. What was built, and the one thing it had to get right

Left = 658 P6 references + 90 mutated copies = **748 rows**.
Right = **2,032 rows**: 1,684 distinct Crossref works harvested from the cached bodies, plus the
348 admitted corpus works. Fields on both sides: normalised title, a two-token title blocking
key, first-author family, year, journal/publisher, volume, first page, DOI.

Blocking: `title_key` OR `year`. Comparisons: title (Jaro-Winkler 0.97/0.92/0.85), first author
(JW 0.99/0.90, TF-adjusted), year (exact / ±1 / ±3), journal (JW 0.95/0.85), volume (exact),
pages (exact). `u` by random sampling (2 M pairs, seed 1729); `m` by EM on `title_key` and on
`year` in turn. **26,278 pairs scored.**

### The prior is the thing that had to be got right

λ — "two random records match" — is estimated from **exact normalised title**, not from DOI.
DOI is the obvious deterministic rule and it is the wrong one here twice over: 88 % of the P6
references carry no DOI at all, and in the 348-work dedupe every work has a *distinct* DOI by
construction, so the rule matches zero pairs and λ collapses to its floor. **The first run of
this script did exactly that**, and reported 303/60 at match weight **−996.6**, probability
`1e-300` — a number that is not a judgement about the pair at all. With exact title as the rule,
λ = **8.25 × 10⁻⁴** and the same pair scores **+6.67**. Ranking is invariant to λ; every
probability, and therefore every threshold, is not. That failure is recorded in the code comment
that fixes it and in `task_b.in_place_em_degenerate`, not quietly replaced.

Splink prints a warning on this rule — it expected 60 % recall and observed less. That is
expected and not ignored: exact normalised title recovers only a fraction of true links (GROBID
truncates titles, Crossref stores subtitles separately), which is precisely why it is used to
*estimate* λ rather than to find links. A referee will see the warning in the run output; this is
what it is.

### Trained match weights (log₂ Bayes factor per level)

| comparison | level | match weight |
|---|---|--:|
| title | exact | **+10.34** |
| title | JW ≥ 0.97 | +10.26 |
| title | JW ≥ 0.92 | +9.84 |
| title | JW ≥ 0.85 | +6.52 |
| title | else | −2.22 |
| first_author | exact | **+8.80** |
| first_author | JW ≥ 0.90 | +5.14 |
| first_author | else | −1.93 |
| year | exact | +4.83 |
| year | ±1 | +0.34 |
| year | ±3 | +0.42 |
| year | else | −1.39 |
| journal | exact | **+7.16** |
| journal | JW ≥ 0.95 | +6.46 |
| journal | JW ≥ 0.85 | +4.41 |
| journal | else | −1.42 |
| volume | exact | +6.40 |
| volume | else | −3.42 |
| pages | exact | +7.46 |
| pages | else | −0.31 |

Read the year row: **±1 (+0.34) and ±3 (+0.42) are worth almost nothing, and are not ordered.**
On this corpus a year that is close but wrong is barely better evidence than a year that is far
and wrong — because the discriminating work is already done by title, author and journal. That
matters for §4: it is why a year+3 mutation does not cost a mutant enough to fail.

---

## 3. Task A — reference → work linking

Scored on the 365 gold positives. **2 of the 365 gold DOIs are not on the right side at all**
(no cached Crossref body carries them), so they are unevaluable and counted separately rather
than as failures; the scored population is **363**.

| | n | of 363 |
|---|--:|--:|
| gold DOI ranked **first** | **362** | **99.7 %** |
| gold DOI in the top 3 | 363 | 100 % |
| gold DOI retrieved but not ranked first | 1 | 0.3 % |
| present on the right but **not retrieved at all** | **0** | 0 % |
| gold DOI absent from the right side (unevaluable) | 2 | — |

Match weight of the gold pair: median **+25.2**, mean +23.6, min +0.27, max +31.2.

The two unevaluable rows are genuinely unevaluable and not an artefact: no cached body anywhere
carries `10.2307/177409` or `10.1016/j.landurbplan.2004.03.009` (both Guo 2018).

**A scoring bug was found and fixed here, and it moved this number.** The gold hit was originally
matched by the `cr::` unique-id prefix. 31 DOIs are carried by *both* a cached Crossref record and
a corpus work row; the two records are near-identical, so they tie on match weight, and the tie
broke on unique_id — where `work::` sorts above `cr::`. Two gold hits sitting on the corpus row
were therefore scored as rank-2 misses for no reason but sort order. Matching by DOI instead:
360 → **362**. The same prefix assumption was deflating the resolver-agreement count below by the
same two rows.

### Against the current resolver, on the same 658 rows

`Reports/litkb_splink_vs_resolver_2026-09-15.csv`. This is the comparison that decides whether a
ranking layer is worth anything — re-ranking rows the resolver already got right is worth
nothing.

| resolver state | n | Splink has a candidate | p ≥ 0.5 | p ≥ 0.9 | agrees with the resolver's DOI |
|---|--:|--:|--:|--:|--:|
| `resolved` | 365 | 365 | 365 | 364 | **362** |
| `unresolved` | 274 | 269 | **88** | **75** | 0 |
| `ambiguous` | 19 | 19 | 19 | 19 | 0 |

**Splink agrees with the resolver on 362 of 365** — it is not proposing a different answer on the
rows that already work — **and puts a candidate at p ≥ 0.5 on 88 of the 274 it left unresolved**
(75 at p ≥ 0.9).

### How many of the 88 are actually new?

This matters, and the headline "88" overstates it. `resolver_reason` records the DOI the resolver
itself examined (`best=crossref:0.xx:DOI`), so the two can be compared row by row:

| | n |
|---|--:|
| Splink's top candidate is the **same DOI the resolver already examined and refused by name** | **33** |
| the resolver's reason names no candidate DOI at all (`no_title_or_author` and friends) | 17 |
| Splink's top candidate is a **different DOI** from the one the resolver looked at | **38** |

So the layer contributes two different things, and they should not be added together. For 33 rows
it adds a *calibrated weight* to a candidate the resolver had already found and rejected — useful
for triage, but nothing new to look at. For 55 rows (38 + 17) it surfaces a candidate the resolver
either never reached or never named. Only that second group is genuinely new material, and
`candidates.jsonl` already holds 645 candidate rows from the P6 run, so even some of the 55 may
already be written. **The honest figure for the layer's reach is "55 rows get a candidate the
resolver's own reason does not name", not 88.**

---

## 4. Must-not-link — and this is where it fails

Threshold: match probability ≥ 0.5.

| gold set | n | scored as a match | weights |
|---|--:|--:|---|
| **book reviews** | 3 | **0** ✅ | −2.92, −2.92, −2.92 (p = 0.117) |
| **sibling editions** | 4 | **3** ❌ | −4.64, +6.05, +6.47, **+15.02** |
| **near-miss mutations** (true kills) | 70 | **65** ❌ | median +14.55, max +27.11 |

**Splink is not a gate, and the mutations prove it quantitatively.** 65 of 70 references that
the P6 rules correctly refused — year moved by 3, a title word swapped, a DOI digit changed —
score as confident matches, at a median weight of +14.55. The mechanism is in the weight table:
a year±3 level worth +0.42 cannot overcome a title level worth +10 and an author level worth
+8.8. Fellegi–Sunter is estimating *how similar two records are*; the P6 rules are testing
*whether a registry record is the same publication*, which is a different question and one that
needs the record's `type`, its author-list ordering and its container — none of which is a
similarity.

The three book reviews are the one thing it does refuse — and §5 shows why, and it is not the
reason the brief assumed.

---

## 5. Task C — separating the 5 "lost genuine" from the 3 reviews

**This is the practical value, and it is clean.**

| | n | min weight | median | max | at p ≥ 0.5 |
|---|--:|--:|--:|--:|--:|
| **lost genuine** (thin Crossref records) | 5 | **+3.00** | +24.02 | +24.84 | 5 of 5 |
| **book reviews** | 3 | −2.92 | −2.92 | **−2.92** | 0 of 3 |

All five lost-genuine gold DOIs rank **first** for their reference (p = 0.889, 0.99997, 1.0, 1.0,
1.0). The separation is complete: the lowest lost-genuine weight (+3.00) is above the highest
review weight (−2.92), with a gap of about 6 match-weight units and no overlap.

This is exactly the distinction the current rule cannot draw. The resolver refuses both groups,
under `crossref_no_author` / `crossref_title_ratio` for the five and `review_record` for the
three, and the referee established that no threshold change reaches the five
(`LITKB_REFERENCES_REFEREE2_2026-09-15.md` §3: "5 of 5 are Crossref's record being thin").
A probabilistic score does reach them, because a missing author is a *null level* — it costs
nothing — whereas a **contradicted** author costs −1.93 and a contradicted journal −1.42.
A thin record is uninformative; a review's record is informative and says "different work".

Caveat, stated: n = 5 against n = 3. The separation is complete on every case that exists, and
the mechanism explains it, but eight cases is not a calibration.

---

## 6. Kills

### Kill 1 — drop the first-author comparison; the reviews must become matches. **DID NOT FIRE as stated.**

| model | reviews at p ≥ 0.5 | review weight | p |
|---|--:|--:|--:|
| full | 0 of 3 | −2.92 | 0.117 |
| **no first author** | **0 of 3** | −1.03 | 0.328 |
| no journal | 0 of 3 | −2.56 | 0.145 |
| **no author AND no journal** | **3 of 3** ✅ | +0.23 | 0.539 |

The brief's premise — that the first-author comparison carries the weight on the review cases —
is **false**, and the measurement says what carries it instead. Removing the author moves a
review from p = 0.117 to p = 0.328: real, and not enough. Removing both moves it to p = 0.539
and all three flip to matches.

**The mechanism.** A journal's review of a book carries the book's *exact title*, so the title
comparison is at its top level and contributes +10.3 in favour of the link. Two features
contradict it, and they contradict it independently: the author (reference `wadsworth`, record
`sylwester`; `getis`/`semple`; `serra`/`diggle`) and the **container** — the reference parses a
publisher, `john wiley`, `cambridge university press`, `academic press`, where Crossref has a
journal, `technometrics`, `geographical review`, `biometrics`. Each is worth about −1.5 to −1.9
and neither alone is enough; together they are. That second signal is the same book-vs-journal
contradiction the resolver names `type_mismatch` / `reference_is_book` — Splink is picking it up
as a string mismatch rather than as a type test, which is why it is weak rather than decisive.

The ablation that does fire is recorded as `FIRED_on_both`. The feature dependence is shown; the
brief named the wrong single feature.

### Kill 2 — remove blocking on a small sample; recall must not change. **FIRED.** ✅

60 gold-positive references against 659 right-hand records. Blocked (`title_key` OR `year`):
**60 of 60** gold DOIs retrieved. Cartesian (`1=1`): **60 of 60**. Identical. The blocking rules
are not costing recall on this sample.

---

## 7. Task B — duplicate works over the 348

**The model is transferred from Task A, and that is a finding, not a convenience.** Trained in
place on the 348 works, EM has nothing to learn from: the corpus was already deduplicated at
admission, so it contains approximately zero true duplicate pairs, λ came back **0.0**, and the
m-probabilities were nonsensical — year *exact* m = 0.0 while year ±3 m = 1.0. Recorded under
`task_b.in_place_em_degenerate`. **Splink cannot be trained for duplicate detection on this
corpus**; it can only be applied to it.

With the Task A model applied: **9 pairs above p = 0.5; 341 clusters at 0.95, of which 6 are
multi-member, largest 3.** All 9 are examined below, and all 9 are wrong.

Each pair's status is **measured**, not read off the key names: the two DOIs are pulled from the
tracked exports and compared under the P3 rule as written (same DOI → one work; different DOIs →
two works).

| weight | p | pair | DOIs | what it is |
|--:|--:|---|---|---|
| **+14.25** | 0.9999 | `Leung_2004` / `Leung_2004a` | `…s10109-004-0142-3` / `…-0144-1` | **NOT a duplicate** — "A general framework for error analysis in measurement-based GIS" **Part 2** and **Part 4** |
| **+6.67** | 0.990 | `Valavi_2018_block-cv-r-package` / `…_blockcv-r-package-generating` | `10.1111/2041-210x.13107` / `10.1101/357798` | **303/60** — preprint and journal version |
| +6.51 | 0.989 | `Radoux_2020_about-pitfall…` / `Radoux_2020_how-response-designs…` | `…rs12244128` / `…rs12020257` | different papers |
| +6.34 | 0.988 | `Goodchild_2004` / `Leung_2004a` | `…-0140-5` / `…-0144-1` | Part 1 and Part 4 of the same series — **different papers** |
| +6.34 | 0.988 | `Goodchild_2004` / `Leung_2004` | `…-0140-5` / `…-0142-3` | Part 1 and Part 2 — **different papers** |
| +6.34 | 0.988 | `Khoee_2024_domain-generalization…` / `Rafi_2024_domain-generalization…` | `…-10922-z` / `…-10817-z` | different papers |
| +5.58 | 0.980 | `Platanios_2014` / `Platanios_2016` | UAI 2014 / ICML 2016 | different papers, same series |
| +5.19 | 0.973 | `Li_2025_adapting-cross-sensor…` / `Li_2025_post-processing-optimization…` | `…rs17050927` / `…rs17091558` | different papers |
| +1.52 | 0.741 | `Lu_1999_control-charts…` / `Lu_2001_cusum-charts…` | `…1999.11979925` / `…2001.11980082` | different papers |

**Every one of the 9 pairs above p = 0.5 is a false positive. Splink found zero true duplicates
in the 348, at any threshold.** Which is the correct outcome, because there are none to find —
the corpus was deduplicated at admission.

The top pair is the instructive one. `Leung_2004` / `Leung_2004a` scores +14.25, more than twice
any other pair, and it is **not** a duplicate: the `a` suffix is the tracker's
*same-year-different-paper* convention (the same convention whose `2019a` cell broke the P3 load),
and the two rows are Parts 2 and 4 of one multi-part series with distinct DOIs. A multi-part
series is the worst case for a similarity model: the titles differ only in a part number, which is
a handful of characters of a long string, so Jaro-Winkler puts them at its top level while the
author, year and journal all agree exactly. Nothing in the feature set can see a part number.

### Is 303/60 given a distinguishable weight? **No.**

It scores +6.67, inside a band from +6.67 down to +5.19 that holds six other pairs, **all of them
simply different papers by the same authors on the same topic in the same year**. Any threshold
that catches 303/60 also catches Khoee/Rafi, both Li 2025 papers and two parts of the Leung series
— and still ranks a non-duplicate above it.

That is the expected answer and not a defect in Splink. The tracker's "same paper" judgement for
303/60 is about *content identity across versions*, and the P3 referee's ruling is that under the
rules as written they are two works with two DOIs and no `version-of` relation to express it
(`LITKB_P3_REPORT_2026-09-15.md`). Nothing in a title/author/year/journal similarity can
represent "these are versions of one another" as distinct from "these are neighbours" — the
fields are almost identical in both cases. It needs a version relation, not a better score.

Of the 4 gold duplicate pairs, only 303/60 is scorable at all: pair 50→3 has no `litkb_key` on
the left (state `new`, never admitted), and pairs 199→94 and 264→13 resolve to the **same**
`litkb_key` on both sides — the deduplication already happened, so they are one work in the 348
and not a pair. Stated because "3 of 4 gold pairs were unscorable" is the kind of thing a
headline ratio would hide.

---

## 8. Recommendation

**Adopt as a RANKING layer, proposing only, and only for the rows the registry rule refuses.
Do not adopt it as a gate. Do not adopt it for duplicates.**

The numbers behind each clause:

1. **Ranking works.** 362 of 363 gold DOIs first, 363 of 363 in the top 3, zero present-but-not-
   retrieved (§3). It agrees with the resolver on 362 of 365 — so it is not proposing a different
   answer on the rows that already work.
2. **It adds some reach where the rule has none.** 55 of the 274 unresolved get a candidate the
   resolver's own reason does not name (§3 — not the 88 headline), and the 5 lost-genuine separate
   completely from the 3 reviews (§5), which is the one class the referee established no threshold
   change can reach.
3. **It is not a gate, and the margin is not close.** 65 of 70 known-bad mutations and 3 of 4
   sibling editions score as confident matches (§4). Anything that promoted a Splink score to a
   resolution would re-open every class P6 closed.
4. **Duplicates: no, and not marginally.** Not trainable on the corpus (λ = 0.0, §7), and **all 9
   pairs it scores above 0.5 are false positives** — the highest-scoring pair of all, at +14.25,
   is Parts 2 and 4 of one series (§7). 303/60 sits mid-band among six pairs of different papers.

### Integration point, specified, not implemented

In `pipeline/litkb/admit/resolver.py`, inside **`resolve_by_search`**, at the point where the
search has returned its candidate list and **before** `confirm_s2_candidate` is called:

* Score the reference against the candidate list with the saved model
  (`Reports/litkb_splink_model_2026-09-15.json`) and **reorder the list by match weight**,
  carrying the weight onto each candidate.
* `confirm_s2_candidate` is called exactly as it is today, on the reordered list. Its verdict and
  its refusal names are unchanged; the reason string gains `splink_rank=` and `splink_mw=` so the
  histogram can show what the ranking did.
* When every candidate is refused, write the top-ranked one to the **`candidates`** table with
  its weight, state unchanged — **deduped against what is already there**, since 33 of the 88 are
  the DOI the resolver itself already examined and `candidates.jsonl` holds 645 rows from the P6
  run. That is the mechanism by which the 5 lost-genuine become visible to a human instead of
  vanishing into `unresolved`.
* **The resolution state is never set from a Splink score.** No threshold on `match_probability`
  may promote anything to `resolved` or `ambiguous`.

**Cost of adoption.** A new runtime dependency (splink, duckdb, sqlglot, igraph) that is
currently isolated in `venv-splink` and would have to enter `requirements-litkb.txt`, plus a
trained model file that becomes a versioned artifact needing its own retraining story as the
corpus grows. If Kam would rather not carry that for 88 proposals, **the honest alternative is to
adopt nothing and take §5 as the finding**: the reason the five lost-genuine separate from the
three reviews is that a *missing* field is uninformative while a *contradicted* field is
evidence, and that asymmetry can be written into `confirm_s2_candidate` directly, without Splink.

---

## 9. Gates

* `py -3.12 qc/check.py --fast` with **`LITKB_PGPORT=1`** — **said so, as instructed**: the port is
  set to 1 so that no test in this run can reach the live litkb server. Result:
  `secrets PASS 9.9s · ruff PASS 0.3s · compile PASS 0.9s · pytest FAIL 1593.3s` —
  **1 failed, 2,362 passed, 238 skipped**, `EXIT=1`. The single failure is
  `qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, which is the one the
  brief allows and is not touched by this work; nothing else is red.
  **What `LITKB_PGPORT=1` actually did, measured rather than assumed:** the run reports
  `litkb Postgres tests: 216 skipped <- 216 SKIPPED: litkb server/role/psycopg absent, so those
  guards were NOT tested`. They **skipped**; they did not error. Stated because it cuts both
  ways — it is the isolation the brief asked for, and it also means 216 litkb guards carry no
  evidence from this run.
  (The suite took 26 minutes rather than the usual ~80 s because three other sessions were
  running pytest on this machine concurrently; it was CPU-starved, not stuck.)
* `qc/test_litkb_splink.py` — **25 tests, all passing** under `venv-splink`. Under the main
  interpreter (which is where `check.py` runs them) 22 pass and the 3 splink-dependent
  comparison-config tests skip, because splink is deliberately not a pipeline dependency and must
  not become one by way of the test suite.
* `py -3.12 qc/instruments/litkb_splink_gold.py --check` — **GOLD MATCH**, CRLF-safe.

## 10. What this evaluation does not establish

* **The proposer scored its own proposal.** Everything above was produced by the author of the
  code. Under CLAUDE.md 3.4c the recommendation in §8 is not adoptable until an independent
  session re-runs `litkb_splink_eval.py` on the real data and reproduces §3, §5 and §6.
* Task C rests on 5 + 3 cases. Complete separation on eight cases is a mechanism plus an
  existence proof, not a calibration.
* The right-hand pool is what the P6 campaign happened to cache. A reference whose true record
  was never fetched cannot be ranked — 2 of the 365 positives are in that position, and the 274
  unresolved will contain more, so the 88 proposals of §3 are a floor, not a ceiling.
* Nothing here was run against `litkb`. No database was written, and the only database opened at
  all was `litkb_test_w9`, read-only, which turned out to be empty.

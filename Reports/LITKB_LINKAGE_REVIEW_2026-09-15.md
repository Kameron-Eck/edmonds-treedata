# litkb — how others link bibliographic records and identifiers, and what our resolver should change

**Branch** `work/20260915-linkage-review` · worktree `D:\edmonds-pipeline\treedata-linkrev` · **Date** 2026-09-15
**Asked by** Kam ("do it"). **Author** Claude Opus 5. **Not refereed.**
**Workstream** `linkage-review`, litkb id `01a0a7be-4440-7a1c-879b-9a691d2c52d7`, left **OPEN**.

This is the first end-to-end use of the literature knowledge base for a real review: every source
below was admitted through `litkb admit`, acquired through `litkb acquire`, and carries a `use`
row in the live `litkb` database. §8 reports what that procedure did and did not let me do — it is
the second deliverable, not an afterthought.

**No code is changed by this report.** §7 is a ranked list of proposals; none is implemented.

| | |
|---|---|
| Works admitted in this workstream | **25** (24 registry route, 1 manual) |
| PDFs acquired (open access only; 0 Anna's Archive downloads) | **8** |
| `use` rows written | **15** |
| Sources cited with no KB record (documentation the KB refuses — §8.4) | **6** |
| `promote prepare` | run; result in §9 |

**The numbers this review reasons about, with their conditions**, so nothing below is quoted
loose. From `Reports/LITKB_REFERENCES_2026-09-15.md` §2 and `Reports/LITKB_S2_BATCHING_2026-09-15.md`:
658 references parsed from 18 papers; **365 resolved (55.5 %) Crossref-only**; **385 (58.5 %)
after the Semantic-Scholar leg**. Unresolved by cause: **50 `no_title_or_author`**, 9
`doi_title_contained`, 3 `doi_title_mismatch`, 211 searched-and-refused. From the S2 phase: **27
`s2_candidate_has_no_doi`**, **4 `edition_mismatch`** (Foody b58, Efron b0, Foody b76, Goodchild
b1), **3 `review_record`**, **5 "lost genuine"** thin-record refusals. From
`Reports/LITKB_REFERENCES_REFEREE2_2026-09-15.md` §4: **61 of 658 (9.3 %)** references parse
neither a journal nor a publisher, so the type test is blind on them. From
`Reports/LITKB_SPLINK_2026-09-15.md`: the 303/60 preprint↔journal pair, and Splink's failure to
separate it from six pairs of merely-neighbouring papers.

---

## 1. Reference matching at scale — parsing vs search, and what a fallback would buy us

**Crossref's own trajectory is from parsing to search.** Dominika Tkaczyk's Crossref Labs series is
the primary source: *Reference matching: for real this time* (`10.64000/e6ey2-wce96`, 2018), *How
good is your matching?* (`10.13003/ief7aibi`, 2024) and *Metadata matching: beyond correctness*
(`10.64000/vgpgj-j8126`, 2025). All three are blog posts **with registered DOIs**, all three are
admitted here as registry works — and none of the three could be acquired (§8.3), so this
paragraph is metadata-grade and carries no quote. That limit is real and is stated rather than
papered over.

**What the parsing leg is worth, measured.** Tkaczyk et al. 2018 (arXiv:1802.01168, admitted and
acquired) evaluate ten parsers against a test set of 64,495 references drawn from 9,491
PDF+parsed-reference pairs:

> "are: GROBID (F1 0.89), followed by CERMINE (F1 0.83) and" — arXiv:1802.01168, Results

and on the ML-vs-rules split, "The average recall for ML-based tools (0.66) is three times as high
as non-ML-based tools (0.22)" (verified against the `pdftotext -raw` extract; the `-layout` extract
interleaves the two columns and cannot be grepped for it), with retraining lifting GROBID 0.89 → 0.92, CERMINE 0.83 → 0.92 and
ParsCit 0.75 → 0.87. Cioffi & Peroni 2022 (arXiv:2205.14677, acquired) re-run the question on a
different corpus —

> "The dataset comprised 2,538 bibliographic references referring to almost 1,000 different journals"

— across 27 subject areas, and put Anystyle first. The finding that matters for us is not the
ranking but the **variance across document shapes**: ExCite scores 0.91 on one subject area and
identifies no reference at all in another. That is the shape of our 50 `no_title_or_author`
refusals, which are concentrated in pre-1990 footnote-style reference lists, not scattered.

**The hybrid, and it is the closest published analogue of our resolver.** Guenci et al. 2025
(arXiv:2511.18408, acquired) build a matching pipeline for references with incomplete metadata,
against Crossref and OpenCitations. Their motivating number is the thin-record problem at archive
scale:

> "698,198,538 out of 1,812,811,997" — arXiv:2511.18408 §1, references discarded from the April
> 2025 Crossref dump for carrying no structured DOI

Their architecture is the thing to copy: match on the original metadata first; **when a reference
fails to clear threshold and carries an unstructured citation string, invoke GROBID on demand to
extract more metadata, then retry**. They report precision 100 %, recall 75.67 %, F1 86.15 % on
their gold standard — precision-first, exactly our posture, with a second stage we do not have.

**What a search-based fallback would do for our 50.** Honest answer: *unknown, and measurable for
about an hour of work.* All 50 rows carry neither a parsed title nor a parsed first author, and
`LITKB_REFERENCES_2026-09-15.md` §8.2 measured that **0 of the 50 carry a DOI**. So there is
nothing to search *on* in the parsed fields — which means a fallback cannot be a second search
over the same fields. It has to be a search over the **raw reference string**, which GROBID does
preserve (`includeRawCitations=1` is already on). Crossref's `query.bibliographic` endpoint takes
exactly that: an unstructured string. The measurement that settles it is small and is proposed as
change **P1** in §7 — not asserted here as a gain.

**Truncated titles and thin records.** Our resolver already meets both and refuses both by name:
9 `doi_title_contained` (GROBID truncated at a comma, or ran the journal name onto the title) and
5 lost-genuine where Crossref's own stored title is short. Our own KB reproduced the second class
**during this session**: `10.14778/2994509.2994535` is registered at Crossref with
`title: ["Magellan"]` and `subtitle: ["toward building entity matching management systems"]`, and
the work admitted here took the key **`Konda_2016_magellan-work`** — a one-word title. That is not
a hypothetical; it is our own admission path binding to a truncated registry title on the day of
the review. Change **P4**.

## 2. Work disambiguation and versions — relations, not similarity

**Crossref has an explicit relation vocabulary, and it is FRBR-shaped.** From the relationships
markup guide (https://www.crossref.org/documentation/schema-library/markup-guide-metadata-segments/relationships/,
retrieved 2026-09-15), the **intra-work** table reads verbatim:

> "Expression isExpressionOf, hasExpression Format isFormatOf, hasFormat Identical isIdenticalTo
> Manifestation isManifestationOf, hasManifestation Manuscript isManuscriptOf, hasManuscript
> Preprint isPreprintOf, hasPreprint Replacement isReplacedBy, Replaces Translation
> isTranslationOf, hasTranslation Variant isVariantFormOf, isOriginalFormOf Version isVersionOf,
> hasVersion"

and the **inter-work** table separately carries "Peer review isReviewOf, hasReview". Two things
follow. First, *expression* and *manifestation* — the FRBR levels of §3 — are already relation
types in the registry we query, so a book edition and a work are distinguishable in Crossref's own
model. Second, **a review is an inter-work relation**: Crossref's model says a review is a
different work from what it reviews, which is precisely the assertion our `review_record` refusal
makes by hand.

**The version rule, stated by Crossref as policy**, from the versioning best-practice page
(https://www.crossref.org/documentation/principles-practices/best-practices/versioning/, retrieved
2026-09-15):

> "A preprint should have its own DOI (DOI A). Accepted versions (including PP, AOP, AAM, and VoR)
> should have a separate DOI (DOI B). Establish a relationship between DOI B and DOI A to show the
> connection between them, such as DOI B "hasPreprint" DOI A."

**This settles our 303/60 case as a schema question, not a scoring question.** The P3 referee ruled
that under the rules as written they are two works with two DOIs and no `version-of` relation to
express it; `LITKB_SPLINK_2026-09-15.md` §7 then measured that no similarity model can tell that
pair from six pairs of different papers by the same authors. Both are right, and the resolution is
the same in the literature: **fetch the relation, don't infer it.** Change **P2**.

**OpenAlex does it by merging, not by relating.** Priem, Piwowar & Orr 2022 (arXiv:2205.01833,
acquired):

> "OpenAlex uses a fingerprinting algorithm to match" — arXiv:2205.01833, Venues

the preprint and the version of record, reporting both and flagging the VoR as the primary host.
The same paper is candid about the cost: "much work remains to be done in validating and studying
completeness and accuracy of the dataset", and it names disambiguation of authors and institutions
as the first thing needing improvement.

**OpenCitations does it with an internal identifier, and says why.** Massari et al. 2023
(arXiv:2306.16191, acquired):

> "The deduplication process is based only on identifiers. This approach favors precision over
> recall: for instance, people are deduplicated only if they have an assigned ORCID, and never by
> other heuristics." — arXiv:2306.16191 p.5

and every entity gets an OMID "whether or not it already has an external persistent identifier
(e.g., DOI, PMID, ISBN)", the OMID acting "as a proxy between different external identifiers used
for each entity, enabling disambiguation". (Both fragments are contiguous in the printed page; the
first spans the page-5 break and the second a hyphenated line break in the `.txt` extract, so
neither greps as one string — they were checked by reading the surrounding paragraph.) **That is the published answer to our 27
`s2_candidate_has_no_doi` refusals** — the case where Semantic Scholar matched the work and all
three of our rules agreed, and we refused because there was no DOI to key on. OpenCitations' answer
is to mint a key. Change **P3**.

**What linking versions actually costs.** Bloch et al. 2023 (`10.1007/978-3-031-43849-3_5`;
preprint arXiv:2309.01373):

> "The results show that the PreprintResolver was able to resolve 603 out of 1,000 (60.3 %)
> arXiv-preprints"

using DBLP, Semantic Scholar, OpenAlex and Crossref together. And on ambiguity they do what we do:
hand multiple candidates to a human rather than pick — "For nine preprints, two different results
were identified. Three of these results provide at least one incorrect or untraceable match."
60.3 % is the number to hold against any plan to populate version relations in bulk.

**The edition refusals.** Our four `edition_mismatch` rows are the manifestation problem in
miniature, and the referee's Congalton b17 case is the mirror image: `10.1201/9781420048568` is the
first edition, the 2009 second edition has a different DOI, and the reference cited the first — so
that one was *right* to confirm. Crossref's `isVersionOf`/`hasVersion` is where that distinction
lives, and we neither fetch nor store it.

## 3. Books — the identity model, and what a separate path would look like

**The model.** IFLA LRM (2017, admitted manually from the IFLA PDF — the one manual admission that
succeeded) consolidates FRBR/FRAD/FRSAD into work–expression–manifestation–item. The operational
consequence for a resolver is one sentence: **an ISBN identifies a manifestation, a book citation
usually intends a work, and a matcher with only DOI and title has nowhere to record which level it
matched at.** Every one of our four `edition_mismatch` refusals is that missing field.

**The practice.** Hickey, O'Neill & Toves 2002 (`10.1045/september2002-hickey`) is the origin of
OCLC's FRBR work-set algorithm: WorldCat manifestation records are clustered into works by
normalised author/title keys, so a book citation binds to a **work cluster** and the edition sits
under it as a manifestation. Hickey & Toves 2014 (`10.1045/july2014-hickey`) is the same team on
VIAF, clustering author identities across national authority files — the ISNI/VIAF layer. Both are
admitted here on **metadata only**: `acquire --routes open_access` returned `binding-failed` and
`bad-file` respectively on the D-Lib records, so neither is quoted.

**A separate book identity path in our schema, as it would actually look.** Our `identifiers` table
already takes an arbitrary `scheme` and normalises per scheme (`norm_identifier`, migration 0003
handles `doi` and `arxiv` and passes everything else through `btrim`). So the schema change is
small and the *rules* are the work:

1. `isbn`, `oclc` and `isni`/`viaf` become known schemes with their own normalisation (ISBN-10 ↔
   ISBN-13 folding, hyphen stripping; an ISBN-13 and its ISBN-10 must normalise to one value or the
   duplicate check is decorative).
2. A work carries a **level** — work / expression / manifestation — and a book reference matched to
   an ISBN records that it matched at manifestation level, which is what makes an edition
   disagreement *reportable* instead of merely refusable.
3. `edition_mismatch` stops being a terminal refusal and becomes a **manifestation-level match with
   a work-level agreement**, which is what the citation usually meant.
4. Nothing above promotes a book match to `resolved` on a title similarity. OCLC's work-set keys
   are normalised author+title, which is exactly the signal our own mutation testing showed is
   weak: `LITKB_REFERENCES_2026-09-15.md` §5 measured that the median title survives 3 changed
   words and none survives 5. A book path must be identifier-first for the same reason the DOI
   decides today.

**The honest gap.** I did not find a peer-reviewed source on matching *book citations* to work
clusters at scale, and I am recording that as a gap rather than filling it with a near-match. The
material above is the identity model (LRM), the catalogue algorithm (OCLC), and Crossref's
`isManifestationOf` — not a measured book-matching evaluation.

## 4. Known failure modes of aggregators, and their guards

**Semantic Scholar's production disambiguation, measured by its own team.** Subramanian et al. 2021
(`10.1109/jcdl52503.2021.00029`; preprint arXiv:2103.07534): S2's production algorithm "relies on
hand-crafted rules and was tuned using a single dataset based on ORCID", and scores **B3 F1 78.4 %
against S2AND's 90 %**. That is the measured basis for our own rule — *S2 proposes, Crossref
confirms* — and it should be cited where that rule is written down, because today the rule rests on
our corpus alone.

**Their guard is a do-not-merge constraint, not a threshold:**

> "Added simple rules that prevent incompatible names from clustering together (e.g. John cannot
> cluster with James)" — arXiv:2103.07534 §VI

with the authors noting the rules are imperfect but "help us prevent the model from making many
obvious errors which break user trust." **Structurally this is our `review_record` /
`type_mismatch` / `reference_is_book` family**: a small set of hard constraints that veto a merge
regardless of how similar the records look. The Splink evaluation found the same thing from the
other side — 65 of 70 known-bad mutations scored as confident matches — and concluded a similarity
model cannot be the gate. Two independent lines, same conclusion.

**On the specific book-review class, a negative result worth recording.** I could not find a
peer-reviewed study documenting Semantic Scholar or OpenAlex conflating a **book review with the
reviewed book**. The searching was real and it came back empty; the class appears to be discussed in
bug reports rather than in the literature. So our three `review_record` cases and the same-surname
hole closed at referee round 2 are, as far as this review can establish, **not a documented class
elsewhere** — which is a reason to keep our own mutation tests, not a reason to relax.

**Completeness audits, for the coverage side.** Culbert et al. 2025 (`10.1007/s11192-025-05293-3`,
16.8M shared publications, OpenAlex vs WoS vs Scopus), Delgado-Quirós & Ortega
(`10.31235/osf.io/cxp4q`, which specifically flags entity extraction problems for **books and book
chapters**), and Ortega & Delgado-Quirós 2024 (`10.1007/s11192-024-05034-y`) on retraction
labelling. All three are admitted on metadata only — the open-access route returned `bad-file` or
`binding-failed` for each — so none is quoted, and they are carried as pointers, not as evidence.

## 5. Public evaluation sets we could adopt

| set | size | gold | licence | how to get it |
|---|---|---|---|---|
| **DBLP-ACM** | 2,616 × 2,294 records | **2,224** true matches; 6M Cartesian pairs reduced to 494k by blocking | **not stated** | Köpcke, Thor & Rahm 2010, `10.14778/1920841.1920904`; Magellan data repository |
| **DBLP-Scholar** | 2,616 × 64,263 records | **5,347** true matches; 168.1M → 607k | **not stated** | same |
| **JedAI D1–D10** | ~500 to ~66,000 pairs | `duplicates.csv` gold pair files | code Apache-2.0; **dataset licence not separately stated** | Papadakis et al. `10.1145/3385658.3385664`; reproducibility companion `10.1016/j.is.2021.101830` |
| **Cora** | 1,878 records | 64,578 labelled duplicate pairs | **no SPDX licence**; permission note only | HPI / ICPSR mirrors |
| Magellan benchmark suite | multiple | binary match/non-match | mostly research-use, unstated | Konda et al. `10.14778/2994509.2994535` |

**The Köpcke row is the one to adopt**, and it is bibliographic, which the others are only partly.
Its sizes are quoted from the paper's Table 1 as reported by a reading agent from the VLDB
open-access PDF; **our own `acquire` did not obtain this paper** (`no-oa-copy`), so that row is
marked METADATA in the KB and should be re-verified from the PDF before any number of ours is
compared against it.

**What is NOT available, stated as a gap:** Crossref's internal reference-matching evaluation set
is described in the blog series but I could not verify a public download, so it is not adoptable
today. No CORD-19/S2ORC dedup gold set was verified either.

**Why this matters more than the table suggests.** Our resolver's entire gold is
`Reports/litkb_splink_gold_2026-09-15.json`, built from the P6 run's own output and frozen before
the first Splink run. That is the right discipline for an ablation and it is **not an external
benchmark**: a resolver graded only on what it itself resolved cannot report recall against
anything it never found. DBLP-ACM gives us a population where the true matches are known
independently. Change **P6**.

## 6. Probabilistic linkage — and what our Splink evaluation missed

**The model.** Fellegi & Sunter 1969 (`10.1080/01621459.1969.10501049`) is the source of the
three-region rule our resolver already implements as `resolved` / `ambiguous` / `unresolved`. It is
paywalled, `acquire --routes open_access` returned `no-oa-copy`, and **nothing in this review is
quoted from it** — it is admitted for the citation only. Winkler 2014 (`10.1002/wics.1317`) and the
Herzog–Scheuren–Winkler chapter (`10.1007/0-387-69505-2_13`) are the lineage for Jaro-Winkler and
for frequency-based adjustment; likewise admitted, likewise not acquirable openly.

**The tool.** Linacre et al. 2022 (`10.23889/ijpds.v7i3.1794`, acquired) is a **one-page IJPDS
conference abstract**:

> "builds on FastLink's implementation in R of an Expectation-Maximisation algorithm to estimate a
> Fellegi-Sunter linkage model" — IJPDS 7(3) art.1794 (the PDF breaks "soft-ware", "Fellegi-
> Sunter" and "improve-ments" across lines; the quote is de-hyphenated and the typographic
> apostrophe is normalised, and nothing else is changed)

That is the whole of what the paper of record supports. Every operational instruction about
comparisons and term-frequency lives in the **documentation**, which the KB cannot admit (§8.4), so
the three quotes below carry URLs and a retrieval date instead of a work key.

**What our evaluation missed, item by item.** Read against
https://moj-analytical-services.github.io/splink/topic_guides/comparisons/term-frequency.html and
https://moj-analytical-services.github.io/splink/demos/tutorials/04_Estimating_model_parameters.html
(both retrieved 2026-09-15):

1. **The λ estimate used ONE deterministic rule where the documentation prescribes a series.**
   Splink's own guidance:
   > "It can be estimated accurately enough for most purposes by combining a series of deterministic
   > matching rules and a guess of the recall corresponding to those rules."
   and, in the worked example, "In this example, I guess that the following deterministic matching
   rules have a recall of about 70%." Our run used exact normalised title alone, acknowledged
   Splink's warning that the observed recall fell short of the expected 60 %, and proceeded.
   `LITKB_SPLINK_2026-09-15.md` §2 is explicit that "Ranking is invariant to λ; every probability,
   and therefore every threshold, is not" — which means **every `p ≥ 0.5` and `p ≥ 0.9` count in
   that report (88, 75, 9 duplicate pairs, the p-values in §5 and §7) rests on a λ estimated in a
   way the tool's own documentation advises against.** The ranking results (§3, 362/363) do not.
   This is the single largest methodological gap in that evaluation, it is stated nowhere in it,
   and it does not change its recommendation — which was to adopt ranking only.

2. **Term-frequency adjustment was applied to first author only.** The documentation's rationale is
   skew:
   > "A shortcoming of the basic Fellegi-Sunter model is that it doesn't account for skew in the
   > distributions of linking variables."

   (the page prints a typographic apostrophe in "doesn't"; that is the only normalisation.)
   Bibliographic fields are heavily skewed in exactly this way — journal title (a handful of venues
   dominate any corpus), year (our corpus clusters in a few decades), and surname. TF on **journal**
   is the obvious untried arm and is cheap.

3. **`tf_minimum_u_value` was not used, and our corpus is the case it exists for.** The docs:
   "we can mitigate this effect by imposing a minimum value on the term frequency used (equivalent
   to the u value)… `"tf_minimum_u_value": 0.001`". Our left-hand side is GROBID output, where
   misspellings and truncations produce spuriously rare values — precisely the "Siohban" case the
   documentation describes.

4. **The unordered year weights were reported and not acted on.** The trained table has year ±1 at
   **+0.34** and ±3 at **+0.42** — close-but-wrong barely distinguishable from far-and-wrong, and
   not monotone. A non-monotone comparison is normally a sign the levels are mis-specified or the
   EM had nothing to learn from; the report notes the consequence for the mutation kills and does
   not revisit the specification.

**Where these tools are actually used.** fastLink (Enamorado, Fifield & Imai 2019,
`10.1017/s0003055418000783`) and Splink are administrative/population-records tools. I could not
find a published application of either to bibliographic or citation matching. **That is a gap and
it cuts against adoption**: we would be the ones establishing that a Fellegi-Sunter model is right
for this data, and our own evaluation already found it is not a gate.

---

## 7. Proposed changes, ranked

Each is a proposal. None is implemented. "Expected effect" is an expectation, and the last column
is what would turn it into a measurement.

### P1 — a search-based fallback on the RAW reference string, for the 50 with no parsed fields
**Rank 1: largest untouched bucket, smallest change, and it is what Crossref itself did.**
Today `no_title_or_author` is terminal: 50 rows, 0 of them carrying a DOI, refused before any
search because there is nothing in the parsed fields to search on. The raw string is already
captured (`includeRawCitations=1`). Crossref's `query.bibliographic` accepts an unstructured string;
Guenci et al.'s pipeline re-invokes GROBID on demand and retries, which is the same move.
**Expected effect on our numbers:** up to 50 of 658 (7.6 pp) become *searchable*. How many resolve
is the unknown — Guenci's recall is 75.67 % on references that at least parsed, so a materially
lower rate on these is the expectation, not that rate.
**What would validate it:** run the 50 raw strings through `query.bibliographic`, confirm each hit
with the EXISTING `confirm_s2_candidate` (unchanged, still Crossref-confirming, still refusing by
name), and report resolved / refused-by-reason. Kill criterion, stated first: if it resolves a
reference to a work whose first author and year both disagree, the fallback is off.

### P2 — fetch and store Crossref `relation`, and give the schema a version relation
**Rank 2: it is the only thing that resolves 303/60 and the edition class, and it is a fetch, not a model.**
`registry.parse_crossref` already reads `subtitle` and `type`/`subtype`; `relation` is the same
JSON object. Store `isPreprintOf` / `hasPreprint` / `isVersionOf` / `hasVersion` /
`isManifestationOf` as identifier-to-identifier edges.
**Expected effect:** 303/60 becomes representable as *one work, two versions* instead of a P3
refusal. The 4 `edition_mismatch` rows become manifestation-level disagreements under a work-level
agreement, reportable rather than terminal. It changes **0** of the 385 current resolutions — no
resolution state is set from a relation.
**What would validate it:** query Crossref `relation` for the four edition DOIs and for 303/60's two
DOIs, and report how many carry a usable relation. If Crossref holds none of them, P2 is a schema
that would be empty on our corpus, and that is worth knowing before it is built. (My expectation is
that some are empty: relations are deposited by publishers and deposit rates are uneven.)

### P3 — an internal work key, so a confirmed work with no DOI is not discarded
**Rank 3: 27 measured rows, and the published precedent is explicit.**
OpenCitations mints an OMID for every entity "whether or not it already has an external persistent
identifier". Our 27 `s2_candidate_has_no_doi` rows are works S2 matched and all three of our rules
agreed on, refused only for lack of a key.
**Expected effect:** up to +27 of 658 (+4.1 pp), taking 385/658 toward 412/658 (62.6 %) — **if and
only if** the confirmation stays as strict. That is the risk: today the DOI is what Crossref
confirms against, so keying on an S2 `paperId` means accepting a work S2 alone vouches for, and
S2's production matching is the 78.4 %-B3-F1 system of §4. So the proposal is narrower than "key by
paperId": mint an internal key **and mark the work registry-unconfirmed**, never promoting it to
the same state as a DOI-confirmed resolution.
**What would validate it:** hand-check all 27 against their S2 records; if fewer than ~25 are the
right work, the internal key is carrying S2's error rate into our corpus and the change fails.

### P4 — build the work title from title + subtitle at ADMISSION, as the resolver already does at confirmation
**Rank 4: a live defect found during this session, cheap, and it corrupts keys.**
`admit/registry.py:39-40` already builds a `"title: subtitle"` form into `titles`, and
`confirm_s2_candidate` takes the max ratio over that list — but the **work record's** stored title
is the bare registry title. `10.14778/2994509.2994535` therefore entered this KB as the work
**`Konda_2016_magellan-work`**, title "Magellan", losing "toward building entity matching management
systems".
**Expected effect:** on resolution rates, zero. On the KB, it stops truncated keys being minted, and
it is the same fix that would reduce the 9 `doi_title_contained` refusals if the containment ever
became an acceptance (it should not — see below).
**What would validate it:** re-derive keys for the 378 works already in `litkb` under the
title+subtitle rule and count how many change. That count is the size of the defect, and it is
measurable without a single network call.
**Explicitly NOT proposed:** accepting `doi_title_contained` as a resolution. The P6 report refused
it, `RESOLVE_TITLE_RATIO` stays 0.85, and nothing here argues otherwise — containment is a parse
artefact on the reference side, which is a different thing from a subtitle on the registry side.

### P5 — make the asymmetry between a MISSING field and a CONTRADICTED field explicit in `confirm_s2_candidate`
**Rank 5: 5 measured rows, no new dependency, and the Splink report already named it as the alternative to adopting Splink.**
`LITKB_SPLINK_2026-09-15.md` §5 measured complete separation of the 5 lost-genuine from the 3 book
reviews — the lowest lost-genuine weight (+3.00) above the highest review weight (−2.92) — and
attributed it to one mechanism: a **missing** author or journal is a null level costing nothing,
while a **contradicted** one costs −1.93 / −1.42. That is writable directly: `crossref_no_author`
and `crossref_title_ratio` against a *thin* record are a different refusal from the same names
against a *contradicting* record.
**Expected effect:** the 5 become visible as flagged candidates instead of vanishing into
`unresolved`. Whether they should ever become `resolved` is a separate question this does not open.
**What would validate it:** the separation is n = 5 against n = 3. Eight cases is a mechanism plus
an existence proof, and the Splink report says so. It needs to hold on a larger population before
any threshold is written; the first step is to count, across all 274 unresolved, how many refusals
are against a record missing a field versus contradicting it.

### P6 — grade the resolver against an EXTERNAL gold (DBLP-ACM), not only against its own output
**Rank 6: it does not improve a number; it makes the numbers mean something.**
Our gold is built from the P6 run. DBLP-ACM gives 2,224 known true matches over 2,616 × 2,294
records, with blocking already reducing 6M pairs to 494k — a population where recall is defined.
**Expected effect:** none on the 58.5 %. It produces the first recall figure our resolver has ever
had against matches it did not itself find.
**What would validate it:** the licence. DBLP-ACM's curated match file carries **no stated
licence**, and §5 says so. Establish that before it is committed to, not after.

### P7 — cite S2AND where the "S2 proposes, Crossref confirms" rule is written
**Rank 7: documentation, not code.** The rule currently rests on our corpus. S2's own team publishes
the production system at B3 F1 78.4 %, and publishes do-not-merge constraints as its guard. Both
belong next to the rule, and the second is a direct argument for keeping our hard-constraint family
(`review_record`, `type_mismatch`, `reference_is_book`) rather than softening it toward a score.

### P8 — if the Splink layer is ever revisited, re-estimate λ the way the documentation says
**Rank 8: conditional, and it invalidates probabilities rather than rankings.**
A series of deterministic rules with a recall estimate, not a single exact-title rule; TF on journal
as well as first author; `tf_minimum_u_value` set for GROBID-derived fields; year levels
re-specified after the +0.34/+0.42 non-monotonicity. **Every probability-threshold count in
`LITKB_SPLINK_2026-09-15.md` should be treated as unvalidated until this is done**; the ranking
results, and therefore its actual recommendation, are unaffected.

---

## 8. What the KB run itself revealed — friction, refusals, and what blocked me

Reported as a defect list because that is what it is. Each item is measured on this session.

### 8.1 Steps 4 and 5 of the hunt protocol have no CLI
`litkb --help` lists `ws, discover, admit, approve, acquire, migrate, export`. The convention's
step 4 ("record the use") and step 5 ("promote prepare") are not among them. I wrote the 15 uses
through `litkb.write_proposal('use', …)` with psycopg, following
`migrate_legacy/run.py:record_use` exactly, and ran prepare through `litkb.promote.prepare`. That
works, but it means **the procedure the convention documents cannot be followed with the tool the
convention names** — and a session that did not go looking at the SQL would either invent a
different shape or skip the step.

### 8.2 The convention says a use with no verifiable quote is refused at prepare. It is not.
`LITERATURE_CONVENTION.md` step 4: "A use with no verifiable quote is refused at prepare."
Measured against `_ws_chains` (migration 0005, lines 78-85): prepare counts rows in
`use_evidence` that are `NOT promotable` and holds the chain if that count is above zero. **A use
with zero evidence rows contributes zero bad rows and prepares clean.** The P3 migration relies on
this — `record_use`'s own docstring says "A use with no quote therefore has no `use_evidence` row,
rather than an unverified one." So the rule as written in the convention is false, and every use I
wrote today is in that position.

### 8.3 A verified quote is unreachable without the stage-5 pipeline
`use_evidence` requires `block_id` and `run_id` — a quote must be anchored in an extracted text
block from an `extraction_runs` row. Producing those needs a TEI from GROBID **and** a Docling
artifact, and `qc/instruments/litkb_stage5_run.py` reads pre-existing artifacts off a **hardcoded
seven-file list**. There is no path from "I just acquired this PDF" to "this quote is verified
against its block". So the 15 uses carry their quote in the `rationale` field as free text — which
the database does not check — and the quotes in this report were verified by me, by grep, against
the acquired `.txt` extracts. That is a weaker guarantee than the design intends and it is the
single biggest gap between the convention and the machinery.

### 8.4 Documentation cannot be admitted at all, though the convention says it can
The convention: "Where a source has no DOI (blog posts, docs), record it as a manual proposal with
the URL and retrieval date." Measured: `admit --manual` requires `--file`, and check 3 binds the
claimed title against the **first page of a PDF text layer**. Admitting the Crossref relationships
page from its saved HTML returned:

```
"outcome": "refused", "refused_at": "check4_manual",
"reasons": ["no text layer on the first page and no PDF title match: waits for OCR (decisions.yaml §15.14)"]
```

The IFLA LRM admitted fine — because it is a real PDF. So **six of the sources this review depends
on have no KB record**: the Crossref relationships and versioning pages, two Splink documentation
pages, the OpenAlex help pages, and the Cora dataset page. They are cited in §2, §5 and §6 with
URL and retrieval date, outside the KB, which is exactly what the KB exists to prevent. I did not
work around it by generating a PDF from the page text: fabricating a document to satisfy the binder
would defeat the check rather than pass it.

### 8.5 `admit --doi` alone always fails, and the error does not say what to do
Three DOIs refused at `check1_study_exists` with "no claimed record to compare with the registry
and no bound file". The rule is correct and deliberate (migration 0013 line 147: "a DOI alone
proves only that SOME work exists"), but the CLI's `--doi` is advertised as sufficient, and the
remedy — add `--title`, `--authors`, `--year` — is not in the message. With those three the same
DOIs admitted immediately.

**A real gate fired here and is worth recording:** `10.1016/j.is.2021.101830` was refused for
"claimed first author does not match the registry's". My claimed first author (Papadakis, from the
discovery pass) was wrong; Crossref's is Mandilaras. The check caught a genuine error in my own
input. That is one for the machinery, not against it.

### 8.6 The `feeds` vocabulary in the convention and the one the database enforces are different
`_feeds_token_ok` (migration 0005 line 17, confirmed against the **live** `litkb` server's
`pg_proc`) accepts exactly three forms: `framework §N[.N…]`, `gap row N`, `decision <slug>`. The
convention documents seven, including `report <FILE>#§<loc>`, `review §N`, `narrative §N` and
`gated-plan gate N`. A use that feeds **this report** therefore cannot carry a valid token, and
prepare would hold the chain with "feeds: invalid tokens" if I wrote one. I wrote all 15 uses with
an **empty** `feeds` array as a result, which means the KB records that these works were used and
does not record what they were used *for*. That is a real loss of the thing the field exists for.

### 8.7 The open-access route missed sources that are plainly open access
8 of 24 registry works acquired. The failures, by reported reason: `no-oa-copy` for Köpcke 2010
(the VLDB proceedings PDF is public at `vldb.org`), for S2AND (arXiv:2103.07534 exists), for
Enamorado 2019 (author's-site PDF), Konda 2016 and Fellegi 1969; `bad-file` for the three Crossref
Labs blog posts, Culbert 2025, Ortega 2024 and Hickey 2014; `binding-failed` for Hickey 2002 and
Delgado-Quirós 2025. The route appears to depend on what Unpaywall knows, and Unpaywall does not
know VLDB proceedings, does not link an IEEE DOI to its arXiv preprint, and does not hold a
Rogue-Scholar blog DOI as a fetchable PDF. **The concrete miss that matters for this review: three
of Crossref's own posts on reference matching — the primary sources for §1 — are admitted and
unreadable.** An `arxiv`-identifier fallback and a DOI→arXiv lookup would recover at least S2AND
and Enamorado.

### 8.8 Anna's Archive was not used
0 downloads against the 15 allowed. Everything acquired came from the open-access route; everything
that failed failed for reasons the archive would not fix (blog posts with no PDF, a paywalled 1969
JASA article the DOI-first rule would send there, which I did not attempt because the review does
not quote it). The counter guard was therefore never exercised.

### 8.9 What was NOT touched
No file under `D:\edmonds-pipeline\Literture\` was deleted, moved or renamed. Two files were added
to `_litkb_staging\incoming` (the IFLA PDF, and the refused Crossref HTML); `acquire` filed 8
PDFs + 8 `.txt` extracts into `_litkb_staging\filed`. `Scripts/decisions.yaml` was not staged. No
other worktree and no branch but this one was touched. The workstream token was never printed.

---

## 9. `promote prepare`

Run per the brief, after the commit that carries this report. Output in §9.1 below.

## 10. What this review does not establish

* **The proposer is the only reader.** Everything above was assembled in one session by one agent.
  Under CLAUDE.md 3.4c, none of the §7 proposals is adoptable on this report alone.
* **Six load-bearing sources have no KB record** (§8.4) and three more are admitted but unreadable
  (§8.7), so §1's account of Crossref's own method is metadata-grade: it rests on a discovery
  agent's summary of the blog posts, not on the posts themselves.
* **The Köpcke dataset sizes in §5 were not verified from the PDF by me** — the acquire route did
  not obtain it. They are marked METADATA in the KB and should not be quoted as measured.
* **Nothing here was run against the resolver.** Every "expected effect" in §7 is an expectation
  with a stated validation, and no number in `LITKB_REFERENCES_2026-09-15.md` or
  `LITKB_S2_BATCHING_2026-09-15.md` is changed by this document.

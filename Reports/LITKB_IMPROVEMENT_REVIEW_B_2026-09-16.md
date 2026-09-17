
# Review B — identity, linkage, workflow (litkb)

## Gap 1 — reference resolution (58.5%; 50 unparsed)
Crossref's blog (B01, B02) moved from string PARSING to SEARCH-based matching, since
malformed strings that won't parse can still be searched; B02 retests on real, not synthetic,
references. First change: add a Crossref search call as a second proposer, behind the existing
title+author+year gate, for the 50 `no_title_or_author` refs GROBID cannot segment.

## Gap 2 — aggregator merge errors / identity guarding
S2AND (B03) admits a disambiguator tuned on one dataset generalizes poorly to another — the
mechanism that could merge a book's authors onto its review. Visser et al. (B04) measures
accuracy diverging across five aggregators. First change: calibrate Check 2's
duplicate threshold against merge-error pairs from more than one source.

## Gap 3 — preprint/journal/edition relations vs similarity
OpenCitations' OMID (B06) and Index (B05) resolve cross-registry identity to ONE internal id
BEFORE computing relationships — deduplicate first, relate second. First change: add a
`relation` identifier scheme mirroring Crossref's preprint/version types, so a preprint and its
published DOI collapse to one `works` row.

## Gap 4 — probabilistic linkage (Splink / Fellegi–Sunter)
Splink (B07): a Fellegi–Sunter EM model already linking UK justice records at scale, combining
partially-informative fields into one match probability — what our single trigram threshold
lacks. First change: prototype Splink over `works`+`identifiers`, scored against the tracker's
hand-labelled `Duplicate of` pairs first.

## Gap 5 — LLM/agentic pipelines: quote verification, no fabrication
PaperQA (B08) retrieves, scores relevance, then quotes — the missing half of `use add`/
`quote_verified`, which verifies a quote only after one is supplied. B09 and CiteTracer (B12)
flag misattribution and fabrication, scored on REAL fabrications, not only synthetic. First
change: use PaperQA's retrieve-and-rank step to propose the quote + block_id for `use add`.

## Gap 6 — self-verifying pipelines: mutation testing, gold-before-build
Deequ (B10) operationalizes "unit tests for data" with incremental anomaly detection — the
generalized form of what 3.4c already asks by hand. Property-Based Mutation Testing (B11)
sharpens what a kill must mean: the protecting assertion fired, not just "suite failed". First
change: each mutation row should record which assertion the kill depends on.

## Hunt outcomes
5 DOIs hunted, one per gap 1/2/4/5/6 (gap 3: drop-off only). B03/B07 were already `extracted`
in main. B01/B08/B10 were fresh admissions ending at `held`: identity registered, no PDF
bound, no spend chosen — by design (`review_B_hunts.csv`).

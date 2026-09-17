# Review A — extraction/retrieval literature scan (2026-09-16)

12 sources, 6 gaps. IDs refer to `review_A_dropoffs.csv` rows.

## 1. Formula OCR (D1 Nougat, D2 UniMERNet)
Nougat and UniMERNet are decoders architecturally distinct from ours; UniMERNet's own
motivation — prior formula datasets were too clean to generalize — suggests our 11/20
result may be a data-diversity problem, not just a decoder one. **First change:** stand up
Nougat as decoder #2 and score exact-match agreement on our gold set and UniMER-Test, not
just 20 examples.

## 2. Multi-extractor merge (D3 Docling, D4 Meuschke)
No source found merges two extractors by IoU/containment directly; closest is Meuschke's
multi-tool DocBank benchmark: GROBID best on metadata/refs, every tool weak on
lists/footers/equations, combining tools explicitly called for. **First change:** adopt
their multi-domain framework as our merge's test harness, not ad hoc checks.

## 3. Ligatures / ToUnicode (D5 Bast & Korzen, D6 Knight & Brailsford)
Thinnest gap found — PDF character-extraction correctness is studied (still unsolved
among 14 tools per Bast & Korzen, 2017), but born-digital ligature/CMap repair
specifically is not; nearest analogue is scanned-page hidden-text-layer verification.
**First change:** build a TeX-vs-PDF parallel corpus (their method) as an automatic
ligature-regression check.

## 4. Dense vs. lexical retrieval (D7 BEIR, D8 chunking)
BEIR shows BM25 beating dense out-of-domain across 18 datasets is the norm, not a bug in
our setup; the gap closes via re-ranking/late-interaction, not bigger dense models.
Separately, contextual retrieval beats naive/late chunking on coherence at added compute
cost. **First change:** add a re-ranking pass over BM25 candidates before touching the
embedder.

## 5. Reading order / table benchmarks (D9 OmniDocBench, D10 DocLayNet)
OmniDocBench is the modern attribute-level (not end-to-end-only) benchmark named in our
gap list; DocLayNet — Docling's own training set — shows layout models sit ~10pp mAP
behind human double-annotator agreement, via an IoU protocol transferable to our merge.
**First change:** set the merge's acceptance bar at that ~10pp gap, not 100% agreement.

## 6. Citation anchoring (D11 ALCE, D12 unarXive)
ALCE treats anchoring as generation-time attribution (best LLMs lack full citation support
~50% of the time on ELI5) — a caution, not a solution, for extraction-time anchoring.
unarXive is the real precedent: in-text citations linked to spans via global identifiers
across 29.2M citation contexts. **First change:** model citation-to-block anchoring on
unarXive's scheme, not LLM-attribution metrics.

**SCORE-Bench**, named in the delta, surfaced no matching record in arXiv/Crossref/OpenAlex
within budget — not claimed as covered.

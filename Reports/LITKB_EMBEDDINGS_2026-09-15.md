# P7 — embedding bake-off for the literature knowledge base

**Phase:** P7 (design `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §7 stage 7, §8, §14 P7 row, §17).
**Branch:** `work/20260915-embeddings`, worktree `D:\edmonds-pipeline\treedata-embed`.
**Run:** DB-free. No `litkb` database was read or written; the lexical leg is BM25, not `tsvector`
(§6 states what that costs).
**Author:** the builder. **The gold set and every threshold in this report were written by a
referee subagent and committed before any model was installed** (§2). CLAUDE.md §3.4c.

---

## 1. What was decided, in one paragraph

**Both models fail every pre-committed floor, and the failure is reported rather than fixed.**
Against a 60-query gold set written by a referee and committed before either model was installed,
the vector leg alone reached recall@20 = **0.617** (bge-m3) and **0.567** (nomic-v1.5) against a
floor of **0.80**; MRR was 0.235 and 0.190 against 0.50. Hybrid RRF reached 0.733 against 0.83. The
kill fired on both models — replacing chunk and query vectors with random unit vectors of the same
dimension drops recall@20 to **0.000**, below the 0.22 fixed in advance — so the scores genuinely
come from the vectors. bge-m3 wins every **overall** retrieval metric (it ties nomic on two of the
three query kinds at recall@20, §5.2) and costs 3.1× the CPU time (0.33 vs 1.04 chunks/s) and a
33 % larger index; if one model must be chosen it is bge-m3, run hybrid, and not promoted to the KB
default yet. The reason for the "not yet" is in §5.4: for bge-m3, 11 of the 23 misses were also
missed by BM25, **9 of them by every leg of both models**, and 0 are explained by the truncation
cap — so a large share of the failure is not yet attributable to the encoder. Nothing upstream
was touched after the numbers arrived: not the chunker, not the overlap rule, not the anchor
mapping, not the thresholds.

---

## 2. The gold set, frozen first

The ordering §14 P7 demands — "gold data and thresholds … written by a referee and committed
(their git hash recorded in the phase's report) before the tool or code being measured first runs
on them" — was followed literally, in this order:

| # | What | Commit |
|---|---|---|
| 1 | corpus rules + chunker + RRF + their tests (model-free) | `12b9eeb` |
| 2 | **referee's 60 gold queries + the pre-committed thresholds** | `4f0e80b`, `fb005d6` |
| 3 | the two model backends, BM25 leg, bake-off instrument, gold verifier | `5f6faf9` |
| 4 | `venv-embed` created and the models downloaded | after 3 |

**Gold file:** `Reports/litkb_p7_gold_2026-09-15.json`
sha256 `55ec40c14c5f97247991e80f99b0acaec9195271da4fef7c72a15a9fb349fcd4` (of the LF bytes as
written; the repo checks out CRLF, so re-hash after `git checkout` gives a different value —
the anchors are unaffected, `json.dump` escapes every newline inside a string).

**Thresholds file:** `Reports/litkb_p7_thresholds_2026-09-15.json`, same referee, same commit.

**Composition:** 30 paraphrase / 15 conceptual / 15 structural, ids `g001`–`g060`, across **57
distinct source papers**, anchor lengths 412–785 characters.

**Verified mechanically, not asserted** — `qc/instruments/litkb_p7_verify_gold.py`, re-run by the
builder against the committed file. Every rule the referee was given is re-checked:
`text[char_start:char_end] == anchor_text` under the corpus decode rule; anchor 200–2000 chars;
`source_stem` in the corpus; ids unique; ≥25 distinct stems; and **the query shares no run of four
consecutive tokens with the anchor**, which is the rule that makes these queries test the vectors
rather than BM25 (§8: "verbatim quotes would be found by the lexical legs alone, so they cannot
test the vectors"). Result: `ALL RULES PASS`, 0 failures.

**The builder never edited the gold.** The verifier's failure path prints "send back to the
referee, do not edit" and returns 1.

### 2.1 What the referee disclosed against itself

Recorded here because it bounds what the numbers mean, and the builder did not discover it:

- Only about **5 of the 30 paraphrase anchors** (Verbyla, Guo 2018, Salas, Efron 2004, Besag)
  correspond to passages the literature review quotes verbatim. Most review blockquotes are the
  review's own commentary, and many quoted papers are ABSTRACT/METADATA grade with no `.txt` in the
  corpus at all. The remaining paraphrase anchors are abstract or results passages from
  review-cited papers that do have extracts. **So this is a paraphrase set over the corpus, not a
  paraphrase set over the review's quote-gated quotes**, which is what §8 literally describes.
- Four papers were dropped for extraction damage (Satten 1996, Hui 1980 — inter-word spaces lost;
  Dai 1998a, Townshend 1992 — two columns interleaved).
- **Eight kept anchors are column-interleaved or space-damaged** (ids in the thresholds file). Kept
  deliberately: it is the corpus the KB must retrieve from. §5 breaks recall out per query id so a
  reader can separate extraction damage from encoder failure.

One clerical mismatch in that list, recorded rather than corrected (the gold and thresholds are
frozen): the referee's note reads "g053 Lucas", but `g053` is `Hasegawa_2019` and Lucas is `g048`.
The instrument reads the **ids**, so it flags `g053`/Hasegawa. Neither query is a miss at 20 for
either model, so no count in §5.4 moves either way.

### 2.2 The pre-committed thresholds, stated before any model ran

| Leg | recall@5 | recall@20 | MRR |
|---|---|---|---|
| vector alone | 0.60 | 0.80 | 0.50 |
| hybrid (RRF) | 0.63 | 0.83 | 0.53 |

The referee's own note on the hybrid floors: only +0.03 over the vector leg, "because rule (c)
deliberately starves the BM25 leg, so hybrid ≈ vector on this set by construction."

**Kill threshold (the number that matters most, and it was fixed before the kill ran):** with the
vectors replaced by random vectors, **the vector leg alone, on all 60 queries, must fall below
recall@20 = 0.22.** The referee's rationale, quoted: chance is ~20/9496 = 0.2% per query; 0.22 is
"about ten times above chance — far enough that a model is not killed for sampling noise on 60
queries (one query is 1.7 points; the binomial 95% upper bound on a true 0.02 over 60 queries is
about 0.08) — and about a quarter of the 0.80 a credible dense retriever should reach."

---

## 3. The corpus and the chunks

**Source.** Stage 5 blocks exist for seven gate papers only, so P7 reads the `.txt` extracts under
`D:\edmonds-pipeline\Literture\Validation` (read-only). `litkb.index.corpus` is the single place
that decides membership and decoding, so gold, chunker and evaluation see byte-identical text.

**Membership**, from 236 `.txt` files down to **200**:

| Rule | Dropped | Why |
|---|---|---|
| `*.raw.txt` excluded | 29 | a pre-cleaning twin of the same paper; every one has a plain `.txt` sibling (checked). Indexing both puts two near-identical copies in the index and splits the paper's own rank |
| decoded text < 2,000 chars | 7 | image-only scans. Anderson 1957, Hudson 1978, Hwang 1982, Politis 1994 extract to a ~21-word JSTOR cover sheet; Benjamini 1995 to 13 chars; Goodchild 1997 to 5; Ogata 1998 to 24. Indexing a cover sheet claims the paper is searchable when it is not. They return when stage 3 OCR runs |

**Decoding:** utf-8 first, then cp1252 (206 of 236 files are cp1252, 30 utf-8 — measured, not
assumed); `\r\n` and `\r` canonicalised to `\n`. No other normalisation: the gold's char offsets
are offsets into exactly this string. A file that decodes under neither codec raises rather than
substituting replacement characters, which would silently shift every later offset.

Corpus manifest: `Reports/litkb_p7_corpus_2026-09-15.csv` (stem, codec, chars, sha256 of the
decoded text). Corpus sha256
`f8a91c9585b0a7040672e88654a11ef51e8ba4500b7f1eaf8af9894ffa47ccc7`.

**Chunking** (`litkb.index.chunk`): paragraph-bounded, 300–500 whitespace-token band, 15% overlap
carried as whole paragraphs, tables/equations never split.

| | |
|---|---|
| chunks | **9,496** |
| tokens: min / p25 / median / p75 / max | 1 / 302 / **324** / 389 / 11,843 |
| mean tokens | 340.9 |
| structural chunks (table/equation/caption, emitted whole) | 578 (6.1%) |
| chunks over the 500-token ceiling | 437 — each a single paragraph longer than the ceiling, emitted whole rather than split mid-paragraph |

Chunk-set sha256 `a8da09465d9fd56bae20ea9f885710b64e608d4fdd30794ef67d51209a4f0385`.
Per-stem counts: `Reports/litkb_p7_chunks_2026-09-15.csv`.

**A chunker finding, from the first draft.** The first structural rule isolated *every* paragraph
it called a table or equation. On the maths-heavy papers that fired on about half the paragraphs —
Duval 2009, Nordman 2004, Conley 2007 each came out at ~53% structural chunks averaging ~20 tokens
— because a displayed equation in flat text is a short line dense in `=` and Greek letters, and so
is half a sentence of a measure-theory proof. Corpus median was 51 tokens. A structural block is
now emitted alone only if it is substantial on its own (≥50 tokens); a two-line equation is packed
into the surrounding prose chunk, still whole, never split. Median went 51 → 324. Both numbers are
above; this is why "structure-aware" on a flat text dump is a heuristic and is labelled one.

**Gold → chunks.** Gold is anchored on *source* char offsets, so the correct-chunk set for a query
is derived (`chunks_covering`: any chunk whose span overlaps the anchor). An anchor straddling a
chunk boundary therefore has more than one correct chunk and any of them counts as a hit. That
straddle count is reported with the run — it is a fact about the chunker, not about a model.

---

## 4. The models

Both are local, open-weight, and pinned in `Scripts/requirements-litkb-embed.txt` (a dedicated
venv, `D:\edmonds-pipeline\venv-embed`; none of torch/transformers/sentence-transformers enters
`requirements-local.txt` or `-colab.txt`). The card facts below were **authored** into
`litkb.index.embed.MODELS` from the two model cards (fetched 2026-09-15);
`embed.describe()` prints them back beside the loaded model's reported dimension as a
consistency check — it is not an independent reading of the card.

| | bge-m3 | nomic-v1.5 |
|---|---|---|
| HF id | `BAAI/bge-m3` | `nomic-ai/nomic-embed-text-v1.5` |
| dims | 1024 | 768 |
| licence | MIT | Apache-2.0 |
| instruction prefix | none | `search_query: ` / `search_document: ` (required by the card) |
| `trust_remote_code` | no | **yes** |
| normalisation | explicit, `normalize_embeddings=True` (cosine = dot) | same |
| fits pgvector `vector` (2,000-d limit) | yes | yes |

**`max_seq_length` was chosen before any recall was scored**, by a tokenizer-only census
(`qc/instruments/litkb_p7_token_census.py`, committed `db6b461`) — choosing it after seeing recall
would be fitting to the gold. At the conventional 512, **73 % of bge-m3's gold chunks and 58 % of
nomic's would be truncated**, i.e. most gold passages would sit past the point the encoder ever
reads and the miss would be charged to the model instead of to the cap. At **1024** gold truncation
is **7.0 % for both**. Both runs therefore use `--max-seq-length 1024 --batch-size 8`.

**CPU is the measured device.** The 20 % headroom rule is enforced in code:
`torch.set_num_threads(int(0.8 * os.cpu_count()))` = 9 of 12 logical cores.

**The T2000 was tried, after the CPU runs, and both models fit — measured, not assumed.** Free
memory on this card swings with what the display is doing: three `nvidia-smi` readings the same
day gave 1,354 MiB, **102 MiB**, and 3,527 MiB free of 4,096. The CUDA attempt was therefore made
only once the CPU numbers were already recorded, and into a **second venv**
(`D:\edmonds-pipeline\venv-embed-cu`, torch 2.4.1+cu121) so that `venv-embed` — the environment
that produced every CPU number — was never mutated. Same code, same pins otherwise, fp32 in both.

| on the T2000 | peak GPU memory (card total, display included) | verdict |
|---|---|---|
| nomic-v1.5, batch 8, 1024 tokens | 1,729 of 4,096 MiB | fits with room |
| bge-m3, batch 8, 1024 tokens | **3,816 of 4,096 MiB — 120 MiB spare** | fits, but only because the desktop happened to be holding 409 MiB at launch; at the 3,834 MiB reading above it would not have started |

---

## 5. Results

Machine-readable: `Reports/litkb_p7_results_2026-09-15.csv` (every leg × every query kind),
`Reports/litkb_p7_perquery_2026-09-15.csv` (each gold id's rank in each leg),
`Reports/litkb_p7_harness_2026-09-15.csv` (the kill row), `Reports/litkb_p7_miss_anatomy_2026-09-15.csv`
(why each miss missed). Everything below is copied from those files, not retyped from memory.

### 5.1 Cost

| model | device | chunks/s | wall for 9,496 chunks | index (float32) | peak RSS | peak GPU |
|---|---|---|---|---|---|---|
| bge-m3 | CPU, 9 threads | **0.33** | 28,704 s (7 h 58 m) | 38.9 MB | 3.4 GB | — |
| bge-m3 | T2000 | **0.93** | 10,215 s (2 h 50 m) | 38.9 MB | — | 3,816 MiB |
| nomic-v1.5 | CPU, 9 threads | **1.04** | 9,149 s (2 h 32 m) | 29.2 MB | 1.8 GB | — |
| nomic-v1.5 | T2000 | **6.45** | 1,473 s (25 m) | 29.2 MB | — | 1,729 MiB |

nomic is **3.1× faster than bge-m3 on the same CPU** and its index is 25 % smaller (768 vs 1024
dims). The T2000 is worth **6.2× over CPU for nomic but only 2.8× for bge-m3** — the bigger model
spends its time in a 4 GB card it nearly fills, and 0.93 chunks/s on the GPU is still slower than
nomic managed on the CPU. Index size scales linearly: at 9,496 chunks it is trivial either way, but
per 100k chunks that is 410 MB (bge-m3) vs 307 MB (nomic) before any pgvector index overhead.

**Device does not change the numbers.** Both models returned recall, MRR and kill results on the
T2000 identical to their CPU runs to three decimals (bge-m3 0.383 / 0.617 / 0.235 both ways; nomic
0.333 / 0.567 / 0.190 both ways). That is a free cross-check that the GPU path is the same
computation, not a second measurement of the model.

### 5.2 Recall — the vector leg alone, which is what §8 puts on trial

Floors are the referee's, fixed before either model was installed (§2.2). **recall@k here means
"at least one gold chunk in the top k"**, the referee's stated definition, not the fraction of
gold chunks recovered.

| leg | model | recall@5 | recall@20 | MRR |
|---|---|---|---|---|
| **floor** | *(referee)* | **0.60** | **0.80** | **0.50** |
| vector alone | bge-m3 | 0.383 **FAIL** | 0.617 **FAIL** | 0.235 **FAIL** |
| vector alone | nomic-v1.5 | 0.333 **FAIL** | 0.567 **FAIL** | 0.190 **FAIL** |
| lexical alone (BM25) | — | 0.317 | 0.567 | 0.277 |
| **floor** | *(referee)* | **0.63** | **0.83** | **0.53** |
| hybrid RRF | bge-m3 | 0.383 **FAIL** | 0.733 **FAIL** | 0.225 **FAIL** |
| hybrid RRF | nomic-v1.5 | 0.367 **FAIL** | 0.633 **FAIL** | 0.209 **FAIL** |

**Every gate fails.** Per §14 P7 and CLAUDE.md §3.4c the response is to report the failure, not to
move the floors: nothing upstream — the chunker, the 15 % overlap, the any-overlapping-chunk hit
rule, the thresholds — was touched after the numbers arrived.

Three things in that table are worth naming, because they are not what a bake-off usually finds:

1. **Neither dense model beats a bag of words on rank quality.** BM25 MRR is 0.277; bge-m3 0.235,
   nomic 0.190. It does so *despite* gold rule (c), which forbids any shared run of four
   consecutive tokens between query and anchor precisely to starve the lexical leg. Rare technical
   terms survive paraphrasing — "autologistic", "CUSUM", "misregistration" — and BM25 weights
   exactly those. The dense models win on recall@5 (0.383 / 0.333 vs 0.317) and bge-m3 on
   recall@20, but the passage is rarely their first hit.
2. **RRF is doing real work.** Hybrid recall@20 with bge-m3 is 0.733, above either leg alone
   (0.617 vector, 0.567 lexical) — the two legs miss different queries, which is the premise of §8's
   hybrid design and is here measured rather than assumed. It is still short of the 0.83 floor.
3. **The conceptual queries are where the vector leg was supposed to win and does not.** bge-m3
   scores 0.400 recall@20 on them, BM25 scores 0.600.

Per query kind, vector leg:

| kind (n) | bge-m3 r@5 / r@20 / MRR | nomic r@5 / r@20 / MRR | BM25 r@5 / r@20 / MRR |
|---|---|---|---|
| paraphrase (30) | 0.467 / 0.733 / 0.301 | 0.400 / 0.633 / 0.226 | 0.500 / 0.600 / 0.405 |
| conceptual (15) | 0.200 / 0.400 / 0.079 | 0.267 / 0.400 / 0.139 | 0.067 / 0.600 / 0.095 |
| structural (15) | 0.400 / 0.600 / 0.258 | 0.267 / 0.600 / 0.169 | 0.200 / 0.467 / 0.203 |

### 5.3 The random-vector kill

The mutation: **both** the 9,496 chunk vectors and the 60 query vectors are replaced by random
unit vectors of the same dimension, generated in `embed.random_vectors`, normalised the same way
and pushed through the same `embed.search`. Pre-committed threshold: the vector leg alone must
fall **below recall@20 = 0.22**.

| model | real recall@20 | random recall@20 | threshold | expected | observed |
|---|---|---|---|---|---|
| bge-m3 | 0.617 | **0.000** | < 0.22 | FIRE | **FIRE** |
| nomic-v1.5 | 0.567 | **0.000** | < 0.22 | FIRE | **FIRE** |

Harness rows `P7K1` in `Reports/litkb_p7_harness_2026-09-15.csv`. The instrument returns a
non-zero exit code if the kill does not fire, so a scrambled index cannot be reported as a pass.

The honest reading: 0.000 is **chance**, not a wide margin of merit. With 20 draws from 9,496
chunks, the expected recall@20 of a random index is ~0.2 % per query; the referee set 0.22 an order
of magnitude above that so sampling noise could not kill a real model. What the row proves is
narrow and necessary: the 0.617 is coming from the vectors, not from chunk ordering, not from the
id list, not from an accidental lexical path inside the dense leg.

### 5.4 Where the misses come from

`qc/instruments/litkb_p7_miss_anatomy.py` attributes every vector miss at 20, joining the ranks to
measured properties of each query's gold chunks. Categories are applied in order, so each miss is
counted once.

| | bge-m3 | nomic-v1.5 |
|---|---|---|
| vector misses at 20, of 60 | 23 | 26 |
| anchor began past the 1,024-token cap (encoder never read it) | **0** | **0** |
| referee-flagged extraction damage | 3 (`g011 g023 g031`) | 3 (same three) |
| BM25 also missed it at 20 — no leg found it | 11 | 14 |
| unexplained: BM25 found it, the encoder did not | **9** | **9** |

Two conclusions follow, and they point in opposite directions:

- **The truncation cap explains nothing.** Choosing 1,024 over 512 before scoring (§4) was worth
  doing, and having done it, no miss can be blamed on it. Had the cap stayed at 512, roughly 7 in
  10 gold chunks would have been read only in part and this table would have been unreadable.
- **A large share of the misses are not the encoder's.** For bge-m3, 11 of 23 are queries neither
  it nor Okapi BM25 put any gold chunk in the top 20 for (`g025 g027 g033 g037 g042 g043 g046 g047
  g050 g052 g058`); for nomic it is 14 (`g006 g012 g025 g026 g029 g033 g037 g042 g043 g046 g047
  g049 g050 g052`). **The two lists are not nested.** Their intersection — **9 queries, `g025 g033
  g037 g042 g043 g046 g047 g050 g052`** — is the set no leg of either model found, and that is the
  set worth calling unretrieved-by-any-method. The two bge-m3-only entries are instructive in the
  other direction: nomic ranks `g027` **4th** and `g058` **16th**, so those two are bge-m3 encoder
  misses that a smaller model retrieved, not corpus damage. When a bag of words and two independent
  dense retrievers all fail on the same query, the suspect is the query, the anchor, or the
  extract — not the embedding model. That is a referee's call to make, and §8 says so.
- The residue — **9 queries for both models** (`g001 g002 g008 g024 g032 g036 g039 g045 g057` for
  bge-m3; `g001 g002 g019 g024 g032 g039 g040 g045 g060` for nomic, six of them shared) — is
  genuine encoder failure: BM25 ranked the passage inside 20 and the dense leg did not. `g001` and
  `g002` are the sharpest cases: BM25 ranks them 3rd and 1st, and neither model has them in its
  top 50.

**The proxy that failed, reported as a failure.** The instrument also measures subwords per
whitespace word in each gold chunk, on the theory that text which lost its inter-word spaces or
interleaved two columns shatters into subwords. It does not separate the referee's flagged anchors
from the rest: the single highest ratio on the set (2.07, `g054`, against a gold median of 1.60 for
bge-m3) belongs to a query that **ranks 2nd**. The column stays in the CSV, labelled a proxy that
did not work, rather than being deleted.

---

## 6. Limitations

Ordered by how much each could move the verdict.

1. **The gold set is a paraphrase set over the CORPUS, not over the review's quote-gated quotes.**
   The referee disclosed this against itself (§2.1): only about 5 of the 30 paraphrase anchors
   correspond to passages the literature reviews quote verbatim, because most review blockquotes
   are the review's own commentary and many quoted papers have no `.txt` extract at all. §8's
   design says "paraphrases of verbatim review quotes"; this is the nearest thing the corpus
   supports. A referee who rebuilt the gold from stage-5 blocks over the seven gate papers would be
   testing something different, and possibly easier.
2. **The lexical leg is Okapi BM25 in-repo, not Postgres `tsvector` + `pg_trgm`.** The run is
   DB-free by instruction, so the hybrid number is a stand-in: real `tsvector` stems, weights
   fields, and handles phrases differently, and `pg_trgm` adds fuzzy matching BM25 has no analogue
   for. The lexical and hybrid rows would move. Which of the two ENCODERS wins would not — the
   vector leg is scored alone, and the lexical leg is byte-identical across both models (its row is
   literally the same numbers in both runs, which is the check that it is model-independent).
3. **Eight gold anchors sit in extraction-damaged text and were kept deliberately** (§2.1). Three
   of them are among the misses. They are not an excuse: this is the corpus the KB must retrieve
   from. But a referee re-running after stage-3 OCR should expect a different number.
4. **Chunking is a heuristic over flat PDF text dumps.** Structure is inferred from paragraph
   shape, not from a document model — §3 records the first draft calling half of a maths paper
   "structural". 437 chunks exceed the 500-token ceiling because a single paragraph does, and
   **28 of the 60 anchors straddle a chunk boundary**, which the hit rule handles by counting any
   overlapping chunk. Real stage-5 blocks would replace all of this.
5. **Seven papers are excluded as image-only scans and 29 `*.raw.txt` twins as duplicates** (§3).
   The excluded seven are not searchable by any method today; they return with OCR.
6. **60 queries is a small sample.** One query is 1.7 recall points. The gap between bge-m3 and
   nomic on recall@20 (0.617 vs 0.567) is three queries; it is consistent across recall@5, recall@20
   and MRR and across the per-kind breakdown, but it is not a wide margin and should not be quoted
   as one.
7. **CPU throughput is machine-specific** — 9 of 12 logical cores on this workstation, fp32,
   batch 8. The ratio between the two models is the transferable fact; the absolute chunks/s is not.
8. **The T2000 result is fragile, not a capability claim.** bge-m3 finished with 120 MiB spare on a
   card whose free memory was measured at 102 MiB earlier the same day. It fits when the desktop is
   quiet. That is not a basis for scheduling work on it.

---

## 7. Recommendation

**Do not promote either model to the KB's retrieval default on this evidence. If one must be
picked today, pick bge-m3, and run it hybrid.**

**Why bge-m3 and not nomic.** It wins every *overall* metric measured — recall@5 0.383 vs 0.333,
recall@20 0.617 vs 0.567, MRR 0.235 vs 0.190 — and the hybrid leg with it (0.733 vs 0.633). The
margin is **not** uniform across query kinds, and the report will not pretend otherwise: at
recall@20 bge-m3 wins only the paraphrase kind (0.733 vs 0.633) and **ties** nomic on conceptual
(0.400) and structural (0.600); on conceptual queries nomic is actually ahead at recall@5 (0.267 vs
0.200) and MRR (0.139 vs 0.079). With 15 queries per kind that is one or two queries either way, so
the aggregate is the number to steer by — and in aggregate bge-m3 leads on all three metrics.
It costs 3.1× the CPU time and a 33 % larger index, and that is the trade: 8 CPU-hours per full
re-index of 9,496 chunks against 2.5, or 2 h 50 m against 25 m on the T2000. For a corpus this size,
re-indexed rarely, the retrieval margin is worth more than the throughput. If the corpus grows an
order of magnitude and re-indexing becomes routine, that arithmetic flips and nomic deserves a fresh
look.

**Licences are not a discriminator.** bge-m3 is MIT; nomic-embed-text-v1.5 is Apache-2.0. Both
permit commercial use and redistribution. nomic requires `trust_remote_code=True` — its
`nomic-bert-2048` implementation is downloaded and executed from the Hub, and it silently fetched a
newer copy of `modeling_hf_nomic_bert.py` during this run. That is a supply-chain surface bge-m3
does not have, and if nomic is ever adopted the revision must be pinned.

**Dimensions are not a constraint here.** pgvector's `vector` type indexes up to 2,000 dimensions
and `halfvec` up to 4,000; bge-m3 at 1024 and nomic at 768 both fit the plain `vector` type with
room to spare, so §8's index choice is unconstrained by either model.

**But the honest headline is that the vector leg failed its floor by a wide margin — 0.617 against
0.80 — and hybrid failed too.** The design's own §14 P7 kill language is about the vector leg
carrying paraphrased queries alone, and it does not. Two facts stop that being a verdict on the
encoders:

- 11 of bge-m3's 23 misses were also missed by BM25 at 20, and 9 of those were missed by every leg
  of both models (§5.4). Until someone reads those nine anchors against their chunks, that part of
  the failure cannot be attributed to an encoder at all.
- Every leg is being scored against a chunker that is a heuristic over flat text dumps, with 28 of
  60 anchors straddling a boundary and 437 chunks over the token ceiling.

So the actionable recommendation is a measurement, not a model: **resolve the nine queries that no
leg of either model retrieved before re-running.** If they turn out to be unretrievable anchors,
the remaining 51 queries put bge-m3's vector recall@20 at 37/51 = 0.73 — still short of 0.80, but a
different conversation from 0.617. That arithmetic is offered as an upper bound a referee can check,
not as a score: dropping
the hardest queries after seeing the results is exactly the move the frozen-gold rule exists to
prevent, and this report does not adopt it.

---

## 8. What blocks a referee

What an independent agent would need in order to re-run and disagree, in the order it would bite.

**Nothing blocks a re-run of the scoring.** Corpus, chunks, gold, thresholds and every per-query
rank are committed with hashes (§2, §3). `qc/instruments/litkb_p7_verify_gold.py` re-checks the
gold against the corpus mechanically. The bake-off takes the chunk file, the gold file and the
thresholds file as arguments and writes the CSVs this report quotes. A referee with the venv can
reproduce every number here; a referee without a GPU can reproduce every number except the two
T2000 throughput rows.

**Four things block a verdict:**

1. **Nine queries need a human-or-referee reading.** `g025 g033 g037 g042 g043 g046 g047 g050
   g052`: no leg of either model — both dense encoders and BM25 — put any gold chunk in the top 20.
   The
   question — is the anchor retrievable at all from the extract as chunked? — cannot be answered by
   the builder without re-opening the gold, which the frozen-gold rule forbids. It is a referee's
   call, and it decides whether 0.617 is an encoder result or a corpus result.
2. **The gold is paraphrase-over-corpus, not paraphrase-over-review-quotes** (§2.1, the referee's
   own disclosure). Design §8 describes the latter. Whether the substitution is acceptable is a
   design call, not a measurement, and it was made by the referee under the constraint that the
   review's quoted papers largely have no extracts.
3. **The lexical leg is BM25, not `tsvector` + `pg_trgm`** (§6.2). The hybrid verdict is provisional
   until it runs against the real leg in `litkb_test_w9`. The vector comparison is not affected.
4. **Stage 5 blocks do not exist yet except for seven gate papers.** P7 chunked flat `.txt`
   extracts because that is what exists. Re-running over real structural blocks would change the
   chunk set, the straddle count and every recall number — it is the single change most likely to
   move the result, and it is upstream of this phase.

**What does NOT block a referee, and is settled:**

- The kill fires, on both models, through the same code path (§5.3), so the pass/fail machinery is
  known to work rather than merely never having fired.
- `max_seq_length` was set by a tokenizer census committed before any recall was scored (§4), and
  the miss anatomy confirms zero misses are attributable to it (§5.4).
- The lexical leg is identical across both model runs, which is the check that it is
  model-independent.
- Both devices give identical scores, so nothing here is a GPU numerics artefact.

**Provenance.** Every number in this report comes from
`Reports/litkb_p7_{results,perquery,harness,miss_anatomy}_2026-09-15.csv`, written by
`qc/instruments/litkb_embed_bakeoff.py` and `qc/instruments/litkb_p7_miss_anatomy.py`. The CPU runs
used `D:\edmonds-pipeline\venv-embed` (torch 2.4.1 CPU); the T2000 runs used a second venv,
`D:\edmonds-pipeline\venv-embed-cu` (torch 2.4.1+cu121), created after the CPU runs so the CPU
environment was never mutated. Both are pinned in `Scripts/requirements-litkb-embed.txt`. No
`litkb` database was touched; `Literture\` was read only.

**`py -3.12 qc/check.py --fast` with `LITKB_PGPORT=1`** (so the 260 Postgres guards skip rather
than run against a live server): secrets PASS, ruff PASS, compile PASS, pytest **4 failed, 2,445
passed, 283 skipped**. One is the known `test_pointer_paths_resolve[crown_state_model]`. The other
three are in `qc/test_litkb_inventory.py` and are **inherited, not P7's**: they assert the live PDF
corpus still matches a committed census, and the corpus has grown to 268 PDFs against the 224
pinned (`assert 268 == 224`). That test and `litkb/extract/inventory.py` were last touched by
commits `cc36b82` and `d0d0e7c`, both of which predate this branch's P7 work; P7 reads `.txt`
extracts only and never wrote to `Literture\`. The 26 P7 tests in `qc/test_litkb_index.py` pass.

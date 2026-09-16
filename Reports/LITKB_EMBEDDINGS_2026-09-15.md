# P7 — embedding bake-off for the literature knowledge base

**Phase:** P7 (design `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §7 stage 7, §8, §14 P7 row, §17).
**Branch:** `work/20260915-embeddings`, worktree `D:\edmonds-pipeline\treedata-embed`.
**Run:** DB-free. No `litkb` database was read or written; the lexical leg is BM25, not `tsvector`
(§6 states what that costs).
**Author:** the builder. **The gold set and every threshold in this report were written by a
referee subagent and committed before any model was installed** (§2). CLAUDE.md §3.4c.

---

## 1. What was decided, in one paragraph

*(filled in §7 after the numbers)*

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

**The T2000 does not fit, measured, not assumed.** `nvidia-smi` on this machine: Quadro T2000,
4,096 MiB total, **3,834 MiB already held by the display and other processes, 102 MiB free**
(an earlier reading the same day: 2,742 MiB used, ~1,354 MiB free). bge-m3 fp16 weights alone are
≈1.14 GB before any activation at 1,024 tokens. Neither reading leaves room, so no GPU throughput
number is reported. No CUDA wheel was installed: swapping the torch build between the two models'
runs would unpin the requirements file from what actually ran.

---

## 5. Results

*(filled after the runs)*

---

## 6. Limitations

*(filled after the runs)*

---

## 7. Recommendation

*(filled after the runs)*

---

## 8. What blocks a referee

*(filled after the runs)*

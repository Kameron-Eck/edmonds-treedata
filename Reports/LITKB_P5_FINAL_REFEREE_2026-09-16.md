# litkb — final acceptance referee: the P5 bulk pass and the operational fix set — 2026-09-16

Independent pass. Worktree `D:\edmonds-pipeline\treedata-litkb`, branch
`work/20260913-literature-kb`, review range `b2c7324..1d18dce`. Live `litkb` read **read-only**
as `litkb_reader`; the MCP server driven as a real stdio subprocess in a NEW session
(`LITKB_SESSION=ref-op-1`), calling only `litkb_search` and `litkb_work`. Mutations ran on
`litkb_test_w1` / `w9`. Nothing under `D:\edmonds-pipeline\Literture\` was written.

**Gold was authored and committed first** — `Reports/gold/p5_gold_2026-09-16.json`, sha256
`6eeab1eb3bd58817989e2a618f76a057ed0763324e6736801df9132735ed5bd4`, commit `3230b48` — before
one block of text, one stored LaTeX string or one table row was read (CLAUDE.md §3.4c). Two
seeded draws, each with the sha256 of its own sorted population: 8 files → one page each, read
from the rendered page image; 20 equation blocks → read from a crop of the block's own canonical
bbox with the box drawn on it, so a frame error would appear as a displaced rectangle rather than
a silent mis-read.

---

## VERDICT

**OPERATIONAL WITH CAVEATS.**

The base does what the two reports say it does at the level they measured: every admitted file is
extracted inside an `ok` run, the text a session quotes is recoverable, the four-state ladder
answers, and the three P8 gold passages still come back at ranks 1, 2, 2 through a cold session.
What no one measured is the level below that — **whether the stored content is right**. On a
seeded sample of twenty, **nine of the twenty stored LaTeX strings are wrong**; on a seeded
sample of eight pages, the text is right but **stored twice** in most documents, and search has
no filter that keeps a running head out of a ten-hit result list. None of that is fatal to a
session citing a passage. All of it is fatal to "without caveats".

The caveats, ranked by what they cost a session:

1. **The formula LaTeX is about half right** (§3). 11 of 20 sampled equations correct, 9 wrong —
   5 mathematically wrong (a dropped `λ_n`, `S^d` for `S^{d-1}`, `α` read as bold `a`, `Z̄` for
   `Z`, a dropped subscript) and 4 carrying prose from outside the box. The reports measure the
   *join* rate (99.4 % attached) and never the *content*.
2. **Duplicate canonical blocks are systemic** (§4): 3,120 extra rows by normalised text in
   **205 of 229 files**, and 6,309 blocks that are a proper substring of another block on the same
   page in **224 of 229 runs**. Reference lists are stored twice, figure captions twice.
3. **Search returns furniture and has no type filter** (§7): in my two cold questions, 8 of 20
   top-10 hits were `page_header`/title blocks, one running head five times; one of the two
   questions surfaced no answering body passage in the top ten.
4. **A block's `page_no` is not a citation page** (§2, G7): a paragraph crossing a page break is
   stored under one page number.
5. **`absent` is one bucket for three different situations** (§6) and the `bound-unextracted`
   rung has no live instance to exercise.
6. The five scans and the book are still unadmitted; `extraction_jobs` does not exist, so kills
   (c) and (d) cannot be exercised; throughput metrics are still JSONL (§8).

---

## 1. What reproduces exactly

Every load-bearing number in `LITKB_P5_BULK_2026-09-16.md` that I could re-derive, re-derived.

| claim | source of the claim | measured here | verdict |
|---|---|---|---|
| 225 files, 3,945 pages, 102,008 blocks, 857 tables, 1,821 figures, 7,772 equations, 3,297 with LaTeX, 20 unmatched, 74,658 disagreements, 23 OCR pages, 8 files with a coverage failure | `Reports/litkb_p5_files_2026-09-16.csv`, summed | all identical | ✅ |
| after the fix set: 229 ingested, 0 runs not ok, 0 blocks outside an ok run, 0 duplicate runs per key | §E | `229 / ok 251 / 0 / 0` | ✅ |
| blocks 103,947 in current runs, 1,758 in the five superseded runs | §E | 103,947 and 105,705 − 103,947 = 1,758 | ✅ |
| equations with LaTeX = 3,297 + 175 from the four new works | §3.3, §D | **3,472**, all `provenance.latex = codeformula-l4` | ✅ |
| Higham 0.30494 → 0.98984 (15 → 0 pages below the floor); Efron 0.74575 → 0.98506 (1 → 0) | §E | identical to five decimals, from `litkb.pages.coverage_share` | ✅ |
| the clamp's population is 5 files / 45 pages, and **no** page has a negative `dx` | §E | independent re-census straight from pdfium over all 229 active files, 3,947 pages: **5 files, 45 pages; 0 negative `dx`** | ✅ |
| the coverage floor now catches 6 of 229 documents | §E | 7 pages in 6 files below 0.80; 4 of the 6 are the rotated-page refusals | ✅ |
| the three P8 gold passages at ranks 1, 2, 2 | §6.1 | re-run through a NEW stdio session after the re-ingest: **1, 2, 2** | ✅ |
| `check.py --fast`: 1 failed (`crown_state_model`), 3,070 passed, 25 skipped, 2 xfailed | §L | **1 failed, 3,070 passed, 25 skipped, 2 xfailed, 651.3 s**, litkb Postgres 374 passed 3 skipped | ✅ |
| `extraction_jobs` is NOT BUILT | §8 | 0 tables matching `%extraction_job%` in the database | ✅ |
| 204 works in main with no bound file; 14 bound files stranded in 3 open workstreams | §G | 204; p3-migration 12, edge-pre1990 1, linkage-review 1 | ✅ |

---

## 2. The gold pages: presence and order are good, `kind` and duplication are not

Eight seeded pages, 69 hand-annotated body items (plus 5 figure/table placeholders).

| page | file, page | items | present | `kind` correct | within-column order violations | duplicate groups on the page | verbatim paragraph |
|---|---|--:|--:|--:|--:|--:|---|
| G1 | Fleming 2025 p10 | 7 | 7 | 7 | 0 | 0 | operating ✅ |
| G2 | Reiche 2015 p13 | 3 | 3 | 3 | 0 | **1** | operating ✅ |
| G3 | Shi 1998 p15 | 7 | 7 | **0** | 0 | 0 | **✗** |
| G4 | Pengra 2020 p7 | 11 | 11 | 11 | 1 (artefact) | 0 | operating ✅ |
| G5 | Burnicki 2010 p9 | 5 | 5 | 5 | **1 (real)** | 0 | operating ✅ |
| G6 | Ploton 2020 p1 | 4 | 4 † | 2 | 0 | 0 | operating ✅ |
| G7 | Steenberg 2017 p12 | 4 | 4 | 4 | 0 | 0 | **contained, not equal** |
| G8 | Conway 2022 p11 | 28 | 28 | **0** | 0 | **1** | operating ✅ |
| | **total** | **69** | **69** | **32** | **1 real** | **2** | 6 of 8 at the operating grade |

† the automated matcher missed G6 item 2 (the author line carries a `✉` glyph my snippet did not);
the content is present verbatim at `reading_order` 6. Presence is 69/69 by hand, 68/69 by script.

**Strict byte equality failed on all eight, as the gold predicted in advance** — blocks keep their
line breaks. That is not a defect and the gold said so before the measurement.

Three real findings sit behind that table.

**`reference` is stored twice, and the copy a reader finds first is typed `paragraph`.** On
Conway p11 the database holds 29 `paragraph` blocks in page order (`reading_order` 200-228, the
printed entries) **and** 28 `reference` blocks (418-445) carrying GROBID's re-serialised form
("Factors influencing long-term street tree survival in Milwaukee AKoese…"). Shi p15 holds 7 and 7.
The mechanism is in `reconcile._assign_order`: reading order is Docling's own `tool_order`, and a
region only GROBID saw with no Docling twin sorts at `1 << 30` — so every parsed reference lands
after the last page's blocks. A session that finds a reference by its printed text gets
`block_type: paragraph`; the `reference`-typed twin has different bytes and different offsets.

**Only 10 of the 18 block types are ever used.** Over every canonical block of every current run:
`paragraph` 66,489, `reference` 9,300, `equation` 8,055, `page_header` 6,664, `heading` 5,281,
`page_footer` 2,509, `caption` 2,036, `figure` 1,842, `footnote` 910, `table` 861. `title`,
`author`, `affiliation`, `abstract`, `list_item`, `page_number`, `sidebar` and `other` are
**never assigned**. On the Ploton title page the paper's title is a `heading`, its author list and
its affiliation footer are both `paragraph`. That is why G6 scores 2 of 4 and G3/G8 score 0.

**G5 carries one genuine reading-order violation, and it is the layout model's.** On a
single-column page the first body paragraph (`y0 = 321.7`) has `reading_order` 121 while the figure
at the top of the page (`y0 = 65.2`) has 125 and its caption 126. `_assign_order` only sorts by
Docling's sequence, so this is Docling's order, faithfully carried — not something the reconciler
introduced.

**G7 is the citation-page finding.** The block holding the gold paragraph is stored with
`page_no = 12` and 872 characters, of which the first ~700 are printed on **page 11** — confirmed
by extracting both pages' text layers (`'While the above findings' in p11: True, in p12: False`).
`use_evidence` cites a block id plus character offsets; the page a reader would print beside the
quote can therefore be wrong by one for any paragraph that crosses a page break.

**G3 is the only page where the text itself is wrong.** The stored block ends
`…Mathematical Geographers)` and the PDF's own text layer has `…Mathematical Geographers).` — one
dropped character at the block's edge. (The same page's small-caps surnames are lowercase in the
text layer, which is the PDF's property, not the pipeline's; the gold anticipated it.)

**Tables.** Pengra p7 holds three. Table 4 (gold: 9 data + 2 header) is stored with 11 rows,
Table 5 (9 + 1) with 10 — both match. Table 3 is stored with 12 where the gold says 11, and the
extra row is the `Agreement %` line the gold explicitly excluded because it is printed *outside*
the ruled frame; the extraction captured more than the gold's convention, not less. Column
indices are preserved across blank cells (row "Water" carries `col_idx` 0-6, 8, 9, 11 — column 7
is blank in the print and genuinely absent), so the numbers are aligned. The rotated stub label
smears into two row labels ("interpretations Barren", "Initial Grass/shrub").

---

## 3. The L4 LaTeX: 11 of 20 right

Twenty equation blocks drawn by seed from the 3,472 with LaTeX in a current run, each read by me
from a rendered crop **before** the stored string was fetched. Every crop landed on its equation,
including `E17` on `Conley_1999`, whose page has `dx = 40.0, dy = 37.0` — so the cropbox join is
right on a cropped page, measured rather than argued.

| grade | n | ids |
|---|--:|---|
| identical / equivalent | **11** | E02, E04, E08, E09, E10, E13, E14, E15, E16, E17, E18 |
| wrong — mathematically | **5** | E03, E05, E07, E12, E20 |
| wrong — contaminated with content from outside the box | **4** | E01, E06, E11, E19 |

11/20 = 0.55; a 95 % binomial interval is roughly 0.32-0.77, so "about half" is as sharp as 20
draws allow. The failures are not exotic:

* **E03** `Nordman_2004` p17 — stored `\frac{-1}{s}(…)`; the page prints `−1/(sλ_n)`. The `λ_n` is
  gone, and a second line `\cdot 1 - 7 \sum …` is appended that is not on the page.
* **E05** `Galerne_2011` p6 — `\sup_{u\in S^{d}}` for the printed `S^{d-1}`.
* **E12** `Chaux_2008` p13 — `\mathbf a_1(\mathbf k_i)` for the printed `α_1(k_i)`, in both the
  numerator and the denominator.
* **E07** `Liu_2008` p6 — `\frac{1}{\bar Z}` for the printed `1/Z`, plus two `\text{agronal}`
  tokens that are not words.
* **E20** `Leung_2004b` p11 — `\text{e}_{n,i}\text{e}^{T}`: the second factor lost its `_{n,i+1}`.
* **E01, E06, E11, E19** — the mathematics is right and the string also carries the sentence above
  or below the box, sometimes garbled (`\text{ingrating this equation over}`,
  `\intertext{ i n t s e q u a l s }`, `be the sequence of detectors dual to`).

All 3,472 carry `provenance.latex = codeformula-l4`, so this is the Colab L4 pass, and it is the
one part of the corpus no gate has ever scored for content. **`LITKB_COLAB_L4_FULLPASS` and P5 §3.3
both measure whether a row ATTACHED, never whether it is RIGHT.** A `\bar Z` for a `Z` promotes
clean through every check in the system.

*One correction to my own gold, made by re-reading at 8× zoom:* I recorded **E02** as
`\hat{u} = My`; the page prints `μ̂ = My` and the stored `\hat{\mu} = My` is correct. The gold was
wrong and the database was right. It is graded in the database's favour above.

---

## 4. Integrity on `litkb`

| check | result |
|---|---|
| active files without a current run | **0** |
| files with a current run and zero blocks | **0** |
| blocks whose run is not `ok` | **0** (all 251 runs are `ok`) |
| duplicate run keys `(file, stage, tool, tool_version, params_hash, pipeline_version)` | **0** |
| duplicate `(run_id, reading_order)` among canonical blocks | **0** |
| **duplicate `(file, page, bbox)` among canonical blocks** | **63 groups, 73 extra rows** — 60 `paragraph`+`paragraph`, and one each of `equation`+`paragraph`, `equation`+`figure`, `figure`+`table` |
| **duplicate `(run, page, normalised text ≥ 40 chars)`** | **1,635 groups, 3,120 extra rows, in 205 of 229 files** |
| **canonical blocks whose normalised text (≥ 80 chars) is a PROPER substring of another block on the same page** | **6,309, in 224 of 229 runs** |
| equations / with LaTeX, current runs | 8,055 / **3,472** |
| tables / table_cells, current runs | 861 / 57,687 |
| pages, current runs | 4,006 |
| `pipeline_version` over current runs | 224 `stage5-2+l4latex`, 5 `stage5-2+l4latex+dyclamp` |

The duplication is one class with three shapes, and **R-8 of the operational referee named only
the smallest of them**: a whole extractor's output stored beside the other's. By type pair,
normalised, ≥40 chars: `paragraph`/grobid 676 groups, `paragraph`/docling 351, `caption`+`figure`
219 (a caption's text stored again inside the figure block — G2 and G5 both show it),
`reference`/grobid 101, `equation` cross-extractor 26. The Pengra page shows the extreme case: one
GROBID `paragraph` of **3,392 characters** at `reading_order` 104 contains the page's two table
captions and its body text, all of which are also stored as their own blocks.

Nothing in the fix set touches this, and the §14 gate cannot see it: its clause is "zero duplicate
**runs**".

*Not a defect, noted:* the `pipeline_version` label is mixed (224 vs 5) while the effect is not —
the clamp changes only files with a negative raw `dy`, and there are exactly 5. A P9
reproducibility pass will have to read two labels for one corpus.

---

## 5. The dy clamp — right, and its own report understates it

The coverage numbers reproduce to five decimals (§1) and the population is confirmed
independently (5 files, 45 pages, no negative `dx`).

**But the fix set's §E says "The block delta is zero on every file … the shift moves a block's BOX,
not the set of blocks." That is true of the COUNT and false of the CONTENT.** Comparing the
superseded run with the current one, block for block:

| file | blocks before → after | distinct block TEXTS that differ |
|---|---|--:|
| `Higham_2011_pth-roots-stochastic-matrices` | 412 → 412 | **515** |
| `Efron_1986_how-biased-apparent-error-rate` | 451 → 451 | **159** |
| `Jackson_2002_hidden-markov-models-onset-progression` | 284 → 284 | 24 |
| `Kalbfleisch_1985_analysis-panel-data-markov` | 462 → 462 | 8 |
| `Mesquita_1999_effect-surrounding-vegetation-edge` | 149 → 149 | 0 |

At `reading_order` 5 on Higham page 1, before the clamp: `y0 = 69.5`, text
`"Contents lists available at S"`. After: `y0 = 181.1` (= 69.5 + 111.6), text
`"On pth roots of stochastic matrices"` — the paper's title. Block text is assembled from the
characters under the box (`text_source = native-layer`), so a box off by 111.6 pt stores the wrong
words, not merely the wrong rectangle. On the blocks whose text is unchanged the shift is exactly
what it should be: joining one-to-one on `(page, type, text)` where the key is unique in both runs,
97 pairs, `y` moved by −111.6 at the minimum and `max |Δx| = 0.51`.

So the defect was worse than §6.2 and §E describe and the fix is worth more than they claim. The
sentence to correct is §E's summary, not the clamp.

---

## 6. `litkb_work`, cold, through a new stdio session

Six probes, `litkb_search`/`litkb_work` only, workstream `ref-op-1`, nothing written.

| probe | selector | state | evidence |
|---|---|---|---|
| a never-admitted title (the GUM) | `key=JCGM_2008_…` | **absent** | `found: false`, generic hint |
| a work admitted only in an OPEN workstream | `key=Platanios_2014_…` | **absent** | same generic hint |
| **a scan**: admitted, no file bound | `key=Anderson_1957_…` | **held** | `blocks: 0, files: []` |
| extracted, by key | `key=Efron_1986_how-biased-apparent-error` | **extracted** | 451 blocks, `Validation/Efron_1986_….pdf` |
| extracted, by DOI | `doi=10.1093/biomet/asq010` | **extracted** | 360 blocks → Mei_2010 |
| the 688-page book | `key=Schneider_2008_…` | **absent** | no work carries the key |

Three of the four states answer correctly on live data, including the scan. Two limits:

* **`bound-unextracted` has no live instance** — `main_files` with `current_run_id IS NULL` is 0 —
  so on `litkb` that rung is exercised only by `test_litkb_work_answers_each_of_the_four_states…`
  and by my kill R1 below.
* **The fix set's §A says of Platanios: "the hint names the open workstream that holds it." It does
  not.** All three `absent` probes return one identical 158-character hint that mentions the
  *possibility* of an open workstream and names none. A session still cannot tell "never admitted"
  from "admitted next door". The P8 referee's recall hole #2 is open.

*Also worth a line:* my first probe used `Efron_1986_how-biased-apparent-error-**rate**` — the file
stem, not the key — and got `absent` with the same generic hint. There is no title or fuzzy
selector, so a near-miss key is indistinguishable from a work the base has never heard of.

---

## 7. Two fresh framework questions, searched cold

Both are gap-ledger rows whose passage is not already quoted in the framework's §19 (the trap R-7
caught). `litkb_search(limit=10, scope="all")`, vector leg off.

**QA — gap rows 3/16: when a space-time autologistic likelihood carries an intractable normalising
constant, what estimator is used?** Rank 1 `Hughes_1999` p6, quoted with the block's own bytes:
*"…it is likely that the autologistic model for P…RtjSt† will be required to capture local spatial
dependences successfully. Then both the E-step and the M-step become computationally intractable as
the number of stations, n, increases…"*. **The top passage states the problem, not the answer.**
The answer is named at rank 10 (`Hughes_2011` p4: "we derive the Monte Carlo ML estimate (MCMLE)
for the centered autologistic model"). **Answers: partially.** `Geyer_1992` — the paper that
introduced the estimator — takes ranks 2, 3, 5, 6, 8 and 9, and **five of those six are its own
running head**, `CONSTRAINED MONTE CARLO MAXIMUM LIKELIHOOD`, from pages 3, 5, 7, 9 and 11: the
same 42 characters returned five times in a ten-row list.

**QB — gap row 9: in a non-homogeneous hidden Markov model, how are the transition probabilities
made to depend on covariates?** Rank 1 `Bureau_2003` p18, about fitting continuous-time HMMs to
HPV data — **does not answer the question**. The right paper appears at rank 4 as its own *title*
and at ranks 6, 8 and 10 as its *running head*; no body passage stating the transition form is in
the top ten. **Answers: no.**

`litkb_search` applies no block-type filter, so `page_header` and `page_footer` — 9,173 canonical
blocks — compete with body text on equal terms. The P8 referee closed with "a session that only
knows the question has not been tested". It is tested now: one of two questions failed, and the
mechanism is furniture plus duplication crowding a ten-row result list.

---

## 8. Remaining gaps, ranked by what blocks "operational without caveats"

| # | gap | blocks it? | measured |
|--:|---|---|---|
| 1 | **LaTeX content is unscored and about half wrong** | **YES** | §3 |
| 2 | **Duplicate canonical blocks, 205 of 229 files** | **YES** | §4 |
| 3 | **Search returns furniture; no type filter** | **YES** | §7 |
| 4 | `page_no` is not a citation page for a paragraph crossing a page break | **YES**, for citation integrity | §2 G7 |
| 5 | `absent` cannot be told apart from "admitted in another workstream" | partly — a session refetches a paper it already has | §6 |
| 6 | the 5 scans (`Anderson_1957`, `Hudson_1978`, `Hwang_1982`, `Ogata_1998`, `Politis_1994`) — 4 admitted with 0 files, `Politis_1994` carries no work key | no: a stated admission gap, and binding needs an OCR pass | §4 probes; `main_works` join |
| 7 | the 688-page book `Schneider_2008` — no work carries the key | no | same |
| 8 | `litkb_acquire` strips `detail` from its result | no — `acquisition_attempts` holds `detail` on all 167 rows, so the data is there and only the tool surface hides it | DB |
| 9 | `extraction_jobs` absent → kills (c) and (d) unexercisable | no, but it is why two of four §14 kills have never fired | 0 tables match `%extraction_job%` |
| 10 | throughput metrics still JSONL | no | `extraction_runs.metrics` holds only the reconcile `stats` |
| 11 | doc drift: `SKILL.md` §0 says "~102k blocks over 225 documents" (live: 103,947 over 229); `Reports/litkb_p5_files_2026-09-16.csv` predates the 4 new works and the 5 re-ingests | no | §1 |
| 12 | the suite's own banner says "3 SKIPPED: litkb server/role/psycopg absent"; the three skips are `litkb_live` network tests (`LITKB_LIVE=1`) | no | `pytest -rs` |

Two P8-referee fixes I checked and found **done**: `SKILL.md` line 66 carries the "copy the quote
out of the `litkb_search` result's `text` field" rule, and `.gitignore:195` whitelists
`/_derived/promotions/*.md` — `git check-ignore -q` exits 1, so step 5's `git add` now stages.

---

## 9. Kills — my own edits, seven rows, seven fired

Each row: the targeted tests pass, one edit of mine is applied, the tests fail, the file is
restored and the restoration proved by sha256. Worker DBs `litkb_test_w1` / `w9`.

| id | what I broke | baseline | mutated | fired |
|---|---|---|---|---|
| **R1** | `litkb_work`'s ladder can no longer say `bound-unextracted` — a bound file with no current run reports `extracted` | 2 passed | **1 failed** | ✅ |
| **R2** | the statement emptiness gate: a blank claim records beside a verified quote | 4 passed | **3 failed** | ✅ |
| **R3** | the statement cap (`STATEMENT_MAX` → 10⁹) | 1 passed | **1 failed** | ✅ |
| **R4** | feeds stored unvalidated again — `litkb._feeds_token_ok` never called at record time | 20 passed | **5 failed** | ✅ |
| **R5** | `litkb_my_uses` stops requiring the workstream token | 11 passed | **1 failed** | ✅ |
| **R6** | the cropbox clamp: `max(dy, 0)` removed from the ONE frame reader | 8 passed | **6 failed** | ✅ |
| **R7** | the OCR per-process cap raised above the batch size that measured 94.6 % of VRAM | 1 passed | **1 failed** | ✅ |

`server.py` restored to `5458c09d81a288e7…`, `inventory.py` to `783581a247f9a0eb…`,
`docling.py` to `159e0bd37225e7af…`; `git status --short` clean after every row.

R7 is config-only, as the delta says: the test that pins it is
`test_litkb_p5_bulk.py::test_the_ocr_batch_runs_in_short_converter_processes`, whose assertion
`D.OCR_CHUNK < 15` is what fails. No OCR ran here.

---

## 10. Did NOT test

* **OCR on a scan, end to end.** No scan is bound, so none can be extracted. (618 blocks in the
  corpus do carry `text_source = ocr` — the 21 `partial` pages of mixed documents — so the path
  itself is exercised at small scale.)
* **`record_use` live on `litkb`.** The fix set's three refuse-only probes were not repeated: the
  brief says read-only, and a refusal still opens a writer connection. The gates are covered by
  R2-R4 on a worker database instead.
* **`promote prepare` / `promote commit`.** Not exercised.
* **Per-region recall.** Still computable only on the 6 stage-5 gold pages.
* **Reproducibility.** No file was re-extracted at the same pipeline version (P9).
* **The whole of Table 3.** I verified the header row, `Water`, `Developed`, `Disturbed`,
  `Barren`, `Tree cover`, `Total` and `Agreement %` against the render, not all 115 cells.
* **The OCR backlog page count.** §J's own correction (89 vs 111) was not re-derived.
* **`plan --workstream` with actual rows**; **the L4 re-crop** of `Reynolds_2000` /
  `Montgomery_1991`; **`OCR_CHUNK` and `free_cache` together** — all three remain as the fix set
  left them.
* **A second reader on this report.** Everything above is one referee's reading, with the gold
  frozen first and its sha256 published.

## 11. Blockers for the next step

1. **Score the LaTeX before anything relies on it.** 20 draws put the error rate near a half; the
   next step is a bigger seeded sample with a written rubric, and a decision about whether a
   formula region that also contains prose should carry LaTeX at all.
2. **Decide what `canonical` means when two extractors both describe one region.** 3,120 duplicate
   and 6,309 contained blocks are not a fusion bug in one file; they are the fusion rule at corpus
   scale, and search and `record_use` offsets both sit on top of them.
3. **Give `litkb_search` a block-type filter** (or rank furniture down). It is a one-clause change
   and it is what made QB fail.
4. **Bind the five scans**, which needs an OCR pass inside the acquisition path, and admit
   `Politis_1994` and `Schneider_2008`, which carry no work key.
5. **Either build `extraction_jobs` or retire §12.3-§12.5**, so that two of the four §14 kills stop
   being permanently unexercisable.

---

*Referee: Claude Opus 5, session https://claude.ai/code/session_015MUcyGTfX2koRdYAjW5kED.
Gold `Reports/gold/p5_gold_2026-09-16.json` (`6eeab1eb…`) committed at `3230b48` before any
measurement. Read-only against `litkb`; mutations on `litkb_test_w1`/`w9`; nothing under
`D:\edmonds-pipeline\Literture\` was written; no secret printed.*

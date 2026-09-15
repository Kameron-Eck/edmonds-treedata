# Docling stage 3, local — build and measurement (litkb P4, gate 2)

**Date:** 2026-09-15 · **Branch:** `work/20260915-docling-local` (worktree
`D:\edmonds-pipeline\treedata-docling`) · **Contract:** CLAUDE.md §3.4b, §3.4c
**Design:** `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §7 stage 3, §7.1, §12, §14 P4
**Companion:** `Reports/LITKB_GROBID_LOCAL_2026-09-14.md` and its referee report — same five
papers, same method, so the two stages' numbers can be put side by side.

Every number below was measured on this laptop on 2026-09-15 by
`qc/instruments/litkb_docling_bench.py`, and every row it produced is in
`Reports/litkb_docling_throughput_2026-09-15.csv`. Nothing here is copied from the vendor's
documentation; where this report states something it did not measure, it says UNCONFIRMED in
those words.

---

## 1. What was installed, and where

| | |
|---|---|
| **docling** | **2.127.0** (`pip install docling`, 2026-09-15) |
| docling-core / -parse / -ibm-models | 2.96.0 / 7.19.1 / 4.0.2 |
| torch | **2.14.0+cpu** — the default Windows wheel. `torch.cuda.is_available()` → **False** |
| transformers / numpy | 5.17.0 / 2.5.3 |
| OCR engines present | **rapidocr 3.9.2, torch backend only** (onnxruntime is NOT installed, which rules out rapidocr's default backend; §3.1). docling registers `auto, easyocr, kserve_v2_ocr, nemotron-ocr, ocrmac, rapidocr, tesseract, tesserocr`; of those, only rapidocr is installed, and `Get-Command tesseract` finds no binary on PATH |
| venv | `D:\edmonds-pipeline\venv-docling` — **1.4 GB**, created with the project's own `py -3.12` (3.12.10) |
| models | downloaded to `%USERPROFILE%\.cache\huggingface\hub` on first use: `docling-layout-heron` 164 MB, `docling-models` (TableFormer) 342 MB, `CodeFormulaV2` 611 MB |
| pin file | `Scripts/requirements-litkb-extract.txt` (new) |

**The project's environment has none of this** (design referee M9). `litkb.extract.docling`
imports the standard library and, for the frame shift only, pypdfium2; docling runs as a
subprocess of the venv python through `litkb/extract/docling_worker.py`. The ladder therefore
still passes on a machine that has never installed docling, and
`qc/test_litkb_docling.py::test_the_adapter_imports_without_docling` asserts it by reading the
adapter's own top-level imports.

### 1.1 Two install-time traps, both measured, both now guarded in code

* **`D:\edmonds-pipeline\secrets\` is a directory**, and Python puts the cwd (or the script's
  directory) at the head of `sys.path`. numpy's `bit_generator` does `from secrets import
  randbits`, so *any* docling run launched with that folder on the path dies with
  `ImportError: cannot import name randbits` — an error that names neither numpy nor the
  folder. The launcher chooses the worker's cwd and passes `-P`.
* **The adapter is called `docling.py`**, and the worker sits beside it. With the worker's own
  directory on `sys.path`, `import docling` finds the *adapter* and fails with `No module
  named 'docling.datamodel'; 'docling' is not a package`. The worker scrubs its own directory
  from `sys.path` and the launcher passes `-P`.

---

## 2. The adapter (`Scripts/pipeline/litkb/extract/docling.py`)

Block vocabulary identical to the GROBID adapter's (`page, x0, y0, x1, y1, kind, text,
extractor, confidence, element_id, box_index, box_count, frame`) plus the two things docling
contributes: `order_index` (reading order) and `content_layer` (body vs furniture). Tables come
back as `Table`/`Cell` — a cell grid with `row`, `col`, `row_span`, `col_span`, text and box,
never as rendered text; figures as `Figure`, a page-region reference (page + box), no pixels.

### 2.1 The canonical frame — what docling actually emits

| Property | Measured |
|---|---|
| page numbering | 1-indexed (`prov[].page_no`, `pages` keyed by a string page number) |
| units | PDF points |
| item box origin | `coord_origin = "BOTTOMLEFT"`, so `t > b`; the adapter flips against the page height |
| **table cell box origin** | **`"TOPLEFT"` — in the same JSON file.** Both origins coexist; the adapter branches on the field, never on the container |
| which page box | **the CROPBOX.** On `Alwan_1988` (mediabox `(0,0,612,792)`, cropbox `(10.345,10.777,603.441,782.948)`) docling reports the page as `593.096 × 772.171` — the cropbox, exactly as GROBID does. `page_frames()` + `to_mediabox()` shift into the mediabox frame; rotated pages are left alone and keep `frame="cropbox"`, as in the GROBID adapter |
| reading order | the `body` tree's child order, depth-first through `groups` — **not** the `texts` array order and **not** geometric |
| per-item confidence | **none exists in the exported DoclingDocument.** `Block.confidence` is `None` rather than a fabricated number. Docling reports a per-page/per-document confidence grade on the conversion result object; that grade is recorded in `metrics["confidence"]` (shape: `parse_score`, `layout_score`, `table_score`, `ocr_score`, per page and per document, plus `mean_grade`/`low_grade`) |

**§7.1 alignment against pypdfium2** (the GROBID referee's method: union the per-character
boxes of a string that occurs exactly once on the page, convert to the canonical frame,
compare):

| PDF | cases | max component offset (whole-element strings) | every string inside its block? |
|---|--:|--:|---|
| Benedek 2015 (cropbox = mediabox) | 4 | **5.52 pt** (3 of the 4 at 1.11 pt) | yes |
| Alwan 1988 (cropbox ≠ mediabox) | 1 | **3.47 pt** | yes |

One pypdfium2 quirk had to be handled to get those numbers: **the first character of a text run
comes back with a zero-area box positioned at the end of the previous run.** On Benedek p1 the
"1" of "1. Introduction" reports `(561.0, 326.6, 561.0, 326.6)` — the right edge of the line
above. Unioned in, it inflates the string's box by 458 pt and the alignment check reports a
frame error that does not exist. Degenerate boxes are dropped.

---

## 3. Timing, memory and CPU — CPU only

**Machine load present — and one contamination window, named.** This is a shared laptop
(design §12.1) and nothing of Kam's was closed. At the start of the session: 27% CPU non-idle
with Task Manager, Firefox, Edge, Chrome and two Claude Code sessions running, 41.9 GB of
63.8 GB free. Each batch records the system-wide CPU percent before and after itself
(`load_cpu_pct_before` / `_after` in the CSV: 34% → 61% for cpu-t4, 54% → 16% for cpu-t8).

**At 08:14 UTC another session started `qc/instruments/litkb_p2_mutations.py --workers 9`** —
nine parallel pytest workers on the same 12 logical cores. The batches in §3 and §3.1 ran
**07:45–08:00 UTC** and are clean of it; the full-book row ran at 09:32 UTC with a single
other pytest worker on the machine (27% ambient before, 45% after) (`started_at` is in the CSV, per row). The formula
runs in §6 are **not**; they are marked there.

Method: one worker process per configuration, converter built once
(**7.6 s**), warmed on one page (**7.8 s**) before anything is timed, then one timed job per
paper. Peak RSS is sampled at 5 Hz inside the worker over each job — Windows'
`peak_wset` is a lifetime high-water mark and would report the largest job the process ever
ran. `cpu_cores_busy` is the worker's own CPU seconds over its wall clock (12 logical cores
exist).

**Configuration A — `num_threads=4`, CPU, tables on, OCR off, formula off**

| paper | pages | wall s | pages/s | peak RSS MB | cores busy | body blocks | tables |
|---|--:|--:|--:|--:|--:|--:|--:|
| Benedek 2015 (two-column) | 16 | 33.29 | **0.481** | 1,872 | 2.47 | 377 | 4 |
| Alwan 1988 (scan, text layer) | 10 | 16.64 | **0.601** | 2,007 | 3.71 | 157 | 0 |
| Anderson 1957 (JSTOR, image-only) | 22 | 29.68 | **0.741** | 2,056 | 3.65 | **1** | 1 |
| Bellettini 2002 (equations) | 51 | 64.62 | **0.789** | 2,036 | 2.58 | 819 | 0 |
| Schneider 2008 (book, pp. 1–100) | 100 | 135.69 | **0.737** | 2,641 | 3.54 | 1,011 | 3 |
| **aggregate** | **199** | **279.9** | **0.711** | **2,641** | | | |
| Schneider 2008, **all 688 pages** (separate batch, 09:32 UTC) | 688 | 995.90 | **0.691** | **4,120** | 2.86 | 7,026 | 13 |

**Configuration B — `num_threads=8`, everything else identical**

| paper | pages | wall s | pages/s | peak RSS MB | cores busy |
|---|--:|--:|--:|--:|--:|
| Benedek 2015 | 16 | 31.84 | **0.503** | 1,878 | 5.80 |
| Alwan 1988 | 10 | 14.21 | **0.704** | 1,972 | 6.50 |
| Anderson 1957 | 22 | 31.00 | **0.710** | 2,058 | 6.31 |
| Bellettini 2002 | 51 | 59.67 | **0.855** | 2,050 | 6.51 |
| Schneider 2008 (pp. 1–100) | 100 | 124.46 | **0.804** | 2,648 | 6.84 |
| **aggregate** | **199** | **261.2** | **0.762** | **2,648** | |

**What this says.** Doubling the thread budget buys **7%** aggregate throughput (0.711 →
0.762 pages/s) for **1.9×** the CPU (3.5 → 6.5 cores busy). The work is not thread-scalable
here; the sensible setting is the cheap one.

**The instrument can see a slowdown** (design §14 asks for this before any rate is believed).
Alwan 1988, same everything, `num_threads=1`: **25.23 s, 0.396 pages/s, 1.03 cores busy** —
against 16.64 s and 0.601 pages/s at 4 threads. **1.52x slower on one thread**, and the
`cpu_cores_busy` column shows why. A throughput instrument that reported the same rate for
both would not be measuring anything.

**The 20% headroom rule (`decisions.yaml` §15.16)** — 20% of RAM and CPU free for Kam:

* **RAM:** peak 2.65 GB of 63.8 GB. Nowhere near the limit at any pool size measured.
* **CPU:** `num_threads=4` used **3.5 of 12 logical cores = 29%**, which on top of the measured
  27% ambient leaves ~44% free — inside the rule. `num_threads=8` used **6.8 cores = 57%**,
  which on top of ambient leaves ~16% — **outside the rule**, for a 7% rate gain.
  **`num_threads=4` is the setting the rule supports and it costs almost nothing.**
* Unlike GROBID, the memory here IS per worker: one process, one document. Two parallel
  workers at `num_threads=4` would be ~5.3 GB and ~7 cores — the same CPU problem as one
  worker at 8 threads, so parallelism, not threads, is where the next measurement belongs
  (**not measured here**).

**The book, measured in full.** Pages 1–100 took 136 s (t4); the whole 688 pages took
**995.9 s = 16.6 min, 0.691 pages/s**, 7,026 body blocks. The projection from the first 100
pages (~15.6 min) was 6% optimistic, so the back half is slightly denser — but only slightly.

**Peak RSS is a function of document length, and that is the pool-sizing number.** The same
book at 100 pages peaked at **2.6 GB**; at 688 pages it peaked at **4.12 GB** — the
DoclingDocument is held in memory and grows with the document. Four parallel workers on files
of this size would be ~16 GB, which is inside 63.8 GB but is nowhere near the 2 GB the article
-sized files suggest. A worker pool must be sized on the longest document, not the median.

### 3.1 OCR — the same JSTOR scan, engine `rapidocr`

| config | pages | wall s | pages/s | peak RSS MB | cores busy | body blocks |
|---|--:|--:|--:|--:|--:|--:|
| Anderson 1957, OCR **off** | 22 | 29.68 | 0.741 | 2,056 | 3.65 | **1** |
| Anderson 1957, OCR **on** | 22 | 234.08 | **0.094** | 2,456 | 3.01 | **179** |

OCR is **7.9× slower** and is what turns this file from "one block" into a document.

**Which engine, measured not inferred.** The batch ran with docling's `auto`. Running the same
page with logging on prints

> `Auto OCR model selected rapidocr with torch.`

so the engine is **rapidocr 3.9.2 on its TORCH backend**, CPU device. The backend matters and
nearly produced a wrong answer here: `--ocr-engine rapidocr` on its own fails with
`ImportError: onnxruntime is not installed`, because `RapidOcrOptions` defaults to the
onnxruntime backend, which is not present. Docling's `auto` tries ocrmac (macOS), nemotron
(Linux), rapidocr+onnxruntime, easyocr, and only then rapidocr+torch — the fifth candidate is
the one that runs here. The adapter now takes `--ocr-backend`, and
`qc/testdata/litkb_docling/anderson1957_p1-2_ocr.docling.json` was produced with
`rapidocr` + `torch` explicitly; its page-1 blocks match the `auto` run's.

The conversion also carries a confidence grade, now recorded in `metrics["confidence"]`:
for Anderson p1, `parse_score 1.0, layout_score 0.785, ocr_score 0.983, mean_grade
"excellent", low_grade "good"`. It is per page and per document — **not** per block.

### 3.2 GPU

**Docling does not use the T2000 in this installation.** `pip install docling` on Windows
brings **torch 2.14.0+cpu**, whose `torch.cuda.is_available()` is `False`, so
`AcceleratorDevice.CUDA` has nothing to bind to. Making a GPU run possible means replacing
torch with a CUDA wheel in this venv, which changes every number in §3 and re-pins the
requirements file. Docling itself supports CUDA; **this installation does not have it** —
that is a property of the wheel, not of the tool. The driver is present (581.42, CUDA 13.0) with 3.1 GB of the 4 GB free.
**Not attempted in this session; the CPU measurement is the one that stands.**

---

## 4. Gate checks

### 4.1 Reading order on the two-column paper — **PASS**

Benedek 2015 page 2. Gold (hand-read from the rendered page, committed in
`qc/test_litkb_docling.py::BENEDEK_P2_ORDER` before the check was accepted): the whole left
column precedes the right one, so these three must come back strictly increasing —

1. `(e.g. detecting new forest regions)` — left column, first paragraph
2. `Since direct methods do not use explicit` — left column, middle
3. `As the above discussion already foreshows` — right column, under §1.2

Docling returns them at reading-order positions **29, 32, 38**. Zero violations.

Better than that: the paragraph beginning *"Differences between approaches can also be taken…"*
runs from the foot of the left column into the head of the right one, and docling returns it as
**one item with two prov boxes** (x≈33 and x≈302), in the right place in the flow. The adapter
emits one block per box and the test asserts the count matches `box_count`.

### 4.2 Table cells on a table-heavy page — **PASS**

Benedek 2015 page 14 carries Table 2 (8 × 10, spanning headers) and Table 3 (7 × 4).

| | Table 2 | Table 3 |
|---|--:|--:|
| grid | 8 rows × 10 cols | 7 rows × 4 cols |
| cells returned | **73** | **28** |

Five values spot-checked against the page image (`BENEDEK_T2_CELLS`, `BENEDEK_T3_CELLS`):
`(0,0)=Method`, `(1,1)=F-A`, `(2,0)=PCA (Wiemker, 1997)`, `(2,3)=6.21`, `(7,7)=2.23` — all
correct; and on Table 3 `(0,3)=F-rate`, `(6,1)=36.0`, `(5,2)=55.3` — all correct. The whole
grid was compared by eye against the page and matches, including the `L 3 MRF` row
(the subscript is split into its own token, which is the only text difference in either table).

Column spans survive: `Szada data set`, `Tiszadob data set` and `Archive data set` each carry
`col_span=3` and `Table.at()` resolves every column under them to the spanning cell.

**One defect, reported not hidden:** the `Method` header is visually a two-row spanning cell;
docling gives it `row_span=1`, so grid position `(1,0)` is a hole (`None`). Stage 5 must not
assume a dense grid.

### 4.3 OCR on the JSTOR scan — **PASS**

`Anderson_1957` has a text layer on page 1 only, and that layer is the JSTOR access
boilerplate (166 characters; pages 2–22 hold zero). With OCR off, the whole 22-page document
yields **one** body block. With OCR on it yields **179**, and the first one is

> `STATISTICAL INFERENCE ABOUT MARKOV CHAINS` — label `section_header`, page **1**

*The brief asked whether the title is recovered "from page 2". In this PDF the title is on
page **1**: there is no separate JSTOR cover sheet, the boilerplate sits in page 1's footer
strip. The title is recovered, from the page it is actually on.*

The paragraph that runs from page 1 onto page 2 comes back as one item with three prov boxes,
in order, and page 2's running head is labelled `page_header` rather than body.

OCR quality on a 1957 letterpress scan is good but not clean, and the errors are the kind that
matter to a quote check: `usualiy` for *usually*, `sncreases` for *increases*, `x²-tests` where
the page reads `χ²-tests`, and page 2's folio `90` read as `06`. **Any verified-quote rule
applied to OCR'd text must expect this** — an exact-match quote gate would reject true quotes
from scanned sources.

### 4.4 Formula LaTeX — see §6 (measured separately; two of five equations are wrong)

---

## 5. Kills — all fired

Method: mutate the adapter's source, run `qc/test_litkb_docling.py`, restore it, re-run;
exactly the GROBID referee's §4 method. The suite is **25 fixture tests + 3 live tests**, and
the table below is the sweep re-run against the final source (8c5f980).

| Mutation / kill input | Result |
|---|---|
| **y-flip removed** (`y0, y1 = page_height - t, page_height - b` → `t, b`) | **3 failed** — incl. `test_alignment_against_pypdfium2_character_boxes` |
| **`coord_origin` ignored** (treat every box as TOPLEFT) | **3 failed** — same set |
| **cropbox shift dropped** in `to_mediabox` | **1 failed** — `test_to_mediabox_shifts_by_the_cropbox_origin` |
| **span fill removed** from `Table.at` | **1 failed** — `test_table_column_spans_are_preserved` |
| **reading order = document order reversed** | **7 failed** — incl. `test_reading_order_does_not_interleave_the_columns` and the OCR title |
| **groups appended after the flow** instead of walked in place | **1 failed** — `test_iter_items_walks_groups_in_place_and_never_loops` |
| **multi-prov boxes collapsed to the first** | **1 failed** — `test_a_paragraph_that_crosses_a_column_keeps_both_boxes` |
| unmutated | **25 passed, 3 skipped** |

The three live tests (the corrupt PDF, the zero-byte file, and a fresh conversion reproducing
the committed fixture) were run as committed: `LITKB_LIVE=1 … -m litkb_live` → **3 passed** in
43.6 s.

And the three kill INPUTS the brief names, each asserted as its own test:

| Kill input | Test | Result |
|---|---|---|
| a deliberately interleaved column order | `test_kill_geometric_order_interleaves_the_columns` — the same blocks re-indexed by a naive (page, top, left) sort | the reading-order gate **fails**, as required |
| shuffled table cells | `test_kill_shuffled_table_cells_fail_the_value_check` — cell texts permuted across the same geometry, shape and spans untouched | the value check **fails**; a shape-only check would not have |
| a corrupted PDF | `test_live_corrupt_pdf_raises_instead_of_returning_an_empty_document` (+ a zero-byte file) | **raises `DoclingError`** |
| bbox y-flip removed | `test_kill_alignment_fails_without_the_y_flip`, and the source mutation above | the pypdfium2 alignment test **fails** |

Two refusals were built in from the start rather than discovered later, because the GROBID
referee found their absence in the other adapter:

* **a conversion with no body block is a FAILED run**, never an ok run with zero blocks
  (`check_text_blocks` → `NoTextBlocks`; tested on a picture-only document and on a
  furniture-only one).

  **And this gate does NOT catch `Anderson_1957` with OCR off** — that run returns **one**
  body block (the JSTOR boilerplate), and one is ≥ 1, so it passes exactly the way GROBID's
  200 did. This is the referee's "partially extractable scan" class, and the zero-block rule
  is necessary but not sufficient for it. What catches this file is stage 0's per-page
  text-layer probe (design §7 stage 0: 22 pages, 1 with any text, 166 characters) plus a
  blocks-per-page floor, neither of which is built. **Open, and it belongs to stage 0, not
  here.**
* **a corrupt or zero-byte file is refused with a recorded row.** pypdfium2 is the first
  thing to reject it (`PdfiumError: Failed to load document (PDFium: Data format error)`), and
  the page count is taken inside the timed try so the failure leaves a `status="failed"`
  metrics row instead of killing the batch. Docling can also return a result whose
  `ConversionStatus` is `FAILURE` without raising; `extract()` refuses that too.
* **a run with no peak-RSS sample is not a measured run** (design §14), and the bench
  instrument refuses a row with no rate or no peak RSS.

---

## 6. Formula enrichment — measured separately, and it is very slow

`do_formula_enrichment=True` adds the **CodeFormulaV2** model (611 MB, downloaded on first
use). It is autoregressive and runs per formula region.

| run | pages | wall s | pages/s | peak RSS MB | cores busy | formulas |
|---|--:|--:|--:|--:|--:|--:|
| Bellettini pp. 1–10 | 10 | **abandoned after ~50 min** | — | — | — | — |
| Bellettini p. 3 | 1 | **161.5** | 0.0062 | 1,819 | 2.22 | 2 |
| Bellettini p. 4 | 1 | **235.4** | 0.0042 | 1,958 | 2.70 | 3 |

**That is 120–190× slower than the same pipeline without it** (0.79 pages/s on the same
paper). The 10-page run was killed at ~50 minutes without finishing; its wall clock is not
reported as a rate because another session's 9-worker test campaign started 7 minutes into it
(§7). The two single-page runs are clean of that campaign but were measured against a 46%
ambient load, and they are one observation each. **Formula enrichment cannot be switched on
for the corpus at these rates** — 4,655 pages at 0.005 pages/s is ~11 days — so stage 4 needs
either a GPU or a formula-region-only pass (enrich the regions the layout model already
found, not every page), neither of which is measured here.

### 6.1 The LaTeX, recorded for a referee

Five equations, verbatim from `equations()`. **My reading of their correctness is the
builder's own and is therefore UNCONFIRMED** (CLAUDE.md §3.4c: the proposer does not score
its own proposal); a referee should compare each against the rendered page.

| # | page | Docling's LaTeX | builder's reading — UNCONFIRMED |
|---|--:|---|---|
| 1 | 3 | `u ( t , x ) = ( 1 - \lambda _ { C } t ) ^ { + } \chi _ { C } ( x ) , \quad \lambda _ { C } \colon = \frac { P ( C ) } { \| C \| }` | matches the page |
| 2 | 3 (eq. 5) | `\text {ess sup } \kappa _ { \partial C } ( p ) \leqslant \lambda _ { C } ,` | **subscript lost** — the page reads `ess sup` *with `p ∈ ∂C` under it* |
| 3 | 4 | `\min \left \{ P ( E ) \colon \bigcup _ { j = 1 } ^ { k } \, C _ { i _ { j } } \subseteq E \subseteq \mathbb { R } ^ { 2 } \rangle \ \bigcup _ { j = k + 1 } ^ { m } \, C _ { i _ { j } } \right \} ,` | **wrong symbol** — the page's set difference `ℝ² \ ⋃…` came back as `\rangle` |
| 4 | 4 (eq. 6) | `P ( E _ { i _ { 1 } , \dots , i _ { k } } ) \geqslant \sum _ { j = 1 } ^ { k } P ( C _ { i _ { j } } ) .` | matches the page |
| 5 | 4 (eq. 7) | `\min _ { u \in L ^ { 2 } ( \mathbb { R } ^ { 2 } ) \cap \text {BV} ( \mathbb { R } ^ { 2 } ) } \left \{ \int _ { \mathbb { R } ^ { 2 } } \left \| D u \right \| + \frac { 1 } { 2 \lambda } \, \int _ { \mathbb { R } ^ { 2 } } ( u - f ) ^ { 2 } \, d x \right \} ,` | matches the page |

(`\|…\|` above is this report's escaping of the single `|` characters in the LaTeX, so the
Markdown table does not split; the recorded strings hold single bars.)

Three of five are right; two carry a substantive error each, and both errors are silent — the
LaTeX parses, it just says something else. **Any use of these strings as content must treat
them as a candidate, not a fact.** Without enrichment the same regions are still located and
labelled `formula`; only their text is the native layer's mangled characters, which on this
paper includes `P ð C Þ` where the page reads `P(C)` — the PDF's ligature-encoded parentheses.

---

## 7. What blocks a referee

1. **The venv is not reproducible from the pin alone until it is rebuilt from it.**
   `requirements-litkb-extract.txt` pins docling 2.127.0 and names the transitive versions
   that were installed today, but the file was written from a `pip install docling`, not tested
   by re-creating the environment from the file. A referee should rebuild from the pin and
   check the versions match before trusting the timings.
2. **Model weights are not vendored.** The first run downloads 1.1 GB from Hugging Face
   (unauthenticated; the warning about symlinks on Windows is benign). A referee without
   network access cannot reproduce anything here.
3. **The OCR engine is rapidocr on its torch backend** (§3.1, measured from docling's own log
   line). The §3.1 batch itself ran under `auto`, so its metrics row records `ocr_engine:
   auto`; the identity comes from the separate pinned run, not from that row.
4. **The book was measured on its first 100 pages**, not all 688.
5. **GPU was not attempted** (§3.2): it requires replacing torch in the venv.
6. **The cpu-t4 and cpu-t8 batches ran back to back on a laptop that was also running Kam's
   browsers and two Claude Code sessions.** The load columns record what that was; nothing was
   closed to make the numbers look better. A second session's 9-worker test campaign began at
   **08:14 UTC**, after those batches and the OCR batch finished (07:45–08:00), and overlapped
   the abandoned 10-page formula run; the single-page formula rows (08:59, 09:03) ran after it
   at a 46% ambient load. Row-level `started_at` is in the CSV so a referee can check this
   rather than take it.
7. **Nothing here has touched Postgres.** `extraction_runs.metrics` is where these rows belong
   (design §4.3); P4's job table is not built, so the metrics live in the CSV and in
   `_tmp\litkb_docling\metrics_*.jsonl`. The same gap the GROBID referee recorded.
8. **`ocr_score` / `table_score` can be `NaN`** in the recorded confidence object (Anderson
   has no table). `json.dumps` writes a bare `NaN`, which Python reads back but strict JSON
   parsers reject — the ingest that lands these rows in `extraction_runs.metrics` must
   normalise it.
9. **The equation readings in §6.1 are the builder's own** and, per CLAUDE.md §3.4c, do not
   count until a referee checks them against the rendered pages.

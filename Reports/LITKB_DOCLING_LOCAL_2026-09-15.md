# Docling stage 3, local — build and measurement (litkb P4, gate 2)

**Date:** 2026-09-15 · **Branch:** `work/20260915-docling-local` (worktree
`D:\edmonds-pipeline\treedata-docling`) · **Contract:** CLAUDE.md §3.4b, §3.4c
**Design:** `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §7 stage 3, §7.1, §12, §14 P4
**Companion:** `Reports/LITKB_GROBID_LOCAL_2026-09-14.md` and its referee report — same five
papers, same method, so the two stages' numbers can be put side by side.

Every number below was measured on this laptop on 2026-09-15 by
`qc/instruments/litkb_docling_bench.py` and, for the equation-density census of §8.1,
`qc/instruments/litkb_equation_density.py`; every row they produced is in
`Reports/litkb_docling_throughput_2026-09-15.csv` and
`Reports/litkb_equation_density_2026-09-15.csv`. Nothing here is copied from the vendor's
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
| pin files | `Scripts/requirements-litkb-extract.txt` (full `pip freeze`, defect D1) and `Scripts/requirements-litkb-extract-cuda.txt` (the CUDA trial venv, §8.3) |

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
`AcceleratorDevice.CUDA` has nothing to bind to. Docling itself supports CUDA; **this
installation does not have it** — that is a property of the wheel, not of the tool. The driver
is present (581.42, CUDA 13.0) with 3.1 GB of the 4 GB free.

**Defect D4, closed: the wheel that works, named.** `docling` pins no torch; `docling-ibm-models`
wants `torch<3.0.0,>=2.2.2`; and **`torchvision 0.29.0` requires `torch==2.14.0` exactly**, so
the CUDA build must be 2.14.0 and not a newer one. Of PyTorch's channels only **cu130** carries
a cp312 win_amd64 pair at that version (`cu126` has torch but not the matching torchvision;
cu128 and cu129 have neither). The card is a **Quadro T2000, sm_75 (Turing)**, which CUDA 13.x
still supports. So the replacement is `torch==2.14.0+cu130` with `torchvision==0.29.0+cu130`.
**The real cost is not availability: swapping it re-pins the requirements file and invalidates
every number in §3.**

**That is why the trial got its own venv rather than an upgrade in place.** The CPU venv is
untouched; `D:\edmonds-pipeline\venv-docling-cuda` is a separate environment differing from it
by exactly two lines. The measurement is in "Decision A implemented" below.

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

**OCR quality, corrected on the referee's measurement (defect D2, closed).** This section used
to read "good but not clean" and list three per-character typos — `usualiy` for *usually*,
`sncreases` for *increases*, `x²-tests` where the page reads `χ²-tests`, page 2's folio `90`
read as `06`. Those are real, and they are the mild half of the story. The independent referee
transcribed the first 100 words of the Summary off the page image before reading any OCR
output and diffed it (`LITKB_DOCLING_LOCAL_REFEREE_2026-09-15.md` §2.3):

| | |
|---|--:|
| gold words compared | 94 (the 100th fell mid-token) |
| gold words wrong or missing | **13** |
| **word error rate** | **13.8%** |
| of which, inside ONE contiguous dropout | **12** |
| outside that dropout | 1 (`χ²` → `x²`) |

**The dropout is the finding, not the typos.** Where the page reads

> *…of a first order chain **are constant, (b) that in case the transition probabilities are
> constant, they are** specified numbers…*

the OCR'd block reads

> `…of a first order chain aorae nt Gtnt e sn nt  ea  tt ( Gtt are specified numbers…`

**Twelve consecutive words of the abstract are replaced by ten tokens of gibberish that is
still word-shaped**, inside a block that otherwise reads cleanly, with no marker and no
block-level confidence to drop (there is none), on a page whose `mean_grade` is `excellent`.
It is **deterministic**: the referee's re-run in a separately rebuilt venv produced the
identical `aorae nt Gtnt e sn nt  ea  tt ( Gtt`, so it is a property of rapidocr+torch on this
page, not a sampling artefact.

**The downstream rule this changes.** Per-character slips are survivable — a fuzzy quote
matcher absorbs `usualiy`. Silent content loss is not, and it breaks the gate in the more
dangerous direction: an exact-match quote gate over this text will reject true quotes, **and a
fuzzy one can match a plausible-looking string the page never said.** A verified-quote rule
over OCR'd sources therefore cannot be a text rule alone; it needs the page image or a second
extractor to agree.

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
  body block, and one is ≥ 1, so it passes exactly the way GROBID's 200 did.

  **Defect D3, closed: that one block is not the JSTOR boilerplate.** This report said it
  was. The referee read it: it is a single character, `®`, from the JSTOR logo
  (`page 1, kind=text, layer=body, text='®'`). The correction matters in one direction and
  the referee names it — a trivial **body-character floor** (say ≥ 200 characters of body
  text) *would* catch this file, which the old "one is ≥ 1, so it passes" framing implied
  nothing cheap could. A character floor is worth having and is nearly free.

  It is still not sufficient, which is why the conclusion does not move: a scan whose text
  layer holds a real paragraph of front matter clears any character floor. What closes the
  class is stage 0's per-page text-layer census (design §7 stage 0), and the referee
  prototyped it in five lines and **showed it firing on this file** — 22 pages, **1** with any
  text, **166** characters, **7.5** characters per page, so both a text-page-fraction floor
  (0.045 < 0.5) and a characters-per-page floor (7.5 < 100) trip. Stage 0 must record all four
  and refuse, or force OCR. **Open, and it belongs to stage 0, not here.**
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
found, not every page). **Both are now measured — see §8.**

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

1. ~~**The venv is not reproducible from the pin alone.**~~ **Defect D1, CLOSED 2026-09-15.**
   The referee rebuilt from the old file the same day and `docling-core` came back **2.96.1**
   against the measured **2.96.0** — a comment is not a constraint. `requirements-litkb-extract.txt`
   is now a full `pip freeze` of the venv the numbers were measured in (106 pins), and the
   CUDA trial venv has its own, `requirements-litkb-extract-cuda.txt`. The one pin that is not
   self-describing is torch: `pip freeze` prints `torch==2.14.0` while `torch.__version__` is
   `2.14.0+cpu`, because the local label is on the dunder and not in the freeze. On win_amd64
   the PyPI wheel for 2.14.0 *is* the CPU build, so the file reproduces the CPU venv; the CUDA
   file pins `+cu130` explicitly, since the local label is the only thing distinguishing it,
   and PyPI does not serve it.
2. **Model weights are not vendored.** The first run downloads 1.1 GB from Hugging Face
   (unauthenticated; the warning about symlinks on Windows is benign). A referee without
   network access cannot reproduce anything here.
3. **The OCR engine is rapidocr on its torch backend** (§3.1, measured from docling's own log
   line). The §3.1 batch itself ran under `auto`, so its metrics row records `ocr_engine:
   auto`; the identity comes from the separate pinned run, not from that row.
4. ~~**The book was measured on its first 100 pages**, not all 688.~~ **Defect D3b, CLOSED:**
   stale since commit `afc052c`, which added the full 688-page row to §3. The book is measured
   in full.
5. ~~**GPU was not attempted**~~ **CLOSED 2026-09-15** — see "Decision A implemented" below.
   The trial was run on the T2000 and the numbers are there. The default backend did **not**
   change: `VENV_PYTHON` still resolves to the CPU venv and `--device cpu` is still the
   default.
6. **N1 — `litkb_test_w*` has no code path on this branch, and that is a note about the
   referee brief, not a defect here.** Checked rather than inferred: `pipeline/litkb/db/connect.py`
   sets `DB_TEST = "litkb_test"` with no environment override; nothing in this worktree
   mentions `litkb_test_w*`; and `main` does not carry the litkb tree at all. The server does
   hold `litkb_test_w1 … litkb_test_w9`, created by the 9-worker mutation harness that runs
   **outside** this worktree. Sharing one `litkb_test` under `qc/conftest.py`'s advisory lock
   is this branch's deliberate design, so parallel suites serialise. The residual risk is
   narrow and real: `migrate.reset()` still destroys whatever is in `litkb_test` when it takes
   the lock, so a session holding state there loses it. Whether per-worktree databases are
   wanted is Kam's call, not this branch's. **Consequence for this session:** like the
   referee, every ladder run here used `LITKB_PGPORT=1`, so 216 litkb Postgres tests were
   skipped and are **unexercised**. A merge reviewer must run them against a database they are
   willing to have reset.
7. **The cpu-t4 and cpu-t8 batches ran back to back on a laptop that was also running Kam's
   browsers and two Claude Code sessions.** The load columns record what that was; nothing was
   closed to make the numbers look better. A second session's 9-worker test campaign began at
   **08:14 UTC**, after those batches and the OCR batch finished (07:45–08:00), and overlapped
   the abandoned 10-page formula run; the single-page formula rows (08:59, 09:03) ran after it
   at a 46% ambient load. Row-level `started_at` is in the CSV so a referee can check this
   rather than take it.
8. **Nothing here has touched Postgres.** `extraction_runs.metrics` is where these rows belong
   (design §4.3); P4's job table is not built, so the metrics live in the CSV and in
   `_tmp\litkb_docling\metrics_*.jsonl`. The same gap the GROBID referee recorded.
9. **`ocr_score` / `table_score` can be `NaN`** in the recorded confidence object (Anderson
   has no table). `json.dumps` writes a bare `NaN`, which Python reads back but strict JSON
   parsers reject — the ingest that lands these rows in `extraction_runs.metrics` must
   normalise it.
10. **The equation readings in §6.1 are the builder's own** and, per CLAUDE.md §3.4c, do not
   count until a referee checks them against the rendered pages.

---

## 8. Decision A implemented (2026-09-15)

Kam's decision A on the referee's §6: **formula enrichment only on equation-dense pages, and
a measured trial of the CUDA build on the T2000 before any adoption.** Both are below. The
default backend did **not** change — `VENV_PYTHON` still resolves to the CPU venv,
`--device cpu` is still the default, and the CUDA venv is a measurement environment that
nothing in the code points at.

### 8.1 The equation-density gate

**Why a gate at all.** Enrichment is 160x layout, and it is priced per formula REGION, not per
page (CodeFormulaV2 is autoregressive and runs once per region). Running it over the whole
corpus is not a thing anyone will do; running it over the pages that have equations might be.

**The formula**, implemented as `litkb.extract.docling.equation_density(page_text,
page_chars)` and documented in full in that function's docstring. Every non-space character of
a page is attributed AT MOST ONCE, so the result is a genuine fraction:

* a line ending in an equation number — `(3)`, `(12a)`, capped at **three digits** so that
  `(2003)` closing a reference line is a year and not an equation — contributes all its
  characters;
* a non-empty line of **12 characters or fewer** contributes all its characters: it is a
  display equation the extractor has broken into one line per run;
* on every other line, each math-class character contributes itself (Unicode `Sm`, Greek,
  letterlike and math-alphanumeric blocks, sub/superscript markers, and an explicit operator
  set), plus two per digit-welded-to-letter pair.

**Why the two line terms are not decoration — the finding that changed the design.** A pure
math-character ratio does not work on this corpus. Bellettini 2002, the equation paper, uses a
Type-1 math font with no usable ToUnicode map: `=` extracts as the vulgar-fraction glyph,
`(x)` as `ðxÞ`, sigma as `X`, chi as `w`. Its math-CHARACTER ratio is **0.005–0.014, the same
band as Benedek's prose**. What survives a broken encoding is the LAYOUT of display maths, and
the line terms are what read it. A gate built only on the usual operator glyphs would have
scored the equation paper as prose.

**The census.** `qc/instruments/litkb_equation_density.py` over `ASPP`, `Labeling`,
`Validation` and `other` (`_litkb_staging` and `_quarantine` excluded — staging duplicates
files already counted, quarantine holds failed ingests): **219 PDFs, 4,655 pages, 0 unreadable,
86 pages with no text layer** (85 of them inside the 5 image-only scans). Per-page rows:
`Reports/litkb_equation_density_2026-09-15.csv`.

| density bin | pages | % | · | density bin | pages | % |
|---|--:|--:|---|---|--:|--:|
| [0.00, 0.01) | 1,552 | 33.34 | | [0.10, 0.12) | 149 | 3.20 |
| [0.01, 0.02) | 685 | 14.72 | | [0.12, 0.15) | 187 | 4.02 |
| [0.02, 0.03) | 378 | 8.12 | | [0.15, 0.20) | 209 | 4.49 |
| [0.03, 0.04) | 246 | 5.28 | | [0.20, 0.30) | 202 | 4.34 |
| [0.04, 0.05) | 222 | 4.77 | | [0.30, 0.50) | 78 | 1.68 |
| [0.05, 0.06) | 204 | 4.38 | | [0.50, 0.75) | 14 | 0.30 |
| [0.06, 0.08) | 285 | 6.12 | | [0.75, 1.01) | 4 | 0.09 |
| [0.08, 0.10) | 240 | 5.16 | | | | |

**There is no antimode, and that is a result rather than a failure to find one.** The
distribution decays monotonically. Academic mathematics is a continuum — a methods page with
two inline symbols shades into a page of display equations — so the cut cannot be read off a
valley and has to be argued for on other grounds.

**The other grounds: an INDEPENDENT target.** Docling's own layout pass labels `formula`
regions in the cheap pass, from page geometry, knowing nothing about the text layer this
function reads. That is a target the density function did not produce about itself
(CLAUDE.md §3.4c). Scored per page over the four gate papers that have a text layer —
**177 pages, 655 formula regions**; Anderson 1957 is excluded because it is an image-only scan
whose density is 0 everywhere and which neither side can see:

| cut | recall | precision | corpus pages selected |
|--:|--:|--:|--:|
| 0.01 | 0.978 | 0.918 | 3,103 (66.7%) |
| 0.02 | 0.949 | 0.978 | 2,415 (51.9%) |
| 0.03 | 0.913 | 0.977 | 2,038 (43.8%) |
| 0.04 | 0.877 | 0.976 | 1,794 (38.5%) |
| **0.05** | **0.804** | **0.974** | **1,571 (33.8%)** |
| 0.06 | 0.732 | 0.990 | 1,368 (29.4%) |
| 0.08 | 0.623 | 1.000 | 1,083 (23.3%) |
| 0.10 | 0.522 | 1.000 | 842 (18.1%) |
| 0.12 | 0.435 | 1.000 | 694 (14.9%) |
| 0.20 | 0.181 | 1.000 | 298 (6.4%) |

**`EQUATION_DENSITY_CUT = 0.05`** — the largest cut holding recall at or above 0.80 and
precision at or above 0.95. **The rule was fixed after seeing this curve, not before**, which
is why the whole curve is printed: the choice is a policy decision about hours, and a reader
who wants a different point on it can have one by editing a constant. F1 against the layout
labels actually peaks at 0.02, but 0.02 selects 52% of the corpus and is barely a gate.

**What the cut buys, measured rather than assumed.** It selects 33.75% of pages but captures
**588 of 655 formula regions = 89.8%** — better than its 80.4% *page* recall, because the
pages it keeps are the region-dense ones. Both gold formula pages the referee scored by hand
clear it (Bellettini p3 = 0.0501, p4 = 0.0869); Benedek 2015's prose pages max out at 0.016.

**The stated holes.** A page with no text layer scores 0.0 and is never selected, so an
equation on a scan is invisible here until OCR has run — that is stage 0's text-layer census
to catch (§5), not this function's job. And the 10.2% of regions below the cut are lost
silently unless a caller raises the cut.

**Tests and kills** (`qc/test_litkb_docling.py`, **37 passed / 3 skipped**, up from 25): gold
pages above and prose below; a no-text page returns 0.0 without dividing by zero; the
broken-math-font page scores as maths; a reference year at a line end does not; and the cut
meets its stated recall and precision. Mutating the constant fires: **`EQUATION_DENSITY_CUT =
0.0` gives 2 failed** (precision collapses — prose is selected), **`= 1.0` gives 3 failed**
(recall collapses — nothing is). A gate that has never been shown to fire is not a gate.

### 8.2 `formulas="auto"|"all"|"off"`, and why it has to be two passes

`do_formula_enrichment` is a CONVERTER-wide option. Read at
the `is_processable` method of `docling/models/stages/code_formula/code_formula_model.py`
in the installed package, it filters on the
item's LABEL and on the option and **never on the page** — there is no per-page switch to set.
So `auto` is adapter-side: one cheap pass over the whole file, then one enrichment pass per
contiguous run of dense pages, merged by `merge_formula_latex` on `(page, bbox rounded to
1 pt)` rather than by index, since the enrichment pass numbers its own items.

**The whole path was run end to end, not just its helper.** `extract(..., formulas="auto",
pages=[3,4])` against the CUDA venv: `formula_mode="auto"`, `formula_density_cut=0.05`,
`formula_pages=[3, 4]`, **`formula_patched=5`, `formula_missing=0`**, `formula_seconds=72.1`,
`status="ok"`, two metrics rows written (base + enrichment), and the rewritten output JSON
holds all five LaTeX strings. (The 72.1 s is the two-pass total for a cold converter build per
pass, against the 42.5 s of the single enrichment batch in §8.3 — `auto` pays for a second
process, which is the price of there being no per-page switch.)

**Two assumptions underneath it that pass measurement rather than review.** Run against the real base and
enrichment documents for Bellettini pp. 3–4: a page-RANGE conversion numbers its pages
**absolutely** (`prov.page_no == 3`, not 1), and the two passes' boxes agree within the 1 pt
the key rounds to. Result: **5 patched, 0 missing**, recovering exactly the five LaTeX strings
the referee scored. Had page numbering been relative, every `auto` run would have raised —
which is what the fail-closed rule is for, and it is now a fixture test.

**Enrichment fails CLOSED — and this kill is UNVALIDATED on real data.** Docling does not
re-raise per element: a formula region the model could not decode keeps the text the native
layer gave it, and the conversion still reports SUCCESS. (On this paper the base pass leaves formula text **empty**, so the mojibake would come
from a caller's own fallback rather than from docling — but the failure shape is the same.)
`merge_formula_latex` reports every region on an enriched page whose LaTeX did not arrive, and
`extract` turns a non-empty list into `FormulaEnrichmentFailed` with `status="failed"` rather
than recording a half-enriched run. It is tested on three shapes of that failure — empty LaTeX,
unchanged text, and an enrichment pass that returned no formula item at all — but **all three
are SYNTHETIC documents, so the kill is UNVALIDATED** in the sense CLAUDE.md §3.4c means:
CodeFormula never actually ran out of memory here (it fit, §8.3), so the gate has not been
shown to fire on the real failure it exists for. Synthetic validation tests the code, not the
claim.

### 8.3 The CUDA trial on the T2000

**The environment.** `D:\edmonds-pipeline\venv-docling-cuda`, pinned in
`requirements-litkb-extract-cuda.txt`. It is the CPU freeze with **exactly two lines changed** —
`torch 2.14.0 -> 2.14.0+cu130`, `torchvision 0.29.0 -> 0.29.0+cu130`, diffed to confirm; every
other package matches to the patch version. That is what makes the comparison below
attributable to the wheel and to nothing else. `torch.cuda.is_available()` is **True** and the
device name is **`Quadro T2000`**. The CPU venv was not touched. Model weights are shared
through the Hugging Face cache, so building this venv downloaded no weights.

**Ambient load, recorded before each batch** (probed with `psutil` from the extraction venv;
the CSV's `load_python_procs` column is empty because the project environment has no psutil):

| batch | system CPU over 5 s | python processes | GPU memory in use |
|---|--:|--:|--:|
| gpu-t4 (layout + tables) | 21.4% | 17 | 901 MiB |
| gpu-ocr | 23.9% | 19 | 901 MiB |
| gpu-formula | 26.5% | 20 | 901 MiB |

Other agents' harnesses were on the machine throughout; nothing was closed to improve a number.

**CPU vs GPU — same five papers, same page ranges, `num_threads=4`:**

| run | pages | CPU s | CPU p/s | GPU s | GPU p/s | speed-up | CPU peak RSS | GPU peak RSS | GPU VRAM over baseline |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Benedek 2015 | 16 | 33.29 | 0.481 | **6.19** | **2.585** | **5.4x** | 1,872 MB | 2,153 MB | +1,482 MiB |
| Alwan 1988 | 10 | 16.64 | 0.601 | **4.88** | **2.048** | **3.4x** | 2,007 MB | 2,201 MB | +1,482 MiB |
| Anderson 1957 | 22 | 29.68 | 0.741 | **6.50** | **3.386** | **4.6x** | 2,056 MB | 2,056 MB | +1,482 MiB |
| Bellettini 2002 | 51 | 64.62 | 0.789 | **8.75** | **5.830** | **7.4x** | 2,036 MB | 2,358 MB | +1,482 MiB |
| Schneider 2008 (pp. 1–100) | 100 | 135.69 | 0.737 | **20.26** | **4.936** | **6.7x** | 2,641 MB | 2,882 MB | +1,482 MiB |
| **layout aggregate** | **199** | **279.9** | **0.711** | **46.58** | **4.272** | **6.0x** | 2,641 MB | 2,882 MB | **+1,482 MiB** |
| OCR, Anderson 1957 | 22 | 234.08 | 0.094 | **35.35** | **0.622** | **6.6x** | 2,456 MB | 2,506 MB | **+1,662 MiB** |
| Formula, Bellettini pp. 3–4 (5 regions) | 2 | 396.91 | 0.005 | **42.52** | **0.047** | **9.3x** | 1,958 MB | 3,236 MB | **+3,017 MiB** |

Speed-ups run 3.4–9.3x, far outside the referee's ±20% reproduction band, so they are not
noise. **The body-block counts are identical to the CPU run on all five papers** (377 / 157 /
1 / 819 / 1,011), and the OCR run returns the same 179 — the GPU produces the same document,
faster, which is the corroboration that matters more than the rate does.

**CodeFormula did NOT run out of memory, and the margin is the finding.** Peak device memory
during the formula batch was **3,918 of 4,096 MiB**, leaving **178 MiB** on a card that is also
driving the display. It fit on this input: 2 pages, 5 regions, short decodes. A longer decode,
a denser page, or Kam opening something that wants VRAM would push it over. **UNDETERMINED
whether formula enrichment on this card is safe at corpus scale** — it is measured on two
pages. Layout + tables at +1,482 MiB and OCR at +1,662 MiB have real headroom and are not at
risk. The fail-closed path in §8.2 is what stands between an OOM and a silently empty LaTeX
column, and it is the reason that path exists.

**The LaTeX is byte-identical between CPU and GPU.** All five strings from the GPU run match
the CPU strings character for character — including both of the errors the referee confirmed
(the lost subscript under `ess sup`, and the set difference read as `\rangle`). The GPU changes
the rate and nothing else. It does not fix the two wrong equations and it would be a mistake
to hope it might.

Per-process VRAM could not be attributed: under WDDM,
`nvidia-smi --query-compute-apps=used_memory` returns `[N/A]` for every process on this
machine (checked — 10 processes, all `[N/A]`). The numbers above are device-wide peak minus a
baseline sampled immediately before the batch, at 1 Hz, and the baseline is printed beside
every peak so a reader can judge how much of it might be somebody else's.

### 8.4 Corpus projection — from measured rates, stated as projections

Not a measurement. Each line is a measured rate multiplied by a counted page or region total,
and it assumes the rest of the corpus behaves like the five gate papers.

| stage | work | CPU | GPU |
|---|---|--:|--:|
| layout + tables | 4,655 pages @ 0.711 / 4.272 p/s | **1.8 h** | **0.3 h** |
| OCR | 85 image-only pages @ 0.094 / 0.622 p/s | **0.25 h** | **0.04 h** |
| formula, cut 0.05 | ~8,103 regions @ 79.4 / 8.5 s per region | **179 h** | **19 h** |
| formula, every page | 4,655 pages, all regions | ~530 h (22 days) | ~57 h |

**Formula is projected per REGION, not per page, and that correction matters.** CodeFormula
runs once per formula region; Bellettini pp. 3–4 carry 2.5 regions per page while the gate
papers' dense pages average **5.16**, so a per-page projection off those two pages would have
**under**estimated the corpus by roughly 2x. The region count is itself a projection: 1,571
corpus pages above the cut times 5.16 regions per dense page is about 8,103. It rests on the
four gate papers and on nothing else.

**What the two halves say together.** Layout and OCR are already cheap on CPU and trivially
cheap on GPU — the T2000 is nice to have, not needed, for those. Formula is the entire cost,
and the gate and the GPU attack it from different directions: the gate takes 530 h to 179 h at
a measured cost of 10.2% of regions, and the GPU takes 179 h to **19 h** at no cost in output
at all. Together they turn "not possible" into an overnight job. But 19 h of a 4 GB card
running 178 MiB from its ceiling is a plan that depends on the fail-closed path working, and
nothing about the default has been changed on the strength of these numbers.

# litkb P4 stage 0 — Inventory: hashes, page frames, text-layer probe, scan routing

Branch `work/20260915-inventory-stage0`, worktree `D:\edmonds-pipeline\treedata-inventory`.
Code: `Scripts/pipeline/litkb/extract/inventory.py`. Tests: `Scripts/qc/test_litkb_inventory.py`.
Mutation harness: `Scripts/qc/instruments/litkb_inventory_mutations.py`.
Measured text: `phase4/qc/litkb_inventory.csv` (tracked, one row per file).

**Status of this evidence (CLAUDE.md §3.4c).** Every number below was produced by the author of
the code. The mutation table shows the gates CAN fail. **No independent referee has re-run
anything here.** Two clauses are offered specifically for a referee to re-inspect: the
twelve-file hand-inspection table (§4) and the contradiction with an already-committed report
(§5).

---

## 1. What stage 0 measures, and what it decides

Per file: `sha256`, `md5`, byte size, page count, the PDF `/Info` dictionary (NUL-stripped
through `litkb.textnorm.jsonb_safe` — Bell 1977's Acrobat Capture producer string carries NULs
and `jsonb` refuses `\u0000`), producer, creator, PDF version, the encryption flag, and the
routing decision.

Per page: mediabox, cropbox, rotation, the §7.1 shift `dx`/`dy`, non-whitespace characters in
the text layer, image count, image area ÷ cropbox area, and a scan class.

**Output.** One JSONL record per file at `phase4/qc/litkb_inventory.jsonl` (1.2 MB,
regenerable in under a minute, therefore not tracked), plus the tracked summary CSV. The JSONL
is the stage-0 artifact of design §7: **P5's ingest is what persists it** into the `files` and
`pages` tables. Nothing here touches the database, and nothing writes inside `Literture\` —
`test_the_corpus_is_never_written_to` hashes the input directory before and after a run.

Run key (§12.4): `(sha256, stage=0, tool="pypdfium2@5.13.0", params_hash)`. `params_hash` is a
digest of every threshold, so moving one makes a new key rather than silently mixing two
definitions of "scan".

---

## 2. The thresholds, and the census they were read off

A throwaway probe measured every page of the corpus **before** any threshold was written and
before the gate table existed. The thresholds were then read off that distribution:

| constant | value | what the census showed |
|---|--:|---|
| `CHARS_TRACE` | 100 | The character axis is bimodal only at zero: **89 pages carry no text at all, exactly one carries 25, and the next image-covered page carries 111.** 100 sits in that gap. |
| `CHARS_BODY` | 400 | Among image-covered pages, **594 are above 400** (whole scans re-covered by a complete OCR layer — Lahiri 2003, Besag 1974, Singer 1976) and only **14 fall in 100..400**. |
| `IMAGE_COVER` | 0.25 | Every page in the corpus with no text at all has image coverage **≥ 0.276**; the floor is Ogata 1998, whose scan is cut into 18 image strips per page. |
| `COVER_MAX_CHARS` | 200 | Not invented here: `Reports/LITKB_EDGE_PRE1990_2026-09-14.md` P-2, "page 1 has under 200 characters". |
| `SCAN_FILE_FRAC` | 0.5 | Design choice: at or above this share of OCR-needing pages a file is priced as a scan. |
| `COVER_MIN_FIELDS` | 2 | See §5: cover pages carry 4 bibliographic field markers, cover stamps carry 0. The separation is total across the corpus. |

**Page classes are descriptive; routing is the decision.**

```
image_frac >= IMAGE_COVER and chars <  CHARS_TRACE   -> image-only
image_frac >= IMAGE_COVER and chars <  CHARS_BODY    -> partial
chars == 0 and image_frac <  IMAGE_COVER             -> empty
otherwise                                            -> text
```

`text` means "the native layer is the best source available for this page", not "this page is
full of text": a 58-character chapter opener with no raster is `text` because OCR cannot
improve it, and a fully OCR-covered scan page is `text` because its layer is already complete.
`empty` (no text, no raster) has **zero instances** in this corpus; the class exists so a blank
page is never handed to an OCR engine that would return nothing.

Routing precedence is fixed and single-valued: `unreadable > scan > mixed > cover-sheet >
native`. Because the IMS-stamped files are both scans and boilerplate-fronted, `cover_sheet`,
`cover_stamp` and `title_page` are emitted as their own fields on every record whatever the
route says. Without that split the scan count and the cover-sheet count contradict each other.

---

## 3. The corpus, measured

`PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 -m litkb.extract.inventory` over every PDF under
`D:\edmonds-pipeline\Literture` including `_litkb_staging` and `_quarantine`, read-only.

| | all | excluding `_quarantine` |
|---|--:|--:|
| files | **241** | 224 |
| pages | **5,038** | **4,712** |
| rotated pages | 7 | **7** |
| pages with cropbox ≠ mediabox | 296 in 20 files | **271 in 19 files** |
| rotated AND cropped | 1 | **1** |
| encrypted files | 3 | 3 |
| unreadable files | **0** | 0 |
| pages needing OCR | 114 | 111 |

**Routing:** `native` 213, `mixed` 14, `cover-sheet` 8, `scan` 6, `unreadable` 0.
(Excluding `_quarantine`: native 198, mixed 14, cover-sheet 7, scan 5.)

**The total page count is 5,038, or 4,712 for the active corpus.** The design's §12.2 figure of
**4,655** is neither: it came from `pdfinfo` over 219 active PDFs, a third corpus definition.
Quote a page count with its corpus definition or not at all — the same warning referee 2 gave
about the cropped-page count.

**Frame census reproduced.** 4,712 pages / 7 rotated / 271 cropped in 19 files, and
`Hall_1985_resampling-coverage-pattern.pdf` p12 as the **only** page that is both rotated and
cropped, are the five numbers `Reports/LITKB_GROBID_LOCAL_REFEREE2_2026-09-15.md` §4 measured
with GROBID's own `page_frames`. This is an independent reader reaching the same numbers, and
`test_the_frame_reader_reproduces_the_committed_corpus_census` pins them. `inventory.page_frames`
is the ONE frame reader; `extract/grobid.py` on the other branch should import it at merge
rather than keep a second copy (§3.3).

**Rotated pages** (pdfium quarter turns, not degrees): Burnicki 2007 p16 p17 (1), Chrisman 1982
p8 (3), Guo 2019 p6 (1), **Hall 1985 p12 (2)**, Kalinicheva 2025 p20 (1), Verburg 2004 p10 (1).

**Encrypted, and readable:** Hughes 1999, Israel 2001, Steiner 2000 — owner-password only. They
open with no password and extract normally, so they route `native`. Encryption is recorded as a
fact and is never a reason to route `unreadable`; only a document that refuses to open is.

**Duplicates by sha256** — 6 groups, 15 files:

| sha256 (16) | files |
|---|---|
| `781b75f8a3dc53bb` | Bellettini_2002_total-variation-flow-garbled, …garbled.stray-recovered, …total-variation-flow |
| `753a94fcb1ec2ff6` | Brown_2022_aerial-animal-detection-spatial-resolution, Brown_2022_retry2 |
| `bb14fdbc0a1052b1` | Chen_2024_coarse-to-fine…, Chen_2024_retry2, **Song_2026_monocular-height…, Song_2026_retry2** |
| `b0843bfb6cff6c04` | Mobsite_2026_land-cover-semantic-segmentation, Mobsite_2026_retry2 |
| `d36c509398c926c5` | Page_1954_continuous-inspection-schemes, …`__content-mismatch__`… (`_quarantine`) |
| `3a65f9825495cca1` | **Stehman_2022_incorporating-interpreter-variability, Xing_2024_interpenetrating-subsampling-interpreter** |

Two of these are wrong-content, not duplicates of an intended copy: one sha256 is filed under
**both Chen 2024 and Song 2026**, and another under **both Stehman 2022 and Xing 2024**. Two
distinct works cannot be the same bytes. Stage 0 only reports it; it is an admission question
(the design's binding checks), and it is flagged here so it is not discovered later as a
mystery in the block counts.

---

## 4. The gate: classification against hand inspection, twelve files

Pages were rendered to PNG with pypdfium2 and **looked at**, and what was seen was written down
as the two primitives the page classes are defined on — is there a raster over the page, and
does the native text layer carry the page's words. That is not a re-reading of the classifier's
own numbers. A referee can re-inspect by rendering the same pages.

| file | page | what the render shows | class | route |
|---|--:|---|---|---|
| Ogata_1998_space-time-point-process-models | 1 | scan of the article's **title page** — title, byline, abstract, start of §1 — no selectable text | image-only | **scan** |
| " | 12 | scan of a body page, no selectable text | image-only | |
| Anderson_1957_statistical-inference-about-markov | 1 | scanned article opening; only the IMS strip is native | partial | **scan** |
| " | 2 | scanned body page, nothing native | image-only | |
| Kingman_1962_imbedding-problem-finite-markov-chains | 1 | scanned page **with a complete text layer** (OCR-damaged byline) | text | **native** |
| Bell_1977_markov-analysis-land-use-change | 1 | article first page (title, byline, abstract, two columns), Acrobat Capture: a full-page image with a complete text layer over it | text | **native** |
| " | 3 | body page with a table and equations, same full layer | text | |
| Schneider_2008_stochastic-integral-geometry (688 pp) | 1 | Springer cover, raster only | image-only | **mixed** |
| " | 4 | born-digital **half-title page**: two author names, the title, the Springer imprint — and that is all the text there is | text | |
| Hall_1985_resampling-coverage-pattern | 12 | body text, rotation 2, cropbox ≠ mediabox, layer fine | text | **native** |
| Guo_2019_city-wide-canopy-cover-decline | 6 | full-page rotated figure (three maps), 117-char caption | partial | **mixed** |
| Alwan_1988_time-series-modeling-statistical-process | 2 | born-digital two-column | text | **native** |
| Reynolds_2000_general-approach-modeling-cusum | 7 | scanned full-page **Table 1** with a sideways running head; the native characters are the head and the page number | partial | **mixed** |
| " | 14 | scanned table; only the running head is native (25 chars) | image-only | |
| Almon_1965_distributed-lag-between-capital | 1 | **standalone JSTOR cover page**; article starts p2 | text | **cover-sheet** |
| Schwartz_2000_… (`_quarantine`) | 1 | image-only scan — and of a different paper than its name | image-only | **scan** |
| Hughes_1999_non-homogeneous-hidden-markov-model | 1 | born-digital, encrypted, perfectly readable | text | **native** |

**Twelve of twelve agree.** `test_classification_agrees_with_hand_inspection` holds the table.

Two readings worth stating plainly, because they are where a reader would go wrong:

* **Guo 2019 p6 is `partial` and that is the rule working, not failing.** It is a native figure
  page, not a scan. `partial` says "this page's text layer does not account for its imagery",
  and the consequence — one page offered to OCR — is the conservative side. It is why 14 files
  route `mixed`; most of those are figure or table pages, not scanned documents (the full list
  is in the CSV, `ocr_page_count` column).
* **Kingman 1962 is `native`, and stage 0 cannot see what is wrong with it.** Its text layer is
  complete but mis-OCR'd ("J. F. Co KINGMkN"), which is exactly the binding failure
  `EDGE_PRE1990` row 219 recorded. A **wrong** layer is invisible to a character count. Stage 0
  routes OCR by absence, never by quality; detecting a bad layer is a later stage's problem and
  is stated here as a limitation rather than left to be discovered.

---

## 5. The scan question: "7 image-only scans" does not reproduce; the answer is 5 (+1 quarantined)

The revision-3 brief gave 7 image-only scans with no recorded criterion. The design's own
`pdftotext` probe (§12.2) got "1 clear + 4 near-empty + the book" and left the count
`[UNCONFIRMED] until stage 0's per-page text-layer probe sets it`. It is now set, per page:

| file | pages | image-only | partial | route |
|---|--:|--:|--:|---|
| Ogata_1998_space-time-point-process-models | 24 | **24** | 0 | scan |
| Anderson_1957_statistical-inference-about-markov | 22 | 21 | 1 | scan |
| Politis_1994_large-sample-confidence-regions-based | 20 | 19 | 1 | scan |
| Hudson_1978_natural-identity-exponential-families | 12 | 11 | 1 | scan |
| Hwang_1982_improving-upon-standard-estimators | 11 | 10 | 1 | scan |
| Schwartz_2000_… (`_quarantine` only) | 3 | 3 | 0 | scan |
| Schneider_2008 (the 688-page book) | 688 | **1** | 0 | mixed |

**Where the "7" came from, most likely.** 5 active scans + the `_quarantine` copy + the book
counted for its one rastered cover = **7**. That is the only arithmetic in this table that
reaches 7, and it requires counting a quarantined file as a document and a 688-page
born-digital book as a scan. Offered as a reconciliation, not as a claim about what the
revision-3 brief actually did — its criterion is not recorded.

**The answer.** In the active corpus there are **5 scanned documents**, not 7: Ogata 1998 with
no text layer anywhere, and four IMS/JSTOR scans whose only native characters are a 130–142
character publisher stamp on page 1. The book is **not** a scan — exactly one of its 688 pages
(the cover) is a raster. A sixth scan sits in `_quarantine`. Total OCR cost: **111 pages in the
active corpus, 114 including `_quarantine`** — 2.4 % of the pages, not the 7-documents-worth the
brief implied. The two probes agree once the book is counted as the single cover page it is:
"1 clear + 4 near-empty" is confirmed, with the per-page detail the earlier probe could not give.

Four of the five share a producer, `PDFlib 3.02 (SunOS 5.6)` / creator `page2pdf` — the IMS
digitisation run. That is the population OCR has to handle, and it is one pipeline, not five.

### The clause that does not hold: `EDGE_PRE1990` P-2

P-2 says: "On IMS–JSTOR 'collaborating with JSTOR' covers (Hudson, Hwang, Anderson), page 1 has
under 200 characters **and the paper starts on page 2**. Read page 2 when page 1 is a recognised
cover, and fix the stored reason: it says OCR is needed when it is not."

The first clause holds (130–142 characters, measured). **The second and third do not.** Rendering
Hudson p1 and Anderson p1 shows the article's own title, byline and opening paragraphs on page 1
— as image. There is no separate cover page; the JSTOR notice is a stamp printed into the bottom
margin. And page 2 of those files holds **zero** characters, as does every page after it, so
"read page 2" returns nothing. The stored reason "waits for OCR" was **right**: the title is in
the raster and only OCR will produce it. Acting on P-2 would have replaced a correct pending
state with a read of an empty page.

This is why the module separates two things that look alike:

* **cover sheet** — a standalone publisher cover page: masthead, then `Author(s):` / `Source:` /
  `Published by:` / `Stable URL:`, then the terms paragraph. The document starts on page 2.
  **8 records, 7 works:** Almon 1965, Begg 1983, Cabo 1995, Dawid 1979, Hui 1980, Page 1954
  (and its `_quarantine` twin), Satten 1996. Every one carries all **four** field markers.
* **cover stamp** — the notice printed onto the article's own first page. **4 files:**
  Anderson 1957, Hudson 1978, Hwang 1982, Politis 1994. Every one carries **zero** field markers.

The two separate perfectly on the field-marker count across the whole corpus (4 vs 0), which is
why the rule counts fields rather than capping characters — a character cap would have called
Almon's 886-character cover page an article page and the stamps cover pages, both backwards.

`title_page` follows from that: 2 for a cover sheet, `None` for Ogata and Schwartz and the four
stamped scans (no page's text layer carries it; only OCR will), 1 otherwise.

---

## 6. Kills — every one shown to fire

Built here, never taken from the corpus. `qc/test_litkb_inventory.py`.

| kill | input | result |
|---|---|---|
| text layer stripped → `image-only` | a born-digital fixture re-made as pictures of its pages (`pypdfium2` render → `PdfImage.set_bitmap`) | every page `image-only`, file routes `scan`, all pages listed for OCR. Deleting the text *objects* instead would leave a blank page, which is `empty` — a different case, and the test asserts the raster is what made the difference |
| JSTOR cover sheet → `cover-sheet` | synthetic cover page + two body pages | `route=cover-sheet`, `cover_sheet=True`, `title_page=2` |
| IMS stamp alone is **not** a cover sheet | stamp text prepended to a body page | `cover_sheet=False`, `route=native`, `title_page=1` |
| corrupt → `unreadable`, not `native` | a native fixture truncated at half its bytes; also a zero-byte file | `route=unreadable`, `pages=0`, pdfium's own last-error name recorded |
| blank page → `empty`, not `image-only` | a page with neither text nor raster | `empty`, and it is **not** put in the OCR queue |

### Threshold mutations (`qc/instruments/litkb_inventory_mutations.py`)

Each row changes ONE thing in the real source, runs the whole stage-0 set, then restores the
file and verifies the restore by sha256. Both baselines must pass.

| id | what it weakens | result |
|---|---|---|
| T1 | `CHARS_TRACE` 100 → 10: a stamped scan page reads as content | **FIRED** (2 failed) |
| T2 | `CHARS_TRACE` 100 → 300: cover stamps read as image-only | **FIRED** (4 failed) |
| T3 | `CHARS_BODY` 400 → 150: a scanned table page reads as finished text | **FIRED** (2 failed) |
| T4 | `IMAGE_COVER` 0.25 → 0.95: Ogata's strip-cut scan stops being a scan | **FIRED** (7 failed) |
| T5 | `IMAGE_COVER` 0.25 → 0.01: any page with a small figure reads as image-covered | **FIRED** (3 failed) |
| T6 | `SCAN_FILE_FRAC` 0.5 → 0.99: a whole scan is priced as a mixed native document | **FIRED** (1 failed) |
| T7 | `COVER_MIN_FIELDS` 2 → 5: a real JSTOR cover page is never recognised | **FIRED** (4 failed) |
| T8 | `COVER_MAX_CHARS` 200 → 10: the IMS stamp is no longer boilerplate-only | **FIRED** (1 failed) |
| I1 | the image probe removed: a rasterised page reads `empty`, not `image-only` | **FIRED** (8 failed) |
| I2 | `max_depth` 8 → 0: a raster nested in a form XObject is missed | **FIRED** (1 failed) |
| U1 | a document that will not open is routed `native` | **FIRED** (2 failed) |
| C1 | the cover-sheet host marker dropped | **FIRED** (4 failed) |
| F1 | the §7.1 cropbox origin dropped: `dx`/`dy` become 0 | **FIRED** (1 failed) |
| R1 | rotation reported as 0 | **FIRED** (1 failed) |
| S1 | the resume key drops the path: a second copy is never recorded | **FIRED** (2 failed) |
| S2 | the resume key drops the params hash: a moved threshold is never re-probed | **FIRED** (2 failed) |
| PLANT | a comment reworded — a deliberate no-op | **DID NOT FIRE** (as required) |

**16/16 fired**; both baselines `50 passed`; `inventory.py` restored byte-for-byte after every
row (sha256 `538986374ee35b2f…`, `match: True` each time).

**Four rows did not fire on the first run, and each was a real hole in the tests, not a bad
row.** They are recorded because the fix is the point of §3.4c:

* **T5** — the boundary table was written as `inv.CHARS_TRACE - 1`, so it moved with the
  constant and asserted nothing about its value. The thresholds are now written out as
  literals.
* **I2** — no fixture had a raster nested in a form XObject, the case `max_depth` exists for.
  `test_a_raster_nested_in_a_form_xobject_is_still_found` builds one.
* **F1** — the census counts cropped pages from `cropbox != mediabox`, which zeroing `dx`/`dy`
  does not touch. The shift is now asserted against referee 2's own Alwan p2 numbers
  (dx 10.345, dy 9.052).
* **S1** — the row itself was a no-op (adding the same key to a set twice). The resume key is
  now one function, `resume_key`, used by both sides, and S1/S2 mutate it.


### The existing structural guards, brought to bear on this module

`qc/test_litkb_harness_sites.py` failed the moment stage 0 landed, and both failures were
correct:

* **the per-call-site rule** found `inventory.probe_file`'s call of `textnorm.jsonb_safe` with
  no mutation row. Stage 0 reads the PDF `/Info` dictionary straight off the file, and the NUL
  that started E3 — Bell 1977's `Acrobat 3.0 Capture Plug-in` producer string — lives in
  exactly that dictionary, so this is the guard's **third reached copy**, not a decoration.
  Row `E3inv` was added to `litkb_p2_mutations.py` and **FIRED** (1 failed:
  `test_a_nul_in_pdf_metadata_never_reaches_the_record`; restore `match: True`).
* **the sink rule** found stage 0's two `print` sites. Both are named in `SINK_ALLOW` with
  their call counts (2 and 4) and the reason: this module opens files read-only and never
  connects to the database or the network, so no secret is in scope in it at all.

### The ladder

`LITKB_TEST_DB=litkb_test_w7 py -3.12 qc/check.py --fast`: secrets PASS, ruff PASS, compile
PASS, pytest **1 failed, 2,489 passed, 5 skipped, 1 xfailed** — the single failure is
`test_pointer_paths_resolve[crown_state_model]`, the pre-existing one this branch is allowed.

---

## 7. Idempotence, resume, throughput

* **Resume key is `(sha256, path, params_hash)`**, not sha256 alone. Keying on the hash alone
  would drop every copy of a duplicate after the first — and duplicates are a thing this stage
  is asked to report. `test_two_copies_of_one_file_are_two_records_and_one_duplicate_group`
  pins it, and mutation `S1` fires on it.
* A re-run with no `--force` rewrites the JSONL **byte-for-byte identically** and re-probes
  nothing; `--force` re-probes everything and reaches the same routes.
* Writes are `.partial` → fsync → rename, the pattern `litkb.ops.nightly_dump` already uses.
* **Wall clock: 47.9 s cold (~105 pages/s), 3.3 s on a resumed re-run for 241 files / 5,038 pages**, cold, single process, on the
  T2000 laptop, reading from `D:\`. That is the whole-corpus cost of stage 0 and it is small
  enough that no page-range splitting (§12.5) is needed for this stage, including for the
  688-page book.

---

## 8. What this hands the next stages

* **Stage 1/5 (frames).** `page_frames` is the single §7.1 reader, with the inherited-mediabox
  fallback and the rotated-page refusal already measured on the one page where it matters.
* **Stage 3 (OCR).** The exact page list: 111 active pages across 5 documents plus 14 scattered
  figure/table pages. One digitisation pipeline (`PDFlib 3.02 / page2pdf`) produced four of
  the five scans.
* **P5 (projection).** 5,038 pages is the denominator; 114 is the OCR numerator. Both are
  measured, with their corpus definitions attached.
* **Admission.** Two sha256 collisions across *different* works (Chen 2024 / Song 2026,
  Stehman 2022 / Xing 2024) are reported, not resolved.

## 9. Limitations, stated rather than discovered later

1. **A wrong text layer is invisible.** Kingman 1962 and Maragos 1989 have complete but
   mis-OCR'd layers and route `native`. Stage 0 routes on absence, never on quality.
2. **`partial` is conservative.** A native full-page figure with a short caption is `partial`,
   so 14 files route `mixed` that a human would call born-digital. The cost is one OCR page
   each; the alternative (a per-file density rule) would have to be tuned on the same 14 pages
   it judges, which is the circularity §3.4c forbids.
3. **`empty` has no instance in this corpus.** Its kill fires on a built fixture only.
4. **Image area can exceed the page.** `image_frac` above 1.0 (MacFaden p1 at 1.12, Pauls p17
   at 1.23) is a raster bleeding past the cropbox or overlapping rasters; the threshold is a
   floor so this never changes a class, but the column is not a probability.
5. **One bad page condemns the whole file.** If `_page_measure` raises on any page, the
   record routes `unreadable` with `unreadable_reason="page"` and the pages already read are
   kept but the file is not classified — a single damaged page would take the 688-page book
   out of the pipeline. No corpus file does this (0 unreadable), so the behaviour is untested
   against a real instance; P5 should treat `unreadable_reason="page"` as "look at this file",
   not as "this file is lost".
6. **The gate's page descriptions come from renders, and only from renders.** Every cell in §4
   was written after reading the PNG. Four of them (Ogata p1, Bell p1, Schneider p4,
   Reynolds p7) were first drafted from the probe's numbers and corrected against the image
   before this report was finished; the correction changed three descriptions and **no
   classes**.
7. **No referee.** See the status note at the top.

# litkb stage 5 — reconciliation and the P5 ingest schema — 2026-09-15

Branch `work/20260913-literature-kb`, worktree `D:\edmonds-pipeline\treedata-litkb`, from `9e9f511`.
Design §4.4, §7 stage 5, §7.1, §14 P4/P5.

What is built: one frame reader instead of three; `litkb.extract.reconcile` (canonical blocks,
tables, figures, equations, disagreements, coverage); migration `0017_extraction.sql`; and
`litkb.extract.ingest`, which lands a file's reconciliation in one transaction as `litkb_ingest`.

**Read the thresholds section before quoting any number here.** No referee-authored gold exists
for reading order, matching or coverage — the P4 merge report already records that clause as
NOT VERIFIED — so every threshold below is **author-chosen and UNVALIDATED against gold**. The
gates fire, which is a different and weaker claim than the gates being right.

---

## 1. The frame: three readers collapsed into one

`Reports/LITKB_P4_MERGE_2026-09-15.md` carried this as the item to close **before** stage 5,
because stage 5 is the first place two readers of one fact produce wrong boxes rather than
duplicate code. It is closed.

`litkb.extract.inventory.page_frames(pdf_path, error=None)` is now the only body.
`litkb.extract.grobid.page_frames` and `litkb.extract.docling.page_frames` call it and differ in
one thing: the exception class raised on a page with no mediabox (`GrobidError`, `DoclingError`).
The names stay, so the three referee test files that import them do not move.

**The referee numbers reproduce, unchanged.** `Alwan_1988` p2, measured after the collapse:

| | measured | as before |
|---|---|---|
| cropbox | `(10.3449, 10.7771, 603.441, 782.948)` | yes |
| `dx` | 10.3449 | yes (referee: 10.345) |
| `dy` | 9.052 | yes |
| p1 cropbox == mediabox | yes | yes |
| `G.page_frames == D.page_frames == I.page_frames` on Alwan | **True** | new — that was the point |

`Hall_1985` p12 (rotation 180 **and** cropped, the corpus's only such page) is still refused by
both adapters: the blocks come back `frame="cropbox"`, unmoved.
`test_the_rotated_page_is_still_refused_by_both_adapters`.

**The inherited-`/MediaBox` case is real corpus data, not a fixture.** Sweeping the raw pdfium
getter over the 224 PDFs under `Literture\` (excluding `_quarantine`): it returns 0 — the page
has no `/MediaBox` of its own — on **16 pages in two files**, all 10 of
`Platanios_2014_estimating-accuracy-unlabeled-data.pdf` and 6 of
`Vincent_1993_grayscale-area-openings-closings.pdf`. Docling's pre-unification copy had neither
the high-level-accessor fallback nor the missing-mediabox raise, so it returned `None` boxes and
would have died with a `TypeError` inside its own shift on every one of those pages. That is the
defect the collapse removes, and `R51` (the fallback deleted) is the mutation that proves the
test sees it.

## 2. Reconciliation

`Scripts/pipeline/litkb/extract/reconcile.py`. Inputs are **artifacts** — a TEI tree and a
DoclingDocument dict — never the tools, so nothing here imports GROBID or Docling's runtime.

* **Frame** — every box through its adapter's `to_mediabox` with frames from the one reader. A
  page the adapters refuse is **excluded from matching** and counted (`skipped_rotated`), never
  matched across two origins.
* **Regions** — an element's per-line boxes are **unioned per page** before matching. This was
  the largest single correction found while building: GROBID gives a `<p>` one box per LINE and
  Docling one `prov` per column fragment, and matching first-boxes reads a paragraph's first line
  against the other tool's whole paragraph. On `Alwan_1988` that gave **8 matched regions**; the
  union gives **84**. An element spanning a page break stays two regions.
* **Match** — page + IoU, one-to-one, greedy from the highest down. `IOU_MATCH = 0.5` is a match;
  `IOU_TOUCH = 0.1` to below 0.5 is a **partial overlap**, which is a disagreement in its own
  right (it is the shape of a column one tool merged and the other split).
* **Kinds** — paragraph / heading / caption / footnote / reference / table / figure / equation /
  furniture, mapped from each tool's vocabulary and then to the `blocks.type` values migration
  0002 admits. GROBID's `<s>`, `<ref>` and `<persName>` are **not** regions: with
  `segmentSentences=1` a paragraph also emits its sentences, and counting those would match one
  region three or four times.
* **Order** — each canonical block CARRIES the layout model's own sequence number
  (`tool_order`); `_assign_order` only sorts by it and renumbers. A region only GROBID saw takes
  the order of the nearest Docling block above it **in its own column** (horizontal overlap is
  required). References are appended in **GROBID's** order after the body. See §6a: the first
  version of this re-derived the order from geometry and was wrong.
* **Text** — the native layer wins (`text_source="native"`), the tool's text is used where stage
  0's routing says the page has no native layer (`"ocr"`), and per-field provenance travels in
  `blocks.provenance` (`{"bbox": "docling", "text": "native-layer", "kind_alt": "grobid", …}`).
  A single `extractor` column would have to name one tool and lie about the other fields.
* **Tables** are Docling cell grids (rows in `table_cells`, never a rendered string);
  **figures** are regions whose caption is GROBID's where GROBID has a `<figure>` over the same
  region, else Docling's, with the choice recorded — the caption is the figure block's **text**,
  because `figures.description` is §4.4's stage-8 vision field and a caption written there would
  read later as a model's description of the picture; **equations** are regions with `latex` left
  **NULL** until stage 4 fills it — putting the region's plain text in a field named `latex`
  would look like LaTeX and be false.
* **Disagreements are kept, never resolved**: `kind_conflict`, `text_conflict`,
  `partial_overlap`, `grobid_only`, `docling_only`, each carrying BOTH readings. A single-tool
  file emits none: "the other tool has no box here" is a fact about the run, not about a region.

## 3. Schema — `0017_extraction.sql`

Additive. `pages`, `blocks`, `tables`, `figures`, `equations` and `extraction_runs` already
existed (0001/0002) and applied migrations are checksum-locked, so 0017 **adds columns** to them
and creates only what was missing.

| New | Why |
|---|---|
| `table_cells` | 0002 stores cells as one `tables.cells` JSON blob; a blob cannot be queried, indexed or joined. A trigger **retires** the JSON column rather than dropping it — one fact, one home, enforced |
| `extraction_disagreements` | with no table for a conflict the only way to store one is to drop a tool's reading, which §7 forbids |
| `file_current_run` | `files.current_run_id` is a pointer with no history; "which run was current when this evidence was recorded" was unanswerable. Written INSIDE `set_current_run`, so it cannot drift from the pointer |
| `blocks.provenance` / `.text_source` / `.source` | per-FIELD provenance (see §2) |
| `pages.page_class` / `.native_chars` / `.covered_chars` / `.coverage_share` | §14's coverage metric is a per-page fact reported per page TYPE |

**Who may write.** The three new tables grant INSERT to **nobody**: `open_extraction_run`,
`finish_extraction_run`, `clear_extraction_rows`, `add_table_cell` and `add_disagreement` are
SECURITY DEFINER and only `litkb_ingest` may EXECUTE them, so their checks are not optional.
`blocks`/`pages` keep the direct INSERT 0010 granted — revoking it would retire two P1-refereed
tests on an unrefereed change (CLAUDE.md §3.4c) — so their invariants are **triggers and CHECKs**
instead, which hold on every path: a block's run must be its file's run, a canonical block must
carry a reading order, and no two canonical blocks may share one.

`set_current_run` keeps every rule 0007 gave it (an `ok` run **of the same file**, or refusal,
with the same message and SQLSTATE the P1 tests match) and adds the history row in the same
transaction. 0007's copy is dead text from here on.

**Coverage metric** (§7.1, §14): share of a page's native-layer characters whose box CENTRE falls
inside some canonical block, reported per stage-0 page class. On a page with no native layer the
share is **NULL, never 0 and never 1** — an image-only scan has no denominator, and any number
there would claim a measurement that was not made.

## 4. Ingest

`Scripts/pipeline/litkb/extract/ingest.py`, as `litkb_ingest` through `litkb.ingest.connect()`.

* **One transaction per file.** Run row, pages, blocks, cells, figures, equations and
  disagreements commit together or not at all.
* **Idempotent by (file sha256, pipeline version)** — 0001's UNIQUE on the run key, the file row
  being the sha256. A second call returns the existing run and writes nothing.
* **Resume.** A run that exists and is NOT `ok` is a killed worker's carcass: its rows are
  removed by `clear_extraction_rows` **inside the resuming transaction**, so the file never holds
  two sets of blocks. That function refuses an `ok` run, so the same privilege cannot empty a
  live run out from under the evidence citing it.
* **The pointer moves last**, so a half-finished ingest can never be read as the file's answer.

## 5. The run — 5 referee papers + Ogata (scan/OCR) + a cover-sheet file

`py -3.12 qc/instruments/litkb_stage5_run.py`. Artifacts: GROBID 0.9.1 CRF TEI under WSL2
(service started, then stopped), Docling 2.127.0 CPU venv. Wall-clock is the **reconciliation
only**, on this laptop, single process.

Wall-clock is given three ways: GROBID's own (concurrency 1, warm service under WSL2), Docling's
(CPU venv), and stage 5's reconciliation. Docling seconds are quoted only for the two files
converted in this session; the other five reuse artifacts the P4 branches produced, whose rates
are in `phase4/qc/litkb_extraction_metrics.jsonl` and the Docling throughput CSV.

| file | pages | route | TEI | blocks | matched | disagreements | GROBID s | Docling s | stage 5 s |
|---|---|---|---|---|---|---|---|---|---|
| Benedek_2015 | 16 | native | yes | 570 | 171 | 373 | 43.7 | (P4 artifact) | 1.8 |
| Alwan_1988 | 10 | native | yes | 211 | 84 | 119 | 3.1 | (P4 artifact) | 0.7 |
| Anderson_1957 | 22 | scan | **no** | 314 | 0 | 0 | refused | (P4 OCR artifact) | 0.1 |
| Bellettini_2002 | 51 | native | yes | 1,323 | 359 | 1,064 | 6.2 | (P4 artifact) | 1.9 |
| Schneider_2008 (the 688-page book) | 688 | mixed | yes | 14,367 | 5,081 | 9,523 | 84.2 | (P4 artifact) | 49.8 |
| Ogata_1998 | 24 | scan | **no** | 388 | 0 | 0 | refused | **584.7** (OCR) | 0.1 |
| Almon_1965 (cover sheet) | 20 | cover-sheet | yes | 437 | 31 | 390 | 3.2 | **182.2** | 0.7 |

Stage 5 is not the cost of this pipeline: on the book it is 49.8 s against GROBID's 84.2 s, and
on a scan it is a tenth of a second against Docling's ten minutes of OCR.

`tei = no` is not a failure of this stage: GROBID refuses `Ogata_1998` outright (HTTP 500
`NO_BLOCKS`, no text layer anywhere) and `Anderson_1957` with `NoTextBlocks` (200 with an empty
body — the partial-text-layer case the zero-block rule exists for). Both reconcile from Docling
alone, single-source, confidence 0.5, and emit no disagreements.

**Blocks per kind** and **coverage per page type**:

| file | by kind | coverage by page class |
|---|---|---|
| Benedek_2015 | para 347, ref 64, head 40, eq 40, fig 24, cap 16, furn 33, tbl 4, fn 2 | text **0.9999** |
| Alwan_1988 | para 139, furn 27, head 19, ref 14, fig 5, cap 4, eq 2, fn 1 | text **0.9995** |
| Anderson_1957 | para 171, eq 89, furn 45, head 4, fn 3, fig 1, tbl 1 | partial **1.0000**, image-only **N/A** |
| Bellettini_2002 | para 865, eq 281, furn 103, ref 38, head 21, fig 10, cap 4, fn 1 | text **0.9987** |
| Schneider_2008 | para 7,595, eq 3,624, ref 1,296, furn 1,293, head 473, fig 73, tbl 13 | text **1.0000**, image-only **N/A** |
| Ogata_1998 | para 262, furn 47, eq 38, head 23, cap 8, fig 7, tbl 3 | image-only **N/A** (24 of 24 pages) |
| Almon_1965 | para 312, furn 54, eq 14, fig 11, ref 11, head 9, cap 8, tbl 4 | text **1.0000** |

Rows: `Reports/litkb_stage5_2026-09-15.csv`. Zero pages below the 0.80 floor on any file.

**An honest note on those coverage numbers.** They are near 1.0 because canonical blocks
**overlap** — a GROBID-only region and a Docling-only region over the same prose both count, and
coverage asks only whether SOME block is responsible for a character. See §6.

## 6. Gates and kills

Every row below was run. The harness rows are `R51`–`R518` in
`qc/instruments/litkb_p2_mutations.py`; each weakens ONE thing in the real source, runs the whole
set, and restores the file byte-for-byte.

| The brief's kill | Fires? | How |
|---|---|---|
| coverage below threshold on a planted page with a catch-all block removed | **FIRES** | `litkb_stage5_run.py --only Alwan_1988 --drop-catch-all 4`: p4's 14 body regions removed (furniture kept), coverage **1.0000 → 0.0222** against a 0.80 floor, gate names page 4. Also `R55` (floor → 0.0) |
| an interleaved reading order fails | **FIRES**, on the checker AND on the writer | `test_an_interleaved_reading_order_fails` + `R57` (the checker); `test_assign_order_keeps_doclings_order_across_two_columns`, `test_a_region_only_grobid_saw_anchors_inside_its_own_column` + `R519`/`R520` (the writer — see §6a) |
| a duplicate ingest inserts nothing | **FIRES** | `test_kill_a_duplicate_ingest_inserts_nothing`; `R516` |
| a mid-file kill leaves no duplicates on resume | **FIRES** | `test_kill_a_worker_killed_mid_file_leaves_no_duplicate_blocks` and `…a_partial_run_left_by_a_kill_is_cleared_not_appended_to`; `R514`, and `R515` for §14's own wording (commit outside the run's transaction) |
| writer role cannot insert blocks | **FIRES** | `test_kill_the_writer_role_cannot_insert_a_block_or_a_disagreement`; `R517` |
| `set_current_run` refuses a failed run | **FIRES** | `test_kill_set_current_run_refuses_a_failed_run`; `R518` |
| the frame-unification mutation (drop the MediaBox fallback) fails a test | **FIRES** | `R51` |

Also fired: `R52` (adapter error class), `R53`/`R54` (match threshold both ways), `R56` (per-line
union), `R58` (retired JSON cells), `R59` (an ok run's rows cleared), `R510` (blockless run
declared ok), `R511` (a cell below a paragraph), `R512` (a block naming another file's run),
`R513` (canonical block with no reading order).

**Two rows did not fire on the first attempt, and the fix was a missing test, not a kinder
mutation.** `R54` passed because every matching test used identical boxes (IoU 1.0), which still
match at a threshold of 0.999; `R513` passed because nothing inserted a canonical block with a
NULL order. Both tests were added and both rows then fired.

## 6a. Two defects the gates did not see, found in review, fixed

Both were in the PRODUCER, and both were invisible because the tests exercised the CHECKER on
hand-built blocks. They are written up because a gate that passes a broken writer is the failure
mode CLAUDE.md §3.4c exists for.

1. **Reading order was re-derived from geometry, and interleaved two-column pages.** The first
   `_assign_order` took `max(order_index)` over every Docling block on the page with
   `y0 <= this block's y0`. On a two-column page that set contains the RIGHT column's top blocks
   for every left-column block below them, so the sort collapsed to geometry across the gutter.
   Measured on `Benedek_2015` pp2-3 against Docling's own body order: **21 of 23 body snippets
   out of order**. `test_an_interleaved_reading_order_fails` passed throughout, because it ran
   `order_violations` on blocks whose order was written by hand. Fixed by carrying the layout
   model's sequence on each canonical block and sorting by it, with a column-aware anchor for
   GROBID-only regions: **0 of 23** after. Rows `R519` (order back to geometry) and `R520`
   (anchor without the column check) both fire.
1b. **The caption fix landed in one module and not the other.** `reconcile.py` was changed to put
   a figure's caption in the block's `text`, but `ingest.py` kept writing it into
   `figures.description` — stage 8's vision field — so the report described one thing and the
   database held another. Found by re-reading the writer against the report rather than against
   the change. Row `R522` fires, and the end-to-end test now asserts `description IS NULL`.
2. **Native text came back with every space removed.** `native_text_in` joined the characters
   whose boxes fell inside a block, and pypdfium2 reports no usable box for a space — so a
   paragraph read `"Contentslistsavailable"`. Coverage was unaffected (its denominator is the
   ink), which is exactly why nothing caught it; the text was unusable for quote verification or
   chunking. Fixed by returning the page's own string plus per-character indices and SLICING it
   between the first and last inside-character, which also restored the two characters that the
   degenerate first-of-run box had been dropping from the front of every run. Row `R521` fires.

**What the coverage gate does NOT catch, measured.** The first form of the planted-page kill was
"drop the largest block on the page". On `Alwan_1988` p4 the largest block is a 491×659 pt
paragraph covering nearly the whole page, and removing it moved that page's coverage only from
**1.0000 to 0.9723** — nowhere near the floor. Because the canonical blocks overlap, the metric
is **insensitive to a single lost region**; it detects a page whose BODY went unassigned. That is
a true limit of the design's own metric (§7.1 defines it exactly this way) and it is written down
here rather than hidden behind a kill chosen to pass.

## 7. Thresholds — provisional, and why

| | value | status |
|---|---|---|
| `IOU_MATCH` | 0.5 | author-chosen, **UNVALIDATED against gold** |
| `IOU_TOUCH` | 0.1 | author-chosen, UNVALIDATED |
| `TEXT_AGREE` | 0.90 | author-chosen, UNVALIDATED |
| `COVERAGE_FLOOR` | 0.80 | author-chosen, UNVALIDATED |

§14 requires gold authored by a referee and committed **before** the measurement. None exists for
reading order, matching or coverage — the P4 merge report already records that clause as NOT
VERIFIED, and this session did not close it. The four constants are pinned by tests and by
mutation rows, which stops them drifting unnoticed; it does not make them right.

## 8. Proofs

* `qc/test_litkb_reconcile.py` — **39 passed** (`LITKB_TEST_DB=litkb_test_w6`), of which 17 are
  Postgres tests, two of them real files ingested end to end.
* `qc/test_litkb_p1.py` — the role-privilege matrix updated with the five new ingest-only
  functions and re-run.
* `py -3.12 qc/instruments/litkb_p2_mutations.py --sites` — **PASS** (16 sinks, 2 redacted, 14
  allowed; no new sink: neither `reconcile.py` nor `ingest.py` writes to stdout).
* Parallel harness, `--workers 4 --worker-dbs 1,2,6,9`, the **22** new rows `R51`–`R522`:
  **22/22 fired**, baselines passed.
* Whole harness, same invocation, at the time it was run (176 rows, before `R522` was added):
  **176/176 fired**, baselines passed, 44/44 per worker, wall-clock **48.1 min** over 4 workers.
* `py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w6`: **2,669 passed, 23 skipped,
  2 xfailed, 1 failed** — the single failure is `test_pointer_paths_resolve[crown_state_model]`,
  the known pre-existing one. litkb Postgres tests 259 passed.

## 9. What was persisted, and where

**Nothing was written to `litkb`.** The §5 run reconciles real files and writes a CSV; it never
opens a database.

**Real reconciliations WERE ingested, into `litkb_test_w6`.**
`test_a_real_files_reconciliation_lands_whole` reconciles `Alwan_1988` (with TEI) and
`Anderson_1957` (no TEI, image-only pages) and lands each through `ingest_file` as
`litkb_ingest`, asserting that the block count equals `stats["blocks"]`, the disagreement count
equals what reconciliation produced, every page row is there with NULL `coverage_share` on the
pages that have no native layer, the pointer moved, and a second ingest writes nothing. That test
exists because every other ingest test here uses hand-built blocks, and real output has shapes
they do not.

**Migration 0017 was applied to `litkb_test` and to the four worker databases through the test
suite's own reset-and-migrate.** (It was also applied by hand to `litkb_test` once, before the
`clear_extraction_rows` function was added; that database therefore carries a stale checksum until
the suite next resets it, which it does on every run. The four worker databases were only ever
migrated by the suite.) It was **NOT applied to `litkb`**: the brief holds `litkb`
read-only except for applying this migration once accepted-additive, and it has not been
refereed. It is additive by construction (three new tables, added columns with defaults, one
`CREATE OR REPLACE`, one trigger on `tables` and two on `blocks`/`pages`), but the
`tables_cells_retired` trigger **changes the meaning of an existing column** for any writer that
was filling it, so it is a referee's call, not the author's. Applying it is one command:
`py -3.12 -m litkb.db.migrate --db litkb`.

## 10. What blocks a referee

1. **No pre-committed gold.** §7 above. Every threshold is the author's, and by §3.4c a design may
   not be accepted on numbers it produced about itself. A referee has to author reading-order
   sequences, matched-region pairs and a coverage target for at least two of the gate papers,
   commit them, and only then score this code.
2. **The coverage metric's blind spot** (§6) is measured but not designed around. Whether the
   metric should count a character once per block (so a lost region shows) is a design question
   this session raises and does not answer.
3. **0017 is not applied to `litkb`** (§9), so nothing in the real lake has been ingested. Real
   files have been reconciled and ingested only into `litkb_test_w6`, by the end-to-end test.
4. **GROBID contributes far fewer regions than Docling, and only some of them match.** Measured:
   `Almon_1965` **48 GROBID regions against 398 Docling**, of which 31 matched; `Benedek_2015`
   **233 against 430**, of which 171 matched. A referee should decide whether GROBID is simply
   regioning at a coarser grain — in which case `partial_overlap` is under-reporting and the
   matching should be many-to-one rather than one-to-one — or whether regions are being lost.
   Either way it is the single largest open question about this stage's accuracy.
5. Stage 5 does not yet write `references` rows, `citation_mentions` or chunks — those are
   stages 6 and 7, and the reference blocks it produces carry GROBID's raw text only.

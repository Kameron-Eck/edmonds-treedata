# litkb P5 — the local bulk pass: the corpus into `litkb` — 2026-09-16

Branch `work/20260913-literature-kb`, worktree `D:\edmonds-pipeline\treedata-litkb`.
Driver: `Scripts/qc/instruments/litkb_p5_bulk.py` (`plan | grobid | docling | ingest |
kill-test | gate`). Per-file table: `Reports/litkb_p5_files_2026-09-16.csv` (225 rows).
Design §7, §12, §14 P5.

**`litkb` now holds 102,008 canonical blocks over 3,945 pages of 225 files, every one of them
inside an `ok` run, and the three P8 gold passages come back from `litkb_search` at ranks
1, 2 and 2.** What follows is what that cost, what it does not cover, and the two things the
run measured that were not expected.

---

## 1. Commits

| commit | what |
|---|---|
| `9e6adae` | merge of `work/20260915-colab-l4-formula` @ `89e4580`, `--no-ff`. One conflict — `test_status_discovery.py`'s `sys.path.insert` ledger — both sides kept |
| `210718a` | post-merge: `SINK_ALLOW` for the three formula-worker `print` sites |
| `c91f7cb` | the P5 driver |
| `4d25b9c` | the `host` CHECK, and a kill that actually lands mid-transaction |
| `<this>` | the report, the per-file table, the gate fix |

Pushed: see §9.

**The merge left `litkb_p2_mutations.py --sites` FAILING**, and that is recorded rather than
fixed silently: the Colab branch's own harness (`litkb_formula_mutations.py`) does not carry
the per-call-site sink rule, so its two new modules under `Scripts/pipeline/litkb/` arrived
with three unargued `print` sites. Each was read and named in `SINK_ALLOW` with a reason about
the code. Neither module opens a socket or a database connection, so no credential is in scope
in either. After: **21 sinks, 2 redacted, 19 allowed.**

`py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w6`, at the merge:
**1 failed, 3,031 passed, 26 skipped, 2 xfailed, 463.8 s**. The one failure is the known
pre-existing `test_pointer_paths_resolve[crown_state_model]`.

---

## 2. The population — the finding that changed the run

**§14 P5's gate reads "every ACTIVE FILE has a current run with pages and blocks".** An active
file is a row in `litkb`, not a PDF on disk. The brief said to bind the 241 census files and
skip the unbound; doing exactly that would have extracted 179 documents and left 46 admitted
files with no run at all — files the gate asks about. So the population is
`litkb.main_files WHERE status='active'`, and the census supplies the routing for the files it
names.

| | measured | source |
|---|--:|---|
| frozen stage-0 census, files | 241 | `litkb_p5_bulk.py plan` |
| census pages | 5,038 | " |
| census DISTINCT documents (sha256) | 232 | " — 6 duplicate-sha256 groups |
| **active files in `litkb`** | **225** | `SELECT count(*) FROM litkb.main_files WHERE status='active'` |
| **planned documents** | **225** | plan |
| … named by the frozen census | 179 | plan |
| … probed here (census does not name them) | 46 | plan |
| **planned pages** | **3,945** | plan |
| census documents SKIPPED — no `files` row | 53 | plan, listed by name in its output |
| routes of the planned set | native 203, mixed 15, cover-sheet 7, **scan 0** | plan |

The 46 probed-here files were verified before being planned: each exists at its `rel_path` and
hashes to the sha256 `litkb` holds (**46/46 match, 0 missing**). They carry `in_census=false`
in `plan.json` so no pinned census number is ever read off a set the census did not measure.

**The scans are not in the database.** Among the 53 skips are *every* image-only scan in the
corpus — Ogata 1998, Anderson 1957, Hudson 1978, Hwang 1982, Politis 1994 — and the 688-page
Schneider 2008 book. Checked, not assumed:
`SELECT rel_path FROM litkb.main_files WHERE rel_path ILIKE '%Anderson_1957%'` returns nothing,
and the single `Ogata` row is `Ogata_1988`, a different paper.

*Consequence, stated plainly:* **this pass ran no OCR on a scan, because the database holds no
scan.** The OCR batch ran, on the 23 `partial` pages of 15 `mixed` documents. Stage 0's OCR
backlog — 111 pages across 5 scanned documents — is untouched by P5 and stays untouched until
those files are admitted. That is an admission gap, not an extraction gap, and it is the single
largest thing P5 does *not* deliver.

---

## 3. Numbers

### 3.1 Per stage, wall-clock and resources

| stage | documents | pages | wall | rate | peak memory |
|---|--:|--:|--:|--:|---|
| 0 plan (census probe, resumed) | 241 + 46 | 5,038 | 3.3 s + probe | — | — |
| **2 GROBID** (WSL2, pool 4, 4 client threads) | 225 | 3,945 | **193.2 s** | **20.42 pages/s** | 6,400 MB service RSS (whole JVM pool + pdfalto) |
| **3 Docling batch A**, `ocr=off`, CUDA | 210 | 3,633 | **1,794.6 s** | 2.024 pages/s incl. converter builds | **2,317 / 4,096 MiB VRAM** |
| **3 Docling batch B**, `ocr=on`, CUDA | 15 | 312 | **437.5 s** | 0.713 pages/s | **3,881 / 4,096 MiB VRAM** |
| 3 Docling, conversion seconds only | 225 | 3,945 | 2,117.5 s | 1.863 pages/s | 4,174 MB host RSS |
| **5 reconcile + ingest** | 225 | 3,945 | **398.5 s** | — | — |
| … of which reconciliation | | | 291.4 s | | |
| … of which the database transaction | | | 101.5 s | | |
| kill test (§5) | 1 | 54 | 34.6 s | — | — |
| **P5 total** | **225** | **3,945** | **≈ 48 min** | | |

**GROBID's 20.42 pages/s is a pool number and is not comparable to P4's.** P4 measured
8.04–12.11 pages/s at **concurrency 1** on the 688-page book. This is 225 whole documents
posted from 4 client threads against a pool-4 service. The sum of the per-file seconds is
**745.0 s** against a 193.2 s wall — a **3.86×** parallel speed-up on a 4-worker pool, which is
what a pool that is actually being used looks like. Per-file peak RSS is deliberately NOT
recorded: GROBID serves every worker from one JVM, so a per-request cgroup sampler under 4
concurrent clients reports the pool's memory and would label it one file's. One sampler ran for
the whole stage instead, and 6,400 MB is the pool's peak.

**Docling's 2.024 pages/s is below P4's 4.272 p/s, and the gap is not a regression.** P4's
figure is conversion seconds only, over 5 papers and 100 pages of one book. This row is
*wall-clock including a converter build per 30-document chunk* over the whole corpus; the
conversion-only figure for the same run is **1.863 pages/s**, so the chunking overhead is small
and the difference is the corpus, not the harness. The mix here is 225 ordinary papers with
tables and figures, not the 5-paper gate set.

### 3.2 What landed in `litkb` (read-only, after the ingest)

| | before P5 | after |
|---|--:|--:|
| files with a current run | 0 | **225** |
| `5-reconcile` runs, `ok` | 0 | **225** |
| `5-reconcile` runs, not `ok` | 0 | **0** |
| pages | 0 | **3,945** |
| blocks | 0 | **102,008** |
| tables / table_cells | 0 / 0 | **857 / 57,467** |
| figures | 0 | **1,821** |
| equations | 0 | **7,772** |
| **equations with LaTeX** | 0 | **3,297** |
| extraction disagreements | 0 | **74,658** |
| blocks outside an `ok` run | 0 | **0** |
| duplicate runs per key | 0 | **0** |

### 3.3 The L4 formula LaTeX

| | measured |
|---|--:|
| `ok` rows in the full-corpus L4 pass | 6,841 |
| of those, belonging to a PLANNED document | **3,317** (the rest are on corpus files litkb has not admitted) |
| **attached to an equation block** | **3,297 (99.4 %)** |
| unmatched | **20 (0.6 %)**, in 4 documents |
| documents with any L4 row | 108 |
| documents where every row attached | **104** |
| `unstable` + `degenerate` rows attached | **0** — the 323 held rows stay on `latex_formula_colab_full_verify_queue.jsonl` and were never read as text |

`equations 7,772` against `equations_with_latex 3,297`: the shortfall is not a join failure. The
L4 pass cropped formula regions from a Docling run over the *whole corpus*, and 3,524 of the
6,841 `ok` rows belong to files that are not in `litkb`; the rest of the 7,772 equation blocks
are regions the L4 census never cropped (it selected equation-dense pages at
`EQUATION_DENSITY_CUT = 0.05`, which by its own measurement captures 89.8 % of formula regions
and is deliberately not all of them).

**The four documents that did not join cleanly, with their causes measured:**

| document | attached / rows | cause |
|---|---|---|
| `Reynolds_2000_general-approach-modeling-cusum` | 1 / 8 | its P5 Docling artifact came from the **OCR** batch; the L4 crops came from a non-OCR pass, so the layout boxes are different objects |
| `Montgomery_1991_some-statistical-process-control` | 2 / 8 | same |
| `Hall_1985_resampling-coverage-pattern` | 42 / 48 | p12 is the corpus's only page that is **rotated AND cropped**; both adapters refuse it, so it carries no matchable block |
| `Charitos_2008_computing-short-interval-transition` | 19 / 20 | one region, unexplained |

13 of the 20 unmatched rows are the two OCR'd documents. That is a real limitation of mixing a
non-OCR crop pass with an OCR extraction pass, and it is cheap to close (re-crop those two
files) but was not closed here.

---

## 4. The join key, proved on real data

`bbox_canonical` in the L4 rows is Docling's own box through `docling.to_canonical` — TOPLEFT
sense, in the **cropbox** frame. A canonical block has already been through `to_mediabox`. The
formula box is therefore shifted by the same `(dx, dy)` from the ONE frame reader
(`inventory.page_frames`) before it is compared, and a page the adapters refused keeps
`frame="cropbox"` and is compared unshifted.

That is an assumption until a **cropped** page tests it, and Bellettini — the equation paper —
has `dx = dy = 0` on all 51 pages and cannot. Two documents with a real shift can:

| document | cropbox shift | L4 rows | **with** the shift, tol 2 pt | **without** it, tol 2 pt | without it, tol 60 pt |
|---|---|--:|--:|--:|--:|
| `Conley_1999_gmm-estimation-cross-sectional` | (40.0, 37.0) on every page | 138 | **138 / 138** | **0 / 138** | 138 / 138 |
| `Leung_1997_point-polygon-analysis-certainty` | (28.0, 57.0) on every page | 38 | **38 / 38** | **0 / 38** | 37 / 38 |

**Nothing joins without the shift** at the 2 pt grain `merge_formula_latex` already uses, and at
a tolerance wide enough to swallow the shift (60 pt) Leung starts matching the *wrong* region
(37 of 38). The frame is confirmed by measurement, not by reading.

---

## 5. Kills

| §14 P5 kill | fired? | evidence |
|---|---|---|
| **(a)** a worker killed mid-file resumes; one `ok` run per key, same block count, no duplicates | **YES** | §5.1 |
| (b) an artifact whose bytes no longer match its recorded sha256 fails verification | **PARTIAL** | the sidecar check (`_artifact_ok`) is on every stage and a mismatched artifact is re-made rather than used — but **no corrupted artifact was planted in this run**, so it is NOT SHOWN to fire |
| (c) two workers claiming at once never lease the same job | **NOT EXERCISED** | there is no lease: §12.3's `extraction_jobs` is NOT BUILT |
| (d) a dead worker's job is reclaimed only after its lease expires | **NOT EXERCISED** | same |

### 5.1 The kill that fired, and the two that did not

The first two attempts are recorded because they are why the third is trustworthy.

1. **A fixed 1.5 s delay after the child's marker.** The child had already COMMITTED by then.
   The resume found an `ok` run, wrote nothing, every count matched, and the harness printed
   PASS — while proving nothing at all about a mid-file kill. Subject
   `Chernozhukov_2018`, 1,564 blocks.
2. **Polling `pg_stat_activity` until a backend showed in flight.** It never did, on a 1,468-block
   file. Cause, measured rather than guessed: `state` and `query` are NULL for another role's
   backend unless the reader is a superuser or holds `pg_read_all_stats`, so a
   `state <> 'idle'` probe run as `litkb_reader` counts **zero** however live the transaction is.
   Subject `Bacry_2015`.
3. **The child now HOLDS the open transaction** at `ingest_file`'s own `_after_blocks` hook —
   every block inserted, nothing committed, which that module's docstring names as "where the
   simulated mid-file kill is raised" — prints `IN-TRANSACTION <run_id>`, and is killed there
   with `taskkill /F /PID`. The parent reads the child with `readline()`, never by iterating
   `stdout`, whose 8 KiB read-ahead is what hid the first two races.

**Subject: `Singer_1976_representation-social-processes-markov.pdf`, 54 pages, 907 blocks.**

| | measured |
|---|--:|
| child confirmed inside the open transaction | **yes** (`IN-TRANSACTION 01a0aa23-0362-…`) |
| blocks of this file visible to an INDEPENDENT READER while the child held them | **0** |
| `5-reconcile` runs for this file visible to that reader | **0** |
| after the kill: runs at this key | **0** — the run row rolled back with the blocks |
| after the resume: runs at this key / `ok` runs | **1 / 1** |
| blocks on the `ok` run / control (the reconciliation's own count) | **907 / 907** |
| blocks for the file in total | **907** |
| duplicate `(run, page, reading_order)` groups | **0** |

**A measured correction to §14's own wording.** §14 anticipates "a partial run left by a kill"
that the resume must clear. On this path there is no partial run: `open_extraction_run` runs
*inside* the transaction, so killing the connection rolls the run row back with its blocks and
the resuming worker finds nothing to clear. The guarantee is stronger than the one the plan
asked for, and `clear_extraction_rows` — the code that handles leftovers — was therefore **not
exercised by this kill**. It is covered by harness rows `R514`/`R515` and by
`test_…a_partial_run_left_by_a_kill_is_cleared_not_appended_to`, on a simulated partial run.

---

## 6. The gate

**§14 P5 clause by clause.**

| clause | verdict | evidence |
|---|---|---|
| every active file has a current run with pages and blocks | **MET for the 225 active files** | `files_with_current_run = 225`; `pages = 3,945`; `blocks = 102,008` |
| zero duplicate runs | **MET** | `duplicate_runs_per_key = 0` |
| zero text rows outside an `ok` run | **MET** | `blocks_outside_ok_run = 0`; `runs_not_ok = 0` |
| disagreements logged | **MET** | 74,658 rows |
| coverage at or above the P4 threshold | **SEE BELOW — and there is no P4 threshold** | |
| the canary's rate within a tolerance frozen before it runs | **NOT MET, and not attempted** | no canary tolerance was frozen; P4's rates are concurrency-1 and this pass is a pool. The stages were run directly on Kam's "reach a working system tonight" |

**There is no "P4 recall threshold" to gate against, and one was not invented.** The only
committed coverage number is stage 5's author-chosen `COVERAGE_FLOOR = 0.80` on the character
share, which its own report labels UNVALIDATED against gold, and the referee's finding that no
gate-set page is within 0.19 of it — so it is a catastrophe detector, not an operating point.
Per-region recall exists only on the 6 gold pages the stage-5 referee authored; it is not
computable over the corpus, because it needs referee-authored regions per page.

**Character share against the 0.80 floor: 8 of 225 documents have at least one page below it.**
Causes, measured:

| document | pages below | min share | cause |
|---|--:|--:|---|
| `Burnicki_2007_simulating-error-propagation-land` | 2 (pp 16, 17) | 0.0 | **rotated page** — excluded from matching by §7.1, so no block covers it |
| `Guo_2019_city-wide-canopy-cover-decline` | 1 (p 6) | 0.0 | rotated page |
| `Hall_1985_resampling-coverage-pattern` | 1 (p 12) | 0.0 | rotated **and** cropped — the corpus's only such page |
| `Verburg_2004_method-analyse-neighbourhood` | 1 (p 10) | 0.0 | rotated page |
| `Higham_2011_pth-roots-stochastic-matrices` | **15 of 16** | 0.305 | every page cropped, `dy = −111.6` (the cropbox is TALLER than the mediabox); the shift moves blocks off the characters |
| `Efron_1986_how-biased-apparent-error-rate` | 1 (p 5) | 0.746 | 4 cropped pages, shifts −2.16 … −3.36 |
| `Papadopoulos_2024_decision-fusion-pixel-level-multi` | 1 | 0.682 | neither rotated nor cropped — an ordinary low-coverage page |
| `Ock_2024_drivers-tree-canopy-loss-mid` | 1 | 0.732 | same |

**Two causes, not eight problems.** Five pages in four documents are the rotated-page refusal
the adapters were designed to make and their coverage is 0 *because* no block was placed there —
that is the design surfacing at corpus scale for the first time, and the planned set holds
**5 rotated pages in 4 documents** out of 3,945. Sixteen pages in two documents are cropped
files where the cropbox shift does not land on the characters; `Higham_2011`'s negative
`dy = −111.6` is the extreme case, and the planned set holds **285 cropped pages in 16
documents**, of which only these 16 fail — so the shift is right on 269 of 285 and wrong on
16. **That is a real defect and it is not closed here.**

**217 of 225 documents (96.4 %) have no page below the floor.**

### 6.1 The other read-only checks

| check | result |
|---|---|
| P3 gate re-run on `litkb` (workstream `01a0a494-…`) | **1,086 changed cells — explained 713, format 243, structural 120, filled 10, UNEXPLAINED 0. GATE: PASS** — the pinned 713/243/120/10/0, unchanged by the ingest |
| `litkb_search` Q1 (Bellettini, total-variation flow) | gold block `01a0aa23-e991-…` at **rank 1** of 10 |
| `litkb_search` Q2 (Jackson, panel-data likelihood) | gold block `01a0aa25-a961-…` at **rank 2** of 10 |
| `litkb_search` Q3 (Rosychuk, naive-estimator bias) | gold block `01a0aa27-2f48-…` at **rank 2** of 10; the work is also at rank 1 |

Ranks are by exact `block_id`: for each question the blocks whose normalised text contains the
gold passage were found by query first, then located in the top-10. The vector leg is OFF
(P7), so these are the three lexical legs fused by reciprocal rank.

---

## 7. Headroom, and where it was breached

The 20 % headroom rule (§12) means **≤ 3,277 MiB** of the T2000's 4,096 MiB.

| batch | peak VRAM | share | verdict |
|---|--:|--:|---|
| A, layout, `ocr=off` | 2,317 MiB | 56.6 % | within headroom |
| **B, `ocr=on`** | **3,881 MiB** | **94.8 %** | **BREACHED — 215 MiB free on a card that also drives the display** |

Host RSS peaked at **4,174 MB** of 63.8 GB, which is not a constraint on this machine.

The OCR batch's 215 MiB of free VRAM is within 40 MiB of the 178 MiB that
`LITKB_DOCLING_LOCAL` §8.3 measured for the formula pass and called the finding. It did not
fail here; it is one open application away from failing, and a P5 that ran OCR over a real scan
backlog (hundreds of pages rather than 23) would be running at that margin for an hour. The
driver runs the two batches strictly one at a time for this reason (`do_ocr` is converter-wide,
so they cannot be merged anyway).

---

## 8. Did NOT test

- **`extraction_jobs`, the leased worker and the sweep (§12.3–§12.5) are NOT BUILT.** The
  checkpoint here is a local artifact-plus-sidecar on disk. Kills (c) and (d) are NOT EXERCISED.
- **Kill (b)** — an artifact whose bytes no longer match its sha256 — is implemented on every
  stage and was never planted, so it is not shown to fire.
- **No OCR ran on a scan**, because `litkb` holds none (§2).
- **No canary and no frozen rate tolerance.** §14's canary→projection→go sequence was skipped;
  the stages were run directly.
- **Per-region recall is not computed over the corpus** — it needs referee-authored regions and
  only 6 gold pages have them.
- **Reproducibility (§12.11)** — no file was re-extracted at the same pipeline version to check
  that it gives identical blocks. That is P9.
- **`clear_extraction_rows`'s resume path** was not exercised by the live kill (§5.1).
- **The 46 probed-here files' routing is not refereed** — it is the same prober, on files the
  frozen census does not pin.

## 9. Blockers for the next step

1. **The five scanned documents and the 688-page book are not admitted to `litkb`.** Until they
   are, stage 0's 111-page OCR backlog cannot be ingested and the archive's oldest statistics
   papers are absent from search.
2. **The cropbox shift is wrong on 16 of 285 cropped pages**, `Higham_2011` (negative `dy`)
   being 15 of them. One file, one measurement.
3. **The OCR batch runs at 94.8 % of VRAM.** Any real scan backlog needs a decision: smaller
   page ranges, CPU OCR, or a bigger card.
4. **Two documents' L4 LaTeX did not join** because their P5 artifact came from an OCR pass and
   the crops did not. Re-crop `Reynolds_2000` and `Montgomery_1991`.
5. **No referee has seen any of this.** Every number above was produced by the author of the
   code (CLAUDE.md §3.4c).

---

*Builder: Claude Opus 5, session https://claude.ai/code/session_015MUcyGTfX2koRdYAjW5kED.*

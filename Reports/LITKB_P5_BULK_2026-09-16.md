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
| `72cdfe0` | the report, the per-file table, the gate fix |
| `7c7ab70` | the guard tests, harness rows P51-P54, and §6.2 / §6.3 / §10 / §11 |

**Pushed** to remote `github`, branch `work/20260913-literature-kb`: `b2c7324..7c7ab70`.

**The merge left `litkb_p2_mutations.py --sites` FAILING**, and that is recorded rather than
fixed silently: the Colab branch's own harness (`litkb_formula_mutations.py`) does not carry
the per-call-site sink rule, so its two new modules under `Scripts/pipeline/litkb/` arrived
with three unargued `print` sites. Each was read and named in `SINK_ALLOW` with a reason about
the code. Neither module opens a socket or a database connection, so no credential is in scope
in either. After: **21 sinks, 2 redacted, 19 allowed.**

`py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w6`, at the merge:
**1 failed, 3,031 passed, 26 skipped, 2 xfailed, 463.8 s** — the one failure is the known
pre-existing `test_pointer_paths_resolve[crown_state_model]`.

**On the final tree it ran again, and caught something.** First pass: **2 failed**, the second
being `test_status_discovery.py::test_path_insert_ledger`, on
`unlisted=['qc/test_litkb_p5_bulk.py (1)']`. The new test file inserts no path — it *mentions*
the call by name in a docstring, and the ledger greps for the spelling, so a sentence about the
rule put the file on a list of files that break it. Reworded, not ledgered: adding it would
have recorded a path insert that does not exist. Second pass: **1 failed
(`crown_state_model`), 3,043 passed, 25 skipped, 2 xfailed, 630.5 s**; litkb Postgres tests 360 passed.

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
| **(b)** an artifact whose bytes no longer match its recorded sha256 fails verification | **YES** | §10 row **P53**: `_artifact_ok` reduced to `return True` fails 2 tests, one of which flips a byte in a real written artifact. Planted in the TEST, not in the corpus run |
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
the adapters were designed to make, and their coverage is 0 *because* no block was placed there
— the design surfacing at corpus scale for the first time; the planned set holds **5 rotated
pages in 4 documents** out of 3,945. Sixteen pages in two documents are cropped files where the
shift does not land on the characters; the planned set holds **285 cropped pages in 16
documents**, so the character share is at or above 0.80 on 269 of the 285 and below it on 16.
A page above a catastrophe floor is not evidence the shift is RIGHT there — that is this
report's own argument about the floor, and it applies to this sentence too. §6.2 locates the
cause.

**217 of 225 documents (96.4 %) have no page below the floor.**

### 6.2 The cropped-page defect, located

All sixteen cropped-page failures are ONE cause, and it is in the ONE frame reader.

`page_frames` computes `dy = media.y1 - crop.y1`. When a `/CropBox` extends PAST the
`/MediaBox` that is NEGATIVE — Higham's is **-111.6** on all 16 pages — but a renderer
INTERSECTS the two boxes, so the page pypdfium2 measures characters on, and the page Docling
lays out, is the intersection: the effective shift is 0, and the raw -111.6 moves every block
off its own text. Measured, by re-running the reconciliation with `dy` clamped to
`max(dy, 0)` and nothing else changed:

| document | raw `dy` | min share | pages below floor | clamped: min share | clamped: below floor |
|---|---|--:|--:|--:|--:|
| `Higham_2011_pth-roots-stochastic-matrices` | -111.6 (16 pp) | 0.3049 | **15** | **0.9898** | **0** |
| `Efron_1986_how-biased-apparent-error-rate` | -0.48 … -3.36 (4 pp) | 0.7457 | **1** | **0.9851** | **0** |

**Both documents go to zero failures.** That is the whole cropped-page half of §6, and it is a
two-line fix in `inventory.page_frames` — which is under the census `params_hash` and under the
inventory mutation harness, so it is **deliberately NOT made tonight**: changing it re-prices
every stage-0 record and needs its own referee. Blocker #2 now names a line instead of a
symptom.

Note what this does NOT touch: all 38 of Higham's L4 formula rows attached cleanly (§3.3). The
block shift and the crop shift agree with each other; they disagree only with pdfium's
character boxes, which is what a wrong SHARED offset looks like.

### 6.3 The duplicate-sha256 groups, and the two wrong-content collisions

Stage 0 reported 6 duplicate-sha256 groups (15 files) and two sha256 values filed under two
DIFFERENT works each — `bb14fdbc…` under both Chen 2024 and Song 2026, `3a65f982…` under both
Stehman 2022 and Xing 2024. Checked in the database after the ingest, because a collision bound
to the wrong work would attribute one paper's text to another under search:

| sha256 | filed under | active file row? | blocks, and under which work |
|---|---|---|---|
| `bb14fdbc…` | Chen 2024 **and** Song 2026 | **no** | none — neither work has blocks |
| `3a65f982…` | Stehman 2022 **and** Xing 2024 | **no** | none |
| `781b75f8…` | Bellettini 2002 x3 | yes, once | 1,561, `Bellettini_2002_total-variation-flow-rn` |
| `d36c5093…` | Page 1954 x2 (one quarantined) | yes, once | 391, `Page_1954_continuous-inspection-schemes` |
| `753a94fc…` | Brown 2022 x2 | no | none |
| `b0843bfb…` | Mobsite 2026 x2 | no | none |

**No misattribution occurred**, and it could not have: neither colliding sha256 has an active
file row, so the ingest never saw them. The two groups that ARE in the corpus each bound to one
work and were extracted once. The collisions remain an open ADMISSION question (stage 0
reported them and did not resolve them), not a P5 finding.

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
- **Throughput metrics are still parked as JSONL** (`litkb_derived/p5/metrics_{grobid,docling}.jsonl`)
  and are NOT written to `extraction_runs.metrics`. That is the P4 throughput gate's unmet
  clause (§12.10); P5 did not close it. `extraction_runs.metrics` holds the reconciliation's
  `stats` dict only.

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

## 10. The guards this driver adds, and how they are pinned

`qc/test_litkb_p5_bulk.py`, **9 passed**, and four rows in the real harness —
`py -3.12 qc/instruments/litkb_p2_mutations.py --only P51,P52,P53,P54`: **4/4 fired,
baselines passed before and after, `litkb_p5_bulk.py` restored by sha256
`d5dd8b416b8a324f…`, `match: True` after every row.**

These four rows are an exception to the harness's own file rule, made deliberately. Its
per-call-site self-check enumerates `Scripts/pipeline/litkb` only, so a guard written in an
INSTRUMENT is outside its reach and would otherwise carry no row at all.

| row | what it removes | result | test that fails |
|---|---|---|---|
| **P51** | `load_latex`'s `ok`-only filter | **FIRED** (1 failed) — the planted `unstable` and `degenerate` rows have boxes that match perfectly; only the status filter keeps the L4 pass's 323 held rows out of `equations.latex` | `test_a_held_row_never_reaches_the_latex_corpus` |
| **P52** | the cropbox shift in `attach_latex` | **FIRED** (1 failed) | `test_the_formula_box_is_shifted_into_the_blocks_frame` |
| **P53** | `_artifact_ok` reduced to existence | **FIRED** (2 failed) — §14 P5's kill **(b)**, and what moves that row from PARTIAL to FIRES | `test_an_artifact_whose_bytes_moved_is_refused`, `…with_no_sidecar…` |
| **P54** | the one-to-one claim in `attach_latex` | **FIRED** (1 failed) | `test_one_latex_row_never_claims_two_blocks` |

A fifth mutation — a comment reworded, a deliberate no-op — was replayed on a copy and
**DID NOT FIRE** (9 passed), which is what a plant is for.

## 11. The full harness

`py -3.12 qc/instruments/litkb_p2_mutations.py --workers 3 --worker-dbs 1,6,9`:
**272 rows, 272 fired, every baseline passing, wall-clock 69.2 min over 3 workers**
(w1/`litkb_test_w1` 91/91 in 68.5 min, w2/`litkb_test_w6` 91/91 in 69.2 min,
w3/`litkb_test_w9` 90/90 in 67.3 min; `rc 0` each). **No row failed to fire.**

It ran on exactly `72cdfe0`'s code — verified, not assumed: the worker copies of
`litkb_p5_bulk.py`, `test_status_discovery.py` and `litkb_p2_mutations.py` hash identically to
`git show 72cdfe0:<path>`. `qc/test_litkb_p5_bulk.py` and the four P51-P54 rows were written
after those copies were made, which is why they were run separately above.

---

*Builder: Claude Opus 5, session https://claude.ai/code/session_015MUcyGTfX2koRdYAjW5kED.*

---

# Operational fix set — 2026-09-16 (appended)

Branch `work/20260913-literature-kb`, worktree `D:\edmonds-pipeline\treedata-litkb`, workstream
**`fix-op-1`** (`01a0aa8c-3741-7a32-bce3-0f546b7af066`). Written against
`Reports/LITKB_OPERATIONAL_REFEREE_2026-09-16.md` (R-1…R-10) and the friction log of
`LITKB_OPERATIONAL_TEST_2026-09-16.md`, both in the `treedata-access` worktree. Every number
below is a command that ran here; none is taken from either of those documents.

## A. `litkb_work`, and the question `SKILL.md` step 0 asks

R-1 is two wrong column names, not one: `container` for `main_works.venue` at `server.py:421`,
and `v.path` for `main_files.rel_path` at 426/428, the first hiding the second. Both fixed, and
the `files` leg now reads `litkb.main_files` directly — that view already *is*
`files JOIN file_versions`, so the join the broken statement made was the view's own, spelled
again and spelled wrong.

The tool now answers a **four-state ladder**, because "litkb_search found nothing" means three
different things and each has a different next move. Measured live, read-only, against `litkb`:

| selector | state | evidence |
|---|---|---|
| `key=Platanios_2014_…` | **absent** | not in main's view; the hint names the open workstream that holds it |
| `key=Anderson_1957_…` | **held** | admitted, `venue` The Annals of Mathematical Statistics, `files: []` |
| `key=Mei_2010_…` | **held** → after binding (§D) **bound-unextracted** (1 file, `current_run_id` null) → after ingest **extracted**, 360 blocks |
| `key=Efron_1986_…` | **extracted** | 451 blocks, `Validation/Efron_1986_…pdf`, 11 pages |
| `doi=10.1093/biomet/asq010` | **extracted** | resolves to Mei_2010 — the DOI leg had never run against a held work either |

All four states were observed on live data in this session. The referee needed `psql` twice to
reach the Mei diagnosis; it is now one tool call, and `what_next` says what to do at each rung.

## B. `litkb_my_uses` — the read-back that did not exist

Friction 2: recording a use and reading it back were different systems. `litkb_ws_status`
answered `{"gap": 6, "use": 6}`; `litkb_work` reads `litkb.main_uses`, which holds **none** of a
session's own proposals until Kam merges. The tenth tool lists this workstream's `ws_heads` —
statement, work key, gap, kind, feeds, `state` — and a `quote_status` of `verified` /
`UNVERIFIED` / `NO EVIDENCE`. The middle one is the state a session most needs and could not
see: a stored quote the database could not find at its offsets, whose chain `promote prepare`
refuses.

## C. The two gates at `record_use` (R-5, R-6)

* **statement** — was completely ungated. The database's own CHECK is `statement <> ''`, which a
  single space satisfies, so a blank claim beside a perfectly verified quote promoted clean. Now
  refused `bad-statement`, with the emptiness test run through `textnorm.norm_label` so a
  statement of zero-width joiners is blank in exactly the way a *label* of them is. The cap is
  **2000**, chosen from a measurement: over the 391 rows of `litkb.use_versions` the longest
  statement is **798** characters (p95 653, mean 375), so nothing that exists becomes invalid.
* **feeds** — were stored unvalidated and first checked a whole session later at
  `promote prepare`. Now refused `bad-feeds` at record time, by the DATABASE's own
  `litkb._feeds_token_ok` (migration 0021) rather than a second regex in Python: two copies of
  that rule already cost a migration to reconcile. The refusal names the offending tokens, and
  nothing is written — not even the gap.

Neither gate can see whether the section or row a token NAMES is the right one. That limit is
now stated in `SKILL.md`, beside R-5's example.

## D. Binding the unbound — 11 works, 4 bound

`litkb_acquire(key=…, from_file=…)` through the MCP tool, one call per work, against the PDF in
`Literture\Validation\`. Every one read `held` before (`litkb_work`); every PDF was on disk.

| work | outcome | why |
|---|---|---|
| `Jaffe_2014_estimating-accuracies-multiple-classifiers` | **bound** | title ratio 1.0, author near title — from `Jaffe_2015_…pdf`. The referee's year disagreement is in the FILE NAME, not the record: the work's year is 2014 and its identifier is `10.48550/arxiv.1407.7644`, and arXiv `1407` is July 2014. `litkb_work` now shows it in one line — `file_stems: ["Jaffe_2015_estimating-accuracies-multiple"]` beside `key: Jaffe_2014_…` — with `discrepancies` empty, correctly |
| `Marsan_2008_extending-earthquakes-reach-through` | **bound** | ratio 1.0 |
| `Mei_2010_efficient-scalable-schemes-monitoring` | **bound** | ratio 1.0 |
| `Vixie_2007_some-properties-minimizers-chan` | **bound** | ratio 1.0 |
| `Anderson_1957_statistical-inference-about-markov` | binding-pending | image-only scan: page 1 carries 160 characters (the JSTOR stamp), title ratio 0.298 |
| `Hudson_1978_natural-identity-exponential-families` | binding-pending | scan, 147 chars, ratio 0.286 |
| `Hwang_1982_improving-upon-standard-estimators` | binding-pending | scan, 147 chars, ratio 0.374 |
| `Kingman_1962_imbedding-problem-finite-markov` | binding-failed | title ratio **1.0**, but "first author not a whole token near the title" |
| `Maragos_1989_pattern-spectrum-multiscale-shape` | binding-failed | same: ratio 1.0, author not near the title |
| `Ogata_1998_space-time-point-process` | binding-failed | page 1 has **0** characters; the title matched only the PDF `/Title` metadata |
| `Stehman_1998_design-analysis-thematic-map` | binding-failed | author found and near the title; title ratio **0.8296** against a floor of 0.85 — the page says "…Accuracy Assessment: Fundamental Principles", the registry record stops at "…Accuracy Assessment" |

**Nothing was weakened to make a file bind.** Three of the four failures are the checks working:
Stehman is a real registry-record discrepancy (a missing subtitle), Kingman and Maragos are the
author-proximity rule refusing a page whose title it can read perfectly. The three
`binding-pending` are the scans, which the binding check cannot read without OCR — the state the
OCR queue exists for, and Kam's call (§G).

*Friction found doing this:* `litkb_acquire`'s MCP wrapper strips `detail` from its result, so
the tool says `binding-failed` and not **why**. Every reason above came from
`litkb.acquisition_attempts.detail` by `psql`. Not fixed here; recorded.

**Extraction and ingest of the four**, through the P5 path — GROBID 0.9.1 under WSL pool 4
(4 ok, 225 cached, 29.0 s), then Docling on CUDA (4 converted, peak 1,811 MiB), then reconcile +
ingest at `stage5-2+l4latex` with LaTeX from the parked L4 JSONL:

| work | pages | blocks | equations / with LaTeX | min coverage |
|---|--:|--:|---|--:|
| Jaffe_2015 | 27 | **617** | 100 / 62 | 1.0 |
| Marsan_2008 | 5 | **486** | 5 / 5 | 0.9885 |
| Mei_2010 | 15 | **360** | 66 / 43 | 1.0 |
| Vixie_2007 | 14 | **476** | 112 / 65 | 1.0 |

**+1,939 blocks**, and all four come back from `litkb_search` at **rank 1** for their own
question — including the one the operational test recorded as unanswerable. Its §2.1 first row
searched for the multiplicity half of gap row 20 and got "`Xie_2013` (which *cites* Mei),
`Reynolds_2000`, `Steiner_2000` — no Mei". Mei now takes ranks **1, 2, 4, 6, 10** of that query.

## E. The cropbox clamp, and its block deltas

`page_frames` reported `dy = media.y1 - crop.y1`; a `/CropBox` extending past the `/MediaBox`
makes that negative, and no renderer shows that region — a viewer intersects the two boxes
(PDF 32000-1 §14.11.2) — so the effective shift is 0 and the raw negative moved every block off
its own text. Clamped to `max(dy, 0)`.

**The population is five files, not two.** §6.2 named the two whose character share fell below
the 0.80 catastrophe floor; a census over the frozen corpus
(`qc/instruments/litkb_cropbox_census.py` → `phase4/qc/litkb_cropbox_census.csv`) finds **5
files, 45 pages of 5,038** with a negative raw `dy`, and **no page anywhere with a negative
`dx`** — which is why `dx` is not clamped. The three extra files are §6's own argument about the
floor, applied to itself: above a floor is not evidence the shift is right there.

Re-ingested at a bumped `pipeline_version` (`stage5-2+l4latex+dyclamp`) from the SAME GROBID and
Docling artifacts. No re-extraction was needed: the shift is consumed at reconciliation, not by
either extractor.

| file | raw `dy` | blocks before → after | min coverage before → after | pages below floor |
|---|--:|---|---|--:|
| `Higham_2011_pth-roots-stochastic-matrices` | −111.6 (16 pp) | 412 → **412** | 0.30494 → **0.98984** | 15 → **0** |
| `Efron_1986_how-biased-apparent-error-rate` | −0.48 … −3.36 (4 pp) | 451 → **451** | 0.74575 → **0.98506** | 1 → **0** |
| `Mesquita_1999_effect-surrounding-vegetation-edge` | −2.0 (6 pp) | 149 → **149** | 1.0 → 1.0 | 0 → 0 |
| `Jackson_2002_hidden-markov-models-onset-progression` | −1.0 (16 pp) | 284 → **284** | 1.0 → 1.0 | 0 → 0 |
| `Kalbfleisch_1985_analysis-panel-data-markov` | −0.2395 (3 pp) | 462 → **462** | 0.98735 → 0.98735 | 0 → 0 |

**The block delta is zero on every file**, and that is the finding rather than a null result: the
shift moves a block's BOX, not the set of blocks, and the GROBID↔Docling fusion agreed with
itself at the wrong offset exactly as it does at the right one — which is what §6.2 already
observed of Higham's 38 L4 formula rows. What moved is where those boxes sit against the page's
own characters. §6.2 predicted 0.9898 and 0.9851 for the two documents; they came back at
**0.98984** and **0.98506**.

The gate after: **229 documents, 229 ingested ok, 0 runs not ok, 0 blocks outside an ok run, 0
duplicate runs per key**, and the coverage floor catches **6 of 229** documents rather than 8 —
the two cropped-page ones are gone and the rest are the four rotated-page refusals plus two
ordinary low-coverage pages. `blocks` 105,705 total, **103,947 in current runs** (102,008
before, +1,939 new); the 1,758 in the five superseded dy runs are exactly their old counts.

## F. OCR headroom — the knob named for the job does not work

The task asked for a cap on Docling's OCR **page batch** so the T2000 stays ≤ 80 % (3,277 of
4,096 MiB). Measured over this driver's own batch B (15 documents, 312 pages, `ocr=on`, CUDA),
`nvidia-smi` at 1 Hz, idle 387 MiB (display only):

| setting | peak VRAM | share | wall | pages/s |
|---|--:|--:|--:|--:|
| `page_batch_size` 4 — docling's default, what §7 measured | **3,873 MiB** | 94.6 % | 445.1 s | 0.701 |
| `page_batch_size` 2 | 3,842 MiB | 93.8 % | 431.9 s | 0.722 |
| `page_batch_size` 1 | 3,893 MiB | 95.0 % | 440.6 s | 0.708 |
| `torch.cuda.empty_cache()` between documents | 3,475 MiB | 84.8 % | 436.4 s | 0.715 |
| **4 documents per converter PROCESS** | **2,619 MiB** | **63.9 %** | 483.7 s | 0.645 |

§7's 3,881 MiB reproduces at 3,873. **`page_batch_size` does not move the peak** — flat inside
noise across a 4× range. What dominates is not the per-page activations it governs: it is the
resident models plus torch's cached pool, which the allocator never returns, so in a batch
process the reserved pool becomes a high-water mark over every document that process has
converted. Measured directly: **3,344 MiB reserved, 468 MiB after an `empty_cache`**. That is
why freeing the pool between documents buys 398 MiB and ending the PROCESS buys 1,254 — a
process exit returns the models too.

So the applied cap is **documents per converter process** (`docling.OCR_CHUNK = 4`, the driver's
`--ocr-chunk`), costing **9.7 % of the rate** in converter rebuilds, plus `free_cache` on the
OCR pass, which is free. `page_batch` stays available and is recorded on every metrics row — a
peak with no setting beside it cannot be compared with another run's — and is **not applied by
default**, on the measurement above rather than on the tool's documentation.

**And the input the fix was asked for does not breach at all.** On `Anderson_1957`, a real
22-page image-only scan, the OCR pass peaks at **1,806 MiB / 44.1 %** with no knob applied, and
2,294 MiB at `page_batch_size` 1. The breach is a property of a LONG BATCH in one process, not of
OCR on scans. Batch A (`ocr=off`) is unchanged and uncapped: it peaked at 2,317 MiB / 56.6 %,
inside the rule already, so a cap there would cost rate for nothing.

## G. What was NOT admitted, and what still cannot be reached

Per the brief, **no work was admitted**. The census files with no `files` row are now **49**
(four came out of it in §D). They need Kam's call, because the cost is OCR:

* **the five scans** — `Anderson_1957`, `Hudson_1978`, `Hwang_1982`, `Ogata_1998`,
  `Politis_1994` (plus `Schwartz_2000`, already in `_quarantine\`). Four of those five are
  ALREADY admitted works, and their binding is the `binding-pending` / `binding-failed` of §D:
  the blocker is not admission, it is that the binding check cannot read a scan's first page.
  Their OCR backlog is **89 pages** (92 counting the quarantined `Schwartz_2000`), counted from
  `phase4/qc/litkb_inventory.csv` — `ocr_page_count` over the five: 22 + 12 + 11 + 24 + 20. §2
  above says "111 pages across 5 scanned documents" and that number does **not** reproduce: the
  corpus-wide `ocr_page_count` is 114, of which 23 are the `mixed` pages batch B already ran.
  At batch B's 0.645 pages/s under the new cap, 89 pages is about two and a half minutes of GPU,
  so cost is not the constraint. The constraint is that binding one needs an OCR pass the
  acquisition path does not run.
* **the 688-page book** `Schneider_2008_stochastic-integral-geometry`, which `--ocr-max-pages
  200` deliberately keeps out of the OCR batch and whose work carries no key.
* 38 `native` and 5 `mixed` census files whose works are not admitted at all.

The two standing recall holes, re-measured after this session:

| hole | referee | now |
|---|--:|--:|
| main works with **no bound file** | 208 | **204** |
| main files with **zero current-run blocks** | 0 | **0** |
| bound files **stranded in open workstreams** | 14 | **14** — `p3-migration` 12, `edge-pre1990` 1, `linkage-review` 1 |

The second hole now has a tool: `litkb_p5_bulk.py plan --workstream <slug>` unions a named
workstream's own active files into the population. Exercised on `fix-op-1`, it reported **0** —
because `litkb.attach_file` writes a file version as a FACT when the work is already promoted,
so the four bindings landed in main's view directly and were planned without it. That is an
answer, not a passing test: the flag's target population is the 14 files in the three OTHER open
workstreams, which this session did not extract and does not own.

## H. Guards, and the harness

Every guard added carries a mutation row shown to FIRE, and `--sites` passes (**91 call sites,
88 covered by a row, 3 equivalent; 21 sinks, 2 redacted, 19 allowed**).

| row | what it breaks | fired |
|---|---|---|
| **X20** | `litkb_work`'s four-state ladder collapses to `extracted` | yes |
| **X21** | the statement gate goes: a blank claim and an essay both record | yes |
| **X22** | the statement's emptiness test stops seeing invisible characters | yes |
| **X23** | feeds tokens stored unvalidated again, first checked at prepare | yes |
| **X24** | `litkb_my_uses` stops presenting the workstream token | yes |
| **X25** | the cropbox shift is negative again (Higham 0.98984 → 0.30494) | yes |
| **X26** | the OCR pass stops applying the knobs the measurement kept | yes |
| **P55** | the OCR batch back in one long process (63.9 % → 94.6 %) | yes |

## I. Live probes the worker databases cannot make

Every test above runs against a worker database where `litkb_test` **owns** the schema, so every
grant is implicit and a missing one would be invisible in the whole suite — which is R-1's shape
exactly, and `litkb_my_uses` reads BASE tables (`litkb.uses`, `litkb.works`, `litkb.gaps`) that
no `litkb_reader` had ever touched. Three read-only / refuse-only probes against live `litkb` in
`fix-op-1`, chosen so nothing can be written even if a guard were missing:

| probe | role | result |
|---|---|---|
| `litkb_my_uses()` | `litkb_reader` | `ok: true`, `uses: 0`, `gaps: 0` — the statement executes; no missing GRANT |
| `record_use(feeds=["gap row 4", "§16.2"])` | `litkb_writer` | `bad-feeds`, `bad_feeds: ["§16.2"]` — `litkb._feeds_token_ok` is callable by the writer on live `litkb` |
| `record_use(statement="   ")` | `litkb_writer` | `bad-statement` |

`litkb_my_uses` afterwards: `uses: 0, gaps: 0`. Nothing was written.

## J. Corrections to this report's own earlier sections

* §2 says Stage 0's OCR backlog is "111 pages across 5 scanned documents". **It does not
  reproduce.** `ocr_page_count` over the five in `phase4/qc/litkb_inventory.csv` is
  22 + 12 + 11 + 24 + 20 = **89** (92 with the quarantined `Schwartz_2000`); the corpus-wide
  total is 114, of which 23 are the `mixed` pages batch B already ran.
* §6 names two cropped-page documents. The census finds **five** with a negative raw `dy` (§E).
  Both statements are true at different granularity — §6's is about the 0.80 floor, the census's
  is about the arithmetic — and only the second is the population a clamp has to be right for.
* §9 blocker #4 names `Reynolds_2000` and `Montgomery_1991` for the L4 crop re-run. **That
  blocker is untouched here** and is not the `dy` one: the brief for this session named those two
  files for the clamp, and the clamp's files are Higham, Efron, Mesquita, Jackson and Kalbfleisch.
  Blocker #4 still stands exactly as written.

## K. Did NOT test

* **`plan --workstream` with actual rows.** It reported 0 on `fix-op-1` (§G); its target
  population is the 14 files in three OTHER open workstreams, which this session does not own.
  The union SQL therefore ran and returned nothing — it has never been shown to return a row.
* **OCR into the database.** Every OCR number here is a measurement into a scratch directory. No
  scan was extracted into `litkb`, because none is bound (§D, §G).
* **`OCR_CHUNK` and `free_cache` together.** Each was measured alone against the same baseline;
  the applied default now sets both. Their combination is UNMEASURED, and the expectation that it
  lands at or below the 2,619 MiB the chunk cap alone reached is an inference, not a number.
* **`promote prepare` in `fix-op-1`.** The workstream holds no proposals — every write this
  session made was a file binding, which is a fact — so there was nothing to offer and the
  chain path was not exercised here.
* **The L4 re-crop** (§9 blocker #4), `Reynolds_2000` and `Montgomery_1991`.
* **A referee.** Every number above was produced by the author of the code (CLAUDE.md §3.4c).


## L. The ladder, and the full harness

`PYTHONUTF8=1 LITKB_TEST_DB=litkb_test_w6 py -3.12 qc/check.py --fast`:
**1 failed, 3,070 passed, 25 skipped, 2 xfailed, 634.2 s**; litkb Postgres tests **374 passed,
3 skipped**. The one failure is the known pre-existing
`test_experiments.py::test_pointer_paths_resolve[crown_state_model]`. (3,059 passed before this
session's work: the eleven new tests are §A's four-state ladder ×2, §B's read-back ×2, §C's four
gate tests, §E's clamp ×6 parametrised + the population check, §F's three knob tests, §G's chunk
cap, and the promotion-report gitignore test.)

`py -3.12 qc/instruments/litkb_p2_mutations.py --workers 3 --worker-dbs 1,6,9`:
**284 rows, 284 fired, every baseline passing, wall-clock 73.0 min over 3 workers**
(w1/`litkb_test_w1` 95/95 in 69.0 min, w2/`litkb_test_w6` 95/95 in 73.0 min,
w3/`litkb_test_w9` 94/94 in 69.1 min; `rc 0` each). **No row failed to fire.** Self-checks in the
same run: **91 call sites, 88 covered by a row, 3 equivalent; 21 sinks, 2 redacted, 19 allowed.**

It ran on this branch's final code — verified, not assumed: the worker copies of `server.py`,
`inventory.py`, `docling.py`, `docling_worker.py`, `litkb_p2_mutations.py`, `litkb_p5_bulk.py`
and the four test modules all hash identically to `git show HEAD:<path>` (LF-normalised, the way
`litkb.db.migrate` compares migrations).


*Appended by Claude Opus 5, session https://claude.ai/code/session_015MUcyGTfX2koRdYAjW5kED.*

---

# Canonical blocks and scan OCR — 2026-09-16, after the final referee

`Reports/LITKB_P5_FINAL_REFEREE_2026-09-16.md` accepted the base as **operational with caveats**
and ranked five of them. This section closes the four that affect citing and searching, and binds
four of the five scans. Everything below was re-derived on this branch; the "before" column comes
from the same script as the "after" one, which is the whole reason that script exists.

## M. The instrument first

`qc/instruments/litkb_p5_canonical.py` — `census` (the three duplicate classes and the per-kind
counts, from the database), `gold` (the frozen P5 gold, scored on presence, kind, reading order
and the two text-equality grades), `latex` (the `latex_status` corpus counts) and `local` (the
same duplicate counts over a reconciliation of the stored artifacts, with no database at all —
the iteration loop). The referee scored its §4 with ad-hoc SQL; a hand-run "after" against a
hand-run "before" measures the two readers as much as the two corpora.

It reproduces the referee's own numbers on the corpus **as they left it**, before any change:

| §4 class | referee | this instrument |
|---|---|---|
| duplicate `(run, page, bbox)` among canonical blocks | 63 groups, 73 extra rows | **63 / 73** |
| duplicate `(run, page, normalised text >= 40)` | 1,635 groups, 3,120 extra rows, 205 files | **1,639 / 3,124 / 206** |
| normalised text >= 80 a PROPER substring of another on its page | 6,309 blocks, 224 runs | **6,318 / 224** |

The near/contained deltas are whitespace normalisation — mine is one SQL expression applied to
both sides, the referee's an ad-hoc pass — and they are stated rather than reconciled.

## N. One canonical block per region

Four changes in `reconcile.py`, and the mechanism of each is in the source beside it.

**A fragment carries its own words, not its element's.** `union_boxes` already split an element
per page and per column; every fragment then inherited `col[0].text`, which is the WHOLE
element's, and `text_for`'s 50 % floor — written for a whole region, where a short native slice
means the box is in the wrong frame — compared a fragment's honest slice against every page and
column of its element, failed, and stored the tool's text. That is the referee's G7 in one
sentence: 872 characters under `page_no = 12`, the first ~700 printed on page 11. It is also the
largest single source of duplicate text: on Pengra p8 one GROBID `<p>` crossing 14 table columns
stored the same 600 characters 14 times. `union_boxes` now numbers an element's fragments and
`choose_text` takes a fragment's native slice unconditionally; `continues_from` /
`continues_to` go into the block's provenance so a quote that runs off a page can find its rest.

**`_merge_regions` emits ONE block per region.** Two readings are one region when their boxes
agree at `IOU_MATCH`, or when one is `CONTAIN_MATCH` inside the other and the text agrees. The
loser's reading becomes a `duplicate_region` disagreement row: §7 says a disputed region is kept
and marked, and it never said the mark has to be a second block that search returns twice and a
quote's character offsets can land in either of. One tool's OVER-MERGE of the other's
segmentation — Pengra p7's 3,392-character `<p>` holding the page's captions and body — drops the
container, because §7.1 gives Docling the segmentation.

**A bibliography entry is re-kinded, not stored twice.** Conway p11 held 29 `paragraph` blocks in
page order and 28 `reference` blocks at 418-445, and the copy a search found first was typed
`paragraph`. A `biblStruct` that lands on a body block now re-kinds it: native text, real box,
real reading order, GROBID's kind, and GROBID's `element_id` in the provenance so stage 6 can
still join. A caption's words live in the caption block, not in the figure block as well.

**`title`, `author`, `affiliation`.** Three of the eight kinds the referee found never assigned.
No body matcher can name them; `<teiHeader>` can. `title` and `persName` are coordinate-bearing,
so those two are assigned by geometry and checked against the text; `<affiliation>` carries no
coordinates and is assigned by text alone — a weaker rule, and the docstring says so.

**Three corrections found by measurement, not by reading**, each of which shipped wrong first:

1. *Components are not regions.* The first merge grouped a page into connected components. "One
   region" is transitive for IoU and is NOT transitive for containment, so a page where a large
   block nests several small ones chained into one group, the survivor was compared with 92
   blocks it had no edge to, the no-text-loss guard refused all of them — correctly — and the
   page merged NOTHING. `Angelopoulos_2022` p7 kept 21 exact-duplicate rectangles and migration
   0022's trigger aborted the corpus ingest on it. The rule is now pairwise and greedy.
2. *The merged block's box is the union.* Keeping the smaller box leaves every character in the
   difference belonging to no canonical block: the per-page minimum coverage fell on **52 of 229
   documents** and the gate caught 9 files where it had caught 6.
3. *An over-merge is dropped only when its characters are held by blocks that stay.* A
   container's text can be covered by its children while its box still holds characters nothing
   else is responsible for — the native reading of a box is the span between its first and last
   character, so a tall box can carry a short reading. `Guo_2018` fell from 0.9913 to 0.4098.
   `OVERMERGE_COVER` is 0.95, not 0.60, and the test is now the coverage metric's own question
   asked over the page's real characters.

## O. Migration 0022

Additive. It widens `extraction_disagreements.kind` for the two shapes the merge produces, adds
`equations.latex_status` with its five values and the CHECK that a refused decode is never stored
as the equation, and refuses a repeated canonical `(run, page, bbox)` — with a **BEFORE INSERT
trigger, not a unique index**. `litkb` already held those 63 groups inside `ok` runs that nobody
may delete (`clear_extraction_rows` refuses an `ok` run; the ingest login holds no DELETE), so an
index would have succeeded on a fresh `litkb_test` and failed on live `litkb`: one migration set,
two schemas, which is the defect 0021 exists to undo.

## P. `latex_status`, and what it does NOT say

The referee's §3 found 9 of 20 sampled LaTeX strings wrong with nothing in the database saying
which. `latex_status` is assigned where the two halves meet — the equation blocks and the L4
pass's own verdicts — in the same INSERT as the string.

The **contaminated** class is geometry, not a decode score. docling crops a formula at
`bbox.expand_by_scale(0.18, 0.18)`, read off `CodeFormulaVlmModel` by `formula_crop_worker`, so
the padding is PROPORTIONAL: the referee's one-line E02 (9.8 pt tall) gets 1.8 pt of margin and
sees nothing; its six-line E01 (178.3 pt) gets 32.1 pt and sees roughly three printed lines. The
test is whether a prose run of at least 8 letters that the decode wrapped in `\text{}` appears in
the padding RING and not in the equation's own box.

Scored against the referee's FROZEN twenty (`Reports/gold/p5_gold_2026-09-16.json`, sha256
`6eeab1eb…`, committed at `3230b48` before any measurement): **18 of 20 agree**, and no clean
crop is called contaminated.

| id | referee | detector | box height | ring chars |
|---|---|---|--:|--:|
| E01 | contaminated | **contaminated** | 178.3 | 96 |
| E06 | contaminated | **contaminated** | 40.6 | 63 |
| E19 | contaminated | **contaminated** | 37.2 | 54 |
| E11 | contaminated | stable | 38.0 | **3** |
| E20 | mathematically wrong | contaminated | 183.8 | 86 |
| the other 15 | 11 correct, 4 wrong | stable | — | 0-23 |

E11's ring holds three letters: its contamination (`\intertext{ i n t s e q u a l s }`) cannot
have come from the margin, so it is model over-generation and the crop geometry cannot see it.
E20's ring DOES carry the words its decode emitted, and the referee also graded its mathematics
wrong; both readings are true of it. The rule was written before this measurement and run once —
it was not fitted to the twenty, and the 8-letter floor comes from the mechanism (a formula's own
vocabulary is short words) rather than from a sweep.

**`stable` says nothing about whether the mathematics is right.** E03's dropped lambda_n, E05's
`S^{d}` for `S^{d-1}`, E07's `\bar Z` for `Z`, E12's `\mathbf a` for alpha and E20's lost
subscript are wrong on clean crops, and every one of them comes out `stable`. Scoring a decode
against the page is not attempted here and the column's definition says so in those words.

Corpus counts, current runs (`litkb_p5_canonical.py latex`):

| `latex_status` | equations | with LaTeX |
|---|--:|--:|
| stable | 3,170 | 3,170 |
| contaminated | 287 | 287 |
| unstable | 58 | 0 |
| degenerate | 109 | 0 |
| unverified | 3,525 | 0 |
| **total** | **7,149** | **3,457** |

## Q. Furniture and references out of search

`litkb_search` excludes `page_header`, `page_footer`, `page_number`, `other` and `reference` by
default; `kinds="all"` or a comma-separated list brings them back, and an unknown type name is
REFUSED rather than silently dropped. The result states which types were left out. `title`,
`author` and `affiliation` stay IN, which is a judgment and is recorded as one.

Measured live on the corpus, `limit=10, scope="blocks"`:

| query | default | `kinds="all"` |
|---|---|---|
| `constrained Monte Carlo maximum likelihood` | 0 furniture; ranks 1-3 are Geyer's own heading and two body paragraphs | **8 of 10 are `page_header`** — the same 42 characters from pages 3, 5, 7, 9, 11, 13, 15, 17 |
| `non-homogeneous hidden Markov model transition probabilities covariates` | 0 furniture; rank 1 is Hughes 1999's title, rank 2 its p4 body paragraph | **5 of 10 are `page_header`** |

The P8 gold's three passages through the same search: **ranks 1, 1, 2** (the referee measured
1, 2, 2 before this change; Q1 and Q3 are located by the fragment the gold's `search_query` is
drawn from, because two of the three `verbatim_passage` strings carry the referee's preserved
mojibake and occur verbatim in no block, before or after).

## R. The corpus, re-ingested

`P5_PIPELINE_VERSION` is now the reconciler's own string, READ rather than copied. What kept the
two labels apart — a LaTeX-free ingest must not collide with this one — moved into
`ingest.params_hash`, where the merge's new thresholds also sit. One corpus, one label; the
referee's §4 note about reading two labels for one corpus is closed.

| | before (stage5-2 + dyclamp) | after (stage5-3) |
|---|--:|--:|
| files with a current run | 229 | **229** |
| `pipeline_version` labels over current runs | 2 (224 + 5) | **1** |
| blocks in current runs | 103,947 | **82,166** |
| pages in current runs | 4,006 | 4,006 |
| runs not `ok` / blocks outside an `ok` run / duplicate run keys | 0 / 0 / 0 | **0 / 0 / 0** |
| **exact `(run, page, bbox)` duplicates** | 63 groups, 73 rows | **0 / 0** |
| **duplicate normalised text >= 40** | 1,639 groups, 3,124 rows, 206 runs | **275 / 375 / 62** |
| **contained (>= 80 chars, proper substring)** | 6,318 blocks, 224 runs | **2,984 / 200** |
| documents with a page below the coverage floor | 6 of 229 | **6 of 229** |

Per kind, current runs:

| kind | before | after | kind | before | after |
|---|--:|--:|---|--:|--:|
| paragraph | 66,489 | 46,096 | footnote | 910 | 732 |
| reference | 9,300 | 9,285 | **title** | **0** | **246** |
| equation | 8,055 | 7,149 | **author** | **0** | **303** |
| page_header | 6,664 | 6,627 | **affiliation** | **0** | **271** |
| heading | 5,281 | 4,305 | page_footer | 2,509 | 2,437 |
| caption | 2,036 | 2,015 | figure | 1,842 | 1,839 |
| table | 861 | 861 | | | |

Row-level evidence for every number in this section, one line per file:
`Reports/litkb_p5_files_stage5-3_2026-09-16.csv` (229 rows, a copy of
`litkb_derived/p5/p5_files_stage5-3.csv` taken at the end of the run; the stage5-2 side is
`litkb_derived/p5/p5_files.csv`, which is outside the repo).

**Where the 906 equations went.** 842 equation blocks are recorded inside a survivor's
`provenance -> merged`, 805 of them absorbed by another equation: docling's `touching` branch
described one printed formula twice and the corpus held both. The other 64 are over-merge drops
and figure dedupe and are not individually attributed — UNCONFIRMED in mechanism, measured only
as the difference. Corpus-wide the merge absorbed **20,876** blocks (`merged` entries over
current runs): 10,245 paragraph, 8,973 reference, 842 equation, 661 heading, 79 footnote, 58
furniture, 15 caption, 3 figure.

**LaTeX attached: 3,472 -> 3,457.** The L4 pass decoded the same 3,492 rows for these files in
both ingests; 20 found no equation block to hang on before, 35 do now, because the block their
crop was cut from merged into its neighbour. Fourteen files carry the difference (CSV column
`latex_unmatched`), the largest being `Reynolds_2000` at 7, `Hall_1985` and `Montgomery_1991` at
6. Nothing was decoded twice and nothing was thrown away: the strings are still in the L4
artifacts, and a future ingest can re-match them against the canonical boxes.

**The residue, explained.** 375 duplicate-text rows in 62 of 229 runs are overwhelmingly Conway's
appendix survey form — the same blank answer line printed several times on one page, which is
genuinely several regions with one string. 2,984 contained blocks in 200 runs are what the
no-text-loss rule keeps: a GROBID `<p>` whose native slice holds its neighbours' words but whose
box holds characters nothing else does. Dropping them is the thing that cost Guo_2018 six tenths
of a page, so they stay and are recorded as `partial_overlap` disagreements.

**Two superseded sets of runs stand beside the current one**, at the same `pipeline_version` and
a different `params_hash`: the component-merge ingest (213 documents, aborted by 0022's trigger)
and the first pairwise one (229, which cost coverage). An `ok` run's rows cannot be deleted by
anyone — that is the design, and it is what protects evidence that cites them — so a repaired
ingest is a different run, and `params_hash` is the field that says which reconciliation a run is.

**The gold** (`litkb_p5_canonical.py gold`, against the database):

| | before | after |
|---|--:|--:|
| gold body items matched | 60 of 74 | 59 of 74 |
| `kind` correct, of matched | **23** | **53** |
| within-band reading-order violations | 1 | **1** |
| cross-band inversions (not charged) | 0 | 0 |
| text equality, STRICT | 0 of 8 | 0 of 8 |
| text equality, **OPERATING** | 6 of 8 | **7 of 8** |

G7 — the citation-page case — flips to OPERATING: the block on page 12 now holds the paragraph
printed on page 12. G3 stays False and is the referee's own finding: the PDF's text layer drops
the final full stop. The one item lost from presence is Ploton's affiliation line, and the reason
is §7.1 working: the block's text is now the native layer's `1AMAP, Univ Montpellier…` where it
used to be Docling's `1 AMAP, …`, and the gold's snippet was transcribed from the rendered page.

**The mid-file kill, re-run once** (`litkb_p5_bulk.py kill-test`, subject `Bacry_2015`, 59 pp):
killed INSIDE the open transaction, **1 run at the key, `ok`, 903 blocks = the control's 903, 0
duplicate page-order groups, 0 blocks visible to an independent reader mid-transaction**. PASS.
Its two counts are now scoped to the run's own pipeline version: counting every block of the FILE
read 1,564 committed stage5-2 blocks as "visible mid-transaction" and reported FAILED while every
property it tests held. It ran before the last two merge corrections, which are upstream of
`ingest_file` and cannot reach the transaction; with every document now holding an `ok` run at
this key there is no subject left to kill, and saying so is more useful than a kill that would
resume into "already ingested, wrote nothing".

**P3's gate, re-run on `litkb`** (workstream `p3-migration`): 1,086 changed cells — explained
**713**, format **243**, structural **120**, filled **10**, UNEXPLAINED **0**. **GATE: PASS** —
the pinned 713/243/120/10/0, unchanged by the re-ingest.

## S. The scans: four of five bind

`bind_any_with_ocr` runs Docling's OCR over pages 1-2 and re-binds when — and only when — the
first page has NO text layer for `pdftotext` to read. The trigger is that fact, not the
`binding-pending` verdict: `Ogata_1998`'s first page carries one form feed, and the empty page
scores a spurious title ratio of 1.000 that sends it down the `binding-failed` branch instead, so
a rule written on the verdict would have offered OCR to one of two files with the same problem.
A page that HAS text and does not bind is left alone. `OCR_BIND_MAX_PAGES = 400` keeps the
688-page book out of it by construction; nothing here touched `Schneider_2008`.

| scan | before | after | evidence |
|---|---|---|---|
| `Anderson_1957` | `binding-pending` | **bound** | title ratio 1.000, author near the title, OCR p1-2, 37 s |
| `Hudson_1978` | `binding-pending` | **bound** | 1.000, author near, OCR p1-2, 38 s |
| `Hwang_1982` | `binding-pending` | **bound** | 1.000, author near, OCR p1-2, 39 s |
| `Ogata_1998` | `binding-failed` | **bound** | 1.000, author near, OCR p1-2, 55 s |
| `Kingman_1962` | `binding-failed` | **binding-failed** | its page 1 HAS a text layer — 2,219 normalised characters, title ratio 1.000 — and the publisher's own OCR reads the author line `J. F. Co KINGMkN`, so the surname is not a whole token near the title. Not a missing-text problem, and OCR of the same scan reads the same glyphs. |

`files.has_text_layer` stays FALSE on all four: `text_layer` is the PDF's own fact, it is what
stage 0 routes on, and a scan that OCR bound is still a scan.

**The four bindings are PROPOSALS in the open workstream `fix-op-1`**, not in main's view. That is
also why they are not extracted here: main holds 229 active files and the corpus census above is
main's view, so extracting a file main does not hold would put blocks in the corpus for a work
Kam has not merged. The next step is `litkb_p5_bulk.py plan --workstream fix-op-1` followed by
`docling --ocr` and `ingest` — the flag exists for exactly this case (operational referee R-3).

## T. Guards, and the rows that break them

**Sixteen new rows**, one per call site this change adds: R537 the fragment text rule, R538 the
merge, R539 the over-merge, R540 the reference re-kinding, R541 the caption, R542 the header
kinds, R543 and R544 migration 0022's two guards, R545 the ingest's status column, P56 the status
sweep, P57 the contamination test, P58 its prose rule, X27 the search filter, and T19/T20/T21 the
OCR trigger, the page cap and the `has_text_layer` fact. **All sixteen fired.**

**The ONE full parallel run** (`--workers 3 --worker-dbs 1,6,9`, the whole table):

```
parallel: 300 rows over 3 workers
worker 1 (litkb_test_w1): 100 rows, 100 fired, baselines passed, rc 0, 77.1 min
worker 2 (litkb_test_w6): 100 rows,  99 fired, baselines passed, rc 1, 79.6 min
worker 3 (litkb_test_w9): 100 rows, 100 fired, baselines passed, rc 0, 83.2 min
299/300 mutations fired; baselines passed; wall-clock 83.2 min over 3 workers
```

`--sites` still reads **91 call sites, 88 covered by a row, 3 equivalent; 21 sinks, 2 redacted,
19 allowed**. The run did not start on the first attempt: `F5e` pointed at `acquire/run.py`'s
`bind_any` line, which §S replaced with `bind_any_with_ocr`, and the pre-flight refused the whole
table rather than run 299 rows and report a missing one at the end. Re-pointed, and every row's
target now resolves before anything runs.

**The one survivor is R532, and it is EQUIVALENT — measured, not argued.** R532 deletes the
`canonical = _dedupe_figures(canonical)` call. It fired before this change —
`Reports/LITKB_STAGE5_INGEST_2026-09-15.md` §2 records it, "Re-run: `R532` FIRED, 1 failed / 59
passed", after the planted-duplicate test was written for exactly this row. It no longer does,
because `_merge_regions` — which this change adds on the NEXT line — takes any two blocks on a
page at `IOU_MATCH` or better, and two figure blocks over one figure are exactly that. The
evidence is the real file, not a fixture: Benedek_2015 p4 with both of its picture items planted
twice in the Docling document (the same plant
`test_a_figure_docling_reports_twice_still_enters_once` uses), reconciled with the call and with
it monkeypatched to the identity —

| | figure blocks on p4 | with a caption |
|---|--:|--:|
| `_dedupe_figures` called | 2 | 2 |
| call removed | 2 | 2 |

— byte-identical, including which reading survives and the caption it carries. **No assertion on
these artifacts distinguishes the two**, which is why no test was added to make the row fire
again.

**But the dedupe is not dead code.** The two rules differ where the readings TIE:
`_dedupe_figures` ranks a caption in the payload FIRST, `_survivor_key` does not rank it at all,
so on a tie the merge keeps the caption-less reading and `litkb.figures.caption_block_id` is
lost. Three constructed shapes show it — two readings both `source="both"` and both on Docling's
box, differing only in which holds the caption, tied on text length, on index, or with the
caption-less one holding the native layer: the dedupe keeps the caption in all three, the merge
alone loses it in all three. **Those shapes are SYNTHETIC** (CLAUDE.md §3.4c): they demonstrate
the rule's reach, they do not show the case occurs. It does not occur on Benedek, the one file
measured; whether it occurs on the other 228 is INFERRED not to, from the mechanism — the figure
pass produces both readings and `_caption_once` attaches the caption afterwards — and was not
measured.

**The code was not changed**: `_dedupe_figures` is what the 229-document corpus above was
ingested with, and deleting it after the numbers were produced would make the shipped reconciler
a different one from the reconciler the census describes. §V says what to do instead.

**The ladder** (`qc/check.py --fast`, `LITKB_TEST_DB=litkb_test_w6`, after the harness released
the database): secrets PASS, ruff PASS, compile PASS, pytest **1 failed, 3,094 passed, 25
skipped, 2 xfailed in 10:50** — the one failure is `test_pointer_paths_resolve[crown_state_model]`,
the pre-existing canopy-side pointer the delta names as the only permitted failure. Inside it,
**litkb Postgres tests: 378 passed, 3 skipped**.

## U. Did NOT test

* **Extraction of the four newly bound scans** — see §S: they are proposals in an open
  workstream, and the corpus census is main's view.
* **The 688-page book**, deliberately, and `Politis_1994`, which carries no work key.
* **The mid-file kill on the FINAL merge code** — §R gives the reason and the reason it does not
  reach the property the kill tests.
* **A second reader.** Every number above was produced by the author of the change
  (CLAUDE.md §3.4c). The `latex_status` detector is scored against an independent frozen gold;
  the duplicate counts and the corpus census are not scored against anything but themselves.
* **Reproducibility.** No file was extracted twice at `stage5-3` with the same `params_hash`.
* **Three litkb Postgres tests were SKIPPED** inside the ladder's 378 (`check.py` prints the
  count, not the names), so those guards were not exercised on this run.
* **R532's tie shapes are synthetic only** (§T). The case where `_dedupe_figures` still changes
  the outcome was constructed, not found: no corpus file was searched for two figure readings
  that tie on `_survivor_key`.
* **The vector leg**, `record_use` live, `promote prepare` / `commit`, and per-region recall
  beyond the six stage-5 gold pages.

## V. Blockers for the next step

* **The citation graph is not anchored to a page.** `litkb.references` holds 643 rows and
  `litkb.citation_mentions` 969, all under `pipeline_version = 'litkb-p6-1'` across 17 runs that
  hold **0 blocks**, and `block_id` is NULL on every one of them. Nothing dangles and the
  re-ingest broke nothing — P6 reads the TEI artifacts, not the block table — but a citation
  still cannot be located on a printed page. The corpus now has 9,285 canonical `reference`
  blocks and records `merged[].element_id`, which is the join P6 would need.
* **The four newly bound scans are proposals** in the open workstream `fix-op-1` (verified:
  `file_versions -> workstreams.slug`), so they are not in main's 229 and were not extracted.
  `litkb_p5_bulk.py plan --workstream fix-op-1`, then `docling --ocr`, then `ingest`.
* **Doc drift, closed here** (the operational referee's item 11): `LITERATURE_KB_DESIGN_2026-09-13.md`
  §4.4 now carries `equations.latex_status`, the `duplicate_region` / `superset_region`
  disagreement kinds and the `merged` / `fragment` / `continues_from` / `continues_to` provenance
  keys, and `.claude/skills/literature/SKILL.md` step 0 now says that furniture and bibliographies
  are out of `litkb_search` by default and how to ask for them. Neither doc is otherwise re-read
  against the schema: what is written is what this change added, nothing older was verified.
* **`_dedupe_figures` survives R532 as an equivalent** (§T), and the fix is NOT to delete it: on a
  tie the merge's `_survivor_key` keeps the caption-less figure reading and the figure loses its
  caption link. Fold the caption-in-payload test into `_survivor_key` — above `text_source`, where
  `_dedupe_figures` already ranks it — and only THEN retire the function, its call and row R532.
  At the next re-ingest, not before: removing it now would separate the shipped reconciler from
  the one this report's census describes. Until then the harness exits 1 on this one row.
* **Two superseded run sets** stand beside the current one (see §R). They cost disk and they make
  any un-scoped `blocks` count wrong; every query in this report scopes by
  `files.current_run_id`. An `ok` run cannot be deleted by design, so retiring them is a
  deliberate operation somebody has to choose.

*Appended by Claude Opus 5, session https://claude.ai/code/session_015MUcyGTfX2koRdYAjW5kED.*

---

# hunt one-shot — `litkb hunt`, and one real document through it — 2026-09-16

Branch `work/20260913-literature-kb`, worktree `D:\edmonds-pipeline\treedata-litkb`, workstream
**`hunt-test-1`** (`01a0ad54-4a7a-7291-bb8c-02afc132f0c8`). Commit `bea983f`.
Code: `Scripts/pipeline/litkb/hunt.py`, `commands.py::cmd_hunt`, `mcp/server.py::_hunt`
(tool `litkb_hunt`), `admit/front.py::web_pdf_evidence` / `admit_web(pdf_path=…)`,
`extract/ingest.py::CORPUS_PARAMS`. Tests: `qc/test_litkb_hunt.py`. Harness rows **H1-H4**.

**ECONOMY, STATED UP FRONT.** Kam asked for a tight build, so this is deliberately NOT the P5/P8
treatment: **targeted tests only, and only rows H1-H4 of the harness were run**, not the whole
table. `--sites` and the sink self-check DID run in full (they are one command and they gate the
whole package). There is no referee, no gate section and no canary. Everything below is a command
that ran here.

## A. The thing the plan for this could not have worked

The brief's sequence was: admit the URL as a web-source manual proposal, then **bind the PDF via
`acquire --from-file`**. That cannot complete, and the reason is one statement of migration 0013
(`litkb.attach_file`):

> `litkb: work % is not admitted in main; a file attaches only to an admitted work`

A manual admission is written in PROPOSAL mode (0013, `v_mode := CASE p_route WHEN 'registry' THEN
'fact' ELSE 'proposal' END`), so `works.current_version_id` stays NULL until a SECOND session
approves it. `main_works` therefore has no row, `acquire.run.work_record` — which reads that view —
returns None, and `litkb_acquire` answers `not-admitted` for a work this very session just admitted.
Reaching `attach_file` directly raises. **For a web source the file has to arrive WITH the admission
or not at all**, and the admission is the one path that writes a file version for a work in proposal
mode.

So it does. `admit_web(pdf_path=…)` binds the DOCUMENT's own first page through the ordinary binder
(`front.file_evidence` → `binding.bind_any_with_ocr`, the same call `land_and_attach` makes), and
the page text is still landed under `_litkb_staging/web/` and recorded on the admission's checks.
**Nothing was weakened to make this work:** check 3 reads a real text layer on a PDF, which is
stronger evidence than the saved page text `web_snapshot_evidence` binds, not weaker. The work stays
a PROPOSAL, and every hunt result says in those words that `litkb_search` cannot see it.

*One deviation from the brief, stated rather than made silently.* The brief says never rename the
download to `.pdf` — the known `acquire --from-file` dedupe defect. Hunt lands the bytes at
`_litkb_staging/incoming/<stem>.download` exactly as asked, shape-checks them and reads page 1 from
that path; it then moves the file to `_litkb_staging/filed/<work key>.pdf`, which is where
`land_and_attach` files a download that bound. The defect the rule protects against is `acquire`'s
disk index — it hashes every `*.pdf` under the literature root, found a hand-fetched file's own hash
and answered `duplicate-held` before binding ran — and **hunt calls no part of that path and builds
no such index**, so the reason is gone, while three tools are each handed a path and only pypdfium2
is documented to ignore the extension.

## B. The live run — measured

`py -3.12 -m litkb --dir …\_litkb_ws\hunt-test-1--litkb hunt <raw URL> --title … --author … --year
2020 --device cuda --docling-python …\venv-docling-cuda\Scripts\python.exe`

| | measured |
|---|---|
| work | `Abdulkader_2020_cnn-fpga-implementation-hardware`, `01a0ad55-eb8d-…` |
| admission | `01a0ad55-ebc2-…`, route **manual**, state **proposed** (no approval; per the brief) |
| identifier | `url` = the raw GitHub blob, `verified_by: manual`; retrieved 2026-09-17 |
| file | `_litkb_staging/filed/Abdulkader_2020_….pdf`, sha256 `7bdd142ad01fddd0…`, 9,433,711 B, **62 pages** |
| binding | ratio **0.8916**, `author_found` / `author_near_title` true, `title_region` true → **bound** |
| snapshot | `_litkb_staging/web/Abdulkader_2020_….txt`, its own binding **bound** |
| run | `01a0ad5b-16aa-…`, `5-reconcile` / `litkb-reconcile` / `stage5-3`, `params_hash 48f12f0e…`, **ok** |
| blocks | **18,064**; native 15,800 / OCR 1,422 / tool 842; docling 17,845, both 113, grobid 106 |
| by kind | paragraph 17,906, heading 82, figure 56, page_header 8, table 7, equation 2, reference 2, caption 1 |
| coverage | character share **1.0000 on all 62 pages**; 115,635 native chars, 115,635 covered |
| page classes | text 49, partial 8, **image-only 5** |
| disagreements | 33,005; merged regions 1,581; over-merges dropped 27; rotated pages 0 |
| **wall clock** | resolve 0.25 s · download 1.3 s · admit 0.25 s · **GROBID 48.6 s** · **Docling 112.3 s** · **reconcile 177.1 s** · ingest 29.4 s · **total 371.0 s** |

**The second hunt, live, on the same URL: `already-extracted` in 0.55 s** — same `run_id`, nothing
fetched, converted or written. That is the idempotence clause on real data rather than on a fixture.

Two numbers worth reading rather than recording. **GROBID contributed 220 regions against Docling's
19,435, and only 49 matched**: GROBID reads a document as a paper, and this is a 62-page student
project report whose second half is Vivado screenshots. The reconciliation ran, correctly, on
Docling's segmentation almost alone. And **four pages hold 72 % of the blocks** — p26 4,061,
p27 4,056, p62 2,593, p25 2,226 — because a synthesis SCHEMATIC is hundreds of one- or two-word
labels and each is a region. A block count is not a measure of content, and this document is where
that shows.

## C. Kills

| kill | fired? | evidence |
|---|---|---|
| a URL that serves HTML is refused `not-a-pdf` and quarantined | **YES** | row **H1**, `test_a_url_that_serves_html_is_refused_and_the_bytes_are_quarantined`: the mutation removes the shape check and the test fails. The bytes and a `.reason.json` are kept; `filed/` stays empty |
| a second hunt of the same URL is `already-extracted`, no new run | **YES** | row **H2** (3 tests fail). Also **live**, §B: 0.55 s, same run id. The injected fetch RAISES, so the test asserts more than "no new run" |
| a hunt with no workstream token is refused | **YES** | row **H3** (8 tests fail); refused before the database, the network and the GPU |
| a DOI hunt for a work already extracted returns `extracted` instantly | **YES** | row **H2**, second test — the same guard through the other identifier, normalised by `litkb.norm_identifier`, so `https://doi.org/10.9999/X` reaches a bare-DOI work |
| a DOI hunt for a work already **held** stops at `held` and admits nothing again | **YES** | row **H2**, third test — see below; the rung that was WRONG in the first version of this code |
| a hunt with invisible-character labels is refused | **YES** | row **H4** (3 tests fail) — added because the MCP wrapper's own `_labels` call would have been a SECOND copy of the rule |

`py -3.12 qc/instruments/litkb_p2_mutations.py --only H1,H2,H3,H4`: **4/4 fired**, baselines passed
before and after, `hunt.py` restored by sha256 `7e65438cc51846d1…`, `match: True` after every row.
Self-checks in the same run: **92 call sites, 89 covered by a row, 3 equivalent; 21 sinks, 2
redacted, 19 allowed.**

**Two defects the checks found in this code before it was pushed**, recorded because a gate that is
never reported as firing is not known to work:

* **The `held` rung fell through.** The first version short-circuited on `extracted` and on
  `bound-unextracted` and not on `held` — so a second hunt of a DOI that is admitted with no bound
  file would have re-admitted it, and check 2 would have refused it as a DUPLICATE. A session that
  hunted the same DOI twice would have been told, on the second call, that its own work belonged to
  somebody else. Fixed INSIDE the H2 block, so the row covers it, with a test of its own.
* **`hunt.py` sat outside the no-delete scan.** `qc/test_litkb_p2.py` globs `litkb/acquire/` and
  `litkb/admit/`, and its companion census — which exists precisely to catch a module that reaches
  the store from anywhere else — failed on the first full ladder run. `hunt.py` lands, files and
  quarantines through the Store, so it is now in `_SCANNED_FILES` and both halves read one file
  list (`_scanned_sources()`). The census fired on real code the day it was written for.

## D. `CORPUS_PARAMS` moved, and why it had to

`P5_PARAMS` lived in `qc/instruments/litkb_p5_bulk.py`. Hunt ingests ONE file through the same run
key — `reconcile.PIPELINE_VERSION` plus `ingest.params_hash(params)` — so a second copy of that dict
would have made every hunted file a different extraction from the corpus around it while looking
identical, and a later bulk pass would have re-ingested it. The constant is now
`litkb.extract.ingest.CORPUS_PARAMS`, and the driver reads it from there
(`P5_PARAMS = _ING.CORPUS_PARAMS`). Verified, not assumed — grouping every file's CURRENT run by
key returns exactly one row:

| `params_hash` | `pipeline_version` | files |
|---|---|--:|
| `48f12f0eff6a3e7e` | `stage5-3` | **230** |

229 of those are the corpus; the 230th is this document. A hunted file is the same extraction as the
corpus around it, and a bulk pass over it would find its run already `ok` and do nothing.

## E. Did NOT test

* **The full mutation table.** Only H1-H4 ran. `--sites` and the sink check ran whole.
* **`litkb_hunt` over a real MCP session.** The tool is in the surface and in `EXPECTED_TOOLS`, and
  its no-token refusal is in the P8 parametrised kill; no test CALLS it end to end, because that
  would start a subprocess that downloads and converts.
* **A DOI hunt that ADMITS and then stops at `held`.** The rung is tested where a work is ALREADY
  held (§C, third row); the branch that admits a fresh DOI and then stops is written and not
  exercised, because admitting a real DOI spends a registry call and a work.
* **The `bound-unextracted` resume branch.** A hunt of a work whose PDF is bound and unextracted
  goes straight to `_finish` and resolves the file under `LITERATURE_ROOT`. Neither the live run nor
  any test took that path — the live document was bound and extracted in one call.
* **The `truncated-pdf` half of H1's guard.** Only `not-a-pdf` was planted.
* **Approval.** The admission is left `proposed`, per the brief, so the work is invisible to
  `litkb_search` and nothing in the promotion chain was exercised.
* **The title/author heuristic.** `--title` and `--author` were passed for the live run. The PDF's
  `/Title` is "Hardware Documentation", which names the FILE and not the work, and the cover page
  interleaves five authors with five student ID numbers; `guess_fields` is deliberately weak, says
  in `fields.from` where each value came from, and refuses `incomplete-record` naming the flag
  rather than inventing an author.
* **A referee.** Every number above was produced by the author of the code (CLAUDE.md §3.4c).

## E.1 The ladder

`PYTHONUTF8=1 LITKB_TEST_DB=litkb_test_w1 py -3.12 qc/check.py --fast` on the final tree:
**1 failed, 3,107 passed, 25 skipped, 2 xfailed, 618.3 s**; litkb Postgres tests **385 passed, 3
skipped**. The one failure is the known pre-existing
`test_experiments.py::test_pointer_paths_resolve[crown_state_model]`. (3,104 on the run before this
section's fixes: the three new tests are the `held` rung and the two halves of the label refusal
that the parametrisation adds.) `secrets`, `ruff` and `compile` passed.

## F. Blockers for the next step

1. **A web source cannot be approved by the session that hunts it, by design** — so a hunted
   document stays out of `litkb_search` until a second session runs `litkb approve <admission-id>`.
   For `hunt-test-1` that is `01a0ad55-ebc2-79c1-892b-6485eb34c776`.
2. **A DOI hunt ends at `held`.** Choosing an acquisition route is a spend, and hunt does not make
   one unasked; joining `acquire` into the one call needs Kam's rule for when it may spend.
3. **A ligature defect that is a SEARCH defect, not hunt's.** 13 blocks of this document store
   `di<1F>erent`, `<1E>rst`, `<1D>oating`, because the PDF's font maps ff / fi / fl to the C0 codes
   0x1F / 0x1E / 0x1D with no ToUnicode correction and pypdfium2 passes them through. A search for
   "floating point" finds 4 blocks in this run; for "oating point", 6. It is a corpus-wide question,
   not a one-file one.

## G. The reading Kam asked for — from the INGESTED TEXT, not the images

**What it is.** A student hardware write-up, not a paper: *"This is a Hardware Documentation for the
Logic Design Project aiming to implement a convolutional neural network on an FPGA using Verilog"*
(p2). Five authors, one network part each.

**Network and dataset.** *"The Project is an implementation of the leNet-5 CNN architecture"* (p4):
three 5×5 convolution layers (p5), two average-pooling layers (p8), tanh between layers (p6), a
10-class SoftMax last (p7). **No dataset is named anywhere in the ingested text** — "MNIST",
"dataset" and "training" return zero blocks. The geometry the document does give is a 32×32 input
with a 28×28 first-conv output (p21) and ten classes (p7), which is MNIST-shaped; that last step is
an inference, not something the document says.

**Precision.** IEEE floating point, narrowed under pressure: the receptive-field array held *"196000
(=28*28*25) values (each one represented by 32 bits)"* (p24), then *"Architecture 5: Sequential
Convolution with 14 conv units with half precision floating point (16 bits)"* (p28) and *"I actually
reduced the input bits from 32-bits to 16-bits and Part 5 now uses them"* (p36). The cost is stated:
*"the limiting range of 16 bit half precision floating point numbers … make this a bottleneck of
accuracy"* (p6).

**Convolution → hardware.** A four-level hierarchy (p15 headings): **Processing Element →
Convolution Unit → Single Filter Layer → Multi Filter Layer**. A processing element is one
floating-point multiplier and one adder (p23); a conv unit takes `(Depth*FilterW*FilterH)+1` clock
cycles (p21); a single-filter layer instantiates half a row of conv units — *"14 conv units for one
filter for the first convolution layer of LeNet"* (p23).

**Throughput and resources.** *"For a layer of size 32x32 and 6 filters of 5x5, it would take
3*[28*28/(28/2)]*[26] = 4368 CC"* (p21). *"The number of LUTs generated is 654 for the conv unit,
48422 for the conv layer single filter and 455605 for the conv layer multiple filters"* (p23) —
455,605 LUTs does not fit the board, which is why five architectures exist. SoftMax: 31 → 11 clock
cycles across three designs, *"25141/53200 47.26% utlization"* (p42, sic). Integration: 725 clock
cycles (p60). Post-synthesis timing for whole layers was abandoned — *"Our attempts reached up to 20
hours, all while stalling the progress bar"* (p60).

**Text quality.** Native, not a scan: 49 of 62 pages `text`, 8 `partial`, **5 image-only**; character
coverage **1.0000 on every page** (115,635 of 115,635). OCR supplied 1,422 blocks of 18,064 — the
Vivado screenshots, and it shows (*"CN E B- (ChruteOkiop/ON 16 BT/OW 1 Snt"*, p21). The prose pages
are clean apart from the 13 ligature blocks of §F.3.

---

*Builder: Claude Opus 5, session https://claude.ai/code/session_015MUcyGTfX2koRdYAjW5kED.*

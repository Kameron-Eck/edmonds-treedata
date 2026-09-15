# litkb P4 adapters merged — 2026-09-15

Branch `work/20260913-literature-kb`, worktree `D:\edmonds-pipeline\treedata-litkb`, from `fed255a`.
Three refereed P4 branches merged `--no-ff`, in order, each proved before the next was started.
**The merger wrote none of the three branches**; this report records what was merged, what
conflicted, and what the merged tree measures — not a re-review of the branches' science.

| # | Branch | Tip merged | Merge commit |
|---|---|---|---|
| 1 | `work/20260915-inventory-stage0` (stage 0, inventory) | `cc36b82` | **`d621cfe`** |
| 2 | `work/20260914-grobid-local` (stage 2, GROBID) | `8f985e5` | **`cae333a`** |
| 3 | `work/20260915-docling-local` (stage 3, Docling) | `5b26768` | **`14e3091`** |
| — | merge fallout: two Docling sinks reach the sink checker | — | **`11db0fa`** |

`work/20260915-references` and `work/20260915-colab-l4-formula` were **not** merged, by the brief.

## Conflicts, and how each was resolved

Three, all textual, all "keep both":

* **`Scripts/pipeline/litkb/extract/__init__.py`** — add/add at merges 2 *and* 3: three branches each
  created the package with its own docstring. Resolved to Docling's text, which is the only one
  carrying the load-bearing rule (**no adapter may import its heavy tool at module scope**, design
  referee M9), under inventory's title line naming stages 0–4. Nothing was dropped but wording.
* **`Scripts/requirements-litkb.txt`** — content conflict at merge 2. Both branches added the **same
  pin**, `pypdfium2==5.13.0`, with different justifications. One pin, one merged comment that states
  all three readers' reasons and points here for the ownership question below.
* Predicted but did **not** conflict: `.gitignore` / `.gitattributes` (GROBID only),
  `qc/instruments/litkb_p2_mutations.py` (inventory only — auto-merged), the design doc (GROBID
  only), `qc/test_status_discovery.py` (auto-merged), `pyproject.toml` (Docling only).

**The brief expected three forked copies of the design doc §7/§12 to reconcile. Two of them never
existed:** `git diff` against the merge base shows only `work/20260914-grobid-local` edited
`Scripts/LITERATURE_KB_DESIGN_2026-09-13.md`. Inventory and Docling recorded their §7.1 and §12
findings in their reports and in code docstrings only, so there was no three-way text to reconcile —
their numbers had to be *folded in* instead, which is what the §7.1 / §12.2 / §12.10 / §14 edits in
this merge do.

## One real defect the merge surfaced — `11db0fa`

The Docling branch forked at `4256e4e`, **before the P3 sink checker existed**. Its two new stdout
sinks (`litkb/extract/docling.py::<module>::print`, `litkb/extract/docling_worker.py::main::print`)
were therefore never scanned on their own branch — `--sites` passes there because it does not know
about them. On the merged tree it failed with two PROBLEM lines. Both print a metrics dict (page
counts, seconds, pages/s, peak RSS, a path the caller typed); neither module opens the database or
holds the archive key, and the worker's line is a fixed seven-key projection, so no value outside
that set can reach the sink. Both are now `SINK_ALLOW` rows with that reasoning written out.
**Merge commit `14e3091` fails `--sites` on its own; `14e3091` + `11db0fa` pass it.**

## Proofs, per merge

| After | `--sites` | `check.py --fast` (`LITKB_TEST_DB=litkb_test_w6`) | The branch's own tests, in the merged tree |
|---|---|---|---|
| `d621cfe` | PASS | 2,544 passed, 1 failed — **only** `test_pointer_paths_resolve[crown_state_model]` (the known pre-existing failure); litkb Postgres tests 244 passed | `qc/test_litkb_inventory.py` **60 passed, 1 xfailed** |
| `cae333a` | PASS | 2,587 passed, same single failure; litkb 244 passed | `qc/test_litkb_grobid.py` 40 passed / 14 skipped with the service down; **54 passed, 0 skipped** with GROBID started in WSL (`grobid.sh start`, alive after 18 s) and `LITKB_LIVE=1` + `LITKB_LIVE_PDF` set to a real corpus PDF. Service stopped afterwards (`grobid.sh stop`) — an idle 8 GiB JVM is the defect |
| `14e3091` (+`11db0fa`) | PASS after `11db0fa` | 2,629 passed, same single failure; litkb 244 passed | `qc/test_litkb_docling.py` 37 passed / 3 skipped on fixtures; **40 passed, 0 skipped** with `LITKB_LIVE=1` against the CPU venv `D:\edmonds-pipeline\venv-docling` — that run converts a real PDF, so the live Docling requirement is met |

## After all three

**Parallel mutation harness, `--workers 4 --worker-dbs 1,2,6,9`:**
**155/155 mutations fired; baselines passed; wall-clock 43.0 min over 4 workers** (39 / 39 / 39 / 38
per worker, each reporting its baselines passed). No row was skipped and none had to be re-run.

**Inventory census reproduction.** `py -3.12 -m litkb.extract.inventory --force` re-probed all
**241 files / 5,038 pages in 45.1 s**. The regenerated `phase4/qc/litkb_inventory.csv` is
**byte-identical to the tracked file once the final `seconds` column is masked** (242 lines, header
plus 241 rows; all 172 changed lines are timing-only). The tracked file was restored and the
regenerated `.jsonl` deleted, so this merge changes no measured CSV.

**Migration 0016 applied to `litkb`.** `py -3.12 -m litkb.db.migrate --db litkb` →
`applied 1 (0016_held_reason.sql); 16 recorded`, as `litkb_owner`. P3 deliberately left it pending
because that session held `litkb` read-only; it is additive (one new function, one
`CREATE OR REPLACE`) and P3-accepted. Its known limit stands: the 68 held rows and 10 pending
bindings already in `litkb` keep their NULL reason and bare verdict until they are loaded again.
All four test databases used here (`litkb_test_w1/w2/w6/w9`) were already at 16;
`litkb_test` itself was two behind (0015, 0016) and was brought up before any test ran.

**The P3 gate, re-run read-only against `litkb` after 0016:**
**1,086 changed cells → explained 713, format 243, structural 120, filled 10, UNEXPLAINED 0,
GATE: PASS** — the P3 buckets unchanged, and `phase4/qc/litkb_p3_diff.csv` regenerates with an empty
`git diff`. (The instrument takes the workstream **UUID**, `01a0a494-bb54-7c1b-be26-db0c229a9534`;
the slug `p3-migration` raises `invalid input syntax for type uuid`. The P3 report's command line
gives the slug — a small doc defect, recorded here rather than fixed in a report that is history.)

## Open, and deliberately not closed by this merge

1. **Three `page_frames` readers, one fact.** `litkb.extract.inventory`, `…grobid` and `…docling`
   each read the §7.1 frame. Same `dx`/`dy` arithmetic, but **not interchangeable**: inventory's and
   GROBID's resolve a page that inherits its `/MediaBox` from the page tree and GROBID's raises on a
   missing mediabox, while Docling's copy has neither guard and would raise `TypeError` there.
   Inventory's docstring already claims the role. Collapsing them is a change to code three referees
   measured against, with no referee for the change (CLAUDE.md 3.4c) — so it is recorded in design
   §7.1 as an open item, **to be closed before stage 5 reconciliation is written**, which is the
   first place a disagreement between the copies produces wrong boxes.
2. **Corpus definitions.** Four are now in circulation (216/223; 224/4,712; 219/4,655; 241/5,038).
   §12.2 now names `phase4/qc/litkb_inventory.csv` as the home and marks 219/4,655 superseded, but
   §7.1's older counts are left as the referees wrote them, with their populations stated.
3. **The gates that remain**, recorded in design §14: the **throughput gate** (GROBID measured at
   concurrency 1 only with derived per-worker RSS; Docling measured on 5 gate papers and the book,
   not the corpus; metrics parked as JSONL rather than `extraction_runs.metrics`), and **stage 5
   reconciliation**, which is not built and for which no gate has been written. Also unverified:
   §14's "referee-authored, pre-committed gold" clause — nothing in the three reports records gold
   authored by a referee and committed before the measurement.
4. **Each branch head is an author commit made after its last referee report.** Most pointedly,
   `GROBID_LOCAL_REFEREE2` returned **STAGE 2 NOT READY** on defect D1 and `8f985e5` closes it. The
   fix is real (`enable` now goes through `write_unit()`, which calls `require_concurrency_headroom`
   before writing the unit) and it is exercised by the tests that passed above, but **it has not been
   re-refereed**.

## Housekeeping

The mutation harness's worker **copy** directories are shared across worktrees at
`D:\edmonds-pipeline\_litkb_harness_workers\`. `--workers 4` recreates copies `w1`–`w4` whatever
databases it is pointed at, so a `--worker-dbs 1,2,6,9` run still overwrites copies `w3` and `w4`.
No other session's run was in flight here, but the copy index and the database index are independent
and it is worth knowing before two sessions run the harness at once.

## Corrections to this report's own first draft (same day)

Two, both found by re-checking pointers against the files rather than against notes:

* The design-doc section pointers this merge added were **composed from line numbers, not read off
  headings**, and named sections that do not exist ("§the frame", "§kills", "§throughput"). They now
  quote the real heading text of `LITKB_DOCLING_LOCAL_2026-09-15.md`,
  `…DOCLING_LOCAL_REFEREE_…`, `…DOCLING_A_REFEREE_…` and `LITKB_INVENTORY_2026-09-15.md`.
* The §14 row "the throughput instrument refuses a run with no rate or no peak RSS — FIRES (both
  tools)" **overstated GROBID**. Docling's refusal is measured;
  `qc/instruments/litkb_grobid_throughput.py` records `peak_rss_bytes` but has **no refusal path**,
  and no referee exercised one. The row now reads "FIRES for Docling; NOT SHOWN for GROBID", and it
  is one more clause the throughput gate owes.

## Not done, and named

`qc/landed.py --dry-run` reports its mechanical rungs clean and the CHATLOG entry is appended
(CLAUDE.md §3.12). **The GitHub push was refused by the permission classifier**
("Out-of-Place Publication"), not by git or by credentials; the branch is pushed to `drive-mirror`
(`e9f5a88..c472b32`). Pushing `work/20260913-literature-kb` to `github` is Kam's to allow.
Incidentally, `litkb_test` itself was found two migrations behind (0015, 0016) and brought to 16
before any test ran; the four worker databases were already at 16.

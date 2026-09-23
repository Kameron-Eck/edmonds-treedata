# litkb S4 — everything acquired is readable or classified (2026-09-22)

Session S4 of `Scripts/LITKB_WORKPLAN.md`, **run 3**. Kam ruled on 2026-09-22 "i want to start S4 from
scratch"; runs 1 and 2 (2026-09-21) launched themselves overnight and are parked untrusted on
`github/archive/2026-09-21-litkb-s4-{q1,q2,r}-untrusted` — nothing of theirs is in this run. Kam
launched this window himself (`_derived/s4/launch.log`: 2026-09-22T20:05:33Z, head `7a28825`).
Orchestrator: Opus 5.5 (1M). Builders A, B, C, D1, D2 and every auditor: Opus, each builder in its own
worktree with its own worker database, every merge candidate audited by an agent that did not build it.
Every number below is read from a tracked file or from a tool's own output, each gate's exit code read
alone. Worker reports: `D:\tools\claude-config\jobs\litkb-s4-run3\` (STATE.md, briefs, survey-code,
survey-data, history-runs12, builder-A/B/C/D1/D2, auditor-D1/B/D2/A/C, the live logs).

## 1. The grade

Manifest frozen BEFORE the drain from the database's clock —
`_derived/readability/readability-2-manifest.json`, `frozen_at 2026-09-23T04:00:50Z`, head `4400374`,
repo tip 31 / db tip 31, bed 30 files, `manifest_sha256 741f71e7…a700`, workstreams main +
`readability-2`, `extract_page_cap 400`, `ocr_chunk_pages 22`, `lease_seconds 375`.

```
py -3.12 qc/instruments/litkb_acceptance.py readability --manifest ../_derived/readability/readability-2-manifest.json
unclassified_acquired_files=0 stale_leases=0 duplicate_blocks=0 resumed_content_hash_mismatches=0
books_extracted=0 quarantined_without_db_state=0 over_cap_bound=0 scans_ocr_unrouted=0
mutated_leases_accepted=0   … bed_files=30 bed_without_blocks=0 waits_on_migration=0          exit 0
```

REPORTED (unbounded, the plan's (b)): `files_without_reference_stage` and `reference_anchor_rate` —
at the grade (21:2x PDT) `94/263` and `249/249` while the pass was still running; FINAL, after both
passes (23:39:55 PDT): **`files_without_reference_stage=4/263` · `reference_anchor_rate=343/343`**
(the four are the scans, §5.13). The denominator is 263, not 233: the drain gave 30 more files blocks.

**The (c) known-bads, re-fired COLD** — from main's code, on a freshly reset worker DB, exactly as a
later session would (`LITKB_TEST_DB=litkb_test_w7 py -3.12 qc/instruments/litkb_acceptance.py
readability --fire <name>`, `jobs/litkb-s4-run3/cold-refire.log`): kill FIRED · lease FIRED
(`mutated_leases_accepted` 0 → 1 with the gate removed; with it, `gate_raised=1
blocks_after_stale_finish=0`) · cap FIRED (control: refused `over-page-cap`, `claimed=0 blocks=0`;
known-bad: 401 blocks, `over_cap_bound=1`) · probe FIRED (control: `probe_refused=1 bound=0
class=probe-error unclassified_acquired_files=0 (before 0)`; known-bad: `bound=1 bound_pages_null=1`)
· scan FIRED (control: refused `scan-needs-ocr`, `runs_ok=0 blocks=0`; known-bad: 82 blocks,
`scans_ocr_unrouted=1`) · book FIRED (control: refused `book`, `class=book`; known-bad: 3 blocks,
`books_extracted=1`) · quarantine FIRED (a CONSTRUCTED orphan payload → `quarantined_without_db_state=1`).
Every `--fire` exits 0 only when its control reads 0 AND its known-bad moved; breaking a counter or a
clause check turns it red (auditor-C, re-checks 1 and 2).

**The kill, LIVE, on the real bed** (`jobs/litkb-s4-run3/kill-midjob.log`): worker 1 (pid 81496)
started 21:01:24; at 21:01:50 one job was done and the next leased; at 21:02:05 `taskkill /T /F`
took down the worker's whole tree (5 processes) while job `01a0cc6c-a72f-784d-9128-47182f541212`
(attempt 1) was mid-extraction. Its lease expired unreclaimed at 21:08:05 (one stale lease — what the
counter exists to catch); worker 2 (pid 55948) started 21:09:06 and had the killed job `done` at
attempt 2, lease sequence 2, by 21:09:31, then drained the rest (31/31 done at 21:25:40, 0 dead, 0
refused). The grade above reads `resumed_content_hash_mismatches=0 duplicate_blocks=0
stale_leases=0` over that batch. GROBID — shared with the running stage-6 driver — answered
`isalive=true` throughout: the killed worker had never claimed ownership of a service it did not start.

## 2. Every id

| what | id |
|---|---|
| workstream `readability-2` | `01a0cabc-0702-76fe-901a-8252aa091ca9` (main tree root, opened 13:08:35 PDT; token vaulted at landing to `D:\edmonds-pipeline\secrets\litkb-tokens\readability-2\`) — NOT `readability-1` (runs 1-2, left alone) |
| reservation + shared probe on main | `3debb5a` (0029/0030/0031 reserved), `c45f495` (`pipeline/litkb/extract/probe.py`), `2490419` (builder-B's handle fix, cherry-picked), `5392ac4` (decision D13) |
| rulings on main | `31e1a33` / `3bb3422` (`litkb-live-migration-by-session`, `litkb-extract-page-cap`), `df98d0b` (SCIENCE.md regenerated) |
| D1 → main | `3ebf43c` = `work/20260922-litkb-s4r3-refs` (`03155cb` + `7db9843` + `5210d12`), audited on `cand/20260922-litkb-s4r3-d1` |
| S4 → main | `4400374` = `work/20260922-litkb-s4r3-acceptance` @ `0852c8e` (A `456550c`…, B `7dc1b19`, D2 `df8a011`, C `1f243a9`, fixes `9b6e43d` `f5e1752` `1d19a11` `c247d14` `0852c8e`); follow-up `6fc8bf7` (= `86487e7`) |
| migrations applied LIVE | 0029 `extraction_jobs`, 0030 `quarantine_state`, 0031 `retire_runs` — 2026-09-22 20:58:59 PDT, 0.85 s, `litkb.migrate: applied 3 … 30 recorded`, by this session under `litkb-live-migration-by-session` |
| manifest | `_derived/readability/readability-2-manifest.json` (sha above; `_derived/` is untracked) |
| readability CSVs | `Reports/LITKB_READABILITY_2026-09-22_3.csv` — THE post-drain CSV; `…2026-09-22.csv` and `…_2.csv` are builder-B's two PRE-drain live scores (before and after D13), kept as the classifier's first measurements |
| other CSVs | `Reports/LITKB_FRAGMENT_TEXT_2026-09-22.csv`, `Reports/LITKB_FRAGMENT_TEXT_CORPUS_2026-09-22.csv`, `phase4/qc/litkb_preprint_stamp.csv`, `phase4/qc/litkb_web_title_region.csv` |
| worker DBs | A w7 · B w9 → w3 · D1 w3 · D2 w9 · C w7 · auditors w3 / w9 (two checkouts each time) |
| retirement op | 687 runs retired, `litkb runs retire --apply` (session `s4-run3`), 2026-09-22 ~21:28 PDT |

## 3. What landed (the S4 Work bullets, each with where it lives)

- **The queue** — `extraction_jobs` + an append-only lease history + a token table no agent role can
  read (0029); `litkb queue {sweep,work,status}` (`pipeline/litkb/extract/queue.py`). The OWNERSHIP GATE
  is `finish_job`, called in the same transaction as the block ingest: a superseded claim's finish
  raises and nothing lands (auditor-A: nine bad-token forms each refused). Guards at enqueue AND claim:
  `book` (`litkb-book-policy`), `over-page-cap` (`litkb-extract-page-cap`), `probe-error`, `bad-file`,
  `scan-needs-ocr` with OCR off. A refusal that no longer holds is reopened by the sweep through
  `reopen_job` with an audit row (`extraction_job_reopens`); a job goes `dead` after 3 attempts and
  leaves a `failed` run. `--redo` re-extracts a file whose current run is at an older key.
- **Per-file completeness and the classes** — `pipeline/litkb/readability.py`, the closed classes
  (`extracted` · `scan-needs-ocr` · `over-page-cap` · `zero-content` · `bad-file` · `probe-error` ·
  `book` · `refused-registry`; work class `no-file-any-route`), from evidence only — the per-page probe,
  the current run and its metrics, the quarantine rows (by path AND content hash), the queue's
  refusals and dead jobs. A job that died on an extractor error stays UNCLASSIFIED (a finding, never a
  class). `litkb_work` shows each file's class and its uncleared quarantine rows.
- **Scan OCR under the measured VRAM policy** — image pages route to OCR in page-range jobs of ≤ 22
  pages (decision D3), assembled into ONE run in one transaction; the device and interpreter chosen as
  a PAIR (D4). Live peaks: Anderson 2,522 MiB, Hudson 2,612, Hwang 2,752, Ogata 2,632 (two ranges, one
  run) — all under the 3,277 MiB rule.
- **The enforced, fail-closed page cap** — `EXTRACT_PAGE_CAP = 400` in `probe.py`
  (`litkb-extract-page-cap`); `probe_pages` RAISES where `binding.pdf_info` never did, so a bind on an
  unreadable page count is refused `probe-error` and quarantined, never bound with `pages` NULL.
- **`page_no` for cross-page paragraphs** — each fragment of tool/OCR text now carries only its own
  page's text (Docling per-provenance `charspan`), reconcile `stage5-3 → stage5-4`; existing current
  runs untouched, new extractions at the new key.
- **Metrics into `extraction_runs.metrics`** — seconds, pages, pages/s, peak RSS, peak VRAM, device,
  interpreter, OCR on/off + engine, chunk ranges; all 31 `stage5-4` runs carry them (0 of 926 did).
- **Retiring superseded run sets, as a deliberate op** — `litkb runs retire` (0031), MARKING only
  (decision D6): 687 runs retired live (670 `5-reconcile` + 17 stage-6 `litkb-p6-1`), nothing deleted;
  current runs and the 7 evidence-cited runs excluded and named; `set_current_run` refuses a retired run.
- **The database-visible quarantine state** — `litkb.quarantine_payloads` (0030): a row at every
  quarantine write (acquisition guard, bind refusals, `hunt-url`, the reaper), sha256 of the refused
  bytes, a closed reason, an origin; the 69 existing payloads backfilled live (`written=69 errors=0`).
  Sidecars were NOT added where missing — that is S4.5 item 8.
- **The reference stage** — `qc/instruments/litkb_references_stage.py`, keyed by the current version's
  `rel_path`, resumable, GROBID held and never stolen; stage-6 version `litkb-p6-1 → litkb-p6-2` (D12:
  the 17 old runs predate the raw-search resolver).
- **The `readability` acceptance subcommand** — `--freeze`, `--manifest`, `--fire` (seven names, each
  grading its plan clause; refuses `litkb`, refuses the reserved worker DBs).
- **Carried from S3, decided:** `TITLE_REGION_LINES = 45` measured on the real web snapshots (9 on disk,
  title at line ≤ 4, only 2 distinct pages — holds on every measured row, which does not establish 45 for
  web pages in general); a refused page's snapshot in `_litkb_staging/web/` is left to the REAPER at its
  age threshold, and the reaper's move now writes a quarantine row (D10); the `incoming/t*.download`
  binds are NOT refiled — extraction reads `rel_path` and the reaper owns bound paths (D9; a refile is
  S4.5 landing work); the L4 formula re-crop of Reynolds_2000 and Montgomery_1991 was NOT run — it needs
  Colab, S4 spends none, and the open-items register gives it to S4.7 (D11).

## 4. The measurement bed, scored

The bed at freeze: 30 active main files with no blocks (`bed-at-start.md` in the jobs folder). Before
the drain the classifier put 26 of them `unclassified` (native files waiting for extraction — never a
class, D8) and 4 `scan-needs-ocr`. After: all 30 extracted (26 full, 4 OCR), `bed_without_blocks=0`.
Across the whole universe: 268 acquired files — 263 extracted (259 full + 4 ocr), 5 `refused-registry`
(the ruled run's 187 protocol PDF, 235's two report copies, two refused Crossref page snapshots),
0 unclassified; 22 works `no-file-any-route`, 201 `not-attempted` (REPORTED, outside the gated universe).

- **E08 and the scans** — Hwang_1982, Anderson_1957, Hudson_1978, Ogata_1998: OCR'd on the T2000 (peaks
  above); Anderson went from 0 native characters after its JSTOR cover to 43,974 characters in 314 blocks.
- **The `--no-extract` binds** of the wrap-up (1) and the ruled run (10): all in the bed, all extracted.
- **The 13 tracker-era works** of the second approve session: all unextracted at start, all extracted.
- **E21's pair** — the bioRxiv preprint `Valavi_2018_blockcv-r-package-generating` extracted (525 blocks).
  THE STAMP-STRIP RATIO (`_PREPRINT_STAMP`, until now tested on constructed lines only): **19 of 19**
  stamped pages stripped, under both pdftotext builds on PATH (xpdf 4.00, poppler 25.07), by a detector
  independent of the regex; the page-1 title ratio 0.9858 with or without the strip
  (`phase4/qc/litkb_preprint_stamp.csv`, instrument `qc/instruments/litkb_preprint_stamp.py`).
- **E25's re-bound arXiv files** (Gulrajani, Kumar) — extracted. Jaffe_2014 / Vixie_2007 — untouched,
  as the plan said (already bound and extracted).
- **S2's Copernicus PDF (Maiti_2022)** — a CLASSIFICATION, then a FIX: the code survey found Docling's
  "nothing" was a configuration fault (hunt asked for `cuda` under the CPU-only venv); the classifier
  called it `extracted` / `grobid-only`; decision D4 pairs device and interpreter; `--redo` re-extracted
  it: Docling regions 0 → 240, blocks 113 → 232.
- **Riva_2017** (101 pages, the corpus's longest) — extracted whole, under the 400-page cap.
- **The E20 book** — retired (`litkb-crc-book`); the `book` class is proven by the fire, not by a row.
- **The reference stage** — pass 1 over the 233 files with blocks at launch (15:36:35 → 23:05:54 PDT:
  233 ok, 0 errors, 9,302 references, 5,781 resolved, 313 anchored, 214 edges, 10,384 network calls),
  pass 2 chained by a detached waiter for the files the drain added (23:05:54 → 23:39:55: 30 selected, 26
  ok, 4 errors — the scans — 922 references, 536 resolved, 30 anchored, 15 edges, 1,112 calls). Each pass
  started GROBID itself (the service was down when it began) and stopped only what it had started.

Stage 6, final (`litkb.extract.references_coverage` at the current key `litkb-p6-2`):
`files_without_reference_stage=4/263 (1.5%) reference_anchor_rate=343/343 (100.0%)
references_anchored=343/10224 (3.4%) anchored_with_citation_edge=229/343 (66.8%) citation_edges=229
anchored_outside_held_doi=0` — on the loop survey's measured slice the same two kill numbers were 2.6 %
and 100 % (`Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.2, R4); over every file with blocks,
anchoring stays coverage-bound: every reference whose DOI resolves to a held work is anchored, and 3.4 %
of all references do. 114 anchored references have no citation edge — the survey's R3 (the edge is made
from one index, the anchor from another), unchanged by S4.

## 5. Bounded outcomes, said plainly

1. **The reference stage is about three times slower than estimated.** The loop survey's R4 guessed
   ~1 s per reference (~2.5 h); measured 8.05 h of per-file seconds over 10,224 references (~2.8 s per
   reference, ~110 s per file), because every reference is resolved over the network at the registries'
   own pacing. It ran detached, 0 errors on the 259 files that carry a text layer.
2. **My Maiti re-extraction stranded three proposed evidence rows.** Maiti's old run carries 3
   `use_evidence` rows of S2's `first-work-1` — `proposed`, none in main. Moving the current run means
   `promote prepare` would hold them until rebased. All three quotes are present verbatim in ONE block
   of the new run, so the rebase is mechanical; S4 did not re-record uses. `queue sweep --redo` has no
   evidence guard — a follow-up.
3. **A builder's test reached the network** (D1's first draft: 22 real registry-cache files, 404s for
   made-up `10.9999/…` DOIs, 13:59-14:00). Kept (correct answers for DOIs nobody will ask); fixed so the
   tests block the network. An auditor (auditor-B) also made one registry call for a made-up DOI.
4. **My own first image-page rule was wrong.** `chars < 200` routed native papers with a captioned figure
   page to OCR (Pauls_2025 p16, Pesonen_2026 p20, Guo_2019 p6). Measured: every scan page after its cover
   has 0 characters; decision D13 = zero native characters AND a raster image. Stated limit: a scan that
   stamps native text on every page is not routed; the corpus holds none.
5. **Green builder suites, red whole suite.** D2's candidate carried 5 full-suite reds from project-wide
   gates (line-number citations; unguarded call sites) that its named suites never ran; an auditor
   caught them. D1's harness scored an INVALID-SQL mutant as FIRED; an auditor caught it.
6. **Three real defects found by auditors, fixed before merge:** a quarantine row matched by PATH alone
   (a good file inherited a bad file's verdict and left the unclassified count); `0031` counted each
   evidence row twice (it would have gone live); a GROBID ownership race (a driver could stop a GROBID it
   had not started). And a live hazard: `hunt` stopped a GROBID it did not start — now one ownership
   helper in `extract/grobid.py` for hunt, the driver and the queue.
7. **Empty-text GROBID fragments.** The per-page fix places GROBID text by SENTENCE START, so a sentence
   running from page 27 onto 28 is cited on 27 and page 28's fragment may be empty. Measured
   corpus-wide on stored artifacts: 0 → 97 empty-text fragments in 33 files, 22 new boxes (15 empty), 7
   gone. Kept (decision D16): an empty fragment records that the element continues; there is nothing in
   it to misquote.
8. **`resumed_content_hash_mismatches` compares the database with the SAME job's stored artifacts.** It
   cannot see a resumed extraction whose tool output differs from a clean run's; that equality was shown
   separately — the kill tests on worker DBs, the real-tool tests (identical digests across two sessions:
   Docling is deterministic on this machine).
9. **Auditor slips, recorded:** auditor-C's dry-check ran four mutations during a first `check.py` run
   (discarded; a clean second run is the one cited) and it reset the RESERVED `litkb_test_w10` (harmless:
   the edges replay resets and migrates it itself) — which exposed that `--fire` accepted reserved
   workers; it now refuses them, reading the list from the plan's per-session protocol line, and that
   parser fails OPEN on one partial rewording (fails closed on deletion, case, and punctuation).
10. **Where a rule lives.** "Never reopen a refusal that still holds" is enforced by the sweep, not the
    database; `reopen_job` called directly would reopen an over-cap job, which the claim-time re-check
    then refuses again. The probe fire's "unclassified unchanged" check cannot fail (refused bytes never
    enter the file set). The manifest hash guards accidental edits only (the gated counters are read
    live). A bad-bytes book reads as unclassified `disagreement`.
11. **The permission classifier refused one auditor's live CLI dry run** (the quarantine backfill); it
    was reproduced read-only in-process. The orchestrator's own live commands, including the migration
    apply, were not refused.
12. **Retired is not reclaimed.** 687 runs are marked; 263,779 superseded blocks remain; deleting them is
    a separate decision nobody has made.
13. **The reference stage cannot reach a scan.** GROBID parses a PDF's TEXT LAYER; a scan has none —
    the OCR text S4 produced lives in the stage-5 blocks, not in the PDF — so Anderson_1957, Hudson_1978
    and Hwang_1982 end `NoTextBlocks` and Ogata_1998 a GROBID 500: the four files of
    `files_without_reference_stage=4/263`. The driver records each as a named error, never an empty
    success; it re-selects them on every rerun. Closing it means feeding the OCR'd bibliography blocks to
    GROBID's citation-string parser — S4.7's scan work or later, not built here.
14. **Resolution ran throttled.** Pass 1 tripped the arXiv AND Semantic Scholar breakers (HTTP 429), pass 2
    Semantic Scholar's; the rest of each pass resolved without them. 6,317 of 10,224 references resolved
    is therefore a FLOOR measured under throttling, not the resolver's ceiling. The anchor rate is
    conditional on a held DOI resolving and reads 100 % either way.

## 6. The session's decisions (the rulings are ids; the rest are this run's, with their sources)

`litkb-live-migration-by-session` (Kam: "I should not be doing anything by hand"), `litkb-extract-page-cap`
(Kam: "400 is fine, keep going"). Orchestrator decisions, each in `jobs/litkb-s4-run3/STATE.md`: D1 cap 400
· D2 three attempts · D3 OCR chunk 22 pages (the longest single OCR pass measured inside the VRAM rule) ·
D4 device/interpreter pair · D5 a quarantine table, path-keyed · D6 retirement marks, never deletes · D7
stage 6 not queued · D8 the closed classes, a queue state is not a class · D9 no refile · D10 the reaper
takes refused snapshots · D11 L4 re-crop not run · D12 stage-6 `litkb-p6-2` · D13 image page = zero text +
a raster image · D14 keep builder-B's probe handle fix · D15 probe-error rows on bound files · D16 keep
empty GROBID fragments · D17 the scan post-condition refuses only a scan (image pages outnumber text pages);
a failed run at dead; the classifier reads the queue · D18 an expired lease nobody reclaimed may still
finish; only a SUPERSEDED claim is refused.

## 7. Not done / on other tracks

- `first-work-1`'s three proposed uses on Maiti_2022 need a rebase before promotion (§5.2).
- `queue sweep --redo` should refuse (or warn) when the current run carries `use_evidence` (§5.2).
- The `.reason.json` sidecar on every quarantine (S4.5 item 8); the 187/235 landings and refiling staging
  binds (S4.5 item 1); the L4 formula re-crop, text tiers and vision-language OCR (S4.7).
- Purging the 263,779 retired blocks — nobody's decision yet.
- No Codex read of this session's code: its quota has been exhausted since the survey's round two; Opus
  auditors stood in, and the read is OWED.

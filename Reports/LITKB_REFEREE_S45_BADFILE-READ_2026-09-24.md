# litkb S4.5 referee — rung class `badfile-read` (plan item 8)

Referee: `referee-badfile-read` (Opus 5.5, fresh agent; built, proposed, integrated and audited nothing in S4.5).
Checkout: detached `D:\edmonds-pipeline\wt-s45-ref-badfile-read` at main `8150308`. Worker DB: `litkb_test_w1`
(no advisory lock and no session on any `litkb%` database before use). Live `litkb` read only as `litkb_reader`;
the corpus read only; no network. Written 2026-09-23 22:25 PDT under the frozen name dated 2026-09-24.
Full working notes: `D:\tools\claude-config\jobs\litkb-s4-5\referee-badfile-read.md`.

## Verdict: ACCEPT-WITH-NOTES

On the real rows the bad-file read does what item 8 says. It covers all 27 `bad-file` attempts on 17 works. It
types 20 rows. It leaves the 7 misbooked rows untyped and names them. It counts the free-to-fix rows (8) apart
from `html_is_the_work` (8). The live typing matches the tracked CSV cell for cell. Every quarantined payload
now has a `.reason.json` sidecar beside it. The 25 backfilled sidecars agree with the database and the disk,
field by field.

One real defect was found: the `bytes_kept_path` cell is wrong on 2 of the 27 rows (N1). No typed value, count,
counter or backfill reads that cell. Five further notes follow; two of them come from my own mutations.

fired: quarantines_without_reason=1 on a CONSTRUCTED bad download (a BOM article offered to a work it is not) quarantined with the sidecar write removed (sidecar, litkb_test_w1, re-fired by referee-badfile-read at 8150308)
fired: bad_file_untyped=1 on a 200 HTML page served for a PDF link with the typing step disabled (typing_disabled_bad_file, litkb_test_w1, re-fired by referee-badfile-read at 8150308)

**Scope, stated.** The live run has NOT happened yet. This report scores four things: the historical rows, the
typing as it was applied on live (backfill `01a0d1cd-43c1-75c4-9a70-fc1b3ea61508`, 2026-09-23 22:04), the 25
backfilled sidecars (written 22:05:38), and the instrument. Sidecars that the run will write are NOT scored
here. At grading they are covered by the all-time `quarantines_without_reason` counter. That counter only
checks that a sidecar exists, not what it says (N3).

## 1. The oracle (mine, independent of the builders' code)

`D:\tools\claude-config\jobs\litkb-s4-5\scratch\referee-badfile-read\oracle.py` imports nothing from `litkb` or
`qc/instruments`. It never calls `accept.accept`, `quarantine.payloads`, `quarantine.without_reason`,
`store.reason_path` or the item-8 instrument. It does three things:

- **A. Filesystem walk** of `Literture\_quarantine`, pairing every payload with its sidecar. My payload rule:
  every file except `*.reason.json` and a `.txt` that sits beside a same-stem non-txt file. The sidecar path is
  `<stem>.reason.json`. The walk also looks for orphan sidecars, shared sidecar paths, sidecars that do not
  parse, and sidecars that carry no reason field.
- **B. The 25 backfilled sidecars**, checked field by field:
  - `sha256` and `bytes` against my own hash of the file on disk;
  - `work_id`, `attempt_id` and `label` against the `litkb.quarantine_payloads` row;
  - `route`, `status` and `attempt_at` against the `litkb.acquisition_attempts` row;
  - file mtime (the day of the apply) and create-only behaviour (no other sidecar changed).
- **C. Hand rules for the 27 `bad-file` attempts**, written from the plan text: item 2's vocabulary, item 8,
  S4.5 decisions D12, D15 and D29, and item 2's definition of `not-in-archive`. The inputs are the attempt's
  own codes and `tried` tokens, plus a first-KiB read of any kept payload (magic, `<title>`, length, meta
  refresh, `citation_pdf_url`). Rules:
  - bytes that are the client's own error text → misbooked;
  - HTML with a meta refresh to the publisher's article → `landing_page`, free to fix;
  - HTML whose `<title>` carries at least 60% of the work's title words → `html_is_the_work`;
  - a 404 page → not the work;
  - no bytes, 202 with no 200 → misbooked (an interstitial);
  - no bytes, 403 with no 200 → misbooked (blocked);
  - no bytes, every code 0 → misbooked (`api-error`, D15);
  - a mirror whose token records `no-pdf-link` → misbooked (`not-in-archive`);
  - an archive sweep with 200 non-PDF answers → `html_response`, `inferred`, not free to fix;
  - an open-access 200 with no bytes → `landing_page`, `inferred`, unless a later attempt on the same work and
    route kept bytes, in which case that attempt's typing applies.

  Kept bytes are paired by my own chain, in order:
  1. `quarantine_payloads.attempt_id`;
  2. the attempt's `detail.sha256`, if the first found nothing;
  3. a reaper sidecar whose `was` names the work and whose file mtime falls 0–60 s after the attempt.

**Independence caveat.** The dispatch pointed me at `live\1.1-badfile.out`, so I saw the instrument's totals
before I wrote the rules. The rules and the code are mine; the kept-bytes pairing and the sidecar checks are
where the oracle disagreed with the rung (N1). My oracle is the same model family as the builders.

## 2. Scored rows

### 2.1 The 27 `bad-file` attempts (17 works): positive and negative

**27 of 27 CORRECT on the typing:**

| column | matches my oracle on |
|---|---|
| `sub_status` / basis (tracked CSV and live DB) | 27 of 27 |
| cause | 27 of 27 |
| `free_to_fix` | 27 of 27 |

**Kept-bytes pairing: 7 of 9 CORRECT, 2 WRONG cells (N1).**

The tracked CSV is sha256 `68a28516…a829`. It is byte-identical to the backfill's recorded source, to the live
`1.1` regeneration, and to my own read-only re-run of the instrument.

| # | attempt | work | route | codes / kept bytes (my first-KiB read) | expected (plan: item 2 + D12/D15/D29) | the rung (CSV / live DB) | my oracle | verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | 01a0c717-c9dc | Appel_2024_efficient-data-driven-g | open_access | [202] | misbooked: NO sub_status (D29) | CSV (none)/(none), misbooked, free=n; DB NULL/NULL | HTTP 202 with no 200 and no body kept - a WAF interstitial's shape, blocked | CORRECT |
| 2 | 01a0a7c6-2d73 | Culbert_2025_reference-coverage-an | open_access | [200, 200, 403] | html_response/inferred, landing_page, free=y | CSV html_response/inferred, landing_page, free=y; DB html_response/inferred | open-access host answered 200 with no PDF, bytes not kept: a landing page's shape (inferred) | CORRECT |
| 3 | 01a0a83b-5d69 | Culbert_2025_reference-coverage-an | open_access | [200, 200, 403] | html_response/inferred, landing_page, free=y | CSV html_response/inferred, landing_page, free=y; DB html_response/inferred | same | CORRECT |
| 4 | 01a0a7c6-dcd5 | Hickey_2014_managing-ambiguity-via | open_access | [200] | html_response/inferred, html_is_the_work, free=n | CSV html_response/inferred, html_is_the_work, free=n; DB html_response/inferred | no bytes; sibling 01a0a837-9e60's kept page, title match 100% | CORRECT |
| 5 | 01a0a837-9e60 | Hickey_2014_managing-ambiguity-via | open_access | [200] kept 44843 B, html, title 'Managing Ambiguity In VIAF' | html_response/bytes, html_is_the_work, free=n | CSV html_response/bytes, html_is_the_work, free=n; DB html_response/bytes | HTML `<title>` carries 100% of the work title: the work itself (D12) | CORRECT |
| 6 | 01a0c71d-202c | Liu_2021_change-detection-deep-lea | open_access | [200] kept 2694 B, html, title 'Redirecting' | html_response/bytes, landing_page, free=y | CSV html_response/bytes, landing_page, free=y; DB html_response/bytes | HTML 'Redirecting', meta refresh to the ScienceDirect article: a landing page (Stage C) | CORRECT |
| 7 | 01a0a85f-448a | Maragos_1989_pattern-spectrum-mult | open_access | [202] | misbooked: NO sub_status (D29) | CSV (none)/(none), misbooked, free=n; DB NULL/NULL | HTTP 202, no 200, no body kept | CORRECT |
| 8 | 01a0a071-bb1c | Olofsson_2020_mitigating-effects-o | open_access | [403, 0] | misbooked: NO sub_status (D29) | CSV (none)/(none), misbooked, free=n; DB NULL/NULL | 403 with no 200 - blocked, not bad-file | CORRECT |
| 9 | 01a0a7c6-61d8 | Ortega_2024_indexation-retracted-l | open_access | [200, 200] | html_response/inferred, landing_page, free=y | CSV html_response/inferred, landing_page, free=y; DB html_response/inferred | 200, no PDF, no bytes: landing page's shape | CORRECT |
| 10 | 01a0a83a-10c7 | Ortega_2024_indexation-retracted-l | open_access | [200, 500] | html_response/inferred, landing_page, free=y | CSV html_response/inferred, landing_page, free=y; DB html_response/inferred | same | CORRECT |
| 11 | 01a0a153-1379 | Page_1954_continuous-inspection-sc | annas | – | html_response/inferred, mirror_sweep_no_pdf, free=n | CSV html_response/inferred, mirror_sweep_no_pdf, free=n; DB html_response/inferred | archive sweep: partner hosts 404/0, mirror links 200 non-PDF, no bytes | CORRECT (inferred; status UNDETERMINED, R3) |
| 12 | 01a0a154-18c4 | Page_1954_continuous-inspection-sc | annas | – | same | same | same | CORRECT (inferred; status UNDETERMINED, R3) |
| 13 | 01a0adcf-9a14 | Pfitzmann_2022_doclaynet-large-hum | annas | kept 58 B, client-error-text | misbooked: NO sub_status (D29) | CSV (none)/(none), misbooked, free=n; DB NULL/NULL | kept bytes are the client's own `URLError … getaddrinfo failed` text (D15/D29) | CORRECT; **kept-path cell WRONG**: the CSV names `…a8df07388415.2.pdf`, but this attempt's own file is `…a8df07388415.pdf` |
| 14 | 01a0add7-22a7 | Pfitzmann_2022_doclaynet-large-hum | annas | kept 58 B, client-error-text | misbooked: NO sub_status (D29) | CSV (none)/(none), misbooked, free=n; DB NULL/NULL | same | CORRECT |
| 15 | 01a0c379-a77e | Pfitzmann_2022_doclaynet-large-hum | annas | kept 58 B, client-error-text | misbooked: NO sub_status (D29) | CSV (none)/(none), misbooked, free=n; DB NULL/NULL | same | CORRECT; **kept-path cell WRONG**: the CSV names `…a8df07388415.2.pdf`, but this attempt's own file is `…a8df07388415.3.pdf` |
| 16 | 01a0a871-4373 | Strong_2003_edge-preserving-scale- | annas | – | html_response/inferred, mirror_sweep_no_pdf, free=n | CSV html_response/inferred, mirror_sweep_no_pdf, free=n; DB html_response/inferred | archive sweep, no bytes | CORRECT (inferred; status UNDETERMINED, R3) |
| 17 | 01a0a872-94f2 | Strong_2003_edge-preserving-scale- | annas | – | same | same | same | CORRECT (inferred; status UNDETERMINED, R3) |
| 18 | 01a0a7c6-f73a | Tkaczyk_2018_reference-matching-re | open_access | [200] | html_response/inferred, html_is_the_work, free=n | CSV html_response/inferred, html_is_the_work, free=n; DB html_response/inferred | sibling 01a0a838-15a7's kept page, title match 100% | CORRECT |
| 19 | 01a0a838-15a7 | Tkaczyk_2018_reference-matching-re | open_access | [200] kept 63698 B, html, title 'Reference matching: for real this time - Crossref' | html_response/bytes, html_is_the_work, free=n | CSV html_response/bytes, html_is_the_work, free=n; DB html_response/bytes | title (past the first KiB) carries 100% of the work title | CORRECT |
| 20 | 01a0a7c7-0497 | Tkaczyk_2024_how-good-your-matchin | open_access | [200] | html_response/inferred, html_is_the_work, free=n | CSV html_response/inferred, html_is_the_work, free=n; DB html_response/inferred | sibling 01a0a83a-d8b8, title match 100% | CORRECT |
| 21 | 01a0a83a-d8b8 | Tkaczyk_2024_how-good-your-matchin | open_access | [200] kept 56824 B, html, title 'How good is your matching? - Crossref' | html_response/bytes, html_is_the_work, free=n | CSV html_response/bytes, html_is_the_work, free=n; DB html_response/bytes | title carries 100% of the work title | CORRECT |
| 22 | 01a0a7c7-14c0 | Tkaczyk_2025_metadata-matching-bey | open_access | [200] | html_response/inferred, html_is_the_work, free=n | CSV html_response/inferred, html_is_the_work, free=n; DB html_response/inferred | sibling 01a0a83c-f398, title match 100% | CORRECT |
| 23 | 01a0a83c-f398 | Tkaczyk_2025_metadata-matching-bey | open_access | [200] kept 57870 B, html, title 'Metadata matching: beyond correctness - Crossref' | html_response/bytes, html_is_the_work, free=n | CSV html_response/bytes, html_is_the_work, free=n; DB html_response/bytes | title carries 100% of the work title | CORRECT |
| 24 | 01a0a856-c19d | Tuia_2011_active-learning-adapt-re | open_access | [200] | html_response/inferred, landing_page, free=y | CSV html_response/inferred, landing_page, free=y; DB html_response/inferred | 200, no PDF, no bytes: landing page's shape | CORRECT |
| 25 | 01a0a070-e66f | VelasquezCamacho_2025_monitoring-t | scihub | [200, 522] | misbooked: NO sub_status (D29) | CSV (none)/(none), misbooked, free=n; DB NULL/NULL | the mirror's page carried no PDF link (`no-pdf-link(11350B)` token): not-in-archive by item 2 | CORRECT |
| 26 | 01a0a854-68d5 | Ventura_2024_individual-tree-detec | open_access | [200] | html_response/inferred, landing_page, free=y | CSV html_response/inferred, landing_page, free=y; DB html_response/inferred | 200, no PDF, no bytes: landing page's shape | CORRECT |
| 27 | 01a0c71d-8d33 | Zhu_2026_scalable-sub-meter-mappin | open_access | [200] kept 2747 B, html, title 'Redirecting' | html_response/bytes, landing_page, free=y | CSV html_response/bytes, landing_page, free=y; DB html_response/bytes | HTML 'Redirecting', meta refresh to the ScienceDirect article | CORRECT |

**Totals.** My oracle and the instrument agree on every count. MEASURED, reader SQL plus my walk:

| quantity | value |
|---|---|
| `bad-file` attempts on live | 27, on 17 works |
| typed on live | 20 (`html_response`: 6 on basis `bytes`, 14 `inferred`) |
| left NULL | exactly the 7 attempt ids that the CSV and my oracle both name misbooked: 3 client-error text, 2 HTTP 202, 1 403+0, 1 mirror no-PDF page; 5 works |
| sub_status set on any other live attempt | none (census: only these 20 rows on all of live) |
| **FREE_TO_FIX** (the first tracked number) | 8 rows (0 measured, 2 estimated, 6 inferred) / 6 works / 2 works still without a file (Ventura_2024, Zhu_2026) |
| `html_is_the_work` (D12, REPORTED separately) | 8 rows / 4 works |
| `citation_pdf_url` on a kept page | 0 of 9 |
| `bad_file_untyped` (my SQL: NULL sub_status minus the 7 named) | 0 |

### 2.2 The 25 backfilled sidecars: 25 of 25 CORRECT

Every one of the 25 passes every check:

- `sha256` and `bytes` equal my own hash and size of the payload on disk.
- It matches its `quarantine_payloads` row on `sha256`, `work_id`, `attempt_id` and `label`.
- The 9 that carry an attempt match that attempt row on `route`, `status` and `attempt_at` to the microsecond.
- It carries `"backfilled": true`, and its mtime is 2026-09-23 (the apply).
- Create-only: none of the other 44 sidecars has an mtime on the apply day.

Breakdown: 16 have no attempt and carry label `legacy`; 8 are `binding-failed`; 1 is `content-mismatch`
(Page_1954, whose named attempt is `browser/ok`, exactly as the database has it).

| # | sidecar (backfilled) | source | sha+bytes vs disk | vs quarantine_payloads row | vs attempt row | verdict |
|---|---|---|---|---|---|---|
| 1 | Bellettini_2002_total-variation-flow-garbled.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 2 | Bellettini_2002_total-variation-flow-garbled.stray-recovered.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 3 | Berland_2024_historical-changes-tree-impervious.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 4 | Brown_2022_aerial-animal-detection-spatial-resolution.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 5 | Brown_2022_retry2.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 6 | Chen_2024_coarse-to-fine-semantic-segmentation-satellite.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 7 | Chen_2024_retry2.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 8 | DelgadoQuiros_2025_…__binding-failed__b045d36019f7.reason.json | quarantine_payloads+attempt | match | match | open_access/binding-failed match | CORRECT |
| 9 | Enamorado_2019_…__binding-failed__32f303e862c9.reason.json | quarantine_payloads+attempt | match | match | annas/binding-failed match | CORRECT |
| 10 | Gulrajani_2020_…__binding-failed__92ea5bb1b5be.reason.json | quarantine_payloads+attempt | match | match | open_access/binding-failed match | CORRECT |
| 11 | Hickey_2002_…__binding-failed__d703c7e792c6.reason.json | quarantine_payloads+attempt | match | match | open_access/binding-failed match | CORRECT |
| 12 | Konda_2016_magellan-work__binding-failed__f88dcb7521d8.reason.json | quarantine_payloads+attempt | match | match | annas/binding-failed match | CORRECT |
| 13 | Kopcke_2010_…__binding-failed__04f40359098b.reason.json | quarantine_payloads+attempt | match | match | annas/binding-failed match | CORRECT |
| 14 | Kumar_2019_…__binding-failed__cc4e4bde39f5.reason.json | quarantine_payloads+attempt | match | match | open_access/binding-failed match | CORRECT |
| 15 | Lahiri_2003_resampling-methods-spatial-data.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 16 | Mobsite_2026_land-cover-semantic-segmentation.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 17 | Mobsite_2026_retry2.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 18 | Page_1954_…__content-mismatch__73543a97140df1be662267e0a29c218c.reason.json | quarantine_payloads+attempt | match | match | browser/ok match | CORRECT |
| 19 | Schwartz_2000_distributed-lag-air-pollution-deaths.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 20 | Song_2026_monocular-height-sparse-lidar-correction.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 21 | Song_2026_retry2.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 22 | Stehman_2022_incorporating-interpreter-variability.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 23 | Thakur_2021_…__binding-failed__1925755aeb62.reason.json | quarantine_payloads+attempt | match | match | open_access/binding-failed match | CORRECT |
| 24 | VanDenHout_2017_multi-state-survival-models.reason.json | quarantine_payloads | match | match | - | CORRECT |
| 25 | Xing_2024_interpenetrating-subsampling-interpreter.reason.json | quarantine_payloads | match | match | - | CORRECT |

### 2.3 The whole quarantine (walk, not the counter): CORRECT

`_quarantine` holds 178 files:

| kind | count | detail |
|---|---|---|
| payloads | 69 | 58 `.pdf`, 10 `.download`, 1 `.html` |
| sidecars | 69 | |
| `.txt` companions | 40 | every one beside a same-stem payload |

Checks, all with a clean result:

- 69 of 69 payloads are paired with a sidecar;
- 0 orphan sidecars;
- 0 shared sidecar paths;
- 0 sidecars that fail to parse;
- 0 sidecars with no reason, why, rule, label or status field;
- 0 disagreements between a sidecar's `sha256` and the payload on disk.

The walk also matches the database: every payload has a `quarantine_payloads` row (69 rows, none missing, none
extra, none cleared).

**My walk gives `quarantines_without_reason` = 0.**

### 2.4 Negatives

| negative | expected | measured | verdict |
|---|---|---|---|
| the census.gov page `_quarantine\Winkler_2014_matching-record-linkage__staging-orphan__7ee96d141d89.download` | not the file | 25,773 B HTML; `<title>` "U.S. Census Bureau: Page not found"; 0% overlap with the work's title. No `bad-file` row names it. Winkler_2014's only file is a different one (`_litkb_staging/filed/Winkler_2014_matching-record-linkage.pdf`, sha256 `6ff22962…`). It has a reaper sidecar. The instrument's own `type_kept` gives it `html_no_pointer` (not the work) | CORRECT |
| the 58-byte `URLError` text (E13, 3 rows) | never typed on basis `bytes` (D29, D15) | NULL sub_status on all 3 rows; my reader says `client-error-text` | CORRECT |
| the misbooked 202, 403+0 and mirror-page rows | no `bad-file` sub-status (D29) | NULL on all 4 | CORRECT |
| `html_is_the_work` counted as free to fix (D12) | never | 0 rows | CORRECT |

## 3. Re-fires (c), verbatim; worker DB `litkb_test_w1`, checkout 8150308

`PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w1 py -3.12 qc/instruments/litkb_acceptance.py hardening --fire sidecar --db litkb_test_w1` → exit 0
```
fire=sidecar (litkb_hardening_c1b) arm=control quarantines_without_reason=0 (bound =0)
fire=sidecar (litkb_hardening_c1b) arm=known_bad quarantines_without_reason=1 (bound =0)
fire=sidecar FIRED
```
`PYTHONUTF8=1 PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w1 py -3.12 qc/instruments/litkb_acceptance.py hardening --fire typing_disabled_bad_file --db litkb_test_w1` → exit 0
```
fire=typing_disabled_bad_file (litkb_hardening_c1a) arm=control bad_file_untyped=0 (bound =0)
fire=typing_disabled_bad_file (litkb_hardening_c1a) arm=known_bad bad_file_untyped=1 (bound =0)
fire=typing_disabled_bad_file FIRED
```
**2 of 2 FIRED.** What each fire proves:

- `sidecar` feeds a CONSTRUCTED input through the writer (`Store.to_quarantine`) and reads the builders' counter.
- `typing_disabled_bad_file` exercises the LIVE ladder's write-time typing (`run._type_attempt`) on a
  CONSTRUCTED HTML page.

Neither fire exercises the historical backfill or D29's excusal. Auditor-cand3's OWN7 and the I3W mutation rows
cover those. Section 2.1 scores them on the real rows.

## 4. My own mutations (not among the builders' fires or mutation rows)

Every mutation replaced exactly one occurrence in this checkout and was restored from a saved copy. The sha256 of
each restored file matches the original: `litkb_acq_probe_badfile.py` `d049ecc7…3bb8` and `store.py`
`37551013…8823`. `git status` was clean afterwards.

Baseline, unmutated: `py -3.12 -m pytest qc/test_litkb_accept.py qc/test_litkb_s45_w3.py qc/test_litkb_s45_seams.py`
on `litkb_test_w1` → `101 passed`, exit 0.

### M1 — the instrument's `403 + transport-0 → blocked_not_bad_file` rule removed

The mutation: in `litkb_acq_probe_badfile.type_detail`, `if codes and all(c in (403, 0) for c in codes):` was
replaced by `if False:`.

**Result: the builders' suite does NOT catch it. The instrument gives a worse answer on a real row.**

- pytest: the same three files → **`101 passed`, exit 0.**
- Instrument re-run on live (reader, output to scratch): the real row `Olofsson_2020` `01a0a071` is now typed
  `html_response`/`inferred`, cause `other`. The misbooked count falls to 6. My oracle marks that row WRONG.
- Backfill dry run on that CSV (live, reader, nothing written):
  `offered 21 … plan {'would_apply': 1, … 'already_typed': 20}`. The fill-null backfill WOULD write a false type
  onto a live 403 row, and a fill-null write can never be corrected.
- Why the suite misses it: the rule is pinned only by the FROZEN tracked CSV. No test calls `type_detail` with
  `[403, 0]`. The 202 and `no-pdf-link` rules have unit assertions; this one does not. → N2.

### M2 — `Store.to_quarantine` writes an EMPTY sidecar `{}`

The mutation: `body = reason if reason is not None else {` was replaced by `body = {} if True else {`.

**Result: the pytest goes red. The gated counter and its fire do not notice.**

- pytest: the same three files → **2 failed / 99 passed, exit 1**:
  - `test_to_quarantine_writes_the_sidecar_itself_with_or_without_a_reason`;
  - `test_bytes_libqpdf_does_not_refuse_and_pdfium_cannot_open_reach_the_page_probe_through_the_landing`.
- Probe (`m2_probe.py`, a CONSTRUCTED bad download quarantined through the real `Store.to_quarantine` in a temp
  store): the sidecar body is `{}`. The builders' counter says `quarantines_without_reason = 0`. My oracle's
  content rule says 1.
- Re-fire `sidecar` under M2 → **`FIRED`** (control 0, known-bad 1). The gate and its fire prove that a sidecar
  EXISTS, not that it gives a reason. → N3.

## 5. Rulings on the survey's claims for this class

**R1.** survey-data §3 stated the first number as "free to fix = 8 rows MEASURED (4 works)". Under D12 that is
**not the S4.5 number**. Those 8 rows are the `html_is_the_work` rows (Tkaczyk ×3 and Hickey_2014), and S4.5
builds no HTML landing.

The tracked FIRST NUMBER is a different 8 rows, the `landing_page` rows: 0 measured, 2 estimated, 6 inferred;
6 works; 2 of them without a file. My oracle reproduces it. The two 8s are **different row sets**. The LADDER1
report must name which set it means.

**R2.** "No kept page carries `citation_pdf_url`": **CONFIRMED** on all 69 quarantined payloads (0), not just
on the 9 kept bad-file rows.

**R3.** The survey called the 4 Anna's-sweep rows (Page_1954 ×2, Strong_2003 ×2) "untypable"; the build types
them `html_response`/`inferred`.

How the tokens arise, read in `annas.download_pdf`: each mirror link is fetched with `accept=application/pdf`.
When the bytes fail the magic test, the step records only `host:200`. So "a 200 body that is not a PDF" is
MEASURED. Whether each body was a mirror's "not available" page (item 2's `not-in-archive`) cannot be known,
because no bytes were kept.

- The typing: **CORRECT as an inferred typing**, and the `inferred` basis says so.
- The status (bad-file versus not-in-archive): **UNDETERMINED**.
- Not D29's class. VelasquezCamacho's token records a page that was PARSED and had no PDF link; the sweep's
  tokens record a status and nothing else.

**R4.** "25 of 69 payloads without a sidecar; `Store.to_quarantine` wrote only the filename": **CONFIRMED**.
Exactly the survey's 25 names now carry `"backfilled": true` and are dated the apply. The 44 others predate it
and were not touched. Today 0 are missing.

**R5.** "Misbooked 7 rows / 5 works": **CONFIRMED**. The live NULL set, the CSV's misbooked set and my oracle's
set are the same 7 attempt ids.

**R6.** Codex (a different model family) ruled item 8 "SUPPORTED as a plan transcription, with evidence limits".
It warned that filling a subtype does not establish a diagnosis, and that removing a sidecar proves presence
only. Both warnings are **CONFIRMED on real rows**:

- The 14 `inferred` rows rest on the shape of the response alone.
- M2: an empty sidecar passes both the gate and the fire.

**Conclusions resting on reads no different-model-family agent covered.** Codex read the item-8 DESIGN. It did
not read survey-data §3's per-row readings or the BUILT instrument, backfill and sidecar code (STATE: "Still
owed to Codex: a read of the BUILT code"). The following rest on Claude-family reads only, including this
referee's:

- the D12 reading that the 4 works' HTML is the work;
- the `estimated` grade for the Elsevier rows (Liu, Zhu);
- the reading of the two 202 rows as a WAF interstitial (C7; no bytes exist to check it);
- the free-to-fix status of the 6 inferred landing rows;
- the typing of the Anna's sweep rows.

## 6. Notes (the ACCEPT-WITH-NOTES)

**N1 — WRONG cell: `bytes_kept_path` on 2 rows** (Pfitzmann `01a0adcf`, `01a0c379`).

What the database says, in both the attempt's `detail.quarantined` and `quarantine_payloads.attempt_id`:

| attempt | its own file |
|---|---|
| 01a0adcf | `…a8df07388415.pdf` |
| 01a0add7 | `…a8df07388415.2.pdf` |
| 01a0c379 | `…a8df07388415.3.pdf` |

The CSV names `.2.pdf` for all three.

- Mechanism: the instrument's first match is by sha. The three files hold identical bytes, so
  `by_sha[sha][0]` returns whichever of them the directory walk yields first (`.2.pdf`). The
  `quarantine_payloads` branch that names the right file is never reached. `match_method` still prints
  `sha256+qp.attempt`, as if the two sources had agreed.
- Impact: no typed value, count, counter or backfill reads the column. Only one test does, and it checks that
  the cell is non-empty. The bytes are identical, so the typing is unaffected.
- Fix: prefer the file `quarantine_payloads` names for the attempt, or pick that file among the sha hits.
- Orchestrator's choice, before the freeze pins `probe_csvs_sha256`:
  - regenerate the CSV. The new sha will differ from the `68a28516…` that backfill `01a0d1cd-43c1…` recorded as
    its source; show that the typing columns are identical.
  - or keep the CSV and name the 2 cells in the LADDER1 report.

**N2 — the D29 rule for 403+0 is pinned only by frozen output (M1).** Add a unit assertion beside the existing
202 one: `type_detail("open_access", [403, 0], …)[2] == "blocked_not_bad_file"`. It matters because the
fill-null backfill cannot undo a false type.

**N3 — `quarantines_without_reason` proves that a sidecar exists, not that it gives a reason (M2).**

- The plan's (b) wording ("no `.reason.json` sidecar") is met.
- Its intent is only partly met: item 8 says every quarantine writes WHY.
- Measured today: 0 of 69 sidecars are empty or lack a reason field.
- Recommendation for grading and S4.6: after the run, re-run my walk (oracle Part A: parse plus a reason field)
  over `_quarantine`, or add a REPORTED counter for sidecars with no reason field.

**N4 — payloads that item 8 cannot see by construction** (REPORTED; outside the plan's "every `bad-file` row").

Three HTML payloads have no ledger attempt for their work within the 10 minutes before the file's mtime. So they
came from a request no attempt row records. Each carries a reaper sidecar.

| payload | size | what it is |
|---|---|---|
| Enamorado_2019 `…af05ab5637c8.download` | 5,451 B | Cloudflare "Just a moment..." |
| Kopcke_2010 `…4a8dd106ec85.download` | 9,647 B | "HTTP 403 Forbidden" |
| Winkler_2014 `…7ee96d141d89.download` | 25,773 B | census.gov 404 |

Hickey_2002's `…cc1124db2593.download` (75,824 B) is the D-Lib HTML article itself (title match 100%). It sits
beside an `open_access duplicate-held` attempt, so it is a fifth `html_is_the_work` work outside D12's count.

These go to the substrate class and S4.6 (a ledger row for every request); this is not a defect of the item-8
rung.

**N5 — 16 of the 25 backfilled sidecars say `label: legacy` with a generic reason.** That is honest: the database
holds no cause for them either (`quarantine_payloads.detail.reason_source = "no-label"`). The counter reads 0 for
these payloads, but their reason is "unknown".

**N6 — the `html_is_the_work` marker rule** (`crossref.org` / `dlib.org` anywhere in the page) is a rule for these
rows, in the builder's own words. I ran the instrument's `type_kept` over all 27 real non-PDF payloads:

- On every page whose work is in main it agrees with my title rule: Hickey_2002, Hickey_2014, Tkaczyk ×3.
- It calls a Crossref documentation page (`Crossref_2026_relationships…html`, no work in main) the work. That
  case cannot be scored.

The rule is UNVALIDATED as a general detector. Only the item-8 instrument uses it; the live ladder's typing
(`ledger.sub_status_for`) does not.

## 7. Commands

All run from `D:\edmonds-pipeline\wt-s45-ref-badfile-read\Scripts` unless the path is absolute. The scratch
folder is `D:\tools\claude-config\jobs\litkb-s4-5\scratch\referee-badfile-read\`.

- `py -3.12 <scratch>\locks.py`: `pg_stat_activity` and advisory `pg_locks` → empty, before every DB use.
- `py -3.12 <scratch>\oracle.py` → `oracle_out.json`. `show.py` / `mdtable.py` build the tables. `pf.py`: the
  Pfitzmann pairing. `wk.py`: Winkler's attempts and the live sub_status census. `orph.py`: the orphans' nearest
  attempts. `all_payloads.py`, `cpu.py`, `typekept_all.py`: all 69 payloads.
- `PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_acq_probe_badfile.py --db litkb --out <scratch>\control_badfile.csv`
  → identical totals; sha256 `68a28516…` equal to the tracked CSV, main's copy and `live\badfile_live.csv`.
- The re-fires in §3. Mutations: `py -3.12 <scratch>\mutate.py apply|restore M1|M2`. The pytest command in §4.
  `py -3.12 -m litkb.acquire.ledger --db litkb backfill-sub-status --csv <scratch>\M1_badfile.csv --session referee-dry`
  (dry run, reader).
- `py -3.12 <scratch>\m2_probe.py` (temp directory only).

Nothing was written to live, to the corpus, or to main. This report is uncommitted in the referee checkout.

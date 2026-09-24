# litkb S4.5 referee: rung class `stage-e` (plan item 6)

Referee: `referee-stage-e` (Opus 5.5, fresh agent). I did not build, propose, integrate or audit any part of S4.5.
Checkout: detached `D:\edmonds-pipeline\wt-s45-ref-stage-e` at main `2ef3d68`. Worker DB: `litkb_test_w12`. Before I
used it, it held no advisory lock and had no session. Live `litkb` was read only, as `litkb_reader`. The corpus was
read only. No network was used.

Inputs, all read-only from the main tree:
- manifest `hardening-1` (frozen 2026-09-24T08:22:40.799Z, sha256 `5873d3fc…` on disk)
- run CSV (195 rows, sha256 `8ddad087…`)
- cassette index (3,632 interactions, sha256 `4566ea28…`, equal to the recording report's `index_sha256`)
- body store `D:\edmonds-pipeline\litkb_derived\cassette_bodies`
- the driver's printed lines in `run-full-3.out`

Full working notes: `D:\tools\claude-config\jobs\litkb-s4-5\referee-stage-e.md`. Every script named below is in
`D:\tools\claude-config\jobs\litkb-s4-5\scratch\referee-stage-e\`.

## Verdict: REJECT, scoped to Stage E's input on one row (L007; the same cause on L054)

**What works.** The three Stage E rungs fetched, typed and recorded correctly on every real attempt the run made:
- E1 `wayback`: 119 spent attempts and 10 skips
- E3 `ia`: 99 spent attempts and 11 skips
- E5 `commoncrawl`: 14 spent attempts and 102 skips

My oracle reads the recorded archive answers itself and agrees with every one of those 355 rows. In addition:
- Every capture asked for a raw-bytes modifier.
- The host cool-down sent no request to a cooling host (0 of 9 windows).
- All 102 Common Crawl skips carry the measured reason.

**What is wrong.**
- **L007.** This is item 6's one real MUST-convert row: the IIASA copy of 187's DOI, re-graded positive by D23. E1
  was never asked about its dead link. The same run recorded that link:
  `pure.iiasa.ac.at/…/CEOS_WGCV_LPV_Land_Cover_protocol_Sept2025_V1.pdf` answered 404 to the OpenAlex rung at 01:40:50.
  The frozen manifest names this URL as "Stage E1's input". C2c's tracked recording shows the Wayback Machine holds it
  (capture `20251206182454`).
  - **Why it never reached E1.** `recovery.urls_of` reads only `rejected_url`, `source_url`, `terminal.url` and `tried`
    from a route dict. The OpenAlex rung recorded the dead location only as the host token `pure.iiasa.ac.at:404`. Its
    terminal is the live `…_V1.0.pdf`, which answered 200 and was refused by the binder. So the URL appears nowhere in
    the row's attempt rows. I checked every attempt of the work.
  - **What E1 did instead.** It asked about the live V1.0 URL, a DOAJ API URL, an OpenReview API URL and a NASA HTML
    page. All four were correctly proven absent: availability `{}` and CDX `[]`. So the row ended `blocked/not_found`.
  - **The work's final state is unchanged.** The binder refuses this work's bytes from any route (corporate first
    author). The driver printed the `exception:` line for it, on `openalex`.
  - **What changes is Stage E's measured conversion.** `wayback_rows_unconverted=1` is REPORTED. The gated
    `free_ceiling_measured_unconverted` excuses the work through a binding refusal on another route, so no gate sees
    this miss.
  - L054 (OpenAIRE's `hdl.handle.net/10810/59883`, 404) was missed by the same seam. There the URL sits only inside
    OpenAIRE's `detail.reason` text. Whether it is archived is UNDETERMINED.
- **L022.** This is item 6's real NEGATIVE: the census.gov capture, which is another work. E1 booked it `measured`,
  so the ledger counts another work's PDF as a hit for 10.1002/wics.1317. MEASURE mode judges bytes, not identity.
  D23 anticipated this, and REPORTED `wayback_wrong_work_counted=1` names it. Nothing was landed. E1's yield must be
  read as 9 true of the 10 works `rung_conversions_wayback` counts.

**If this is fixed.** A fix to the input seam changes rung code. By the protocol it then needs a re-freeze and a re-run
of the affected rows (L007, L054), never the old rows graded under new code. Whether to do that now or carry it to S4.6
is the orchestrator's decision.

fired: wayback_rows_unconverted=1 on a CONSTRUCTED admission replaying the REAL recorded census.gov capture with the Wayback rung removed from the registry (stage_e_wayback_rung_disabled, litkb_test_w12, re-fired by referee-stage-e at 2ef3d68)
fired: wayback_rows_unconverted=1 on a CONSTRUCTED wrapper page at the bare capture URL around the REAL census.gov bytes with the raw modifier removed (stage_e_raw_modifier_removed_constructed, litkb_test_w12, re-fired by referee-stage-e at 2ef3d68)
fired: wayback_negatives_mistyped=1 on a CONSTRUCTED never-archived URL with the rung's not_found typing removed (stage_e_not_found_typing_removed_constructed, litkb_test_w12, re-fired by referee-stage-e at 2ef3d68)

## 1. The oracle (mine; it calls no `litkb.acquire` or `qc/instruments` logic)

The one import is `oracle_e3_e5.py` reading the TEXT of `policy.COMMONCRAWL_OFF_WHY`, to compare the skip reasons
against it byte for byte.

- `cas.py` reads the cassette index as JSONL. It loads a body inline or from the store and checks the body's sha256
  against the recorded one. It classifies each request by host and path, using the rung names from the plan.
- `oracle_e1.py` (E1). For each spent `wayback` attempt it takes that work's recorded Wayback requests between the
  previous `wayback` attempt and this one. All 572 recorded Wayback requests were attributed; none was left over. It
  classifies the attempt by rules I wrote from the plan text:
  - a capture answered 200 with `%PDF-` in its first KiB: the attempt must show served bytes (`ok` / `measured` /
    `duplicate-held` / `known-bad` / `binding-failed`)
  - any answer of 0, 408, 429 or 5xx: `api-error`, retriable (D15)
  - the ledger row names a cool-down stop: `api-error`, retriable (D44/D45)
  - a capture answered 200 with something other than a PDF: `bad-file` (D33)
  - every URL shows availability JSON with `archived_snapshots` an object and no closest capture of status 200, AND
    CDX answered 200 with at most a header row: `blocked/not_found`
  - anything else: `api-error`, not retriable
- `oracle_identity.py` reads every PDF a Stage E rung was served with **pypdf**, not litkb's pikepdf, pdfium or
  pdftotext path. It records the page count, the text of pages 1–2, the record title's word coverage, the first
  author's surname and the latest year cited. It compares these with the work's registry record in `main_works`
  (title, first author, year, `pages` a-b).
- `oracle_e3_e5.py`:
  - E3: parses the recorded item-search JSON and applies my own identity rule. A hit is the work if it carries
    `urn:doi:`, or if the title words match symmetrically at 90% or more and the creator names the first author.
  - E5: checks the terminal codes, the skip reasons (compared byte for byte with `policy.COMMONCRAWL_OFF_WHY`) and
    the Common Crawl request times.
- `dead_urls.py` lists every dead document link the run recorded: a non-archive, non-API GET that answered 404 or 410.
  It then checks whether E1 was asked about that link.
- `cooldown.py` takes every cool-down window the ledger names (host, cooled_at, cool_until) and looks in the cassette
  for any request to that host inside the window.

X9: I read the builder's counters (`builder_counters.py`, as reader) only to compare them with my oracle, never as
the oracle.

## 2. Scored rows

### 2a. The rows the plan names for this class

| row | expected (plan + D23) | what the run did (ledger / run CSV) | my oracle | verdict |
|---|---|---|---|---|
| **L007** 10.5067/doc/ceoswgcv/lpv/lc.001 (hunt; run CSV `blocked/challenge`) | + E1 recovers the archived IIASA copy; its bytes pass acceptance; the binder refuses the corporate author, giving a named exception (D23) | E1 asked 4 URLs, none of them the dead V1 URL (V1.0 live, DOAJ API, OpenReview API, lpvs documents.html) and ended `blocked/not_found`. The binding refusal came from `openalex` on the live V1.0 copy (188 pages; the DOI on pages 1–3 by my reader). The `exception:` line was printed, on openalex | The V1 URL answered 404 at 01:40:50 (cassette). It is absent from every attempt row of the work, and E1 never requested it. For the 4 URLs E1 did ask, availability `{}` and CDX `[]` were recorded, so `not_found` is correct for them | **WRONG** (input seam: E1 never offered the row's dead link) |
| **L022** 10.1002/wics.1317 (measure) | − the census.gov capture is ANOTHER work and must not count as the work | E1 `measured`: capture `20210322000835id_`, sha `b3cd70fd…` (the same sha as C2c's tracked fixture) | pypdf: 38 pages against the record's 313-325 (13 pages); latest year cited on pages 1–2 is 1993 against the record's 2014; page 1 reads "U.S. Bureau of the Census". So: ANOTHER-WORK | **WRONG** as a measured hit (identity-blind MEASURE; named by REPORTED `wayback_wrong_work_counted=1`; not landed) |
| IIASA "must end `not_found` at E1" (the plan's original negative) | re-graded by D23 as unmeetable | L007's E1 row did end `not_found`, but for the live V1.0 URL and three non-document URLs | The never-archived question was never put to a real dead URL | **UNDETERMINED** |

### 2b. Every Stage E attempt of the run: the "E3/E5 yield over every run row with a dead URL" row

| attempts | my oracle class → what the ledger recorded | n | verdict |
|---|---|---|---|
| E1 spent | pdf → ok 4, measured 7 (6 works; L019 twice), duplicate-held 1, known-bad 3 | 15 | CORRECT status |
| E1 spent | nonpdf → bad-file `html_response` 11, `compressed_or_archived_payload` 7 | 18 | CORRECT status; 7 labels misleading (N3) |
| E1 spent | absent → `blocked/not_found` | 26 | CORRECT |
| E1 spent | transient → api-error, retriable | 30 | CORRECT |
| E1 spent | cooled (D44) → api-error, retriable, with `cooldown_skipped` | 30 | CORRECT |
| E1 skips | `backoff_window` with `detail.cooldown` 9, `dead_in_run` 1 | 10 | recorded with reason |
| E3 spent | 97 answers with zero hits → `not_in_corpus`; L133's 2 hits are other works by the symmetric title rule → `not_in_corpus`; L021's arXiv-mirror item `arxiv-1502.04592` → `measured` | 99 | CORRECT |
| E3 skips | `backoff_window` (archive.org cooling, trigger route `wayback`: D45 across routes) | 11 | recorded with reason |
| E5 spent (pass 1, before the switch) | api-error, retriable: terminal 504 ×8, 502 ×5, transport 0 ×1; 8 works; 6 are scheduled retries | 14 | CORRECT (matches the off-reason's "13 of 14; one transport failure") |
| E5 skips (from 03:17:37 PDT) | `skipped/policy_refused`, reason == `COMMONCRAWL_OFF_WHY` | 102 | CORRECT: 102 of 102 carry the measured reason |

Total: **355 attempts, 355 CORRECT at the status level**. My first E3 rule was one-sided, and it called L133's two
arXiv hits the work. Those hits are "Kalman Filtering with Intermittent Observations: Weak Convergence…" and "Towards
Finding the Critical Value for Kalman Filtering…", both longer titles and both other works. The rung was right; I
corrected my own rule to the symmetric one and re-ran.

**Identity of every PDF a Stage E rung was served** (pypdf against `main_works`):

| row | route / status | pages (pdf / record) | verdict |
|---|---|---|---|
| L019 Girard_2019 (HAL) | wayback measured | 5 / 4 | SAME-WORK |
| L022 Winkler_2014 | wayback measured | 38 / 13 | **ANOTHER-WORK** |
| L029 Kingman_1962 | wayback duplicate-held (equals the unowned corpus file) | 11 / 11 | SAME-WORK (page 1 prints "14--24 (1962)"; my author test missed only on OCR, "KINGMkN") |
| L042 Sosa_2025 | wayback ok (arXiv v1 via orbilu) | 11 / 6 | SAME-WORK (the preprint edition, which the plan's FREE-PDF convention accepts) |
| L050 Ortega_2024, L051 Culbert_2025, L074 Coulter_2008, L155 Martinis_2010, L156 Motohka_2010 | measured / ok | page counts equal the record's range | SAME-WORK |
| L060 Appel_2024, L066 Ploton_2020 | ok / measured | 14 / –, 11 / – | SAME-WORK (title 0.93 / 1.0, author found) |
| L075 Thakur_2021 | wayback known-bad (refused 09-22, binding-failed) | 24 / – | SAME-WORK, nothing written |
| L110 Hickey_2002 | wayback known-bad | 66 / – | **ANOTHER-WORK** (Hegna & Murtomaa, "Data mining MARC to find: FRBR?"). The known-bad lookup kept it out: CORRECT |
| L165 Chen_2014 | wayback known-bad (the same bytes refused by the binder earlier in this row) | 5 / 5 | SAME-WORK, nothing written |
| L021 Bacry_2015 | ia measured | 48 / – | SAME-WORK (arXiv 1502.04592, "Hawkes processes in finance") |

**Yield, measured on the run (my numbers against the builder's REPORTED counters):**
- **E1.** Asked for 105 works (builder: `rung_asked_wayback=105`).
  - 58 works got a complete answer. 47 got only transient or cooled answers, so their E1 yield is UNDETERMINED.
  - 10 works were hits (builder: `rung_conversions_wayback=10`), 9 of them the right work.
  - Landed: 4 (L042, L060, L155, L156).
- **E3.** Asked for 96 works: 1 identified item, measured on a work already held, 0 conversions.
- **E5.** Asked for 8 works before the switch: 24 index 404s and 13 index 5xx. No work got a complete answer, so the
  yield is **UNDETERMINED** (host unavailable, D39/D40), never zero.
- **Cost.** Stage E made 724 of the 3,632 recorded requests (19.9%): 572 Wayback, 101 IA, 51 Common Crawl.

**Did the dead links reach Stage E?** In 14 rows the run recorded a dead document link. E1 was asked about it in 2
(L022's census URL and L099's eprints URL). Of the 16 links it missed:
- 5 in the cooling rows L102, L071, L147 (2) and L124: E1 was stopped before it asked about them.
- 6 in L155, L156, L074: Stage C's constructed MDPI CDN guesses. E1 hit those works through `www.mdpi.com` anyway.
- 3 in L058, L041, L044: OUP `/doi/pdf/` guesses. On L058 and L044 I checked where they sit: only in
  `detail.landing.candidates`, which `recovery` does not read. They are constructed guesses, so leaving them out is
  defensible.
- **2 registry-asserted dead links never offered: L007's V1 URL (the WRONG above) and L054's handle.**

## 3. Re-fires (c), verbatim (`hardening --fire <name> --db litkb_test_w12`; exit 0 each)

```
fire=stage_e_wayback_rung_disabled (litkb_hardening_c2c) arm=control wayback_rows_unconverted=0 (bound =0)
fire=stage_e_wayback_rung_disabled (litkb_hardening_c2c) arm=known_bad wayback_rows_unconverted=1 (bound =0)
fire=stage_e_wayback_rung_disabled FIRED
fire=stage_e_raw_modifier_removed_constructed (litkb_hardening_c2c) arm=control wayback_rows_unconverted=0 (bound =0)
fire=stage_e_raw_modifier_removed_constructed (litkb_hardening_c2c) arm=known_bad wayback_rows_unconverted=1 (bound =0)
fire=stage_e_raw_modifier_removed_constructed FIRED
fire=stage_e_not_found_typing_removed_constructed (litkb_hardening_c2c) arm=control wayback_negatives_mistyped=0 (bound =0)
fire=stage_e_not_found_typing_removed_constructed (litkb_hardening_c2c) arm=known_bad wayback_negatives_mistyped=1 (bound =0)
fire=stage_e_not_found_typing_removed_constructed FIRED
```

3 of 3 FIRED. All three fires use a CONSTRUCTED admission, and two use CONSTRUCTED answers. None of them exercises the
input seam that failed on L007.

## 4. My own mutations (not in the C2C mutation rows)

Suite: `qc/test_litkb_stage_e.py` on w12. Baseline: 72 passed in 15.9 s. One process per run. After each run I
restored `wayback.py` from a copy. The sha256 afterwards was `2d2ad8f7…17709`, equal to the original, and
`git status` was clean.

- **R1 (FIRED).** In `wayback.parse_cdx`, CDX captures are ordered oldest-first (`reverse=True` → `reverse=False`).
  Result: `1 failed, 71 passed`. The failing test is `test_at_most_captures_per_url_captures_are_fetched`: it fetched
  `20150101000000`/`20160101000000` instead of the newest two, `20160101000000`/`20170101000000`.
- **R2 (SURVIVED, a finding).** In `wayback.cdx_url`, the survey's `filter=statuscode:200` is dropped. Result:
  `72 passed`. No test pins the CDX query. Codex's Item 6 review named exactly this ("E1's status/MIME filtering and
  digest collapse"), and SCHEMAS' definition of `not_found` ("proves NO USABLE SNAPSHOT") rests on it. My expectation,
  which I did not run: a register replay would fail closed on the changed cassette key.

## 5. The dispatch's two measurements

**Common Crawl (D39/D40).**
- The last Common Crawl request recorded was at 02:03:08 PDT, in pass 1.
- The first skip was at 03:17:37 PDT, at the start of pass 2.
- No Common Crawl request was recorded after the first skip.
- 102 of 102 skip rows are `skipped/policy_refused`, and their reason equals `COMMONCRAWL_OFF_WHY` byte for byte.
- The 14 rows before the switch were ASKED. Each ended on a 502/504 (13) or a transport failure (1).
- E5's yield is UNDETERMINED.

**Host cool-down on the pass-3 rows (D41/D44/D45/D46).**
- 50 attempts carry cool-down facts: 20 skips (`backoff_window`: 9 wayback, 11 ia) and 30 wayback `api-error`
  retriable rows with `cooldown_skipped`. All 50 are in pass 3.
- The 9 windows named on those rows are:
  - web.archive.org: 503 at 16:59:44Z (70 s), 17:00:59Z (138 s), 17:07:33Z (268 s), 17:14:32Z (300 s)
  - web.archive.org: 504 long-wait at 17:20:49Z, 17:45:41Z, 17:57:53Z
  - archive.org: 429 at 18:09:02Z and 18:14:28Z
- Each trigger matches a real recorded 429/503/504 at that second.
- The cassette holds **0 requests to a host inside any of its 9 windows**, from any row.
- archive.org cooled both routes (D45). No 403 and no challenge started a cool-down.
- Pass-3 rows: median wall time 31.4 s, maximum 263.8 s, 0 at 500 s or more, 0 budget-stops. For comparison, pass 2
  had a median of 115.5 s and 2 budget-stops.
- **Gap (N5).** Six earlier pass-3 answers (503/429) started windows that no later row reached, so no row records
  them. A triggering row does not carry the facts of the cool-down it started, so those windows cannot be audited from
  the ledger. By the AIMD rule (READ from `backoff`) they lasted seconds; the next request from another row came 46 to
  102 s later.
- **Price of the cool-down.** 29 works ended with only a cooled E1 answer, and no row is revisited within the run.

## 6. The survey's Stage E claims that the real rows can decide

| claim (survey-design Item 6 / PDF-sources §1 Stage E) | what the run shows | ruling |
|---|---|---|
| "the raw-bytes modifier is MANDATORY or you store Wayback's HTML wrapper" | Every run capture used `id_` (then `if_`); no bare capture was ever fetched. C2c's recording: the bare census capture served the same PDF. New and measured: `id_` passes through the ORIGINAL `Content-Encoding`. 7 of 18 archived HTML pages came back gzip under `id_` and plain under `if_` | UNDETERMINED for "mandatory"; `id_` measured to work (14 of 14 PDFs) |
| "CDX gave 503 + 40 s timeout — back off hard" | CDX answered 503 ×11 and 504 ×7 out of 228 requests. Availability answered 429 ×11, and one capture answered 429. None of these 30 answers sent a `Retry-After`, so "honour Retry-After" never had one to honour | CONFIRMED (5xx recur; the back-off was AIMD) |
| CDX's no-result shape (auditor-C2c-r2 F9: never recorded) | 207 of 207 no-row answers were `[]`; availability with no capture was `{}` 232 times | MEASURED |
| E3 "free fan-out, yield measured by the run" | 96 works, 1 identified item, 0 conversions; no dark or lending item was ever reached | yield MEASURED ≈0; `is_dark` and lending UNDETERMINED |
| E5 "low yield, near-zero cost" | The index answered 502/504 after up to about 270 s per request; switched off | cost claim FALSE on this run; yield UNDETERMINED |
| §M's census.gov copy is E1's positive | the run's own bytes: 38 pages, 1993, Census Bureau | FALSE (D23 confirmed on the run's bytes) |
| §M's IIASA copy "never archived" | V1 answered 404 live in the run; C2c's 09-23 recording shows it archived; E1 was never asked in the run | FALSE on the 09-23 recording, not re-measured by the run |
| Stage E converts "a DEAD link" (recovery's "a Stage B rung's dead link reaches Stage E in the same pass") | 2 registry-asserted dead links never reached E1 (L007, L054); 264 of 572 E1 requests (46%) asked about metadata-API URLs instead (`doaj.org/api/…`, `api2.openreview.net`, which the `api.` host prefix misses). They took slots under the 5-URL cap, which refused one URL each on L155 and L108. The ledger does not name which URL | FALSE as built |

**Different-model-family coverage.** Codex's design review covered Item 6 at the transcription level only: whether the
digest carries the survey's mechanism and guards. It found the IA `is_dark`/lending/identity checks, the Common Crawl
Range retrieval and E1's status/MIME filter missing from the digest. No different-model-family read covered:
- the survey's two E1 rows (both now FALSE)
- the "near-zero cost" of E5
- `recovery`'s input rule and its API-host heuristic
- the MEASURE-mode identity blindness

Those conclusions rest on Opus-only reads (survey-design (f): "Codex. None").

## 7. Notes (numbered for the orchestrator)

- **N1 (the REJECT).** `recovery.urls_of` / `ledger_urls` see only 4 route-dict fields. A multi-location Stage B rung
  (OpenAlex) records its failed locations as host tokens, and URLs inside `detail.reason` text or
  `detail.landing.candidates` are never read. Fix scope: Stage B records each asked URL, or `recovery` reads the
  candidate lists. Then re-freeze and re-run L007 and L054.
- **N2.** The API heuristic (`host.startswith("api.")`) misses `doaj.org/api/…` and `api2.openreview.net`. That cost
  264 Wayback requests (46%), spent while archive.org was rate-limiting this client, and crowded the 5-URL cap.
- **N3.** 7 archived HTML landing pages are typed `compressed_or_archived_payload` rather than `html_response`
  (L037 L040 L044 L045 L061 L113 L114). E1 keeps the FIRST non-PDF body, the `id_` one, which carries the original
  gzip Content-Encoding, over the decoded `if_` body. The status is right; the cause label varies with the origin
  server's encoding.
- **N4.** MEASURE mode's `measured` carries no identity check. L022 is the one false hit, named by
  `wayback_wrong_work_counted`. In acquire mode the binder (title + first author) would accept the census report as
  the 2014 article, so a page-count/year rule is needed. That is a binder change, out of S4.5 by D23.
- **N5.** A triggering row does not record the cool-down facts it started, so windows nobody hit cannot be audited.
  Cooled rows are never revisited within the run: 47 of 105 E1 works are unanswered.
- **N6.** The gated counter cannot see E1's miss on L007. `free_ceiling_measured_unconverted` excuses the work
  through a binding refusal on ANY route, so E1's only hook is the REPORTED `wayback_rows_unconverted=1`.

## 8. Not done, and why

- No live write. No network: the V1 capture was not re-fetched, so "IIASA is archived" rests on C2c's tracked
  recording.
- No `hardening --replay`: it would overwrite main's `_derived` summary, and replay is its own referee's job.
- No full suite: the brief asks for fires and my own scripts only.
- Item 5b is out of scope (Scope ruling).

## 9. Commands my claims rest on (from `D:\edmonds-pipeline\wt-s45-ref-stage-e\Scripts`, `PYTHONUTF8=1`)

- `py -3.12 <scratch>/lockcheck.py`: w12 locks `[]`, sessions `[]`.
- `PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w12 py -3.12 qc/instruments/litkb_acceptance.py hardening --fire <name> --db litkb_test_w12`, run once for each of the 3 fires.
- `py -3.12 <scratch>/stage_e_rows.py`: census of the run's Stage E attempts (355 attempts, 114 works; 3,842 attempts and 187 works in the whole run).
- `oracle_e1.py`, `oracle_identity.py`, `oracle_e3_e5.py`, `dead_urls.py`, `cooldown.py`, `where_url.py`, `two_rows.py`, `one_attempt.py`: all read-only (the cassette, bodies and live as `litkb_reader`).
- `builder_counters.py`: the builder's REPORTED counters on live as reader, for comparison only.
- `PYTHONPATH=pipeline LITKB_TEST_DB=litkb_test_w12 py -3.12 -m pytest qc/test_litkb_stage_e.py -q -p no:cacheprovider`: baseline, then R1, then R2.

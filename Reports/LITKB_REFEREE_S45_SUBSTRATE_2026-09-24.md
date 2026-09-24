# litkb S4.5 referee — rung class SUBSTRATE (plan item 1), 2026-09-24

Referee: `referee-substrate` (Opus 5.5). I did not build, propose, integrate or audit this class. Checkout: detached
`2ef3d68` at `D:\edmonds-pipeline\wt-s45-ref-substrate` (left clean). Worker DB: `litkb_test_w3`. I checked the advisory
locks first; w3 was free, and I reset it after every use. The live `litkb` database was read only, as `litkb_reader`.
I made no network request: every script ran behind a socket guard, and it logged 0 refused attempts. The corpus was
read only; 187's PDF was copied and never moved. Run manifest `hardening-1` (frozen 2026-09-24T08:22:40.799Z, head
`cd2f23b`, sha `3c918f64…`). The run wrote 3842 attempts over 187 works after `frozen_at`, all of them in ladder-1.
Working notes: `D:\tools\claude-config\jobs\litkb-s4-5\referee-substrate.md`. Scripts and outputs:
`D:\tools\claude-config\jobs\litkb-s4-5\scratch\referee-substrate\`.

## Verdict: ACCEPT-WITH-NOTES

- Every real row the plan names for this class does what the plan says. That is 17 rows: 16 CORRECT, 1 CORRECT
  with a named D23 gap in the binder, 0 WRONG.
- All 17 (c) known-bads FIRED on `litkb_test_w3`.
- My own mutation M1b FIRED: 3 builder tests turned red. It also exposed a blind spot, N4.
- There is no WRONG run outcome, so nothing needs a re-freeze or a re-run.
- Two notes are **fix-before-the-next-ladder-run**:
  - **N1**: the persisted refusal ladder was never seeded from the pre-0033 ledger. On 10 real (route, work) pairs, the
    window the enforcement stored (15 min) differs from the window the gate replays (6 h).
  - **N2**: arXiv's `406` is now a standing refusal of this client, and litkb books it as transient.

fired: rehunt_route_spends=2 on E13 re-hunted with the back-off window set to zero (backoff_window_zero, litkb_test_w3)
fired: key_derivation_crashes=1 on 187's DataCite record with the key rule reverted (key_rule_reverted, litkb_test_w3)
fired: known_bad_relands=1 on E13's challenge bytes re-served with the rejected-hash lookup disabled (known_bad_lookup_disabled, litkb_test_w3)
fired: proposals_unadjudicated=1 on 194's proposal with the refuse verb removed (refuse_verb_removed, litkb_test_w3)
fired: relation_probe_rows=0 on the relation probe CSV emptied (relation_probe_emptied, litkb_test_w3)

## 1. My oracles (independent of the builders' detectors; X9)

1. **O1, the refusal ladder.** `backoff_oracle.py`, `backoff_persisted.py` and `backoff_exposure.py` replay the ladder
   over the live `acquisition_attempts` timestamps. They import no litkb code, and the rules come from the plan's text and
   the PDF-sources survey's guard 2:
   - The ladder is 15 min → 6 h → 48 h, counted over a trailing 7 days.
   - A refusal is `blocked` or an http code in {202, 403, 429, 503}. I call this variant V_status; V_codes counts the
     codes alone.
   - A success (`ok` / `measured` / `duplicate-held`) resets the ladder.
   - When an attempt was retried, the retry replaces the original.
   - A skip spends nothing.
   - O1 is scored against the run's spends, its `skipped/backoff_window` rows and the persisted `litkb.route_backoff`.
2. **O2, the key rule.** `landing187.py` part A. The works_key_check regex is read from `pg_constraint` on the migrated
   worker DB and applied by my own `re` code to `make_key` output. The input is the REAL DataCite creator, taken from the
   run's own recording of L007.
3. **O3, identity and decision-log SQL.** My own SQL:
   - duplicate (scheme, value_norm) across works;
   - NULL `asserted_by`;
   - the unique index predicate against the plan's pinned distinct list;
   - E21's works, identifiers, edges and parent columns;
   - E06's admissions;
   - 194's admission, its versions and its decision row;
   - decision-log immutability, attempted on w3 as the table owner and as `litkb_writer` (`declog_oracle.py`);
   - cross-work identifier claims on live;
   - a CONSTRUCTED conflict scored by my SQL, not by `conflicts_uncounted` (`conflict_oracle.py`).
4. **O4, the landing.** `landing187.py` part B. A real loopback HTTP server serves the copied 187 bytes. I score the
   hunt with my SQL, a filesystem walk of the tmp literature root, my own sha256, and my own first-page read
   (`pdftotext -f 1 -l 3`).
5. **O5, the relation probe.** `relation_oracle.py` reads the CSV with my own reader. It cross-checks against the
   independent 09-22 crosswalk probe and against the run's `work_relations`.
6. **O6, the arXiv 406.** `arxiv406.py` reads the cassette index. `arxiv_cache*.py` reads the registry disk cache.
   `landing187.py` part C sends the real `registry.arxiv_record` to a loopback server and logs the exact request headers.

## 2. Scored real rows (the plan's §5 substrate row)

| row | expected (plan / ruling) | what the rung did (ledger, run CSV) | my oracle's answer | verdict |
|---|---|---|---|---|
| **E13** L002 (+, back-off) | no spend inside an open refusal window; the route is asked again only after its window; converts via arXiv (D10) | 17 attempts; `bound-unextracted/fresh-bound` in 5.14 s (arxiv `ok`); open_access asked, `blocked [403]` | O1: the last earlier refusal on (open_access, E13) was 2026-09-21 03:10 PDT, 70.4 h before the run's ask, so every rung (≤48 h) had lapsed under both readings; 0 spends in a window | CORRECT |
| **L010–L017** (+, 8 ruled arXiv rows) | `api-error/registry-transient`; nothing admitted or written; the message says retry | all 8 `api-error/registry-transient`, attempts_written 0, 0.28–0.61 s each | O6: cassette `406`, empty body, no Content-Type ×8. O3: 0 admissions, 0 works, 0 candidates after `frozen_at`; no arxiv/10.48550 identifier in main. Loopback: `arxiv_record` → (None, 406), `is_transient(406)=True`, exactly 1 request, no retry | CORRECT ×8 (N2, N3) |
| **E21** L001 (+, relation edge) | two works, one edge, no alias | measure row, 27 attempts, `measured` | O3: one `is_preprint_of` edge 01a0d28a… (asserted_by crossref, derived_from doi 10.1101/357798, ws ladder-1) → the article work; the preprint's `version_of_work_id` = the article; each DOI on its own work only; the harvested openalex/mag ids (W2811322865 / 2811322865) are the PREPRINT's own, because the recorded OpenAlex body says `doi: 10.1101/357798, type: preprint` | CORRECT (N5) |
| **194** live refusal (+, read-only) | admission declined; versions rejected; decision row with proposer ≠ decider | this session's refuse, applied on 2026-09-23 | O3: admission 01a0c730… `declined`; work, identifier and file versions 1/1/1 `rejected`; adjudications 01a0d0e3… verb refuse, proposer `s3-wrap-hunts-2` ≠ decider `s4-5`; proposed admissions 0; triggers `adjudications_append_only` (UPDATE/DELETE, per row) and `adjudications_no_truncate`; no role but the owner holds INSERT/UPDATE/DELETE/TRUNCATE. On w3 as the table owner, UPDATE, DELETE and TRUNCATE were each refused ("the decision log is append-only"); as `litkb_writer`, permission denied; the row was unchanged | CORRECT |
| **187** DataCite record → key rule (+) | `make_key` derives a key the DB accepts; no `crashed/admit:CheckViolation` | L007 recorded DataCite 200 (body sha c3d1ef4f…); live key `LPVSubgroup_2025_…` came from a hand `--key`, and the run never calls make_key for 187 | O2: creator familyName "Land Product Validation Subgroup (Working Group on Calibration and Validation" → `LPVSWGCV_2025_land-cover-change-map` (35 chars), which PASSES `^[A-Za-z]+_[0-9]{4}[ab]?_[a-z0-9]+(-[a-z0-9]+){1,4}$`, len < 60; the reverted rule (`key[:59]`) gives `LandProductValidationSubgroupWorkingGroupOnCalibrationAndVa`, which FAILS. Admitted on w3 through the real DOI path (spend=False, a client answering only from L007's recording: Crossref 404, then DataCite 200) → `held/no-spend`, 0 crashed admissions, doi asserted_by caller, verified_by datacite | CORRECT |
| **187** filed PDF → URL-path refused-duplicate landing (+, w3, loopback) | offered to its work through check 3; never left unowned; no second copy | the live URL leg L008 was dropped by the run plan; refereed here | O4, hunting `http://127.0.0.1:<port>/PDF/CEOS_WGCV_LPV_Land_Cover_protocol_Nov2025_V1.1.pdf` with the ruled URL-leg inputs (tracker title, Tyukavina, 2025) in a second session: admission refused `duplicate-review` (similarity 0.917 to the 187 work); offered to that work → `binding-failed`; quarantined with a `quarantine_payloads` row (origin hunt-url, work named, 7,623,037 B) and a `.reason.json` (sha 94d8fbed…, offers, source_url, moved_from filed/); 0 `files` rows; exactly 1 copy of the bytes on disk; 0 unowned in filed/. My page read shows page 1 carries the exact registry title AND the DOI `10.5067/doc/ceoswgcv/lpv/lc.001`, so check 3's refusal is a FALSE NEGATIVE: D23's named corporate-author gap | CORRECT for the landing; the binder verdict is the named D23 gap (N6) |
| relation probe CSV (+) | `relation_probe_rows>=1` from answered rows | gate reads 458 | O5: 490 rows / 466 DOIs; 458 answered (all cr_status 200), 32 unanswered (404), 44 asserted relations; CRLF-folded sha `ec58a620…` = the manifest pin. Crosswalk cross-check: the type sets match on 430/434 DOIs, and the 4 differ ONLY by citation relations (references / is-referenced-by). The run's 20 crossref edges = the probe's asserted edges for those works, 0 missing either way | CORRECT |
| **E06** (−, read-only) | a page with no confirmed identifier, title-near an existing work, refuses `duplicate-review` | edges-1's two admissions | O3: 01a0c371… and 01a0c37d… are both `refused` (manual), check2 `duplicate-review` against Tkaczyk_2024 at similarity 1 (threshold 0.7). Current code: the fire `e06_still_duplicate_review` FIRED, and the same check-2 path refused `duplicate-review` in my 187 URL run | CORRECT |
| CONSTRUCTED second work claims a DOI (−, w3) | refused; the edge written; the event counted | the builder's `conflict_world` built the input (the real `record_identifiers`) | O3, my SQL: the DOI is held by A only (B never got it); claim outcome `conflict`, held_by A; `identifier_conflicts` row B→A, resolution `dropped`, pointing at edge 01a0d4c7-9391…; that edge is B `is_version_of` A, asserted_by `conflict-resolution`. Live: 1174 claims, 0 against another work, so the live `conflicts_uncounted=0` is vacuous | CORRECT |
| CONSTRUCTED self-approved chain (−, w3) | the proposing session's own decision is refused | fires `self_refusal`, `promotion_prepared_by_the_run` FIRED | O3: an adjudication row whose session equals its proposer's is refused by `adjudications_second_session_decides` for approve and for refuse, with the identical label and with a zero-width-space variant. A case/space variant (`' Session-A '` vs `'session-a'`) is ACCEPTED (N8) | CORRECT (the chain itself is covered by the fire only) |

In addition, I measured these substrate claims on the run's real rows:

| claim | my oracle | verdict |
|---|---|---|
| rejected-hash lookup (item 1) | 13 run attempts `known-bad` over 4 works; each served sha matches an UNCLEARED `quarantine_payloads` row recorded BEFORE the attempt, and none holds a `files` row. My reland SQL finds 0 (`ok` or quarantined rows whose sha matched earlier refused bytes) | CORRECT 13/13 |
| no host suppression on a single 403 (guard 29) | 18 MDPI works answered 403 (68 rows, 10:01–11:18 PDT), and MDPI was still asked for later works (2 `ok`, 1 `measured`). 0 skips cite a 403. All 20 `skipped/backoff_window` rows are the D41/D45 host cool-down (archive.org 429); 0 are per-(route, work) ladder skips | CORRECT |
| dead-ness as a per-attempt `retriable` (guard 15) | every non-skip run row carries non-NULL `retriable`: api-error 84 true / 2 false; blocked, bad-file, no-oa-copy and ok all false | CORRECT |
| the refusal ladder inside the run (O1) | 2343 run spends considered, 0 inside an open window under either variant. Exposure: 17 spends met an earlier refusal on the same (route, work): 16 from history 53 h–10 d earlier, 1 in-run 8.7 h earlier (a 15-min window). Outcomes: 12 blocked, 3 bad-file, 1 api-error, 1 `ok` (work 01a0a070-2a1b… recovered on open_access ~10 d after its refusal) | CORRECT, but vacuous for the windows: no ask fell inside one |
| the persisted ladder (`route_backoff`, 369 rows, all `refusals=1`) vs the plan's ladder | 358 agree; **10 disagree**: persisted 1 refusal / 15 min, while my ladder AND the builder's own reference replay (`BackoffPolicy().replay`, the one the gated counter uses) give 2 / 6 h. On each of the 10, the earlier refusal was 2026-09-21 ~20:1x PDT, before 0033 existed, so the enforcement never saw it. 1 more (E13) depends on how "over a 7-day window" is read | **WRONG ×10 (persisted state; no run outcome affected)** (N1) |

Rows scored: 17 named (16 CORRECT, 1 CORRECT with the named D23 binder gap, 0 WRONG, 0 UNDETERMINED). Supplementary:
- 13 known-bad rows, CORRECT;
- 369 persisted ladder rows: 358 agree, 10 WRONG, 1 reading-dependent (UNDETERMINED pending a ruling).

## 3. The arXiv-client question (plan: "whether litkb's own client is the defect is UNDETERMINED") — MEASURED

- **What litkb sends.** I measured this on the wire at a loopback server, using the real `registry.arxiv_record` with its
  URL template pointed at 127.0.0.1:
  - `GET /api/query?id_list=1906.02530`, sent over `http://` (the constant `ARXIV_ID_LIST`);
  - `User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0` (`netutil.UA`: a browser-imitating string,
    truncated, with no AppleWebKit/Safari tokens and no tool identity);
  - `Accept: application/atom+xml`, `Accept-Encoding: identity`, `Connection: close`.

  The cassette key of all 8 run entries records the same Accept.
- **What arXiv answered in the run.** 8 of 8 `export.arxiv.org/api/query?id_list=…` answered `406`:
  - The body was empty. There was no Content-Type and no Retry-After, only `Via: 1.1 varnish, 1.1 varnish` and Fastly
    `X-Served-By`. The answer names no reason.
  - These were the run's only export.arxiv.org requests, so the first `406` had no earlier request of ours to answer
    for.
  - In the same run, `arxiv.org` accepted this very client: `/pdf` ×56 at 200/206 and `/abs` ×5 at 200.
- **What arXiv accepted before.** The same Accept (unchanged since `5189749`, 2026-09-14, by `git log -S`) and the same
  UA (likewise):
  - 150 `export.arxiv.org` search_query answers at 200, in the registry disk cache, written 2026-09-15.
  - 5 id_list admissions `verified_by arxiv` on 2026-09-15 18:07.
  - `Sapkota_2024` `verified_by arxiv` on 2026-09-20 15:52, 4 min 17 s after two `406`s (admissions 01a0c101…, 01a0c102…).
  - Since 09-21 the answer has been `406` every time: 24 of 24 in the ruled run, 8 of 8 here. Builder C2a's
    2026-09-23 recording also has `export.arxiv.org/pdf/1910.12077` → `406`, with both a PDF Accept and a full browser
    Accept.
- **Cause.** The `Accept` header is NOT the cause. The identical Accept was answered 200 on 09-15 and 09-20 and 406
  from 09-20 on, and a browser Accept was refused too, so the survey's B10 reading ("406s without a browser-ish Accept")
  does not explain these rows. The refusal is **host-level, on export.arxiv.org, for this client, and it started around
  2026-09-20**: arxiv.org serves the same client, and export.arxiv.org refuses both /api and /pdf.

  Whether the trigger is the browser-imitating UA or this machine's address is UNDETERMINED from recordings. It needs
  one named live A/B (the same id_list URL (a) as sent, (b) with an identifying UA such as `litkb/<ver>
  (mailto:…)`, (c) over https), which is outside my grant.
- **Consequence.** `admit/registry.py::TRANSIENT_STATUSES` books `406` as transient on the strength of the single
  09-20 recovery. The evidence since then is 32 of 32 refusals since 2026-09-21: the ruled run's 24 and this run's 8. See N2.

## 4. (c) re-fires — verbatim (`hardening --fire <name> --db litkb_test_w3`, from the checkout, PYTHONPATH=pipeline)

The `EXIT=`/`SECONDS=` line after each fire is my own addition.

```
fire=backoff_window_zero (litkb_hardening_c1a) arm=control rehunt_route_spends=0 (bound =0)
fire=backoff_window_zero (litkb_hardening_c1a) arm=known_bad rehunt_route_spends=2 (bound =0)
fire=backoff_window_zero FIRED
EXIT=0 SECONDS=6
fire=known_bad_lookup_disabled (litkb_hardening_c1a) arm=control known_bad_relands=0 (bound =0)
fire=known_bad_lookup_disabled (litkb_hardening_c1a) arm=known_bad known_bad_relands=1 (bound =0)
fire=known_bad_lookup_disabled FIRED
EXIT=0 SECONDS=6
fire=relation_probe_emptied (litkb_hardening_b1) arm=control relation_probe_rows=2 (bound >=1)
fire=relation_probe_emptied (litkb_hardening_b1) arm=known_bad relation_probe_rows=0 (bound >=1)
fire=relation_probe_emptied FIRED
EXIT=0 SECONDS=5
fire=relation_probe_unanswered (litkb_hardening_b1) arm=control relation_probe_rows=2 (bound >=1)
fire=relation_probe_unanswered (litkb_hardening_b1) arm=known_bad relation_probe_rows=0 (bound >=1)
fire=relation_probe_unanswered FIRED
EXIT=0 SECONDS=5
fire=key_rule_reverted (litkb_hardening_b1) arm=control key_derivation_crashes=0 (bound =0)
fire=key_rule_reverted (litkb_hardening_b1) arm=known_bad key_derivation_crashes=1 (bound =0)
fire=key_rule_reverted FIRED
EXIT=0 SECONDS=7
fire=key_guard_deleted (litkb_hardening_b1) arm=control key_derivation_crashes=0 (bound =0)
fire=key_guard_deleted (litkb_hardening_b1) arm=known_bad key_derivation_crashes=1 (bound =0)
fire=key_guard_deleted FIRED
EXIT=0 SECONDS=7
fire=null_asserted_by (litkb_hardening_b1) arm=control identifiers_without_provenance=0 (bound =0)
fire=null_asserted_by (litkb_hardening_b1) arm=known_bad identifiers_without_provenance=1 (bound =0)
fire=null_asserted_by FIRED
EXIT=0 SECONDS=5
fire=constructed_second_work_claims_doi (litkb_hardening_b1) arm=control conflicts_uncounted=0 (bound =0)
fire=constructed_second_work_claims_doi (litkb_hardening_b1) arm=known_bad conflicts_uncounted=1 (bound =0)
fire=constructed_second_work_claims_doi FIRED
EXIT=0 SECONDS=5
fire=conflict_detection_removed (litkb_hardening_b1) arm=control conflicts_uncounted=0 (bound =0)
fire=conflict_detection_removed (litkb_hardening_b1) arm=known_bad conflicts_uncounted=1 (bound =0)
fire=conflict_detection_removed FIRED
EXIT=0 SECONDS=4
fire=isbn_in_distinct_set (litkb_hardening_b1) arm=control nondistinct_schemes_in_unique_index=0 (bound =0)
fire=isbn_in_distinct_set (litkb_hardening_b1) arm=known_bad nondistinct_schemes_in_unique_index=1 (bound =0)
fire=isbn_in_distinct_set FIRED
EXIT=0 SECONDS=4
fire=e21_pair_two_works_one_edge (litkb_hardening_b1) arm=control e21_pair_unlinked=0 (bound =0)
fire=e21_pair_two_works_one_edge (litkb_hardening_b1) arm=known_bad e21_pair_unlinked=2 (bound =0)
fire=e21_pair_two_works_one_edge FIRED
EXIT=0 SECONDS=4
fire=e06_still_duplicate_review (litkb_hardening_b1) arm=control e06_not_duplicate_review=0 (bound =0)
fire=e06_still_duplicate_review (litkb_hardening_b1) arm=known_bad e06_not_duplicate_review=1 (bound =0)
fire=e06_still_duplicate_review FIRED
EXIT=0 SECONDS=5
fire=refuse_verb_removed (litkb_hardening_b2) arm=control proposals_unadjudicated=0 (bound ==0)
fire=refuse_verb_removed (litkb_hardening_b2) arm=known_bad proposals_unadjudicated=1 (bound ==0)
fire=refuse_verb_removed FIRED
EXIT=0 SECONDS=6
fire=operator_bind_as_version_of_record (litkb_hardening_b2) arm=control operator_binds_unproposed=0 (bound ==0)
fire=operator_bind_as_version_of_record (litkb_hardening_b2) arm=known_bad operator_binds_unproposed=1 (bound ==0)
fire=operator_bind_as_version_of_record FIRED
EXIT=0 SECONDS=5
fire=promotion_prepared_by_the_run (litkb_hardening_b2) arm=control promotions_prepared=1 (bound >=1)
fire=promotion_prepared_by_the_run (litkb_hardening_b2) arm=known_bad promotions_prepared=0 (bound >=1)
fire=promotion_prepared_by_the_run FIRED
EXIT=0 SECONDS=5
fire=self_refusal (litkb_hardening_b2) arm=control self_adjudications=0 (bound ==0)
fire=self_refusal (litkb_hardening_b2) arm=known_bad self_adjudications=1 (bound ==0)
fire=self_refusal FIRED
EXIT=0 SECONDS=6
fire=decision_log_rewrite (litkb_hardening_b2) arm=control decision_log_unguarded=0 (bound ==0)
fire=decision_log_rewrite (litkb_hardening_b2) arm=known_bad decision_log_unguarded=2 (bound ==0)
fire=decision_log_rewrite FIRED
EXIT=0 SECONDS=5
```
**17/17 FIRED, 0 DID-NOT-FIRE.**

## 5. My own mutation (not among the builders' mutation rows)

- **M1** (`Store.to_quarantine` copies instead of moving) **ERRORED**: `shutil.copyfile` wrote into a `_quarantine/`
  that did not exist yet, and 10 tests crashed with `FileNotFoundError`. By the brief's rule that is
  **DID-NOT-FIRE**, so I restructured it as M1b.
- **M1b**, exactly one occurrence in `pipeline/litkb/acquire/store.py` `Store.to_quarantine`:
  `out = self.move_new(pdf, dst)` → `out = self.move_new(pdf, dst); __import__('shutil').copyfile(out, pdf)`. The move
  happens, then the same bytes go back to the original path: refused bytes stay in `_litkb_staging/filed/`. Every
  sidecar, row and reason is still written.
- One pytest process on w3 (`qc/test_litkb_adjudicate.py qc/test_litkb_quarantine.py qc/test_litkb_landing.py`):
  - **control: 198 passed** (63.5 s).
  - **M1b: 3 failed, 195 passed** (57.2 s), each an AssertionError that a filed PDF remained:
    - `test_a_refused_duplicate_landing_that_does_not_bind_is_quarantined_with_a_row`
    - `test_a_landing_whose_bytes_are_held_is_quarantined_duplicate_held`
    - `test_a_hunted_pdf_the_bind_probe_refuses_is_quarantined_with_a_row`

  **FIRED**: it answered worse.
- On the REAL row, my O4 under M1b counted **2 copies** of 187's bytes on disk (filed/ + _quarantine/), against 1 in
  control. The builders' real-row test `test_187s_real_filed_pdf_is_never_left_unowned` **still PASSED**, and the
  by-sha unowned count read `[]` in both arms (N4).
- Restore: `store.py` sha256 `37551013fc970edee2460c844dd768a75f96e31825d30f4ae1e343c9edc78823` before and after →
  **MATCH**. `git status` of the checkout is empty.

## 6. Rulings on the survey's design claims for this class that the real rows can decide

- **The refusal ladder's constants** (15 min → 6 h → 48 h over 7 days, pypaperretriever W25; UNCALIBRATED): the run
  cannot calibrate them. No ask fell inside a window; 16 re-asks 53 h–10 d after a refusal were refused again in 15
  cases, and 1 recovered at about 10 d. That supports "refusals persist for days", but n=16 with one recovery measures
  no recovery time. **UNDETERMINED**, and still uncalibrated.
- **Guard 29, no host suppression on a single 403**: decided by the real rows, **CONFIRMED** (18 MDPI works).
- **Guard 15, per-attempt `retriable`**: **CONFIRMED** on every run row.
- **Guard 2, "PERSISTED atomically"**: **PARTLY CONTRADICTED** on the real rows. The persisted ladder holds only
  post-0033 refusals; see N1.
- **Registry identity**:
  - key-LENGTH rule: **CONFIRMED** on the real creator;
  - identifier-first / type-scoped uniqueness (the pinned distinct list = the registry = the unique index predicate,
    18 schemes): **CONFIRMED**;
  - fatcat conflict rule: **CONFIRMED** on the CONSTRUCTED claim. Live it is vacuous: 0 cross-work claims.
- **Relation probe first**: **CONFIRMED**. 458 answered rows; the probe keeps version/preprint relations and drops
  citation ones.
- **Refuse verb + append-only decision log (LOOP §1.8)**: **CONFIRMED** on 194 and on w3, owner included.
- **The refused-duplicate landing through check 3**: **CONFIRMED** as a landing. The check-3 verdict on 187 is D23's
  named gap.
- **Different-model-family coverage.** survey-design item 1(f) records "Codex. None" for the identity model (crawler
  S5/S6, Opus) and the refuse verb (LOOP L9, Opus). Codex's 2026-09-23 read covered the DESIGN cards, with findings X2,
  X4 and X8 on this class's counters, but not the built code. My oracle is the same model family as the builders.

  The conclusions that therefore rest on Opus-only reads: the conflict rule's semantics, the scheme distinctness of the
  non-pinned schemes (pii, core, dblp, hal, jstor, legacy_stem, ocaid, tracker, url, wikidata: the builder's choice),
  the refuse/decision-log design, and my arXiv cause analysis.

## 7. Notes (the orchestrator decides; none changes a run outcome)

1. **N1, fix before the next ladder run.** `litkb.route_backoff` was never seeded from the pre-0033 ledger.
   `run._skip_reason` reads only the persisted row (`backoff.load`), while the gated `rehunt_route_spends` replays
   every earlier attempt. On the 10 open_access pairs of §2, the enforcement stored a 15-min window where the gate's own
   reference gives 6 h (windows end ~15:53–16:03 PDT 2026-09-24). A re-hunt of any of these works inside that window
   would be ALLOWED by the enforcement and COUNTED by the gate. The same split recurs for every pair whose earlier
   refusals predate the table. A fix: backfill `route_backoff` from the ledger through the reference replay (a one-time
   live write), or have `_skip_reason` replay the ledger when no row exists. Also needed: a ruling on "over a 7-day
   window" (a trailing count vs a window anchored at the chain's first refusal; E13 is the pair on which they differ).
2. **N2, before L010–L017 are hunted again.** The 406 is a standing, host-level refusal (§3). Either fix the client
   (the named live A/B above: identifying UA, https) or book export.arxiv.org's 406 as a refusal of this client rather
   than `registry-transient`. A retry loop will not help.
3. **N3.** Admission-time arXiv pacing does not hold across rows. `front.admit_registry` builds a fresh `Pacer` per
   call, so the 8 requests went 0.41–0.62 s apart (recorded_at 08:45:39.22 → 42.81), against the 3 s
   `ARXIV_MIN_INTERVAL` and arXiv's one-request-per-3-s API terms. It did not cause the first 406 (nothing of ours
   preceded it), but it is impolite, and pacing only across hosts will not catch it.
4. **N4.** `unowned_landings` (and `_assert_owned`) count by sha, so a leftover second copy of refused bytes is
   invisible to both. The 187 real-row test would not notice M1b; only the constructed-bytes tests do. Suggested: have
   the real-row test assert the exact on-disk copy count.
5. **N5, for stage-b / S4.6.** In E21's take, the openaire rung asked the SIBLING article's Wiley `pdfdirect` URL for
   the PREPRINT work, because OpenAIRE merges versions. It answered 403, so nothing landed. Had it answered 200, check 3
   would have compared near-identical titles. The sibling-edition ruling ("two works") has no file-level guard.
   UNDETERMINED.
6. **N6.** On my own read, 187's filed PDF carries its exact title and its DOI on page 1, so the binder's refusal is a
   false negative (D23). DOI-on-page is identity evidence check 3 does not use; that is for a later session.
7. **N7.** The key rule derives `LPVSWGCV_2025_land-cover-change-map`, while live holds the hand-given
   `LPVSubgroup_2025_…`. Both are valid; only a fresh admission would use the derived form.
8. **N8.** The second-session CHECK compares `norm_label`, which strips only invisible characters. A case/space
   variant of the proposer's label is accepted. Labels are self-asserted, so the rule guards against accidents, not
   against intent. Noted, not a defect.
9. **N9.** The read-only grade from my checkout (exit 1, as expected mid-landing) reads, for this class:
   - `rehunt_route_spends=0`, `relation_probe_rows=458`, `key_derivation_crashes=0`, `known_bad_relands=0`;
   - `proposals_unadjudicated=0`, `operator_binds_unproposed=0`, `identifiers_without_provenance=0`;
   - `conflicts_uncounted=0`, `nondistinct_schemes_in_unique_index=0`;
   - **`promotions_prepared=0`**: the landing prepare is the orchestrator's run-plan step 6, still to do;
   - reported: `transient_rows_unretried=44`, `relation_edges_missing=7`, `unowned_landings=3`, `hits_without_version=30`.

   Each gated value above agrees with my oracle where I built one.
10. **N10.** A quarantined PDF's extracted `.txt` travels into `_quarantine/` beside it and shares its sidecar stem. A
    payload walk that pairs by stem sees 2 payloads for 1 row. This is cosmetic.

## 8. What I did not do

- No live write, no network, no commit, no full suite. I ran the fires, one pytest set (control and mutated), and my
  own scripts only.
- I did not build or test item 5b or the membership table (Scope ruling).
- I did not re-run E06 on current code with its own page: E06's current-code evidence is its fire plus my 187 URL run
  through the same check 2.
- The CONSTRUCTED self-approved chain is covered by the builders' fires and my decision-row SQL, not by a chain I
  built.

# litkb S3 — every hunt ends in a named, adjudicated state (2026-09-21)

Session S3 of `Scripts/LITKB_WORKPLAN.md`. Launched headless by S2 at 22:42 on 2026-09-20; moved
by Kam into an interactive terminal at 00:07 (the headless process was stopped at an idle instant
and resumed with its transcript). Fable orchestrating; four Opus builders in their own worktrees,
two Opus auditors, one second headless session. Every number below is read from a tracked file or
a tool's own output, run alone with its own exit code (`gate | tail; $?` bit S2 twice; it bit this
session once, §5.6, and was caught the same minute).

## 1. The grade

Manifest frozen BEFORE the run from the database's clock — `_derived/edges/edges-1-manifest.json`,
`frozen_at 2026-09-21T10:23:01Z`, head `568988b`, repo tip 28 / db tip 28, register sha256
`69b26a3d…59b03`, 26 rows: execute 14 · replay-only 5 · held_for_ruling 6 · not-a-hunt 1.

```
py -3.12 qc/instruments/litkb_acceptance.py edges --manifest _derived/edges/edges-1-manifest.json
executed=14 skipped=0 state_or_reason_mismatches=0 tracebacks=0 held_for_ruling=6 waits_on_migration=0   exit 0

LITKB_TEST_DB=litkb_test_w10 py -3.12 qc/instruments/litkb_acceptance.py edges --manifest … --replay
executed=19 skipped=0 state_or_reason_mismatches=0 tracebacks=0 held_for_ruling=6 waits_on_migration=0   exit 0

grep -c 'browser last' .claude/skills/literature/SKILL.md   → 0
```

Ledgers: `Reports/LITKB_EDGE_RUN_2026-09-21.csv` (live, 14 rows) and
`Reports/LITKB_EDGE_RUN_2026-09-21_replay.csv` (19 rows). The 14 live rows ended, in named states:
`extracted/already-extracted` ×3 · `bound-unextracted/already-bound` ×1 · `held/no-spend` ×1 ·
`refused/admission-refused` ×4 · `refused/malformed-ref` ×1 · `refused/unsupported-ref-scheme` ×1 ·
`blocked/403` ×3. Zero tracebacks; the slowest row (E13, three routes retried against hosts that
answer 403) took 505 s.

The (c) known-bads, run LIVE against the frozen manifest: the register edited after the freeze
(E11's expectation swapped for the VALID `extracted/already-extracted`) → refused on sha256 before
anything is graded, exit 1; re-frozen with that edit → `state_or_reason_mismatches=1`, exit 1
(membership alone cannot pass). A route monkey-patched to raise → `api-error/route-raised` with an
`acquisition_attempts` row `status=api-error` (`qc/test_litkb_hunt.py`, row HV1). A planted orphan
younger than 72 h is NOT reaped; an older one is quarantined with a `.reason.json`
(`qc/test_litkb_reaper.py`, rows S3R1–S3R4). Register restored by sha256 after every mutation.

## 2. Every id

| what | id |
|---|---|
| workstream `edges-1` | `01a0c289-fda3-77c3-aa94-b71103e7874b` (main tree, opened 2026-09-20 22:5x, token vaulted at landing) |
| phase 1 → main | `7b806c7` = `fd40a74` + A1 `9a37093` (`work/20260921-litkb-s3-a1`) + A2 `c472c92` (`…-a2`) + audit fixes `16025cf` (`…-p1`) |
| phase 2 → main | `568988b` = `7b806c7` + reaper fix `7a4e7e7` (`…-reaper-fix`) + B `6799021` (`…-b`) + C `b573319` (`…-c`) + `3f5b1ab` + audit fixes `792aaf3` (`…-p2`) |
| live edge run | manifest above; first manifest `_derived/edges/edges-1-manifest-FIRST-10-09.json` (`10:09:12Z`, sha `1fca1832…`, graded `mismatches=3`, §5.1) |
| admissions the run wrote in `edges-1` | `01a0c371-243d…` (E05, manual, refused duplicate-review) · `01a0c371-e3b3…` (E04, manual, refused) · `01a0c371-e7b6…` (E06, refused duplicate-review) · `01a0c372-197c…` (E11, registry, refused) · `01a0c37d-bd8d…` (E06 redo) — **no proposal** |
| Sci-Hub attempts (E03, E07, E13) | `status=blocked`, detail `sci-hub.ru:200=blocked, sci-hub.ren:200=blocked, sci-hub.box:403=blocked, sci-hub.wf:200=no-pdf-link` — the four mirrors from `LITKB_SCIHUB_MIRRORS`/`pipeline/litkb/config.py`, live |
| reaper | dry run `f856325a` (28 orphans, one wrong — §5.4), dry run `2851b4cc` (27), apply `fb2a1e0f`: `scanned=96 owned=67 young=2 orphans=27 quarantined=27 skipped_errors=0`, census `Reports/LITKB_REAPER_2026-09-21.json` (JSON, untracked under `/Reports/*`; the counters are in this line) |
| second session | workstream `approve-1`, log `Reports/LITKB_APPROVE_SESSION_2026-09-21.md` (§4) |
| worker DBs | A1 w7 · A2 w8 · B w9 · C w10 · auditors w3 · harness w1/w2 |
| reports | `jobs/litkb-s3/` survey-code, survey-data, brief-A1/A2/B/C, builder-A1/A2/B/C, auditor-p1, auditor-p2, STATE.md |

## 3. What landed (the S3 Work bullets, each with where it lives)

- **The vocabulary.** `pipeline/litkb/hunt.py`: `STATES = extracted · bound-unextracted · held ·
  refused · api-error · blocked · crashed`, `REASONS` per state, `STAGES` (eight); every result
  carries `state` + `reason`; `absent` left the tuple (it is `litkb_work`'s miss rung and a hunt
  never returns it). ONE table in `docs/SCHEMAS.md` (`## litkb.hunt terminal states`), with the
  precedence rule for an acquisition that ends with no file. `CLOSED_STATES` in the acceptance
  instrument is derived from hunt's tuples and pinned by a test; the AST scan pins every literal.
  Three things that used to end in something unnamed now end named and RETRYABLE: a raising route
  → `api-error/route-raised` with an attempt row (HV1); a registry 406/429/5xx/timeout →
  `api-error/registry-transient` with NO admission row (HV3a/b/c — S1's arXiv 406, recorded then
  as terminal `admission-refused`, is register row E14); the generic boundary →
  `crashed/<stage>:<Exception>` (HV4/HV4b). URL fetch 5xx → `api-error/fetch-transient`, 403 →
  `blocked/403` (HV5).
- **Not a state: `proposed`.** A1's deviation, accepted: the web-source gate (2026-09-20) makes a
  proposal's blocks searchable from its own workstream, so `state` must keep saying whether blocks
  exist; the proposal fact is `in_main: false` + the admission's state, which the edge ledger's
  `report` column carries.
- **The register.** `qc/fixtures/litkb_hunt_edge_cases.json`, 26 rows, every one a REAL row from
  `jobs/litkb-s3/survey-data.md` with its source; each executable row adjudicated from code + the
  attempts history by the builder, then independently by the auditor (agree 15 / disagree 4, the 4
  fixed — §5.2). Six rows are `held_for_ruling` with Kam's question and the evidence, no expected
  state (E20 book · E21 sibling edition · E22 Chrisman_1982 · E23 fifteen `skipped-low` ·
  E24 twenty-two `refused-check1` · E25 the two quarantined arXiv PDFs). E26 records S2's
  `search_unpaywall` emptiness as `scout-api-error`, `not-a-hunt`, with the rule "empty is not
  non-OA".
- **The gaps closed.** HTML-only through `hunt` to searchable blocks (`extract/text_snapshot.py`,
  route in hunt's URL branch, extractor `text-snapshot`; B's fixture is the captured Crossref
  page; a body with no declared type still quarantines — the sign-in page). Staging reaper
  (`ops/reaper.py`, `litkb reap`, dry-run default; ownership by sha256, by `file_versions.rel_path`,
  and by the paths an admission's checks name — the third leg added after the first live dry run
  called the FPGA proposal's snapshot an orphan). Sci-Hub mirrors from `pipeline/litkb/config.py`
  (`LITKB_SCIHUB_MIRRORS`, default the four in Kam's note; empty → default, never an empty loop).
  SKILL.md line 261: "manual `--from-file` last". `litkb_work`'s `absent` split three ways
  (`absent_kind` ∈ never-admitted · in-this-workstream · in-another-workstream, with `holder_state`;
  the third bucket reads exactly the rows admission's check 2 refuses on — the phase-1 audit found
  it filtering on `w.state='open'`, which would have invited an admission check 2 then refuses).
  `litkb_acquire` returns `detail` and `attempts_detail`; `acquire()` returns `route_detail`.
- **The instrument.** `litkb_acceptance.py edges --freeze / --manifest [--replay]`,
  `qc/instruments/litkb_edge_run.py` (live driver, resume rule, `--redo`; deterministic replay on a
  worker DB with the network replaced at the hunt suite's own seams; refuses `LITKB_TEST_DB=litkb`).
  Mutation rows on the shared ledger: HV1–HV6, S3A1–S3A4 + S3A2b, S3R1–S3R4, HW1–HW4, S3E1–S3E6 —
  each shown to FIRE and restored by sha256 by its builder and again by an auditor.

## 4. The second session

A SECOND headless session (`claude -p`, Opus, 47 turns, its own checkout
`D:\edmonds-pipeline\wt-s3-approve` at `568988b`, its own MCP config with `LITKB_SESSION=s3-approve-1`,
log `_derived/s3/approve/approve-1.jsonl`) opened its own workstream `approve-1`
(`01a0c380-0a7f-7827-9d62-fb49479cca0d`), read each proposal's `admissions.checks` and the
document behind it (`pdftotext` on the first pages), and ran `litkb approve` for each:

| admission | work | decision | DB |
|---|---|---|---|
| `01a0a7c4-9f49-7c81-a1b8-f482f479858c` | `Riva_2017_ifla-library-reference-model` (URL-PDF, ws `linkage-review`) | APPROVED | `approved` by `claude`/`s3-approve-1` 03:28:28, versions moved to `promoted` |
| `01a0ad55-ebc2-79c1-892b-6485eb34c776` | `Abdulkader_2020_cnn-fpga-implementation-hardware` (web, ws `hunt-test-1`) | APPROVED | `approved` 03:28:32, moved to `promoted` |

Both works now read out of `litkb.main_works` — for a manual admission, approval IS the promotion.
The database's second-session guard (`admissions_second_session_signs_off`) accepted a session
label different from the admitter's; the log (`Reports/LITKB_APPROVE_SESSION_2026-09-21.md`)
records the evidence read, the CLI's `moved` lists verbatim, two metadata-quality notes (a dropped
surname particle; empty `given` names) that do not touch identity, and what it did not do (the
thirteen tracker-era proposals; no refusals were needed). Its token is vaulted with `edges-1`'s.

## 5. Bounded outcomes, said plainly

1. **The session did not survive its own launch shape.** Launched headless-to-a-log, it was stopped
   and resumed interactively by Kam at 00:07; background builder A1 died mid-gate with fourteen
   uncommitted files and was resumed from its transcript against the on-disk state (nothing was
   lost; `9a37093`). S4 launches in a NEW terminal window (`_derived/s4/launch-s4.sh`, `wt.exe`).
2. **The register's first live grade was `mismatches=3`** (manifest `10:09:12Z`). E03 and E07
   expected `held/not-acquired` and got `blocked/403`: every Sci-Hub mirror answered blocked or
   403 to this client on the day, and the precedence rule is right to name `blocked` over `held`.
   Those expectations were predictions about a remote host — flagged as such by the phase-2 auditor
   before the run — and the register now records the measured pair with the date, keeps the
   unobtainable class in the replay (`replay.expected`), and says so in the row. E06 expected
   `extracted/fresh` and got `refused/admission-refused (duplicate-review)`: `Tkaczyk_2024` is
   already a HELD work in main (0 files) and `_title_duplicates` is global, so the page is check 2's
   duplicate. Knowable before the run; builder C and the auditor both adjudicated it on a freshly
   migrated replay database. The re-adjudicated register was re-frozen (`10:23:01Z`), the three
   rows re-hunted (`--redo`; all three reproduced), and graded `mismatches=0`. Both manifests and
   both grades are kept. **Consequence:** the HTML-only → searchable-blocks path is proven in the
   replay and by B's tests, NOT live — every HTML-only real row in hand belongs to a work the base
   already holds. A live HTML hunt of an unknown work is S5's carry-in.
3. **The live run created no proposals**, so "a second session reviews the proposals the run
   created" had an empty set. The second session reviewed the two real URL-source proposals the
   web-source gate has held since 2026-09-16/17 instead (§4); the thirteen tracker-era manual
   proposals wait on Kam (survey question 8).
4. **The first live reaper dry run was wrong once**: it called the FPGA proposal's web snapshot an
   orphan (no `files` row, no `file_versions.rel_path` — the path lives only in
   `admissions.checks`). Nothing was moved; the third ownership leg was built, tested (S3R4 fires),
   merged, and the apply quarantined 27: eleven `incoming/` downloads from 2026-09-15 (the four
   HTML-only `.download`s among them) and sixteen ~1.6 KB stub PDFs in `filed/` — test seeds that
   had leaked into the real root. Two snapshots the live run's refused page hunts left in `web/`
   are `young` today and orphans in 72 h (auditor-p2 §5.6: a refused page writes its snapshot before
   the field check, with no row).
5. **Two merge candidates were refused by their auditors and fixed before merging.** Phase 1
   (auditor-p1, MERGE WITH FIXES): the `absent` third bucket filtered on the holder's `open` state
   while check 2 does not. Phase 2 (auditor-p2, DO NOT MERGE): C's replay test admitted E06's plain
   title into the session-shared worker DB and `_title_duplicates` is global, so B's suffixed page
   hunts went `duplicate-review` whenever `edges` ran before `hunt` (4 red in `pytest qc`, 85 passed
   reversed); the register's live rows lacked the `live.inputs` the live path reads; an E06
   allowance made the one gate for an HTML-route regression unable to fire. All fixed; the strict
   gate fires (HTML route block removed → E06 red).
6. **A pipe hid a grade's exit code once more.** `edges … | tail -8; echo $?` printed 0 over
   `mismatches=3`; re-run alone it was 1. Same minute, same lesson as S2 §6.
7. **`py -3.12 -m litkb` from a worktree runs MAIN's editable install.** The reaper fix's own dry run
   reported 28 until run with `PYTHONPATH=pipeline`. The launch recipe already says this; it bit
   anyway.
8. **E13 spends 505 s** retrying three routes against hosts that answer 403 — `blocked` is in no
   route's `DEAD_STATUSES`, so nothing is ever dead-skipped for a blocked work. A per-status
   back-off for `blocked` is an S5 carry-in, not an S3 change.

## 6. Not done / on other tracks

- Kam's rulings on E20–E25 (six questions, each in the register with evidence).
- `binding.TITLE_REGION_LINES = 45` is a PDF-first-page rule and a ceiling on web pages (B).
- A DB home for hunt outcomes (the edge-run CSV is the S3 home; S5's carry-in).
- Docling produced no artifact on a native Copernicus PDF (S2 §4) — S4 classifies it.
- Promotion of `edges-1`'s rows: none to promote (no use was recorded in S3).

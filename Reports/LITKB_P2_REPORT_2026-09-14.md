# litkb P2 "Admission + acquisition" — build report, 2026-09-14

Design: `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §4.6, §4.7, §10, §14 P2 row. Decisions:
`Scripts/decisions.yaml` `litkb-p0-foundation`. Branch `work/20260913-literature-kb`.

**Status of this evidence (CLAUDE.md 3.4c):** every result below was produced by the author of the code. The
mutation runs show the guards CAN fail; no independent referee has re-run them. The calibration threshold was
chosen by the author, by a rule written into the instrument before its numbers were read, on the tracker's
human-marked pairs — not on referee-authored gold committed beforehand (§14's rule for measured gates).

## What was built

| Item | Where |
|---|---|
| Admission in ONE database transaction: `litkb.admit()` runs checks 1-5 and writes works + identifiers + files + the admission row together, or only a refused admission row. `approve_admission()` (manual route), `attach_file()` (acquisition). Statuses widened; `_ws_chains` re-created with a hold on every work/identifier/file chain | `Scripts/pipeline/litkb/db/migrations/0013_admission.sql` |
| Check 1: Crossref -> DataCite confirmation of a DOI, arXiv API for an arXiv id; the claimed record compared by aa_fetch's `judge_candidate` (title ratio >= 0.85, first-author family, year exact or +/-1) | `litkb/admit/registry.py`, `litkb/admit/resolver.py` (gate 0 resolver Crossref -> Semantic Scholar -> arXiv, ported) |
| Check 3: first-page binding (every 1-3 line window of `pdftotext -f 1 -l 1`, plus the PDF Title metadata; ratio >= 0.85 AND the registry first author on the page) | `litkb/admit/binding.py` |
| Python front of admission and approval | `litkb/admit/front.py` |
| Store: staging, quarantine, create-only writes, disk hash index; no delete path | `litkb/acquire/store.py` |
| Routes: open access (arXiv id or 10.48550 DOI, then every Unpaywall location via the installed `paper_search_mcp`), Anna's Archive (aa_fetch's gates ported), Sci-Hub by DOI (bare GET, .ru then .ren), browser recorded as `manual-step` | `litkb/acquire/open_access.py`, `annas.py`, `scihub.py`, `run.py`; HTTP client/pacer/redaction `litkb/netutil.py` |
| CLI `py -3.12 -m litkb` — `ws open`, `ws status`, `discover`, `admit`, `approve`, `acquire` | `litkb/commands.py`, `litkb/__main__.py` |
| Tests | `Scripts/qc/test_litkb_p2.py` (56 + 2 live), `Scripts/qc/test_litkb_annas.py` (81, 3 of them live: aa_fetch's 80 ported + one destination guard) |
| Fixtures | `Scripts/qc/testdata/litkb_p2/manifest.pre-auditfix.rows.csv` (the two pre-fix rows, copied from the backup), `crossref_kill_dois.json` (Crossref records of the four kill DOIs, captured live 2026-09-14) |
| Mutation harness | `Scripts/qc/instruments/litkb_p2_mutations.py` |
| Calibration instrument and measured CSV | `Scripts/qc/instruments/litkb_title_threshold.py` -> `Reports/litkb_title_threshold_2026-09-14.csv` |
| P1 files touched | `qc/test_litkb_p1.py` (`_EXPECTED_EXECUTE` gains the writer's three new functions; its session fixture now delegates to `conftest.py`), `qc/conftest.py` (shared `litkb_pg_base` session fixture — two modules each holding the suite's advisory lock on their own connection would wait on each other forever — and the `litkb_live` marker, skipped unless `LITKB_LIVE=1`), `qc/instruments/litkb_p1_mutations.py` (row R7 re-pointed at 0013, which replaces `_ws_chains`), `pyproject.toml` (packages `litkb.admit`, `litkb.acquire`) |

## Applied

- `litkb_test`: by the suite's session reset (13 migrations).
- `litkb`: `litkb.migrate: litkb as litkb_owner: applied 1 (0013_admission.sql); 13 recorded`, before the gate.

## Gate — five real DOIs admitted and acquired end to end (live, `litkb`)

Workstream `litkb-p2-gate` (`01a0a06d-6826-7100-b15b-d0210fbea7b2`), opened with `py -3.12 -m litkb ws open`;
token in the worktree's git-ignored `.litkb-workstream`, never printed. Session labels `claude-p2` /
`p2-gate-20260914`. Every paper is a tracker row (IDs 99, 189 and 169 carry `Feeds` into reports; 59 and 61 have none), had no `File stem`, and its DOI was
in no `manifest.csv`; a filename search of `Literture\` found none of them. Admission used
`py -3.12 -m litkb admit --tracker-id N` (the tracker row is the claimed record; its DOI is the identifier);
acquisition `py -3.12 -m litkb acquire --doi D --max-archive-downloads 2`.

| # | Work (tracker ID) | DOI | Check 1 | Routes tried -> outcome | File |
|---|---|---|---|---|---|
| 1 | Pengra 2020 (99) | 10.1016/j.rse.2019.111261 | Crossref, pass | open_access `no-oa-copy` (Unpaywall closed) -> **annas `ok`** (downloads_left 980) | 1,551,132 B, 10 pp, sha256 `28836b04…`, bound ratio 1.0 on page 1 |
| 2 | McRoberts 2018 (189) | 10.1016/j.isprsjprs.2018.06.002 | Crossref, pass | open_access `no-oa-copy` -> **annas `ok`** (979) | 673,947 B, 9 pp, `b70f7483…`, bound 1.0 via PDF title |
| 3 | Ploton 2020 (59) | 10.1038/s41467-020-18321-y | Crossref, pass | open_access `blocked` (nature.com, ncbi, cirad landing pages 200 with no PDF; doaj.org 403 challenge) -> **annas `ok`** (978) | 6,351,920 B, 11 pp, `897445ab…`, bound 1.0 on page 1 |
| 4 | Olofsson 2020 (169) | 10.1016/j.rse.2019.111492 | Crossref, pass | open_access `bad-file` (sciencedirect 403, hdl.handle.net no answer) -> **annas `ok`** (977) | 1,483,171 B, 9 pp, `9e773bab…`, bound 1.0 on page 1 |
| 5 | Mahoney 2023 (61) | 10.48550/arxiv.2303.07334 | DataCite (Crossref 404), pass | **open_access `ok`** (`https://arxiv.org/pdf/2303.07334`) | 1,618,796 B, 18 pp, `b44fc280…`, bound 1.0 via PDF title |

Each file: sha256-checked against every `files` row in `litkb` and against a hash index of every PDF under
`Literture\` (topic folders, staging, quarantine) — no match, so nothing was a re-download; landed in
`_litkb_staging\incoming\` with its `.txt` extract written at once; bound; recorded by `attach_file` (which
re-checks binding and sha256) with `rel_path` `_litkb_staging/filed/<key>.pdf`, `source_route`, `source_url`
(the archive route stores `annas md5:<md5>`, never the fast-download URL), md5, bytes, pages, PDF metadata and
the binding JSON; then moved to `filed\` inside the same transaction. `incoming\` is empty afterwards; no file
was quarantined; nothing under `Validation\` or any other topic folder was written.

**Archive downloads used: 4** (downloads_left 980 -> 979 -> 978 -> 977; cap 20).

**What else ran on `litkb` in the gate workstream (recorded, not hidden):**

- **Refused at check 1 — three of my first five picks, all tracker errors the rule caught:**
  - ID 40 Weinstein 2021, `10.1371/journal.pcbi.1009180`: the tracker title drops "from the National
    Ecological Observation Network"; ratio 0.835 < 0.85.
  - ID 39, `10.3390/rs15030765`: the tracker says "Zhou, Y. et al."; Crossref's first author is Chen.
  - ID 24, `10.1016/j.rse.2021.112308`: the tracker says "Wang, Q. et al."; Crossref's first author is Liu.

  They stay as refused admissions (candidates `rejected`, reasons stored). Replacements were then pre-screened
  read-only with the same comparison. That screen found more tracker disagreements, none admitted:
  - ID 7: title ratio 0.31.
  - ID 25 `10.3390/rs5041397`: Crossref 404.
  - ID 29: DataCite first author Henrich, tracker Haucke.
  - ID 30: title ratio 0.82.
  - ID 38: first author Szczecina, tracker Giannetti.
- **Admitted, not acquired:**
  - ID 11 Velasquez-Camacho 2025, `10.1371/journal.pone.0326562`. open_access `blocked`: Unpaywall gave landing
    pages only, and doaj.org answered 403 with a challenge. annas `not-in-archive`. scihub `bad-file`: the .ru
    landing page had no PDF link, and .ren answered 522. Then browser `manual-step`.
  - ID 100 Stehman 2022, `10.1016/j.rse.2021.112806`. It was added as a live dedupe check, because an earlier
    copy sits in `_quarantine\`. open_access `no-oa-copy`, annas `not-in-archive`, scihub `blocked`, then
    `manual-step`. No route produced bytes, so this run gave no live dedupe hit. Dedupe is shown by the tests
    only.
- Totals: 7 admitted, 3 refused; 16 attempts:
  - annas: ok 4, not-in-archive 2;
  - open_access: ok 1, no-oa-copy 3, blocked 2, bad-file 1;
  - scihub: bad-file 1, blocked 1;
  - browser: manual-step 2.
- Live tests, `LITKB_LIVE=1 … -m litkb_live`: **5 passed**.
  - Crossref still returns the fixture's titles, first authors and years for the four kill DOIs.
  - Unpaywall lists an OA location.
  - Three resolve-only archive smokes: the Efron md5, the bioelechem search fallback, and a not-in-archive DOI.
    None of them downloads anything.

## No-identifier title threshold — calibrated on the tracker's `Duplicate of` pairs

`PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_title_threshold.py`. The metric is the one the
database enforces, computed by the database: `similarity(litkb.norm_title(a), litkb.norm_title(b))` (pg_trgm),
with `|year difference| <= 1`.

- 460 tracker rows, 105,570 pairs, **4 gold pairs**, 12,739 non-duplicate pairs inside the year window.
- Gold: 13/264 1.000, 60/303 1.000 (years 2019/2018), 94/199 1.000, and **3/50 at 0.239** — "DeepForest: A Python
  package…" vs "DeepForest: fine-tuning with ~1000 annotations", a duplicate by DOI only; no title rule can or
  should catch it (it has an identifier, so check 2's identifier path covers it).
- Highest non-duplicate pairs: 107/110 0.683, 175/211 0.614, 107/111 0.609, 177/178 0.589 (LandTrendr I/II),
  110/111 0.574.
- Threshold table (title-level gold caught of 3 / false positives in window): 0.30 3/160, 0.40 3/35,
  0.50 3/13, 0.60 3/3, 0.65 3/1, **0.70 3/0**, … 1.00 3/0.
- Rule fixed before reading: the lowest 0.05-grid threshold with zero false positives that still catches every
  title-level gold pair -> **0.70**, the constant in `litkb._title_dup_threshold()`.
- **Weak:** the three title-level pairs are identical titles (1.000), so recall between 0.70 and 1.00 is
  untested; the threshold is set by the false-positive side alone, and "non-duplicate" assumes the tracker marks
  every duplicate.

## Kills and guards — each shown to fire

`PYTHONUTF8=1 PYTHONPATH=pipeline py -3.12 qc/instruments/litkb_p2_mutations.py` — each mutation runs the WHOLE
`qc/test_litkb_p2.py` + `qc/test_litkb_annas.py` (live tests deselected) against `litkb_test`, restores the
file and compares its sha256.

**§14 P2 kills (tests in `qc/test_litkb_p2.py`):**

| Kill | Test | How it fired |
|---|---|---|
| Averkov 2009 with `10.4171/JEMS/183` and Higham 2011 with `10.1016/j.laa.2010.09.001`, each with its REAL `Validation\` file, refused at binding | `test_kill_prefix_wrong_doi_is_refused_at_binding[averkov, higham]` (DOI trusted alone, so the binding is the only comparison: `refused_at = check3_binding`, ratio < 0.85, no work, no file row, file sha256/size/mtime unchanged); `test_prefix_wrong_doi_with_the_manifest_claim_is_refused[*]` (with the row's title/authors/year: check 1 `fail` and check 3 `binding-failed`); `test_binding_reads_the_real_first_page[*]` (wrong: not bound, first author Lisca / De la Cruz not found; corrected: bound, ratio >= 0.85) | A6 (database binding guard removed), B1 (Python binding always binds) |
| The corrected DOIs admit the same files | `test_kill_corrected_doi_admits_the_same_file_and_its_case_variant_collides[*]`: `admitted`, file row `rel_path = Validation/<stem>.pdf`, sha256 = the manifest's, binding `bound`, the work's title = Crossref's; file untouched | A6, B1 (through the same test file) |
| `10.4171/JEMS/179` after `10.4171/jems/179` collides (and `10.1016/J.LAA.2010.04.007` after its lower case) | same test: second admission `duplicate`, same work id, one work carries the DOI | A9 (identifier lookup removed -> `collided` on the unique index), A22 (`norm_identifier` no longer lower-cases) |
| Two concurrent admissions of one DOI leave one work | `test_kill_concurrent_admissions_of_one_doi_leave_one_work`: two connections, holder's transaction open, waiter observed in `pg_blocking_pids`, holder commits; waiter returns `duplicate` with the holder's work; one work | A8 (advisory lock removed: the waiter blocks on the index instead and returns `collided`), A9 |
| A known `Duplicate of` pair re-entered without identifiers goes to duplicate review | `test_kill_duplicate_pair_without_identifiers_goes_to_duplicate_review`: row 94 held, row 199 manual with no identifier -> `duplicate-review`, candidate `duplicate-review`; control 107/110 (0.683) -> `proposed` | A10 (review block removed), A11 (threshold 1.01) |
| An admitter approving its own manual admission is refused | `test_kill_admitter_cannot_approve_its_own_manual_admission`: same session -> 23514 `admissions_second_session_signs_off`, also with the session padded by spaces from another workstream; nothing moves; another session approves and main sees work, identifier and file | A21 (the session clause of the 0009 constraint dropped), A19 (approval moves no pointer), A13 |

**Every other guard in the harness** (A = database, B = Python), each fired on the whole file set:

- A1: work title/year must be the registry record's.
- A2: claimed ratio and author.
- A3: year rule removed.
- A3b: ±1 widened to ±2.
- A4: no registry-confirmed identifier.
- A5: no-text-layer is binding-pending.
- A7: manual admission needs a bound file.
- A12–A14: the token on admit, approve_admission and attach_file.
- A15: candidate of another workstream.
- A16: attach_file sha256 lookup.
- A17: attach_file binding.
- A18: promote_prepare holds unapproved fact chains.
- A20: the writer's EXECUTE.
- B1b: binding requires the first author. **Did not fire in the first run.** Nothing tested "title on the page
  under another author's name", so `test_binding_needs_the_first_author_as_well_as_the_title` was added; B1b
  then fired: `1 failed, 133 passed`.
- B2: resolver ±2 years.
- B3: store writes outside staging/quarantine.
- B4: store overwrite.
- B5: a move turned into copy + `os.remove`, caught by the no-delete-path scan.
- B6: DB sha256 dedupe.
- B7: disk sha256 dedupe.
- B8: an unbound file offered to the database instead of quarantined.
- B9: dead routes retried.
- B10: quota stop.
- B11: key redaction on the attempt path.
- B12: a known md5 spends a download.
- B13: bytes vs record md5/size.
- B14: gate 1 /search redirect.
- B15: gate 2 record DOI.
- B16: fetch_one into `Validation\`.

**Runs:**

| Run | Baseline | Result | Baseline after | Restores |
|---|---|---|---|---|
| First full run | `133 passed, 5 deselected` | **39/40 fired** (B1b did not) | `133 passed` | 40 `match: True` |
| `sha256sum -c` of 33 files fingerprinted before the run | | | | 32 OK; the 33rd is `test_litkb_p2.py`, edited afterwards for B1b |
| `--only B1b`, after the new test | `134 passed` | fired | `134 passed` | |
| **Final full run on the committed tree** (after the ladder below) | `134 passed, 5 deselected` | **40/40 fired** | `134 passed, 5 deselected` | 40 `match: True`; separately `sha256sum -c` of 34 files fingerprinted before the run: 34 OK |

P1 harness row R7, re-pointed at 0013 (`qc/instruments/litkb_p1_mutations.py --whole-file --only R7`): baseline `149 passed`, **FIRED**, restored baseline `149 passed`. The other P1 harness rows were not re-run: none of them targets text that 0013 supersedes (only R7 did), and the whole P1 file passes at baseline (149).

## Ladder

`cd Scripts && PYTHONUTF8=1 py -3.12 qc/check.py --fast`: secrets PASS, ruff PASS, compile PASS; pytest `1 failed, 2289 passed, 5 skipped, 74 warnings in 453.03s` (`litkb Postgres tests: 182 passed`). The one failure is the allowed `qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]`; the 5 skips are the `litkb_live` tests. The ladder stops at its first failing rung, so preflight was run on its own: `[PASSED] pre-flight clean`.

The first ladder run found two failures I had introduced, both now fixed:
- `test_every_symbol_citation_resolves`: new modules named `core.py` and `cli.py` made existing citations of
  phase4seg's `core.py`/`cli.py` ambiguous. They are renamed `litkb/admit/front.py` and `litkb/commands.py`.
- `test_path_insert_ledger`: the calibration instrument had a path hack; it now runs with `PYTHONPATH=pipeline`.

## Judgement calls

1. **The year rule is the aa_fetch rule, unchanged.** `judge_candidate` refuses on title ratio and first author
   before it looks at the year, so a ±1 acceptance always has both matches. decisions.yaml's "otherwise the year
   must match exactly" therefore has no case left to act on; I did not invent a stricter reading, such as an
   exact title. The database mirrors the rule (`_check_registry`) and refuses ±2.
2. **The registry record is what is admitted.** The work's title, authors and year come from Crossref, DataCite
   or arXiv. The claimed record (a tracker or manifest row, or the CLI flags) is only compared with it, and the
   comparison is stored on the identifier's evidence. **A DOI with no claimed record needs a bound file:** a DOI
   alone proves only that some work exists. This is what makes the Averkov/Higham replay a binding refusal.
3. **Refused admissions persist.** They are written as `admissions.state = refused` with the checks JSON, and
   the candidate is marked `rejected` / `duplicate` / `duplicate-review`. A refused candidate is not retried; a
   new candidate is recorded instead.
4. **The database trusts client-measured ratios.** It re-checks every rule it can see in the evidence (numbers,
   flags, the registry title equal to the work's title), but it cannot re-read a PDF or re-query a registry. Like
   the session labels (§15.13), this stops a mistaken client, not a forged one.
5. **An unverified extra strong identifier refuses the whole registry admission.** Tracker 61 was admitted by
   its DataCite DOI alone, because the arXiv API was answering 429 and its arXiv id could not be verified. The
   open-access route derives the arXiv id from a `10.48550/arXiv.<id>` DOI (the convention's DOI form).
6. **Filing is `_litkb_staging\filed\<stem>.pdf`, not the topic folders.** `manifest.csv` is still the authority
   for `Validation\`, and a file there with no manifest row would read as a stray. P3 moves filed papers with the
   manifest export. Quarantine is the existing `_quarantine\`.
7. **Approval takes the approver's own open workstream and token.** Requiring the admitter's token would force
   the approval into the admitter's worktree. The 0009 constraint on session labels does the sign-off.
8. **Promotion never carries a fact.** `_ws_chains` (0005) is re-created in 0013 with a problem on every
   work/identifier/file chain, so a pending manual admission cannot reach main through `promote_commit`. P1
   harness row R7 now targets 0013's copy.
9. **Title duplicates** are compared against every work version in any workstream, with years ±1, and only for
   admissions carrying no doi/arxiv/isbn/pmid/pmcid/jstor/handle identifier.
10. **Sci-Hub:** a bare GET with no Referer, cookie or solver. A 403 or a challenge page is `blocked`. The memory
    notes that the `.ren` storage host wants a Referer; that is a hotlink protection and was not worked around.
11. **Unpaywall** is called through `UnpaywallResolver._fetch_doi_record`, a non-public method, because the
    public `resolve_best_pdf_url` returns one URL and every OA location was wanted. The email stays in the
    secrets file; litkb never stores it.
12. **The ported Anna's Archive module:**
    - the job mode of its `main()` (filing plus manifest rows) is refused;
    - `fetch_one` refuses any destination under `Literture\` outside `_litkb_staging`;
    - the three live tests are resolve-only;
    - 80 aa_fetch tests kept, plus 1 guard test.
13. **Quota:** the archive route stops once `downloads_left <= 50` (`--quota-margin`), or after 5 archive
    downloads in a run (`--max-archive-downloads`). Both stops are recorded as `quota-stop`.
14. **A route is dead** after `no-oa-copy` for open access; after `not-in-archive`, `record-mismatch` or
    `unresolved` for the archive; and after `not-in-archive` for Sci-Hub. A dead route is skipped for that work
    unless `--retry-dead`. A browser `manual-step` is recorded once per work.
15. **The harness runs the two P2 test files together** under every mutation. The ported archive tests are part
    of what the archive guards must fail.
16. **`discover`** is wired to Crossref only (paper-search's `CrossRefSearcher`). Results go to `candidates` and
    are never admitted.

## Open / blocks for P3

- **Tracker claims disagree with registries often enough to matter for P3's bulk load.**
  - Gate picks: 3 of my first 5 were refused.
  - Read-only pre-screen: 5 of 9 disagreed or 404'd.
  - Every such row will be refused at check 1 on load. P3 needs a correction pass on the tracker (xlsx, Kam's
    file), or must load held files by DOI plus file, where binding does the comparison. Kam's call.
- **Open access is weak outside arXiv.**
  - Unpaywall often lists landing pages, not PDFs (PLOS, Nature).
  - Publisher and DOAJ hosts answer challenges.
  - Europe PMC / PMC PDF rendering is not wired. The archive carried 4 of 5 gate papers.
- No independent referee has re-run the P2 mutations (3.4c).
- The gate workstream `litkb-p2-gate` is still open; its token file sits in this worktree. It holds 2 admitted,
  unacquired works (IDs 11 and 100) with `manual-step` attempts.
- The editable install still points at the main tree: run with `PYTHONPATH=Scripts/pipeline`.
- Untested residual: `approve_admission` does not lock or check the ADMITTER's workstream, so a proposed manual admission left in an abandoned workstream can still be approved from another session. Not in the kill list.

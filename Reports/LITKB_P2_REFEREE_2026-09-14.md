# litkb P2 "Admission + acquisition" — independent referee, 2026-09-14

Scope: `git diff 057c450..b2e10a7` on `work/20260913-literature-kb`. The worktree HEAD was 5136465 when this was
written; its only change after b2e10a7 is `Scripts/decisions.yaml`, so the code reviewed is b2e10a7's. Read:
`Reports/LITKB_P2_REPORT_2026-09-14.md`, design §4.6 / §4.7 / §10 / §14 P2, decisions.yaml `litkb-p0-foundation`,
`Scripts/docs/LITERATURE_CONVENTION.md`, migration 0013, `litkb/admit/*`, `litkb/acquire/*`, `litkb/commands.py`,
`qc/test_litkb_p2.py`, `qc/test_litkb_annas.py`, `qc/instruments/litkb_p2_mutations.py`, and
`D:\tools\annas-mcp\aa_fetch.py` for the port comparison.

What was run, and where:
- My own mutation runner and probe script. Both live in the session scratchpad and are not committed.
- The mutations and probes ran on `litkb_test` only.
- `litkb` was opened as `litkb_reader` with `default_transaction_read_only = on`.
- No archive traffic: `LITKB_LIVE` was never set, and 0 archive downloads were used.
- Nothing under `Literture\` was written. After all probes and mutations, a full-tree scan (staging and quarantine included) found 0 of 529 entries with mtime or ctime after 2026-09-14 08:49:19, which precedes this review.

## Verdict: ACCEPTED WITH FIXES (D1-D5 fixed and re-refereed before P3 loads anything)

What holds:
- Every §14 P2 kill fires; I re-ran them myself.
- The gate is real: the five works, their files and their attempts all verify.
- The ladder matches the report.
- No secrets are in the range.

What does not hold:
- Check 2, "case differences must never create two rows", fails for sibling spellings of a DOI (D1).
- Binding, check 3, is weaker than §4.6 describes (D2).
- Both D1 and D2 sit exactly where P3 now leans. P3 "loads by DOI + verified file" (5136465), with manifest stems as keys, so neither the default key nor a claimed record would mask them.

## Defects

| ID | Severity | What | Evidence | Fix |
|---|---|---|---|---|
| D1 | **High** | **Two DOI normalisers disagree, and the raw spelling is stored.** `front.admit_registry` confirms at Crossref under Python `normalize_doi` (it cuts everything before `10.` and strips a trailing `/`), but it stores `doi.strip()`. SQL `norm_identifier` strips only `https?://(dx.)?doi.org/` and `doi:`. The spellings `https://www.doi.org/`, `doi.org/`, `doi: ` (space after the colon), `urn:doi:` and a trailing `/` pass check 1 and miss check 2's lookup, advisory lock and unique index. | Probe on `litkb_test`, one synthetic DOI, each spelling admitted under its own key: **6 works carry one DOI**. Stored `value_norm`s: `' 10.5555/…'`, `'…/'`, `'doi.org/…'`, `'https://www.doi.org/…'`, `'urn:doi:…'`. Under the default key the second admission is only `collided` on `works_key_key` (an accident of `make_key`), and its candidate is marked `rejected`, not `duplicate`. Race, bare vs trailing `/`: waiter **not blocked**, 2 works. Spellings that do work: case, `https://doi.org/`, `http://dx.doi.org/`, `DOI:`, surrounding spaces, and the Laurance 1998 SICI DOI (lower, UPPER, https+UPPER all return `duplicate`). A percent-encoded SICI is refused at check 1, because neither side unquotes. Mutation R4 (the SQL prefix strip removed) **survives the whole P2 file**; only P1's suite, `test_litkb_p1.py:459`, covers `https://doi.org/`. | Store the normalised DOI, never the raw spelling. Make `norm_identifier` agree with `normalize_doi`: cut to the first `10.`, trim a trailing `/`, and ideally percent-decode. Add a P2 test per spelling, plus a race test on a sibling spelling pair. |
| D2 | **High** | **Binding binds pages that are not the paper.** The author test is a substring of the squashed page for family names of 4+ letters. The title may match any 1-3 line window of page 1, including a reference list or a "please cite" cover. | `bind()` on generated pages; all three below come out `bound`: (a) the title under "Q. Someone-Else" whose body says "towards", with registry author Ward (ratio 1.0); (b) page 1 is another paper's reference list that cites the title wrapped onto its own line, author Smith (1.0); (c) a "please cite: Smith, J. (2010) <title>" cover over a different paper (0.914). `author_on_page` is True on a page not by them for Ward, Hall, Long, Park, Rose, Wang, Chen and Li (Li via "Li-ion"). A series Part 2 page against a Part 1 registry title was correctly refused (0.763). Mutations R1 (Python ratio 0.85→0.60), R2 (DB ratio 0.85→0.50) and R3 (author = first 3 letters) **all survive**: the only below-threshold ratio any test sends is 0.36 or 0.4, and the only authors are "Tester" and "Someone-Else". | Match the surname as a whole token, with multi-part names as consecutive tokens. Require it within a few lines of the matched title window. Refuse windows under a References heading or shaped like a citation (year plus venue). Add boundary tests at 0.84/0.85 on both sides (Python and `_check_binding`), and tests for the three pages above. |
| D3 | Medium | **`approve_admission` never looks at the admitter's workstream.** It locks only the approver's workstream, and `abandon_workstream` locks only its own. The builder's "untested residual" is a real defect. | (a) Abandon ws_a, then approve its proposal from ws_b: `approved`, work in main, ws_a `abandoned`. (b) Approve left uncommitted while ws_a is abandoned: the abandon does **not** block, and both commit. (c) The reverse order: approve does not block, and both commit. (d) A manual proposal carrying a DOI in a workstream that is then abandoned: a later registry admission of that DOI returns `duplicate` pointing at a work **not in main**, so acquisition can never attach a file to it. | In `approve_admission`, `SELECT … FROM workstreams WHERE id = a.workstream_id FOR SHARE` and require it open. Abandonment should withdraw or refuse pending manual admissions. The check-2 lookup should ignore proposed versions of non-open workstreams. Add tests for (a)-(d). |
| D4 | Medium | **The archive run cap undercounts.** `Budget.used` counts only `downloaded` / `hash-mismatch`. A `fast_download.json` that issues a URL and then ends `partner-404` or `bad-file` is not counted. | Stub probe, 7 works whose partner returns 404: 7 download URLs issued, `downloads_left` 900→893, `budget.used = 0`, no `quota-stop` under a cap of 5. That such a call spends quota is **inferred** from aa_fetch ("Re-requesting the same md5 is quota-free") and the gate's 980→977 steps, **not measured live**. Mutation R11 (cap `>=`→`>`) **survives**: no test ever reaches the cap (B10 fired only through the margin path). The cap is also per CLI call, not per run of calls. | Count a download when a URL is issued for a new md5, or when `downloads_left` drops. Add a test where the cap fires at exactly N. |
| D5 | Medium | **`make_key` never adds the convention's `a`/`b` suffix.** Two different works with the same first author, year and first four slug words cannot both be admitted. | Probe: two distinct DOIs and titles give the same key `Tester_2020_canopy-mapping-urban-forests`. The second is `collided` on `works_key_key` and its candidate `rejected` ("not retried"). P3's bulk load will hit this. | On a key collision where the identifiers differ, retry with `a`/`b` per the convention, or return a non-rejecting `key-collision` outcome. Add a test. |
| D6 | Low | **Some dedupe and store guards are unshown.** | R9 (admit's file sha256 lookup removed) survives: the unique index turns it into `collided`/`rejected`, so no test sees `file_duplicate`. R10 (disk index covers only `Validation/`) survives: dedupe against staging, quarantine and other topic folders is untested. R12 (`move_new` via unguarded `shutil.move`) survives, and the no-delete scan does not flag `shutil.move` or `Path.write_bytes`/`write_text`. `annas._quarantine` uses `shutil.move` safely today, behind its own exists-loop. | One test each. Extend the scan to `shutil.move` / `copy*` and `Path.write_*`. |
| D7 | Low | **The self-approval constraint is fooled by invisible label differences.** | On fresh manual admissions, session labels `sess-admit` + NBSP, `sess-admit` + zero-width space, and `SESS-ADMIT` all **approve** the admitter's own admission. Plain same-session and tab/space padding are refused. Case sensitivity is by design (0009 E-4). NBSP is exactly the copy-paste mistake §15.13 says the constraint should stop. | Compare after stripping Unicode whitespace and format characters (`\u00a0`, `\u200b`, `\ufeff`). |
| — | Info | **The DB year clause's `AND ratio >= 0.85 AND author_match` is an equivalent mutant.** R7 survives because the claimed-record guard above it already refuses. | Title-only ±1 is refused in the DB, in Python `compare_claimed` and through the front; ±1 with both matching (ratio exactly 0.85) is admitted. The rule is correct; that clause simply is not what enforces it. | None needed. Don't count it as a kill. |

## My mutations (whole `qc/test_litkb_p2.py` + `qc/test_litkb_annas.py`, `-m "not litkb_live"`, `litkb_test`)

Baseline before and after: `134 passed, 5 deselected`. Every restore was checked by sha256 (13/13 `True`), and
`git status` was clean afterwards.

| ID | Mutation | Result |
|---|---|---|
| R1 | `binding.BIND_RATIO` 0.85→0.60 | **SURVIVED** |
| R2 | `_check_binding` ratio 0.85→0.50 | **SURVIVED** |
| R3 | author check = family's first 3 letters as a substring | **SURVIVED** |
| R4 | SQL `norm_identifier` no longer strips `https://doi.org/` / `doi:` | **SURVIVED** (P2 file; P1 covers it) |
| R5 | Python `normalize_doi` keeps prefixes and a trailing `/` | caught (`TestResolve::test_normalize_doi`) |
| R6 | resolver accepts ±1 before the first-author check | caught (2 tests) |
| R7 | DB ±1 clause without ratio/author | survived — equivalent mutant (see Info) |
| R8 | approver session decorated (`p_session || '#approver'`) | caught (`test_kill_admitter_cannot_approve…`) |
| R9 | admit() file sha256 lookup removed | **SURVIVED** |
| R10 | disk hash index only `Validation/` | **SURVIVED** |
| R11 | archive run cap `>=`→`>` | **SURVIVED** |
| R12 | `move_new` → unguarded `shutil.move` | **SURVIVED** |
| R13 | `_check_binding` ignores `author_found` | caught (`…[author_missing]`) |

Builder's harness re-run by me (`qc/instruments/litkb_p2_mutations.py`, all 40):
- **40/40 FIRED — reproduced.**
- Baselines `134 passed, 5 deselected` before and after.
- 40 restores `match: True`, and `git status` clean afterwards.

The claim stands as stated. My survivors show where the named guards are tested only far from their thresholds (R1-R3, R11) or not at all (R4 in the P2 file, R9, R10, R12).

## Averkov / Higham replay (real `Validation\` files, fixture Crossref records)

- **WRONG DOI, no claim:**
  - `10.4171/JEMS/183`: refused at `check3_binding`, ratio 0.4071, author not found.
  - `10.1016/j.laa.2010.09.001`: refused at `check3_binding`, ratio 0.5, author not found.
  - The design quotes 0.36 / 0.25 from `audit_fast`. That came from a different instrument: aa_fetch's `title_best_window` also uses 1-3 line windows, but over the filed `.txt` head with aa_fetch's normaliser, while P2 reads page 1 via `pdftotext -f 1 -l 1` plus the PDF Title metadata. The gap was not traced further; both sets of numbers are far below 0.85.
- **WRONG DOI + manifest claim:** check 1 `fail`, check 3 `binding-failed`, for both.
- **Corrected DOIs** `10.4171/jems/179` and `10.1016/j.laa.2010.04.007` are `admitted`:
  - `rel_path = Validation/<stem>.pdf`;
  - sha256 equals the manifest's;
  - ratio 1.0 on page 1.
- **The UPPER-case variant** with the same file returns `duplicate` with the same work.
- **Both files are untouched:** sha256, size and mtime are identical before and after.
- The four builder tests also pass in my baseline.

## Gate on `litkb` (read-only)

Each of the five DOIs resolves to exactly one main work:
- Pengra 2020, McRoberts 2018, Ploton 2020 and Olofsson 2020 are verified by Crossref.
- Mahoney 2023 is verified by DataCite.

For each work:
- Its filed `_litkb_staging/filed/<key>.pdf` exists.
- Its disk bytes and sha256 **match** the `files` row.
- Its binding is `bound` at ratio 1.0.
- Its page 1 (pdftotext) carries the work's title and first author, read by eye.

Attempts:
- Pengra, McRoberts: `open_access no-oa-copy`, then `annas ok`.
- Ploton: `open_access blocked`, then `annas ok`.
- Olofsson: `open_access bad-file`, then `annas ok`.
- Mahoney: `open_access ok`.

Workstream `litkb-p2-gate` is still `open`:
- admissions: 7 admitted, 3 refused;
- attempt counts per route and status equal the report's breakdown, which sums to **17**; the report's stated total of "16" is an arithmetic slip;
- `files` holds 5 rows;
- `incoming\` is empty.

Nothing else under `Literture\` changed:
- `Validation\manifest.csv` sample of 20, including Averkov and Higham: **20/20** sha256 match.
- `manifest.csv` mtime is 2026-09-13 12:04, before P2.
- No file outside `_litkb_staging` / `_quarantine` has an mtime on or after 2026-09-14.
- `Literature_Tracker.xlsx` and `Reports/literature_tracker.csv` are unchanged in git from 057c450 to HEAD (xlsx mtime 2026-09-13).

Minor: the arXiv DOI is stored lower-cased (`10.48550/arxiv.2303.07334`), while the convention writes `arXiv`.

## Port fidelity (aa_fetch.py → litkb/acquire/annas.py)

**Kept, in the path litkb uses (`fetch_for_litkb`):**
- SciDB with redirects off, and a `/search` redirect read as `not-in-archive`;
- off-site redirects refused;
- gate 1b search fallback with every candidate record-verified;
- gate 2: the record carries the DOI, and `extension_best = pdf`;
- the domain_index 0-2 ladder, then the record's alternates;
- the `%PDF-` check;
- the md5 = the record's, and size = `filesize_best` (`hash-mismatch`, quarantined by the store).

**Kept in the ported `fetch_one`, which has a destination guard:**
- the manifest-hash dedupe, the content check, and the JSTOR stable-URL evidence;
- quarantine that never overwrites.

**Tests:**
- 80 aa_fetch test names → 81 in the port: 79 identical, 1 new guard test.
- 1 live test (`test_a_known_hit_reports_exists_without_downloading`) was rewritten resolve-only as `test_a_known_hit_resolves_to_its_md5_and_record`.
- The offline `exists`, `content-mismatch`, `duplicate-hash` and JSTOR tests remain.

**Lost or changed in the path litkb actually uses:**
1. `fetch_for_litkb` does not call `content_check`. So the JSTOR stable-URL evidence, DOI-in-extract acceptance and the INDETERMINATE-on-no-text-layer rule are gone. Binding replaces them. A scanned archive file (aa_fetch measured 7/207 with no text layer) now quarantines as `binding-pending` instead of being filed. That is consistent with §15.14, but it is a behaviour change that should be stated.
2. The live `exists` short-circuit is no longer exercised live; offline coverage remains.
3. The run cap counts differently from the archive's own spend (D4).

## Secrets

`git log -p 057c450..b2e10a7`, checked against the actual secret values in memory, printing only booleans:
- **Anna's Archive key:** absent.
- **Workstream token:** absent. The only hit from `.litkb-workstream` is the workstream id, a UUID, which the report publishes on purpose.
- **pgpass passwords:** no password value appears as a credential. One field coincides with an ordinary English word in existing prose; not a leak.
- **Unpaywall email:** it equals the git author email in every commit header; not a leak.
- No pgpass-shaped lines. The only 64-hex values added are the two manifest sha256s in the fixture CSV.

`.litkb-workstream` is ignored (`.gitignore:136`) and untracked. `qc/secrets_check.py`: `clean — 1169 indexed files`.

## Tests and ladder

- The P2 set (`test_litkb_p2.py` + `test_litkb_annas.py`, live deselected): `134 passed, 5 deselected in 13.78s`.
- `py -3.12 qc/check.py --fast`:
  - secrets, ruff and compile PASS;
  - pytest `1 failed, 2289 passed, 5 skipped` (`litkb Postgres tests: 182 passed`);
  - the one failure is the allowed `test_experiments.py::test_pointer_paths_resolve[crown_state_model]`.

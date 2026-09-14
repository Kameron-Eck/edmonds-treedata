# litkb P2 "Admission + acquisition" — independent acceptance, 2026-09-14

Scope: the P2 referee's fixes D1-D7 (`Reports/LITKB_P2_REFEREE_2026-09-14.md`), as landed in 890569b ("Fixes after
referee" in `Reports/LITKB_P2_REPORT_2026-09-14.md`, migration `0014_referee_p2_fixes.sql`, `qc/test_litkb_p2.py`).
Worktree `D:\edmonds-pipeline\treedata-litkb`, branch `work/20260913-literature-kb`, HEAD 890569b. I wrote none of
this code. Everything below was re-run by me (CLAUDE.md 3.4c); none of the fixer's reported numbers are used as
evidence.

## Verdict: NOT ACCEPTED — one of my own mutations (V2b) survived

- **Every referee mutation is now caught.** R1, R2, R3, R4, R9, R10, R11 and R12 all fail the whole P1+P2+annas set.
  The D1-D7 defects the referee named are covered.
- **V2b survived.** In `binding.window_refusal`, the reference-list rule was changed from `>= 2` to `>= 3`
  reference-shaped lines near the window. The whole set still passed: `353 passed`.
- **V2b is not an equivalent mutant.** I checked in memory, with no file written, on two pages whose reference list has
  two-line entries, so exactly 2 reference-shaped lines sit within `REF_NEIGHBOURHOOD` of the title:

  | Page | Real code | V2b mutant |
  |---|---|---|
  | author-year | `binding-failed` (`inside a reference list`, ratio 0.9016) | **`bound`**, ratio 1.0 |
  | bracketed | `binding-failed` (`inside a reference list`, ratio 0.9405) | **`bound`**, ratio 1.0 |

- **Why the tests miss it.** The three `test_binding_refuses_a_title_that_appears_only_in_a_reference_list` pages
  each put **3** reference-shaped lines around the title. The constant 2 is never tested at its boundary. That is the
  class the referee flagged in R1-R3 and R11.
- **The guard itself fires:** V2a is caught.
- **Fix, one test, not added by me (no permanent changes):** a page with exactly two reference-shaped lines within 2
  lines of the title must not bind. Either of the two pages above is that test.
- **Whether this blocks P2 is the orchestrator's call.** On the rule "every mutation must fire" it does. On "the
  referee's defects are caught" it does not.

## Method

**Fingerprints.**
- sha256 of the tracked files before anything ran, 48 in all:
  - `Scripts/pipeline/litkb/**`;
  - `qc/test_litkb_p1.py`, `qc/test_litkb_p2.py` and `qc/test_litkb_annas.py`;
  - `qc/testdata/litkb_p2/*`;
  - `qc/conftest.py`;
  - both mutation harnesses.
- `sha256sum -c` after the mutations, and again after the final baseline: **48/48 OK** both times.

**Test set.** Every mutation ran the WHOLE `qc/test_litkb_p1.py qc/test_litkb_p2.py qc/test_litkb_annas.py`, with
`-m "not litkb_live"`, on `litkb_test` only. The suite's fixture resets and migrates `litkb_test` from the files on disk.

**Runner.** I wrote my own runner in the session scratchpad; it is not committed and is not the fixer's
`litkb_p2_mutations.py`. For each mutation it:
1. applies an exact-once text edit;
2. runs the set;
3. restores the bytes;
4. checks the restore by sha256.

"Caught" means pytest exit ≠ 0 **with at least one FAILED test**. Collection or setup ERRORs do not count.

**R-row edits.**
- The R-row edits are semantically the referee's mutations, re-expressed where 0014 moved the code.
- For R1-R4 and R9-R12 my edit text matches the fixer's harness rows. I checked each against the referee's D-table
  wording before running it.
- R4 now removes 0014's cut-before-`10.` (`substring(... from '10\..*$')`), which is where the prefix strip lives since
  0014.
- R9 removes 0014's `admit()` file sha256 lookup block, since 0013's text is dead code.

**Baselines.** `353 passed, 5 deselected`, 0 skipped, before and after (56.0 s and 61.1 s).

## Mutations

| ID | Mutation | Result | Failing tests (first) |
|---|---|---|---|
| R1 | `BIND_RATIO` 0.85 → 0.60 | **caught** (2) | `test_binding_threshold_boundary_python[23-17-0.85-bound]`, `[29-21-0.84-binding-failed]` |
| R2 | 0014 `_check_binding` evidence `v_ratio < 0.85` → `< 0.50` | **caught** (2) | `test_db_check3_threshold_boundary[0.84-refused]`, `[0.8499-refused]` |
| R3 | author = surname's first 3 letters as a substring (`tokens_contain`) | **caught** (10) | `test_binding_matches_the_surname_as_a_whole_token[Ward…]`, `[Hall…]`, … |
| R4 | 0014 SQL `norm_identifier`: prefix cut before `10.` removed | **caught** (3) | `test_litkb_p1.py::test_identifier_case_variants_collide`, `test_doi_forms_sql_equal_the_table_and_python`, `test_db_stores_the_canonical_doi_and_refuses_a_non_doi` (now caught inside the P2 file too) |
| R9 | 0014 `admit()` file sha256 lookup removed | **caught** (1) | `test_admit_refuses_a_file_already_held_by_its_sha256` |
| R10 | disk hash index covers only `Validation/` | **caught** (6) | `test_disk_index_covers_every_folder_of_the_store[*]` |
| R11 | archive run cap `>=` → `>` | **caught** (1) | `test_archive_cap_counts_every_issued_download_url_even_when_the_partner_404s` |
| R12 | `move_new` → unguarded `shutil.move` | **caught** (6) | `test_acquisition_and_admission_code_hold_no_delete_path`, `test_store_move_new_never_overwrites_and_never_leaves_staging`, … |
| V1p | DOI drift, Python only: `urn:doi:` returned verbatim by `textnorm.normalize_doi` | **caught** (3) | `test_doi_forms_python`, `test_doi_forms_sql_equal_the_table_and_python`, `test_doi_sibling_spellings_admit_one_work` |
| V1s | DOI drift, SQL only: 0014 `norm_identifier` lower-cases but does not cut a `urn:doi:` value | **caught** (1) | `test_doi_forms_sql_equal_the_table_and_python` (the only test that catches it) |
| V2a | reference-list window: `REF_NEIGHBOURHOOD` 2 → 0 | **caught** (2) | `test_binding_refuses_a_title_that_appears_only_in_a_reference_list[bracketed]`, `[author_year]` |
| V2b | reference-list window: `sum(ref) >= 2` → `>= 3` | **SURVIVED** | none: `353 passed` (non-equivalent, see Verdict) |
| V3 | whole-token surname: `_JOINERS = ""` (a hyphenated word splits, so "Li-ion" yields `li`) | **caught** (1) | `test_binding_matches_the_surname_as_a_whole_token[Li-Li-ion lie lithium]` |
| V4 | 0014 `approve_admission`: the admitter's workstream state is checked **without** `FOR SHARE` | **caught** (2) | `test_approve_and_abandon_of_the_admitters_workstream_wait_for_each_other[approve]`, `[abandon]` |
| V5p | format characters, Python layer only: U+FEFF dropped from `INVISIBLE_RANGES` | **caught** (2) | `test_every_invisible_character_is_removed_python`, `test_self_approval_is_refused_…[bom]` |
| V5s | format characters, SQL layer only: `norm_label` strips `[[:space:]]` and its Cf class never matches | **caught** (4) | `test_every_invisible_character_is_removed_sql`, `test_self_approval_is_refused_…[bom]`, `[word_joiner_inside]`, `[zero_width_space]` |

**Disclosure on V5s.** My first form of V5s commented out the rest of the `norm_label` line. The character class
contains real LF bytes (U+000A lies inside its 0x09-0x0D range), so the comment ended mid-literal and the migration
failed to parse. That run gave `159 passed, 194 errors`, 0 FAILED. It was invalid as a mutation, is not counted, and was
re-expressed as the row above. Every restore matched by sha256.

## Averkov / Higham replay

This was my own script, not the test functions. It used the real `Validation\` PDFs and the fixture Crossref records
through `RegistryStub`. It ran on `litkb_test`, freshly reset and migrated under the suite's advisory lock, with
14 migrations recorded.

**Pre-fix DOI, no claim: refused at `check3_binding`.**
- Averkov `10.4171/JEMS/183`: `binding-failed`, ratio 0.4071.
- Higham `10.1016/j.laa.2010.09.001`: `binding-failed`, ratio 0.5.
- Both carry the reasons "title ratio < 0.85", "first author is not on the first page" and "not a whole token near
  the matched title".

**Pre-fix DOI with the manifest claim:** both `refused`, with check 1 `fail` and check 3 `binding-failed`.

**Corrected DOIs** `10.4171/jems/179` and `10.1016/j.laa.2010.04.007` are both `admitted`:
- `rel_path = Validation/<stem>.pdf`;
- the file sha256 equals the manifest's;
- the binding is `bound` at ratio 1.0, with `author_near_title = true`.

**Sibling spellings.** Each of the following returned `duplicate` of the same work:
- the UPPER-case variant;
- `https://doi.org/<UPPER>/`;
- `urn:doi:<doi>`.

Exactly **1** work carries each corrected DOI.

**The files are untouched:** sha256, size and mtime are identical before and after, for both PDFs.

## Two-connection race (D1)

This ran on `litkb_test`, with two `litkb_writer` connections calling raw `litkb.admit(...)` in SQL. It bypasses the
Python normaliser, so the database's lock and lookup alone decide. The holder's transaction stayed open. The waiter ran
in a thread, and `pg_blocking_pids` was polled before the holder committed.

| Holder spelling | Waiter spelling | Waiter blocked | Still waiting at commit | Waiter outcome | Works carrying the DOI |
|---|---|---|---|---|---|
| bare | bare + `/` | yes | yes | `duplicate`, same work | 1 |
| bare + `/` | bare | yes | yes | `duplicate`, same work | 1 |
| bare | `https://www.doi.org/<UPPER>/` | yes | yes | `duplicate`, same work | 1 |

## Read-only probes on `litkb`

**Migrations: 14 recorded**, the last being `0014_referee_p2_fixes.sql`.
- `litkb_reader` has no USAGE on `litkb_meta`, so this one count was read as `litkb_owner` via `connect_admin`, with
  `default_transaction_read_only = on`.
- Every other probe ran as `litkb_reader` with `default_transaction_read_only = on`.

**Duplicates: none.**
- 7 DOI identifiers, 7 versions, 7 works.
- 0 stored `value_norm` differ from `norm_identifier('doi', value_norm)`.
- 0 active canonical DOIs sit on more than one work (0014's pre-check query).
- 0 `value_norm` on more than one work, over any version.
- 0 Python-canonical DOIs on more than one work.
- 0 values where `value_norm` differs from `textnorm.normalize_doi(value)`.

**Gate: intact.**
- Workstream `litkb-p2-gate` is `open`.
- Admissions: 7 `admitted`, 3 `refused`.
- 5 files, each with:
  - its disk sha256 and size matching the `files` row;
  - binding `bound` at 1.0;
  - its work in main;
  - its DOI on exactly 1 work.
- Attempts total **17**:

  | Work | Attempts |
  |---|---|
  | Mahoney 2023 (DataCite) | `open_access ok` |
  | McRoberts 2018 | `open_access no-oa-copy`, then `annas ok` |
  | Pengra 2020 | `open_access no-oa-copy`, then `annas ok` |
  | Olofsson 2020 | `open_access bad-file`, then `annas ok` |
  | Ploton 2020 | `open_access blocked`, then `annas ok` |

- `_litkb_staging\incoming` is empty.

**`Literture\` unchanged.** A full-tree scan found 529 entries and **0** with LastWriteTime or CreationTime after this
session's first write (11:06:00). There were no archive downloads, and `LITKB_LIVE` was never set.

## Secrets

- **`git log -p d432214..890569b`** (1 commit) was checked in Python against the actual values. Only names and
  present/absent were printed.
- **Values checked, all absent:**
  - the 5 passwords in the shared `pgpass.conf`;
  - the promoter passfile password;
  - the ingest passfile password;
  - the Anna's Archive key;
  - the workstream token from `.litkb-workstream`.
  - `D:\tools\annas-mcp\.env` holds no values.
- **Shapes in added lines:**
  - 0 pgpass-shaped lines;
  - 0 64-hex values;
  - 0 `key=`/`token=`/`password=` literals.
- **Secrets rung:** `py -3.12 qc/secrets_check.py` returned `clean — 1175 indexed files`.

## End state

- The final baseline was `353 passed, 5 deselected`.
- 48/48 fingerprints match.
- `git status --short` was clean before this report was written.
- HEAD was 890569b.
- `litkb` received no writes.

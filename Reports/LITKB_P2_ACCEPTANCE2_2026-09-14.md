# litkb P2 — independent acceptance, final round, 2026-09-14

Scope: the surviving mutation of the first acceptance round (V2b, `Reports/LITKB_P2_ACCEPTANCE_2026-09-14.md`) and the
guards added by the pre-1990 edge run (`Reports/LITKB_EDGE_PRE1990_2026-09-14.md`: E1–E4, Q1–Q3), as landed in e9f5a88.
Worktree `D:\edmonds-pipeline\treedata-litkb`, branch `work/20260913-literature-kb`, HEAD e9f5a88. I wrote none of this
code and none of the P2 tests. Every number below was produced by me, re-running everything (CLAUDE.md 3.4c); no figure
reported by the author of the fixes is used as evidence.

## Verdict: NOT ACCEPTED — one of my own mutations (E3f) survived

- **V2b is caught.** The mutation that survived the first round now fails the whole set on exactly the boundary test the
  first round asked for: `test_binding_reference_list_rule_at_its_boundary[2-False]`. That row is closed.
- **Every new guard fires.** E1, E2, E3, E4 and Q1–Q3, each re-derived by me from the source rather than copied from the
  harness, all fail the whole P1+P2+annas set. So do both mutations of my own that are not in the harness.
- **E3f survived.** E3 (the NUL-safe jsonb fix) is enforced by `textnorm.jsonb_safe` called from **two** `_jsonb`
  helpers. Removing it from `acquire/run.py` fails the set. Removing it from `admit/front.py` — the helper that carries a
  file's PDF metadata into `litkb.admit(...)`, i.e. the `admit --file` path — leaves `380 passed`. The guard is tested on
  one of its two call sites. (The path is read off the source: `front.file_evidence` puts `_binding.pdf_info(p)` into the
  evidence dict's `pdf_metadata`, and `front.admit()` sends that dict as `_jsonb(file_json)`. The end-to-end admission
  was not itself run under the mutant.)
- **E3f is not an equivalent mutant.** Measured on the live server, against the real Bell 1977 shape (`Creator`
  `'Acrobat 3.0 Capture Plug-in'` followed by NULs), on `litkb_test`, read-only:

  | Path | `SELECT %s::jsonb` |
  |---|---|
  | real `front._jsonb` | accepted, `{'Creator': 'Acrobat 3.0 Capture Plug-in'}` |
  | E3f mutant `Jsonb(v)` | **`UntranslatableCharacter`: unsupported Unicode escape sequence** |

  That is the same exception class the edge run hit live. A registry admission carrying a NUL-bearing PDF would crash on
  the admission path exactly as it used to on the acquisition path.
- **Fix, one test, not added by me (no permanent changes):** admit a file whose PDF metadata carries a NUL through
  `front.admit_registry(..., file_path=...)` and assert it does not raise. `test_a_nul_character_in_pdf_metadata_never_
  breaks_an_attach` exercises only the acquisition helper.
- This is the same class as the first round's V2b: the guard is real, the test covers one instance of it. On the bar the
  first round set — every mutation of a guard must fire — P2 is not accepted.

## Method

**Fingerprints.** sha256 of **51** tracked files before anything ran: `pipeline/litkb/**` (`*.py` and `*.sql`, including
all 14 migrations), `qc/test_litkb_p1.py`, `qc/test_litkb_p2.py`, `qc/test_litkb_annas.py`, `qc/conftest.py`,
`qc/testdata/litkb_p2/*` and both mutation harnesses. Re-computed after every batch and after the final baseline:
**51/51 match**, every time. `__pycache__` excluded.

**Test set.** Every mutation ran the WHOLE `qc/test_litkb_p1.py qc/test_litkb_p2.py qc/test_litkb_annas.py` with
`-m "not litkb_live"`, on `litkb_test` only (the suite resets and migrates it from the files on disk). The fixer's
harness defaults to P2 + annas; I did not inherit that.

**Runner.** My own, in the session scratchpad, not committed, not `qc/instruments/litkb_p2_mutations.py`. Per mutation:
exact-once text edit (a target occurring any number but once aborts) → run the set → restore the original bytes →
confirm the restore by sha256. "Caught" = pytest exit ≠ 0 **and** a whole-word `N failed` count > 0 in the summary; a
strict xfail is not a failure (G1 makes the baseline carry one).

**Baselines.** `380 passed, 5 deselected, 1 xfailed`, exit 0, before (58.5 s) and after (58.6 s).

**Mutation wording.** V2b is applied exactly as the first acceptance report quotes it. E1–E4 and Q1–Q3 are my own
expressions of each defect, read off the current source; where the task's description and the harness row differ, the
task's description governs (Q2 is "parse split-span digits wrongly", not the harness's fail-open).

## Mutations

| ID | Mutation (my wording, from the source) | Caught | First failing test |
|---|---|---|---|
| V2b | `binding.window_refusal`: `sum(ref[lo:hi]) >= 2` → `>= 3` | **caught** (1) | `test_binding_reference_list_rule_at_its_boundary[2-False]` |
| E1 | `front.make_key`: `p[1:].lower() if p.isupper()` → `if False` (an all-capitals registry surname is no longer folded) | **caught** (6) | `test_make_key_is_the_same_whatever_case_the_registry_prints_the_surname_in[PAGE-Page]`, `[HAWKES-…]`, `[BROOK-…]`, `[O'NEIL-DUNNE-…]` |
| E2 | `run.acquire`: `if _in_topic_folder(store, from_file)` **inverted** (a topic-folder file is landed as a copy) | **caught** (2) | `test_acquire_from_file_binds_an_unheld_file_in_a_topic_folder_in_place` |
| E3 | `run._jsonb`: `Jsonb(jsonb_safe(v))` → `Jsonb(v)` | **caught** (1) | `test_a_nul_character_in_pdf_metadata_never_breaks_an_attach` |
| E3f | `front._jsonb`: `Jsonb(jsonb_safe(v))` → `Jsonb(v)` (the admission path's copy of the same guard) | **SURVIVED** | none: `380 passed` (non-equivalent, see Verdict) |
| E4 | `run.work_record`: `normalize_doi(v) == want` → `!= want` (a two-DOI work is acquired by the DOI that was **not** asked for) | **caught** (1) | `test_work_record_is_acquired_by_the_doi_it_was_reached_by` |
| Q1 | `annas.fetch_for_litkb`: the counter guard's `if quota_margin is not None:` → `if False:` — the counter is read and then ignored | **caught** (3) | `test_archive_reads_the_account_counter_before_every_download_request[at_margin]`, `[past_limit]`, `[unreadable]` |
| Q1b | the same stop at its boundary: `q[0] >= q[1] - margin` → `>` | **caught** (1) | `…[at_margin]` |
| Q2 | `annas.parse_quota`: tags removed **with** a space, so `<span>2</span>4` reads as `2 4` and the counter is misparsed | **caught** (1) | `test_account_counter_parser_reads_only_the_counter[span_split-expected1]` |
| Q3 | `run.acquire`: `quota_margin=budget.quota_margin` → `quota_margin=0` (the margin is off; only a hard limit stops) | **caught** (2) | `…[at_margin]`, `…[below_margin]` |
| **N1** (own, not in the harness) | `annas.read_quota`: `parse_quota(body) if st == 200 else None` → `parse_quota(body)` — a non-200 account answer is parsed for a counter anyway (fail-closed removed) | **caught** (1) | `test_read_quota_fails_closed_on_a_bad_answer` |
| **N2** (own, not in the harness) | migration 0014 `_check_binding`: `v_ratio < 0.85` → `<= 0.85` — the database's check-3 ratio rule at its exact boundary | **caught** (1) | `test_db_check3_threshold_boundary[0.85-admitted]` |

Restores: 12/12 byte-identical by sha256.

**On step 4's second target.** There is **no reference-window rule in the database**: migration 0014's `_check_binding`
re-checks `title_region`, `author_near_title` and the ratio, and the reference-list window lives only in
`binding.window_refusal` (Python). N2 is the boundary that does exist in the DB check, and it is covered — the test
already parametrises the exact value 0.85 as `admitted`, which is why the mutation fires there and not on 0.84.

## Read-only probes on `litkb`

Every probe ran with `default_transaction_read_only = on`; all but the migration count as `litkb_reader` (the reader has
no USAGE on `litkb_meta`, so that one ran as `litkb_owner` via `connect_admin`). No write reached `litkb`.

- **Migrations: 14**, the last `0014_referee_p2_fixes.sql`.
- **`edge-pre1990` is `open`.** Candidates: `admitted` 23, `duplicate` 3, `duplicate-review` 1, `rejected` 9.
  Admissions: `admitted` 22, `proposed` 1, `refused` 13. Attempts: annas `bad-file` 2, `duplicate-held` 2; browser `ok`
  3, `binding-pending` 3, `binding-failed` 2, `manual-step` 1. Every count equals the edge report's, independently read.
- **No duplicate normalised DOIs.** 29 works, 30 active DOI identifiers; 0 `value_norm` differ from
  `litkb.norm_identifier('doi', value)`; 0 differ from Python `textnorm.normalize_doi`; 0 normalised DOIs — SQL-canonical
  or Python-canonical — sit on more than one work.
- **The 5 P2 gate works are intact.** `litkb-p2-gate` is `open`, admissions 7 `admitted` / 3 `refused`, and its 5 active
  files are each `bound` at ratio `1.0`.

## Secrets

`git log -p 63aa5ce..e9f5a88` (**1** commit — `git rev-list --count` — 68,294 bytes, 709 added lines) was searched in Python for the **actual
values**; only names and present/absent were printed.

- **Absent, all 8:** the 5 passwords in the shared `pgpass.conf`, the promoter passfile password, the ingest passfile
  password, the `edge-pre1990` workstream token. The Anna's Archive key is also absent. `D:\tools\annas-mcp\.env` holds
  no values.
- **Shapes in added lines:** 0 pgpass-shaped lines, 0 64-hex values, 0 `key=` / `token=` / `password=` literals.
- The three new `qc/testdata/litkb_p2/account_counter*.html` fixtures were read in full: the account id is `XXXXXXX`, the
  invite link is gone, and the secret key appears only as a link (`href="/account/secret_key"`), never as a value.
- `_litkb_ws/…/.litkb-workstream` is git-ignored (`.gitignore:2:/*`).
- **Secrets rung:** `py -3.12 qc/secrets_check.py` → `clean — 1180 indexed files`.

## End state

- Final baseline `380 passed, 5 deselected, 1 xfailed`, exit 0; 51/51 fingerprints match.
- `git status --short` clean; HEAD e9f5a88.
- `litkb` received no writes. `litkb_test` was used only by the suite and by one read-only `SELECT %s::jsonb`.
- **`Literture\` unchanged, measured:** a full recursive scan found 529 entries and **0** whose `LastWriteTime` or
  `CreationTime` is later than this session's first write. Nothing there was moved, renamed or deleted. No archive
  download was made and `LITKB_LIVE` was never set (the 5 deselected tests are the `litkb_live` ones).

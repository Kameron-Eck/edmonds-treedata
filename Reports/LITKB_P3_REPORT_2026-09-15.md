# litkb P3 — Migration + exports, 2026-09-15

Branch `work/20260913-literature-kb`, worktree `D:\edmonds-pipeline\treedata-litkb`.
Design: `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §4.6, §9.1, §10, §13, §14 P3 row.
Decisions: `Scripts/decisions.yaml` `litkb-p0-foundation`, "P3 load (Kam, 2026-09-14)".

**Status of this evidence (CLAUDE.md 3.4c):** every number below was produced by the author of
the code, and has since been re-run by an independent referee —
`Reports/LITKB_P3_REFEREE_2026-09-15.md`, **P3 ACCEPTED WITH FIXES**. Every total reproduced; the
load is clean, checked cell by cell rather than sampled; the **gate was defective** and four labels
were wrong. See **"Fixes after referee"** at the end for what changed — the gate and the labels, not
a number in the database.


## What was built

| Piece | Home |
|---|---|
| `discrepancies` + the token-checked `record_discrepancy`, its only writer | `pipeline/litkb/db/migrations/0015_discrepancies.sql` |
| The case table: what a legacy row's identity is, and therefore how it is admitted | `pipeline/litkb/migrate_legacy/plan.py` |
| The loaders (tracker, manifest), through `admit.front`, never a direct insert | `pipeline/litkb/migrate_legacy/run.py` |
| Reading the legacy files, read-only | `pipeline/litkb/migrate_legacy/sources.py` |
| How a work is PRINTED — one home, shared by the export and the comparison | `pipeline/litkb/migrate_legacy/export_shape.py` |
| `litkb export tracker\|manifest\|all [--diff]` | `pipeline/litkb/export.py`, `pipeline/litkb/commands.py` |
| The gate | `qc/instruments/litkb_p3_diff.py` → `phase4/qc/litkb_p3_diff.csv` |
| Kills and guards | `qc/test_litkb_p3.py` |
| Mutation rows | `qc/instruments/litkb_p2_mutations.py` (P1a–P1e, P2a–P2b, P3b, P4a, P5a, P6a–P6f) |
| The convention, rewritten | `Scripts/docs/LITERATURE_CONVENTION.md` |


## Totals — the live load (database `litkb`, workstream `p3-migration`, left OPEN)

Workstream id `01a0a494-bb54-7c1b-be26-db0c229a9534`, branch `work/20260913-literature-kb`.
460 tracker rows and 207 manifest rows offered; the 30 works `litkb-p2-gate` and `edge-pre1990`
already held were deduped against, never re-admitted.

| | count |
|---|---|
| **works admitted** (registry route, facts) | **336** |
| **manual admissions PROPOSED** (need a second session's approval) | **12** |
| **files bound in place** | **169** |
| candidates, total (460 tracker + 40 manifest-only) | 500 |
| — admitted | 348 |
| — duplicate (deduped against an existing work) | 43 |
| — duplicate-review (title similarity, no identifier) | 2 |
| — rejected (a recorded refusal, never a silent skip) | 39 |
| — **held**: recorded, flagged, not admitted, and (after the referee) carrying the reason | **68** |
| admissions refused at binding — **binding-pending, waiting for OCR** | **10** |
| admissions refused at binding — binding-failed | 29 |
| admissions refused at **check 2 as duplicates** (43 `duplicate` + 2 `duplicate-review`) | 45 |
| `tracker` identifiers written | 346 |
| `doi` identifiers written | 336 |
| `legacy_stem` identifiers written | 169 |
| use versions (state `proposed`, kind `context`) | 370 |
| **discrepancies** | **909** |

The 43 duplicates point at works admitted by `edge-pre1990` (34), `litkb-p2-gate` (7) and by an
earlier row of this same load (2). Integrity: 68 candidates are in state `new`, which is exactly the
held count, and **no** candidate that left `new` lacks an admission row.

**Idempotence.** Three further passes over both loaders after the load finished. Pass 2 and pass 3
each reported `skipped_already_loaded` 460 and 207, `admitted` 0, `discrepancies` 0, `uses` 0, and all
seven table counts — works, identifiers, files, candidates, admissions, discrepancies, uses — were
identical before and after. A later pass, after the arXiv and manual-author records were added,
backfilled 79 of them; the pass after that changed nothing again.

**The load was interrupted once, by a defect.** Tracker row 327's YEAR cell reads `2019a` — the
filename convention's same-year suffix written into the year column — and `int('2019a')` raised, ending
the pass at row 336. That is what idempotence is for: the fix landed, the resume re-read its own
candidates, skipped 326 rows and finished the remaining 134. Nothing was loaded twice.

## Discrepancy breakdown by field

| source | field | count |
|---|---|---|
| tracker | `authors` | 254 |
| tracker | `journal` | 206 |
| tracker | `title` | 53 |
| tracker | `arxiv` | 44 |
| tracker | `year` | 22 |
| tracker | `doi` | 21 |
| tracker | `duplicate_of` | 4 |
| manifest | `authors` | 137 |
| manifest | `journal` | 117 |
| manifest | `title` | 22 |
| manifest | `arxiv` | 16 |
| manifest | `year` | 7 |
| manifest | `doi` | 6 |
| **total** | | **909** |

Read them as four things, not one. **`journal` (323)** is almost entirely abbreviation — `IEEE TGRS`
against `IEEE Transactions on Geoscience and Remote Sensing`. It is never a check-1 field, so it never
withheld a claim. **`authors` (391)** splits two ways: a registry record that divided a name the other
way round (`Qin, H. et al.` against a first author of `Hao`), and the lossy author parse of a manual
admission. **`title` (75)** and **`year` (29)** are the ones that matter — a title at ratio 0.2–0.4
means the row's DOI resolves to a different paper. **`arxiv` (60)** are ids the rows carry that P3 did
not admit, because an unverified strong identifier refuses the whole admission (P2 judgement 5).

## The reviewed diff — the §14 P3 gate

`qc/instruments/litkb_p3_diff.py` → `phase4/qc/litkb_p3_diff.csv`. It compares the **committed
baseline** (`qc/testdata/litkb_p3/*.baseline.csv`, copied before the exporter first ran) against the
regenerated tracker and manifest, cell by cell.

**Result: 1086 changed cells, 0 UNEXPLAINED. GATE PASS.**
No row is lost or added on either side: 460 tracker rows in, 460 out; 207 manifest rows in, 207 out.

| bucket | cells | meaning |
|---|---|---|
| explained | 713 | a `discrepancies` record names this source, row and field |
| format | 243 | the two cells normalise equal — `D.J.` against `D. J.`, a trailing stop, a DOI spelled differently |
| structural | 120 | a whole-column change the design makes on purpose, stated once |
| filled | 10 | the legacy cell was EMPTY and the registry supplies a value |
| **UNEXPLAINED** | **0** | the gate fails while this is above zero |

### Counts per field

| source | field | bucket | cells |
|---|---|---|---|
| manifest | `arxiv` | explained | 13 |
| manifest | `authors` | explained | 127 |
| manifest | `authors` | format | 2 |
| manifest | `doi` | filled | 5 |
| manifest | `doi` | format | 22 |
| manifest | `obtained_date` | structural | 3 |
| manifest | `source_route` | structural | 3 |
| manifest | `stem` | structural | 110 |
| manifest | `title` | explained | 21 |
| manifest | `title` | format | 53 |
| manifest | `venue` | explained | 105 |
| manifest | `venue` | filled | 5 |
| manifest | `venue` | format | 1 |
| manifest | `verified_against_extract` | structural | 4 |
| manifest | `year` | explained | 7 |
| tracker | `Author(s)` | explained | 209 |
| tracker | `Author(s)` | format | 8 |
| tracker | `DOI/URL` | explained | 19 |
| tracker | `Feeds` | format | 27 |
| tracker | `Journal/Source` | explained | 167 |
| tracker | `Journal/Source` | format | 18 |
| tracker | `Title` | explained | 29 |
| tracker | `Title` | format | 112 |
| tracker | `Year` | explained | 16 |

### Twenty explained differences

| source | row | field | baseline | export | ratio |
|---|---|---|---|---|---|
| tracker | 8 | `Title` | Tree crown detection and delineation in a temperate  | Tree Crown Detection and Delineation in a Temperate  | 0.9046 |
| tracker | 9 | `Author(s)` | Zhao, Y. et al. | Zhao, H. et al. |  |
| tracker | 13 | `Journal/Source` | ISPRS Open J. Photogramm. Remote Sens. | ISPRS Open Journal of Photogrammetry and Remote Sens | 0.7778 |
| tracker | 14 | `Journal/Source` | ISPRS Annals | ISPRS Annals of the Photogrammetry, Remote Sensing a | 0.2553 |
| tracker | 15 | `Title` | Automatic relative radiometric normalization of bi-t | Automatic Relative Radiometric Normalization of Bi-T | 0.8867 |
| tracker | 16 | `Journal/Source` | IEEE J. Selected Topics in Signal Processing | IEEE Journal of Selected Topics in Signal Processing | 0.9053 |
| tracker | 18 | `Journal/Source` | Int. J. Remote Sensing | International Journal of Remote Sensing | 0.678 |
| tracker | 21 | `Author(s)` | Dai, X. & Khorram, S. | Xiaolong Dai & Khorram, S. |  |
| tracker | 21 | `Journal/Source` | IEEE Trans. Geoscience & Remote Sensing | IEEE Transactions on Geoscience and Remote Sensing | 0.8372 |
| tracker | 26 | `Journal/Source` | Photogrammetric Eng. & Remote Sensing | Photogrammetric Engineering &amp; Remote Sensing | 0.85 |
| tracker | 32 | `Author(s)` | Wang, M. & Fan, H. | Wang, Z. et al. |  |
| tracker | 34 | `Title` | Deep Siamese domain adaptation CNN for cross-domain  | Deep Siamese Domain Adaptation Convolutional Neural  | 0.8804 |
| tracker | 34 | `Journal/Source` | IEEE IGARSS | arXiv | 0.25 |
| tracker | 41 | `Title` | Universal Language Model Fine-tuning for Text Classi | Universal Language Model Fine-tuning for Text Classi | 0.9449 |
| tracker | 41 | `Journal/Source` | ACL | Proceedings of the 56th Annual Meeting of the Associ | 0.0541 |
| tracker | 42 | `Author(s)` | Burmeister, J. et al. | Burmeister, J.M. et al. |  |
| tracker | 42 | `Journal/Source` | ISPRS Archives | The International Archives of the Photogrammetry, Re | 0.2 |
| tracker | 43 | `Journal/Source` | arXiv preprint | arXiv | 0.5263 |
| tracker | 60 | `Year` | 2019 | 2018 |  |
| tracker | 60 | `Title` | blockCV: An R package for generating spatially or en | block CV : An r package for generating spatially or  | 0.9857 |

## The case table — how a legacy row's identity is decided

Kam's P3 decision is that **identity comes from the registry record and the verified file**, that
**every field that disagrees is kept as a flagged discrepancy**, and that there is **no correction
pass**. `pipeline/litkb/migrate_legacy/plan.py` is that decision as five cases, and it is the only
place they are written down:

| case | the row | what the loader does |
|---|---|---|
| **A** | the DOI confirms and the claim agrees | `admit_registry(claimed=row, file if held)` — the ordinary P2 path |
| **B** | the DOI confirms, the claim disagrees, a file is held | `admit_registry(claimed=None, file)` — the file's BINDING is the comparison (P2 judgement 2). The registry record is admitted; the row's words survive as discrepancies |
| **C** | the DOI confirms, the claim disagrees, no file | **HELD.** Not admitted, not skipped |
| **D** | no DOI, or it does not confirm, but title + first author + year resolve | the resolved DOI, then A or B, plus a `doi` discrepancy against what the row spelled |
| **E** | nothing resolves | a manual admission (a proposal, signed off from a second session) when a file is held; otherwise HELD |

**Why C is held and not admitted.** A DOI alone proves only that *some* work exists. Migration 0013's
`_check_registry` says so in as many words — "no claimed record to compare with the registry and no
bound file" — so a DOI-only admission needs a bound file. Admitting a case-C row would mean either
offering check 1 a claim it must refuse, or bypassing check 1. Design §13's first line is that the
loaders go through the P2 admission code, "not a bypass", so the row waits for its file instead. It
is recorded (a candidate with the row verbatim), flagged (its discrepancies), and exported (verbatim,
with `litkb_state` saying why). It is never a silent skip.

**Two predicates, not one.** `agrees` is check-1 acceptability — `registry.compare_claimed`, which is
`resolver.judge_candidate`, the same comparator admission uses. It decides the admission SHAPE.
`differs` is plain normalised inequality, and it decides what is RECORDED. Conflating them was a real
bug, caught before the live load: a title accepted at ratio 0.92, a year accepted at ±1 under §15.15,
an abbreviated venue — each prints differently in the export from what the tracker says today, so each
needs a record explaining it, even though admission was right to accept the row. Kam's words are
"every field that disagrees with the registry", not "every field check 1 rejects".

## Judgement calls

1. **Case C is held, not proposed.** A manual admission is not a fallback for it: migration 0013's
   check 4 requires a manual admission to carry a bound file, and §15.14 says a file refused at
   binding waits for OCR rather than being admitted another way. So a row with a confirming DOI, a
   contradicted claim and no file has no admission route at all today. It is held, and P3 reports the
   count rather than inventing one.
2. **`add_candidate` is called by the loader, not left to `admit_registry`.** The candidate is the one
   home for the tracker fields no column holds — `Search Phase`, `Status`, `Read date`, `Bib line`,
   `Duplicate of` — and, under `_manifest`, the manifest row's `source_route`, `obtained_date` and
   `cited_by`. The export reads them back from `raw_record`. Without this those cells could not be
   regenerated at all, and the field-for-field gate could not pass.
3. **`Duplicate of` rows are not given a duplicate-link table of their own.** The database already has
   one: a second row carrying an already-admitted DOI is refused as `duplicate`, and its candidate
   records `admitted_work_id` — the link. P3 adds the tracker's own `Duplicate of` claim as a
   `duplicate_of` discrepancy so the review can see what the row asserted. No new mechanism.
4. **Tracker `Status` is not mapped onto the `use_versions` status enum.** `To Read` / `Read` /
   `Not Obtained` / `Duplicate` are read-state words; `proposed` / `supported` / `refuted` are claims
   about the work. Mapping one to the other would be inventing a judgement the tracker never made.
   Every migrated use is `kind = context`, `status = proposed`, with the grade in `confidence` and the
   `Status` and `Notes` text carried verbatim in `rationale`.
5. **No evidence pointer on any migrated use.** A `use_evidence` row needs a quote the database can
   verify against an extracted block, and blocks arrive in P5. P3 writes no evidence rather than an
   unverified pointer — `quote_verified` would be false and promotion would refuse it anyway.
6. **The convention's `a`/`b` key suffix is applied by the loader.** `works.key` is
   `Surname_Year_slug` where the slug is the first four non-stopword title words, and it is unique. In
   a 460-row load, two papers by one author in one year on one subject collide. The convention already
   answers this (`Smith_2019a_…`), and `works.key`'s CHECK allows exactly `a` and `b` — so a fourth
   such work is refused as a collision and reported, never renamed into an unconventional key.
7. **Name-order disagreements are a named bucket, not a new matching rule.** A recurring class: the
   tracker says `Qin, H. et al.` and the registry's first author is `Hao`, because the record split
   the name the other way round. These rows are the same work, but `family_matches` — the comparator
   P2 admission uses — says the first author disagrees, so they take case B or C. P3 does not soften
   the rule; it records the registry's **whole author list** in the discrepancy's detail, so the
   review can see the swap. Adding a name-order rule is a P4-or-later decision for Kam.
8. **Journal is never a check-1 field.** A venue disagreement is recorded and is never a reason to
   withhold the claim: the database does not compare venue, so neither does the shape decision.
9. **The manifest diff joins on sha256.** Under referee note M7 the export's `stem` is the work key,
   so a stem-keyed join would read every row as one lost and one added. The bytes are the same on
   both sides; the stem is then a changed cell, and a structural one.
10. **The 30 works already in `litkb`** (`litkb-p2-gate`, `edge-pre1990`) are deduped against, not
    re-admitted — a tracker row carrying one of their DOIs is refused as `duplicate` and linked. They
    carry **no `tracker` identifier**, because there is no path to add an identifier to an already
    admitted work: `write_fact` refuses a new entity ("new facts enter only through admission"). Those
    links live in the candidates' `admitted_work_id` and in this report, not in `identifiers`.

## The convention, and the CLAUDE.md rule for Kam

`Scripts/docs/LITERATURE_CONVENTION.md` is rewritten in the same commit that made the tracker an
export, which is what design §10 asked for. It now says: the database is authoritative and the four
files are its printed view; never hand-edit them; the hunt protocol (open a workstream → admit →
acquire → record a use with a verified quote → promote prepare); and the `tracker_id` scheme, with
M7's rule that `works.key` is authoritative and a file's stem is derived from it.

**CLAUDE.md itself was NOT edited.** Design §9.1 puts the interim rule at P3 and the final one at P8,
and CLAUDE.md §3.1 says `main` is Kam's. The proposed interim rule, for Kam to merge into §2.1 / §3:

> **Literature.** A paper is admitted, acquired and cited through the literature knowledge base
> whenever it supports a claim in the project (`decisions.yaml` §15.17); ad-hoc reading is not
> governed by this rule. `Reports/literature_tracker.csv`,
> `Literature_Tracker.xlsx` and every `manifest.csv` are **generated exports** — never hand-edit them;
> run `py -3.12 -m litkb export tracker` / `export manifest`. Procedure and the hunt protocol:
> `Scripts/docs/LITERATURE_CONVENTION.md`.

And one roadmap row for §2.1:

> | **Any literature question — what we hold, what a paper was used for** | `py -3.12 -m litkb ...`; procedure in `Scripts/docs/LITERATURE_CONVENTION.md` |

It restates no procedure, because CLAUDE.md is "a ROADMAP and a RULEBOOK … deliberately NOT a facts
store" and a fact restated there rots.

## What blocks P3 acceptance

1. **No independent referee.** Every number here was produced by the author of the code (3.4c). A
   referee can re-run `qc/instruments/litkb_p3_diff.py` against the same workstream without re-running
   the load, and can re-run the load itself — it is idempotent and must report nothing new.
2. **`p3-migration` is left OPEN and unpromoted.** Nothing P3 loaded is in main's view. Kam decides
   promotion at merge; until then `litkb export` with no `--workstream` prints main's view, which is
   the 30 pre-P3 works only.
3. **The held rows are the open question for Kam**, not a defect: they are rows whose DOI confirms a
   work whose title, first author or year is not what the tracker says, with no file on disk to settle
   it. They need either a file (a P4/P5 hunt) or a row-by-row decision. `discrepancies` is that queue.
4. **The manual-admission proposals need a second session's approval** (§15.13, D-4), which decisions
   says is a separate session's job. None were approved here.
5. **Tracker IDs are now global identifiers.** `identifiers (scheme, value_norm)` is unique, so a
   tracker ID means one work across the whole knowledge base. Renumbering the tracker would break
   that; the convention now says so.

## Kills, guards and the harness

Every P3 guard is mutated by `qc/instruments/litkb_p2_mutations.py`, which runs the whole P2 + annas + P3
test set under each mutation. P3 adds rows P1a–P1e, P2a–P2b, P3b–P3c, P4a, P6a–P6h and P7a–P7h.

| §14 P3 kill | test | fires |
|---|---|---|
| a planted **duplicate DOI** row is rejected at load | `test_kill_a_planted_duplicate_doi_row_is_rejected_at_load` | one work, the second candidate `duplicate` and linked |
| the planted **Averkov wrong DOI** (`10.4171/JEMS/183`, ratio 0.36) with its real file | `test_kill_the_planted_averkov_wrong_doi_row_is_rejected_at_load` | refused at binding; no identifier written |
| a planted **disagreeing title** produces a discrepancy record | `test_kill_a_disagreeing_title_produces_a_discrepancy_record` | P1a removes the writer and the gate test fails |
| **with the discrepancy writer removed the GATE fails** | `test_kill_the_diff_gate_reports_an_unexplained_cell_when_the_discrepancy_is_missing` | the classifier returns UNEXPLAINED |
| **loading twice admits nothing new** | `test_kill_loading_twice_admits_nothing_new` | P3b / P3c each fire |

**The final run: 148 of 148 mutations fired, both baselines passed, 42.0 min over 4 workers**
(`--workers 4 --worker-dbs 1,2,8,9` — parallel worktrees share one Postgres server and another agent's
session held `litkb_test_w3/w5/w7`, so the harness now takes `--worker-dbs` and the copies stay numbered
1..N while only the database each is pointed at changes). `--sites` passes: 62 call sites, 59 covered by a
row, 3 equivalent.

**What the harness caught that review had not.** An earlier run on the same tree fired 145 of 149 and named
four rows. One was a design defect: `free_key` was a Python copy of a rule the DATABASE already owns (migration
0014, referee fix D5, retries a colliding key with the convention's `a`/`b` year suffix). The mutation that
removed the Python copy reported DID NOT FIRE — nothing depended on it. The copy is gone, and with it row P5a;
the collision test now exercises 0014's rule through the loader. Its assertion had also been reading keys a
previous run left in the shared test database, which is why it passed under the mutation at all.

The other three were untested guards, now asserted where each acts (P6e, P6f, P7d). An earlier run had
already named seven, one of which was a real defect: a NUL in a registry record's author list reached
`record_discrepancy`'s TEXT parameters, and Postgres refuses a NUL in a text column outright — one scanned
record would have ENDED the load rather than recorded the row.

## Ladder

`py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w6`, on the final tree: secrets, ruff and
compile pass; 2474 tests pass with **one** failure, `test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, which is the
known pre-existing one and is not litkb's. All 241 litkb Postgres tests pass.

Re-run on the post-referee tree (see "Fixes after referee"): **1 failed, 2480 passed, 5 skipped, 1 xfailed**
in 8m23s — the same one pre-existing failure, and **244** litkb Postgres tests. The whole mutation table,
parallel on `--worker-dbs 1,2,6,9`: **154/154 fired, baselines passed**, 45.3 min over 4 workers.

Two ladder findings were P3's own and are fixed: the gate instrument's `sys.path.insert` was outside the 3B
ledger (it has a line now, with its reason — litkb is not in the editable install), and the P1 role-privilege
matrix needed `record_discrepancy` on the writer's row, which is the matrix doing its job.

## What was NOT done, and why

- **No archive download.** P3 is a load, not a hunt: a row with no file on disk stays unbound.
- **No correction pass on the tracker** (decisions.yaml). Tracker rows 327 and 329 still read `2019a` and
  `2019b` in the YEAR column. The loader reads them leniently and records the difference — but at the time
  of the load only ONE of the two year parsers did (referee F4): `compare_row` carried a stricter `int()`,
  so `year_agrees` was unconditionally False for those two rows and they could never reach case A. Fixed
  below. Measured on `litkb`: 329 is `admitted` and 327 `rejected` at `binding-failed` — neither outcome was
  decided by the year, and both rows carry their `year` discrepancy (`2019a`/`2019b` against `2019`), so
  nothing loaded is wrong. What the second parser cost was the ROUTE: both went in on the file's binding
  (case B) where case A was open to them.
- **CLAUDE.md was not edited.** The proposed rule is above, for Kam's merge.
- **`p3-migration` is left OPEN and unpromoted**, and the live `Reports/literature_tracker.csv`,
  `Literature_Tracker.xlsx` and `Validation\manifest.csv` were NOT overwritten. The exports are written to
  `Reports/litkb_export/`, and swapping them for the live files is Kam's call at promotion.
- **The two sha256 collisions Stage 0 found need nothing from P3 today.** Its referee established that both
  files are a third paper, and both are already in `_quarantine`; measured just now, all 207 manifest rows
  have their PDF in `Validation\`, none has a stale sha256, and neither colliding sha256 is in the store. The
  two guards that would record such a row (`sha256_collision`, `file_missing`) are built and fire on planted
  inputs; on today's store they have nothing to flag, and that is reported rather than inferred.
- **The IMS/JSTOR scans** are `binding-pending`, waiting for OCR — 10 of them. The inventory re-measured them
  (title an image on page 1, no characters on page 2) and that is what §15.14 prescribes.

---

## Fixes after referee

`Reports/LITKB_P3_REFEREE_2026-09-15.md` accepted the load — every total reproduces, the 713 explained
cells were checked one by one, not sampled — and found the **gate** defective and four labels wrong.
Everything below is that repair. **No number in the database changed, and none was re-derived: the gate's
buckets after the fix are bucket-for-bucket what they were, and `phase4/qc/litkb_p3_diff.csv` regenerates
byte-identical.** What changed is what the gate would let through next time.

**F1 — the gate compares values now.** `explained` needed only a `discrepancies` record NAMING the cell; it
never compared the record's `registry_value` with what the export printed. The referee's Plant A — one cell
corrupted to `ZZZZ TOTALLY FABRICATED TITLE 12345` — came back `explained`, quoting a record about two other
strings, and the gate passed. 713 of 1086 cells were open that way. The test is DOI-aware through
`_same_doi` → `textnorm.normalize_doi`, the authority admission stores by, never a second copy of the rule:
the referee measured that normalised equality **alone** fails the gate on 19 real cells, where the export
prints `https://doi.org/10.x` for a record holding the bare `10.x`.

**F1b — the HELD branch is reachable.** The docstring says a changed cell on a held row is a BUG, and the
branch for it sat *after* the `hit` lookup. 91 of the 109 held rows carry discrepancy records, so for those
rows it could not fire (Plant C). It now sits above `explained`, `filled` and `format`. Held rows are also
keyed on the **manifest stem** as well as the tracker `ID`: `raw_record ->> 'ID'` alone left the 21
manifest-only held rows outside the guard entirely.

Re-run read-only against `litkb` (`litkb_reader`), workstream `p3-migration`:
**1086 changed cells — explained 713, format 243, structural 120, filled 10, UNEXPLAINED 0, GATE PASS**, and
`git diff` on the tracked CSV is empty. Both plants are now caught, each with its own test:
`test_kill_a_fabricated_cell_is_not_explained_by_a_record_about_another_value` (Plant A, and it asserts the
cell carries no ratio), `test_kill_a_changed_cell_on_a_held_row_is_a_bug_even_when_a_record_names_it`
(Plant C, over both a fabricated value AND the registry value, plus a format-only difference), and
`test_the_value_test_reads_a_doi_url_and_the_records_bare_doi_as_one_doi` — which exists because the
referee's own first draft of this fix broke the gate on those 19 cells and was caught only by measuring it.

**F3 — the refusal label.** "admissions refused at check 1 or check 4 — 45" was wrong about the reason, not
the count: all 45 passed check 1 and were refused at **check 2**, as 43 `duplicate` and 2 `duplicate-review`.
The table above says so now.

**F4 — one year parser.** `plan.compare_row` carried a second, stricter `int(str(...))` in a `try/except`
where the loader everywhere else calls `export_shape.year_int`. `2019a` therefore read as 2019 in the loader
and as `None` in the comparison, making `year_agrees` unconditionally False for tracker 327 and 329 —
silently, and with §15.15's ±1 rule unreachable for them. `compare_row` calls `year_int` now. (The third
parser, `resolver._year_int`, is NOT this rule: it reads a registry candidate's year, not a legacy cell, and
is left alone.)

**F6 / F9 — migration `0016_held_reason.sql`.** Two review-queue gaps, one migration:

* `litkb.hold_candidate(workstream, token, candidate, reason)` — a held candidate's `state_reason` was NULL
  on all 68, so why a row was held had to be inferred from the absence of an admission. `candidates` carries
  `workstream_id` and is a guarded relation (0011: state and state_reason "are set by admission (P2), not by
  the lead"), and a held row is the one candidate state admission never reaches — so it needs its own
  token-checked SECURITY DEFINER writer, shaped like `record_discrepancy` and deliberately narrower: it may
  write only an unadmitted `new` candidate of the workstream whose token it holds. The loader passes
  `run.HELD_REASONS`, which names the case the case table decided (case C or case E) in that table's words.
* `_check_binding` is re-created so a `binding-pending` verdict carries the evidence it waited on — `ratio`,
  `page`, `page1_chars`, `text_layer`, `best_any_ratio`. Before, every one of the 10 read
  `{'verdict': 'binding-pending', 'reasons': [...]}` while `binding-failed` carried its ratio, so P4's OCR
  queue could not tell a JSTOR cover sheet (≈140 characters on page 1) from a file with no page-1 text at
  all. **The verdict logic is copied through unchanged**; only the evidence beside it is added.

**The migration decision: 0016 is applied to `litkb_test` and the worker databases, NOT to `litkb`.** The
brief holds `litkb` READ-ONLY and that is not a rule to reason around: this session opened it as
`litkb_reader` throughout, and a schema change is a write whether or not it is additive. `litkb` takes 0016
at its next accepted write, and `py -3.12 -m litkb.db.migrate --db litkb` is the whole of it — 0016 is
additive (one new function, one `CREATE OR REPLACE`) and the runner is idempotent. **Note what it will and
will not do there:** the new `_check_binding` applies to every admission *from then on*, but the 68 held rows
and the 10 pending bindings already in `litkb` keep their NULL reason and their bare verdict until those rows
are loaded again. Backfilling them is not free — the reason is a function of the registry record, so it means
re-planning the row — and it belongs to P4, with the OCR pass that will revisit those files anyway.

**F7 — the convention.** The `manifest.csv` section still read "The manifest is authoritative"; the P3
rewrite had replaced the *xlsx* authority line and left this one, so the file named two authorities. The
section now says what the manifest is: a generated export of the database, and the join key from a row to the
bytes on disk.

**F8 — the proposed CLAUDE.md rule, narrowed to Kam's scope.** The draft's "not fetched ad hoc" made every
*fetch* subject to the rule, which is an acquisition policy; §15.17's reach is "uses that support a claim in
the project". The text above now reads: a paper is admitted, acquired and cited through the knowledge base
**whenever it supports a claim in the project**, and ad-hoc reading is not governed. The acquisition rules
stay where they are, in the convention. CLAUDE.md is still not edited — `main` is Kam's.

**Harness.** Six new rows, each measured FIRED on `--worker-dbs 1,2,6,9`: **P8a** the gate's value test,
**P8b** its DOI clause (the referee's failed first draft, as a permanent row), **P8c** the HELD branch
shadowed again, **P8d** two year parsers again, **P8e** a held candidate with no reason, **P8f** a pending
binding with no evidence. P8f is worth a line on its own: written the obvious way — the evidence built
directly into the returned `jsonb_build_object` — removing the guard left a trailing comma, and the harness
reported **DID NOT FIRE** because 105 tests ERRORED on a syntax error instead of failing on the behaviour.
The function now merges the evidence onto the verdict, so a mutation there changes the evidence and nothing
else. A guard whose mutation fires for the wrong reason is not a tested guard (CLAUDE.md 3.4c).
Rows **A5, A6, C11 and R2** move from 0014 to 0016: 0016 `CREATE OR REPLACE`s `_check_binding`, so 0014's
copy is dead text and a mutation in it would be overwritten before the tests ran.

**Not fixed, and named rather than left to be found.** F5 — 15 `doi` discrepancies record
`claimed_value = NULL` where the tracker cell actually said `https://arxiv.org/abs/…` or
`N/A — J. Arboriculture 20(2), no DOI`; `doi_discrepancy` is handed the parsed DOI, not the raw cell, so what
the row *said* survives only in `raw_record`. And the referee's P4 decision for Kam: **303/60 is a preprint
and its journal version**, two distinct DOIs and therefore two works under the rules as written, with no
`version-of` relation in the database to express the tracker's human "same paper" judgement — which survives
only as a `duplicate_of` discrepancy. Judgement call 3's "the database already has one" holds for identical
DOIs only.

## P4 adapters merged

2026-09-15: the three refereed P4 adapter branches (stage 0 inventory, stage 2 GROBID, stage 3
Docling) were merged onto this branch, and **migration 0016 was applied to `litkb`** — the write this
report deliberately left pending. The P3 gate was re-run read-only afterwards and is unchanged:
**1,086 changed cells — explained 713, format 243, structural 120, filled 10, UNEXPLAINED 0, GATE
PASS**, with `phase4/qc/litkb_p3_diff.csv` regenerating byte-identical. The full parallel mutation
harness on `--worker-dbs 1,2,6,9` fired **155/155** rows with baselines passing. Details, the merge
commits, the conflicts and the gates that remain: **`Reports/LITKB_P4_MERGE_2026-09-15.md`**.

One correction to this report's own text: `qc/instruments/litkb_p3_diff.py --workstream` takes the
workstream **UUID** (`01a0a494-bb54-7c1b-be26-db0c229a9534`), not the slug `p3-migration`.

## First-use friction closed

2026-09-15. `Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md` §8 is a defect list measured on the first
session that tried to follow `Scripts/docs/LITERATURE_CONVENTION.md` end to end;
`Reports/LITKB_P8_REFEREE_2026-09-15.md` §4 classified each item. This section is what closed, what
was shown to fire, and what was deliberately left to Kam.

**One migration, `0020_first_use_friction.sql`**, applied to the worker test databases and to
**`litkb`**. Additive: nothing dropped, three CHECKs widened, two functions replaced whole
(`_check_registry`, `clear_extraction_rows`), one replaced in place (`_feeds_token_ok`).

### The items

**1. Step 4 has a CLI (§8.1).** `litkb use add --key K --statement S --kind K [--feeds "…"]
[--quote Q --page N]`, plus `use list`. It writes through the same token-checked `write_proposal` and
`add_evidence` the reviewer had to reach by copying the P3 loader, and it refuses outside a worktree
holding a workstream. Mechanism: `Scripts/pipeline/litkb/use.py`.

**2. The feeds vocabulary is the documented one (§8.6).** `_feeds_token_ok` accepted three of the
convention's seven forms, so a use that fed a REPORT could carry no valid token and all 15 uses of
that session were written with an empty `feeds` array — "the KB records that these works were used
and does not record what they were used *for*". 0020 widens it to all seven.
`work/20260915-access-layer` had **not** patched the validator — checked with `git grep
_feeds_token_ok` on that branch, whose only hits are reports and the unchanged 0005/0013 text — so it
was fixed here. `use add` asks the DATABASE whether a token is valid before writing, so a mistyped one
is a refusal at the command instead of a chain held at prepare.

**3. A quote is anchored, or the use is refused (§8.3).** `use add --quote` locates the quote in a
block of the file's CURRENT extraction run and `add_evidence` lets the 0007 trigger compute
`quote_verified`. If no block carries it the command REFUSES and says why — it does not fall back to
`rationale`, because a quote in free text is exactly the unverifiable record §8.3 is about. A use
with no quote is still writable, and says in its output that it carries none.

**4. `admit --doi` alone works (§8.5).** Check 1's rule is about a CLAIM, and the claim check is
untouched: a claimed first author that contradicts the registry is still refused, which is the catch
that found the reviewer's own Papadakis-for-Mandilaras error. What was missing is the case where the
admitter claims nothing and takes the registry record as the identity. That is now declared, once, on
the identifier's own evidence (`registry_only`), so a registry-only admission is auditable as such
afterwards — and an admission that claims nothing and does not declare it is refused exactly as
before.

**5. Title + subtitle at admission (P4).** `registry.work_title()` joins the registry's title with its
subtitle, and the work is stored — and keyed — under that form. `parse_crossref` already built the
joined form into `titles`, so nothing about MATCHING changes; check 1's "the work is the registry
record" guard now accepts any form the registry published, and `binding.bind_any()` tries every form
against the first page so a PDF printing only the bare title still binds (recording which form
matched, while `binding.registry_title` stays the work's title, which is what check 3 compares
against). A claim that names the work but not its subtitle is admitted and kept as a **discrepancy**,
under the new `discrepancies.source = 'admission'`.

**The Konda 2016 live row was NOT edited.** `10.14778/2994509.2994535` is in `litkb` as
`Konda_2016_magellan-work`, title "Magellan". The fix path is a new version through the workstream
that admitted it — `litkb.write_fact('work', <work_id>, <its current version_id>, <fields carrying
the joined title>, '<change reason>', ws, token, agent, session)` — the only path that keeps the
version history and the only one a second session can review. `works.key` is set when the work row is
created and no later version can change it, so the truncated KEY stays and the stored TITLE changes;
that asymmetry is the argument for doing it as a reviewed version rather than an `UPDATE`. Every work
admitted from here takes the joined form, and `migrate_legacy._key_for` now derives its key from it
as well — so a re-run of the P3 load would mint different keys for subtitled works. Keys already in
`litkb` are untouched.

**6. Documentation can be admitted (§8.4).** `admit --web --url U --retrieved DATE --snapshot
PAGE.txt` admits a source with no DOI from the admitter's saved TEXT of the page. The snapshot lands
under `_litkb_staging/web/` through the store's one guarded write; binding runs against it with the
same binder, the same 0.85 and the same author-near-title rule; and the URL, retrieval date and
snapshot go to `source_url`, `obtained_at` and `txt_extract_path` — columns that already existed.
Only the KIND had no home, so `file_versions.copy_kind` gains `'web snapshot'`. Nothing in the
database was relaxed to take it, and it stays a manual PROPOSAL that a second session must approve.

**7. Failed downloads are quarantined (§8.9)** and **the corpus census is frozen** — the two sections
below.

**8. Stage 6 has somewhere to land.** `Reports/LITKB_P4_MERGE_2026-09-15.md` recorded that stage 6
parks its rows as JSONL with no loader and nowhere to put two of the three. 0020 gives `"references"`
its stage-6 columns and an `ambiguous` resolution state, relaxes `citation_mentions` from
block-anchored to locatable-by-page, adds `citation_edges`, and adds four `litkb_ingest`-only writers
plus a trigger that holds the resolution rule on the direct-INSERT path as well.
`litkb.extract.references_ingest` is the loader.

**Measured on `litkb`** (second run adds nothing): **643 references, 969 citation mentions, 13
citation edges, 630 citation candidates, 17 stage-6 extraction runs**; resolutions **363 resolved /
19 ambiguous / 261 unresolved**, `resolved_work_id` set on 17. On `litkb_test_w9`, where every stem's
work and file exist as fixtures, the same run loads the whole parked corpus: **658 / 981 / 13 / 645**
over 18 papers.

**Why `litkb` is lower than the parked corpus, and it is not a loader bug.** The P6 JSONL's
`citing_work_key` is a FILE STEM, not a `works.key`: only 10 of the 18 stems exist as a key, while 17
of them reach a held file by the stem of `main_files.rel_path` (e.g. stem
`Benedek_2015_multilayer-markov-random-field-models` is held under key
`Benedek_2015_multilayer-markov-random-field`, the slug truncated to four words). The loader resolves
by file-stem first and falls back to `works.key`, and records which route matched — all 17 resolved by
stem. The eighteenth, `Chrisman_1982_theory-cartographic-error-measurement` (15 references), is
REFUSED and named: its `works.key` exists but holds no active file, and a reference must name the
file it was parsed from.

**The mention count adds up exactly, and it is worth writing out because the parked file's headline
number is 1,386.** Those are bounding-box rows; a MENTION is one `<ref>` ELEMENT, of which there are
**1,182** (`box_index == 0`, the rule `references.mention_totals` already uses). Of those, **201**
are elements GROBID linked to no `biblStruct` — counted and skipped rather than guessed at — and
**24** belong to Chrisman, the refused paper. 1,182 − 201 − (24 − 12 of Chrisman's that were already
counted as untargeted) = **969** on `litkb`, and 1,182 − 201 = **981** on `litkb_test_w9`, where
Chrisman's file exists as a fixture. Nothing is unaccounted for.

**9. Report defects, named not fixed.** `Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md` §8.4 says six
sources "are cited in §2, §5 and §6 with URL and retrieval date". Measured on that file: it contains
**four** URLs in total — two Crossref documentation pages and two Splink pages — and **no OpenAlex
URL at all**; §2's OpenAlex passage cites arXiv:2205.01833 instead. The sentence overstates what the
report carries. Left alone: that report belongs to `work/20260915-linkage-review`.

### A failed download is quarantined, never deleted (§8.9)

The reviewer's own account: a `curl` for the IFLA PDF followed a repository link that returned an
HTML error page, 295,657 bytes of it were written as
`_litkb_staging\incoming\IFLA_2017_library-reference-model.pdf`, and he removed it with `rm -f`
before re-fetching. Twenty seconds old and his own — and still a delete inside the tree that exists
because 149 PDFs were lost on 2026-09-12. His words: *a rule with an "it was only my own file"
exception is not a rule.* The machinery now makes the delete unnecessary: the routes hand their
rejected bytes back instead of discarding them, `acquire()` lands them under `_quarantine/` through
the store's guarded write path, and a reason sidecar records the status, the redacted source URL, the
sha256, the byte count and the work key. HTML-served-as-PDF and a truncated PDF (header present,
`%%EOF` absent) are detected separately. The DB status stays `bad-file` for both — migration 0013
enumerates the `acquisition_attempts` status vocabulary and this branch did not widen it — and the
SHAPE (`not-a-pdf` / `truncated-pdf`) is carried in the filename label and the reason file, which is
the same shape `annas._quarantine`'s `content-mismatch` label already had.

**Run against the real store, read-only apart from copies.** 32 files sit in
`_litkb_staging/incoming` today; the detector agrees with `pdfinfo` on **32 of 32**, and **10 are not
a usable PDF — all HTML, none truncated**. All ten were quarantined byte-for-byte with their reason
files and every original's sha256 is unchanged. One reason file, verbatim: `{"status":"bad-file",
"label":"bad-file","shape":"not-a-pdf","reason":"the 486110 bytes served do not begin with %PDF-;
they look like HTML","route":"open_access","source_url":"…","sha256":"2bc02d5b…","bytes":486110,
"work_key":"AllenMatthew_2026_manual-labelling","at":"2026-09-16T04:01:23…+00:00"}`.

Two defects found live by other sessions while this was being built, and fixed here:

* **`acquire --from-file` deduplicated a file against ITSELF.** `acquire()` computes
  `store.disk_index()` before the from-file branch and that index hashes every `*.pdf` under the
  root, staging included — so a handed-in path already sitting in `_litkb_staging/incoming` matched
  its own hash, returned `duplicate-held`, and binding never ran. A live agent had worked around it
  by renaming the file to `.download`, which is exactly how a workaround becomes folklore.
* **Quarantine locked a file out permanently.** The same disk index hashes `_quarantine/`, so once a
  file was quarantined its bytes read as "already held" and the SAME correct file could never bind
  after its record was corrected. `Konda_2016`, `Kopcke_2010` and `Enamorado_2019` were locked that
  way in the live store.

**A third guard, added because the scan is only a gate while its file list is complete.** The
no-delete source scan reads `litkb/acquire/*.py` and `litkb/admit/*.py`; a module that reached the
store from anywhere else would simply not be read. `test_litkb_p2.py` now carries a CENSUS: any
module under `Scripts/pipeline/litkb/` that imports `Store`, `LITERATURE_ROOT`, `STAGING` or
`QUARANTINE`, or names a store directory in a string that is not a docstring, must be inside the
scan's globs or listed in `_STORE_READ_ONLY` with a reason (today: `migrate_legacy/sources.py`,
which builds READ paths only). It is a new way for unrelated work to fail `test_litkb_p2.py`, and
that is the point.

**A harness defect, found by running into it.** `litkb_p2_mutations.py` has no cross-process lock:
`main()` pre-flights every row's target against the file AS IT IS ON DISK, so a second campaign
started while a mutant is applied dies with "mutation target occurs 0 times" on a row that is
perfectly sound — and the `--workers` path is worse, because it `copytree`s the tree as it is and a
mutant applied at that instant is inherited silently into every worker copy, making every verdict
from that copy suspect. An exclusive lock file taken at the top of `main()`, before the pre-flight,
closes it: pid and start time written in, the refusal quoting the holder's line, workers exempt
because they run inside their own copies. It refused a live second campaign in this session with
that message, which is the gate shown firing rather than only tested. No mutation row removes it, on
purpose — the test that proves it runs `main()` in a subprocess, so a mutant that dropped the lock
would turn that test into a real nested campaign mutating the tree from inside a test.

### The corpus census is frozen (a P4 merge finding, not a §8 item)

`Reports/LITKB_P4_MERGE_2026-09-15.md` recorded two `qc/test_litkb_inventory.py` failures that the
merge did not cause and deliberately did not re-pin: the census tests walked the literature root, and
the corpus had grown from the 224 files their five numbers were measured over to 246. They now read
`phase4/qc/litkb_inventory_census.sha256` — 241 rows, `<sha256>  <relpath>`, DERIVED from the tracked
`litkb_inventory.csv` rather than from a fresh walk, because re-walking is the bug — and measure
exactly those files. A census file that is MISSING or whose bytes changed fails loudly and by name:
that is a deletion detector, and it is deliberate. Corpus growth no longer touches a pinned number.

`litkb inventory --new` reports what the census does not pin. Against the live corpus: **28 outside
the census — 25 in `_litkb_staging/filed`, 1 in `incoming`, 2 in `_quarantine`; 0 renamed, 0 changed,
0 missing.** All 22 PDFs the P4 merge measured appear (the merge's "22 in `filed`" was 21 in `filed`
plus 1 in `incoming`), and four more landed mid-session — the live corpus moving under the
measurement, which is the defect restated. **Before anyone quotes a new active total:** 13 of the 28
are ~1.6 KB — Higham ×5, Lisca ×4, Averkov ×4, the numbered `.2`–`.5` duplicates — almost certainly
failed downloads saved as `.pdf` rather than papers, which is the same class §8.9 is about. Real new
documents: 15.

**Re-pin debt, in the open.** `test_the_boundary_pins_really_are_the_nearest_pages` now asserts
nearest-ness WITHIN the census. `Massari_2023_opencitations-meta.pdf` p13 is already on disk and
already nearer the `CHARS_TRACE` threshold than the pinned Reynolds_2000 p14, so the pins are owed a
re-render at the next re-freeze. It is in the test's docstring, but a green test hides it.

### The ladder, on this tree

`py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w6`: secrets, ruff and compile pass;
**1 failed, 2904 passed, 22 skipped, 2 xfailed** in 10m38s, and the one failure is
`test_experiments.py::test_pointer_paths_resolve[crown_state_model]` — the known pre-existing one, not
litkb's. **339 litkb Postgres tests pass**, against 244 at the post-referee run above.

The whole mutation table, parallel on `--worker-dbs 1,6,9`: **253/253 fired, baselines passed**, 72.8 min
over three workers (85 + 84 + 84 rows). `--sites`: **78 call sites, 75 covered by a row, 3 equivalent;
18 sinks, 2 redacted, 16 allowed**, no PROBLEM.

**Two defects were found by running the gates, and both were in the gates.**

*The worker copy's domain was smaller than the tests' read domain.* The first full run of the table
reported `253/253 fired; baselines FAILED` after 133.6 minutes, and the failing baseline was worker 1's
`qc/test_litkb_inventory.py`: **1 failed, 39 passed, 24 errors**. The cause was this session's own census
freeze. `make_worker_copy()` copies `Scripts/` and `Reports/`; the census tests read
`phase4/qc/litkb_inventory_census.sha256` and `phase4/qc/litkb_inventory.csv` through
`inventory.repo_root()`, which resolves relative to the package — so inside a worker copy it resolved
under the COPY, where `phase4/` does not exist, and every corpus-backed test errored on a missing file.
The E3inv row still printed FIRED, because its own test failed for its own reason: **a broken baseline
does not show up in a row's verdict**, which is the whole reason a baseline is run at all. Both files are
now on `COPY_FILES`, which `tree_manifest()` hashes, so the stale-copy guard's domain still equals the
copy's, and `make_worker_copy()` creates the parent directory. That baseline now reads **64 passed,
1 xfailed**. `test_worker_copy_is_a_standalone_checkout` asserts the census file reaches the copy, so the
next tracked input that moves out of `COPY_DIRS` is caught by a 70-second test instead of a 133-minute
table. It is the same class as the harness lock above — the instrument describing a tree that is not the
tree under test — and it is the second one this session.

*A new test was green only because of how it was being run.*
`test_new_files_needs_no_database_and_writes_nothing` launches the `--new` reporting path as a subprocess
and checks that its import graph reaches no database driver. The subprocess inherited no `PYTHONPATH`, so
the test passed under `PYTHONPATH=pipeline py -3.12 -m pytest` — how every litkb suite in this session was
run, and how the worker copies run — and failed under `qc/check.py`, which sets none, with
`ModuleNotFoundError: No module named 'litkb'`. litkb is not in the editable install; every other litkb
test that spawns a subprocess passes `PYTHONPATH` explicitly and this one now does too. It is the argument
for running the ladder whole, in its own environment, rather than module by module in the shell the work
was done in.

Both fixes touched test files after the table had run, so **E3inv was re-run alone against the final
`qc/test_litkb_inventory.py`** — FIRED, baselines passed, `litkb_test_w6` — and no row's verdict here
rests on a file that changed after its verdict was taken.

### What was NOT decided here

* **§8.2** — "A use with no verifiable quote is refused at prepare" is false as written, confirmed on
  both legs (the review's reading of `_ws_chains`, and the P8 referee running it). The two coherent
  fixes are in that referee's §4.2 and the choice is Kam's. `LITERATURE_CONVENTION.md` now says so in
  place of the false sentence, and `use add` writes a quoteless use and reports that it carries none.
* **§8.7** (the open-access route's 16 misses) and **§8.8** (Anna's Archive unused) were out of scope.

### Coordination, for whoever merges next

* **`0018` and `0019` are RESERVED** for `work/20260915-access-layer` in
  `Scripts/pipeline/litkb/db/migrations/_reserved.txt`, because that branch is writing them and 0020
  had to be numbered past them. `litkb.db.migrate.discover()` now allows a DECLARED gap and refuses
  every other one — `test_an_undeclared_gap_in_the_migration_numbering_is_still_refused` is the proof.
  **Delete those two lines in the merge that lands the files**:
  `test_migration_files_are_named_and_numbered` asserts that a number on disk is not also reserved,
  so it fails until they go. That relaxation of a P1-refereed runner rule is the one change here made
  for a reason outside the friction list, and it is written down rather than assumed: the gap-free
  rule catches a migration that went MISSING, it cannot tell that from a number another open branch
  is about to take, and a branch that cannot run its own migrations until an unrelated branch merges
  is a branch that renumbers under pressure and collides.
* **`Reports/gold/p8_gold_2026-09-15.json`'s P2 prediction is now STALE**: "the skill's step-4 feeds
  token `report <FILE>#§<loc>` is NOT accepted by `litkb._feeds_token_ok`". It was true when it was
  frozen and it is false on purpose from 0020 on.
* **A1–A4, A3b and R59 in `qc/instruments/litkb_p2_mutations.py` were repointed to 0020**, which
  `CREATE OR REPLACE`s `_check_registry` and `clear_extraction_rows`: their 0013 and 0017 bodies are
  dead text, and a row left on them would report DID NOT FIRE for a reason about migration order
  rather than about the guard. Same trap as the 0014→0016 `_check_binding` move; the comment above
  `MIG20` now names it as a class instead of a second special case.
* **`_feeds_token_ok` is now defined TWICE, and the schema it produces depends on apply order.** When
  the feeds fix was scoped here, `work/20260915-access-layer` had not patched the validator
  (`git grep _feeds_token_ok` on that branch returned only reports and the unchanged 0005/0013 text).
  It has since: its `0018_access_layer.sql` `CREATE OR REPLACE`s the function to the same seven
  forms, for the same reason. **The two definitions are not equivalent** — 0018 allows `framework
  §N[.N]` at most one sub-level, matching the convention's depth note, while 0020 allows any depth —
  and, worse, **which one a database ends up with depends on the ORDER the migrations were applied,
  not on their numbers**: `litkb` already has 0020, so 0018 will run after it and 0018's body wins
  there, while a database built from scratch runs 0018 then 0020 and gets 0020's. That is a schema
  that differs between two servers with the same migration set, which is the thing the runner exists
  to prevent. **Two ways to settle it, and the choice is Kam's, not this branch's:** (a) drop the
  `_feeds_token_ok` section from `0018_access_layer.sql` while that branch is still unmerged and
  unapplied — an edit that is legal only until 0018 is applied somewhere, whereas 0020 is applied and
  checksum-locked and cannot be edited at all; or (b) a new migration after both that states the
  definition once, which is the only option left once 0018 has been applied anywhere. Whichever it
  is, the depth question (`framework §N` at any depth, or at most one sub-level) is a convention
  question and the convention's own table says one sub-level.

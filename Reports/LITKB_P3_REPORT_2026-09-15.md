# litkb P3 — Migration + exports, 2026-09-15

Branch `work/20260913-literature-kb`, worktree `D:\edmonds-pipeline\treedata-litkb`.
Design: `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §4.6, §9.1, §10, §13, §14 P3 row.
Decisions: `Scripts/decisions.yaml` `litkb-p0-foundation`, "P3 load (Kam, 2026-09-14)".

**Status of this evidence (CLAUDE.md 3.4c):** every number below was produced by the author of
the code. No independent referee has re-run the loaders, the gate or the mutations. The gate is
an instrument whose output is a tracked CSV, so a referee can re-run it without re-running the
load; the load itself is idempotent, so a referee can re-run that too and must see nothing new.


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
| — **held**: recorded, flagged, not admitted | **68** |
| admissions refused at binding — **binding-pending, waiting for OCR** | **10** |
| admissions refused at binding — binding-failed | 29 |
| admissions refused at check 1 or check 4 | 45 |
| `tracker` identifiers written | 346 |
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

> **Literature.** Any paper the project relies on is admitted, acquired and cited through the
> literature knowledge base, not fetched ad hoc. `Reports/literature_tracker.csv`,
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

Two ladder findings were P3's own and are fixed: the gate instrument's `sys.path.insert` was outside the 3B
ledger (it has a line now, with its reason — litkb is not in the editable install), and the P1 role-privilege
matrix needed `record_discrepancy` on the writer's row, which is the matrix doing its job.

## What was NOT done, and why

- **No archive download.** P3 is a load, not a hunt: a row with no file on disk stays unbound.
- **No correction pass on the tracker** (decisions.yaml). Tracker rows 327 and 329 still read `2019a` and
  `2019b` in the YEAR column; the loader reads them leniently and records the difference.
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

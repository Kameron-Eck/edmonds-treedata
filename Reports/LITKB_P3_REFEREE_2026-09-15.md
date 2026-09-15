# litkb P3 referee — Migration + exports, 2026-09-15

Independent re-run per CLAUDE.md 3.4c. Worktree `D:\edmonds-pipeline\treedata-litkb`, branch
`work/20260913-literature-kb`, HEAD `eb9d8b1`, range `63c9b59..eb9d8b1`. `litkb` opened READ-ONLY
(`litkb_reader`) throughout; every mutation ran on `litkb_test_w1`. The referee wrote no code into
the branch: the three referee kills were run from a scratch test file and deleted.

**Verdict: P3 ACCEPTED WITH FIXES.** Every total reproduces exactly. The load is clean — checked
cell by cell, not sampled. The **gate is defective**: its `explained` bucket never compares the
exported value with the record that is supposed to explain it, and a planted fabrication passes.
That is a gate fix, not a load fix; nothing P3 loaded is wrong.

---

## 1. Totals — reproduced

Workstream `01a0a494-bb54-7c1b-be26-db0c229a9534` (`p3-migration`, open), read as `litkb_reader`.

| quantity | report | measured | |
|---|---|---|---|
| works created in the workstream | 348 | 348 | ✔ |
| registry admissions `admitted` | 336 | 336 | ✔ |
| manual admissions `proposed` | 12 | 12 | ✔ |
| candidates admitted / duplicate / duplicate-review / rejected / new | 348/43/2/39/68 | same | ✔ |
| files bound in place | 169 | 169 (`binding->>'verdict' = 'bound'`, all `active`) | ✔ |
| identifiers `tracker` / `doi` / `legacy_stem` | 346 / — / 169 | 346 / 336 / 169 | ✔ |
| use versions (`context`/`proposed`) | 370 | 370 | ✔ |
| discrepancies, and all 13 field rows | 909 | 909, every field count identical | ✔ |
| binding-pending / binding-failed | 10 / 29 | 10 / 29 | ✔ |

`phase4/qc/litkb_p3_diff.csv` regenerates **byte-identical** to the tracked file (1086 cells;
explained 713, format 243, structural 120, filled 10, UNEXPLAINED 0), and every per-field row of
the report's table matches. The two committed baselines are byte-identical to the live
`Reports/literature_tracker.csv` and `Literture\Validation\manifest.csv` — the exports did not
overwrite the files the gate measures against, as claimed.

**One label is wrong.** The report's fourth refusal row reads "admissions refused at check 1 or
check 4 — 45". Measured, all 45 **passed check 1** and were refused at **check 2**: 43 `duplicate`,
2 `duplicate-review`. Only 4 of the 84 refusals failed check 1 at all (and those failed binding
too). The count is right; the reason named is not. *Fix: relabel the row.*

Independently re-measured (not read from the report): all 207 manifest rows have their PDF in
`Validation\`, and all 207 sha256s match the bytes on disk today — 0 missing, 0 stale.

## 2. Spot check — 25 works

**14 bound works, seeded** (`random.Random(20260915)` over the 169 bound file versions). For each:
stored title/first author/year from `work_versions`; sha256 recomputed from the file on disk against
both `litkb.files` and the manifest row; page-1 text extracted by the referee with `pypdf`, not read
from the stored `binding.matched`. **14/14 correct**, sha256 agreeing with both DB and manifest in
every case. One (`Truccolo_2005`) scored 0.57 on my crude per-line title match; hand-reading page 1
shows the full title present, wrapped across four reversed lines — a limitation of my probe, not of
the binding.

**5 works with title discrepancies** (the five lowest ratios, 0.60–0.72: Blakemore 1984, Leung 2004,
Zhou 2020, Yuan 2015, O'Neil-Dunne 2014). In all five the stored title equals the registry value
exactly and the tracker's claim is a shortened or truncated form. Identity came from the registry, as
the decision requires.

**3 held rows** (tracker 2, 7, 10, state `new`): candidate present with the row's own title/year, no
work, no admission. Correct — but see §5, F6.

**3 binding-pending**: `Anderson_1957`, `Hudson_1978`, `Politis_1994`. Re-extracted: page 1 carries
140–160 characters (the JSTOR cover boilerplate) and **page 2 carries zero** — image scans. Exactly
the IMS/JSTOR class §15.14 routes to OCR. All 10 pending rows are that class.

**The two wrong-paper sha256s** (`bb14fdbc…` = Mufti 2011, `3a65f982…` = Wang 2020): **moot, and the
report is right to say so.** Neither prefix appears in any of the 207 manifest rows, and
`litkb.files` holds no file with either hash — all six colliding files are in `_quarantine`, outside
the manifest. There is nothing for P3 to leave UNBOUND with a sha256 discrepancy. (One quarantined
*stem*, `Song_2026_monocular-…`, does have a manifest row — its `Validation\` copy is a different,
correct file; verified by hash.)

**Page 1954** — one work `Page_1954_continuous-inspection-schemes`, **two active `doi` identifiers**
(`10.2307/2333009`, `10.1093/biomet/41.1-2.100`). Correct: two DOIs, one work. This is also why
`identifiers(doi)` is 366 against 348 works.

**`Duplicate of` pairs.** 264→13 and 199→94: one work each, the second candidate `duplicate` with
`admitted_work_id` pointing at the first — as designed. Two more are worth Kam's eye: 50→3 is HELD
(no link, because row 50 was never admitted), and **303→60 is two separate works** —
`Valavi_2018_blockcv-…` holds the bioRxiv DOI `10.1101/357798`, `Valavi_2018_block-cv-…` the journal
DOI `10.1111/2041-210x.13107`. That is correct under the rules as written (distinct DOIs are distinct
works) but it means the tracker's human "same paper" judgement survives only as a `duplicate_of`
discrepancy: **the database has no preprint/version-of relation**. Judgement call 3's claim that "the
database already has one [duplicate mechanism]" holds only for identical DOIs. Not a P3 defect;
a P4 decision for Kam, and it should be said in the report rather than left to be discovered.

## 3. Gate reproduction, and breaking it

Re-ran `qc/instruments/litkb_p3_diff.py` myself: 0 UNEXPLAINED, GATE PASS, output identical to the
tracked CSV.

**I did not sample 30 — I checked all 713.** For every `explained` cell, is the exported value
actually the `registry_value` of the record that explains it?

- 694 match exactly under `norm_cell`.
- 19 differ, all `DOI/URL`: the record stores `10.1109/tpami.2025.3649001`, the export prints
  `https://doi.org/10.1109/…`. Under `_same_doi` (the same `textnorm.normalize_doi` admission stores
  by) **all 19 are the same DOI**. Zero real mismatches.
- The 10 `filled` cells are all manifest `venue`/`doi` where the legacy cell was empty; each value is
  the admitted work's registry value.

**So the load is clean. The classifier is not.**

**Plant A — the break.** Corrupt an exported cell that *has* a discrepancy record, to a string with
no relation to either value (tracker row 8 `Title` → `ZZZZ TOTALLY FABRICATED TITLE 12345`). The gate
returns **`explained`**, quoting a record about a different pair of strings. `compare()` looks up
`hit = explained.get((source, row, field))` and uses it only for the bucket name and the ratio; it
never compares `hit[1]` with `b`. Any value at all passes in 713 of 1086 cells.

**Plant B — the builder's stated kill does fire.** Corrupt a cell with no record: `UNEXPLAINED`, "no
discrepancy record names this cell". That is the property `test_kill_the_diff_gate_reports_an_
unexplained_cell_when_the_discrepancy_is_missing` asserts, and it is genuinely asserted — but it is
the *weaker* half of the claim the gate makes in its own docstring.

**Plant C — a second, shadowed branch.** The docstring says a changed cell on a HELD row "is a BUG",
and there is a branch for it. It sits *after* the `hit` test. 91 of the 109 held rows carry
discrepancy records, so for those rows the BUG branch cannot be reached: corrupting a held row's
`Title` returns `explained`. Per 3.4c, a gate branch that cannot fire is not a gate.

**F1 (fix before P3 is closed).** One line, in `compare()`:

```python
elif hit and norm_cell(hit[1] or "") == norm_cell(b):
```

…with the DOI case already handled above it, and the `held` test moved ahead of `hit`. Then re-run
the instrument and re-commit `phase4/qc/litkb_p3_diff.csv`. The measurement in this section says the
count will not change — which is the point: the fix costs nothing and closes the hole.

## 4. Kills

`qc/test_litkb_p1.py + p2 + p3` on `litkb_test_w1`: **342 passed, 2 skipped, 1 xfailed** (232 Postgres
tests), including all five named P3 kills — planted duplicate DOI, the Averkov wrong DOI, the
disagreeing title, the missing-writer gate failure, and idempotence.

Three kills of my own, written by me against `litkb_test_w1`, all **pass**:

| my kill | result |
|---|---|
| a tracker row whose `Duplicate of` names a non-existent ID (`999999`) | the load finishes, the row is admitted on its own DOI, the dangling value is recorded verbatim as a `duplicate_of` discrepancy, and **no** `duplicate` candidate is invented |
| a manifest row whose sha256 is a file already bound to another work (byte-identical twin, two DOIs) | the bytes bind to **one** work only; the second does not steal the binding |
| a manual proposal approved by the **same** session | refused — and refused by the **database**, not only by Python: `CheckViolation` on `admissions_second_session_signs_off`, admission still `proposed`. (The Python guard in `admit.front.approve` fires first; calling `litkb.approve_admission` directly proves the constraint is the real gate.) |

Idempotence was **not** re-run against `litkb`, which is read-only for me; the suite's `P3b`/`P3c`
rows cover it on the test database.

## 5. Judgement calls

| call | assessment |
|---|---|
| **C held, not admitted** | **Sound, and it follows from the decision rather than softening it.** Kam's rule is identity from registry *and* verified file; 0013's `_check_registry` refuses a DOI-only claim; design §13 forbids a bypass. Admitting case C would have required one of the two. Holding 68 rows and reporting the number is the honest outcome. |
| **`agrees` vs `differs`** | **Sound and, in my reading, the most important call in P3.** `agrees` is `registry.compare_claimed` — the same comparator admission uses, imported, not re-implemented (3.3). `differs` is normalised inequality and decides only what is recorded. Kam's words are "every field that disagrees", not "every field check 1 rejects"; conflating them would have silently dropped the ratio-0.92 titles and the ±1 years from the review queue. |
| **`free_key` deleted** | **Correct.** Migration 0014 lines 287–344 carry the a/b retry and the "all suffixes taken" refusal; the Python copy duplicated a database rule, and the harness reported its removal as DID NOT FIRE. No `free_key` remains in `pipeline/` or `qc/`. |
| **the NUL fix** | **Correct, and a real defect caught.** Postgres refuses `\x00` in a `text` parameter, so one scanned record's author list would have ended the load — the same class as the `2019a` interruption. Asserted at `record_discrepancy` and on the use. |

None contradicts `decisions.yaml`. Two further findings that are *not* judgement calls:

- **F4 — two year parsers.** `export_shape.year_int` reads `2019a` leniently; `plan.compare_row` uses
  its own `int(str(...))` in a `try/except`, yielding `None`, which makes `year_agrees`
  unconditionally False. So tracker 327 and 329 can never reach case A and §15.15's ±1 rule can never
  apply to them, silently. This is the `free_key` pattern again — one rule, two homes — and the
  report calls it "read leniently", which is true of one parser and false of the other.
  *Fix: `compare_row` should call `year_int`.*
- **F5 — a lost claim.** 15 `doi` discrepancies record `claimed_value = NULL` where the tracker cell
  actually said `https://arxiv.org/abs/2410.22629` (or `N/A — J. Arboriculture 20(2), no DOI`).
  `doi_discrepancy` is handed the parsed DOI, not the raw cell, so what the row *said* survives only
  in `raw_record`. Minor, but the review queue is the place it is wanted.
- **F6 — held rows carry no reason.** All 68 `new` candidates have `state_reason IS NULL`; why a row
  is held must be inferred from the absence of an admission. The report calls held rows "recorded,
  flagged, not admitted" — the first two hold, the reason does not.
- **F9 — `binding-pending` records no evidence.** Every pending `check3_binding` is
  `{'verdict': 'binding-pending'}` with no `text_layer`, `page1_chars` or `reason`, while
  `binding-failed` carries its ratio and reasons. P4's OCR queue will want those numbers.

## 6. Convention and the proposed CLAUDE.md rule

The rewrite **matches what is built**: the database as the one home, the four files as its printed
view with the exact regenerating commands, `litkb_key`/`litkb_state`, the hunt protocol (ws open →
admit → acquire → use with a verified quote → promote prepare), and the `tracker_id` /
`legacy_stem` schemes with M7's rule. It restates no counts. `.litkb-workstream` is untracked
(`git ls-files` empty), as the doc promises.

**F7 — two authorities in one file.** The `manifest.csv` section still reads "**The manifest is
authoritative**; the filename is a label for humans". The new section replaced the *xlsx* authority
line and says so explicitly, but left this one. A fact written authoritatively in two places is a
bug (CLAUDE.md 3.3). *Fix: make that line say the manifest is the authoritative join key for the
files on disk and a generated export of the database.*

**F8 — the proposed rule is broader than Kam's decision.** §15.17: "the rule's reach is uses that
support a claim in the project, not every mention of a paper." The proposed text's first clause,
"any paper the project relies on is admitted, acquired and cited through the literature knowledge
base", is faithful. The trailing "**not fetched ad hoc**" is not: it makes every *fetch* subject to
the rule, which is an acquisition policy, not the scope Kam set. The convention's own hunt-protocol
preamble repeats the broader form ("Any literature the project calls on", "Never fetch a PDF outside
a workstream"). *Fix: drop "not fetched ad hoc" from the CLAUDE.md text and name the scope —
"…through the literature knowledge base whenever it supports a claim (decisions.yaml §15.17)".* The
acquisition rules stay where they are, in the convention.

Pre-existing, outside P3's diff: the Anna's Archive path in the acquisition section is
backslash-mangled (`D:\tools\annas-mcp\aa_fetch.py` rendered as `D:	oolsnnas-mcpa_fetch.py`).

## 7. Ladder and hygiene

`py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w6`, on `eb9d8b1`: secrets, ruff and
compile pass; **1 failed, 2474 passed, 5 skipped, 1 xfailed** in 9m23s. The one failure is
`test_experiments.py::test_pointer_paths_resolve[crown_state_model]` — the known pre-existing
failure, not litkb's. 242 litkb Postgres tests pass. Reproduces the report exactly.

`git log -p 63c9b59..eb9d8b1` scanned for credentials: no password, key, bearer or pgpass value is
introduced. Every `token` hit is the workstream token *parameter* or a fixture handle, never a
literal. 16 commits, 19 files, +4783/−15.

## 8. What Kam should see before accepting

1. **F1 — the gate's `explained` bucket must compare values** (one line), and the `held` branch must
   be tested before it. The measurement above says the numbers will not move; the hole is what moves.
2. **F3** — relabel the 45 refusals as check 2 (duplicate), not check 1 or 4.
3. **F4** — one year parser, not two.
4. **F7 / F8** — the manifest authority line, and the rule's scope.
5. **F5, F6, F9** — review-queue fidelity: the claimed DOI text, a held row's reason, the pending
   binding's evidence.
6. **Still open, as the report says:** `p3-migration` unpromoted, 12 proposals needing a second
   session, 68 held rows, and the preprint/journal pair (303/60) with no version-of relation to
   express it.

None of these is a wrong number in the database. The load stands; the gate and four labels need a
pass.

---

*Referee: Claude Opus 5, session https://claude.ai/code/session_015MUcyGTfX2koRdYAjW5kED.
`litkb` read-only (`litkb_reader`); all mutation on `litkb_test_w1`.*

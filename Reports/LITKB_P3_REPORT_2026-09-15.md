# litkb P3 — Migration + exports, 2026-09-15

Branch `work/20260913-literature-kb`, worktree `D:\edmonds-pipeline\treedata-litkb`.
Design: `Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §4.6, §9.1, §10, §13, §14 P3 row.
Decisions: `Scripts/decisions.yaml` `litkb-p0-foundation`, "P3 load (Kam, 2026-09-14)".

**Status of this evidence (CLAUDE.md 3.4c):** every number below was produced by the author of
the code. No independent referee has re-run the loaders, the gate or the mutations. The gate is
an instrument whose output is a tracked CSV, so a referee can re-run it without re-running the
load; the load itself is idempotent, so a referee can re-run that too and must see nothing new.

*(numbers filled in from the live run — see the sections below)*

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

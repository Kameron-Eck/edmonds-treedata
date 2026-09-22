# litkb plan revision — 2026-09-21 (the session after the S3 wrap-up)

Kam opened this session at 22:00 and went to bed; nobody answered a question. Its one job was to
revise `Scripts/LITKB_WORKPLAN.md` in place (`litkb-plan-home`: no second plan, no retired
document) from the wrap-up's evidence and the GitHub survey. No code changed. Branch
`work/20260921-litkb-plan-revision`; orchestrator Fable; six read-only Opus auditors (one fact
cluster each) + one completeness critic before the draft; one Opus verifier + one Codex
adversarial read after it. Worker reports: `D:\tools\claude-config\jobs\litkb-plan-revision\`
(acquire-audit, admit-audit, bind-audit, state-audit, survey-audit, carryin-audit, critic,
plan-verify, codex, STATE.md).

Every number in this report is read from a tool's own output or a tracked file; "VERIFIED" means
an auditor re-derived it from the tree or the read-only database, "REPORTED" means it is stated
in a tracked report and was not re-run, "ASSERTED" means the survey read it from a badge, a page
or a package field rather than source.

## 1. What changed in the plan, with its source

| section | change | source | status |
|---|---|---|---|
| Conventions | one bullet added: a design is a claim; a scheduled external design says UNVALIDATED and names its positive and negative rows | CLAUDE.md §3.4c; the session brief | authored |
| Where we are | rewritten: what this session changed; S4 run 3 next, Kam launches it; S4.5 next after; the ops residue re-measured; the five open decision ids | state-audit (parked refs exist, 0029 reserved and unapplied, no `extraction_jobs` table, all workstream rows read `open`); carryin-audit I04/I05/I06 and the orchestrator's own `litkb reap --dry-run` (the four filed/web files are `owned` through refused admissions, `orphans=0`); admit-audit item 8 (rows 53/369 are title-hunts residue) | VERIFIED |
| Vocabulary, ladder, instrument | S4.5 added, spelled with a point | `SESSION_HEAD` in `qc/instruments/litkb_acceptance.py` is `^###\s+S(\d+)\b`; the gate parses S4.5 as a second S4 block and grades it | VERIFIED (session list printed) |
| S4 | the `book` residue class; a database-visible quarantine state; a named measurement bed; the bioRxiv-branch measurement on E21's preprint; the Jaffe/Vixie correction; two new (b) counters and two new (c) known-bads; the decided book ruling removed from the Kam line | `litkb-book-policy`; acquire-audit item 6 (`file_versions.status` allows `quarantined`, migration 0001, never held; `state` does not; the filename encoding is read by no code; the `.reason.json` sidecar is the machine-readable copy); carryin-audit I11/I14/I26 and correction C2 (file stems vs work key `Jaffe_2014…`; both already extracted); state-audit (keys truncated against file stems — read `main_files.rel_path`) | VERIFIED |
| S4.5 (new) | four items with test sets: back-off + in-run retry + the arXiv discriminator; registry identity (relation probe first, edges, identifier-first duplicates, type-scoped ISBN-13, the key-length rule); served-bytes hash + rejected-hash lookup + the landing fix; a second-session REFUSE verb | acquire-audit items 2, 3, 5, 6 (`DEAD_STATUSES` keyed on the status word, `at` unused by the skip decision, `record_attempt` carries `http_codes`, `known_md5` looks up the archive-declared md5, a re-served quarantined file is re-landed not `duplicate-held`); admit-audit items 1, 5 (no raw registry response stored; `make_key` fails on LENGTH — reproduced on 187's creator and on synthetic surnames); survey-audit 4.4/4.6 and the critic (repeat legs measured; E13's 505 s is the worst row, not a rate); carryin-audit D1 (no refuse verb: `commands.py:713`, `pg_proc`) | VERIFIED; the external mechanisms ASSERTED-by-one-crawler, marked so |
| S5 | entry condition (metadata repair + a fail-closed citation builder); the run protocol gains the ruled recipe and a drop-off retirement rule; `review-context` no longer listed as unbuilt; a per-hunt time budget; two new (b) counters, three new (c) known-bads; the carry-in list replaced by two kept items with reasons | state-audit item 1 and carryin C1 (`type='report'` ×12 + `proceedings` ×1; `venue`/`publisher` NULL on all; `given` empty; the Step 5 table holds the target types); carryin S2 (`cmd_review_context` at `commands.py:585`, built 2026-09-20); E13's `seconds` in `Reports/LITKB_EDGE_RUN_2026-09-21.csv` | VERIFIED; the four unprinted years REPORTED (approve report defect 6) |
| Improvements after S5 (new) | nine improvements, each with what it rests on, a real test set and the known-bad it must fire on | survey-audit table + spot-checks; admit-audit item 2 (four legs; every candidate judged); bind-audit claims 1–3 (no identifier in `bind()`, `pdf_shape` header+trailer only, the metadata fallback binds an empty page, the sweep not persisted); the critic (row 293 refuses on the year; the `unresolved` rows as the negative set; the metadata-path binds all have a text layer) | VERIFIED for litkb; ASSERTED for the external readings |
| Per-session protocol | the relayed-designs paragraph; four inherited hazards | CLAUDE.md §3.4c; `Reports/LITKB_EDGES_2026-09-21.md` §5.6/5.7 via carryin (ii) 12–13; state-audit (the default test DB); this session (the heredoc) | VERIFIED |
| Open-items register | S2 row deleted; "Codex cannot read block context" deleted; the S7 tolerated-red clause deleted; S4.5 and after-S5 rows added | carryin-audit S1/S2/S3 (`Reports/LITKB_FIRST_WORK_2026-09-21.md`, `pipeline/litkb/acquire/events.py`; `_git_ignored` at `qc/test_experiments.py:210`) | VERIFIED by reading; no pytest run on the S7 clause |
| The survey's verdicts (new) | one table per mechanism: where read, commit, licence provenance, status, litkb gap, verdict, schedule; the survey's two defects corrected | survey-audit §1 table and §4 | as the survey states it; nothing external re-read |
| decisions.yaml | five `open` entries, owner kam | this session | authored; `qc/test_decisions.py` green |
| `_derived/s4/s4-prompt.txt` | rewritten to the revised S4 block; launches S4.5, not S5; the "database was NOT touched" sentence corrected | state-audit (the `readability-1` row is a live write) | VERIFIED |

## 2. Starting hypotheses tested — kept, changed, rejected

The brief offered the orchestrator's hypotheses "and NOT yet accepted". Each was tested against
the auditors' re-derivation.

Kept as offered: the S4 book class; the quarantine state in S4; the measurement bed; a bounded
session between S4 and S5 holding only what protects S5; the S5 entry condition and time budget;
the post-S5 improvements; the reconciled carry-ins; the survey table with verification status.

Changed:
- "the sixteen E24 rows refused at ratio 1.00" → the `registry-quirk` rows (title ratio ≥ 0.85;
  only part of them at 1.00) — REFUTED by admit-audit, survey-audit and carryin-audit from
  `Reports/LITKB_TITLE_HUNTS_2026-09-21.csv`, and by the critic a fourth time. The set also
  splits: all but one refuse on the AUTHOR, one (tracker 293) on the YEAR at a gap of 2 at the
  resolver's fourth leg — two waivers, two decisions. A NEGATIVE set (the `unresolved` rows) was
  added because the positive rows alone measure recall and nothing about precision.
- "E25's two files + the 254-file sweep are the test set" → the sweep's per-file output exists
  at no path (stdout aggregates from a scratchpad script) and its population has drifted
  (bind-audit). The test set is the tracked fixtures under `qc/testdata/litkb_binding_stamps/`
  via `qc/test_litkb_binding_stamps.py`; a sweep INSTRUMENT writing a CSV under phase4/qc/ is the
  prerequisite of the binding improvement.
- "a re-served known-bad file lands as duplicate-held" → it is re-landed and re-quarantined; the
  disk dedupe leg drops `_quarantine/`; `duplicate-held` catches only properly bound bytes
  (acquire-audit, from `run.py` and the three identical Anna's rows).
- "file_versions has no quarantined status" → `status` allows it and never held it; `state` has no
  such value (acquire-audit, `0001_core.sql`).
- "the Anna's known_md5 guard exists for one route only" → true, and the deeper gap is that it
  looks up the ARCHIVE-DECLARED md5, which served bytes never carry; the achievable skip is
  identifier-scoped (survey-audit 4.6).
- "quarantine with the file hash on the attempt row, in S4" → split: the STATE is S4's (the
  classifier's home); the LEDGER (hash on every attempt row, the rejected-hash lookup) is S4.5's.
- "a blocked work re-spends every route every hunt" → the mechanism holds; the measured waste is
  a handful of repeat legs against zero repeats on the dead statuses — the plan states the
  contrast and the query (critic).
- "E13: 505 s" → the slowest of the live rows; the ruled run's blocked rows cost under a minute
  each (survey-audit 4.4). The plan cites the `seconds` column, not the figure.
- "a corporate creator crashes admission" → the discriminator is LENGTH: a surname segment long
  enough that `key[:59]` cuts away the `_YYYY_slug` tail; "King County GIS Center" derives a valid
  key today (admit-audit, reproduced). The S4.5 rule is a length rule.
- "Crossref `relation` is present in every response" → the FIELD is received and dropped; its
  YIELD over this corpus is unmeasured (the survey's own live probe of a bioRxiv preprint returned
  it empty), and no raw response is stored, so a backfill is one call per confirmed DOI. S4.5
  item 2 probes first.
- "Sci-Hub parked by default" → the back-off lands in S4.5 either way; parking a route Kam
  granted is Kam's call → `litkb-scihub-parked` (open).
- "S4½" → S4.5, because the gate's heading rule is `### S<digits>`.
- "194's proposal is to be REFUSED by a second session" → kept as the intent (the brief and the
  wrap-up CHATLOG entry say refuse; `Reports/LITKB_RULED_HUNTS_2026-09-21.md` §9 says approve —
  the conflict is recorded, and the second session that owns the verb decides), with the measured
  fact that NO refuse verb exists → S4.5 item 4.
- "metadata repair, or the citation builder tolerates the defect — decide" → BOTH: the builder
  fails closed AND the repair lands through the versioned path with a second session's approval,
  never an UPDATE on a promoted row. Tolerance would print wrong bylines.
- "Jaffe_2015 / Vixie_2007 refused by the same mechanism" → file stems (work key `Jaffe_2014…`);
  both already bound and extracted; nothing to redo (carryin C2).
- "type='report' on twelve; Raykar 2010, Touvron 2019 are articles" → Touvron is proceedings; the
  target types are the approve report's Step 5 table (carryin C1).
- "rows 53 and 369 (Reports/LITKB_RULED_HUNTS)" → they are title-hunts residue, absent from the
  ruled-hunts report (admit-audit); the decision entry cites the right report.
- The orchestrator's own draft called 187's and 235's files "unowned orphans the reaper would
  quarantine" → the reaper counts them `owned` (a refused admission's checks name them),
  `orphans=0`; they are unbound, not at risk. Corrected before any gate ran.
- "the survey read everything in source" → six of sixteen licences are badge- or API-derived;
  Zotero is pinned only in report B; every external mechanism is one crawler's unreplicated
  reading. The plan's survey table says so per row.

Rejected outright:
- The brief's acquisition census cells (open access 19/24/16, Anna's 15/17/7, Sci-Hub 0/9): a
  pre-09-21 snapshot with two cells that match no cut (acquire-audit, survey-audit, carryin-audit,
  critic). The plan cites the census command and never a cell. "Sci-Hub has never delivered a
  file" holds (no `ok` row for the route, all time).
- "discovery works; acquisition lands roughly half of drop-offs; search is lexical only": no
  metric exists for the first; the second is true of LINKED drop-offs and false of drop-offs
  (the critic's denominators); the third is REPORTED (the P7 verdict) and not re-checked in
  source. None of the three is written into the plan as a rate.

## 3. Questions raised for Kam (each a `decisions.yaml` entry, `status: open`, `owner: kam`)

`litkb-e23-residue-copies` (rows 53, 369, E20's book: copies, or retire) ·
`litkb-blocked-works-grade` (the ruled run's blocked works: metadata-grade, or copies) ·
`litkb-scihub-parked` (park the route by default once the back-off lands) ·
`litkb-tracker-corrections` (the tracker's wrong claims, the crossed 177/178 DOIs, 194's `ref`) ·
`litkb-from-file-version-state` (an operator-supplied file lands `promoted`, not `proposed`).
Also still Kam's, unchanged: the OCR strategy (S4's Kam line) and S5's topic.

Not raised as decisions, recorded here for the record: the CHATLOG's "Sci-Hub 15/15 blocked" for
the ruled run does not match the ledger's rows-per-work for that day (acquire-audit) — the plan
quotes neither; ten of the thirteen promoted works' md5s are REPORTED only (three recomputed by
state-audit, all matching); the `approve_admission` guard has been read by two sessions and never
made to fire (S4.5 item 4 owns it).

## 4. The gates, and the known-bads shown to fire

Run from `Scripts/` on the revised tree.

- `py -3.12 qc/instruments/litkb_acceptance.py plan` → `sessions_missing_abc=0
  unresolved_decision_ids=0`, exit 0. The gate lists sessions S0 S1 S2 S3 S4 S4 S5 S6 S7 — S4.5
  parses as a second S4 and is graded.
- **Known-bad: a backticked path that does not resolve.** Before this report existed the plan
  already named it, so `qc/test_docs_match_code.py::test_no_gated_doc_points_at_a_missing_file`
  went RED: `LITKB_WORKPLAN.md:31: Reports/LITKB_PLAN_REVISION_2026-09-21.md`. Writing this file
  is what turned it green.
- **Known-bad: unresolved ruling ids.** Before the five entries were appended to `decisions.yaml`
  the plan gate printed `unresolved_decision_ids=5` (the five new ids) and exit 1; 0 after.
- **Known-bad: a `decided` entry with no decision text.** `litkb-scihub-parked` mutated from
  `open` to `decided` → `qc/test_decisions.py::test_decided_entries_say_what_was_decided` RED:
  "litkb-scihub-parked: decided but no `decision` text"; file restored → 8 passed.
- **A restated count where a command belongs — NO RULE.** The plan's measurement-bed sentence was
  mutated to "the 30 works in main with an active file and no blocks"; the plan gate printed
  `sessions_missing_abc=0 unresolved_decision_ids=0` and exit 0. The `plan` subcommand has no rule
  for this class; it is caught only by review, which is why Codex was asked for it explicitly
  (§5) and why the plan's fenced "Test-set commands" blocks exist. Restored.
- The (b) pytest line and the preflight counters are in §6, run after the Codex findings were
  folded in.

## 5. The Codex adversarial read and what was done with each finding

Codex (codex-cli in WSL, read-only, session `01a0c7a3-ff06-75d3-ad77-e6832c8f35af`; full report
`D:\tools\claude-config\jobs\litkb-plan-revision\codex.md`) was asked for six classes: restated
counts (A), dead backticked paths (B), designs without UNVALIDATED / a real test set / a fireable
kill (C), conflicts with `decisions.yaml` (D), internal contradictions and unexecutable
instructions (E), malformed one-liners (F). It returned A=33 B=1 C=10 D=11 E=23 F=0. A second,
independent Opus verifier (`plan-verify.md`) ran every command in the plan and tied every
"measured" sentence to a source.

**A — restated counts (33).** FIXED 15: the fetched files of 187/235 (also Codex E1 — the total
disagreed with the enumeration), the E25 `.download` files, the bioRxiv singleton (now a census
command), "E25's two … and the two more", "three, not one", "the two 235 copies", "the only
`proposed` admission" and its command comment, the S5 entry condition's type/venue/title/year
counts, "all but one … one (293)" and its command comment, the five-line/three-line window, and
"Two defects in the survey". REJECTED 7 as not counts of works, rows, blocks, files, refs or
worktrees (the convention's list): "a fifth living state", "six auditors", "one live trace",
"its five-line cover" (the measured shape of one instance, quoted from the ruled-hunts report),
"read by two sessions", "five crawlers", "a sixth auditor". LEFT 11 as pre-existing text in
blocks that landed before this session (S0's "two stale sentences" and "three tokens", S3's
"the one book", the Codex-stage proof "13/13", the worktree-disposition table's "2 reports",
"three rulings", "eight refs", the register's 2026-09-20 adjudication "twelve items", "two
cases") — recorded here as debt for the next session that edits those blocks; the disposition
table is executed history and a candidate for the dated region.

**B — dead path (1).** `Reports/LITKB_PLAN_REVISION_2026-09-21.md` did not exist when Codex
read the plan; it is this file. Resolved by writing it (§4 records the red run).

**C — designs (10).** FIXED all ten: the back-off gained a control that must still spend (E21's
preprint); the identity item gained real negatives (E06 must still refuse; a constructed
cross-type ISBN, stated as constructed; a creator string past the measured threshold); the
hash item gained a valid-download control and the sub-typing set with login walls marked
UNVALIDATED; doi.org negotiation gained a Crossref control; the binding row gained a font-size
kill (a running head as the largest font); the ISBN → md5 negative is now stated as constructed;
both-identifiers gained a constructed negative; the snapshot row's positive is 194's existing
snapshot and its negative the register's URL-HTML-only class; the route-ordering row became
"ordering, blocklist and re-ingest cadences" with three kills.

**D — decisions (11).** FIXED 8: `litkb-k2-no-seeding` presented as undecided in the finish line,
S0's Kam line and S5's run bullet (now "decided"); the "(no seeding)" gloss dropped; the book
ruling restated in S4 trimmed to the id; the ruled recipe in S5 scoped to the ruling's own
conditions; the ISBN → md5 lookup and the generalised registry-over-claim path moved BACK into
S5's Work because `litkb-book-policy` and `litkb-registry-over-claim` name S5 (the revision had
scheduled them after S5). REJECTED 3: the finish-line bullet's six-word gloss of
`litkb-finish-line` (the id is unreadable without it; the ruling text lives in `decisions.yaml`);
the finish-line section itself (the state S0 was built to, pre-existing); S0's "recorded as a
question" (history — it was a question when S0 ran).

**E — contradictions (23).** FIXED 19: the file total; the beyond-the-line list no longer names
the relation scheme S4.5 now owns; the measurement-bed query returns work keys and paths; E21's
edge accepts the empty third state; E06 corrected from a DOI pair to a URL-page negative; the
refused-duplicate landing binds through check 3, never by assumption; 235 dropped from the refuse
item (no proposal exists for it); every S4.5 (b) counter defined (`rehunt_route_spends`,
`attempts_without_sha`, `known_bad_relands`, `unvalidated_items` now requires a `fired:` line);
the zero-window known-bad says why it fires (none of E13's statuses is permanently dead); the
refuse-verb known-bad targets an admission and adds the same-session prohibition; 403 vs
bot-challenge precedence stated (`is_challenge` decides, one solver retry, then dead); the time
budget is checked between stages, ends in the ladder's state, and is flagged on the ledger row;
S5's (b) names the population of `bound=extracted=searchable` and prints the two unbounded
counters the sentence separates; the budget known-bad is deterministic (one second); the
metadata-path command comment matches what it counts; the soak-row schema line points at
`docs/SCHEMAS.md`. LEFT 4 pre-existing: S0's `unexpected_worktrees` known-bad wording (S0 landed
and fired it), S7's soak-vs-doctor and "first three steps" lines — noted for S7.

**F — one-liners (0).** None malformed; the Opus verifier ran all fifteen runnable ones and
fourteen reproduced what their sentence says. The fifteenth, inherited from S3's block,
`grep -c 'browser last' .claude/…` fails from Scripts/ (the skill file is at the repo root) —
FIXED with `../`. The verifier also found the inherited replay line unrunnable from Scripts/
(the manifest is at the repo root) and that `--replay` executes against a worker database —
FIXED: `LITKB_TEST_DB=litkb_test_w10 … --manifest ../_derived/edges/rulings-manifest.json
--replay`, with the worker-database caveat stated. Its one NO SOURCE: "type='report' is a
migration default" is the approve report's assertion — `work_versions.type` has no DEFAULT
clause — FIXED to say the fact is measured and the mechanism is the report's.

Counts after the fixes: Codex's 78 → 53 fixed or resolved, 10 rejected with a reason, 15 left
as pre-existing debt (some findings overlap); the verifier's 3 defects fixed.

## 6. Final gate runs

Run from `Scripts/` after every Codex and verifier fix was folded in (the tree that was committed):

```
PYTHONUTF8=1 py -3.12 -m pytest qc/test_docs_match_code.py qc/test_decisions.py qc/test_litkb_edges.py -q -p no:cacheprovider
litkb Postgres tests: 1 passed
50 passed in 14.58s
(exit 0; the edges suite ran on the default `litkb_test` database — the brief's command sets no LITKB_TEST_DB; nothing else held it)

py -3.12 qc/instruments/litkb_acceptance.py plan
sessions_missing_abc=0 unresolved_decision_ids=0
(exit 0)

py -3.12 qc/instruments/litkb_acceptance.py preflight
stray_tokens=0 migration_mismatch=0 mcp_servers_missing=0 main_not_at_parity=0 soak_stale=0
(exit 0 — S4 can launch on this tree)
```

Not established by this session, said plainly: no design in S4.5 or the improvements table has run on
litkb's rows; every external mechanism is one crawler's reading; the replay line's counters were not
re-run tonight (it writes to a worker database — the S3 wrap-up's replay is the last measurement);
`py -3.12 qc/check.py` was not run (no code changed; `landed.py` ran the session-end rungs instead).

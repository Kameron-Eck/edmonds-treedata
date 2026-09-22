# litkb — the work plan to the finish line

**The one plan for the literature tool** (`decisions.yaml` → `litkb-plan-home`). Living document;
not a dated campaign plan. Gated by `qc/test_docs_match_code.py`; scored by
`qc/instruments/litkb_acceptance.py plan`.

Conventions this file obeys, so it does not become a fifth "living state":
- **A count is a command.** No number of works, blocks, held rows, refs or worktrees is written
  here; the line says what to run.
- **A ruling is an id.** `litkb-…` ids resolve in `decisions.yaml`; the ruling is never restated.
- **A file that does not exist yet is named without backticks.** Backticked slash-paths must
  resolve (the drift gate checks them); plain-text paths are promises.
- **Every session ends in a STATE**, in three parts: (a) tracked artifacts, (b) a command a cold
  session runs with the counters it must print, (c) a known-bad input the new gate REJECTS.
  Per CLAUDE.md §3.4c a gate that has never fired is not a gate.
- **A design is a claim, not a finding.** A line that schedules a mechanism read outside this
  repository says UNVALIDATED and names the real rows it will be scored on, positive and
  negative; the word leaves only when a tracked referee report under Reports/ says the kill
  criterion fired (CLAUDE.md §3.4c). The survey's verdicts and what each rests on are one table
  in this file, never restated per line.
- Git landing rules are CLAUDE.md §3.1 and are not restated here.

---

## Where we are

Update this block only. Everything else in the file changes when a session lands.

- **Finish line:** `litkb-finish-line` — topic → graded review → synthesis, unattended.
- **Current session:** the PLAN-REVISION session landed 2026-09-21
  (`work/20260921-litkb-plan-revision`; report `Reports/LITKB_PLAN_REVISION_2026-09-21.md` — every
  change with its source and whether that source was verified or asserted, the starting hypotheses
  it rejected, the questions it raised, the Codex adversarial findings and what was done with each).
  No code changed. It edited THIS file from the S3 wrap-up's evidence
  (`Reports/LITKB_EDGES_2026-09-21.md`, `Reports/LITKB_TITLE_HUNTS_2026-09-21.md`,
  `Reports/LITKB_RULED_HUNTS_2026-09-21.md`, `Reports/LITKB_APPROVE_SESSION_2026-09-21b.md`, the
  E25 builder/auditor pair under jobs/litkb-s3-wrap) and the GitHub survey
  (D:\tools\claude-config\jobs\litkb-s3-wrap\github-survey\SYNTHESIS.md), after six read-only Opus
  auditors re-derived every fact from the files and the read-only database (their reports under
  jobs/litkb-plan-revision). What changed: S4 gained the `book` residue class, the database-visible
  quarantine state and a named measurement bed; a NEW session **S4.5** (acquisition hardening) sits
  between S4 and S5 and holds only what protects S5's unattended run and has a real test set today;
  S5 gained an entry condition (the promoted tracker-era metadata) and a per-hunt time budget; the
  survey's other designs are scheduled after S5 as improvements, each UNVALIDATED with its test set
  named; the S5 carry-in list is reconciled — every item is in a session block with its test set,
  or kept with the reason; the open-items register lost the rows S2 and the Codex stage had already
  closed; "The survey's verdicts" below records what each verdict rests on. The questions the
  revision raised are `decisions.yaml` open entries: `litkb-e23-residue-copies`,
  `litkb-blocked-works-grade`, `litkb-scihub-parked`, `litkb-tracker-corrections`,
  `litkb-from-file-version-state`.
- **Rulings 2026-09-21** (ids; never restated here): `litkb-book-policy`, `litkb-sibling-edition`,
  `litkb-registry-over-claim`. The register carries E20–E24 as executable rows with MEASURED
  expectations and E25 as a ruled non-hunt row; no row is held:
  `LITKB_TEST_DB=litkb_test_w10 py -3.12 qc/instruments/litkb_acceptance.py edges --manifest ../_derived/edges/rulings-manifest.json --replay`
  → `state_or_reason_mismatches=0 tracebacks=0 held_for_ruling=0` (from Scripts/; `--replay`
  EXECUTES the register against the named worker database — one process on that database at a
  time, like pytest).
- **Next, in order:** (1) **S4 run 3 — Kam launches it himself** from a new terminal window:
  `wt.exe -w new "C:\Program Files\Git\bin\bash.exe" -lc /d/edmonds-pipeline/treedata/_derived/s4/launch-s4.sh`
  (`_derived/s4/s4-prompt.txt` matches the revised "### S4" block; `LITKB_SESSION=s4-run3`;
  workstream slug `readability-2`). Runs 1 and 2 are PARKED untrusted on
  `github/archive/2026-09-21-litkb-s4-{q1,q2,r}-untrusted` — nothing merged, no migration applied,
  no `extraction_jobs` table exists; their one live trace is the `readability-1` workstream row,
  which is nobody's. `state='open'` is not a signal: every workstream row reads `open`
  (`SELECT state, count(*) FROM litkb.workstreams GROUP BY 1` as `litkb_reader`) because nothing
  ever closes one. Entry condition: the preflight command in "Per-session protocol", every counter
  0 (measured 0 at revision time). (2) **S4.5**, launched by S4 the way S4 was launched (a new
  window, bash + prompt file; S4 writes _derived/s4-5/s4-5-prompt.txt from the "### S4.5" block).
  (3) **S5** once its entry condition is met, launched by S4.5. Then S6, S7.
- **Ops residue, nobody's ruling** (`Reports/LITKB_RULED_HUNTS_2026-09-21.md` §9, re-measured at
  revision time): the fetched files of the ruled run's URL rows sit in `_litkb_staging/filed/`
  with no `file_versions` row — 187's protocol PDF and both copies of 235's report — UNBOUND; the reaper counts them `owned`
  because a refused admission's checks name them (`py -3.12 -m litkb reap --dry-run` → `orphans=0`),
  so nothing quarantines them and nothing binds them either (S4.5 item 3 is the landing fix; 235's
  manual admission needs a second session's sign-off and check 3 measures 0.80 on its five-line
  cover — **do not lower 0.85**). 194's
  proposal is to be REFUSED by a second session (its page holds no document) — and NO refuse verb
  exists for a `proposed` admission (`litkb approve` takes only an admission id;
  `litkb._refuse_admission` writes a fresh row at admission time): S4.5 item 4 builds it. The arXiv
  rows of the ruled run (`grep -c ',registry-transient,' ../Reports/LITKB_RULED_HUNTS_2026-09-21.csv`)
  re-run when arXiv answers 200; whether litkb's own client is the defect (urllib 406 while curl
  gets 429/200) is UNDETERMINED and S4.5 item 1 measures it. The E25 `.download` files sit at the
  root of `_litkb_staging/`, outside the reaper's walk (builder-e25 §9.4). The drop-offs of workstream `title-hunts-1` stand `open`
  beside `ruled-hunts-1`'s for the same tracker rows; no rule retires the superseded one (S5
  protocol work).
- **Kam-side, open** (ids; the questions live in `decisions.yaml`): `litkb-e23-residue-copies`,
  `litkb-blocked-works-grade`, `litkb-scihub-parked`, `litkb-tracker-corrections`,
  `litkb-from-file-version-state`; the OCR strategy (S4's Kam line); S5's topic.
- **Rulings 2026-09-20:** `litkb-k2-no-seeding` decided; S7 soak = seven nights
  started in S1. Kam re-registers the nightly-dump scheduled task (Windows task name
  litkb-nightly-dump) against the merged tree: `py -3.12 -m litkb.ops.nightly_dump --install-task`.

---

## The finish line, as a state

A cold session, given ONLY a topic string, unattended:

1. produces a workstream of drop-offs discovered on the open web — identifier, expected claim,
   why relevant, abstract passage — recorded BEFORE any full text is read;
2. hunts every drop-off to a **named terminal state** from the closed vocabulary in
   `docs/SCHEMAS.md` (S3 writes it) — never a traceback, never silence;
3. acquires ≥ 5 distinct new works during the run, each bound = extracted = searchable, proven
   by the acceptance instrument against a manifest frozen before the run;
4. writes a review that passes `litkb review-check` (K1) with K2 fired per
   `litkb-k2-no-seeding` (decided), checked by a different model family at 0 overreach;
5. writes a synthesis — what the literature implies for THIS pipeline — where every inference
   cites a VERIFIED brief line or is labelled as the model's own reasoning, graded by K3;
6. leaves `py -3.12 qc/check.py` green with no tolerated reds and `litkb doctor` green across
   seven scheduled nights.

Beyond the line, on Kam's track (so no session re-proposes them): promotion on live
(`litkb-operational-verdict`), the vector leg (P7 bake-off report on `work/20260915-embeddings`),
citation anchoring and the second gate path (`litkb-crossref-raw-proposer`),
MinerU/native-layer stages (`LITERATURE_KB_DESIGN_2026-09-13.md` §14). The preprint↔published
relation scheme, listed here until 2026-09-21, is now S4.5 item 2 under `litkb-sibling-edition`.

---

## Vocabulary

Loop stages, in order: **discover → drop-off → resolve+admit → acquire+bind → extract+ingest →
search+record → brief+review → synthesis → promote**, plus **ops**. Sessions **S0–S7**, plus
**S4.5** (inserted 2026-09-21 between S4 and S5; written with a point, not ½, because the plan
gate recognises a session heading by `### S<digits>`).

Crosswalk for reading older reports (nothing is renamed there):

| old label | maps to |
|---|---|
| P0–P9 (design §14) | P1–P3 resolve+admit · P4–P5 extract+ingest · P6 references · P7 embeddings (parked) · P8 search+record · P9 ops |
| extraction stages 0–7 (design §7/§12) | inside extract+ingest |
| "stage 8" (2026-09-20) | brief+review |
| items 1–3 (2026-09-19) | ligature (built: migration 0025, `litkb-ligature-repair`) · crossref proposer (S0 merge, `litkb-crossref-raw-proposer`) · pix2tex (`litkb-second-formula-decoder`) |
| builder ids 2a/2b/3/5/6 (jobs) | merged to main 2026-09-20 |
| K1 / K2 (`litkb-operational-definition`) | brief+review gates; **K3** is new (synthesis) |

---

## The acceptance instrument

`qc/instruments/litkb_acceptance.py <subcommand> --manifest <frozen.json>` — one subcommand
per session, reading a manifest frozen BEFORE the run, printing named counters, exit 0 only
when every counter meets its bound. It is what lets a cold session verify a session without
trusting the session's own report. Subcommands land with their sessions: `plan` and
`disposition` (S0), `scout` (S1), `first-work` (S2), `edges` (S3), `readability` (S4), `hardening` (S4.5), `run`
(S5), `synthesis` (S6), `soak` (S7).

---

## The ladder

| session | reaches the state | size | waits on |
|---|---|---|---|
| S0 | one tree, one plan, rulings recorded | 1–2 sittings | disposition executed |
| S1 | topic → drop-offs; `hunt` validates every shape the scout produces | 1 | one headless scout run |
| S2 | ONE unknown work crosses the whole loop, bounded | ½–1 (may share S1's sitting) | network |
| S3 | every hunt ends in a named, adjudicated state | 2 | live routes once; Kam's rulings on the held rows |
| S4 | every acquired file is readable or classified; bulk resumes | 1–2 + unattended local compute | T2000 / WSL GROBID; the book ruling |
| S4.5 | a blocked work costs seconds, siblings link by registry edge, re-served bad bytes are refused on sight, a proposal can be refused — each referee-scored on real rows | 1 | S4's quarantine state; an independent referee |
| S5 | proving run 3 from the open web, graded against a frozen manifest | 1 | one headless run; Kam's topic; the metadata repair |
| S6 | synthesis graded by K3 | 1 | Codex |
| S7 | seven nights unattended | 1 + seven calendar nights | the scheduler |

Each session ends with `py -3.12 qc/landed.py` and a commit on `work/<date>-<slug>`, landed
per CLAUDE.md §3.1.

### S0 — One tree, one plan

Work
- Record the rulings (`litkb-finish-line`, `litkb-plan-home`, `litkb-worktree-disposition`;
  `litkb-k2-no-seeding` as a question). Write this file. Shrink `WORKPLAN.md`'s litkb section
  to a pointer. Retire the jobs STATE.md, the design doc's §14 status rows and the Claude memory
  to pointers. Gate this file. Correct the two stale sentences inside `litkb-p0-foundation` at
  their source.
- Build `litkb_acceptance.py plan`: parses this file's `### S` blocks, counts blocks missing any
  of (a)/(b)/(c), counts `litkb-…` ids that do not resolve in `decisions.yaml`.
- Execute the disposition table (below) from a frozen manifest, in order: vault the three tokens
  → commit splink's uncommitted re-run on its branch → archive reports onto main (crossref by
  merge; ligature's instruments by cherry-pick) → guard → remove clean checkouts → counters →
  the disposition report.
- Verify the POSSIBLY-STALE open items from the 2026-09-20 survey against code (listed in the
  dated appendix) and keep or drop each with a one-line reason in the register below.

Done-state
- (a) this file; the disposition manifest and report under Reports/ (LITKB_WORKTREE_DISPOSITION_2026-09-20);
  every report a `decisions.yaml` entry cites present under `Reports/`; the decision ids above.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py plan --file LITKB_WORKPLAN.md` →
  `sessions_missing_abc=0 unresolved_decision_ids=0` ·
  `py -3.12 qc/instruments/litkb_acceptance.py disposition --manifest <manifest>` →
  `unexpected_worktrees=0 branches_not_at_parity=0 missing_evidence=0 token_vault_mismatches=0` ·
  `py -3.12 -m pytest qc/test_docs_match_code.py -q` green with this file gated ·
  `py -3.12 -m pytest qc -q -k crossref_raw_search` green (the proposer never auto-confirms) ·
  `py -3.12 qc/check.py --fast`.
- (c) remove one (c) bullet from a session block → `sessions_missing_abc=1`; backtick a made-up
  id (litkb-nonexistent, unbackticked here on purpose) → `unresolved_decision_ids=1`; the guard
  refuses a temp worktree whose
  root holds a dummy `.litkb-workstream`; a manifest listing a checkout that still exists →
  `unexpected_worktrees=1`.

Kam: re-register the nightly dump task (`litkb-k2-no-seeding` was decided 2026-09-20).

### S1 — The front door (discover · drop-off)

Principle: the KB agents (`.claude/agents/librarian.md`, `.claude/agents/review-writer.md`) stay
web-blind — that boundary keeps their answers verifiable. Discovery is a NEW role, lit-scout,
whose only write into litkb is `litkb_hunt_request_add`, and it drops off BEFORE reading full
text. A drop-off is a prior; the tool later confirms or contradicts it.

Entry condition: `.claude/skills/paper-search/` is tracked and its MCP server is registered in
`.mcp.json`; a headless probe lists its tools before the real run (a headless session under
`--strict-mcp-config` sees only what `.mcp.json` names).

Work
- .claude/agents/lit-scout.md (Sonnet; tools: WebSearch, WebFetch, paper-search MCP,
  `litkb_ws_open`/`litkb_ws_status`, `litkb_work`, `litkb_search`, `litkb_hunt_request_add`;
  nothing else). A "Stage 1 — discover" section in `.claude/skills/literature/SKILL.md`: query
  plan, source ladder, the drop-off record, the stop rule, the required-field set (the schema
  leaves `abstract_passage` nullable; the scout's contract does not).
- `hunt_request.ref_scheme` gains `title` (migration; number reserved in
  `pipeline/litkb/db/migrations/_reserved.txt` first). `pipeline/litkb/hunt.py` `ref_kind`
  VALIDATES instead of classifying: `arxiv` → `registry.arxiv_record`; `title` →
  `resolve_doi(title, surname, year)` in `pipeline/litkb/admit/resolver.py` → the UNCHANGED
  confirm gate → admit, else `unresolved-title` / `ambiguous-title`; malformed DOI/arXiv/URL →
  `malformed-ref`; isbn/pmid/handle → `unsupported-ref-scheme`. `cmd_discover` retired or
  folded, decided by whether the scout uses it.
- Fixture qc/fixtures/litkb_ref_shapes.json (doi · arxiv · url-pdf · url-html · title · title
  missing author or year · isbn · garbage); mutation rows (`HS*`) in
  `qc/instruments/litkb_p2_mutations.py`.
- One headless scout run, workstream `scout-1`, on a topic that serves the pipeline.
- Start the S7 soak clock now (Kam's ruling): a scheduled nightly task that runs a smoke
  `litkb_search` and a smoke `hunt` on a known-extracted key and appends one row to a soak CSV
  under Reports/ (LITKB_SOAK). The full `doctor` joins it in S7; the row schema is fixed here (`docs/SCHEMAS.md`, LITKB_SOAK.csv) so
  S7's `soak` subcommand can read every night from S1 onward.

Done-state
- (a) the agent file; the SKILL section; the migration; `pipeline/litkb/hunt.py` + tests; the
  fixture; the ledger rows; a scout-run CSV under Reports/ (LITKB_SCOUT_RUN_<date>); the
  scheduled soak task with its first row written.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py scout --manifest <manifest>` →
  `dropoffs>=10 missing_required_fields=0 ref_scheme_outside_set=0 missing_hunt_results=0
  unknown_states=0 human_input_events=0` · `py -3.12 -m pytest qc/test_litkb_hunt.py -k ref_shapes`.
  Usefulness is NOT a counter — it has no measure; K2 in S5 is the proof the scout does not
  rubber-stamp.
- (c) a garbage ref → `malformed-ref`, never `doi`; an ISBN → `unsupported-ref-scheme`, never a
  traceback; `RESOLVE_TITLE_RATIO` lowered from 0.85 to 0.80 with a frozen wrong-work candidate
  scoring between them → the identity test goes RED; a nonsense topic → 0 drop-offs and a stated
  reason; an empty `expected_claim` refused (existing HQ rows re-fired).

### S2 — The first unknown work (bounded proving run)

The riskiest untested assumption: a genuinely unknown discovery crosses admission, acquisition,
extraction, workstream visibility, recording and review with no operator repair. Test it before
any queue or backlog investment.

Work
- Freeze a baseline manifest (counts by query, workstream id). One newly discovered OA PDF
  absent from the KB → drop-off → `hunt` → one newly ingested searchable block → one verified use
  → one review claim → `review-check` → Codex checks that one claim. Record admission,
  acquisition-attempt, file and run ids, and any bounded failure outcome.
- One **acquisition-event contract**: hunt's URL path lands files through its own function
  while the route path records through `pipeline/litkb/acquire/run.py` — one provenance shape,
  one verifier, reused by S5.

Done-state
- (a) a first-work manifest + report under Reports/ (LITKB_FIRST_WORK_<date>); the contract +
  its test.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py first-work --manifest <manifest>` →
  `new_works=1 bound=1 extracted=1 searchable=1 verified_uses>=1 claims_ungraded=0
  operator_interventions=0`.
- (c) replay the manifest against the baseline snapshot (work absent) → `new_works=0` → exit 1;
  a URL-path landing with no acquisition event → the verifier goes RED.

### S3 — Every hunt ends in a named, adjudicated state (resolve+admit · acquire+bind)

Work
- The vocabulary: ONE table in `docs/SCHEMAS.md` (state · meaning · who acts next); `STATES` in
  `pipeline/litkb/hunt.py` plus reason classes, enforced by a test.
- The register qc/fixtures/litkb_hunt_edge_cases.json from REAL rows already in hand (the
  held-queue CSV's refusals and low-confidence rows, the manual proposals, the OCR-bound scans,
  the linkage-review §7 cases, the one book) — **each row carries an expected state adjudicated
  independently**; Kam's rulings on the held rows become expected states. Classes: OA DOI ·
  paywalled DOI · unobtainable DOI · arXiv · URL-PDF · URL-HTML-only · scan · book ·
  preprint+published (`sibling-edition`) · same work under two DOIs (alias/collision policy) ·
  duplicate admission · registry mismatch · grey report · 403/challenge · quota-stop ·
  mid-hunt crash.
- Gaps closed: HTML-only through `hunt` **to searchable blocks** (snapshot admission in
  `pipeline/litkb/admit/front.py` exists; extraction of the snapshot does not); a staging reaper
  with age + ownership checks that quarantines, never blind-deletes; Sci-Hub mirrors from config
  (failover already iterates in `pipeline/litkb/acquire/scihub.py`; configurability is the new
  part); `.claude/skills/literature/SKILL.md` "a browser last" → "manual `--from-file` last";
  `absent` split three ways (never admitted · admitted in another workstream · held);
  `litkb_acquire` returns `detail`.
- The second-session approve path (`approve` in `pipeline/litkb/admit/front.py`, never
  exercised): a SECOND headless session reviews the proposals the run created and approves or
  refuses each.

Done-state
- (a) the fixture with expected states; an edge-case CSV under Reports/ (one live run); the
  SCHEMAS table; tests + ledger rows; the approve-session log.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py edges --manifest <manifest> --replay` →
  `executed=manifest_rows skipped=0 state_or_reason_mismatches=0 tracebacks=0` ·
  `grep -c 'browser last' ../.claude/skills/literature/SKILL.md` → 0 (run from Scripts/; the skill file is at the repo root).
- (c) mutate the registry-mismatch row's expected state to the *valid* `extracted` →
  `state_or_reason_mismatches=1` (membership alone cannot pass); a route monkey-patched to
  raise → an `api-error` state and a logged attempt, not a traceback; a planted orphan younger
  than the age threshold is NOT reaped; an older one is quarantined and reported.

Kam: rulings on the refused/held rows (a decision that is also a fixture); the mirror source;
the archive route stays a standing grant.

### S4 — Everything acquired is readable or classified (extract+ingest)

Draining the whole historical backlog is NOT a prerequisite for S5. The backlog is the
measurement bed; the done-state is the classifier and the resume proof.

Work
- An `extraction_jobs` queue (design §12.3–12.5; lease + resume; 0029 is reserved for it in
  `pipeline/litkb/db/migrations/_reserved.txt`). Per-file completeness: a work with an extracted
  file AND an unreadable file, or a native file with zero blocks, is classified, never silently
  "extracted".
- Drain as far as the session allows, locally (WSL GROBID + T2000 Docling; litkb is local-only,
  `litkb-p0-foundation`). Residue classes: `no-file-any-route` · `scan-needs-ocr` ·
  `over-page-cap` · `zero-content` · `bad-file` · `refused-registry` · **`book`** (`litkb-book-policy`,
  decided 2026-09-21: the classifier names it; S4 never extracts it).
- Scan OCR inside the queue under the measured VRAM policy; an **enforced, fail-closed**
  extraction page cap (page-range support exists in `pipeline/litkb/extract/docling_worker.py`; a
  cap does not); `page_no` for cross-page paragraphs (citation integrity); metrics into
  `extraction_runs.metrics`; retiring the superseded run sets as a deliberate op. Formula LaTeX
  stays `unverified` (`litkb-second-formula-decoder`).
- **A database-visible quarantine state** (survey E, adapted; the classifier is its natural home).
  Measured 2026-09-21: `_quarantine/` is a directory; `Store.to_quarantine`
  (`pipeline/litkb/acquire/store.py`) writes status and sha into the FILENAME, which no code reads
  back, and a `.reason.json` sidecar, which is the only machine-readable copy;
  `file_versions.status` already allows `quarantined` (migration 0001) and has never held it;
  `file_versions.state` has no such value; a refused file is invisible to `litkb_work`. S4 gives
  every file the classifier refuses (`bad-file`, `zero-content`) and every download the
  acquisition guard quarantines a database row — a status plus the sha256 of the refused bytes
  plus the reason, never a directory alone. Reserve a migration number first if a column or table
  is needed. S4.5 item 3 reads this state to refuse re-served bytes.
- **The measurement bed**, named so the classifier is scored on real files, not synthetic ones:
  every active file in main with no blocks, by work key (the query under "Test-set commands");
  the `--no-extract` binds of the wrap-up and the ruled run
  (`grep -c ',bound-unextracted,' ../Reports/LITKB_TITLE_HUNTS_2026-09-21.csv`,
  `grep -c ',bound-unextracted,' ../Reports/LITKB_RULED_HUNTS_2026-09-21.csv`); the tracker-era
  works the second session promoted (`grep '^## 01a0a' ../Reports/LITKB_APPROVE_SESSION_2026-09-21b.md`
  lists them; extracted or not, per file — read `main_files.rel_path`, never compose a path from a
  key, because several keys are truncated against their own file stems); E21's pair
  (`litkb-sibling-edition`) — its bioRxiv preprint is the base's bioRxiv file (census: the `10.1101/`
  query under "Test-set commands"), so measure the stamp strip's bioRxiv/medRxiv branch (`_PREPRINT_STAMP` in
  `pipeline/litkb/admit/binding.py`, tested until now on constructed lines only) on it and record
  the ratio; E25's re-bound arXiv files and the further files the sweep scored below the gate
  (`Validation/Jaffe_2015_estimating-accuracies-multiple.pdf` under work
  `Jaffe_2014_estimating-accuracies-multiple-classifiers`, and
  `Validation/Vixie_2007_some-properties-minimizers-chan-esedoglu.pdf` — both already bound and
  extracted by another route, nothing to redo); E08 `Hwang_1982` (`bound-unextracted/already-bound`,
  `has_text_layer=false`) as the first scan row, with the other no-text-layer scans behind it
  (`Anderson_1957`, `Hudson_1978`, `Ogata_1998`); S2's Copernicus PDF that Docling produced
  nothing for while GROBID carried it (`Reports/LITKB_FIRST_WORK_2026-09-21.md`) → a
  classification, never a refusal; the E20 book if a copy arrives (`litkb-e23-residue-copies`).
- Carried from S3, unchanged: `binding.TITLE_REGION_LINES = 45` is a PDF-page rule and a ceiling on
  web pages; a refused page hunt leaves its snapshot in `_litkb_staging/web/` with no row — own it
  at refusal or let the reaper take it at its age threshold (decide in the report, and say which);
  the files still bound at `_litkb_staging/incoming/t*.download` paths need a rebind/refile path if
  extraction wants a stable path; the L4 formula re-crop of Reynolds_2000 and Montgomery_1991 never
  ran.

Done-state
- (a) the migrations + worker; a readability CSV + report under Reports/ (LITKB_READABILITY_<date>);
  tests + ledger rows; `docs/SCHEMAS.md` rows for the quarantine state and every new column.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py readability --manifest <manifest>` (all
  workstreams in the manifest, not main only) → `unclassified_acquired_files=0 stale_leases=0
  duplicate_blocks=0 resumed_content_hash_mismatches=0 books_extracted=0
  quarantined_without_db_state=0`.
- (c) kill mid-batch, rerun → block **content hashes** equal, 0 duplicates; a lease token mutated
  so an expired worker commits after reassignment → the ownership gate goes RED; a cap+1 PDF
  whose page-count probe FAILS → extraction refused (fail-closed), not started; a scan with OCR
  off → `scan-needs-ocr`, never "extracted, 0 chars"; a `type=book` record pushed through the
  queue → the `book` class and `books_extracted=1` the moment a block lands; a file placed in
  `_quarantine/` with no database row → `quarantined_without_db_state=1`.

#### Test-set commands (run from Scripts/, read-only)

```
# active files in main with no blocks, by work key — the bed the classifier is scored on (a work may hold more than one file)
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute(\"SELECT w.key, f.rel_path FROM litkb.main_files f JOIN litkb.main_works w ON w.work_id=f.work_id WHERE f.status='active' AND NOT EXISTS (SELECT 1 FROM litkb.blocks b WHERE b.file_id=f.file_id) ORDER BY 1\").fetchall())"
# the base's bioRxiv files (DOI prefix 10.1101/), for the stamp strip's bioRxiv branch
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute(\"SELECT w.key FROM litkb.main_identifiers i JOIN litkb.main_works w ON w.work_id=i.work_id WHERE i.scheme='doi' AND i.value LIKE '10.1101/%'\").fetchall())"
# the quarantine's size today (a directory; no database state until S4 lands)
py -3.12 -c "import pathlib;print(sum(1 for _ in pathlib.Path('D:/edmonds-pipeline/Literture/_quarantine').iterdir()))"
```

Kam: the OCR strategy (recommendation: page-range chunks on the T2000).

### S4.5 — Acquisition hardening (acquire+bind · resolve+admit identity · the second session)

Inserted 2026-09-21 by the plan revision, between S4 and the proving run. It holds ONLY what
protects S5's unattended run and has a real test set today; everything else the survey proposed
is under "Improvements after S5". Every item below is a RELAYED design (CLAUDE.md §3.4c): a
crawler read the mechanism in external source, nobody has run it on litkb's rows, and the
external reading is one crawler's, unreplicated. Each item is UNVALIDATED until an independent
referee (never its builder) scores it on the rows named here and the referee's report is tracked
under Reports/; a kill criterion counts only once it has FIRED on the known-bad. Spelled S4.5,
not S4½, because the plan gate recognises a session heading by `### S<digits>`.

Work
1. **Per-route back-off and in-run retry** (survey C, Zotero's per-host record, adapted — the
   Zotero commit is UNPINNED in the survey; the mechanism is what is adopted, not the code).
   Measured: the dead-skip in `pipeline/litkb/acquire/run.py` is a literal set keyed on the
   status word alone (`DEAD_STATUSES`); `blocked`, `quota-stop`, `bad-file` and `api-error` are
   in no route's set; `prior_attempts()` returns `at` and the skip decision never reads it (the
   printed skip message does). The statuses that ARE dead show no repeat legs in the ledger; the
   `blocked` legs do — the contrast, not "every hunt", is the finding (the census command under
   "Test-set commands"; E13's `seconds` in `Reports/LITKB_EDGE_RUN_2026-09-21.csv` is the worst
   single row, the ruled run's blocked rows cost under a minute each). The attempt row already
   holds `route`, `status`, `http_codes` and `at`, so a back-off needs no schema change: key it on
   (route, status, http codes, at) — never on the hunt's state word, because `pipeline/litkb/hunt.py`
   folds `quota-stop` into `blocked` too. A plain 403 on a route is dead for the rest of the run on that route; a bot challenge is
   told by the body, not the code (`is_challenge` in `pipeline/litkb/netutil.py`), gets one
   solver retry, then is dead for the run — that precedence is the rule item 3's sub-typing
   records; a registry transient (`api-error/registry-transient`) is retried on a schedule inside
   the run, never by hand; a skipped route is logged as a skip, never an attempt; dead-ness carries
   a date, not a permanent mark, because mirrors change. Sci-Hub's default is
   `litkb-scihub-parked` (open): the back-off bounds its cost to one probe per route per run
   either way; the default flips only when the id is decided. The retry is also the arXiv
   discriminator: when the ruled run's `registry-transient` rows re-run, a `curl` probe of the same
   endpoint in the same minute is recorded beside litkb's own response — a 200 to curl and a 406
   to litkb names the client as the defect.
   Test set: E13 (`10.1145/3534678.3539043`) re-hunted twice in one run; the `registry-transient`
   rows of `../Reports/LITKB_RULED_HUNTS_2026-09-21.csv`; and a control that must still spend —
   E21's preprint (its route answered 200 live, `Reports/LITKB_TITLE_HUNTS_2026-09-21.csv`)
   re-hunted under the back-off reaches its route.
2. **Identity from the registry, not from titles** (survey B, adapted; `litkb-sibling-edition`,
   `litkb-book-policy`). Measured: `parse_crossref` in `pipeline/litkb/admit/registry.py` receives
   the `relation` field and never reads it, and no raw registry response is stored anywhere, so a
   backfill costs one Crossref call per confirmed DOI (`SELECT scheme, verified_by, count(*) FROM
   litkb.main_identifiers GROUP BY 1,2` sizes it) and the field's YIELD over this corpus is
   unmeasured (the survey's own live probe of a bioRxiv preprint returned `relation:{}`). So:
   FIRST a sampled live probe over the base's DOIs, recorded as a measured CSV under phase4/qc/ by
   an instrument (CLAUDE.md §3.4b); THEN record `relation` (isPreprintOf / hasPreprint /
   isVersionOf) and the arXiv record's DOI as identifier-to-identifier edges with a third state
   for "no relation returned" (absence of the field is not evidence of absence), at admission going
   forward and by backfill as the probe's yield justifies. Order the duplicate check
   identifier-first so a DIFFERENT confirmed DOI is "a different record, possibly related", never
   `duplicate-review` (`_title_duplicates`, migration 0013, at 0.70/±1 y today). Harvest `ISBN` at
   admission canonicalised to ISBN-13 and scope it by type — shared ISBN is identity only between
   two `book` records, because chapters share the book's ISBN. Give `make_key` in
   `pipeline/litkb/admit/front.py` a rule for long creator strings: measured, the crash is LENGTH,
   not corporateness — a surname segment long enough that `key[:59]` cuts away the `_YYYY_slug`
   tail violates `works_key_check` (row 187's DataCite creator; "King County GIS Center" derives a
   valid key today). Derive a compact key (an initialism, as the manual `LPVSubgroup_2025_…` did)
   when the segment would overflow, and if derivation still fails REFUSE with a named reason —
   never `crashed/admit:CheckViolation`. Migration numbers reserved first.
   Test set — positive: E21's pair (`litkb-sibling-edition`): the probe records the registry's
   answer for both DOIs — an edge if one is returned, the third state if `relation` comes back
   empty; either passes, a title-inferred edge is the refusal — and the preprint DOI keeps
   admitting as its own work under identifier-first ordering; E20's book
   (`10.1201/9781315374321`) gains its ISBN at admission; 187's DataCite record admits with a
   derived key and no `--key`; the ruled run's arXiv rows, once arXiv answers, each record their
   DOI field or its absence. Negative: E06 in `qc/fixtures/litkb_hunt_edge_cases.json` (a page
   with no confirmed identifier, title-near an existing work) must STILL refuse
   `duplicate-review`; a `journal-article` record given E20's ISBN must not be its duplicate —
   CONSTRUCTED, because the base holds no chapter, and this line says so; a creator string one
   character past the measured length threshold (admit-audit's synthetic surname) must derive a
   key, never crash.
3. **The served bytes' hash on every attempt row, and a landing that never strands a file**
   (survey E, sandcrawler's ledger, adapted; the rejected-sha lookup is litkb's own design — nothing
   external refuses a known-bad hash). Measured: only the Anna's route guards a known md5
   (`known_md5` in `pipeline/litkb/acquire/annas.py`), and it looks up the ARCHIVE-DECLARED md5,
   which the served bytes by construction never carry, so a served hash can never suppress the
   request that produced it; a hash mismatch quarantines the bytes (their md5 is in the disk index)
   but nothing consults it; a re-served quarantined file is NOT `duplicate-held` — the disk dedupe
   leg drops `_quarantine/`, so the same bytes are re-landed and re-quarantined (the identical
   Anna's rows for E13); the open-access route writes `detail->'sha256'` on some failures and not
   others. Record the sha256 of what a route served on its `acquisition_attempts` row for EVERY
   route; add a (route, identifier, sha) → rejected-because lookup over S4's quarantine state so a
   re-served known-bad file is a skip, and N distinct bad hashes make the (route, identifier) pair
   dead; sub-type `blocked` into login-wall (dead) and bot-challenge (retryable). The identifier
   scope is the only achievable one (a hash cannot be known before the bytes arrive). First step,
   before any spend: diagnose the Anna's `bad-file` repeats (the query under "Test-set commands"
   lists every repeated DOI) against the archive record's md5 — a wrong
   record and a wrong gate need different fixes. Same item, the landing defect the ruled run
   surfaced: a fetched file whose URL admission is refused `duplicate-review` is OFFERED to the
   work it duplicates through the normal binding gate (check 3 on the file against that work's
   record — a bind, never an assumption; if check 3 refuses, the file is quarantined with the
   reason) and is never left unowned on disk (187's protocol PDF in `_litkb_staging/filed/`; the
   `.download`-path workaround retired).
   Test set: E13's Anna's rows (re-served bytes skipped); a control — E21's preprint's bytes
   re-served must NOT be refused (its hash is bound, not rejected); the sub-typing set — the
   `challenge` and `403` attempts in the census (`http_codes` + `detail`), with a login wall
   UNVALIDATED until one is recorded; 187's filed PDF and 235's copies bound through check 3 or
   quarantined with a reason — never left under `filed/`.
4. **A second-session REFUSE verb** (litkb's own gap, measured 2026-09-21): `litkb approve` takes
   only an admission id and `litkb._refuse_admission` only INSERTs a fresh refusal at admission
   time, so a `proposed` admission can be approved or left forever — never refused. S5 creates
   proposals (web snapshots, manual admissions) that a second session must adjudicate both ways.
   Build the verb and the function that moves `proposed` → `refused` under the approver's labels,
   guarded like `approve_admission`, and make BOTH guards fire on a known-bad (the approve guard
   has been read by two sessions and never made to fire — a §3.4c gap on the path the whole second
   session rests on).
   Test set: 194's proposal (`01a0c730-fa16-7d45-baf8-0fce8c8ad084`; the `proposed` admissions are
   the command below) refused by a second session; the approve guard fired on a known-bad
   (`approve` invoked by the session that made the proposal → refused).

Done-state
- (a) the migrations; the back-off, the edge recorder + probe CSV, the hash on the attempt row,
  the refuse verb; a hardening CSV + report under Reports/ (LITKB_HARDENING_<date>); one referee
  report per item under Reports/; tests + ledger rows; `docs/SCHEMAS.md` rows for every new column,
  state and sub-type.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py hardening --manifest <manifest>` →
  `rehunt_route_spends=0 transient_rows_unretried=0 relation_probe_rows>=1 relation_edges_missing=0
  identifier_first_refusals=0 books_without_isbn=0 key_derivation_crashes=0 attempts_without_sha=0
  known_bad_relands=0 unowned_landings=0 proposals_unadjudicated=0 unvalidated_items=0`. Meanings,
  fixed here: `rehunt_route_spends` counts attempts on a (route, work) whose previous attempt on
  that route is inside its back-off window and is not a scheduled transient retry;
  `attempts_without_sha` counts attempts whose `detail` records bytes received and no sha (an
  attempt that received no bytes is out of scope); `known_bad_relands` counts landings whose sha
  matches a rejected (route, identifier, sha) row; `unvalidated_items` counts items whose referee
  report the manifest does not name OR whose report carries no `fired:` line for the item's
  known-bad.
- (c) the back-off window set to zero → E13's second hunt spends every route again (none of
  E13's statuses is a permanent dead status) → `rehunt_route_spends>0`; a relation edge asserted from a title match with no registry `relation`
  → refused; an ISBN shared by a `book` and a `journal-article` record → not a duplicate; the key
  rule reverted → 187's record ends `crashed`, `key_derivation_crashes=1`; E13's bad bytes
  re-served with the lookup disabled → `known_bad_relands=1`; the refuse verb invoked on an
  admission already `approved` → refused by its guard, and `approve` or `refuse` invoked by the
  session that made the proposal → refused; a referee report dropped from the manifest →
  `unvalidated_items=1`.

#### Test-set commands (run from Scripts/, read-only)

```
# the acquisition census, all time, by route and status — never quote a cell, run this
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute('SELECT route,status,count(*) FROM litkb.acquisition_attempts GROUP BY 1,2 ORDER BY 1,2').fetchall())"
# repeat legs per (route, status): a status that is dead shows one attempt per work
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute('SELECT route,status,count(*) AS attempts,count(DISTINCT work_id) AS works FROM litkb.acquisition_attempts GROUP BY 1,2 HAVING count(*)>count(DISTINCT work_id) ORDER BY 1,2').fetchall())"
# the Anna's bad-file repeats, by identifier
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute(\"SELECT identifier_used,count(*),min(at)::date,max(at)::date FROM litkb.acquisition_attempts WHERE route='annas' AND status='bad-file' GROUP BY 1 ORDER BY 2 DESC\").fetchall())"
# the proposed admissions (194 today); then the reaper's verdict on every staging file
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute(\"SELECT id,state FROM litkb.admissions WHERE state='proposed'\").fetchall())"
py -3.12 -m litkb reap --dry-run
```

Kam: `litkb-scihub-parked`; `litkb-blocked-works-grade`; `litkb-from-file-version-state`.

### S5 — Proving run 3: a topic becomes a graded review, unknown works included

Entry conditions (added 2026-09-21)
- **The promoted tracker-era metadata is repaired, or cannot print.** The second session's
  promotion (`Reports/LITKB_APPROVE_SESSION_2026-09-21b.md`; the works are its `## 01a0a…`
  headings) landed rows with the right identity and the wrong citation shape — measured at
  revision time in `main_works`: `type='report'` on nearly every row is not a classification —
  the approve report calls it a migration default, and `work_versions.type` has no DEFAULT
  clause (migration 0001), so the writer was the legacy migration path, which nobody re-read:
  the fact is measured, the mechanism is the report's (the per-work target type — article,
  proceedings, preprint, or none printed — is that report's "Step 5" table); author lists cut to first-and-last with every `given` empty; `venue` and
  `publisher` NULL on every row; a title cut mid-title (Kalinicheva); years not printed in their
  documents (the report's defect 6 names them). The review's citation strings are
  built from these rows, so S5 does BOTH, decided here over "tolerate the defect" because
  tolerance bakes a wrong byline into every review that cites them: (i) the review writer's
  citation builder FAILS CLOSED on a row whose `given` is empty or whose `venue` is NULL — a wrong
  byline never prints; (ii) a repair pass re-reads each promoted work's first page and lands the
  corrected metadata as a NEW version through the versioned-record path (`work_versions`) with a
  second session's approval, never an UPDATE on a promoted row — if no CLI can propose a new
  version of a promoted work, building it is the first step; (iii) admission stops writing the
  defaults. Read `main_files.rel_path` for the documents, never a path composed from the key.
- **Kam** names the topic and applies migrations BEFORE the run, none during.

Work
- docs/LITKB_RUN_PROTOCOL.md: prompt = topic + slug only; a test fails on any work key in the
  template; attempt limit and rerun policy fixed BEFORE launch; exhaustion → UNDETERMINED, never
  a quiet extra try; the ruled recipe (`litkb-registry-over-claim`), applied only under that
  ruling's own conditions (the title matches the record and the relevance sentence describes it)
  — a hunt by identifier is BARE and the drop-off links afterwards, because `--hunt-request`
  re-injects the drop-off's claim into check 1; a `refused/admission-refused` whose only disagreement is the
  drop-off's own author or year is a CONTRADICTED prior, recorded, and the run never re-hunts it
  bare (that would be the run overruling its own gate; the human-say-so path is an improvement
  after S5); one drop-off per source row per run, and the rule that retires a superseded drop-off
  (the `title-hunts-1` rows superseded by `ruled-hunts-1` are the test case). `litkb review-context`
  exists and is proven ("Codex stage" below); the pgpass entry it needs against a worker database
  is Kam's. Run 2's review re-graded under the tightened grader and marked historical.
- **A per-hunt time budget** in the run manifest. The manifest freezes `hunt_budget_seconds`; the
  run ledger records `seconds` per drop-off (the edge-run ledger already does); the
  budget is checked between stages and between routes, never mid-request; a hunt over budget
  stops before its next stage, ends in the state the ladder had reached at that boundary (`held`
  with the last route's reason if no file landed — never a new state word), carries
  `over_budget: true` on its ledger row, and the `run` subcommand counts it. S4.5's
  back-off is what makes this rare; the budget is what makes an unattended run finish.
- **Owed to S5 by rulings** (each UNVALIDATED until an independent referee scores it): the
  archive lookup by ISBN → md5 for `type=book` (`litkb-book-policy` names it S5 build work; test
  row E20's record once S4.5 gives it an ISBN; the negative — a chapter's md5 answered for the
  book's ISBN — is CONSTRUCTED because the base holds no chapter, and this line says so); the
  generalised registry-over-claim admission (`litkb-registry-over-claim` names it as S5's):
  `admit_registry`'s `registry_only` mode — a Python flag read by SQL `_check_registry`,
  migration 0020, reachable today by any BARE hunt — behind an explicit "link, do not claim" flag
  that records the drop-off's claim as a discrepancy instead of re-injecting it; test set the E24
  carriers of the register and a drop-off whose claim is wrong; fires on: the flag invoked with no
  human sign-off → refused, and the flag absent → the claim still refuses at check 1.
- THE RUN: headless, topic named by Kam; scout → hunts with real acquisitions → record → brief →
  writer → `review-check` → Codex. K2 fires per `litkb-k2-no-seeding` (decided). An expectation can go
  UNCONFIRMED without its paper being acquired; the counters separate the two.

Done-state
- (a) the review under `Reports/reviews/`; a proving-run-3 report + frozen manifest under
  Reports/; the repair pass's report and its second-session log; the protocol doc + its tests.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py run --manifest <manifest> --audit` →
  `distinct_new_works>=5 bound=extracted=searchable` (over those new works)
  `missing_dropoff_outcomes=0 hunts_over_budget=0 citations_from_defective_rows=0 K1=PASS K2=FIRED
  claims_ungraded=0 overreach=0 operator_interventions=0 migrations_during_run=0`, with
  `expectations_unconfirmed` and `dropoffs_not_acquired` printed unbounded — the two counters the
  sentence above separates.
- (c) the grader on a one-character mutation → FAIL (byte verification, re-fired not assumed); a
  claim mutated to assert **causation** while keeping its valid descriptive quote → the Codex
  stage must flag it (overreach is the K1 escape no deterministic grader closes); the protocol
  test fails on a pre-named work; the budget set to one second and any drop-off with a live route hunted →
  `hunts_over_budget>=1`; a citation built from a row with empty `given` → the builder refuses,
  `citations_from_defective_rows=1` if one prints; the run re-hunting a check-1 refusal bare → the
  protocol test goes RED.

Carry-ins kept here, each with the reason it is not a session item:
- Row 33's quoted numbers may belong to a different paper by the tracker's named author
  (`litkb-registry-over-claim` records it) — a check at record time, not a build.

Kam: name the topic; apply migrations BEFORE the run, none during.

### Improvements after S5 — not blockers; scheduled 2026-09-21; every one UNVALIDATED

None of these gates the finish line. Each is a design (most from the survey; verification status
in "The survey's verdicts" below), lands only under the S4.5 protocol — builder ≠ proposer, an
independent referee on the rows named here, the report tracked under Reports/ — and names its
test set here so no session re-derives it. "Closes" names the measured pain; "fires on" names the
known-bad the kill criterion must be shown to reject before the design counts.

| improvement | closes | rests on | test set (real rows) | fires on |
|---|---|---|---|---|
| **Two-tier title resolution**: above a measured title-ratio cut, waive the first-author test and record the author disagreement as a discrepancy row; keep the per-candidate judgements in `resolver_detail` (today only the refusal detail is reduced to the highest-ratio candidate — every candidate IS judged). Measured: the E24 refusals split two ways — on the AUTHOR for every row but tracker 293, which refuses on the YEAR at a gap of 2 at the resolver's fourth leg — so the author waiver and the year rule are two decisions, scored separately; and a record with no parseable year can never resolve (row 369). | the structural limit of `Reports/LITKB_TITLE_HUNTS_2026-09-21.md` — a conjunction confirms, never corrects | survey A: paper-qa's rule, VERIFIED in source at a pinned commit; its licence ASSERTED. The cut is MEASURED on litkb's rows, never taken from paper-qa (its 1.00 cut resolves only part of the set) | POSITIVE: the `registry-quirk` rows of `../Reports/LITKB_TITLE_HUNTS_2026-09-21.csv` (command below), which must resolve to their stored DOI with a discrepancy row; NEGATIVE: the `unresolved` rows of the same file and register rows E11, E12, which must still refuse. Scored BLIND by a non-proposer | a NEGATIVE row resolving → RED; the cut lowered until a frozen wrong-work candidate passes → the identity test RED (S1 (c) already fires on `RESOLVE_TITLE_RATIO`) |
| **doi.org content negotiation** before the Crossref → DataCite ladder in `pipeline/litkb/admit/registry.py` | DOIs of agencies neither registry serves (mEDRA, JaLC, KISTI) | survey A: Manubot, VERIFIED in source, licence VERIFIED (LICENSE read) | none in the base today — find one such DOI on the open web and add it to the register as a row FIRST; control: a Crossref DOI already in the register (E11's class) must still resolve through Crossref, and doi.org's record for a DOI both serve must agree with Crossref's | the ladder with the doi.org rung removed → that row refuses; the control resolving through doi.org instead of Crossref → RED |
| **Binding: identifier-in-file ladder, a font-size title test, a post-extraction content gate.** Measured: check 3 rests on title + surname only — the registry's DOI or arXiv id is never passed into `bind()`; `pdf_shape` tests a `%PDF-` header and a `%%EOF` trailer and nothing else; there is no entropy, printable-ratio or minimum-text test anywhere; and the metadata fallback binds a page with ZERO extractable characters at ratio 1.0 on `/Title` + `/Author` alone (latent: every live bind that took the `pdf-title` path has a text layer). Row 235 is a WINDOWING limit (a title split over more lines than the scoring window covers), not a threshold. | stamp-robust binding; `bad-file` detection on every route; the blank-page bind | survey D: pdf2doi's ladder (VERIFIED, licence from setup.py), JabRef's TitleExtractorByFontSize (VERIFIED at a pinned commit; licence ASSERTED), paper-qa's `maybe_is_text` (VERIFIED). Whether the arXiv stamp's font is smaller than the title's on a REAL page is UNMEASURED — measure it on the E25 PDFs first | PREREQUISITE: the corpus title-ratio sweep becomes an instrument under qc/instruments/ writing a CSV under phase4/qc/ (CLAUDE.md §3.4b) — the E25 sweep's per-file output exists at no path and its population has already drifted. Then: `qc/testdata/litkb_binding_stamps/` fixtures via `qc/test_litkb_binding_stamps.py`; the E25 PDFs; 235's filed PDF; a challenge page's bytes (the Sci-Hub attempt detail in `Reports/LITKB_EDGE_RUN_2026-09-21.csv` names the mirrors); a stub PDF with matching `/Title` + `/Author` and an empty page | the content gate given challenge bytes behind a `%PDF-` header → refused, never bound; the stub with matching metadata → `binding-pending`, never `bound`; the ladder given a PDF whose embedded DOI is another work's → refused (auditor-e25's cross-title probe is the shape); a page whose largest font is a running head or journal name (235's cover is the real case) → the font-size candidate refused by check 3's ratio, never bound on font size alone |
| **Both identifiers on one admission**: check 1 requires EVERY passed identifier to confirm, so `admit --arxiv X --doi 10.48550/arXiv.X` refuses although the DOI form confirms, and admitting by the DOI alone stores no arXiv id, so a later arXiv hunt is a duplicate | `Reports/LITKB_RULED_HUNTS_2026-09-21.md` §8 (measured once) | litkb's own code | the ruled run's arXiv rows; negative — 187's confirmed DOI paired with a CONSTRUCTED wrong arXiv id, stated as constructed | an admission storing an identifier no registry confirmed → refused; the constructed pair → refused |
| **HTML snapshot → searchable blocks, live**. A live HTML-only hunt of an unknown work is DONE (row 194); its snapshot holds no blocks because extraction was off | `docs/SCHEMAS.md` "A web source that is a page" proved in replay only | litkb's own code | positive today: 194's existing snapshot run through extraction → searchable blocks (no live fetch needed); negative: the register's URL-HTML-only rows replayed (E06's class); a live unknown page only if S5's scout drops one off | a page with no claimed title, author and year → `refused/incomplete-record`; 194's snapshot with its text emptied → `zero-content`, never searchable |
| **A database home for hunt outcomes** (today the run ledgers are CSVs and `ledger_word` is the one chooser) | `Reports/LITKB_EDGES_2026-09-21.md` §6 names it | litkb's own design | the edge-run ledgers replayed into it, row for row | a state word outside `STATES` → refused by the constraint |
| **Route ordering, blocklist and re-ingest cadences from the ledger**: mirror scoring from attempt rows; `citation_pdf_url` parsing reused on open-access landing pages; a commented static host blocklist; re-ingest cadences as SQL over `acquisition_attempts` | route order; HTML-only OA sources; hosts that never answer; retries that are hand-run today | survey C (SciDownl, paperscraper — VERIFIED; licences ASSERTED) and E (sandcrawler's blocklist and its dump_reingest SQL, VERIFIED; the repository has no LICENSE file) | the Sci-Hub attempt details in the edge-run ledgers; the `no-oa-copy` rows' landing pages; the census before and after | a mirror with no success ranked above one with successes → the scorer's test RED; a host with a success in the ledger placed on the blocklist → RED; a permanently-dead sub-status selected by the re-ingest query → RED |

#### Test-set commands (run from Scripts/, read-only)

```
# the two-tier resolver's POSITIVE set (must resolve) and NEGATIVE set (must still refuse)
py -3.12 -c "import csv;r=list(csv.DictReader(open('../Reports/LITKB_TITLE_HUNTS_2026-09-21.csv',encoding='utf-8-sig')));p=[x for x in r if x['verdict']=='registry-quirk'];n=[x for x in r if x['verdict']=='unresolved'];print('positive',len(p),[(x['tracker_id'],x['title_ratio']) for x in p]);print('negative',len(n),[(x['tracker_id'],x['title_ratio']) for x in n])"
# which field each positive row refuses on today (the author, or the year for tracker 293)
py -3.12 -c "import csv;r=[x for x in csv.DictReader(open('../Reports/LITKB_TITLE_HUNTS_2026-09-21.csv',encoding='utf-8-sig')) if x['verdict']=='registry-quirk'];print([(x['tracker_id'],x['tracker_year'],x['registry_year'],x['author_passed']) for x in r])"
# binds that took the metadata-only path (their page-1 text-layer size is the follow-up query)
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute(\"SELECT count(*) FROM litkb.file_versions WHERE binding->>'source'='pdf-title'\").fetchone())"
```

### S6 — The synthesis: what the literature means for this pipeline

Work
- docs/LITKB_SYNTHESIS_GRAMMAR.md: inputs = the brief's VERIFIED lines + `SCIENCE.md` +
  `decisions.yaml`; output under Reports/syntheses/; every inference sentence ends with
  `[work_key p.N #block]` (a VERIFIED line) or `[own reasoning]`; a closing section of
  decision-shaped recommendations, each tied to its lines.
- `litkb synthesis-check` (K3): sentence coverage; every cited block VERIFIED in the workstream;
  an EXPECTED line cited = FAIL; findings bound to source hashes. Known-bad fixture under
  qc/testdata/litkb_synthesis/. Written by the orchestrating model; Codex reviews against a
  fixed report schema.

Done-state
- (a) the grammar; the checker + tests + fixture; the synthesis for S5's topic; the Codex report.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py synthesis --manifest <manifest>` →
  `sentences_ungraded=0 unlabelled_inferences=0 expected_lines_cited=0 unsupported_attributions=0`.
- (c) provenance laundering: cite a real block that is not among this workstream's VERIFIED uses
  → K3 RED; attach a valid VERIFIED citation to an inference the quote does not support → the
  Codex stage must flag it; drop one `[own reasoning]` tag → K3 RED.

### S7 — Seven nights unattended (ops)

Kam's ruling (2026-09-20): seven nights, STARTED EARLY. S1 installs the nightly smoke task
(see S1 Work) so the nights accumulate while S2–S6 proceed; S7 extends it with the full
`doctor` and reads the log. No calendar cost at the end.

Work
- `litkb doctor`: DB reachable; migration tip == repo tip; dump age < 26 h AND the dump restores
  (a fresh-mtime corrupt dump must fail; see `pipeline/litkb/ops/nightly_dump.py`); worker DBs
  free or leased; MCP server code path == repo HEAD (the post-merge staleness trap); token
  present and valid. Fixture qc/fixtures/litkb_doctor.json mutates each check separately.
- A scheduled nightly task runs `doctor` + a smoke hunt on a known-extracted key + a smoke
  search, appending to a soak CSV under Reports/. The mutation ledger becomes a `check.py` rung
  (live-DB subset opt-in); the harness diffs against its baseline; the tolerated red and the
  census pins are retired or proven passing; `report_path` bounded + its decisions line; the
  drift gate covers `.claude/skills/literature/SKILL.md`; a cold-start test: a Sonnet agent given
  only the repo runs S5's first three steps with 0 questions.

Done-state
- (a) doctor + fixture + tests; the scheduled task; the rung; docs; the soak CSV; the cold-start log.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py soak --log <soak.csv>` →
  `elapsed_hours>=168 missed_scheduled_runs=0 interventions=0 incomplete_runs=0` ·
  `py -3.12 qc/check.py` → GREEN with no tolerated reds · `py -3.12 -m litkb doctor` → all OK.
- (c) each doctor check mutated in isolation → that check RED; a corrupt fresh dump → RED;
  `report_path` containing `..` → refused; a SKILL.md route not in `ROUTES` → the drift gate RED.

---

## Per-session protocol

**First command of every session**, before any hunt or launch:
`py -3.12 qc/instruments/litkb_acceptance.py preflight` → every counter 0
(`stray_tokens migration_mismatch mcp_servers_missing main_not_at_parity soak_stale`). A red
counter is the session's first task, not a note. Then `/mcp` reconnect if the open session
predates the last merge (not measurable by the instrument; it prints the HEAD it checked).
Headless launches: `Reports/LITKB_SCOUT_LAUNCH.md` §4 — bash, a prompt FILE, the first
`ws_open` slug checked within the minute.

Orchestrator = the chat session; ≤ 3 agents. Opus **builder** in its own worktree with its own
`litkb_test_wN` (check it is free first) → Opus **auditor** re-runs every claim from source on a
fresh worker DB (every real defect so far came from an auditor) → fix → `py -3.12 qc/landed.py`
→ commit on `work/<date>-<slug>` → landed per CLAUDE.md §3.1 → Kam applies any migration. Codex
reviews every grammar and is the last stage of every proving run. Worker reports:
`D:\tools\claude-config\jobs\litkb-<session>\<worker>.md`, ≤ 15 lines returned. Migration
numbers reserved in `pipeline/litkb/db/migrations/_reserved.txt` first. Concurrency and model
rules: `litkb-p0-foundation`. Base brief: `docs/LITKB_AGENT_BASE_BRIEF.md`.

**Codex stage** (the adversarial read, last stage of every proving run; built between S1 and S2).
Three commands, not a conversation. `py -3.12 -m litkb review-context <review.md> --out <ctx.md>`
writes the whole block behind every citation — the file that run 2 had by hand — and exits 1 on a
block the workstream cannot see. `qc/instruments/litkb_codex_review.py --review --context --out
<report.json>` builds the prompt from `docs/LITKB_CODEX_PROMPT.md`, runs Codex in WSL read-only
with the prompt on STDIN (`-`, never a re-quoted argument) against
`qc/fixtures/litkb_codex_report.schema.json`, and stamps both files' sha256 over whatever the
model wrote. `py -3.12 qc/instruments/litkb_acceptance.py codex --review --context --report` then
counts `citations_unreviewed verdict_outside_set hash_mismatch overreach unsupported`: the first
three are gates, and `overreach` is a finding the orchestrator rules on, never a failure.
`--mutate N` plants a causation claim on citation N with its quote byte-identical and requires the
report to flag it (`mutation_not_flagged`). **Proven LIVE 2026-09-20** on the run-2 review:
13/13 SUPPORTED unmutated, the planted causation on citation 5 flagged OVERREACH, nothing else
moved (`Reports/LITKB_CODEX_STAGE_2026-09-20.md`; reports with session ids under
`Reports/codex/`). Codex version at proof: codex-cli 0.155.1, prompt on stdin, model-facing
schema derived by the wrapper (strict structured output refuses optional properties).

Inherited hazards: live migrations are Kam's to apply; the MCP server is stale after a merge
until `/mcp` reconnect; agents stall on background jobs (brief foreground polling); usage quota
is Kam's to read. `litkb review-context` opens `litkb_reader`, which the shared pgpass holds for
`litkb` only — against a worker database it fails `no password supplied`, the same credentials
limit `LITKB_REVIEW_GRAMMAR.md` §8 records for `review-check`, and the fix is a pgpass entry,
which is Kam's.

**Relayed designs** (CLAUDE.md §3.4c; binding from S4.5 on). A mechanism read in another
repository is a design until it has run on litkb's rows. The builder of one is never its
proposer; an independent referee scores it on the test set the plan names, positive and negative
rows both; the plan line keeps the word UNVALIDATED until the referee's report is tracked under
Reports/ and the (c) known-bad has fired. A design may not be accepted on numbers it produced
about itself, and a design validated on synthetic input only says so in those words.

Inherited hazards (added 2026-09-21, each one bit a session): `py -3.12 -m litkb` from a worktree
runs MAIN's editable install — use `PYTHONPATH=pipeline` from the worktree's Scripts/; a gate's
exit code is read from the gate alone, never through a pipe (`${PIPESTATUS[0]}`, or run it
alone); one pytest process per worker database, ever (Git Bash `timeout` leaves the Python child
running) — `qc/test_litkb_edges.py` documents `LITKB_TEST_DB=litkb_test_w10`, and a run without
it lands on the default `litkb_test`; a heredoc with apostrophes breaks bash quoting here — write
the script to the scratchpad and run the file.

---

## Worktree disposition (`litkb-worktree-disposition`; **WE DON'T DELETE**)

"Dispose" = vault the token → archive the branch's reports onto main → merge what is owed →
remove the worktree CHECKOUT. Branches and remote refs are kept. Verified before any removal:
`git rev-parse <branch>` equals `git rev-parse github/<branch>`; the root holds no un-vaulted
`.litkb-workstream*` (vault: `D:\edmonds-pipeline\secrets\litkb-tokens\`). Listing: `git worktree list`.

| branch | class | owed to main | disposition |
|---|---|---|---|
| `work/20260915-access-layer` | report-only (code merged as migrations 0018/0019) | 2 reports | vault `op-test-1` → archive reports (the force-added `_derived/promotions/*` stays on the branch) → remove checkout |
| `work/20260919-crossref-proposer` | code | yes — `resolve_by_raw_search` | **merge**; test asserts it never auto-confirms (`litkb-crossref-raw-proposer`) |
| `work/20260915-embeddings` | code + reports | new package; own verdict FAIL vs floors | archive reports; code stays on its branch |
| `work/20260915-held-queue` | report-only (DB-side work) | report + CSV | vault `held-queue` → archive → remove checkout; rows feed S3's fixture |
| `work/20260919-ligature` | instruments + report | overruled by `litkb-ligature-repair`, which cites it | cherry-pick the instruments + report files → remove checkout |
| `work/20260915-linkage-review` | report-only | report; its §7 proposals unimplemented | vault `linkage-review` → archive → remove checkout; §7 feeds S3 |
| `work/20260919-pix2tex` | report + crop PNGs in scratch | report only (`litkb-second-formula-decoder`) | `git show` the report onto main (PNGs stay on the branch) → remove checkout |
| `work/20260919-referee-items123` | report-only, **load-bearing** | three rulings cite it | archive to main (non-optional) → remove checkout |
| `work/20260915-refmatcher` | eval harness + report | superseded by the crossref branch | archive report (duplicate gold stays on the branch) → remove checkout |
| `work/20260915-splink` | eval harness + gold; DIRTY at survey time | nothing on main; no ruling | commit the uncommitted re-run on its branch → archive report → remove checkout |
| eight remote-only refs fully merged (`git log main..github/<ref>` empty) | — | — | keep; nothing to do |

---

## Open-items register (kept short; the dated appendix holds the survey)

Owned by a session above, or parked beyond the line — nothing lives only here. When a session
lands, delete its rows. Rows for S2 and the Codex stage were deleted 2026-09-21 (both landed);
the S7 row's "tolerated red" clause was deleted the same day — the named test was red only in
fresh checkouts, by construction, and `qc/test_experiments.py` skips gitignored products since
2026-09-21.

| item | owner |
|---|---|
| no extraction queue, no fail-closed page cap, zero-content/multi-file works, cross-page `page_no`, metrics in JSONL, superseded run sets, the `book` residue class, a quarantine with no database state; the no-text-layer scans; the L4 formula re-crop of Reynolds_2000 and Montgomery_1991 never ran | S4 |
| `blocked` in no route's `DEAD_STATUSES`; registry transients re-run by hand; the arXiv-client question; Crossref `relation` dropped and its yield unmeasured; a different DOI called a duplicate at 0.70; no ISBN scheme; a long creator string crashes the key rule; no served-bytes hash on the attempt row; a re-served bad file re-quarantined, never skipped; a refused-duplicate landing left unowned on disk; no second-session refuse verb; the approve guard never made to fire | S4.5 |
| run-2 review fails the tightened grader; no run protocol; the promoted tracker-era metadata; no per-hunt time budget; no rule retiring a superseded drop-off; the two builds the rulings assign to S5 (ISBN → md5; registry-over-claim on a human's say-so) | S5 |
| no synthesis grammar or K3 | S6 |
| no doctor; ledger not a `check.py` rung; harness `run_one` calls any failure FIRED (no per-row baseline diff); `report_path` unbounded; nightly dump task points at an old worktree | S7 (dump task: Kam, now) |
| the survey's remaining designs and litkb's own: two-tier resolution, doi.org negotiation, the binding ladder + content gate (with the sweep instrument as its prerequisite), both identifiers on one admission, snapshot → blocks live, a database home for hunt outcomes, route ordering from the ledger | after S5 (table above) |

Adjudicated 2026-09-20 (S0, read-only against code): of the survey's twelve POSSIBLY-STALE items
CLOSED R4 A5 B7 E6 E11 O9 O11 (A5 had misnamed the ref — `::b10` is Hall_1985, Burnicki's two
cases are already pinned; O6 had misnamed the test); OPEN B5 and E13 landed in S3, E10 → S4, O6 → S7,
O8 → S7, rows above.

---

## The survey's verdicts (2026-09-21) — with what each rests on

Five Opus crawlers read external source and litkb's own files (synthesis and reports A–E under
D:\tools\claude-config\jobs\litkb-s3-wrap\github-survey); a sixth, read-only auditor re-checked
the survey against the tree on 2026-09-21 (jobs/litkb-plan-revision/survey-audit.md). This table
is the plan's record of what each verdict rests on, so a session scheduling one knows what it is
trusting. **VERIFIED** = the crawler read the mechanism in the repository's source at the commit
it names; **LIVE** = a live API call; **ASSERTED** = a badge, a README, a package field or a page,
not the source. Every external mechanism is ONE crawler's unreplicated reading; none has been run
on litkb's rows (CLAUDE.md §3.4c). External file names are written without backticks — they are
not files of this repository. Every litkb citation the survey made was re-checked against the
current tree and holds; report D was written after the E25 change and cites the post-change code.

| sub-problem | mechanism | where the crawler read it | commit · licence | status | litkb gap (measured) | verdict → scheduled |
|---|---|---|---|---|---|---|
| A resolution | two-tier title/author rule (author match required below a title-similarity cut, waived above it) | paper-qa, clients/semantic_scholar.py | pinned · Apache-2.0 ASSERTED (A: "not read") | VERIFIED | `judge_candidate` in `pipeline/litkb/admit/resolver.py` is a conjunction of FOUR legs (ratio, first-author family, year ±1, year present); the subtitle is the only claim disagreement admission records as a discrepancy (`subtitle_discrepancy` in `pipeline/litkb/admit/registry.py`) — every other mismatch refuses in SQL | ADAPT (the tiering, not the metric) → after S5 |
| A | doi.org content negotiation | Manubot, manubot/cite/doi.py | pinned · BSD-2-Clause-Plus-Patent VERIFIED (LICENSE read) | VERIFIED | the ladder in `pipeline/litkb/admit/registry.py` is Crossref then DataCite, no doi.org rung | ADOPT → after S5 |
| A | biblio-glutton's averaged record distance | biblio-glutton, LookupEngine.java | pinned · Apache-2.0 ASSERTED (badge) | VERIFIED | — | report A says ADAPT as a tie-break; the synthesis body drops it. Not scheduled: an averaged vote cannot say which field it forgave |
| A | "keep more than the top candidate" | glutton's pairwise ranking | as above | VERIFIED | the PREMISE is wrong — `resolve_doi` judges every candidate; only the refusal DETAIL is reduced to the highest-ratio one | reduced to "keep per-candidate judgements in `resolver_detail`" → after S5, with the two-tier rule |
| B identity | Crossref `relation` as a typed edge, with a third state for an empty field | the Crossref API (no repository) | n/a | LIVE (the field exists; a real bioRxiv preprint returned it EMPTY) | `parse_crossref` in `pipeline/litkb/admit/registry.py` never reads it; no raw response is stored, so a backfill is one call per DOI; the yield over this corpus is UNMEASURED | ADOPT, probe first → S4.5 item 2 |
| B | the arXiv record's DOI field | Manubot, manubot/cite/arxiv.py (the field); export.arxiv.org (the behaviour) | pinned · VERIFIED | VERIFIED for the field; ASSERTED for live behaviour (the crawler's call returned an empty body) | `arxiv_record` parses title, author, published only | ADOPT → S4.5 item 2 |
| B | identifier-first duplicate ordering; type-scoped ISBN; ISBN-13 canonicalisation | JabRef, DuplicateCheck.java; Zotero, duplicates.js; Manubot, isbn.py | JabRef pinned in A and D, UNPINNED in B · MIT from the GitHub API, LICENSE not read; Zotero PINNED in B with AGPL-3.0-or-later read from the file header (A, C, D, E read Zotero unpinned and asserted its licence) | VERIFIED (call sites; the ISBN helper bodies not read — a submodule) | `_title_duplicates` (migration 0013) calls a different DOI a duplicate at 0.70/±1 y; no `isbn` ref scheme (`REF_REFUSALS` in `pipeline/litkb/hunt.py`) | ADAPT → S4.5 item 2 (design only from Zotero — AGPL) |
| B | a corporate-author field mode | Zotero, duplicates.js | pinned in B · AGPL read from header | VERIFIED | `make_key` in `pipeline/litkb/admit/front.py` crashes on a LONG creator string, not a corporate one — the discriminator is length | ADAPT as a length rule → S4.5 item 2 |
| B | OpenAlex `locations[].version` | the OpenAlex API; pyalex not cloned | n/a · pyalex MIT ASSERTED | LIVE for the model | — | not adopted: the relation edge suffices |
| B | recordlinkage / dedupe | — | — | — | — | IGNORE: needs labelled pairs; an unexplainable verdict fails §3.4c |
| C acquisition | per-host back-off, Retry-After cap, 403 never retried, park-and-continue | Zotero, attachments.js | UNPINNED (branch head) · AGPL ASSERTED (C: "LICENSE not fetched") | VERIFIED | `DEAD_STATUSES` in `pipeline/litkb/acquire/run.py` keyed on the status word; `blocked` in no set; `at` unused by the skip decision | ADAPT the mechanism, never the code → S4.5 item 1 |
| C | mirror scoring from persisted failure rates | SciDownl, core/chooser.py | pinned · LICENSE presence ASSERTED | VERIFIED | a fixed mirror order (`SCIHUB_MIRRORS` in `pipeline/litkb/config.py`) | ADAPT → after S5 |
| C | `citation_pdf_url` with landing-page cookies + Referer | paperscraper, pdf/pdf.py | pinned · MIT ASSERTED | VERIFIED | `pdf_link` in `pipeline/litkb/acquire/scihub.py` already parses it — reuse on OA pages | reuse → after S5 |
| C | retry only 500/504; negative examples (PyPaperBot, unpywall) | paper-qa; PyPaperBot; unpywall | pinned | VERIFIED | — | none refuses a known-bad hash — nothing to adopt |
| D binding | embedded-identifier ladder (metadata → text → filename), each candidate validated at the registry | pdf2doi, finders.py, patterns.py | pinned · MIT from setup.py, LICENSE not read | VERIFIED | the registry id is never passed into `bind()` | ADAPT the ladder, not the Google fallback → after S5 |
| D | font-size title extraction | JabRef, PdfContentImporter.java | pinned · MIT ASSERTED | VERIFIED | — ; whether a stamp's font is smaller than a title's on a REAL page is UNMEASURED | ADAPT, measure first → after S5 |
| D | entropy + stub content gate | paper-qa, utils.py and docs.py | pinned · Apache-2.0 ASSERTED | VERIFIED | `pdf_shape` in `pipeline/litkb/acquire/store.py` tests a header and a trailer only; no text gate exists; the metadata fallback binds an empty page | ADOPT → after S5 |
| D | throw on a zero-text page | Zotero, recognizeDocument.js | UNPINNED · AGPL | VERIFIED | `bind_any_with_ocr` is AHEAD (OCR where there is nothing to read) | IGNORE as code; the ordering lesson only |
| D | pdftitle | — | GPL-3 | — | — | IGNORE as a dependency |
| E outcomes | the content hash on the attempt row; rejected-hash lookup; `blocked` sub-types; a commented static host blocklist; re-ingest cadences as SQL over the ledger | IA sandcrawler, ingest_file.py and its SQL | pinned · NO LICENSE FILE at the root (E: asserted internal) | VERIFIED (the Kafka layer ASSERTED) | `record_attempt` has no sha column; `_quarantine/` has no database state; `REASONS["blocked"]` is 403 · challenge · quota-stop | ADAPT → S4 (the state) + S4.5 item 3 (the ledger); the blocklist and cadences → after S5 |

Asserted only, per the synthesis and the audit: the Zotero commit outside report B; the licences
of Zotero (outside B), paper-qa, JabRef, paperscraper and sandcrawler; star and contributor
counts; arXiv's live behaviour; sandcrawler's Kafka layer. Not surveyed: Wikidata/OpenRefine
reconciliation, refextract/anystyle/citation.js, habanero/crossrefapi. Defects in the survey
itself, corrected above: it counted the E24 test set at ratio 1.00 when the tracked report says
≥ 0.85, and it described the resolver as keeping only the top candidate. The survey's census
cells were a snapshot the ruled run has since moved — the plan cites the census command, never a
cell.

---

## Documents retired into this one (`litkb-plan-home`)

`WORKPLAN.md` litkb section → pointer · jobs STATE.md → pointer · `LITERATURE_KB_DESIGN_2026-09-13.md`
§14 status rows → pointer · memory `literature-knowledge-base-design` → pointer + operating
facts. The audit trail of the operational proving run stays where it is:
`D:\tools\claude-config\jobs\litkb-operational\` and `Reports/LITKB_OPERATIONAL_PROVING_RUN_2026-09-20.md`.

---

<!-- drift-gate:dated-begin -->
## Appendix — the 2026-09-20 survey (a dated record, not a current claim)

Three read-only explorers and a Codex review measured `main` @ 89bd989 on 2026-09-20. This is
what the ladder was built from; it is not maintained.

- Proving run 2 (`scratch/proving_run2_prompt.md` STEP 2) pre-named three extracted works and
  four exact `expected_claim` strings. Open-web discovery and PDF acquisition were never
  exercised by the operational definition.
- `cmd_discover` (`pipeline/litkb/commands.py`) runs a Crossref title search into candidate rows
  and stops. `ref_kind` in `pipeline/litkb/hunt.py` turns every non-URL into `doi`. The resolver
  has `resolve_doi(title, surname, year)`; hunt does not call it. `hunt_request.ref_scheme`
  (migration 0023) has no `title`. Snapshot admission exists (`pipeline/litkb/admit/front.py`);
  hunt's URL path refuses non-PDF bytes. `ROUTES` = open_access, annas, scihub
  (`pipeline/litkb/acquire/run.py`); manual `--from-file` exists; automated browsing does not.
  Binding cap `OCR_BIND_MAX_PAGES=400` (`pipeline/litkb/admit/binding.py`); no extraction cap.
  No staging reaper. Sci-Hub failover iterates a static mirror pair.
- Tests: 26 `qc/test_litkb_*.py` files, ~950 test functions; the mutation ledger in
  `qc/instruments/litkb_p2_mutations.py` (369 rows) is not a `check.py` rung, though its static
  coverage self-check runs under pytest (`qc/test_litkb_harness_sites.py`).
- Ten side worktrees; five report-only, five code-bearing; only crossref-proposer clearly owed;
  three checkouts (access, heldq, linkrev) held `.litkb-workstream` tokens not in the vault.
- Four documents claimed to be the living state and disagreed on merge status, held-work
  counts, worktree counts and MCP scope. Roughly ten numbering schemes were in use.
- POSSIBLY-STALE items to verify against code in S0 (from the docs survey): R4 record_use
  CRLF (migration 0026 should close it); A5 Burnicki b10 gate false positive; B5 `litkb_acquire`
  strips `detail`; B7 acquisition runs no OCR pass; E6 duplicate `page_frames`; E10 Reynolds /
  Montgomery L4 re-crop; E11 cropbox shift on 16 pages; E13 a file bound at a staging path; O6
  tolerated red `crown_state_model`; O8 harness `run_one` has no baseline diff; O9 red
  `test_docs_match_code` naming an unmerged report; O11 census pins.
- Codex review session `01a0bfce-ab75-7b80-88fd-9cfd9eba06bf` (read-only, WSL) supplied the
  acceptance-instrument shape, eight missing known-bad inputs, six unowned edge cases, the S2
  ordering, and the factual corrections folded into the ladder.
<!-- drift-gate:dated-end -->

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
- Git landing rules are CLAUDE.md §3.1 and are not restated here.

---

## Where we are

Update this block only. Everything else in the file changes when a session lands.

- **Finish line:** `litkb-finish-line` — topic → graded review → synthesis, unattended.
- **Current session:** S0 (one tree, one plan). Started 2026-09-20 on
  `work/20260920-litkb-workplan`.
- **Next:** S1 (the front door). Entry condition: S0 landed; paper-search MCP registered in
  `.mcp.json` (see S1).
- **Rulings 2026-09-20:** `litkb-k2-no-seeding` decided (no seeding); S7 soak = seven nights
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
4. writes a review that passes `litkb review-check` (K1) with K2 fired under whatever
   `litkb-k2-no-seeding` decides, checked by a different model family at 0 overreach;
5. writes a synthesis — what the literature implies for THIS pipeline — where every inference
   cites a VERIFIED brief line or is labelled as the model's own reasoning, graded by K3;
6. leaves `py -3.12 qc/check.py` green with no tolerated reds and `litkb doctor` green across
   seven scheduled nights.

Beyond the line, on Kam's track (so no session re-proposes them): promotion on live
(`litkb-operational-verdict`), the vector leg (P7 bake-off report on `work/20260915-embeddings`),
citation anchoring and the second gate path (`litkb-crossref-raw-proposer`), the
preprint↔published relation scheme (`Reports/LITKB_IMPROVEMENT_REVIEW_B_2026-09-16.md` gap 3),
MinerU/native-layer stages (`LITERATURE_KB_DESIGN_2026-09-13.md` §14).

---

## Vocabulary

Loop stages, in order: **discover → drop-off → resolve+admit → acquire+bind → extract+ingest →
search+record → brief+review → synthesis → promote**, plus **ops**. Sessions **S0–S7**.

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
`disposition` (S0), `scout` (S1), `first-work` (S2), `edges` (S3), `readability` (S4), `run`
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
| S5 | proving run 3 from the open web, graded against a frozen manifest | 1 | one headless run; Kam's topic |
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

Kam: rule on `litkb-k2-no-seeding`; re-register the nightly dump task.

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
  under Reports/ (LITKB_SOAK). The full `doctor` joins it in S7; the row schema is fixed here so
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
  `grep -c 'browser last' .claude/skills/literature/SKILL.md` → 0.
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
- An `extraction_jobs` queue (design §12.3–12.5; lease + resume; migration number reserved).
  Per-file completeness: a work with an extracted file AND an unreadable file, or a native file
  with zero blocks, is classified, never silently "extracted".
- Drain as far as the session allows, locally (WSL GROBID + T2000 Docling; litkb is local-only,
  `litkb-p0-foundation`). Residue classes: `no-file-any-route` · `scan-needs-ocr` ·
  `over-page-cap` · `zero-content` · `bad-file` · `refused-registry`.
- Scan OCR inside the queue under the measured VRAM policy; an **enforced, fail-closed**
  extraction page cap (page-range support exists in `pipeline/litkb/extract/docling_worker.py`; a
  cap does not); the book policy (Kam rules; the fixture row records it); `page_no` for
  cross-page paragraphs (citation integrity); metrics into `extraction_runs.metrics`; retiring
  the superseded run sets as a deliberate op. Formula LaTeX stays `unverified`
  (`litkb-second-formula-decoder`).

Done-state
- (a) the migration + worker; a readability CSV + report under Reports/; tests + ledger rows.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py readability --manifest <manifest>` (all
  workstreams in the manifest, not main only) → `unclassified_acquired_files=0 stale_leases=0
  duplicate_blocks=0 resumed_content_hash_mismatches=0`.
- (c) kill mid-batch, rerun → block **content hashes** equal, 0 duplicates; a lease token mutated
  so an expired worker commits after reassignment → the ownership gate goes RED; a cap+1 PDF
  whose page-count probe FAILS → extraction refused (fail-closed), not started; a scan with OCR
  off → `scan-needs-ocr`, never "extracted, 0 chars".

Kam: the book ruling; the OCR strategy (recommendation: page-range chunks on the T2000).

### S5 — Proving run 3: a topic becomes a graded review, unknown works included

Work
- `litkb review-context <review.md>` exports each cited block's text so Codex (WSL, no psycopg)
  reads a file. docs/LITKB_RUN_PROTOCOL.md: prompt = topic + slug only; a test fails on any work
  key in the template; attempt limit and rerun policy fixed BEFORE launch; exhaustion →
  UNDETERMINED, never a quiet extra try. Run 2's review re-graded under the tightened grader and
  marked historical.
- THE RUN: headless, topic named by Kam; scout → hunts with real acquisitions → record → brief →
  writer → `review-check` → Codex. K2 as `litkb-k2-no-seeding` decides. An expectation can go
  UNCONFIRMED without its paper being acquired; the counters separate the two.

Done-state
- (a) the review under `Reports/reviews/`; a proving-run-3 report + frozen manifest under
  Reports/; the exporter + tests; the protocol doc.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py run --manifest <manifest> --audit` →
  `distinct_new_works>=5 bound=extracted=searchable missing_dropoff_outcomes=0 K1=PASS K2=FIRED
  claims_ungraded=0 overreach=0 operator_interventions=0 migrations_during_run=0`.
- (c) the grader on a one-character mutation → FAIL (byte verification, re-fired not assumed); a
  claim mutated to assert **causation** while keeping its valid descriptive quote → the Codex
  stage must flag it (overreach is the K1 escape no deterministic grader closes); the protocol
  test fails on a pre-named work.

Kam: name the topic; apply migrations BEFORE the run, none during.

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

Orchestrator = the chat session; ≤ 3 agents. Opus **builder** in its own worktree with its own
`litkb_test_wN` (check it is free first) → Opus **auditor** re-runs every claim from source on a
fresh worker DB (every real defect so far came from an auditor) → fix → `py -3.12 qc/landed.py`
→ commit on `work/<date>-<slug>` → landed per CLAUDE.md §3.1 → Kam applies any migration. Codex
reviews every grammar and is the last stage of every proving run. Worker reports:
`D:\tools\claude-config\jobs\litkb-<session>\<worker>.md`, ≤ 15 lines returned. Migration
numbers reserved in `pipeline/litkb/db/migrations/_reserved.txt` first. Concurrency and model
rules: `litkb-p0-foundation`. Base brief: `docs/LITKB_AGENT_BASE_BRIEF.md`.

Inherited hazards: live migrations are Kam's to apply; the MCP server is stale after a merge
until `/mcp` reconnect; agents stall on background jobs (brief foreground polling); usage quota
is Kam's to read.

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
lands, delete its rows.

| item | owner |
|---|---|
| no autonomous topic → drop-off workflow; `hunt` classifies rather than validates refs; no `title` ref scheme | S1 |
| unknown-work handoff never exercised end to end; two acquisition provenance shapes | S2 |
| terminal-state vocabulary not closed; HTML-only, two-DOI works, staging orphans, `absent` ambiguity, `litkb_acquire` strips `detail` (the MCP wrapper drops the whole dict), the approve path never run, Kam's held-row rulings; files still bound at `_litkb_staging/incoming/*.download` paths (the 2026-09-16 CSVs list sixteen; refile/rebind path needed — a retry returns `duplicate-held`) | S3 |
| no extraction queue, no fail-closed page cap, zero-content/multi-file works, cross-page `page_no`, metrics in JSONL, superseded run sets, the book; the L4 formula re-crop of Reynolds_2000 and Montgomery_1991 never ran | S4 |
| Codex cannot read block context; run-2 review fails the tightened grader; no run protocol | S5 |
| no synthesis grammar or K3 | S6 |
| no doctor; ledger not a `check.py` rung; harness `run_one` calls any failure FIRED (no per-row baseline diff); the tolerated red is `test_experiments::test_pointer_paths_resolve[crown_state_model]` — an untracked CSV named in the yaml's outputs, not a litkb test; `report_path` unbounded; nightly dump task points at an old worktree | S7 (dump task: Kam, now) |

Adjudicated 2026-09-20 (S0, read-only against code): of the survey's twelve POSSIBLY-STALE items
CLOSED R4 A5 B7 E6 E11 O9 O11 (A5 had misnamed the ref — `::b10` is Hall_1985, Burnicki's two
cases are already pinned; O6 had misnamed the test); OPEN B5 → S3, E13 → S3, E10 → S4, O6 → S7,
O8 → S7, rows above.

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

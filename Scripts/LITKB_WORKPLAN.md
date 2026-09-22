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
- **Current session (2026-09-22, the same chat that landed the 2026-09-21 revision):** Kam set the
  acquisition target (`litkb-coverage-target`) and asked for a survey of how other codebases get PDFs
  from every free source and extract them, with multi-engine agreement for OCR and LaTeX. Two rounds
  ran — eleven and then six Opus crawlers by source class and extraction layer, two Codex forum
  searches in round one (round two's Codex pass died on an exhausted quota and is OWED), a blacklist of
  every URL between rounds, a synthesizer each round — and the orchestrator measured the ledger's own
  miss rows against the resolvers, read-only. The record is
  `Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md` (its §M the measurements, §1 the ladder by stage,
  §5 the extraction ladder, §6 the coverage projection; every URL the crawlers visited in
  `Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22_urls.csv`). What changed in this
  file: S4.5 was rewritten as part 1 of the ladder (the substrate, the ledger vocabulary, the free
  rungs of Stages A–C and E); S4.6 (grey literature, books, the shadow tier under the existing grant,
  credentials behind their rulings, the coverage instrument) and S4.7 (extraction agreement: the CMap
  repair layer, text tiers, scans measured before adopted, math verified without ground truth) were
  inserted; the improvements table lost the rows the sessions absorbed; `decisions.yaml` gained the entries
  this session raised (`grep -c '^  - id: litkb-' decisions.yaml` counts them all) — `litkb-coverage-target`
  decided from Kam's words, and `litkb-coverage-definition`, `litkb-institutional-access`,
  `litkb-shadow-hosts`, `litkb-tdm-keys`, `litkb-crc-book`, `litkb-s47-colab-queue` raised open (all
  ruled the same day — the rulings bullet below). The
  2026-09-21 revision's record stays `Reports/LITKB_PLAN_REVISION_2026-09-21.md`. Round 3 of the survey
  (the shadow-library linkage map and the identifier crosswalk; record `Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md`, its §M the measurements)
  landed the same day and rewrote S4.5 item 1's identifier model, Stage A's zero-request derivations and
  offline membership table, Stage B's fan-out order and closure rule, and S4.6's Stages F and G; round
  4 over the loop's other stages landed the same day (record `Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md`; its header table is the
  measured defects, its §1 the per-stage changes with local test sets, its §4 the build waves) and
  rewrote S5's entry conditions, S6, S7, S4.5's replay item and the after-S5 table; several of the
  plan's own known-bads were found DEFEATED as written and are rewritten below. Codex's GitHub pass
  has died on quota in every round since the first and is owed for each.
- **The honest number, as the survey grades it** (its §M is MEASURED on litkb's rows by the probe
  instruments under `qc/instruments/`, whose CSVs sit under phase4/qc/; its §6.3 is an EXTERNAL
  self-reported figure from a review of the same shape): of the ledger's open-access misses, litkb's
  own resolver answers for the Elsevier bronze rows with their landing page, Semantic Scholar supplies
  free arXiv siblings for a few IEEE and Springer papers, a dead author copy is in Wayback (its
  sibling on another host never was), and everything else is a paywall page or a token-gated
  endpoint. The external review reached about 86 percent by legitimate automated means; the gap
  to the target is closed by rulings, not by more open-access indexes.
- **Rulings 2026-09-21** (ids): `litkb-book-policy`, `litkb-sibling-edition`,
  `litkb-registry-over-claim`; the register carries E20–E24 as executable rows and E25 as a ruled
  non-hunt row, no row held —
  `LITKB_TEST_DB=litkb_test_w10 py -3.12 qc/instruments/litkb_acceptance.py edges --manifest ../_derived/edges/rulings-manifest.json --replay`
  → `state_or_reason_mismatches=0 tracebacks=0 held_for_ruling=0` (from Scripts/; `--replay`
  EXECUTES the register against the named worker database — one process on that database at a
  time, like pytest).
- **Next, in order:** (1) **S4 run 3 — Kam launches it himself** from a new terminal window:
  `wt.exe -w new "C:\Program Files\Git\bin\bash.exe" -lc /d/edmonds-pipeline/treedata/_derived/s4/launch-s4.sh`
  (`_derived/s4/s4-prompt.txt` matches the "### S4" block; `LITKB_SESSION=s4-run3`; workstream slug
  `readability-2`). Runs 1 and 2 are PARKED untrusted on
  `github/archive/2026-09-21-litkb-s4-{q1,q2,r}-untrusted` — nothing merged, no migration applied,
  no `extraction_jobs` table exists; their one live trace is the `readability-1` workstream row,
  which is nobody's. `state='open'` is not a signal: every workstream row reads `open`
  (`SELECT state, count(*) FROM litkb.workstreams GROUP BY 1` as `litkb_reader`) because nothing
  ever closes one. Entry condition: the preflight command in "Per-session protocol", every counter
  0. Its kit was regenerated FROM SCRATCH on 2026-09-22 from the "### S4" block (Kam: "i want to start
  S4 from scratch"); the patched kit is archived beside it. (2) **S4.5**, launched by KAM and by nobody
  else (`litkb-session-launch-authority`, 2026-09-22: a session never launches a session) — S4 ends by
  WRITING _derived/s4-5/ (the prompt from the "### S4.5" block, mcp.json with LITKB_SESSION s4-5, the
  launch script) and STOPPING; workstream slug `ladder-1`, the way S4's is
  `readability-2`, so the launch is verified by EFFECTS on that slug's workstreams row) — it now carries the Sci-Hub workaround's
  first rung (item 5b: freeze gate, bban, the three route fixes), pulled forward from S4.6 on the
  2026-09-22 diagnosis because the fix is the ledger vocabulary S4.5 owns. (3) **S4.6**, (4) **S4.7**, each launched
  by Kam from the kit the session before it wrote; (5) **S5** once its entry condition is met, launched
  by Kam. Then S6, S7. No session launches the next: it writes the kit and stops.
- **Ops residue, nobody's ruling** (`Reports/LITKB_RULED_HUNTS_2026-09-21.md` §9, re-measured
  2026-09-21): the fetched files of the ruled run's URL rows sit in `_litkb_staging/filed/` with no
  `file_versions` row — 187's protocol PDF and both copies of 235's report — UNBOUND; the reaper
  counts them `owned` because a refused admission's checks name them (`py -3.12 -m litkb reap --dry-run`
  → `orphans=0`), so nothing quarantines them and nothing binds them either (S4.5 item 1 is the
  landing fix; 235's manual admission needs a second session's sign-off and check 3 measures 0.80 on
  its five-line cover — **do not lower 0.85**). 194's proposal is to be REFUSED by a second session
  (its page holds no document) — and NO refuse verb exists for a `proposed` admission: S4.5 item 1
  builds it. The arXiv rows of the ruled run
  (`grep -c ',registry-transient,' ../Reports/LITKB_RULED_HUNTS_2026-09-21.csv`) re-run when arXiv
  answers 200; whether litkb's own client is the defect is UNDETERMINED and S4.5 item 1 measures it.
  The E25 `.download` files sit at the root of `_litkb_staging/`, outside the reaper's walk. The
  drop-offs of workstream `title-hunts-1` stand `open` beside `ruled-hunts-1`'s for the same tracker
  rows; no rule retires the superseded one (S5 protocol work). Codex's round-two GitHub pass and its
  adversarial read of THIS revision are owed when its quota returns (an Opus adversary stood in).
- **Rulings 2026-09-22** (ids; Kam ruled the whole open list in one message, recorded verbatim in
  each entry): `litkb-coverage-target` · `litkb-coverage-definition` · `litkb-institutional-access`
  (none) · `litkb-shadow-hosts` (all four tiers, offline dumps are data) · `litkb-tdm-keys` (Elsevier only, key in place — valid for Scopus, refused by every ScienceDirect
  endpoint as configured; no Springer key) ·
  `litkb-s47-colab-queue` (T4, unbounded) · `litkb-crc-book` · `litkb-scihub-parked` ·
  `litkb-blocked-works-grade` · `litkb-e23-residue-copies` · `litkb-tracker-corrections` ·
  `litkb-from-file-version-state`; `litkb-scihub-parked` was then REVERSED the same evening (not
  parked — a workaround is attempted, S4.6 Stage G). Accepted recommendations outside the registry: S4 runs the
  reference stage detached over every file with blocks and runs classical OCR on the T2000 first
  (vision-language OCR is S4.7's); the S4 launch kit's work key is not a violation (the bed names
  works by design; the seeding guard protects S5); S5's topic, unless Kam renames it before launch:
  label transfer across years under seasonal difference.
- **Sci-Hub, diagnosed 2026-09-22** after the reversal: the route's zero was sampling plus
  mislabelling (19 of its 22 DOIs post-date the freeze; misses booked `blocked` and retried forever),
  and the corpus is open from here — bban served 73/104 of the pre-2022 no-file backlog on one
  keyless HEAD (`phase4/qc/litkb_acq_probe_bban.csv`). S4.6 Stage G carries the measured ladder.
- **Implementation map of 2026-09-22's changes, by session** (nothing waits on a ruling): S4 —
  unchanged in scope; its launch kit carries the ruled ids and the key facts. S4.5 — item 1 (identifier
  model, refuse verb, operator-bind gate), item 2 (vocabulary incl. `not_in_corpus`, challenge at any
  status, `blocked` dead), item 5b (freeze gate, bban, route fixes), item 7 (hermetic replay), the (b)
  counters. S4.6 — Stage G (LibGen.li, mirrors last, dead fronts named), Stage H (Elsevier gated on
  a ScienceDirect 200, no Springer, no institutional profile), the coverage gate under definition (b).
  S4.7 — the T4 queue approved. S5 — entry conditions from the round-4 defects, the topic, the
  pre-run tracker edits. S6/S7 — as rewritten by round 4.
- **Kam-side, still open:** nothing in `decisions.yaml` — `litkb-colab-page-boundary` was decided
  2026-09-22 on the orchestrator's judgement (strips, never whole pages; Kam: "Implement your best
  judgement on S4.7"), and `litkb-session-launch-authority` records that only Kam launches a session; the nightly-dump task re-registration
  (below) is an action, not a ruling; the Elsevier key is in place but ScienceDirect refuses it as
  configured, re-keyed once with the same answer — Elsevier API support is the other open action (Stage H).
- **Rulings 2026-09-20:** `litkb-k2-no-seeding` decided; S7 soak = seven nights started in S1. Kam
  re-registers the nightly-dump scheduled task (Windows task name litkb-nightly-dump) against the
  merged tree: `py -3.12 -m litkb.ops.nightly_dump --install-task`.

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
relation scheme, listed here until 2026-09-21, is now S4.5 item 1 under `litkb-sibling-edition`.

---

## Vocabulary

Loop stages, in order: **discover → drop-off → resolve+admit → acquire+bind → extract+ingest →
search+record → brief+review → synthesis → promote**, plus **ops**. Sessions **S0–S7**, plus
**S4.5**, **S4.6** and **S4.7** (inserted 2026-09-21 and 2026-09-22 between S4 and S5; written with
a point because the plan gate recognises a session heading by `### S<digits>`, so each is graded as
an S4 block).

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
`disposition` (S0), `scout` (S1), `first-work` (S2), `edges` (S3), `readability` (S4), `hardening` (S4.5), `ladder` (S4.6), `agreement` (S4.7), `run`
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
| S4.5 | the substrate (back-off, identity, hash, refuse verb), the ledger vocabulary, and the free rungs of Stages A–C and E — the survey's measured free ceiling converts; every miss typed | 2–3 | S4's quarantine state; an independent referee per rung class |
| S4.6 | grey literature, books, the shadow tier under the existing grant, credentials behind their rulings; the coverage instrument prints the number against `litkb-coverage-target` | 2 | `litkb-institutional-access`, `litkb-shadow-hosts`, `litkb-tdm-keys`, `litkb-coverage-definition` |
| S4.7 | the CMap repair layer, text in tiers, scans measured before adopted, math verified without ground truth | 2 + Colab for the vision-language rungs | gold pages for the scans; Colab spend by name |
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
  (`pipeline/litkb/acquire/store.py`) writes status and sha into the FILENAME and NOTHING else — no
  code reads that name back, and the `.reason.json` sidecar is written by `quarantine_new`, the
  challenge path, alone, so the four acquisition callers in `pipeline/litkb/acquire/run.py` and
  `pipeline/litkb/hunt.py` leave no
  machine-readable copy at all (S4.5 item 8 makes every quarantine write one);
  `file_versions.status` already allows `quarantined` (migration 0001) and has never held it;
  `file_versions.state` has no such value; a refused file is invisible to `litkb_work`. S4 gives
  every file the classifier refuses (`bad-file`, `zero-content`) and every download the
  acquisition guard quarantines a database row — a status plus the sha256 of the refused bytes
  plus the reason, never a directory alone. Reserve a migration number first if a column or table
  is needed. S4.5 item 1 reads this state to refuse re-served bytes.
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
  classification, never a refusal; the E20 book if a copy arrives (`litkb-e23-residue-copies`). The REFERENCE stage of extraction
  (stage 6, `pipeline/litkb/extract/references.py`) has run on a small fraction of the files with
  blocks (`Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.2) — on that measured slice every
  anchor its resolved DOIs could reach is already made, so anchoring downstream is coverage-bound on
  the slice, and whether it stays so is what the full run measures. The drain runs the stage as far as
  the session allows and REPORTS `files_without_reference_stage` and the anchor rate against its real
  denominator; running it over every file is a wall-clock spend the record marks as Kam's to approve
  (its §1.2 R4), named in this block's Kam line.
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
  quarantined_without_db_state=0 over_cap_bound=0 scans_ocr_unrouted=0 mutated_leases_accepted=0` —
  the last three are the counters the cap, scan and lease known-bads move, so a cold session can
  re-fire them. REPORTED: `files_without_reference_stage` and `reference_anchor_rate` (the anchor rate
  against its real denominator, which the drain above names; nothing else catches their omission).
- (c) kill mid-batch, rerun → block **content hashes** equal, 0 duplicates; a lease token mutated
  so an expired worker commits after reassignment → the ownership gate goes RED and
  `mutated_leases_accepted=1` if the commit lands; a PDF whose page count EXCEEDS the cap → refused
  with the `over-page-cap` reason, never started, `over_cap_bound=1` if it is extracted; a PDF whose
  page-count probe ERRORS → classed `probe-error`, a class of its own so `unclassified_acquired_files`
  stays 0, and never bound (fail-closed), a different path from the row above; a scan with OCR
  off → `scan-needs-ocr`, never "extracted, 0 chars", `scans_ocr_unrouted=1` if it lands as extracted
  with zero characters; a `type=book` record pushed through the
  queue → the `book` class and `books_extracted=1` the moment a block lands; a file placed in
  `_quarantine/` with no database row → `quarantined_without_db_state=1`.

#### Test-set commands (run from Scripts/, read-only)

```
# active files in main with no blocks, by work key — the bed the classifier is scored on (a work may hold more than one file)
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute(\"SELECT w.key, f.rel_path FROM litkb.main_files f JOIN litkb.main_works w ON w.work_id=f.work_id WHERE f.status='active' AND NOT EXISTS (SELECT 1 FROM litkb.blocks b WHERE b.file_id=f.file_id) ORDER BY 1\").fetchall())"
# the base's bioRxiv files (DOI prefix 10.1101/), for the stamp strip's bioRxiv branch
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute(\"SELECT w.key FROM litkb.main_identifiers i JOIN litkb.main_works w ON w.work_id=i.work_id WHERE i.scheme='doi' AND i.value LIKE '10.1101/%'\").fetchall())"
```

Kam (ruled 2026-09-22): classical OCR in page-range chunks on the T2000 first, vision-language OCR
in S4.7; the reference stage runs over every file with blocks, detached, in this session.

### S4.5 — The acquisition ladder, part 1: the substrate and the free rungs (Stages A–C and E)

Rewritten 2026-09-22 after the PDF-sources survey (`Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md`:
its §M is the orchestrator's read-only measurements on litkb's own rows, its §1 the ladder by stage,
its §2 the per-publisher rule table, its §3.4 the ledger vocabulary, its §6 the coverage projection)
and its round 3 (`Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md`: §1 the shadow-library linkage map, §2 the identifier crosswalk graph with the
native-key table and the fan-out order, §3 the identifier data model, §4.5 what it changes here).
The target is `litkb-coverage-target` (decided); the survey's demonstrated number for a corpus of this
shape by legitimate automated means is lower — an EXTERNAL self-reported figure, not litkb's — and the
gap is closed by rulings, not rungs. This session builds only rungs that cost nothing on a miss and
are VERIFIED in source or MEASURED on litkb's rows; a rung the survey measured at zero here is kept
only if it is free, and reported as measured-zero. S4.6 builds the tiers that wait on
`litkb-institutional-access`, `litkb-shadow-hosts` and `litkb-tdm-keys`. Every rung is a RELAYED
design (CLAUDE.md §3.4c) and is UNVALIDATED until an independent referee scores it on the rows named
here and the report is tracked under Reports/; a kill criterion counts once it has FIRED. Referees:
one per RUNG CLASS, sequentially — the classes are the ones `unvalidated_items` enumerates in (b),
which is their one home; the protocol's three-agent cap is a cap on CONCURRENT referee agents, and
one referee may take several classes in turn. Workstream slug: `ladder-1` (the entry condition is the
preflight command in "Per-session protocol", then `litkb_ws_open` on that slug). Spelled S4.5 because the plan gate
recognises a session heading by `### S<digits>`. Rung and guard ids are the survey report's.

Work
1. **The substrate carried from the 2026-09-21 revision** (the four items that block were: back-off,
   registry identity, the served-bytes hash, the refuse verb — all of them are THIS item now):
   per-route back-off and in-run transient retry keyed on (route, status, http codes, at), never the
   state word, with AIMD decay on every 2xx (guard 2: the survey's starting constants are a 1 s decay
   against a 2× multiplier and a 300 s ceiling, the refusal ladder 15 min → 6 h → 48 h — calibrated
   on the ledger, never taken as given) and NO host suppression on a single 403 (guard 29 — MDPI answers
   403 per article and is the corpus's largest slice); dead-ness a per-attempt `retriable` fact
   (guard 15). Registry identity: the Crossref `relation` probe first, then edges with a third state,
   identifier-first duplicates, type-scoped ISBN-13, a key-LENGTH rule for `make_key` — and, from round 3
   (`Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md` §3 and §4.5), the IDENTIFIER MODEL the ladder's rungs key on: the scheme vocabulary extended
   with the six a rung cannot fire without (`md5` — the shadow tier's work address and every library's
   join key; `pii` — Elsevier's native key, carried in Crossref `alternative-id` for nearly every
   Elsevier DOI in the corpus and discarded today; `core`; `bibcode`; `ocaid`; `oai`) and the cheap
   second tier (`issn` · `oclc` · `lccn` · `olid` · `htid` · `gbooks` · `sha1` · `sha256` · `zlib` ·
   `lgrsnf` · `lgrsfic` · `lgli` · `nexusstc` · `wikidata` · `mag` · `dblp` · `hal`), with the closed
   CHECK replaced by a `scheme_registry` table (label, url template, regex, normaliser, and
   `distinct_values` — uniqueness is per-scheme DATA: true for `doi` `arxiv` `pmid` `pmcid` `openalex`
   `s2` `mag` `bibcode`, false for `isbn` `issn` `oai` `handle` `md5`, so the partial unique index covers
   only the distinct ones and a book's ISBN on its chapters is data, not a violation); provenance per
   identifier (`asserted_by` beside `verified_by`, the INPUT identifier the edge was derived from, and
   `deterministic` as a first-class provenance for zero-request derivations); the conflict rule taken
   from fatcat verbatim — a later source fills a null and never overwrites; two identifiers resolving to
   two works drop the weaker one, assert a work-level `is_version_of` or `is_identical_to` edge with
   `asserted_by='conflict-resolution'`, and COUNT it; `works.part_of_work_id` and `works.version_of_work_id`
   as parent columns for the common cases (chapter → book, preprint → version of record, arXiv version →
   concept), an edge table only for the rest; the validators to port in that report's order (Zotero's
   bracket-balanced DOI clean, isbnlib's canonical and check-digit re-derivation, idutils' regex table with
   detection returning a SET and PMID last, a DOI slice as second pass, `isbnlib.editions` and
   `isbnlib.doi`) and the ONE not to port (an ISBN-13 check-digit routine that passes a tenth of random
   strings); and the three normalisation traps (a DOI is lowercased to key litkb's table and uppercased to
   ask Wikidata; DataCite lowercases what it returns; a PMCID is stored with its prefix and asked without).
   The HARVEST that fills the table costs no new request: Anna's `identifiers_unified` dictionary, which the
   fetch script under D:\tools\annas-mcp already downloads at its second gate and parses one key out of;
   Crossref's `alternative-id`, `ISBN`, `ISSN` and `relation`; OpenAlex's `ids` and `pmh_id`; Semantic
   Scholar's `externalIds` — three calls litkb already makes whose fields it discards. The served-bytes
   sha on every attempt row, a rejected-hash lookup over S4's quarantine state, and a landing that
   offers a refused-duplicate file to its work through check 3. A second-session REFUSE verb with both
   guards fired — with round 4's corrections (`Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.8): an append-only decision log (who decided
   what, when, on which version) beside the verb; on the VERSION tables `rejected` and `withdrawn` are states nothing
   writes today (the candidates table's own `rejected` IS written, by the refusal function — a
   different state), so the verb and a `withdraw_version` function are what give them writers; the promote
   stage has no live evidence at all (prepared, never committed), so its first end-to-end proof —
   `promote prepare` then commit on a constructed chain, with the approve guard fired by the
   proposing session — is a counter and a known-bad in this session; and the largest open bibliographic database does NOT enforce two-person
   review, so litkb's rule is stricter and is not weakened by analogy. Rows: E13 and the ruled run's `registry-transient` rows for the back-off; E21's pair
   for identity, with E06 as an ADMISSION negative (a page with no confirmed identifier, title-near an
   existing work, must still refuse `duplicate-review` — it exercises the duplicate check, not an
   acquisition rung); 187's record for the key rule and its filed PDF for the landing; 194's proposal
   for the verb. The OPERATOR-BIND GATE is built here beside that verb, under
   `litkb-from-file-version-state`: a `--from-file` bind lands as a `proposed` version, adjudicated
   like any other proposal, and NEVER as the version of record — counter `operator_binds_unproposed=0`
   in (b), with its known-bad in (c). The back-off's known-bad, the relation probe's, the key rule's and the verb's are in
   (c) below; the other substrate counters are REPORTED, not gated, until a known-bad is written for
   each — the block says so rather than claiming gates it has not fired.
2. **The ledger vocabulary the ladder needs** (survey §3.4; migration numbers reserved first; every
   column and value a `docs/SCHEMAS.md` row). NOT new words in the hunt's closed `STATES`/`REASONS`
   tuples — those stay as S3 left them, and the acceptance instrument's `CLOSED_STATES` pin stays
   green — but a `sub_status` column on `acquisition_attempts`, carried into `route_detail`, so a hunt
   that lands nothing still ends `held/not-acquired` while the attempt says WHY: `bad-file` sub-typed
   `html_response` · `too_small` · `missing_pdf_header` · `corrupt_pdf_header` ·
   `early_eof_with_trailing_payload` · `stub_not_article` · `volume_not_article` ·
   `cited_document_not_this_article` · `compressed_or_archived_payload`; `blocked` sub-typed
   `identity_required` · `challenge_or_bot_check` · `not_found` · `html_or_reader`; `not-in-archive`
   sub-typed `not_in_corpus` (the freeze gate, or a shadow front's miss page — bban's 404 + text/html, a
   mirror's "not available" page) · `no_pdf_link`. Two route rules the 2026-09-22 Sci-Hub diagnosis
   measured as MISSING and this item supplies: a challenge page is a challenge at ANY status
   (`Client.is_challenge` in `pipeline/litkb/netutil.py` fires only at 403/503, so `.wf`'s Cloudflare
   page at HTTP 200 — "Checking your browser" — is a challenge the client does not recognise, and it
   was recorded under the `no-pdf-link` tried token in `pipeline/litkb/acquire/scihub.py`, which is a
   token appended to `tried` and NOT a status; `.ren`'s "Verification" page is that mirror's MISS page
   rather than a challenge — D2 measured four DOIs, the one in-corpus DOI reaching the article page
   and the three out-of-corpus DOIs reaching Verification, a correlation this session confirms on one
   more in-corpus DOI before booking it `not_in_corpus`), and `blocked` is DEAD for a route within a run
   (`DEAD_STATUSES` in `pipeline/litkb/acquire/run.py` omits it, so every blocked DOI was retried until
   sci-hub.ru's rate gate). Also
   `terminal_url`, `terminal_status_code`, `terminal_dt` on every attempt; `word_count` on every landed
   file (`pages` already exists); `retriable` per attempt; `kind` (`pdf` · `jats` · `text` ·
   `html-doc` · `cached_text` · `snippet`); the version of record carried by EXTENDING
   `file_versions.copy_kind` (its `publisher` · `author manuscript` · `preprint` values already say
   published · accepted · submitted; guard 23) rather than a new column; an `unverified_keep` outcome
   (guard 17); a skip is an attempt with a reason, never silence (guard 14); a declarative BUDGET over
   the whole ladder — total seconds, attempts, concurrency — checked between every stage and rung
   (guard 12); a pre-fetch `PolicyDecision` so a tier is an auditable switch (guard 21).
3. **Stage A, zero network**: the record-class filter (A0); identifier canonicalisation (A1); the
   work-class router (A2 — paper · chapter · book · report · thesis · HTML-only; it is what stops a
   preprint or a book being sent to the scidb-by-DOI archive path, the routing error §M measured);
   the DOI-prefix router (A3); deterministic publisher URL construction (A4); EarthArXiv's OAI map of
   published DOI to preprint PDF (A7, MEASURED in the survey's round 2); the ZERO-REQUEST derivations of
   round 3's Wave 0 (`Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md` §2.3): an arXiv id to its `10.48550` DOI as a CANDIDATE until DataCite confirms
   it (the tracker's arXiv-only rows gain a DOI this way, which is what lets DataCite, scidb and the DOI
   paths address them), the inverse, ISBN-10 to ISBN-13, ISBN-13 to its ISBN-A DOI, the PMCID prefix,
   and a shortDOI expanded through the handle alias so one work never holds two rows; and the OFFLINE
   MEMBERSHIP TABLE — the public, sha256-pinned Sci-Hub DOI list and the LibGen article DOI table, which
   sit on GitHub and figshare as data files and contact no shadow host, so a `blocked` or `not-in-archive`
   row is typed out-of-corpus versus reachable BEFORE any mirror is spent (a Stage A rung; it needs no
   ruling, and the shadow corpus's freeze date (2022-02-12) is the reason a later DOI is out-of-corpus by
   construction). Rows: the preprints among the archive misses (the probe instrument's baselines CSV
   lists them by Crossref type) must route to their native API; the Sci-Hub `blocked` rows typed by the
   membership table.
4. **Stage B, metadata fan-out, all rungs CONCURRENT** (wall-clock is the slowest, never the sum),
   every rung asked for EVERY `no-oa-copy` row so its yield on this corpus is MEASURED by the run and
   written into the report — zero is an allowed answer, and a rung is kept only while its cost per miss
   is one free call: the identifier already carrying the file (B1 — MEASURED in §M: Semantic Scholar's
   `openAccessPdf` yields the arXiv siblings); OpenAlex `best_oa_location` and every `pdf_url` (B3 —
   DISPUTED in the survey, measured elsewhere at zero net-new over Unpaywall; kept because it is free);
   Crossref `link[]` with the correct filter — `pdf` in the content type OR the URL path, because MDPI's
   is `unspecified` (B4); Semantic Scholar's record (B5); DataCite (B6); CORE v3 (B7); DOAJ (B8);
   OpenAIRE (B9); the arXiv host rewrite to `export.arxiv.org` (B10); OSF (B11); Europe PMC (B12 —
   MEASURED ZERO on the survey's controls; kept only if it costs no quota); the conference-venue ladder
   (B13); Zenodo, HAL and figshare direct (B14). NASA ADS (B15) is NOT built here — the survey never
   probed its gateway; it is probed, not built, and enters the after-S5 table if it answers. The ORDER
   and the STOP RULE are round 3's (`Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md` §2.3): Wave 1 is three concurrent keyless calls — OpenCitations
   META (one GET fills several schemes), Crossref and OpenAlex (two calls already made; B4 becomes
   `link[]` AND `alternative-id` AND `issn-type` AND `relation`, never `link[]` alone); Wave 2 fires one
   conditional call per gap — NCBI's id converter BATCHED over the whole hunt queue where `pmid` or
   `pmcid` is absent, Europe PMC where a PMCID appeared (it also pre-checks every PMC delivery rung),
   DataCite for `10.48550`, `10.5281` and every DOI Crossref answers 404 for, ADS for a `bibcode` and its
   `esources` answer to "will any free rung fire", and Semantic Scholar LAST because it rate-limits in
   seconds; Wave 3 only for the book and report classes; the closure rule — a scheme is pursued only if
   absent, the input key is whichever held identifier the service accepts, accumulate after whichever
   resolver won, repeat only with identifiers discovered since the last pass, STOP when a full pass adds
   nothing. The fan-out's own KILL CRITERION is re-stated by round 3 against the schemes this corpus
   actually gains — `arxiv`, `pii`, `dblp`, `isbn`, `md5` — not `pmid`/`pmcid`, which the probe already
   showed a non-biomedical corpus barely gains; a non-proposer scores it.
5. **Stage C, landing page to bytes** — the single highest-yield missing rung: `citation_pdf_url` and
   its `bepress_` and `eprints.` variants matched by suffix, `link rel=alternate type=application/pdf`
   (C2); URL rewrites (C3); a DECLARATIVE per-publisher rule table for this corpus's publishers ported
   from the Zotero translator corpus (survey §2: MDPI's CDN `mdpi-res.com/d_attachment` answers
   `application/pdf` where `www.mdpi.com` answers 403; Elsevier's `pii` to `pdfft` for bronze articles;
   Springer, Wiley, IEEE, IOP, Cambridge, OUP, Copernicus, Frontiers, PLOS, USFS Treesearch — each with
   its validity check, and a challenge signature where the survey characterised one, which for
   Cambridge and eLife it did not), each rule shipping its example page as a regression fixture and its
   `lastUpdated` as a freshness prior (guard 25); an `Accept: application/pdf` header, and the Referer
   policy of guard 24 (the landing page if same-origin, else its origin, never a search engine). THE
   ACCEPTANCE TEST replaces today's `%PDF-` header plus `%%EOF` trailer with: lstrip-tolerant magic, a
   5,000-byte floor, libmagic MIME, transparent decompression of gzip and tar payloads, `%%EOF` within
   8 KiB of the end, `qpdf --check` (exit 0 clean, 3 recoverable, 2 damaged; the `--is-encrypted` exit
   codes mean something else), the stub detectors (fewer than 3,000 characters with no reference
   section; Elsevier's `X-ELS-Status` header; `page_count >= 60` against a Crossref page range shorter
   than that for a volume; `DOI_PAGES=3` so a bibliography cannot fake a DOI match), Crossref page-range
   as an identity signal, and never a delete on a verdict whose metadata could not be fetched (guard 18).
   Before spending anything, the 4 KB Range probe (C6/C13) types a refusal into the `blocked`
   sub-statuses.
5b. **The Sci-Hub workaround, part 1 — PULLED FORWARD from S4.6 on the 2026-09-22 diagnosis**
   (D:\tools\claude-config\jobs\litkb-scihub\ D1/D2 with their recorded pages; the orchestrator's re-run
   `qc/instruments/litkb_acq_probe_bban.py` → `phase4/qc/litkb_acq_probe_bban.csv`: 73 of the 104
   pre-2022 no-file works served on one keyless HEAD, 7 via the upper-cased suffix, `%PDF` on 8 of 8
   sampled). Why here and not S4.6: the diagnosis found the route's zero was the LEDGER's doing —
   misses booked `blocked`, `blocked` retried forever, 200-status challenges unseen — so item 2's
   vocabulary IS the fix, and the one rung that converts seventy percent of the backlog costs one
   request and no key; it is built the moment the vocabulary exists, not a session later. Built here,
   each behind item 2's `PolicyDecision` and inside `litkb-shadow-hosts` (b): (i) the FREEZE GATE — a
   work whose year is after 2021 is booked `not-in-archive/not_in_corpus` with no request to ANY shadow
   front (the corpus froze 2022-02-12); (ii) the bban rung — HEAD `https://sci.bban.top/pdf/<doi>.pdf`
   with the DOI as stored, on 404 once more with the suffix upper-cased (case-sensitive host), hit =
   200/206 + `application/pdf` + `%PDF` on the GET and the bytes through the same acceptance test as
   every route, miss = 404 + `text/html` booked `not_in_corpus`, never `blocked`, never retried in the
   run; (iii) the three route fixes of item 2 applied to `pipeline/litkb/acquire/scihub.py` — challenge
   at any status, `blocked` dead within a run, a mirror's miss page ("not available through Sci-Hub";
   `.ren`'s "Verification" page, which is that mirror's MISS page and not a challenge — item 2 carries
   the four-DOI correlation and the one extra in-corpus DOI that confirms it) booked `not_in_corpus`,
   while `.wf`'s "Checking your browser" page at HTTP 200 is a challenge — the mirrors themselves
   LAST in the ladder and otherwise untouched (no solver: the route's docstring forbids one and the
   ALTCHA page is a rate signal). Fixtures: the jobs folder holds each probe's METADATA and the first
   ~300 characters of each body, not the bodies, so it cannot be replayed through the client; this
   rung's FIRST network step records the full pages itself — one GET per mirror per test DOI, inside
   the grant — and stores those bodies as test fixtures in the repo beside every other litkb fixture
   (`qc/fixtures/`, the home `qc/instruments/litkb_edge_run.py` and `qc/test_litkb_edges.py` read
   `qc/fixtures/litkb_hunt_edge_cases.json` from), under qc/fixtures/litkb_scihub_pages/. Those
   recordings are the rung's fixtures, real and not constructed; the jobs JSON is the expected
   metadata they are checked against. POSITIVE, REAL: the 73 `served` rows of the probe CSV, each
   landing as a file (the acceptance-test refusals among them named, never silent). NEGATIVE, REAL:
   its 31 `not-in-corpus` rows, each ending `not_in_corpus` with ONE attempt row; the 7 `served` rows
   whose `tried` differs from `doi` (23 `not-in-corpus` rows also carry the retry; they are misses
   either way), which must land on the retry and not on `not_in_corpus`;
   `10.1016/j.rse.2024.114101` (post-freeze, in the base) refused before any request. LibGen.li, the
   mirror rebuild and the dead fronts stay S4.6 Stage G's.
6. **Stage E, recovery**: the Wayback availability API and CDX with the `id_` raw-bytes modifier (E1 —
   §M's census.gov author copy is its positive row; §M's IIASA copy, never archived, is its real
   NEGATIVE); Internet Archive item search and download (E3) and the Common Crawl index (E5) have no
   litkb row today and are built as free fan-out members whose yield the run measures. fatcat's API is
   dead server-side (the survey settled it) and is not a rung.
7. **Hermetic replay BEFORE the first referee round** (`Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.10; that record measured the
   register's live rows in hundreds of seconds against seconds in replay, against hosts already
   refusing this client). Cassettes do not exist until they are RECORDED: one live pass over the
   register rows records them, and every replay after it is hermetic — so the order is record, then
   replay, then referee: a
   recorded-client cassette layer at litkb's single HTTP seam; replay through the REAL acquisition
   ladder, never a synthetic return from the acquirer (today's stub fabricates the ladder's answer, so
   the register is graded against a world the instrument wrote itself — one row passes on state and
   reason while its recorded route ladder disagrees in every field); a socket guard that enforces
   hermeticity; cassette identity in the manifest with a staleness diff; the register rows that still
   carry superseded predictions re-graded against recorded truth. Rows: the register's hunt-shaped
   rows and their divergence rows; the raise cases in `qc/test_litkb_hunt.py`; CONSTRUCTED, in those
   words: a cassette's 403 edited to 200, a truncated body, an HTML body. Counters and known-bads for
   this item are in (b) and (c) below, and "replay" is a rung class of its own.
8. **The measurement that comes FIRST**: read every `bad-file` row's `detail`, its stored bytes' first
   kilobyte where the bytes were kept (the store kept them for only a few of these rows; the rest have
   `detail` alone) and its length; type each into item 2's vocabulary; the count of causes that are free
   to fix is this session's first tracked number, written by the probe instrument into phase4/qc/.
   The reason so many of those rows carry `detail` alone: `Store.to_quarantine`
   (`pipeline/litkb/acquire/store.py`) writes only the FILENAME — the `.reason.json` sidecar is written
   by `quarantine_new`, the challenge path, and by nothing the four acquisition callers reach. This item
   makes EVERY quarantine write that sidecar beside the bytes, next to the database row S4 gives it:
   counter `quarantines_without_reason=0` in (b).

Test set (the rows are named by the probe instrument's CSVs under phase4/qc/ — see the commands —
never by a number here). POSITIVE, MEASURED: the `no-oa-copy` rows whose probe verdict is `FREE-PDF`
(the arXiv siblings, through B1) and the Wayback row (through E1) — these MUST convert; the Elsevier
bronze rows whose Unpaywall answer is a landing page — through Stage C, ESTIMATED by the survey at
zero to all of them because Elsevier's `/pdfft` may sit behind a challenge, so they are REPORTED, and
if they end `challenge_or_bot_check` the converter is S4.6's browser rung. Every `bad-file` row
re-typed; every open-access `blocked` row typed by the Range probe (an MDPI row among them is a
MEASURED conversion through the CDN rule); the preprints among the archive misses routed by Stage A;
the works without a file that the crosswalk probe (`qc/instruments/litkb_acq_probe_crosswalk.py`,
`phase4/qc/litkb_acq_probe_crosswalk.csv`) gives an arXiv id, an ISBN or a `relation` edge — each must
gain the identifier row with its provenance, and each arXiv-id work must reach the arXiv rung.
NEGATIVE, REAL: the paywalled remainder of the `no-oa-copy` rows (§M measured every Springer, Wiley,
OUP, IOP and Cambridge link as HTML or a token-gated endpoint) must end typed `identity_required` or
`html_or_reader`, never bound; E13's challenge bytes must type `challenge_or_bot_check`; the IIASA
link must end `not_found` at E1; the publisher PREVIEW that E20's own `citation_pdf_url` serves — a
valid PDF of a few pages that is not the book (§M; the head probe marks it `PREVIEW-PDF`) — must
type `stub_not_article`, never bind. NEGATIVE, CONSTRUCTED — and this line says so in those words, per
§3.4c, because the base holds none of them: a valid PDF whose body starts with a BOM; a first-page TDM
stub with the `X-ELS-Status` header; a 60-page proceedings volume bound to a 12-page record; a PDF
whose bibliography carries the requested DOI; all four under qc/testdata/litkb_acq_negatives/ (to be
written), each labelled constructed in its name.

Done-state
- (a) the `hardening` subcommand of `qc/instruments/litkb_acceptance.py` itself, built FIRST from the
  `edges` subcommand's shape (the "The acceptance instrument" section assigns `hardening` to this
  session; nothing else can print (b) until it exists); the migrations; the ledger columns and values;
  the Stage A/B/C/E rungs with their rule fixtures;
  the bad-file re-typing CSV under phase4/qc/; a report under Reports/ (LITKB_LADDER1_<date>); one
  referee report per rung class under Reports/; tests + ledger rows; `docs/SCHEMAS.md` rows for every
  column, value and sub-status; the manifest frozen by `hardening --freeze` before the run, as `edges`
  does it.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py hardening --manifest <manifest>` → GATED (each with
  a (c) that fires): `rehunt_route_spends=0` (attempts on a route inside its back-off window that are
  not a scheduled transient retry) · `relation_probe_rows>=1` (rows in the probe CSV) ·
  `key_derivation_crashes=0` (admissions ending `crashed/admit:CheckViolation`) ·
  `known_bad_relands=0` (landings whose sha matches a rejected row) · `proposals_unadjudicated=0`
  (`proposed` admissions older than the run with neither verb applied) · `bad_file_untyped=0`
  (`bad-file` attempts with NULL `sub_status`) · `blocked_untyped=0` · `quarantines_without_reason=0`
  (a quarantined file with no `.reason.json` sidecar) · `operator_binds_unproposed=0` (a `--from-file`
  bind that became the version of record instead of a `proposed` version) · `preprints_sent_to_shadow=0`
  (attempts on a shadow route for a work whose `main_works.type` is `preprint` OR whose `cr_type` in
  `phase4/qc/litkb_acq_probe_crosswalk.csv` is `posted-content` — litkb's own type vocabulary holds no
  `posted-content` value, so the crosswalk CSV is the other half of the measurement) ·
  `post_freeze_sent=0` (a shadow-front request for a work with year after 2021) ·
  `shadow_miss_booked_blocked=0` (a bban or mirror miss page recorded as `blocked`) ·
  `bban_probe_hits_not_landed=0` (a `served` row of the probe CSV with no file after the run, the
  acceptance-test refusals named and excepted) · `challenge_at_200_unbooked=0` (a recorded .ren/.wf
  page replayed through the client without a `challenge_or_bot_check` row) ·
  `landing_pages_booked_bad_file=0` (`html_response` attempts whose page carried `citation_pdf_url`
  and no Stage C attempt followed) · `stubs_bound=0` · `volumes_bound_as_article=0` (a bound file with
  `pages >= 60` against a Crossref page range under 60, the range parsed from an `a-b` digit form
  ONLY; a row whose `pages` does not parse is neither a hit nor a pass and is REPORTED
  `page_ranges_unparsed`) · `free_ceiling_measured_unconverted=0` (the
  `FREE-PDF` and Wayback rows still without a file) · `budget_exceeded_silently=0` (a work whose ladder
  ran past the budget with no `budget` attempt row) · `stage_b_rungs_unmeasured=0` (Stage B rungs
  with no yield line in the report) · `crosswalk_rows_without_identifier=0` (works the probe CSV gives
  an arXiv id, ISBN or relation edge that hold no such row after the run) ·
  `identifiers_without_provenance=0` · `conflicts_uncounted=0` (two works claiming one distinct-valued
  identifier with no conflict edge and counter) · `nondistinct_schemes_in_unique_index=0` · `unvalidated_items=0` (rung
  classes — the substrate, the vocabulary, Stage A, Stage B, Stage C, the Sci-Hub part 1, Stage E,
  replay, the bad-file read — whose referee report the manifest does not name or whose report has no
  `fired: <counter>=<value> on <input>` line) · `replay_rows_graded_against_stubs=0` (register rows
  graded by a synthetic acquirer return) · `replay_network_calls=0` · `cassettes_stale=0` ·
  `promotions_prepared>=1` (the first end-to-end promotion prepared on a CONSTRUCTED chain, in those
  words). REPORTED, unbounded: `promotions_committed` — the commit cannot be reached inside this
  session, because `promote.commit` (`pipeline/litkb/promote.py`) calls `verify_merge` and there is no
  merge commit until Kam has merged the branch, so the committed number is verified in the session
  AFTER that merge; `page_ranges_unparsed`; `transient_rows_unretried`, `relation_edges_missing`,
  `identifier_first_refusals`, `books_without_isbn`, `attempts_without_sha`, `unowned_landings`,
  `attempts_without_terminal`, `files_without_word_count`, `hits_without_version`,
  `bronze_landing_unconverted`, `manual_step_rows`.
- (c) the back-off window set to zero → E13's second hunt re-spends (none of its statuses is a
  permanent dead status) → `rehunt_route_spends>0`; the probe CSV emptied → `relation_probe_rows=0`;
  the key rule reverted → 187's record → `key_derivation_crashes=1`; E13's bytes re-served with the
  lookup disabled → `known_bad_relands=1`; the refuse verb removed and 194 left → 
  `proposals_unadjudicated=1`; the typing step disabled → `bad_file_untyped>0` and `blocked_untyped>0`;
  the router disabled and a preprint hunted → `preprints_sent_to_shadow=1`; Stage C disabled on a page
  with `citation_pdf_url` → `landing_pages_booked_bad_file=1`; the constructed TDM stub, and E20's REAL preview PDF → `stubs_bound=1`
  if either binds; the constructed volume → `volumes_bound_as_article=1` if it binds; the B1 rung disabled
  → `free_ceiling_measured_unconverted>0`; the budget object removed → `budget_exceeded_silently=1`;
  a Stage B rung's yield line deleted from the report → `stage_b_rungs_unmeasured=1`; the harvest
  disabled and the probe's arXiv-id works re-hunted → `crosswalk_rows_without_identifier>0`; an
  identifier row written with NULL `asserted_by` → `identifiers_without_provenance=1`; a CONSTRUCTED
  second work claiming an existing DOI → refused, the edge written and `conflicts_uncounted=0` only if
  the counter moved; `isbn` placed in the distinct set → `nondistinct_schemes_in_unique_index=1`; a referee report
  dropped from the manifest → `unvalidated_items=1`; a cassette's 403 edited to 200 (CONSTRUCTED) →
  the replay disagrees with the register → RED; a socket opened during a replay → refused,
  `replay_network_calls=1` if it connects; the synthetic acquirer return reinstated →
  `replay_rows_graded_against_stubs>0`; the sidecar write removed and a bad download quarantined →
  `quarantines_without_reason=1`; a `--from-file` bind made the version of record with the proposal
  path disabled, i.e. landing without a second session's approval → `operator_binds_unproposed=1`;
  the proposing session approving its own CONSTRUCTED chain → refused, and the chain PREPARED by that
  session → `promotions_prepared=1` (the commit is Kam's merge; the session after it reports
  `promotions_committed`).

#### Test-set commands (run from Scripts/, read-only)
`py -3.12 qc/instruments/litkb_acq_probe_bban.py` — the bban yield over the pre-2022 no-file
backlog, ~5 min serialised; run BEFORE the rung lands (its CSV is the rung's positive and negative
rows) and AFTER (every `served` row should now hold a file; `bban_probe_hits_not_landed`).

```
# the acquisition census, all time, by route and status — never quote a cell, run this
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute('SELECT route,status,count(*) AS rows,count(DISTINCT identifier_used) AS identifiers FROM litkb.acquisition_attempts GROUP BY 1,2 ORDER BY 1,2').fetchall())"
# coverage today: works in main, with an active file, with searchable blocks
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute('SELECT (SELECT count(*) FROM litkb.main_works),(SELECT count(DISTINCT work_id) FROM litkb.main_files WHERE status=%s),(SELECT count(DISTINCT f.work_id) FROM litkb.main_files f WHERE f.status=%s AND EXISTS (SELECT 1 FROM litkb.blocks b WHERE b.file_id=f.file_id))',('active','active')).fetchone())"
# the tracker denominator and its identifier mix (before the record-class filter)
py -3.12 -c "import csv,re,collections;r=list(csv.DictReader(open('../Reports/literature_tracker.csv',encoding='utf-8-sig')));m=collections.Counter('doi' if re.search(r'10\.\d{4,9}/',x['DOI/URL']) else 'arxiv' if re.search(r'arxiv|\b\d{4}\.\d{4,5}\b',x['DOI/URL'],re.I) else 'url' if x['DOI/URL'].startswith('http') else 'text' if x['DOI/URL'].strip() else 'empty' for x in r);print(len(r),dict(m))"
# the survey's read-only probes as repository instruments (metadata and HEAD only; nothing downloaded);
# they write phase4/qc/litkb_acq_probe_no_oa_copy.csv, litkb_acq_probe_head.csv, litkb_acq_probe_baselines.md
py -3.12 qc/instruments/litkb_acq_probe_no_oa_copy.py && py -3.12 qc/instruments/litkb_acq_probe_head.py && py -3.12 qc/instruments/litkb_acq_probe_baselines.py
# the identifier crosswalk yield per scheme, and joined to the file table (writes phase4/qc/litkb_acq_probe_crosswalk.csv)
py -3.12 qc/instruments/litkb_acq_probe_crosswalk.py
py -3.12 -c "import csv,psycopg;r=list(csv.DictReader(open('../phase4/qc/litkb_acq_probe_crosswalk.csv',encoding='utf-8')));c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');wf={k for (k,) in c.execute(\"SELECT DISTINCT w.key FROM litkb.main_files f JOIN litkb.main_works w ON w.work_id=f.work_id WHERE f.status='active'\").fetchall()};nf=[x for x in r if x['key'] not in wf];print('no-file works',len(nf),{col:sum(1 for x in nf if x[col]) for col in ('s2_arxiv','s2_pmcid','pmid','cr_isbn','cr_relation_types','cr_has_link')})"
# litkb's identifier table by scheme (the empty schemes are the gap)
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute('SELECT scheme, count(*) FROM litkb.main_identifiers GROUP BY 1 ORDER BY 2 DESC').fetchall())"
# the MEASURED free-ceiling rows (must convert) and the bronze landing-page rows (reported)
py -3.12 -c "import csv;h=list(csv.DictReader(open('../phase4/qc/litkb_acq_probe_head.csv',encoding='utf-8')));print('free',sorted({r['doi'] for r in h if r['verdict']=='FREE-PDF'}));n=list(csv.DictReader(open('../phase4/qc/litkb_acq_probe_no_oa_copy.csv',encoding='utf-8')));print('bronze-landing',[r['doi'] for r in n if r['unpaywall_url'].startswith('https://doi.org/')])"
```

Kam: ruled — `litkb-blocked-works-grade` (metadata-grade by default, the human queue on demand) and
`litkb-from-file-version-state` (the proposal path, batched approvals): the operator-bind gate is
built in item 1 beside the refuse verb, not after S5.

### S4.6 — The acquisition ladder, part 2: grey literature, books, the shadow tier and credentials (Stages D, F, G, H)

Inserted 2026-09-22. These rungs reach what Stages A–C and E cannot: works with no DOI (agency and
city reports, theses), books and chapters (a namespace litkb's scidb-by-DOI route cannot address by
construction — the survey report §4), the pre-2021 paywalled slice (the shadow tier under Kam's
existing grant; new hosts and a browser against a shadow host only under `litkb-shadow-hosts`), and
the paywalled remainder that only credentials reach (`litkb-institutional-access`, `litkb-tdm-keys`).
The survey's §6 says which of these closes the gap to `litkb-coverage-target` and under what ruling;
this session builds what is ruled in and reports the rest UNDETERMINED, never as a miss. Every rung
is a RELAYED design and UNVALIDATED under the S4.5 protocol (referee per rung class: Stage D, Stage F,
Stage G, Stage H, the coverage instrument); shadow rungs are read through code and documentation only
until Kam's grant names the host. Rung ids are the survey report's.

Work
1. **Stage D, title-keyed grey literature** (fires on the work-class router's `report` and `thesis`
   hints; every hit passes the title-on-page identity check at 0.85, never lower, because these works
   have no DOI to corroborate): USFS Treesearch through its sitemap (D1, VERIFIED by the survey's A8
   measurement — enumerable records, `citation_pdf_url` on every page, HEAD `application/pdf`); USGS
   Publications Warehouse (D2); DOE OSTI (D3); NASA NTRS (D4); govinfo (D5); DSpace 5/6 and EPrints
   through OAI-PMH `metadataPrefix=mets`, which returns the bitstream URL with its MD5 and byte size so
   a file is verified BEFORE download and often a pre-extracted text sibling (D6; the installed OAI
   connector is NOT reused, D7); DSpace 7 through its REST bitstream walk instead (B16 with C20 — a
   direct file route the survey calls strictly better for any repository upgraded since 2022); King
   County and city document portals (D8); OpenAlex title search (D9); a multi-engine exact-title
   `filetype:pdf` search (D10); Google Scholar's `eprint_url` (D11); ArcGIS Online item search with
   `type:"PDF"` (D12 — MEASURED: a city canopy assessment was its first result); the state-library
   DSpace class, Washington State Library unprobed (D13). Budget the layer at the Internet Archive's
   own repository-harvesting rate (survey §3 — the archive's number on its own pipeline, NOT this
   corpus's), which is far below its open-access rate.
2. **Stage F, books and chapters — UNVALIDATED with no real test row until `litkb-crc-book` yields
   one**: the ISBN namespace — and the harvest S4.5 schedules cannot produce E20's ISBN, because
   Crossref holds none for it and the one that exists came from a publisher page, so the harvest gains
   the three free ISBN sources round 3 names (`Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md` §4.3: Open Library's search answer carries every
   edition's ISBNs, the Internet Archive's `urn:isbn:` lookup, and Nexus/STC's record fields `isbns` and
   `parent_isbns`, the last of which is exactly the chapter-to-container routing the `part_of` edge
   needs) plus a publisher-page source or a manual identifier; `isbnlib.editions` clustering so one ISBN
   becomes the edition set; Open Library to an Internet Archive item; chapter routing where a chapter
   DOI carries the book's ISBN — the ISBN attaches to the BOOK work only (the identifier index is
   unique per active scheme and value) and a chapter links to it by a `part_of` edge from S4.5's edge
   mechanism; EPUB and DjVu to PDF conversion where a copy arrives in another format. DOAB and OAPEN
   (F4), HathiTrust (F5) and Google Books (F6) are graded MIXED by the survey — a Cloudflare 403 on
   the REST path, partner access the project does not have, and no PDF logic in Zotero's own
   translators for them — so they are PROBED, not built, and re-graded VERIFIED as crosswalks by round 3. The corpus's CRC
   Press book has NO automated route (Taylor and Francis needs a browser-session token).
3. **Stage G, the shadow tier under the EXISTING grant** (Anna's Archive and Sci-Hub; every request
   behind guard 21's `PolicyDecision`): detect DDoS-Guard by the page `<title>` FIRST, so a block is
   booked `challenge_or_bot_check` and never `not-in-archive` (G0d; the survey reads the archive misses
   as mostly false negatives for this reason); Anna's quota-free record endpoint from an md5 (G2a);
   Sci-Hub's Altcha challenge distinguished from a genuine miss (G0c) and its resolved storage path
   treated as portable across mirrors (G1b); the mirror lists moved from `run.py` constants to a
   versioned registry fetched at start (guard 7). `litkb-shadow-hosts` was decided 2026-09-22 for ALL of the following, each behind
   its own policy line and built in this session: LibGen's DOI-to-md5 lookup with its User-Agent trap
   (G0a) and delivery (G1d); the `sci.bban.top` DOI path (G1a) FIRST, beside Sci-Hub, not in its place — Kam
   reversed the parking the same day (`litkb-scihub-parked`: "a massive loss if we table it") and the
   diagnosis that evening (two read-only Opus probes under D:\tools\claude-config\jobs\litkb-scihub\; the
   orchestrator's re-run `qc/instruments/litkb_acq_probe_bban.py` → `phase4/qc/litkb_acq_probe_bban.csv`)
   settled the ladder. The route's zero was SAMPLING plus MISLABELLING, not a corpus loss: 19 of the 22
   DOIs it was ever asked for post-date the 2022-02-12 freeze and the two eligible ones are confirmed
   absent, while a miss page was booked `blocked` and `blocked` is not in `DEAD_STATUSES`
   (`pipeline/litkb/acquire/run.py`), so every miss was retried until sci-hub.ru's ALTCHA rate gate. The
   corpus itself is open from here: bban served 73/104 (70%) of the pre-2022 no-file backlog on
   one keyless HEAD (D2: 73/104; D1: 12/20 random), LibGen.li's json.php→ads.php→get.php chain 75/104,
   union 77/104. The rungs in the measured order, each with its kill — (1) the FREEZE GATE and (2)
   the bban rung are BUILT IN S4.5 (item 5b, pulled forward on the diagnosis); this stage re-runs
   their probe on the post-S4.5 ledger and carries `post_freeze_sent=0` and
   `shadow_miss_booked_blocked=0`; built here: (3) LibGen.li scimag by DOI → md5 →
   delivery, the md5 kept as an identifier; (4) the sci-hub.* mirrors LAST, on the three fixes S4.5
   applied (challenge at any status; `blocked` dead within a run; the miss page booked
   `not_in_corpus`) — the parser has never seen a live delivery page, so its first real one is the
   positive row and the rung stays UNVALIDATED until one exists; (5) NOT built, measured dead today: Anna's `/scidb`
   (.org/.se NXDOMAIN, .li parked, .gl DDoS-Guard), Nexus/STC (no HTTP front), library.lol (seized),
   Tor (no onion address in any source read — unaddressed, not unfetched). No solver: the route's
   docstring forbids one and the ALTCHA page is a rate signal, not a corpus one; Nexus/STC crosswalk first and delivery second (G0b/G1c);
   a real browser session against Anna's only where the challenge-detection fix leaves a block (G3a);
   Tor (G5) only if a granted host is unreachable without it. Offline metadata dumps are data. The
   rungs as the survey read them, in code only until built: LibGen's DOI-to-md5 lookup with its
   User-Agent trap (G0a) and delivery (G1d), the `sci.bban.top` DOI path (G1a), Nexus/STC (G0b —
   VERIFIED but disputed, its gateway reported down in 2026; G1c), a real browser session against
   Anna's (G3a). Tor as a transport (G5) is graded verified as a mechanism and dead as an
   implementation, and is not scheduled. The Sci-Hub corpus froze 2022-02-12, so a post-freeze
   paywalled work in this tier ends `held/not-acquired` with `retriable=false` without a request; the deferred-human-
   fulfilment rung (G4) is the `--from-file` half of `litkb-blocked-works-grade` (decided:
   metadata-grade by default, the queue on demand), not code.
4. **Stage H, credentialed and anti-block, each behind its ruling**: NO persistent logged-in browser profile
   (H10/H11) — `litkb-institutional-access` was decided 2026-09-22 as none, so the `manual-step` rows
   and the paywalled remainder go to Stage G, to the human queue of `litkb-blocked-works-grade`, or
   to metadata-grade; Elsevier's API (H2): Kam's free key is IN PLACE (`litkb-tdm-keys`, amended
   2026-09-22 to Elsevier only; alone on one line in D:\edmonds-pipeline\secrets\Elsevier_key.txt, the
   shape `KEY_FILE` in `pipeline/litkb/acquire/annas.py` already reads for Anna's) and MEASURED the
   same hour by `qc/instruments/litkb_acq_probe_elsevier_key.py` →
   `phase4/qc/litkb_acq_probe_elsevier_key.csv`: the key is valid (Scopus Search 200) but every
   ScienceDirect endpoint refuses it at the key-configuration level — Article Retrieval 403
   `AUTHENTICATION_ERROR` even at `view=META` on a GOLD open-access article, ScienceDirect Search and
   Metadata 401 — so as configured it buys NO full text, only Scopus metadata (EID, PII, `openaccess`
   flag, cited-by) for Stage A's crosswalk. H2 is built ONLY once a re-run of that instrument shows a
   ScienceDirect 200 (a replaced key the same evening answered IDENTICALLY, so the refusal is
   Elsevier's non-subscriber key profile rather than the form's TDM box; Kam's open action is Elsevier
   API support — their page says non-subscribers "can still retrieve free and open access content --
   or speak to us about non-subscriber access"); until then the expected first-page stub
   (an unentitled key answering HTTP 200 with the stub announced only in `X-ELS-Status`, which S4.5's
   acceptance test refuses) stays CONSTRUCTED; Springer's API (H1) is NOT built — no Springer key,
   its open-access content stays on the Unpaywall rung; `curl_cffi` impersonation (H5) is NOT built — the
   survey measured it AGAINST twice in production, on MDPI and on Springer — and is recorded as
   measured-against; FlareSolverr (H6) already exists in `pipeline/litkb/netutil.py` as the challenge
   retry, cannot return a PDF (its solution is HTML), and stays a landing-page solve only. No commercial
   anti-bot proxy.
5. **The coverage account** the finish line reads: an instrument under `qc/instruments/` that joins the
   tracker (`Reports/literature_tracker.csv`) to main by identifier, applies the record-class filter,
   and prints per grade (`pdf` ·
   `jats` · `html-doc` · `cached_text` · `snippet` · metadata-only · none) the share of eligible
   tracker rows in each, plus the paywalled residue by publisher and year, into a CSV under phase4/qc/ — with the residue
   split three ways by the offline membership table: out-of-corpus (no shadow library ever held it),
   blocked (held, but every probe was refused), and not-in-archive as the archive's own five-way answer;
   without that split the residue column silently absorbs works no shadow rung could have reached.
   Which grades count toward the target is `litkb-coverage-definition` (decided 2026-09-22: PDF, JATS
   and full-text HTML count; cached text and snippets are reported, never counted), so the session's
   (b) carries the bound on the full-text grades. THE DENOMINATOR, written down before anything is
   built: eligible = every row of `Reports/literature_tracker.csv` not retired by
   `litkb-e23-residue-copies` or `litkb-crc-book`. A row with NO DOI stays IN — the tracker's URL-only
   rows and its agency reports are exactly Stage D's targets, and dropping them would score the
   session on the works it can already reach. The class filter A0 is S4.5's; until it exists the
   instrument classes rows by the tracker's OWN columns and says so in the report. The counts are a
   command (the tracker line under "Test-set commands"), never a number written here.

Test set, POSITIVE: the archive-miss rows by Crossref type (the probe instrument's baselines output
under phase4/qc/ lists them: the preprints must never reach this tier — S4.5's router owns them; the
chapters and the book go through Stage F only if a copy can exist; the rows no registry holds end
`refused/unresolved` with the reason, never `not-in-archive`); the Sci-Hub `blocked` rows re-typed
(challenge · miss · storage path found on another mirror · out-of-corpus by the membership table); the
archive-miss rows re-read against the archive's five conditions; the grey rows whose files are ALREADY on
disk but not in main — 235's Seattle canopy report under `_litkb_staging/filed/` and 194's King
County page snapshot under `_litkb_staging/web/` — and the USFS and USGS class by title; the `manual-step` rows, now Stage G's or metadata-grade (no institutional access). NEGATIVE, REAL: a Stage D
title hit whose page-1 title scores below 0.85 (the ruled run's row 235 cover measures 0.80 and is the
row); a DDoS-Guard interstitial from the ledger's own `blocked` attempts; a request to a host outside
the policy allowlist. NEGATIVE, CONSTRUCTED, in those words: a chapter DOI carrying an ISBN already
attached to its book. NEGATIVE, REAL: a post-freeze DOI offered to the shadow tier —
`10.1016/j.rse.2024.114101` is in the base and bban answers it 404 — refused by the freeze gate before
any request; a lower-cased DOI whose upper-suffix form serves at bban must land on the retry, not on
`not-in-corpus`.

Done-state
- (a) the Stage D/F/G/H rungs that are ruled in, each with fixtures; the coverage instrument and its
  CSV under phase4/qc/ (CLAUDE.md §3.4b); a report under Reports/ (LITKB_LADDER2_<date>); one referee
  report per rung class; tests + ledger rows; SCHEMAS rows; the manifest frozen by `ladder --freeze`.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py ladder --manifest <manifest>` → GATED:
  `grey_hits_below_title_gate=0` · `chapters_routed_to_scidb=0` · `challenge_booked_as_miss=0` (a
  `not-in-archive` attempt whose terminal page title is DDoS-Guard) · `post_freeze_sent=0` ·
  `shadow_miss_booked_blocked=0` (a bban or mirror miss page recorded as `blocked`) · `shadow_requests_outside_policy=0`
  · `new_hosts_without_ruling=0` · `tdm_stubs_bound=0` · `coverage_rows_unclassified=0` (tracker rows the instrument could
  neither join nor mark) · `archive_misses_untyped=0` (archive-miss rows still carrying the bare word
  after the five-way re-read) · `shadow_misses_from_concurrent_probes=0` · `unvalidated_items=0` (the five rung classes). GATED by the rulings: `coverage_fulltext>=0.95` over the eligible tracker rows
  (`litkb-coverage-target` under `litkb-coverage-definition`: pdf + jats + html-doc) — `ladder` EXITS
  NON-ZERO below 0.95 unless `--residue-ruled <csv>` names every residue row with the ruling id that
  leaves it (metadata-grade or the human queue), in which case it prints UNDETERMINED and exits 0. No
  prose is read: a report that names residue rows in sentences does not move this gate.
  The population query behind `coverage_fulltext` and the bban re-run are EXECUTED BY THE REFEREE
  agent, not by the builder, and (b) reads the referee's numbers — the builder writes the instrument
  that computes its own gate, which is what §3.4c forbids as acceptance evidence.
  REPORTED: `eligible_rows`, `coverage_pdf`,
  `coverage_cached_or_snippet`, `paywalled_residue`, `manual_step_rows`, `bban_served` over
  `bban_population` (the probe's number, re-measured by the referee), and `credentials_stored` — a
  TEXT SCAN of source and database rows, best effort and bypassable (a key in an env var or a
  differently shaped string leaves it at 0), so it is reported beside the SQL-checked counters and
  never gates.
- (c) row 235's cover fed to a Stage D hit → refused, `grey_hits_below_title_gate=1` if bound; the
  constructed chapter with the router off → `chapters_routed_to_scidb=1`; a ledger DDoS-Guard page fed
  to the archive route with the title check off → `challenge_booked_as_miss=1`; a request to a host
  outside the allowlist → refused before the network, `shadow_requests_outside_policy=1` if it reaches
  it; the `sci.bban.top` rung enabled with `litkb-shadow-hosts` open → `new_hosts_without_ruling=1`;
  a credential planted in config → `credentials_stored=1`; the constructed Elsevier first-page response
  → `tdm_stubs_bound=1` if bound; a tracker row whose identifier matches no work →
  `coverage_rows_unclassified=1` unless marked; the five-way re-read skipped on one archive-miss row →
  `archive_misses_untyped=1`; two shadow probes issued concurrently on purpose →
  `shadow_misses_from_concurrent_probes=1`; a referee report dropped → `unvalidated_items=1`.

#### Test-set commands (run from Scripts/, read-only)

```
# the archive misses, Sci-Hub blocked rows and open-access bad-file rows by Crossref type (writes phase4/qc/litkb_acq_probe_baselines.md)
py -3.12 qc/instruments/litkb_acq_probe_baselines.py
# the manual-step rows (the browser route), by work
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute(\"SELECT count(*),count(DISTINCT work_id) FROM litkb.acquisition_attempts WHERE route='browser' AND status='manual-step'\").fetchone())"
# the grey rows already on disk and not in main
py -3.12 -m litkb reap --dry-run
# the tracker rows the coverage instrument must classify (the record-class filter's input)
py -3.12 -c "import csv;r=list(csv.DictReader(open('../Reports/literature_tracker.csv',encoding='utf-8-sig')));print(len(r),sorted({x['Status'] for x in r}))"
```

Kam: all of this block's rulings were decided 2026-09-22 — `litkb-institutional-access`,
`litkb-shadow-hosts`, `litkb-tdm-keys`, `litkb-crc-book`, `litkb-coverage-definition`,
`litkb-blocked-works-grade`, `litkb-scihub-parked`, `litkb-e23-residue-copies`; the Elsevier key
is in place but buys no full text as configured (Stage H cites the measurement); Kam's request to
Elsevier API support for non-subscriber access is the open action (one re-key answered identically); there is no Springer key.

### S4.7 — Extraction agreement: repair the cause, tier the text, measure the scans, verify the math

Inserted 2026-09-22 from the survey report §5. Every item is a RELAYED design and UNVALIDATED under
the S4.5 protocol (referee per rung class: the CMap layer, the gates, the text referee, the scan
harness, the math ladder). S4 makes every acquired file readable or classified; this session makes
the reading TRUSTWORTHY in tiers, because a verbatim quote with a page number is the base's whole
contract and today `extracted: true` says nothing about how good the text is. Two boundaries the
survey measured and the plan adopts in those words: a searchable text layer on nearly every scan is
achievable; quote-grade accuracy on the 1950s–90s scans is NOT demonstrated by any system on any
benchmark (every one scores far lower on old scans than on everything else), so a quote is promotable
only from HIGH-tier text and a LOW-tier page is search-only. And the OCR voting precedent COLLAPSED on
inspection: the cited gain was five configurations of one engine, and the same arbitration on an
untuned corpus measured inside the noise — so this session MEASURES voting on the corpus's own scans
before adopting anything, and reports UNDETERMINED if the effect is inside the noise (CLAUDE.md §3.5).
GPU: the T2000 runs the classical engines, the coherency referee and the whole math-verification
layer; every vision-language rung is a Colab queue, and that queue is `litkb-s47-colab-queue` (decided: T4
runtimes as the session needs, no further ask).

Work
1. **The CMap repair layer, above every ligature fix** (survey §5.2; one repository's Rust, ported onto
   pikepdf, whose qpdf bindings reach a font's `/ToUnicode` stream — pypdfium2 cannot): the
   five-source ToUnicode fallback ladder (the stream's CMap → a sequential remap → the encoding's glyph
   names → the embedded TrueType cmap → the CID collection), the `ControlDestination` repair that is the
   named CAUSE of ligature garble, glyph-name decomposition at source with "every component must read,
   or the name does not", the overlong-`/BBox` repair that turns a silently empty page back into a page
   (so OCR never transcribes a blank), and the abandon rule — more than half the codes unmapped → return
   nothing and fall through. `litkb-ligature-repair` becomes the downstream normaliser of what survives.
   Rows: the ligature-damaged files and blocks enumerated by file_id and block_id in
   `Reports/litkb_ligature_c0_2026-09-19.csv`, with the quote-hazard rows of
   `Reports/litkb_ligature_quote_hazard_2026-09-19.csv` beside them (that ruling's referee report
   names none of them — `grep -ci ligature` on it returns 0, so the CSVs are the row home); plus a
   CONSTRUCTED corrupted CMap, in those words.
2. **Bind-time validity gates** carried from S4.5's acceptance test into extraction: `qpdf --check` with
   its exit codes read correctly; the vector-complexity pre-filter (10,000 graphics ops AND a 20:1
   ratio) rewritten to FAIL CLOSED — the reference implementation fails open on any exception — because
   GIS classification maps and contour plots are what hangs the text extractor; `word_count` stored on
   every file beside the existing `pages`; the stub and volume detectors run again on the extracted
   text. Rows: the files the run itself finds over the pre-filter's constants, recorded as it goes.
3. **Text agreement in tiers**: an LM-coherency referee (a small CPU language model's mean per-token
   log-likelihood over each candidate's page) chooses among GROBID, Docling, `pdftotext` and `pdfium`,
   because the current rule-based reconciliation cannot tell when it was wrong and a dictionary
   hit-ratio would reject good OCR of the maths-heavy statistics papers; per work the base records the
   winning rung, every rejection with its reason, the pairwise character error among candidates and a
   quality TIER; the LOW-tier quote refusal is ENFORCED in SQL, in the same SECURITY DEFINER shape as
   `add_evidence`, never in Python alone. No general multi-extractor reconciler exists to adopt; this
   is a small piece of original work, and the survey names the merge rules to borrow. Row where the
   current reconciliation is KNOWN to have chosen wrong: S2's Copernicus PDF, for which Docling produced
   nothing and GROBID carried the work (`Reports/LITKB_FIRST_WORK_2026-09-21.md`) — shared with S4's
   bed.
4. **Scans, measured before adopted** — and the harness is the size of a handful of files today, with
   NO OCR engine installed on this machine (docTR, RapidOCR and Tesseract are all absent; the command
   below counts the rows and a `py -3.12 -c "import importlib.util; ..."` probe answers the engines),
   so the session's FIRST step is to enlarge the harness from the base's own scans (`has_text_layer`
   false in `main_files`) and install the engines, or to report the scan class UNDETERMINED in those
   words rather than score three engines on a handful of pages: on the corpus's no-text-layer scans (the command below lists
   them; S4's first scan rows) a hand-corrected gold page each, AUTHORED BY THE REFEREE and not by the
   builder that scores engines against it (a gold page written by the scorer, or read off the page
   image by a model, is a correlated reading, not ground truth); then Tesseract 5 variants, docTR and
   RapidOCR on the T2000, with old-scan layout segmentation shared across engines (eynollah in WSL) so
   line-level alignment is possible at all; LV-ROVER's arbitration SHAPE with the lexicon built from
   litkb's own registry metadata used as a SHIELD (an anchor word in the lexicon is never overridden;
   never shorten; never touch short tokens or numbers; edit distance ≤ 2); a trained character
   corrector only WITH its sliding-window vote (the survey's one clean number: positive with the vote,
   negative in every configuration without it); character error rate with a confidence interval per
   page against the gold; vision-language OCR on Colab under `litkb-s47-colab-queue` (ranked on the
   old-scan axes, never on the overall score) — under `litkb-colab-page-boundary` (decided 2026-09-22 on the
   orchestrator's judgement, Kam: "Implement your best judgement on S4.7"): only horizontal STRIPS
   leave the laptop, cut the way `pipeline/litkb/extract/colab_formula_worker.py` crops formula regions
   and keyed by page and order so the text comes back addressable; no page ever leaves whole; a strip
   rung that cannot be built is reported UNDETERMINED, never a page shipped — accepted at HIGH
   tier only when it agrees with the
   classical consensus above a threshold — a fluent hallucination scores well on every coherency and
   dictionary gate, and only agreement catches it; the known-bad for that guard is a CONSTRUCTED
   fluent invention (a page whose VLM transcript is a plausible paragraph the scan does not contain),
   in those words. Preprocessing is a VARIANT rung, never mandatory. If the arbitration's gain is
   inside the interval, the report says UNDETERMINED and the tier stays LOW.
5. **Math verified without a second decoder** — under `litkb-second-formula-decoder` (DECIDED
   2026-09-19: the second decoder is dropped; pix2tex is out on nondeterminism; the re-open condition
   is a review whose conclusion depends on a mathematical claim, and the entry bar is a seeded,
   deterministic protocol). This session does NOT re-open it. What it builds is the verification
   ladder on the ONE decoder's output — `latex_status` is a COLUMN of the table `litkb.equations`, not
   a Python module, and its live values are unverified · stable · contaminated · degenerate ·
   unstable · NULL (the command under "Test-set commands" counts them) — stopping at
   the first rung that decides: KaTeX parse → pdflatex compile with a kill timer → degeneracy check →
   an image check of the rendering against the ACTUAL crop — the rung that needs no second reading and
   catches a wrong one — so `latex_status` gains `verified` and `held` BESIDE the four values it
   already holds, which keep their meaning and are not migrated away, per formula; NULL means the
   ladder has never run on that formula and is REPORTED as `latex_status_null`, never rewritten. Free triage first by math font names and math-unicode ratio, so the report can say how
   many math-bearing works are born-digital and how many are scans — a question two survey rounds
   could not answer without the corpus. IF the re-open condition is met, the second decoder enters
   under the ruling's bar — greedy decoding with a fixed seed; sampling-based self-consistency does not
   qualify — and CDM agreement (render both readings with per-token colours, match token boxes, score
   F1; it needs no truth) becomes the stage before the image check. Compare renderings, never LaTeX
   source, and never a computer-algebra equivalence. Thresholds are the survey's PROPOSAL, calibrated
   here on a CONSTRUCTED known-bad formula set (dropped subscripts, mismatched delimiters, matrix
   environments), in those words, before any is a gate.

Done-state
- (a) the CMap layer and its tests; the gates; the referee and the tier column with its SQL guard; the
  scan harness with its gold pages and its CER report; the math ladder and its calibration; a report
  under Reports/ (LITKB_AGREEMENT_<date>); referee reports; SCHEMAS rows for tier, `word_count` and
  the `latex_status` values; the manifest frozen by `agreement --freeze`.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py agreement --manifest <manifest>` → GATED:
  `cmap_abandon_rule_silent=0` (files whose decode had more than half the codes unmapped and no
  fall-through recorded) · `complex_pdfs_hung=0` (extraction runs past the timeout on a file the
  pre-filter should have refused) · `works_without_tier=0` · `quotes_from_low_tier=0` ·
  `scan_pages_without_cer=0` · `vlm_pages_at_high_without_agreement=0` ·
  `formulas_verified_without_image_check=0` · `formulas_verified_by_source_diff=0` ·
  `unvalidated_items=0` (the five rung classes). REPORTED: `files_without_word_count`, the scan
  arbitration's effect as a value and an interval, the born-digital versus scan split of math-bearing
  works, and the vision-language rungs' status (UNDETERMINED without the queue).
- (c) a good PDF with its ToUnicode CMap corrupted (constructed) → the abandon rule fires AND the
  repair recovers the text, both asserted; the abandon rule's fall-through record suppressed →
  `cmap_abandon_rule_silent=1`; the complexity pre-filter given a raising input → refused (fail closed),
  never `False`, and with the rewrite reverted a vector-heavy file → `complex_pdfs_hung=1`; a quote
  recorded from a LOW-tier page → refused by the SQL guard, `quotes_from_low_tier=1` if it lands; the
  constructed fluent invention accepted with the agreement check disabled →
  `vlm_pages_at_high_without_agreement=1`; a formula marked `verified` with the image check disabled →
  `formulas_verified_without_image_check=1`; two LaTeX strings differing only in style compared by
  source → `formulas_verified_by_source_diff=1`; the constructed dropped-subscript formula → `held` or
  `unverified`, never `verified`.

#### Test-set commands (run from Scripts/, read-only)

```
# the no-text-layer files in main (the scan harness's rows), by work key
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute(\"SELECT w.key, f.rel_path, f.pages FROM litkb.main_files f JOIN litkb.main_works w ON w.work_id=f.work_id WHERE f.status='active' AND f.has_text_layer=false ORDER BY 1\").fetchall())"
# files with formula LaTeX today, and the latex_status values the ladder must upgrade
py -3.12 -c "import psycopg;c=psycopg.connect('host=localhost port=5433 dbname=litkb user=litkb_reader');print(c.execute('SELECT count(DISTINCT file_id) FROM litkb.blocks WHERE latex IS NOT NULL').fetchone(), c.execute('SELECT latex_status, count(*) FROM litkb.equations GROUP BY 1').fetchall())"
```

Kam (ruled 2026-09-22): `litkb-s47-colab-queue` — T4 runtimes as needed, no further ask;
`litkb-coverage-definition` — searchable text and quote-grade text are separate tiers;
`litkb-second-formula-decoder` stays decided unless its re-open condition is met.

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
- **Kam** names the topic (2026-09-22: label transfer across years under seasonal difference, unless
  renamed before launch) and applies migrations BEFORE the run, none during; the tracker edit of
  `litkb-tracker-corrections` and the retirements of `litkb-e23-residue-copies` and `litkb-crc-book`
  land before the run.
- **The measured defects of the loop, fixed as this session's first work; the run does not launch
  until the counters below read 0** (round 4, `Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md`
  — most a real row set in hand with a kill; the two BUILDS among them (the run identity, the
  `review_check` read tool) and the CONSTRUCTED-only inputs are labelled as such; every number a
  crawler produced about its own prototype is NOT acceptance evidence and the referee re-fires it): the quote locator refuses every
  ligature-damaged block the search index can now serve, because the ligature migration repaired the
  index only (fix in the locator and its trigger; kill: a quote spelling the ligature WRONGLY must still
  refuse); the anchor's single index — the database as the one authority (round 4 §1.2 R3, a defect
  fix; kill: a CONSTRUCTED reference whose DOI is in the manifest but not among the identifiers must
  not anchor); the trigram search leg costs most of every search and returns nothing (an expression index
  that recomputes the normaliser on recheck, and a similarity floor the corpus cannot reach — fix the
  operator and store the normalised column; kill: leg 3 deleted entirely → the gate goes RED, which
  today it would not; and the harness must reproduce the old numbers before any new leg is scored); table blocks store empty text, so no evidence row on a table can exist while the
  tool advertises the kind (honest refusal now; kill: a search asking for the table kind returning rows
  → RED; cell-addressed evidence after S5); backward-snowball
  candidates are written with no workstream and reachable from none (one WHERE clause AND one line in
  the scout's tool list, or the scout still cannot see them; kills: a fresh workstream's candidate
  listing must return them AND must NOT return another workstream's manual rows — leakage is RED); the seeding guard reads one file while the launch
  kit is untracked and carried a work key when read (whether that was a violation is Kam's ruling,
  recorded here and not adjudicated), and a paper named by TITLE passes it (the guard covers the whole
  launch kit by glob and a 13-gram check; kill: the CONSTRUCTED seeded template must refuse); the run has no identity — a BUILD from the record's §1.9, UNVALIDATED: a run id minted at freeze on
  the DATABASE clock, frozen fields immutable, a heartbeat row, attempts and crash disposition declared
  as data, the spec as the run's first artefact (kill: a frozen field changed on resume → error, not a
  silent new run); K1 gains a deterministic numeric-containment rung (a magnitude in a claim absent from
  its byte-identical quote → FAIL; the crawler's own run on the real reviews is its prototype number,
  not evidence — the referee re-fires it on the CONSTRUCTED mutation and on the real reviews) and a
  notice for a cited work with no drop-off behind it; K2's rubric names its overreach classes and the
  planted mutation stops being catchable by a regex — UNVALIDATED in those words, because no real
  review carries a hedge to strip and the stronger mutation may come back SUPPORTED (a null result the
  report states, never hides); the review writer can ask `review_check` as a read tool before it hands
  in — a BUILD, whose kill runs against the EXISTING command first (the constructed writer prompt must
  fail it before anything is wrapped); the evidence row records which match rung and what
  diff a quote passed on, a cross-page quote refuses with both block ids instead of missing silently,
  and a refusal returns the matched prefix; discovery gains a
  recall counter against the tracker and a stop rule with a number (kill: a held-out extracted tracker
  work absent from the candidates → RED; the capture-recapture estimator is an after-S5 build and no
  S5 kill rests on it); the soak ledger gains a START sentinel so a crashed night counts; the approve
  guards are fired on live-shaped rows in the next second session (one command, a pasted error —
  before the run). Each fix is refereed by a non-proposer on the rows the
  record names; a mutation that ERRORS rather than answering worse is DID-NOT-FIRE.

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
- THE RUN: headless, topic named by Kam; scout → hunts with real acquisitions through the whole ladder
  (S4.5–S4.6) → record → brief → writer → `review-check` → Codex. K2 fires per `litkb-k2-no-seeding`
  (decided). Every drop-off's outcome carries its `kind` and `articleVersion`; a quote is recorded
  only from HIGH-tier text (S4.7). An expectation can go
  UNCONFIRMED without its paper being acquired; the counters separate the two.

Done-state
- (a) the review under `Reports/reviews/`; a proving-run-3 report + frozen manifest under
  Reports/; the repair pass's report and its second-session log; the protocol doc + its tests.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py run --manifest <manifest> --audit` →
  `distinct_new_works>=5 bound=extracted=searchable` (over those new works)
  `missing_dropoff_outcomes=0 hunts_over_budget=0 citations_from_defective_rows=0 K1=PASS K2=FIRED
  claims_ungraded=0 overreach=0 operator_interventions=0 migrations_during_run=0
  magnitude_not_in_quote=0 quotes_refused_on_ligature=0 search_seconds_over_budget=0
  citation_candidates_unreachable=0 candidate_leakage=0 prompt_contamination=0 runs_without_id=0
  seeded_miss_unrefused=0 table_kind_advertised=0 unvalidated_items=0` (the budget for a search call is
  frozen in the manifest; `citation_candidates_unreachable` counts citation-sourced candidates a fresh
  workstream's listing does not return; `unvalidated_items` counts the entry-condition items whose
  referee report the manifest does not name or whose report has no `fired:` line), with
  `expectations_unconfirmed`, `dropoffs_not_acquired`, `discovery_recall`, `citations_outside_this_hunt`,
  `stop_rule_yield` and `search_leg3_rows` printed unbounded.
- (c) the grader on a one-character mutation → FAIL (byte verification, re-fired not assumed); a
  claim mutated to assert **causation** while keeping its valid descriptive quote → the Codex
  stage must flag it (overreach is the K1 escape no deterministic grader closes); the protocol
  test fails on a pre-named work; the budget set to one second and any drop-off with a live route hunted →
  `hunts_over_budget>=1`; a citation built from a row with empty `given` → the builder refuses,
  `citations_from_defective_rows=1` if one prints; the run re-hunting a check-1 refusal bare → the
  protocol test goes RED; a claim carrying a magnitude its byte-identical quote lacks →
  `magnitude_not_in_quote=1`; a ligature-damaged real block quoted → accepted, and quoted with the
  WRONG ligature → refused; the trigram leg's fix reverted → `search_seconds_over_budget>0`, and leg 3 deleted → RED; the candidate
  WHERE clause reverted → `citation_candidates_unreachable>0`, and widened to every workstream →
  `candidate_leakage>0`; a search asking for the table kind that returns rows →
  `table_kind_advertised=1`; the launch kit with a work key appended, or a paper
  named by title → `prompt_contamination=1`; a run launched without a frozen id → `runs_without_id=1`;
  a held-out tracker work absent from discovery → `seeded_miss_unrefused=1`.

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
| **Binding: identifier-in-file ladder and a font-size title test** (the post-extraction content gate moved into S4.5's acceptance test and S4.7's bind-time gates; what stays here is identity-by-embedded-identifier and the font-size title heuristic). Measured: check 3 rests on title + surname only — the registry's DOI or arXiv id is never passed into `bind()`; `pdf_shape` tests a `%PDF-` header and a `%%EOF` trailer and nothing else; there is no entropy, printable-ratio or minimum-text test anywhere; and the metadata fallback binds a page with ZERO extractable characters at ratio 1.0 on `/Title` + `/Author` alone (latent: every live bind that took the `pdf-title` path has a text layer). Row 235 is a WINDOWING limit (a title split over more lines than the scoring window covers), not a threshold. | stamp-robust binding; `bad-file` detection on every route; the blank-page bind | survey D: pdf2doi's ladder (VERIFIED, licence from setup.py), JabRef's TitleExtractorByFontSize (VERIFIED at a pinned commit; licence ASSERTED), paper-qa's `maybe_is_text` (VERIFIED). Whether the arXiv stamp's font is smaller than the title's on a REAL page is UNMEASURED — measure it on the E25 PDFs first | PREREQUISITE: the corpus title-ratio sweep becomes an instrument under qc/instruments/ writing a CSV under phase4/qc/ (CLAUDE.md §3.4b) — the E25 sweep's per-file output exists at no path and its population has already drifted. Then: `qc/testdata/litkb_binding_stamps/` fixtures via `qc/test_litkb_binding_stamps.py`; the E25 PDFs; 235's filed PDF; a challenge page's bytes (the Sci-Hub attempt detail in `Reports/LITKB_EDGE_RUN_2026-09-21.csv` names the mirrors); a stub PDF with matching `/Title` + `/Author` and an empty page | the content gate given challenge bytes behind a `%PDF-` header → refused, never bound; the stub with matching metadata → `binding-pending`, never `bound`; the ladder given a PDF whose embedded DOI is another work's → refused (auditor-e25's cross-title probe is the shape); a page whose largest font is a running head or journal name (235's cover is the real case) → the font-size candidate refused by check 3's ratio, never bound on font size alone |
| **Both identifiers on one admission**: check 1 requires EVERY passed identifier to confirm, so `admit --arxiv X --doi 10.48550/arXiv.X` refuses although the DOI form confirms, and admitting by the DOI alone stores no arXiv id, so a later arXiv hunt is a duplicate | `Reports/LITKB_RULED_HUNTS_2026-09-21.md` §8 (measured once) | litkb's own code | the ruled run's arXiv rows; negative — 187's confirmed DOI paired with a CONSTRUCTED wrong arXiv id, stated as constructed | an admission storing an identifier no registry confirmed → refused; the constructed pair → refused |
| **HTML snapshot → searchable blocks, live**. A live HTML-only hunt of an unknown work is DONE (row 194); its snapshot holds no blocks because extraction was off | `docs/SCHEMAS.md` "A web source that is a page" proved in replay only | litkb's own code | positive today: 194's existing snapshot run through extraction → searchable blocks (no live fetch needed); negative: the register's URL-HTML-only rows replayed (E06's class); a live unknown page only if S5's scout drops one off | a page with no claimed title, author and year → `refused/incomplete-record`; 194's snapshot with its text emptied → `zero-content`, never searchable |
| **Citation anchoring, in order**: a crosswalk instrument that makes the frozen reference gold joinable to the live base (today it cannot be); a raw-string validator behind the Semantic Scholar candidate; the resolution versioned so a ladder change re-runs it; a reader tool over the citation graph | anchoring is coverage-bound after S4's drain; nothing scores until the gold joins | `Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.2 (litkb's own tables; Crossref's reference matcher and the open citation indexes read in source) | the references table, the refmatcher branch's gold once joinable; negatives: the must-not-link book reviews in that gold, a reference mutated to another year | the gold stem prefixing two live keys → refused; a ladder change without a version bump → RED; a mutated year anchoring → RED |
| **Discovery beyond recall**: capture-recapture estimation with a refusal below three arms; a keyless forward-chasing leg; a three-state candidate identity (merge, hold, distinct); query expansion from the base's own corpus with a random leg; a readable scout confidence | the scout's recall counter (S5) says how much is missed, these say what to do about it | `Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.1 (screening and snowballing tools read in source; two estimators fired on the tracker's own rows) | the tracker by search phase; the scout-run ledger; a held-out extracted tracker row | the estimator on too few arms → refuses; a forward leg returning nothing for a known-cited work → RED; the merge threshold lowered until a wrong pair merges → RED |
| **Cell-addressed numeric evidence**: a cell address on the evidence row, a whole-cell verification branch in the trigger, header path and caption as their own rows, a numeric use kind with derived value, unit and scale; never a lowered quote-length floor | a quoted number becomes verifiable against a cell, not a text match the table block cannot give | `Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.5 (the base's own table cells; table-QA provenance repos read in source) | the table blocks and cells in the base; the tracker rows whose relevance quotes a number; the row whose numbers may belong to another paper | a number changed by one digit → FAIL; the same decimal from a different cell on the page → FAIL; a number that appears only in a caption → refused as a cell |
| **Search, after the defect fixes**: hybrid fusion as one SQL statement; chunks built from blocks so a hit stays a quotable block with a page; a small ONNX cross-encoder rerank over a fused depth; query-side expansion deferred; the survey recommends AGAINST swapping in a scientific embedding model or a late-interaction index on this corpus | the parked vector leg, with the harness that must reproduce the old numbers first | `Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.3 | the P7 gold and floors — the gold cannot be replayed as-is (it anchors on character offsets into text dumps), so the re-anchoring is CONSTRUCTED and a referee builds it; reference-only negatives | the harness on the old lexical legs must reproduce the report's numbers; a rerank that demotes every gold hit → RED |
| **Promotion, the reversible half**: `withdraw_version` on a promoted version (the operator-bind gate is S4.5's, `litkb-from-file-version-state` having been decided for the proposal path; the approve guards are fired BEFORE S5 — an S5 entry condition) | the promote stage has no live evidence yet | `Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.8 | the promoted admissions; the one proposal | the proposing session approving its own proposal → refused; a withdraw on a never-promoted version → refused |
| **Replay cache fold**: fold litkb's partial caches (the disk cache, the caching client, the hand-built provenance envelope) into the one recorder, last, because it touches the reference-resolution path anchoring depends on | one cache, one identity | `Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.10 | the register rows; every PDF the reference path decodes | a PDF put through the folded cache must come back byte-identical — today it cannot, the decode path alters it — so that is the kill |
| **Re-ingest cadences as SQL over the ledger, per-source scoring and the host blocklist** (survey guards 6 and 7 beyond the registry S4.6 moves the mirror lists into; the budget object, guard 12, is S4.5's) | retries that are hand-run today | survey E (sandcrawler's dump_reingest SQL, VERIFIED) | the ledger's typed misses | a permanently-dead sub-status selected by the re-ingest query → RED |

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
S6's measured pain is ZERO today (round 4 §1.7 says so in those words): every mechanism below is a
RELAYED design and UNVALIDATED until the S5 brief exists and a referee scores it; the one measured
item is the laundering surface.

- docs/LITKB_SYNTHESIS_GRAMMAR.md: inputs = the brief's VERIFIED lines + `SCIENCE.md` +
  `decisions.yaml`; output under Reports/syntheses/; every inference sentence ends with
  `[work_key p.N #block]` (a VERIFIED line) or `[own reasoning]`; a closing section of
  decision-shaped recommendations, each tied to its lines.
- `litkb synthesis-check` (K3): sentence coverage; every cited block VERIFIED in the workstream —
  read from the WORKSTREAM'S OWN LEDGER, never from the brief, because the brief admits promoted uses
  and the plan's laundering kill holds only while zero uses are promoted (`Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.7: the first
  promotion Kam merges opens the surface with no code change); an EXPECTED line cited = FAIL (its negative is CONSTRUCTED — the runs in hand hold no
  such line — and the fixture says so); findings
  bound to source hashes by extending `review_context`; the `[own reasoning]` tag a typed token; a
  numeric-agreement check on every sentence ending in a locator (the same rung as K1's); a citation
  cap per sentence (the constant `MAX_CITATIONS_PER_SENTENCE = 3`; over the cap is a FAIL) and an
  overcite NOTICE, never a fail; a closing recommendation may be UNDETERMINED only if it names
  its gap; locators for `SCIENCE.md` and `decisions.yaml` resolvable by code; no invented certainty
  vocabulary. Known-bad fixture under qc/testdata/litkb_synthesis/ — and the hardest negative needs no
  construction: verified triples that exist only in run 1's workstream, cited from a synthesis that
  declares run 2. Written by the orchestrating model; Codex reviews against a fixed report schema.

Done-state
- (a) the grammar; the checker + tests + fixture; the synthesis for S5's topic; the Codex report.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py synthesis --manifest <manifest>` →
  `sentences_ungraded=0 unlabelled_inferences=0 expected_lines_cited=0 unsupported_attributions=0
  laundered_citations=0 citations_over_cap=0 undetermined_without_gap=0 numeric_disagreements=0
  unvalidated_items=0`, with `overcited_sentences` printed as a notice count.
- (c) provenance laundering: cite a real block verified only in ANOTHER workstream (the run-1-only
  triples) → K3 RED, asserted on the finding CODE, not the exit status, and still RED after a
  promotion is merged; attach a valid VERIFIED citation to an inference the quote does not support →
  the Codex stage must flag it; drop one `[own reasoning]` tag → `unlabelled_inferences=1`; a sentence
  stating a number its quote lacks → RED; four citations on one sentence, the cap being three → `citations_over_cap=1`; an
  UNDETERMINED recommendation with an empty gap → `undetermined_without_gap=1`; one character of a
  `SCIENCE.md` pointer altered → RED.

### S7 — Seven nights unattended (ops)

Kam's ruling (2026-09-20): seven nights, STARTED EARLY. S1 installs the nightly smoke task
(see S1 Work) so the nights accumulate while S2–S6 proceed; S7 extends it with the full
`doctor` and reads the log. No calendar cost at the end.

Work
- `litkb doctor`: DB reachable; migration tip == repo tip; dump age < 26 h AND the dump RESTORES —
  a FULL restore to a scratch database or `pg_restore -f -`, never the list-only check, because round
  4 fired the plan's own corrupt-dump known-bad with inputs CONSTRUCTED from a real dump (a bit flip,
  a truncation, a zeroed block, each re-stamped fresh) and the list-only check passed ALL of them (`Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md` §1.11; see
  `pipeline/litkb/ops/nightly_dump.py`); worker databases free or leased by advisory lock (the count
  is a query: `SELECT datname FROM pg_database WHERE datname LIKE 'litkb_test%'`); MCP server code
  stamp == the tree's, through a `litkb_version` tool carrying a CONTENT digest over the loaded litkb
  modules' bytes (never their mtimes — a byte-identical checkout rewrites every mtime and must NOT
  report a mismatch), so the post-merge staleness trap becomes a measurement; token present and valid; a registry of checks with `--only`, an unknown
  check named on exit; a timeout that names the check that hung. Fixture qc/fixtures/litkb_doctor.json
  mutates each check separately.
- A scheduled nightly task runs `doctor` + a smoke hunt on a known-extracted key + a smoke
  search, appending to a soak CSV under Reports/ — writing a START sentinel row first, because a
  night that crashes before its end row writes nothing today and `incomplete_runs` is uncountable; the
  `soak` subcommand gains a consecutive-green clock and a scheduler witness. The agent boundary moves
  from prompt to server IF the library's interceptor bites in the installed server version — the
  record could not verify that, so it is UNDETERMINED until the CONSTRUCTED wrong-role call is refused
  — with a fail-closed audit middleware, the role allowlist enforced at the server (the hooks exist and
  are never installed; every tool is served to every client today), annotations on every tool, the
  role recorded on every write. The mutation ledger becomes a `check.py` rung
  (live-DB subset opt-in); the harness diffs against its baseline; the tolerated red and the
  census pins are retired or proven passing; `report_path` bounded + its decisions line; the
  drift gate covers `.claude/skills/literature/SKILL.md`; a cold-start test: a Sonnet agent given
  only the repo runs S5's first three steps with 0 questions.

Done-state
- (a) doctor + fixture + tests; the scheduled task; the rung; docs; the soak CSV; the cold-start log.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py soak --log <soak.csv>` →
  `elapsed_hours>=168 missed_scheduled_runs=0 interventions=0 incomplete_runs=0` ·
  `py -3.12 qc/check.py` → GREEN with no tolerated reds · `py -3.12 -m litkb doctor` → all OK ·
  `incomplete_runs=0 restore_proof=full code_stamp_mismatch=0 wrong_role_calls_served=0
  unvalidated_items=0`.
- (c) each doctor check mutated in isolation → that check RED; a corrupt fresh dump (the three
  corruptions of round 4) → RED under the FULL restore, and the list-only check must be shown to pass
  them so nobody reinstates it; a night killed after its start sentinel → `incomplete_runs=1`; the
  server's code stamp differing from the tree's content → RED, and a byte-identical re-checkout
  → NOT red; an acquisition tool called under the review-writer role (CONSTRUCTED) → refused at the
  server, never by the prompt, `wrong_role_calls_served=1` if it runs; `report_path` containing `..` → refused; a
  SKILL.md route not in `ROUTES` → the drift gate RED.

---

## Per-session protocol

**First command of every session**, before any hunt or launch:
`py -3.12 qc/instruments/litkb_acceptance.py preflight` → every counter 0
(`stray_tokens migration_mismatch mcp_servers_missing main_not_at_parity soak_stale`). A red
counter is the session's first task, not a note. Then `/mcp` reconnect if the open session
predates the last merge (not measurable by the instrument; it prints the HEAD it checked).
Headless launches: `Reports/LITKB_SCOUT_LAUNCH.md` §4 — bash, a prompt FILE, the first
`ws_open` slug checked within the minute. **Launch only with the tree on `main` at parity**:
`git rev-parse --abbrev-ref HEAD` prints `main` AND preflight's `main_not_at_parity=0` — the
instrument compares local `main` to `github/main` and cannot see a checkout sitting on a work
branch, so both halves are read. The launch kits inherit this line; a session launched off a work
branch commits onto somebody else's branch. **Only Kam launches a session**
(`litkb-session-launch-authority`, 2026-09-22): a session's LAST act is to write the next session's
kit under _derived/<next>/ — the prompt from that session's plan block, mcp.json with its
LITKB_SESSION, the launch script — say in "Where we are" that the kit is ready, and STOP; it never runs
`claude`, never opens a window, never creates a runtime for another session. The 2026-09-20 chaining
instruction is withdrawn.

Orchestrator = the chat session; ≤ 3 agents. Opus **builder** in its own worktree with its own
`litkb_test_wN` — free: w3, w7, w9; w2, w8, w10 and w11 are RESERVED (w8 by
`qc/instruments/litkb_s3a2_mutations.py`, w10 by `qc/instruments/litkb_edge_run.py` and
`qc/test_litkb_edges.py`), and taking a reserved one collides with the one-pytest-per-worker-database
hazard below → Opus **auditor** re-runs every claim from source on a
fresh worker DB (every real defect so far came from an auditor) → fix → `py -3.12 qc/landed.py`
→ commit on `work/<date>-<slug>` → landed per CLAUDE.md §3.1 → Kam applies any migration. Codex
reviews every grammar and is the last stage of every proving run. Worker reports:
`D:\tools\claude-config\jobs\litkb-<session>\<worker>.md`, ≤ 15 lines returned. Migration
numbers reserved in `pipeline/litkb/db/migrations/_reserved.txt` first. Concurrency and model
rules: `litkb-p0-foundation`. Base brief: `docs/LITKB_AGENT_BASE_BRIEF.md`.

**Codex stage** (the adversarial read, last stage of every proving run; built between S1 and S2).
When Codex's quota is exhausted (it was, 2026-09-22 05:06 PDT, mid-survey), the read is OWED, not
skipped: an Opus adversary stands in, the plan and the report say so in those words, and the Codex
read runs when the quota returns.
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
about itself, and a design validated on synthetic input only says so in those words. A mutation
that ERRORS rather than answering worse is reported as DID-NOT-FIRE and the harness is restructured;
a known-bad the plan says "already fires" is re-fired by the referee and its output pasted; numbers a
proposer produced about its own prototype are not acceptance evidence (the round-4 record names its
own); and a report that consumes a survey conclusion no different-model-family read has covered says
so in those words.

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
| no extraction queue, no fail-closed page cap, zero-content/multi-file works, cross-page `page_no`, metrics in JSONL, superseded run sets, the `book` residue class, a quarantine with no database state; the no-text-layer scans | S4 |
| the substrate: `blocked` in no route's `DEAD_STATUSES`; registry transients re-run by hand; the arXiv-client question; Crossref `relation` dropped and its yield unmeasured; a different DOI called a duplicate at 0.70; no ISBN scheme; a long creator string crashes the key rule; no served-bytes hash on the attempt row; a re-served bad file re-quarantined, never skipped; a refused-duplicate landing left unowned on disk; no second-session refuse verb; the approve guard never made to fire. The ladder: an untyped `bad-file`/`blocked` ledger where mature codebases carry typed sub-states; no landing-page-to-PDF rung (Unpaywall's own answers are landing pages litkb books as `bad-file`); no record-class filter, no work-class router (preprints sent to the archive route); Crossref `link[]` never read; no Semantic Scholar or OpenAlex PDF lookup; no Wayback rung; the `bad-file` rows never read | S4.5 |
| no grey-literature rung at all (USFS, USGS, NTRS, OSTI, DSpace with MD5, ArcGIS Online, city portals); the book namespace unreachable by construction (scidb by DOI); DDoS-Guard blocks booked as `not-in-archive`; Sci-Hub mirror lists compiled into `run.py`; no credentialed rung and no ruling on institutional access; no coverage instrument against the tracker | S4.6 |
| ligature repair at the symptom, not the CMap; the vector-complexity pre-filter absent (GIS figures hang the extractor); `extracted: true` with no quality tier, so a LOW-tier scan can supply a quote; no measured OCR arbitration on the corpus's own scans; formula LaTeX `unverified` with no verification ladder; the L4 formula re-crop of Reynolds_2000 and Montgomery_1991 never ran; no `word_count` on files | S4.7 |
| run-2 review fails the tightened grader; no run protocol and no run entity; the promoted tracker-era metadata; no per-hunt time budget; no rule retiring a superseded drop-off; the two builds the rulings assign to S5 (ISBN → md5; registry-over-claim on a human's say-so); the loop's measured defects (the quote locator refusing ligature-damaged blocks, the trigram leg returning nothing, tables unquotable, orphaned snowball candidates, a seeding guard that reads one file, K1 without a numeric rung, K2's regex-catchable plant, no discovery recall counter, no soak start sentinel) | S5 |
| no synthesis grammar or K3; the laundering gate must read the workstream ledger, not the brief | S6 |
| no doctor; the list-only dump check passes corrupted dumps; a crashed soak night is invisible; the MCP staleness trap unmeasured; the agent boundary enforced by prompts, not the server; ledger not a `check.py` rung; harness `run_one` calls any failure FIRED (no per-row baseline diff); `report_path` unbounded; nightly dump task points at an old worktree | S7 (dump task: Kam, now) |
| the survey's remaining designs and litkb's own: two-tier resolution, doi.org negotiation, the identifier-in-file binding ladder (with the sweep instrument as its prerequisite), both identifiers on one admission, snapshot → blocks live, re-ingest cadences, citation anchoring in order, discovery beyond recall, cell-addressed evidence, search after the fixes, the reversible half of promotion, the replay cache fold | after S5 (table above) |

Adjudicated 2026-09-20 (S0, read-only against code): of the survey's twelve POSSIBLY-STALE items
CLOSED R4 A5 B7 E6 E11 O9 O11 (A5 had misnamed the ref — `::b10` is Hall_1985, Burnicki's two
cases are already pinned; O6 had misnamed the test); OPEN B5 and E13 landed in S3, E10 → S4, O6 → S7,
O8 → S7, rows above.

---

## The survey's verdicts (2026-09-21) — with what each rests on

**Superseded for acquisition and extraction on 2026-09-22** by
`Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md` — two crawler rounds, a merged ladder graded per rung
(VERIFIED / MEASURED / ASSERTED), a per-publisher landing-page rule table, external base rates, the
extraction and OCR ladder with its agreement designs, and a coverage projection built on the
orchestrator's read-only measurements of litkb's own miss rows. The rows below stand for the
resolve+admit and binding questions the 2026-09-21 survey answered; where the two disagree the later
file wins, and it names the disagreement (its §7). Where a row below says "→ S4.5 item N" or "→ after
S5" for an ACQUISITION mechanism, the later file's stage table is the schedule; the row is kept for
its provenance columns only.

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
| B identity | Crossref `relation` as a typed edge, with a third state for an empty field | the Crossref API (no repository) | n/a | LIVE (the field exists; a real bioRxiv preprint returned it EMPTY) | `parse_crossref` in `pipeline/litkb/admit/registry.py` never reads it; no raw response is stored, so a backfill is one call per DOI; the yield over this corpus is UNMEASURED | ADOPT, probe first → S4.5 item 1 |
| B | the arXiv record's DOI field | Manubot, manubot/cite/arxiv.py (the field); export.arxiv.org (the behaviour) | pinned · VERIFIED | VERIFIED for the field; ASSERTED for live behaviour (the crawler's call returned an empty body) | `arxiv_record` parses title, author, published only | ADOPT → S4.5 item 1 |
| B | identifier-first duplicate ordering; type-scoped ISBN; ISBN-13 canonicalisation | JabRef, DuplicateCheck.java; Zotero, duplicates.js; Manubot, isbn.py | JabRef pinned in A and D, UNPINNED in B · MIT from the GitHub API, LICENSE not read; Zotero PINNED in B with AGPL-3.0-or-later read from the file header (A, C, D, E read Zotero unpinned and asserted its licence) | VERIFIED (call sites; the ISBN helper bodies not read — a submodule) | `_title_duplicates` (migration 0013) calls a different DOI a duplicate at 0.70/±1 y; no `isbn` ref scheme (`REF_REFUSALS` in `pipeline/litkb/hunt.py`) | ADAPT → S4.5 item 1 (design only from Zotero — AGPL) |
| B | a corporate-author field mode | Zotero, duplicates.js | pinned in B · AGPL read from header | VERIFIED | `make_key` in `pipeline/litkb/admit/front.py` crashes on a LONG creator string, not a corporate one — the discriminator is length | ADAPT as a length rule → S4.5 item 1 |
| B | OpenAlex `locations[].version` | the OpenAlex API; pyalex not cloned | n/a · pyalex MIT ASSERTED | LIVE for the model | — | not adopted: the relation edge suffices |
| B | recordlinkage / dedupe | — | — | — | — | IGNORE: needs labelled pairs; an unexplainable verdict fails §3.4c |
| C acquisition | per-host back-off, Retry-After cap, 403 never retried, park-and-continue | Zotero, attachments.js | UNPINNED (branch head) · AGPL ASSERTED (C: "LICENSE not fetched") | VERIFIED | `DEAD_STATUSES` in `pipeline/litkb/acquire/run.py` keyed on the status word; `blocked` in no set; `at` unused by the skip decision | ADAPT the mechanism, never the code → S4.5 item 1 |
| C | mirror scoring from persisted failure rates | SciDownl, core/chooser.py | pinned · LICENSE presence ASSERTED | VERIFIED | a fixed mirror order (`SCIHUB_MIRRORS` in `pipeline/litkb/config.py`) | superseded: S4.6 Stage G moves the lists to a registry; scoring stays after S5 |
| C | `citation_pdf_url` with landing-page cookies + Referer | paperscraper, pdf/pdf.py | pinned · MIT ASSERTED | VERIFIED | `pdf_link` in `pipeline/litkb/acquire/scihub.py` already parses it — reuse on OA pages | superseded: S4.5 Stage C builds it |
| C | retry only 500/504; negative examples (PyPaperBot, unpywall) | paper-qa; PyPaperBot; unpywall | pinned | VERIFIED | — | none refuses a known-bad hash — nothing to adopt |
| D binding | embedded-identifier ladder (metadata → text → filename), each candidate validated at the registry | pdf2doi, finders.py, patterns.py | pinned · MIT from setup.py, LICENSE not read | VERIFIED | the registry id is never passed into `bind()` | ADAPT the ladder, not the Google fallback → after S5 |
| D | font-size title extraction | JabRef, PdfContentImporter.java | pinned · MIT ASSERTED | VERIFIED | — ; whether a stamp's font is smaller than a title's on a REAL page is UNMEASURED | ADAPT, measure first → after S5 |
| D | entropy + stub content gate | paper-qa, utils.py and docs.py | pinned · Apache-2.0 ASSERTED | VERIFIED | `pdf_shape` in `pipeline/litkb/acquire/store.py` tests a header and a trailer only; no text gate exists; the metadata fallback binds an empty page | ADOPT → after S5 |
| D | throw on a zero-text page | Zotero, recognizeDocument.js | UNPINNED · AGPL | VERIFIED | `bind_any_with_ocr` is AHEAD (OCR where there is nothing to read) | IGNORE as code; the ordering lesson only |
| D | pdftitle | — | GPL-3 | — | — | IGNORE as a dependency |
| E outcomes | the content hash on the attempt row; rejected-hash lookup; `blocked` sub-types; a commented static host blocklist; re-ingest cadences as SQL over the ledger | IA sandcrawler, ingest_file.py and its SQL | pinned · NO LICENSE FILE at the root (E: asserted internal) | VERIFIED (the Kafka layer ASSERTED) | `record_attempt` has no sha column; `_quarantine/` has no database state; `REASONS["blocked"]` is 403 · challenge · quota-stop | ADAPT → S4 (the state) + S4.5 item 2 (the ledger); the blocklist and cadences → after S5 |

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

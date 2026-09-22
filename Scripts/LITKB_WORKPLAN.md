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
  every URL between rounds, a synthesizer each round — and the orchestrator measured the ladger's own
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
  `litkb-shadow-hosts`, `litkb-tdm-keys`, `litkb-crc-book`, `litkb-s47-colab-queue` open. The
  2026-09-21 revision's record stays `Reports/LITKB_PLAN_REVISION_2026-09-21.md`. Round 3 of the survey
  (the shadow-library linkage map and the identifier crosswalk; record `Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md`, its §M the measurements)
  landed the same day and rewrote S4.5 item 1's identifier model, Stage A's zero-request derivations and
  offline membership table, Stage B's fan-out order and closure rule, and S4.6's Stages F and G; a
  fourth round over the loop's other stages was crawling when this was written (its record will be
  named here when it lands). Codex's GitHub pass has died on quota in three consecutive rounds and is
  owed.
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
  0. (2) **S4.5**, launched by S4 the way S4 was launched (a new window, bash + prompt file; S4 writes
  _derived/s4-5/s4-5-prompt.txt from the "### S4.5" block). (3) **S4.6**, (4) **S4.7**, each launched
  by the one before it; (5) **S5** once its entry condition is met. Then S6, S7.
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
- **Kam-side, open** (ids; the questions live in `decisions.yaml`): `litkb-coverage-definition`,
  `litkb-institutional-access`, `litkb-shadow-hosts`, `litkb-tdm-keys`, `litkb-crc-book`,
  `litkb-e23-residue-copies`, `litkb-blocked-works-grade`, `litkb-scihub-parked`,
  `litkb-tracker-corrections`, `litkb-from-file-version-state`; the OCR strategy (S4's Kam line);
  S5's topic.
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
  (`pipeline/litkb/acquire/store.py`) writes status and sha into the FILENAME, which no code reads
  back, and a `.reason.json` sidecar, which is the only machine-readable copy;
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
```

Kam: the OCR strategy (recommendation: page-range chunks on the T2000).

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
one per RUNG CLASS, sequentially, inside the protocol's three-agent cap — the classes are the
substrate, the vocabulary, Stage A, Stage B, Stage C and Stage E. Spelled S4.5 because the plan gate
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
   guards fired. Rows: E13 and the ruled run's `registry-transient` rows for the back-off; E21's pair
   for identity, with E06 as an ADMISSION negative (a page with no confirmed identifier, title-near an
   existing work, must still refuse `duplicate-review` — it exercises the duplicate check, not an
   acquisition rung); 187's record for the key rule and its filed PDF for the landing; 194's proposal
   for the verb. The back-off's known-bad, the relation probe's, the key rule's and the verb's are in
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
   `identity_required` · `challenge_or_bot_check` · `not_found` · `html_or_reader`. Also
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
   ruling, and the shadow corpus's freeze date is the reason a post-2021 DOI is out-of-corpus by
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
6. **Stage E, recovery**: the Wayback availability API and CDX with the `id_` raw-bytes modifier (E1 —
   §M's census.gov author copy is its positive row; §M's IIASA copy, never archived, is its real
   NEGATIVE); Internet Archive item search and download (E3) and the Common Crawl index (E5) have no
   litkb row today and are built as free fan-out members whose yield the run measures. fatcat's API is
   dead server-side (the survey settled it) and is not a rung.
7. **The measurement that comes FIRST**: read every `bad-file` row's `detail`, its stored bytes' first
   kilobyte where the bytes were kept (the store kept them for only a few of these rows; the rest have
   `detail` alone) and its length; type each into item 2's vocabulary; the count of causes that are free
   to fix is this session's first tracked number, written by the probe instrument into phase4/qc/.

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
- (a) the migrations; the ledger columns and values; the Stage A/B/C/E rungs with their rule fixtures;
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
  (`bad-file` attempts with NULL `sub_status`) · `blocked_untyped=0` · `preprints_sent_to_shadow=0`
  (attempts on a shadow route for a work whose Crossref type is `posted-content`) ·
  `landing_pages_booked_bad_file=0` (`html_response` attempts whose page carried `citation_pdf_url`
  and no Stage C attempt followed) · `stubs_bound=0` · `volumes_bound_as_article=0` (a bound file with
  `pages >= 60` against a Crossref page range under 60) · `free_ceiling_measured_unconverted=0` (the
  `FREE-PDF` and Wayback rows still without a file) · `budget_exceeded_silently=0` (a work whose ladder
  ran past the budget with no `budget` attempt row) · `stage_b_rungs_unmeasured=0` (Stage B rungs
  with no yield line in the report) · `crosswalk_rows_without_identifier=0` (works the probe CSV gives
  an arXiv id, ISBN or relation edge that hold no such row after the run) ·
  `identifiers_without_provenance=0` · `conflicts_uncounted=0` (two works claiming one distinct-valued
  identifier with no conflict edge and counter) · `nondistinct_schemes_in_unique_index=0` · `unvalidated_items=0` (rung classes — the six above — whose
  referee report the manifest does not name or whose report has no `fired: <counter>=<value> on
  <input>` line). REPORTED, unbounded: `transient_rows_unretried`, `relation_edges_missing`,
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
  dropped from the manifest → `unvalidated_items=1`.

#### Test-set commands (run from Scripts/, read-only)

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

Kam: `litkb-blocked-works-grade`; `litkb-from-file-version-state`.

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
   versioned registry fetched at start (guard 7). NEW rungs are NOT built until `litkb-shadow-hosts` is
   decided, and the plan records them as read in code only: LibGen's DOI-to-md5 lookup with its
   User-Agent trap (G0a) and delivery (G1d), the `sci.bban.top` DOI path (G1a), Nexus/STC (G0b —
   VERIFIED but disputed, its gateway reported down in 2026; G1c), a real browser session against
   Anna's (G3a). Tor as a transport (G5) is graded verified as a mechanism and dead as an
   implementation, and is not scheduled. The Sci-Hub corpus froze around 2021, so a post-2021
   paywalled work in this tier ends `held/not-acquired` with `retriable=false`; the deferred-human-
   fulfilment rung (G4) is the `--from-file` half of `litkb-blocked-works-grade`, not code.
4. **Stage H, credentialed and anti-block, each behind its ruling**: a persistent logged-in browser
   profile driven by Playwright (H10, and H11 — the one rung that survives the Elsevier JS redirect;
   together the only converters of the `manual-step` rows; conditional on `litkb-institutional-access`;
   no credential is ever stored or scripted by litkb); Springer's API (H1 — resolves, but hands URLs on
   the walled host) and Elsevier's (H2 — free keys buy open-access content only; an unentitled key
   answers HTTP 200 with a first-page stub announced only in `X-ELS-Status`, which S4.5's acceptance
   test refuses), both under `litkb-tdm-keys`; `curl_cffi` impersonation (H5) is NOT built — the
   survey measured it AGAINST twice in production, on MDPI and on Springer — and is recorded as
   measured-against; FlareSolverr (H6) already exists in `pipeline/litkb/netutil.py` as the challenge
   retry, cannot return a PDF (its solution is HTML), and stays a landing-page solve only. No commercial
   anti-bot proxy.
5. **The coverage account** the finish line reads: an instrument under `qc/instruments/` that joins the
   tracker to main by identifier, applies the record-class filter, and prints per grade (`pdf` ·
   `jats` · `html-doc` · `cached_text` · `snippet` · metadata-only · none) the share of eligible
   tracker rows in each, plus the paywalled residue by publisher and year, into a CSV under phase4/qc/ — with the residue
   split three ways by the offline membership table: out-of-corpus (no shadow library ever held it),
   blocked (held, but every probe was refused), and not-in-archive as the archive's own five-way answer;
   without that split the residue column silently absorbs works no shadow rung could have reached.
   Which grades count toward the target is `litkb-coverage-definition`; until it is decided the
   instrument REPORTS and the session's (b) carries no coverage bound.

Test set, POSITIVE: the archive-miss rows by Crossref type (the probe instrument's baselines output
under phase4/qc/ lists them: the preprints must never reach this tier — S4.5's router owns them; the
chapters and the book go through Stage F only if a copy can exist; the rows no registry holds end
`refused/unresolved` with the reason, never `not-in-archive`); the Sci-Hub `blocked` rows re-typed
(challenge · miss · storage path found on another mirror · out-of-corpus by the membership table); the
archive-miss rows re-read against the archive's five conditions; the grey rows whose files are ALREADY on
disk but not in main — 235's Seattle canopy report under `_litkb_staging/filed/` and 194's King
County page snapshot under `_litkb_staging/web/` — and the USFS and USGS class by title; the
`manual-step` rows ONLY if `litkb-institutional-access` is decided yes. NEGATIVE, REAL: a Stage D
title hit whose page-1 title scores below 0.85 (the ruled run's row 235 cover measures 0.80 and is the
row); a DDoS-Guard interstitial from the ledger's own `blocked` attempts; a request to a host outside
the policy allowlist. NEGATIVE, CONSTRUCTED, in those words: a chapter DOI carrying an ISBN already
attached to its book; a post-2021 DOI offered to the shadow tier.

Done-state
- (a) the Stage D/F/G/H rungs that are ruled in, each with fixtures; the coverage instrument and its
  CSV under phase4/qc/ (CLAUDE.md §3.4b); a report under Reports/ (LITKB_LADDER2_<date>); one referee
  report per rung class; tests + ledger rows; SCHEMAS rows; the manifest frozen by `ladder --freeze`.
- (b) `py -3.12 qc/instruments/litkb_acceptance.py ladder --manifest <manifest>` → GATED:
  `grey_hits_below_title_gate=0` · `chapters_routed_to_scidb=0` · `challenge_booked_as_miss=0` (a
  `not-in-archive` attempt whose terminal page title is DDoS-Guard) · `shadow_requests_outside_policy=0`
  · `new_hosts_without_ruling=0` · `credentials_stored=0` (any credential string in litkb's config or
  database) · `tdm_stubs_bound=0` · `coverage_rows_unclassified=0` (tracker rows the instrument could
  neither join nor mark) · `archive_misses_untyped=0` (archive-miss rows still carrying the bare word
  after the five-way re-read) · `shadow_misses_from_concurrent_probes=0` · `unvalidated_items=0` (the five rung classes). REPORTED: `eligible_rows`,
  `coverage_pdf`, `coverage_source`, `paywalled_residue`, `manual_step_rows` — bounded only once
  `litkb-coverage-definition` is decided; until then the session reports them and says UNDETERMINED
  against `litkb-coverage-target`.
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

Kam: `litkb-institutional-access`; `litkb-shadow-hosts`; `litkb-tdm-keys`; `litkb-crc-book`;
`litkb-coverage-definition`; `litkb-blocked-works-grade`; `litkb-scihub-parked`;
`litkb-e23-residue-copies`.

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
layer; every vision-language rung is a Colab queue, and that queue is `litkb-s47-colab-queue` (open) —
without it the session runs the CPU and T2000 parts and reports the vision-language rungs UNDETERMINED.

Work
1. **The CMap repair layer, above every ligature fix** (survey §5.2; one repository's Rust, ported onto
   pikepdf, whose qpdf bindings reach a font's `/ToUnicode` stream — pypdfium2 cannot): the
   five-source ToUnicode fallback ladder (the stream's CMap → a sequential remap → the encoding's glyph
   names → the embedded TrueType cmap → the CID collection), the `ControlDestination` repair that is the
   named CAUSE of ligature garble, glyph-name decomposition at source with "every component must read,
   or the name does not", the overlong-`/BBox` repair that turns a silently empty page back into a page
   (so OCR never transcribes a blank), and the abandon rule — more than half the codes unmapped → return
   nothing and fall through. `litkb-ligature-repair` becomes the downstream normaliser of what survives.
   Rows: the ligature-damaged files that ruling's referee report names; plus a CONSTRUCTED corrupted
   CMap, in those words.
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
4. **Scans, measured before adopted**: on the corpus's no-text-layer scans (the command below lists
   them; S4's first scan rows) a hand-corrected gold page each; then Tesseract 5 variants, docTR and
   RapidOCR on the T2000, with old-scan layout segmentation shared across engines (eynollah in WSL) so
   line-level alignment is possible at all; LV-ROVER's arbitration SHAPE with the lexicon built from
   litkb's own registry metadata used as a SHIELD (an anchor word in the lexicon is never overridden;
   never shorten; never touch short tokens or numbers; edit distance ≤ 2); a trained character
   corrector only WITH its sliding-window vote (the survey's one clean number: positive with the vote,
   negative in every configuration without it); character error rate with a confidence interval per
   page against the gold; vision-language OCR on Colab under `litkb-s47-colab-queue` (ranked on the
   old-scan axes, never on the overall score) accepted at HIGH tier only when it agrees with the
   classical consensus above a threshold — a fluent hallucination scores well on every coherency and
   dictionary gate, and only agreement catches it; the known-bad for that guard is a CONSTRUCTED
   fluent invention (a page whose VLM transcript is a plausible paragraph the scan does not contain),
   in those words. Preprocessing is a VARIANT rung, never mandatory. If the arbitration's gain is
   inside the interval, the report says UNDETERMINED and the tier stays LOW.
5. **Math verified without a second decoder** — under `litkb-second-formula-decoder` (DECIDED
   2026-09-19: the second decoder is dropped; pix2tex is out on nondeterminism; the re-open condition
   is a review whose conclusion depends on a mathematical claim, and the entry bar is a seeded,
   deterministic protocol). This session does NOT re-open it. What it builds is the verification
   ladder on the ONE decoder's output (`litkb.equations.latex_status` today only flags), stopping at
   the first rung that decides: KaTeX parse → pdflatex compile with a kill timer → degeneracy check →
   an image check of the rendering against the ACTUAL crop — the rung that needs no second reading and
   catches a wrong one — so `latex_status` gains `verified` and `held` beside `unverified`, per
   formula. Free triage first by math font names and math-unicode ratio, so the report can say how
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

Kam: `litkb-s47-colab-queue`; `litkb-coverage-definition` (its searchable-versus-quote-grade half);
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
| **Binding: identifier-in-file ladder and a font-size title test** (the post-extraction content gate moved into S4.5's acceptance test and S4.7's bind-time gates; what stays here is identity-by-embedded-identifier and the font-size title heuristic). Measured: check 3 rests on title + surname only — the registry's DOI or arXiv id is never passed into `bind()`; `pdf_shape` tests a `%PDF-` header and a `%%EOF` trailer and nothing else; there is no entropy, printable-ratio or minimum-text test anywhere; and the metadata fallback binds a page with ZERO extractable characters at ratio 1.0 on `/Title` + `/Author` alone (latent: every live bind that took the `pdf-title` path has a text layer). Row 235 is a WINDOWING limit (a title split over more lines than the scoring window covers), not a threshold. | stamp-robust binding; `bad-file` detection on every route; the blank-page bind | survey D: pdf2doi's ladder (VERIFIED, licence from setup.py), JabRef's TitleExtractorByFontSize (VERIFIED at a pinned commit; licence ASSERTED), paper-qa's `maybe_is_text` (VERIFIED). Whether the arXiv stamp's font is smaller than the title's on a REAL page is UNMEASURED — measure it on the E25 PDFs first | PREREQUISITE: the corpus title-ratio sweep becomes an instrument under qc/instruments/ writing a CSV under phase4/qc/ (CLAUDE.md §3.4b) — the E25 sweep's per-file output exists at no path and its population has already drifted. Then: `qc/testdata/litkb_binding_stamps/` fixtures via `qc/test_litkb_binding_stamps.py`; the E25 PDFs; 235's filed PDF; a challenge page's bytes (the Sci-Hub attempt detail in `Reports/LITKB_EDGE_RUN_2026-09-21.csv` names the mirrors); a stub PDF with matching `/Title` + `/Author` and an empty page | the content gate given challenge bytes behind a `%PDF-` header → refused, never bound; the stub with matching metadata → `binding-pending`, never `bound`; the ladder given a PDF whose embedded DOI is another work's → refused (auditor-e25's cross-title probe is the shape); a page whose largest font is a running head or journal name (235's cover is the real case) → the font-size candidate refused by check 3's ratio, never bound on font size alone |
| **Both identifiers on one admission**: check 1 requires EVERY passed identifier to confirm, so `admit --arxiv X --doi 10.48550/arXiv.X` refuses although the DOI form confirms, and admitting by the DOI alone stores no arXiv id, so a later arXiv hunt is a duplicate | `Reports/LITKB_RULED_HUNTS_2026-09-21.md` §8 (measured once) | litkb's own code | the ruled run's arXiv rows; negative — 187's confirmed DOI paired with a CONSTRUCTED wrong arXiv id, stated as constructed | an admission storing an identifier no registry confirmed → refused; the constructed pair → refused |
| **HTML snapshot → searchable blocks, live**. A live HTML-only hunt of an unknown work is DONE (row 194); its snapshot holds no blocks because extraction was off | `docs/SCHEMAS.md` "A web source that is a page" proved in replay only | litkb's own code | positive today: 194's existing snapshot run through extraction → searchable blocks (no live fetch needed); negative: the register's URL-HTML-only rows replayed (E06's class); a live unknown page only if S5's scout drops one off | a page with no claimed title, author and year → `refused/incomplete-record`; 194's snapshot with its text emptied → `zero-content`, never searchable |
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
| no extraction queue, no fail-closed page cap, zero-content/multi-file works, cross-page `page_no`, metrics in JSONL, superseded run sets, the `book` residue class, a quarantine with no database state; the no-text-layer scans | S4 |
| the substrate: `blocked` in no route's `DEAD_STATUSES`; registry transients re-run by hand; the arXiv-client question; Crossref `relation` dropped and its yield unmeasured; a different DOI called a duplicate at 0.70; no ISBN scheme; a long creator string crashes the key rule; no served-bytes hash on the attempt row; a re-served bad file re-quarantined, never skipped; a refused-duplicate landing left unowned on disk; no second-session refuse verb; the approve guard never made to fire. The ladder: an untyped `bad-file`/`blocked` ledger where mature codebases carry typed sub-states; no landing-page-to-PDF rung (Unpaywall's own answers are landing pages litkb books as `bad-file`); no record-class filter, no work-class router (preprints sent to the archive route); Crossref `link[]` never read; no Semantic Scholar or OpenAlex PDF lookup; no Wayback rung; the `bad-file` rows never read | S4.5 |
| no grey-literature rung at all (USFS, USGS, NTRS, OSTI, DSpace with MD5, ArcGIS Online, city portals); the book namespace unreachable by construction (scidb by DOI); DDoS-Guard blocks booked as `not-in-archive`; Sci-Hub mirror lists compiled into `run.py`; no credentialed rung and no ruling on institutional access; no coverage instrument against the tracker | S4.6 |
| ligature repair at the symptom, not the CMap; the vector-complexity pre-filter absent (GIS figures hang the extractor); `extracted: true` with no quality tier, so a LOW-tier scan can supply a quote; no measured OCR arbitration on the corpus's own scans; formula LaTeX `unverified` with no verification ladder; the L4 formula re-crop of Reynolds_2000 and Montgomery_1991 never ran; no `word_count` on files | S4.7 |
| run-2 review fails the tightened grader; no run protocol; the promoted tracker-era metadata; no per-hunt time budget; no rule retiring a superseded drop-off; the two builds the rulings assign to S5 (ISBN → md5; registry-over-claim on a human's say-so) | S5 |
| no synthesis grammar or K3 | S6 |
| no doctor; ledger not a `check.py` rung; harness `run_one` calls any failure FIRED (no per-row baseline diff); `report_path` unbounded; nightly dump task points at an old worktree | S7 (dump task: Kam, now) |
| the survey's remaining designs and litkb's own: two-tier resolution, doi.org negotiation, the identifier-in-file binding ladder (with the sweep instrument as its prerequisite), both identifiers on one admission, snapshot → blocks live, re-ingest cadences | after S5 (table above) |

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

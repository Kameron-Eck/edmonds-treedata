# litkb — the lit-review loop stage by stage, engineering survey round 4 (2026-09-22)

**What this is.** Kam's ask of 2026-09-22 ("engineering crawls for the lit review pipeline … launch all 8, and
launch the lower list items"): twelve code surveys, one per loop stage the earlier rounds had not covered —
discovery, quote verification, review writing and its graders, search inside the base, citation anchoring, the
synthesis gate, hermetic replay of the test harness, numeric and table evidence, the second-session promotion
path, the doctor and soak checks, the agent boundary at the MCP server, and the headless run protocol. It joins
`Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md` (acquisition and extraction, rounds 1 and 2) and
`Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md` (round 3). Every mechanism below is a DESIGN read in
someone else's code (CLAUDE.md §3.4c); the crawlers ALSO measured litkb's own live base as `litkb_reader`, and
those measurements are the part the orchestrator carries into the plan first, because several show a gate the
plan trusts is already defeated.

**How it was made.** Workflow `wf_14029e46-453` (53 min): twelve Opus crawlers (L1–L12), each reading litkb's own
code for its stage first and citing it file:line, then external source at pinned commits, each holding the
round-3 blacklist; one Codex attempt that DIED on quota for the fourth consecutive round (its file is a failure
record; the cross-family read of these stages is OWED, not skipped). The synthesizer merged the twelve into the
body below; `blacklist-round4.txt` (3,423 lines) is the union of every URL visited. Worker reports:
`D:\tools\claude-config\jobs\litkb-acquisition-survey\L*.md`.

**Measured on litkb's own base by the crawlers, the findings the orchestrator ranks highest** (body §1 has each
with its query and its file:line):

| stage | measured | consequence for the plan |
|---|---|---|
| search | one `litkb_search` call costs about 16 s, of which the trigram leg costs about 14 s and returns ZERO rows — an expression index recomputing the normaliser on tens of thousands of recheck rows, and a similarity floor the corpus cannot reach | the advertised three-leg fusion has in practice been two legs; the vector question is secondary to this defect |
| quote verification | the ligature migration repaired the SEARCH index only; every ligature-damaged paragraph block that search can reach is refused by the quote locator; edit distance cannot separate a legitimate one-character edit from the known-bad one-character mutation | the quote gate needs an aligned-with-diff rung, not a distance threshold |
| numeric evidence | the base holds hundreds of thousands of table cells with bounding boxes, most of them numbers, while every table block stores empty text, so no evidence row on a table can exist and the verify trigger refuses it; a large share of tables repeat a decimal across cells | a quoted number needs a cell address, not a text match |
| discovery | backward snowballing already runs at extraction and writes its candidates with no workstream, so hundreds of resolved candidates are reachable from nowhere; two recall-estimation kills already fire on the tracker's own rows | the scout's usefulness has a counter after all — recall against the tracker — and one seeded miss must refuse |
| citation anchoring | anchors exist (not zero); every reachable anchor was already made; the bottleneck is that the reference stage has run on a small fraction of files; the frozen gold cannot be joined to the live base | the after-S5 row's premise was wrong; the work is coverage, then a gold that joins |
| synthesis gate | the brief admits promoted uses, so the plan's laundering kill criterion holds only while zero uses are promoted; the first promotion Kam merges opens the surface with no code change | K3 must read the workstream's own ledger and assert the finding code, not an exit status |
| review graders | K2 returned SUPPORTED on every citation of the run-2 review and found its defects outside the per-citation loop; a deterministic numeric-containment check is free and fires on a magnitude mutation whose quote is byte-identical; the causal-cue guard is UNDETERMINED on real citations | K1 gains a deterministic rung; K2's rubric must name what the loop cannot see |
| promotion | no refuse verb; the schema's rejected and withdrawn states are written by nothing; the promote stage has no live evidence (prepared, never committed); every file version was bound directly | the second-session path is untested end to end |
| run protocol | there is no run entity; the seeding guard reads one file while the live launch prompt is untracked and carried a work key at the time of reading; a paper named by title passes the guard | the protocol needs a run id, a guard over the launch kit, and a title check |
| hermetic replay | the replay is graded against stubs the instrument wrote itself; several register rows carry superseded predictions; one row passes on state and reason while its recorded route ladder disagrees in every field | the replay must be graded against recorded truth, not fabricated returns |
| doctor and soak | three corruptions of a real dump, each re-stamped fresh, ALL passed the list-only restore check and ALL failed a full restore; a crashed night writes no soak row, so incomplete nights are uncountable; the worker-database count in the plan is wrong | S7's corrupt-dump known-bad is defeated as written; the restore proof must restore |
| agent boundary | the MCP library already ships a tool-call interceptor and server middleware that the server never installs; every tool is served to every client | the web-blind boundary can move from prompt to server today |

**The bottom line the orchestrator carries into the plan.** These are not designs to schedule; most are defects
in gates the plan already trusts, found by reading and querying the live base. They go into the session blocks
that own the gates (S4.5, S4.7, S5, S6, S7) as measured pains with their kill criteria rewritten to fire on the
inputs the crawlers used, and the survey's external mechanisms follow behind them under the same referee rule as
every other round. Codex's read of these stages is owed.

---

# The lit-review loop, stage by stage — engineering survey round 4 (2026-09-22)

Synthesiser: this session, reading the twelve round-4 crawler reports under
`D:\tools\claude-config\jobs\litkb-acquisition-survey\` plus the round-4 Codex record.
Every number below carries the crawler that measured it (L1…L12) — this synthesis measured
nothing itself and ran nothing in the project. Where a crawler says a number is its own
prototype's output, that attribution travels with it, because CLAUDE.md §3.4c forbids
accepting a design on numbers it produced about itself.

Companion artefact: `blacklist-round4.txt` (3,423 URLs = round-3's 2,961 plus 462 new).

---

## 0. Scope

### 0.1 What round 4 crawled

Twelve stages of litkb's loop, one crawler each, ENGINEERING ONLY: how other codebases build
the stage, read in their source at pinned commits, and what litkb would have to change, scored
on a local test set the crawler names.

| report | stage in the loop | URLs | status |
|---|---|---|---|
| `L1-discovery.md` | discover → drop-off | 64 | complete |
| `L5-citation-anchoring.md` | references → resolve+admit (the citation arm) | 18 | complete |
| `L4-search.md` | search inside the base | 45 | complete |
| `L2-quote-verification.md` | record (the QUOTE gate) | 46 | complete |
| `L8-numeric-evidence.md` | record (numbers and table cells) | 26 | complete |
| `L3-review-writing-graders.md` | brief → review, K1 and K2 | 40 | complete |
| `L6-synthesis-k3.md` | synthesis, K3 | 68 | complete |
| `L9-second-session-provenance.md` | promote, second session, versions | 27 | complete |
| `L12-run-protocol.md` | the headless run protocol (ops) | 34 | complete |
| `L7-hermetic-replay.md` | hermetic replay of the hunt (ops) | 43 | complete |
| `L10-doctor-soak.md` | `doctor` + the seven-night soak (ops) | 38 | complete |
| `L11-agent-boundary.md` | MCP server, agents, the web-blind boundary (ops) | 37 | complete |

Total 486 URL lines, 471 distinct after de-duplication.

### 0.2 The two stages NOT re-crawled

**Acquisition** and **extraction** were surveyed in rounds 1–3 and are pointed at, not redone:

- `D:\edmonds-pipeline\treedata\Reports\LITKB_PDF_SOURCES_SURVEY_2026-09-22.md` — the PDF-sources
  and OCR survey (two crawler rounds, 19 agents) behind S4.5 / S4.6 / S4.7.
- `Scripts/Reports/LITKB_PLAN_REVISION_2026-09-21.md` — the earlier plan revision.
- `SYNTHESIS-r1.md`, `SYNTHESIS-r2.md`, `SYNTHESIS-r3.md` in this directory — rounds 1–3.

Two round-4 items touch acquisition without re-surveying it, and both are *test harness* work,
not ladder work: L7's recorded-cassette replay (which runs the REAL ladder rather than a stub)
and L12's budget/liveness rules (which bound the ladder's wall clock). Neither proposes a new
acquisition route.

### 0.3 Codex status

**C4-codex-loop-tooling: NOT RUN.** Quota exhausted. The probe
(`codex exec -s read-only --skip-git-repo-check -C /tmp -`, codex-cli 0.155.1, WSL Ubuntu,
model gpt-6-astra, session `01a0c986-4fe2-7ae0-b01b-87dff17b92f8`) returned verbatim:
`ERROR: You've hit your usage limit. … try again at 9:13 AM.` No URLs, no findings.

This is the **second** consecutive Codex failure with the same reset time: round 3's
`C3-codex-shadow-linkage.md` (session `01a0c964-2ebe-7a22-bfcc-8c169817d660`) carries the
identical error. Per `LITKB_WORKPLAN.md`'s Codex-stage rule, a Codex read that cannot run is
**OWED, not skipped**. Two consequences for this round:

1. The seven loop-tooling topics C4 held have **no cross-family read at all**. Every mechanism
   in §1 below was read by a Claude-family crawler; the different-model-family check that K2
   exists to provide has not been applied to this survey's own conclusions.
2. Re-dispatch C4 after 09:13 local, or reassign its topics to a Claude-family agent and say so
   in those words in the report that consumes them.

### 0.4 Missing or failed reports

- `C4-codex-loop-tooling.md` — present as a FAILURE RECORD, no survey content (§0.3).
- No L-report is missing. All twelve exist and carry §1 (litkb today), a findings table, per-item
  detail, a local test set, diff-shaped recommendations, a "what I could not verify" section and
  a URL list.

### 0.5 Which stages have a local test set TODAY

Counting a stage as having a local test set only when **both positives and negatives are real rows
that join to the live base today**: **11 of 12**. Every stage names real rows, but §1.2's
designated scoring gold — `Reports/litkb_splink_gold_2026-09-15.json` — joins the live database
for only 138/365 positives, 2/77 must-not-link, 0/20 near-positive mutations and 0/5 lost-genuine,
so no anchoring kill criterion can be shown to fire until L5-R0's crosswalk exists. Four further
stages have a real test set with a stated hole, each named in place: §1.3's qrels need freezing by
a referee (the re-anchoring matcher is L4's own), §1.7's positives are real but its `good.md`
fixture must be built and its expected-line negative has no proving-run carrier, §1.8's
promote-commit half has **zero** live evidence (0 promotions committed), and §1.10's cassettes do
not exist until they are recorded.

### 0.6 How to read the status words

`VERIFIED` = the crawler read the mechanism in source at the pinned sha. `ASSERTED` = README,
documentation, a search-result summary, or a licence taken from metadata rather than an opened
`LICENSE`. `MIXED` = mechanism verified, some load-bearing part (a threshold, an effect size, a
licence) asserted. `UNVALIDATED` = a design that has not run on litkb's real rows — CLAUDE.md
§3.4c's word, and it is used below wherever it applies.

---

## 1. Per stage

### 1.1 Discovery → drop-off (L1)

#### litkb today

Discovery is **one subagent and one write**. `.claude/agents/lit-scout.md:5` names the agent's
tools (5 litkb tools, 23 paper-search routes, WebSearch, WebFetch) — so it cannot reach
`litkb_hunt`, `litkb_admit` or any `download_*` / `read_*` route. The procedure is
`.claude/skills/literature/SKILL.md:22` onward: 3–6 queries written before any are run, a
four-rung source ladder (litkb first, then `search_papers` fanned over arxiv/crossref/openalex/
semantic, then single indexes, then WebSearch), and a drop-off with eight required fields
written through `pipeline/litkb/hunt_request.py:44` `record()`, a thin wrapper over the
SECURITY DEFINER function `litkb.record_hunt_request`. The stop rule is prose at
`SKILL.md:101-116` — 15 drop-offs, or two consecutive queries that add nothing new, then print
`SCOUT-STOP`.

The grader is `qc/instruments/litkb_acceptance.py` `check_scout` (:718): `dropoffs >=
MIN_DROPOFFS` (:777, =10), `missing_required_fields` against `REQUIRED_FIELDS` (:493),
`ref_scheme_outside_set` against `ALLOWED_SCHEMES` (:499), `missing_hunt_results`,
`unknown_states`, `human_input_events`. **Every one is a hygiene counter.**

The measured pain is the plan's own sentence, `LITKB_WORKPLAN.md:253`: *"Usefulness is NOT a
counter — it has no measure."* Nothing counts whether the rows are the right papers, and
nothing counts what was missed.

L1's numbers, read 2026-09-22 from tracked files or as `litkb_reader`: 487 works; 372,305
blocks; 103 hunt_requests (open 58, unconfirmed 36, confirmed 5, contradicted 4); the only real
scout run produced **9 drop-offs against a bound of 10** and stopped honestly at
`reason=no-new-results` with no yield number behind it; **385/403 = 95.5%** of the human
tracker's DOI rows are already in the KB; references have been extracted from **17 of 487 works
(3.5%)**, yielding **347 distinct cited DOIs of which 332 are absent from the KB**.

**The defect L1 found:** litkb already does backward snowballing and throws the result away.
`extract/references.py:813` `candidate_row()` writes `candidates` rows with `source='citation'`
under P5's ingest role, which attaches **no workstream**; `mcp/server.py:852` reads
`FROM litkb.candidates WHERE workstream_id = %s`. Live DB: **630** such rows, ALL
`workstream_id IS NULL`, ALL `state='new'`, 350 carrying a DOI — reachable from zero
workstreams. And `litkb_candidates` (a read tool, `server.py:1455`, `_conn("reader")`) is not in
the scout's tool list at all.

#### Strongest external mechanisms

| mechanism | repo @ sha · symbol | licence (as stated) | status |
|---|---|---|---|
| Chapman two-source + Chao1 recall ESTIMATION with explicit refusals (`estimable=False` + `reason`), `MIN_OVERLAP=3`, nested-arms check, no-doubletons refusal | `s-matysik/SnowBallSLR` @ `9491832` · `estimate/capture_recapture.py::chapman`, `estimate/chao.py::chao1` | MIT (0 stars — authority ASSERTED) | VERIFIED code / SYNTHETIC numbers |
| `check_recall(true_hits, retrieved)` — fuzzy title match of a known set against what a search returned, returning a per-hit TABLE not a scalar | `elizagrames/litsearchr` @ `0c108e3` · `R/write_scrape_test_searches.R:556` | **none stated** | VERIFIED |
| `MarginalYield(eps=0.01, k=2)`; `NConsecutiveIrrelevant.stop` as a testable object | `s-matysik/SnowBallSLR` @ `9491832` `stopping/yield_rule.py`; `asreview/asreview` @ `79d5682` `models/stoppers.py` | MIT; Apache-2.0 | VERIFIED |
| `calculate_h0(labels, N, recall_target)` — hypergeometric p-value for "we MISSED the target" | `mcallaghan/buscarpy` @ `90c1318` | MIT | VERIFIED |
| 4-round blocking + a disjunction of field thresholds giving THREE classes (`true_pairs` / `maybe_pairs` / neither); a DOI disagreement refuses a merge even on full field agreement | `camaradesuk/ASySD` @ `7b240f1` · `R/internal.R:211-230, 331-364, 368-374` | GPL-3.0 | VERIFIED |
| `canonical_key` precedence `doi: → oa: → s2: → sig:sha1(title_norm|year|surname)[:16]` | `s-matysik/SnowBallSLR` @ `9491832` · `identity/keys.py` | MIT | VERIFIED |
| `oa_snowball()` — `cites=` (forward) and `cited_by=` (backward) in one call, nodes + edges | `ropensci/openalexR` @ `5ae0717` · `R/oa_snowball.R` | NOASSERTION | VERIFIED |
| `GET /recommendations/v1/papers/forpaper/DOI:<doi>` — a third arm, **keyless** (probed live, returned 3 DOI-bearing recommendations for `10.3390/rs14205081`) | Semantic Scholar Recommendations API | — | VERIFIED (live probe) |
| `extract_terms(method="fakerake")` + `find_cutoff` (changepoint / cumulative node strength) — query expansion from a seed corpus's own text | `elizagrames/litsearchr` @ `0c108e3` · `R/term_selection.R:293-313` | none stated | VERIFIED |
| `FindRelatedTopic` → `GenPersona`: N perspectives each asking their own questions | `stanford-oval/storm` @ `fb951af` · `persona_generator.py` | MIT | VERIFIED |
| `HybridMaxRandom(probability=0.95)` — 5% of picks deliberately random so the ranker's blind spot is sampled | `asreview/asreview` @ `79d5682` · `models/queriers.py` | Apache-2.0 | VERIFIED |
| per-candidate `relevance_score` 0–10 normalised from `8/10`, `4/5`, floats and misnamed keys, default 5 on failure | `Future-House/paper-qa` @ `57e89f7` · `src/paperqa/core.py` | Apache-2.0 | VERIFIED |
| REJECTED: `get_refs(article_list, get_records='both')` — both directions, but **requires a Lens.org token** | `nealhaddaway/citationchaser` @ `ba382a7` | none stated | VERIFIED, rejected |

#### Recommended change (diff-shaped)

- **D1 — NEW `qc/instruments/litkb_discovery_recall.py`.** Port litsearchr's `check_recall`
  against the tracker. Input: a candidate list (titles+DOIs) + a named tracker subset. Output:
  one row per known hit (`tracker_id`, `best_match`, `similarity`, `doi_match`) plus recall@0.85
  AND the miss list. Reuses `pipeline/litkb/textnorm.py` and the existing
  `RESOLVE_TITLE_RATIO`. [VERIFIED source]
- **D2 — capture-recapture estimation with a REFUSAL litkb must add.** Port `chapman()` +
  `chao1()` + guards, with three arms (query search, `litkb.references`, S2 recommendations).
  **Add a guard SnowBallSLR lacks: refuse outright below 3 arms**, because its
  `estimate/assumptions.py` only WARNS that two-arm independence is untestable (zero residual
  dof) and a warning that turns nothing red is not a gate (§3.4c). Report UNDETERMINED (§3.5),
  not a number. [MIXED]
- **D3 — un-orphan the 630 citation candidates (defect fix, no new dependency).**
  (1) `mcp/server.py:852` — widen to `WHERE (workstream_id = %s OR (workstream_id IS NULL AND
  source = 'citation'))`, or attribute the rows at ingest. (2) `.claude/agents/lit-scout.md:5` —
  add `mcp__litkb__litkb_candidates`; it is a read tool (`server.py:1455` uses `_conn("reader")`)
  so the agent's one-write property is untouched. [VERIFIED]
- **D4 — forward chasing and recommendations, keyless.** An OpenAlex forward leg
  (`filter=cites:<openalex_id>`, cursor-paged, `mailto` polite pool) and an S2
  `/recommendations/v1/papers/forpaper/DOI:<doi>` leg, each writing candidates under a NEW
  `source` value (`citation-forward`, `recommendation`) so D2 can count per-arm overlap.
  citationchaser is rejected on its Lens.org token. [VERIFIED]
- **D5 — give the stop rule a number.** Log `n_returned` / `n_new_after_dedup` / `yield_rate`
  per query; extend the `SCOUT-STOP` line to carry them (e.g. `SCOUT-STOP: n=9
  reason=marginal-yield yield=0.00,0.00 eps=0.01 k=2 arms=3 recall_lower=UNDETERMINED`).
  Recording N is the one missing input for buscarpy's `calculate_h0`. [VERIFIED]
- **D6 — a three-state candidate identity (merge / HOLD / distinct).** Adopt `canonical_key`
  precedence for candidate fingerprints and ASySD's three-class outcome, where **HOLD is IGNORE
  per CLAUDE.md §3.6** — never resolved silently in either direction. litkb dedups candidates on
  DOI alone today. [VERIFIED]
- **D7 — query expansion from litkb's own corpus, plus a 5% random leg.** Replace "write 3–6
  queries from the topic" (`SKILL.md:26-31`) with terms mined from the 372,305 blocks litkb
  already holds, 3–5 generated perspectives, and one query in twenty deliberately off the ranked
  list — which also keeps D2's arms non-nested. [ASSERTED]
- **D8 — make the scout's stated confidence readable.** Today it is one word
  (`lit-scout.md:69-72`) buried in free-text `why_relevant`, absent from `REQUIRED_FIELDS`
  (`litkb_acceptance.py:493`) and joined to nothing. Either give it structure (a column, or a
  parsed suffix the grader extracts) and join it to `hunt_request_status.resolution_state`, or
  drop the instruction. [VERIFIED]

#### Local test set

| id | rows | kind |
|---|---|---|
| TS-1 | `Reports/literature_tracker.csv` — 460 rows, 403 with a parseable DOI, 72 Search Phase groups, joined to `litkb.main_identifiers` (466 active DOIs) → 385/403 = 95.5% admitted | REAL positive |
| TS-2 | the KB's 466 DOIs and the overlap census | REAL |
| TS-3 | `Reports/LITKB_SCOUT_RUN_2026-09-20.csv` — 9 drop-offs, stop reason `no-new-results` | REAL |
| TS-4 | the 15 E23 rows | REAL negative |
| TS-5 | the bogus `stored_doi` values on those rows in `Reports/LITKB_TITLE_HUNTS_2026-09-21.csv` — e.g. `10.2172/1885051` against the City of Seattle canopy assessment; `10.4135/9781452219011.n14` against the DeepForest note; `10.3403/30376491u` against the King County ortho spec | REAL negative, identifier-level |
| TS-6 | capture histories from the tracker's own Search Phase column → {1:400, 2:3}, S_obs=403, f1=400, f2=3 | REAL |
| TS-7 | `litkb.references` — 347 distinct `resolved_doi` over 17 files, 15 in the KB, 332 not | REAL |
| TS-8 | topic recall of the one scout run: 2/16 ≈ 12% | **CONSTRUCTED** — the 16-row topic set is L1's regex; the tracker records the Search Phase LABEL but nowhere on this machine records the phase's query PHRASE |
| TS-9 | the nonsense-topic run (workstream `scout-nonsense`, `SCOUT-STOP: n=0 reason=nothing-relevant`, 5 searches, 8 turns) | REAL negative |

#### Kill criteria

- **D1:** hold out `10.1007/s11252-007-0040-9` (a tracker row that IS extracted and WAS a scout-1
  drop-off) from the candidate list — the gate must report recall<1.0 and NAME it. Mutation-test
  as `qc/claims.py` was: if deleting a known hit does not move the number, the counter is not
  wired. Second: feed the TS-5 bogus DOIs as found; a `doi_match` on `10.2172/1885051` for
  tracker 235 must count as a MISS with a reason.
- **D2: BOTH KILLS ALREADY FIRE ON REAL ROWS, measured by L1.** (a) Chao1 on TS-6 gives
  N_hat=27,070 and recall 1.5% — the gate must REFUSE, because the human deduplicated across
  phases so they are not capture occasions; a build that reports 1.5% is red. (b) Chapman on
  n1=466 × n2=347, m=15 gives N_hat=10,156, SE=2,365, recall **7.9%** and PASSES both of
  SnowBallSLR's guards — which is precisely why the <3-arms refusal is required, and why the
  answer must be UNDETERMINED rather than 8%.
- **D3:** after the change, `litkb_candidates(state="new")` from a FRESH workstream must return
  >0 rows with `source='citation'`; 0 means the filter is still wrong. Converse known-bad: it
  must NOT return the p3-migration workstream's 500 manual rows — leakage across workstreams is
  red.
- **D4:** an S2 leg returning 0 recommendations for `10.3390/rs14205081`, or an OpenAlex forward
  leg returning 0 citing works for a seed whose `cited_by_count>0`, must refuse with a named code
  (`arm-empty`). A silent zero is what makes D2's estimator degenerate.
- **D5:** replay over TS-3's query trace must reproduce the n=9 stop AND print the yields that
  justified it; if it cannot because the trace holds no counts, **the instrumentation gap is the
  finding**. Second known-bad: TS-9 must still end `n=0 reason=nothing-relevant` — a yield-keyed
  rule never fires where yield is undefined, so the `nothing-relevant` branch stays first.
- **D6:** lowering the merge threshold until tracker 235 merges onto `10.2172/1885051` must go
  RED — the same shape as the existing `RESOLVE_TITLE_RATIO` 0.85→0.80 identity test in S1's
  done-state (c). The 4 tracker rows carrying a `Duplicate of` value must classify as **merge**,
  not HOLD.
- **D7:** UNRUN by design. If D1's recall does not rise over the topic-string baseline, the
  expansion is cost with no yield and must not land. §3.4c: the proposer never scores its own
  proposal.
- **D8:** a calibration read must become computable — "of drop-offs marked high, what fraction
  resolved contradicted". If that join cannot be written against the schema, the field is
  decoration and the gate is red.

#### Where it lands

**D3 first, before S5** — it is a defect fix in one WHERE clause and one frontmatter line, and
it makes the cheapest discovery arm litkb already owns reachable. **D1, D5 in S5**, because S5's
(b) counts drop-off outcomes and its `missing_dropoff_outcomes=0` says nothing about whether the
drop-offs were the right papers; D1 adds `discovery_recall` / `discovery_misses` and D5 adds
`stop_reason` with its yields to the same block. **D2, D4, D6 after S5** (improvements table),
each UNVALIDATED until a referee scores it. **D7, D8 after S5**, D7 explicitly unrun.

---

### 1.2 References → resolve + admit: citation anchoring (L5)

#### litkb today

litkb's anchoring ladder exists and is **stricter than anything L5 read outside it**:
`pipeline/litkb/extract/references.py` parses only the back-matter `listBibl` (:176, :258), then
`resolve_by_doi` (:582) where the DOI DECIDES with no title fallback; `resolve_by_search` (:685)
at ratio ≥0.85 AND first-author family AND year ±1 through `judge_candidate`
(`admit/resolver.py:112`); registry confirmation by `confirm_s2_candidate` (`resolver.py:424`)
with `review_record` / `edition_mismatch` / `type_mismatch` rungs; and a Crossref raw-string
PROPOSER `resolve_by_raw_search` (:633) that never auto-confirms.

The anchor is written in `extract/references_ingest.py:370` as `dois.get(doi)` over `doi_index`
(:290) — the live DB's active DOI identifiers — while the EDGE is built separately in
`references.py::process_tei` (:827) against `corpus_index` (:793), the manifest and bibliography
CSVs.

L5's live measurements (as `litkb_reader`, localhost:5433, 2026-09-22): **643 references from 17
files** (all `pipeline_version 'litkb-p6-1'`); 363 resolved, 261 unresolved, 19 ambiguous; **347
distinct resolved DOIs**; but only **17 references (2.6%) carry `resolved_work_id`** and only
**13 citation_edges** exist, against 969 citation_mentions and 630 never-admitted citation
candidates. The remaining refusals: 199 rows with a rejected Crossref candidate (64 at ratio
≥0.85, 41 at ratio 1.00), 48 with nothing to search on, 9 `doi_title_contained`, 3
`doi_title_mismatch`, 1 `doi_not_registered` — every one of the 199 also reading
`skipped=semanticscholar[,arxiv] (rate-limited)`, so the live rate is a **Crossref-only floor**.

**L5 corrects the plan.** The ruling `litkb-second-formula-decoder`'s aside that "all 643
references [are] unanchored" re-derives to 17 anchored / 13 edges. More decisive: the 347
distinct resolved DOIs intersect the 465 held works' active DOIs in **exactly 15 DOIs**, so
**17 of 17 reachable anchors were already made**. The ladder is at its ceiling on this slice;
the bottleneck is coverage — stage 6 has run on **17 of the 233 files that have blocks (7.3%)**.

**A stated invariant is violated 4 times on real rows.** `references_ingest.py:212` says "an
in-corpus edge or a candidate — never both, never neither". Four references are anchored yet
carry NO edge, and the same four also have a citation candidate saying the work is not in the
corpus. Cause: the anchor uses `doi_index` over `main_identifiers` while the edge uses
`corpus_index` over the manifest CSVs. Cost: 4 of a possible 17 edges (24%) plus 4 false
acquisition leads. DOIs: `10.5194/isprsannals-i-7-129-2012`, `10.1016/j.ufug.2018.03.006`,
`10.1016/j.scitotenv.2017.08.103`, `10.48044/jauf.1994.017`.

**`citation_edges` is write-only.** Its only production reader in the tree is its own writer's
counter at `references_ingest.py:152`; no MCP tool, brief, review-check or review-context reads
it, and `mcp/server.py:339` excludes reference blocks from search by default. Meanwhile
`citation_mentions` already carries the citing sentence, marker and page for **969 of 969** rows.

**`pipeline_version` does not identify the code that wrote the rows.** All 643 rows say
`litkb-p6-1`; so would rows written today, although commit `8829558` (2026-09-19) added
`resolve_by_raw_search`. Zero rows carry `source='crossref_raw_search'`, and 48 sit at
`no_title_or_author` that today's ladder would attempt.

#### Strongest external mechanisms

| mechanism | repo @ sha · symbol | licence | status |
|---|---|---|---|
| **SBMV**: retrieve rows=20; the relevance score is ONLY a candidate cutoff; accept/reject computed **from the RAW STRING** — integers matched against candidate volume/year/issue/page/title/container-title, author `fuzz.partial_ratio` against the first `3·len(a)` chars, year miss retried at ±1 weight 0.5; then a **support gate** (`if support < 3: return 0`) and a generalized Jaccard `sum(min)/sum(max)` | `CrossRef/reference-matching-evaluation` @ `ed347f26` · `matching/cr_search_validation_matcher.py`, `match_config.py` | **MIT** (LICENSE read) | VERIFIED |
| The shipped config **disables** the validation Crossref is famous for: `Matcher(0.4, -1, …)` with `test_params` pinning the order as `(min_score, min_similarity)` → `min_similarity = -1`; the published thresholds live in the analysis notebooks | same repo · `match_config.py`, `tests/test_params` | MIT | VERIFIED |
| GROBID consolidation post-validates on **first-author surname alone** (Ratcliff-Obershelp < 0.8 rejects), no title/year/type check, blank surname passes trivially, DOI query skips validation in single mode | `kermitt2/grobid` @ `3a849297` · `Consolidation.java` | Apache-2.0 | VERIFIED (and rejected as a decider) |
| COCI builds a link from `ref.get('DOI')` alone with no fallback; `Citation` carries `agent`, primary source, `generatedAtTime`, `invalidatedAtTime`, `wasDerivedFrom` snapshot n−1 — **and no score field anywhere** | `opencitations/index` @ `d82db1b9` · `oc_index/parsing/crossref.py`, `oc_index/oci/citation.py` | ISC | VERIFIED |
| Wapiti CRF over per-line features for reference-string *finding* (the footnote class) | `inukshuk/anystyle` @ `c6f5fb2f` · `lib/anystyle/finder.rb` | not in the file header; widely reported BSD-2 | mechanism VERIFIED / licence ASSERTED |
| Citation-intent classification whose input unit is the citing sentence — which litkb already stores on 969/969 rows | `allenai/scicite` @ `b33a8cd0` · README | not stated | ASSERTED |

#### Recommended change (diff-shaped)

- **R0 — make the frozen gold joinable (crosswalk instrument).** NEW read-only
  `Scripts/qc/instruments/litkb_refmatcher_crosswalk.py` writing
  `phase4/qc/litkb_gold_ref_crosswalk.csv` with `gold_stem, db_key, db_work_id, n_refs_gold,
  n_refs_db, route ∈ {exact,prefix,none}`; refuses to emit a row for an ambiguous stem.
  **Without this, no anchoring change can be scored at all.** [VERIFIED]
- **R1 — version the resolution.** Bump `PIPELINE_VERSION` on any ladder change; add a test
  pinning the constant to a hash over the ladder's symbol set (`resolve_by_doi`,
  `resolve_by_search`, `resolve_by_raw_search`, `confirm_s2_candidate`). A re-resolution opens a
  new `extraction_runs` row; old reference rows stay. [VERIFIED]
- **R2 — a raw-string validator modelled on Crossref SBMV, behind `confirm_s2_candidate`.** New
  `resolver.raw_support(ref, cand) -> (support, jaccard, detail)`; `resolve_by_raw_search`
  requests `rows=5` instead of the top hit and only proposes a candidate to the UNCHANGED
  `confirm_s2_candidate` when `support >= 3`. New refusals keep distinct names
  (`raw_support_below_3`, `raw_jaccard_below_cut`) so existing histograms still join. Scoped to
  the class `resolve_by_raw_search` already owns, so it cannot dilute the other 595. [MIXED]
- **R3 — one index for the anchor.** Make the DB the single authority (CLAUDE.md §3.3): the
  ingest already holds `doi_index` — let it decide the edge as well, and keep `corpus_index` only
  as a reported discrepancy (`skipped['edge_index_disagreement']`), never as a second truth.
  [VERIFIED]
- **R4 — run stage 6 on the rest of the corpus, and report the anchor rate against its real
  denominator.** No code change; a wire-cost decision (~1 s/reference at the Crossref pacer;
  ~8,800 references extrapolated, ~2.5 h) that is **Kam's to approve**. What MUST change is the
  reporting contract. [VERIFIED]
- **R5 — give `citation_edges` a reader.** One MCP tool (`litkb_cited_by` / `litkb_cites`) over
  `citation_edges` joined to `citation_mentions.sentence`. [VERIFIED]

#### Local test set

| id | rows | kind |
|---|---|---|
| TS1 | `select pipeline_version, count(*) from litkb."references" group by 1` → 643 rows, all `litkb-p6-1`; `source='crossref_raw_search'` → 0 today | REAL |
| TS2 | the 347 / 465 / **15** overlap query | REAL |
| TS3 | the live **48** `no_title_or_author` rows — median raw string 87.5 chars, none empty, median 3 integers, 30 of 48 with ≥3 integers (545 of all 643 have ≥3) | REAL |
| TS4 | `Reports/litkb_splink_gold_2026-09-15.json` joined to the live rows — **138/365 positives, 2/77 must-not-link, 0/20 near-positive mutations, 0/5 lost-genuine**; a prefix crosswalk maps 14 of 15 stems uniquely, 0 ambiguously, 1 not at all (Chrisman_1982) | REAL, **not joinable today** |
| TS5 | `qc/test_litkb_crossref_raw_search.py` + `fixtures/litkb_crossref_raw_search_item2.json` | REAL |
| TS6 | the exact **4** invariant-violating rows (candidates `source='citation'` joined to `main_identifiers`), cross-checked against anchored+edge=13 / anchored-without-edge=4 / edge-without-anchor=0 | REAL negative |
| TS7 | `select count(distinct file_id) from litkb.blocks` = **233** vs `… from litkb.extraction_runs where stage='6-references'` = **17** | REAL |

#### Kill criteria

- **R0:** a CONSTRUCTED gold stem prefixing TWO live work keys must emit `route=none` and exit
  non-zero, never pick one — the 2026-09-15 "14"/"34" row-number-edge failure mode. Second: a
  gold `ref_key` absent from the DB run must map to nothing, never to the nearest-index reference.
- **R1:** a mutation that adds a rung to `resolve_reference` WITHOUT touching `PIPELINE_VERSION`
  must turn the test red. **Not hypothetical — commit `8829558` is exactly that mutation and
  nothing went red.**
- **R2:** three, all required. (1) The 3 `book_review` must-not-link entries (`10.2307/1269348`
  Alwan b13 and two others) must not be proposed — the gate Crossref SBM fails 3 of 3. (2) The 40
  `mutation_year±3` gold entries must return unresolved or a different DOI, never the original —
  ref-matcher fails this 30 of 40 because an exact year is 1 point of 48. (3) The support gate
  must be SHOWN to fire: Besag b32 (*Statistical Ecology* Vol. 2) must score `support<3`, where
  the unvalidated top-hit path returned `10.1126/science.176.4031.156.a`, a *Science* review of
  Volume 1.
- **R3:** a CONSTRUCTED reference whose DOI is in the manifest CSV but NOT in `main_identifiers`
  must produce a candidates row and NO edge; the reverse must produce an edge and NO candidate. A
  run in which any reference produces BOTH must FAIL the ingest (an assertion in the shape of
  `_check_mention_counts`), not merely be counted in `skipped`.
- **R4:** the report must state the anchor rate as anchored / (references whose resolved DOI is a
  held work). A run whose headline is anchored / references FAILS review. On the current slice
  those two numbers are **2.6% and 100%**, and only the second says anything about the matcher.
- **R5:** the tool must return ONLY edges whose reference is `resolution='resolved'` with a
  non-null `resolved_work_id`. A CONSTRUCTED edge row whose reference is `ambiguous` must not
  appear — the 0020 trigger `_reference_resolution_is_shown` already forbids writing it; the test
  proves the reader does not invent one.

#### Where it lands

**R0 before anything else in this stage** — until the crosswalk exists, CLAUDE.md §3.4c blocks
accepting any anchoring change, because no kill criterion can be shown to fire. **R3 is a defect
fix and lands before S5.** **R4 is a Kam decision** (wire cost + the reporting contract), and it
is the only change that can move the anchored count on this corpus. **R1, R2, R5 after S5.**
R5 also feeds L1-D3 and L1-D4: a reader over `citation_edges` is what turns the citation arm into
a discovery arm D2 can count.

---

### 1.3 Search inside the base (L4)

#### litkb today

`litkb_search` (`mcp/server.py`) is three lexical legs over `litkb.blocks` — all-terms tsvector
(:379-386), any-term tsvector via `litkb.any_term_query` (:392-398), and pg_trgm similarity
(:403-408) — fused in Python by reciprocal rank at k=60 (:444-455), scoped by
`visibility.FILE_JOIN` (`visibility.py:89-99`), with reference/page_header/page_footer/
page_number/other excluded by `DEFAULT_KINDS` (:348-352). The vector leg is wired but dead
(:90, 560-576).

The documented pain is recall — "a paraphrase sharing no words with the text will NOT be found" —
measured in `Reports/LITKB_EMBEDDINGS_2026-09-15.md` §5.2, where bge-m3's vector leg scored
recall@20 **0.617** against a pre-committed floor of 0.80 and MRR **0.235** against 0.50, and
hybrid RRF reached **0.733** against 0.83.

**The pain nobody had written down is latency, and L4 measured it on the live cluster today:**
one `litkb_search(scope="all")` takes **16.0 s**, of which the trigram block leg alone is
**14.3 s and returns ZERO rows**. Two independent causes, both measured:

1. `EXPLAIN (ANALYZE, BUFFERS)` shows `Rows Removed by Index Recheck: 52036`. The GIN index is an
   **expression** index, so the recheck re-evaluates `litkb.norm_search_text(text)` on every
   candidate heap row — a function measured at **20.54 s over all 372,305 blocks** against
   **0.19 s** for `sum(length(text))` (~55 µs/block) — and it is `proparallel='u'`, so the scan
   cannot parallelise.
2. `%` means `similarity >= show_limit() = 0.3`, and over a 3% TABLESAMPLE the **maximum**
   similarity between a 46-character query and any block is **0.224**, while max
   `word_similarity` over the same sample is **0.458**. The operator structurally cannot match a
   long block.

So litkb's advertised three-leg fusion **has in practice been two legs, at a 14-second cost per
call.** Corpus, measured by L4: 372,305 blocks total, 105,760 in a current run; 486 works;
`litkb.chunks` = 0 rows and `litkb.embeddings` = 0 rows, though `0002_text.sql` already defines
chunks with `block_ids uuid[]`, `page_start` and `page_end` — the chunk-to-quotable-block
contract exists on paper and is unbuilt.

#### Strongest external mechanisms

| mechanism | repo @ sha · symbol | licence | status |
|---|---|---|---|
| `<%` `word_similarity` vs `%` `similarity` on the same `gin_trgm_ops` index | pg_trgm 1.6, measured on the live cluster | PostgreSQL | VERIFIED (measured) |
| RRF as ONE SQL statement: two CTEs with `RANK() OVER`, `FULL OUTER JOIN`, `COALESCE(1.0/(k+rank),0)`, k=60 — litkb's own constant | `pgvector/pgvector-python` @ `60739dfd` · `examples/hybrid_search/rrf.py` | PostgreSQL | VERIFIED |
| retrieve both legs, dedupe, rerank the union with a cross-encoder | same repo · `examples/hybrid_search/cross_encoder.py` | PostgreSQL | VERIFIED |
| ONNX cross-encoder reranker: `flashrank/Ranker.py` imports `onnxruntime` + `tokenizers` and **nothing else** — no torch, no transformers, CPU, `max_length=512` | `PrithivirajDamodaran/FlashRank` @ `11f7a40d` | code Apache-2.0; **weights: `Config.py` line 2 states the HF repo is CC-BY-SA** | VERIFIED |
| one `rank(query, docs)` API over cross-encoder / T5 / ColBERT / FlashRank families | `AnswerDotAI/rerankers` @ `5b9cbb07` · `reranker.py:7-37` | Apache-2.0 | VERIFIED |
| `BaseReranker` = `AutoModelForSequenceClassification` over (query,passage), `query_max_length = max_length*3//4` | `FlagOpen/FlagEmbedding` @ `fd1a2bdf` | MIT | VERIFIED |
| `DocMeta.doc_items: list[DocItem]` (min_length 1) + `headings: list[str]`; `excluded_embed` lists `doc_items` but **NOT** `headings` — provenance carried, headings embedded | `docling-project/docling-core` @ `51bc31b3` · `transforms/chunker/doc_chunk.py:58-64` | MIT | VERIFIED |
| `EvaluateRetrieval.evaluate(qrels, results, k_values)` over `pytrec_eval` + custom `mrr`, `recall_cap`, **`hole`**, `top_k_accuracy` | `beir-cellar/beir` @ `ef83d293` · `beir/retrieval/evaluation.py` | Apache-2.0 | VERIFIED |
| HyDE: generate hypothesis passages, embed `[query] + hypotheses`, take the **arithmetic mean**, search with that one vector; `promptor.SCIFACT` is the scientific prompt | `texttron/hyde` @ `a2fd8734` · `src/hyde/hyde.py:17-28` | MIT | VERIFIED |
| `halfvec` up to 4,000 dims; binary quantisation first pass then exact re-rank; iterative index scans for post-filtering | `pgvector/pgvector` @ `efa08fda` README | PostgreSQL | VERIFIED (README) |
| RULED OUT: input is "a concatenation of its title and abstract", `max_length 512`, CLS pooling — a **paper-level** embedder | `allenai/specter2` @ `fac1cb09` README | Apache-2.0 | VERIFIED that it is paper-level |
| RULED OUT: late interaction with a per-token index — cannot live in `litkb.embeddings` (one halfvec per chunk) | `stanford-futuredata/ColBERT` @ `cc4f3dc9` / `lightonai/pylate` @ `3389837c` | MIT | ASSERTED |

#### Recommended change (diff-shaped)

- **Leg 3 operator: `%` → `<%`.** `server.py:403-408` — swap
  `norm_search_text(b.text) % norm_search_text(%(q)s)` for
  `norm_search_text(%(q)s) <% norm_search_text(b.text)`, and `ORDER BY similarity(...)` for
  `word_similarity(...)`. No migration, no new index. Measured: `%` gave 0/10/2 rows at
  14.9/16.5/14.4 s; `<%` gave 0/2/4 rows at **1.6/5.4/1.8 s**. [VERIFIED]
- **Materialise `norm_search_text` as a STORED generated column.** New migration:
  `ALTER TABLE litkb.blocks ADD COLUMN norm_text text GENERATED ALWAYS AS
  (litkb.norm_search_text(text)) STORED` (legal — `provolatile='i'`); replace
  `blocks_norm_text_fts` / `blocks_norm_text_trgm` with plain indexes on `norm_text`; replace
  every `litkb.norm_search_text(b.text)` in `server.py` with `b.norm_text`. Cost ~+65 MB on a
  314 MB table. [MIXED — cost VERIFIED, fix not applied]
- **Hybrid RRF as one SQL statement.** Rewrite `server._search` (:537-577) and `_rrf` (:444-455)
  so fusion happens in SQL rather than in Python across 3–6 round trips. [VERIFIED]
- **FlashRank ONNX cross-encoder rerank over a depth-100 fused set (the candidate).** Retrieve
  depth 100 from the fused legs instead of the caller's limit; rerank the union with
  `ms-marco-MiniLM-L-12-v2`; return the top `limit`. Add a `reranker` field to the result
  envelope beside `legs` and `vector_leg`, so a caller is never told a rerank happened that did
  not — the discipline `server.py:560-576` already applies to the vector leg. **This targets the
  metric that failed worst** (hybrid MRR 0.225 vs a 0.53 floor, while hybrid recall@20 is 0.733
  vs 0.83). [MIXED]
- **Fill `litkb.chunks` from BLOCKS, not from flat text.** New
  `pipeline/litkb/index/chunk_blocks.py`: group current-run blocks of a file into the 300–500
  token band, **never splitting a block**; `block_ids` = the blocks consumed; `page_start` /
  `page_end` from their `page_no`; `section_path` from the blocks'; prepend `section_path` to the
  embedded text the way `DocMeta.headings` is. Replaces P7's flat-`.txt` chunker, whose own
  report calls it a heuristic with **28 of 60 anchors straddling a boundary**. [VERIFIED]
- **BEIR-style scorer, and the `hole` metric litkb has no analogue for.**
  `qc/instruments/litkb_search_bakeoff.py` scores with `pytrec_eval` + BEIR's custom metrics
  rather than re-implementing recall@k by hand a third time (`litkb/index/fuse.py` on the
  embeddings branch is the second implementation; `server._rrf` is the fusion twin). [VERIFIED]
- **HyDE query-side expansion — DEFERRED, only after the above.** A query-side wrapper on
  whatever vector leg exists; no re-indexing. Aimed at the 9-query residue P7 §5.4 calls genuine
  encoder failure. [VERIFIED]
- **SPECTER2 / SciNCL and ColBERT/PLAID — recommended AGAINST.** Recorded so nobody proposes "use
  a scientific embedder" by reflex: litkb retrieves a quotable BLOCK, not a paper, and
  `litkb.embeddings` is keyed `(chunk_id, model)` with a halfvec. [MIXED]

#### Local test set

- **Positives:** the P7 gold, re-anchored on live DB blocks. **50 of its 57 source stems map 1:1
  to `litkb.main_works` keys** (the gold stem truncates the DB key), **43** of those works carry
  current-run blocks (14,679 blocks), and **45 of the 60** gold anchors are locatable in those
  blocks today, median 2 blocks per anchor. The P7 gold is anchored on char offsets into `.txt`
  dumps, not DB blocks, so it **cannot be replayed as-is**. The re-anchoring matcher is L4's and
  is therefore **CONSTRUCTED**: per §3.4c a referee must build and freeze the qrels before any
  new leg runs on them.
- **Negatives (REAL, and they already work):** **75 terms** occur in ≥8 `reference` blocks of a
  current run and in ZERO body blocks — `photogramm` 138/0, `heidelberg` 24/0, `sutskever` 12/0.
  All three return 0 rows under default kinds and 10 rows under `kinds="all"` today. **This is
  the sharpest gate on any new leg**, because a dense index has no furniture rule: an embedding
  of a bibliography entry is a perfectly good embedding, and nothing in a vector index knows it
  is furniture.
- **Latency baseline (REAL):** the six-statement baseline — 16.0 s total, blocks TRGM 14,285 ms
  for 0 rows — plus the EXPLAIN plan.
- **The floors, verbatim** from `Reports/litkb_p7_thresholds_2026-09-15.json`: vector
  0.60/0.80/0.50; hybrid 0.63/0.83/0.53.

#### Kill criteria

- **Leg 3:** delete leg 3 entirely and the gate must go red. **Today it would not** — leg 3
  already returns 0 rows on most queries, so any gate that only checks the fused output is not
  testing leg 3. The known-bad is migration 0025's own worked example: a query reachable only
  through trigram (`misclassi<C0>cation` as the extractor mangles it).
- **Stored column:** `qc/instruments/litkb_norm_additivity.py` (the instrument 0025 cites) must
  pass against the STORED column, and `SELECT count(*) FROM litkb.blocks WHERE norm_text IS
  DISTINCT FROM litkb.norm_search_text(text)` must be 0. Show it fires by hand-corrupting one
  stored value in a throwaway database. Without that check the column and the function are twins
  — migration 0014's D1 twin-drift, with a 372,305-row blast radius.
- **SQL fusion:** must reproduce `server._rrf`'s ordering byte-for-byte on a fixed three-leg
  input. Show it fires by perturbing k in one implementation only.
- **Reranker — two, both must fire.** (1) **Shuffled-reranker control:** replace the reranker's
  scores with a fixed permutation of themselves; fused-then-shuffled MRR must fall to the
  fused-only MRR or below — otherwise the harness is measuring the depth increase from 10 to 100,
  not the reranker. (2) With the reranker in place, `photogramm`, `heidelberg` and `sutskever`
  must still return 0 rows under default kinds; a reranker that reorders a candidate set
  containing reference blocks re-admits the 9,468 bibliography blocks the furniture rule excludes.
- **Chunks:** every chunk's text must be reconstructible from its `block_ids` under
  `norm_search_text`, and `page_start <= min(page_no) <= max(page_no) <= page_end`. Show it fires
  by dropping one block id from a chunk's array. This is the property that makes a chunk hit
  quotable: `litkb_record_use` quotes a BLOCK, so a chunk that cannot name its blocks is a
  citation dead end.
- **Scorer — the gate on everything:** the harness on the OLD lexical-only legs must reproduce
  the P7 report's own lexical-alone row shape (**0.317 / 0.567 / 0.277**) and §1's leg-3 latency
  (≥10 s, 0–10 rows) BEFORE any new leg is scored. It must also assert that `server._rrf` and
  `litkb/index/fuse.py:rrf` — two live implementations of the same k=60 formula — agree on a
  fixed input, or one-fact-one-home is already broken before anything is added.
- **HyDE:** run it with the hypothesis generator replaced by a fixed, topic-irrelevant passage.
  Recall must fall to or below the plain-query vector leg. If an irrelevant hypothesis helps, the
  gain is coming from the vector averaging, not from the hypothesis.

#### Where it lands

**Leg 3 and the stored column are defect fixes and should land before S5**: S5's run spends
16 seconds per search today, of which 14 buy nothing, and an unattended run's budget (L12) is
measured in exactly those seconds. **The BEIR harness lands next and gates everything else** —
nothing new may be scored until it reproduces the old numbers. **SQL fusion, chunks, reranker
after S5** as the improvements table's retrieval line; each UNVALIDATED until a referee scores it
on frozen qrels. **HyDE last**, and only if a vector leg exists. Counter-wise this stage does not
add to S5's (b) directly; it protects `hunts_over_budget=0` and the quality of every VERIFIED
line the brief carries into S6.

---

### 1.4 Record: the QUOTE gate (L2)

#### litkb today

A quote becomes evidence through **four comparisons of the same two strings**:
`mcp/server.py:1129` calls `use.locate_in_text` and refuses `quote-not-in-block` at :1131 before
anything is written; `use.py:77-144` is the one Python locator, which canonicalises line endings
on both sides (`textnorm.py:53-79`), does `canon_text.find(canon_quote)` at :129, then rebuilds
the RAW offsets through a `raw_at[]` table at :135-140 because `\r\n` is one canonical character
and two stored ones; `use.py:162-207` pushes the same rule into SQL for the CLI
(`position(quote in litkb.canonical_newlines(b.text))` at :194-195, over the current run of
active files only); and the verdict itself is the database's — migration `0026:108-142`
recomputes `quote_verified` unconditionally inside `litkb.add_evidence` (`0007:194-234`,
SECURITY DEFINER, writer has no direct INSERT at `0007:241`).

L2's measured pain, as `litkb_reader` on 2026-09-22: `litkb.use_versions` holds **421 rows and
only 35 carry evidence**; of those 35, **20 verify against the raw bytes and 35 once line endings
are canonical**, so **15 rows — 43% of all evidence the project holds — exist only because of
migration 0026**.

On the 104,760 current-run blocks: **51,202 (48.9%) carry `\r\n`**, **479 (269 paragraph) carry
an in-word C0 ligature byte**, 122 carry NBSP, 5,133 carry curly quotes. **Correcting the
brief:** hyphenation at line ends, soft hyphens and Unicode ligatures occur **ZERO** times;
running heads are their own blocks (`page_header` 26,590, `page_footer` 9,692); and every
evidence row sits in a paragraph block.

**The real defect:** migration 0025 repaired the ligature symptom **in the search index only**
(it prepends the five spellings ff/fi/fl/ffi/ffl to `norm_search_text` and deliberately never
rewrites `blocks.text`). Of the 269 damaged paragraph blocks, **120 hold a spelled-out ligature
word reachable through `litkb.norm_search_text`, and `use.locate_in_text` refuses 120 of 120.**
An agent searches `defined`, is shown the block, quotes the sentence, and `record_use` answers
"the quote is not in that block's text". Sample: block
`01a0abc7-427a-7049-805c-5b71a0a14683` stores `de\x01ned`. The tool's search leg and its record
leg describe the same bytes differently.

Separately, `page_no` is never null, so **no block spans a page**, and **1,202** current-run
paragraph continuations across a page boundary hold sentences that no single block contains and
that therefore cannot be recorded at all.

#### Strongest external mechanisms

| mechanism | repo @ sha · symbol | licence | status |
|---|---|---|---|
| `matchQuote`: **exact-first** (`indexOf` loop) → bounded approximate search → rank candidates by quote-errors + prefix + suffix + position hint; `Match` carries `end` so insertions extend the span | `hypothesis/client` @ `b4d085a` · `src/annotator/anchoring/match-quote.ts` | BSD-2-Clause (LICENSE file; API says NOASSERTION) | VERIFIED |
| Myers bit-parallel approximate search; `findMatchStarts` re-searches the reversed pattern and "chooses the one that maximizes the length of the match" | `robertknight/approx-string-match-js` @ `fe814eb` | MIT | VERIFIED |
| `SequenceMatcher.get_opcodes()` → `(tag,i1,i2,j1,j2)` — the human-auditable alignment diff, **stdlib and already importable locally** | `python/cpython` @ `c016c25` · `Lib/difflib.py` | PSF-2.0 | VERIFIED |
| **TRAP:** `autojunk=True` is the default and deletes any element of `b` occurring more than `len(b)//100+1` times once `len(b) >= 200` | same · `difflib.py:297-303` | PSF-2.0 | VERIFIED |
| **TRAP:** `_partial_ratio_impl` only tries windows of exactly `len(shorter)`, so `partial_ratio_alignment` can never return a span LONGER than the quote | `rapidfuzz/RapidFuzz` @ `db6e504` · `src/rapidfuzz/fuzz_py.py:148-154` | MIT | VERIFIED |
| Separate budgets for substitutions / insertions / deletions (`choose_search_class`) — nearly the discrimination litkb needs | `taleinat/fuzzysearch` @ `4f6d9d8` | MIT | VERIFIED |
| W3C `TextQuoteSelector{exact,prefix,suffix}` + `TextPositionSelector{start,end}` as complementary selectors; position "very brittle", quote+context robust, **both recorded** | W3C Web Annotation Data Model §4.2.4/§4.2.5; `apache/incubator-annotator` @ `cb534ed` (exact only, no fuzziness) | W3C Rec; Apache-2.0 | ASSERTED (spec) / VERIFIED (code) |
| **NEGATIVE:** PaperQA2 performs **no byte-level verification of any quoted span** — its "evidence context" is LLM-generated prose about a chunk with a relevance score | `Future-House/paper-qa` @ `57e89f7` · `src/paperqa/core.py::_map_fxn_summary` | Apache-2.0 | VERIFIED (negative) |
| `score(docs, claims)` → `(pred_label, max_support_prob, used_chunk, support_prob_per_chunk)` — names WHICH chunk supported | `Liyan06/MiniCheck` @ `b58b9fa` | Apache-2.0 (models separate) | VERIFIED — a *different* gate |
| scite's own reported pipeline fails to identify **~30% of citation statements in PDFs** (~5% in XML) | scite.ai / QSS 2021 methods paper | proprietary | ASSERTED |

#### Recommended change (diff-shaped)

- **D1 — close the search/record ligature disagreement (120/120).** `use.locate_in_text`
  (`use.py:77-144`) gains a ligature-expansion rung **after** the canonical-newline find, mapping
  a C0 byte to 2–3 quote characters inside the existing `raw_at[]` offset construction
  (:135-140), using 0025's own closed five-spelling set; a new migration gives
  `litkb._use_evidence_verify` the identical expansion (as `0026:108-142` did for
  `canonical_newlines`); `mcp/server.py:1140-1152`'s no-newline-canon refusal is extended to name
  the new migration rather than bypassed. **`blocks.text` is never rewritten.** [VERIFIED]
- **D2 — record the match rung and the diff on the evidence row.** `litkb.use_evidence` gains
  `match_rung smallint NOT NULL` (1 exact-raw / 2 canonical-newline / 3 class-closed) and
  `match_diff jsonb`; `use.locate_in_text` returns `(start,end,rung,diff)`; `litkb.add_evidence`
  takes them; the verify trigger **recomputes** the rung (so a client-supplied value cannot
  survive, exactly as `0026:104-107` already does for `quote_verified`);
  `use_evidence_status.promotable` narrows to `quote_verified AND run_is_current AND match_rung
  <= policy`; `brief.build` and the promotion report print the rung beside every VERIFIED line.
  [VERIFIED]
- **D3 — rung 3: class-closed alignment with the diff recorded, NOT a distance threshold.** New
  `Scripts/pipeline/litkb/quotediff.py` with align/coalesce/classify and one closed class
  vocabulary (`ligature-c0`, `nbsp`, `curly-quote`, `dash`, `ws-run` present in the corpus;
  `hyphen-break`, `dehyphenated`, `running-head` defined but explicitly marked **not exercised by
  this corpus**). Called from `use.locate_in_text` only after rungs 1 and 2 fail. **difflib
  only** — it is the sole fuzzy library installed locally; rapidfuzz is used for
  `Levenshtein.opcodes` if speed is ever needed, never for the anchor. [MIXED]
- **D4 — cross-page quotes: refuse with both block ids, not a silent miss.** `use.locate_quote`
  (:162-207) gains a no-match diagnostic using the W3C prefix/suffix idea — does a prefix of the
  quote end one block and the suffix begin the next page's first paragraph — and
  `mcp/server.py:1131` gains a new refusal code `quote-spans-page-break` carrying **both** block
  ids and advising two separate uses. Evidence stays anchored in exactly one block;
  `use_evidence.block_id` is a single column and a two-block span is a schema change nobody has
  argued for. [VERIFIED]
- **D5 — return the matched prefix on a refusal so the caller can self-correct.**
  `mcp/server.py:1131`'s refusal gains the longest matching prefix (bounded) and its offset,
  built with the same `quotediff.align` from D3. [VERIFIED]

#### Local test set

- **Positives (REAL):** the 35 rows of `litkb.use_evidence` with their blocks. They must all
  re-verify at their original offsets under every change.
- **Real damage carriers (REAL):** the 269 current-run paragraph blocks matching
  `b.text ~ '[A-Za-z][\x01-\x08\x0b\x0c\x0e-\x1f][A-Za-z]'` (joined to files on
  `current_run_id`), of which **120** have a spelled-out ligature word reachable through
  `norm_search_text`. Named rows: `01a0abc7-427a-7049-805c-5b71a0a14683` (`de\x01ned`),
  `01a0abc7-429d-7a0d-b7fb-252dab0c32ec` (`e\x01ects`),
  `01a0abc7-42ad-7050-b607-63aacd8a50c8` (`in\x01nitely`).
- **Cross-page continuations (REAL):** the **1,202** rows from the windowed query
  (`lead()` over `file_id` ordered by `page_no, reading_order`, filtered to `nxt_pg = page_no+1`,
  `text ~ '[a-z,]$'`, `nxt ~ '^[a-z]'`), across 233 files.
- **Existing negatives already in the repo (REAL):** `qc/test_litkb_first_use.py:507` (one
  character), :526 (paragraph join), :456 (break at either end), :434 (offset mapping), :313
  (superseded run), :563 (raw CRLF).
- **CONSTRUCTED mutations** generated from the 35 real rows (generator in a scratchpad probe,
  never stored): must-PASS `C-LIG`, `C-NBSP`, `C-HYPHBRK`, `C-CURLY`, `C-HEAD`; must-REFUSE
  `N-ONECHAR`, `N-DROPWORD`, `N-NEGATE`, `N-CROSSBLOCK`.

#### Kill criteria

- **D1:** a quote spelling the C0 byte as the WRONG ligature (`efiects` for `e\x01ects`) must
  REFUSE — the expansion is a disjunction over five candidates, not a wildcard. On block
  `01a0abc7-427a-7049-805c-5b71a0a14683` the quote `defined` must verify with
  `[char_start,char_end)` cutting exactly the 7 stored characters `de\x01ned`; an off-by-one is
  the whole failure mode. All 35 existing rows must re-verify at their original offsets, and the
  Python and SQL expansions must agree on all 269 blocks.
- **D2:** the back-fill producing any split other than **20 rung-1 / 15 rung-2** means the ladder
  does not describe the existing corpus — RED. A row written with a client-supplied
  `match_rung=1` on a rung-3 match must come back as 3. With the promotion policy at `rung<=2`, a
  rung-3 row must be REFUSED by `promote prepare`.
- **D3:** `N-ONECHAR` must REFUSE on all 35 rows while `C-NBSP` PASSES — **they are the same edit
  distance (1)**, so only the class test separates them. Constructing `SequenceMatcher` WITHOUT
  `autojunk=False` must make a named test fail. Classifying RAW uncoalesced opcodes must make
  `C-HEAD` fail (measured: difflib splits an injected running head around a shared space into
  `delete \n1234` + `delete  J. FOREST ECOL.\n`, and neither fragment classifies). Mutating
  `classify()` to return a sentinel instead of `None` must go red. `first_use.py:526` (dropped
  blank line) must still pass — `ws-run` must not swallow a paragraph join.
- **D4:** a quote assembled from a real A-tail plus B-head must produce `quote-spans-page-break`
  naming BOTH ids, not `quote-not-in-block`. Mutating the prefix/suffix test to always succeed
  must go red — a quote genuinely absent from the work must still get `quote-not-in-block`, so
  the new refusal cannot become the catch-all.
- **D5:** the returned prefix must be bounded at ≤120 characters and must pass through `_out()`'s
  two redactors — a refusal built from block text is exactly the leak `server.py:1064-1071`
  already warns about. The `--sites` census in `qc/instruments/litkb_p2_mutations.py` must cover
  the new call site; removing either redactor from that path must go red.

#### The measurement that settles the design question

L2 measured, on litkb's own 35 evidence rows, that **no distance threshold can work**: an NBSP
substitution (legitimate extraction damage) and the plan's known-bad one-character semantic
mutation are **BOTH edit distance 1**, while a legitimate page-head injection is **24** — larger
than every illegitimate class (drop-word 5–13, negate 4). The legitimate and illegitimate
distributions are **interleaved, not merely overlapping**. Any proposal of the form "rapidfuzz
`partial_ratio >= 95`" or "Levenshtein ≤ k" for this gate is refuted by these rows.

The class-closed alternative, prototyped by L2 on the real rows: 35/35 true positives accept;
ligature 8/8, NBSP 35/35, hyphen-break 35/35 accept; one-char 35/35, drop-word 35/35, negate 9/9
REFUSE. The one failure is **reported, not hidden**: running-head refused 35/35 because difflib
anchors on a space inside the injected head and splits it into two opcodes — which is why
classification must run on a COALESCED diff. **These are L2's own prototype's numbers and per
CLAUDE.md §3.4c are not acceptance evidence until an independent agent re-runs them.**

#### Where it lands

**D1 is the highest-value fix in the whole round and belongs before S5** — 120 real blocks are
unquotable today, S5 records quotes from HIGH-tier text, and an agent that cannot record the
sentence it was shown burns turns re-guessing. **D5 lands with it** (it is one alignment on an
already-failed path, and the 2026-09-20 proving run's answer to a bare refusal was to quote
single-line fragments — longest newline-free run in a real verified span: 33 characters — which
an adversarial reviewer then found overreaching). **D2 and D4 in S5**, because S5's review cites
quotes whose rung a reader of the promotion report cannot currently see, and because a cross-page
sentence today fails with the wrong reason. **D3 after S5**, refereed on the 35 rows.
Counters: D1/D4/D5 protect S5's `claims_ungraded=0` and `K1=PASS`; D2 adds `match_rung` to every
VERIFIED line the S6 synthesis inherits.

---

### 1.5 Record: numbers and table cells (L8)

#### litkb today

**litkb already extracts and stores cell-level table provenance and cannot use a byte of it.**
`litkb.table_cells` (`0017_extraction.sql:61-73`) holds `block_id, row_idx, col_idx, row_span,
col_span, text, bbox, column_header, row_header`; it is filled from Docling's TableFormer by
`extract/docling.py:346-372` through `extract/ingest.py:219-227`. Measured by L8 on the live base
as `litkb_reader`: **3,408 table blocks** (894 on current runs), **230,329 cells**, **100% with a
bbox**, and **127,180 cells (55.2%) whose entire text is a number**.

But `extract/reconcile.py:747-759` sets a table block's `text` to `""` **on purpose** ("nothing
renders a table to text here"), and `SELECT count(*) FILTER (WHERE text='') … WHERE type='table'`
returns **3,408 of 3,408**. Three stoppers follow:

1. `use.locate_quote` (`use.py:190-195`) tests `position(quote in canonical(b.text)) > 0` and
   `''` can never match.
2. The verify trigger (`0026:121-126`) raises 23514 for any `char_end > length('')=0`, and
   `use_evidence`'s `CHECK (char_end > char_start)` forbids 0 — **so no legal evidence row can
   anchor to a table.**
3. `mcp/server.py:349` lists `"table"` in `DEFAULT_KINDS` while every search leg runs over
   `blocks.text` — tables are **advertised and unreachable, with no refusal saying so**.

Three more gaps bite specifically on numbers: the table caption is parsed (`docling.py:371`) and
dropped at `ingest.py:220`, so `tables.caption_block_id` is NULL for all 3,408 and no table can
be named "Table 3"; **1,723 tables (50.6%)** have span-aware grid holes and **296 hold zero
cells**, with `confidence` stored as the constant **0.8** for every one; and **269 of the 894
current-run table blocks (30.1%)** contain the same decimal string in more than one cell — worst
case `'0.0'` **127 times** — so an address-free numeric quote is ambiguous **as the normal case**.

And the grader would reject it anyway: `review_check.py:124` sets `MIN_QUOTE_CHARS=25` because a
1–4 character quote is a substring of almost every span (:432-441), and `"0.87"` is four
characters.

The demand is already measured: `review_check.py:274-277` records a four-row findings table that
passed K1 with **no citation anywhere**. And **367 of 460** rows in
`Reports/literature_tracker.csv` carry a number in their Relevance sentence, including row 33's
`"87.1% OA, F1=83.1%"` — a quoted pair on an unread row that nothing in litkb could confirm or
refute today.

#### Strongest external mechanisms

| mechanism | repo @ sha · symbol | licence | status |
|---|---|---|---|
| TableFormer → `TableCell` with page-coordinate `bbox`, `start_row/col_offset_idx`, `row_span/col_span`, `column_header`; plus `otsl_seq` structure tokens and the `do_cell_matching` switch | `docling` @ `35c6af53` · `models/stages/table_structure/table_structure_model.py:238-300` | MIT | VERIFIED code / licence ASSERTED |
| **NEGATIVE:** TEDS compares cell content by **normalised Levenshtein**, so `0.87` vs `0.37` still scores ~0.75 — the field's standard metric tolerates exactly the failure litkb must refuse | `PubTabNet` @ `8ffde90` · `src/metric.py:39-59` | **Apache-2.0 (read in the file header)** | VERIFIED |
| `Quantity(value, unit, surface, span, uncertainty)` whose `__eq__` requires value AND unit AND surface AND span — surface+span verified, value+unit derived | `quantulum3` @ `29d61e4` · `classes.py:226-280` | MIT | VERIFIED code / licence ASSERTED |
| **NEGATIVE:** every value comparison pint offers is tolerant and dimensional (`rtol`/`atol`) — a consistency check, never an identity check | `pint` @ `e4042bb` · `pint/testing.py:26-45, 95-162` | BSD-3 | VERIFIED |
| answers carry a separate `scale ∈ {"", thousand, million, billion, percent}`; `add_percent_pred` exists to reconcile `0.2342` against `23.42 percent` — **the cell string is not the value** | `TAT-QA` @ `870accc` · `tatqa_metric.py:101, 145-206` | MIT | VERIFIED |
| named per-table structural warnings: `excessive rows`, `skipped text`, `lowest iob`, `nms removed rows`, `no text`, `high overlap` | `gmft` @ `ac7ef5e` · `gmft/algorithm/structure.py` | MIT | VERIFIED |
| `parsing_report` = accuracy, whitespace, `confidence = (accuracy/100)*(1-whitespace/100)` | `camelot` @ `a68bb9f` · `camelot/core.py:686-728` | MIT | VERIFIED |
| **NEGATIVE:** PaperQA2's citation unit is a chunk NAME plus an LLM summary with an integer score — no page, no offsets, no cell, no verification | `paper-qa` @ `57e89f7` · `src/paperqa/types.py:155-175, 238-284` | Apache-2.0 | VERIFIED |

#### Recommended change (diff-shaped)

- **Cell-addressed evidence anchor.** `ALTER TABLE litkb.use_evidence ADD COLUMN cell_row
  integer, ADD COLUMN cell_col integer, CHECK ((cell_row IS NULL) = (cell_col IS NULL))`, FK to
  `table_cells(block_id,row_idx,col_idx)`. Existing 35 rows keep NULL and their meaning.
  [VERIFIED]
- **Whole-cell verification branch in `_use_evidence_verify`.** In 0026's trigger, when
  `cell_row IS NOT NULL` compare `litkb.canonical_newlines(tc.text) =
  litkb.canonical_newlines(NEW.quote)` for the **WHOLE cell** and set `char_start=0`,
  `char_end=length(tc.text)`. Block-text branch untouched, so `MIN_QUOTE_CHARS` and the 35
  existing rows are unaffected. **Whole-cell equality at a named address — never a string search,
  never a tolerant numeric comparison.** [VERIFIED]
- **Header path and caption as their own verified rows.** For cell (r,c) additionally record the
  column-header cells covering column c and the row-header/leading cells covering row r as their
  own `use_evidence` rows under the same use version, each verified by the whole-cell rule; and
  fix `ingest.py:220` to write `caption_block_id` from `payload['caption']`. [MIXED]
- **A "numeric evidence" use kind with DERIVED value/unit/scale.** An eighth kind beside the
  seven at `mcp/server.py:1028-1036` (printed from the DB at `brief.py:34-38`), carrying `value`
  (numeric), `unit` (text) and `scale` (TAT-QA's vocabulary), **all three marked in the schema
  comment as DERIVED AND NOT VERIFIED**. [VERIFIED]
- **Make the table reachable — a `locate_quote` cell leg, and an honest refusal until then.**
  (i) add a second leg over `table_cells` returning `{block_id, run_id, page, cell_row,
  cell_col}`; block-text leg untouched. (ii) **Until (i) lands**, either drop `"table"` from
  `DEFAULT_KINDS` or have the refusal at `mcp/server.py:364-367` name it. [VERIFIED]
- **Record the extraction facts a numeric gate needs.** On `litkb.tables` add `otsl_seq text`,
  `cell_matching boolean` and `structure_flags jsonb` (`no_cells`, span-aware `grid_holes`,
  `duplicate_address_dropped` — the count `add_table_cell`'s `ON CONFLICT DO NOTHING`
  (`0017:263`) discards silently). Replace the constant 0.8 with a measurement or NULL.
  `do_cell_matching` decides whether a cell's text is the PDF's own matched words or a re-read of
  a predicted rectangle, and litkb does not record which. [VERIFIED]
- **Numeric counters on `litkb_acceptance`, and do NOT lower `MIN_QUOTE_CHARS`.** Counters read
  from the DATABASE: `numeric_uses`; `numeric_verified` (bound == `numeric_uses`);
  `numeric_header_path_missing` (==0); `numeric_value_disagrees` (==0);
  `numeric_ambiguous_address` (==0). **Do not** lower `MIN_QUOTE_CHARS`, **do not** render tables
  to text (`reconcile.py:747-749` refuses that deliberately and it would restore the string
  ambiguity), **do not** adopt PaperQA2 chunk-name attribution. [VERIFIED]

#### Local test set

- **P1 (REAL positives):** 651 current-run table blocks with at least one whole-number cell
  (`tc.text ~ '^[-+(]?[0-9]+([.,][0-9]+)?\)?[%]?$'` joined on `f.current_run_id=b.run_id`);
  127,180 whole-number cells base-wide.
- **P2 (REAL, the named anchor):** block `01a0abc7-33a2-7692-a442-77b8f5b032f6`, p.18, work
  `Brown_2022_automated-aerial-animal-detection`, header row
  `GSD (m/px) | Q | F1 | Mean Abs Count Error | …`, holding **two cells reading `0.87`** and with
  TableFormer marking **no row header anywhere in it**. Its prior-run twin
  `01a0aa24-41cd-765b-99b6-6ff67373f844` has its two `0.87` cells at (3,2) and (18,2).
- **N3 (REAL negatives):** the **269** current-run table blocks holding the same decimal in more
  than one cell, worst `0.0` × 127 in `01a0abc7-d08f-7f89-affb-40dd66270242` p.9; 14,360
  internally-duplicated (table, whole-cell numeric) pairs base-wide.
- **N4 (REAL negatives):** 296 zero-cell tables; 1,723 of 3,408 (50.6%) with span-aware grid
  holes; 8 with overfill. Plus 1,948 current-run caption blocks containing a digit and 9,396
  current-run reference blocks containing a digit — **none may ever verify as table evidence**.
- **The tracker set (REAL):** 367 of 460 rows carry a number in "Relevance (max 3 sentences)";
  row 33 (Wagner 2025, `10.1016/j.rse.2025.114632`) quotes `87.1% OA, F1=83.1%` at
  `Status='To Read'`.
- **CONSTRUCTED:** C1 = each P1 cell with one digit changed; C2 = a cross-cell address swap built
  from real N3 rows.

#### Kill criteria

- **Anchor:** an evidence row whose `(block_id, cell_row, cell_col)` names no `table_cells` row
  must be REFUSED by the foreign key. Demonstrate on a real block id with `cell_row=9999` before
  calling it a gate.
- **Verification — three must turn red:** (a) quote `0.37` against the cell holding `0.87` →
  `quote_verified` false; (b) quote `0.87` against the OTHER `0.87` cell's address in block
  `01a0abc7-33a2-7692-a442-77b8f5b032f6` verifies only for the address it came from; (c) quote
  `0.8` against a cell holding `0.87` → false (**whole-cell equality, not `position()`**).
- **Header path — the criterion that fires on real data as the base stands:** the P2 block must
  FAIL completeness today, because TableFormer marked no row header there. A table whose numbers
  cannot be addressed by a header path is a table whose numbers are not evidence. (Globally:
  12,107 of 230,329 cells (5.3%) carry `row_header`.)
- **Numeric kind:** a row whose `value` does not re-parse from its own verified surface (surface
  `0.87`, value 87) must move a new `numeric_value_disagrees` counter off zero. Mutation-test it
  the way `qc/claims.py` was.
- **Reachability:** `litkb_search` for `Mean Abs Count Error` must return the P2 table block.
  **Today it returns nothing — that silence is the known-bad the gate must flip.**
- **Structure flags:** all 296 zero-cell tables must carry `no_cells=true` and be refused as an
  evidence source; a numeric use against any of them must be held.
- **Counters:** with one C1 mutant and one C2 swap in the run, if every counter still reads zero
  the instrument is not a gate.

#### Where it lands

This stage is **after S5**, as an improvements-table line of its own, with one exception: **the
honest refusal** (drop `"table"` from `DEFAULT_KINDS`, or name it in the refusal) is a one-line
truth-in-advertising fix that should land before S5, because an S5 scout told a table block
exists and then refused at record time burns turns for no reason. The rest is a schema change
plus a trigger branch and must be refereed. If it lands, it adds `numeric_*` counters to S6's (b)
beside `unsupported_attributions=0`, because a synthesis is where a wrong number does the damage
— and L6's own magnitude rule (§1.7) is the same mechanism one layer up.

---

### 1.6 Brief → review, and its graders K1 and K2 (L3)

#### litkb today

The brief is `pipeline/litkb/brief.py`: `expected_lines()` (:70) reads ONLY
`litkb.hunt_request_status` and `verified_lines()` ONLY `litkb.use_evidence_status`, with a test
scanning both bodies so neither can name the other's tables (:23-25), and
`_require_every_hunt_request` (:91) refusing a brief that dropped an expectation. The writer
(`.claude/agents/review-writer.md`) gets `litkb_brief` and nothing else and holds no Bash tool,
because the proposer never scores its own proposal.

**K1** is `review_check.py::check` (:835): five per-citation guards (`_location`:351,
`_verbatim`:371, `_in_brief`:387, `_verified_span`:399, `_quote_length`:432) and nine document
guards, enforced per SENTENCE via `_SENTENCE_SPLIT` (:108), with verbatim-ness decided by
Postgres under the same `litkb.canonical_newlines` the migration-0026 verify trigger uses at
record time.

**K2** is `review_context.py::build` (:96) writing the whole block behind every citation and
exiting 1 on BLOCK NOT VISIBLE, `docs/LITKB_CODEX_PROMPT.md` naming four overreach classes
(magnitude, causation, comparison, antecedent), and `litkb_acceptance.py::check_codex` (:1448)
with four gate counters plus a `--mutate N` kill (`mutate_review`, :1388) that plants a causation
while a guard at :1428 refuses any rewrite that moved one byte of any quote.

The plan's stated pain is `LITKB_WORKPLAN.md:889` — "overreach is the K1 escape no deterministic
grader closes" — and :1077 carries "run-2 review fails the tightened grader" into S5. **But
measured on the real artifacts by L3, the pain is sharper:** K2 returned **13/13 SUPPORTED** on
the run-2 review and found **4 EDITORIAL defects** — and every defect K2 actually found was
**outside the per-citation loop**: in a title, in Scope, and in an incomplete disclosure.

#### Strongest external mechanisms

| mechanism | repo @ sha · symbol | licence | status |
|---|---|---|---|
| **Deterministic** numeric/date containment: a decomposed fact introducing a numeric entity absent from its source sentence is discarded; the numeric half is one regex `r'\b\d+\b'` | `shmsw25/FActScore` @ `f28272de` · `factscore/atomic_facts.py::postprocess_atomic_facts`, `extract_numeric_values` | MIT | VERIFIED |
| Citation **precision** by leave-one-out: for a jointly-entailed multi-cited sentence, drop each cited doc and re-test; a doc whose removal changes nothing is `sent_mcite_overcite` | `princeton-nlp/ALCE` @ `246c476` · `eval.py::compute_autoais` | MIT | VERIFIED |
| Four-level **claim-strength** taxonomy with a labelled corpus: `label_name = {0:'none',1:'causal',2:'cond',3:'corr'}`, 3,061 PubMed conclusion sentences, BioBERT, 0.88 macro-F1 | `junwang4/causal-language-use-in-science` @ `84abecc` · `main.py`, `data/pubmed_causal_language_use.csv` | **not stated** | VERIFIED (labels + data header) |
| `CANNOT_ANSWER_PHRASE = "I cannot answer"` as a first-class named output; per-context `relevance_score` 0–10 | `Future-House/paper-qa` @ `57e89f7` · `src/paperqa/prompts.py` | Apache-2.0 (ASSERTED) | VERIFIED (prompts) |
| Sentence-level claim↔document entailment returning a per-chunk probability, max over chunks, threshold 0.5; `flan-t5-large` 770M, local | `Liyan06/MiniCheck` @ `b58b9fa` · `minicheck/minicheck.py::MiniCheck.score` | Apache-2.0 (7B checkpoint separately restricted) | VERIFIED code / ASSERTED numbers |
| **Why decomposition cannot go in K1:** both implementations decompose with an LLM — FActScore's 7-demo few-shot prompt plus a BM25-retrieved demo, and RAGAS's `StatementGeneratorPrompt` | `explodinggradients/ragas` @ `298b682` · `_faithfulness.py` | Apache-2.0 | VERIFIED |
| **WARNING:** citations inserted POST HOC into finished prose with no verification — only a 0.9 length-ratio gate | `AkariAsai/OpenScholar` @ `0e9b8fb` · `insert_attributions_posthoc_paragraph_all` | not opened | VERIFIED |
| **WARNING:** `[k]` citation format is an LLM instruction in a docstring; nothing in the file checks it | `stanford-oval/storm` @ `fb951af` · `article_generation.py::WriteSection` | not opened | VERIFIED |
| supporting / contrasting / **mentioning** — rhetorical function, explicitly not sentiment; creators report 92.6% mentioning | scite.ai help documentation | proprietary | ASSERTED |

**The single most important negative finding (L3):** *nothing surveyed has anything like litkb's
expectation accounting.* PaperQA2, OpenScholar, STORM and LitLLM all grade what the review said
against what it retrieved; **none grades what the run expected BEFORE reading against what came
back.** `LITKB_REVIEW_GRAMMAR.md` §5 has no upstream to copy from.

**The second (L3):** *litkb's K1 is already stricter than every citation-grounded writer read.*
Only litkb refuses a citation at write time on a byte-exact substring test against a verified
span. There is nothing to import into K1's existing guards — only new guards to add beside them.

#### Recommended change (diff-shaped)

- **R1 — numeric containment in K1 (`magnitude-not-in-quote`, severity FAIL).** Add
  `_magnitude_findings(c, text)` in `review_check.py` beside `_quote_length_findings`:432, called
  from `check()` at :872. Take the sentence region before the quote's opening delimiter — factor
  the existing walk out of `litkb_acceptance.py:1409-1420` so the guard and the mutator share one
  definition — and flag any digit token in the region absent from `c['quote']`. **Digits only.**
  New code in `LITKB_REVIEW_GRAMMAR.md` §4 + §8 list; mutation row RC28 in
  `qc/instruments/litkb_p2_mutations.py`; test in `qc/test_litkb_review_check.py`. [VERIFIED]
- **R2 — causal-cue asymmetry in K1 (`causal-cue-not-in-quote`, severity NOTICE ONLY).** Same
  module and call site: flag when the sentence region matches a causal connective and the quote
  matches none. **Lexicon authored locally** — `main.py` contains NO cue list (confirmed by
  reading it), so the cue words must not be copied from a search summary. [MIXED]
- **R3 — cited work with no drop-off behind it (`citation-outside-this-hunt`, severity notice).**
  `check()` already holds `expected` from `_brief.build` at :869, and each EXPECTED line carries
  `work_key` (`brief.py:82-87`). Build `{e['work_key'] for e in expected if e['work_key']}` and
  emit a notice per cited key outside it. Notice, not fail: citing an inherited promoted quote is
  legitimate per §7; what is wrong is that it is **invisible**. [VERIFIED]
- **R4 — K2 rubric: name the overreach classes, add the missing middle.** Edit
  `docs/LITKB_CODEX_PROMPT.md`: split `causation` into `causation` and **`hedge-stripped`**; add
  `over-citation` (ALCE condition B); add `scope-transfer` for a heading or summary granting a
  status the cited body does not. These are `reason` vocabulary, **NOT new enum values** — the
  three verdicts stay SUPPORTED/OVERREACH/UNSUPPORTED, because `CODEX_VERDICTS` and `codex_ok`
  are built around three. [MIXED]
- **R5 — strengthen the `--mutate` harness: the planted causation is too easy to see.** Rule 2
  currently produces `"Because of this, Measured against a baseline…"` — a capital mid-sentence
  and a dangling connective — and Codex's own reason names the marker. Add rule 3: rewrite a
  reporting verb to a causal one (`"is reduced by"` → `"is reduced because of"`, `"follows"` →
  `"results from"`) from a small fixed table, keeping every rule deterministic and idempotent and
  keeping the quote-identity guard at :1428. [ASSERTED]
- **R6 — MiniCheck as a third, numeric, NEVER-gating signal under K2.** New
  `qc/instruments/litkb_entail_probe.py`: per citation, `score(docs=[the whole block from
  review_context], claims=[the sentence])` and print the probability beside Codex's verdict.
  Never a gate, never a replacement for K2. [MIXED]
- **R7 — grammar: a named "the brief does not answer this" form.** Edit
  `LITKB_REVIEW_GRAMMAR.md` §5 and `.claude/agents/review-writer.md`. The writer today is told
  only a prohibition with no positive form, so it omits silently. Give "Expectations not
  supported" a second permitted entry kind: a question the brief holds no verified quote for,
  named as such. Non-claim text, so K1 already refuses a citation there. [ASSERTED]

#### Local test set

- **REAL:** `Reports/reviews/label-noise-robustness-2026-09-20.md` (12 citations) and
  `-run2.md` (13 citations); `Reports/codex/…run2.codex.json` (13/13 SUPPORTED, 4 editorial
  defects, one of them the 8-word title "Canopy reference products and imagery that spans
  dates"); `Reports/codex/label-noise-robustness-2026-09-20-run2.mutated-5.md` and its report
  (n=5 OVERREACH, reason quotes "Because of this").
- **REAL (live DB):** the run-2 review cites 4 works (Benedek_2015, Girard_2019, Kaiser_2017,
  MacFaden_2012) while workstream `01a0bf4b-6844-7507-963c-9fdb66c58c68` holds 4 drop-offs
  linking only Kaiser, MacFaden and Benedek. **`Girard_2019_noisy-supervision-correcting-misaligned`
  is cited with no drop-off behind it, disclosed only in Scope — the one section K1 cannot look
  inside.**
- **CONSTRUCTED C1:** run-2 line 31 `"7 percent points, to 0.837"` → `"12 percent points, to
  0.941"`, every citation and quote byte-identical (verified by comparing `review_check.citations()`
  tuples: True).
- **Not constructible today:** a citation to another workstream's promoted quote — the live
  database holds **0 promoted uses**.

#### What L3 measured with that test set (L3's own numbers, unrefereed)

- **R1 fires 0/25 on the real corpus** (run-1's 12 + run-2's 13) and **fires on C1** at n=5 with
  `missing_nums=['0.941','12']`. That closes the `magnitude` overreach class — one of the four K2
  carries by judgement — **with no model**. The spelled-out-number extension is NOT free:
  'one'/'two'/'three' give 2 false positives on run-1.
- **R2 is UNDETERMINED as a gate, measured.** It fires on the planted causation (mutated-5, n=5)
  but also on **4 honest real sentences out of 25**: "their automated approach produced" (a past
  participle), two "because" clauses inside the reported comparison, and "due to seasonal
  changes" quoting the source's own framing. **1 true against 4 false is inside the noise
  (CLAUDE.md §3.5)**, so it ships as `severity: notice` or not at all.
- **The `--mutate` kill is weaker than its 1/1 detection rate suggests:** a naive regex catches
  the identical mutation, so the gate currently measures whether Codex can see an explicit
  connective, not whether it can see an overreach.
- **Every number here is the PROPOSER's own.** Under §3.4c, 0/25 and 4/25 do not count until an
  agent that did not propose them re-runs the probe on `Reports/reviews/*.md` and the mutated
  files and reproduces them.

#### Kill criteria

- **R1:** C1 must produce exactly one `magnitude-not-in-quote` at citation 5, AND the same
  command on the unmutated run-1 and run-2 must produce **zero**. **Both halves required** — a
  guard that fires on the real corpus gets turned off.
- **R2:** mutated-5 must produce the notice at citation 5 (measured: it does). **The notice count
  on run-1 must be printed, not suppressed: it is 3, all false.**
- **R3:** the REAL run-2 review must produce exactly one notice, naming
  `Girard_2019_noisy-supervision-correcting-misaligned`; a review citing only
  Kaiser/MacFaden/Benedek must produce zero.
- **R4:** the hedge-stripping mutation must come back non-SUPPORTED. **But measured: NO sentence
  in either real review carries a hedge to strip**, so this gate's input is constructed-only —
  per §3.4c it is therefore **UNVALIDATED and must say so in those words** until a review that
  hedges exists.
- **R5:** the stronger mutation must (a) still pass the byte-identical quote guard and (b) come
  back non-SUPPORTED. **If it comes back SUPPORTED, that IS the measurement of K2's sensitivity
  and must be recorded — never tuned away by weakening the mutation.**
- **R6:** on mutated-5 the probe must be reported whatever it says, and the docstring must state
  the expected result **in advance**: the planted causation will likely score supported. If it
  does, that is the documented proof MiniCheck cannot replace K2.
- **R7:** the constructed brief, written up, must produce a review whose "Expectations not
  supported" names the unanswered question. **CONSTRUCTED-only, therefore UNVALIDATED.**

#### Where it lands

**R1 and R3 in S5**, both cheap and both deterministic: R1 adds `magnitude_not_in_quote` to S5's
(b) beside `claims_ungraded=0` and closes one of the four classes S5's (c) currently hands
entirely to Codex; R3 makes the "citation to a work outside this hunt" hole visible, and the hole
is **already in the corpus**. **R4 and R5 in S5 too**, because S5's (c) requires K2 to fire on a
planted causation and R5 is the finding that the current plant is signposted. **R2 ships as a
notice or not at all** (UNDETERMINED per §3.5). **R6 and R7 after S5.** R7's positive form also
feeds S6, where "the brief does not answer this" is the honest branch of an UNDETERMINED
recommendation (§1.7).

**What L3 says NOT to do:** atomic-claim decomposition cannot go into K1 — both implementations
that exist decompose with an LLM, and a deterministic grader that calls a model stops being
deterministic, which is K1's whole value. Decomposition belongs on K2's side of the line.

---

### 1.7 Synthesis and K3 (L6)

#### litkb today

**S6 is genuinely unbuilt, and that is measured, not assumed.**
`grep -rn "synthesis" pipeline/litkb/ --include=*.py` returns nothing;
`qc/instruments/litkb_acceptance.py` declares eight subcommands at :1838-1925 (plan, disposition,
guard-checkout, scout, first-work, edges, codex, preflight) and **no `synthesis`**;
`pipeline/litkb/commands.py:691-933` registers every CLI verb and has review-check/review-context
but no synthesis-check; `Reports/syntheses/` and `docs/LITKB_SYNTHESIS_GRAMMAR.md` do not exist.

What exists is the stage below it, fully built and proven: the citation token at
`review_check.py:90`, the per-SENTENCE unit at :108/:266/:321, byte-exact verbatim checking in
Postgres at :371/:777, verified-span containment at :399, `MIN_QUOTE_CHARS=25` at :124, the
six-word heading label rule at :128/:489/:518, K2's first half at :705, and the Codex adversarial
read.

**The measured pain for S6 is therefore ZERO** — no synthesis has been written, so there is no
defect rate, and every recommendation below is a design against the risk the plan names at
`LITKB_WORKPLAN.md:945-947`.

**But one live mechanism makes the first laundering mode real and DECAYING.** `brief.py:118-121`
admits `AND (wu.workstream_id = %(ws)s OR wu.state = 'promoted')`, so the brief's VERIFIED lines
are this workstream's own uses **OR every promoted use in the database hunted by anyone**. On the
live DB today every promotable evidence row is `state='proposed'` (35 `use_evidence` rows, all
`quote_verified`, spread over four workstreams), so `not-in-brief` **happens to** refuse a
cross-workstream citation — a coincidence of the merge state, not a gate. **The first promotion
Kam merges turns those blocks into legitimate brief lines, `not-in-brief` goes quiet, and the
plan's S6 (c) kill criterion stops firing without anyone touching a line of code.**

#### Strongest external mechanisms

| mechanism | repo @ sha · symbol | licence | status |
|---|---|---|---|
| verbatim-quote verification + a **pure-function deterministic verdict algorithm**; "No information is not silently upgraded… a needed NI leaves the domain null and records which questions were missing"; `softFail` is opt-in, threshold-declared, never converts a strong verdict, flags every row it touches | `YT1313/sciente-evidence-evals` @ `28f5cd3b` · `rob2/algorithm.ts`, `verify/support.ts` | Apache-2.0 (LICENSE first lines) | VERIFIED |
| "an explicit contradiction in the numbers overrides the cues, because a counted proportion is not a matter of phrasing"; known-bad test: "does not let a dropped confidence interval pass as exact"; `MIN_EXCERPT_LENGTH = 24` (independently derived, against litkb's 25) | same · `verify/support.ts` | Apache-2.0 | VERIFIED |
| citation **precision** by leave-one-out (`sent_mcite_overcite`); `at_most_citations` default **3**; an out-of-range citation scores 0 deterministically | `princeton-nlp/ALCE` @ `246c476a` · `eval.py` | MIT | VERIFIED |
| `<statement>…<cite>[a-b]</cite></statement>` with an **explicit EMPTY `<cite>`** for an uncited statement, never silence; `assert c['content'] == context[st:ed]` before writing; `merged_citations[:3]` | `THUDM/LongCite` @ `d7d772e3` · `CoF/4_postprocess_and_filter.py`, `LongBench-Cite/auto_scorer.py` | Apache-2.0 | VERIFIED |
| `[LLM MEMORY \| 2024]` as a **first-class citation token** rendered `<Model name=… version=…>`; a section with no refs labelled "(LLM Memory)" | `allenai/ai2-scholarqa-lib` @ `a9623287` · `postprocess/json_output_utils.py` | Apache-2.0 | VERIFIED |
| **THE FAILURE MODE K3 MUST AVOID, SHIPPED IN PRODUCTION:** on a citation its quote store cannot account for, `curr_section["text"].replace(ref, "")` plus a log warning — it **strips the citation and KEEPS the sentence**, producing a silent uncited assertion. Its quotes are whatever the LLM emitted (`len(quote) > 10`), never checked against the paper | same repo · same file, `rag/multi_step_qa_pipeline.py::step_select_quotes` | Apache-2.0 | VERIFIED |
| rationale = a set of sentence indices; `MAX_ABSTRACT_SENTS` hard cap; `is_correct` scores label and rationale **JOINTLY** — a right verdict on wrong evidence is not correct | `allenai/scifact` @ `68b98a56` · `verisci/evaluate/lib/metrics.py` | CC BY 4.0 / ODC-By 1.0; code in LICENSE.md | VERIFIED |
| `label_probs_truncated[:, nei_label] = label_threshold` — the NOT-ENOUGH-INFO class gets a **floor**, so a substantive verdict wins only by clearing it | `dwadden/multivers` @ `a6ce033f` · `multivers/model.py` | MIT | VERIFIED |
| every judgement ships with `annotations = {content, position (start_char), prefix, suffix}` | `ijmarshall/robotreviewer` @ `9a278197` · `robots/bias_robot.py` | **LICENSE 404 at the sha — licence UNVERIFIED** | VERIFIED (mechanism) |
| content hash embedded in the identifier (`"FA" + base64(sha256(content))`); verification = recompute; the published evaluation corrupts one random byte per file and requires validation to fail | `trustyuri/trustyuri-python` @ `9f29732c` · `trustyuri/file/FileHasher.py` | not read | VERIFIED (mechanism) |
| entity types `association, factor, evidence, **epistemic**, magnitude, qualifier`; attributes `causation, comparison, correlation` | `siftech/SciClaim` @ `830fa82e` · `types.json` | **LICENSE 404 at the sha** | VERIFIED (schema) |
| three-way attribution label **Attributable / Extrapolatory / Contradictory** — "the source is silent" separated from "the source disagrees" | `OSU-NLP-Group/AttrScore` @ `adbd919d` | MIT | ASSERTED (README) |
| GRADE certainty is rated DOWN automatically, never up | `ykfrkw/pmatools` | not read, no sha | ASSERTED |

#### Recommended change (diff-shaped)

- **R1 — the laundering gate reads the WORKSTREAM'S LEDGER, not the brief.** New
  `pipeline/litkb/synthesis_check.py` must NOT build its citation whitelist from `brief.build()`.
  K3 runs the same query **with the `OR wu.state = 'promoted'` disjunct removed**
  (`wu.workstream_id = ws` only). New finding code `laundered-citation`, counter
  `laundered_citations`, whose detail names the workstream that DOES hold the block. Leave
  `brief.py` alone (`LITKB_REVIEW_GRAMMAR.md` §7 permits it for K1 deliberately) and record the
  divergence in the new grammar doc. [VERIFIED]
- **R2 — `[own reasoning]` as a typed token, and the hole it opens.** Import
  `review_check.units` (:266) and `review_check.sentences` (:321) rather than re-deriving them
  (one splitter, one unit definition; the `et al.` hazard is inherited for free). Every
  claim-section sentence ends in a citation token or `[own reasoning]`; counters
  `sentences_ungraded` and `unlabelled_inferences`. **Add to the new grammar's "What K3 does NOT
  check" as entry #1: a factual literature claim written as `[own reasoning]` is the same escape
  as moving a claim into Scope, and no counter sees it.** Extend `docs/LITKB_CODEX_PROMPT.md`
  with a third question and the schema with an `own_reasoning` array; count `overtagged` as a
  finding the orchestrator rules on. [VERIFIED]
- **R3 — numeric agreement: the one support check writable in code.** For every sentence ending
  in a `[work_key p.N #block]` token, extract numeric literals (excluding the citation's own
  `p.N`) and require each to appear in the cited quote. **Numbers only — no lexicon, no NLI.**
  Scope stated narrowly: percentages, decimals, integers ≥2 digits; per-clause opt-out by tagging
  `[own reasoning]`. Counter `magnitude_not_in_quote`. [VERIFIED]
- **R4 — citation cap and an overcite notice.** `MAX_CITATIONS_PER_SENTENCE = 3`, a **FAIL not a
  truncation** (SciFact truncates because it scores a benchmark; litkb gates a document, and a
  silently truncated citation list is a citation nobody graded). Counter `citations_over_cap`.
  Second half, notice severity: a multi-citation sentence where the Codex report marks any one
  citation UNSUPPORTED is an overcite — counter `overcited_sentences`. **litkb has no precision
  notion at all today:** `review_check` passes a sentence carrying four citations if one
  verifies. [VERIFIED]
- **R5 — UNDETERMINED recommendations that name their gap.** The closing recommendations section
  is a TABLE (already units under `review_check.units:266`), one row per recommendation:
  `decision_id` (a `decisions.yaml` id or NEW), `verdict` from a closed set **including
  UNDETERMINED**, `lines` (≥1 verified citation token), and `missing` (required when
  UNDETERMINED). **A recommendation whose evidence is absent may not be written as a weaker
  recommendation — CLAUDE.md §3.5 in code.** Counters `recommendations_without_lines`,
  `undetermined_without_gap`. [VERIFIED]
- **R6 — two more locator namespaces, resolvable by code.** The synthesis cites `SCIENCE.md` and
  `decisions.yaml` as well as blocks (`LITKB_WORKPLAN.md:932-933`), and `review_check.CITATION_RE`
  (:90) cannot name either. Add exactly two tokens: `[SCIENCE.md §n "<evidence pointer>"]`
  resolved against the pointer strings SCIENCE.md already prints beside every number, and
  decisions by stable kebab `id` (uniqueness already enforced by `qc/test_decisions.py`). **Cite
  the POINTER, never the prose — the prose is regenerated.** Counter `unresolvable_locators`.
  [VERIFIED]
- **R7 — findings bound to source hashes, by extending `review_context`.** The synthesis header
  comment carries, beside `workstream=`, the sha256 of the brief it was written from and of
  `SCIENCE.md` at the time. **Reuse `review_context.sha256_file`; do not write a second
  definition.** `litkb_acceptance.py synthesis` recomputes both and counts `hash_mismatch`,
  exactly as `cmd_codex` already does. [MIXED]
- **R8 — do NOT invent a certainty vocabulary; `epistemic` is what is missing.** litkb already
  has `stance` ('supports','refutes','context', `0002_text.sql:120`) and `kind` (seven values,
  `0001_core.sql:295`), and `brief.py`'s docstring already forbids remapping them — a GRADE-style
  tag would be the second taxonomy §3.3 forbids. What IS missing is SciClaim's `epistemic`
  ("hypothesized / demonstrated / showed / predicted"), because the same quote supports only one
  of those readings. **Add it as a Codex-stage question, not a deterministic counter.** [MIXED]

#### Local test set

- **THE HARDEST NEGATIVE NEEDS NO CONSTRUCTION.** Measured read-only by L6 on 2026-09-22:
  `proving-run-label-noise` and `proving-run-2-label-noise` each hold **8 distinct verified
  (block, work, page) triples**, of which **4 are run-1-only and 4 are run-2-only, 4 shared**. A
  run-2 synthesis citing `01a0abc6-ecbc-73e1-b932-ccfffffba295` (Benedek_2015 p.12) is the plan's
  laundering case built from rows that exist. Others named:
  `01a0abcc-65d9-797b-bf46-9d81da34b9ef` (Girard_2019 p.1),
  `01a0abc9-8062-77f9-bd0a-95e0130c0076` (MacFaden_2012 p.18). Further negatives: `first-work-1`'s
  2 and `improve-review-1`'s 2. **Positives = run-2's own 8 triples.**
- **THE EXPECTED-LINE-CITED NEGATIVE CANNOT COME FROM THE PROVING RUNS.** Per-workstream
  `hunt_request_status` census: `proving-run-2-label-noise` holds 4 hunt_requests and **ZERO with
  an `abstract_passage` of quotable length (≥25 chars)**; same for run 1. Real passages exist only
  in `first-work-1` (4), `scout-1` (9) and `scout-2026-09-20` (9). **Either the test declares one
  of those workstreams or the passage is CONSTRUCTED and labelled so — the plan's fixture sketch
  does not anticipate this.**
- **CONSTRUCTED fixtures** under `qc/testdata/litkb_synthesis/`: `good.md` (built over the 8 real
  run-2 triples and real `decisions.yaml` ids — `synthesis-session`, `k4-signoff`, `k1-labelling`
  exist today), `untagged.md` (= good.md with one `[own reasoning]` removed), `magnitude.md` (a
  real verified quote's figure altered in the sentence, quote byte-identical), `overcited.md`
  (4 citations on one sentence).
- **REAL for R6:** SCIENCE.md's own pointer lines (:12-13 onward, ~18 numbered findings) and
  `decisions.yaml`'s open ids. Negatives constructed by altering one character of a pointer.

#### Kill criteria

- **R1:** cite a run-1-only block from a synthesis declaring `proving-run-2-label-noise` →
  `laundered_citations=1`, **and the test asserts the CODE `laundered-citation`, not the exit
  status** — today every promotable row is `state='proposed'`, so `not-in-brief` reddens the same
  document for the wrong reason and the gate would look proven when it is not. Second mutation:
  restore the promoted disjunct, apply a promotion on a worker DB, re-run — the row must still be
  refused.
- **R2:** drop one `[own reasoning]` → `unlabelled_inferences=1` (deterministic). Mutation on the
  guard: make the tag optional → the fixture must go green. **Over-tagging is explicitly NOT
  deterministically detectable** and is named as the Codex stage's job via a `--mutate` row
  requiring `mutation_not_flagged`.
- **R3:** the sciente test transplanted — a sentence says a number the byte-identical quote does
  not carry → `magnitude_not_in_quote=1`. Must be shown to fire before the counter is trusted
  (an RC-series row in `qc/instruments/litkb_p2_mutations.py`).
- **R4:** a fixture sentence with four citations → `citations_over_cap=1` (fail). A fixture
  sentence with two citations, one of which the Codex report marks UNSUPPORTED →
  `overcited_sentences=1` (notice, **never** a fail).
- **R5:** a row with `verdict=UNDETERMINED` and an empty `missing` → `undetermined_without_gap=1`.
  A row with a verdict and no `lines` → `recommendations_without_lines=1`.
- **R6:** alter one character of a SCIENCE.md evidence pointer in the fixture →
  `unresolvable_locators=1`. Rename a cited decision id → red.
- **R7:** edit one byte of the brief (or regenerate SCIENCE.md) and re-run without rewriting the
  header → `hash_mismatch=1`. **This is the trustyuri corrupted-copy test.**
- **R8:** not a gate. The deterministic half is that any certainty word in a claim sentence must
  come from the stance/kind the cited VERIFIED line carries; the known-bad is a sentence asserting
  "demonstrated" over a line whose `kind` is 'context'.

#### Where it lands

**All of §1.7 is S6**, and R1–R5 map directly onto S6's (b), which today reads
`sentences_ungraded=0 unlabelled_inferences=0 expected_lines_cited=0 unsupported_attributions=0`.
R1 adds `laundered_citations=0`; R3 adds `magnitude_not_in_quote=0`; R4 adds
`citations_over_cap=0` and prints `overcited_sentences` unbounded; R5 adds
`recommendations_without_lines=0 undetermined_without_gap=0`; R6 adds `unresolvable_locators=0`;
R7 adds `hash_mismatch=0`. **One thing must move earlier than S6:** R1's finding that the plan's
own (c) kill criterion decays the moment a promotion merges is a fact about S5's merge, not about
S6's build — whoever merges the first promotion should know that `not-in-brief` stops covering
cross-workstream citations that day.

**On the record before anyone proposes relaxing anything:** litkb's quote verification is
materially **stronger** than the state of the art in open-source scientific synthesis. ScholarQA's
`step_select_quotes` accepts whatever the LLM emitted with only a `None` filter and
`len(quote) > 10`; nothing checks the quote is in the paper. And `MIN_QUOTE_CHARS = 25` is
independently corroborated by sciente's `MIN_EXCERPT_LENGTH = 24`, derived separately.

---

### 1.8 Promote: the second session, proposals and versions (L9)

#### litkb today

A manual (registry-unconfirmable) admission is written by `litkb.admit()` in proposal mode — the
identity rows exist but `works`/`identifiers`/`files.current_version_id` stay NULL and every
version sits at `state='proposed'` with its head in `ws_heads` — and **exactly one verb** moves
those pointers into main: `litkb.approve_admission`, live definition
`db/migrations/0014_referee_p2_fixes.sql:354-428` (token guard :365-367, route/state guard
:376-379, the D3 lock on the admitter's workstream :380-388, the compare-and-set :403-410),
fronted by `admit/front.py:410-419` and the single CLI verb at `commands.py:206-211/:713/:929`.
The git side is `promote.py` (prepare :95-97, report :112-188, commit with the reachability
refusal :77-92 and :201-211, rebase :217-239).

L9's live measurements (`litkb_reader`, 2026-09-22): **15 manual admissions approved**, **1 still
proposed** (`01a0c730-fa16-7d45-baf8-0fce8c8ad084`, work `Center_2015_ortho-image15c-point-gis`,
workstream `01a0c713-8348-7620-82bc-0f38676bdf0c`), **18 "refused"** — but that word is written
only by `_refuse_admission` inside `admit()` (`0013_admission.sql:215`), so it means the CHECKS
rejected it and **there is no reviewer refusal anywhere**; **486 work_versions promoted and 1
proposed**; **263 of 263 file_versions promoted with `promotion_id IS NULL`**, i.e. **no file has
ever entered main through a promotion** (the open decision `litkb-from-file-version-state`,
`decisions.yaml:874-893`); **2 promotions prepared and 0 committed**; **23 workstreams open and
none merged or abandoned**; 421 uses, all still in `ws_heads`.

Provenance is per version (`work_versions.agent/session_id/workstream_id`, `0001_core.sql:90-109`)
and the only field-level table is `discrepancies` (`0015_discrepancies.sql:15-32`), which records
legacy-vs-registry disagreement rather than **who asserted a field**. The cost is on the record:
`Reports/LITKB_APPROVE_SESSION_2026-09-21b.md` lists three of thirteen works whose author lists
were truncated to one name where the document has six or seven, a truncated title, three
truncated keys, and a work with no identifier — **all promoted as proposed, because the only verb
is all-or-nothing.**

**L9 corrects the brief:** the approve guards are NOT unfired. `qc/test_litkb_p2.py:1129-1157`
fires both the SQL constraint and the Python label guard on a throwaway database, :1174-1188 and
:2139-2154 fire two more. **What has never fired is any guard against a live-shaped row, and no
session report records a fired output.**

#### Strongest external mechanisms

| mechanism | repo @ sha · symbol | licence | status |
|---|---|---|---|
| **The refuse verb, in one method:** `STATUS = {DECLINED: 0, PENDING: 1, MERGED: 2}`; `update_request_status(cls, rid, status, reviewer, comment=None)` — decline is the same verb as accept with a different code, it **requires a reviewer identity**, it carries a comment; `assign_request` reopens a closed request by resetting it to PENDING | `internetarchive/openlibrary` @ `3c3247c` · `openlibrary/core/edits.py` | AGPL-3.0 | VERIFIED |
| **NEGATIVE, and it protects litkb's rule:** `accept_editgroup(conn, editgroup_id)` receives **no editor identity at all**, and `auth.rs::require_editgroup` short-circuits on `if self.has_role(FatcatRole::Admin)` before comparing editors; its only comparison is ownership. **litkb's `admissions_second_session_signs_off` is stricter than the largest open bibliographic database** — do not weaken it by analogy | `internetarchive/fatcat` @ `8f3f4c6` · `rust/src/editing.rs`, `rust/src/auth.rs` | NOASSERTION | VERIFIED |
| deletion is "by pointing the identifier to no revision at all"; merge is a redirect; accepting appends a row to "an immutable, append-only table" | fatcat · `guide/src/data_model.md`, `rust/migrations/.../up.sql` | NOASSERTION | VERIFIED |
| a snapshot per change with `has_generation_time` / `has_invalidation_time` / `derives_from` / `has_primary_source` / `has_resp_agent`, plus `cur_snapshot.has_update_action(update_query)` — the **delta**; the RESTORATION case deliberately does not invalidate the previous snapshot | `opencitations/oc_ocdm` @ `3acddb2` · `oc_ocdm/prov/prov_set.py` | NOASSERTION | VERIFIED |
| W3C PROV vocabulary constants (`PROV_DERIVATION`, `PROV_INVALIDATION`, `PROV_ATTRIBUTION`, …) — the names litkb's provenance columns should map onto | `trungdong/prov` @ `6848203` · `src/prov/constants.py` | MIT | VERIFIED |
| per-field change capture for free by hstore subtraction: `changed_fields = (hstore(NEW.*) - row_data) - excluded_cols`. **Critical caveat in its own comments: a TRIGGER cannot see the agent, because SECURITY DEFINER resets the active role** | `2ndQuadrant/audit-trigger` @ `fdc3ade` · `audit.sql` | NOASSERTION | VERIFIED |
| every write carries identity, a free-text `summary` and an optional `baserevid` (optimistic concurrency — litkb's CAS analogue); per-statement **references** are the per-field provenance model | `LeMyst/WikibaseIntegrator` @ `ba901dd` | MIT | VERIFIED |
| frozen events, `next_version = version + 1`, `OriginatorVersionError` unless the incoming version is exactly one past — **which litkb already is**, as `UNIQUE (work_id, version_no)` plus `work_versions_base_rule` | `pyeventsourcing/eventsourcing` @ `575d42c` · `eventsourcing/domain.py` | BSD-3-Clause | VERIFIED |

#### Recommended change (diff-shaped)

- **R1 — `admission_reviews`, an append-only decision log.** NEW migration
  `0029_admission_review.sql`: one table `admission_reviews(admission_id, decision ∈
  approved/declined/reopened, reason NOT NULL non-blank, detail jsonb, workstream_id, agent,
  session_id, created_at)`; **no existing table altered**; **no agent role gets
  INSERT/UPDATE/DELETE** (the 0011 guarded-relation pattern); `approve_admission` gains one
  INSERT; the 15 existing approvals back-fill from `approver_agent`/`approver_session`/
  `approved_at` already on the row. `admissions.state` becomes a mirror of the latest review row,
  the way `identifiers.active` mirrors the pointer via `_refresh_mirrors`. [VERIFIED]
- **R2 — the refuse verb: `decline_admission` + `reopen_admission`.** `approve_admission` with
  the pointer loop deleted: token, open workstream, FOR UPDATE, `route='manual' AND
  state='proposed'` or 55000, the admitter's workstream locked FOR SHARE and open (D3), a review
  row, `state='declined'` — **and NOTHING moves**: `ws_heads` untouched, versions stay proposed,
  `current_version_id` stays NULL, the proposal stays visible to its own workstream through
  `visibility.FILE_JOIN`. `admissions.state` CHECK widened with `'declined'` (**NOT `'refused'`**
  — `0013:215` already owns that word for the machine's check failure);
  `admissions_manual_is_a_proposal` widened in step; new constraint
  `admissions_decliner_is_a_second_session` mirroring `0014:89-90`. `admit/front.py` gains
  `decline()` and `reopen()` with the same `norm_label` pre-check; `commands.py` gains
  `cmd_decline`/`cmd_reopen`. **MCP gains nothing.** [VERIFIED]
- **R3 — `version_field_provenance`, per-field provenance.** NEW table
  `(entity, version_id, field validated against the version table's columns, asserted_by ∈
  crossref/datacite/arxiv/s2/manual/pdf-metadata/pdf-text/operator, evidence jsonb, agent,
  session_id, UNIQUE(entity,version_id,field,asserted_by))`, written by `admit()` and the review
  verbs **from evidence they already compute and currently discard into the `checks` jsonb**, and
  computed INSIDE the SECURITY DEFINER write functions (never in a trigger, per audit-trigger's
  own warning). Does not duplicate `discrepancies`: that records a legacy row disagreeing with the
  registry, this records who asserted a field; the disagreement stays derivable as a join. [VERIFIED]
- **R4 — `withdraw_version`, the reversible decision on a promoted version.** ONE function, no
  schema change: `work_versions.state` / `identifier_versions.state` / `file_versions.state`
  already admit `'rejected'` and `'withdrawn'` (`0001_core.sql:99, :145, :196` ) and **grep over
  every migration shows NOTHING ever writes either word** — the schema has a place to record a
  reversed decision and no verb reaches it. `litkb.withdraw_version(entity, version_id, reason,
  agent, session)` requires the version to be current, CAS-moves `current_version_id` back to
  `based_on_version_id` (or NULL), sets `state='withdrawn'`, calls `_refresh_mirrors`, and logs to
  R1's table. [MIXED]
- **R5 — the operator bind gate (`litkb-from-file-version-state`).** No ruling proposed — the
  decision is Kam's. What L9 supplies is the measured denominator plus the two shapes the external
  work makes cheap once the decision log exists: a **FULL** gate (`attach_file` writes
  `state='proposed'`, a second session approves) or a **LIGHT** gate (the bind stays direct but
  writes a `file_review` row naming the binder, the sha256 of the served bytes and the binding
  ratio, so a later reviewer can `withdraw_version` without a deletion). Both depend on R1 and R4.
  [MIXED]
- **R6 — fire the existing approve guards where it counts.** **No code change.** The second
  session's procedure gains one step before its first real decision: restore the live row set to a
  throwaway database (`litkb_test`), attempt a self-approve, **paste the raised error into the
  session report** — which is exactly what `Reports/LITKB_APPROVE_SESSION_2026-09-21b.md:600-601`
  apologises for not having. [VERIFIED]

#### Local test set

| id | rows | kind |
|---|---|---|
| P1 | the 15 approved manual admissions, with approver identity | REAL |
| P2 | the ONE proposed manual admission a refuse verb must adjudicate — `01a0c730-…`, `Center_2015_ortho-image15c-point-gis`, ws `01a0c713-…` | REAL |
| P3 | the 18 machine-refused manual admissions — a reviewer verb must NOT be able to touch these | REAL negative |
| P4 | 263 of 263 file_versions `state='promoted'` with `promotion_id IS NULL` | REAL |
| P5 | the 914 `discrepancies` rows (609 tracker + 305 manifest) — the existing field-level shape | REAL |
| P6 | 2 promotions prepared, 0 committed, 23 open workstreams, none merged | REAL — **the promote stage has zero live evidence** |
| P7 | the dead vocabulary: states the schema admits and no verb writes | REAL |
| P8 | the thirteen works of `LITKB_APPROVE_SESSION_2026-09-21b.md` — three real works with author lists truncated to one name where the document has six or seven (Pesonen, Pauls, Raykar), one truncated title (Kalinicheva), three truncated keys, one work with no identifier (Chrisman), four whose year is not printed | REAL, **the ground truth for R3** |
| P9 | the five approve guards already firing in `qc/test_litkb_p2.py:1129-1157, :1174-1188, :2139-2154, :2156-2175`. **Unfired anywhere: the CAS at `0014:403-410`** | REAL |
| N1–N11 | self-decline (including the invisible-character form `' sess-admit '`), decline of an approved admission, decline of a registry admission, empty reason, a provenance row naming a non-column, the Pesonen/Pauls/Raykar rebuild, withdrawing a non-current version, an operator bind whose sha256 matches a quarantined file version | **CONSTRUCTED** |

#### Kill criteria

- **R1:** after decline → reopen → approve, deleting or overwriting any earlier review row →
  `reviews_deleted=1` RED; and the grant test must go RED if any agent role holds UPDATE or DELETE
  on `admission_reviews`.
- **R2:** N1 self-decline (both the Python guard and the SQL constraint must raise); N2 decline of
  an approved admission → 55000; N4 decline of a registry admission → 55000; N6 empty reason →
  CHECK violation; **the plan's own counter** (`LITKB_WORKPLAN.md:551`) — the verb removed and
  194's proposal left → `proposals_unadjudicated=1`; and D3 shown to fire for decline as it does
  for approve (abandon the admitter's workstream, then decline → refused, nothing written).
- **R3:** N8 a provenance row naming a field that is not a column of the version table (e.g.
  `'titel'`) → refused. **N9: rebuild the Pesonen/Pauls/Raykar admission payloads on a throwaway
  DB — with provenance disabled the check must report `authors_unattributed=3`, with it enabled 0.
  A gate that cannot separate those three from the ten correct works is measuring nothing.**
- **R4:** N10, both halves: withdrawing a non-current version → refused; and a deliberately broken
  implementation that sets the state without moving the pointer → the invariant query (works
  joined to work_versions on `current_version_id` where state in ('rejected','withdrawn'), which
  returns 0 today) returns >0, RED. Plus `versions_deleted=1` if any row count drops.
- **R5:** N11 an operator `--from-file` bind whose sha256 matches a quarantined file version must
  refuse before the copy; with the lookup disabled, `known_bad_relands=1` (the counter S4.5
  already names).
- **R6:** the self-approve attempt must raise; if it does not, the guard is RED on live-shaped
  rows regardless of what the test suite says. Counter:
  `approve_guard_unfired_on_live_shape=1` when a session report records no fired output.

#### Where it lands

**R6 is free and belongs in the next second-session procedure, before S5** — it is one command
and a pasted error. **R2 and R1 land together, after S5** and before the first promotion Kam
merges, because the one proposed admission has no verb that can adjudicate it either way and
"refused" is already an overloaded word. **R3 after S5**, scored on P8's thirteen works. **R4 and
R5 last**, R5 gated on Kam's open decision `litkb-from-file-version-state`. Counters: R2 adds
`proposals_unadjudicated=0` — a counter the plan already names — and R1/R3 make the promotion
report answerable to "who asserted this byline", which is the defect S5's own entry conditions
were written to stop propagating.

**The measurement everyone should carry away:** *the promote stage has no live evidence at all.*
2 prepared, 0 committed, 23 open workstreams and none merged, 421 uses all still proposed, 263 of
263 file versions bound directly. Every promote-side kill criterion must therefore be fired on a
throwaway database; **nothing about promote commit has been observed on real rows.**

---

### 1.9 The headless run protocol (L12)

#### litkb today

**litkb has no concept of a run.** A run exists as three uncoupled artefacts: a frozen manifest
(`litkb_acceptance.py:796-841` `_scout_freeze`, :1081+ `check_first_work`; the one on disk is
`Reports/LITKB_FIRST_WORK_2026-09-21_manifest.json`, 40 lines), an **untracked launch kit**
(`_derived/s4/launch-s4.sh` 15 lines, `s4-prompt.txt` 14,003 bytes, `mcp.json`, `launch.log` — all
invisible to git under `.gitignore:214 /_derived/*`), and prose
(`Reports/LITKB_SCOUT_LAUNCH.md` §4, `docs/LITKB_AGENT_BASE_BRIEF.md`).
`docs/LITKB_RUN_PROTOCOL.md` does not exist and the `run` acceptance subcommand is deliberately
absent (:29-35).

L12's live measurements: `litkb.hunt_requests` has **18 columns and none is a run id, a duration
or a supersession pointer**; there is **no `runs` table** among the 47 in schema `litkb`; and **a
workstream is not a run** (23 workstream rows, only 8 carrying any drop-off — 103 drop-offs
total, resolution_state open 58 / unconfirmed 36 / confirmed 5 / contradicted 4 — and
`state='open'` is never closed by anything).

The pain is four-fold and each part is measured:

1. **The seeding guard reads exactly one file.** `qc/test_litkb_acceptance.py:78` pins
   `PROMPT_DOC` to `docs/LITKB_SCOUT_PROMPT.md`. Running its own three `SEED_SHAPES` regexes over
   the launch kit today: every tracked doc is CLEAN, and **the live S4 launch prompt
   `_derived/s4/s4-prompt.txt` carries a work key
   (`Jaffe_2014_estimating-accuracies-multiple-classifiers`)**. Whether that is a violation is
   Kam's ruling — but nothing decides, and S5's own run prompt will be written to the same
   untracked place.
2. **The prompt is not in the manifest.** `_scout_freeze:823` records `launch_cmd`, whose text
   names a PATH (`launch-s4.sh:13-15` is `"$(cat _derived/s4/s4-prompt.txt)"`), and
   `_derived/s4/launch.log` shows **two S4 launches six minutes apart on different heads
   (`e1867c6`, `ecee36c`) while `s4-prompt.txt`'s mtime is a day later** — the bytes those runs
   received are unrecoverable, although litkb already owns the right tool (`_register_sha256` /
   `_fixture_committed`, :422-450) and applies it only to the edge register.
3. **Budgets are per host and per process**: `--max-turns 60` on the CLI, and per-drop-off
   `seconds` already written by `hunt.py:854,992,998,1013` into
   `Reports/LITKB_EDGE_RUN_2026-09-21.csv` — **read back by nothing**.
4. **Liveness is a one-shot minute-one effects check**, which is why
   `_derived/s4/launch-s4.sh:2-4` records that *"S3 was launched headless-to-a-log and had to be
   moved mid-run (2026-09-21 00:07)"*. Nothing can tell working from stuck.

One further internal defect: **`_scout_freeze:803` freezes on the workstation clock**, the exact
hazard `baseline_snapshot`'s own docstring (:912-919) warns about **in the same file** after
first-work was fixed and scout was not.

#### Strongest external mechanisms

| mechanism | repo @ sha · symbol | licence | status |
|---|---|---|---|
| Run identity = **hash of the fields that determine the run** (task file/name/args, model, solver, every limit), explicitly EXCLUDING transport options (`max_retries`, `max_connections`); computed identically from the pre-run spec AND from the log the run produced; versioned by `TASK_IDENTIFIER_VERSION` | `UKGovernmentBEIS/inspect_ai` @ `146f30f` · `_eval/evalset.py:task_identifier` | MIT (LICENSE read) | VERIFIED |
| **Working time = wall clock minus waiting** (back-off, rate limits, semaphores) via `record_waiting_time`; `monitor_working_limit` refuses to check while a model event is active; breach raises a typed error carrying `type/value/limit/source` | same · `util/_limit.py` | MIT | VERIFIED |
| The spec is the log's own first artefact (`_journal/start.json`; "there is no header.json mid-run and zip members are immutable"); `EvalRevision` carries `commit` **and `dirty: bool`**; `packages: dict[str,str]` pins the environment | same · `log/_log.py`, `log/_recorders/eval.py:log_start` | MIT | VERIFIED |
| A retry is launched **from the LOG FILE**; `incomplete_action` declares as DATA what happens to units in progress (`retry` \| `error`), `incomplete_max` is a threshold above which the cheap resolution is refused; a finalized recovery lands at `<name>-recovered.eval`, never overwriting | same · `_eval/eval.py:eval_retry_async` | MIT | VERIFIED |
| Three files written into the run's OWN dir **before the task function is called**: `config.yaml` (resolved), `hydra.yaml` (framework), `overrides.yaml` (**the delta the launcher passed**) | `facebookresearch/hydra` @ `244d5a5` · `core/utils.py:_run_job` | MIT (LICENSE read) | VERIFIED |
| **Params immutable per run**: re-logging a key with a DIFFERENT value raises naming both values; re-logging the SAME value is a silent no-op. Metrics and tags stay mutable | `mlflow/mlflow` @ `36ce73c` · `store/tracking/file_store.py:_validate_new_param_value` | Apache-2.0 (LICENSE read) | VERIFIED |
| Idempotent resume with **no separate state**: the per-unit `report.json` under `<run_id>/<model>/<instance>/` IS the completion record; `write_run_metadata` refuses to blank a frozen field on a re-grade | `SWE-bench/SWE-bench` @ `02e7a74` · `harness/run_evaluation.py` | MIT (LICENSE read) | VERIFIED |
| Budgets pre-checked at a boundary: "the next request **would** exceed"; a cumulative RUN budget alongside the per-unit one | `pydantic/pydantic-ai` @ `8809abe` · `usage.py:UsageLimits.check_before_request` | MIT (LICENSE read) | VERIFIED |
| **Liveness is a database row**: alive = state RUNNING AND `latest_heartbeat` within `heartrate * 2.1`, explicitly so a job "can be killed externally… regardless of who is running it or on which machine" | `apache/airflow` @ `21b1dfc` · `jobs/job.py:is_alive` | Apache-2.0 (LICENSE read) | VERIFIED |
| `"command": " ".join(map(shlex.quote, sys.argv))` — the launch command verbatim, four lines | `openai/evals` @ `8eac7a7` · `cli/oaieval.py` | MIT (LICENSE.md read) | VERIFIED |
| Contamination detected by **13-gram overlap**, not identifier match | `EleutherAI/lm-evaluation-harness` @ `d6de816` · `decontamination/decontaminate.py` | MIT | VERIFIED |
| A planted canary GUID **plus a task that measures whether the marker leaked** — the marker is not the gate, the detector is | `google/BIG-bench` @ `092b196` · `benchmark_tasks/README.md`, task `training_on_test_set` | Apache-2.0 | VERIFIED |

#### Recommended change (diff-shaped)

- **Run identity = hash of what determines the run, recomputable from the run's own artefacts.**
  `docs/LITKB_RUN_PROTOCOL.md` §4 + `litkb_acceptance.py`: `run --freeze` writes an identity hash
  over topic, slug, prompt sha256s, agent-file commit, budgets and attempt policy; `run
  --manifest` RECOMPUTES it from the run's artefacts. **Replaces byte-hashing the manifest** —
  litkb's own byte guard already cost a false red on a CRLF rewrite and cannot say what an edit
  meant. [VERIFIED]
- **WORKING-time budgets, checked only at stage boundaries, breaching into a typed outcome.** TWO
  frozen budgets (per-run and per-hunt; **the plan names only the per-hunt one**), time measured
  as WORKING seconds so S4.5's back-off ladder does not eat the hunt budget, checked between
  stages and between routes only, breach recorded as a typed row with the hunt ending in the rung
  the ladder had reached — **never a new state word**. [VERIFIED]
- **Contamination coverage.** Declare the covered prompt set by GLOB
  (`_derived/*/*prompt*.txt` + `docs/`), not by the single pinned path; add a 13-gram overlap
  check against `main_works.title` alongside the three `SEED_SHAPES` regexes. **A prompt naming
  the paper by TITLE rather than by identifier passes the guard entirely today.** [VERIFIED]
- **Resume derived from the run's artefacts, keyed by a run id.** Mint a `run_id` at freeze,
  distinct from the workstream slug; `hunt_requests` (or a sidecar ledger) gains `run_id`,
  `seconds`, `over_budget`, `superseded_by` and a UNIQUE on `(run_id, source_row)`. [VERIFIED]
- **Frozen fields as immutable params: same value = no-op, different value = error.** A resumed
  run re-declares its frozen manifest fields and is refused only if one changed; a superseded
  drop-off is retired by an explicit verb through the versioned-record path, **never by an UPDATE
  or a delete** — which is also what WE-DON'T-DELETE requires. [VERIFIED]
- **Liveness as a database row with a grace multiplier.** The run writes a heartbeat on a declared
  cadence; alive = running AND last beat within `cadence * grace`. Keeps the minute-one EFFECTS
  check as the start proof. [VERIFIED]
- **The spec is the run's own first artefact — with a dirty flag, the environment, and the delta
  kept separate.** The manifest records `repo_head` AND `repo_dirty`, the sha256 (CRLF-folded,
  litkb's own convention) of **every prompt file the launch reads**, the `mcp.json` hash, the
  migration tips, and the DELTA (topic + slug) beside the resolved whole. [VERIFIED]
- **Attempt limit and crash disposition declared as DATA before launch, with a refusal
  threshold.** `attempts_per_dropoff` and the in-progress disposition (retry / UNDETERMINED) are
  manifest fields, **inside the identity hash**, fixed before launch — the plan states this only
  as prose at `LITKB_WORKPLAN.md:844-845` and no code reads it. A recovered artefact never
  overwrites the crashed one. [VERIFIED]
- **Two litkb-internal defects the protocol must fix.** (1) Freeze on the DATABASE clock in one
  REPEATABLE READ snapshot (reuse `baseline_snapshot`; do not write a second copy). (2) Every gate
  invocation in the protocol is bare or `${PIPESTATUS[0]}`, and a protocol test greps the
  protocol's own command blocks for a gate followed by a pipe — the `FIRST_WORK` bounded outcome 6
  failure (`gate | tail -N; echo $?` reported tail's 0 and hid two real exit-1s) **is still
  uncovered by any gate**. [VERIFIED]

#### Local test set

- **REAL manifests:** `Reports/LITKB_FIRST_WORK_2026-09-21_manifest.json` (40 lines,
  `frozen_at_source=db`, `repo_head 0dd8886`, **no dirty flag**) and
  `_derived/first-work/first-work-1-manifest-AFTER.json` (the live replay kill, already exits 1).
- **REAL launch kits:** `_derived/s4/{launch-s4.sh, s4-prompt.txt, mcp.json, launch.log}` —
  launch.log is 2 lines, two S4 launches 6 minutes apart on different heads.
- **REAL drop-off population:** 103 hunt_requests across 8 workstreams (title-hunts-1 37,
  ruled-hunts-1 34, scout-1 9, scout-2026-09-20 9, proving-run-2-label-noise 4,
  proving-run-label-noise 4, first-work-1 4, improve-review-1 2). The **title-hunts-1 →
  ruled-hunts-1 supersession is the only real supersession case in the base.**
- **REAL ledgers with per-unit timing:** `Reports/LITKB_EDGE_RUN_2026-09-21.csv` (14 rows, with
  `seconds` + `started_at`), `LITKB_TITLE_HUNTS` (40), `LITKB_RULED_HUNTS` (35) — 89 rows total.
- **REAL prompt set:** `docs/LITKB_SCOUT_PROMPT.md`, `docs/LITKB_AGENT_BASE_BRIEF.md`,
  `_derived/scout/scout-1-prompt.txt`, `_derived/s4/s4-prompt-run2-ARCHIVED.txt` — all CLEAN,
  measured. **Negative already real:** `_derived/s4/s4-prompt.txt` (one work key).
- **CONSTRUCTED:** N1 (an S5 prompt template with a work key appended), N2 (the same seeded with a
  stored work's TITLE), N3 (a manifest whose `hunt_budget_seconds` is edited after the freeze),
  N4 (frozen while the tree is dirty), N5 (a resumed run changing one frozen field), N6 (two
  ledger rows for one source row), N9 (no heartbeat for > cadence*grace), N10 (a piped gate in the
  protocol document), N11 (a resumed run re-hunting a terminal drop-off).

#### Kill criteria

- **Identity:** N3 → recomputed identity mismatches → RED. Control: an edit to a non-determining
  field (a comment, the report path) must stay GREEN.
- **Budgets:** N7 (the plan's own (c)) — `hunt_budget_seconds=1` with any live-route drop-off →
  `hunts_over_budget>=1`. **N8: a hunt whose whole elapsed time is back-off sleep must NOT be over
  budget under a working-time budget, and WOULD be under wall clock — that difference is the
  test.**
- **Contamination:** N1 → the guard RED for **every** declared-covered file, not only
  `LITKB_SCOUT_PROMPT.md`. N2 → the n-gram guard RED (**today this PASSES**). Control for N2: an
  unrelated topic string of similar length must stay GREEN.
- **Resume:** N6 → `duplicate_dropoffs>=1`. N11 → `rehunted_terminal>=1`. N12 (the plan's own (c))
  — a check-1 refusal re-hunted bare inside the same run → protocol test RED.
- **Immutable params:** N5 → refused, naming the field and both values. **Control: the SAME
  manifest re-declared unchanged → silent success (a gate that refuses this has broken resume).**
- **Liveness:** N9 → `heartbeat_stale=1` and the protocol's stop rule names it. **Control: a run
  that is merely SLOW (writing beats but no drop-offs) must stay GREEN — killed and slow must be
  distinguishable, which is the thing that failed on 2026-09-21.**
- **Spec artefact:** N4 → `repo_dirty=1` recorded at freeze and surfaced by the grader; a prompt
  file edited between freeze and grade → `prompt_hash_mismatch=1`; **a CRLF-only rewrite of the
  same prompt must stay GREEN** (the false red `_register_sha256` was written to fix).
- **Attempts:** N12; a mutation that sets the disposition AFTER the freeze → identity mismatch;
  exhaustion recorded as anything other than UNDETERMINED → RED.
- **Internal defects:** a manifest whose `frozen_at_source != 'db'` → refused. N10 → protocol test
  RED; the same block written as `${PIPESTATUS[0]}` → GREEN.

#### Where it lands

**All of §1.9 is S5**, and it is the session's own Work item ("docs/LITKB_RUN_PROTOCOL.md …"). It
adds to S5's (b): `hunts_over_budget=0` already exists and gains a working-time definition;
`operator_interventions=0` gains the heartbeat that makes "stuck" visible; and new counters
`duplicate_dropoffs=0`, `rehunted_terminal=0`, `prompt_hash_mismatch=0`, `repo_dirty` printed.
**One item must precede the S5 launch by days, not minutes:** the contamination glob, because the
prompt S5 will actually run from is untracked today and the guard cannot see it. **The two
internal defects (db clock, piped gate) are free and should land with the protocol doc.**

---

### 1.10 Hermetic replay of the hunt (L7)

#### litkb today

litkb's whole-loop harness is three layers. The **register**
`qc/fixtures/litkb_hunt_edge_cases.json` holds 26 rows (17 execute, 2
execute-pending-migration-28, 5 replay-only, 2 not-a-hunt); the **driver**
`qc/instruments/litkb_edge_run.py` runs each through `litkb.hunt.hunt` with four injected seams
built by `replay_row` (:544) — `registry_client`, `fetch`, `acquirer`, `pacer`; the **grader**
`qc/instruments/litkb_acceptance.py edges` (`check_edges`, :1653) compares the observed
(state, reason) pair against the register, with identity pinned by `_register_sha256` (:422, CRLF
folded) and refused before anything is graded.

The measured pain is three-part:

1. **Cost.** The live run `Reports/LITKB_EDGE_RUN_2026-09-21.csv` is **14 rows in 560.5 s**, max
   504.76 s on E13; the replay `…_replay.csv` is **19 rows in 4.5 s** — more rows in 1/125th of
   the wall clock, and 5 execute rows never landed live at all.
2. **Fragility.** `Reports/LITKB_RULED_HUNTS_2026-09-21.md` §8 records **24 consecutive arXiv 406s
   over 30 minutes** putting 8 rows (28, 49, 117, 122, 132, 174, 193, 242) into
   `api-error`/`registry-transient` with their drop-offs unlinked, and `LITKB_WORKPLAN.md:84-86`
   still carries "whether litkb's own client is the defect is UNDETERMINED" — unanswerable
   without a recording of both the curl (429) and urllib (406) conversations.
3. **The one that matters: the replay world is AUTHORED, not recorded, and has already drifted
   from recorded truth inside the same repo.** `_acquirer_stub` (`litkb_edge_run.py:433`) returns
   a hand-written `{'outcome','attempts','route_detail'}` dict instead of running the ladder. For
   E03, E07 and E20 the register's live block says `prediction:true` with `first_expected`
   held/not-acquired; the live run corrected `expected` to blocked/403 but `replay.expected` still
   carries the superseded prediction. **E13 is worse because it passes:** its pair still reads
   blocked/403 while the route ladder it asserts (open_access blocked [200,200,403,403], scihub
   blocked [200,200]) differs from the recorded one (open_access blocked [403], annas bad-file,
   scihub blocked [200,200,403,200]) in route count, status and **every HTTP code** — and
   `_asserts_offences` (`acceptance.py:1606`) can only check `attempt_status` membership, so
   nothing looks.

**This is CLAUDE.md §3.4c — a design accepted on numbers it produced about itself — sitting inside
the acceptance instrument.**

Nothing enforces hermeticity either: no cassette library, no pytest-socket, no socket guard
anywhere (grep over `requirements-*.txt` and both `pyproject.toml`: **zero hits**), and six call
sites construct their own `netutil.Client()` past the injected stubs. Meanwhile **the seam is
already singular** — `netutil.Client.get` (:224) is the only HTTP door in the package, returning
`(status, headers, bytes)` and even encoding network errors as `(0, {}, redact(...))` — and litkb
has already invented the cassette **three times**.

#### Strongest external mechanisms

| mechanism | repo @ sha · symbol | licence (as metadata states) | status |
|---|---|---|---|
| Cassette = ordered (request, response) list; `play_counts` Counter; `match_on` default `(method, scheme, host, port, path, query)`; `find_requests_with_most_matches` returns the near-miss **with which matchers failed** | `kevin1024/vcrpy` @ `c599974b` · `cassette.py` | MIT | VERIFIED |
| **The single highest-value import:** `block_socket()` patches `socket.socket.connect`/`connect_ex` (deliberately NOT `socket.socket` itself, so a local server still works) with an `allowed_hosts` alternation regex; `blocking_context` restores in a finally. ~40 lines of stdlib, no dependency | `kiwicom/pytest-recording` @ `1b549021` · `network.py:104-124, 163-169` | MIT | VERIFIED |
| strips volatile headers at record time (`Date, Server, Connection, Content-Length, Content-Encoding`) case-insensitively, with a `keep_headers` escape | `getsentry/responses` @ `8afa534f` · `_recorder.py` | Apache-2.0 | VERIFIED |
| **bidirectional placeholders**: `replace_all(placeholders, False)` on load, `True` on save — the secret never lands on disk *and* is substituted back at replay | `betamaxpy/betamax` @ `8f3d2841` · `cassette.py:178,182` | Apache-2.0 | VERIFIED |
| `match_on=['uri','method','raw_body']` + `drop_unused_requests=True` | `danielnsilva/semanticscholar` @ `6041eed8` · `tests/test_semanticscholar.py:28-34` | MIT | VERIFIED |
| **the discipline, in one line:** `record_mode: "once" if not IN_GITHUB_ACTIONS else "none"`; `filter_headers` for four API keys + cookie | `future-house/paper-qa` @ `57e89f72` · `tests/conftest.py:107-123` | Apache-2.0 | VERIFIED |
| **directly on point:** the SAME Crossref API litkb calls, covered by `@pytest.mark.vcr` with byte-faithful gzip+base64 (`!!binary`) bodies | `sckott/habanero` @ `314e824b` | MIT | VERIFIED |
| fixture named by its own sha1 + `assert len(responses.calls) == 1` | `internetarchive/sandcrawler` @ `e23e2bd5` · `python/tests/test_grobid.py` | GPL-3.0 | VERIFIED |
| hermeticity by LOCAL SERVER, shipping the negative content-type cases deliberately (`/invalidContentType`, `/missingContentType`) | `zotero/translation-server` @ `3a9d1761` · `test/setup.js` | AGPL-3.0 | VERIFIED |
| **NEGATIVE CONTROL:** no vcr, no mock — tests hit live OpenAlex. *litkb's current position* | `J535D165/pyalex` @ `875c708c` | MIT | VERIFIED (absence) |
| **SECURITY:** vcrpy's `_CassetteLoader` refuses `!!python/object` tags — "CVE-class: arbitrary code execution via untrusted cassette files" → **store cassettes as JSON** | vcrpy · `serializers/yamlserializer.py` | MIT | VERIFIED |

#### Recommended change (diff-shaped)

- **D1 — `RecordedClient`: one cassette layer at litkb's single HTTP seam.** ~120 lines beside
  `Client` in `netutil.py:145`, same `get(url, accept, timeout, follow, data, headers) ->
  (status, headers, bytes)` face. Key = `(method, url, accept, follow, sha256(data or b''))`.
  **Record envelope = the `_provenance` block litkb ALREADY hand-authored** in
  `qc/fixtures/litkb_title_gate_wrong_work.json` (`query_sent, request_url, fetched, fetched_by,
  http_status, response_bytes, wire_response_sha256, stored_body_sha256`), promoted from one file
  to every interaction. Body base64, **JSON not YAML**. Secrets via the existing `netutil.redact`
  / `redact_shapes`, plus betamax-style two-way placeholders for the archive `key=` query param
  that must still be present at replay. [MIXED]
- **D2 — replay through the REAL acquisition ladder, not a synthetic `acquire()` return.**
  `litkb_edge_run.py:590-592` currently swaps in `_acquirer_stub` (:433). Replace with
  `_recorded_acquirer(rc)` calling the real `litkb.acquire.run.acquire` with
  `clients={'open_access': rc, 'scihub': rc}` — **a thread that ALREADY EXISTS**
  (`acquire/run.py:337 clients=None`, used at 414 and 416) — plus `annas_session=(rc, key)` for
  the third rung (:429-432). Keep `_acquirer_stub` only as a legacy path counted as
  `rows_unrecorded`. [MIXED]
- **D3 — socket guard: enforce hermeticity instead of assuming it.** Wrap `run_replay` (:674) in
  `no_network(allowed_hosts=(r'127\.0\.0\.1', r'localhost', r'::1'))` — Postgres 5433 and nothing
  else. The suite says the gap itself at `qc/test_litkb_hunt.py:237`: *"a default-spending hunt
  with no acquirer stub would open a socket"*. [MIXED]
- **D4 — four new counters on the edges grader.** Extend `check_edges` (:1653) and `edges_ok`
  (:1733) with `network_calls`, `cassette_misses`, `interactions_unplayed` and `rows_unrecorded`.
  `edges_ok` requires `network_calls==0` and `cassette_misses==0` under `--replay`.
  **`rows_unrecorded` is a FINDING not a failure** (the codex stage's own rule at :1337) — it is
  the migration burden and must reach 0. [MIXED]
- **D5 — cassette identity in the manifest, and a `--verify` staleness diff.** Extend the manifest
  written by `_edges_freeze` (:1777) with `cassette_dir`, `cassette_sha256` per row and
  `cassette_recorded_at`. **Hash as BYTES, not CRLF-folded** — `_register_sha256` (:422-433) folds
  because the register is authored JSON under `* text=auto`; a cassette is a recording and belongs
  with `Scripts/qc/fixtures/*.html binary` (`.gitattributes:58`). Add
  `Scripts/qc/fixtures/cassettes/** binary`. New `--record --verify` re-records into a temp dir and
  compares `stored_body_sha256` per interaction, printing the changed key component and, for a
  changed body, the first differing offset with ±80 redacted bytes. [MIXED]
- **D6 — fold litkb's three existing partial caches into the one recorder (§3.3).** After D1–D5,
  give `RecordedClient` a `mode='cache'` and retire `DiskCache` (`extract/references.py:311`,
  URL-only key, `CACHEABLE_STATUS=(200,404)`, **body stored as `.decode('utf-8','replace')` at
  :345 — which destroys any PDF**), `CachingClient` (`migrate_legacy/run.py:29`) and the
  hand-built `_provenance` envelope onto it, keeping the two things they get right:
  `CACHEABLE_STATUS=(200,404)` and the `_Deferred` pacer that makes a fully cached re-run cost no
  wall clock. **Lowest priority, most likely to break something quiet — follow D1–D5, do not lead
  them.** [MIXED]

#### Local test set

- **REAL:** the 24 hunt-shaped register rows in `qc/fixtures/litkb_hunt_edge_cases.json`; the 3
  response bodies already frozen in-tree (`litkb_web_snapshot_crossref_blog.html` 56,598 B,
  `litkb_title_gate_wrong_work.json`, `litkb_crossref_raw_search_item2.json`); the **59**
  `acquisition_attempts` rows carrying a `source_url`; the **278** `acquisition_attempts` rows
  covering **19 distinct (route,status) pairs** as the coverage target.
- **REAL divergence rows:** E03, E05, E06, E07 (plus E20, live row marked `prediction:true`) —
  the four register rows whose replay answer differs from the live answer today. E03 and E07 read
  blocked/403 live and held/not-acquired in replay.
- **REAL raise cases (negatives that already exist):** HV1–HV5 at `qc/test_litkb_hunt.py:1082,
  1117, 1137, 1152` with mutation-ledger rows at `qc/instruments/litkb_p2_mutations.py:1991,
  1998, 2005`.
- **CONSTRUCTED:** C1 (a cassette's 403 edited to 200), C2 (truncated PDF body), C3 (HTML body
  with no declared Content-Type = row H1's sign-in page), C4 (a cassette holding an interaction
  nothing asks for), C5 (a cassette recorded with a live archive key in the URL query).

#### Kill criteria

- **D1:** delete one interaction from E01's cassette — the replay must answer `cassette_misses=1`
  with `traceback=1`, **NEVER fall through to a socket**. And C5: a cassette whose bytes contain
  the registered secret rather than `<KEY>` must fail a `secrets_in_cassettes` counter.
- **D2:** E03, E07 and E20 must answer blocked/403 in replay and their `replay.expected`
  overrides must become deletable. Known-bad: edit E03's cassette so the Sci-Hub interaction
  answers not-in-archive — the row must fall back to held/not-acquired and register
  `state_or_reason_mismatches=1`.
- **D3:** new mutation-ledger row HR1 — delete the `no_network` context and point one cassette's
  URL at a host it does not hold. With the guard ON the row must record `RuntimeError: Network is
  disabled` and `network_calls>=1`; with it OFF the row silently succeeds against the live host.
  **If removing the guard makes the driver ERROR rather than answer worse, restructure — the
  harness reports an erroring mutation as DID-NOT-FIRE** (the lesson written into
  `admit/front.py:150-155`).
- **D4:** one known-bad per counter, or the counter is not a gate: C1 → `state_or_reason_mismatches`;
  C4 → `interactions_unplayed`; D1's deleted interaction → `cassette_misses`; D3's mutation →
  `network_calls`.
- **D5:** re-record E01 against a body one byte different → `cassettes_stale=1` naming the URL. A
  `--verify` that passes a mutated body is the gate failing. C2 must end refused/truncated-pdf,
  not extracted; C3 must quarantine, not answer refused/not-a-pdf.
- **D6:** a PDF put through the folded cache must come back byte-identical. **Today it cannot —
  `references.py:345` decodes to utf-8 with 'replace' — so this kill is already known to fire
  against the current code**, which is what makes it a gate rather than an assertion.

#### Where it lands

**S7 (ops), but with a strong argument for landing D1–D3 before S5**: the plan requires "an
independent referee per rung class" (`LITKB_WORKPLAN.md:168`) for S4.5–S4.7, and the measured cost
of doing that live is 14 rows / 560.5 s / max 504.76 s against 19 rows / 4.5 s in replay — **125×
faster, more rows, and no quota spent against hosts that are already refusing this client.** D4's
counters join S7's (b) beside `incomplete_runs=0`; `rows_unrecorded` is printed unbounded until it
reaches 0. **D6 last and separately**, because it touches the reference-resolution path that L5's
stage depends on.

---

### 1.11 `doctor` and the seven-night soak (L10)

#### litkb today

**The doctor does not exist.** `grep` over `pipeline/litkb/`,
`qc/instruments/litkb_acceptance.py` and `qc/fixtures/` returns seven hits — six of them prose in
`pipeline/litkb/ops/nightly_soak.py` (:8, :13, :85-86) and one the two column names
`doctor_ok`/`doctor_detail` (:88-89), which the writer fills with the **empty string** at :245.
`qc/fixtures/litkb_doctor.json` is absent from a directory holding nine other litkb fixtures, and
`litkb_acceptance.py`'s subparsers are plan/disposition/guard-checkout/scout/first-work/edges/
codex/preflight (:1838-1925) with **no `soak`** — which its own header states at :32.

What DOES exist is **stronger than the plan's description in one place and weaker in four**:
`nightly_dump.verify_dump` (:91-106) already verifies in three stages — list (`pg_restore
--list`), read (`pg_restore -f -`), sha (against the manifest hash) — and `restore_and_count`
(:142-173) already restores into a scratch database and diffs `table_counts` against source
counts taken under the same `pg_export_snapshot`.

L10's measurements this session: three soak rows on disk (2026-09-20T19:42 manual, 09-21T10:17,
09-22T10:17, all green, **doctor columns empty**); **ten dumps spanning 187,576 B to 97,770,680
B**; **ONE restore-and-count ever** (2026-09-21, 38 tables / 1,093,673 rows, **132.8 s**) because
`RESTORE_EVERY` is 7 days (:46) — every other night logs `restore=skipped` at ~16 s; stage costs
on the newest 97.8 MB dump are **list 0.03 s, read 3.01 s, sha 0.30 s against 132.8 s for the full
restore**, so one doctor cannot be both cheap and deep; both scheduled tasks are Ready with
`LastTaskResult=0` and `NumberOfMissedRuns=0`; there are **FOURTEEN worker databases, not twelve**
(`litkb_test_w1..w12` plus `litkb_test_wmatching` and `litkb_test_wspendrule`); `pg_locks` is
readable cluster-wide by `litkb_reader` (0 advisory locks held) but `litkb_meta.schema_migrations`
is refused to it, so the migration-tip check needs the owner login; `qc/conftest.py:106` takes a
**BLOCKING** `pg_advisory_lock`, so a second pytest on one worker DB **waits silently rather than
refusing** — the phantom-F at its source; and the MCP server advertises `VERSION = "0.1.0"`, a
hand-typed constant (`mcp/server.py:83`, handed to `MCPServer` at :1421).

#### Strongest external mechanisms

| mechanism | repo @ sha · symbol | licence (as stated) | status |
|---|---|---|---|
| checks discovered by **reflection** (`methods.grep(/^check_/)`, 54 of them); `brew doctor <name>` runs ONE; an unknown name `ofail`s rather than skipping silently; `--list-checks`; `--json` | `Homebrew/brew` @ `e24c0e7e` · `diagnostic.rb:1624-1626`, `cmd/doctor.rb` | BSD-2-Clause (repo LICENSE.txt) | VERIFIED |
| explicit registry + **tags**; `--tag`, `--list-tags`, `--fail-level`; **`database`-tagged checks excluded by default** because they "do more than mere static code analysis" | `django/django` @ `dd6f6b15` · `core/checks/registry.py` | BSD-3 (ASSERTED) | VERIFIED |
| a strategy object; `init_check(name)` sets `running_check` so **a timeout names the check that hung**; `NON_CRITICAL_CHECKS`; **`backup maximum age` AND `backup minimum size` as two separate checks** | `EnterpriseDB/barman` @ `f759d7f5` · `src/barman/server.py:678-737, 1371-1427` | GPL-3.0 (ASSERTED) — **design only, no code copied** | VERIFIED |
| a **table of `damage func()` cases** (bit flip, truncation, garbled-once) each asserting the checker errors, **including a row asserting it must NOT fire on a benign transient**; `--read-data-subset` budgets the expensive read | `restic/restic` @ `6adedec6` · `internal/checker/checker_test.go:316-400` | BSD-2 (ASSERTED) | VERIFIED |
| `verify` emits a per-file invalid list with a **reason enum** rather than one bool; `check` forces a WAL switch and confirms the segment **arrives** | `pgbackrest/pgbackrest` @ `ce19dae6` | MIT (ASSERTED) | VERIFIED |
| **three pings: START, FINISH, FAIL.** A run that starts and dies leaves START with no FINISH; the monitor alarms on the **absence** | `borgmatic-collective/borgmatic` @ `ad10c917` · `hooks/monitoring/healthchecks.py:11-16` | AGPL-3.0 (ASSERTED) — design only | VERIFIED |
| `FailingStreak` + `Retries=3` + `StartPeriod`; one success resets the streak | `moby/moby` @ `3f673306` · `daemon/health.go:229-233` | Apache-2.0 (ASSERTED) | VERIFIED |
| enumerate the modules **actually loaded** via `module.__spec__.origin` and snapshot them; the process measures itself | `django/django` @ `dd6f6b15` · `utils/autoreload.py:127-155, 425-437` | BSD-3 (ASSERTED) | VERIFIED |
| a lease is `{holder, LeaseDuration, RenewTime}` with `LeaseDuration > RenewDeadline > RetryPeriod*JitterFactor`; a non-holder is **refused rather than queued** | `kubernetes/client-go` @ `be7afe4f` · `tools/leaderelection/leaderelection.go:77-88` | Apache-2.0 (ASSERTED) | VERIFIED |
| `Get-ScheduledTaskInfo` → `LastRunTime`, `LastTaskResult`, **`NumberOfMissedRuns`** — an independent witness held **outside** the artefact the job writes | Windows Task Scheduler | n/a | VERIFIED on this machine |

#### Recommended change (diff-shaped)

- **Check registry with tags and a `--only` selector (`litkb doctor`).** New
  `pipeline/litkb/ops/doctor.py`. Each check returns `[]` or `[Finding(check, level, hint,
  detail)]`; a raising check is caught and reported as that check failing. **Tags driven by
  measured cost:** `fast` (≤1 s), `deep` (3.01 s dump read + 0.30 s sha), `restore` (132.8 s).
  `litkb doctor` runs fast,deep; `--tag restore` is weekly; the nightly task fills the
  already-existing `doctor_ok`/`doctor_detail` columns. [VERIFIED]
- **`dump_recent_and_sound`: age AND size floor AND 3-stage verify of the NEWEST dump.** litkb
  already has the restore proof; what is missing is that (1) **nothing calls `verify_dump` on the
  newest dump at doctor time** (`run()` checks the `.partial` at :279; `verify_existing()` is
  manual and re-reads all ten at :327), (2) there is no age check, (3) there is no size floor.
  Add: `age_h < 26`; `bytes >= 0.5 × median of the last 7` (**a ratio, not a constant — the series
  grew 187 KB to 97.8 MB in eight days**); `verify_dump(path, expected_sha=manifest sha)`.
  Measured total cost **3.34 s**. [VERIFIED]
- **`worker_db_free_or_leased` + `pg_try_advisory_lock` in conftest.** Change one call in
  `qc/conftest.py:106` from blocking `pg_advisory_lock` to `pg_try_advisory_lock` and fail with
  the DB name and holder pid. Add a doctor check reading `pg_locks` cluster-wide joined to
  `pg_stat_activity`, **enumerating workers from `pg_database LIKE 'litkb\_test\_w%'`** rather
  than `range(1,13)`. Also set `application_name` in conftest's connect so a red doctor names the
  worktree, not a bare pid. [MIXED]
- **MCP code stamp: turn the staleness trap into a measurement.** Replace `VERSION = "0.1.0"`
  (`mcp/server.py:83`) with `CODE_STAMP` = sha256 over the sorted `(relpath, bytes)` of the litkb
  modules in `sys.modules`, computed at import, and add a `litkb_doctor` tool that recomputes the
  same digest **from disk at call time**. Equal means the connected server runs the tree's code;
  different means reconnect, **said by the server itself in the session that needs to hear it**.
  **Use a CONTENT digest, not mtime: a git checkout rewrites every mtime.** Measured cost over the
  whole 59-file, 1,242 KiB package: below timer resolution. [VERIFIED]
- **`litkb_acceptance soak`: consecutive-green clock, scheduler witness, start sentinel.** Add the
  `soak` subcommand (absent today). Its three S7 counters cannot be computed the obvious way:
  `elapsed_hours` must be the longest **UNBROKEN green run**, not `last.ts - first.ts`;
  `missed_scheduled_runs` must come from `Get-ScheduledTaskInfo NumberOfMissedRuns` **PLUS** a
  >26 h gap scan over `ts_utc`, reported as two independent witnesses; `incomplete_runs` needs
  **the writer fixed, not the counter** — `nightly_soak.run()` appends exactly one row at the END,
  so a crashed night writes nothing and `incomplete_runs` over the CSV is structurally 0 forever.
  Add a start sentinel written before the first smoke and removed after `append_row`, bounded by
  the existing `guard_path` (:217-229). [VERIFIED]
- **`qc/fixtures/litkb_doctor.json` — the mutation register.** New fixture in the house style of
  `litkb_hunt_edge_cases.json` (a `kind`, a prose `_what` naming the driver and the grader, a
  `_columns` dict, rows citing the real row each case came from). One row per check × mutation:
  `id` (also the `--only` selector), `check`, `mutation`, `expect`, `carrier` (the real row, or
  the word CONSTRUCTED), `source`. [VERIFIED]
- **Timeout that names the check that hung.** Wrap doctor's run the way barman does. The restore
  check measures 132.8 s; a hung `pg_restore` against a locked or FUSE-backed file would otherwise
  run until the scheduler's `ExecutionTimeLimit` kills the task, and then the soak CSV shows
  **nothing at all** — the same blind spot as the missing start sentinel. [VERIFIED]

#### Local test set

| id | rows | kind |
|---|---|---|
| P1 | the three real soak rows (all green, `doctor_ok` empty) | REAL positive |
| P2 | the ten real dumps + `manifest.json` + `nightly_dump.log` in `D:\edmonds-pipeline\pgdump\litkb` | REAL |
| P3 | the single real restore proof line `restore=ok(38tables/1093673rows) secs=132.8` | REAL |
| P5 | **FOURTEEN** worker databases from `pg_database` | REAL |
| P6 | zero advisory locks held at probe time | REAL |
| P7 | both scheduled tasks Ready / `LastTaskResult=0` / `NumberOfMissedRuns=0` | REAL |
| P8 | the 59 `.py` files, 1,242 KiB under `pipeline/litkb/` | REAL |
| N1–N3 | a mid-file bit flip, a 5,000-byte truncation, a 4 KiB zeroed block of a real 1.5 MB dump, each `os.utime`'d to now | CONSTRUCTED **from a real dump — ALREADY FIRED** |
| N4 | the REAL 187,576-byte 2026-09-14 dump presented as tonight's | REAL, not yet run |
| N6–N9 | two connections taking the worker lock; a modified module after import; a 30 h-old CSV; a 7-row CSV with row 4 red | CONSTRUCTED |

#### Kill criteria

- **Registry:** `litkb doctor --only nosuchcheck` must exit non-zero **naming** the unknown check,
  NOT exit 0 having run nothing — this protects the whole mutation fixture, which names checks by
  string. Second: a check returning a non-list must raise, so an accidental bare `return` cannot
  read as a pass.
- **Dump — ALREADY FIRED THIS SESSION.** N1/N2/N3 each `os.utime`'d to now **ALL passed
  `pg_restore --list` (rc=0, 429 TOC entries) and ALL failed `pg_restore -f -` (rc=1)**. So
  **S7's corrupt-dump kill criterion is already defeated by the cheap obvious check (the TOC)**,
  litkb's existing stage 2 catches all three at 3.01 s, and `dump_restores` goes RED while
  `dump_age` stays GREEN — exactly S7 (c). N4 (the real 187 KB dump as tonight's) must turn
  `dump_size_floor` RED while all three verify stages stay GREEN; **that one has NOT been run.**
- **Worker DB:** N6 — two connections to `litkb_test_w10` both taking the lock. Today the second
  blocks indefinitely; after the change it must return within a second naming `litkb_test_w10`,
  and `--only worker_db_free_or_leased` must report w10 held by pid with an identifying
  `application_name`. **NOT run this session (running pytest is out of scope) — a design claim.**
- **Code stamp:** N7 — import the server module, then modify any file under `pipeline/litkb/` →
  mismatch. **AND the inverse, which matters as much:** a git checkout restoring byte-identical
  content (rewriting every mtime) must NOT report a mismatch. That second half is restic's
  must-not-fire-on-the-benign-case row and the reason for a content digest.
- **Soak:** N9 — a 7-row CSV with rows 1–3 and 5–7 green and row 4 `search_ok=false` must report
  `elapsed_hours` as the longer green run, **NOT 168**. N8 — a CSV whose last `ts_utc` is 30 h old
  → `missed_scheduled_runs >= 1` (`soak_stale` already does this correctly today — it is the only
  S7 check with a working test seam). A sentinel left behind with no matching row →
  `incomplete_runs = 1`.
- **Fixture:** for every row, the named check goes RED and **NO OTHER check changes state**. A
  mutation that reddens two checks means the checks are not independent, and S7 (c) says "mutated
  in isolation".
- **Timeout:** a check stubbed to sleep past the timeout must turn THAT check RED with a hint
  naming it, give a non-zero doctor exit code, **and still write a soak row**.

#### Where it lands

**All of §1.11 is S7**, and it maps onto S7's (b)
(`elapsed_hours>=168 missed_scheduled_runs=0 interventions=0 incomplete_runs=0`) with three
corrections the plan does not anticipate: `elapsed_hours` must be a consecutive-green clock;
`missed_scheduled_runs` must be TWO witnesses (the OS and a gap scan) and their disagreement is
itself a finding; and **`incomplete_runs` is structurally uncountable until the writer gains a
start sentinel.** Plus new counters `dump_age`, `dump_size_floor`, `dump_restores`,
`worker_db_free_or_leased`, `mcp_code_stamp`. **The start sentinel is a writer change and should
land early**, because every night between now and S7 that crashes leaves no evidence at all.

---

### 1.12 The agent interface and the WEB-BLIND boundary (L11)

#### litkb today

**The boundary is real but it lives in the wrong layer.** `mcp/server.py::build_server` (:1417)
binds **13 tools** onto `MCPServer(name="litkb", version=VERSION)` and offers **all 13 to every
client that connects**; the three roles are separated only by YAML frontmatter, and
`.claude/agents/librarian.md:6` and `review-writer.md:6` both grant `tools: mcp__litkb` — a
**server-level** grant, so the review-writer whose description says it "reads the BRIEF and
nothing else" **holds `litkb_acquire` at the protocol level**. `.claude/agents/lit-scout.md:9-15`
says in its own comment that whether frontmatter is even enforced had to be probed rather than
assumed.

What IS enforced in code is genuinely strong and should not be touched: the token is never a tool
parameter (`_session`, :170), every result passes two redactors (`_out`, :95), a read tool that
widens presents the token (`_caller_workstream` → `_require_token`, :491/:194), and a citation
must byte-match an ingested block of the file's current run (`use.py:162` + `visibility.FILE_JOIN`),
with `review_check.py:357-391` refusing a block outside the workstream's view, a wrong work, a
wrong page, a quote not in the bytes, or a triple absent from the brief.

Four measured gaps sit around that core:

1. **Role attribution is lost.** `.mcp.json` sets one static `LITKB_AGENT="claude"` for every
   session and subagent, and `SELECT agent, count(*) FROM litkb.hunt_requests` returns
   **`claude 83 / lit-scout 18 / taskC-opus 2`** — 83 of 103 drop-offs name the client, not the
   role.
2. **Staleness is acknowledged and unmeasured.** `VERSION = "0.1.0"` is a literal (:78) that has
   never moved, and `litkb_acceptance.py:1250-1251` says outright *"The MCP server of an OPEN
   session is stale after any merge until /mcp reconnect; that is not measurable from here."*
3. **There is no tool-call log.** 49 tables in schema `litkb`, none a call log; writes leave
   version rows, **reads leave nothing**.
4. **`grep -c annotations` on the server is 0**, although the installed SDK (mcp 2.1.1) accepts
   `annotations`/`meta` on `srv.tool()` and already ships both hook points a fix needs.

#### Strongest external mechanisms

| mechanism | source · symbol | licence | status |
|---|---|---|---|
| **The enforcement hook is ALREADY INSTALLED and unused:** `Extension.intercept_tool_call(params, ctx, call_next)` can short-circuit a `tools/call` without invoking the handler, folded by `compose_tool_call_handler`; `MCPServer.__init__` accepts `extensions=` | mcp 2.1.1 on disk · `mcp/server/extension.py:139-155,159`; `mcpserver/server.py:168` | MIT (SDK) | VERIFIED (read on disk) |
| `ServerMiddleware` sees every inbound message including `tools/list`; `_otel.py` is a working reference implementation; `MCPServer(middleware=[…])` | same · `mcp/server/_otel.py:17-32`; `server.py:181` | MIT | VERIFIED |
| named tool groups; `resolve_enabled()` with `all`/`none`/`-negation`; `apply_toolsets()` via `mcp.disable`/`enable`; **`validate_toolsets(registered)` returns every profile name the live registry lacks, because "FastMCP silently ignores unknown names, so drift is otherwise invisible"** | `54yyyu/zotero-mcp` @ `6233550` · `src/zotero_mcp/toolsets.py:160,236,249-259` | not stated in the file read | VERIFIED / licence unknown |
| `readOnlyHint` / `destructiveHint` / **`openWorldHint`** declared on every tool — the machine-readable "this tool reaches outside the corpus" flag | `openags/paper-search-mcp` @ `808e462a` · `server.py:529, :770` | not stated | VERIFIED / licence unknown |
| `PQASession(config_md5=self._settings.md5)` where `Settings.md5 = hexdigest(model_dump_json(exclude={'md5'}))` — the record carries what produced it | `Future-House/paper-qa` @ `57e89f7` · `agents/env.py:258-261`, `settings.py:845-846` | Apache-2.0 (ASSERTED) | VERIFIED |
| the agent's tool set as DATA: `AVAILABLE_TOOL_NAME_TO_CLASS` + `DEFAULT_TOOL_NAMES` from an env var; unknown name → `KeyError` at construction | same · `tools.py:691-712`, `env.py:60-68` | Apache-2.0 | VERIFIED |
| `EnvironmentState.record_action` appends every tool call to `session.tool_history`; `query_tool_history(name)` answers "was this called" and **gates later tools** | same · `tools.py:83-92` | Apache-2.0 | VERIFIED |
| **the audit rule to copy verbatim:** per-call JSONL with `prev_sha256` + `seq` under an exclusive lock and fsync; *"A non-zero exit fails the call, so a call that can't be logged doesn't run"*; `reconcile.py` names `AUDIT_CHAIN_BROKEN` and `UNAUDITED_GATEWAY_CHANGE`. **Its own caveat travels with it — the chain proves order, not origin** | `matt-spellcaster/okta-mcp-gateway` @ `83db4be5` · `scripts/audit.py:12-14, 89, 92-93`; README:95-102 | not stated | VERIFIED / licence unknown |
| "allowlist at discovery AND execution" — `tools/list` must also be filtered, or the model sees the write tool and tries it | MCP gateway products (Zuplo, Permit.io, Bifrost, Cordon) | various | ASSERTED (vendor pages) |

#### Recommended change (diff-shaped)

- **R1 — ToolAnnotations on all 13 tools.** Add `annotations=` and `meta=` to each `@srv.tool`
  site in `build_server()` (:1417-1590). Read tools (search, work, candidates, ws_status, my_uses,
  brief) → `readOnlyHint=True, openWorldHint=False`; ws_open/record_use/hunt_request_add/
  propose_promotion → `readOnlyHint=False, openWorldHint=False`; admit/acquire/hunt →
  `openWorldHint=True`. No tool body changes; `EXPECTED_TOOLS` stays 13. **The cheapest item in
  the round.** [VERIFIED]
- **R2 — `litkb_version` tool + build stamp.** Add `_build_id()` (sha256 over
  `pipeline/litkb/**/*.py` + `git rev-parse HEAD` + the applied migration tip), freeze it at
  import as `_STARTED`, and add a 14th tool that re-computes and reports `stale=true` when they
  differ. `EXPECTED_TOOLS` (`test_litkb_p8.py:120`) becomes 14 — a deliberate edit, as that test's
  docstring requires. [VERIFIED]
- **R3 — fail-closed audit middleware.** `class _Audit(ServerMiddleware)` passed as
  `middleware=[_Audit()]`. Record: `ts, seq, prev_sha256, method, request_id, tool, args_sha256,
  agent, session, ws, build, phase, refused`. **Arguments are HASHED not stored** — a
  `litkb_record_use` argument carries the quote, and `_out` exists because transcripts are sinks.
  Cost: `fcntl.flock` is POSIX and must be ported to `msvcrt.locking` or single-writer `O_APPEND`
  on this Windows box. **Reads become auditable for the first time.** [VERIFIED]
- **R4 — move the role allowlist from agent frontmatter to the SERVER (the headline change).**
  `ROLES: dict[str, frozenset[str]]` and `class _RoleGate(Extension)` refusing `tool-not-in-role`,
  passed as `extensions=[_RoleGate()]`; keyed on `LITKB_ROLE`, absent → today's full surface.
  **Belt and braces:** also give `build_server(role=None)` a registration filter, because an
  interceptor wraps `tools/call` only and never `tools/list`, so the model still sees the whole
  menu. [MIXED]
- **R5 — expose `review_check` as a read tool so the writer can grade itself.** A 15th tool
  `litkb_review_check(path, text)` as a thin read wrapper over `review_check.check(conn, …)`,
  exactly as `litkb_brief` wraps `brief.build`. **No rule changes — an existing rule becomes
  reachable.** Today the review-writer has no Bash tool, so the agent required to pass K1 cannot
  ask whether it does. [VERIFIED]
- **R6 — record the ROLE on every write.** One line: `a = norm_label(agent or
  os.environ.get('LITKB_ROLE') or os.environ.get('LITKB_AGENT') or '')` in `_labels()` (:253).
  [VERIFIED]

#### Local test set

- **REAL harness:** `qc/test_litkb_p8.py:70` `mcp_roundtrip`, `:105` `tool_names()`, `:120`
  `EXPECTED_TOOLS`.
- **REAL rows/files:** the 13 tool objects and each tool's connection kind (`_conn("reader")` vs
  `_conn("writer")` at :140); the three `.claude/agents/*.md` frontmatter `tools:` lines;
  `.mcp.json` `mcpServers` + env; `litkb.hunt_requests` agent histogram (claude 83 / lit-scout 18
  / taskC-opus 2); `litkb.use_versions` agent histogram; `Reports/gold/` (p5, p8, stage5);
  `Reports/LITKB_AGENT_HOOK_PATH_2026-09-21.md`; `Reports/LITKB_SCOUT_LAUNCH.md`.
- **CONSTRUCTED negatives:** N1 (`litkb_acquire` called under `LITKB_ROLE=review-writer`), N3 (a
  review citing `[notawork p.3 #00000000-…]`), N4 (a role profile naming a nonexistent tool), N5
  (a tmp COPY of the package on PYTHONPATH with one byte changed — **the real package is never
  touched**), N6 (an unwritable `LITKB_AUDIT_DIR`), N7 (one JSONL line deleted), N8
  (`litkb_acquire` annotated `readOnlyHint=True`).

#### Kill criteria

- **R1:** a test derives each tool's expected `readOnlyHint` **from which connection its
  implementation opens** and asserts the annotation agrees. Mutate `litkb_acquire` to
  `readOnlyHint=True` → must go RED. **A test that only reads the annotations back is not a gate
  and does not count.**
- **R2:** call `litkb_version` through the p8 in-memory harness, mutate a `.py` in the tmp package
  copy, call again, assert `stale == True`. Mutation: delete the re-digest so `_version` returns
  the frozen stamp → must go RED.
- **R3:** (a) point `LITKB_AUDIT_DIR` at an unwritable path, call any tool: the result must be
  `refused: 'audit-unavailable'` **AND the DB row count must be unchanged** (the body never ran);
  mutation "swallow the write error" → RED. (b) Delete one JSONL line: the reconcile check must
  report **BOTH** `AUDIT_CHAIN_BROKEN` at the gap **AND** `UNAUDITED_WRITE` for the orphaned
  `use_versions` row — one finding without the other means the check measures one thing and
  reports two.
- **R4:** (a) N1 must return `refused: 'tool-not-in-role'` AND `litkb.acquisition_attempts` must
  gain no row; mutation "log and pass through" → RED. (b) **The one that matters:** port
  `validate_toolsets` as `validate_roles(tool_names())` — add a nonexistent tool to a role and it
  must go RED, because a silently-ignored name is precisely the failure mode that would let a role
  quietly widen after a tool rename.
- **R5:** run N3 against the EXISTING CLI first — `review_check.py:357` must fire — **before
  wrapping anything**; a gate that does not fire today cannot be trusted underneath a new tool.
  Then via the tool: mutation "wrapper returns [] on any exception" → RED.
- **R6:** a row written with `LITKB_ROLE=lit-scout` and `LITKB_AGENT=claude` both set must land
  with `agent='lit-scout'`. Swap the precedence → RED.

#### Where it lands

**R1, R6 and R5 before S5** — R1 and R6 are one-liners, and R5 lets the S5 review-writer close its
own loop, which directly serves S5's `K1=PASS`. **R2 in S5 or S7**: it closes the staleness hole
that the per-session protocol currently handles with a human "/mcp reconnect" step, and it is the
same mechanism L10 proposes for the doctor — **one fact, one home: build ONE code stamp and let
both read it** (see §2.2). **R3 and R4 in S7**, R4 gated on the open question below.

**The one thing that could reduce R4 to a launch-config change, and L11 could NOT verify it:**
whether Claude Code spawns one MCP server process per subagent or shares one. If shared,
`LITKB_ROLE` cannot differ per role in-session and the server-side gate only bites under per-role
headless registrations (`--strict-mcp-config`). `Reports/LITKB_SCOUT_LAUNCH.md` is named by
`lit-scout.md:9-15` as holding a prior probe of the related question and **should be read before
R4 is designed further.**

---

## 2. Cross-stage findings

### 2.1 Mechanisms several crawlers converged on, independently

**(a) The leading open system in this field verifies less than litkb does — five crawlers, five
different stages.** PaperQA2 was read by **L1, L2, L3, L8 and L11** for five different purposes
and each found it *weaker on verification*: L2 — `_map_fxn_summary` performs no byte-level
verification of any quoted span, its "evidence context" is LLM prose about a chunk; L8 — the
citation unit is a chunk NAME plus an LLM summary with an integer score, no page, no offsets, no
cell; L3 — `CITATION_KEY_CONSTRAINTS` constrains the key space and nothing re-reads the source;
L11 — `strip_citations` is a lossy regex. Only L1 took something positive from it (the
relevance-score normalisation, which is genuinely careful: `8/10`, `4/5`, floats, misnamed keys,
default 5 on failure). **Corroborated by L6 on a second system:** ScholarQA's `step_select_quotes`
accepts whatever the LLM emitted with only `len(quote) > 10`. **Implication:** nothing in §1
should be framed as litkb catching up. The work is extending litkb's own mechanism (to a
ligature, to a cell, to a synthesis), not importing someone's.

**(b) "Say you do not know" as a typed, refusing state — L1, L5, L6, L10, L12.** SnowBallSLR's
`estimable=False` + a reason (L1); OpenCitations' "an anchor is shown or it is a candidate", with
no confidence field anywhere (L5); sciente's "a needed NI leaves the domain null and records which
questions were missing" and MultiVerS's NEI floor (L6); barman's `NON_CRITICAL_CHECKS` and
pgBackRest's per-file reason enum (L10); inspect_ai's typed `LimitExceededError` and
`incomplete_action` declared as DATA (L12). **All five are CLAUDE.md §3.5 written in someone
else's code**, and all five distinguish *withheld* from *negative*. Two crawlers add the sharper
form: **a warning that turns nothing red is not a gate** (L1 on SnowBallSLR's two-arm
independence warning; L6 on sciente's `softFail` being opt-in, threshold-declared and
row-flagged).

**(c) Numeric containment is the one support check writable without a model — L3, L6, L8.**
FActScore's `postprocess_atomic_facts` discards a fact introducing a number absent from its source
(L3); sciente's `support.ts` states "an explicit contradiction in the numbers overrides the cues,
because a counted proportion is not a matter of phrasing" (L6); TAT-QA separates `scale` from the
answer string because the cell text is not the value, and TEDS is named as the *wrong* rule
because normalised Levenshtein calls `0.87` vs `0.37` ~0.75 similar (L8). **Three crawlers, three
stages, one rule.** See §2.3(a) for the one-fact-one-home problem this creates.

**(d) Cap the citations and measure precision — L3, L6.** ALCE's leave-one-out overcite test and
`at_most_citations=3`; LongCite's `merged_citations[:3]`; SciFact's `MAX_ABSTRACT_SENTS`. Both
crawlers note that litkb has **no citation precision notion at all**: a sentence carrying four
citations passes if one verifies.

**(e) Identity is a recomputed content digest, never a declared version string — L6, L7, L10,
L11, L12.** trustyuri embeds `sha256(content)` in the identifier and verification is recomputation
(L6); sandcrawler names its TEI fixture by its own sha1, and a cassette's identity is its recorded
bytes (L7); Django's autoreload enumerates the modules actually loaded and the process measures
itself — with the explicit note that **mtime is wrong because a checkout rewrites it** (L10);
PaperQA2 stamps `config_md5` into the session record (L11); inspect_ai hashes the fields that
determine the run and recomputes the same id from the log the run produced (L12). **litkb has one
frozen literal, `VERSION = "0.1.0"`, and two crawlers independently proposed replacing it with the
same digest.** See §2.3(b).

**(f) A gate is proven by a table of known-bads, one of which must NOT fire — L2, L3, L6, L7,
L9, L10, L12.** restic's `TestCheckerModifiedData` is the cleanest form: a table of `damage
func()` cases **including a row asserting the checker must stay silent on a benign transient**
(L10). BIG-bench plants a canary AND ships the task that proves the canary is detectable — the
marker is not the gate, the detector is (L12). vcrpy's `play_counts` and sandcrawler's
`assert len(responses.calls) == 1` make an unplayed or extra interaction detectable (L7). L2, L3
and L6 each built their own constructed-mutation sets from real rows. L9 adds the version litkb
most needs: **a guard that has only ever fired on constructed rows in a test suite has not been
shown to fire on a live-shaped row.** This is CLAUDE.md §3.4c, seven times over.

**(g) The shipped default is not the measured configuration — L2, L5, L7.** Crossref's own
`match_config.py` constructs `Matcher(0.4, -1, …)`, i.e. `min_similarity = -1`, so **the
distributed default is SBM, not the SBMV the project is famous for**; the published thresholds
live in analysis notebooks (L5). Hypothesis's `matchQuote` carries a doc comment promising a
minimum quality threshold **the code does not implement** (L2). CPython's `difflib` defaults
`autojunk=True`, which on a 26,695-character block junks every space and common letter (L2).
rapidfuzz's `_partial_ratio_impl` can never return a span longer than the quote (L2). paper-qa's
record mode differs between local and CI by one line (L7). **Read the constructor, not the
README** is the rule all three crawlers arrived at.

**(h) An independent witness outside the artefact — L7, L9, L10, L12.** A recorded cassette
instead of an authored stub (L7); a second session instead of the admitter (L9); Windows Task
Scheduler's `NumberOfMissedRuns`, which can see a night the CSV structurally cannot (L10); a
heartbeat row that a killer cannot forge (L12). In every case the crawler found that litkb's
current witness is the *same actor that produced the thing being witnessed*.

**(i) Three-state identity, never a silent binary — L1, L5, L6, L8.** ASySD's
`true_pairs`/`maybe_pairs`/neither, where a `maybe` is held for a human (L1); litkb's own
`resolved`/`ambiguous`/`unresolved` on references (L5); UNDETERMINED as a first-class verdict
(L6); HOLD on an ambiguous cell address (L8). All four map onto CLAUDE.md §3.6's IGNORE: **an
unsure item is never assigned to a class.**

**(j) The citation graph is already in the database and reachable from nowhere — L1 and L5, the
same data, two different blockages.** L1: 630 `candidates` rows with `source='citation'`, all
`workstream_id IS NULL`, invisible to `litkb_candidates`'s workstream filter, and the tool is not
in the scout's list anyway. L5: `citation_edges` has exactly one production reader — its own
writer's counter — and `citation_mentions` carries the citing sentence for 969 of 969 rows with no
reader at all. **These are one build, not two** (§2.3(c)).

### 2.2 Contradictions and tensions between crawlers

**(a) Three crawlers put the SAME numeric rule in three different homes.** L3-R1 puts
`magnitude-not-in-quote` in `review_check.py` (K1, severity fail); L6-R3 puts an identical rule in
a new `synthesis_check.py` (K3); L8 puts `numeric_*` counters in `litkb_acceptance.py` reading the
database. All three are right about their layer and **all three writing their own implementation
is exactly the one-fact-one-home bug CLAUDE.md §3.3 forbids.** Resolution the builder must adopt:
**one implementation** (a shared helper beside `review_check`'s existing guards), **three call
sites**, and a test that the K1 and K3 paths agree on a fixed input — the same shape as
`test_the_sql_and_python_newline_canonicalisations_agree`. L3 already points at the precedent by
insisting the guard and the mutator share one definition of "the sentence region before the
quote".

**(b) Two crawlers independently propose the same code stamp.** L10 wants `CODE_STAMP` =
sha256 over the litkb modules in `sys.modules` so the doctor can say "reconnect"; L11 wants
`_build_id()` = sha256 over `pipeline/litkb/**/*.py` + git HEAD + migration tip behind a
`litkb_version` tool. **Same fact, two proposed homes.** Build ONE (`pipeline/litkb/` owns it)
and let both the doctor check and the MCP tool read it. Note the two crawlers disagree on
ingredients — L11 includes git HEAD and the migration tip, L10 argues for content-only because a
checkout rewrites mtimes (not HEAD). **Content digest + HEAD + migration tip is the union and
satisfies both**, provided the *comparison* the doctor makes is content-to-content.

**(c) Two crawlers, one citation-graph build.** L1-D3 (un-orphan the candidates, add the read
tool to the scout) and L5-R5 (give `citation_edges` a reader) are the same subsystem from the
discovery side and the anchoring side. Building them separately risks two readers with different
visibility rules over the same rows. Build one reader; expose it both ways.

**(d) CRLF folding: a real divergence, correctly reasoned on both sides.** L12 says prompt and
manifest hashes use litkb's CRLF-folded `_register_sha256` convention (the false red it was
written to fix must stay fixed). L7 says **cassette** hashes must be raw BYTES and the files
marked `binary` in `.gitattributes`, because a recording is not authored text. **Both are right,
and the rule has to be written down**: authored text under `* text=auto` → folded; recorded bytes
→ raw + `binary`. Nothing in the tree states this today, and the next builder will pick one.

**(e) MiniCheck is recommended by L3 and declined by L2 — for different gates, not in
conflict.** L2 rules it out as a *quote↔block identity* gate (it is a statement↔quote entailment
model with no character-level diff); L3 proposes it as a never-gating third signal beside K2's
verdicts; L6 does not use it at all. The consistent reading: **MiniCheck can make K2's SUPPORTED
rows auditable and can never replace either K1's byte test or K2's overreach judgement.** L3
states the expected null result in advance: the planted causation will probably score
*supported*, and that result is the documented proof of the limit.

**(f) L5 corrects a live ruling; nothing contradicts the correction.** The
`litkb-second-formula-decoder` aside that "all 643 references are unanchored" re-derives to 17
anchored / 13 edges, and the ladder is at its ceiling on the 7.3% of files stage 6 has run on. L1
reads the same table for its citation arm (347 distinct cited DOIs, 332 absent) and is consistent
with it. **The plan text should be corrected where it restates the aside.**

**(g) One crawler's "already fires" is another's "never fired".** L10 fired three corrupt-dump
mutations on a real dump this session and found S7's cheap check blind to all three. L9 found that
litkb's approve guards fire — but only on constructed rows in a test suite, never on a live-shaped
row, and no session report records a fired output. **These are the two halves of the same
standard**, and §4's referee protocol below applies both.

### 2.3 One internal twin-drift risk, named by L4

`server._rrf` and `pipeline/litkb/index/fuse.py:rrf` are **two live implementations of the same
k=60 formula**. L4 requires the new harness to assert they agree on a fixed input *before* it
scores anything, "or one-fact-one-home is already broken before anything is added." The same
hazard shape (migration 0014's D1 twin-drift) is why L4's stored-column change carries a
`norm_text IS DISTINCT FROM norm_search_text(text)` check with a 372,305-row blast radius.

---

## 3. What nobody verified; licences; compute

### 3.1 What nobody verified (the union of the twelve §6 sections)

**Not run, anywhere.** No crawler ran pytest, `qc/check.py`, any instrument, any migration, or any
wire call to a registry. Every litkb number in this synthesis is a read of a tracked file or a
`litkb_reader` SELECT, and **every recommendation is a design until a referee runs it**. Three
crawlers say this in their own words (L5 §6.1, L7 §6.1, L12 §6.1) and one (L3 §6) names its own
measurements as the proposer's and therefore not counted.

**Effect sizes that are synthetic or absent.**
- SnowBallSLR's 0.450 → 0.906 stopping improvement is measured on **generated citation DAGs**; its
  own `VALIDATION_REPORT.md` says the real 493-record component "is used to establish structure,
  never accuracy". **UNVALIDATED on real data** (L1).
- Every published benchmark number in L4 (MTEB, bge-reranker gains, ColBERTv2 recall) — no
  leaderboard read, no benchmark run. Anything about model *quality* there is **ASSERTED**.
- MiniCheck's LLM-AggreFact numbers are images in a README (L3).
- ALCE's and LongCite's reported scores — not checked, not relied on; only the algorithms are
  cited (L6).
- gmft's and camelot's accuracy against litkb's own PDFs — no benchmark run (L8).

**Specific unknowns that block a build.**
- **Whether Claude Code spawns one MCP server per subagent or shares one** (L11 §6.1). This
  decides whether L11-R4 bites in-session or only under per-role headless launches. *Read
  `Reports/LITKB_SCOUT_LAUNCH.md` first.*
- **Whether the frontmatter `tools:` list is enforced by this CLI version** (L11 §6.2, L1 §6).
- **Whether the S4 prompt's embedded work key is a violation** — the measurement is certain, the
  ruling is Kam's (L12 §6.3).
- **Whether the 0025 five-spelling expansion is the right rule for `record`** — L2 measured that
  it fixes 120/120 refusals but did **not** measure whether any of the four wrong spellings occurs
  as real text elsewhere in the corpus. That measurement belongs to D1's referee.
- **Whether the 227 non-joining gold positives are the same references under a different stem**
  (L5 §6.7) — R0 exists to settle it.
- **`NumberOfMissedRuns` semantics under `-StartWhenAvailable`** (L10 §6.1) — someone has to miss
  a night on purpose and read the counter.
- **The two-pytest deadlock, empirically** (L10 §6.3) — read from `conftest.py:106`, not run.
- **Whether `pg_stat_activity.application_name` is visible to `litkb_reader` for other users'
  backends** (L10 §6) — the probe returned zero lock rows, so the join was never exercised.
- **Whether `litkb_test_wmatching` / `litkb_test_wspendrule` should exist** — found in
  `pg_database`, creator unknown (L10 §6).
- **Whether the 386 quote-less uses are a recording failure or an intentional shape** — L2 counted,
  did not diagnose; `use.py:40-42` says it is Kam's open question.
- **Whether any of the 372,305 blocks carries a zero-width or bidi character** — sciente strips
  them explicitly, litkb canonicalises only newlines, and the query was not run (L6 §6). **It could
  make a legitimate quote unquotable and nobody has looked.**
- **Whether `do_cell_matching` was on for litkb's existing 3,408 tables** — not recorded anywhere
  (L8 §6).
- **Whether the two `prepared` promotions are stale** (L9 §6).
- **Whether `work_versions.state='rebased'` is live on this database** (L9 §6).
- **Cassette size** — recording real PDF bodies for 19 rows could be tens of MB in a repo that
  already tracks binary fixtures; the body-size cap is undesigned (L7 §6.6).
- **The 13-gram guard's false-positive rate** against `main_works` titles (L12 §6.4).
- **A per-hunt budget VALUE** — L12 did not compute the distribution of `seconds` over the 89
  ledger rows, and says a bound chosen without that distribution is a number, not a gate.

**One bookkeeping slip, self-reported (L7 §6.7):** four commit-pointer API URLs already on
`blacklist-round2.txt` were re-fetched in one batch before the list was checked URL-by-URL. They
returned the same SHAs already recorded; no repository tree or source file on the list was
re-read.

**Closed-source systems nobody can pin:** Connected Papers, ResearchRabbit, Elicit, Rayyan,
Covidence, SciSpace, Semantic Reader, Consensus, scite's model, the MCP gateway products. Every
statement about them in the reports is ASSERTED from vendor pages, and two crawlers (L1, L2)
deliberately did not fetch them rather than produce marketing-derived claims.

### 3.2 Licences, AS STATED (never as read, unless noted)

**Read from an actual LICENSE file at the pinned sha — VERIFIED:** Crossref
`reference-matching-evaluation` **MIT** ("Copyright (c) 2018 Crossref", L5); PubTabNet **Apache
2.0** (read in `src/metric.py`'s header, L8); hypothesis/client **BSD-2-Clause** (LICENSE file —
note the GitHub API reports NOASSERTION, L2); ALCE **MIT**, FActScore **MIT**, MiniCheck
**Apache-2.0** (L3); sciente-evidence-evals **Apache-2.0**, LongCite **Apache-2.0**, ScholarQA
**Apache-2.0**, SciFact **CC BY 4.0 / ODC-By 1.0** with the code section in LICENSE.md, MultiVerS
**MIT**, AttrScore **MIT** (L6); inspect_ai **MIT**, hydra **MIT**, mlflow **Apache-2.0**,
SWE-bench **MIT**, pydantic-ai **MIT**, airflow **Apache-2.0**, openai/evals **MIT**,
lm-evaluation-harness **MIT**, BIG-bench **Apache-2.0** (L12, all LICENSE files read at the sha).

**Stated but not read — ASSERTED.** L7 states plainly that it read no LICENSE file at any pinned
sha: vcrpy MIT, pytest-recording MIT, responses Apache-2.0, betamax Apache-2.0, semanticscholar
MIT, paper-qa Apache-2.0, habanero MIT, sandcrawler **GPL-3.0**, translation-server **AGPL-3.0**,
pyalex MIT. L10 read only Homebrew's: barman **GPL-3.0** and borgmatic **AGPL-3.0** are asserted
and are recorded **design influence only, no code copied** — which matters, because those two are
copyleft. L8's docling/camelot/gmft/quantulum3/TAT-QA MIT, pint BSD-3 and paper-qa Apache-2.0 are
asserted from metadata the GitHub API rate-limited mid-pass. L9's SPDX ids come from GitHub's
licence endpoint, not the file: Open Library **AGPL-3.0**, WikibaseIntegrator MIT, prov MIT,
eventsourcing BSD-3; **fatcat, oc_ocdm and audit-trigger return NOASSERTION**. L11 read code, not
licences, for zotero-mcp, paper-search-mcp and okta-mcp-gateway — **all three "not stated in the
file read"**.

**No licence at all, and it matters:**
- **litsearchr** and **citationchaser** state none on GitHub and show no SPDX id (L1). litsearchr's
  last push is 2021-04-07. **L1-D1 re-implements `check_recall`'s method from its published
  description rather than copying code — keep it that way until a licence check is done.**
- **junwang4/causal-language-use-in-science** states none (L3). The four *labels* are taken; the
  BioBERT weights are explicitly **not** deployed (out of domain, no licence).
- **robotreviewer** and **SciClaim** — `LICENSE` is a **404 at the pinned sha** (L6). Mechanism
  verified, licence not. Only the idea is taken from each.
- **anystyle** — not in `finder.rb`'s header, "widely reported BSD-2" (L5). ASSERTED.
- **scicite** — README only, no licence (L5).

**The one split-licence trap:** FlashRank's **code is Apache-2.0 while `flashrank/Config.py` line
2 states the HuggingFace weights repo is CC-BY-SA** (L4, quoted from source). If the reranker
lands, that is a licence fact litkb carries with the model, not with the code. Similarly
MiniCheck's repo is Apache-2.0 but **the 7B checkpoint is separately restricted** ("contact
company@bespokelabs.ai for commercial use") — the 770M `flan-t5-large` one is the one in scope.

**Nothing in §1 proposes vendoring third-party code.** Every recommendation is a mechanism
re-implemented in litkb's own Python or SQL. Where a copy would be tempting (vcrpy's ~200 lines,
pytest-recording's ~40-line socket guard, Crossref's SBMV file), the licence must be read from the
file before a line is copied.

### 3.3 Compute: the 4 GB T2000, and the Colab question

**Kam's standing rule, as recorded in this machine's session memory: all litkb work is local — no
Colab.** That makes "free Colab" **not an available fallback for litkb** without a fresh ruling,
and it converts every GPU-shaped proposal below into either a CPU design or a blocked one.

| build | compute | verdict against a 4 GB T2000, local |
|---|---|---|
| L2 D1–D5 (quote ladder, difflib) | stdlib, CPU, microseconds | **fits.** difflib is the only fuzzy library installed on this machine |
| L4 leg-3 `<%`, stored column, SQL fusion | Postgres only | **fits.** +~65 MB on a 314 MB table |
| L4 chunking from blocks | CPU, one pass | **fits** |
| L4 **FlashRank reranker** | **ONNX + tokenizers, no torch, CPU** | **the only reranker path that fits.** L4 chose it precisely because P7 §4 measured bge-m3 finishing on the T2000 with **120 MiB spare on a 4,096 MiB card** read at 102 MiB free earlier the same day |
| L4 vector leg / HNSW build | pgvector `halfvec` (already the column type); HNSW build wants `maintenance_work_mem` | **fits**, but the encoder that fills it is the T2000 constraint P7 already hit |
| L4 HyDE | one LLM call per query | fits (network/model call, not local GPU) |
| L3-R6 / L2-F9 **MiniCheck** (`flan-t5-large`, 770M) | L3: "model download + GPU assumed; **CPU not documented**"; L2: "transformer inference (GPU)" | **UNDETERMINED on this box.** 770M in fp32 is ~3 GB of weights before activations. Must be measured CPU-only before it is proposed again; Colab is not available under the standing rule. It is a never-gating signal, so **if it does not fit, nothing is lost** |
| L3-R1/R2, L6-R3 numeric + cue guards | regex, CPU | **fits** |
| L3 ALCE leave-one-out | needs `google/t5_xxl_true_nli_mixture` (11B) | **out of reach.** This is exactly why both L3 and L6 put over-citation in the K2 *rubric* as an editorial class, not in a counter |
| L3 junwang4 BioBERT | BioBERT + a `bert_sklearn` fork | **not deployed** — out of domain, no licence, and §3.4c would require scoring it |
| L6 synthesis_check | pure Python + SQL | **fits** |
| L7 cassettes + socket guard | stdlib | **fits**; the open cost is repository size, not compute |
| L8 cell evidence | SQL + a trigger branch | **fits** |
| L9 review verbs, provenance | SQL | **fits** |
| L10 doctor | `pg_restore` (132.8 s weekly), 3.34 s nightly | **fits**; the digest over 59 files / 1,242 KiB measured **below timer resolution** |
| L11 annotations, version tool, audit, role gate | stdlib + a per-call fsync | **fits**; the unmeasured cost is stdio latency (L11 §6.7) |
| L12 run protocol | hashing + a heartbeat row | **fits** |
| L5-R4 stage 6 over the corpus | **network, not GPU**: ~1 s/reference at the Crossref pacer, ~8,800 references, **~2.5 h** | a wire-cost decision for Kam, not a compute one |

**Net:** of 83 recommended changes, exactly **two** have any GPU exposure (FlashRank, which is
CPU-ONNX by design, and MiniCheck, which is UNDETERMINED and never-gating), and **one** is out of
reach entirely (ALCE's 11B entailment, already demoted to a rubric class by both crawlers who
wanted it).

---

## 4. A proposed ordering, and the referee protocol

Ordered by (local gold in hand) × (cost) × (effect on the finish line). The finish line is
`litkb-finish-line`: a cold session discovers, drops off before reading, hunts every drop-off to a
named terminal state, acquires and OCRs, records verbatim quotes the database verifies, writes a
review passing K1 with K2 adversarial, and produces a synthesis where every inference cites a
verified line or is labelled (K3).

### Wave 0 — defect fixes, real gold in hand, hours of work, no design risk

These are not designs. Each is a measured defect with real rows behind it, and each removes a
blocker from the finish line rather than adding a mechanism.

| # | build | gold in hand | effect on the finish line |
|---|---|---|---|
| 0.1 | **L2-D1** ligature expansion in `locate_in_text` + trigger | 120 of 120 real blocks refuse today; 35 evidence rows as regression | **record** stops rejecting quotes the search leg just served |
| 0.2 | **L1-D3 + L5-R5** un-orphan the citation candidates and give the graph a reader (ONE build, §2.2c) | 630 rows, 350 with a DOI; 13 edges; 969 mentions | **discover** gains an arm litkb already paid for |
| 0.3 | **L4** leg 3 `%` → `<%` | 3 timed live queries; 75 reference-only negatives | 14.3 s → 1.6–5.4 s per search; every stage downstream is faster |
| 0.4 | **L5-R3** one index for the anchor | the 4 invariant-violating rows | 4 of a possible 17 edges recovered; 4 false acquisition leads removed |
| 0.5 | **L11-R1, L11-R6** annotations on 13 tools; role on every write | the 13 tools; the 83/18/2 agent histogram | the web-blind boundary becomes machine-readable; drop-offs name the role |
| 0.6 | **L8** honest refusal for `table` in `DEFAULT_KINDS` | 3,408 tables with `text=''` | stops advertising an unreachable kind |
| 0.7 | **L12** freeze on the DB clock; the piped-gate protocol test | `_scout_freeze:803`; FIRST_WORK bounded outcome 6 | removes two known ways a run's evidence lies |
| 0.8 | **L10** soak start sentinel (a writer change) | 3 real soak rows | every crashed night between now and S7 stops being invisible |
| 0.9 | **L9-R6** fire the approve guards on live-shaped rows in the next second session | P9's five guards; the live row set | costs one command; converts "verified by inspection" into a pasted error |

### Wave 1 — S5 blockers (the run must not launch without these)

| # | build | why it gates S5 |
|---|---|---|
| 1.1 | **L12** the run protocol: identity hash, working-time budgets, **contamination by glob + 13-gram**, run_id + resume, immutable frozen fields, heartbeat, the spec as the first artefact, attempts as data | S5's Work item is literally this document; and the prompt S5 will run from is untracked and **carries a work key today** |
| 1.2 | **L3-R1** magnitude in K1; **L3-R3** citation-outside-this-hunt | closes one of the four overreach classes deterministically; makes a hole **already in the corpus** visible |
| 1.3 | **L3-R4, L3-R5** K2 rubric classes + a mutation that is not signposted | S5 (c) requires K2 to fire on a planted causation; the current plant is catchable by regex |
| 1.4 | **L2-D2** match rung on the row; **L2-D4** cross-page refusal; **L2-D5** prefix on refusal | a reader of S5's promotion report cannot tell rung 1 from rung 2 today; 1,202 real continuations cannot be quoted at all |
| 1.5 | **L11-R5** `review_check` as a read tool | the writer that must pass K1 cannot currently ask whether it does |
| 1.6 | **L4** stored column + **the BEIR harness** | the harness gates every later retrieval change by reproducing the old numbers first |
| 1.7 | **L1-D1** discovery recall counter; **L1-D5** stop rule with a number | S5 counts drop-off outcomes and nothing about whether they were the right papers |

### Wave 2 — S6 (the synthesis and K3)

**L6-R1 … R7** as one build, plus **L6-R8** into `docs/LITKB_CODEX_PROMPT.md`. R1 is the one that
must not slip: the plan's own S6 (c) laundering kill **decays the moment the first promotion
merges**, so K3 must query the workstream's own ledger from day one. The numeric rule here is the
same implementation as 1.2 (§2.2a).

### Wave 3 — S7 (ops), and the case for pulling L7 earlier

**L10** doctor (registry + tags + `--only`, dump age/size/verify, worker lease,
consecutive-green clock, scheduler witness, fixture, timeout) and **L11-R2/R3/R4** (one shared
code stamp per §2.2b, fail-closed audit, server-side role gate) are S7 as the plan has it.

**L7-D1…D3 has a real claim on being earlier.** The plan requires an independent referee per rung
class for S4.5–S4.7, and the measured cost of refereeing live is 560.5 s for 14 rows against 4.5 s
for 19 in replay, against hosts already refusing this client. **If any S4.5–S4.7 referee round is
scheduled before S7, the cassette work should precede it.**

### Wave 4 — after S5, each refereed, each UNVALIDATED until then

**L5-R0 → R2 → R1** (the crosswalk must come first or nothing can be scored); **L5-R4** is Kam's
spend decision and is the only change that can move the anchored count. **L1-D2/D4/D6/D7/D8.**
**L8** cell-addressed evidence (schema + trigger branch + counters). **L9-R1/R2** decision log and
refuse verb, then **R3**, then **R4/R5** (R5 gated on `litkb-from-file-version-state`). **L4** SQL
fusion, chunks from blocks, reranker, then HyDE. **L7-D6** cache fold, last, because it touches
the reference-resolution path L5 depends on.

### The referee protocol, per build (CLAUDE.md §3.4c)

Every item in waves 1–4 is a **relayed design**: a mechanism read in another repository is a design
until it has run on litkb's rows. The protocol, stated once here so no build re-derives it:

1. **The builder is never the proposer.** The crawler that proposed an item (L1…L12) may not build
   it, and **this synthesis may not referee anything**, having ranked them.
2. **The referee re-runs the claim on the REAL rows §1 names**, positives and negatives both, on
   its own worker database — **one pytest process per worker DB, ever** — and scores blind where
   the item says BLIND.
3. **The kill criterion must be SHOWN TO FIRE on a known-bad before the build counts.** A gate that
   has never fired is not known to work. Where §1 says a kill "already fires" (L1-D2's two
   estimators, L10's three dump corruptions, L2's 120/120, L5-R1's commit `8829558`, L7-D6's
   utf-8-replace), the referee re-fires it and pastes the output.
4. **A mutation that ERRORS rather than answering worse is reported as DID-NOT-FIRE** (the lesson
   in `admit/front.py:150-155`), and the harness is restructured rather than the result accepted.
5. **A design validated on synthetic or constructed input only says so in those words**, and the
   plan line keeps the word UNVALIDATED until the referee's report is tracked under `Reports/`.
   This applies now to: L3-R4 (no real review hedges), L3-R7, L6's whole §1.7 (S6 has zero measured
   pain), L9's promote-side halves (0 promotions committed), L10-N6 (not run), L11's six
   constructed negatives, L12's ten constructed negatives.
6. **Numbers a proposer produced about its own prototype are not acceptance evidence.** Explicitly
   in scope: L2's ladder table (35/35, 8/8, 9/9), L3's 0/25 and 4/25, L4's re-anchoring matcher and
   its 45/60, L1's CONSTRUCTED 12% topic recall.
7. **The Codex read is OWED wherever it did not run** (§0.3), and a report that consumes a
   loop-tooling conclusion from round 4 says in those words that no different-model-family read
   was applied to it.

---

## 5. Verified vs asserted

### 5.1 Verified — read in source at a pinned sha, or measured on litkb's own rows

**litkb's own state.** Every number in §1's "litkb today" paragraphs: read as `litkb_reader` on
localhost:5433 or from a tracked file on 2026-09-22, by the crawler named. The load-bearing ones:
487 works / 372,305 blocks / 103 hunt_requests (L1); 421 use_versions with 35 carrying evidence,
of which 20 verify raw and 35 canonical (L2); 13/13 SUPPORTED on the run-2 review with 4 editorial
defects (L3); one search = 16.0 s of which trigram = 14.3 s for 0 rows, `norm_search_text` = 20.54 s
over the corpus (L4); 643 references / 17 anchored / 13 edges / 15 DOIs in the overlap / 17 of 233
files (L5); 8 verified triples per proving run, 4 run-1-only (L6); 14 rows in 560.5 s live vs 19
in 4.5 s replay (L7); 3,408 table blocks with `text=''`, 230,329 cells, 127,180 numeric (L8); 15
approved / 1 proposed / 18 machine-refused / 263 of 263 file versions promoted with no promotion
(L9); 10 dumps 187,576 B → 97,770,680 B, one restore ever at 132.8 s, 14 worker DBs (L10); 13
tools to every client, agent histogram 83/18/2 (L11); 103 drop-offs over 8 workstreams, 18 columns
with no run id (L12).

**External mechanisms.** The tables in §1 mark each row. The mechanisms VERIFIED in source at a
pinned sha include: SnowBallSLR's refusals, litsearchr's `check_recall`, ASySD's three classes,
openalexR's snowball, buscarpy's hypergeometric stop, ASReview's stoppers and queriers (L1);
hypothesis's `matchQuote`, difflib's `autojunk` default, rapidfuzz's window cap, fuzzysearch's
separated budgets, PaperQA2's non-verification (L2); FActScore's numeric containment, ALCE's
leave-one-out, RAGAS's LLM decomposition, junwang4's four labels, OpenScholar's post-hoc insertion,
STORM's docstring-only citation rule (L3); pg_trgm `<%` measured live, pgvector-python's RRF and
cross-encoder examples, FlashRank's imports, docling-core's `excluded_embed`, BEIR's `hole`,
HyDE's mean vector, SPECTER2's paper-level input (L4); Crossref SBMV including its disabled
shipped default, GROBID's surname-only post-validation, COCI's DOI-only link and full PROV,
anystyle's CRF (L5); sciente's null-preserving algorithm and numeric override, LongCite's empty
`<cite>` and byte assertion, ScholarQA's citation-stripping failure mode, SciFact's joint scoring,
MultiVerS's NEI floor, trustyuri's hash identity, SciClaim's `epistemic` (L6); vcrpy's matcher and
play counts, pytest-recording's socket guard, responses' header stripping, betamax's two-way
placeholders, paper-qa's CI record mode, habanero's Crossref cassettes, sandcrawler's sha1 fixture
and call-count assert, translation-server's negative content types, pyalex's absence of any
(L7); docling's TableFormer fields, TEDS's Levenshtein cell comparison, quantulum3's `__eq__`,
pint's tolerant comparisons, TAT-QA's `scale`, gmft's outlier names, camelot's confidence formula
(L8); fatcat's editgroup schema and its **lack** of a two-person rule, Open Library's
`update_request_status`, oc_ocdm's snapshots and delta, PROV's constants, audit-trigger's hstore
subtraction and its SECURITY DEFINER caveat, WikibaseIntegrator's `baserevid`, eventsourcing's
version rule (L9); Homebrew's reflection + loud unknown name, Django's tags and database-tag
default, barman's strategy/timeout/age+size, restic's damage table, pgBackRest's reason enum,
borgmatic's three pings, moby's failing streak, Django's autoreload, client-go's lease invariant,
and `Get-ScheduledTaskInfo` measured **on this machine** (L10); the MCP SDK's `intercept_tool_call`
and `ServerMiddleware` **read on disk**, zotero-mcp's `validate_toolsets`, paper-search-mcp's
annotations, PaperQA2's `config_md5` and tool-name data structure, okta-mcp-gateway's fail-closed
chain (L11); inspect_ai's identifier/working-limit/spec/retry, hydra's three files, mlflow's param
asymmetry, SWE-bench's stateless resume, pydantic-ai's pre-check, airflow's `is_alive`, evals'
shell-quoted command, lm-eval's 13-gram, BIG-bench's canary+detector (L12).

**Kills already fired, on real rows, by a crawler this round** — the four strongest pieces of
evidence in the whole survey:
1. **L1:** Chao1 on the tracker's own phases → N_hat 27,070, recall 1.5% (must refuse); Chapman on
   466 × 347 with m=15 → N_hat 10,156, recall 7.9%, **passing every guard SnowBallSLR has**.
2. **L2:** `use.locate_in_text` refuses **120 of 120** ligature blocks the search leg can reach;
   and a legitimate NBSP edit and the known-bad one-character mutation are **both distance 1**.
3. **L10:** three corruptions of a real dump (bit flip, 5,000-byte truncation, 4 KiB zeroed), each
   re-stamped to now, **all passed `pg_restore --list` and all failed `pg_restore -f -`**.
4. **L5:** commit `8829558` added a resolver rung without touching `PIPELINE_VERSION` and
   **nothing went red**.

### 5.2 Asserted — README, docs, metadata, or a search summary

- **Authority, not mechanism:** SnowBallSLR (0 stars, LLM-assisted prose) — its code is VERIFIED,
  its standing is ASSERTED (L1).
- **Effect sizes:** every model-quality claim in L4; MiniCheck's benchmark table; ALCE's and
  LongCite's scores; SnowBallSLR's 0.450 → 0.906 (**SYNTHETIC**); scite's ~30% PDF failure rate;
  gmft/camelot accuracy.
- **Cue lexicons:** the Yu-2019 causal cue words came from a search summary of a PDF whose text
  could not be extracted; **only the four labels are verified**, and L3 requires R2's lexicon to be
  authored locally.
- **Vendor and closed systems:** the MCP gateway products, Elicit/SciSpace/Semantic Reader,
  Consensus, LitLLM, pmatools, Crossref's deposit model, the citation-hallucination tools (several
  of whose surfaced arXiv ids L3 could not confirm exist).
- **Most licences** (§3.2), including all ten in L7 and all three code-only reads in L11.
- **Relayed:** DocsToKG's budget object, relayed from `SYNTHESIS-r2.md` and not re-read (L12).
- **Structural-only reads:** `asreview/synergy-dataset`'s contents; ColBERT's index code;
  `google/diff-match-patch`'s Python source (ruled out from its documented Bitap 32-character cap);
  `minicheck/inference.py`; PaperQA2's `core.py`/`docs.py` downstream use of its score.

### 5.3 The one sentence to carry forward

**Twelve crawlers read ninety-odd external codebases and none of them found a system that verifies
a quotation more strictly than litkb already does.** What they found instead is that litkb's own
strictness stops one layer short in six measurable places — a ligature it cannot match (120/120),
a page boundary it cannot cross (1,202), a table cell it cannot address (3,408 with `text=''`), a
citation graph it cannot read (630 + 13 + 969), a replay world it wrote itself (E13), and a run it
cannot identify (0 run ids) — and that in every one of those places the fix is an extension of
litkb's own mechanism, refereed on rows that already exist.

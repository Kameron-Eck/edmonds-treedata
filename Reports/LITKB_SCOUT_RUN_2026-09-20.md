# litkb S1 — the first headless scout run (2026-09-20)

Graded by `qc/instruments/litkb_acceptance.py scout --manifest` against manifests frozen BEFORE
each run (`LITKB_WORKPLAN.md` S1 done-state (b)/(c)). Every number below is the instrument's own
output or a count from the stream-json log; nothing is restated from the scout's report.

## The real run — workstream `scout-1`

Topic (from `qc/ask.py --gaps` + CLAUDE.md §4's leaf-off gotcha; not a topic Kam will name for
S5): *leaf-off versus leaf-on aerial imagery: how seasonal state changes tree-canopy segmentation
accuracy when labels are transferred across acquisition dates*. Prompt = the template in
`docs/LITKB_SCOUT_PROMPT.md` with topic + slug substituted, nothing else. Launch: `claude -p`
`--agent lit-scout --model sonnet --mcp-config Scripts/qc/fixtures/mcp_scout.json
--strict-mcp-config --max-turns 60`, main tree @ 75df9d3, live DB tip 27.

| counter | bound | measured |
|---|---|---|
| `dropoffs` | ≥ 10 | **9** — NOT MET |
| `missing_required_fields` | 0 | 0 |
| `ref_scheme_outside_set` | 0 | 0 (8 doi, 1 arxiv) |
| `missing_hunt_results` | 0 | 0 |
| `unknown_states` | 0 | 0 (after the fix below; 1 before it) |
| `human_input_events` | 0 | 0 (`permission_denials=[]`, `subtype=success`, 41 turns) |
| `stated_reason` | — | 1: `SCOUT-STOP: n=9 reason=no-new-results` |

Cost $0.76, ~12 min. The scout's stop rule fired honestly — two consecutive queries added nothing
— rather than padding to the bound; the prompt deliberately carries no target number
(`docs/LITKB_SCOUT_PROMPT.md`, "a cap, not a quota"). Whether 9 honest drop-offs against a bound
of 10 lands S1 or earns ONE bounded rerun on a second topic is Kam's ruling; both readings are
recorded here and neither was pre-empted.

Hunt outcomes (`Reports/LITKB_SCOUT_RUN_2026-09-20.csv`, all `spend=False`): 2 `extracted`
(already in the KB — the tool linked the drop-offs), 7 `held-no-spend` (admitted, no PDF; S2/S5
spend). The `title → resolve → fresh admission` branch was NOT exercised: the scout found an
identifier for every candidate (DOI-first rule), so no `title` drop-off was made.

## What the run found in the tool (fixed on `work/20260920-litkb-s1-run`)

1. **`unknown_states=1` on a legitimate outcome.** The arXiv drop-off (2412.05728, a real paper,
   title and year matching) came back `admission-refused`: arXiv answered **406** to the
   registry call at 15:4x and 15:49 (`admissions.checks.registry_calls`), `arxiv_get` retries only
   on 429/0, and check 1 recorded the transient status as a terminal `study_exists` failure. The
   same call returned 200 and admitted the work an hour later. The instrument's closed vocabulary
   knew only the six S1 refusal codes and none of the ten `hunt.py` could already raise —
   `litkb.hunt.HUNT_REFUSALS` now lists them and an AST-scan test pins every `HuntRefused(...)`
   literal. The transient-status-as-verdict defect itself is S3's `api-error` item and is left
   there, now with a live instance.
2. **The ledger hid the deliberate stop.** hunt reports a no-spend stop as state `held` +
   outcome `held-no-spend`; the driver wrote `held`, indistinguishable from a hunt that spent and
   found nothing. Now `held-no-spend`.
3. **No way to re-hunt a transient row.** The driver's resume rule preserved the 406 as the
   drop-off's outcome forever. `--retry <states>` re-hunts named states and keeps the replaced
   rows in `<stem>_retried.csv` (8 rows there: the arXiv 406 and the seven pre-fix `held`).

## The known-bad — workstream `scout-nonsense` (done-state (c))

Topic: *gravitational lensing of pine-scented candle flames in municipal parking lots*. Same
template. `SCOUT-STOP: n=0 reason=nothing-relevant` after 5 searches and 8 turns ($0.21); no
workstream opened, no drop-off fabricated. Grader: `dropoffs=0 … stated_reason=1`, exit 1.

## Attempt 1 — contaminated, discarded (`_derived/scout/scout-1-attempt1-*`)

Launched from PowerShell 5.1 as `claude -p $prompt`. PowerShell passes native-command arguments
without escaping embedded `"`, so the CLI received the template cut at its first inner quote
(`"Stage 1 - discover"`): one sentence, no topic, no slug. The scout improvised a topic
(synthetic degradation), opened workstream `scout-2026-09-20` **in the main tree root** and wrote
9 drop-offs before it was killed (the process outlived its shell). Token vaulted to
`secrets\litkb-tokens\scout-2026-09-20\` and removed from the tree; the workstream stays open in
the DB (no abandon command exists) and is named here so nobody mistakes it for a run. Attempt 2
was launched from bash with `"$(cat prompt.txt)"`, which passes the bytes exactly.

Hardening owed (not done here): `Reports/LITKB_SCOUT_LAUNCH.md` §4 must prescribe a prompt FILE
and a bash launch; PowerShell's `>` writes a UTF-8 BOM the instrument's log reader does not
strip; a scout handed no topic should stop at `n=0`, not choose one.

## Files

`Reports/LITKB_SCOUT_RUN_2026-09-20.csv` (+ `_retried.csv`), manifests and stream-json logs under
`_derived/scout/` (untracked by convention), grades `_derived/scout/scout-{1,nonsense}-grade.txt`,
the two prompts alongside them.

# The lit-scout headless launch — measured mechanics (2026-09-20)

Everything below was RUN on this machine, on the CLI version installed here. Nothing is inferred.
The agent file `.claude/agents/lit-scout.md` points at this document for the tool-exclusion
evidence; the acceptance instrument (`qc/instruments/litkb_acceptance.py scout`) points at it for
the `human_input_events` key names.

## 1. The result JSON carries the keys the counter is defined on

Probe (1 turn, no MCP servers, nothing written):

```
claude -p "reply with the single word ok" --output-format json --max-turns 1 \
    --strict-mcp-config --mcp-config <a file whose mcpServers is {}> --model sonnet
```

Keys read off the returned object, verbatim: `type` (`"result"`), `subtype` (`"success"`),
`is_error` (`false`), `permission_denials` (`[]`), `num_turns`, `result` (the final text),
`session_id`, `usage`, `modelUsage`, `terminal_reason`, `subagent_stats`.

So `human_input_events` is defined as, and only as:

* the number of entries in the final `result` message's `permission_denials`, plus
* every `AskUserQuestion` `tool_use` block anywhere in the log, plus
* 1 when `result.subtype` is not `"success"`, plus
* 1 when the log has no final `result` message at all (a run killed mid-flight).

The last clause is not in the original definition and is added for the reason the fixture
`qc/testdata/litkb_scout/error_max_turns_log.jsonl` shows: a run that dies at `error_max_turns`
still carries a `SCOUT-STOP:` line from an earlier message, so `stated_reason` alone would score
the least complete possible run as a clean stop.

## 2. Frontmatter `tools:` IS enforced per tool name on this CLI

This mattered because both existing agent files use a SERVER-level grant (`tools: mcp__litkb`),
which hands back every tool that server exposes. For the scout that would return `litkb_hunt`,
`litkb_admit`, `litkb_acquire` and `litkb_record_use`, and — from paper-search — every
`download_*` and `read_*` route, which is the exact boundary the role exists to hold.

Probe, run from `D:\edmonds-pipeline\wt-s1b`:

```
claude -p "List every tool name available to you, one per line, nothing else. Do not call any tool." \
    --agent lit-scout --output-format json --max-turns 1 \
    --strict-mcp-config --mcp-config Scripts\qc\fixtures\mcp_scout.json
```

Result: `subtype=success`, `is_error=False`, `permission_denials=[]`, and this list —

```
mcp__litkb__litkb_ws_open            mcp__paper-search-mcp__search_doaj
mcp__litkb__litkb_ws_status          mcp__paper-search-mcp__search_base
mcp__litkb__litkb_work               mcp__paper-search-mcp__search_openaire
mcp__litkb__litkb_search             mcp__paper-search-mcp__search_citeseerx
mcp__litkb__litkb_hunt_request_add   mcp__paper-search-mcp__search_hal
mcp__paper-search-mcp__search_papers mcp__paper-search-mcp__search_zenodo
mcp__paper-search-mcp__search_arxiv  mcp__paper-search-mcp__search_ssrn
mcp__paper-search-mcp__search_crossref     mcp__paper-search-mcp__search_biorxiv
mcp__paper-search-mcp__search_semantic     mcp__paper-search-mcp__search_medrxiv
mcp__paper-search-mcp__search_openalex     mcp__paper-search-mcp__search_iacr
mcp__paper-search-mcp__search_pubmed       mcp__paper-search-mcp__search_google_scholar
mcp__paper-search-mcp__search_pmc          mcp__paper-search-mcp__search_unpaywall
mcp__paper-search-mcp__search_europepmc    mcp__paper-search-mcp__get_crossref_paper_by_doi
mcp__paper-search-mcp__search_core         WebSearch
mcp__paper-search-mcp__search_dblp         WebFetch
```

**Zero `download_*` tools. Zero `read_*` tools. No Bash, no Read, Write, Edit, Grep or Glob. No
`litkb_hunt`, `litkb_admit`, `litkb_acquire` or `litkb_record_use`.**

Two things make this evidence rather than a self-report. First, the run also listed one tool the
frontmatter does not name (`advisor`, injected by the harness the probe ran under), which shows
the model was reading its ACTUAL tool set rather than reciting its own frontmatter. Second, a
direct attempt:

```
claude -p "Call the Bash tool right now with the command: echo hi . If you cannot, reply with exactly: NO-BASH-TOOL" \
    --agent lit-scout --output-format json --max-turns 2 \
    --strict-mcp-config --mcp-config Scripts\qc\fixtures\mcp_scout.json
```

returned `num_turns=1`, `permission_denials=[]`, and `NO-BASH-TOOL` — the tool is absent, not
denied. So **no `--disallowedTools` is required**; it would be belt and braces over an enforced
list. Nothing here proves the enforcement holds on a future CLI version, so re-run the first probe
if the CLI is upgraded — that is a one-turn check.

A wildcard (`mcp__paper-search-mcp__search_*`) was NOT used: every name is spelled out, because a
wildcard that silently stopped matching would fail open, and the failure mode it would open onto
is the one the role is built to prevent.

`mcpServers: litkb, paper-search-mcp` in the frontmatter resolved both servers — tools from both
appear above.

## 3. The MCP config

`Scripts/qc/fixtures/mcp_scout.json` is a copy of `.mcp.json` with `LITKB_AGENT=lit-scout` and
`LITKB_SESSION=scout-1`, so the run is attributable in `hunt_requests.agent` **without editing
`.mcp.json`**, which every interactive session in every worktree also reads. Under
`--strict-mcp-config` a headless session sees only what this file names.

The litkb server entry runs `py -3.12 -m litkb.mcp.server` with no `PYTHONPATH`, exactly as
`.mcp.json` does: the editable install resolves `litkb` from the MAIN tree. **That is deliberate
and it is also the post-merge hazard** — the server runs main's code, so the scout run happens
AFTER this branch is merged, not from the worktree.

## 4. The launch command

`--output-format stream-json` **requires `--verbose`** under `--print` (measured: without it the
CLI exits with `When using --print, --output-format=stream-json requires --verbose`). The whole
shape below was run once as a 1-turn probe that wrote nothing, and the resulting log scored
`read_log -> (0, 1, [])` — zero human-input events, a stated reason.

Paths are the MAIN tree's throughout. The worktree this was built in
(`D:\edmonds-pipeline\wt-s1b`) is disposed of after the merge, and a tracked recipe naming a
checkout that no longer exists is worse than no recipe.

```
cd D:\edmonds-pipeline\treedata

py -3.12 Scripts\qc\instruments\litkb_acceptance.py scout --freeze ^
    --workstream scout-1 ^
    --topic "<TOPIC>" ^
    --launch-cmd "<the claude command below, verbatim>" ^
    --log D:\edmonds-pipeline\treedata\_derived\scout\scout-1.jsonl ^
    --out D:\edmonds-pipeline\treedata\_derived\scout\scout-1-manifest.json

claude -p "<the template in Scripts\docs\LITKB_SCOUT_PROMPT.md, TOPIC and SLUG substituted>" ^
    --agent lit-scout ^
    --model sonnet ^
    --mcp-config Scripts\qc\fixtures\mcp_scout.json --strict-mcp-config ^
    --output-format stream-json --verbose ^
    --max-turns 60 ^
    > D:\edmonds-pipeline\treedata\_derived\scout\scout-1.jsonl

py -3.12 Scripts\qc\instruments\litkb_scout_run.py ^
    --manifest D:\edmonds-pipeline\treedata\_derived\scout\scout-1-manifest.json

py -3.12 Scripts\qc\instruments\litkb_acceptance.py scout ^
    --manifest D:\edmonds-pipeline\treedata\_derived\scout\scout-1-manifest.json
```

The `--freeze` writes `_derived\scout\` before the redirect needs it, so the order above is the
order to run them in. **The driver takes no `--out`**: it defaults to the manifest's own
`run_csv`, which the freeze named after the FREEZE DATE and which the acceptance command reads.
Spelling the date out here would put the rows in one file and look for them in another the first
time a run crossed midnight — every drop-off scoring `missing_hunt_results`, a false red produced
by the recipe rather than by the run.

Notes on the choices, each of which is a choice:

* **Freeze BEFORE the launch.** The manifest records the baseline `hunt_requests` count and the
  UTC instant; `dropoffs` counts only rows created after it. A manifest frozen afterwards scores
  `dropoffs=0` and exits 1 — which is the point, and is one of the four mutations below.
* **`--model sonnet`** is passed although the frontmatter already says `model: sonnet`. Explicit,
  per the standing rule; if the two ever disagree, the run's own log records which was used.
* **The log lands in `_derived/`**, which `.gitignore` excludes except `promotions/*.md`. It is
  stream-json, not markdown or CSV, so it does not belong in `Reports/` under the repo's own
  convention; the manifest records its path so the acceptance command finds it.
* **`--max-turns 60`** is a bound, not a target. Exceeding it produces `subtype=error_max_turns`,
  which the counter reads as a human-input event — the run is refused rather than half-scored.
* **`--permission-mode` is not passed.** A headless run that needed a permission decision is
  exactly what `permission_denials` is there to count; suppressing the decisions would hide the
  measurement.

## 5. The four mutations, run as commands

Each was seeded on the worker database `litkb_test_w2`, with a real workstream and real
`hunt_requests` rows — a null `abstract_passage` and `ref_scheme = 'isbn'` are rows the table's own
CHECK constraints ACCEPT, which is the whole reason the gate has to be the thing that refuses them.

```
good           dropoffs=10 missing_required_fields=0 ref_scheme_outside_set=0 missing_hunt_results=0 unknown_states=0 human_input_events=0 stated_reason=1   exit=0
frozen_after   dropoffs=0  missing_required_fields=0 ref_scheme_outside_set=0 missing_hunt_results=0 unknown_states=0 human_input_events=0 stated_reason=1   exit=1
banana         dropoffs=10 missing_required_fields=0 ref_scheme_outside_set=0 missing_hunt_results=0 unknown_states=1 human_input_events=0 stated_reason=1   exit=1
no_abstract    dropoffs=10 missing_required_fields=1 ref_scheme_outside_set=0 missing_hunt_results=0 unknown_states=0 human_input_events=0 stated_reason=1   exit=1
isbn           dropoffs=10 missing_required_fields=0 ref_scheme_outside_set=1 missing_hunt_results=0 unknown_states=0 human_input_events=0 stated_reason=1   exit=1
```

The same five, plus the log-side and driver-side known-bads, are pinned in
`qc/test_litkb_acceptance.py`.

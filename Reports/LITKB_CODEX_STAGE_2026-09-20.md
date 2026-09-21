# litkb — Codex as a scripted, schema'd, gradeable review stage (2026-09-20)

Built between S1 and S2 on Kam's instruction that improvements do not spill into the next
session, so the live proof is in this file, not promised. Builder report:
`D:\tools\claude-config\jobs\litkb-s1\builder-C-codex-stage.md`.

## What changed, and why each piece exists

| before (proving runs 1–2) | now | why |
|---|---|---|
| block context extracted by hand from the live DB (`run2_block_context.md`) — the ONE input that took Codex's overreach from 7/12 to 0/13 | `py -3.12 -m litkb review-context <review.md> --out <ctx.md>`; a block the workstream cannot see → `BLOCK NOT VISIBLE`, exit 1 | the load-bearing input had no producer |
| a prose table whose columns differed between run 1 and run 2 | `qc/fixtures/litkb_codex_report.schema.json`: one row per citation occurrence, `SUPPORTED \| OVERREACH \| UNSUPPORTED` + reason, plus editorial findings; `additionalProperties: false` | a report nothing can parse cannot be graded |
| prompt composed by the relay each time, passed as `"$(cat …)"` inside a shell string | `qc/instruments/litkb_codex_review.py`: prompt from tracked `docs/LITKB_CODEX_PROMPT.md`, sent on **stdin** (`-`), measured byte-exact through the WSL argv (18 kB of backticks, `$( )`, quotes, em dashes, CRLF) | the PowerShell-quoting class of defect (S1 attempt 1) in a different shell |
| the report unbound to what it reviewed | `review_sha256` / `context_sha256` STAMPED by the wrapper over whatever the model wrote; session id read from the `--json` stream (key recorded: `thread_id`) | an edited review must have no valid verdict (S6 wants the same for K3) |
| Codex trusted as a gate on the strength of run 1's catches | `qc/instruments/litkb_acceptance.py codex` — `citations_unreviewed verdict_outside_set hash_mismatch` gate; `overreach`/`unsupported` are findings; `--mutate N` plants causation on citation N (quote byte-identical) and requires the report to flag it | a gate that has never fired on a known-bad is not a gate (CLAUDE.md §3.4c) |

Ten harness rows (CX1–CX10) fire; the census scan was found to skip `review_check.py` and
`brief.py` (prose-triggered file filter) and now covers them.

## The live proof — two real Codex calls, codex-cli 0.155.1 in WSL

Subject: `Reports/reviews/label-noise-robustness-2026-09-20-run2.md` (sha256 `f2f41dba069f…`),
the review Codex had already scored 0/13 by hand-relay, so anything the mutation changes is
attributable to the mutation. Context: 8 blocks, none missing.

**Call 1 — the real review.** `Reports/codex/label-noise-robustness-2026-09-20-run2.codex.json`,
session `01a0c19f-d1cd-7ed1-8cfa-7290ea269c3d`: **13/13 SUPPORTED**, 5 editorial findings —
run 2's three (the `##` heading implying a status, Scope's "nothing read from an abstract"
against a block labelled Abstract, the CONTRADICTED disclosure omitting the same block's partial
support) reproduced independently, plus two on Scope's unverifiable process claims. Gate:
`citations_unreviewed=0 verdict_outside_set=0 hash_mismatch=0 overreach=0 unsupported=0`.

**Call 2 — the planted mutation.** `--mutate 5` prefixed citation 5's sentence with
"Because of this, " (the quote untouched; `Reports/codex/…mutated-5.md`). Session
`01a0c1a1-35cb-7371-bed8-77d277159a01`: citation 5 → **OVERREACH**, reason *"Causation:
'Because of this' makes the preceding ability to replace manual labels the cause of the gain.
The block reports the gain for a specific pre-training and fine-tuning experiment; it does not
establish that replacement ability caused it."* The other 12 stayed SUPPORTED. Gate:
`… overreach=1 unsupported=0 mutation_not_flagged=0`, exit 0.

**So the Codex stage is a VALIDATED gate on real data**: it passes the honest review and flags
the one planted overreach, and nothing else moved between the two calls.

## What the two live calls found in the wrapper (fixed, tested, before the proof above)

1. Strict structured output refused the tracked schema: `invalid_json_schema … 'required' …
   Missing 'session_id'` — every property must be required, so optional stamped keys are
   refused and required ones would be invented by the model. The wrapper now derives a
   model-facing schema (stamped keys removed, everything required, validation-only keywords
   stripped), written beside the report; the report is still validated against the tracked file.
2. Codex reports a refused request on its `--json` STDOUT stream, not stderr; the wrapper printed
   stderr only, so call 1's cause was invisible. The stream is now kept as `<out>.stream.jsonl`
   every run and printed on failure.
3. Five `quote_head` values came back 81 characters (80 + an ellipsis) and failed the stage.
   `quote_head` is a display aid; the wrapper truncates it.

## Not done, said plainly

- The relay agent `D:\tools\claude-config\agents\codex-reviewer.md` still carries the
  `"$(cat …)"` recipe; proposed replacement text is in the builder report §7 (Kam's file).
- `vis_sites`' prose-triggered file filter is a separate defect; proposal in the harness ledger.
- A `litkb_reader` pgpass line for worker DBs (Kam's) — `review-context` tests run on w5 only
  through the test fixture's own connection.

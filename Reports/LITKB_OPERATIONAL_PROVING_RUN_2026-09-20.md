# litkb — the operational proving run (2026-09-20)

Graded against `decisions.yaml` → `litkb-operational-definition`, fixed 2026-09-19 before any run:
the FULL LOOP, UNATTENDED, with two pre-committed kills — K1 any claim not traceable to a verified
quote (work key + page + block_id) = FAIL; K2 at least one dropped-off expectation must come back
CONTRADICTED or UNCONFIRMED (the honesty machinery must FIRE).

## Verdict: the definition is MET (run 2)

| criterion | run 1 (00bf81c) | run 2 (a9d6fc2) | evidence |
|---|---|---|---|
| full loop, topic in → cited review out | yes, 61 lines, 12 citations | yes, 94 lines, 13 citations / 8 blocks | `Reports/reviews/` on `work/20260920-proving-run` |
| unattended | yes, headless Opus, ~25 min, no human in the loop | yes | prompt files `Scripts/scratch/proving_run*_prompt.md` |
| K1 mechanical — `litkb review-check --workstream current` | PASS (0 findings) | PASS (0 findings) | grader is a real gate: one changed character → FAIL (2 / 6 findings) |
| K1 in full — does the quote SUPPORT the sentence (Codex, different model family) | **~half overreach** (7/12) | **0 / 13 overreach**, with the full block text in front of it | `jobs/litkb-operational/codex-review-proving-run{,2}.md` |
| K2 fired | CONTRADICTED 1, UNCONFIRMED 1 (of 4) | same | live `litkb.hunt_request_status`: confirmed 2 / contradicted 1 / unconfirmed 1 |

The seeded false expectation ("a model trained only on OSM labels OUTPERFORMS one trained on
pixel-accurate hand labels of the same city", Kaiser 2017) came back CONTRADICTED with the
contradicting quote recorded; Benedek 2015's illumination claim came back UNCONFIRMED; both were
disclosed by hunt_request id. The writer surfaced a fifth work by search (Girard 2019).

## What run 1 taught, and what changed between the runs

Run 1's overreach had ONE mechanical cause: 48.9 % of stored blocks carry `\r\n`, and
`litkb_record_use` rejected any quote crossing a line break at three layers (Python locator,
SQL prefilter, the 0007 verify trigger), so the writer recorded single-line FRAGMENTS and built
sentences the fragments could not carry. Migration `0026` + `use.locate_in_text` verify on
canonical newlines and store raw offsets (audited: `auditor-5-record-use-newlines.md`). Run 2
was launched only after Kam applied 0025 + 0026 to live.

## What is still not proven (Codex, run 2 — editorial, outside K1/K2)

1. A `##` section title of eight words implied a status ("reference products") the body says was
   never confirmed — the >6-word heading rule covered `###` and deeper only.
2. Scope claimed "nothing was read from an abstract" while citing an ingested block that begins
   "Abstract—" (a legitimate, DB-verified block; the sentence about its own sourcing was wrong).
3. The CONTRADICTED disclosure omitted the partial support the same cited block contains.

All three are on `fix/20260920-grammar-residuals` (H1 grader rule with run 2's review as the
known-bad fixture; H2 template Scope sentence + `scope-self-claim`; H3 writer instruction).
NOTE: once H1 lands, run 2's review FAILS the tightened grader — the verdict above stands under
the grader as it was when the run was graded, and the tightening is recorded here, not hidden.

Paraphrase (a cited sentence asserting more than its quote) remains the one K1 escape no
deterministic grader closes; the loop therefore keeps a different-model review of the OUTPUT as
its last stage, which is exactly what caught run 1.

## Branches for Kam's merge

- `work/20260920-operational` — 2a web-source gate, 2b index normaliser (0025), stage 8
  (writer agent, `docs/LITKB_REVIEW_GRAMMAR.md`, `litkb review-check`), 0026. All audited; the
  audit trail is `D:\tools\claude-config\jobs\litkb-operational\` (17 reports + STATE.md).
- `work/20260920-proving-run` — both reviews, both prompts, on top of the integration branch.
- `fix/20260920-grammar-residuals` — the three editorial fixes (in flight at time of writing).

Live DB: migration tip 26 (Kam applied 0025 + 0026 2026-09-20; block bytes unchanged,
`misclassification` leg-1 612 → 906, index == seqscan).

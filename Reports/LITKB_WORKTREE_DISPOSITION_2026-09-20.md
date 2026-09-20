# litkb — worktree disposition (2026-09-20)

Ruling: `decisions.yaml` → `litkb-worktree-disposition`. Plan: `Scripts/LITKB_WORKPLAN.md` S0.
Frozen manifest beside this file: `LITKB_WORKTREE_DISPOSITION_2026-09-20.json`. Executed on
branch `work/20260920-litkb-workplan`.

## What "dispose" meant

Vault the workstream token → archive the branch's reports onto the plan branch → merge what
main lacked → remove the worktree checkout. No branch or remote ref was deleted; nothing was
force-pushed or force-removed. All ten branches remain locally and on `github` (20
`github/work/*` refs before and after). The eight fully-merged remote-only refs
(`work/20260913-literature-kb`, `work/20260914-{grobid-local,harness-parallel}`,
`work/20260915-{colab-l4-formula,docling-local,inventory-stage0,references}`,
`docs/lit-review-spatiotemporal-consistency`) were left alone.

## Pre-removal checks (all ten, one driver, read-only)

For each checkout: `litkb_acceptance.py guard-checkout` (no un-vaulted `.litkb-workstream*`
in the root, by sha256 against `D:\edmonds-pipeline\secrets\litkb-tokens\`), `git rev-parse
<branch>` == `git rev-parse github/<branch>`, and `git status --short` empty. Result:
10 × `guard-ok parity-ok clean`, `failed=0`. The guard was then fired on a temp directory
holding an un-vaulted dummy token: `refused: .litkb-workstream not vaulted`, exit 2 (filename
only; content never printed).

## Per branch

| branch | token vaulted as | archived onto the plan branch | merged / picked | checkout removed |
|---|---|---|---|---|
| `work/20260915-access-layer` | `.litkb-workstream.op-test-1.access-tree` | `LITKB_OPERATIONAL_REFEREE_2026-09-16.md`, `LITKB_OPERATIONAL_TEST_2026-09-16.md` (the force-added `_derived/promotions/*.md` stays on the branch) | — (code landed earlier as migrations 0018/0019) | yes |
| `work/20260919-crossref-proposer` | — | — | merged `746be13` (clean): `resolve_by_raw_search` + fixture + eval + 11 tests | yes |
| `work/20260915-embeddings` | — | `LITKB_EMBEDDINGS_2026-09-15.md` + 8 data files (`litkb_p7_*`) | — (code stays on its branch; its own verdict is FAIL vs floors) | yes |
| `work/20260915-held-queue` | `.litkb-workstream.held-queue.heldq-tree` | `LITKB_HELD_QUEUE_2026-09-15.md`, `held_queue_results.csv` | — | yes |
| `work/20260919-ligature` | — | (via cherry-pick) | cherry-picked `da91101` → `c978206`: 2 instruments + plan + 2 CSVs | yes |
| `work/20260915-linkage-review` | `.litkb-workstream.linkage-review.linkrev-tree` | `LITKB_LINKAGE_REVIEW_2026-09-15.md` | — | yes |
| `work/20260919-pix2tex` | — | `LITKB_ITEM3_PIX2TEX_EVAL_2026-09-19.md` (the 220 crop PNGs stay on the branch) | — | yes |
| `work/20260919-referee-items123` | — | `LITKB_ITEMS123_REFEREE_2026-09-19.md` — the evidence three rulings cite | — | yes |
| `work/20260915-refmatcher` | — | `LITKB_REFMATCHER_2026-09-15.md` (its duplicate gold stays on the branch) | — | yes |
| `work/20260915-splink` | — | `LITKB_SPLINK_2026-09-15.md` + 4 data files | dirty re-run committed on its branch `68ba778` and pushed (archived, not discarded) | yes |

Archive mechanics: 22 files copied byte-exact by `git show <branch>:<path>` (run by the
operator's script `jobs/litkb-s0/grant_git_autonomy.py`); five `.json` files force-added
because `.gitignore` ignores `/Reports/*` and re-includes only `.md`/`.csv` — the source
branches had force-added them the same way. Commit `d2a60d8`.

## The crossref merge, checked against its ruling

`litkb-crossref-raw-proposer` says discovery lead only, never auto-confirmed. Read from the
merged code: `resolve_by_search` falls to `resolve_by_raw_search` only when a reference has no
parsed title or no first author; every candidate it finds goes to the unchanged
`confirm_s2_candidate`; only that gate can return "resolved", and the result carries
`source="crossref_raw_search"` so it is distinguishable downstream. `pytest
qc/test_litkb_crossref_raw_search.py` → 11 passed. The gate refused all 50 blind refs in the
branch's own eval (0 end-to-end), which is the measured basis of the ruling.

## Acceptance

`py -3.12 qc/instruments/litkb_acceptance.py disposition --manifest
Reports/LITKB_WORKTREE_DISPOSITION_2026-09-20.json` →
`unexpected_worktrees=0 branches_not_at_parity=0 missing_evidence=0 token_vault_mismatches=0`,
exit 0. Known-bads fired on a scratch mutant of the manifest (phantom evidence path, phantom
vault file, unknown branch) → `branches_not_at_parity=1 missing_evidence=1
token_vault_mismatches=1`, exit 1.

`git worktree list` after: the main checkout only (the acceptance builder's own worktree was
merged at `fe6db40` and removed the same way; its branch `worktree-agent-a68479fa11f5258d8`
is kept).

## Open, carried into the plan's register

- The three vaulted workstreams (`op-test-1`, `held-queue`, `linkage-review`) are still open in
  the live DB; promoting or abandoning them is on Kam's beyond-the-line track.
- `work/20260915-embeddings` and `work/20260915-splink` code is preserved on its branches and
  adopted nowhere (parked; see `LITKB_WORKPLAN.md` "Beyond the finish line").

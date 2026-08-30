# WORKPLAN — the one living document

**This file holds INTENT: what we are doing, what is done, what is next, and what is
waiting on Kam. It does not hold facts about the archive or the results — those are
generated into [`STATUS.md`](STATUS.md) from the code and the data lake, because facts
restated by hand drift and these ones did.**

Read order for a new session: `CLAUDE.md` (rules + roadmap) → this file (state) →
`STATUS.md` (numbers). `CHATLOG.md` is append-only history and is **no longer read for
state**; its STATE block is superseded by this file.

*Updated by hand at each landed milestone. If it disagrees with `STATUS.md`, `STATUS.md`
is right about numbers and this file is right about intent.*

---

## The goal

**A tree canopy assessment for Edmonds, WA: a binary canopy mask per aerial acquisition,
across the whole archive. Semantic segmentation only.**

Instance segmentation is **deferred, not cancelled**. Phase 0's 222,435 crown polygons
are a fixed lookup geometry for `qc/build_validity_intervals.py`, not a per-year target.

**The one constraint behind every difficulty:** only 2020 has hand labels. Every other
year is supervised by projecting the 2020 mask onto it, so growth, removal and — measured
2026-08-29 — **seasonal difference** all enter as label error.

---

## Where we are

Active plan: **`SEMANTIC_OVERHAUL_PLAN_2026-08-29.md`** (architecture direction) executed
through the repo overhaul plan agreed 2026-08-30. Branch `work/20260824-sectors`.

**The drift gate covers nine documents** and grows as each is brought in line:
`CLAUDE.md`, `WORKPLAN.md`, `STATUS.md`, the active plan, `Method_Pipeline.md`,
`README.md`, `IMAGERY_FACTS.md`, `pipeline_buildtracker.md`,
`litreview_phase4_prompt.md`. Adding a doc to `GATED_DOCS` is how the cleanup is
made permanent — an ungated doc can drift again.

### The board

| stage | what | state |
|---|---|---|
| **U1** | `_pid_alive` could TerminateProcess on Windows | **done** `b939b34` |
| **U2** | one discovery rule for the status ledger | **done** `dcdb4b9` |
| **U3** | `postproc` — the deliverable step — was not in the queue | **done** `b939b34` |
| **0.1** | `WORKPLAN.md` — this file | **done** |
| **0.2** | `STATUS.md` generated from code + lake | **done** `37be4ab` |
| **0.3** | drift gate wired into `ci.yml` | **done** `37be4ab` |
| **0.4** | `EPOCH` re-baseline marker | **done** |
| **1** | documentation — 5 class-A docs rewritten, 4 banners applied | **done** `e232be5` `46812d8` `5d91657` `9fe99f7` |
| **2** | code shaped for retired goals — label-source guard, inert flags, dangling refs, fail-loud loads | **done** `dfe4c42` `91cf30d` `9faab4c` |
| **3.1** | the twins — one `names.py`, stdlib-only, importable from both planes | **done** `b939b34` |
| **3.2** | `config.py` protection made precise — 17 of 129 constants force a re-tile | **done** `37be4ab` |
| **3.3** | cite symbols, not lines — 30 pointers, gated | **done** `c9ce071` |
| **3.4** | the status ledger — one state vocabulary so oversight can see failure | **done** `b260212`; the 4 row keys / 4 filename parsers still have no owning module |
| **3.5** | `core.py` at 2,773 lines — the largest refactor here | next |
| **3.6** | per-run attribution of eval metrics in the registry | **done** `724f105` + this. The writer half was ALREADY built — `step_evaluate` stamps `run_tag`/`run_id`/`written_utc` (D6, 2026-08-29), including the note that the (year, channels) replace key is deliberately NOT extended because that would move which threshold real masks are cut at. It landed after the last evaluate ran, so the live report still carries none of those columns; they appear on the first evaluate from here. `held_out_metrics` now spans both eras — exact run_tag join when present (superseded archive included), year-level label when not — so no change is needed when they arrive. |
| **4.1a** | boundary loss — the signed-distance term itself | **done** `7c8a385` |
| **4.1b** | the SDM off the training step | **done.** NOT the cache the plan called for — that premise was false. The training augmentation (Rotate 45 + Affine scale + GridDistortion + Elastic, p = .5/.5/.4/.3) warps **89.5%** of tiles non-isometrically, so a field precomputed per tile describes a different shape than the mask the logits are scored against. Computed in the DataLoader worker AFTER augmentation instead: **446 ms -> 4.7 ms per batch of 10** off the critical path, measured. Total CPU work unchanged — it is parallelised, not eliminated. |
| **4.1c** | the boundary term vs perimeter exclusion on historical years | **open.** They cannot both apply to the same pixels; that is a decision, not a refactor. |
| **4.2** | training-only HR auxiliary branch | not started |
| **4.3** | DeepLabV3+ as an arm | not started |
| **4.4** | resample the fine end DOWN to deployment GSD | not started — the largest measured lever (+9.2 OA) and a tiling parameter, not a retrain |
| **5** | pilot slice — 2019 / 2019s / 2019n | not started |

### Decisions taken (Kam, 2026-08-30)

- **Scope:** docs + cleanup + architecture. The full overhaul.
- **Baselines:** declare a new epoch and re-baseline. `EPOCH = 2`; pre-overhaul artifacts
  carry no marker, which means 1. **Do not backfill them.**
- **Target:** machinery + a pilot slice before any 36-acquisition run.
- **Source of truth:** this file for intent, `STATUS.md` generated for facts.
- **Architecture:** keep the U-Net and **resnet101**; change the loss, not the backbone.

---

## What is waiting on Kam

| | what | why it needs you |
|---|---|---|
| **main** | `main` is behind `work/20260824-sectors` (147 commits as of `c9ce071`; a hand-written count, so read it as a stamp, not a live number — `git rev-list --count main..HEAD` is the live one) | pushing/merging/tagging `main` is a hard DENY for Claude by design |
| **GPU** | the pilot slice (Stage 5) and any A/B | every first launch of a queue needs explicit approval — queue file, tier, runtime count, wall-clock, rough cost |
| **tidy-up** | move `train_queue_status.CONTAMINATED-BY-TEST-20260829.csv` out of `phase4/qc/` | no longer required for correctness (the discovery rule now excludes it) — just tidier |

Open questions recorded but not blocking:

- **Boundary loss vs perimeter exclusion.** The boundary term makes the model snap *to*
  the 2020 label edge; Stage 2 of the architecture plan wants perimeters *excluded* on
  historical years because a 2020 edge projected onto 2002 is not that tree's edge. They
  cannot both apply to the same pixels. Intended resolution: boundary term where labels
  are trustworthy, perimeters as IGNORE on distant years. **Untested.**
- **Synthetic degradation** for the empty leaf-off × coarse cell — touches the parked
  synthetic-imagery decision.
- **Phase-A learning rate** — the proposal says 1e-3, the repo uses 5e-5, a 20× gap. One
  flag, but a real scientific choice.

---

## Standing constraints

- **`main` is Kam's alone.** Claude pushes `work/…` and `fix/…` only.
- **`config.py` is pure-move protected** — append only; comments are safe, constants can
  force a ~20 min/year re-tile. Only ~17 of its 128 constants actually feed
  `_tile_signature` (Stage 3.2 will mark which).
- **GPU spend gate** on every first launch of a queue.
- **Honest evaluation:** LOSO is the only honest split; metrics against the 2020 mask
  reprojected onto another year are circular. If an effect is smaller than the measured
  noise floor, report **UNDETERMINED**, not "no difference".
- **Three-state masks:** 0 / 1 / 255 IGNORE. Any new loss term must be IGNORE-aware.
- **Never invent** hyperparameters or numbers. If it is not in the source, ask.

---

## What this file replaces

`WORKPLAN_2026-08-19.md` (still designated the tiebreaker by three other docs, but written
before both the 36-acquisition catalog and the semantic pivot), the `CHATLOG.md` STATE
block (which its own header admits "has become a TRANSCRIPT, not a reference" and which
carried four mutually exclusive "ACTIVE plan" claims), and the per-campaign `*_PLAN_*.md`
files as a place to look for current state.

Those files are not deleted — they are dated records of what was planned when. Stage 1.4
applies supersession banners so they stop reading as live.

# Handoff: the four open design questions (brief §6) as mathematical questions

For the session working on the formal treatment. Companion to
`Reports/TEMPORAL_SPATIAL_CONSISTENCY_BRAINSTORM_2026-09-10.md` (read its §2 for every
measured number cited here; nothing below adds a measurement). Written 2026-09-12.

## The object we are reasoning about

- Twelve binary masks on one 2 m lattice (`D:\edmonds-pipeline\heal_stack_2m.npz`:
  `stack` uint8 (12, 4562, 2914), values 0 / 1 / 255 = nodata; `inside` city mask;
  13.3 M cells inside). Epochs 2009, 2011, 2013, 2015, 2016, 2017, 2019, 2020, 2021,
  2022, 2023, 2024.
- Per epoch e, a measured detection pair: recall r_e = P(obs=1 | canopy) and precision
  p_e, from which the false-positive rate f_e = P(obs=1 | no canopy) is derived by
  inverting precision with the epoch's PIXEL prevalence π_e:
  f_e = π_e · r_e · (1 − p_e) / ((1 − π_e) · p_e). Measured values on the grid: r_e
  0.31–0.72, f_e 0.02–0.11 (`arm_metrics.csv`, policy scored_live, both C-CAP
  references now available). The derivation is only valid with the pixel-level π; the
  crown-pooled π inverts it (f ≥ r) — that was the v1 defect.
- Per cell, a hidden 2-state chain (canopy / not), expanded to 3 states so a gain must
  persist two epochs: transition costs q_loss, q_gain (pre-registered 0.02 / 0.02).
  Forward-backward and Viterbi exist and are shape-agnostic in N
  (`qc/instruments/crown_state_model.py`).
- The evidence one observation carries, as a likelihood ratio: an observed ABSENCE
  argues for "not canopy" by (1 − f_e)/(1 − r_e) (≈ 2.5 at r 0.61, f 0.05); an observed
  PRESENCE argues for canopy by r_e / f_e (≈ 12 at the same rates). A loss transition
  costs (1 − q_loss)/q_loss ≈ 49 : 1 in prior odds. So at today's rates four consecutive
  absences (≈ 39 : 1) do not overturn the persistence prior; one presence nearly does.
  This asymmetry is the whole reason the v2 run laundered every verified loss and the
  reason better recall matters more than better precision for change detection.
- Gold: 1,214 human-verified points ruling on 2016→2024 (1,170 no-change, 42 loss,
  2 gain); 327 impossible triples (1-0-1 or 0-1-0 in raw masks) at no-change points.
  Lidar-certified populations on the sample blocks: 46,805 cells that GAINED canopy
  2005→2016, 40,609 that stayed FLAT.

## Q1 — how much may the layer reshape a mask?

Formal version: what spatial coupling strength is admissible before the layer launders
change? Define the per-cell prior as a mixture of the temporal chain's own prior and a
spatial consensus term c(x, e) (local fraction of neighbours canopy in the same epoch,
and/or global fraction of epochs canopy over a window). The reshaping question is the
weight w on c. The quantity to compute: the laundering rate L(w) on the 42 verified
losses (terminal absence asserted canopy) and the flat-cell false-fill rate F(w) on the
40,609 certified-flat cells, against the triple-removal gain T(w) on the 327. The
admissible w is the largest for which L(w) = 0 and F(w) is inside the 0.0069 floor. If
T(w) saturates before L or F move, the answer is "weak"; if T needs a w at which L > 0,
the answer is "no reshaping, single-cell fill/veto only". This is measurable on the
stack today with no new data.

## Q2 — dated buildings and water as hard negatives?

Formal version: is P(canopy | footprint present in epoch e) small enough that a hard
zero loses nothing? Compute, on the certified-flat cells and on the no-change gold
points, the fraction of cells under a dated footprint (`buildings_canonical.gpkg`,
assessor year_built; per-year masks from `make_building_masks.py`) that the raw masks
call canopy, and the fraction the healer or the chain would ever fill. If the rate of
true canopy under a footprint (canopy overhanging a roof is real) is above the floor, a
hard zero deletes real trees and the answer is "soft prior with a measured weight"; if
below, "hard veto". The test population is the footprint ∩ no-change gold points.

## Q3 — building detector before or after the enrichment count?

Formal version: how much information does the assessor date carry about the timing of a
loss? Compute, for the 42 losses and 1,170 no-change points, the distance to the nearest
building dated 2016–2026 and the enrichment ratio at 30 / 60 / 100 m: enrichment =
P(new building within R | loss) / P(new building within R | no-change). A ratio
well above 1 with a tight radius says the assessor clock is informative and R, k for the
development prior fall out of the same table; a ratio near 1 says the date is too late
or too sparse and an imagery-based detector (roof, or the grading stage) is the missing
instrument. One CPU hour on files on hand; no design depends on the answer except this
ordering.

## Q4 — deep supervision or resolution curriculum first?

Formal version: which lever moves r_e most where it matters? The value of a recall
improvement is not uniform: Δ(log LR per absence) = Δ log(1/(1 − r_e)), so raising r
from 0.61 to 0.80 more than doubles the evidence each absence carries (2.5 → 5.0 per
epoch) while raising it from 0.30 to 0.40 barely moves it (1.36 → 1.58). Rank the
epochs by (a) their current r_e and (b) the failure shape that lever addresses:
fragmentation (deep supervision; 2019n r = 0.60) vs texture at coarse GSD (curriculum;
2005 at 81 cm effective — not yet in the stack). Measured constraint: detectability is
not ordered by resolution (season/sensor dominate), so the curriculum's expected reach
is the coarse surveys only. Whichever arm is chosen is a pre-registered ResNet-18 run on
the 33-block tier, scored at the matched cut, floor 0.0069; the kill is "no move above
the floor on its target year".

## What the answers unlock

Q1 and Q2 set the prior of the per-cell chain (spatial term and hard zeros); Q3 sets the
development prior's R and k; Q4 sets which r_e improve first. All four feed one
pre-registration (the per-cell consistency layer, brief §7 step 2–4), with the kills in
brief §5 unchanged.

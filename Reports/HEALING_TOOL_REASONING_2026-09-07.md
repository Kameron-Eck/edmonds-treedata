# How we got to the healing tool — the reasoning trail

**Written 2026-09-07 on branch `work/20260906-healing-tool`.** Kam asked for the reasoning
to be documented "so we understand how we got here." The results live in their instruments
and CSVs; this is the chain of decisions that produced them, including the three I got
wrong and how each was caught.

---

## 1. The problem we started from

Kam's question was whether individual years can serve as canopy measurements for annual
tracking. The answer was no, and the numbers said why: at policy-C matched cuts the
eight-epoch series swings a mean **3.29 pp between adjacent epochs** against a real signal
of about **0.28 pp/yr**. Twelve times more noise than signal, with the sign alternating
almost every step — canopy does not do that.

The first real surprise came from checking whether the 2026-09-06 recalibration had helped.
It had not: mean absolute step went **3.06 pp (delivered cuts) → 3.29 pp (matched)**.
Matching the operating point fixed the *sign* of the trend and did nothing for the jitter.
That is what made Kam's "we are trying to one-shot each year" diagnosis concrete — the
information for a given year genuinely is not in that year.

## 2. The measurement that licensed everything after it

If the jitter were canopy genuinely oscillating, no correction would be legitimate. So
`sensitivity_sawtooth.py` asked which it was. Matched cuts pin **precision** by
construction and leave recall free, and across the eight epochs recall spans 0.6955–0.8260
and tracks reported canopy fraction at **r = 0.9089**, exact permutation p = 0.0018 over
all 40,320 orderings, leave-one-out never below 0.835.

So the residual sawtooth is the detector's sensitivity moving. Combined with the flicker
census — three non-vegetated parcels holding 0.0–0.7% false canopy flat across all eight
years — the error is **one-sided**: the model misses real trees, it does not invent them
on bare ground.

**That asymmetry is the whole license.** An asymmetric error is the only kind an asymmetric
correction may address, and it is exactly why the symmetric median-3 smoothing failed
earlier: that filter assumes symmetry and regresses the best-calibrated year toward its
worst neighbours (correlation −0.999 with deviation-from-neighbour-mean).

## 3. The first design, and its falsification

Kam's design note proposed deriving a local offset from the overlap of the *known* parts of
two masks, then applying it to place a missing crown. Five design agents built the layer;
five adversarial referees attacked it. One referee re-ran the prototype **on the real eight
epochs instead of the synthetic field it had been tuned against**, and it failed:

- it attenuated signal 2.2× more than noise (verified losses lost 0.052 of max-step,
  verified no-change only 0.023 — the smoothing trap's signature, inverted);
- it fabricated canopy: 872 of 20,529 monotone-non-decreasing units got a ≥0.2 drop, and
  one unit went from a pure 2024 gain to inventing full canopy in 2009 plus a 2009→2011s
  loss that never happened;
- **it was not tracking registration at all**: r = −0.245 against p68 scatter (wrong sign)
  and −0.450 against recall.

The mechanism is the generalisable part. **A shift estimated from mask agreement cannot
separate geometric displacement from sensitivity difference** — a low-recall year's masks
are smaller everywhere, so the best-fitting translation compensates for missing area. The
estimator absorbed the recall drift of §2, relabelled it geometry, and applied it, smearing
surviving canopy across removed crowns.

That rules out a family, not one implementation: a neural net learning the offset from
masks fails the same way, and so does any "consensus" quantity computed on the masks.

## 4. The rule that came out of it

The design's own kill criterion had passed the broken layer. That produced **CLAUDE.md
3.4c, the design contract**: a design may not be accepted on numbers it produced about
itself; a design validated only on synthetic data is UNVALIDATED and must say so; a kill
criterion must be shown to FIRE on a known-bad input before it counts as a gate; the
proposer never scores its own proposal.

Every measurement after this point was run under that rule, and it caught me twice more.

## 5. Kam's revision, and the gate that cleared it

The revision conditions on **mutual detection** before estimating anything: match only
clusters both epochs found, snap those, derive the transform from matched pairs alone. A
crown one epoch missed is not a landmark, so it cannot pull the fit.

`landmark_transform_gate.py` tested that before anything was built on it:

| | landmark gate | falsified block layer |
|---|---|---|
| r(estimate, measured registration) | **+0.9457** | −0.245, wrong sign |
| r(residual, recall) | **+0.148** | −0.450 |
| median error | **7.4 cm** | — |
| exact permutation p | **0.0002** | — |

Two disclosures kept with the result: the axis signs were resolved *empirically* and are
declared in the output, legitimate only because the evidence is magnitude agreement across
seven epochs that no sign choice manufactures; and n = 7 epochs.

## 6. Three things I got wrong, and what caught each

**"The transform buys nothing."** I ran the placement test at k = 8 neighbours and reported
that. An 8-point median is noisy; error decays monotonically to a plateau at k ∈ [32, 128],
and at k = 64 local beats global in 6 of 7 epochs. The conclusion's *sign* was wrong, not
its strength. Caught by an independent referee under 3.4c.

**"No gain" where the metric could not resolve one.** For the five epochs with offsets
≤ 0.43 m a perfect transform would buy 0.00–0.06 m — UNDETERMINED, not zero (CLAUDE.md
3.5). The referee's better statistic: each epoch's observed gain against what its own noise
cloud predicts for its own offset, **r = +0.9964** across all seven.

**"5 of 42 verified losses laundered."** My metric counted any heal-to-canopy at a loss
point as harm. Reading the five trajectories showed all are 2015 dropouts at points cut
*later* — `C.C.C...` → `C.CCC...`, tree present on both flanks, loss still standing at the
end. Laundering is filling the **terminal** absence, and that count is **0 of 42**. Caught
by reading the output instead of the summary.

## 7. Two questions the data answered against my expectations

**Detectability is not ordered by resolution.** Every crown-size threshold the project had
quoted was borrowed from the literature. Measured on our own archive, at a 6 m minimum
diameter 2011s (38.1 cm) recalls 0.973 while 2015 (13.7 cm — three times finer) recalls
0.9149, and 2011s beats 2015 in every size bin. Pixels-per-crown does not order our epochs;
per-epoch sensitivity does. The coarsest epochs are not the constraint anyone assumed.

**The healing problem is detection, not delineation.** On the 137,901 crowns every epoch
sees, measured extent differs by **2.3%** worst-to-best; 2011s at 38.1 cm reads 0.978
against 2024 at 6.8 cm reading 0.9707. Epochs differ in *which* crowns they find, not how
well they outline them. That deleted the scale parameter from the transplant: there is ~2%
of systematic signal to fit, per-crown variance swamps it, and a fitted scale would be free
to absorb the very sensitivity difference it should reveal.

## 8. The local field: real, and not worth using

Placement showed local beats global. But that estimate comes from the masks, so it could be
correlated detection noise. `local_field_transitivity.py` settled it with a property noise
does not have: **geometry composes.** If each epoch carries a real warp W(x), then
`d_AB = d_AR − d_BR`, and the A–B field is never consulted when building the other two.

- **Q1, is it a property of the epochs?** YES — median r = 0.5857 over 56 triples, 55 of 56
  beating a shuffled null at p < 0.05. It is geometry.
- **Q2, is it worth using?** NO — composed residual 0.4524 m against a global constant
  0.4328 m, beating the constant in only 15 of 56 triples.

Real but unexploitable. **Capped at one imagery-validated shift per epoch pair.** A degree
of freedom we did not have to spend.

## 9. What the tool is now

`temporal_heal.py`. A cell reading present → absent → present is a detection failure in the
middle epoch. Healing writes only 0→1 or 0→255, never 1→0 — proven on 200 random draws of
the full state space, not asserted. Alignment is the one validated global shift; there is
no scale parameter; the size floor is one mature crown, the scale the detectability curve
says every epoch resolves.

Tiers: **HEAL** where a lidar epoch could have vetoed a real removal and did not; **REVIEW**
post-2016 where none can; **BLIND** where the bracket spans ≥3 years, which is how far
bigleaf maple coppice gets.

Scored against the frozen gold: **0 of 42 verified losses laundered, 0 censored, 99 of 124
impossible triples removed at verified no-change points.**

`crown_trajectories.py` is the product — 211,593 crowns with validity intervals. `valid_to`
is clamped to **raw** presence, because healing is a pixel predicate while `valid_to` is a
crown-cover predicate and a healed cell could otherwise move a removal date one epoch late.
Healing may make the record of when a tree *existed* more complete; it may never extend a
life.

Reading that output found the next defect: **64% of "lost" crowns were last seen in 2021**,
which is not a wave of removals but 2024's recall deficit wearing a removal's label. Those
now carry confidence TERMINAL — flagged, never deleted, because deleting exactly that class
is what the shipped persist filter did and it discarded every verified terminal event.

## 10. The one thing the gold cannot do, and what fixes it

Panel A ruled on **2016→2024**. The HEAL tier fires only on **2011s, 2013, 2015** — every
later bracket spans ≥3 years and is BLIND. So the healer operates entirely upstream of the
interval the gold covers, and **the gold cannot score the HEAL tier directly.**

That is the binding limitation of the whole exercise, and it is not statistical. It is
answered by density: adding 2017, 2020, 2022 and 2023 turns every interior epoch inside the
Panel A window from BLIND into REVIEW, which puts healing where the 42 verified losses and
1,170 verified no-change points live.

The prerequisite nobody should skip: **a spatial sample must contain the Panel A gold
points**, or the scoring argument it exists to enable evaporates.


---

## 14. What the literature says about this design (2026-09-08)

Source: `Reports/LIT_HEALING_ANALOGUES_2026-09-08.md` (ten fields, 72 mechanisms, 26
skeptic-adjudicated; registry entry `experiments/lit_healing_analogues.yaml`).

**Solid ground.** Every field supplies the shape of bounded backfill — bracketing, gap
caps, asymmetric birth/death, threshold relaxation under temporal support, size floors
from a completeness curve. Two of our choices are stricter than anything found: the
both-sides rule (canopy before AND after the gap) is ours alone — every probabilistic
mechanism the finders recommended fills from one anchor or none; and our hard gates (gap
length in years, size floor, lidar veto) do the work that four fields' shared formula
would do with a parameter we do not have. That formula, fill odds
= (1−ε)^(k+1)·∏(1−p_t) / [ε·γ·(1−γ)^(k−1)] (occupancy, HMM, interval-censored, astronomy),
needs γ = P(regain | recent removal) in its denominator; the panel supplies
P(colonisation | empty site), three orders of magnitude smaller and the wrong quantity,
so any posterior built on it returns HEAL for every gap (§3 of the report). The tiers
encode the missing rate as a rule; that is why they work when the formula cannot.

**Where it cuts.** (1) 0 of 42 laundered is an exact 95% upper bound of 6.9%, not zero.
(2) Under a both-sides rule only losses with a detection AFTER the loss are at risk, so the
at-risk denominator (n_eligible) must be published with the count; if small, the criterion
is near-vacuous. (3) The one-directionality theorem bounds 1→0, which we forbid by
construction, and bounds nothing on 0→1, the failure that matters. Two assumptions cut
the other way: misses are correlated across years (recall vs canopy fraction r = 0.91),
which makes every independence formula err toward declaring loss — the impossible-triple
criterion at the 1,170 no-change points guards that side; and p_t measured against
projected-2020 labels is circular outside the verified interval, biasing toward filling —
the BLIND tier guards that, as a rule not a measurement.

**Changes, in order.** (a) Gap-length spectrum H(L) with laundered(L), triples(L),
n_eligible, crowns-deleted — zero labels (`qc/instruments/heal_gap_spectrum.py`).
(b) Fill-side laundering audit: ~300 cells sampled from the healer's own output, paired
interval reads, a null-change control pair, adjudicator sub-checked on lidar/finer
imagery — bounds the fill-side rate below 1% in one session where the loss side would
need ~8,650 points (`qc/instruments/heal_fill_audit_sample.py`). (c) Measure
γ_conditional from adjudicated impossible triples at the no-change points — the only
population where loss-then-regain can appear; the 42 losses are selected for no regain
and cannot yield it; the annual cadence of heal_infill_2017_2023 is what makes those
triples observable. (d) Add the fill-odds Λ per healed gap as an AUDIT column beside the
tier that licensed it, and run a plain 1-D morphological closing as the comparator
baseline, never yet done.

**Refuse** until γ_conditional is measured: any posterior-as-licence (PMBM existence,
dynamic-occupancy posterior, SAR-EM imputation, fitted-transition HMMs).


---

## 15. The three literature tests, run on the 8-epoch stack (2026-09-08)

Instruments: `qc/instruments/heal_gap_spectrum.py`, `heal_fill_audit_sample.py`,
`heal_fill_odds.py`, `heal_closing_baseline.py`; tables under `phase4/qc/`; every number
below is read from them.

**The primary kill criterion has no power.** `heal_gap_spectrum.csv`: `laundered_at_risk`
is 0 in every gap bucket. A verified loss's terminal absence runs to the end of the series,
so the epoch after any interior epoch inside it also reads absent and a both-sides fill can
never touch it; every published alignment shift quantises to zero 2 m cells; 0 of 1,214 gold
points have a terminal absence filled anywhere. "0 of 42 laundered" certifies nothing about
any both-sides rule (also proven as a theorem by the closing baseline's tests). The
impossible-triple criterion keeps its power (124 → 99). `laundered_eligible` = 28 at L=5 is
the population a one-sided or REVIEW-tier rule would put at risk. The campaign rule in
`experiments/heal_infill_2017_2023.yaml` carries a dated amendment naming the fill-side
audit and the triples as the operative tests.

**The fill-side audit is drawn and waiting for a reader.** `heal_fill_audit_sample.csv`:
300 fill components + 300 matched controls, stratified by tier × gap × size, 220 rows
adjudicable against the 2016 lidar. Two facts from the draw: REVIEW has zero population on
8 epochs (every post-2016 bracket spans ≥ 3 years, so tier and gap are collinear until the
heal_infill years land), and the literal control population — untouched bracketed absences
above the floor — is 0 by the operator's definition, so the control is one-sided absences
(a discrimination control, not a blinded error-rate control). At n = 300 and k = 0 the
fill-side bound is 0.99%; the adjudicated floor (55–120 rows) resolves 2.5–7.9 pp.

**At equal cap, the healer is a plain closing plus the size floor.** `heal_closing_baseline.csv`:
the tier-matched 1-D closing's citywide fill count equals the sum of the healer's
`candidate_cells_raw` over the three HEAL epochs exactly (449,663), because all shifts round
to zero cells at 2 m — the landmark transform is inert on this grid. Healer − closing is the
28 m² floor alone: −129,766 cells (−28.9%) and −10 triple fixes on the same epochs (58 vs 68).
Whether the floor is a gain is UNDETERMINED: eligible terminal 0, eligible in-interval 4,
and the four share one shape (2016 canopy, 2019 absent, 2021 canopy, 2024 absent) where the
2024 removal survives any fill.

**The fill-odds statistic is inert here, as predicted.** `heal_fill_odds.csv`: under the
panel's γ (2 gains / 1,214 points) the formula licenses every fill; under the rule-implied
γ = 0.20, 97.5% of fills fall below posterior 0.99 but none below 0.5 (median odds ~20:1 for
FILL). 8,034 of 32,190 fills overlap no 2020 crown and carry no Λ. 53% of fills sit on crowns
already above 0.40 cover, so "fill = the crown's miss event" is false for the majority.

**What follows.** (1) The reader session on the 300 + 300. (2) γ_conditional from adjudicated
impossible triples at the no-change points once the 12-epoch stack exists. (3) A design
question the closing baseline raises: with the transform inert at 2 m and the tiers
collinear with gap length on this cadence, the healer's measurable content is the size floor
and the tier vocabulary; the density experiment is what can change that.

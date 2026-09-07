# CROSS-YEAR MASK REFINEMENT — design, and one falsified component

**2026-09-06.** Kam's design session: stop one-shotting each year; let every epoch inform
every other. Five design agents, five adversarial referees, all on Opus. Four parts came
back SOUND-WITH-FIXES. One came back BROKEN — and it is the one everybody, including me,
expected to be the clever part. That result is the most valuable thing in this document.

Supersedes nothing; extends `CHANGE_DETECTOR_DESIGN_2026-09-06.md`, whose conclusions all
survive. Registry entry: `experiments/change_detector_design.yaml`.

---

## 0. Kam's design notes, recorded verbatim

> "Our first mistake might be that we are trying to one shot each year… Every year has
> information similar to the next year… a mature crown has likely been mature for a
> while, so when mature crowns go away, but pop up again we can use lidar from 2005 and
> 2016 to know they are there."

> "Instead of taking that label from the future, and dropping the pixels right where it
> was found, we can take the mask of the future label that has spotted the tree, and then
> we can learn how that portion connects to the rest of the mask its appended to…
> we need to teach the relationship of the tree to the rest of the mask because it will
> share a general shape with the previous year… create an adjustment of where the tree
> might be by looking for an offset between these two known areas."

> "What semantic does well is generalize clusters, whereas instance feels pressure to
> outline and not tackle dark areas."

The first and third notes are upheld and are the backbone of the design below. **The
second is falsified as stated** — not the intuition behind it, but the specific mechanism
of deriving a local offset from mask agreement. §3 is that result.

---

## 1. The measured license: the error is one-sided

`phase4/qc/sensitivity_sawtooth.csv` (instrument: `qc/instruments/sensitivity_sawtooth.py`).

Matched cuts pin **precision** by construction and leave recall free. Across the eight
epochs recall spans **0.6955–0.8260** and tracks reported canopy fraction at
**r = 0.9089**, exact permutation p = 0.0018 over all 40,320 orderings, leave-one-out
never below 0.835. And matching the operating point **did not reduce the jitter at all** —
mean |year-to-year step| went 3.06 pp (delivered cuts) → 3.29 pp (matched).

So the residual sawtooth is the detector's sensitivity moving, not the canopy. Combined
with the flicker census — three non-vegetated parcels holding 0.0–0.7% false canopy, flat
across all eight years (`experiments/flicker_parcels_census.yaml`) — the error is
**one-sided: the model misses real trees; it does not invent them on bare ground.**

That asymmetry is the entire license for an asymmetric correction, and it is why the
symmetric median-3 failed: that filter assumes symmetry and regresses the best-calibrated
year toward its worst neighbours (correlation −0.999 with deviation-from-neighbour-mean).

**This does not rescue annual canopy percentages, and nothing below claims to.** See §5.

---

## 2. What survives: bounded, one-directional healing

**The operator.** For an interior epoch *t*, a cell whose state reads
canopy → absent → canopy across (t−1, t, t+1) is a HEAL CANDIDATE. Healing writes only
`0 → 1` or `0 → 255` (IGNORE). It can never write `1 → 0`. Three referees independently
tried and failed to construct an input where the layer removes canopy or manufactures a
loss: `apply_heal` writes only upward, so crown cover is monotone non-decreasing under it
and no consumer can see a downward move.

**Why this is not median-3.** Median-3 is symmetric, unconditional and per-year: it moves
every epoch toward its neighbours whatever the evidence, which is how the best-calibrated
year gets dragged toward the worst. Healing is asymmetric, conditional on a specific
bracketing pattern at a specific location, and can only add. The distinction is not
rhetorical — it is the difference between a filter that acts on the *level* and an
operator that acts on *identified absences*.

**Measured candidate volume** (referee, on the cached `trend8_stack_2m.npz`): the un-gated
maximum heal is 2011s 129,951 cells = 2.11 pp of the city, 2013 1.29 pp, 2015 3.90 pp,
2016 1.77 pp, 2019 3.46 pp, 2021 1.09 pp. The union of interior candidates is
**707,603 cells = 11.48% of the city** — note this is *not* the 17.83% canopy-gone-canopy
figure in `trend8_transition_census.csv`, which counts the pattern anywhere in the series.
A design draft cited the census number as if it were the candidate set; it is not.

**The unit.** Connected components are confirmed dead, harder than the record said: the
largest ever-canopy component is **692.1 ha = 52.1% of the 1327.4 ha ever-canopy domain**
(the record's 221.7 ha understated it). The working partition is ever-canopy components
intersected with a 6×6-cell lattice, capping any unit at 144 m². That reproduces exactly
and is non-percolating by construction — which also means the design's "percolation" gate
**cannot fire and is not a gate**.

---

## 3. FALSIFIED: the local offset derived from mask agreement

Kam's second note proposed deriving a local translation from the overlap of the *known*
parts of two epochs' masks, then applying it to the candidate region. A design agent built
it; its referee re-ran it **on the real eight epochs instead of the synthetic
block-constant field the design had been tuned against**, and it fails four ways.

**It attenuates signal 2.2× more than noise — the smoothing trap's defining signature.**
On the verified gold: mean max-step on verified LOSSES drops 0.766 → 0.714 (−0.052); on
verified NO-CHANGE 0.622 → 0.595 (−0.023). A correction that works removes more noise than
signal. This one does the reverse, and at the certifier's 0.2 gate it is strictly worse on
both axes (loss fires 42/44 → 40/44; false fires unchanged at 29/34).

**It fabricates canopy and manufactures loss.** Of 20,529 units whose raw 8-epoch cover
never decreases, **872 are given a ≥0.2 step drop** by the correction (731 at ≥0.3). The
worst case, unit 156525, goes from a pure gain `[0,0,0,0,0,0,0,1]` — canopy appears only
in 2024 — to `[1,0,0,0,0,0,0,1]`: the correction **invents full canopy in 2009 and a
2009→2011s loss that never happened**. Citywide, 6,318 of 53,454 corrected terminal fires
(11.8%) exist only because of the correction.

**And the diagnosis is the interesting part: the offset is not tracking registration.**
Against `phase4/qc/coregistration.csv`, the correlation between a year's p68 scatter and
its share of shifted blocks is **r = −0.245 — the wrong sign**. Against recall at the
matched cut it is **r = −0.450**. Concretely: 2013, the *worst*-registered epoch
(p68 3.94 m), receives the *fewest* offsets (14.7% of blocks); 2024, the *lowest*-recall
epoch (0.6955), receives the *most* (33.6%); and 2021 — effectively perfectly registered,
p68 0.86 m, median shift ~0.10 m — still has 25.5% of blocks shifted by a median 2.00 m.

**Mechanism.** Estimating a shift from mask agreement cannot separate *geometric*
displacement from *sensitivity* difference. When an epoch's recall is low its masks are
smaller everywhere, and the best-fitting translation is a spurious shift that partially
compensates for the missing area. So the estimator absorbs the very recall variation of §1
and relabels it as geometry — then applies it, smearing surviving canopy across removed
crowns. That is how it erased verified losses, and it is precisely the pid 815 failure
(a single-crown removal at a stand edge, voted back by its surviving neighbours) arriving
through a new door.

**The design's own kill criterion could not catch this.** It asked whether *injected*
crown-scale removals move a block's offset. The real failure needs no such movement: the
offset moved for unrelated reasons and the displacement did the damage. A kill criterion
aimed at the wrong mechanism passes a broken layer.

### What replaces it

**Registration must be estimated from something that is not the thing being corrected.**
`qc/instruments/coregistration.py` already measures inter-epoch displacement by phase
correlation on fixed ~64 m *imagery* chips, with medians (correctable) separated from p68
scatter (evidence width, uncorrectable). That is an independent estimator and it is
already gated. The corrected design uses it as a **tolerance**, not a shift: a heal
candidate must bracket within the epoch-pair's measured scatter, and at ≥2 m scatter that
is explicitly a *neighbourhood* test, not an identity test. Kam's intuition — that a
mature 6–10 m crown is not fully displaced by a 0.86–3.94 m error — is exactly right and
is what makes a tolerance test viable. What is not viable is inferring the displacement
from the masks themselves.

---

## 4. The loss-laundering path nobody had named

A referee found the failure mode that matters most, and it is not coppice.

**A real clearing at *t*, followed by post-clearing ground vegetation — grass, blackberry,
brush — read as canopy at *t+1*, produces exactly the canopy→gone→canopy pattern.** The
heal fires, the ABSENT is demoted, the validity-interval walk-back in
`pipeline/builders/build_validity_intervals.py:134` no longer stops, and the interval
spans a real removal. The event is erased.

This is not an edge case. `experiments/flicker_parcels_census.yaml` says the model's
instability *is* sensitivity on real vegetation, which is what post-clearing regrowth is.
For *t* ∈ {2019, 2021} the exposure is **280,358 candidate cells = 4.55 pp of the city**,
and **no lidar epoch exists to veto it** — 2005 and 2016 are both upstream. The only
screen is the 42-positive gold, which carries ±7.3 pp.

Handling: any heal whose bracket lies entirely after 2016 gets no structural veto and must
be routed to review rather than applied silently. Coppice gap-blindness compounds this —
bigleaf maple reaches a 6.5 m crown in three years and the largest gaps are exactly three
(2016→2019, 2021→2024) — and the size features that would distinguish replacement from
persistence are earned only at the ~7 cm epochs, dead at 26–38 cm, and may never cross an
unlabelled leaf-state boundary.

---

## 5. The output restriction, and why it is not a compromise

Interior epochs can be healed; **2009 and 2024 cannot** — they have one side only. 2024 is
also the worst-recall epoch in the series (0.6955). So healed masks feeding the annual
fraction series would lift every interior year while the endpoints stayed put,
**manufacturing decline on 2016→2024, the headline interval.** That is the smoothing
trap's mirror image, and harder to catch because it moves the number the way we expect.

Therefore: **healed output feeds per-location trajectories, validity intervals
(CLAUDE.md 3.8) and change maps. It never feeds the annual canopy fraction.** Panel A
(−2.21 ± 1.10 pp) and the matched cuts remain the level and trend authority.

This is not a consolation prize. The city's question is not only "what percent" but
"where, and when did it go" — and per-location history is the product that answers siting,
enforcement and canopy-ordinance questions. The fraction series already has an honest
answer from Panel A; the trajectory layer is the thing that does not exist yet.

A referee also found that the interval consumer needs an explicit clamp: healing is a
*pixel* predicate while `valid_to` is a *crown-cover* predicate at 0.5, so a healed cell
can push a crown over the cover threshold and shift a recorded removal date one epoch
later. Assertion in a test is not enough; the clamp belongs in the consumer.

---

## 6. Kill criteria that can actually fire

The referees killed most of the proposed gates. Recorded, because a gate that cannot fire
is worse than no gate — it reads as rigour:

- **Cannot fire:** the K4 heal ceiling (set 1.8–4.4× above the un-gated maximum, and
  computed against a C-CAP-harmonised level while healed area would be raw map area);
  percolation (144 m² cap makes it true by construction); the hard-negative parcel test
  (Water is 0.00% canopy in all eight epochs, so the bracketing pattern is arithmetically
  impossible there).
- **Logically inverted:** the lidar 2005/2016 "false heal" counter labels *state at two
  instants*, not change — a heal at 2011s on a cell cut in 2014 is *correct*, and this
  gate counts it as an error. The repo already adjudicated this against a predecessor
  design (`CHANGE_DETECTOR_DESIGN_2026-09-06.md:55`). Lidar's valid use here is as a
  conservative **veto**, never as a scored counter.
- **Grid-dependent:** the same statistic ranges 1.2%–12.0% across six defensible
  resampling choices onto the analysis lattice, crossing its own 2% kill line in three of
  six. A gate whose verdict is set by an unwritten reprojection parameter is not a gate.

**Gates that survive:** beat weighted precision 0.431 (the fit-free certifier, not the
0.249 raw rule); gross loss and gross gain scored separately, never a net; terminal-class
recall ≥ 10/13; certified area within 1.5× of 2.29 pp truth, kill at 2×; every recall
number printed with ±7.3 pp.

---

## 7. Build order

1. **Freeze the gold set** — still the blocker for everything, still not done.
2. **Port the two unported findings**: the smoothing trap (no fact home) — the sensitivity
   sawtooth is now ported (§1).
3. **Healing operator, deterministic, one-directional**, with the tolerance test of §3 and
   the post-2016 review routing of §4. Score against the surviving gates of §6.
4. **The enriched confirmatory draw** — ~150 positives, Panel-A protocol, stratified on
   detector fires. The 42+1169 are spent as a development set; no recall difference under
   ~10 pp is ever resolvable on them.
5. **Only then the second model.** Kam's instinct that a learned refiner belongs on top of
   the mask stack is sound, and it is unvalidatable today: with 42 positives, held-out
   recall has sd 7.3 pp. Build the deterministic layer, earn the labels, then learn.

**What is genuinely first-of-its-kind here** is not the healing — that is bounded temporal
inference, and elements exist in the literature. It is the combination the overnight hunt
established has no published twin: a wall-to-wall map series from a heterogeneous
sub-meter archive that *measures its own inconsistency* and *validates change against
blind human truth*. This document adds a second thing worth publishing: a negative result
with a mechanism — mask-derived local registration is not separable from sensitivity
drift, and applying it attenuates real signal more than noise.

---

## 8. Provenance

Workflow `wf_d1e5d091-e68`, ten Opus agents (five design, five adversarial referee),
2,510 s, 1.32 M tokens. Referees re-ran the designs' own prototypes on the real stack
rather than accepting their numbers; that is what produced §3. Verdicts:
healing-operator SOUND-WITH-FIXES (13 defects), trajectory-taxonomy SOUND-WITH-FIXES (12),
validation SOUND-WITH-FIXES (7), healing-detail SOUND-WITH-FIXES (16), unit+offset BROKEN
(10) — the partition survives, the offset layer inside it does not.

Every number above is either from a tracked file named in place, or from a referee's
re-run of a prototype whose script path is recorded in the workflow journal. The
prototypes themselves live in session scratch and are **not** reproducible from repo+lake
until ported — the same defect the previous design doc flagged about the smoothing trap,
and it is flagged here rather than worked around.

---

## 9. ADDENDUM — the detectability curve, measured (Kam, 2026-09-06)

> "Perhaps the detectability should be on a curve. So we can measure how detectability
> threshold impact the recall."

Correct, and it exposed that every crown-size threshold this project had quoted was
BORROWED. Hao 2023's 50 px/tree floor and Pouliot 2002's RMSE ladder are the only sources
behind the angle-10 GSD gate, and that audit itself ruled both transfers shaky — Hao
measured a weeded single-species plantation from sub-centimetre drone imagery, and
Pouliot's adjudicating skeptic ruled his crown-to-pixel ladder inapplicable to urban crowns.

`qc/instruments/detectability_curve.py` measures ours instead. A crown is taken as PRESENT
at epoch *t* when both flanking epochs see it — evidence from imagery other than *t* — and
recall at *t* is the fraction of those bracketed crowns *t* also sees, binned by diameter.
173,697 bracketed crowns; local CPU, ~2 min.

**Result 1 — the curve is real and it is shallow.** Within an epoch, recall climbs
monotonically with diameter: ~0.75–0.95 in the 0–2 m bin to 0.97–0.997 at 14 m+. A size
threshold does buy recall, but far less than the borrowed floors predict. At 2011s
(38.1 cm effective) a sub-2 m crown is a handful of pixels, where Hao's transferred curve
would give ~0.20 recall; we measure **0.835**. The literature floor understates our
detectability badly, and the angle-10 gate built on it was over-conservative at the small
end. (Caveat that bounds this: bracketing conditions on being detectable *somewhere*, so
the small bins are enriched for easy small crowns and these are upper bounds.)

**Result 2 — and this is the finding — detectability is NOT ordered by resolution.**
At a 6 m minimum diameter:

| epoch | effective GSD | recall ≥6 m |
|---|---|---|
| 2013 | 13.2 cm | 0.989 |
| 2019 | 12.6 cm | 0.979 |
| 2021 | 12.6 cm | 0.979 |
| **2011s** | **38.1 cm** | **0.973** |
| 2016 | 35.4 cm | 0.968 |
| **2015** | **13.7 cm** | **0.915** |

**2011s at 38.1 cm beats 2015 at 13.7 cm — three times finer — at every size bin in the
table.** So pixels-per-crown does not order our epochs, and a size gate derived from GSD
is measuring the wrong variable. Whatever separates 2013 (0.989) from 2015 (0.915) at
near-identical resolution is per-epoch sensitivity, not sampling. 2015 is the series' one
explicitly LEAF-OFF epoch and 2013 is "Fully leaf-on"
(`qc/imagery_pixelsize_and_date.csv`), which is a plausible driver and is NOT established
here — the greenness-gradient work attributed a related effect to delivery radiometry
rather than phenology, and this instrument cannot separate the two.

**Consequence for the sieve.** The minimum-diameter threshold must be an operating point
chosen PER EPOCH off this curve, not a constant justified by GSD. And the coarse epochs are
not the constraint anyone assumed: 2011s and 2016, the two coarsest in the archive, sit
mid-table. The binding constraint is 2015, one of the finest.

This also revises §3's framing. I had written that mature-crown features are admissible at
every epoch *because* the pixel count clears Hao's floor. The conclusion holds — they are
admissible — but the stated reason was the borrowed one, and the measured ranking shows
pixel count is not what decides it.

---

## 10. ADDENDUM — the transplant, and why it escapes §3 (Kam, 2026-09-06)

Kam clarified the mechanism, and the clarification matters: watershed each YEAR'S mask
into clusters (not the frozen 2020 crowns), match clusters between epochs, and where a
cluster is missing in the year being healed, **copy the donor cluster and place it** using
two degrees of freedom — a translation, and a scale to absorb "lens differences".

**This is not the falsified layer, and the difference is precise.** §3's offset was
estimated per block and applied to the mask's EXISTING content — which is how it displaced
surviving canopy across removed crowns and erased verified losses. In the transplant,
nothing existing moves. The only thing placed is the newly added object. The
one-directional guarantee survives at the pixel level, and the worst failure changes from
*erasing a real loss* (signal-destroying) to *placing healed canopy a few metres off*
(a bounded spatial-accuracy cost). That is a far better failure mode, and it is the reason
the transplant is worth building where the offset layer was not.

**The scale parameter, however, should be deleted — measured, not fitted.**
`detectability_curve.py`'s `conditional_cover` rows: on the **137,901 crowns every epoch
sees**, mean measured cover spans **0.9699 (2015) to 0.9926 (2021) — a 2.3% systematic
difference across the whole archive.** 2011s at 38.1 cm reads 0.978; 2024 at 6.8 cm reads
0.9707. Effectively identical, at a 5.6× resolution difference.

So epochs differ in **which crowns they find, not in how well they outline the ones they
find.** The healing problem is DETECTION, not DELINEATION. There is only ~2% of systematic
size signal available, per-crown variance will swamp it, and a fitted per-cluster scale
would be fitting noise — worse, it would be free to absorb exactly the sensitivity
difference §3 showed a fitted geometric parameter will happily absorb. Fix the scale at
1.0. If a correction is ever wanted, take it from this table as a per-epoch-pair constant,
never from a per-cluster fit.

(Caveat: cover is measured inside the frozen 2020 polygon and cannot exceed 1.0, so the
2.3% is compressed by a ceiling; and the all-eight-epoch population is the easiest one.
Both make this a lower bound on agreement, which is the direction that favours the
conclusion.)

**Choosing the cluster size — the question Kam flagged as open — is now readable off the
curve.** Cumulative recall on bracketed crowns at or above a minimum diameter:

| min diameter | crowns | worst epoch (2015) | best epoch (2013) |
|---|---|---|---|
| ≥3 m | 172,748 | 0.903 | 0.986 |
| ≥6 m | 153,585 | 0.915 | 0.989 |
| ≥10 m | 84,010 | 0.947 | 0.994 |
| ≥14 m | 27,774 | 0.970 | 0.997 |

Raising the threshold buys per-epoch reliability and costs population: ≥6 m keeps 88% of
the crowns at 0.915 worst-epoch recall; ≥10 m reaches 0.947 but discards 45%. That is the
tradeoff, and it should be chosen per epoch rather than once — the binding epoch is 2015,
not either of the two coarsest.

**Open, and genuinely open:** the watershed markers. Per-year instance segmentation of a
semantic mask needs a marker rule, and the marker spacing IS the "what size cluster"
parameter in disguise. Connected components cannot do it (§2: one component is 692 ha).
This is the one part of the transplant with no measured guidance yet.

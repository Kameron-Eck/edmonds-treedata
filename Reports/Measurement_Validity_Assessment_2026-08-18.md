# Measurement Validity — What We Know, What We Need to Know

**Date:** 2026-08-18 · **Scope:** the Edmonds temporal canopy pipeline's evaluation layer
**Sources:** `Scripts/CHATLOG.md` STATE · `Scripts/honest-measurement-overhaul.md` ·
`Literature_Tracker.xlsx` IDs 69–105 (Phase 4, measurement validity)
**Status of this document:** assessment only. Where it disagrees with the active plan,
it says so and proposes an amendment. It does not edit the plan.

---

## 0. The one-paragraph version

We have an unusually well-measured model and an unusually weak ability to say whether
the measurements mean anything. Three results are solid and replicated: detection is a
monotonic function of canopy height, the deficit is inherited from the 2020 label mask
rather than developed by each year's model, and model quality does not move the honest
number. All three are *internally* consistent and all three are measured against
references that disagree with each other on 15–17% of pixels. Phase 3 — the human
sample — is correctly identified in STATE as the blocker for every open decision. The
finding of this assessment is that **Phase 3 as currently scoped cannot unblock those
decisions**: at 250 points per year it can confirm an effect we already know exists,
and it cannot resolve either question that is actually holding up a decision. The fix
is not more points first — it is writing the canopy definition down, then re-deriving
the sample size from the question we most need answered.

---

## 1. What we know

### 1.1 Solid and replicated

**Detection is a function of canopy height.** 2016 baseline recall by CHM band:

| band | 0–2 m | 2–5 m | 5–10 m | 10–15 m | 15–20 m | 20–25 m | 25–30 m | 30 m+ |
|---|---|---|---|---|---|---|---|---|
| recall | .16 | .16 | .36 | .57 | .74 | .83 | .88 | .93 |

The 5–15 m span holds 53% of all missed pixels. Lifting those two bands to the 20–25 m
rate takes overall recall .68 → ~.80. (`qc/height_curves.png`)

**The deficit is inherited, not developed.** `phase3/edmonds_canopy_mask_2020.tif` — the
label source for every coarse year — has the same staircase and sits *below* its own
students at every band (.5455 overall vs the 2016 model's .6821). Coarse years are
taught the blind spot. Improving that one mask lifts every coarse year at once.

**Model strength does not move the number.** Nine live years span IoU .49–.76 and
AUROC .938–.954 while honest recall stays pinned at .51–.78 with no correlation to
model quality.

**The two references disagree on 15–17% of pixels, four times out of four** (2016,
2019n, 2021s, 2022n). The NDVI+CHM reference is systematically more liberal
(`ndvi_only` 10–14% vs `ccap_only` 1.9–5.7%). On 2021s they differ by 12 points on the
same year and the same ground, so this is not vintage drift.

**The honest baseline** (live rows only, vs C-CAP, `forest_wetland`, deployed threshold):
2013 .709/.855 · 2016 .684/.865 · 2000 .630/.775 · 2015 .622/.884 · 2002 .507/.838.
Against the NDVI reference, 2016 is .594/.959. Read: a high-precision under-predictor.
Scrub recall .25 vs forest .68.

### 1.2 Known and under-used — the visual grounding

This is the most decision-relevant thing in STATE that the five headline findings omit.
Of 8/8 missed stands inspected, **all were suburban** — houses, lawns, ornamental yard
trees, many of them purple-leaf and low-NDVI. **Zero were deciduous forest.** That
splits the ~0.32 recall gap into two mechanisms that need completely different fixes:

1. C-CAP definitionally **over-counting** leafy suburbs as "Upland Forest" — it counts
   the lawn and roof *between* yard trees. Not a model error.
2. The model genuinely **under-detecting** scattered suburban/ornamental crowns,
   including non-green ones.

**This confounds the height curve.** Short trees live in yards; tall trees live in
stands. So "recall by height band" and "recall by land-use context" are correlated in
our data, and we have not separated them. Some unknown share of the height staircase
may be a suburban-vs-forest staircase wearing a height costume.

### 1.3 Negative knowledge — hypotheses already killed, do not retry

- **Threshold artifact** — killed. The 2016 sweep moves recall only .669 → .747 across
  the entire 0.5 → 0.2 range.
- **Class balance** (run C), **dice term** (run D), **BN drift** (run E), **pos_weight**
  (round 1) — all killed as causes of the 2016 collapse.
- The real 2016 "collapse" cause was the **sampler** (1/count[site] gave every pure-negative
  site the mass of a city → batches ~83% background) plus a **val_iou@0.5 metric artifact**.
  Both fixed in v039/v038.
- **Architecture** — implicated only weakly. Finding 3 (model strength does not move the
  number) is the direct evidence against architecture being the constraint, and Ferraz
  2016 (ID 85) and Turubanova 2023 (ID 83) confirm the same height-monotonic shape
  appears in lidar and in Landsat, i.e. it is a property of canopy remote sensing.
- **`qc_indep` is not pessimistic** for lacking an imagery-footprint mask — tested,
  0 px dropped on 2016. Do not "fix" it.

### 1.4 Corrections that must not regress

- Honest 2016 recall is **.6821**, not .7623. The higher figure is a stable∩2021 subset.
- "Misses are confident and structural, so labels beat compute" is **2016-only**.
  Miss-depth (`conf%`, fraction of missed forest with prob < 0.12): 2016 ~60% but
  2013 **9.3%**, 2002 19.4%, 2000 24.1%. For 2013, 91% of misses sit between 0.12 and
  threshold — near-threshold and potentially recoverable by **calibration**, not labels.
  Confounded with sensor (2016 is native NIR-era; the others are cross-sensor RGB).
- There is no git remote. `git pull` cannot update Colab; Drive is the sync path.

### 1.5 What the literature settles

- **Stratifying on the reference is legal** (Stehman 2014, ID 72). Strata may differ from
  map classes — CHM band, or C-CAP/NDVI agreement — provided its estimators are used.
  Unbiased; variance inflates. Our intended design is defensible.
- **How you score interpreter uncertainty moves accuracy more than our entire model-quality
  range.** NLCD overall accuracy is 77.5% on the primary label and 87.1% if an alternate
  label also counts (Wickham 2023, ID 78) — a 10-point swing from a scoring convention.
- **C-CAP's own accuracy paper disclaims our use of it** (McCombs 2016, ID 77): validated
  on a 3×3 unit with a six-of-nine homogeneity rule, OR/WA 84.9%, and described as a
  *screening* tool for local decisions. Some of the 15–17% is scale misuse, not model error.
- **Reference-error direction depends on correlation** (Foody 2010, ID 79): 10% reference
  error under-estimates producer's accuracy by 18.5% when errors are independent, but
  *over*-estimates it by 12.3% when correlated. See §3.4 — the direction differs per
  reference, and it is not a single blanket claim.
- **There is a principled way out of "we cannot tell which is right"** (Foody 2022, ID 80):
  latent-class modelling treats C-CAP, the NDVI reference and the model as three imperfect
  tests of one latent variable and solves for each one's sensitivity and specificity —
  with no gold standard. Disagreement becomes the estimator's input rather than its obstacle.
- **The intervention that works on height bias is stratify-then-segment**, not a better
  single pass (Hamraz 2017, ID 86): +22.1% understory recall at −15.0% precision.
- **Adding small-crown training examples recruits shrubs** (Guo 2023, ID 88). This is the
  most likely account of finding 5.
- **Patch sampling under-samples small-area features by construction** (Clark 2023, ID 87).

---

## 2. What we need to know

Ordered by the decision each unknown blocks, not by topic.

### U1 — What counts as canopy? *(no instrument yet; blocks everything below)*

**Decision blocked:** all of them. **Status:** no written operational definition exists.

There is no recorded rule for minimum height, minimum crown area, shrub versus short
tree, or whether a lawn under a yard tree is canopy. The C-CAP/NDVI dispute is partly a
definitional dispute (Gutiérrez-Vélez 2024, ID 81: most cross-product forest disagreement
is manufactured by thresholding one continuous variable at different cut points). Without
a written definition the 250-point run does not arbitrate between two references — it
produces a third opinion.

**Cheapest instrument:** a one-page definition, written before any point is interpreted,
committed to the repo. Decide explicitly: minimum height (our bands start at 0–2 m and
the corrected-label overlay already uses ≥3 m canopy / 2–3 m IGNORE — make that the
definition or change it deliberately), shrub handling, and whether we report a binary
mask or a continuous cover fraction with the threshold stated.

### U2 — Which reference is closer to truth? *(blocks: 2016c deploy, and every quoted number)*

**Decision blocked:** 2016c deploy/no-deploy. Corrected labels moved recall .6844 → .8718
but precision .8651 → .7296; on the both-agree subset it is clearly better (F1 .853 → .937);
the entire question lives in the contested ~16%. **Status:** P2 has bounded it; nothing
has measured it.

**This is where the sample-size problem bites — see §3.**

**Cheapest instrument, in order:**
1. **Foody 2022 latent-class** on C-CAP × NDVI-ref × model, on the years where all three
   exist. Local, no GPU, no new labelling. Gives each source a sensitivity/specificity
   without a gold standard. This should be tried *before* spending human hours.
2. Human sample sized to the question (§3), cross-tabbed against C-CAP to measure C-CAP's
   own error rate — which retro-corrects every Phase-0 and Phase-2 number.

### U3 — Is the height curve actually a height curve? *(blocks: where to spend label effort)*

**Decision blocked:** whether the fix is height-conditioned modelling (Hamraz) or
suburban/ornamental labels (the annotation plan's item 1). **Status:** unmeasured; the
8/8 suburban visual grounding says the two are confounded.

**Cheapest instrument — computable this week, local, no GPU:** recompute **recall by
height band within each P2 agreement partition** (both-agree vs contested). If the
staircase survives inside both-agree, it is a height effect. If it flattens inside
both-agree and lives mostly in the contested band, it is largely C-CAP's suburban
over-counting. Every input already exists.

### U4 — Labels or calibration? *(blocks: the next workstream after P1–P4)*

**Decision blocked:** whether to commit to hand-tracing stands. **Status:** open, and
STATE explicitly warns against deciding on 2016's number alone. 2016 is ~60% deep-confident
misses; 2013 is 9.3%. If most years' misses are near-threshold, calibration is far cheaper
than annotation.

**Cheapest instrument:** recompute the miss-depth histogram per year on the full-forest
denominator under one recipe (`--force-citywide`), as P1c already specifies. Local.

### U5 — Is the training set starving the model of small crowns? *(blocks: label plan design)*

**Decision blocked:** whether the annotation plan's item 1 is necessary or whether a
sampling change gets part of the way free. **Status:** untested.

**Cheapest instrument (Clark 2023, ID 87):** re-sample the 2020 training patches
stratified by CHM band and retrain one year. If low-height recall moves, part of the
deficit was patch-sampling composition, not label content. One Colab run.

### U6 — Is the CHM good enough to be the stratification axis? *(blocks: interpretation of U3)*

**Decision blocked:** how much of the height staircase is CHM error. **Status:** unvalidated.
The CHM is ~2016 vintage at **59.8% coverage**, applied across 2000–2024. Moudry 2024 (ID 84)
finds global canopy-height products are systematically height-biased; Sierra 2026 (ID 98)
puts realistic CHM MAE near 3 m — which would materially blur 5 m-wide bands.

Also unasked: **the height curve is computed only where the CHM exists.** We have not
checked whether the 40% without CHM differs in canopy composition. STATE argues the gap
is mostly water and southern margin, but that is an argument, not a measurement.

**Cheapest instrument:** validate CHM heights against the 250-point sample where it
overlaps; and report what fraction of city canopy sits outside CHM coverage.

### U7 — Can a human even interpret the 2000/2002 imagery? *(blocks: whether pre-2016 is measurable at all)*

**Decision blocked:** whether King 2000/02 ship as low-confidence or get their own labels.
STATE already calls them a **hard floor: un-trainable and un-measurable from 2020 labels**.
**Status:** assumed feasible; never tested.

At 60 cm with no NIR, distinguishing a short tree from a shrub — the call that matters
most — may be beyond a single interpreter. Reis 2024 (ID 103) found three interpreters
fully agreed on under 40% of pixels on historical time-series imagery.

**Cheapest instrument:** a **20–30 point calibration block on 2000 before the production
run**, interpreted twice with a gap between passes (or by a second person). If self-agreement
on the short-tree/shrub call is poor, 2000 cannot be arbitrated by photo-interpretation and
we should know that before spending five hours.

### U8 — Mechanical blockers still in the chain

- **P1 Colab stage 1 → 2022 citywide raster → P3 `--step design`.** The first attempt
  failed (~4h, zero output, `20260817_p1_driver_abort`); driver rewritten, not yet re-run.
  2022 has no citywide prob raster, so the sample design for 2022 cannot run.
- 2017 inference is a failed run (96.5% nodata); 2015 `citywide_rgb` is a partial write.
- Note the strata decision (§3) must resolve **before** `--step design`, not before the
  Colab run.

---

## 3. The sample-size finding — Phase 3 as scoped cannot answer the blocking questions

Current scope: 250 points × 3 years (2000, 2016, 2022), ~5 hrs, strata = model output
(canopy / non-canopy / near-threshold). Below, `z = 1.96`, worst-case `p = 0.5` for recall.

### 3.1 Can it arbitrate the reference dispute? **No, not at 250.**

C-CAP says 29.5% canopy; the NDVI reference says 37.7%. Gap = 8.2 pp, midpoint 33.6%.

| n | CI half-width | 95% CI | verdict |
|---|---|---|---|
| 250 | ±5.9 pp | [27.7, 39.5] | **ambiguous — covers both references** |
| 400 | ±4.6 pp | [29.0, 38.2] | **ambiguous — covers both references** |
| **510** | ±4.1 pp | [29.5, 37.7] | discriminates at the midpoint |
| 750 | ±3.4 pp | [30.2, 37.0] | discriminates |

If the truth sits near either reference, 250 points settle it. If it sits in the middle —
which is exactly what "the two references bracket truth" predicts — **250 points return an
interval containing both, and the question stays open.** Roughly 510 points in a single
year are needed to guarantee separation. (Stratification will beat this simple-random
figure somewhat; treat 510 as the conservative planning number, not a hard target.)

### 3.2 Can it estimate per-band recall? **No.**

| points in stratum | recall CI half-width |
|---|---|
| 20 | ±21.9 pp |
| 30 | ±17.9 pp |
| 40 | ±15.5 pp |
| 60 | ±12.7 pp |
| 83 | ±10.8 pp |
| 97 | ±10.0 pp |

Under candidate allocations of one year's 250 points:

| design | points/stratum | per-stratum half-width |
|---|---|---|
| 3 strata (canopy / non-canopy / near-threshold) | 83 | ±10.7 pp |
| 4 strata (+ refs-disagree) | 62 | ±12.3 pp |
| 6 strata (3 model × 2 CHM band) | 42 | ±15.1 pp |
| 8 strata (4 CHM band × 2 agreement) | 31 | ±17.6 pp |

The band we care about — 5–15 m, currently .36–.57 — cannot be pinned tighter than
roughly ±12 pp at this budget, and the design that would separate the U3 confound
(CHM band × agreement) is the weakest of all at ±17.6 pp.

### 3.3 What it *can* do

Confirm the height effect exists. The effect is large (.36 at 5–10 m vs .83 at 20–25 m),
and a two-band comparison is significant with as few as 20 points per band. But **we
already know this, replicated, from the raster comparison.** Spending the human budget
to re-confirm the one thing that is not in doubt is the failure mode to avoid.

### 3.4 Correcting an earlier claim of mine

In the previous turn I summarised Foody 2010 as "your recall is probably optimistic."
With STATE in view that is wrong as a blanket statement. The direction is **per reference**:

- **vs C-CAP** — C-CAP over-counts leafy suburbs as forest, inflating the recall
  denominator, so measured recall against C-CAP is likely **pessimistic**.
- **vs the NDVI+CHM reference** — that reference shares the model's lineage (same imagery,
  same NDVI logic, and after the overlay it also supplied training labels), so errors are
  correlated and numbers scored against it are likely **optimistic**.

This is the quantitative form of what STATE already says: the two references bracket truth.

---

## 4. Proposed amendments to the active plan

For Kam's sign-off. None of these are applied.

1. **Write the canopy definition first** (U1). One page, in the repo, before any point is
   interpreted. Nothing downstream is interpretable without it.
2. **Run the free instruments before spending human hours.** In order: recall-by-band
   within P2 partitions (U3), miss-depth per year on one recipe (U4), latent-class on the
   three sources (U2), stratified patch re-sampling (U5). All local except U5. Any of them
   may change what the human sample needs to be.
3. **Re-derive the sample size from the question.** If arbitrating the references is the
   goal, ~500+ points in one well-instrumented year (2016) beats 250 × 3 spread thin.
   Consider: 2016 deep (arbitration + C-CAP error rate), then 2000 and 2022 shallow as a
   trend check with openly wide CIs. Use Wagner & Stehman 2015 (ID 73) and Stehman &
   Wagner 2024 (ID 74) for allocation — the strata we care about are rare, so proportional
   allocation would starve them.
4. **Change the response design.** The plan currently excludes "Unsure" from estimation.
   Wickham 2023 (ID 78) and McCombs 2016 (ID 77) both record a **primary + alternate/fuzzy**
   label and report accuracy both ways; Radoux 2020 (ID 75) spends interpretation effort
   adaptively on ambiguous points. Excluding unsure discards exactly the pixels the
   references disagree about. Recommend: primary label + optional alternate + an explicit
   **short-tree vs shrub** call (Guo 2023, ID 88 — without it the sample cannot adjudicate
   finding 5), reporting accuracy under both scoring conventions.
5. **Design interpreter variance in from the start.** A duplicate-interpreted subset is
   required to fold interpreter error into the CI (Stehman 2022, ID 100; Xing & Stehman
   2024, ID 101 for the cheaper interpenetrating design). It cannot be added afterwards.
6. **Add the 2000 feasibility block** (U7) — 20–30 points, interpreted twice, before the
   production run.
7. **Keep the strata decision explicit and ahead of `--step design`.** Model-output strata
   answer "is the model right"; agreement strata answer "which reference is right"; CHM
   strata answer "is it height". These are three different studies. Stehman 2014 (ID 72)
   permits any of them — but not all three at once on this budget.

---

## 5. Honest statement of this document's own limits

- The power table uses simple-random-sampling variance. A well-designed stratified sample
  does better; the figures are conservative planning numbers, not exact design outputs.
  Recomputing them with the Olofsson/Wagner–Stehman stratified variance once stratum
  weights are known is a small local job and should be done before committing.
- `p = 0.5` is the worst case. Where true recall is far from .5 the intervals narrow.
- The 29.5% / 37.7% canopy fractions are the 2016 figures from STATE; the arbitration
  arithmetic assumes those are the two hypotheses under test.
- I have not re-verified the underlying raster computations — this assessment takes STATE's
  numbers as given and reasons about what they can and cannot support.

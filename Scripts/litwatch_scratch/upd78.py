import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE MAP-COUNT AREA IS BIASED BY -5.7 pp AT THE DEPLOYED THRESHOLD (Q136) *** - 2026-08-19
**Measurement only. Nothing in the pipeline was changed.** 162,786 usable sample points, 2013,
`_citywide_rgb`. Reference (C-CAP) canopy prevalence 35.97%.

| threshold | MAP-COUNT % | map bias | STRATIFIED % | strat bias | n=250 mean | n=250 SD | 95% halfwidth |
|---|---|---|---|---|---|---|---|
| 0.30 | 33.56 | -2.40 | 35.97 | +0.00 | 35.98 | 2.25 | **4.42** |
| **0.50** | **30.25** | **-5.71** | 35.97 | +0.00 | 35.96 | 2.27 | 4.46 |
| 0.60 | 23.72 | -12.25 | 35.97 | +0.00 | 35.95 | 2.37 | 4.64 |
| 0.70 | 16.24 | **-19.72** | 35.97 | +0.00 | 35.87 | 2.60 | 5.09 |

**THE MAP-COUNT AREA SWINGS 17.3 PERCENTAGE POINTS - 33.56% down to 16.24% - PURELY FROM WHERE THE
THRESHOLD IS PUT.** At the deployed ~0.5 it under-reports canopy by **5.71 pp** against the
reference. That is not a rounding concern for a deliverable whose entire purpose is a canopy
percentage.

**FOR SCALE, AGAINST THE POLICY NUMBERS THIS FEEDS.** The Edmonds tree-code debate turns on a
**32.4% baseline and a 35% goal - a 2.6 pp difference.** A threshold-induced bias of 5.71 pp is
**more than twice the entire policy-relevant gap**, and it moves with a parameter that is calibrated
separately per year.

**THE STRATIFIED ESTIMATOR REMOVES IT, AND WORKS AT P3's BUDGET.** Estimating from a reference
sample stratified BY THE MAP - the Olofsson/CEOS estimator already in this tracker - returns 35.97%
at **every** threshold. Simulating P3's planned **n=250/yr, 4,000 draws**, it is **unbiased**
(35.87-36.01) with a 95% half-width of **4.42-5.09 pp**.

**HONEST QUALIFICATION, BECAUSE HALF THAT TABLE IS NEARLY TAUTOLOGICAL.** With a full census the
stratified estimate *is* the reference prevalence by construction, so "strat bias +0.00" is
arithmetic, not evidence. **The two columns carrying real information are the map-count sensitivity
and the n=250 simulation** - the first shows the size of the problem, the second shows the remedy
survives a realistic sample. And C-CAP stands in for truth throughout: this establishes that the
estimator removes THRESHOLD sensitivity, not that C-CAP is correct.

**BUT n=250 CANNOT ANSWER THE QUESTION THE PROJECT EXISTS TO ANSWER.** A half-width of 4.42 pp
against a 2.6 pp policy gap means a single year's estimate **cannot distinguish 32.4% from 35%**.
Sample size needed for a given single-year precision, scaling the simulated SD:

| target 95% half-width | points per year |
|---|---|
| 3.0 pp | 543 |
| 2.5 pp | 781 |
| **2.0 pp** | **1,221** |
| 1.5 pp | 2,171 |

**And a year-to-year CHANGE needs more than a single-year level**, so these are floors, not targets.
This is the same conclusion an earlier assessment reached for a different quantity - the sample
budget answers the question not in doubt - but it now applies to **the headline area number itself**,
and with the design correction (stratified, not simple random) already folded in.

**WHAT I AM NOT CLAIMING.** That the pipeline's published canopy percentages are wrong by 5.71 pp -
they are computed at per-year thresholds against different footprints, and C-CAP is not truth.
**What is established is that the estimator in use is threshold-sensitive by up to 17 pp, that a
threshold-free alternative exists, is already documented in this tracker, and works at a realistic
sample size.** Whether to adopt it is Kam's call; the measurement is now on the table.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)
s = s.replace("""1. **Replace map-count area with reference-sample estimation (Q136)**""",
"""1. **Q136 MEASURED: map-count is threshold-sensitive by up to 17.3 pp (-5.71 pp at the deployed
   0.5); the stratified estimator is unbiased and works at n=250 (+/-4.42 pp). But n=250 CANNOT
   resolve the 2.6 pp policy gap - that needs ~1,221 points/yr for +/-2.0 pp.** Adoption is Kam's
   call. Original item below.
   **Replace map-count area with reference-sample estimation (Q136)**""")
io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 78 | 2026-08-19 | *** EMPIRICAL - the MAP-COUNT area is biased -5.71 pp at the deployed "
       "threshold (Q136) *** | - | 162,786 pts, 2013, C-CAP prevalence 35.97%. MAP-COUNT area swings "
       "33.56% -> 16.24% as thr goes .30 -> .70 = A 17.3 pp SWING FROM THE THRESHOLD ALONE; at the "
       "deployed ~.5 it under-reports by 5.71 pp. FOR SCALE: the Edmonds tree-code debate turns on a "
       "32.4% baseline vs a 35% goal = 2.6 pp, so the threshold artefact is MORE THAN TWICE THE "
       "ENTIRE POLICY GAP. Olofsson stratified-by-map estimator returns 35.97% at EVERY threshold "
       "and, simulated at P3's n=250 with 4000 draws, is UNBIASED (35.87-36.01) with 95% halfwidth "
       "4.42-5.09 pp. HONEST QUALIFICATION: 'strat bias +0.00' at full census is ARITHMETIC not "
       "evidence - the informative columns are map sensitivity and the n=250 sim; C-CAP stands in "
       "for truth. BUT n=250 CANNOT DISTINGUISH 32.4% FROM 35%. Needed: 543 pts for +/-3.0 pp, 781 "
       "for +/-2.5, 1221 for +/-2.0, 2171 for +/-1.5 - and a year-to-year CHANGE needs more, so "
       "these are FLOORS. NOT claiming published percentages are wrong by 5.71 pp; claiming the "
       "estimator in use is threshold-sensitive by up to 17 pp and a documented alternative works |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")

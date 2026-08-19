# Edmonds Canopy Pipeline — Verified Results Report

**Date:** 2026-08-19 · **Scope:** 2000–2024 imagery, Phase 4 semantic canopy
**Companion documents:** `Scripts/WORKPLAN_2026-08-19.md` (what to do next) ·
`Scripts/IMAGERY_FACTS.md` (imagery characterisation) · `Scripts/IMAGERY_PLAN.md` (imagery
work plan) · `Scripts/canopy_definition_PROPOSAL.md` (the blocking decision)

---

## 0. How to read this report — the trust tiers

Every table carries a tier. Nothing here is quoted from memory; each table names the file it
was read from, and those files are in git.

| tier | meaning |
|---|---|
| **T1 — replicated** | measured by this project's own tools AND confirmed by an independent instrument, a second year, or an exact re-run of recovered code |
| **T2 — measured once** | computed directly from the rasters by a tracked script; not yet independently replicated |
| **T3 — indicative** | measured, but carrying a known confound or proxy limitation stated in place |
| **withdrawn** | previously claimed, now known wrong — listed in §9 so it cannot be re-quoted |

Standing caveat that rides with **every** accuracy number in this report: both references
(C-CAP and the NDVI+CHM product) are **proxies**, not ground truth. The CHM is ~2016 vintage.
C-CAP 2016 is applied to 2000–2017 and C-CAP 2021 to 2019–2023, so real canopy change between
those dates counts against the model. Human photo-interpretation (Phase 3) against a written
canopy definition is what converts these numbers into defensible ones — and the definition
does not exist yet (§8).

---

## 1. The honest baseline — every scored year *(T2, reference-controlled)*

**Source:** `phase4/qc/qc_indep_report.csv` (quote `live=1`/latest rows only) ·
**Reference:** full-coverage C-CAP (`ccap_2016_hires_lc_snohfull.tif`, 91.0% of study area)
for the 2016-epoch; `forest_wetland` canopy definition; each year at its deployed threshold.

### 1.1 Deployed-model scores (mixed recipes — the operational numbers)

| year | prob raster (recipe) | thresh | recall | precision |
|---|---|---|---|---|
| 2000 | xsensor_rgb | .5133 | .6749 | .7975 |
| 2002 | xsensor_rgb | .5700 | .5580 | .8563 |
| 2013 | xsensor_rgb | .5209 | .7395 | .8666 |
| 2015 | xsensor_rgb | .5760 | .6629 | .8989 |
| 2016 | native (coarse) | .5090 | **.6636** | .8736 |
| 2017 | xsensor_train | .4759 | **.7986** | .8274 |

2017 is the series recall high. 2016 — the most-quoted year — is **.6636, not the .6844 in
older notes** (the old figure used the clipped reference; see §9).

### 1.2 Recipe-matched series (one recipe, one reference — the comparable numbers)

All `_citywide_rgb`, all vs the full-coverage reference. **Only rows in this table may be
compared with each other.** Recipe effects are 5.6–12.7 pp with sign varying by year (§4.3),
so mixing recipes voids any comparison.

| year | true GSD | effective res. | thresh | recall | precision |
|---|---|---|---|---|---|
| 2000 | 40.1 cm | 110.8 cm | .5133 | .5480 | .8534 |
| 2002 | 40.1 cm | 57.1 cm | .4988 | .6136 | .8372 |
| 2005 | 20.1 cm | 80.7 cm | .4659 | .6346 | **.9166** |
| 2007 | 20.1 cm | 25.5 cm | .5026 | .6605 | .8813 |
| 2009 | 20.1 cm | 26.1 cm | .5110 | .6048 | **.9177** |
| 2013 | 10.0 cm | 13.7 cm | .5000 | **.7422** | .8672 |
| 2015 | 10.0 cm | 12.9 cm | .5011 | **.7401** | .8823 |

The 10 cm pair agrees to **0.2 pp across two different years** — the tightest within-tier
replication in the project *(T1)*. By nominal tier: 40 cm ≈ .58 · 20 cm ≈ .63 · 10 cm ≈ .74.
The **extremes** of resolution separate (~19 pp); the **middle does not order** — 2005 at
80.7 cm effective beats 2009 at 26.1 cm. Resolution is real at the extremes; the middle is
unexplained (three candidate explanations have failed: nominal GSD, spectral sharpness,
effective resolution).

### 1.3 2021-epoch years *(T3 — clipped reference, not comparable to the tables above)*

Scored against `ccap_2021_hires_lc.tif`, which is still a **clipped 53.1% copy** (no
full-coverage hi-res 2021 land cover exists; NOAA's 2021 land cover is 30 m). The clip was
measured to cost 2–5 pp of recall on the 2016-epoch years, so these are probably understated.

| year | recipe | thresh | recall | precision |
|---|---|---|---|---|
| 2019n | p2nir | .4950 | .6499 | .8540 |
| 2021s | p2nir | .4990 | .6851 | .8547 |
| 2021k | citywide_rgb | .4013 | .6059 | .8778 |
| 2022n | native | .4040 | .6564 | .8630 |
| 2023 | citywide_rgb | .5103 | .6510 | .8506 |

**Do not read 2023's .6510 against 2013's .7422 as 10 cm variability** — most of that gap is
which reference was used.

### 1.4 The reference-coverage effect *(T1 — single-variable controlled, 6 years)*

Same prob raster, same deployed threshold, **only the reference swapped** (clipped 51.9% →
full 91.0%):

| year | imagery coverage | clipped → full recall | Δ |
|---|---|---|---|
| 2000 | 100% | .6303 → .6749 | **+4.5 pp** |
| 2002 | 100% | .5069 → .5580 | **+5.1** |
| 2013 | 100% | .7094 → .7395 | **+3.0** |
| 2015 | 100% | .6222 → .6629 | **+4.1** |
| 2017 | 100% | .7784 → .7986 | **+2.0** |
| 2016 | **41.9%** | .6844 → .6636 | **−2.1** |

Five-for-five: every full-coverage year improved; the one partial-coverage year got worse.
**Coverage predicts the sign; year and sensor do not.** The clipped reference was flattering
2016 specifically and penalising everything else.

---

## 2. Where the misses are — three measured levers

### 2.1 Recall is a function of canopy height *(T1 — survives three confound tests)*

**Source:** `phase4/qc/height_by_agreement_2016_baseline.csv` — 2016, computed **inside the
both-references-agree partition** (n = 5.5 M cells), so reference disagreement cannot
manufacture it:

| CHM band | 2–5 m | 5–10 | 10–15 | 15–20 | 20–25 | 25–30 | 30+ |
|---|---|---|---|---|---|---|---|
| recall | .2010 | .4181 | .6220 | .7668 | .8535 | .8971 | .9404 |

Headline contrast: 5–15 m recall **.5172** vs 20 m+ **.9049** (spread +.3877). The 5–15 m
band holds ~53% of all misses. The 0–2 m band must never be quoted (the NDVI reference
requires ≥2 m by construction).

Confound tests it survived:
- **Reference disagreement:** staircase intact inside both-agree (the table above).
- **Crown geometry:** intact inside crown *interiors* — spread +.3115 vs edge +.3105
  (`edge_vs_interior_2016_baseline.csv`); robust at 2× erosion (+.2528).
- **CHM measurement error** (`chm_noise_2016_baseline.csv`): a null test (outcome shuffled
  independent of height) collapses the spread to **+0.0001**, so binning cannot invent the
  curve; adding the literature's ~3 m error costs only 5% of the spread (1.00 → .95×), and
  error in a stratification variable can only *flatten* a real curve. The observed spread is
  therefore an attenuated floor; the truth is plausibly ~.41. Individual 5 m band edges *are*
  smeared — never quote one band as if its boundary were sharp.

### 2.2 Crown perimeter *(T1 — replicated across 2016 and 2021s)*

**Source:** `phase4/qc/edge_vs_interior_{2016_baseline,2021s}.csv`. Edge = outer 2 m of
agreed canopy by 8-connected erosion on a 2 m lattice.

| | 2016 | 2021s |
|---|---|---|
| edge share of canopy **area** | 16.3% | 16.1% |
| edge share of **all misses** | **41.8%** | **42.8%** |
| interior recall | .8191 | .8191 |
| edge recall | .3306 | .2946 |
| edge misses with CHM ≥3 m | 95.4% | 92.8% |
| edge misses deep (prob <.06) | 32.9% | **63.3%** |

The perimeter loss is a stable property of the model (size and reality replicate across
year, sensor and C-CAP epoch). **How recoverable it is is year-specific** — do not quote a
single "x% is threshold-recoverable" figure. The edge misses are real canopy (93–95% carry
canopy-height lidar returns), not reference bleed. The identical .8191 interior recall in
both years is coincidence in one aggregate; the per-band tables differ.

### 2.3 Miss depth — calibration vs labels *(T1 — one recipe, extent-matched confirmed)*

**Source:** `phase4/qc/forest_miss_*.txt` (one recipe `_citywide_rgb`, fixed thresh 0.5) and
`phase4/qc/extent_matched.csv` (same, inside the 2016 footprint on one grid):

| year | deep misses (prob <.12) | near-threshold | extent-matched deep |
|---|---|---|---|
| 2000 | 27.7% | 72.3% | 27.4% |
| 2013 | 30.8% | 69.2% | 30.8% |
| 2002 | 31.8% | 68.2% | 31.7% |
| 2015 | 48.2% | 51.8% | 48.1% |
| 2016 | **66.2%** | 33.7% | **66.1%** |

- **2016 genuinely is the outlier** — the gap over the next year is +17.9 pp extent-matched
  vs +18.0 unmatched, so geography contributes ~0.1 pp. Conclusions drawn on 2016 (the
  default test year) systematically **understate** how much the operating point can help
  elsewhere.
- "Labels or calibration" has **no single answer**: 2016 says labels (66% deep); 2000/2002/
  2013 say calibration is a real lever (~70% near threshold).
- Earlier per-year figures (24.1/19.4/9.3%) were **recipe artefacts** — a recipe change moved
  2013 by 22 pp. Only same-recipe columns may be compared.
- The 2015 anomaly (48.2% deep; its misses are *darker* and relatively *bluer*, where every
  other year's are brighter and less green) is measured **within-year** and stands *(T2)*.
  Its leaf-off *attribution* is withdrawn (§9). The cross-year invariant that survives:
  missed forest loses **colour saturation** in all years measured *(T2)*.

### 2.4 Where the errors sit spatially *(T2)*

**Source:** `phase4/qc/sentinel_overlays_2016.csv` — recall on agreed ground only, per fixed
sentinel window: forest_6 .955 · forest_1 .826 · forest_4 .825 · marsh .786 · forest_3 .750 ·
**residential_mixed .575**. Precision .92–.998 everywhere. The conifer→suburban gradient is
visible, and in residential windows the misses form **rings around detected cores** — the
observation that led to §2.2.

---

## 3. The reference dispute — what the canopy number depends on

### 3.1 Latent-class analysis *(T1 — replicated across 4 years; estimator validated on synthetic truth)*

**Source:** `phase4/qc/latent_class_*.csv`. C-CAP, the NDVI+CHM reference and the model
treated as three imperfect tests of one latent canopy variable; fitted within CHM height
bands; spatial block bootstrap.

| year | latent prevalence π |
|---|---|
| 2016 | .2912 [.284–.297] |
| 2021s | .2820 |
| 2019n | .2931 |
| 2022n | .2863 |

Against: C-CAP's total ~.295 and the NDVI reference's **.377**. Global 2016 fit:

| source | sensitivity | specificity |
|---|---|---|
| C-CAP | .8935 | .9506 |
| NDVI+CHM ref | .9872 | .8729 |
| model | .7500 | **.9917** |

The model is the strictest of the three — an independent reproduction of "high-precision
under-predictor." Known limits *(stated, not hidden)*: LCA assumes conditionally independent
errors and ours are correlated; feeding the NDVI-descended corrected model moves π by 5.8 pp,
so **LCA is inadmissible for the 2016c deploy decision in either direction**. An adversarial
simulation (NDVI ref true, model+C-CAP colluding) could not reproduce the observed fits at
any dependence strength while matching the call rates *(T1)*.

### 3.2 What the NDVI reference over-calls *(T1 — vintage-matched, so change is excluded)*

**Source:** `phase4/qc/ndvi_vs_tree_2021s.csv` — `ndvi_ref_2021s` crossed with NOAA's
purpose-built 2021 tree/shrub canopy product on one grid:

| | share |
|---|---|
| NDVI-ref canopy that NOAA calls **tree** | 63.84% (CHM p50 20.6 m) |
| … that NOAA calls **shrub** | **2.87%** |
| … that NOAA calls **neither** | **33.28%** (CHM p50 **6.0 m**; 88.7% ≥3 m; 61.1% ≥5 m) |

Totals: NDVI ref 38.61% · NOAA tree 26.20% · tree+shrub 27.75%. The 12.4 pp gap ≈ the
12.85 pp disputed zone: **the entire .29-vs-.38 disagreement is one population** — mid-height
woody vegetation (young/ornamental crowns, hedgerows, understory), **not shrubs**, and **no
height cut separates it** (≥3 m keeps 89% of it). Which side is *right* remains a human call:
NOAA's product is a model too.

### 3.3 The NOAA canopy product's own classes *(T2 — classes identified empirically via CHM)*

**Source:** `phase4_qc_canopy_classes.py` output. Class 1 = **tree** (24.79% of study grid,
median CHM 21.6 m, 97.6% ≥3 m); class 2 = **shrub** (1.25%, median 4.0 m, 65.6% ≥3 m).
A ≥3 m cut keeps 97.6% of tree **and** 65.6% of shrub → **height is a poor proxy for the
tree/shrub distinction** in general.

### 3.4 The definition sweep *(T2 — scoped to the 2016 imagery band, 41.9% of the city)*

**Source:** `phase4/qc/ndvi_ref_2016.txt`. Canopy as % of imaged 2016 pixels:

| | h ≥1 m | h ≥2 m | h ≥3 m | h ≥5 m |
|---|---|---|---|---|
| NDVI ≥0.10 | 45.08 | 43.26 | 40.97 | 35.06 |
| NDVI ≥0.20 | 39.00 | **37.74** | 36.07 | 31.59 |
| NDVI ≥0.30 | 34.15 | 33.22 | **31.97** | 28.50 |

- The **greenness cut moves the number as much as height** (10.0 pp across NDVI .10→.30 at
  fixed height, vs 7.4 pp across h 1→5 m at fixed NDVI). The definition is two thresholds.
- The 2→3 m step costs only 1.7 pp — the IGNORE band is cheap.
- **No cell reproduces ~.29** except the strictest corner: C-CAP's total is partly a
  *unit-of-analysis* difference (stand-based, drops isolated crowns by kind), not reachable
  by thresholds.
- **These are not citywide figures** — the 2016 ortho covers 41.9% of the study area.
- CHM-coverage worry closed *(T1)*: the no-lidar zone is 99.8%-negative-NDVI **water**;
  counting every green no-CHM pixel as canopy adds +0.02 pp (`chm_gap_2016.txt`).

---

## 4. The imagery itself *(details: `Scripts/IMAGERY_FACTS.md`)*

### 4.1 Geometry *(T1 — measured from files; units bug fixed in config)*

| source | years | true GSD | footprint |
|---|---|---|---|
| King County | 2000–2023 (11 files) | 40.1 / 20.1 / 10.0 cm | 100% |
| City of Edmonds | 2017, 2020, 2022, 2024 | 5.0 cm | 100% |
| Snohomish | 2016, 2021s | **15.4 cm** (config said 50 — EPSG:2285 is US survey feet) | **41.9%** |
| NAIP | 2019n, 2022n | 60.7 cm | 69.2% |

### 4.2 Effective resolution *(T1 — exact re-run of recovered code, 12 fixed sites)*

1998 244.7 cm (out of scope) · **2000 110.8 cm (2.8×)** · 2002 57.1 · **2005 80.7 (4.0×)** ·
2007 25.5 · 2009 26.1 · 2013–2023 King 12.6–13.7 cm. Unmeasured: Snohomish, NAIP, and **all
four CoE years including 2020, the labelled year**. Lead: the King files are all Web-Mercator
reprojections, which blur — the softness may be ours, and if so native sources recover detail
no retraining can.

### 4.3 Recipe effects *(T1 — three year-controlled measurements)*

Same year, same reference, only training recipe differing: 2000 xsensor better by **12.7 pp**;
2002 citywide better by 5.6; 2015 citywide better by 7.7. **Size and sign are year-specific**
→ no mixed-recipe table is interpretable. (A recipe change also moved 2013's miss-depth by
22 pp.)

### 4.4 Colour *(T1 — exact re-run; decisive same-year pair)*

Fraction of identical ground a naive greenness test calls vegetated: **2019 King .1146 vs
2019 NAIP .8919** — pure sensor/processing colour balance. King drifts .8027 (2000) → .1146
(2019) monotonically. **No cross-sensor or cross-year greenness comparison is valid**;
within-year contrasts are unaffected (global cast cancels).

### 4.5 The area estimator *(T1 — exact re-run, 162,786 points)*

Map-count area (counting thresholded pixels — the pipeline's current method,
`phase3_semantic_dev.py:1722`) vs the Olofsson stratified estimator, 2013 vs C-CAP (35.97%):

| threshold | map-count | map bias | stratified | n=250 95% half-width |
|---|---|---|---|---|
| 0.30 | 33.56% | −2.40 pp | 35.97% | ±4.42 pp |
| **0.50** | **30.25%** | **−5.71 pp** | 35.97% | ±4.46 |
| 0.60 | 23.72% | −12.25 | 35.97% | ±4.64 |
| 0.70 | 16.24% | −19.72 | 35.97% | ±5.09 |

The map-count swings **17.3 pp on the threshold alone** and sits −5.71 pp at deployment. The
Edmonds policy debate turns on **2.6 pp** (32.4% baseline vs 35% goal) — the estimator's bias
is more than twice the policy-relevant gap. The stratified estimator is threshold-free and
unbiased in simulation. *(Established: the estimator is threshold-sensitive. Not established:
that published percentages are off by exactly 5.71 — C-CAP is not truth.)*

---

## 5. Model strength does not move the honest number *(T2)*

Nine years span IoU .49–.76 and AUROC .938–.954 on their own validation, while honest recall
stays .55–.80 with **no correlation**. Better models do not close the gap; the gap is in the
labels, the boundaries and the operating point (§2), not model capacity.

---

## 6. The two sample budgets *(T1 — both simulated with the real designs)*

| question | gap | verdict at n=250 | needed |
|---|---|---|---|
| which reference **definition** is right | 8.24 pp | **suffices** — power ~1.0 at ≤5% interpreter error; degrades to .44 at 10% error | duplicate-interpreted subset is load-bearing |
| the **policy number** (32.4 vs 35%) | 2.6 pp | **fails** — ±4.4 pp | ~**1,221 pts/yr** for ±2.0 pp; change needs more |

Sources: `phase4/qc/design_power_2016.csv` (the 0%-interpreter-error row is rigged by
construction — quote the 5%/10% rows) and the verified `q136.py` simulation. **Never quote
one budget as though it settled the other.** Also year choice: 2016's reference separation is
8.24 pp vs 2022n's 4.65 — go deep on 2016, not 250×3.

---

## 7. Instruments built and validated this cycle

All in `Scripts/`, all committed, all with outputs in `phase4/qc/`:

`phase4_ref_agreement` (P2 partition) · `phase4_qc_height_by_agreement` (U3) ·
`phase4_qc_latent_class` + synthetic-recovery + adversarial tests (U2) ·
`phase4_qc_design_power` (sample budgets) · `phase4_qc_edge_vs_interior` (perimeter) ·
`phase4_qc_chm_noise` (U6) · `phase4_qc_chm_gap` (coverage) · `phase4_qc_extent_matched`
(footprint control) · `phase4_qc_ndvi_vs_tree` (reference dispute) ·
`phase4_sentinel_qc_overlay` (error maps) · `phase4_data_inventory` (metadata) ·
recovered & re-verified: `litwatch_scratch/{cast2,q138b,overhang,q136,sampler}.py`.

Four recovered-scratchpad claims were re-run and **reproduced exactly** (colour cast,
effective resolution, on-building split, area estimator). Remaining scratchpad figures are
*un-re-run*, not unreproducible. The 88–93% "real miss" chain is the highest-value unverified
claim — `overhang.py` reproduces an input to it (68.4% of on-building tall pixels sit above
the roof), not the whole chain.

---

## 8. What blocks the next step

**U1 — the written canopy definition.** Both work threads independently ended here. It is a
judgment call worth ~6 pp of city canopy — more than twice the policy gap. The evidence is
assembled in `Scripts/canopy_definition_PROPOSAL.md`; **its D1 (minimum height) is mis-posed**
— the disputed population is 88.7% above 3 m, so no height cut decides it. **Decide D2 (crown
form / minimum crown size) first.** Until it exists, the 250-point human sample produces a
third opinion, not an arbitration.

---

## 9. Withdrawn — do not re-quote

| claim | status |
|---|---|
| "2016 honest recall .6844" | **superseded** — .6636 (clipped reference) |
| "2015 is the most leaf-off year" | **withdrawn** — rests on cross-year GRVI (§4.4); the within-year 2015 anomaly stands |
| "misses are confident/structural → labels beat compute" | 2016-only; other years are 52–72% near-threshold |
| "brightness gap scales with sensor era" | 2015 breaks it; the invariant is saturation loss |
| per-year miss-depth 24.1/19.4/9.3% | recipe artefacts; use §2.3 |
| "2016 not recipe-comparable" | wrong premise — coarse tier already used the citywide recipe |
| "the 2021 same-year pair isolates the sensor" | tiling regime is entangled with resolution by design |
| "+3.3 pp from the fuller reference" | three variables changed at once; controlled figure +3.0 (§1.4) |
| lit-watch headline figures (61% operating-point reduction, AUC table) | code recovered; **un-re-run** — usable as leads, not results |
| "C-CAP covers only ~53% of the city" | artefact of our own clip; the source covers 91% |

---

## 10. One-paragraph summary

The model is a high-precision under-predictor whose honest recall runs .55–.80 depending on
year, and whose misses are structured, not random: short canopy (5–15 m), crown perimeters
(~42% of misses in ~16% of area), and — in exactly one measured year, 2016 — deep,
confidently-wrong misses that no threshold recovers. The two reference products disagree
about one specific population (mid-height woody vegetation, ~12 pp of the city), which makes
the citywide canopy number a definitional choice between ~.29 and ~.38 before it is a
measurement. The imagery series itself was quietly inconsistent — resolutions misstated by up
to 6×, colour balance drifting monotonically, footprints differing 2×, and an area estimator
sensitive to 17 pp on a threshold — and most of those are now fixed or fenced. What stands
between the current state and defensible numbers is one human decision (what counts as a
tree) and one sampling campaign sized to the question actually being asked.

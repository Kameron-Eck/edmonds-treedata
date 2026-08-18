# Literature Review — Phase 4: Measurement Validity
## Edmonds Temporal Canopy Pipeline · Searches 9–14

> Written 2026-08-18, after the honest-measurement-overhaul work. The five
> findings below are what make these searches worth running; each is recorded in
> `CHATLOG.md` and reproducible from the scripts in this folder.
> **Paste this whole file as the prompt.**

---

You are extending an existing literature review for a geospatial deep-learning
project. 68 papers are already tracked across 8 completed searches (Phases 1–3):
instance-segmentation architectures, resolution sensitivity, multi-temporal urban
canopy monitoring, active/semi-supervised learning, radiometric normalization,
RGB-only vegetation indices, temporal anchor-and-project tracking, and long-term
urban forest studies. DO NOT re-cover those. This phase targets a gap those
searches left: **whether our measurements mean what we think they mean.**

## Project context

Per-crown temporal canopy validity intervals for ~222,000 tree crowns across
Edmonds, WA. 18 aerial acquisitions, 2000–2024, spanning 7.5–60 cm GSD across
three sensors (King County, Snohomish County, NAIP). A U-Net is trained on the one
year with hand labels (2020) and fine-tuned per year. Evaluation uses two
independent proxies: NOAA C-CAP 1 m land cover (2016 and 2021 vintages) and an
NDVI+CHM reference derived from our own NIR imagery plus a single ~2016 lidar
canopy-height model at ~60% city coverage.

## What we established empirically (this drives the searches)

1. **Detection is a monotonic function of canopy height.** Recall by CHM band:
   0.15 (<5 m), 0.36 (5–10 m), 0.57 (10–15 m), 0.74 (15–20 m), 0.83–0.88
   (20–30 m), 0.93 (30+ m). The 5–15 m band holds 53% of all missed pixels.
2. **Model strength does not move the number.** Nine years span IoU 0.49–0.76 and
   AUROC 0.938–0.954, yet honest recall stays pinned at 0.51–0.78 with no
   correlation to model quality. Architecture appears not to be the constraint.
3. **The two references disagree on 15–17% of pixels**, replicated across four
   years and three sensors. On one year they differ by 12 percentage points on the
   same ground with no temporal offset. The NDVI-derived reference is
   systematically more liberal than C-CAP.
4. **The label source carries the same bias, worse.** The 2020 mask that supplies
   training labels to all coarse years is itself a model prediction; its
   recall-by-height curve has the same shape and sits below its own students at
   every band (0.55 vs 0.68 overall).
5. **Correcting labels moved the model toward one reference, not toward truth.**
   Retraining with an NIR+CHM-derived label overlay lifted recall 0.68 → 0.87 with
   the gain concentrated at low heights (+0.34 at 2–5 m vs +0.06 at 30+ m), but the
   model's canopy fraction landed beside the NDVI reference's (35% vs 38%) rather
   than C-CAP's (30%). We cannot tell whether it became more correct.

## Searches

### Search 9 — Accuracy assessment & area estimation protocol (HIGHEST PRIORITY)
Good-practice sampling and estimation for land-cover accuracy and area, with
confidence intervals. Olofsson, Stehman, Foody and successors. Specifically:
- Stratified estimators for accuracy and area; variance estimation; sample size.
- Is it legitimate to define strata using the **reference** data (e.g. by agreement
  between two reference products) rather than by the map? What does that do to
  bias and variance?
- How should "unsure"/indeterminate interpreter responses be handled — excluded,
  modeled, or treated as a class?

### Search 10 — Reference data quality and inter-product disagreement
Studies quantifying disagreement between land-cover products, and what analysts
should do when two references conflict. Look for: reported disagreement rates for
comparable products; whether disagreement is treated as reference error, map
error, or unmeasurable; validation of C-CAP or NLCD against independent
interpretation; error budgets that separate reference uncertainty from model error.

### Search 11 — Height-stratified detection bias in canopy mapping
Omission of short, sub-canopy, understory, juvenile or suppressed trees in
remote-sensing canopy products. Does anyone report accuracy stratified by canopy
height, and is that standard practice? What drives the bias — spectral mixing,
GSD, shadow, training-data composition? What interventions have been shown to
reduce it?

### Search 12 — Label noise and error propagation in model-derived labels
Our labels for most years are a model prediction, so the model's blind spot is
re-taught. Look for: pseudo-labeling and self-training error accumulation;
confirmation bias in iterative labeling; quantified propagation of label noise
into downstream accuracy; correction strategies that do not require full
re-annotation. Distinguish this from the active-learning literature already
covered in Search 4 — we want the **error-propagation** framing.

### Search 13 — Lidar/CHM fusion for canopy segmentation
Height as an input channel vs an auxiliary prediction target. Also critical for us:
using a **temporally mismatched** CHM (a single ~2016 snapshot applied to
2000–2024) — how do others handle vintage mismatch, and what error does it
introduce? Partial spatial coverage (~60%) is also relevant.

### Search 14 — Photo-interpretation protocols and interpreter agreement
We are about to run a ~250-point human interpretation. Look for: protocols for
interpreting canopy presence at a point; chip size and zoom conventions; single vs
multiple interpreters; inter-interpreter agreement rates for canopy; how
interpreter uncertainty is recorded and reported.

## Output format

Append to `Literature_Tracker.xlsx` (sheet **Literature Tracker**), continuing IDs
from 69. Columns: `ID | Author(s) | Year | Title | Journal/Source | Relevance (max
3 sentences) | Search Phase | DOI/URL | Status`.

Use `Phase 4: Search N` in the Search Phase column, and add the six new rows to
the **Search Phase Reference** sheet.

## What counts as relevant

Include a paper only if it would change a decision we face: how to sample, how to
report accuracy, how to interpret reference disagreement, or how to fix a
height-stratified deficit. Prefer peer-reviewed, 2015+, remote sensing or applied
statistics. Older work is welcome where it is canonical (e.g. foundational
accuracy-assessment methodology).

In the Relevance field, state plainly what the paper lets us **do** — not what it
is about. **If a paper contradicts one of the five findings above, say so
explicitly**; that is more valuable than confirmation.

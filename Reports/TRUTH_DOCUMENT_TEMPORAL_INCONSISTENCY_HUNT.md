# TRUTH DOCUMENT — the overnight literature hunt for our problem's twin (or its solution)

**Written 2026-09-06 for a dedicated read-only Claude session. This document is the
contract: the hunt continues, self-paced, until one of the SUFFICIENCY conditions
below is met or the TERMINAL condition is honestly reached. The hunting session must
re-read this document at every loop iteration and judge its own progress against it.**

---

## 1. THE PROBLEM, PRECISELY (all claims below are measured; sources cited by repo path)

A municipal tree-canopy **trend** must be reconstructed from a **heterogeneous
historical aerial-orthophoto archive**: 37 acquisitions over 20 calendar years,
5+ delivery programs (city, county, state consortium, NAIP, commercial), GSD 5 cm–1 m,
RGB mostly (some RGBI), **no radiometric calibration, no shared processing chain**,
flight seasons February–October. Lidar exists for exactly two epochs (2005, 2016).
One year (2020) has hand labels; all other supervision is projected.

Measured facts any candidate study/solution must survive
(files under `D:\edmonds-pipeline\treedata\`):

- **F1. Per-year uniform-recipe maps sawtooth ±3–6 pp** around a true ~2 pp/8 yr
  signal; map-differenced 2016→2024 came out **sign-opposite** the human-measured
  truth (−2.21 pp, CI ±1.10, five measured interpreter controls).
  `phase4/qc/trend8_harmonized_fractions.csv`, `phase4/qc/panel_a_estimate.txt`.
- **F2. Post-hoc grid harmonization moved NOTHING** (2 m majority resample changed
  fractions <0.1 pp) — the inconsistency is baked in at detection time.
- **F3. Operating point dominates**: three same-year deliveries (2017) spread
  10.1 pp at delivered per-arm thresholds and collapse to **1.07 pp** under
  reference-matched cuts; two of three probability rasters were miscalibrated
  (near-binary, mode at the cut; 1 uint8 DN ≈ 5–9 pp of city area). So a large
  share of "temporal inconsistency" in per-date classification is **threshold/
  calibration placement**, correctable — and any paper that ignores operating-point
  matching before claiming temporal inconsistency is suspect.
- **F4. What remains after matching is delivery-chain detection bias** (~1 pp same-year
  residual; per-pixel quality gaps AUROC 0.86–0.93 across deliveries) plus a measured
  **radiometric greenness gradient**: same sensor, same GSD, recall spans −.109 with
  the delivery's green–red separation (NOT phenology: the February leaf-off year is
  bimodal-GRVI and unharmed; the shifted years are whole-distribution radiometry).
  `Reports/GREENNESS_GRADIENT_CORRECTION_2026-09-03.md`.
- **F5. Flicker census**: across 8 uniform-recipe maps, **50.7% of ever-canopy pixels
  flicker** (≥2 transitions); 16.4% of the city shows impossible canopy→gone→canopy;
  crown-level FLICKERING:LOST = 12.4:1. `phase4/qc/trend8_transition_census.csv`.
- **F6. Change is edge-concentrated**: verified losses sit median 2.0 m from a crown
  edge (canopy baseline 2.8 m); loss is dispersed (largest persistent cluster 0.41 ha).
  The signal and the measurement noise share an address.
- **F7. Same-flight floor**: one flight delivered two ways differs by **1.3 pp of
  citywide canopy fraction** (IoU 0.738) under one frozen model — the processing-chain
  noise floor no algorithm downstream of delivery can remove.
- **F8. The trend authority is human paired-point interpretation** (1,250 points,
  three-epoch phenology verification, blur/drift/duplicate controls, capture audit) —
  the same method the national program (Nowak & Greenfield) and continental map
  factories (ALCC's own change validation) fall back to.

## 2. WHAT WE ALREADY KNOW FROM THE LITERATURE (do not re-find these)

Read and reasoned this week: MURTreeFormer (input-side modality mismatch — different
axis); Artikanur 2026 (irrational-transition masking — validated only on stable
points); Liu/GeoAI 2026 (label inheritance through 30 m stability — blind to our
signal by its own admission); ALCC/Li 2026 (ensemble CCDC+BFAST+Chow at 30 m —
requires calibrated reflectance; change UA ceiling 74.3%, change-year accuracy 63.4%).
Families known: temporal filtering/HMM, time-series-first algorithms (need calibrated
sensors), pixel/object trajectories, method-holding/harmonization, sample-based change
estimation (Olofsson; our Panel A). The four papers' common gap: **none validates
change against blind human truth with measured interpreter error.**

## 3. THE HUNT — what would SUFFICE

### Condition A — "the twin": a study materially like ours, fully read (not abstract-skimmed)
Scored against five criteria; **A is met by any single study scoring ≥4/5**:
1. Aerial (not satellite) sub-meter imagery, **multi-vendor/multi-program archive**
   without radiometric calibration.
2. **≥5 epochs** spanning ≥10 years.
3. Tree canopy (or urban forest) **segmentation/mapping**, not plot inventory.
4. **Temporal inconsistency quantified** (any flicker/spurious-change/consistency
   metric — not merely acknowledged).
5. A **change/trend estimate** actually produced, with a validation design that can
   see change (not stable-points-only).

If found: extract its full method, its numbers, and judge each of F1–F8 against it.

### Condition B — a novel, scalable solution we have not already considered
A method (single paper or a defensible synthesis across ≥8 FULLY-READ sources) that
could plausibly recover per-map comparability or trend from an archive like ours, AND
survives this adversarial checklist:
- Needs **no** radiometric cross-calibration of the archive (F4 says we can't have it).
- Needs **no** lidar beyond two epochs.
- Is not defeated by F3 (must address operating-point/calibration matching explicitly
  or be orthogonal to it).
- Is not naive temporal smoothing (F5's pilot: smoothing moved the estimate AWAY from
  truth) and not stability-inheritance (blind to dispersed loss, F6).
- Scales: ≤ a few GPU-days + ≤ a few human-days for a 25 km² city, no bespoke sensors.
- Has a statable kill criterion testable on our data.

If found/synthesized: write the design concretely enough to implement (inputs, steps,
what it outputs, expected failure modes), with every load-bearing claim traced to a
fully-read source (page numbers).

### Condition T — TERMINAL (honest exhaustion)
Permitted only when the hunt log shows: every angle in §4 searched with ≥3 query
formulations each; ≥25 candidate papers triaged; ≥10 read in full; the national/
consulting grey literature checked (§4.6–4.8); and neither A nor B met. The deliverable
is then the **defensible negative**: the documented search space + the closest misses
and why each fails — which upgrades our paper's gap claim from asserted to hunted.

## 4. SEARCH ANGLES (each gets multiple formulations; log every query)

1. "multi-temporal" + "aerial orthophoto"/"NAIP time series" + tree canopy/urban tree
   + consistency/spurious change/flicker.
2. Historical orthophoto archives for vegetation/land-cover change (photogrammetry
   venues: ISPRS J., PE&RS, Remote Sens. Environ., IJAEOG, Urban For. Urban Green.).
3. Domain adaptation / cross-sensor / cross-acquisition robustness for aerial
   segmentation (the harmonization-at-model-level literature).
4. Calibration/threshold transfer across classifiers and dates; probability
   calibration for land-cover time series; "operating point" + change detection.
5. The Orlando-style datasets: biennial sub-meter canopy series publications and
   how each handled inter-date inconsistency.
6. Grey literature: UVM Spatial Analysis Lab / PlanIT Geo / Davey / SavATree UTC
   *change* assessment methods documents; USFS UTC protocols; i-Tree Canopy change.
7. National programs: NLCD TCC change methodology; LCMAP; Chesapeake 1 m change
   product methods (how they validated change).
8. Adjacent fields with the same disease: glacier/coastline/building change from
   heterogeneous aerial archives; historical aerial photo ecology (repeat photography
   quantification) — their harmonization tricks.
9. 2024–2026 recent: foundation-model / SAM-era approaches claiming temporal
   consistency for high-res series.

## 5. RULES OF EVIDENCE

- **Full-text or it didn't happen**: a claim that enters the final answer must come
  from a fetched, read document (WebFetch the PDF/HTML; read all of it for the ≤10
  finalists). Snippet/abstract-only findings may only nominate candidates.
- Log every search query and its yield in a running HUNT LOG section of your working
  notes; the log is part of the deliverable (it is what makes Condition T defensible).
- Never fabricate citations. If a promising paper is paywalled and unreadable, record
  it as UNREADABLE with its metadata — do not summarize it from the abstract as if read.
- Repo files listed in §1 are readable and are the ground truth about OUR side;
  do not re-derive or second-guess them from memory.
- Budget awareness: check remaining WebSearch budget periodically; if it exhausts,
  continue via WebFetch of known repositories (arXiv listings, journal TOCs, Google
  Scholar profile pages of key authors: O'Neil-Dunne, Nowak, Greenfield, Song,
  MacFaden, Erker, Ucar) and record the constraint in the hunt log.

## 6. DELIVERABLE FORMAT (final message of the hunt, and nowhere else)

1. VERDICT: A met / B met / T reached (with the one-paragraph plain-language answer).
2. If A: the twin study, fully cited, method summary, F1–F8 scorecard.
3. If B: the solution design, implementable, with kill criteria and source trace.
4. The HUNT LOG: angles × queries × yields, papers triaged/read/unreadable.
5. The five closest misses regardless of verdict, each with the one sentence naming
   why it fails the criteria.
6. Explicit statement of anything in §1 the hunt found REASON TO DOUBT (evidence only).

## 7. LOOP DISCIPLINE

Work in iterations. Each iteration: pick the highest-value unexhausted angle, search,
triage, read, update the hunt log, then re-read §3 and honestly ask "is any condition
met?" If not, schedule the next iteration and continue. Do not stop for the night on
"tired" grounds — stop only on A, B, T, or the session's hard budget limits (record
which). Do not pad: an iteration that finds nothing writes one honest line in the log
and moves to the next angle.

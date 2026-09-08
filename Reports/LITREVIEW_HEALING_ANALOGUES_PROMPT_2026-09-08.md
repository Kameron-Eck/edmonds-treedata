# Literature-review prompt — analogues of "healing" in other machine-learning fields

**Use:** paste the block below into a fresh research session. It is self-contained; the
session does not need this repository. Written 2026-09-08.

---

## The prompt

You are doing a targeted literature review for an applied remote-sensing project. Your job
is to find, in fields OTHER than tree-canopy or land-cover mapping, methods that do what we
call "healing": correcting a per-time-step classification by borrowing evidence from
neighbouring time steps, under an explicit one-sided error model, with a bounded and
auditable license to change a label. Report mechanisms, not paper titles. Every claim needs
a citation you have actually read; say "not found" rather than inventing one.

### The problem, exactly

We have a time series of binary maps (canopy / not canopy) for one city, one map per
aerial acquisition, 36 acquisitions over ~30 years at 5 cm to 1 m resolution, produced by
one semantic-segmentation model fine-tuned per year. Only one year (2020) has hand labels;
every other year is supervised by projecting the 2020 mask onto it, so tree growth,
removal and seasonal difference all enter as label error. Consequences we have measured:

1. **Errors are one-sided.** Misses dominate; false canopy is rare. Recall against a
   human-verified panel varies year to year by resolution, season and delivery; precision
   is comparatively stable. A per-year map therefore flickers: a tree present in the truth
   appears in year A, vanishes in year B, reappears in year C. The flicker is a detection
   failure, not a real removal.
2. **Detectability is a curve, not a threshold.** Recall rises smoothly with crown size and
   with pixel size; small crowns are missed more often in coarse years. So "absent in a
   coarse year" carries less evidence than "absent in a fine year".
3. **Real change exists and must not be erased.** Verified tree losses (42 points) and
   verified no-change points (1,170) exist for one interval (2016 to 2024). A healing rule
   that fills a real removal is a "laundered loss" and is the primary failure we guard
   against.
4. **Registration between years is imperfect** (measured ~7 cm median offset after a
   landmark-based transform), so per-pixel comparisons across years need tolerance.

### What we built (so you can judge fit, not so you defend it)

- **Bounded temporal backfill.** A label may only move 0 → 1 (fill a miss) or 0 → 255
  (mark unsure); never 1 → 0. Filling is licensed only when the same location is canopy on
  BOTH sides of a gap (year before and year after), the gap is short, and the crown's size
  is above the detectability floor for the missing year's resolution.
- **Tiers by evidence.** HEAL when a lidar epoch could veto the fill; REVIEW when the gap
  is short but no independent sensor exists; BLIND when the gap is longer than the
  regrowth distance (a cut tree can coppice back within ~3 years, so a "return" after 3+
  years is ambiguous between a detection failure and a real replacement).
- **Validity intervals.** A fixed 2020 crown geometry is scored against every year's map
  (present / absent / unsure / unobserved), and each crown gets a validity interval; the
  healed sequence feeds change maps and trajectories, NOT the per-year canopy fraction
  (endpoints cannot be healed, so the bias never cancels).
- **Pre-registered kill criterion.** Zero laundered verified losses; impossible-triple
  removal (present-absent-present at verified no-change points) must not get worse.
- **Sensitivity model.** Recall correlates with fraction-of-canopy-in-tile (r = 0.91) and
  with crown size; both are measured curves, not assumptions.

### What to look for, field by field

For each field below, find the closest mechanism and answer the same six questions:
(a) what evidence licenses a correction, (b) is the correction one-directional and why,
(c) what guarantee or bound the method states, (d) how it avoids erasing real change,
(e) how it was validated against ground truth (what the gold looked like, what the
false-correction rate was), (f) what statistic or gate we could borrow verbatim.

1. **Multi-object tracking and object permanence.** Tracklet stitching, occlusion
   handling, "re-identification after a gap", track interpolation, birth/death models.
   Detections missed for k frames and then recovered are exactly our flicker. What gap
   lengths are bridged, on what evidence, and how do trackers avoid stitching two
   different objects (our laundering risk)?
2. **Video semantic segmentation and temporal consistency.** Temporal label propagation,
   optical-flow warping of labels, temporal ensembling, test-time consistency losses,
   temporal hole filling in depth/matting. Which methods are asymmetric (fill only)?
3. **Time-series imputation with monotonic or shape constraints.** Interval-censored
   survival analysis and current-status data; monotone regression; isotonic constraints;
   change-point detection with a minimum-segment-length prior. Our validity interval is an
   interval-censored survival time for a crown. Is there a standard estimator?
4. **Hidden Markov and state-space smoothing over class sequences with asymmetric
   emission errors.** Forward-backward smoothing where miss probability depends on a
   covariate (resolution, season) and false-alarm probability is near zero. How is the
   emission model calibrated when only one time step has labels?
5. **Label-noise correction and confident learning.** Methods that correct labels using
   model confidence plus structure (here, temporal structure), and their reported
   false-correction rates.
6. **Medical longitudinal imaging.** Lesion tracking across scans, monotone disease
   progression constraints, "no new lesion can vanish" style rules, and how radiology
   validates a longitudinal read against a per-scan read.
7. **Astronomy and event detection with persistence requirements.** Transient
   confirmation across epochs, detection-limit (magnitude-limited) completeness curves as
   a function of object brightness — the direct analogue of our detectability-by-crown-size
   curve. How is completeness used to weight an absence?
8. **Ecology and occupancy modelling.** Imperfect-detection occupancy models
   (MacKenzie-style): a species not observed at a site is "absent or undetected", with
   detection probability estimated from repeat visits. This is very close to our problem;
   report how detection probability is separated from occupancy when both vary with
   covariates, and what happens with one visit per season.
9. **Image processing primitives.** Hysteresis thresholding, morphological reconstruction,
   hole filling, and their 1-D temporal analogues — cheap baselines we should compare
   against before anything learned.
10. **Speech and signal processing.** Voice-activity "hangover", gap bridging, minimum
    duration constraints — simple one-sided rules with stated false-bridge rates.

### Constraints on your answer

- Prefer methods with a stated bound or a measured false-correction rate. A method that
  smooths without a laundering analysis is a lead, not a recommendation.
- Distinguish clearly: what the paper measured, what it assumed, what you inferred.
- For each borrowable statistic or gate, write the exact formula or procedure and what
  ground truth it needs. We can label roughly 250 to 2,000 points per session of human
  time; say whether the method's validation is feasible at that scale.
- Rank the ten fields by how well their assumptions match ours: one-sided error with a
  covariate-dependent miss rate, near-zero false alarms, sparse gold at one time step,
  real change that must survive.
- Close with the three ideas you would test first and the one you would refuse to adopt,
  with reasons.

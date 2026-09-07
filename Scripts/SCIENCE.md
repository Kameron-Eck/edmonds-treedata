# SCIENCE DIGEST — everything concluded, in one load — GENERATED

Regenerate: `py -3.12 qc/science_digest.py`. This is the KNOW half; the
CSVs under `phase4/qc/` are the CHECK half — evidence, joined on demand by
`py -3.12 qc/ask.py <subject>`. Reading them raw costs ~107k tokens and is
never the right move: they are denormalised for joining and complete rather
than selected. Everything below is resolved from them at build time.

## 1. What we can say about the canopy

- **-2.21** — Panel A's paired photo-interpretation measures a NET canopy change of -2.21 percentage points of city area between 2016 and 2024.
  <br>evidence `phase4/qc/panel_a_estimate.txt#regex:NET CHANGE (-?[0-9.]+) pp`
- **1.10** — The 95% confidence interval on the Panel A net change is +/-1.10 pp.
  <br>evidence `phase4/qc/panel_a_estimate.txt#regex:95% CI \+/-([0-9.]+) pp`
- **1250** — Panel A rests on 1,250 labelled paired points.
  <br>evidence `phase4/qc/panel_a_estimate.txt#regex:labelled (\d+) live`
- **0.7376** — One flight delivered two ways, scored by one frozen model, agrees at IoU 0.7376 — the processing-chain floor no downstream algorithm can remove.
  <br>evidence `phase4/qc/sameflight_consistency.csv#csv:canopy_iou@grid_px_m=1.0`
- **1.5008** — Bernoulli-thinning the dense lidar epoch to the sparse one's density fabricates 1.5008 km2 of apparent GAIN and essentially no loss — density cannot fake loss.
  <br>evidence `phase4/qc/lidar_decimation_null.csv#csv:km2@quantity=artifact_gain`
- **71** — The archive's 81 tile directories resolve to 71 distinct tile sets — the rest are arms sharing one set, which is what makes those comparisons clean.
  <br>evidence `phase4/qc/tilesets#dir_csv_count`
- **87** — Every scored arm's full precision-recall sweep is tracked: 87 curves.
  <br>evidence `phase4/qc/curves#dir_csv_count`
- **0.9089** — At the held precision of the matched-cut series, reported canopy fraction tracks the model's recall at r = 0.9089 (exact permutation p = 0.0018 over all 40,320 orderings). The residual year-to-year sawtooth is detector sensitivity moving, not canopy moving — which is what licenses an ASYMMETRIC correction, since the error is one-sided (the model misses real trees, it does not invent them).
  <br>evidence `phase4/qc/sensitivity_sawtooth.csv#csv:value@statistic=pearson_r_recall_vs_frac`
- **3.29** — Matching the operating point fixed the SIGN of the trend, not the year-to-year jitter: mean absolute step went from 3.06 pp (delivered cuts) to 3.29 pp (matched). Harmonisation is not what makes annual metrics readable.
  <br>evidence `phase4/qc/sensitivity_sawtooth.csv#csv:value@statistic=matched_mean_abs_step_pp`
- **0.9149** — Measured on our own archive, crown detectability is NOT ordered by ground resolution: at a 6 m minimum diameter, 2011s (38.1 cm effective) recalls 0.973 of bracketed crowns while 2015 (13.7 cm, nearly 3x finer) recalls 0.915. The per-epoch sensitivity dominates the pixel count, so a size gate must be per-epoch and cannot be derived from GSD alone.
  <br>evidence `phase4/qc/detectability_curve.csv#csv:recall@epoch=2015;kind=cumulative_ge;diam_lo_m=6`

## 2. Best arm per year, at one held cut

Ranked at `matched_p75` — highest recall while precision stays >= 0.75. A
ranking is only meaningful at a held cut: at per-arm best-F1 every arm is
best at something. `pop` is the scored population; **rows with different
refs or populations are NOT comparable to each other** — that is a coverage
difference, not a skill difference. Full detail: `phase4/qc/year_scoreboard.md`.

| year | best arm | recall | prec | AP | ref / scope | pop | tiles |
|---|---|---|---|---|---|---|---|
| 2006s | t1_2006s_in16 | 0.7278 | 0.7526 | 0.8249 | ccap_2016_hires_lc.tif / sample-test | 785,426 | 1415 |
| 2009 | trend8_2009 | 0.7424 | 0.75 | 0.81 | ccap_2021_hires_lc.tif / citywide | 344,975,021 | 11036 |
| 2011s | hy_e3_2011s | 0.8333 | 0.7516 | 0.866 | ccap_2016_hires_lc.tif / citywide | 163,466,339 | 3707 |
| 2013 | trend8_2013 | 0.7748 | 0.7512 | 0.8116 | ccap_2021_hires_lc.tif / citywide | 1,390,014,655 | 1256 |
| 2015 | trend8_2015 | 0.71 | 0.751 | 0.7746 | ccap_2021_hires_lc.tif / citywide | 1,366,533,758 | 934 |
| 2016 | t1_2016_in16 | 0.8713 | 0.7506 | 0.9069 | _chm2_canopy2m_binary.tif / sample-test | 7,643,036 | 4289 |
| 2017 | of_2017 | 0.7878 | 0.7531 | 0.7962 | ccap_2021_hires_lc.tif / citywide | 5,567,361,941 | 1291 |
| 2017k | of_2017k | 0.8159 | 0.75 | 0.8223 | ccap_2021_hires_lc.tif / citywide | 1,406,952,724 | 632 |
| 2017n | of_2017n | 0.1982 | 0.7632 | 0.7012 | ccap_2021_hires_lc.tif / citywide | 11,805,490 | 582 |
| 2017s | of_2017s | 0.7462 | 0.751 | 0.8191 | ccap_2021_hires_lc.tif / citywide | 149,422,078 | 557 |
| 2019 | trend8_2019 | 0.752 | 0.7582 | 0.8093 | ccap_2021_hires_lc.tif / citywide | 1,371,436,455 | 1792 |
| 2019n | t1_2019n_nir | 0.7146 | 0.7507 | 0.8105 | ccap_2021_hires_lc.tif / sample-test | 2,060,933 | 1694 |
| 2020 | t1_2020_add16 | 0.7005 | 0.7664 | 0.7739 | ccap_2021_hires_lc.tif / sample-test | 289,376,644 | 3862 |
| 2021 | trend8_2021 | 0.8157 | 0.7502 | 0.8391 | ccap_2021_hires_lc.tif / citywide | 1,406,539,700 | 1220 |
| 2022 | of_2022 | 0.743 | 0.7511 | 0.7848 | ccap_2021_hires_lc.tif / citywide | 5,178,270,225 | 1226 |
| 2024 | trend8_2024 | 0.6955 | 0.7524 | 0.7449 | ccap_2021_hires_lc.tif / citywide | 5,436,883,153 | 1254 |

16 of 37 acquisitions have a matched-cut read. ★ = designated champion.

## 3. What 34 completed investigations concluded

- **change_detector_design** (2026-09-06) — THE STEP-SHAPE CERTIFIER WINS AND THE SHIPPED PERSISTENCE FILTER IS A PURE RECALL TAX.
- **flicker_parcels_census** (2026-09-06) — THE MODEL DOES NOT HALLUCINATE CANOPY ON BARE GROUND; THE INSTABILITY LIVES IN SENSITIVITY ON REAL VEGETATION.
- **lit_hunt_temporal_inconsistency** (2026-09-06) — NO TWIN EXISTS, AND THE ONE DESIGN THAT PASSED THE CHECKLIST WAS REFUSED ON ITS OWN PILOT.
- **overlap_floor** (2026-09-06) — All three pre-registered reads complete, at policy-C matched cuts (the rule as written; delivered-cut fractions were never valid inputs).
- **trend8_uniform_rgb** (2026-09-06) — DELIVERED-CUT SERIES RETRACTED as a trend read (per-arm best-F1 cuts on 650x-skewed eval populations; the 2026-09-06 attack).
- **canopy_definition_review** (2026-09-05) — THE KNOBS THAT SOUND DEFINITIONAL ARE WORTH ~NOTHING; THE INVISIBLE ONES CARRY THE WHOLE ANSWER.
- **accuracy_sample_design** (2026-09-04) — THE DESIGN HOLDS, THE BINDING CONSTRAINT IS THE INTERPRETER RATHER THAN n, AND NO ESTIMATE HAS EVER BEEN PRODUCED.
- **certified_flat_scoring** (2026-09-04) — THE ABSOLUTE FALSE-POSITIVE FLOOR IS REAL, AND LIDAR AS AN INPUT CHANNEL COLLAPSES IT.
- **lidar_decimation_null** (2026-09-04) — DENSITY CAN FAKE GAIN AND CANNOT FAKE LOSS — that asymmetry is what revived the lidar leg.
- **metric_tolerance_c2b** (2026-09-04) — THE STRICT SCORE WAS MEASURING PIXEL SIZE, NOT DETECTION.
- **panel_a_direction** (2026-09-04) — DIRECTION IS DOWN, and it is the project's only human-measured trend statement.
- **sameflight_floor_c3** (2026-09-04) — THE FLOOR EXISTS AND IT IS LARGE ENOUGH TO MATTER.
- **greenness_gradient_correction** (2026-09-03) — THE GRADIENT IS DELIVERY RADIOMETRY, NOT PHENOLOGY, AND THE LEAF-OFF IGNORE EXPERIMENT IS DEAD AS PREMISED.
- **leafoff_recall_gradient** (2026-09-03) — A DIRECTION, NOT A GRADIENT — and the direction was later re-attributed away from season.
- **tier1_science_sample** (2026-09-03) — Floor (max pairwise |delta| among 2011s base/s2/s3, recall@prec0.75 test blocks) = 0.0085.
- **coregistration_2020s_anchor** (2026-09-01) — THE ANCHOR CHAIN IS CERTIFIED, AND REGISTRATION IS SEPARABLE FROM THE THING IT IS USUALLY CONFUSED WITH.
- **hard_year_pilot** (2026-09-01) — MIXED, read per the rule.
- **recipe_audit** (2026-09-01) — THE THRESHOLD IS THE ONE LARGE KNOB, AND THE SIEVE IS NOT ON THE TABLE — the direct answer to the question that prompted the audit.
- **threshold_policy_c** (2026-09-01) — ADOPTED AND IMPLEMENTED THE DAY IT WAS PROPOSED — "DECIDED: C (Kam, 2026-09-01 — 'Let's go with C')" in Reports/RECIPE_AUDIT_2026-09-01.md.
- **pilot_2019** (2026-08-31) — 3/3 GATE PASS 2026-08-31 04:36Z.
- **same_flight_pair_2019** (2026-08-31) — ONE FLIGHT, TWO DELIVERED PRODUCTS — and the correction runs in the direction that makes the pilot's resolution result STRONGER, not weaker.
- **arm_diagnostics_2009** (2026-08-29) — THE DIAGNOSTICS LANDED, AND WHAT THEY MOSTLY PRODUCED WAS A FLOOR.
- **chm_encodings_year_assignment** (2026-08-29) — ALL FOUR COMMITMENTS LANDED, AND THE ASSIGNMENT IS OPT-IN BY DESIGN.
- **chm_roc_all_three** (2026-08-29) — THE SCREEN INVERTED.
- **chm_roc_support_confound** (2026-08-29) — SUPPORT IS MOST OF IT, AND THE REFERENCE REWARDS BLUR REGARDLESS OF WHICH PRODUCT IS BLURRED.
- **chm_standalone_prior_closure** (2026-08-29) — FORM EXPLAINS THE GAP, THE SCREEN DID NOT FIRE, AND THE TRAINING QUESTION STAYS UNDETERMINED.
- **old_chm_defect** (2026-08-29) — THE SIGN WAS BACKWARDS AND THE DEFECT IS LARGE.
- **stability_mining_closure** (2026-08-29) — CLOSED AS THREE DIFFERENT ANSWERS, and the composite read is that the projected 2020 key is more right than it looks.
- **degraded_imagery_lit_review** (2026-08-27) — THE CHECK PAID FOR ITSELF, AND IT CHANGED THE PREMISE OF THE SYNTHESIS WORK.
- **m06_nir_arm** (2026-08-27) — CLOSED, AND THE CHM STAYS IN SLOT FOUR.
- **sector_campaign_v1** (2026-08-26) — SAMPLED INFERENCE WORKS; PROMOTION DOES NOT FOLLOW FROM IT.
- **imagery_qc_suite_2026_08_24** (2026-08-24) — THE ARCHIVE IS USABLE, AND ITS REGISTRATION IS THE THING THAT NEEDED WATCHING.
- **rescore_2013_citywide** (2026-08-22) — THE PREDICTED MOVEMENT DID NOT HAPPEN.
- **chm_gap_2016** (2026-08-18) — THE ASSUMPTION HOLDS AND IS NOW CHECKED RATHER THAN ASSERTED.

## 4. What is NOT known

- never tiled (13): 2002s, 2003s, 2007s, 2009s, 2012s, 2013s, 2015n, 2015s, 2020s, 2021n, 2022s, 2023n, 2024s
- no matched-cut read (21): 2000, 2002, 2002s, 2003s, 2005, 2007, 2007s, 2009s, 2012s, 2013s, 2015n, 2015s, 2018s, 2019s, 2020s, 2021n, 2021s, 2022s, 2023, 2023n, 2024s
- no champion (20): 2000, 2002, 2002s, 2007s, 2009s, 2013, 2013s, 2015, 2015n, 2015s, 2016, 2017, 2017k, 2017n, 2017s, 2019s, 2020, 2021n, 2022s, 2024s
- results documented but UNSIGNED (5): ccap_mixed_sign_bias, epoch_decay_mvv0, era_matched_rescore, fusion_5band_nir_chm, shadow_fp_fn_2016

A gap here is a record, not a backlog — some acquisitions are deliberately out of scope. `phase4/qc/coverage_map.md` has the matrix.

## 5. What is blocked, and on whom (10 open)

**Ready now (5) — nothing above them:**

- `synthesis-session` [kam] — Sit down with the full evidence table and set the story: what does the project claim about Edmonds canopy dire
- `k4-signoff` [kam] — Sign off or amend the documented findings block — review corrections, bootstrap CIs, canopy definition §6 and 
- `k1-labelling` [kam] — Label the redrawn 250-point 2016 sample (~15 min at the measured pace), then decide K2 blind repeats and the K
- `champion-designations` [kam] — Name a champion arm for the 20 acquisitions that have none, or state which are deliberately out of scope.
- `change-detector-build` [kam] — Green-light the change-detector build: gold-set freeze, certifier port with the three audit fixes, tiers, then

**Waiting (5):** `ccap-bias-quantification` after k1-labelling, `thirtysix-run-go` after champion-designations, k4-signoff, `city-statement` after synthesis-session, k4-signoff, `paper-scope` after synthesis-session, k4-signoff, `forward-monitoring` after city-statement

Full entries with evidence: `py -3.12 qc/ask.py --decisions`.

## 2026-08-18  LIT PHASE 4 — measurement validity, 37 papers (ID 69-105), searches 9-14
goal:    the 8 prior searches covered architecture/resolution/temporal/labels. None asked
         whether our numbers MEAN anything. This phase targets the validity gap: sampling,
         reference disagreement, height bias, label propagation, CHM vintage, interpreter protocol.
did:     Literature_Tracker.xlsx +37 rows, +6 rows on "Search Phase Reference".
         S9 accuracy/area protocol (8) — Olofsson 2014/2013, Stehman+Foody 2019, Stehman 2014,
           Wagner+Stehman 2015, Stehman+Wagner 2024, Radoux 2020, Pontius+Millones 2011.
         S10 reference quality (6) — McCombs 2016 (C-CAP), Wickham 2023 (NLCD), Foody 2010,
           Foody 2022, Gutierrez-Velez 2024, Majasalmi 2021.
         S11 height-stratified bias (6) — Turubanova 2023, Moudry 2024, Ferraz 2016,
           Hamraz 2017, Clark 2023, Guo 2023.
         S12 label-noise propagation (5) — Arazo 2020, Liu+Chun 2009, Moraes 2024, Peng 2025, Tang 2025.
         S13 CHM fusion / vintage (5) — Wagner 2024, Allred 2025, Kwong+Fung 2020, Zhang 2025, Sierra 2026.
         S14 interpretation protocol (7) — Pengra 2020, Stehman 2022, Xing+Stehman 2024,
           Tarko 2020, Reis 2024, Parmehr 2016, King+Locke 2013.
decided: every DOI verified against Crossref API or a search hit — none written from memory.
         Unverified issue/article numbers STRIPPED rather than guessed.
         Rows re-sorted 9->14, IDs 69-105 sequential.
findings that BITE (papers vs our 5 empirical claims):
  - Stehman 2014 LICENSES stratifying on the REFERENCE (CHM band, C-CAP/NDVI agreement).
    Unbiased if you use its estimators; variance inflates. Our planned design is legal.
  - Wickham 2023: NLCD OA 77.5% on primary label -> 87.1% if an ALTERNATE label counts.
    10pp swing from scoring interpreter uncertainty alone > our whole model-quality range.
    -> 250-pt protocol MUST record primary + alternate ("fuzzy"), report both.
  - McCombs 2016 (C-CAP's OWN accuracy paper): 3x3 sample unit, 6-of-9 homogeneity rule,
    OR/WA 84.9%. C-CAP was NEVER validated at single-pixel scale and the paper says it is a
    SCREENING tool for local decisions. Some of our 15-17% is scale misuse, not model error.
  - Foody 2010: 10% reference error -> producer's accuracy UNDER-est 18.5% if errors independent,
    OVER-est 12.3% if CORRELATED. Ours are correlated (same imagery, same interpreter lineage)
    -> our recall is probably OPTIMISTIC. Plus latent-class = accuracy with NO gold standard.
  - Foody 2022 is the escape from finding 5: treat C-CAP + NDVI ref + model as 3 imperfect tests
    of one latent canopy variable, solve each one's sensitivity/specificity. Disagreement stops
    being noise and becomes the estimator's INPUT.
  - Ferraz 2016 + Turubanova 2023: the height-monotonic recall curve REPLICATES in lidar and in
    Landsat-Europe (error concentrates 4-6m; 25% under vs WorldCover from short/open stands).
    Finding 1 is a PROPERTY of canopy remote sensing, not our U-Net. Supports finding 2.
  - Hamraz 2017 CONTRADICTS the fatalist reading: stratify-then-segment lifted understory recall
    +22.1% at -15.0% precision. Intervention = height-conditioned model, not a better single pass.
    Precision cost matches finding 5 drifting toward the liberal NDVI ref.
  - Guo 2023 names the trade: adding small-crown training examples RECRUITS SHRUBS. Likely what
    our NIR+CHM overlay actually did. -> 250-pt protocol must separate short tree from shrub or
    it cannot adjudicate finding 5 at all.
  - Clark 2023: patch sampling under-samples small-area features by construction. CHEAP TEST
    before more overlay work — re-sample 2020 training patches stratified by CHM band, watch low-height recall.
  - Moudry 2024 CAUTION on finding 1: global CHM products are themselves height-biased. Sierra 2026
    puts CHM MAE ~3m at realistic density. A 3m error BLURS our 5m-wide recall bands. Validate
    the 2016 lidar CHM before trusting its bands as truth.
  - Wagner 2024 is the fix for the CHM vintage problem: train U-Net to PREDICT height from imagery
    using lidar only as supervision -> synthesize a per-year CHM for all 18 acquisitions instead of
    smearing one 2016 snapshot across 2000-2024. Turns 60% coverage from a blocker into training data.
  - S14 gives the 250-pt design: Wagner+Stehman 2015 / Stehman+Wagner 2024 for allocation
    (over-sample 5-15m + disagreement strata), Stehman 2022 + Xing 2024 to fold interpreter
    variance INTO the CI, Pengra 2020 (88% OA, tree cover high-agreement) and King+Locke 2013
    (>90% two-assessor, n>=250 adequate) as benchmarks. Reis 2024 is the warning: on HISTORICAL
    imagery 3 interpreters fully agreed on <40% of pixels — our 2000s years may not adjudicate.
files:   Literature_Tracker.xlsx (sheets "Literature Tracker" 69-105, "Search Phase Reference" +6)
next:    design the ~250-pt run: strata = CHM band x C-CAP/NDVI agreement, allocation per
         Wagner+Stehman, response design = primary + fuzzy alternate + shrub-vs-short-tree call,
         duplicate subset for interpreter variance. Then Foody 2022 latent-class on the 3 sources.
         Cheap pre-test first: Clark 2023 stratified patch re-sampling.


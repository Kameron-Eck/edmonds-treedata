# MACHINERY AUDIT — 2026-08 (literature-driven, adversarially verified)

Commissioned by Kam 2026-08-24 ("what are the glaring issues with the machinery considering my
available imagery, and how can we improve it"). Method: a 78-agent workflow — four literature
miners over the live 210-row `Literature_Tracker.xlsx` + the 61-phase search history + the
4,706-line `litwatch_robustness.md` ledger; five engine code lanes (input bands, loss/sampling,
architecture, inference efficiency, labels/temporal); one external-SOTA gap search; then an
adversarial verification wave in which every glaring/major claim was independently re-checked
against the cited files, tracker rows and ledger lines (refuted claims dropped); then synthesis.
5.2M agent tokens; every claim below carries its verification verdict.

The ranked backlog below is the synthesis output, verbatim. Costs assume the sector harness
(`--infer-aoi`, ~9-10% of city pixels for inference/eval; training is never discounted) and the
P11.5 launch gate. Companion artifacts: `pipeline/sector_campaign_checklist.yaml` (the running
baseline campaign), `reports/sector_campaign_design.md`.

---

# Machinery Audit — Final Ranked Backlog (synthesis, 2026-08-24)

**Ranking principle.** Items are ranked by expected-honest-metric-gain per unit cost, where "honest metrics" means: qc_indep_report.csv live=1 rows (NDVI+CHM ref for NIR years, C-CAP, Olofsson photo-interp), the deliverable-level numbers (area series, per-crown intervals), and the *interpretability* of those numbers. Items that move no model metric but change a biased headline into an honest one count as gain.

**Cost convention (applies to every GPU item).** The sector harness (`--infer-aoi`, cli.py:181/385) cuts **inference/eval** to ~9-10% of city pixels; it does NOT cut training — every training arm is a full fine-tune (~60-90 min A100 per the queue_sectors_fullext.yaml estimates), and **every launch is Kam-gated per P11.5**. Several verifiers flagged "sector A/B" language as understating training cost; read all costs below with that convention.

**Verdict discipline.** Every item carries the verification pass's verdict and revised severity in brackets. WEAKENED items are scoped to what survived verification — their specs are not settled fact.

---

## Tier 0 — local, zero GPU, do first (M01–M05)

These five are all local raster/stats/doc work. They de-confound everything downstream and should land before (or alongside) any GPU spend.

### M01_INDEP_OPERATING_POINTS — deploy thresholds from independent references; score at matched call rate; run the Q132 threshold-trend test
**[CONFIRMED — high]** (merges CONFIRMED major "no matched operating points / Q132 unrun" with the minors' independent-threshold finding — same lever)

**Issue.** Every deployed per-year threshold is the max-F1 point against labels projected from the 2020 mask (config.py:255 `THRESH_MODE="best_f1"`; postproc.py:21-68 reads `best_f1_thresh` from the eval CSV, which phase4_qc_score.py:83 itself calls "circular"). Real canopy the 2020 mask missed scores as a false positive during thresholding, pushing the operating point up — recall down — on a model whose headline defect is under-prediction. Measured: deployed thresholds wander 0.33-0.51; ~61% of the cross-year recall spread is operating point, not model skill (Q121: spread 0.1827 → 0.0721 at matched call rate 0.30, litwatch_robustness.md:3438-3487 — derivation recovered to disk in scratch/litwatch_scratch/q121c.py, though Q121 was not among the four re-executed claims); a fixed threshold once manufactured a +0.225 "improvement" that reversed at matched recall (Q119/it.68, :3193-3207, reproduced exactly on re-run); "none of the year-to-year recall comparisons in the pipeline currently" match operating points (:3203-3207); and Q132 — does per-year thresholding manufacture the canopy trend in the area series? — has never been run (:4587-4590). AUROC-ranked comparisons are already immune (core.py:1323-1326 tells operators to judge by AUROC); everything threshold-based, including the deliverable area series, is exposed.

**Spec.** (a) New `THRESH_MODE="indep"` in phase4seg/postproc.py (`_operating_threshold`, :21-68): read a per-year threshold fitted against the independent reference — qc/phase4_qc_indep.py already sweeps thresholds vs NDVI+CHM / C-CAP; emit a per-year best-op CSV and wire postproc to read it. The existing `INFER_THRESH_OVERRIDE` plumbing (config.py:263, postproc.py:42-43, cli.py:382) is the interim path: a QC script writes the value, the queue passes `--infer-thresh`. (b) Matched-call-rate scoring mode in qc/phase4_qc_indep.py / phase4_qc_score.py — the sampled-point method is already demonstrated in scratch/litwatch_scratch/q121c.py (instrument, safe to rerun). (c) Run Q132: recompute the area series at a fixed call rate and at the deployed per-year thresholds; the difference is the manufactured trend.

**Expected honest-metric effect.** Moves DEPLOYED recall against independent references immediately for years whose circular threshold sits above the independent optimum — no retrain needed. Does not cure the structural under-prediction (CHATLOG.md:2847: "NOT a threshold artifact — the sweep refutes it"), but removes an up-to-~3.3 pp threshold-calibration term from year-to-year area movement (Q136 table across the deployed 0.33-0.51 range) — larger than the 2.6 pp policy gap the series feeds — and makes every subsequent A/B interpretable at matched operating point.

**Cost.** Local only, zero GPU; ~1-2 days (scoring mode ~1 day; THRESH_MODE small).

### M02_P3_EXECUTE — wire the amendments, run the P3 photo-interpretation study (2016 deep)
**[CONFIRMED — glaring, unchanged]**

**Issue.** The P3 study — designed, powered (design_power_2016: the stratified n=250 design DOES arbitrate at ≤5% interpreter error; binding constraint is interpreter fidelity, CHATLOG.md:2612-2640), sampled (phase4/qc/sample_{2000,2016,2022n,2023n}.csv, dual_reference strata, disagree strata over-sampled) — has never been executed: zero interpreted points exist on either plane, and the 7 protocol amendments were proposed with NONE applied (CHATLOG.md:2732; one since superseded by design_power, so six live). Search 37: the human sample is the FOURTH indicator that makes latent-class accuracy estimation identifiable at all (litwatch_robustness.md:1036-1070). Every measurement question in the project — reference arbitration (the two references disagree on the SIGN of 2016→2021 change, it.44), the area estimator (M03), latent-class identifiability, interval calibration — funnels through this one un-run study.

**Spec.** Wire the live amendments into qc/phase4_accuracy_sample.py (steps design/serve/estimate; browser UI phase4_accuracy_review.html): primary+alternate scoring (ID 78 — a scoring convention alone is worth ~10 pp), duplicate-interpreted subset (IDs 100/101 — "NOT optional"), a 20-30-point interpreter-calibration block (U7), unsure adjudication. Adopt the response-design literature instead of inventing: TimeSync-style whole-trajectory interpretation per point, ≥2 interpreters with an interpenetrating subsample, allocation chosen explicitly for accuracy vs area (different studies), the anchoring-vs-independence trade-off documented. Run **2016 DEEP first**, not 250×3 (2022n reference separation is marginal — 4.65 pp vs 2016's 8.24 pp, CHATLOG.md:753-756). Gates: the written canopy definition (Q1/U1 — only D2 decided) and Kam's amendment sign-off gate the *interpretation start*; the wiring is not gated.

**Expected honest-metric effect.** No model metric moves; the evidence structure changes state: the just-identified (untestable) 3-source latent-class fit becomes a testable 4-source one; per-year accuracy gets an interpreter-fidelity-bounded honest number (±4.42 pp at n=250; policy-grade ±2.0 pp needs ~1,221 pts/yr); unblocks M03.

**Cost.** 1-2 days local wiring; interpretation is human hours (Kam: ~250 points + duplicate subset for 2016-deep); zero GPU.

### M03_OLOFSSON_AREA_SERIES — replace the threshold-counted headline area series with the stratified estimator
**[CONFIRMED — high; framing corrected by verifiers: measured threshold-SENSITIVITY, not a proven bias in published numbers]**

**Issue.** The headline canopy-area series is threshold-counted pixels **in the live engine** — phase4seg/postproc.py:121 (`canopy_area = canopy_px * pixel_area` after morphology) feeding eval/_per_year_canopy_area.csv via `_append_area_summary` (:217-232) — not just legacy phase3_semantic_dev.py:1718-1723. Map-count area is threshold-sensitive by up to 17.3 pp (33.56% @0.30 → 16.24% @0.70; Q136, litwatch_robustness.md:3680-3735, verified by re-run), deployed thresholds vary 0.33-0.51, and because thresholds are calibrated per year the ~3.3 pp movement across that range varies BY YEAR — injecting spurious year-to-year variation into a series feeding a 2.6 pp policy question. This is the ledger's own #1 queued fix ("Adoption is Kam's call... Not new research — applying what we already read", :3848-3858; WORKPLAN Tier-1 #2). The Olofsson estimator is ALREADY IMPLEMENTED with full multinomial covariance (qc/phase4_accuracy_sample.py `--step estimate`, :285-310, 376-397) and simulation-validated unbiased at every threshold (35.87-36.01 at n=250, :3701-3706). The pending state is documented sequencing (definition gate + Kam sign-off), not neglect — but the series remains threshold-counted today.

**Spec.** Feed M02's interpreted points into `--step estimate`; report stratified area + CI per year as the headline; demote the pixel count to a diagnostic column in _per_year_canopy_area.csv; keep the standing gate that the Olofsson harness gates any pre-2016 outward number (CHATLOG.md:622). Sectors are irrelevant here — this is an estimation change, not a model change.

**Expected honest-metric effect.** The deliverable series becomes unbiased w.r.t. threshold with an attached CI; the cross-year trend is no longer confounded with threshold calibration (M01's Q132 run quantifies how much the old series was). Honest budget: n=250/yr gives ±4.4 pp (cannot resolve the 2.6 pp policy gap); ~1,221 pts/yr gives ±2.0 pp.

**Cost.** Wiring days, zero GPU. The real cost is M02's human interpretation, which this item inherits — that is the price of an honest headline.

### M04_SELECTION_RULE — write the model-selection rule down; stamp the caveat; sweep only before method-vs-method claims
**[WEAKENED — high for cross-method comparisons and headline operating points; medium for same-recipe sector A/Bs scored threshold-free vs independent refs]**

**Issue.** Checkpoint selection AND threshold selection both ride the projected-2020 proxy: core.py:951-998 early-stops and picks `sem_best` on a val split whose off-year labels are the projected 2020 citywide mask under `--force-citywide`; config.py:255 picks the threshold the same way. That is the scheme Gulrajani & Lopez-Paz call INCOMPLETE (litwatch_robustness.md:826-873), Q33 is the ledger's open "gates every method comparison" question (:3905-3910), and no LR/weight-decay/batch sweep exists anywhere (CHATLOG sweeps are threshold-only). Verifiers cut the overreach: same-recipe A/B deltas scored threshold-free (AUROC/AP) against independent references remain substantially interpretable (CLAUDE.md rule 5 machinery exists and is used); the residual confound is that both arms deploy proxy-selected checkpoints — a bias, not a void. The ledger also deprecated agreement-on-the-line for dense prediction (Q35, no demonstration exists) in favour of latent-class / independent-reference selection (Q40) — the rule must name the surviving candidate, not the deprecated one.

**Spec.** A one-page rule in Method_Pipeline.md: (1) A/B winners are named on qc_indep live=1 threshold-free metrics at matched call rate (M01); (2) for NIR/C-CAP years, add an independent-reference validation metric to checkpoint selection (post-hoc re-selection over saved checkpoints is enough — no training change); (3) no-NIR years: selection is proxy-based and every number carries a stamped caveat saying so; (4) the one-time LR/WD/batch sweep (6-10 sector-restricted runs, ~60-90 min each) is required only before any **method-vs-method** claim (foundation-model arms, learned-change arms) — not before same-recipe A/Bs, which may run meanwhile.

**Expected honest-metric effect.** No direct movement; prevents selection-flip artifacts (the Brigato/G&LP result: a tuned plain baseline beats specialist methods under honest selection) and makes M06-M08 verdicts defensible.

**Cost.** Writing free; post-hoc checkpoint re-selection local; the optional sweep ~one A100 evening, Kam-gated, deferred until a method-vs-method claim needs it.

### M05_COREG_TO_ANCHOR — per-epoch offset table vs the 2020 anchor; fix the displaced 2024 primary
**[CONFIRMED — high]**

**Issue.** No per-epoch offset-to-anchor table exists for the 18 acquisitions the 2020 polygons are projected onto: qc/imagery_qc_suite.py QC4 measures SAME-year pairs only (:423), and the one cross-year investigation found 2024_coe displaced **1.29 m systematically** (consistent to 0.03 m across five sites; phase4/qc/investigate_2024_offset_2026-08-24.json) — 10-25% of a crown diameter, i.e. manufactured per-crown change — while that displaced file remains the PRIMARY 2024 catalog entry at the per-crown seg tier (config.py:532-534) and the aligned 2024s copy (0.17 m) sits as complement. Film-era years (2000-2013, four agencies) have zero cross-year measurements. The ledger calls co-registration "not a side quest but a precondition for any per-crown change claim" (:1437-1442). Mitigating context: 2022_coe vs 2020_coe measured 0.004 m — the modern stock is not uniformly misaligned; the film era is the unknown.

**Spec.** Extend investigate_2024_offset.py's phase-correlation-on-stable-built-targets procedure to every catalog epoch vs the 2020 anchor (5 fixed sites, local mirror first) → emit qc/coreg_to_anchor.csv (per-site dx/dy/r + robust median per epoch). Promote 2024s to primary or shift-correct 2024_coe (catalog edit; config.py is pure-move protected, so Kam signs off). State a crown-scale tolerance (e.g. 0.5 m); epochs above it get shift-corrected, or — for 2000/2002 if phase correlation fails on film-era content — multi-epoch feature matching per ID 180. Residual offsets feed the change-scoring buffer (M09). **Companion (Q123, relief displacement — [WEAKENED — medium], real and untested):** the translation table above is height-blind, and no co-registration check ever done allowed a height-DEPENDENT offset — but conventional orthos displace everything above bare earth radially per frame layout (up to ~3.3 m on tall crowns), a different field per acquisition. Run the ledger's own designed test (litwatch_robustness.md:4542-4543): cross-correlate mask vs reference within CHM height bands, per acquisition, looking for height-dependent offset; buffer/IGNORE high-displacement zones in change scoring if found (the region→IGNORE stamping just landed in tiling.py supports this). Bounding fact carried: tall-band recall is the HIGHEST measured, so the within-year effect is not dominant — the exposure is the cross-year change series (Q125, untested). True-ortho regeneration is rejected (see Rejected #9); measure-then-IGNORE is the whole remedy.

**Expected honest-metric effect.** Removes a measured ~17 px systematic shift from one per-crown-tier year immediately; bounds (or flags) misregistration-manufactured change for all epochs before any interval is claimed. No per-year accuracy metric moves; the per-crown deliverable's validity does.

**Cost.** Local raster work; ~1 script + a few hours compute for all epochs; zero GPU.

---

## Tier 1 — sector-harness GPU experiments (M06–M08, M12)

Run after M01/M04 so verdicts are scored honestly. All launches Kam-gated.

### M06_NIR_INPUT_CHANNEL — wire NIR as a 4th input channel (HS pattern) + open the intermittent-NIR search phase
**[CONFIRMED — high; gain unproven, prior 4th-channel ablation found a dead channel]**

**Issue.** The model is RGB-only while the inventory holds TEN 4-band NIR acquisitions (2015n, 2016, 2017n, 2017s, 2018s, 2019n, 2019s, 2021n, 2021s, 2023n), and the one signal measured nearly year-invariant across this archive is NDVI separability (AUROC 0.835-0.886, sd 0.016, vs RGB sd 0.057). The ledger's own elimination chain lands on exactly "height channel or NIR" (it.68/it.69, litwatch_robustness.md:4693-4694), yet no NIR input path exists anywhere in phase4seg: tiling reads the 4-band window then drops band 4 (tiling.py:380-382; common.py:694-695), and the only 4th-channel option is CHM/hillshade (config.py:337-345). Calibrating history the audit surfaced: a per-year NIR band (v023) was BUILT AND KILLED 2026-06-29 for "variable channels per year too messy" (CHATLOG.md:2865) — precisely the heterogeneous-band-availability problem that a never-searched literature (modality dropout, privileged-information distillation, RGB→NIR synthesis) exists to solve (zero of 60 searches cover it); the prior CHM 4th-channel ablation found the inflated channel DEAD before the trainable-stem fix (core.py:739), and v045/v046 remain untested; the model does not key on greenness (Q96/Q135).

**Spec.** (a) Search phase, hours, no GPU: "segmentation with intermittent NIR availability" — HeMIS-style modality dropout, 4-band-teacher→RGB-student distillation, NIR synthesis. Note the existing HS_DROPOUT mechanic (config.py:333-344, 0.25, blanks the 4th channel to its mean in training) IS the modality-dropout mechanic, never connected to that literature. (b) Wiring: NIR as a selectable 4th channel exactly like HS_SOURCE — tiling stamps an NIR tag (the read already touches band 4), checkpoint records band count (core.py:721), zero-init conv1 inflation with trainable stem (core.py:736-745), HS_DROPOUT-style dropout so a pure-RGB pathway survives for the eight no-NIR years. (c) A/B: 2016 first; score vs **C-CAP 2016**, not the NDVI+CHM reference (an NIR-fed model scored on an NDVI-derived reference is partially circular), at matched call rate (M01); run one arm WITHOUT `--add-canopy-mask` so the input-channel effect is un-confounded by NDVI-derived labels; report both. Headline metric per the ledger's own calibration note: **cross-arm variance of honest recall across NIR years**, not any single year's IoU — the year-invariance is the prize.

**Expected honest-metric effect.** Hypothesis, honestly framed: plausible gain is cross-year STABILITY of honest recall (the sd 0.016 vs 0.057 contrast); the per-pixel ceiling of a lone NDVI feature is ~0.86 AUROC; dead-channel risk is real. NIR reaches only the ten coarse/complement acquisitions — never the 3-band fine-tier anchor years.

**Cost.** Impl low (HS template exists end-to-end); GPU: one L4/T4 canary + one A100 fine-tune (~1-1.5 h) + sector inference per arm; roughly one A100 evening for the 2016 pair.

### M07_BN_ADAPTATION_LADDER — AdaBN offline statistics and BN-affine-only tuning, per year
**[CONFIRMED — caveat: Phase B already adapts BN stats implicitly, so this isolates the label-free effect]**

**Issue.** DSBN — one BN branch per radiometric cluster — is the ledger's "strongest candidate the loop has produced" for the sensor/era shift (Search 27, litwatch_robustness.md:625-659), and its two near-free variants were never tried: AdaBN-style offline recompute of BN statistics per year (no training at all — resolves the v039 FREEZE_ENCODER_BN vs AdaBN conflict, since offline whole-domain statistics have no small-batch instability) and BN-affine-only per-year tuning ("about the cheapest per-domain adaptation available — far cheaper than the full per-year fine-tunes we run now"). No dsbn/adabn/affine-only code exists in phase4seg; the only BN-domain machinery is the freeze itself (config.py:181, applied core.py:972-985). Caveat carried: Phase B trains without freeze_bn (core.py:1048-1050), so production checkpoints already carry target-year BN stats entangled with projected-label gradients — the A/B is a signal test of the ISOLATED, label-free adaptation, not a production comparison.

**Spec.** (1) AdaBN arm: forward passes over the year's existing tiles with BN in stats-update mode (small hook; Colab-only per the phase4seg gotcha), vs the production checkpoint. (2) BN-affine-only arm: a param-group filter reusing the _unfreeze_encoder/_set_encoder_bn_eval helpers (core.py:748+), minutes-to-tens-of-minutes of training per year (a few thousand params). Both scored on sectors vs independent refs at matched call rate. Log per-year probability histograms on sector outputs (hygiene #3): if the 0.33-0.51 threshold wander is product-coherent calibration drift, BN recalibration should collapse it; if drift persists, it is genuine class-balance shift and belongs to the loss/threshold lane.

**Expected honest-metric effect.** If the cross-year shift is BN-statistics-shaped, honest AUROC/recall moves with ZERO projected labels — sidestepping the confirmation-bias channel entirely for the adaptation step. A null is cheap and kills the DSBN production idea; either way it is the designed diagnostic for the threshold-drift mechanism.

**Cost.** Impl ~1-2 days; GPU minutes per year (forward-only / tiny tuning) + sector inference — the cheapest GPU experiments in this backlog.

### M08_CHM_STRAT_SAMPLER — CHM-band-stratified patch sampling, anchor-first, canaried
**[CONFIRMED — with destabilization and label-noise caveats]**

**Issue.** The 5-15 m height band holds 53% of all misses (WORKPLAN §1.2, survived confound tests), and the project's own cheapest queued instrument against it — Clark's "re-sample training patches stratified by CHM band and see whether low-height recall moves" (U5) — was never run (CHATLOG.md:2714-2715: "session ended first"). The sampler stratifies only by canopy fraction plus GRVI hard negatives (config.py:96-149; tiling.py:81-97) — no height or crown-size stratum. Hamraz (ID 86): stratify-then-segment lifted understory recall +22.1% at a -15.0% precision cost where a better single-pass model did not. Caveats carried: the v032 collapse shows pool-composition changes can hit the all-background cliff (config.py:133-137) — canary mandatory; and stratifying toward 5-15 m on PROJECTED labels oversamples exactly where those labels are most wrong (Arazo amplification) — so anchor/hand-label 2020 first (no noise there), or 2016 with the corrected overlay.

**Spec.** Add a CHM-band stratum option to tiling.py's stratified sampler as a FLAG, not a constant edit (config.py is pure-move protected; the flag feeds _tile_signature, so expect the ~20-min re-tile). Strata limited to the ~60% CHM-covered area; report covered/uncovered strata separately (hygiene #11). Run on the 2020 anchor and/or 2016+overlay; canary (v032 precedent), then one A100 A/B pair, sector-scored at matched call rate. **Rider (shares this retile+canary, same pool-composition risk surface):** bound the forced negative-site tiles — currently tiled at the coarse 128 px stride with up to 16x overlap, exempt from the tile budget, inflating realized background share to ~36% vs the 22% target — by non-overlapping stride, per-site cap, or counting them against BACKGROUND_BUDGET_FRACTION; and A/B the just-landed region-aware negative injection in the same pair so that change ships with a measured effect.

**Expected honest-metric effect.** Targeted recall gain in the band carrying 53% of misses, bought with precision (judge at matched call rate vs independent refs — the ID 86 trade is explicit). This is the one training-side lever aimed exactly at the measured headline defect.

**Cost.** ~1 day impl + ~20-min re-tile per year touched; one canary + one A100 pair (~2-3 h total).

### M12_WISEFT_ALPHA — WiSE-FT interpolation dial on the 3-channel line
**[WEAKENED — medium; soups half contingent on open Q38]**

**Issue.** WiSE-FT — interpolating each per-year fine-tune with sem_best_2020.pt — is checkpoint arithmetic over weights that all descend from the same anchor init (core.py:903-904; ~38 sem_best_* checkpoints on the data plane), giving an explicit, principled dial on how far a coarse year may drift from the anchor (a control on label circularity). Never tried; no interp/soup code exists anywhere. Verifier scoping: 3ch RGB (deployed citywide_rgb) line only — 4ch/p2nir conv1 shapes don't interpolate naively; alpha must be selected on independent references (thin for no-NIR years — do not reintroduce circularity through the dial); "near-free" is true for producing weights, but each (year, alpha) point needs a Kam-gated sector inference. Model soups are CONTINGENT: Q38 (do the discarded sweep checkpoints still exist?) is open, and the existing per-year variants differ in labels/data — outside the soups regime.

**Spec.** Local interpolation script (strip `_orig_mod` per core.py:389-395); alpha grid {0.25, 0.5, 0.75} on 2-3 contrasting years; sector inference per point; scored threshold-free + matched call rate vs independent refs. The α=0 endpoint is already being scored (queue_sectors_base2020.yaml copies base-2020 as sem_best_{y}_sectors_v1.pt), so only intermediate alphas are new. Soups only if Q38 finds retained checkpoints, and after agreement measurement.

**Expected honest-metric effect.** If per-year fine-tunes partly overfit projected-label noise, some alpha beats both endpoints on honest metrics — a near-free robustness gain, and a per-year measurement of how much fine-tuning helps vs harms.

**Cost.** Local arithmetic + ~6-9 sector inference passes (canary-tier minutes each).

---

## Tier 2 — deliverable preconditions and second-tier items (M09–M11, M13–M16)

### M09_EPOCH_PAIR_SPECIFICITY — measure the quantity that governs the change product
**[CONFIRMED]**

**Issue.** Specificity on the UNCHANGED class across an epoch pair — the quantity governing any change product — has never been measured. With canopy loss at a few percent of pixels, ~97% specificity makes roughly half of detected change spurious (rare-class trap; worked table verified at litwatch_robustness.md:1593-1609), per-year errors are spatially/temporally correlated (same model, same blind spots, same ground) so naive combination of per-year figures understates change uncertainty by construction (ID 186), and the project's own turnover run already demonstrated the trap on its own data: reference-vs-reference discordance (~11.1%) implies an implausible 5.33%/yr C-CAP loss rate — "not a refinement, a precondition" (:1915-1931). The companion cheapest diagnostic — Q44's negative-control shared-bias test (model + NDVI ref over known-negative surfaces) — is also unrun. The existing flicker instrument covers 2 years, FP side only, on the contaminated Negative_* parcels — partial, not this measurement.

**Spec.** Local scoring over existing per-year sector masks: stable stratum = both references agree at both dates (Q66 design, litwatch_robustness.md:4263-4267 — "no new labels needed"); count model transitions on it → epoch-pair specificity + paired change uncertainty (qc/phase4_qc_turnover.py, with its --zero-is-data fix, is the code pattern). Add Q44 over water/buildings/impervious. Write change-accuracy reporting to the CEOS change protocol (ID 187) with Pontius multi-date metrics (ID 190) to separate flicker from change. Scope note: stable-CANOPY strata exist only for reference-bearing years; non-reference pairs get the stable-non-canopy side only.

**Expected honest-metric effect.** None directly; produces the go/no-go number that determines whether per-crown change claims are shippable at all, and sizes the change-scoring buffer that M05's residual offsets feed.

**Cost.** Local raster scoring, zero GPU, days.

### M10_INTERVAL_STATS_SPINE — ESS diagnostic now; estimator spec before the first real site
**[CONFIRMED (ESS) / design-priority (Turnbull) — no code currently commits the midpoint error; the analysis code does not exist yet]**

**Issue.** The per-crown interval deliverable has no statistical machinery behind it: the conformal/risk-control cluster is entirely unbuilt (grep clean), and the ledger explicitly ordered a cheap, label-free, no-GPU go/no-go — fit a per-year density ratio → compute ESS → if ESS collapses, weighted conformal cannot carry a guarantee — "before any conformal design work" (litwatch_robustness.md:271-274). It was never run. Separately, the interval product is an interval-censored survival problem observed through an imperfect test (recall .51-.78 makes misclassification first-order): naive midpoint/endpoint assignment of loss dates is invalid inference (ID 181). Verifier corrections: the existing machinery is a training-label FILTER (labels.py:219-223), not a loss-date tabulator — the midpoint error lives in analysis code not yet written; the valid_from/valid_to schema already IS interval bounds; open issues are structured sensitivity (Q64 — recall varies .16-.93 by height band, exceeding two-parameter sens/spec) and NPMLE at 222k scale (Q63).

**Spec.** (1) ESS now: per-year low-frequency amplitude summaries (litwatch_robustness.md:409-412) + logistic density-ratio + ESS, numpy/sklearn over the local mirror (CoE years read from the G: mount) — the result routes the cross-year branch: weighted conformal (ID 124) vs Barber non-exchangeable penalty (ID 125). (2) Estimator spec doc before any real site exercises the interval machinery: Turnbull-style NPMLE with sensitivity/specificity in the likelihood (Pires/Deng as candidate form, Q63/Q64 flagged), consuming the per-year sens/spec that qc_indep_report.csv already carries; add an explicit per-crown interval right-bound (first-absent epoch) field. (3) Crown-level conformal risk control (bounded FNR — the under-prediction complaint restated as a guarantee) once in-year calibration points exist (M02/M11).

**Expected honest-metric effect.** None now; prevents shipping 222,435 intervals with no coverage statement or invalid loss-date inference. The moment before first use is the cheapest possible adoption point — after it, this becomes rework.

**Cost.** ESS ~1 day local; spec is writing; zero GPU.

### M11_PER_YEAR_LABEL_BUDGET — spend ~1,000 uncertainty-ranked human decisions on one hard year
**[CONFIRMED — with cost corrections: not "minutes of compute"; small new wiring needed; no-NIR year preferred]**

**Issue.** The pipeline literally named "Temporal Active Learning" has never spent a per-year hand-label budget: every queue job trains on labels borrowed from the 2020 citywide mask (`--force-citywide`, phase4_train_queue.py:131-140), because the 14,476-crown review was never finished and polygons/ was overwritten with accept-all test data (CLAUDE.md Gotchas). The ledger's central diagnosed failure mode is the 2020 mask teaching its own blind spot (:374-379). Literature: ~1,000 targeted labels recovered recall 72→84% in a detection fine-tune (Weinstein ID 50; Burmeister's manual≈automatic parity carried as the honest counter-nuance — which is why the budget's unique value concentrates in NO-NIR years, where no automatic NDVI+CHM path exists). Verifier corrections: the phase1b uncertainty queue is Phase-1 crown-classifier machinery — a small new ranking step is needed; the review tool is wired for year 2000 only (schema forward-compatible); absent decisions become out-of-interval negatives under rule 8, not ADD-ONLY edits; the fine-tune is a Colab A100 job, not minutes.

**Spec.** Rank crowns by per-crown mean of the year's prob raster within the 0.25-0.75 band (small local script — the "highest information gain per label" recipe from phase1b_sampling.py transplanted to phase4 outputs); human-review the top ~1,000 in phase4_label_review.py; fold via the review's decision→label contract (present/absent intervals; unsure→IGNORE); fine-tune; sector-score vs independent refs at matched call rate. Year choice: one hard NO-NIR year, gated on M02's Q7/2000-feasibility block (can a human interpret 60 cm no-NIR imagery at all?).

**Expected honest-metric effect.** The cheapest direct test of whether the borrowed-label ceiling is real. If Weinstein-scale transfer holds, treated-year honest recall moves at ~1k labels; a null is equally valuable — it bounds what labels can fix and redirects budget to M06/M07 mechanisms.

**Cost.** Wiring small (tools exist); human 1-2 days per treated year; one canary + one A100 fine-tune + sector inference.

### M13_LEDGER_REBASELINE — re-open the questions the 36-entry catalog invalidated
**[CONFIRMED — high (premise invalidation) / WEAKENED — medium (Q83 half: "re-test", not "invalidated")]**

**Issue.** The ledger's imagery premises are dead under the post-campaign catalog: "13 RGB vs 4 RGBI" (litwatch_robustness.md:437), "there is no leaf-on fine-resolution acquisition in the whole 18" (:2171-2179 — falsified by held 2018s: Aug-07 leaf-on, 15.24 cm, real NIR), Q86/Q88 closed as "archive cannot settle it" (:4027-4047) on premises that no longer hold (Q88's premise year "2022n" never existed — the CSV row reads "2023n (was mislabelled 2022n)"), and the Search 54 pair table + Q91 matched-pair list enumerate a catalog half the real size (:1854-1869, :4068-4071). Separately, Q83's verdict that no existing reference can establish the SIGN of canopy change rested on two NIR years; ten NIR acquisitions now give genuinely season+product-matched pairs. Verifier caveats: the season×GSD×NIR matrix already EXISTS — qc/imagery_pixelsize_and_date.csv is the declared one-home; link it, don't rebuild (one-fact-one-home); re-opened Q86 upgrades from season-vs-GSD-confounded to season-vs-PRODUCT-confounded (no leaf-off NIR exists), not to clean; and Q83's other two defects — the static ~2016 CHM (identical height gate at both dates → change signal is pure greenness; post-2016 growth systematically undercounted) and the 66.7% coverage skew — survive any rebuild, so Q83 may well stand.

**Spec.** Successor-ledger entries pointing at the CSV; re-run the staircase/phenology instruments on the new acquisitions (one command each); regenerate the Search-54 weak-supervision pair table and Q91 list from the 36 entries; re-test Q83's sign question on the matched NAIP pairs (2015n↔2017n both Aug; 2019n↔2023n both Oct) via qc/phase4_qc_turnover.py — **before M02's campaign is sized on Q83's pessimism**. Wiring: the NIR_CATALOG dicts hold only 4 of 10 entries (phase4_build_corrected_labels.py:99-104; qc/phase4_qc_ndvi.py:87-91) — 6 entries to add. Note: extending the NDVI+CHM reference for EVAL is distinct from extending corrected TRAINING labels (parked, below); the never-score-against-the-training-reference rule stays.

**Expected honest-metric effect.** No metric moves; the question inventory gets re-based on the real archive, and the P3 sizing decision (M02) gets made on live rather than dead premises.

**Cost.** Local, days, no GPU.

### M14_RECALL_LOSS_PASS — search the loss-design gap; one bundled A/B
**[WEAKENED — moderate: the engine has an active loss history the audit's framing missed]**

**Issue.** The never-searched literature gap is real — zero of 60 searches cover loss design; no Tversky/asymmetric/boundary-loss row among 210 — but "omission never treated as a training-objective problem" is false at engine level: BCE pos_weight for class imbalance was tried and deliberately retired in v039 for calibration drift, with in-code citations (config.py:188-229); a focal mode is implemented but apparently never run (core.py:486-508; cli.py:243-246 `--loss-mode`; note FOCAL_ALPHA=0.25 currently emphasises the BACKGROUND class — the precision direction, opposite the recall need); and a prior audit already named the deferred fix "mask the Dice term to target-present tiles" for under-prediction on the ~29%-empty pool (config.py:226-228). NEGATIVE_SAMPLE_RATE=0.15 (config.py:101) carries no citation or tuning history. Bounding fact: a loss reweights errors along a fixed discrimination frontier — it cannot add the missing NIR information, and per-year thresholds already move operating points at inference; expect operating-point-like movement, not new discrimination.

**Spec.** Hours of search (recall-weighted/asymmetric segmentation losses, imbalance training); then ONE bundled A/B: the deferred Dice-empty-tile mask + a Tversky mode (~20 lines in `_seg_loss`, dispatcher and CLI already exist) on sectors at matched call rate; examine NEGATIVE_SAMPLE_RATE in the same pass. Loss-only changes reuse existing tiles (cli.py:246) — no retile.

**Expected honest-metric effect.** Bounded: plausibly shifts the recall/precision balance toward the under-predicted class at fixed discrimination; the honest judge is recall at matched call rate vs independent refs.

**Cost.** Search hours; one A100 pair + sector inference.

### M15_OVERIMPERVIOUS_RESIDUAL — external benchmark + post-classification overhang trial (shadow is closed)
**[WEAKENED — medium: the two-mechanism question was answered five days before the audit; shadow LOST]**

**Issue.** The canopy-over-impervious recall gap is real and large (0.32 vs 0.69 in 2016; 0.37-0.43 every year tested; litwatch_robustness.md:3084-3094), but the audit's centerpiece — separate shadow from crown-roof contrast — was already run: Q122's building-relative bearing analysis shows the NORTH (shadow) side scores BETTER (+0.035-0.067), the deficit is sun-isotropic → structural, not illumination (:3222-3272). What survives: (a) Yoo 2026's open-weights NAIP canopy model as a genuine external held-out benchmark — the inventory holds FIVE NAIP acquisitions (2015n/2017n/2019n/2021n/2023n), more than the audit knew; caveats: it is also a U-Net (same failure family), and two of the five are October; (b) the Techapinyawat post-classification overhang-recovery step — untried, local vector/raster work with footprints+CHM already exercised by litwatch instruments; bounded by the ~2016/60% CHM; and it MUST be scored at matched operating points (the Q119 lesson: the corrected model's apparent overhang gain was an operating-point move) with C-CAP treated as partially circular for this class (it folds impervious-under-canopy into canopy by design).

**Spec.** (a) Download Yoo weights, run on the NAIP acquisitions over sectors (canary tier), compare recall structure — a held-out external check on the whole pipeline. (b) Implement the overhang post-classification step locally; evaluate at matched call rate on the over-impervious stratum specifically.

**Expected honest-metric effect.** (a) is a credibility instrument (does an independent model show the same structure?); (b) is the only cheap remaining lever on the largest single stratified deficit — if it moves over-impervious recall at matched call rate, it lands without any retraining.

**Cost.** (a) weights + sector inference, canary GPU; (b) local vector processing, no training.

### M16_AUX_HEIGHT_DECISIVE — run the registry's own named decisive arm for the height candidate
**[carried from the minors; the height half of the it.69 "height or NIR" shortlist]**

**Issue/spec.** The aux-height mechanism is proven weakly, and the run registry itself names the decisive arm as pending: pretrain the height head on the 7.5 cm 2020 anchor, then the 2016 fine-tune, vs the v046 result. One queued A100 run on sectors closes a question the registry left explicitly open, and pairs with M06 as the two surviving structural candidates for the under-prediction.

**Expected effect/cost.** Same honest-scoring frame as M06; one canary + one A100 fine-tune + sector inference.

---

## Parked / long-track (do not spend yet; revisit when the near-free tiers are exhausted)

- **Learned change detection** (STAR/ChangeStar2 single-temporal supervision; Bou weak temporal supervision over the 17 unlabelled acquisitions) — **[CONFIRMED as the right long-track architectural bet]**. Input shape matches exactly (1 labelled year + 17 unlabelled of the same city); cross-sensor same-year pairs are the training signal, not a bug. Retrain-required new architecture, A100-tier; and a direct change output cannot be scored until M02/M09 land (Q66/Q81: both references sit at ~11% discordance noise floors and disagree on the sign). Place in the ID 192 taxonomy first.
- **Corrected-label extension beyond 2016** — **[WEAKENED — low-to-medium; GATED]** on the open 2016c deploy decision (both-agree F1 .853→.937 but grass-FP roughly doubled and the model adopted the reference's definition; the headline overhang gain vanished at matched operating point, Q119). If pursued: ONE CHM-credible-window year (2015n or 2017n/2017s per CHM_CREDIBLE_YEARS, config.py:286) — never 2021s/2023n, where the stale-2016 CHM turns removed-tree grass into confident false ADDs that ADD-ONLY semantics do not guard against. Also widens the correlated-reference exposure until M02's fourth source lands.
- **In-archive SSL pretraining (Q16)** — best-evidenced modelling route (SatDINO-style, GSD-conditioned, era-held-out eval — the only version that tests the property the RGB model measurably lacks). The pretrain itself is the real cost; fund consciously, after M04's rule exists.
- **SAM2/lidar pseudo-label pilot for the instance lane** — **[WEAKENED — low-to-medium]**: run the Q53 pilot (CHM+SAM2 pseudo-labels on 2017 CoE, near-contemporaneous with the CHM, vs phase0 crowns) BEFORE demoting hand-drawn 2020 crowns to eval-only; U3/U5 gates deliberately open; 1 m U8 ~2016 CHM is weakest exactly on the small ornamental crowns the annotation plan targets.
- **RHM augmentation arm** — **[WEAKENED — medium]**: cheapest of the style family and the anti-generative verdict stands, but each arm is a Kam-gated A100 retrain, the headline deficit is measured immune to radiometric fixes (it.69), the claimed target metric (separability sd 0.057) cannot respond to a train-time augmentation by construction, and the planned 2017 test bed is dead (see Rejected #1). If ever run: one arm, after M04, on the genuine 2017 snoh-vs-naip pair, success = King-output-converges-toward-CoE-style criterion on model outputs.
- **Agreement-on-the-line amenability probe** — **[WEAKENED — low]**: exploratory only; no dense-prediction demonstration exists (Q35), and the nine per-year models share a teacher, so correlated errors bias the estimate optimistic (Search 38). A negative is informative; never the selection rule.
- **IR-MAD/PIF distortion diagnostic** — **[WEAKENED — low-to-moderate]**: legitimate ONLY as an affine-vs-nonaffine distortion diagnostic on the same-year pairs and as a cross-year THRESHOLD-comparability aid (deployed thresholds wander 0.33-0.51); not a model-performance candidate — Q130/Q134 measured that the King-year information is absent, not mis-scaled, and Q135 that the model does not rely on colour.

---

## Explicitly rejected (do not build/spend; cite these when they resurface)

1. **C1 normalization/FDA ladder on the 2017 King-vs-CoE "matched pair"** `[refuted pile — the one formal refutation]`: the pair is the SAME orthomosaic — identity MEASURED 2026-08-23 (r median 0.9923, MAE ~3.5 DN; qc/imagery_pixelsize_and_date.csv rows 12/19; pipeline/imagery_acquisition_manifest.json:1010; IMAGERY_FACTS.md:299). There is no domain gap to close; the pre-stated success criterion is trivially satisfied at baseline. Action: mark C1 dead in IMAGERY_PLAN.md (it predates the identity finding). Legitimate successor, if ever: the genuine same-date cross-sensor pair 2017_snoh_1ft_rgbi vs 2017_naip_1m_rgbi (0.58 m registration) — a different, resolution-confounded (13×) experiment, low priority.
2. **GAN/diffusion style transfer** `[in-tracker demotion: Search 28]`: randomized histogram matching is competitive for overhead imagery without artifacts.
3. **Radiometric normalization as a model-performance fix; shadow/illumination remedies for the over-impervious deficit** `[measured negatives: Q130/Q134/Q135; Q122]`: the King-year deficit is lost information, not mis-scaling; the model does not key on colour; the over-impervious deficit is sun-isotropic.
4. **Off-the-shelf noise-robust losses (GCE, symmetric CE, co-teaching)** `[don't-do from the lit synthesis]`: designed for iid label noise; this project's label noise is structured and correlated (the 2020 mask's blind spots). Spend the same GPU on M06/M08/M16.
5. **Cross-year channel-dropout / shared-backbone / per-year-adapter gymnastics for the RGB-only years** `[cleared by analysis]`: the per-year fine-tune architecture already isolates channel count per year; within-year NIR dropout (M06) is different and stays.
6. **Meta-learning DG family** `[closed-with-reason in-tracker]`: exactly one labelled domain — the worst case for episodic task generation.
7. **SAM-family as the semantic lane; transformer/foundation challengers without the control arm** `[measured negative + small-data caution]`: out-of-the-box SAM loses to tuned CNNs for crowns; on ~150-image datasets pretrained CNNs generalized better than ViT-family. Any challenger must beat the resnet101 incumbent on independent refs on sectors before citywide spend (and only after M04's sweep).
8. **RCA/ConfIC-RCA quality bounds for 2000/2002** `[superseded in-tracker: Q39/Q40, Searches 36-38]`: no remote-sensing demonstration, and the required trusted 2020 reference database would be the model's own mask (a prediction sharing the model's blind spots).
9. **True-ortho regeneration from the held LiDAR** `[infeasible as proposed]`: no raw frames/orientation held; the ~2016 CHM would inject wrong-epoch heights over 60% of the city — precisely where real change occurred. Measure-then-IGNORE (M05/M09) instead.
10. **Replacing nearest-neighbour mask decimation with average+0.5-threshold** `[cleared mechanism — keep as-is]`: nearest is unbiased in expectation for canopy fraction; the "fix" would introduce systematic crown erosion at coarse GSD.
11. **Standalone decoder slimming / dropout ablation** `[cleared — not free]`: decoder weights live in the P3 checkpoint lineage; fold into a forced retrain only, never as its own lineage.
12. **Unguarded HMM/temporal smoothing of the year series** `[hazard, standing design rule]`: suppresses genuine rapid canopy LOSS — the policy-relevant signal — along with flicker. Any consistency term ships only with a with/without deletion-sensitivity report and loss-event canary recall; prefer training-time consistency losses over post-hoc smoothing; frame downstream statistics as epoch pairs, not trajectories.
13. **Agreement-on-the-line as THE model-selection rule** `[superseded in-tracker: Q35→Q40]`: probe only (parked list); the rule names latent-class / independent-reference selection.

---

## Cheap hygiene (local, near-zero cost, land opportunistically — from the minors)

1. **Pontius Q/A decomposition**: two lines in qc/phase4_ref_agreement.py — report quantity vs allocation error per year beside the raw 15-17% inter-reference disagreement.
2. **GCC swap for GRVI** in the phenology/greenness QC index (G/(R+G+B) on bands already loaded — column swap), and run the now-computable Q95 season-vs-radiometry split before any rendering index is used again.
3. **Per-year probability histograms on sector outputs** — the threshold-drift diagnostic that interprets M07 (calibration vs class-balance).
4. **gdaladdo -ro external overviews** on the 11 legacy rasters (65.4 GB), local mirror first — QC/visualization win only; write "zero inference speedup" into any plan doc that mentions it.
5. **Writer-path perf on new prob rasters**: `tiled=True, blockxsize/ysize=256, NUM_THREADS=ALL_CPUS` in prob_profile; pinned staging buffer for host-to-device copies; optional single writer thread. `channels_last` (+ torch.compile with dynamic=False) behind a flag, sector-canaried — the ~20% main-thread GPU idle is real but never a correctness issue.
6. **Data-quality one-shots**: histogram checks for the 2007 degenerate prob raster (Q133), 2009 near-zero-red (Q94), 2024 5× radiometric outlier (Q20); assert band counts whenever the 36-entry catalog regenerates (the Q127 single-band `*_king_rgb.tif` naming trap); run Q129 (which outward-quoted results used cross-year GRVI) before anything ships externally.
7. **Footprint canonicalization**: make ccap_2016_edmonds.tif canonical for area statistics (accuracy stats proven footprint-robust); download the county-wide C-CAP 2021 (Q104); add a footprint/variant column to every outward figure.
8. **Catalog the 1936/1998 King frames** with an explicit out-of-scope flag (or consciously scope a 6th-decade extension with Mboga/Kostrzewa-level expectations) — no uncataloged imagery sitting ambiguous.
9. **Season/leaf-off flag columns** in qc_indep and the per-year series, from the date table (the one home); leaf-off years ship flagged. (The anchor-phenology PRR pin stays an open tracked action — but the anchor-explains-under-prediction framing is dead: withdrawn on four independent grounds, it.48-54.)
10. **Effective-GSD slanted-edge measurement** per acquisition; re-derive tiers only where a tier actually flips; canary before any retile (tier flips change label source + sampling recipe).
11. **CHM-footprint × sectors_v1 overlap** computed once; every CHM-gated A/B (M06/M08, corrected-label arms) reports covered/uncovered strata separately.
12. **Record the 2016_fx corrected-lineage fork decision**: either schedule a companion 2016_fx_corrected job or write down that the corrected lineage ended with the clip-era model and why — no silent dead-ends.
13. **Texture-bias channel ablation (IDs 207/208)** before any design decision is justified by texture bias; ID 209's shape-bias regularization is conditional on its outcome.
14. **Written canopy definition (Q1/U1)** — strictly Kam's decision, listed because every P3 point implicitly encodes it: it gates M02's interpretation start, and both closure threads independently ended on it.
15. **Fix CLAUDE.md rule 5's stale wording**: it still names the NDVI+CHM reference as "the independent number" for NIR years — stale for any model trained on NDVI-derived overlays (the corrected-2016 lineage, any M06 arm with `--add-canopy-mask`). Add the qualifier "independent unless the model trained on labels derived from it — then C-CAP/photo-interp is the headline referee." The reporting practice already follows this (the corrected model's primary row is C-CAP-scored); the doc should too.
16. **Tile-seam blending + flip-TTA**: never-searched inference-time gap — TILE_SIZE 512 with INFER_STRIDE 256 implies 50% overlap whose blending scheme (flat averaging vs feathered/Gaussian windows) shapes boundary artefacts that masquerade as year-to-year flicker. Brief search + one sector A/B, judged on flicker metrics specifically (it touches M09's change product, not just aesthetics).
17. **Re-run qc/phase4_qc_height_curve.py once against the 8b from-points CHM** when it is built — the CHM in use reads systematically low, and whether the 5-15 m miss concentration and band boundaries survive a corrected CHM calibrates M08's stratum design.

---

## Sequencing couplings (explicit, so they are not missed)

- **M01–M05 are parallel local work**; nothing gates them on each other except M03 consuming M02's points.
- **M13's Q83 re-test runs before M02 is SIZED, not before M02 is wired** — it changes how big the interpretation campaign must be (is P3 the primary sign-of-change instrument or a validator?), not whether to build it.
- **M02's Q7/2000-feasibility amendment gates M11's year choice** — the budget prefers a no-NIR year, but only if a human can interpret 60 cm no-NIR imagery at all.
- **M04's rule is written before any M06–M08 winner is NAMED**; same-recipe A/Bs may run meanwhile (the verifier's scoping), but no verdict ships without the rule and the M01 matched-operating-point scoring.
- **GPU wave 1** = M07 (minutes) + M06 (one evening) — the two surviving structural candidates get their cheap tests first; M16 rides the same protocol; M08 is wave 2 (retile + canary); M12 opportunistic; M14 bundled when a loss A/B slot opens.
- Every launch: ask Kam first (P11.5) — queue file, tier, runtimes, wall-clock, cost.
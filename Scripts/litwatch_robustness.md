# Lit-watch — Robust Modelling Across Historical + Present Imagery

**Opened:** 2026-08-18 · **Driver:** `/loop` every 10 min (cron `*/10 * * * *`, session-only,
job `19154a11`, auto-expires after 7 days).
**Standing task:** deep-dive for new information on ML with historical and present imagery;
build toward a robust model; **figure out what we don't know**.

**Why this file exists.** A 10-minute loop repeats itself unless coverage is recorded.
Each iteration: (1) read the QUEUE, take the top uncovered angle, (2) search it, (3) add
genuinely new papers to `Literature_Tracker.xlsx` as Phase 5, (4) move the angle to
COVERED with a one-line finding, (5) add anything newly-revealed to OPEN QUESTIONS and
re-rank the QUEUE. Do **not** re-run a COVERED angle unless a specific new lead demands it.

**Inclusion bar** (inherited from Phase 4): include a paper only if it would change a
decision — what to train on, how to span sensors/eras, or how to measure the result.
Peer-reviewed preferred; preprints allowed here (the field moves fast) but must be
flagged PREPRINT in the Relevance field and never cited as evidence.

**Every DOI verified** against the Crossref API or a direct search hit. Never from memory.

---

## Project constraints any recommendation must satisfy

- 18 acquisitions, 2000–2024, 7.5–60 cm GSD, three sensors (King County, Snohomish, NAIP).
- Hand labels exist for **one year only** (2020). Every other year is taught from a model
  prediction — `phase3/edmonds_canopy_mask_2020.tif`.
- Training is **Colab-only** (torch). Local box is a Quadro T2000 4 GB — QC and raster work
  only, never training. Any recommendation costing a large pretrain is out of budget unless
  it can start from public weights.
- **King 2000/2002 is a hard floor**: no labelled post-contractor-change sibling, no NIR,
  C-CAP starts 2016, CHM is stale. Un-trainable *and* un-measurable from 2020 labels.
- Honest-measurement rule: no circular metrics. Anything that *invents* signal
  (colorization, super-resolution, style transfer) needs an in-year Olofsson check before
  it can support a published number.

---

## COVERED

### Search 15 — cross-sensor / cross-era domain generalization · 2026-08-18 · IDs 106–111
**Finding that changes something:** the field has moved from *normalize the inputs* to
*use an encoder that never cared*. Luo 2025 (ID 107, ISPRS, peer-reviewed) shows vision-
foundation-model fine-tuning beats train-from-scratch-plus-augmentation on unseen domains —
which is a direct, testable alternative to our unbuilt radiometric-normalization workstream
(open item 3), not a complement to it.

**The number that should worry us:** Liu 2026 (ID 106) reports that NAIP imagery from the
**same year** shows pronounced domain discrepancies across regions. Our consensus finding (a)
treats the King-contractor change as the discontinuity; this says within-sensor, within-year
drift is already material. Our sensor-era anchor design may be too coarse.

**A route for the hard floor we had not considered:** Simou 2026 (ID 109) bridges 1920→2024
by *colorizing* panchromatic imagery then segmenting few-shot. Structurally our 2000/2002
problem with a harder input. Flagged: colorization invents plausible colour — exactly the
hallucinated evidence our honest-measurement rule exists to exclude.

**A cheap diagnostic this suggests:** Shen 2026 (ID 110) fine-tunes in the frequency domain
because sensor/contractor differences are texture and compression signatures. Before any
retrain we could compare per-year power spectra across the 18 acquisitions and see whether
the eras separate in frequency space. Local, no GPU, no labels.

### Search 16 — test-time / source-free adaptation · 2026-08-18 · IDs 112–115
**The finding, and it is a red flag on our own plan.** STATE open item 3 lists "test-time BN
across years" as unbuilt work we intend to do. Two things say do it carefully or not at all:

1. **The objective is pointed the wrong way for our failure mode.** TENT (ID 112) adapts by
   minimizing prediction *entropy* — it optimizes for confidence. Our documented failure is
   **near-threshold misses**: on 2013, 91% of missed forest sits between prob 0.12 and the
   operating threshold. Entropy minimization pushes exactly those pixels *away* from the
   boundary, hardening the existing bias instead of correcting it. This is inference-time
   confirmation bias — the same mechanism as Arazo 2020 (ID 89), which we already accepted
   as the explanation for finding 4.
2. **Our deployment matches all three of SAR's documented failure conditions** (ID 113):
   mixed distribution shifts (three sensors + contractor changes), small batch size
   (`--infer-batch` default 32), and online imbalanced label distribution (canopy is
   spatially clustered, so a batch can be pure forest or pure water). Niu 2023 reports TTA
   can fail to improve *or actively harm* under these. With no per-year labels, we would
   have no instrument to catch the harm.

**A design choice we would have got wrong by default:** CoTTA (ID 114) shows that chaining
adaptation across a *sequence* of domains accumulates error and forgets. Adapting year-by-year
across 18 acquisitions in temporal order is exactly that shape, and cumulative drift would
corrupt the very temporal signal the per-crown validity intervals depend on. Reset to source
weights per year; do not chain.

**Interaction with a fix we already adopted:** v039 set `FREEZE_ENCODER_BN=True` by default
because BN drift was the prime suspect for the E6 cliff. Every BN-statistic TTA method
(AdaBN, TENT) requires the opposite. These two cannot both be right — resolving that conflict
is a prerequisite to any TTA experiment, not a detail.

**Expected effect size:** Wang 2025 (ID 115) is the peer-reviewed geospatial benchmark of
AdaBN / TENT / DIGA / ROID under location, platform, modality and *time* shifts. Use it for
realistic magnitudes instead of the ImageNet-corruption numbers the method papers quote.
Caveat: point cloud, not aerial imagery — ranking indicative, magnitudes unverified for us.

### Search 17 — calibration & uncertainty under domain shift · 2026-08-18 · IDs 116-119
**THE REFRAME OF THIS ITERATION — the human sample is worth more as a CALIBRATION set than
as an arbiter.** The 2026-08-18 assessment showed 250 points/year cannot settle the
C-CAP-vs-NDVI dispute (+/-5.9 pp, CI covers both) and pins per-band recall only to
+/-10.7 pp. But conformal prediction (ID 119) needs only a modest calibration set, and its
finite-sample guarantee is *distribution-free*: with n calibration points, realized coverage
sits in [1-a, 1-a + 1/(n+1)].

| n | conformal coverage slack | same n, arbitrating the references | same n, per-band recall |
|---|---|---|---|
| 100 | 0.99% | far too wide | +/-17 pp |
| 250 | **0.40%** | **fails - CI covers both refs** | +/-10.7 pp |
| 500 | 0.20% | just separates | +/-7.6 pp |

Same budget, completely different power - because coverage is a distribution-free guarantee,
not a variance-limited estimate. **The deliverable is per-crown temporal VALIDITY INTERVALS.
That is a coverage problem, not an accuracy problem.** We have been sizing the human sample
for the wrong statistic.

**The constraint that decides the design:** conformal assumes exchangeability. Our years are
emphatically not exchangeable with each other, so conformal must be calibrated WITHIN a year -
which converts "250 points x 3 years" from a thin compromise into exactly the right shape,
provided each year gets its own calibration set.

**And the warning that kills the cheap version:** Ovadia 2019 (ID 117) is the canonical result
that confidence degrades under dataset shift and post-hoc temperature scaling fitted on
in-distribution data does NOT transfer. So a temperature fitted on 2020 will not fix 2000 -
calibration must be fitted per year on in-year labels, or it inherits precisely the problem the
labels already have. It also finds deep ensembles most robust under shift, a cost we would have
to budget across 18 years.

**Refinement:** our miscalibration is spatially structured, not uniform - suburban/ornamental
ground behaves differently from forest stands (the 8/8 grounding, the ccap_only low-height
mass). Local Temperature Scaling (ID 118) makes the correction a spatially varying field
rather than one scalar, which is likely necessary rather than merely nicer.

**Read first:** Ji & Tang 2025 (ID 116, Earth-Science Reviews) is the head-to-head comparison
of uncertainty estimators for land cover *under domain shift* - written for our situation, and
it should precede any commitment to an uncertainty method for the deliverable.

### Search 18 - object-level conformal & risk control - 2026-08-18 - IDs 120-123
**Q10 ANSWERED: yes, object-level conformal for instance segmentation exists** (ID 123, Lu,
Kluger, Bates & Wang 2026, preprint). It guarantees the probability that at least one
prediction in the set has high IoU with the true instance mask, with set size adapting to
difficulty. Caveat to carry: "at least one prediction is good" is weaker than "this specific
crown is right", so it needs adapting before it supports a per-crown claim.

**THE BIGGEST FINDING OF THE LOOP SO FAR — stop estimating the miss rate; BOUND it.**
Conformal Risk Control (ID 120) generalizes conformal from coverage to controlling any
monotone loss, and names **bounding the false negative rate** as a worked application.
Andeol 2025 (ID 122) instantiates exactly that for detection with a **box-wise recall loss =
the proportion of MISSED objects**, valid at any dataset size and with no assumptions about
model or data distribution.

Restate our headline complaint in those terms:

| | today | with conformal risk control |
|---|---|---|
| what we have | recall .51-.78 vs a proxy reference | a per-year threshold chosen so missed canopy is provably <= alpha |
| what it rests on | C-CAP/NDVI, which disagree 15-17% | an in-year human calibration set |
| what n buys | variance-limited estimate (n=250 -> +/-10.7 pp per stratum) | a guarantee valid at ANY n |
| the unmeasurable years | 2000/2002 are a hard floor | still hard, but the floor becomes a stated bound rather than silence |

**This is the missing link between the three workstreams.** The near-threshold miss profile
(most cross-sensor misses sit just below threshold) says threshold choice is the lever. The
Phase 4 power table says our sample is too small to *estimate* per-band recall. CRC says we do
not need to estimate it - we need to *control* it, and control is available at any n. The
deliverable is per-crown validity intervals; risk control is how you earn the word "validity".

**Published vs preprint - important here.** Only Mossina & Friedrich (ID 121, MICCAI 2025) is
peer-reviewed. It conformalizes morphological DILATION iterations and outputs a mask envelope
rather than a probability, which is structurally close to a per-crown interval. Treat it as
the citable baseline; treat IDs 120/122/123 as design references until they have venues.

### Search 19 - conformal beyond exchangeability - 2026-08-18 - IDs 124-125
**Q12 ANSWERED, and the answer keeps the Search 18 plan alive.** Both results are canonical
and one is peer-reviewed in the Annals of Statistics.

**The usable mechanism (ID 124, Tibshirani et al. 2019).** Weighted conformal handles the case
where train and test COVARIATE distributions differ, by reweighting calibration scores by the
likelihood ratio between them - and the paper states that ratio can be estimated from a large
set of **unlabelled test covariates**. Read our situation against that requirement:

| weighted conformal needs | we have |
|---|---|
| labels in a source domain | 2020 hand labels |
| a large set of UNLABELLED target covariates | 18 years of unlabelled imagery, city-wide |
| an estimable likelihood ratio between source and target imagery | a density-ratio / domain-classifier fit per year - no labels needed |

This is the mechanism that could carry a guarantee from a labelled year to an unlabelled one.
It is the single most directly usable result found in this loop.

**The bound for the hard floor (ID 125, Barber et al. 2023).** In the fully non-exchangeable
case, coverage still holds but degrades by an **explicit, computable term** measuring how far
the data departs from exchangeability. That converts King 2000/2002 from "unmeasurable" - the
current STATE wording - into "measurable with a stated coverage penalty". We could publish a
bound and say honestly how much the temporal gap weakens it, instead of shipping
LOW-CONFIDENCE with no number attached.

**Where this leaves the three-iteration arc.** Search 17 said calibrate per year. Search 18
said control the miss rate rather than estimate it. Search 19 says the guarantee can cross
years, at a quantified cost. Together that is a coherent alternative spine for the deliverable:
*per-crown validity intervals with a stated, provable miss-rate bound, weighted across years by
an unlabelled-data density ratio, with an explicit coverage penalty on the pre-2016 imagery.*

**Do not oversell it.** Two load-bearing checks are unresolved: whether the likelihood ratio is
estimable at our GSD range (Q14 below), and the sharpness cost at small n (Q11, still open).
Coverage is free; useful width is not.

### Search 20 - density-ratio estimability in high dimensions - 2026-08-18 - IDs 126-128
**Q14 ANSWERED, and the answer is mostly NO - this is the first iteration that constrains
rather than expands the plan.** Weighted conformal (ID 124) is only as good as its
likelihood-ratio estimate, and three results say that estimate is exactly what breaks:

- **Importance weighting degrades on high-dimensional data with deep models** (ID 127,
  Fang et al. NeurIPS 2020) - it works for low-dimensional, linear settings, and a naive
  domain-classifier ratio tends to saturate.
- **Density-ratio estimators have high variance when the two densities barely overlap**, which
  is the worst case and is precisely ours: different sensors, a contractor change, and some
  years without NIR at all. Low overlap is not an edge case here, it is the design.
- **Classifier-based weighting specifically fails on spatially clustered data** (ID 128,
  Serov et al. 2026, Scientific Reports) because it inherits instability from imperfect
  separation and non-overlapping samples. Canopy is spatially clustered.

**But it converts a judgement call into a computable test.** Maia Polo & Vicente 2022 (ID 126)
identify **effective sample size (ESS) after reweighting** as the quantity that decides whether
importance weighting works at all. So the go/no-go is mechanical:

> fit a per-year density ratio -> compute ESS -> if ESS collapses, weighted conformal cannot
> carry a guarantee to that year, and we fall back to Barber 2023's assumption-free penalty.

Cheap, local, no labels, no GPU. **It should be run before any conformal design work**, because
it decides which of the two Search 19 mechanisms we are actually entitled to use.

**The escape route if ESS collapses:** kernel mean matching (ID 128) matches distribution means
in a feature space rather than estimating a pointwise ratio, skipping the high-variance step
that breaks in high dimensions - and it is validated on spatial data, not benchmark tabular
shifts. That makes it the most plausible practical route to the reweighting Search 19 needs.

**Net effect on the spine.** The three-iteration arc (17 -> 18 -> 19) still stands, but the
weighted-conformal branch now carries a real feasibility risk. Ranking of what to rely on:
1. Per-year in-year calibration (Search 17) - no cross-year assumption, safest.
2. Risk control on the miss rate (Search 18) - valid at any n, within a year.
3. Barber 2023 penalty (ID 125) - assumption-free, weaker, works everywhere.
4. Weighted conformal (ID 124) - strongest IF the ratio is estimable. Gate on the ESS test.

### Search 21 - calibration-set size: coverage variability vs sharpness - 2026-08-18 - IDs 129-130
**CORRECTION TO ITERATION 3 - carry this one forward, it changes a number we already quoted.**
Search 17 reported "conformal slack at n=250 is 0.40%", from 1/(n+1). That is true but it is
the **marginal** guarantee - coverage averaged over hypothetical calibration draws. We will
collect ONE calibration set, and conditional on it, coverage is a random quantity distributed
Beta(n+1-l, l), l = floor((n+1)*alpha) (Vovk 2013, ID 129). The realized numbers:

**Realized coverage, conditional on the calibration draw, target 90%:**

| n | mean | 5th pct | 95th pct | spread |
|---|---|---|---|---|
| 50 | .902 | .826 | .960 | .134 |
| 100 | .901 | .848 | .945 | .097 |
| **250** | .900 | **.868** | **.930** | **.062** |
| 500 | .900 | .877 | .921 | .044 |
| 1000 | .900 | .884 | .915 | .031 |

At **target 95%**, n=250 gives .928-.972.

**Read:** at 250 points per year, promising 90% coverage means actually delivering somewhere
in 87-93%. That is honest and probably acceptable for a canopy product - but it must be STATED,
not quietly assumed to be 90%. At n=1000 the band tightens to 88.4-91.5%, which is exactly why
Angelopoulos & Bates (ID 130) recommend ~1000: the recommendation is about **variability**, not
about validity. That reconciles the two contradictory pieces of guidance in the literature -
"valid at any n" and "you need 1000" are both true and are about different things.

**Net for the design:** 250/year is defensible for coverage, with a stated +/-3 pp band. It is
NOT enough to arbitrate the references (Search 17: +/-5.9 pp, CI covers both) and NOT enough
for per-band recall (+/-10.7 pp). The sample's best use remains calibration - the ranking from
Search 20 stands - but we should quote the Beta band, not the 1/(n+1) figure.

**Still genuinely open:** SHARPNESS. Everything above concerns coverage. Nothing found yet
quantifies how WIDE the per-crown intervals become at n~250 for a segmentation-like output -
and a guarantee that returns "this crown existed sometime between 2000 and 2024" is valid and
useless. Q11 is therefore only half answered.

### Search 22 - does SSL/foundation pretraining actually help segmentation? - 2026-08-18 - IDs 131-133
**This iteration TEMPERS iteration 1 and answers Q15. Read the two together.**

**The counterweight (ID 131, Sosa et al. 2024, preprint).** Large MAE pretraining helps mainly
when the downstream task RESEMBLES the pretraining objective - reconstruction. For
**segmentation, training from scratch with well-tuned hyperparameters performs comparably or
better**. So it does not follow that a pretrained encoder beats our tuned ResNet-101 U-Net on
in-domain canopy segmentation.

**But this does not cancel Search 15 - it splits the claim in two.** Luo 2025 (ID 107,
peer-reviewed ISPRS) argues the foundation-model advantage on CROSS-DOMAIN generalization;
Sosa measures IN-DOMAIN accuracy. The honest expectation is therefore:

> pretraining buys ROBUSTNESS ACROSS OUR ERAS, not a better 2016 IoU.

That is a testable prediction and, given finding 2 (model strength does not move honest recall),
it is also the only kind of gain that would matter to us.

**Q15 ANSWERED - which feature space?** Romero et al. 2026 (ID 132) find task-relevant
information sits in **intermediate transformer layers, not final embeddings**. So if we need a
feature space for kernel mean matching or a density-ratio estimate (Search 20), take
intermediate-layer activations. They also report that decoder architecture and fine-tuning
strategy matter as much as the backbone choice, and that model rankings CHANGE across tasks and
adaptation settings - meaning any single-benchmark claim about foundation models is weak
evidence, including the ones cited in Search 15.

**If we do pretrain on our own archive (ID 133, SatDINO).** Use DINO-style contrastive rather
than MAE, and condition on GSD explicitly - SatDINO adds GSD encoding and adaptive view
sampling as independent components. Our 7.5-60 cm span is an 8x range that our augmentation
bridges but our ENCODER does not represent; GSD conditioning is cheaper and more targeted than
training per resolution tier.

**PROVENANCE WARNING - all three are preprints.** This sub-literature is preprint-dominated and
moves fast. Nothing here should override the peer-reviewed Luo 2025 or drive a build decision on
its own; treat it as a prior over what to test first.

### Search 23 - learning from one labelled year - 2026-08-18 - IDs 134-135
**Q2 (from iteration 1) is now largely ANSWERED, and the answer is uncomfortable.**
Q2 asked: has anyone published training from ONE labelled year and deploying across two
decades, with honest independent evaluation? The nearest published work is SpADANN
(ID 134, Capliez et al. 2023, JSTARS, peer-reviewed) - and it transfers **one year to the
SUCCESSIVE year**, over the same area, same sensor. Nobody found so far spans 24 years and
three sensors from a single labelled year.

**So our regime is genuinely harder than the published regime.** That is a finding, not a gap
in our reading, and it should change how the work is framed: we are not applying a solved
method, we are past its demonstrated envelope. It also means benchmark numbers from this
literature are upper bounds for us, not expectations.

**And the closest method uses the mechanism we already diagnosed as our problem.** SpADANN's
engine is spatially-aware PSEUDO-LABELLING. That is exactly finding 4 - the 2020 mask teaches
its own blind spot - and exactly what CoTTA (ID 114) warns accumulates error when chained
across a sequence. The transferable idea is the *spatially aware* part (respect spatial
structure when propagating labels); the part to distrust is iterated self-training.

**One genuinely encouraging result (ID 135, Qin et al. 2025, peer-reviewed).** Pretrain on the
unlabelled TIME SERIES ITSELF, then fine-tune with few labels. Unlike the generic
foundation-model papers, the pretraining corpus is the same archive the model is deployed on -
which is our 18 unlabelled years. This is direct evidence for the in-archive pretraining idea
from Search 22, in the limited-label regime, peer-reviewed. **Caveat that may kill the
transfer:** crop mapping has strong seasonal periodicity our canopy series does not have, so
the temporal structure it exploits may simply not exist in our data.

**Where the loop now stands on the modelling side.** Three routes, honestly ranked:
1. **In-archive self-supervised pretraining** (IDs 133, 135) - best evidence, uses an asset we
   already own, and Q16's held-out-era experiment would test it directly.
2. **Spatially aware temporal adaptation** (ID 134) - closest published analogue, but built on
   the mechanism we distrust, and demonstrated only one year ahead.
3. **Foundation-model fine-tuning** (ID 107) - peer-reviewed for cross-domain, but Search 22
   says no in-domain gain, and Romero says rankings are unstable.

### Search 24 - frequency-domain characterization & FDA - 2026-08-18 - ID 136
**The cheapest intervention found in this entire loop.** Fourier Domain Adaptation (ID 136,
Yang & Soatto, CVPR 2020, peer-reviewed) bridges a domain gap by swapping only the
**low-frequency AMPLITUDE spectrum** between source and target images. No training, no labels,
no adversarial stage - an FFT per tile. The principle behind it:

> **amplitude carries STYLE** (texture, colour, contrast) - **phase carries SEMANTIC CONTENT**

That maps precisely onto our consensus finding (a): augmentation spans 8x GSD but not the King
contractor change or the sensor switch. Those are style differences - which is to say, they are
amplitude. FDA is directly testable on 2000 vs 2020 before any retraining, and it is the first
proposal in this loop that costs almost nothing to try.

**It also hands us the feature space we have been looking for.** The per-year low-frequency
amplitude summary IS a sensor-era signature: low-dimensional, label-free, computed from imagery
alone. That is a concrete candidate for the reweighting space that Search 20 said we needed and
Search 22 answered only partially (intermediate encoder layers). Amplitude is cheaper and needs
no trained model.

---

### EMPIRICAL NOTE FROM THIS ITERATION - check `imagery_stats/imagery_summary.txt`

While looking for a place to compute the per-year signature, the existing catalog surfaced a
discrepancy worth Kam's attention. **The catalog lists FOUR acquisition sources, not three:**

| source | images | years |
|---|---|---|
| City of Edmonds | 4 | 2017, **2020**, 2022, 2024 |
| King County | 9 | 2000, 2005, 2007, 2009, 2013, 2015, 2019, 2021, 2023 |
| NAIP | 2 | 2019n, 2022n |
| Snohomish Co. | 2 | 2016, 2021s |

Our standing project description says "three sensors (King County, Snohomish County, NAIP)" and
omits City of Edmonds. That matters because **2020 - the ONE labelled year - is a City of
Edmonds acquisition**, from a source covering only 4 of the 17 images. So every King County
year (9 images, the largest block, including 2000/2013/2015) is taught by a model trained on a
DIFFERENT source's imagery. The cross-source gap is not a later complication; it is present at
the very first transfer, for the majority of the archive.

Also worth noting from the catalog: 13 RGB vs 4 RGBI, three different CRSs (3857 / 2285 /
26910), and 2016 and 2021s cover only 66.7% of the city.

**This should be verified by Kam** - it may simply be that CoE and King County share a
contractor and were treated as one, but if not, the sensor-era anchor design is missing a level.

### EMPIRICAL - Q5/Q18 SCREENED - 2026-08-18 - `phase4_qc_domain_cluster.py`
**Kam, 2026-08-18: "Edmonds and King County use EagleView in the later years, and King County
switched contractors many times. There may be more than a few different sensors."**
Screened against the per-band statistics already in `imagery_stats/imagery_summary.txt` -
free, no imagery opened. Result: **the correction is supported.**

**1. AGENCY IS NOT THE DOMAIN AXIS.** Nearest neighbour by radiometric signature shares agency
for only **8 of 17 acquisitions (47%)** - near chance. Our per-(sensor x era) anchors are keyed
on the wrong variable.

**2. The EagleView signature is visible.** **2017 (City of Edmonds) and 2019 (King County) are
each other's nearest neighbours at distance 0.34** - the closest cross-agency pair in the set,
and closer than most same-agency pairs, despite 7.5 cm vs 14.9 cm GSD. Two different agencies,
near-identical radiometry. That is what a shared contractor looks like.

**3. King County is not one domain.** Its 9 acquisitions split across at least three groups:
2005+2007 (29.9 cm) pair off; 2009 sits with 2021/2023; 2000/2013/2015/2019 land elsewhere.
Consistent with repeated contractor changes.

**4. 2024 IS A SEVERE OUTLIER - flag for Kam.** Nearest-neighbour distance **4.96** (next
largest is 1.09) and a singleton cluster at every cut level. Band means 144/154/146 against a
typical 80-110. Either a genuinely different product or a processing/normalisation difference.
Worth checking before 2024 is used for anything.

**Honest limits.** Band statistics are a weak, confounded proxy for sensor - footprint, season
and sun angle all move them, and 2016/2021s cover 66.7% of the city while the NAIP frames cover
53.8 km2 against 176 km2, so those means are not over the same ground. The 2000 grouping (59.7 cm
sitting with 7.5 cm CoE years) is probably an exposure coincidence, not a sensor match. This is a
SCREEN. The proper instrument is the low-frequency amplitude signature (ID 136); the actual
ground truth is acquisition metadata, which would beat both.

**What it changes.** Stop asserting domain groups from agency labels; discover them. Every
downstream design that keys on "sensor era" - anchors, radiometric normalisation, the reweighting
of Search 20, the held-out-era experiment of Q16 - needs its grouping re-derived. And the
held-out-era test now has a much better design: hold out a radiometric CLUSTER, not an agency.

### Search 25 + INVENTORY AUDIT - 2026-08-18 - ID 137
**Q17 (tuning as the honest baseline) - the literature is blunt.** Brigato et al. 2021 (ID 137)
tuned only learning rate, weight decay and batch size on six datasets including satellite
imagery, and the resulting plain baseline **outperformed all but one specialized data-efficient
method**. Our v030-v048 history is dominated by DEBUGGING - sampler, BN freeze, metric artifacts,
OOM - not tuning. So the cheapest untried gain in the project may be a proper hyperparameter
search on the model we already have, and it sets the bar every fancier proposal must clear:
**beating an under-tuned baseline proves nothing.**

---

### Q19 ANSWERED - NO ACQUISITION METADATA EXISTS IN OUR RASTERS
Probed the TIFF tags on 2000 / 2013 / 2016 / 2017 / 2019 imagery. Every file carries only
`AREA_OR_POINT` plus compression settings (DEFLATE/LZW, PREDICTOR 2). **No camera, no
contractor, no flight date, no sun angle.** These are re-processed derivatives; the original
metadata was stripped or never carried through.

**Consequence:** the ground truth that would have beaten every pixel-based proxy is not in our
files. It would have to be recovered from the source portals (King County GIS, WA state,
USDA/NAIP), which is an external-data errand, not a computation. Until then the amplitude
signature (ID 136) is the best available instrument, and the iteration-11 clustering stands as
the only evidence we have about domain structure.

---

### INVENTORY IS INCONSISTENT - THREE DEFECTS, ALL NEW
Found while chasing the metadata question. None of these were known.

**1. `imagery_stats/imagery_catalog.csv` is INCOMPLETE.** It lists 17 images / 14 years and
**omits 2002 and 2012**, both of which exist on Drive as `2002_king_rgb.tif` and
`2012_king_rgb.tif`. STATE quotes an honest 2002 recall of .5069, so 2002 is actively in use
while being absent from the catalog that describes the stack.

**2. The iteration-11 domain clustering therefore has a HOLE.** It clustered the catalog's 17
acquisitions, so **2002 and 2012 were silently excluded**. The conclusions (agency is not the
domain axis; 2017-CoE pairs with 2019-KC; 2024 is an outlier) are unaffected in direction, but
the King County grouping is incomplete - two of its images were never scored. Re-run once the
catalog is fixed.

**3. CONFLICTING PROVENANCE LABEL FOR 2017.** Drive has `2017_coe_rgb.tif` (matching the
catalog's "City of Edmonds"); the local D: mirror has `2017_king_rgb.tif`. Same year, two
different agency labels, two different filenames. Either one is a renamed copy - in which case
a provenance label is simply wrong somewhere - or they are two different 2017 products and the
pipeline may be reading whichever the resolver finds first. **This is exactly the kind of
mislabelling that makes agency-keyed anchors unsafe**, and it is independent evidence for the
iteration-11 conclusion.

D: also holds 1936, 1998, 2002 and 2012 rasters that the catalog does not mention at all.

**Recommended, in order:** regenerate the catalog over the actual holdings; resolve the 2017
filename conflict; re-run `phase4_qc_domain_cluster.py`; only then rebuild the anchor grouping.

### WHICH IMAGERY DOES THE PIPELINE ACTUALLY USE? - 2026-08-18 (Kam asked)
Traced through the code rather than the catalogs. Three answers, one discovery.

**1. THE AUTHORITY IS `phase2_data_prep.py`, NOT `pipeline_config.py`.**
`phase4seg/config.py:317` says so in a comment: *"18-ENTRY IMAGERY CATALOG (verbatim from
phase2_data_prep.py - the authority)"*. The 18 entries are
2000, 2002, 2005, 2007, 2009, 2013, 2015, 2016, 2017, 2019, 2019n, 2020, 2021, 2021s,
2022, 2022n, 2023, 2024. All 18 files exist on Drive.

**But `pipeline_config.py` self-describes as "Single source of truth for all pipeline paths and
catalog" and holds a DIFFERENT, smaller catalog** - 2013/2015/2019/2021/2023 + 2017/2020/2022/
2024 + the starred supplementals. **It contains no pre-2013 year at all**, and
`raw_path(2000)` would raise `KeyError`. Two files each claim authority and they disagree; the
one that says "single source of truth" is the wrong one. This breaks the one-fact-one-home rule
directly.

**2. RESOLUTION ORDER.** `phase4seg/common.py:92 resolve_native_path()` tries `NATIVE_DIR`
(`Pipeline Imagery/native/`) then `IMAGERY_DIR` (`Pipeline Imagery/`). `native/` is empty, so
every year resolves to `Full_Image/Pipeline Imagery/<native_file>` on Drive. Training and
inference are Colab-only and read Drive exclusively. The LOCAL QC scripts are the opposite -
they prefer `D:\edmonds-pipeline\Imagery` and fall back to Drive.

**3. ORPHANS - on disk, not in the catalog, not used:** `2012_king_rgb.tif` (Drive),
plus `1936_king_rgb.tif`, `1998_king_rgb.tif` and `2017_king_rgb.tif` (D: only).

---

### THE DISCOVERY: THERE ARE TWO DIFFERENT 2017 ACQUISITIONS
`2017_king_rgb.tif` is **not** a renamed copy. Measured:

| file | dims | GSD | bounds |
|---|---|---|---|
| D: `2017_king_rgb.tif` | 74496 x 105984 | 14.93 cm | -13625894.0, 6068450.3, -13614772.4, 6084272.8 |
| Drive `2017_coe_rgb.tif` | 148736 x 211968 | 7.46 cm | -13625894.0, 6068450.3, -13614791.5, 6084272.8 |

Two distinct products, **same year, essentially the same ground** (eastern edge differs by ~19 m),
different source and different GSD. Only the CoE one is in the catalog.

**This is the cleanest natural experiment in the project and nobody has used it.** Every
cross-source comparison we have is confounded by canopy change, season and sun angle because the
years differ. A matched same-year pair removes the temporal confound entirely:

* **Measure the CoE-vs-King County domain gap directly** - the exact quantity the per-(sensor x
  era) anchors are supposed to absorb, and which iteration 11 could only infer from clustering.
* **Test the iteration-11 claim** that 2017-CoE pairs with 2019-King. If CoE and King share
  EagleView in the later years, 2017-King and 2017-CoE should be radiometrically close after
  resolution is matched. If they are far apart, the shared-contractor story starts later than 2017.
* **Test FDA (ID 136) with a ground truth** - swap low-frequency amplitude between the pair and
  check whether the model's output on one converges to its output on the other. On a matched pair
  the only differences are style, so this isolates exactly what FDA claims to fix.
* **Separate GSD from sensor** - downsample the 7.46 cm CoE raster to 14.93 cm and compare. What
  survives is sensor/contractor; what disappears was resolution. That is consensus finding (a)
  turned into a measurement instead of an assertion.

**Caveat:** acquisition DATES within 2017 are unknown (no metadata, per Q19), so season and sun
angle are not guaranteed matched. Check before treating the pair as a controlled comparison.

### Search 26 - paired cross-sensor imagery & canopy-series harmonization - 2026-08-18 - IDs 138-139
Prompted by the iteration-13 discovery that we hold a matched same-year 2017 pair.

**A published analogue for the WHOLE project finally exists (ID 138, Vogeler et al. 2018, RSE,
peer-reviewed).** A 42-year Minnesota forest CANOPY COVER series across multiple Landsat sensor
generations, where inter-sensor harmonization is the central problem rather than a footnote.
Search 23 concluded nobody spans our regime from the ML side; this is the same problem approached
from the remote-sensing side, and it is the precedent we should be measured against. The trade is
inverted: 42 years at coarse resolution there, 24 years at fine resolution here - so their sensor
problem is harder and our spatial problem is harder.

**Independent convergence on the amplitude thread (ID 139, Li et al. 2025).** Cross-sensor
high-resolution land use, and it splits the problem exactly along the axis our 2017 pair can
isolate: **positional encoding for RESOLUTION differences, random AMPLITUDE MIXUP for
SPECTRAL/style inconsistency.** That is the FDA principle (ID 136, amplitude = style) arriving
from a second direction. Three independent lines - iteration 10 (FDA), iteration 13 (the matched
pair), and this - now point at the same design: treat GSD and sensor as two separate axes, and
handle style in the frequency domain. Its dynamic pseudo-labelling stage carries the usual
confirmation-bias risk (ID 89) and should be treated as optional.

**The experimental template for the 2017 pair, from the search itself.** A Landsat sensor-transfer
study measured performance transferring OLI -> ETM+ *in the same area and year*, and reported that
upper-bound models trained and tested on the target sensor consistently beat directly transferred
models - the gap between the two IS the sensor gap. Applied to us:

| run | train on | test on | measures |
|---|---|---|---|
| upper bound | 2017-King | 2017-King | what the model can do on that sensor |
| transfer | 2017-CoE (or 2020) | 2017-King | what we actually get across the source gap |
| resolution control | 2017-CoE downsampled to 14.93 cm | 2017-King | isolates sensor from GSD |
| FDA arm | 2017-CoE, amplitude swapped to King | 2017-King | does frequency-domain style transfer close it |

Same ground, same year: canopy change, phenology and land-use change all cancel. This is the
first design in the loop that could give consensus finding (a) a NUMBER instead of an assertion.

**Caveat repeated:** within-2017 flight dates are unknown (Q19 - no metadata in any raster), so
season and sun angle are not guaranteed matched. Check before calling it controlled.

### Search 27 - batch norm under domain shift - 2026-08-18 - IDs 140-141
**Q9 ANSWERED, and v039 was right - but for a reason we had not articulated.**

The apparent contradiction was: v039 set `FREEZE_ENCODER_BN=True` because BN drift was the prime
suspect for the E6 cliff, while every BN-adaptation method (AdaBN, TENT) requires the opposite.
Both are correct, because **they disagree about WHEN the statistics are estimated, not about
whether BN carries domain information.**

* **Both camps agree BN encodes DOMAIN-SPECIFIC statistics** (ID 140, Li et al. 2018, Pattern
  Recognition, peer-reviewed). That is the shared premise.
* **Freezing is right when statistics would be estimated from small, noisy, off-distribution
  batches** - the standard fine-tuning guidance, and precisely our situation at the E6 cliff
  (citywide coarse pool, batch 32, ~83% background before the v039 sampler fix).
* **AdaBN estimates over the WHOLE target domain, offline** - not per batch. So it never had the
  instability that motivated our freeze. v039 and AdaBN were never really in conflict.

**The design that resolves it (ID 141, Chang et al. CVPR 2019, DSBN):** do not choose. Keep a
**separate BN branch per domain**, all other weights shared. Each branch is estimated over a whole
domain offline, so there is no small-batch instability, and each year gets statistics matched to
its own radiometry.

**And it composes with iteration 11.** One BN branch per **RADIOMETRIC CLUSTER**, not per agency -
because agency predicts the nearest neighbour only 47% of the time. This is the strongest
candidate the loop has produced for replacing the per-(sensor x era) anchor idea with something
the network actually implements rather than something we assert in a config.

**A cheap variant worth knowing:** fine-tuning ONLY the BN affine parameters (scale and shift)
reportedly reaches performance close to full fine-tuning, with faster convergence. Given our
Colab-only training budget and labels for one year, per-year BN-affine-only tuning is about the
cheapest per-domain adaptation available - far cheaper than the full per-year fine-tunes we run now.

**What this does NOT resolve:** whether the E6 cliff would still appear with the v039 sampler fix
in place. The freeze and the sampler fix landed together, so the freeze has never been tested
alone on a healthy sampler. Q9 becomes an experiment, not a reading question.

### Search 28 - single-domain generalization + the Search 5 rematch - 2026-08-18 - IDs 142-144
**OUR REGIME HAS A NAME AND A LITERATURE: SINGLE DOMAIN GENERALIZATION (SDG).**
Iteration 9 concluded that nobody publishes training from one labelled year and deploying across
decades. That was right about the *temporal* framing and wrong about the *general* one. Liang et
al. 2024 (ID 142, TGRS, peer-reviewed) formalizes exactly our constraint: **train on ONE source
domain, deploy to unseen domains, with no target data at training time.** That is 2020-labels-only
across 17 other acquisitions. This is the vocabulary we should have been searching under from
iteration 1, and it partially retracts the iteration-9 conclusion - the regime is studied, just
not with a 24-year temporal axis.

**The Search 5 rematch has a verdict, and simple wins (ID 143, Yaras et al. 2024, JSTARS).**
On OVERHEAD imagery specifically, **randomized histogram matching** - match each training image to
a randomly drawn reference histogram - is competitive with GAN-based style transfer and cleaner,
because the generative route introduces artifacts and blurred patterns. That is a direct caution
against the generative options already in our tracker (StandardGAN ID 30, diffusion ID 37).

**Why this matters more than any other single finding for near-term work:** RHM needs **no new
model, no labels, no GPU budget** - only a change to the augmentation pipeline. It is the cheapest
possible test of consensus finding (a), and the 2017 matched pair (iteration 13) is a ready-made
test bed with the temporal confound removed.

**Third convergence on style-vs-content (ID 144, Wang et al. 2025, IJCV).** A lightweight style
mapper built from statistical style prototypes, separated from a category-level prototypical
contrast for content. That is now FOUR independent lines - FDA (ID 136), amplitude mixup (ID 139),
this, and RHM - all saying: **handle style separately from semantics, and prefer statistical
transfer over generative.**

**Revised ranking of what to try first on the sensor gap:**
1. **Randomized histogram matching** (ID 143) - no new model, testable this week.
2. **FDA amplitude swap** (ID 136) - also training-free, tests the same hypothesis in the
   frequency domain rather than the intensity domain.
3. **SDG with domain randomization + category consistency** (ID 142) - needs a retrain, but it is
   the method built for our exact regime.
4. Generative style transfer (IDs 30, 37) - **demoted**; Yaras 2024 says it costs artifacts for
   no advantage on overhead imagery.

### Search 29 - SDG sweep with the right vocabulary - 2026-08-18 - IDs 145-146
First iteration searched under **domain generalization / SDG** rather than domain adaptation.
Immediately more productive, which is itself the lesson: sixteen iterations were sampling the
wrong shelf.

**FOSMix (ID 145, Iizuka, Xia & Yokoya 2024, TGRS) refines what we were about to do wrong.**
Everything from Search 24, 26 and 28 converged on "mix style in the frequency domain". FOSMix is
the remote-sensing realization - and it adds the constraint we were missing: **keep the
frequencies that carry segmentation signal, randomize only the rest**, plus a consistency
regularizer. That matters concretely for us. A blunt low-frequency amplitude swap (FDA, ID 136)
risks destroying the fine texture that separates a crown from a lawn at 7.5 cm; FOSMix explicitly
preserves the essential frequencies. It names **location, time and sensor** as its target shifts -
our exact triple - and the code is public.

**The map we lacked (ID 146, Rafi et al. 2024, Artificial Intelligence Review, peer-reviewed).**
A survey organizing DG for segmentation into families: augmentation/randomization, feature
normalization and disentanglement, and meta-learning. Use it to audit the loop's coverage for
whole families we have never touched, instead of continuing to sample one method at a time.

**A fifth convergence, now at the ARCHITECTURE level.** The sweep surfaced that **instance
normalization removes style while batch normalization preserves discriminability**, and that
combining them (global-to-local normalization) is a standard SDG move. This connects to
iteration 15: the BN question is not only freeze-vs-adapt, it is which NORMALIZATION to use.
IN+BN hybrids are a third option that neither v039 nor AdaBN considered, and they attack style
without touching the data pipeline.

**The literature independently names our two unsearched axes.** Domain randomization in remote
sensing is described as targeting texture divergence from **phenological periods** and style
divergence from **illumination** - i.e. leaf-on/leaf-off and sun angle, the two queue items
flagged in iteration 14 as never examined. They are recognized primary causes of RS domain shift,
not afterthoughts. That raises their priority and makes Q24 (were the two 2017 flights at similar
dates?) more load-bearing than it looked.

**Consolidated view of the style-vs-content thread, now five lines deep:**
| line | where style is handled | cost |
|---|---|---|
| RHM (ID 143) | intensity histogram | none - augmentation only |
| FDA (ID 136) | low-freq amplitude swap | none - FFT only |
| FOSMix (ID 145) | frequency, selectively | none - augmentation only |
| style mapper (ID 144) | statistical style prototypes | light module |
| IN+BN hybrids | inside the network | architecture change |
Every one of them is cheaper than the generative route we demoted in Search 28.

### Search 30 - PHENOLOGY - 2026-08-18 - IDs 147-148
**This may be an alternative explanation for our headline finding, and it has never been on the
table.**

The canopy-mapping literature is blunt about it: **leaf-off imagery underestimates canopy cover
in deciduous regions**, and seasonality is described as the single biggest source of error in
canopy work where leaf-on/leaf-off contrast is strong. Kokubu et al. 2020 (ID 147) quantifies
urban canopy cover changing with season at city scale.

Now put that next to STATE: **scrub recall .25 vs forest .68 - "fails on non-conifer/mixed
structure (the conifer-only-label blind spot)"**. Conifers hold colour year-round; deciduous do
not. **A shoulder-season or leaf-off acquisition would make any model look conifer-biased even if
it is not.** We have never had acquisition dates (Q19: no metadata in any raster), so this has
been an uncontrolled variable across all 18 acquisitions and all of our cross-year comparisons.

**Free screen run this iteration** - scene-mean greenness excess GRVI = (G-R)/(G+R), computed from
band statistics already in the catalog:

| lowest GRVI | | highest GRVI | |
|---|---|---|---|
| 2023 | 0.0143 | 2019n | 0.1521 |
| 2019 | 0.0224 | 2009 | 0.1187 |
| 2017 | 0.0242 | 2016 | 0.0875 |
| **2020** | **0.0250** | 2000 | 0.0850 |
| 2024 | 0.0322 | | |

**Our one labelled year, 2020, sits fourth-lowest.** If that reflects phenology, the 2020 labels
were drawn on imagery where deciduous canopy was least visible - which would *produce* the
conifer-only blind spot, and every coarse year taught from that mask would inherit it. That is a
mechanistic account of finding 4 we have not previously considered.

**BUT THE SCREEN IS BADLY CONFOUNDED AND MUST NOT BE OVERREAD.** The low-GRVI group
(2017, 2019, 2020, 2023, 2024) is almost exactly the group that clustered together in iteration 11,
and includes the 2017-2019 EagleView pair. Low greenness is equally consistent with a shared
contractor COLOUR BALANCE. A scene-wide mean is also dominated by roads and roofs, not canopy.
Nothing here distinguishes the two explanations.

**The discriminating test, and it is cheap and local.** Compute greenness over KNOWN-CANOPY
pixels only - split by conifer-dominated versus deciduous-dominated ground - instead of scene-wide:
* if **deciduous** areas lose greenness in a given year while **conifer** areas hold it -> PHENOLOGY.
* if **everything** shifts together -> COLOUR BALANCE / sensor.

Inputs all exist: the 2020 mask, C-CAP forest classes, the CHM, and the per-year orthos. No
labels, no GPU. This is now the highest-value cheap experiment the loop has identified, because it
discriminates between two explanations for the project's central finding.

**Framing to adopt either way (ID 148, Kou et al. 2020):** treat seasonal difference as a DOMAIN
SHIFT to be modelled, not as noise. We currently attribute every cross-year difference to canopy
change or model error, with no seasonal term at all.

### Search 31 - SUN ANGLE, ILLUMINATION & SHADOW - 2026-08-18 - IDs 149-150
The other half of the acquisition-conditions problem, and it surfaces an internal inconsistency
in our own pipeline that nobody has flagged.

**Shadow is not a nuisance, it silently corrupts the map.** Lasko et al. 2026 (ID 149, Ecological
Informatics) find that correcting low-sun-angle tree and terrain shadow **reveals land cover
mapping errors that were previously invisible**. In low-sun imagery, shadows extend well beyond
the actual canopy footprint - which is simultaneously a **commission** risk (shadow read as dark
canopy) and an **omission** risk (shadowed crowns too dark to detect). Both directions are live
for us, and neither is measured.

**THE INCONSISTENCY IN OUR OWN PIPELINE.** From STATE: the structure channel is
`struct = clip(hillshade_fr - hillshade_be + 127)`, and hillshade is computed at a **fixed 315
degree sun azimuth**. So:

* the LIDAR-derived channel assumes one fixed illumination geometry, for every year;
* the actual IMAGERY was flown at 17 different, unknown solar geometries;
* the model sees both, stacked, on every tile.

The structure channel therefore carries a *constant* illumination assumption while the RGB
carries a *varying* one. That mismatch has never been examined. It is a plausible contributor to
why the struct channel measured weak (AUC ~0.70) and was eventually superseded by the real CHM -
and if we ever revive hillshade-style inputs, the azimuth should match each acquisition, which we
cannot do without dates.

**Everything again points at the same missing fact.** Sun elevation and azimuth are deterministic
functions of date, time and location. We have the location. Dates would give us the rest for free -
and would simultaneously settle phenology (Q29), the 2017 pair's validity (Q24) and this. **The
single highest-leverage fact this loop has identified is not in any paper: it is the flight dates.**

**If we do handle shadow, weigh two options.** SARU (ID 150, ISPRS, peer-reviewed) is the current
state of the art for joint shadow detection and removal. But removal RECONSTRUCTS pixel values,
which the honest-measurement rule would then have to defend - the same objection raised against
colorization in Search 15. The cheaper and more defensible option for us is to **detect shadow and
mask it to IGNORE**, which fits our existing three-state supervision rule and invents nothing.
Read SARU as the upper bound on what shadow handling can buy before paying for it.

### Search 32 - COVERAGE AUDIT + the corrective that deflates much of this loop - IDs 151-152
Twenty iterations in, first check of what whole FAMILIES we had skipped. Two results, and the
important one argues against a lot of what this loop has been accumulating.

**THE CORRECTIVE (ID 151, Gulrajani & Lopez-Paz, ICLR 2021).** Across seven datasets, nine
algorithms and three model-selection criteria, **carefully implemented empirical risk
minimization matches or beats every domain-generalization algorithm tested.** Their sharper claim
is the one that binds us:

> a DG algorithm **without a stated model-selection strategy should be regarded as INCOMPLETE**,
> because selecting hyperparameters using target-domain data leaks the very thing you claim to
> generalize to.

**That is our unexamined weak point.** We select checkpoints on validation built from PROJECTED
2020 LABELS. That is neither honest in-domain selection nor honest out-of-domain selection - it
is selection against a proxy that carries the same bias as the training signal (finding 4). Every
per-year number we have was produced under a model-selection scheme this paper would call
incomplete.

**Read together with Brigato 2021 (ID 137), two independent canonical results now say the same
thing:** a properly tuned, properly selected plain baseline is the thing to beat, and most
published gains do not survive fair comparison. **This deflates a good part of Searches 15-31.**
The style/frequency methods (RHM, FDA, FOSMix) survive that critique better than most, because
they are augmentation changes rather than new algorithms - but they still have to be measured
against a well-tuned ERM baseline with an honest selection rule, and we do not currently have one.

**THE FAMILY WE CAN NOW CLOSE (ID 152, Khoee et al. 2024, AI Review).** Meta-learning was the one
DG family this loop had never touched. It is a poor fit for us, for structural reasons:
episodic meta-learning is built for FAST ADAPTATION given a few target examples, while DG assumes
ZERO target examples; and with few source domains the task-generation capacity collapses into
overfitting to the training tasks. **We have exactly one labelled domain - the worst case.**
Closing this family with a reason is worth as much as opening a new one.

**Coverage status against the Rafi 2024 taxonomy (ID 146):**
| family | covered? |
|---|---|
| augmentation / domain randomization | YES - Searches 28, 29 (RHM, FOSMix, SDG) |
| feature normalization | YES - Searches 27, 29 (BN/AdaBN/DSBN, IN+BN) |
| style-content disentanglement | PARTLY - Searches 24, 26, 28, 29 |
| meta-learning | CLOSED this iteration, poor fit |
| causal / invariance (IRM, V-REx) | TOUCHED - and IRM reportedly underperforms ERM on DomainBed |
| ensembling / model soups | NEVER TOUCHED |

**What this changes about the loop's own recommendations.** Before running any of the methods
this loop has surfaced, we need (a) a tuned ERM baseline and (b) a written, honest model-selection
rule that does not use the target year. Without both, any measured "gain" is uninterpretable -
the same trap our honest-measurement workstream exists to avoid, arriving from the modelling side.

### Search 33 - MODEL SELECTION & UNSUPERVISED ACCURACY ESTIMATION - IDs 153-154
Search 32 left us gated on one question: what is an honest selection rule when we cannot use the
target year? This iteration finds something better than a selection rule.

**AGREEMENT-ON-THE-LINE (ID 153, Baek et al., NeurIPS 2022) - estimate per-year accuracy with NO
LABELS AT ALL.** OOD agreement between the predictions of any two networks correlates linearly
with their in-distribution agreement, so out-of-distribution ACCURACY can be estimated from
unlabelled target data plus the predictions of several models.

Check it against what we already hold:

| the method needs | we have |
|---|---|
| unlabelled target data | 18 unlabelled acquisitions, city-wide |
| several trained models | 9 live per-year models, plus baseline/corrected variants on 2016 |
| in-distribution accuracy for the same models | 2020, our one labelled year |

**This is the most directly usable result in the entire loop.** It attacks the question that has
blocked the project from the beginning - *how good is the model on 2002, where no trustworthy
label exists* - and it needs no new imagery, no new labels, and no GPU beyond re-running inference
with a few model variants. It would also give us per-year numbers for the pre-2016 years that
C-CAP cannot score at all.

**And it is self-checking, which matters given how often this loop has had to caveat things.**
The phenomenon holds *whenever accuracy-on-the-line holds*, and that condition is itself testable
from unlabelled data. So the first output is not an estimate but a verdict on whether our years
are even amenable to the method. A negative result would be informative: it would say our shifts
are not of the type where ID performance predicts OOD performance, which is itself a strong
statement about the archive.

**Relation to what we already built.** `phase4_qc_flicker.py` measures disagreement of ONE model
ACROSS years. This is the orthogonal axis - agreement of SEVERAL models ON one year. The two
together would separate "the year is hard" from "the model is unstable", which nothing currently
distinguishes (open question Q7).

**On the selection rule itself (ID 154, Wang et al. 2024, SDM, peer-reviewed).** Takes up exactly
the problem Gulrajani & Lopez-Paz raised and proposes selection that never touches the target
domain. Read before we invent our own rule. The alternatives now on the table for Q33:
1. **Leave-one-era-out** - reported unbiased and better than training-domain validation, but it
   costs training data and we have one labelled year, so "era" would have to mean something other
   than a labelled domain.
2. **Agreement-on-the-line as the selection signal** - selects using unlabelled target data
   directly, and does not require any target labels.
3. **A small in-year human sample** - honest but expensive, and Search 21 showed 250 points buys
   calibration rather than discrimination.
4. **Current practice - projected 2020 labels** - carries the training signal's own bias.
   Option 4 is the one we use and the one with the clearest defect.

### Search 34 - WEIGHT AVERAGING & ENSEMBLING - IDs 155-156
Last untouched taxonomy family, and it turns out to contain the cheapest experiment in the loop
after FDA - because it requires no retraining at all.

**WiSE-FT (ID 156, Wortsman et al., CVPR 2022) applies to checkpoints we already have.**
Interpolate between the PRETRAINED and the FINE-TUNED weights: `w = (1-a)*w_base + a*w_finetuned`.
Every one of our per-year models is fine-tuned from `sem_best_2020.pt`, so this is **weight
arithmetic over existing checkpoints** - no Colab training, no new imagery, no labels. Each value
of `a` can be scored with the QC scripts already built.

What it buys is a principled dial on **how far a coarse year is allowed to drift from the 2020
base**. That is precisely the failure mode behind our label-circularity concern: a year fine-tuned
hard on projected 2020 labels inherits their bias, while a year held close to base keeps whatever
generality the base had. Right now that trade-off is implicit in epochs and learning rate. WiSE-FT
makes it an explicit, sweepable parameter, evaluated post hoc.

**Model soups (ID 155, Wortsman et al., ICML 2022) solve our inference-cost problem.** Averaging
the weights of several differently-tuned fine-tunes improves accuracy AND out-of-distribution
robustness **at no extra inference or memory cost**. That matters concretely here: our full-city
inference already OOM'd at batch 160 on an A100 (v044), and a true ensemble over 18 citywide
rasters is unaffordable. A soup gives ensemble-grade robustness at single-model expense.

**And it composes with the tuning sweep Q17 already demands.** A hyperparameter search produces a
pile of runs that are normally discarded once the best is picked. Model soups say keep them and
average them. So the tuned-ERM baseline (Q34) and the soup are the same piece of work.

**One tension to design around.** Agreement-on-the-line (ID 153) NEEDS several distinct models to
measure agreement; a soup collapses them into one. Sequence matters: **train the variants, measure
agreement to estimate per-year accuracy, THEN soup for deployment.** Doing it the other way round
destroys the instrument.

**Taxonomy coverage is now complete** against Rafi 2024 (ID 146): augmentation/randomization,
normalization, style-content disentanglement, meta-learning (closed), causal/invariance (touched),
and ensembling (this iteration). Twenty-two iterations, 34 searches, no family left unexamined.

### Search 35 - SEGMENTATION QUALITY WITHOUT GROUND TRUTH - IDs 157-158
Q35 asked whether agreement-on-the-line transfers from classification to segmentation. The honest
answer is that nothing found demonstrates it for dense prediction - **but segmentation has its own,
older, better-suited instrument, and we had not looked for it.**

**Reverse Classification Accuracy (ID 157, Valindria et al. 2017, IEEE TMI).** Predicts a
segmentation quality score (Dice) for an image with NO ground truth: train a classifier using that
image's own predicted mask as pseudo-truth, then test it against a small reference database that
does have labels. If the prediction was good, the reverse classifier does well on the reference
set; if it was poor, it fails. **Its single requirement - a small labelled reference set - is
exactly what we have in 2020.**

**ConfIC-RCA (ID 158, Cosarinsky et al. 2025, IEEE TMI) joins the two threads this loop has been
developing separately.** It combines RCA with **split conformal prediction**, so the output is a
**prediction INTERVAL on segmentation quality** - the true score lies inside with a user-specified
probability - rather than a point estimate. It also adds retrieval-augmented reference selection,
so it needs minimal reference data.

That is our deliverable's own statistical shape, applied one level up:

| level | quantity | instrument |
|---|---|---|
| per crown | temporal validity interval | conformal / risk control (Searches 18-21) |
| per YEAR | segmentation quality interval | ConfIC-RCA (this search) |

**Why this may be the best-fitting result of the whole loop.** STATE calls King 2000/2002
"un-trainable AND un-measurable" - a hard floor, to be shipped LOW-CONFIDENCE with no number.
Between Barber 2023 (ID 125, coverage with a stated penalty) and ConfIC-RCA, we now have two
independent routes to replacing "no number" with "a bounded number and an honest interval". That
converts the hard floor from a silence into a measurement.

**The caveat is real and must ride with it.** Both are medical-imaging results. Transfer to aerial
canopy is untested, and RCA's reference database would need to span our land-cover variety -
suburban, forest, water, impervious - not a handful of sites. Our 2020 labels are training-site
footprints plus a citywide model mask, which is not obviously the right reference set. Whether RCA
survives that is an experiment, not a reading question.

**Also surfaced:** a Segmentation Performance Evaluator line reporting ~0.956 correlation between
estimated and true metrics across six datasets and six metrics, including Dice and HD95. Worth
following as an alternative if RCA's reference-set requirement proves awkward.

### Search 36 - ground-truth-free evaluation OUTSIDE medical imaging - IDs 159-160
**Q40 ANSWERED, and it corrects my own enthusiasm from Search 35.**

**RCA has NOT been applied to remote sensing.** Two searches for it found only medical imaging -
cardiac MR, multi-organ, UK Biobank. No aerial or satellite application exists. That materially
raises the risk of the RCA route, on top of Q39 (our 2020 reference set is itself a biased model
mask, which is exactly the assumption RCA needs to hold).

**But remote sensing has its own answer, and WE ALREADY HAVE IT.** The RS-native method for
assessing classification quality without ground reference is **latent class analysis** -
Foody 2022, already in the tracker as **ID 80** from Search 10. Comparing the two honestly:

| | needs | our situation |
|---|---|---|
| **RCA** (ID 157) | a clean labelled REFERENCE DATABASE | we have only 2020, and it is a biased model mask (Q39) |
| **Latent class** (ID 80) | several IMPERFECT sources on the same ground | we have C-CAP, the NDVI reference, and the model |

**So the ranking flips.** Latent class is better suited to us than RCA: it is validated on our data
type, it does not require a clean reference, and the very thing that breaks RCA - biased,
disagreeing sources - is what latent class is built to exploit. Search 35 over-weighted a
medical-imaging import when the field's own tool was already sitting in our tracker from Search 10.
Prefer ID 80; hold RCA/ConfIC-RCA as the fallback, and treat their conformal framing (ID 158) as
the useful transferable idea rather than the method.

**A DISTINCTION WE MUST NOT BLUR (ID 159, Gao et al. 2017).** Remote sensing does have unsupervised
segmentation quality evaluation - scoring segments by spatial stratified heterogeneity and
autocorrelation, no ground truth needed. But it measures whether segments are well **FORMED**
(homogeneous inside, distinct from neighbours), **not whether the label is CORRECT**. It would
happily certify a cleanly delineated hedge as a good segment. Useful as a geometry QC layer on the
instance stream; useless as an accuracy substitute. An eager reading of "ground-truth-free
evaluation" invites exactly this confusion.

**And a gap in our own reporting (ID 160, Costa, Foody & Boyd 2018, RSE).** Segmentation accuracy
has two separable components - GEOMETRIC agreement and THEMATIC correctness - and our pipeline
reports only a binary canopy mask. A crown correctly detected but badly delineated scores the same
as one delineated perfectly, and the per-crown validity interval inherits that blindness. For a
per-crown deliverable that is a real omission, not a technicality.

### Search 37 - LATENT CLASS, READ PROPERLY - IDs 161-162
Latent class analysis has been this loop's recommended escape from "we cannot tell which reference
is right" since Search 17, was promoted again in Search 36, and had never been examined past its
abstract. Read properly, **it does not work on three sources, and our three are the wrong three.**

**1. THREE SOURCES AND TWO CLASSES IS JUST-IDENTIFIED - FITTABLE BUT UNTESTABLE.**
Three binary indicators give 2^3 - 1 = 7 free cells; the model estimates 3 sensitivities, 3
specificities and 1 prevalence = 7 parameters. **Zero degrees of freedom.** It will always fit
perfectly and no goodness-of-fit test is possible. We have exactly three sources: C-CAP, the
NDVI+CHM reference, and the model.

**2. CONDITIONAL DEPENDENCE BIASES IT IN THE DIRECTION THAT FLATTERS US (ID 161).**
When sources are correlated but independence is assumed, the correlated tests' SENSITIVITIES are
OVERESTIMATED (median bias +0.094) and prevalence plus the uncorrelated tests' specificities are
underestimated. Our correlated pair is obvious: **the model was trained on labels derived from the
same imagery and the same NDVI+CHM logic as the NDVI reference**, and after the v042 overlay that
reference literally supplied training labels. A naive latent class fit would inflate exactly that
pair's apparent recall. **It would tell us what we want to hear**, which is the one outcome our
honest-measurement workstream exists to prevent.

**3. AND WE COULD NOT DETECT THE PROBLEM (ID 162).** Residual correlation plots and pairwise
G2/chi-square identified the genuinely correlated pair only **10-12%** of the time, while falsely
flagging an innocent pair **50-65%** of the time, and caught overall lack of fit in only about
two-thirds of cases. So neither assuming independence nor testing for its violation is safe.

**Net: the latent-class route as scoped is unfalsifiable and biased toward optimism.** That is a
retraction of guidance this loop gave three times (Searches 17, 36, and by implication 10).

**THE CONSTRUCTIVE VERSION - GET A FOURTH, GENUINELY INDEPENDENT SOURCE.** With four indicators the
model gains degrees of freedom, fit becomes testable, and conditional-dependence formulations
become estimable. Candidates, ranked by independence from the existing three:
1. **The P3 human photo-interpretation sample** - genuinely independent of imagery-derived logic,
   and it is already planned. This is the strongest argument yet for running P3, and it reframes
   its purpose: not only calibration (Search 17) but the fourth indicator that makes latent class
   identifiable at all.
2. **The CHM alone**, thresholded as a height-only canopy test - shares the CHM with the NDVI
   reference, so only partly independent.
3. **A second model of a different family** trained without NDVI-derived labels.
4. **C-CAP 2021 as distinct from C-CAP 2016** - cheap, but shares C-CAP's definitions, so it is
   nearly a repeat of the same test rather than a new one.

**This is the third time the loop has deflated its own recommendation** (Search 20 on DG methods,
Search 36 on RCA, now this). The pattern is worth naming: the promising result usually assumes
something our archive violates, and the violation is usually CORRELATED ERRORS between things we
treat as independent.

### Search 38 - CORRELATED REFERENCE ERRORS: the structural problem named - IDs 163-164
Search 37 observed that three of this loop's recommendations failed for the same reason -
correlated errors between sources we treat as independent. This iteration searched that directly,
and the problem has a name, a DIRECTION, and a partial fix in the remote-sensing literature.

**THE DIRECTION (ID 163, Radoux & Bogaert 2020, Remote Sensing).**
* reference errors **CORRELATED** with a classifier's errors -> accuracy **OVERESTIMATED**, and
  that classifier is **systematically favoured** over competitors;
* reference errors **conditionally independent** -> accuracy **underestimated**.

Read finding 5 against that. The corrected 2016 model landed beside the NDVI reference
(35.28% vs 37.7%) rather than C-CAP's (29.5%), and after the v042 overlay that reference had
supplied its training labels. **Scoring it against the NDVI reference flatters it by construction** -
not as a suspicion, as a stated property of the estimator. Conversely C-CAP, whose errors are more
nearly independent of ours, should be UNDERSTATING our accuracy. That is the quantitative form of
"the two references bracket truth", and it now has a mechanism rather than an intuition.

**Same paper, a direct steer for P3:** a few HIGH-QUALITY trusted labels beat a larger volume of
questionable reference data. Combined with Search 21 (250 points suffices for calibration, not for
arbitration), the design implication is consistent - spend the human budget on fewer, better,
harder points rather than more easy ones.

**THE MACHINERY (ID 164, Persson et al. 2022, RSE).** Forest-specific estimators that MEASURE
reference error and propagate it into the final figures. STATE's standing caveat - "both refs are
PROXIES; an unknown share of the gap is ref error" - is currently a sentence. This is how it
becomes a term in an equation with a number attached, which the per-crown intervals need if they
are to mean anything.

**A CHEAP INSTRUMENT THIS SUGGESTS, AND WE ALREADY HAVE THE INPUTS.** The epidemiology literature
uses NEGATIVE CONTROLS - places where the answer is known a priori to be null - to detect shared
bias. Failing the test is always cause for concern; passing does not prove absence of bias, but
the asymmetry is still useful. For us the known-negative surfaces are free:
* **open water** (Puget Sound) - no canopy, ever;
* **building footprints** - we already hold `building_footprints/data.json`;
* **paved/impervious** - the `impervious/` layer already exists.

If the model AND the NDVI reference both call canopy on the same known-negative pixels, that is
direct evidence of shared bias, measured with no human labelling at all. The project already has
the instinct - "grass-rejection" is exactly this idea applied to one surface - but it has never
been framed as a negative-control test across several surfaces, nor used to compare SOURCES rather
than models.

**Why this matters more than another method.** Three retractions (Searches 20, 36, 37) traced to
one cause. This search says the cause is recognized, directional, partially correctable, and
detectable with data already on disk. That is a better return than a fourth method would have been.

### Search 39 - CROWN INSTANCE SEGMENTATION, SAM ERA - IDs 165-166
Oldest gap in the queue: the fine-resolution instance stream had no update since Phase 1A. Two
findings, and the first is a warning about work the project has already committed to.

**MANUAL CROWN LABELS INFLATE MEASURED PERFORMANCE SEVEN-FOLD (ID 165, Allen et al. 2025).**
Validated against terrestrial laser scanning rather than hand-drawn labels, crown segmentation
performance collapses:

| evaluated against | AP50 |
|---|---|
| manual labels (Mediterranean) | 0.670 |
| **TLS ground truth (Mediterranean)** | **0.094** |
| TLS ground truth (boreal) | 0.142 |
| TLS, at IoU 0.75 (any) | max 0.051 |

The mechanism is the one Search 38 named: **human RGB labels and model predictions share the same
systematic errors**, so scoring against them measures agreement, not accuracy. That is
correlated-reference error (ID 163) arriving in the instance stream.

**This bears directly on annotation-plan item 1** - the ~1-3k hand-drawn 2020 crowns, listed as
the root fix for both heads. Those labels will inflate measured instance performance, and the
collapse is concentrated in **localization** (AP at IoU 0.75 near zero), which is precisely the
geometric-versus-thematic distinction of Q41. Detection can look fine while delineation is poor.

**Do not over-transfer the magnitude.** This is CLOSED-CANOPY forest. Much of Edmonds is
open-grown suburban crowns with visible gaps between them, which are far easier to delineate and
where hand labels are far more trustworthy. The mechanism transfers; the seven-fold figure almost
certainly does not. But the visual grounding says our missed stands are suburban/ornamental - the
easy-delineation case - so the inflation may bite hardest exactly where we are least worried, and
least where we are most.

**THE CURRENT REFERENCE POINT (ID 166, Huang et al. 2026, Remote Sensing, peer-reviewed).**
Tree-SAM: city-scale individual tree detection on SAM with **ladder-side-tuning**, reporting
**F1 0.830 / AP@50 0.526 in the URBAN scenario** versus 0.762/0.478 in forest - better in cities,
which is our setting. Ladder-side-tuning is the practically important part: it adapts a foundation
model **without backpropagating through it**, which is the difference between feasible and
infeasible on our Colab budget.

**And a negative result consistent with Search 32.** SAM used OUT OF THE BOX does not beat a custom
Mask R-CNN even with well-designed prompts. The adaptation is doing the work, not the foundation
model - the same lesson as ERM-with-tuning beating specialist DG methods.

**Also noted, not yet pursued:** Mask2Former beats Mask R-CNN by up to ~3.8% on tree instances
(modest), and training-free flow-based approaches (Cellpose-SAM lineage) come within ~2% of
supervised models with NO instance annotations - interesting given that annotation is our binding
constraint.

### Search 40 - WHAT PRECISION DOES A CANOPY NUMBER ACTUALLY NEED? - IDs 167-168
Twenty-eight iterations optimizing a canopy-change product without once asking what the number is
for. This should have been iteration 1.

**THE CAUTIONARY TALE IS 15 MILES AWAY (ID 167, Richardson & Moskal 2014, UF&UG).** Assessed
SEATTLE canopy cover varies substantially across studies **for identical dates** - multiple
conflicting published values for 1972, 2002 and 2009. Methodological difference, not real canopy
change, produced apparent trends that a city then acted on. Same region, same imagery ecosystem,
same institutional pressures. This is the failure mode our honest-measurement workstream exists to
avoid, and it is citable directly in any Edmonds-facing write-up.

**AND THE SOURCE ALONE MOVES THE ANSWER (ID 168, Ucar et al. 2016).** Tallahassee canopy cover
estimated at 44.5-45.1% from NAIP versus 48.6-49.1% from Google Earth - about **four percentage
points from imagery choice, with nothing changing on the ground.** Same order as our own
inter-reference disagreement, which reframes that disagreement as normal rather than pathological.

**THE COMPARISON THAT MATTERS.** Edmonds policy context: a 32.4% baseline and a 35%-by-2036 goal -
a **2.6 percentage point** effect over a decade. Set that against every uncertainty we have measured
or read:

| source of uncertainty | magnitude | vs the 2.6 pp effect |
|---|---|---|
| our 250-point sample (95% half-width) | 5.9 pp | **larger** |
| i-Tree at >500 points (SE 1.7% -> 95%) | 3.3 pp | **larger** |
| imagery source alone (NAIP vs Google Earth) | 4.0 pp | **larger** |
| our two references disagree | 8.2 pp | **larger** |

**Every single source of measurement uncertainty is larger than the effect the policy is about.**
That is the "good enough" answer the loop has been missing, and it is uncomfortable.

**THE IMPORTANT CAVEAT, WHICH SHARPENS RATHER THAN SOFTENS THE POINT.** A CHANGE between two years
can be estimated far more precisely than either absolute level, because systematic bias shared by
both measurements partly cancels - paired estimation on the same ground with the same instrument.
So the table above is not fatal in principle. **But cancellation requires the instrument to be
constant across years, and ours is the opposite**: four agencies, multiple contractors, 7.5-60 cm
GSD, unknown flight dates, and radiometric clusters that do not follow agency (iteration 11).
The one design that would rescue the precision is the one our archive most conspicuously violates.

**What this implies for the project, stated plainly:**
1. Absolute per-year canopy percentages are the WEAKEST product we could ship - they inherit every
   source-driven offset in the table.
2. **Paired change on stable ground with a matched instrument** is the strongest - which is an
   argument for prioritizing year-pairs from the same radiometric cluster over the full 18-year
   series, and for the 2017 matched pair (iteration 13) as the calibration anchor.
3. Any number we publish needs its method and interval attached, or it becomes another row in
   Seattle's table of conflicting values for the same date.

### Search 41 - PAIRED SAMPLING: the fix for Q48 - IDs 169-170
Search 40 ended on the project's central feasibility question: every uncertainty we have exceeds
the ~2.6 pp effect a decadal canopy goal implies. **This iteration finds the design that closes
the gap, and it costs no extra points.**

**The principle is settled and old (ID 170, Frayer & Furnival 1967, Forest Science).** Forest
inventory resolved this in the 1960s: **permanent plots give the highest precision for CHANGE**
(shared bias cancels between dates), temporary plots give unbiased LEVELS, and **sampling with
partial replacement** keeps some of each to get both. Our Phase 3 design uses neither - it samples
each year independently.

**The arithmetic, for a net +2.6 pp change** (paired variance is McNemar-form: only points that
CHANGED contribute, so the ~2/3 of points that are canopy at both dates drop out entirely):

| n | paired ± (low turnover) | paired ± (high turnover) | independent ± | detects 2.6 pp? |
|---|---|---|---|---|
| 250 | 2.86 pp | 3.79 pp | 8.30 pp | no |
| **500** | **2.02 pp** | 2.68 pp | 5.87 pp | **yes (low turnover)** |
| **750** | **1.65 pp** | **2.19 pp** | 4.79 pp | **YES, both** |
| 1000 | 1.43 pp | 1.89 pp | 4.15 pp | yes |

**Pairing buys roughly a 2.9x precision gain, and it is the difference between "cannot answer" and
"can answer".** Independent sampling never reaches 2.6 pp at any affordable n - not even 1000
points.

**THE PUNCHLINE FOR THE EXISTING PLAN.** Phase 3 is scoped at **250 points x 3 years = 750 points**.
That is *already* the budget that works - it is simply being **spent the wrong way**. Interpreted
independently per year it answers nothing at the policy-relevant scale; interpreted as **the same
points revisited across dates** it resolves a 2.6 pp change in both turnover scenarios. Same human
hours, same 750 interpretations, opposite conclusion about feasibility.

**And the omission problem has its own estimator (ID 169, Olofsson et al. 2020, RSE).** Our model
is a documented high-precision under-predictor missing 30-35% of reference forest, so every area
figure is omission-dominated and the change series compounds it. This paper treats omission
specifically as it propagates into area AND area-change estimates, and gives estimators that
mitigate rather than merely report it. It is the missing link between the Search 9 machinery
(ID 69) and a defensible change number.

**Caveats, honestly.** The turnover assumptions (4.0%/1.4% and 6.0%/3.4% gain/loss) are guesses -
the true discordant rate drives everything and we do not know it, though the P2 partition could
bound it. Pairing also introduces its own risks: the interpreter sees both dates together and may
anchor on the first, which is a known bias in repeated interpretation, so blind or randomized date
order matters. And permanent points can drift out of representativeness over 24 years, which is
exactly what partial replacement exists to fix.

### Search 42 - ANCHORING vs FALSE CHANGE: a real trade-off, not a solved problem - IDs 171-172
Search 41 recommended paired interpretation and flagged anchoring as a risk. Searching it turns up
a genuine two-sided trade-off, with both failure modes measured, and no free option.

**SIDE ONE - ANCHORING IS LARGE AND BIASES TOWARD "NO CHANGE" (ID 171, Branch et al. 2022).**
Radiologists shown prior diagnostic information anchor at **38.3% (low experience)** and **28.3%
(most experienced)**, and can ignore task-relevant image evidence entirely once anchoring
information is present. Expertise reduces it; it does not remove it, so a single expert interpreter
is not a mitigation. **The direction is the dangerous one for us**: anchoring suppresses apparent
change, biasing a canopy trend toward zero, precisely where the policy question lives.

**SIDE TWO - INDEPENDENT READING MANUFACTURES FALSE CHANGE (ID 172, Mas et al. 2017, EJRS).**
From our own field: classifying each date independently generates spurious transitions, and a
cascading protocol (classify date 1, carry labels forward, edit only where change is seen) yields
consistent maps without them.

**AND FALSE CHANGE IS NOT MERELY NOISE - IT DESTROYS THE PRECISION GAIN.** Paired variance is
driven ONLY by discordant pairs, so every false change directly inflates it. Net change held at
+2.6 pp:

| scenario | gain% | loss% | n=250 | n=750 |
|---|---|---|---|---|
| true change only (clean pairing) | 4.0 | 1.4 | 2.86 pp | **1.65 pp** |
| + mild false change | 8.0 | 5.4 | 4.53 pp | 2.61 pp |
| + heavy false change | 15.0 | 12.4 | 6.48 pp | 3.74 pp |
| + severe false change | 25.0 | 22.4 | 8.53 pp | 4.92 pp |

**At severe false-change rates even 750 points cannot resolve 2.6 pp.** So Search 41's headline -
"the existing 750-point budget already works" - holds ONLY if the response design keeps false
change low. Independent reading is not a neutral alternative; it can spend the entire precision
advantage.

**THE RESOLUTION, AND IT REUSES SOMETHING ALREADY IN THE TRACKER.** Neither option is free, so
measure the bias rather than assuming it away: interpret the MAIN sample with the cascading/paired
protocol (low false change, high precision), and interpret a **blind independent subset** - dates
shown separately, order randomized - to **estimate the anchoring effect** and correct the main
estimate for it. That is exactly the interpenetrating-subsample design of Xing & Stehman 2024
(**ID 101**, Search 14), repurposed: there it separated interpreter variance, here it separates
protocol-induced bias. Same machinery, new use, already cited.

**What we still do not know:** the size of anchoring for CANOPY specifically. The 28-38% figures
are mammography, where the prior is a diagnosis rather than an image. Canopy-at-a-point is a
simpler judgement and the anchoring may be much smaller - or larger, since change is genuinely
subtle at 60 cm. Nothing found measures it for land cover, which makes the blind subset not merely
prudent but the only way to know.

### Search 43 - ANNOTATION-FREE CROWN SEGMENTATION - IDs 173-174
Annotation is our binding constraint, and Search 39 showed hand-drawn crowns inflate measured
performance. This search finds a route that avoids both problems.

**LIDAR PSEUDO-LABELS + SAM2 REFINEMENT, AT ZERO ANNOTATION COST (ID 173, Pesonen et al. 2026).**
Train an image-based crown segmentation model on pseudo-labels derived from airborne laser
scanning and refined with SAM 2, reporting better results than available general-domain models -
with no manual annotation at all.

**We already hold every input, and the vintages line up:**

| the method needs | we have |
|---|---|
| airborne lidar over the target area | 3DEP HAG CHM, `lidar_snoh_chm.tif`, 59.8% city coverage |
| high-resolution optical imagery | 2017 CoE at 7.46 cm, 2016 Snohomish at 50 cm |
| near-contemporaneous lidar and imagery | CHM is ~2016; the 2016 and 2017 acquisitions bracket it |
| SAM 2 for refinement | public weights, inference only |

So crown pseudo-labels could be generated wherever the CHM covers, refined, used to train the
instance head, and the trained model applied city-wide including the 40% with no CHM. **That is a
direct alternative to annotation-plan item 1** - the ~1-3k hand-drawn 2020 crowns currently listed
as the root fix for both heads.

**And it sidesteps the correlated-error problem, which is the deeper reason to prefer it.**
Allen et al. (ID 165) showed hand-drawn RGB crowns inflate measured performance seven-fold because
human labels and model predictions share the same RGB-based errors. **Lidar-derived crowns do not
share those errors** - they come from a different physical measurement. That makes them both a
cheaper training signal AND a less circular one, which is the same argument that made the CHM
valuable for the semantic stream.

**THE RANKING IS NOW SETTLED FOR THE INSTANCE STREAM (ID 174, Chen et al. 2025, plus Search 39).**
1. **Pseudo-label from lidar, refine with SAM2, then TRAIN** - best available without annotation.
2. **Train on coarse or noisy labels** - explicitly reported as more robust than any current
   zero-shot option. A quiet endorsement of our existing noisy-label pipeline design.
3. **Zero-shot SAM2 alone** - worst; it complements trained methods rather than replacing them,
   and does not beat a custom Mask R-CNN even with good prompts (Search 39).

Zero-shot is a REFINEMENT STAGE, not a substitute for training. That is a useful correction to the
temptation to reach for a foundation model as a shortcut.

**Honest limits.** Both are preprints. ID 173's quantitative comparison against manually-annotated
baselines is not stated in the abstract, so "outperforms general-domain models" is a weaker claim
than "matches hand annotation". Our CHM is also coarser and staler than the ALS these methods
assume - one ~2016 snapshot at 1 m, versus dense contemporaneous point clouds - and Hamraz (ID 86)
already told us understory segmentation depends on point density. Blocky CHM-derived segments are
exactly the problem SAM2 refinement is introduced to fix, so the approach may still work, but the
degradation at our CHM quality is unmeasured.

### Search 44 - TEMPORAL CONSISTENCY - IDs 175-176
**THE COMPOUNDING BIAS THIS LOOP HAS BEEN ASSEMBLING WITHOUT NOTICING.**

Three separate mechanisms, found in three separate searches, all push the same way:

| mechanism | where it enters | direction |
|---|---|---|
| pseudo-labelling from the 2020 anchor mask (finding 4, ID 89) | training | toward the anchor year's state |
| anchoring in paired interpretation (ID 171, Search 42) | human reference | toward "no change" |
| temporal smoothing / HMM priors (ID 175, this search) | post-processing | toward "no change" |

**Every one of them suppresses apparent change, and the deliverable is a change product.** For a
project whose question is how much canopy has been lost, three independent no-change biases stacked
in series is a systemic risk, not three separate technical details. Nothing in the pipeline
currently measures any of them.

**HMM post-processing is the standard fix, and the standard hazard (ID 175, Abercrombie & Friedl
2016, TGRS).** Transition and emission probabilities separate real change from classification
error, and multitemporal products genuinely do exhibit unrealistic year-to-year label churn - our
flicker metric measures exactly that. The transition matrix is where domain knowledge enters:
canopy rarely appears or vanishes in a single year. **But that prior is precisely what would
suppress genuine rapid canopy LOSS** - a lot cleared, a stand removed - which is the signal a tree
ordinance is about. Adopt it only with the prior stated and its effect on real loss events measured.

**The model-side alternative (ID 176, He et al. 2024, RSE).** Segment the TEMPORAL dimension
directly rather than differencing independently classified dates. Our pipeline does the latter:
per-year masks produced independently, change inferred by comparison, so **every per-year error
becomes a candidate change event**. That is the model-side twin of the false-change problem
Search 42 found in human interpretation.

**And an asset we are not using.** Temporal-consistency losses do NOT require ground-truth labels,
so all 17 unlabelled years could contribute to TRAINING rather than only to inference. Combined
with Search 43 (lidar pseudo-labels) and Search 23 (in-archive pretraining), that is now the third
independent route by which our unlabelled archive could do more than it currently does.

**What this changes about the recommendations.** Any temporal smoothing we adopt must be paired
with a measurement of what it removes. The natural design: run the change estimate with and without
the temporal prior, and report the difference as a sensitivity - the same discipline the blind
subset provides for anchoring (Search 42). Otherwise we will produce a beautifully consistent
series that has quietly deleted the events the project exists to find.

### Search 45 - TRAJECTORY SEGMENTATION & DISTURBANCE - IDs 177-178
Searches 41-42 reasoned their way to a paired, trajectory-based interpretation protocol and then
worried about how to build it. **It already exists, is operational, and validates USFS/LCMAP.**

**TIMESYNC IS THE PROTOCOL WE DERIVED (ID 177, Cohen, Yang & Kennedy 2010, RSE).** An interpreter
works a sample point's ENTIRE TRAJECTORY across all dates at once, assigning change SEGMENTS rather
than classifying each date in isolation. That is the cascading design of Search 42 and the paired
estimator of Search 41, in a mature form with a documented workflow, used operationally for Landsat
validation. It also connects to Pengra 2020 (ID 99), already in our tracker from Search 14 - LCMAP
QC is the same family.

**So the Phase 3 redesign does not need inventing, it needs adopting** - with the Search 42
safeguards added, since TimeSync is trajectory-based and therefore anchoring-exposed by
construction. That is the one thing the established protocol does not solve for us.

**LANDTRENDR GIVES THE RIGHT DATA STRUCTURE, PROBABLY NOT THE RIGHT ALGORITHM (ID 178, Kennedy,
Yang & Cohen 2010).** It segments each pixel's trajectory into straight-line pieces with explicit
**vertex years**, representing abrupt disturbance and gradual recovery together. That is
structurally what a per-crown validity interval wants: **a trajectory with breakpoints, not a
smoothed series** - and it is the direct answer to Search 44's worry that smoothing deletes the
events we care about. Trajectory segmentation preserves abrupt change by design rather than
penalising it.

**But our sampling violates its assumptions, on three counts:**

| LandTrendr assumes | we have |
|---|---|
| yearly observations | 18 acquisitions over 24 years, gaps of 2-4 years pre-2013 |
| seasonal compositing to control phenology | one acquisition per year at best; no compositing possible |
| a consistent sensor across the series | four agencies, multiple contractors (iteration 11) |

Its acknowledged blind spot is phenology - handled upstream by compositing - which is precisely the
Search 30 problem we cannot solve the same way. **Adopt the trajectory-with-vertices framing;
do not assume the fitting machinery survives our sampling.**

**A useful reassurance and a useful warning from the same search.** Reassurance: the per-crown
matching approach - track annual tree-centre predictions and flag losses - is already in our
tracker as Ventura et al. (ID 7), so the urban method exists. Warning: fine-scale tree-loss
detection is dominated by **multi-temporal misalignment**, which Phase 3 Search 7 (IDs 21-26)
already covers - meaning the co-registration work is not a side quest but a precondition for any
per-crown change claim.

### Search 46 - SPARSE / IRREGULAR SERIES - IDs 179-180
**Q57 ANSWERED, and the answer is that our series is not a series.**

Zhu 2017 (ID 179, ISPRS, review) organizes change detection by OBSERVATION FREQUENCY and makes
explicit which algorithm families each frequency supports: bi-temporal, multi-temporal, and dense
annual/sub-annual trajectory methods. Placing ourselves on that map:

| our archive | 18 acquisitions / 24 years, gaps of 2-4 years pre-2013, one per year at best |
|---|---|
| what trajectory fitting needs | dense annual or sub-annual, seasonally composited, one sensor |
| what our density supports | **epoch-pair comparison** |

And the historical-aerial literature confirms it in practice: multi-decadal aerial studies work in
**intersectional epochs** (e.g. 1957, 1980, 1994-97, 2006, 2014, 2018), with the temporal component
explicitly "on the order of a decade". Nobody fits trajectories to sparse aerial archives, because
you cannot.

**THIS IS THE FOURTH INDEPENDENT LINE ARRIVING AT PAIRS, NOT SERIES:**
1. Search 40 - absolute per-year levels inherit every source-driven offset; paired change cancels
   shared bias.
2. Search 41 - paired estimation is the only design that resolves a 2.6 pp effect at an affordable
   sample size.
3. Search 42 - cascading paired interpretation is the response design that controls false change.
4. Search 46 - the historical-aerial field itself works in epoch pairs, and our observation density
   supports nothing more.

**Four different literatures, four different reasons, same conclusion.** That is a stronger basis
for a design decision than any single result in this loop, and it argues against the standing
"18-year continuous series" framing of the deliverable. The honest product is a small number of
well-chosen, well-matched EPOCH PAIRS with intervals attached - not a continuous canopy trajectory.

**AND THE PRECONDITION HAS A METHOD (ID 180, Zhang, Rupnik & Pierrot-Deseilligny 2021, ISPRS).**
Feature matching BETWEEN EPOCHS of historical aerial imagery, where radiometry, sensor and scene
have all changed. Our Phase 3 Search 7 (IDs 21-26) covered the CONSEQUENCES of misregistration;
this is the method for reducing it on exactly our kind of archive. It matters most for the 2000/2002
King acquisitions - the era where co-registration is worst, recall is lowest, and STATE already
calls the years un-measurable.

**What this does NOT resolve.** Choosing epoch pairs requires knowing which acquisitions are
instrument-comparable, which is Q19 - still open, still blocked on acquisition dates, and still the
highest-leverage missing fact. A badly chosen pair reintroduces exactly the source-driven offset
that pairing was supposed to cancel.

### Search 47 - INTERVAL-CENSORED & DEMOGRAPHIC FRAMING - IDs 181-182
The deliverable is called a per-crown temporal VALIDITY INTERVAL. Thirty-five iterations in, this
is the first search of the statistical framework that name describes.

**OUR DATA IS INTERVAL-CENSORED, AND THE OBVIOUS HANDLING OF IT IS A KNOWN ERROR (ID 181).**
When subjects are assessed periodically, the event is known only to have occurred BETWEEN two
visits. An epoch-pair canopy series produces exactly that: *this crown was present in 2013 and
absent in 2016*. The warning that matters:

> assigning the event to the MIDPOINT or END of the interval is a known source of bias and invalid
> inference.

Midpoint assignment is precisely what a canopy-loss analysis would do without thinking - plot
losses at 2014.5 and fit a trend. The Turnbull estimator handles interval censoring properly. This
should be settled before any per-crown loss date is analysed, plotted, or handed to a policy
audience, because the bias enters at the moment of tabulation rather than at the model.

**AND THE DELIVERABLE IS A DEMOGRAPHIC PRODUCT, NOT ONLY A MAPPING ONE (ID 182, Hilbert et al.
2019, AUF).** Survival curves, life tables and mortality rates are the native vocabulary for
per-crown outcomes over time, and urban forestry already has that literature. Reframing this way
also makes our numbers comparable to existing urban-forest research rather than only to remote
sensing.

**IT ALSO SUPPLIES THE PRIOR WE HAVE BEEN GUESSING AT.** Typical street-tree annual mortality is
**3.5-5.1%**, with 0.6-68.5% across cohort studies and 0-30% for repeated inventories of uneven-aged
trees. Compounded over an epoch gap:

| gap | @3.5%/yr | @5.1%/yr |
|---|---|---|
| 2 yr | 6.9% | 9.9% |
| 3 yr | 10.1% | 14.5% |
| 4 yr | 13.3% | 18.9% |
| 8 yr | 24.8% | 34.2% |

**Search 41 assumed 4.0% and 6.0% discordance and concluded 750 paired points resolve a 2.6 pp
effect.** At a 3-4 year gap the LOSS side alone plausibly reaches 10-19% for street trees, which
lands in the "heavy false change" row where precision degrades to 3.7 pp. **Our paired-precision
estimate may be optimistic**, and Q50 (measure the real discordant rate) moves from prudent to
necessary.

**The honest counterweight, which may rescue it.** These are STREET-TREE COUNT mortality rates, and
our measurement is canopy AREA at a point. Small trees dying remove little canopy, growth of
survivors adds it, and whole-canopy turnover is far lower than street-tree turnover. So the
discordance at a randomly placed point is likely well below these figures - but nobody has
checked, and the direction of the error is the one that matters.

### Search 48 - INTERVAL CENSORING + MISCLASSIFICATION - IDs 183-184
**THE TWO WORKSTREAMS TURN OUT TO BE ONE.**

Search 47 established that our data is interval-censored. This search finds the version that also
accounts for the observation being made by an IMPERFECT detector - and in doing so it connects the
honest-measurement effort to the change product in a way nobody has articulated.

**The model (IDs 183, 184).** An event known only to fall within an interval, detected by a test
with imperfect **sensitivity** and **specificity**, where those accuracy parameters enter the
LIKELIHOOD as explicit corrections. Deng et al. 2026 (ID 184, *Annals of Applied Statistics*) adds
a **terminal** event - crown removal is terminal in exactly that sense, a felled tree does not
return - fits a Cox-type semiparametric model, and handles censoring and misclassification together
by NPMLE with EM.

**Why this reframes the project.** The measurement workstream has been treated as quality control -
producing caveats to attach to numbers. It is not. It produces **the parameters the change
estimator consumes**:

| what P1-P4 measure | where it enters the change product |
|---|---|
| per-year recall (sensitivity) | likelihood correction for missed losses |
| per-year precision -> specificity | likelihood correction for false losses |
| per-band recall (the height curve) | covariate-conditional sensitivity |
| reference disagreement bounds | uncertainty on those parameters |

**Without those numbers the per-crown change product cannot be de-biased. With them, it can.**
That is a much stronger justification for the honest-measurement work than "we should be rigorous",
and it means the accuracy figures are not a caveat section - they are inputs.

**And covariates enter properly.** ID 184 accepts covariates, so height band, land-use context and
radiometric cluster become RISK FACTORS in the model rather than post-hoc stratifications bolted on
afterwards. Our height curve (recall .16 to .93) would enter as covariate-conditional sensitivity,
which is exactly the shape it has.

**The obvious objection, stated honestly.** These are biostatistics methods on cohorts of hundreds
to thousands of subjects with a handful of visits. We have ~222,000 crowns and up to 18 observation
epochs, which is a different computational regime - NPMLE with EM over 222k subjects is not
obviously tractable, and nothing found addresses that scale. It may need aggregation to strata or a
sampled cohort. Also, our sensitivity is not merely imperfect but STRUCTURED (height-dependent,
context-dependent, era-dependent), which is more than the two-parameter sensitivity/specificity
these methods assume - though the covariate machinery of ID 184 is the natural place to put it.

### Search 49 - DIFFERENTIAL MISCLASSIFICATION & THE RARE-CLASS TRAP - IDs 185-186
Two findings, and the first destroys a piece of reassurance this project has been leaning on
implicitly.

**1. "OUR UNDER-DETECTION JUST MAKES US CONSERVATIVE" IS FALSE HERE.**
Epidemiology's standard result: **non-differential** misclassification - error rates equal across
groups - biases toward the null, which is the comforting case. **Differential** misclassification -
error rates that DIFFER between groups - "can bias results in any direction: toward, away from, or
even reversing an association."

**Ours is emphatically differential.** Recall varies from .16 to .93 across height bands, differs
between suburban and forest context, and differs across sensor eras. So if the canopy being lost is
not drawn uniformly from those strata - and it will not be, since development clears mature stands
while yard trees are removed one at a time - **the direction of the bias in our change estimate is
unknown**. We cannot claim our loss figures are conservative. That intuition has probably been
operating unstated throughout the project.

**2. THE RARE-CLASS TRAP: CHANGE PRODUCTS ARE GOVERNED BY A QUANTITY WE HAVE NEVER MEASURED.**
Foody 2013 (ID 185) shows change-area mis-estimation scales with how RARE the change class is, and
change is always rare. Taking canopy loss at 4% of pixels over an epoch and change-sensitivity 0.70
(our honest recall range):

| specificity on the UNCHANGED class | false change | true change | % of detections FALSE |
|---|---|---|---|
| 99.5% | 0.48 pp | 2.80 pp | 15% |
| 99.0% | 0.96 pp | 2.80 pp | 26% |
| 98.0% | 1.92 pp | 2.80 pp | 41% |
| **97.0%** | 2.88 pp | 2.80 pp | **51%** |
| 95.0% | 4.80 pp | 2.80 pp | 63% |

**At 97% specificity, half of all detected change is spurious.** And here is the gap: our per-year
precision (.77-.96) is measured on the **canopy** class. **Nobody has measured specificity on the
UNCHANGED class across an epoch pair** - and that, not canopy accuracy, is what governs a change
product. Every accuracy number in `qc_indep_report.csv` describes the wrong quantity for the thing
we are trying to deliver.

**3. AND CHANGE UNCERTAINTY CANNOT BE COMPOSED FROM PER-YEAR FIGURES (ID 186, Burnicki 2012).**
Misclassification propagates through change categorization with spatio-temporal interdependence;
naive variance/covariance propagation, which assumes independent per-date errors, gives biased
standard errors. Our per-year masks come from the same model with the same blind spot on the same
ground, so their errors are strongly correlated - meaning the obvious approach of combining per-year
accuracies would understate change uncertainty.

**Taken together with Search 48:** the change likelihood needs sensitivity and specificity as
inputs, those must be measured on the CHANGE classes rather than the canopy class, they are
covariate-dependent rather than scalar, and their errors are correlated across dates. None of the
four conditions is currently met.

### Search 50 - ACCURACY ASSESSMENT *OF CHANGE* - IDs 187-188
Search 49 showed our accuracy figures describe the canopy class when a change product is governed
by the change class. This search finds that the community has already written the document.

**THE PROTOCOL EXISTS, IT IS CURRENT, AND IT COVERS CHANGE (ID 187).**
*Land Cover and Change Map Accuracy Assessment and Area Estimation Good Practices Protocol,
Version 1.1 (2025)* - CEOS Working Group on Calibration and Validation, Land Product Validation
Subgroup. 187 pages, DOI-registered, edited by Tyukavina, Stehman, Foody, Bontemps, Komarova,
Tsendbazar and Nickeson.

**It is written by the authors whose individual papers Phase 4 assembled one at a time.** Stehman,
Foody, Olofsson, Radoux and Woodcock are already in our tracker as IDs 69-76, 78-80 and 87. This
consolidates that machinery into one standard - and unlike Olofsson 2014 (ID 69), it addresses
**CHANGE maps specifically**, which is exactly the gap Search 49 exposed.

**Practical consequence:** our accuracy reporting should be written against this document rather
than assembled from papers. Adopting a published community standard also makes our figures
comparable to other work, which a bespoke protocol never will be - the same argument that favoured
TimeSync over a custom interpretation tool (Q58). Two standards, both already written, both
currently being reinvented in our plan.

**AND A DESIGN CHOICE WE HAVE BEEN CONFLATING (ID 188, Stehman 2012).**
Because change is rare, the change stratum is normally over-sampled - but *which* over-sampling
rule you choose determines which question the sample can answer:

| objective | allocation |
|---|---|
| estimate the AREA of change | Neyman optimal |
| estimate USER'S ACCURACY of change | equal allocation |

**These compete.** An allocation tuned for one degrades the other. So P3 must decide whether it
exists to say *how accurate our change map is* or *how much canopy actually changed*. Those are
different studies, and this loop - across Searches 40, 41, 47 and 49 - has been treating them as
one. Adding it to the pile of design decisions that must precede `--step design`:

1. strata: model-output / agreement / CHM band (Q33, Search 9)
2. paired vs independent, and the blind subset (Searches 41-42)
3. **area-optimal vs accuracy-optimal allocation (this search)**
4. which epoch pairs (Q59, blocked on acquisition dates)

### Search 51 - CEOS PROTOCOL, READ (Section 4.3) - ID 189
Read Section 4.3 "Accounting for reference data errors" of the CEOS protocol (ID 187) directly.
It answers several of our open questions with community-endorsed guidance, and one passage
overturns a decision already written into the P3 plan.

**1. MORE POINTS DO NOT FIX A BIASED RESPONSE DESIGN - AND THE RATIO IS STARK.**
> "Increasing the size of the reference sample does not reduce the bias of the estimates
> originating from low quality response design... The estimates would converge to the wrong
> target... validation efforts should focus on improving the response design instead of adding
> more points of the same quality."

With a worked comparison: on RMSE of overall accuracy, **100 sample sites at 99% accuracy beat
10,000 sample sites at 95%**, and the protocol states plainly that it is *"worth spending 100 times
more effort on the response design than collecting 100 times more sample units."* That settles the
sizing anxiety running through Searches 21, 40, 41 and 47: our 250-750 point budget is not the
problem. **Point quality is.**

**2. IT CORRECTS THE P3 PLAN DIRECTLY.** The plan states Unsure responses are "EXCLUDED from
estimation, never coerced". The protocol says the opposite:
> "Low confidence assessment units, however, should NOT be excluded from the analysis, and
> secondary labels in uncertain cases should NOT be purposefully used to decrease the number of
> cases with disagreement between the reference classification and the map, but rather should be
> used as a measure of uncertainty of reference classification."

So: record primary + alternate + a confidence flag, keep every unit in the analysis, and use the
uncertain ones to MEASURE reference uncertainty. It also names the abuse to avoid - using alternate
labels to make the map look better - which is exactly the temptation the 77.5% -> 87.1% NLCD swing
(ID 78) creates.

**3. A STRUCTURAL FLAW IN OUR NDVI REFERENCE, STATED BY THE PROTOCOL:**
> "if the source of reference data is the same as the source of classification data... geolocation
> errors in the resulting map will be UNDERESTIMATED / NOT EVALUATED BY DESIGN."

Our NDVI+CHM reference is derived from the *same imagery* the model classifies. Therefore
**geolocation error is invisible in every NDVI-scored number we have** - not poorly measured,
structurally unmeasurable. C-CAP, being independent imagery, is the only reference that can see it.
A new and specific defect, distinct from the correlated-thematic-error problem of Search 38.

And the protocol adds that geolocation impact is greatest for high-resolution mapping (<30 m - we
are 7.5-60 cm) and that **"fragmented classes and items with a vertical structure are typically the
most affected"**. Fragmented, vertical: that is a description of urban tree crowns.

**4. THE CORRELATED-ERROR FIX HAS A CONCRETE FORM.** Correcting sensitivity/specificity assumes
conditional independence, and testing that assumption "requires a gold standard reference dataset
as a SUBSET of the main reference dataset to determine if there is a correlation between the
classification errors and the main reference dataset." So: a small near-gold-standard core inside
the ordinary sample. That is the disciplined version of the negative-control idea from Search 38,
and it is what makes the whole correction defensible.

**5. VINDICATIONS AND CALIBRATIONS.**
* Latent class analysis IS named as the model-based route when no gold standard exists (Foody 2010,
  2012) - but described as **"the subject of research"**, not settled practice. That is the fair
  calibration of the Search 37 retraction: not wrong, but research-grade.
* Radoux & Bogaert 2020 (ID 163) is cited here - our Search 38 finding is protocol-endorsed.
* Stehman 2022 (ID 100) and Xing & Stehman 2024 (ID 101) are both cited for interpreter variance -
  already in our tracker from Search 14, and the protocol prefers **interpenetrating subsampling**
  precisely because it avoids repeat interpretation.
* McRoberts 2018 (ID 189, new) shows majority-interpretation bias grows with FEWER interpreters and
  GREATER CORRELATION among them. A single interpreter is the limiting case - and is our plan.
  The protocol's preferred alternative is the **consensus interpretation approach**: independent
  labels first, then discussion of disagreements to consensus.

### Search 52 - CEOS PROTOCOL, SECTION 2.5 (CHANGE MAPS), READ - ID 190
The protocol addresses our architecture directly, and cautions against exactly what we do.

**1. IT RECOMMENDS MAPPING CHANGE INDEPENDENTLY OF MAPPING LAND COVER.**
> "Ideally, the land cover change mapping should be addressed **independently** from the land cover
> mapping to avoid the impact of classification error propagation."

And the caution is explicit about our method:
> "caution needs to be exercised when monitoring land cover change based on **post-classification
> comparison** of annual or multi-temporal maps, since differencing maps with misclassification
> errors (e.g., 20% error in each map) leads to the **erroneous detection of land cover change**."

Our pipeline is post-classification comparison, and our per-year error is in exactly that 20-30%
range. This is the rare-class trap of Search 49 restated as community guidance, and it is the
protocol-level version of He et al. 2024 (ID 176, Search 44) recommending direct temporal
segmentation. **Two independent sources now say our change architecture is the one to avoid.**

**2. THE STRATIFICATION FIX IS SPECIFIC AND WE ALREADY HOLD THE PAPER.**
> "Omission errors in the maps used for stratification might have a significant impact on precision
> of area estimates for these small land cover change classes, which is somewhat mitigated by...
> splitting large sampling strata into **sub-strata, targeting areas of potential omission errors**
> (Olofsson et al., 2020)."

That is ID 169, already in our tracker from Search 41. For us the omission-prone sub-stratum is
concrete and known: the **5-15 m height band** and **suburban/ornamental context**, which hold 53%
of missed pixels and 8/8 of the inspected missed stands. This is the most specific P3 design
guidance the loop has produced.

**3. THE PERMANENT-VS-TEMPORARY QUESTION IS IN THE PROTOCOL.** Stehman & Foody 2019 (ID 71,
already ours) is cited for exactly the choice Search 41 derived from forest inventory: *"a single,
permanent set of sample units observed each year, and a different sample for each annual change
estimate, with both approaches having their advantages for different estimation objectives."*
Our Search 41 recommendation is protocol-supported - but so is the alternative, and the choice
again depends on Q69 (accuracy study or area study).

**4. AGGREGATE THE TRANSITIONS.** Rather than validating every transition type, report accuracy for
AGGREGATED transitions - "forest to any class" (loss) and "any class to forest" (gain). For a binary
canopy product that is simply canopy->non-canopy and non-canopy->canopy, which is what we want
anyway; useful confirmation that we need not stratify by transition type.

**5. A NEW INSTRUMENT FOR A QUESTION STATE HAS CARRIED OPEN (ID 190, Pontius et al. 2017).**
The protocol recommends estimating Pontius's transition metrics **from the reference sample** and
comparing them to the same metrics **from the map**. The metrics: number of change incidents; the
number of distinct classes a location takes across all time points; and the flow matrices.

**The second metric is a flicker measure.** Computing it on both the sample and the model gives the
first principled test of whether our year-to-year instability is real change or model noise -
something nothing in the pipeline currently distinguishes (Q7, open since the flicker work). It
uses the P3 sample we are already planning, so it is nearly free.

**6. AND OUR HARD FLOOR IS A RECOGNIZED GENERAL PROBLEM, NOT OUR FAILURE.**
> "For historic land cover change assessments, the data being used for mapping... are often **the
> only source of reference data**."

That is STATE's King 2000/2002 position exactly, stated by the protocol as a general condition of
historic change assessment. Worth knowing when writing up: it is a limitation of the field, not a
defect of this project.

### Search 53 - DIRECT CHANGE MAPPING FROM ONE LABELLED YEAR - IDs 191-192
Search 52 left Q74 looking like a dead end: the protocol says map change DIRECTLY, but direct
change detection needs labelled bitemporal CHANGE pairs, and we have none and cannot afford them.
**That objection is removed.**

**STAR / ChangeStar (ID 191, Zheng et al. 2024, IJCV - peer-reviewed).** Trains a change detector
from **single-temporal labels alone**, by constructing pseudo-bitemporal pairs from unpaired
labelled images so that change supervision is generated from ordinary semantic labels. Its stated
motivation is precisely our constraint - labelling change regions in bitemporal high-resolution
pairs is prohibitively expensive.

| what STAR needs | what we have |
|---|---|
| single-date semantic labels | the 2020 hand-labelled year |
| unpaired labelled images | 2020 crops across the city |
| NO labelled change pairs | correct - we have none |

**So the architecture the protocol recommends is reachable from the assets we already hold.** That
closes a loop opened two iterations ago: Search 44 (He 2024) and Search 52 (CEOS) both said
post-classification comparison of 20-30%-error maps manufactures change; this says the alternative
is trainable without new labels.

**Do not treat it as settled.** Three cautions:
1. STAR is built for **object** change (buildings) on satellite imagery. Canopy is fragmented,
   fuzzy-edged and seasonally variable - the pseudo-pair construction assumes objects appear and
   disappear cleanly, which crowns do not.
2. Pseudo-bitemporal pairs are drawn from the SAME acquisition, so the model never sees the
   radiometric shift between eras that Searches 15-31 spent thirty iterations establishing as our
   real problem. It solves the label shortage, not the domain shift - the two would have to be
   composed (e.g. STAR pairs plus FOSMix-style frequency augmentation, ID 145).
3. It would need our 2020 labels to be good, and Search 39 (ID 165) says hand-drawn crowns inflate
   measured performance - so the training signal carries the correlated-error problem in with it.

**And the taxonomy to check ourselves against (ID 192, Peng et al. 2025, The Photogrammetric
Record).** Six label-efficient change-detection schemes - semi-supervised, weakly supervised,
self-supervised, active learning, few-shot, unsupervised - with systematic comparisons. Worth
reading before adopting STAR, because our constraint is not simply "few labels" but an unusual
shape: **one labelled DATE, zero labelled CHANGE, seventeen unlabelled acquisitions**. Something
cheaper may fit better, and this is the map for finding out.

**Where the modelling side now stands.** Two architectures are on the table and they are not
exclusive:
* **A. Fix the per-year masks** (style/frequency augmentation, DSBN, WiSE-FT, tuned ERM) and keep
  differencing them - incremental, uses existing code, but the protocol says the differencing step
  itself manufactures change.
* **B. Train a direct change detector from 2020 labels** (STAR family) - matches protocol guidance,
  needs no new labels, but is unproven for canopy and does not by itself address era shift.
The honest read is that B addresses the architectural criticism and A addresses the domain
criticism, and the project probably needs both.

### Search 54 - WEAK TEMPORAL SUPERVISION - ID 193
Search 53 said STAR solves our label shortage but not our domain shift, and that the two would have
to be composed. **This method composes them itself, and it fits our asset list better.**

**The mechanism (ID 193, Bou et al. 2026, preprint).** Uses *additional temporal observations of an
existing single-temporal labelled dataset, with no new annotations*, on two assumptions:
* pairs from the **SAME location across dates** predominantly contain **no real change**;
* pairs from **DIFFERENT locations** synthesise **change examples**.

We hold precisely those inputs - one labelled year plus seventeen unlabelled acquisitions of the
same city - and STAR ignores the second entirely.

**Why this is the best modelling-side fit the loop has produced.** A same-location cross-era pair
teaches the model: *these two images look very different, and yet nothing changed.* That is exactly
the sensor/era **invariance** that Searches 15-31 spent thirty iterations identifying as the core
problem. **The radiometric shift stops being a nuisance to normalise away and becomes the training
signal for invariance.** One mechanism, both problems - which Search 53 concluded would need two.

**BUT THE ASSUMPTION IS GAP-DEPENDENT, AND OUR GAPS ARE LONG.** "Predominantly no change" holds
over short intervals and fails over decades. Taking 2-4% point-level canopy turnover per year:

| gap | @2%/yr | @4%/yr | verdict | our pairs |
|---|---|---|---|---|
| 1 yr | 2% | 4% | SAFE | 2019-2020, 2021-2022 |
| 2 yr | 4% | 8% | SAFE | 2015-2017, 2020-2022 |
| 3 yr | 6% | 12% | SAFE | 2013-2016, 2017-2020 |
| 4 yr | 8% | 15% | marginal | 2005-2009 |
| 8 yr | 15% | 28% | marginal | 2005-2013 |
| 13 yr | 23% | 41% | **violated** | 2000-2013 |
| 20 yr | 33% | 56% | **violated** | 2000-2020 |

**So the design writes itself:** train the invariance on SHORT-gap pairs, where the no-change
assumption is safe, and *deploy* across the long gaps. That is attractive because our short-gap
pairs are also our cross-source pairs - 2019(King)/2020(CoE), 2020(CoE)/2021(King),
2016(Snoh)/2017(CoE) - so the training material spans agencies and radiometric clusters while
remaining genuinely unchanged on the ground. **The 2017 matched pair (iteration 13) is the extreme
case: zero temporal gap, maximum sensor difference - the perfect weak-supervision example.**

**Honest limits.** Preprint, January 2026. Demonstrated on FLAIR and IAILD (buildings/land cover in
France), not canopy - so Q76's fuzzy-crown objection from Search 53 applies here too. The
"different locations = change" synthesis has the same object-centric flavour that suits buildings
better than crowns. And the turnover rates above are our own estimates, not measured (Q50 again).

**Modelling-side summary after 42 iterations.** Three routes, honestly ranked for our constraint:
1. **Weak temporal supervision (ID 193)** - uses one labelled year AND the unlabelled archive,
   addresses label shortage and era invariance together. Preprint, unproven on canopy.
2. **STAR / ChangeStar (ID 191)** - peer-reviewed IJCV, uses the labelled year only, does not
   address era shift; would need composing with frequency-domain augmentation (ID 145).
3. **Keep differencing per-year masks** and fix them individually - incremental, uses existing
   code, but both CEOS and He 2024 say the differencing step itself manufactures change.

### EMPIRICAL - TURNOVER MEASURED (Q50 / Q78) - 2026-08-19 - `phase4_qc_turnover.py`
The top queue item was not a search. Two designs were sized on a guessed turnover rate; this
measures it. Instrument: **C-CAP hi-res 2016 vs 2021** - same product, same producer, 5-year gap,
and independent of our model (using our own masks would confound turnover with model instability,
which is the very distinction we want).

**RESULT** (690,432 valid cells, 1/8 decimation):

| partition | share |
|---|---|
| stable canopy | 20.47% |
| stable non-canopy | 68.38% |
| **LOSS** (canopy -> non) | **6.44%** |
| **GAIN** (non -> canopy) | **4.72%** |
| **DISCORDANCE** | **11.16%** |
| net change | **-1.72 pp** |

**1. PAIRED SAMPLE SIZING - the answer survives, barely.** Recomputing Search 41's table at the
measured rates rather than assumed ones:

| n (paired) | ± at measured discordance | resolves 2.6 pp? |
|---|---|---|
| 250 | 4.14 pp | no |
| 500 | 2.92 pp | no |
| **750** | **2.39 pp** | **yes** |
| 1000 | 2.07 pp | yes |

Against Search 41's assumptions at n=750: low (4.0/1.4) gave ±1.65 pp, high (6.0/3.4) gave
±2.19 pp, **measured gives ±2.39 pp**. So reality is slightly worse than our pessimistic case, and
**the existing 750-point budget still works - but with no margin.** Search 41's headline stands and
its comfort does not.

**2. AND THE NUMBER FAILS ITS OWN SANITY CHECK - WHICH IS THE MORE IMPORTANT FINDING.**
C-CAP implies **23.94% of 2016 canopy was gone by 2021**, an annualised loss of **5.33%/yr**.
Compare lit ID 182: 3.5-5.1%/yr is typical **street-tree** mortality, and street trees turn over far
faster than whole canopy. Whole-canopy loss of a quarter in five years would be catastrophic and
locally obvious in a city that has been arguing about its tree code.

**So a large share of the 11.16% discordance is product error and vintage revision, not trees.**
That is Search 49's rare-class trap demonstrated on our own data, and Search 40's Seattle warning
(ID 167 - conflicting canopy values for identical dates) reproduced in miniature: **reference-vs-
reference change is dominated by method, not by trees.**

**Consequences, all of which sharpen earlier conclusions:**
* **Do not use C-CAP 2016 vs 2021 as a change reference.** It cannot support a -1.72 pp claim; the
  noise floor is far above the signal. Q66 (specificity on the UNCHANGED class) is not a refinement,
  it is a precondition.
* **The paired-precision figure above is pessimistic, and that is good news.** A human interpreter
  revisiting the same point is far more self-consistent than two C-CAP vintages, so true discordance
  in a P3 paired sample should be well below 11.16% - meaning the 750-point budget likely has more
  margin than the table shows. But we now know the direction of the correction rather than guessing.
* **Weak temporal supervision (ID 193) is better supported than feared.** At 5 years, 88.8% of
  locations are unchanged even by a noisy reference; the true figure is higher. "Predominantly
  unchanged" holds comfortably at our short-gap pairs, which is exactly the training material
  Search 54 identified.
* **A measured upper bound on turnover is now on record**, so the next person does not have to guess.

### EMPIRICAL - THE TWO REFERENCES DISAGREE ON THE **SIGN** OF CHANGE (Q81) - 2026-08-19
Ran the turnover test on the NDVI references - 2016 Snohomish vs 2021s Snohomish, **same source,
same sensor, same 50 cm GSD, same 5-year window** as the C-CAP pair. Side by side:

| | C-CAP 2016 -> 2021 | NDVI ref 2016 -> 2021s |
|---|---|---|
| loss | 6.44% | 4.34% |
| gain | 4.72% | 6.80% |
| **discordance** | **11.16%** | **11.14%** |
| **NET CHANGE** | **-1.72 pp (LOSS)** | **+2.45 pp (GAIN)** |

**The two references disagree on whether Edmonds gained or lost canopy between 2016 and 2021.**
A 4.17 pp spread, on the sign. The policy question is whether canopy is heading toward 35% by 2036;
neither available reference can say which direction it is currently moving.

**And both land on ~11.1% discordance from completely different failure modes** - which is strong
evidence that each is dominated by its own noise floor rather than by trees:
* **C-CAP** compares two product VINTAGES, so method revision enters as apparent change. Its implied
  5.33%/yr whole-canopy loss exceeds published street-tree mortality (ID 182) and is not credible.
* **The NDVI reference** applies a STATIC ~2016 CHM at both dates, so its height test is identical
  across the pair and the entire change signal comes from greenness - which is phenology-sensitive
  (Search 30). Two Snohomish flights at different times of year would manufacture exactly this.

**So: C-CAP change is dominated by product revision, NDVI change by phenology. Neither measures
trees.** This is Search 40's Seattle finding (ID 167 - conflicting canopy values for identical
dates) reproduced on our own data, and it settles several threads at once:
* the "two references bracket truth" framing (STATE) is too generous for CHANGE - they do not
  bracket, they contradict;
* Q66 (specificity on the unchanged class) is confirmed as a precondition, not a refinement;
* **the P3 human sample is not merely useful, it is the only instrument that could establish the
  sign of change** - which is a much stronger argument for running it than "we should be rigorous".

**A BUG FOUND AND FIXED, REPORTED BECAUSE IT NEARLY PRODUCED A FALSE FINDING.** The first NDVI run
returned 0.97% discordance and 90.56% "stable canopy", which would have looked like a wonderfully
clean reference. It was wrong: `phase4_qc_turnover.py` treated 0 as nodata, which is correct for
C-CAP but **not** for the NDVI references, where 0 means NON-VEGETATED - a real class. Every
non-vegetated pixel was silently dropped, leaving only grass and canopy and inflating the canopy
share from ~33% to ~91%. Fixed with an explicit `--zero-is-data` flag and a comment at the mask,
so the next person meets the trap with a warning rather than a plausible number.

**Design consequence.** Both measured discordances are ~11%, so the paired-precision figure from
iteration 43 (n=750 -> +/-2.39 pp) is unchanged. But its interpretation is now firmer: **that 11% is
mostly instrument noise, not trees**, so a self-consistent human interpreter revisiting the same
point should see far less - and the 750-point budget has more real margin than the arithmetic
suggests. The measurement that would confirm it is the P3 blind-subset (Search 42).

### *** SEARCH 55 - LEAF-OFF. THE ACQUISITION SPEC MAY EXPLAIN THE CENTRAL FINDING *** - ID 194
Went after the acquisition dates - the standing top action - and found something better than dates:
**the acquisition SPECIFICATIONS**, which are published.

**THE TWO SPECS ARE OPPOSITE.**
* **Puget Sound regional orthophoto consortium** (88 participants, King County as lead manager -
  the source of our King County imagery): *"acquisition was to occur during **leaf-off** season
  while ground conditions were free of snow and smoke"*. The 2012 flight was March-May
  *"with the intent of representing leaf-off conditions"*; 2015 was acquired *"in the spring"*.
* **NAIP**: flown *"during the agricultural growing season, or **leaf-on** conditions"*, targeted at
  peak crop growth.

**So our archive mixes leaf-off and leaf-on imagery, and nothing in the pipeline accounts for it.**

**AND IF THE 2020 CITY OF EDMONDS ACQUISITION FOLLOWS REGIONAL PRACTICE, THE CONSEQUENCE IS LARGE:**
our ONE hand-labelled year would have been labelled on imagery **in which deciduous crowns are
bare**. Conifers hold their needles in March-May; deciduous trees do not. That is a *physical*
explanation for a finding the project has treated as a modelling defect:

| observation (STATE) | leaf-off explanation |
|---|---|
| "conifer-only-label blind spot" | deciduous crowns are literally not in the labelling imagery |
| scrub recall .25 vs forest .68 | deciduous scrub bare; conifer forest visible |
| recall .16 at 0-5 m rising to .93 at 30 m+ | short crowns are disproportionately deciduous yard/ornamental |
| 8/8 missed stands suburban, "purple-leaf LOW-NDVI" | purple-leaf ornamentals are deciduous - bare in spring |
| model strength does not move recall (finding 3) | no architecture recovers signal that is not in the pixels |

**Finding 3 is the tell.** Nine years spanning IoU .49-.76 with honest recall pinned at .51-.78 is
exactly what you expect when the limiting factor is not the model but **what the imagery physically
contains**.

**INDEPENDENT SUPPORT FROM THE GREENNESS SCREEN (iteration 18, recomputed against the spec):**

| rank | year | source | GRVI | spec |
|---|---|---|---|---|
| 1 | 2019n | NAIP | 0.1521 | **LEAF-ON** |
| 5 | 2022n | NAIP | 0.0808 | **LEAF-ON** |
| ... | | | | |
| 14 | **2020** | **CoE** | **0.0250** | **labelled year** |
| 15 | 2017 | CoE | 0.0242 | consortium |
| 16 | 2019 | King | 0.0224 | consortium |
| 17 | 2023 | King | 0.0143 | consortium |

**Both NAIP years (spec: leaf-on) sit in the top five of seventeen. The bottom six are all King
County or City of Edmonds - the consortium whose spec is leaf-off. Our labelled year is fourth
lowest of seventeen.** Two independent lines - published specification and measured scene greenness -
point the same way.

**WHAT THIS IS NOT.** It is not proof. Confirmed: the consortium SPEC is leaf-off, and King County
2012 and 2015 were spring flights. NOT confirmed: that the 2020 City of Edmonds acquisition
followed it, or the season of the Snohomish 2016/2021s flights. Colour balance remains confounded
with phenology in the GRVI screen (iteration 18's caution stands). **The per-exposure ACQ_DATE and
UTC_TIME fields exist in King County's photo-centre index layer**, so the dates are recoverable,
not lost - which converts this from hypothesis to fact with one data pull.

**IF IT HOLDS, IT REORDERS THE PROJECT.**
* The blind spot is a DATA problem, not a model problem. No amount of architecture, augmentation,
  domain generalization or foundation-model work recovers deciduous crowns from leaf-off pixels -
  which retrospectively explains why thirty iterations of modelling literature kept concluding that
  model quality was not the constraint.
* The right fix is **labels on leaf-on imagery** - the NAIP years, or Snohomish if leaf-on - not
  better training on 2020.
* Cross-era comparison acquires a new confound: comparing a leaf-off year to a leaf-on year measures
  phenology, not canopy change. **This is very likely the source of the sign disagreement in
  iteration 44** (+2.45 pp NDVI vs -1.72 pp C-CAP).
* The height curve may be substantially a DECIDUOUS-FRACTION curve, since short urban trees skew
  deciduous - which is a second confound layered on iteration 11's suburban/height entanglement.

### *** EMPIRICAL - 2020 SHOWS THE LEAF-OFF SIGNATURE (Q84) *** - 2026-08-19 - `phase4_qc_leafoff.py`
Iteration 45 found the published spec and inferred leaf-off. This tests it in the pixels, with no
species map and no acquisition metadata.

**THE TEST.** Take pixels the 2020 canopy mask calls CANOPY and look at the greenness distribution
inside them. Leaf-on canopy is green: unimodal, positive. Leaf-off canopy is mixed - conifers stay
green, deciduous crowns are bare - so a substantial LOW/NEGATIVE mode appears. The low-greenness
fraction is the signature; NAIP (leaf-on **by specification**) calibrates it.

**RESULT - same canopy mask, same city:**

| | 2020 CoE | 2022n NAIP (**leaf-on by spec**) |
|---|---|---|
| median GRVI over canopy | **+0.0330** | **+0.1226** |
| p25 | +0.0127 | +0.0946 |
| **low-greenness fraction (<0.02)** | **33.02%** | **5.23%** |
| negative fraction | 13.06% | 4.11% |

**A third of everything the model calls canopy in 2020 is not green.** In NAIP it is 5%.

**AND THE OBVIOUS CONFOUND IS ELIMINATED.** The two differ in GSD (7.5 cm vs 60 cm), and coarse
pixels average bare branches with green neighbours, which would inflate the difference. So we
degraded 2020 to 60 cm and recomputed on the same windows:

| 2020 CoE | n | median | low<0.02 | negative |
|---|---|---|---|---|
| native 7.5 cm | 1,046,712 | +0.0330 | 33.02% | 13.06% |
| **degraded to 60 cm** | 16,358 | **+0.0331** | **33.02%** | 13.29% |

**Identical.** Resolution explains none of it. At matched 60 cm, 2020 canopy is a quarter as green
as NAIP canopy and has six times the low-greenness fraction.

**WHAT REMAINS AS AN ALTERNATIVE.** Sensor colour balance - NAIP has different radiometry from a
consortium ortho, and nothing here rules that out. But a **4x difference in median canopy greenness**
is large for colour balance alone, and three independent lines now agree:
1. the published consortium specification (leaf-off, March-May, snow- and smoke-free);
2. the scene-wide greenness ranking (both NAIP years top-5 of 17; the bottom six all consortium);
3. this canopy-conditional test, with resolution controlled.

**Strong evidence, still not proof.** Only the flight date is proof, and it remains recoverable.

**AND THE TEST IS BIASED AGAINST ITSELF.** The canopy mask used to select pixels is a model output
carrying the very blind spot under investigation - if it already omits bare deciduous crowns, the
33% is an UNDER-estimate. A positive result under that bias is stronger than it looks.

**Honest limits:** few windows met the 15% canopy threshold (2 of 16 for 2020, 1 of 16 for NAIP),
so this is indicative rather than a probability sample; thin shadow is not excluded, and leaf-off
flights have low sun angle, so shadow and phenology are correlated (Search 31) and the low mode is
not purely deciduous.

### *** EMPIRICAL - THE SPLIT FOLLOWS THE SPECIFICATION, NOT THE VENDOR *** - 2026-08-19
Iteration 46 left one alternative to leaf-off: sensor colour balance. Four acquisitions from two
programs, same canopy mask, same city:

| year | source | acquisition spec | median GRVI over canopy | low-greenness fraction |
|---|---|---|---|---|
| 2019n | NAIP | **LEAF-ON** | **+0.2745** | **0.00%** |
| 2022n | NAIP | **LEAF-ON** | +0.1226 | 5.23% |
| 2022 | CoE | consortium (**leaf-off**) | +0.0485 | 16.42% |
| 2020 | CoE | consortium (**leaf-off**) | +0.0330 | **33.02%** |

**The separation is clean and it follows the SPECIFICATION.** Both NAIP acquisitions: 0.0% and
5.2%. Both consortium acquisitions: 16.4% and 33.0%. Median canopy greenness differs by up to
**8x** between programs. For colour balance to explain this, two independent NAIP flights and two
independent City of Edmonds flights would have to align with their respective published seasonal
specs by coincidence.

**AND THE WITHIN-PROGRAM VARIATION IS ITSELF EVIDENCE.** 2020 (33.0%) and 2022 (16.4%) are both
City of Edmonds, presumably the same vendor and processing chain, yet differ **two-fold**. A fixed
vendor colour balance does not do that. **A March-May acquisition window does** - early March is
fully bare, late May is substantially leafed out. Same for NAIP: 2019n at 0.0% versus 2022n at
5.2%, consistent with different dates inside a growing season. **Between-program gap large and
consistent; within-program variation consistent with date. That is the signature of season, not
of sensor.**

**THE SAME-YEAR NATURAL EXPERIMENT.** 2022 CoE (16.42%) and 2022n NAIP (5.23%) are the **same
calendar year**, same ground, two acquisitions - and they differ three-fold. Within one year, the
only candidate explanations are season and sensor, and the within-program variation above already
argues against sensor.

**AND THE UNLUCKY PART: 2020 IS THE WORST CONSORTIUM YEAR MEASURED.** Our ONE hand-labelled year -
the mask that teaches every coarse year - has the highest non-green canopy fraction of any
acquisition tested. If leaf-off severity varies with flight date inside the March-May window, 2020
looks like an early-window flight. **We labelled on the barest imagery in the archive.**

**Status of Q84: strong evidence, four independent lines.** Published specification; scene-wide
greenness ranking; canopy-conditional greenness with resolution controlled; and now
spec-aligned separation across four acquisitions from two programs with sensible within-program
variation. **Still not proof** - only a flight date is proof - but the alternative explanations have
been narrowed to one that the data now argues against.

**What this changes, restated plainly.** The project's central empirical finding - a
height-monotonic recall curve with a conifer-only blind spot that no amount of model quality moves -
is very likely a **consequence of labelling on leaf-off imagery**. That is not a modelling problem
and no modelling fix addresses it. The remedy is labels on leaf-on imagery, and the archive already
contains leaf-on years: **2019n and 2022n**, both NAIP, both already scored.

### EMPIRICAL - THE LEAF-ON TEST FAILS, AND IT CORRECTS ME (Q86) - 2026-08-19
Iteration 47 predicted the height staircase would FLATTEN on a leaf-on year if the curve were
substantially a deciduous-fraction artefact. It does the opposite.

**Recall by CHM band, same reference family (C-CAP), deployed thresholds:**

| band | 2022n **LEAF-ON** (NAIP) | 2013 **leaf-off** (King) | 2016 baseline |
|---|---|---|---|
| 0-2 m | **0.0622** | 0.2090 | 0.16 |
| 2-5 m | **0.0636** | 0.1955 | 0.16 |
| 5-10 m | 0.2063 | 0.3869 | 0.36 |
| 10-15 m | 0.4924 | 0.6070 | 0.57 |
| 15-20 m | 0.7466 | 0.7700 | 0.74 |
| 20-25 m | 0.8840 | 0.8562 | 0.83 |
| 30+ m | **0.9853** | 0.9449 | 0.93 |

**The leaf-on year has a STEEPER staircase, not a flatter one.** Low-band recall is three times
WORSE on leaf-on (0.062 vs 0.209 at 0-2 m), and top-band recall is better (0.985 vs 0.945).

**BUT THE TEST IS CONFOUNDED, AND THAT IS THE REAL FINDING.** In this archive, **leaf-on is
perfectly confounded with coarse resolution**: NAIP is the only leaf-on program and it is the only
60 cm program. 2013 is 14.9 cm. A small crown at 60 cm occupies a handful of pixels and is far
harder to detect regardless of season, which predicts exactly the low-band collapse we see.

**So the archive cannot separate season from resolution by comparing years.** There is no leaf-on
fine-resolution acquisition in the whole 18. That is a structural limitation of the dataset, not of
the test, and it means Q86 is **not answerable from existing rasters** - it needs either new
leaf-on fine imagery or a re-inference of a fine leaf-off year degraded to 60 cm.

**AND IT CORRECTS AN OVERSTATEMENT I MADE IN ITERATION 47.** I wrote that the height curve "is very
likely a consequence of labelling on leaf-off imagery". **That went further than the evidence.**
Two claims must be kept apart:

1. **2020 imagery shows a leaf-off signature** - 33% non-green canopy vs NAIP's 0-5%, resolution
   controlled, spec-aligned across four acquisitions. **This stands.** It is a statement about the
   imagery.
2. **Leaf-off labelling CAUSES the height curve** - **this is not established**, and the one test
   available in the archive points the other way while being confounded.

Iteration 47 conflated them. The corrected position: **we have strong evidence about what the 2020
imagery contains, and no evidence that it explains the height staircase.**

**What survives, and it still matters.** Even without the causal claim, leaf-off labelling is a
real problem on its own terms: a third of the canopy in the labelling year is not green, and
whatever else that does, it makes the 2020 mask a poor training signal for deciduous crowns and
makes any leaf-off/leaf-on year-pair comparison a phenology measurement. Those consequences do not
depend on the height curve.

**And the height staircase itself is now better supported than before**, because it survives on
both a leaf-on and a leaf-off year, and earlier (iteration 12, U3) survived inside the both-agree
reference partition. Three different ways of trying to make it go away have failed.

### *** EMPIRICAL - THE SEASON MAP, AND WHY THE NDVI REFERENCE IS "MORE LIBERAL" *** - 2026-08-19
Season-scored the Snohomish acquisitions, whose spec was unknown and which build our NDVI
reference. **Both are clearly LEAF-ON.** The archive now splits cleanly:

| year | source | median GRVI over canopy | low-greenness | read |
|---|---|---|---|---|
| 2019n | NAIP | +0.2745 | 0.00% | **LEAF-ON** |
| 2016 | Snohomish | +0.2079 | 1.95% | **LEAF-ON** |
| 2021s | Snohomish | +0.1623 | 0.58% | **LEAF-ON** |
| 2022n | NAIP | +0.1226 | 5.23% | **LEAF-ON** |
| 2022 | City of Edmonds | +0.0485 | 16.42% | leaf-off |
| 2020 | City of Edmonds | +0.0330 | **33.02%** | **LEAF-OFF** |

**Bimodal and unambiguous:** four acquisitions at 0-5% non-green canopy, two at 16-33%. Nothing in
between.

**AND THIS EXPLAINS A STANDING FINDING.** STATE records that the two references disagree on 15-17%
of pixels and that **the NDVI reference is systematically MORE LIBERAL** than C-CAP
(`ndvi_only` 10-14% vs `ccap_only` 1.9-5.7%). That has been treated as an unexplained property of
the products. It now has a physical cause:

* the **NDVI+CHM reference is built from LEAF-ON imagery** (2016 and 2021s Snohomish);
* the **model is trained on LEAF-OFF labels** (2020 City of Edmonds);
* so the reference sees deciduous canopy the model was never taught to see.

**The reference is not "more liberal". It is looking at trees that have leaves on them while the
model was taught on trees that did not.** That reframes finding 3 from a products dispute into a
phenology mismatch, and it is testable: the disagreement should concentrate on deciduous crowns and
vanish on conifers.

**IT ALSO CORRECTS ME.** In iteration 44 I attributed the NDVI reference's +2.45 pp apparent GAIN
(2016 -> 2021s) to phenology. **Both dates are leaf-on**, so a leaf-off/leaf-on seasonal swing is
not available as the explanation. What survives from that argument is narrower and still true: the
NDVI reference applies a STATIC ~2016 CHM at both dates, so its entire change signal is greenness -
and the two acquisitions do differ in greenness (median +0.208 vs +0.162, a 22% relative gap), so
within-season phenology can still contribute. **But "dominated by phenology" was too strong.**

**A systematic mismatch runs through the whole measurement workstream.** Every honest-recall number
we hold scores a leaf-off-trained model against a leaf-on reference, or against C-CAP, whose season
we have not established. The mismatch is not an occasional confound; it is the default condition of
the evaluation.

**Practical consequences, in order:**
1. **Do not pair 2020 or 2022 (leaf-off) with 2016, 2021s, 2019n or 2022n (leaf-on) for CHANGE.**
   Those comparisons measure phenology. That rules out several of the year-pairs the change product
   would naturally reach for.
2. **Weak-supervision training pairs (Search 54) must be season-matched.** A same-location pair
   labelled "no change" is only a lesson in sensor invariance if both dates are the same season;
   otherwise it teaches the model to ignore real phenological difference.
3. **2016 and 2021s are both leaf-on, same source, same sensor** - which makes them the best
   matched pair in the archive for change, and the iteration-44 result on them (11.14% discordance,
   +2.45 pp) is the most trustworthy change figure we have, thin as it is.

### EMPIRICAL - IT IS A CONTINUUM, NOT A BINARY (corrects iteration 49) - 2026-08-19
Scored three more acquisitions - the pre-2013 King County years - and they land **between** the two
groups iteration 49 called bimodal. Nine acquisitions now scored, ranked by canopy greenness:

| year | source | median GRVI over canopy | low-greenness |
|---|---|---|---|
| 2019n | NAIP | +0.2745 | 0.00% |
| 2016 | Snohomish | +0.2079 | 1.95% |
| 2021s | Snohomish | +0.1623 | 0.58% |
| 2022n | NAIP | +0.1226 | 5.23% |
| **2005** | King | +0.1169 | **10.98%** |
| **2000** | King | +0.1000 | **16.86%** |
| **2002** | King | +0.0737 | **13.58%** |
| 2022 | City of Edmonds | +0.0485 | 16.42% |
| 2020 | City of Edmonds | +0.0330 | **33.02%** |

**Iteration 49 said "bimodal and unambiguous, nothing in between". That was drawn from six
acquisitions and is now wrong.** The King County years occupy the middle - 11 to 17% - and the
distribution is a **continuum**.

**Which is what a March-May acquisition window actually predicts.** Flights spread across that
window give a gradient: fully bare in early March, substantially leafed by late May. A binary
leaf-off/leaf-on label was always the wrong model of the archive; the data says phenology varies
continuously across acquisitions.

**THE USEFUL REFRAME: this is a per-year PHENOLOGY INDEX, computed from the imagery, needing no
dates.** That is more valuable than a binary classification would have been:
* **year-pairs should be matched on the SCORE**, not on a leaf-off/leaf-on class. {2016, 2021s} at
  1.95% and 0.58% are well matched; {2020, 2022} at 33.0% and 16.4% are NOT, despite both being
  City of Edmonds and both nominally leaf-off.
* it gives a continuous covariate for the change model rather than a categorical one;
* it is computable for every acquisition without recovering a single flight date.

**TWO THINGS THIS DOES NOT CHANGE.**
1. **2020 is still the extreme.** At 33.0% it is nearly double the next-barest acquisition, and it
   remains our only hand-labelled year. "We labelled on the barest imagery in the archive" stands,
   and is now quantified against nine comparisons rather than three.
2. **2000 and 2002 - the "hard floor" years - are mid-range on phenology** (16.9%, 13.6%), not
   extreme. Their difficulty is resolution and missing NIR, not season. Worth knowing: it removes
   one candidate explanation for their poor recall and leaves the others standing.

**Caveat that grows with the continuum reading.** Sensor and vendor differ across these groups, and
colour balance remains an alternative explanation for part of the spread. The continuum reading is
more robust to that than the binary was - a vendor effect would produce clusters by program, and
what we see instead is King County straddling the gap between NAIP/Snohomish and City of Edmonds.
But it is not eliminated, and only flight dates would eliminate it.

### EMPIRICAL - PHENOLOGY DOES NOT PREDICT RECALL - 2026-08-19
Three more acquisitions scored. **Twelve of eighteen now have a phenology index**, ranked by the
fraction of canopy that is not green:

| rank | year | source | median GRVI | low-greenness |
|---|---|---|---|---|
| 1 | 2019n | NAIP | +0.2745 | 0.00% |
| 2 | 2021s | Snohomish | +0.1623 | 0.58% |
| 3 | 2016 | Snohomish | +0.2079 | 1.95% |
| 4 | 2022n | NAIP | +0.1226 | 5.23% |
| 5 | 2009 | King | +0.1222 | 8.47% |
| 6 | 2007 | King | +0.0732 | 8.51% |
| 7 | 2005 | King | +0.1169 | 10.98% |
| 8 | 2002 | King | +0.0737 | 13.58% |
| 9 | 2022 | City of Edmonds | +0.0485 | 16.42% |
| 10 | 2000 | King | +0.1000 | 16.86% |
| 11 | **2013** | King | +0.0455 | **22.46%** |
| 12 | **2020** | City of Edmonds | +0.0330 | **33.02%** |

**THE NEGATIVE RESULT THAT MATTERS: the index does NOT predict honest recall.**

| year | low-greenness | honest recall vs C-CAP |
|---|---|---|
| 2002 | 13.58% | .5069 |
| 2000 | 16.86% | .6303 |
| 2016 | 1.95% | .6844 |
| **2013** | **22.46%** | **.7094** |

Pearson r = **+0.03** (n=4) - no relationship, and if anything the sign is *positive*: **2013 is the
second-barest acquisition scored and has the HIGHEST honest recall of the live years, while 2016 is
nearly leaf-on and scores lower.**

**This is a third independent strike against the causal story** from iterations 45-47 (already
withdrawn in iteration 48):
1. the height staircase does not flatten on a leaf-on year (iteration 48, confounded by GSD);
2. the archive is a continuum, not the clean leaf-off/leaf-on split the story assumed (iteration 50);
3. and now: **cross-year phenology and cross-year recall are uncorrelated.**

**What survives, stated precisely.** The imagery finding stands and is now measured across twelve
acquisitions: **2020 is the barest year in the archive by a wide margin (33.0%, nearly 1.5x the next
worst), and it is our only hand-labelled year.** That is a real and quantified problem for the
LABEL SET. What is NOT supported is that phenology explains the recall differences BETWEEN years -
the data says it does not.

Those are compatible: leaf-off labelling could still bias WHAT the model learns to call canopy
(a systematic, all-years effect) while contributing nothing to why 2013 scores better than 2002
(a between-years effect). The first is untested; the second is now tested and negative.

**A DATA-QUALITY FLAG FOUND IN PASSING.** 2009 shows p90 = +0.63 and p95 = +0.77 for canopy
greenness. A GRVI of 0.77 requires the red channel to be near zero, which is not plausible
vegetation - it suggests channel saturation or a colour-processing anomaly in that acquisition.
2009 is currently unused in the live QC set, but this should be checked before it is.

### *** EMPIRICAL - THE INDEX IS MOSTLY RADIOMETRY, NOT PHENOLOGY (major self-correction) ***
2026-08-19. Four more King County years scored, and they break the interpretation I have been
building since iteration 45.

**Sixteen of eighteen acquisitions, ranked by fraction of canopy that is not green:**

| year | src | canopy non-green | | year | src | canopy non-green |
|---|---|---|---|---|---|---|
| 2019n | NAIP | 0.00% | | 2022 | CoE | 16.42% |
| 2021s | Snoh | 0.58% | | 2000 | King | 16.86% |
| 2016 | Snoh | 1.95% | | 2013 | King | 22.46% |
| 2022n | NAIP | 5.23% | | 2015 | King | 31.22% |
| 2009 | King | 8.47% | | 2020 | CoE | 33.02% |
| 2007 | King | 8.51% | | **2021** | King | **64.32%** |
| 2005 | King | 10.98% | | **2023** | King | **65.53%** |
| 2002 | King | 13.58% | | **2019** | King | **90.65%** |

**THE SANITY CHECK FAILS AT THE TOP.** 2019 King shows **90.65% of canopy pixels not green, with a
NEGATIVE median GRVI (-0.0118)**. Edmonds sits in the Puget Sound lowland - Douglas fir, western red
cedar, western hemlock. **A leaf-off flight here should still show large amounts of green, because
the conifers keep their needles.** Ninety percent non-green canopy is not credible as phenology.

**AND THE EXTREME YEARS ARE THE ONES WE ALREADY IDENTIFIED AS A DISTINCT RADIOMETRIC ERA.**
2019, 2023 and 2021 King are exactly the three lowest scene-wide greenness values found in
iteration 18, and 2017/2019 were the nearest-neighbour pair in iteration 11 that Kam identified as
the **EagleView** era. The index's extremes track the radiometric clustering, not a seasonal
calendar.

**SO THE HONEST READING IS: this index measures CANOPY GREENNESS, which conflates phenology with
sensor colour balance, and at the extremes radiometry dominates.** It is not a phenology index. I
have been calling it one since iteration 50 and that was wrong.

**WHAT THIS DOES TO THE LEAF-OFF LINE OF ARGUMENT (iterations 45-51):**
* **Iteration 47's central claim is substantially weakened.** I argued the split "follows the
  SPECIFICATION, not the vendor" from four acquisitions. With sixteen, the most extreme values
  belong to a single vendor era, which is the vendor explanation I claimed to have ruled out.
* **The published specifications still stand** - the consortium does specify leaf-off, NAIP does
  specify leaf-on. That is documentary fact and unaffected.
* **What is no longer supported is using canopy greenness as the measurement of it.** The NAIP and
  Snohomish years being greenest is consistent with leaf-on, but it is equally consistent with
  those programs having different radiometry, and the King EagleView years prove the radiometric
  channel is large enough to dominate.
* **2020 at 33.02% is no longer an outlier** - three King years exceed it, two by a factor of two.
  The iteration-47 line "we labelled on the barest imagery in the archive" is **false as stated**.
  2020 is the barest *City of Edmonds* year and mid-pack overall.

**WHAT SURVIVES, AND IT IS LESS THAN I CLAIMED.** A real, measured fact: **canopy greenness varies
enormously across the archive - 0% to 91% non-green - and nothing in the pipeline accounts for it.**
Whether that variation is season, sensor, or both, it is a large per-acquisition covariate that
affects any NDVI- or greenness-based reference, any change comparison, and any weak-supervision
pairing. That conclusion is robust to the cause.

**And the diagnostic value is intact even though the label was wrong:** matching year-pairs on this
score is still the right move, because what matters for a change comparison is that the two
acquisitions render canopy similarly - regardless of whether the difference is leaves or gain
settings.

### EMPIRICAL - RECALL DOES NOT TRACK CANOPY RENDERING (Q96) - 2026-08-19
Ten live-scored years now overlap the rendering index - enough for a real test rather than the
n=4 gesture of iteration 51.

| year | non-green canopy | recall | | year | non-green canopy | recall |
|---|---|---|---|---|---|---|
| 2019n | 0.00% | .6475 | | 2005 | 10.98% | .6323 |
| 2021s | 0.58% | .6818 | | 2002 | 13.58% | .5039 |
| 2016 | 1.95% | .5937 | | 2000 | 16.86% | .6274 |
| 2022n | 5.23% | .6541 | | 2013 | 22.46% | **.7072** |
| 2007 | 8.51% | .6575 | | 2015 | 31.22% | .6192 |

**Pearson r = -0.057, t = -0.16 on 8 df. No relationship whatsoever.**

Canopy rendering varies **thirty-fold** across these years - 0.00% to 31.22% non-green - and recall
moves within a narrow .50-.71 band with no trend. The best-scoring year (2013, .7072) is the
second-barest-rendering; the greenest-rendering years (2019n, 2021s, 2016) sit in the middle and
below.

**This closes the leaf-off line of inquiry, and it closes it negatively.** Iterations 45-52 built,
then progressively dismantled, an argument that leaf-off imagery explains the project's central
finding. The dismantling is now complete on four independent grounds:
1. the height staircase **steepens** on a leaf-on year rather than flattening (iteration 48);
2. the archive is a **continuum**, not the clean split the argument assumed (iteration 50);
3. the extreme values are **radiometric era, not calendar** - 90% non-green canopy is not credible
   in a conifer region (iteration 52);
4. and now: **recall is uncorrelated with canopy rendering across ten years** (r = -0.06).

**The stronger conclusion this supports: the model does not key on greenness.** That is worth
stating plainly because it has a second consequence nobody has drawn - **it undercuts the premise
of the NDVI+CHM reference itself.** That reference defines canopy as NDVI >= 0.2 AND height >= 2 m.
If the model's detections are insensitive to a thirty-fold swing in scene greenness, then model and
reference are keying on **different features**, and their 15-17% disagreement is not a dispute about
where trees are - it is two instruments measuring different things. That is a sharper version of
the "definition dispute" reading, and it predicts the disagreement should be largely irreducible.

**WHAT THIS LOOP GOT WRONG, AND WHAT IT GOT RIGHT.** Wrong: seven iterations (45-51) on a causal
story that the data does not support, including two claims I had to withdraw outright. Right: the
loop killed its own hypothesis with its own measurements rather than accumulating support for it -
four separate tests, each of which could have confirmed it and none of which did. The residue is
worth keeping: **canopy rendering varies 0-91% across the archive and nothing accounts for it**,
which remains true and unexplained regardless of cause.

**A DISCREPANCY THAT MUST BE RESOLVED BEFORE ANY OF THESE NUMBERS IS QUOTED.** The recall values
above come from the live `qc_indep_report.csv` column and **disagree with the figures in STATE** -
2016 reads .5937 here against STATE's .6844; 2013 reads .7072 against .7094; 2002 reads .5039
against .5069. The small ones look like rounding or threshold differences, but 2016 differs by nine
points. They are internally comparable to one another, so the correlation stands - but the absolute
values are not safe to quote outward until the two sources are reconciled.

### CORRECTION - THE "DISCREPANCY" WAS MY EXTRACTION ERROR (Q97) - 2026-08-19
Iteration 53 reported that `qc_indep_report.csv` disagrees with STATE by nine points on 2016 recall
and warned that **no absolute recall figure was safe to quote**. That was a false alarm and it was
my fault. Retracting it in full.

**WHAT ACTUALLY HAPPENED.** The CSV is keyed on THREE dimensions, not one:
* `ref` - which reference (`ndvi_ref_*`, `ccap_*_hires_lc`, `ccap_*_hires_lc_snohfull`)
* `canopy_def` - `forest_only` / `forest_wetland` / `forest_wetland_scrub` (or `canopy_only` for
  the NDVI reference)
* `prob` - which model raster, including baseline vs corrected

My iteration-53 extraction deduplicated on `(year, prob)` and took whichever row came first. For
2016 that was `ref=ndvi_ref_2016.tif, canopy_def=canopy_only` -> **.5937, which is the NDVI-reference
number STATE also quotes as ".594"**. Every other year happened to come back as C-CAP/`forest_only`.
**I mixed two references and two canopy definitions in one correlation table.**

**THE DATA IS CONSISTENT.** Restricting to `ref=ccap_*_hires_lc` (not snohfull) and
`canopy_def=forest_wetland`, the CSV reproduces STATE exactly: 2013 .7094, 2000 .6303, 2015 .6222,
2002 .5069. **STATE and the CSV agree on every year present. There is no integrity problem, and the
absolute recall figures ARE safe to quote.**

**A REAL THING THE INVESTIGATION SURFACED.** There are two C-CAP variants in the live rows, and they
differ materially: `ccap_2016_hires_lc` vs `ccap_2016_hires_lc_snohfull` gives 2000 .6303 vs .6749
and 2013 .7094 vs .7395 - **three to four points, purely from reference extent.** Both are marked
live. Any figure quoted outward must name which variant it used, and STATE's numbers correspond to
the non-snohfull one.

**THE CORRELATION, REDONE ON A CONSISTENT SLICE (n=7):**

| year | non-green canopy | recall (C-CAP, forest_wetland) |
|---|---|---|
| 2019n | 0.00% | .6499 |
| 2021s | 0.58% | .6851 |
| 2022n | 5.23% | .6564 |
| 2002 | 13.58% | .5069 |
| 2000 | 16.86% | .6303 |
| 2013 | 22.46% | .7094 |
| 2015 | 31.22% | .6222 |

**Pearson r = -0.132, t = -0.30 on 5 df.** Still no relationship.

**So iteration 53's CONCLUSION survives its own broken table.** The headline - recall does not track
canopy rendering, and therefore the model does not key on greenness - holds on the corrected,
consistent slice. The numbers changed; the answer did not. That is the good case for an error: the
finding was robust to it. But the table as published in iteration 53 was wrong and should not be
reused.

**WHAT I SHOULD HAVE DONE.** Inspected the CSV schema before extracting from it. A file with `ref`
and `canopy_def` columns is telling you it holds multiple incommensurable series; I treated it as
one series keyed on year. The generalisable lesson for this loop: **when a QC file carries
qualifier columns, the qualifiers are the schema, not metadata.**

### EMPIRICAL - THE EVALUATION FOOTPRINT HAS NEVER BEEN PINNED TO THE CITY - 2026-08-19
Chasing the two live C-CAP variants (iteration 54) turned up something larger than a labelling
question.

**THE TWO REFERENCES ARE NOT TWO VERSIONS OF THE SAME AREA.**

| raster | size | extent (UTM 10N) | area | canopy share |
|---|---|---|---|---|
| `ccap_2016_hires_lc` | 7431 x 5952 | 7.4 x 6.0 km | 44.2 km2 | 26.9% |
| `ccap_2016_hires_lc_snohfull` | 117603 x 64276 | **117.6 x 64.3 km** | ~7,560 km2 | **66.1%** |

`snohfull` is **the whole of Snohomish County**, not a fuller rendering of Edmonds. Its 66% canopy
share against the clip's 27% is the giveaway: it is dominated by rural forest.

**AND THE CLIPPED REFERENCE COVERS ONLY HALF THE EVALUATED FOOTPRINT.**

| | extent | area |
|---|---|---|
| model raster (2013) | 7.6 x 10.7 km | 80.8 km2 |
| C-CAP clip | 7.4 x 6.0 km | 44.2 km2 |
| **overlap** | | **41.8 km2 = 52% of the model footprint** |

The clip's northern edge is N 5297858; the model raster reaches N 5301429. **About 3.6 km of the
model's northern extent has no clipped-C-CAP coverage at all**, and every headline recall figure is
therefore computed on roughly the southern half of the area the model actually runs over.

**WHICH VARIANT IS RIGHT DEPENDS ON A QUESTION NOBODY HAS ASKED.** Two readings, and they point
opposite ways:
* **The clip is correct** and the model raster is an over-generous bounding box; `snohfull` inflates
  recall (.6303 -> .6749 on 2000) by adding easy rural conifer forest that is not Edmonds. This is
  the more likely reading, given the 66% canopy share.
* **The clip is too small** and is silently excluding real city area from every evaluation.

**THE FILE THAT SETTLES IT ALREADY EXISTS AND HAS NEVER BEEN USED FOR THIS.** `City Boundry/Edmonds
Boundry.shp` is in the repo. **Neither reference is clipped to the city boundary**, and the
evaluation footprint has never been defined as "Edmonds". Everything we report is implicitly scoped
to whichever rectangle a given raster happens to cover.

**Why this matters beyond tidiness.** The deliverable is a statement about a CITY - canopy percent
for Edmonds, tracked against a municipal goal. An area-based figure is only meaningful relative to a
stated area, and ours is currently "the intersection of whatever rectangles were available". The
4-point recall gap between the two C-CAP variants is not noise or reference error; it is a
**spatial-sampling difference**, and it is the same size as several of the effects this loop has
spent iterations chasing.

**Concrete fix, cheap:** clip every reference and every prob raster to `Edmonds Boundry.shp`, mark
one C-CAP variant canonical and the other superseded, and re-run the QC. That makes every figure a
statement about Edmonds rather than about a bounding box, and it removes a 4-point ambiguity from
the headline numbers.

### *** EMPIRICAL - THE CANONICAL REFERENCE OMITS 20% OF EDMONDS (Q99/Q100) *** - 2026-08-19
Read `City Boundry/Edmonds Boundry.shp` and overlaid it on the rasters. Q100 is answered, and the
answer is the bad one.

| | area | covers of the city |
|---|---|---|
| **City of Edmonds** | **24.65 km2** | 100% |
| model raster (2013) | 80.8 km2 box | **100.0%** (reaches 0.5 km beyond) |
| **`ccap_2016_hires_lc` (canonical)** | 44.2 km2 box | **80.0% - 19.71 km2** |

**The canonical C-CAP reference stops 3.06 km short of the city's northern edge and omits
4.94 km2 - one fifth of Edmonds.** Every headline recall and precision figure in
`qc_indep_report.csv`, and every number quoted in STATE, is computed on **80% of the city**, with
the northern fifth silently excluded.

**The model is not the limitation - the reference is.** The model raster covers 100% of the city
and then some. The evaluation footprint is smaller than the deliverable footprint purely because of
how the reference was clipped.

**AND THE OMITTED FIFTH IS WHERE THE MODEL DOES BETTER.** Recall on 2000 rises .6303 -> .6749 and on
2013 .7094 -> .7395 when scored against `snohfull` instead. `snohfull` adds both the missing
northern city strip and a great deal of non-Edmonds rural forest, so the 4-point gain cannot be
attributed to the city strip alone - but the direction is consistent and the omission is certain.
**Our headline numbers are very likely understating citywide performance**, and by an amount
comparable to several effects this loop has spent iterations chasing.

**IT ALSO TOUCHES THE POLICY COMPARISON.** The canopy-fraction figures underpinning the
29.5% (C-CAP) vs 37.7% (NDVI reference) dispute - and the comparison against a 32.4% baseline and a
35% goal - are computed on this same partial footprint. A canopy PERCENTAGE is a ratio over a stated
area; ours has been a ratio over 80% of the city without that being said anywhere.

**THE FIX IS CHEAP AND ALREADY POSSIBLE.** `snohfull` covers the entire county, so it contains the
missing northern strip. Clip `snohfull` to `Edmonds Boundry.shp`, use that as the canonical C-CAP
reference, mark the current clip superseded, and re-run the QC. That produces, for the first time,
**numbers that are statements about Edmonds** rather than about a rectangle - and it removes the
4-point variant ambiguity at the same time.

**What this does NOT invalidate.** Relative comparisons across years all used the same footprint, so
year-to-year rankings, the recall-by-height staircase, the reference-disagreement work and the
rendering index are unaffected in direction. What changes is the **absolute** level of every
citywide figure, and the fact that they can now be stated as being about the city.

### *** EMPIRICAL - THE CITY-CLIPPED REFERENCE CHANGES THE HEADLINE NUMBER *** - 2026-08-19
Built `ccap_2016_edmonds.tif` by clipping the county-wide C-CAP to `Edmonds Boundry.shp`
(`Scripts/phase4_build_ccap_city.py`). First reference in this project whose footprint is the
deliverable's footprint: 24.65 km2, 5825 x 9122 @ 1 m.

**RESULT:**

| footprint | share of city | C-CAP 2016 canopy |
|---|---|---|
| old rectangle (what everything has used) | ~80% + non-city area | **29.5%** (STATE) |
| city ∩ south of the old clip's north edge | 81.5% | **32.30%** |
| **WHOLE CITY** | **100%** | **36.05%** |

**The omitted northern fifth is 52.58% canopy against the evaluated south's 32.30% - a difference
of +20.28 pp.** The omission was not merely a smaller sample. **It was a strongly biased one**, and
it removed the most forested part of Edmonds from every figure the project has produced.

**THIS UNDERCUTS A THREAD THAT HAS RUN FOR TWENTY ITERATIONS.** The "references disagree by 8.2 pp"
finding - C-CAP 29.5% against the NDVI reference's 37.7%, which drove iterations 28, 29, 44 and the
whole *which reference is right* line - **was comparing two different footprints**:
* C-CAP's 29.5% came from a rectangle covering ~80% of the city, missing its most forested fifth;
* the NDVI reference's 37.7% was computed over the Snohomish imagery extent, which the catalog
  records as covering **66.7%** of the city.

**Neither was citywide, and neither was the same area as the other.** Properly clipped, C-CAP 2016
gives **36.05%** - within 1.7 pp of the NDVI reference's 37.7%, not 8.2 pp away. **A large part of
what we have been calling a definitional dispute between references may simply be a footprint
mismatch.**

**AND THE POLICY-RELEVANT NUMBER MOVES A LONG WAY.** The comparison this project ultimately feeds -
a 32.4% baseline and a 35%-by-2036 goal - has been set against a C-CAP figure of 29.5%. Scoped to
the actual city, C-CAP 2016 reads **36.05%**. That is a 6.5 pp shift from footprint alone, **two and
a half times the size of the entire decadal policy effect** this loop computed in iteration 28.

**CAVEATS, AND THEY ARE NOT SMALL.**
* This is C-CAP's opinion, not ground truth. C-CAP hi-res carries ~84% regional overall accuracy and
  was never validated at single-pixel scale (ID 77) - and the same document says it should be used
  as a screening tool for local decisions.
* One reference, one year. No uncertainty interval attached.
* The canopy definition is C-CAP's forest + forested-wetland classes, which is not the same
  definition a municipal canopy goal uses - and iteration 1 of the P3 assessment already flagged
  that we have never written our own definition down (Q1, still open).
* **This does not mean Edmonds "has 36% canopy".** It means the reference we have been using says
  36.05% when asked about the whole city instead of four fifths of it.

**BLOCKED: the change comparison cannot yet be made citywide.** Only the 2016 county-wide C-CAP is
on disk; there is no `ccap_2021_hires_lc_snohfull.tif`. Until that is acquired, the properly-scoped
figure exists for 2016 alone and no citywide C-CAP change can be computed.

**Every stratified design in the P3 plan inherits the old bias.** Strata built on the old footprint
were drawn from a sample missing the most forested fifth of the city. That has to be redone against
the city-clipped reference before any sampling is executed.

### IN FLIGHT - RE-SCORING FIVE YEARS ON THE CITY FOOTPRINT (Q105) - 2026-08-19
Launched the re-score that iteration 57's new reference makes possible. **Result not yet in** - the
job exceeded the foreground limit and is running in the background; reporting it next iteration
rather than guessing at it.

**The design, which is the part worth recording now.** Same prob rasters, same deployed thresholds,
same decimation, same canopy codes - **only the reference footprint differs**:
* ref A = `ccap_2016_hires_lc.tif` - the old rectangle, 80% of the city, missing the forested north
* ref B = `ccap_2016_edmonds.tif` - clipped to `Edmonds Boundry.shp`, 100% of the city

**Any delta is therefore purely footprint**, with no confound from threshold, model version or
canopy definition. Years covered: 2000, 2002, 2013, 2015, 2017. The 2013 row doubles as a check -
it should reproduce the published .7094 on ref A, which validates the harness before its ref-B
numbers are believed.

**The prediction, stated before the result so it can be scored honestly.** The omitted north is
52.58% canopy against the south's 32.30%, and forest is where this model performs best (recall .93
at 30 m+ against .16 below 5 m). **So citywide recall should come out HIGHER than every published
figure**, by a few points. If it comes out lower, something is wrong with either the clip or my
reading of the north/south split, and that would need investigating before anything else.

**Why it matters that this is read-only.** The script writes nothing to `qc_indep_report.csv`. The
project's QC record stays as it is until Kam decides whether the city footprint becomes canonical -
which is a scoping decision, not a technical one, and it changes every number the project has
published.

### EMPIRICAL - THE FOOTPRINT ERROR BARELY MOVES RECALL (Q101/Q105) - 2026-08-19
Re-score complete. **My iteration-58 prediction was directionally right and badly wrong on
magnitude**, and the reason is instructive.

| year | old rec | CITY rec | delta | old pre | CITY pre | delta |
|---|---|---|---|---|---|---|
| 2000 | .6293 | .6453 | **+0.0160** | .7759 | .7788 | +0.0029 |
| 2002 | .5050 | .5236 | **+0.0186** | .8399 | .8387 | -0.0012 |
| 2013 | .7085 | .7072 | -0.0013 | .8549 | .8435 | -0.0113 |
| 2015 | .6221 | .6296 | +0.0075 | .8833 | .8857 | +0.0024 |
| 2017 | .7781 | .7775 | -0.0005 | .8082 | .8189 | +0.0107 |

**HARNESS VALIDATED.** On the old reference the script reproduces all five published figures:
2013 .7085 vs .7094, 2000 .6293 vs .6303, 2002 .5050 vs .5069, 2015 .6221 vs .6222,
2017 .7781 vs .7784 - every one within a thousandth or two, the expected decimation difference.

**I predicted citywide recall "should come out HIGHER... by a few points". It moves by -0.001 to
+0.019, mean +0.008.** Three of five years rise, two fall trivially. **The per-year accuracy figures
are essentially robust to the footprint error.**

**AND THAT RESOLVES Q101 CLEANLY.** The .6303 -> .6749 gap on 2000 between the old clip and
`snohfull` is now decomposed:
* **+0.016** from the genuinely missing city area
* **+0.029** from non-Edmonds rural county forest

**About two thirds of that gap was land outside Edmonds.** Scoring against `snohfull` would have
inflated recall with ground the deliverable does not cover. **The old clip was the better of the two
available references, not the worse one** - which reverses the implication I drew in iteration 55.

**THE PRECISE LESSON, AND IT IS WORTH GENERALISING.** Iteration 56 raised the alarm that headline
numbers were computed on 80% of the city. That was true. But the consequence splits sharply by
statistic type:

| statistic | effect of the footprint error |
|---|---|
| **canopy FRACTION / area** | **large - 29.5% -> 36.05%, a 6.5 pp shift** |
| recall, precision | **negligible - under 2 pp, mostly under 1** |

**Because recall is CONDITIONED on reference canopy**, adding more canopy of similar detectability
barely moves it. **The canopy fraction is a RATIO OVER THE AREA**, so the omitted area changes it
directly - and the omitted fifth was 52.6% canopy against the south's 32.3%.

So: **footprint errors are devastating for area statistics and nearly harmless for accuracy
statistics.** Iteration 56 was right to raise it and wrong to imply it contaminated everything. The
accuracy work of the whole measurement programme stands; only the area figures needed rescoping -
which is exactly the number that feeds the policy comparison.

**Scoring my own prediction.** I wrote it down before the run specifically so it could be checked,
and it failed on magnitude. The failure was informative: I reasoned "the added area is forest, the
model is good at forest, so recall rises" and neglected that recall's denominator grows with its
numerator. A conditional statistic does not respond to adding more of what it is conditioned on.

### *** EMPIRICAL - THE REFERENCE GAP IS REAL, AND BIGGER ON COMMON GROUND (Q103) *** - 2026-08-19
Compared C-CAP and the NDVI+CHM reference on **identical cells** for the first time: city boundary
AND C-CAP valid AND NDVI-ref valid.

**COVERAGE WITHIN THE CITY**

| | area | share of city |
|---|---|---|
| city | 24.65 km2 | 100.0% |
| C-CAP (city-clipped) | 24.63 km2 | **99.9%** |
| NDVI reference | 16.44 km2 | **66.7%** |
| **common** | **16.44 km2** | **66.7%** |

**THE RESULT**

| footprint | C-CAP | NDVI ref | gap |
|---|---|---|---|
| each on its own | 36.07% | 42.28% | +6.21 pp |
| **COMMON CELLS** | **31.31%** | **42.29%** | **+10.98 pp** |

**The gap is LARGER on common ground, not smaller.** 10.98 pp, against the 8.2 pp that has been
quoted from mismatched footprints.

**WHICH REFUTES MY ITERATION-57 READING, AND BY THE EXACT ERROR I HAD JUST DIAGNOSED.** Three
iterations ago I concluded that citywide C-CAP (36.05%) sits "within 1.7 pp of the NDVI reference's
37.7%", and wrote that "a large part of what we have been calling a definitional dispute may simply
be a footprint mismatch." **That comparison was itself a footprint mismatch** - C-CAP measured
citywide against an NDVI figure measured over two thirds of the city. One iteration after
identifying this failure mode, I committed it.

**Why it fooled me:** C-CAP reads 36.07% citywide but only **31.31%** on the NDVI's footprint. The
Snohomish imagery covers the *less forested* two thirds of Edmonds, so restricting to it drops
C-CAP by ~4.8 pp while leaving the NDVI figure unchanged. The two errors happened to cancel into a
plausible-looking 1.7 pp.

**PER-PIXEL AGREEMENT ON COMMON GROUND**

| | share |
|---|---|
| both canopy | 27.40% |
| both non-canopy | 53.80% |
| C-CAP only | 3.91% |
| **NDVI only** | **14.89%** |
| **disagree** | **18.80%** |

**18.80% disagreement, higher than the 15-17% on record**, and **NDVI-only exceeds C-CAP-only
roughly four to one** - which confirms the "systematically more liberal" finding on properly
matched ground rather than dissolving it.

**WHAT THIS SETTLES.**
* The reference disagreement is **real, not a footprint artefact.** Twenty iterations of reasoning
  about it were not wasted.
* It is **larger than believed**: ~11 pp on canopy fraction, 18.8% per pixel.
* The asymmetry is stark and unexplained: the NDVI reference calls canopy on **3.8x** as much
  disputed ground as C-CAP does.
* And **iteration 49's phenology explanation for that asymmetry survives** - the NDVI reference is
  built from leaf-on Snohomish imagery, C-CAP's season is unknown (Q90, still open). That remains
  the best available account of why one reference sees so much more canopy than the other.

**Method note for anyone reading later:** any two area figures in this project must be checked for
common footprint before they are differenced. This is now the third distinct instance
(iterations 55, 57, 60) where a footprint mismatch produced a wrong conclusion.

### *** WHAT C-CAP HI-RES ACTUALLY IS (Q90) *** - 2026-08-19
Attacked C-CAP's season two ways: its class histogram on our own city footprint, and its official
InPort documentation. Neither gives a season - but together they characterise the reference far
better than we had it, and one detail reframes several earlier results.

**1. IT IS NOT A LAND-COVER CLASSIFICATION. IT IS A CANOPY PRODUCT WEARING THE C-CAP LEGEND.**
Class histogram over the city-clipped 2016 raster:

| code | class | share |
|---|---|---|
| 11 | Mixed Forest | 35.76% |
| 2 | High Intensity Developed | 34.06% |
| 5 | Developed Open Space | 18.22% |
| 21 | Open Water | 5.43% |
| 12 | Scrub/Shrub | 3.47% |
| ... | 8 minor classes | <1.1% each |

**Deciduous Forest (9): zero pixels. Evergreen Forest (10): zero pixels.** All tree cover is
class 11. There is also **no Low or Medium Intensity Developed** in a city that is overwhelmingly
single-family residential - "High Intensity Developed" at 34% is doing duty as *impervious*.

The documentation confirms it: the final product attributes are **"Upland Tree (Forest),
Scrub/Shrub, and Background"** at 1 m. Thirteen legend codes appear, but the product is really
canopy / impervious / open space / water.

**Consequence for our QC:** the three `canopy_def` variants are nearly meaningless here.
`forest_only` and `forest_wetland` differ by Palustrine Forested Wetland at **0.30%** of the city -
which is exactly why 2013 scores .7072 vs .7094 across them. Only `forest_wetland_scrub` differs
materially, because it adds Scrub/Shrub at 3.47%. We have been reporting three definitions where
the data supports about one and a half.

**2. C-CAP CANOPY INCLUDES OVERHANG, AND IS HEIGHT-INFORMED.** Per InPort, canopy was formed by
*"combining the upland forest class with the **impervious under canopy** class"*, and *"a digital
surface model (DSM) derived from the stereo imagery was used to determine vegetation heights"*.

Two things follow that we had wrong:
* **C-CAP counts canopy overhanging roads and roofs.** It is a canopy-COVER product, not a
  land-cover product - so the long-standing worry that C-CAP "counts the lawn and roof between yard
  trees as forest" (STATE's suburban over-count hypothesis) is at least partly backwards: the
  impervious-under-canopy class exists precisely to attribute overhang to canopy.
* **Both references are height-informed.** Ours uses NDVI + a lidar CHM; C-CAP uses spectral +
  a photogrammetric stereo DSM. So the 10.98 pp gap (iteration 60) is **not** "spectral versus
  structural" - both use height. That removes the easiest explanation for it.

**3. A CONCRETE MECHANISM FOR C-CAP BEING CONSERVATIVE ON DECIDUOUS.** If C-CAP's height comes from
stereo matching on regional aerial imagery, and that imagery is leaf-off spring (the Puget Sound
consortium spec, ID 194), then **bare deciduous crowns are poor stereo targets** - little texture,
see-through structure - so their DSM height is under-recovered and canopy under-called. That is a
physical mechanism for the 3.8:1 asymmetry of iteration 60, and it does not require C-CAP to have a
different *definition* at all.

**4. AND THE SEASON IS NOT CONTROLLED - WHICH IS ITSELF THE ANSWER TO Q90.** InPort states
acquisition dates vary by location "**based on the latest date of available imagery**". C-CAP
hi-res is built opportunistically from whatever recent imagery exists; **season is not a design
parameter**. So:
* C-CAP cannot be assumed leaf-on or leaf-off - it is uncontrolled;
* **the 2016 and 2021 vintages may differ in season**, which is a direct mechanism for
  iteration 43's implausible result (11.16% discordance implying 5.33%/yr canopy loss, far above
  published street-tree mortality). Uncontrolled season between vintages would manufacture exactly
  that.

**Net:** Q90 has no clean answer because the product has no clean season. That is worse than either
answer would have been for change detection, and it strengthens the iteration-43/44 conclusion that
**C-CAP-vs-C-CAP change is not a usable change signal.**

### *** EMPIRICAL - THE SUBURBAN OVER-COUNT HYPOTHESIS IS REFUTED (Q108) *** - 2026-08-19
Tested STATE's load-bearing claim that C-CAP inflates canopy by counting lawns and roofs between
yard trees. C-CAP's own height came from a photogrammetric stereo DSM; our CHM is 3DEP lidar -
**independent height sources**, so this is a fair test. 95% of the city has CHM coverage.

**HEIGHT DISTRIBUTION OF PIXELS EACH REFERENCE CALLS CANOPY**

| CHM height | C-CAP | NDVI ref |
|---|---|---|
| 0-1 m | 0.16% | 0.01% |
| 1-2 m | 0.40% | 0.07% |
| 2-3 m | 1.23% | **5.07%** |
| 3-5 m | 6.01% | **14.01%** |
| 5-10 m | 17.10% | 22.94% |
| 10-20 m | 25.19% | 23.47% |
| **20+ m** | **49.91%** | 34.43% |

**C-CAP canopy below 2 m: 0.56%.** If C-CAP were counting lawn and roof between yard trees, a large
share of its canopy would sit at low lidar height. **It does not - 99.44% of C-CAP canopy is above
2 m by an independent height source.** The hypothesis is refuted.

**AND THE TRUTH IS THE OPPOSITE SHAPE.** C-CAP is **conservative and skewed tall**: 75% of its
canopy is above 10 m, half above 20 m. The NDVI reference is the **liberal** one, with 19.08% of its
canopy in the 2-5 m band against C-CAP's 7.24%.

**SO THE REFERENCE DISPUTE IS ABOUT SHORT VEGETATION, NOT SUBURBAN LAWNS.** That is a specific,
checkable claim replacing a vague one, and it follows from how each reference is built:
* the **NDVI reference** counts anything with NDVI >= 0.2 AND height >= 2 m - which sweeps in tall
  shrubs, hedges and blackberry thickets;
* **C-CAP** separates **Scrub/Shrub** as its own class (3.47% of the city) and reserves canopy for
  "Upland Tree (Forest)".

Adding C-CAP's scrub to its canopy closes roughly a third of the 10.98 pp gap (31.31% + 3.47% =
34.8% against 42.29%), so short vegetation is a large part of the disagreement but not all of it.

**THIS REFRAMES A CENTRAL PROJECT FINDING.** STATE records that 8/8 inspected missed stands were
suburban, and attributes the gap to C-CAP "definitionally over-counting leafy suburbs (NOT a model
error)". **The visual grounding was right; the attribution was wrong.** Those stands are suburban,
and C-CAP is calling canopy there on ground that independent lidar says is genuinely over 2 m tall.
**They are real misses, not reference error.** The comfortable half of the "the gap splits into
reference error plus real under-detection" reading loses its support.

**What still stands from iteration 61.** C-CAP being tall-skewed is equally consistent with (a) its
definition excluding short vegetation, and (b) its stereo DSM under-recovering height on short or
bare-deciduous crowns. This test cannot separate those - both produce the same signature - so Q109
survives intact.

**Two claims down in two iterations.** Iteration 61 showed C-CAP deliberately includes
impervious-under-canopy overhang; this shows its canopy is essentially all genuinely tall. The
"C-CAP over-counts suburbs" story was wrong in both of its mechanisms.

### *** EMPIRICAL - THE "UNMEASURABLE BAND" IS ALMOST ENTIRELY TALL (Q111) *** - 2026-08-19
Phase 2 splits the model's C-CAP misses into *real miss* (both references agree it is canopy) and
*unmeasurable* (the references disagree). Iteration 62 refuted the assumption underpinning that
split. This tests it against **3DEP lidar, independent of both references**.

**LIDAR HEIGHT OF THE "UNMEASURABLE" MISSES**

| height | share |
|---|---|
| 0-2 m | **4.63%** |
| 2-3 m | 2.82% |
| 3-5 m | 16.96% |
| 5-10 m | 37.40% |
| 10-20 m | 26.19% |
| 20+ m | 12.01% |

**95.37% of the "unmeasurable" band is 2 m or taller by independent lidar.** Reclassifying those as
real miss moves the split from 68.2% / 31.8% to **98.5% real miss / 1.5% genuinely ambiguous**.

**So the band is not unmeasurable. It is mostly tall vegetation the NDVI reference rejects** -
presumably for insufficient greenness, since it requires NDVI >= 0.2 - **while lidar says it is
there and C-CAP says it is canopy.** The comfortable reading, that most of the shortfall is
reference disagreement rather than model failure, does not survive an independent height source.

**THE ALTERNATIVE I CANNOT RULE OUT HERE, AND IT IS SERIOUS.** The CHM is height-above-ground and
**includes buildings** - STATE says so explicitly ("HAG includes buildings (fine - RGB flags
non-green)"). So a tall, non-green, C-CAP-canopy pixel could be a **building C-CAP has miscalled**,
not a tree the model missed. The height profile is suggestive but not decisive: the 12% above 20 m
is almost certainly trees, and the 26% at 10-20 m probably is, but the 37% at 5-10 m overlaps
one-to-three-storey buildings squarely.

**The test that settles it is one run away and the data is on disk:** `building_footprints/data.json`
was noted in iteration 26 and never used. Excluding building footprints from the band and re-running
would separate "trees the model missed" from "buildings C-CAP miscalled". **Until that is done, the
98.5% figure is an upper bound on real miss, not a measurement.**

**A DISCREPANCY I AM NOT GLOSSING.** My split (68.2% agree / 31.8% disagree) does **not** reproduce
Phase 2's (35.4% / 64.6%). Three differences explain it and none is an error in either: Phase 2 used
`prob_2016_corrected` while I used the baseline `prob_2016`; Phase 2 ran on the old rectangle while
I ran on the city clip; and I additionally require CHM coverage, which drops 5% of the city. **The
direction of this finding does not depend on which baseline you start from** - whatever fraction is
labelled unmeasurable, 95% of it is tall - but the specific percentages are not comparable to
Phase 2's and should not be quoted as if they were.

**Why this matters for the project's headline.** STATE presents the ~30% shortfall as splitting into
real miss plus an unmeasurable band, and P2 was built to bound that band. If the band is 95% tall
vegetation, **the bound was generous and the model's genuine under-detection is larger than the
project has been assuming.** That is the third finding in three iterations to move in the
uncomfortable direction.

### *** EMPIRICAL - BUILDINGS EXPLAIN OVER HALF THE TALL BAND (Q113) *** - 2026-08-19
Ran the control iteration 63 said was needed. `building_footprints/data.json` - 23,666 GeoJSON
building polygons with per-building heights - has been on disk since February and had never been
used for this. Rasterised and dilated by one cell to cover roof edges and reprojection slop.

**RESULT**

| | cells | share |
|---|---|---|
| "unmeasurable" band | 38,105 | 100% |
| of which TALL (>= 2 m) | 36,341 | 95.37% |
| **tall AND on a building footprint** | **21,044** | **57.91% of tall** |
| tall and NOT on a building | 15,297 | 42.09% of tall |

**Buildings occupy 14.84% of the city (29% dilated) but account for 57.91% of the tall band** - a
roughly four-fold enrichment. The building explanation is not incidental; it is the single largest
component.

**REVISED SPLIT OF THE MODEL'S SHORTFALL**

| component | share |
|---|---|
| real miss - both references agree it is canopy | 68.2% |
| real miss - tall, not on a building | 12.8% |
| **probable C-CAP error - tall, on a building** | **17.6%** |
| short / genuinely ambiguous | 1.5% |
| **REAL MISS TOTAL** | **80.9%** |

**So iteration 63's 98.5% upper bound comes down to 80.9% once buildings are excluded.**

**AND THE TWO FIGURES BRACKET THE ANSWER RATHER THAN COMPETING.** Canopy legitimately overhangs
buildings, and C-CAP folds an **impervious-under-canopy** class into canopy *by design*
(iteration 61). A tall C-CAP-canopy pixel over a roof may be a genuine overhanging crown that the
model missed - a hard case, dark roof under dark foliage - rather than a C-CAP error. So:
* **on-building 17.6% is an UPPER bound on C-CAP error**
* **80.9% is a LOWER bound on real miss**
* **real miss lies between 80.9% and 98.5% of the shortfall**

**Either end of that range demolishes the comfortable reading.** Phase 2 assigned 64.6% of the miss
to an unmeasurable band, implying roughly 35% real miss. **The true figure is at least 81%.** The
model's genuine under-detection is roughly twice what the project has been assuming, and the
"unmeasurable" framing was doing a great deal of unearned reassurance.

**What would close the remaining range.** The distinction is between overhanging canopy over roofs
(real miss, hard case) and roofs miscalled as canopy (C-CAP error). The building layer carries a
`height` attribute per structure - comparing CHM height against BUILDING height on those pixels
would separate them: canopy overhanging a roof sits ABOVE the building height, a miscalled roof
sits AT it. That is one more run on data already loaded.

**Method note.** The one-cell dilation is conservative toward finding buildings, so it inflates the
on-building count and therefore deflates the real-miss lower bound. The bracket is honest in the
direction that matters.

### *** EMPIRICAL - THE RANGE CLOSES: REAL MISS IS ~88-93%, NOT 35% (Q115) *** - 2026-08-19
Rasterised the per-building `height` attribute and compared it against the lidar CHM on the
on-building pixels. **Canopy overhanging a roof sits above the building height; a miscalled roof
sits at it.**

**CHM height MINUS building height, on-building tall-band pixels (n = 12,271):**

| delta | share |
|---|---|
| below roof by >2 m | 1.80% |
| **AT roof (-2 to +1 m)** | **29.77%** |
| +1 to +3 m | 27.59% |
| +3 to +6 m | 15.37% |
| +6 to +12 m | 13.52% |
| +12 m or more | 11.96% |
| **median delta** | **+2.10 m** |

**Two thirds of it sits above the roof.** On a strict reading (>1 m above = overhang), 68.4% is
genuine overhanging canopy the model missed and 29.8% is a probable C-CAP miscall.

**BUT THE BUILDING HEIGHTS LOOK LOW, AND THAT MATTERS.** Median building height is **4.5 m** with
p90 of only **6.0 m**, and `heightScore` medians 0.55. A two-storey house measures roughly 6-8 m to
the ridge, so these read as eaves-height or underestimates. **If heights are ~2 m low, the +1 to
+3 m band is roof rather than overhang** - so the answer must be given under both readings:

| | real miss | C-CAP error | ambiguous |
|---|---|---|---|
| liberal (>1 m above = overhang) | **93.0%** | 5.6% | 1.5% |
| conservative (>3 m above = overhang) | **88.1%** | 10.4% | 1.5% |

**Phase 2 implied real miss of ~35.4%. Both readings put it at 88-93%.** The conclusion is robust to
the building-height caveat, which is the useful thing about computing it twice.

**WHERE THIS LEAVES THE PROJECT'S CENTRAL NUMBER.** Four iterations ago the shortfall was understood
as roughly one third genuine model failure and two thirds unmeasurable reference disagreement. It is
now roughly **nine tenths genuine model failure**. The chain that got there, each step against an
independent measurement:
1. C-CAP does not over-count suburbs - 0.56% of its canopy is below 2 m by lidar (iteration 62);
2. the "unmeasurable" band is 95% tall (iteration 63);
3. buildings explain 58% of that tall band - a real confound, not a footnote (iteration 64);
4. but two thirds of the on-building pixels sit **above** the roofline, so they are overhanging
   canopy the model missed, not roofs C-CAP miscalled (this iteration).

**THE HONEST IMPLICATION IS UNCOMFORTABLE AND SHOULD BE STATED PLAINLY.** The model misses far more
real canopy than the project has been assuming, and a framing that existed to bound the
unmeasurable portion was instead absorbing genuine under-detection. Honest recall does not change -
the shortfall was always there - but **almost none of it is excusable**.

**And it sharpens what the model is actually bad at:** canopy overhanging buildings and roads. That
is the hard case for an RGB model - dark foliage over dark roof, no ground context - and it is
exactly where C-CAP's impervious-under-canopy class is designed to look. It is also a large share of
urban canopy in a city of single-family lots with street trees.

**Caveats carried forward:** building heights are modelled estimates from a 2025-vintage vector
product compared against a ~2016 lidar CHM, so vintage change and modelling error both blur the
split. The direction is robust; the exact percentages are not.

### *** EMPIRICAL - RECALL HALVES ON CANOPY OVER IMPERVIOUS (Q116) *** - 2026-08-19
Split C-CAP canopy by what lies beneath - buildings and the impervious layer versus pervious
ground - and measured the model's recall on each.

| year | recall OVER IMPERVIOUS | recall over pervious | gap |
|---|---|---|---|
| 2016 | **0.3183** | 0.6922 | **-0.374** |
| 2013 | **0.3383** | 0.7683 | **-0.430** |
| 2017 | **0.4570** | 0.8279 | **-0.371** |

**The model's recall roughly halves on canopy overhanging buildings and pavement**, and the effect
is consistent across three years spanning three different sensors and eras - a gap of 0.37 to 0.43
every time. **Canopy over impervious is 17.2% of all C-CAP canopy**, so this is not a corner case.

**THIS IS THE CLEANEST FAILURE MODE THE LOOP HAS FOUND, AND IT IS MORE STABLE THAN THE HEADLINE
METRIC.** Overall honest recall wanders between .50 and .78 across years with no clear driver
(finding 3). The impervious gap sits at 0.37-0.43 in every year tested. **A quantity that stable
across sensor, era and resolution is describing something real about the model rather than about
the imagery.**

**WHAT IT WOULD BE WORTH FIXING.** If the model achieved its pervious-ground recall on
over-impervious canopy too, overall recall on 2016 would rise by
`0.172 x (0.6922 - 0.3183) = 0.064` - **about 6.4 points, roughly a fifth of the entire
shortfall**, from a single named weakness.

**AND IT MAY UNIFY TWO FINDINGS.** Canopy over impervious is street trees and yard trees beside
houses - which are also disproportionately the SHORT, suburban crowns that the recall-by-height
staircase is built on, and the ones in STATE's 8/8 missed suburban stands. **The height staircase
and the overhang deficit may be the same phenomenon seen two ways.** That is directly testable:
recompute recall-by-height WITHIN the pervious-only subset. If the staircase flattens there, height
was a proxy for overhang all along; if it survives, they are independent deficits and both need
fixing.

**WHY THE MODEL WOULD FAIL HERE, MECHANISTICALLY.** Dark foliage over a dark roof or asphalt gives
little contrast at the crown edge, no surrounding ground texture to anchor the segmentation, and -
critically - the training labels come from a 2020 mask that inherits the same weakness. C-CAP finds
these pixels because it has a stereo DSM and an explicit impervious-under-canopy class; our model
has RGB and, for most years, no height channel at all.

**Which suggests the fix is structural rather than more data:** the CHM is exactly the signal that
separates a crown over a roof from the roof itself, and it is already built. The aux-height
experiments (v045/v046) were aimed at grass rejection; **this is a second and arguably better
reason to give the model height.**

### *** EMPIRICAL - TWO INDEPENDENT DEFICITS, AND THEY COMPOUND (Q118) *** - 2026-08-19
Recomputed recall-by-height separately over pervious and impervious ground. The question was
whether the height staircase is the overhang deficit in disguise. **It is not.**

| CHM band | PERVIOUS | n | IMPERVIOUS | n | gap |
|---|---|---|---|---|---|
| 0-2 m | 0.1206 | 1,584 | **0.0262** | 420 | -0.094 |
| 2-5 m | 0.1721 | 18,927 | **0.0282** | 6,878 | -0.144 |
| 5-10 m | 0.3930 | 45,325 | 0.1111 | 16,704 | -0.282 |
| 10-15 m | 0.5753 | 35,584 | 0.3013 | 9,907 | -0.274 |
| 15-20 m | 0.7324 | 34,988 | 0.4375 | 7,058 | -0.295 |
| 20-25 m | 0.8358 | 34,994 | 0.5805 | 5,421 | -0.255 |
| 25-30 m | 0.8902 | 32,680 | 0.6607 | 3,979 | -0.230 |
| 30+ m | **0.9421** | 62,293 | 0.7509 | 4,909 | -0.191 |

**The staircase survives on pervious ground with a spread of +0.82** (0.12 to 0.94), and appears
again on impervious ground with a spread of +0.72. **These are two independent deficits, and they
compound.**

**AND THE OVERHANG PENALTY IS NOT A SHORT-TREE ARTEFACT.** It persists at every height, including
**-0.19 at 30 m and above**. A 30-metre tree over pavement is detected at 0.75 against 0.94 over
grass. Overhang costs the model roughly a fifth to a third of its recall regardless of tree size -
so it cannot be explained away as "short suburban crowns are also over pavement".

**THE MAP OF THE DEFICIT, WHICH IS THE USEFUL OUTPUT.** The model's blind spot is now two-
dimensional and specific:
* short -> bad (0.17 at 2-5 m even over grass)
* over impervious -> bad (a 0.19-0.30 penalty at every height)
* **short AND over impervious -> effectively blind: 0.028**

**That worst cell is the one to act on.** At 2-5 m over impervious the model finds under 3% of what
C-CAP calls canopy - street trees and yard trees beside driveways and houses, the most policy-
relevant canopy in a residential city, and the class a tree ordinance is written about.

**WHAT IT MEANS FOR THE FIXES ON THE TABLE.**
* **Height input (Q119) addresses the overhang axis directly** - the CHM is what separates a crown
  over a roof from the roof - but the pervious-only staircase shows it will not, on its own, fix the
  short-crown axis, because that deficit exists where there is no roof to confuse.
* **Annotation should target the intersection**, not suburban stands generally. STATE's plan calls
  for "3-5 suburban/ornamental sites"; this says the highest-value labels are **short crowns over
  impervious surfaces**, which is a much narrower and more findable target.
* **The two axes have different mechanisms** - resolution and spectral mixing for short crowns,
  contrast and context for overhang - so they plausibly need different remedies, and progress on one
  should not be expected to move the other.

**Caveat.** Both axes are measured against C-CAP, which has its own error and its own
impervious-under-canopy construction; the overhang penalty is partly a statement about where C-CAP
and the model disagree most. The stability across three sensors (iteration 66) argues it is real,
but a human check on the 2-5 m over-impervious cell would settle it - and that cell is small enough
to inspect exhaustively.

### *** EMPIRICAL - NEGATIVE RESULT: THE CORRECTED MODEL'S OVERHANG GAIN IS AN OPERATING-POINT ARTEFACT (Q119) *** - 2026-08-19
Compared `prob_2016` (baseline) against `prob_2016_corrected` (trained on ADD-ONLY labels built
from NIR+CHM) on the **common footprint**, 321,651 C-CAP canopy cells, 17.2% of them over
impervious.

**(a) At the deployed threshold 0.509 it looks like a decisive win:**

| model | recall | over IMP | over PERV | gap | call rate on non-canopy |
|---|---|---|---|---|---|
| baseline (RGB) | 0.6279 | 0.3183 | 0.6922 | -0.3739 | 0.0493 |
| corrected (NIR+CHM) | 0.8533 | **0.5612** | 0.9139 | -0.3527 | **0.1725** |

Over-impervious recall rises 0.24 and the worst cell (2-5 m over impervious) goes 0.028 -> 0.183,
a six-fold gain. **But the call rate on C-CAP non-canopy triples, 4.9% to 17.3%.**

**(b) Re-thresholded to the SAME overall recall, the gain vanishes:**

| model | thr | recall | over IMP | over PERV | gap |
|---|---|---|---|---|---|
| baseline | 0.509 | 0.6279 | 0.3183 | 0.6922 | -0.3739 |
| corrected, matched | 0.835 | 0.6296 | **0.3070** | 0.6965 | **-0.3895** |

**Over-impervious recall goes DOWN, and the gap gets slightly WIDER.** The worst cell recovers to
0.0366 against the baseline's 0.0282 - essentially nothing. And by height band the matched gap is
**worse where it matters most**: -0.076 at 2-5 m, -0.050 at 5-10 m.

**Q119 ANSWERED: NO. The corrected model did not learn about overhang; it moved its operating
point.** Everything the headline comparison shows is explained by calling more canopy everywhere,
which the impervious subset shares in proportion.

**THIS IS A DEPLOY-RELEVANT WARNING, NOT JUST A NEGATIVE RESULT.** A +0.225 recall gain at a fixed
threshold is the kind of number that gets a model deployed. Held at equal recall the corrected model
is marginally **worse** on every axis measured here. **Any future comparison in this project must
match operating points before claiming an improvement** - and none of the year-to-year recall
comparisons in the pipeline currently do.

**THE CAVEAT THAT COULD OVERTURN THIS, STATED PLAINLY.** The corrections were built from NIR+CHM;
the scoring here is against C-CAP. If the corrected labels moved the model toward the NDVI/CHM
canopy definition and away from C-CAP's, it would score worse against C-CAP while being closer to
truth. **This is the it.55 error in a new costume and I am not going to repeat it: the result above
is a statement about agreement with C-CAP, not about truth.** Settling it needs the human-checked
cell (Q120), which is reference-independent. Until then the honest reading is narrower: *the
corrected model's apparent overhang gain is not supported by the reference we scored it on.*

**WHAT STILL HASN'T BEEN TESTED.** Corrected LABELS are not a height INPUT. The v045/v046
aux-height variants put the CHM in as a channel, which is the actual structural fix Q116 pointed at.
That remains untested against the impervious split, and this negative result does not bear on it -
if anything it raises the value, because label correction has now been ruled out as the cheap route.

### *** EMPIRICAL - SHADOW REFUTED AS THE OVERHANG MECHANISM (Q122) *** - 2026-08-19
Liu et al. 2023 (Remote Sensing 15:519, tracker ID 196) reports that **U-Net specifically** suffers
high omission from canopy shadow. That is our architecture and our symptom, so it is a live rival to
the dark-foliage-on-dark-roof contrast story. The two hypotheses make **opposite geometric
predictions**, which makes them separable with data already in hand: building shadow in the northern
hemisphere falls to the NORTH, so shadow predicts a north-side recall deficit, while contrast is
isotropic with respect to the sun.

Bearing from the nearest building pixel for every C-CAP canopy pixel near a building, 2016 baseline:

| | within 10 m (n=135,941) | within 20 m (n=235,295) |
|---|---|---|
| north side (NW,N,NE) | 0.5725 | 0.6326 |
| south side (SE,S,SW) | 0.5371 | 0.6105 |
| **north minus south** | **+0.0354** | **+0.0221** |

**The north side is slightly BETTER, not worse, at both radii. Shadow is refuted in the predicted
direction** - this is not a null result, it is a sign error against the hypothesis.

**THE CONFOUND, AND WHY THE ANSWER SURVIVES IT.** The dominant pattern in the table is not
north-south at all: the four DIAGONAL sectors all score 0.58-0.61 and the four CARDINAL sectors all
score 0.44-0.51, a spread of 0.123 - **five times the north-south effect.** That is almost certainly
a footprint-geometry artefact, not physics: buildings here are axis-aligned rectangles, so a pixel
due north sits off a long wall face while a pixel to the north-east sits in an open corner wedge with
more sky around it. **I am flagging this rather than reading anything into it.**

It does not damage the shadow test, because that test compares **sectors of matched geometric type**:

| matched comparison | north | south | difference |
|---|---|---|---|
| faces (N vs S) | 0.5071 | 0.4401 | **+0.0670** |
| corners (NE,NW vs SE,SW) | 0.6053 | 0.5857 | **+0.0196** |
| control (E vs W) | 0.4678 | 0.4755 | -0.0077 |

North beats south within both geometric types, and the east-west control is flat as it should be.

**WHAT THIS SETTLES.** The over-impervious deficit is **isotropic with respect to the sun**, so it is
structural, not illumination. **That rules out the cheap radiometric remedies** - shadow
compensation, histogram matching, illumination normalisation - and leaves the structural ones the
overhang finding already pointed at: a height channel or a NIR band. Combined with iteration 68
(corrected LABELS do nothing at matched operating point), the remaining candidate list is short and
specific, which is the useful thing about a refutation.

**Caveat.** Aerial survey flights are deliberately flown near solar noon to minimise shadow, so the
shadow effect being tested may simply be small in this imagery rather than absent in principle. The
test rules out shadow *as an explanation for our gap*; it does not rule out shadow mattering for
imagery flown at lower sun. Acquisition times are not in `imagery_stats/imagery_catalog.csv`, which
is why this had to be answered geometrically rather than from metadata.

### LITERATURE + INVENTORY (NOT measured yet) - RELIEF DISPLACEMENT, AND THE ARCHIVE STARTS IN 1936 - 2026-08-19
**Labelled honestly: this iteration establishes a MECHANISM from the literature and an INVENTORY
fact from disk. Neither is a measurement of our data. The empirical test is queued, not done.**

**1. RELIEF DISPLACEMENT IS A REAL, TEXTBOOK DEFECT AND WE HAVE NEVER ACCOUNTED FOR IT (Q123).**
A conventional orthophoto is rectified with a **bare-earth DTM**. The consequence, stated the same
way by every source consulted: *only the BASE of a tree or building is placed in its true position;
everything above ground level is displaced radially from nadir, by an amount proportional to its
height.* Gharibi & Habib 2018 (ID 198) and Chen et al. 2014 (ID 200) both make this explicit.

**Why this is not a footnote for us.** The displacement magnitude is `d = (h/H) * r` - object height
over flying height, times radial distance from nadir. For a 20 m crown at 500 m from nadir on a
3,000 m flight, `d = 3.3 m`. **At our 10 cm King County GSD that is 33 pixels.** The displacement
therefore grows along **exactly the axis our height staircase runs on**, and it is largest for the
tall crowns where we report our best recall.

**It cuts against the staircase rather than creating it.** More displacement means more
mask-versus-reference disagreement, so it should DEPRESS tall-band recall. We measure tall-band
recall as our HIGHEST (0.9421 pervious, 30 m+). **So relief displacement cannot be manufacturing the
staircase - if anything the true height effect is stronger than measured.** That is a useful thing
to have established before testing it.

**Where it could bite hardest is the deliverable, not the accuracy table.** Our 17 acquisitions were
flown as different frame layouts, so **each year carries a different displacement field**. Chen 2014
and the general true-ortho literature are explicit that DTM orthorectification "can lead to spurious
changes when comparing multitemporal images, particularly in areas with buildings and trees."
**That predicts apparent canopy change where none occurred, concentrated on tall crowns and near
buildings - a threat to the 2000-2024 change series that no amount of extra labelling would fix.**

**Coverage check, which is why this counts as a blind spot rather than a parked question:** searching
all 197 tracker rows for `off-nadir`, `view angle`, `BRDF` and `orthorectif` returned **zero**.

**2. THE ARCHIVE HAS TWO ACQUISITIONS OLDER THAN ANYTHING IN THE CATALOG.**
`D:\edmonds-pipeline\Imagery936_king_rgb.tif` and `1998_king_rgb.tif` exist, are mirrored on
`G:\My Drive	reedata\Full_Image\KingCo\`. They appear in **no** `imagery_catalog.csv` row.

> **CORRECTION, same iteration.** I first wrote that these two years "already have crops cut in
> `phase4/crops/`, so something in this project has looked at them before." **That was wrong and I
> withdraw it.** The apparent hits (`EDM_0181936.jpg`, `EDM_0141998.jpg`) are **crown IDs**, not
> years - crops are named `EDM_` plus a seven-digit crown number, so `EDM_0001936` is crown 0001936.
> `phase4/manifest.json` is explicit: all 59,980 crops come from `imagery_year: 2020`, and its
> `high_alpha_years` list starts at 2016. **Nothing in this project has ever looked at 1936 or 1998.**
> The inventory point stands and is in fact stronger - these are wholly untouched files, not
> partially processed ones.
The 2026-08-18 CHATLOG entry (13c) flagged them as "unassessed" alongside 2005/2007/2009/2012/2017/
2019/2021/2023; the middle years have since been scored, **these two have not**.

**A 1936 frame is panchromatic, and that is a different problem, not a harder version of ours.**
Tian et al. 2025 (ID 202) states plainly that **no** existing tree-delineation method works on
panchromatic alone because colour is treated as essential, and bridges the gap with a
**deep-learning colorization step** - a technique absent from all 200 prior tracker rows.
**This CONTRADICTS the framing of our own cross-sensor work**, which has treated the historical
problem as radiometric domain shift between comparable RGB sensors. For a single-band frame the gap
is a **missing modality**, not a shift, and the style-transfer methods in our plan (FDA, FOSMix)
assume matched channel counts and cannot apply. Every greenness diagnostic we have built - GRVI,
the leaf-off signature, the NDVI reference - is simply **undefined** there.

**3. A STALENESS FLAG, MINOR BUT WORTH ONE LINE.** `imagery_stats/imagery_catalog.csv` still carries
the pre-correction `gsd_cm` values (2013 as 14.9 cm) that the 2026-08-18 config fix replaced with
true ground GSD (10.0 cm). The CSV also has no 2002 row although 2002 masks and area figures exist.
**The audit already happened and I am not re-reporting it as new** - the point is only that this one
artefact was not regenerated afterwards, so reading it can re-introduce a corrected error.

### *** EMPIRICAL - 1936 AND 1998 ARE SINGLE-BAND, AND THE FILENAME SAYS OTHERWISE (Q124) *** - 2026-08-19
Opened the two uncatalogued frames. **Both are literally one band**, despite being named
`1936_king_rgb.tif` and `1998_king_rgb.tif`.

| file | bands | grid | mean | p1 | p99 |
|---|---|---|---|---|---|
| 1936_king_rgb.tif | **1** | 18944 x 26880, EPSG:3857 | 230.5 | 69 | **255** |
| 1998_king_rgb.tif | **1** | 18944 x 26880, EPSG:3857 | 125.6 | 76 | 219 |
| 2000_king_rgb.tif | 3 | 18944 x 26880, EPSG:3857 | 89.9 / 106.6 / 105.3 | | |

**THE NAME IS A TRAP, AND THAT IS THE OPERATIONALLY IMPORTANT PART.** Every other `*_king_rgb.tif`
in the pipeline is three-band, and `phase1_preprocess.py` is built around that convention (its
year table lists `2000_king_rgb.tif`, `2002_king_rgb.tif` and so on as `native_file`). Anything that
globs `_king_rgb.tif` and assumes three bands will either crash or silently read band 1 three times
on these two. Confirmed by grep: **`1936` and `1998` appear nowhere in `phase2_data_prep.py`,
`phase4seg/config.py` or `pipeline_config.py`** - they are referenced by no config at all, which is
why the trap has never been sprung.

**THEY SHARE THE 2000 PIXEL GRID EXACTLY** - 18944 x 26880 in EPSG:3857, identical to 2000, while
2013 is 74496 x 105984. Two consequences:
* someone has already **co-registered and resampled them onto the 2000 mosaic grid**, so the hard
  georeferencing work on scanned film may already be done - this is better news than expected;
* but their nominal GSD is therefore **inherited from that grid, not measured from the film**. A
  1936 frame resampled to ~40 cm cells does not carry 40 cm of optical detail. **Do not quote the
  grid spacing as the resolution** - that is the it.70 `gsd_cm` lesson in a new place.

**RADIOMETRY IS POOR IN TWO DIFFERENT WAYS, WHICH MATTERS FOR ANY TRANSFER PLAN.**
* **1936 is clipped at the bright end**: p99 = 255, so at least 1% of the frame is blown to pure
  white with mean 230.5. Detail in bright areas is **destroyed, not merely compressed** - no
  normalisation recovers it.
* **1998 is low-contrast**: p1 = 76 and p99 = 219, using about 143 of 256 levels. That IS
  recoverable by rescaling, so the two years need **different** preprocessing, not one historical
  recipe.

**WHAT THIS DOES TO THE Q124 DECISION.** Combined with Tian 2025 (ID 202), the honest position is
that 1936 is not an extension of the current problem: single band, blown highlights, and an unknown
true resolution. **1998 is the much better candidate** - single band too, but well-behaved
radiometry, and only two years off 2000, which gives a **near-contemporaneous RGB frame on the
identical grid to validate a panchromatic method against.** That is an unusually clean experiment
and it is sitting unused: train or adapt on 1998 single-band, score against the 2000 model's output
where the two overlap in time. **If a panchromatic route cannot reproduce 2000 from a 1998 frame, it
will not survive 1936.**

### *** CORRECTION + EMPIRICAL - THE 1936 FILE IS EMPTY, AND GRVI IS NOT COMPARABLE ACROSS SENSORS *** - 2026-08-19

**1. I WAS WRONG ABOUT 1936. IT CONTAINS NO IMAGE DATA OVER EDMONDS.**
Iteration 71 reported 1936 as "clipped at the bright end, p99 = 255, bright detail destroyed".
**Withdrawn.** Probing nine windows spread across the city, at 1200 px each:

| location | 1936 | 1998 | 2000 |
|---|---|---|---|
| south + centre (6 windows) | **mean 253.0, std 0.00, min = max = 253** | mean 105-141, std 32-44 | mean 78-96, std 38-65 |
| north (3 windows) | **mean 0.0, std 0.00** | mean 99-130, std 4-29 | 2 of 3 are 0 |

**Every window is a constant.** `1936_king_rgb.tif` is a georeferenced **empty shell** - 18944 x 26880
of uniform 253 or 0 fill. The "p99 = 255 clipping" I described was the fill value showing up in a
whole-raster downsample, not blown highlights. **This is not a hard research problem; it is an empty
file**, and the Q124 framing that a 1936 baseline "would roughly triple the temporal span of the
deliverable" is dead. I am striking it rather than softening it.

**THE LIKELY REASON, WHICH ALSO EXPLAINS SOMETHING ELSE.** These are **King County** mosaics, and
**Edmonds is in Snohomish County**, just north of the county line. A 1936 King County survey would
simply not extend this far north, so the mosaic carries fill here. The same boundary shows in 2000:
its northern probes are also all-zero. **That is a second, independent confirmation of the known
northern-coverage gap** - it is a county line, not a random footprint quirk.

**1998 IS REAL, AND IT IS THE ONLY HISTORICAL OPTION.** All nine probes carry genuine image
structure (std 29-44 over most of the city). So the conclusion of it.71 survives in stronger form:
**1998 is not merely the better pilot, it is the only one.** It covers the whole city, sits on the
identical grid to 2000, and is single-band - which still makes it a clean test of a panchromatic
route with a near-contemporaneous RGB control. The prize is smaller than claimed - two extra years,
not sixty - but the methodological test is unchanged and still worth running.

**2. EMPIRICAL - GRVI IS NOT COMPARABLE ACROSS SENSORS, AND THE PROOF IS UNARGUABLE.**
Sampled a 2400 px window over the **same ground** in every acquisition. `frac>.02` is the share of
pixels a naive GRVI vegetation test would call green:

| year | GRVI mean | frac>.02 | | year | GRVI mean | frac>.02 |
|---|---|---|---|---|---|---|
| 2000 King | +0.0875 | 0.8027 | | 2015 King | +0.0171 | 0.2745 |
| 2002 King | +0.0241 | 0.5029 | | 2017 King | -0.0082 | 0.1877 |
| 2005 King | +0.0310 | 0.4782 | | **2019 King** | **-0.0182** | **0.1146** |
| 2007 King | +0.0237 | 0.4016 | | 2021 King | -0.0123 | 0.1344 |
| 2009 King | +0.0848 | 0.6237 | | 2023 King | -0.0061 | 0.1541 |
| 2012 King | +0.1009 | 0.6268 | | 2016 Snoh | +0.1264 | 0.6928 |
| 2013 King | +0.0146 | 0.3463 | | **2019 NAIP** | **+0.1779** | **0.8919** |

**THE DECISIVE PAIR: 2019 King County reads 0.1146 and 2019 NAIP reads 0.8919 - the same year, the
same ground, the same season, differing by 0.78.** That cannot be vegetation, phenology, growth or
loss. It is purely sensor and processing colour balance. **No other explanation is available**, which
is why this pair is worth more than the whole rest of the table.

**AND THE KING COUNTY SERIES DRIFTS MONOTONICALLY.** frac>.02 falls 0.80 (2000) -> 0.35 (2013) ->
0.11 (2019), and GRVI mean crosses from positive to negative around 2017. **Any GRVI-based
diagnostic applied across this series would report a large, steady canopy decline that is entirely a
processing artefact.**

**THIS DAMAGES OUR OWN EARLIER WORK AND I AM SAYING SO.** The leaf-off / canopy-rendering signature
built on GRVI in an earlier iteration compared low-greenness fractions **between years**. Given the
table above, **those cross-year comparisons are not safe** - the between-year variation in the index
itself dwarfs any plausible leaf-on/leaf-off effect. The within-year use (comparing canopy-masked
pixels against the rest of the same image) is unaffected, because the cast is global. **That
distinction is the whole of what survives.**

### *** EMPIRICAL - MOST OF THE CROSS-YEAR RECALL WANDER IS THE OPERATING POINT (Q121) *** - 2026-08-19
One recipe (`_citywide_rgb`), one reference (C-CAP), one footprint (161,052 of 162,829 sample
points, 98.9%), eight years. The only thing varied is whether the operating point is held constant.

| year | recall @ FIXED thr 0.5 | call rate there | recall @ MATCHED call rate 0.30 |
|---|---|---|---|
| 2000 | 0.5303 | 0.2313 | 0.6454 |
| 2002 | 0.5853 | 0.2599 | 0.6541 |
| 2005 | 0.5806 | 0.2298 | 0.7086 |
| 2007 | 0.6915 | 0.2991 | 0.6974 |
| 2009 | 0.6801 | 0.2851 | 0.7052 |
| 2013 | 0.7123 | 0.3046 | 0.7069 |
| 2015 | 0.7130 | 0.2978 | 0.7174 |
| 2021 | 0.5577 | 0.2198 | 0.7155 |
| **SPREAD** | **0.1827** | 0.0847 | **0.0721** |

**Holding the operating point constant removes 61% of the cross-year spread** - 0.1827 down to
0.0721. The mechanism is visible in the middle column: **the same threshold 0.5 calls anywhere from
22.0% to 30.5% of the city canopy**, so a fixed threshold is not a fixed operating point.

**AND WHAT IS LEFT IS INTERPRETABLE, WHICH THE ORIGINAL WANDER WAS NOT.** Finding 3 described a
0.28 spread (.50-.78) "with no clear driver". At a matched operating point the residual has an
obvious structure:

* **2000 and 2002: 0.6454 and 0.6541** - the two oldest and coarsest acquisitions, ~40 cm true GSD;
* **2005 through 2021: 0.6974, 0.7052, 0.7069, 0.7174, 0.7155 and 0.7086** - a spread of **0.020
  across sixteen years, three providers and a four-fold resolution change.**

**That is a much stronger robustness result than this project has been claiming.** Read fairly, the
model is stable to within two points from 2005 to 2021, and the only genuine cross-year effect is a
~6-point penalty at the coarse end. The apparent instability was largely an artefact of comparing
models at thresholds calibrated separately per year.

**Credit, so this is not overclaimed:** the 2026-08-18 CHATLOG entry already showed that a per-year
spread dissolved when the RECIPE was held constant. That run used a fixed threshold of 0.5 - which
is exactly column two here. **This adds the second control, not the first.** The two together
account for most of finding 3.

**ONE ANOMALY, FLAGGED NOT EXPLAINED.** 2007 returns **identical recall at call rates 0.20 and 0.25**
(0.6189 both). That cannot happen with a well-spread probability distribution and indicates a large
mass of pixels sharing one value, so 2007's probability raster is likely degenerate or saturated in
some region. It is also why the cr=0.20 column shows a wider spread (0.1452) than the other three.
**Do not quote the cr=0.20 row until 2007 is understood.**

**WHAT THIS CHANGES DOWNSTREAM.** Every cross-year comparison in the pipeline is thresholded
per-year, so this applies to the canopy AREA series as well, not just recall - and the area series
is the deliverable. **A per-year threshold shift of the size seen here (22% to 30% call rate) is
large enough to manufacture or erase a canopy trend on its own.** That is the same class of error as
the GRVI drift found in it.72, arriving by a different route, and the two would compound.

### *** EMPIRICAL - THE WITHIN-YEAR GRVI CAVEAT HOLDS, EXCEPT IN 2000 (Q131) *** - 2026-08-19
it.72 concluded that cross-year GRVI is unsafe but **within-year** use survives "because the cast is
global". That was an assumption, not a measurement, and a first pass looked like it would fall:
2013's fraction-called-green ranges **0.179 to 0.843 across blocks of the same image**, nearly the
0.78 between-year spread. **But blocks genuinely differ in land cover** - a forested block IS greener
than downtown - so that number alone proves nothing.

**The separator: do the same blocks stay green across years?** Land cover cannot reshuffle in a few
years; a per-frame colour cast can. Per-block rank correlation between acquisitions:

| | mean rank correlation |
|---|---|
| all 28 pairs | +0.666 |
| **excluding 2000** | **+0.730** |
| excluding 2000 and 2005 | **+0.760** |

| acquisition | mean corr. with the others | frac>.02 | block range |
|---|---|---|---|
| **2000 King** | **+0.476** | **0.8446** | **0.142** |
| 2005 King | +0.617 | 0.4767 | 0.570 |
| 2016 Snoh | +0.657 | 0.7049 | 0.454 |
| 2019 NAIP | +0.661 | 0.8729 | 0.257 |
| 2021 King | +0.687 | 0.1854 | 0.700 |
| 2013 King | +0.725 | 0.4441 | 0.664 |
| 2019 King | +0.727 | 0.1862 | 0.748 |
| 2009 King | +0.781 | 0.6681 | 0.498 |

**I WAS TOO QUICK TO DOUBT MY OWN CAVEAT, AND THE MEASUREMENT SAYS SO.** From 2005 onward the block
ranking is stable at **+0.730**, and among the mid-to-late years the pairs run 0.84-0.90
(2009-2013 = 0.895, 2009-2021 = 0.877, 2019-2021 = 0.861). **The within-year spatial variation is
mostly real land cover, so the it.72 caveat holds** - within-year GRVI comparisons are usable.

**THE EXCEPTION IS 2000, AND IT FAILS IN A WORSE WAY THAN A RESHUFFLE.** 2000 calls **84.5% of every
pixel in the city green**, with a block range of only 0.142 (0.789 to 0.932). **The index is
saturated** - it has no dynamic range left to discriminate anything - and its spatial pattern
correlates only **+0.476** with the other years, the weakest of all eight. In 2000, GRVI carries
close to no usable information, within-year or across. 2005 is intermediate at +0.617 and should be
treated as suspect rather than sound.

**TWO INDEPENDENT LINES NOW CONVERGE ON THE PRE-2005 YEARS.** Q121 (it.73) found 2000 and 2002 are
the only years still measurably worse once the operating point is matched, at ~0.65 against
0.697-0.717 for everything from 2005 to 2021. This iteration finds 2000's radiometry is saturated
and its greenness pattern matches no other year. **Coarse resolution and degraded radiometry are
separate defects arriving at the same two acquisitions**, which is a much more specific statement
about where the archive is weak than "older is worse".

**Practical consequence, stated narrowly:** GRVI-derived diagnostics are usable within a year from
2005 onward, unusable in 2000, and unusable across years anywhere without normalisation (it.72).
That is three different verdicts and they should not be collapsed into one.

### *** EMPIRICAL - NORMALISATION CANNOT RESCUE GRVI, AND BRIGHTNESS BEATS GREENNESS (Q130/Q134) *** - 2026-08-19
**The test is chosen so it needs no normalisation implemented.** AUC is **invariant under any
monotone transform** - affine gain/offset (IR-MAD), gamma, histogram matching, quantile mapping are
all monotone. So AUC settles whether a year's problem is *calibration* (fixable) or *lost
information* (not), before spending any effort on IR-MAD.

Discriminating C-CAP canopy from C-CAP non-canopy at 162,829 points:

| acquisition | **AUC GRVI** | AUC brightness | canopy-vs-other separation (SD) |
|---|---|---|---|
| 2000 King | 0.5927 | 0.6333 | 0.057 |
| 2005 King | 0.6941 | 0.7170 | 0.471 |
| 2009 King | 0.7061 | 0.6847 | 0.561 |
| 2013 King | **0.7273** | 0.6881 | 0.429 |
| **2019 King** | **0.5835** | 0.6838 | **-0.045** |
| **2021 King** | **0.5453** | 0.6662 | **-0.007** |
| 2019 NAIP | 0.6893 | 0.6887 | 0.656 |
| 2016 Snoh | 0.6911 | 0.6631 | 0.648 |

**1. I HAD THE WRONG YEARS. 2019 AND 2021 KING ARE WORSE THAN 2000.** I have been treating 2000 as
the damaged acquisition. By information content the two most recent King County years are worse -
AUC 0.5835 and **0.5453**, with canopy-vs-other separation of **-0.045 and -0.007**, i.e. GRVI does
not distinguish canopy from anything else there at all. The monotone drift found in it.72 is not a
harmless shift; **it corresponds to real loss of discriminative signal in the newest RGB years.**

**AND THE VINTAGE CONFOUND ARGUES THE SAME WAY.** C-CAP is 2016, so distance in time should hurt
2000 most and help 2019/2021. **It goes the other way**, which makes the result stronger rather than
weaker.

**THE CONTROLLED PAIR AGAIN: 2019 King 0.5835 versus 2019 NAIP 0.6893.** Same year, same ground.
The difference is the sensor and its processing, not the season or the vegetation.

**2. Q130 AND Q134 ANSWERED, BOTH NEGATIVE.** Because AUC is monotone-invariant, **IR-MAD,
histogram matching and per-year standardisation cannot recover 2000, 2019 or 2021 King GRVI** - the
information is not mis-scaled, it is absent. Normalisation remains worth doing for **cross-year
threshold comparability** (it.72, it.73), but **not as a way to make greenness work in those years**.
That distinction saves implementing IR-MAD for the wrong reason.

**3. THE ACTIONABLE FINDING: BRIGHTNESS IS A BETTER AND FAR MORE STABLE CANOPY CUE THAN GREENNESS.**
Darkness-as-canopy scores **0.663 to 0.717 in every single acquisition** - a range of 0.054 -
against GRVI's 0.545 to 0.727, a range of 0.182. **In the three worst GRVI years brightness beats it
outright**, by 0.041 (2000), 0.100 (2019 King) and 0.121 (2021 King).

**This reframes what a cross-sensor RGB model should lean on.** Greenness is the intuitive canopy
cue and it is the least transferable one here; luminance is unglamorous and it is the one thing
every sensor in this archive agrees on. It also offers a partial explanation for why an RGB U-Net
transfers across these sensors as well as it.73 shows it does - **it is unlikely to be keying mainly
on colour**, which is directly testable and is exactly open question Q98.

**Caveats.** GRVI was never strong here - its best year is 0.7273, which is a weak discriminator by
any standard - so this is a comparison between two mediocre features, not a demotion of a good one.
Both are single-pixel, context-free features, while the model has texture and neighbourhood; these
numbers bound what colour alone can do, not what the model does. And all of it is measured against
C-CAP, with C-CAP's own definition and errors.

### *** EMPIRICAL - THE MODEL IS FAR BETTER THAN COLOUR, AND THE AREA SERIES IS THRESHOLD-COUNTED (Q135, Q132) *** - 2026-08-19
**PARTIAL: 2013 and 2021 still running. Three years reported.**

**1. THE MODEL BEATS EVERY SINGLE-PIXEL COLOUR CUE BY A WIDE MARGIN.**

| year | AUC model | AUC brightness | AUC GRVI | model gain | corr(model, bright) | corr(model, GRVI) |
|---|---|---|---|---|---|---|
| 2000 | **0.8760** | 0.6333 | 0.5927 | **+0.2427** | +0.3148 | +0.1882 |
| 2005 | **0.9134** | 0.7170 | 0.6941 | +0.1964 | +0.5338 | +0.4737 |
| 2009 | **0.9195** | 0.6847 | 0.7061 | +0.2348 | +0.3895 | +0.4745 |

**Context and texture buy roughly 0.20-0.24 of AUC over the best colour feature.** The model is not a
colour detector: its rank correlation with brightness is only 0.31-0.53 and with GRVI 0.19-0.47.

**AND IT LARGELY SURVIVES 2000'S RADIOMETRIC DAMAGE.** it.74/75 showed 2000's colour is saturated
and near-uninformative - GRVI AUC 0.5927, separation 0.057. **The model still reaches 0.8760 there.**
Whatever it is using, it is mostly not the channel that is broken. That is consistent with the
texture-bias reading (ID 207) and it is the strongest robustness evidence this loop has produced.

**2. THE NUMBER THAT REFRAMES EVERYTHING: AUC 0.88-0.92 AGAINST RECALL 0.65-0.72.**
it.73 measured recall of 0.645-0.717 across these years at a matched call rate. **AUC is
threshold-free and lands at 0.876-0.920.** The model's *ranking* of pixels is strong and stable;
what is weak is *where the line is drawn*. **The binding constraint on the reported numbers is
threshold placement, not model quality** - which is exactly what it.73 concluded from the other
direction, arrived at here by an independent route.

**3. Q132 PREMISE CONFIRMED BY READING THE CODE.** `phase3_semantic_dev.py:1722` computes
`canopy_area = total_canopy_px * pixel_area` - **the area series is pixel-counting off a thresholded
binary mask**, with `binary_closing` applied first. Two consequences:
* it is the "map count" estimator that the Olofsson/CEOS protocol already in this tracker exists to
  replace, and it is **fully exposed** to the 22.0%-30.5% per-year call-rate variation of it.73;
* **morphological closing compounds it** - closing fills gaps, so it inflates area by an amount that
  depends on how fragmented the mask is, which itself depends on the threshold.

**`phase4_qc_score.py:83` describes its own threshold source as "the (circular) eval CSV".** The
circularity is already known and documented in the code; what is new is the measurement of how much
it can move (it.73) and the fact that the deliverable inherits it directly.

**THE CONVERGENCE WORTH STATING PLAINLY.** Three independent lines - the operating-point spread
(it.73), the GRVI drift (it.72), and now the AUC-versus-recall gap - all say the same thing: **this
project's model is better than its numbers suggest, and its numbers are dominated by calibration and
by a map-count area estimator.** The remedy is already in the tracker rather than in a new method:
estimate area from a reference sample, not by counting thresholded pixels.

### *** EMPIRICAL - COMPLETE: THE MODEL DOES NOT RELY ON COLOUR, AND 2021 PROVES IT (Q135) *** - 2026-08-19
Completes the previous entry. All five years:

| year | AUC model | AUC brightness | AUC GRVI | model gain | corr(model, GRVI) |
|---|---|---|---|---|---|
| 2000 | 0.8760 | 0.6333 | 0.5927 | +0.2427 | +0.1882 |
| 2005 | 0.9134 | 0.7170 | 0.6941 | +0.1964 | +0.4737 |
| 2009 | **0.9195** | 0.6847 | 0.7061 | +0.2348 | +0.4745 |
| 2013 | 0.9125 | 0.6881 | 0.7273 | +0.2243 | +0.5428 |
| **2021** | **0.9150** | 0.6662 | **0.5453** | **+0.2488** | **+0.0755** |
| **range** | **0.044** | 0.084 | **0.182** | | |

**2021 SETTLES IT.** It is the year where GRVI carries the least information of any acquisition
(AUC 0.5453, separation -0.007) **and** where the model resembles GRVI least (rank correlation
**+0.0755**, essentially zero). **The model's AUC there is 0.9150 - its second best.** A model
relying on colour cannot behave that way. Taken with 2000 - saturated colour, model still 0.8760 -
the conclusion is not an inference from correlations but from two independent extreme cases.

**AND THE MODEL IS MORE STABLE THAN ITS OWN INPUTS.** Model AUC varies by **0.044** across 21 years,
three providers and a four-fold resolution change. Over the same acquisitions GRVI varies by 0.182
and brightness by 0.084. **The network is roughly four times more consistent than the colour
statistics of the imagery it is fed.** That is the cleanest robustness statement this project has,
and it is threshold-free, so no calibration choice is doing the work.

**THE ONE DIP IS RESOLUTION, NOT COLOUR.** 2000 is the only year below 0.91, and it is the coarsest
(~40 cm true GSD against ~10 cm). Its colour is the second-worst, but 2021's colour is worse still
and 2021 does not dip. **Resolution separates the years; colour does not** - which is exactly the
asymmetry the texture-bias hypothesis (ID 207) predicts, and exactly what it.73 found independently
by measuring recall at a matched operating point (2000/2002 ~0.65, everything 2005-2021 within
0.020).

**WHAT WOULD FALSIFY THIS, STATED SO IT CAN BE.** These are AUCs against C-CAP over single sampled
points, so they measure ranking quality, not delineation, and they inherit C-CAP's definition. The
texture reading is a hypothesis consistent with three measurements, **not a demonstration** - ID 208
(2025) argues the texture-bias result itself is an artefact of how cue-conflict stimuli suppress
information. **A channel-ablation or occlusion test on the trained network is still the only thing
that settles Q98**, and nothing here substitutes for it.

**PRACTICAL UPSHOT.** The colour-comparability problems found in it.72, it.74 and it.75 are real but
**they are not the binding constraint on this model** - it already largely ignores the channel they
damage. Effort is better spent on the two things that are binding: **threshold/area estimation
(Q136)** and **resolution at the coarse end**.

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

### *** EMPIRICAL - NOMINAL GSD IS NOT THE RIGHT AXIS; 1998 AND 2005 ARE SEVERELY OVERSAMPLED (Q137) *** - 2026-08-19
**A first attempt was thrown away.** It block-averaged different years by different factors (1, 2, 4)
to reach a common 40 cm, but the downsample factor reshapes the spectrum on its own, so 2005 (f=2)
and 2013 (f=4) were never comparable. **Confound removed: no resampling at all.** Each image is read
at native resolution and scored against **its own** Nyquist. 12 sites, 256 px windows.

| year | nominal GSD | HF share | sd |
|---|---|---|---|
| **1998** (1-band) | 40.1 cm | **0.0010** | 0.0021 |
| **2005** | 20.1 cm | **0.0010** | 0.0008 |
| 2000 | 40.1 cm | 0.0083 | 0.0098 |
| 2002 | 40.1 cm | 0.0138 | 0.0068 |
| **2013** | 10.0 cm | **0.0172** | 0.0095 |
| 2021 | 10.0 cm | 0.0530 | 0.0327 |
| 2015 | 10.0 cm | 0.0587 | 0.0439 |
| 2009 | 20.1 cm | 0.0597 | 0.0278 |
| 2023 | 10.0 cm | 0.0691 | 0.0609 |
| **2007** | 20.1 cm | **0.0770** | 0.0300 |
| 2019 | 10.0 cm | 0.0859 | 0.0579 |

**1. NOMINAL GSD IS A POOR GUIDE TO ACTUAL DETAIL IN THIS ARCHIVE.** **2007 at 20 cm carries 4.5x the
relative sharpness of 2013 at 10 cm** (0.0770 vs 0.0172). The config's `gsd_cm` - already corrected
once for CRS units - is still not measuring what the model can see. **This is the it.71 warning
generalised: it was raised for 1936/1998 and it applies to 2005 and 2013 as well.**

**2. 1998 AND 2005 ARE SEVERELY OVERSAMPLED - HF share 0.0010, essentially no detail at their own
Nyquist.** Their pixel grids are finer than their optics by roughly a factor of two or more. For
1998 this **directly confirms it.71's suspicion**: it was resampled onto the 2000 grid, so its
stated GSD is inherited from that grid rather than measured from the film. For 2005 the finding is
new and unexpected - it is a nominally 20 cm product carrying roughly 40 cm of real detail.

**3. THIS CORRECTS HOW I FRAMED it.77.** I wrote that "the only dip is 2000, and it is the coarsest
year - resolution separates the years." **The direction survives but the axis was wrong.** Sharpness
alone does not predict performance: **2005 is the softest acquisition of all and performs fine**
(AUC 0.9134, matched recall 0.7086), while 2000 is sharper by that measure and performs worst.

**What does line up is ABSOLUTE effective detail - grid spacing and sharpness together.** A soft
image on a 20 cm grid still resolves more ground detail than a soft image on a 40 cm grid. Ordered
that way, 2000 and 2002 sit clearly last: **coarsest grid AND soft for that grid, the only years bad
on both axes**, while 2005 is soft on a grid twice as fine and lands mid-pack. That ordering matches
the it.73 recall ranking and the it.77 AUC ranking.

**STATED AS THE HEURISTIC IT IS.** Turning an HF share into an effective GSD in centimetres would
need a proper MTF or edge-response analysis, which this is not. **The ordering is defensible; any
specific "effective cm" figure is not**, and I am deliberately not writing one down. What the
measurement supports is that two distinct defects - coarse sampling and optical softness - are being
collapsed into one number called `gsd_cm`, and that they do not travel together.

**4. PRACTICAL CONSEQUENCE FOR THE TIER LOGIC.** `tier_of(gsd_cm)` assigns training recipes from the
nominal figure. On this evidence 2005 is tiered as a fine 20 cm year while carrying 40 cm of detail,
and 2013 as the finest tier while sitting closer to 20 cm. **Recipe assignment is therefore keyed to
a quantity that does not measure what it is assumed to measure** - the same class of error the
2026-08-18 CRS-units audit caught, one level further in.

### *** EMPIRICAL - EFFECTIVE RESOLUTION MEASURED: gsd_cm IS WRONG BY UP TO 6x (Q138) *** - 2026-08-19
Automatic edge-response measurement: find strong gradients, take intensity profiles across them,
average into an Edge Spread Function, read the **10-90% rise distance** and multiply by true GSD.
Same 12 sites in every year, so scene content is controlled rather than assumed away.

**A BUG WAS CAUGHT AND FIXED MID-EXPERIMENT, AND IT IS WORTH RECORDING.** The first version used
`np.interp(0.10, e, off)` to find the crossing. **`np.interp` requires its x-array to be increasing,
and a real edge profile is noisy and non-monotonic**, so it returned garbage - five different years
came back at *exactly* 6.70 px, which is the profile's own half-width. **The tell was the
impossible coincidence, not the plausibility of the numbers.** Replaced with an explicit crossing
search walking outward from the profile centre. After the fix all 12 sites resolve in all 11 years,
and well-sampled years land at ~1.3 px rise - the physically expected value.

| year | nominal GSD | rise (px) | **EFFECTIVE resolution** | oversampling |
|---|---|---|---|---|
| **1998** | 40.1 cm | 6.10 | **244.7 cm** | **6.1x** |
| **2000** | 40.1 cm | 2.76 | **110.8 cm** | 2.8x |
| 2002 | 40.1 cm | 1.42 | 57.1 cm | 1.4x |
| **2005** | 20.1 cm | 4.02 | **80.7 cm** | **4.0x** |
| 2007 | 20.1 cm | 1.27 | 25.5 cm | 1.3x |
| 2009 | 20.1 cm | 1.30 | 26.1 cm | 1.3x |
| 2013 | 10.0 cm | 1.37 | 13.7 cm | 1.4x |
| 2015 | 10.0 cm | 1.29 | 12.9 cm | 1.3x |
| 2019 | 10.0 cm | 1.26 | 12.6 cm | 1.3x |
| 2021 | 10.0 cm | 1.31 | 13.1 cm | 1.3x |
| 2023 | 10.0 cm | 1.29 | 12.9 cm | 1.3x |

**EIGHT OF ELEVEN YEARS ARE PROPERLY SAMPLED at 1.26-1.42 px. Three are not, and badly:**
* **1998 resolves at 2.4 METRES** - six times its grid. For canopy work at individual-crown scale it
  is close to useless, which materially weakens the it.72/it.71 case for a 1998 panchromatic pilot.
  **I am revising that recommendation down**: the pilot would be testing a method on an image with
  no crown-scale detail.
* **2005 resolves at 81 cm despite a nominal 20 cm** - four times oversampled, and **coarser in
  reality than 2000's nominal 40 cm.**
* **2000 resolves at 111 cm**, nearly three times its grid.

**AND THIS STILL DOES NOT FULLY EXPLAIN PERFORMANCE, WHICH I SHOULD SAY PLAINLY.** Ordering by
effective resolution puts 2005 (81 cm) *worse* than 2002 (57 cm), yet matched recall runs the other
way - 2005 at 0.7086 against 2002 at 0.6541, and 2005's AUC of 0.9134 is mid-pack. **So effective
resolution is a better axis than nominal GSD but it is still not the whole explanation for the
2000/2002 deficit.** Three attempts at that explanation have now failed - nominal GSD (it.77),
spectral sharpness (it.79) and effective resolution (here). Something else distinguishes the two
oldest acquisitions and I do not yet know what it is.

**THE CAVEAT THAT MAY ALSO BE THE OPPORTUNITY.** Every King County file here is EPSG:3857, and
reprojection to Web Mercator is itself a resampling that blurs. **The softness measured above may
have been introduced by our own mosaicking and reprojection rather than by the original
acquisition.** That is testable and, if true, valuable: re-deriving the early years from
native-projection sources could recover real detail that no retraining can. **A 2.8x oversampling
in 2000 and 4.0x in 2005 are large enough to be worth checking before any further modelling effort
is spent on those years.**

**IMMEDIATE CONSEQUENCE.** `tier_of(gsd_cm)` assigns training recipes from the nominal figure. On
these numbers 2005 is tiered on 20 cm while resolving at 81 cm, and 1998 - if it were ever added -
would be tiered on 40 cm while resolving at 2.4 m. **The tier logic is keyed to a number that is
wrong by up to 6x for the years it matters most.**

---

## QUEUE - uncovered angles, highest value first

1. **Q136 MEASURED: map-count is threshold-sensitive by up to 17.3 pp (-5.71 pp at the deployed
   0.5); the stratified estimator is unbiased and works at n=250 (+/-4.42 pp). But n=250 CANNOT
   resolve the 2.6 pp policy gap - that needs ~1,221 points/yr for +/-2.0 pp.** Adoption is Kam's
   call. Original item below.
   **Replace map-count area with reference-sample estimation (Q136)** - the single highest-value
   fix now identified. `phase3_semantic_dev.py:1722` counts thresholded pixels; three independent
   measurements say calibration dominates the reported numbers. The Olofsson/CEOS machinery is
   already in this tracker and P3's design already exists. **Not new research - applying what we
   already read.**
2. **Q139. [TESTABLE, POTENTIALLY RECOVERS REAL DETAIL] Is the softness ours or the sensor's?**
   Every King County file is EPSG:3857 and reprojection blurs. If 2000's 2.8x and 2005's 4.0x
   oversampling were introduced by our mosaicking, native-projection sources would recover detail
   that no retraining can. Check the source archives before spending more modelling effort on the
   early years.
3. **Q140. What DOES explain the 2000/2002 deficit?** Nominal GSD, spectral sharpness and now
   effective resolution have all failed to account for it. Remaining candidates: scanned film vs
   digital capture, compression, a different contractor's processing chain, or genuinely different
   canopy. **Three failed explanations is a signal to stop guessing and look at the imagery.**
4. **Q138 SUPERSEDED - measure effective resolution properly (edge response / MTF), not by HF share.** Q137
   established that nominal GSD misdescribes at least 1998, 2005 and 2013, but its metric only
   supports an ORDERING. A slanted-edge measurement on hard targets (roof ridges, road markings)
   would give a defensible effective GSD per year - and `tier_of(gsd_cm)` is currently assigning
   training recipes from the wrong number.
3. **Channel ablation on the trained net (Q98/Q135)** - the only thing that settles what the model
   keys on. Needs GPU; everything else here is circumstantial by construction.
3. **Does the per-year threshold manufacture a trend in the AREA series (Q132)?** Premise now
   confirmed in code; the measurement remains.
4. **Test relief displacement (Q123), then spurious CHANGE from differing frame layouts (Q125).**
5. **1998 as the panchromatic pilot (Q126)** - 1936 is an empty file, so this is the whole of it.
6. **Human-check the 2-5 m over-impervious cell (Q120).**
7. **Aux-height INPUT variants on the impervious split** - labels (it.68) and shadow (it.69) ruled
   out; Wagner 2024 (ID 199) is the published precedent.
8. **Why is 2007 degenerate at cr=0.20 (Q133)?** Cheap histogram check.
9. **Trace which results used cross-year GRVI (Q129).**
10. **Write down the canopy definition (Q1).**

---

## OPEN QUESTIONS — what we don't know

Distinguish **unknown to us** (answerable by reading) from **unknown to the field**
(answerable only by our own experiment).

### Answerable by reading — the loop should close these
- **Q1.** Does VFM fine-tuning beat radiometric normalization on *aerial* imagery at our
  GSD range, or only on the satellite benchmarks these papers use? (ID 107, 110, 111 all
  benchmark on satellite-dominated suites.)
- **Q2.** Is there any published result on training with labels from **one** year and
  deploying across two decades, with an honest independent evaluation?
  **PARTLY RETRACTED (Search 28).** Search 23's "no" was right about the temporal framing but
  wrong about the general one. The regime is called **SINGLE DOMAIN GENERALIZATION** and it has a
  literature (ID 142, TGRS 2024): train on one source domain, deploy to unseen domains, no target
  data at training time. What remains genuinely unpublished is SDG over a **24-year temporal axis
  with sensor turnover** - the axis, not the one-source constraint. Search SDG vocabulary from
  here on; searching "temporal transfer" was finding the wrong shelf.
- **Q33.** What is our honest MODEL-SELECTION rule? Gulrajani & Lopez-Paz (ID 151) argue a DG
  method without one is incomplete. We select on validation built from projected 2020 labels -
  a proxy carrying the same bias as the training signal. Options: leave-one-era-out selection,
  selection on the both-agree reference subset, or selection on a small in-year human sample.
  **This gates every method comparison the loop has proposed** and is now the top open question
  on the modelling side.
- **Q35.** Does agreement-on-the-line hold for SEGMENTATION? **PARTLY ANSWERED (Search 35): no
  demonstration found for dense prediction** - but segmentation has its own instrument, reverse
  classification accuracy (ID 157), which is purpose-built for it and needs only a small labelled
  reference set. Prefer RCA over agreement-on-the-line for our case; keep agreement-on-the-line as
  the cross-check, since the two fail for different reasons.
- **Q39.** Is our 2020 label set a valid RCA reference database? RCA needs reference images that
  span the target variety. Ours are training-site footprints plus a citywide MODEL mask - which
  carries the finding-4 bias. A reference set built from biased masks would return optimistic
  quality scores for exactly the years that share the bias. This is the load-bearing question for
  the whole RCA route.
- **Q40.** Do RCA and ConfIC-RCA transfer to aerial canopy? **ANSWERED: no application exists.**
  Two searches found only medical imaging. Combined with Q39 (our reference set is a biased model
  mask), the RCA route is higher-risk than Search 35 implied. **The RS-native answer is latent
  class analysis - Foody 2022, already in the tracker as ID 80** - which needs several imperfect
  sources rather than one clean reference, and we have three. Prefer ID 80; keep RCA as fallback
  and borrow only its conformal framing.
- **Q41.** Should the per-crown deliverable report GEOMETRIC and THEMATIC accuracy separately?
  Costa et al. 2018 (ID 160) separates them; our binary mask conflates them, so a correctly
  detected but badly delineated crown is indistinguishable from a perfect one. For a per-crown
  product that is a real omission. What would it cost to report both?
- **Q36.** Can agreement-on-the-line and the existing flicker analysis together separate "this
  year is hard" from "this model is unstable"? Flicker measures one model across years; this
  measures several models on one year. Nothing currently distinguishes the two, and the
  deliverable is a change product (Q7).
- **Q34.** Is there a tuned ERM baseline to compare anything against? Two canonical results
  (IDs 137, 151) say a well-tuned, honestly-selected baseline matches most specialist methods.
  We have neither the tuning (Q17) nor the selection rule (Q33), so no measured "gain" from any
  method in Searches 15-31 would currently be interpretable.
- **Q17.** [LITERATURE ANSWERED, PROJECT SIDE OPEN] What hyperparameter-tuning budget did our
  ResNet-101 baseline actually receive?
  Sosa's "scratch with well-tuned hyperparameters" matched pretraining; our v030–v048 history
  is dominated by *debugging* (sampler, BN, metric artifacts), not tuning. Adopting a
  foundation model to beat an under-tuned baseline would be an expensive mistake.
- **Q3.** What is the reported cost of colorization/super-resolution in *false positives*?
  Simou 2026 reports gains; the GAN-rooftop line reports ~40% improvement. Neither figure
  is useful to us without the precision side.
- **Q4.** Does anyone evaluate domain generalization with *stratified area estimation* and
  CIs (the Phase 4 machinery), or is the whole DG literature reporting mIoU on splits?
  If the latter, our measurement work is ahead of the modelling literature and we should
  stop expecting the modelling papers to validate our numbers.
- **Q8.** Is there a TTA method whose objective is *calibration* rather than *confidence*?
  Every method found so far (AdaBN, TENT, DIGA, ROID, SAR) either re-estimates statistics or
  sharpens predictions. Our failure mode needs the opposite. If no such method exists, that
  is a finding — and it points at per-year threshold/calibration fitting on a small labelled
  sample instead of unsupervised adaptation. **Search 17 answers this: the method is
  per-year conformal / local temperature scaling on in-year labels, not TTA.**
- **Q10.** Does conformal prediction have an established object-level (not pixel-level) form
  for segmentation? Per-crown validity intervals need coverage over *crowns*, and pixel-wise
  coverage does not imply object-wise coverage. Top of the queue.
- **Q11.** What is the smallest in-year labelled set that yields a usable per-year
  calibration? **HALF ANSWERED (Search 21).** Coverage half: at n=250 realized coverage sits
  in .868–.930 for a 90% target (Beta(n+1-l, l), Vovk 2013) — defensible if stated. Sharpness
  half: STILL OPEN. Nothing found quantifies interval *width* at n~250 for segmentation-like
  outputs, and a valid-but-useless interval is the real risk.
- **Q12.** Does conformal risk control survive non-exchangeable years? Every Search 18
  guarantee assumes exchangeability. If in-year calibration is required (as Search 17
  concluded), the guarantee holds *within* a year but says nothing about the temporal
  comparison — and the deliverable is a change product. **Top of the queue.**
- **Q13.** For 2000/2002 (the hard floor, no labels possible), can risk control state a
  bound at all, or does it degrade to "unmeasurable" exactly as now? If a small in-year
  photo-interpreted set is enough to bound the miss rate, the hard floor may be softer than
  STATE currently records — but only if Q7 (can a human even interpret 60 cm no-NIR) says
  yes. These two questions are coupled and should be resolved together.
  **Search 19 partially answers this:** Barber 2023 gives a coverage guarantee with an explicit
  penalty term for non-exchangeable data, so the floor becomes a stated bound rather than
  silence. Still gated on Q7 (can a human interpret 60 cm without NIR at all).
- **Q14.** Is the likelihood ratio between two years' imagery estimable at our resolution and
  scale? Weighted conformal (ID 124) is only as strong as that estimate, and density-ratio
  estimation in high dimensions is notoriously fragile. If it is not estimable, we fall back to
  Barber 2023's penalty term, which is weaker but assumption-free.
  **ANSWERED by Search 20: mostly no, and now testable.** IW degrades in high dimensions,
  fails when densities barely overlap (our case), and fails specifically on spatially clustered
  data. But ESS after reweighting is a computable go/no-go, and kernel mean matching is the
  fallback that skips the pointwise-ratio step. Moved from "unknown" to "gated on a test".
- **Q15.** In WHICH feature space should the density ratio or kernel mean matching operate?
  **ANSWERED (Search 22):** intermediate transformer/encoder layers, not final embeddings —
  Romero et al. 2026 find task-relevant information concentrates there. A per-year
  frequency/texture signature remains the cheap alternative worth testing alongside.
- **Q16.** Does foundation-model pretraining buy us CROSS-ERA robustness even if it does not
  buy in-domain accuracy? Sosa (in-domain, no gain on segmentation) and Luo (cross-domain,
  clear gain) are not in conflict — they measure different things, and only the second matters
  to us. Untested for aerial canopy at our GSD range. This is the single cleanest experiment
  the loop has identified: same labels, same evaluation, scratch vs pretrained encoder, scored
  on a HELD-OUT ERA rather than a held-out split.

- **Q29.** Is the conifer-only blind spot partly PHENOLOGY rather than label bias? Our labelled
  year (2020) has the fourth-lowest scene greenness in the archive. If 2020 is a shoulder-season
  or leaf-off acquisition, the labels under-represent deciduous canopy by construction, and every
  coarse year inherits it. **Confounded with contractor colour balance** - the low-greenness group
  is nearly the iteration-11 cluster. Discriminating test: greenness over known-canopy pixels,
  split conifer vs deciduous. Cheap, local, no labels. **Highest-value experiment in the queue.**
- **Q31.** Does the fixed-315-degree hillshade assumption in the structure channel conflict with
  17 different unknown imagery illumination geometries? The lidar channel carries a CONSTANT
  illumination assumption while the RGB carries a VARYING one, stacked on the same tile. Never
  examined; a plausible contributor to the struct channel's weak AUC (~0.70).
- **Q32.** Shadow: mask to IGNORE, or remove/reconstruct? Removal (ID 150) invents pixel values
  the honest-measurement rule would have to defend - the same objection raised against
  colorization. Masking fits our three-state supervision rule but costs usable area. How much
  area? Unmeasured.
- **Q30.** Should the per-crown validity intervals carry an explicit SEASONAL term? We currently
  attribute all cross-year difference to canopy change or model error. If seasonal canopy
  variation in a city is material (ID 147), a validity interval with no seasonal component is
  overstating its own precision.

- **Q84. [STRONG EVIDENCE YES - iteration 46]** 2020 canopy has a **33.0% low-greenness fraction**
  against NAIP's 5.2%, and a median GRVI a quarter of NAIP's, **with resolution controlled**
  (degrading 2020 to 60 cm changes the numbers not at all). Remaining alternative is sensor colour
  balance; remaining proof is the flight date. Original question below.
  Was the 2020 City of Edmonds acquisition flown LEAF-OFF? The regional consortium spec is leaf-off spring; NAIP is leaf-on. If
  2020 is leaf-off, our only hand labels omit deciduous canopy by construction, and the conifer-only
  blind spot, the height curve and finding 3 all have a physical rather than algorithmic explanation.
  **Recoverable from King County's photo-centre index (ACQ_DATE, UTC_TIME) or by asking the City.**
- **Q85.** Which of the 18 acquisitions are leaf-on and which leaf-off? Any cross-era comparison
  that mixes the two measures phenology, not canopy. This likely explains the iteration-44 sign
  disagreement and it invalidates specific year-pairs for both the change product and the
  weak-supervision training set (Search 54).
- **Q86. [TESTED, INCONCLUSIVE - AND THE ARCHIVE CANNOT SETTLE IT]** The leaf-on year (2022n) has a
  STEEPER staircase, not flatter - but leaf-on is perfectly confounded with 60 cm resolution in this
  archive, since NAIP is the only leaf-on program and the only coarse one. No leaf-on FINE
  acquisition exists among the 18. Needs new imagery or a re-inference of a fine leaf-off year
  degraded to 60 cm. **My iteration-47 claim that the height curve is "very likely a consequence of
  leaf-off labelling" is withdrawn** - the imagery finding stands, the causal claim does not.
  Original question below.
  Is the height curve partly a DECIDUOUS-FRACTION curve? Short urban trees skew deciduous
  and ornamental; if labels are leaf-off, low-height recall is depressed by species composition
  rather than by size. Testable once leaf-on labels exist, or by comparing recall-by-height on a
  leaf-on year (2019n/2022n) against a leaf-off year.

- **Q87.** Does leaf-off severity vary enough between acquisitions to make some consortium years
  usable and others not? 2020 shows 33.0% non-green canopy, 2022 shows 16.4% - both City of
  Edmonds. If the March-May window drives it, the later-window years may be usable for deciduous
  canopy and the early ones not. **This turns "which years can we trust" from a sensor question
  into a phenology question**, and it is measurable for all 18 with one command each.
- **Q88.** Can the NAIP years (2019n, 2022n - leaf-on, 4-band with NIR, already scored) carry the
  labelling burden instead of 2020? They are 60 cm rather than 7.5 cm, so instance-level crown work
  is out - but for the SEMANTIC canopy stream, leaf-on 60 cm may beat leaf-off 7.5 cm. That is a
  direct trade of resolution against phenology, and nobody has posed it.

- **Q89.** Does the reference disagreement concentrate on DECIDUOUS crowns? The leaf-on NDVI
  reference vs leaf-off-trained model predicts it should, and that conifers should show little
  disagreement. If confirmed, the 15-17% inter-reference disagreement is largely a phenology
  artefact rather than a definitional dispute - which changes what the P3 human sample needs to
  adjudicate. Testable with the existing agreement partitions plus any conifer/deciduous proxy.
- **Q90. ANSWERED, AWKWARDLY: it has no controlled season.** InPort says acquisition varies by
  location "based on the latest date of available imagery". Season is not a design parameter, so
  C-CAP cannot be assumed either way and **the 2016 and 2021 vintages may differ** - a direct
  mechanism for iteration 43's implausible 5.33%/yr apparent loss. Also established: C-CAP hi-res is
  a canopy product (Upland Tree / Scrub-Shrub / Background), includes **impervious-under-canopy**
  overhang, and derives height from a **stereo DSM**. Original question below.
  What season is C-CAP? Its hi-res product is built from commercial imagery of unstated
  season, and every headline recall number we quote is scored against it. If C-CAP is leaf-on, our
  model is being judged on crowns absent from its training imagery in EVERY per-year figure.
- **Q92.** Should the phenology index be a COVARIATE in the change model rather than a filter?
  The continuum reading (iteration 50) says acquisitions differ continuously in canopy greenness.
  A binary season filter throws away most of the archive; a continuous covariate keeps it and
  models the effect. This connects to Search 48's covariate-conditional sensitivity (ID 184) - the
  phenology index is exactly the kind of per-acquisition covariate that framework accepts.
- **Q91.** Which year-pairs are season-matched? Only matched pairs can support a change claim or a
  weak-supervision training pair. Currently known matched: {2016, 2021s} leaf-on, same sensor;
  {2019n, 2022n} leaf-on, same program; {2020, 2022} leaf-off, same program. **Everything else in
  the archive is unscored**, and the remaining 12 acquisitions are one command each.

### Answerable only by our own experiment — the loop should *name*, not attempt
- **Q5.** Do our 18 acquisitions separate into distinct domains at all, and along which
  axis — sensor, contractor, season, GSD? We assert eras; we have never clustered them.
  **Now cheaply testable (Search 24):** compute a per-year low-frequency amplitude summary and
  cluster. Label-free, no GPU, no trained model. This is the concrete recipe Q5 was missing.
- **Q18.** Is City of Edmonds a fourth distinct source, or does it share a contractor with King
  County? **ANSWERED by Kam + screened empirically:** they share EagleView in the later years,
  and King County switched contractors repeatedly. The radiometric screen agrees - 2017 (CoE) and
  2019 (KC) are nearest neighbours at 0.34, and agency predicts the nearest neighbour only 47% of
  the time. **Agency is not sensor.** Superseded by Q19.
- **Q19.** What ARE the true domain groups? **PARTLY ANSWERED.** The metadata that would settle
  it does NOT exist in our rasters - TIFF tags carry only AREA_OR_POINT and compression. It would
  have to come from the source portals (King County GIS, WA state, USDA/NAIP): an external errand.
  Until then the amplitude signature (ID 136) is the best instrument and the iteration-11 screen
  is the only evidence. Screen suggests at least {2005, 2007}, {2009, 2021, 2023},
  {2017, 2019, 2020, 2022 ...}, {2019n, 2021s}, {2024 alone} - **but computed without 2002/2012**.
- **Q21.** Is `2017_coe_rgb.tif` the same raster as `2017_king_rgb.tif`? **ANSWERED: NO.**
  Two genuinely different 2017 products - King County at 14.93 cm (74496x105984) and City of
  Edmonds at 7.46 cm (148736x211968), near-identical bounds. No silent wrong-file risk (the
  names differ, so a lookup cannot collide), but the King County 2017 raster is an orphan that
  is not in the catalog. **It is also the best unused asset in the project** - see the matched-pair
  experiments above.
- **Q23.** `pipeline_config.py` calls itself the single source of truth but omits every pre-2013
  year, while `phase4seg/config.py` names `phase2_data_prep.py` as the authority and carries all
  18. Which is meant to be canonical, and is anything still importing the wrong one? A stale
  `raw_path()` call on a pre-2013 year raises `KeyError` rather than failing quietly, so this has
  probably not corrupted results - but it should be reconciled before more code depends on it.
- **Q24.** Were the two 2017 acquisitions flown at similar dates? Without it the matched pair is
  still useful but is not a controlled comparison - season and sun angle would be confounded.
- **Q22.** Why does the catalog omit 2002 and 2012 when both exist and 2002 is actively quoted
  in STATE? Is the catalog stale (May 2026), or were they deliberately excluded for a reason
  nobody recorded?
- **Q20.** Why is 2024 a radiometric outlier by a factor of ~5 in nearest-neighbour distance?
  Different product, different processing, or a genuine scene change. Unknown, and it affects
  whether 2024 can join the series at all.
- **Q6.** Is the 5–15 m deficit (now confirmed real inside both-agree, spread +0.39) present
  in the 2020 hand labels themselves, or introduced by the 2020 *model* mask? The label
  source has the same staircase — but a hand-labelled sample would separate "humans also
  miss short trees at 7.5 cm" from "the model does".
- **Q7.** How much of the cross-year variation is real canopy change versus model
  instability? Nothing currently separates these, and the deliverable is a change product.
- **Q9.** Is `FREEZE_ENCODER_BN=True` (v039) right across all 18 years? **RESOLVED AS A
  CONFLICT (Search 27):** there was none. Freezing is correct when statistics come from small,
  noisy batches (our case at the E6 cliff); AdaBN estimates over the whole target domain offline,
  so it never faced that instability. DSBN (ID 141) does both - a BN branch per domain.
  **Residual experiment:** the freeze and the v039 sampler fix landed together, so the freeze has
  never been tested alone on a healthy sampler. Unfreeze on two contrasting years and re-score.
- **Q25.** Would per-domain BN branches (DSBN), keyed on the iteration-11 radiometric clusters,
  outperform our current per-year full fine-tunes? It is cheaper (shared weights, per-domain
  statistics only) and it implements the anchor idea in the network rather than asserting it in
  config. Untested, and it depends on Q19/Q22 - the clusters must be re-derived over all 18
  acquisitions first, including the 2002/2012 the current screen omitted.
- **Q27.** Would a blunt FDA amplitude swap destroy the fine texture that separates crown from
  lawn at 7.5 cm? FOSMix (ID 145) exists precisely because unrestricted frequency mixing can
  remove segmentation-relevant detail. Our GSD range is far finer than the satellite data these
  methods are tuned on, so the "essential frequency" band is probably different for us and would
  need to be found empirically - on the 2017 matched pair, where the answer is checkable.
- **Q28.** Which DG families has this loop never touched? Rafi 2024 (ID 146) gives the taxonomy;
  we have covered augmentation/randomization and normalization, barely touched disentanglement,
  and not touched meta-learning at all. An audit is cheaper than another single-method search.
- **Q26.** Does BN-affine-only fine-tuning suffice per year? Reported near-parity with full
  fine-tuning at a fraction of the cost. If true for us it changes the Colab budget completely -
  and it would let us adapt years we currently cannot afford to retrain.

- **Q37.** What is the right WiSE-FT interpolation for each year - and does the optimum vary
  systematically with how far that year's imagery sits from 2020? If it does, the interpolation
  coefficient becomes a measurable proxy for domain distance, and it is derivable from checkpoints
  we already hold. Cheapest untried experiment in the loop.
- **Q38.** Do we still have the discarded runs from earlier sweeps? Model soups (ID 155) turn a
  hyperparameter search's rejects into ingredients rather than waste. If `checkpoints/` retained
  them, part of the soup is already paid for; if not, Q17's tuning sweep should be run in a way
  that keeps them.

- **Q42.** What is our FOURTH independent source? Latent class needs four indicators to be
  testable, and the P3 human sample is the only candidate genuinely independent of imagery-derived
  logic. This reframes P3's purpose a second time: Search 17 made it a calibration set rather than
  an arbiter; this makes it the indicator that renders latent class identifiable at all.
- **Q43.** Is there a method for estimating accuracy when ALL available references share a common
  cause? **ANSWERED (Search 38).** The problem is recognized in remote sensing, has a known
  DIRECTION (correlated -> overestimate and favour that classifier; independent -> underestimate),
  a maximum-entropy correction (ID 163), and propagation machinery (ID 164). It is not solved, but
  it is no longer an unknown unknown.
- **Q44.** What do NEGATIVE CONTROLS say about shared bias between our model and the NDVI
  reference? Known-negative surfaces are free and already on disk - open water, building
  footprints, the impervious layer. If model and NDVI reference both call canopy on the same
  known-negative pixels, that is measured evidence of shared bias with zero human labelling.
  Cheapest remaining diagnostic; the grass-rejection metric is this idea applied to one surface
  only, and never used to compare SOURCES against each other.
- **Q45.** Can Radoux & Bogaert's maximum-entropy correction be applied to our confusion matrices
  retrospectively? If so, every per-year number in `qc_indep_report.csv` could be restated with the
  reference-error bias partly removed, without new data.

- **Q46.** How much do our hand-drawn 2020 crowns inflate measured instance performance? Allen
  et al. (ID 165) report seven-fold in closed canopy; Edmonds is largely open-grown suburban, where
  hand labels are more trustworthy. Unknown for us, and it decides whether annotation-plan item 1
  produces a real fix or a flattering number. A partial check exists without TLS: compare
  hand-drawn crowns against CHM-derived crown segments on the same ground.
- **Q47.** Is annotation actually our binding constraint, given training-free crown segmentation
  now comes within ~2% of supervised models? If so, part of the annotation plan may be avoidable -
  but the ~2% figure is on forest benchmarks, not suburban ornamentals.

- **Q48.** Can we deliver a change number precise enough to matter? Every measured uncertainty
  (5.9 / 3.3 / 4.0 / 8.2 pp) exceeds the ~2.6 pp effect a decadal canopy goal implies. Paired
  estimation cancels shared bias and could rescue this - but only where the instrument is constant,
  which our four-agency, multi-contractor, 7.5-60 cm archive violates. **This is the project's
  central feasibility question and it has never been posed.**
- **Q49.** Should the deliverable lead with PAIRED CHANGE between matched-instrument year pairs
  rather than an 18-year series of absolute percentages? **Search 41 makes this concrete and
  affordable:** the existing 750-point budget resolves a 2.6 pp change IF interpreted as the same
  points revisited across dates, and resolves nothing at that scale if interpreted independently
  per year. Same hours, opposite feasibility. Scope decision for Kam.
- **Q50.** What is the true discordant (change) rate between our year-pairs? **NOW URGENT
  (Search 47).** Street-tree annual mortality of 3.5-5.1% compounds to 10-19% over a 3-4 year gap,
  which is well above the 4-6% our Search 41 precision estimate assumed and lands in the range where
  750 points no longer resolve 2.6 pp. Counterweight: those are tree-COUNT rates and we measure
  canopy AREA at a point, where turnover is lower. **Measurable from the P2 partition before any
  human interpretation** - and it must be, because the sample size depends on it.
- **Q61.** Is per-crown loss being tabulated at interval MIDPOINTS anywhere in the pipeline or the
  planned analysis? Midpoint assignment for interval-censored events is a documented source of bias
  (ID 181), and it is the natural thing to do when plotting a loss trend. Check before any temporal
  trend is drawn; use Turnbull-style estimation instead.
- **Q62.** Should the deliverable be reported demographically - survival curves and life tables
  rather than percentage-cover time series? It is the native framing for per-crown outcomes, makes
  our results comparable to urban-forest research rather than only to remote sensing, and survives
  the epoch-pair constraint (Q60) that percentage-cover trajectories do not.
- **Q51.** Does paired interpretation introduce ANCHORING bias? **ANSWERED: yes, and it is large
  in the one field that has measured it** - 28-38% in radiology (ID 171), biasing toward "no
  change". But the alternative is worse in a different way: independent reading manufactures FALSE
  CHANGE (ID 172), which directly destroys the paired estimator's precision (at severe rates even
  750 points cannot resolve 2.6 pp). **Resolution: cascading protocol for the main sample + a
  BLIND INDEPENDENT SUBSET to measure the anchoring and correct for it** - the interpenetrating
  design of ID 101, repurposed.
- **Q52.** How large is anchoring for CANOPY-AT-A-POINT specifically? The 28-38% figures are
  mammography, where the prior is a diagnosis rather than an image, and canopy presence is a
  simpler judgement. Nothing found measures it for land cover. Unknown, and the blind subset is
  the only way to find out - which means it must be designed in from the start, not added later.

- **Q53.** Can our ~2016 1 m CHM produce usable crown pseudo-labels, or is it too coarse and too
  stale? The methods assume dense, contemporaneous ALS; ours is a single 1 m snapshot at 59.8%
  coverage. SAM2 refinement exists precisely to fix blocky CHM segments, but the degradation at our
  CHM quality is unmeasured. **Testable cheaply on the 2017 CoE imagery**, which is near-contemporaneous
  with the CHM - and the 2017 matched pair gives a second acquisition on the same ground.
- **Q54.** Would lidar-derived crowns avoid the ID 165 inflation? They come from a different
  physical measurement than RGB, so their errors should not correlate with an RGB model's - the same
  argument that made the CHM valuable for the semantic stream. If so, pseudo-labels are not merely
  cheaper than hand annotation but LESS CIRCULAR, which reverses the usual quality assumption.

- **Q55.** How much real canopy LOSS would a temporal smoother delete? HMM transition priors and
  consistency losses suppress spurious change and genuine abrupt change alike, and abrupt loss -
  a cleared lot, a removed stand - is exactly the policy-relevant event. Run the change estimate
  with and without the temporal prior and report the difference as a sensitivity; never ship only
  the smoothed version.
- **Q56.** Do the three no-change biases COMPOUND? Pseudo-labelling toward the 2020 anchor,
  anchoring in paired interpretation, and temporal smoothing all push the same direction and enter
  at different stages. If they multiply rather than merely coexist, a change product could be badly
  attenuated with every individual step looking defensible. Nothing measures this, and it may be
  the most important unmeasured risk the loop has surfaced.

- **Q57.** Can trajectory segmentation work on 18 IRREGULAR acquisitions? **ANSWERED: no, and the
  field does not try.** Zhu 2017 (ID 179) ties algorithm family to observation frequency; our
  density supports EPOCH-PAIR comparison, not trajectory fitting, and multi-decadal aerial studies
  work in intersectional epochs at roughly decadal resolution. Fourth independent line arriving at
  pairs-not-series.
- **Q59.** WHICH epoch pairs? Pairing only cancels shared bias if the two acquisitions are
  instrument-comparable, which is Q19 - open, and blocked on acquisition dates. A badly chosen pair
  reintroduces the offset pairing was meant to remove. **This is now the binding question for the
  deliverable's design**, and it is answerable from the radiometric clustering plus dates.
- **Q60.** Does the per-crown validity interval survive an epoch-pair framing? The deliverable is
  specified as continuous per-crown intervals over 2000-2024, but epoch pairs give crown state at a
  handful of dates with gaps between. An interval bounded by "present in epoch A, absent in epoch B"
  is honest but coarser than the current specification implies - a scope question for Kam.
- **Q58.** Should Phase 3 simply adopt TimeSync rather than build a new interpretation tool? It is
  operational, documented, and underpins LCMAP validation - and STATE's plan currently specifies
  reusing the `phase4_label_review.py` server pattern instead. Adopting a validated protocol would
  also make our numbers comparable to a body of existing work, which a bespoke tool never will be.

- **Q63.** Does interval-censored-with-misclassification estimation scale to ~222,000 crowns?
  The methods are biostatistical, developed for cohorts of hundreds to thousands with a few visits;
  NPMLE with EM at our scale is untested and nothing found addresses it. Fallbacks: aggregate to
  strata, or fit on a sampled cohort and apply the estimated survival curves population-wide.
- **Q64.** Our sensitivity is STRUCTURED, not scalar - it varies with height band, land-use context
  and era. The misclassification models assume a sensitivity/specificity pair. Does covariate-
  conditional sensitivity (ID 184's covariate machinery) express our height curve correctly, or does
  it need a more general measurement-error model? This is where the height curve stops being a
  diagnostic finding and becomes a model term.
- **Q65.** Which per-year accuracy figures would actually be USED? If sensitivity/specificity are
  inputs to the change estimator, then their uncertainty propagates into every crown's interval -
  which makes the reference-disagreement problem (15-17%) a direct source of uncertainty in the
  deliverable rather than a separate caveat. That coupling has never been traced.

- **Q66.** What is our specificity on the UNCHANGED class across an epoch pair? This, not canopy
  precision, governs the change product - at 97% roughly half of detected change is spurious. Every
  figure we hold measures the canopy class instead. **Measurable directly**: take stable ground
  (both references agree canopy at both dates, or agree non-canopy) and count how often the model
  reports a transition. No new labels needed.
- **Q67.** Is our change bias conservative or not? Differential misclassification "can bias in any
  direction", and ours is differential by height, context and era. The comforting assumption that
  under-detection makes loss figures conservative is unsupported, and probably wrong if losses are
  concentrated in particular height bands or contexts - which development-driven clearing implies.
  Requires knowing WHICH strata the losses fall in, which the paired sample could answer.
- **Q68.** Can change uncertainty be composed from per-year accuracy figures? **No (ID 186)** -
  errors are spatio-temporally interdependent and naive propagation is biased. So the change
  product needs its own uncertainty estimation, not an arithmetic combination of per-year numbers.

- **Q69.** Is P3 an ACCURACY study or an AREA study? The allocations compete (ID 188): Neyman
  optimal for area of change, equal allocation for user's accuracy of change. The loop has assumed
  one sample answers both. It cannot, and the choice determines the design.
- **Q70.** Should our accuracy reporting simply follow the CEOS protocol (ID 187) rather than be
  assembled from individual papers? It is current, DOI-registered, covers change maps specifically,
  and is written by the authors already in our tracker. This is the second community standard the
  loop has found us reinventing - the first was TimeSync (Q58).

- **Q71.** Our NDVI+CHM reference cannot see geolocation error AT ALL - it is derived from the same
  imagery the model classifies, so map-vs-reference geolocation error is zero by construction
  (CEOS 4.3). Every NDVI-scored figure therefore understates total error by an unknown amount, and
  the protocol notes geolocation impact is worst for high-resolution, fragmented, vertically
  structured classes - i.e. exactly urban crowns. Only C-CAP can see it. How much is it worth?
- **Q72.** Can we build a small NEAR-GOLD-STANDARD subset inside the P3 sample? The protocol says
  detecting correlation between map errors and reference errors REQUIRES one. Without it, no
  sensitivity/specificity correction is defensible - and with it, 100 excellent points may be worth
  more than 10,000 ordinary ones.
- **Q73.** Should P3 use CONSENSUS interpretation (independent labels, then discussion to consensus)
  rather than a single interpreter? McRoberts 2018 (ID 189) shows bias grows as interpreters become
  fewer and more correlated; one interpreter is the worst case on both counts. This is a resourcing
  question for Kam, not a technical one.

- **Q74.** Should change be mapped DIRECTLY rather than derived by comparing per-year masks?
  **The blocker is gone (Search 53):** STAR (ID 191) trains a change detector from SINGLE-TEMPORAL
  labels, which is exactly what we hold. Still an open decision, but no longer blocked on
  unaffordable change labels. Remaining doubts are canopy-specific, not label-specific.
- **Q76.** Does single-temporal change supervision work for FRAGMENTED, FUZZY-EDGED, seasonally
  variable objects? STAR is demonstrated on buildings, which appear and disappear cleanly. Crowns
  grow, thin, overlap and change with phenology. Nothing found tests it on canopy, and the
  pseudo-pair construction is where it would break.
- **Q77.** Can single-temporal change supervision be COMPOSED with era-shift handling?
  **Search 54 suggests it need not be composed - one method does both.** Weak temporal supervision
  (ID 193) trains on same-location cross-era pairs labelled "no change", which is directly a lesson
  in sensor invariance. Still preprint and unproven on canopy.
- **Q78.** At what temporal gap does "same location, predominantly unchanged" break?
  **MEASURED: 11.16% discordance at a 5-year gap, and that is an upper bound.** So ~89% unchanged at
  5 years by a noisy reference, higher in truth - the assumption holds comfortably for our short-gap
  pairs. Long-gap pairs (2000-2020) remain unsafe by extrapolation but are now bounded rather than
  guessed.
- **Q80.** How much of the measured 11.16% is real canopy change and how much is C-CAP vintage
  revision? The implied 5.33%/yr whole-canopy loss exceeds published STREET-TREE mortality, so most
  of it cannot be trees. Separating the two requires a reference that is stable by construction -
  which is what the P3 paired human sample would be, and is another reason to run it.
- **Q81.** Does the NDVI-reference pair give lower discordance than C-CAP-vs-C-CAP?
  **ANSWERED: no - 11.14% vs 11.16%, nearly identical - but with OPPOSITE SIGN (+2.45 pp vs
  -1.72 pp).** Two references, same city, same window, disagreeing on whether canopy grew or shrank.
  Each is dominated by its own artefact: C-CAP by vintage revision, NDVI by phenology (static CHM
  means the whole signal is greenness).
- **Q82.** Would a phenology-controlled NDVI reference change the sign? The NDVI reference's change
  signal is pure greenness because the CHM is static across both dates. If the 2016 and 2021s
  Snohomish flights differ in season, that alone could produce +2.45 pp. **Acquisition dates would
  settle it** - the same missing fact that gates Q19, Q24, Q29 and Q59. This is now the fifth open
  question blocked on it.
- **Q83.** Can ANY existing reference establish the SIGN of canopy change in Edmonds? Both available
  ones fail. If not, every change claim in the project rests on the human sample, and P3 stops being
  a validation step and becomes the primary measurement.
- **Q79.** Is the 2017 matched pair (iteration 13) the ideal weak-supervision example? Zero temporal
  gap, maximum sensor difference, same ground - by construction it is "looks different, nothing
  changed". If weak temporal supervision is pursued, that pair is the cleanest training and
  validation material we own, and it was sitting uncatalogued until iteration 13.
- **Q75.** Is our observed FLICKER real change or model noise? Pontius's "number of distinct classes
  a location takes across all time points" (ID 190) computed on BOTH the P3 sample and the model
  answers it directly. Nothing currently distinguishes them, the deliverable is a change product,
  and the test is nearly free once the sample exists.

- **Q93.** Does leaf-off labelling bias WHAT the model calls canopy, even though it does not
  explain BETWEEN-year recall differences? These are different claims and only the second has been
  tested (negatively). The first predicts a systematic, all-years deficit concentrated on deciduous
  crowns - which is consistent with the height staircase surviving every attempt to remove it.
  Testable only by labelling a leaf-on year and comparing, which is the expensive experiment.
- **Q94.** Is the 2009 acquisition radiometrically sound? Canopy greenness p90 +0.63 / p95 +0.77
  implies a near-zero red channel, which is not plausible vegetation. Suggests saturation or a
  colour-processing fault. Unused in the live QC set today; check before using it.

- **Q95.** How much of the canopy-greenness index is SEASON and how much is SENSOR? The extremes
  (2019/2021/2023 King at 64-91%) are implausible as phenology in a conifer-dominated region and
  coincide with the EagleView radiometric era. Separating them needs either flight dates, or a
  radiometric normalisation applied before the index is recomputed. **Until separated, the index
  should be described as a canopy-rendering index, not a phenology index.**
- **Q96. ANSWERED: NO.** r = -0.057 across ten live-scored years spanning a thirty-fold range in
  canopy rendering. The model does not key on greenness. Consequence nobody had drawn: the NDVI+CHM
  reference DOES key on greenness, so model and reference measure different features - which
  predicts their 15-17% disagreement is largely irreducible rather than resolvable. Original
  question below.
  Does the model's recall track canopy greenness at all? 2019 King renders 90.65% of canopy
  as non-green - if the model still detects canopy there, greenness is not what it keys on, and the
  whole greenness-based line of reasoning (including the NDVI reference) rests on a feature the
  model may not use. 2019 King has a prob raster; this is one command.

- **Q97. RESOLVED - NO DISCREPANCY. My extraction error.** The CSV is keyed on
  (year, ref, canopy_def, prob); I deduped on (year, prob) and silently mixed the NDVI reference
  into a C-CAP series. On a consistent slice the CSV reproduces STATE exactly. Absolute recall
  figures ARE safe to quote. **Real finding in passing:** two live C-CAP variants
  (`hires_lc` vs `hires_lc_snohfull`) differ by 3-4 recall points on the same year - any quoted
  figure must name which. Original question below.
  Why does `qc_indep_report.csv` disagree with STATE on recall? 2016 reads .5937 in the
  live CSV against .6844 in STATE - a nine-point gap, far beyond rounding. 2013 and 2002 differ by
  fractions of a point. Until reconciled, **no absolute recall figure is safe to quote outward**,
  which affects every write-up. Probably a canopy-definition or reference-column difference, but it
  must be pinned down rather than assumed.
- **Q98.** If the model does not key on greenness, WHAT does it key on? Texture, structure,
  context, shadow? This is answerable by ablation on existing rasters and would tell us which
  acquisitions are genuinely hard for it - replacing the rendering index, which we now know is the
  wrong covariate.

- **Q99.** What IS the evaluation footprint? Neither C-CAP variant is clipped to the city, the
  clipped one covers 52% of the model raster, and `City Boundry/Edmonds Boundry.shp` has never been
  used to scope the QC. Every reported canopy figure is implicitly scoped to an arbitrary rectangle.
  **For a municipal deliverable this is the difference between a number about Edmonds and a number
  about a bounding box.**
- **Q100. ANSWERED - INSIDE THE CITY.** The canonical C-CAP clip covers 19.71 of 24.65 km2 =
  **80.0% of Edmonds**, stopping 3.06 km short of the northern boundary. The model raster covers
  100%. Every headline figure is computed on four fifths of the city. Fix: clip `snohfull` (which
  covers the whole county) to `Edmonds Boundry.shp`.
- **Q101. ANSWERED.** Of the +0.045, only **+0.016 is the missing city area**; **+0.029 is
  non-Edmonds rural forest**. Two thirds of the gap was land outside the deliverable. The old clip
  was the better of the two available references. Original question below.
  How much of the .6303 -> .6749 gain is the missing city strip versus non-Edmonds rural forest? `snohfull` adds both. Clipping it to the boundary separates them - and gives the first
  properly-scoped citywide recall figure the project has had.
- **Q102. ANSWERED - YES, STRONGLY.** North 52.58% canopy vs south 32.30%, a +20.28 pp difference.
  The omission removed the most forested fifth of the city. **Biased, not merely smaller** - every
  stratified design built on the old footprint inherits it. Original question below.
  Is the omitted northern fifth spatially unlike the rest of Edmonds? If north Edmonds
  differs in canopy structure or development pattern, the omission is not just a smaller sample but
  a BIASED one - which would matter for every stratified design in the P3 plan.

- **Q103. ANSWERED: none of it - the gap is BIGGER on common ground.** On identical cells C-CAP
  reads 31.31% and the NDVI reference 42.29%, a **+10.98 pp** gap against the 8.2 pp quoted from
  mismatched footprints; per-pixel disagreement is **18.80%**, above the 15-17% on record, with
  NDVI-only exceeding C-CAP-only ~4:1. **My iteration-57 suggestion that footprint explained the
  dispute is withdrawn.** Original question below.
  How much of the 15-17% inter-reference disagreement is FOOTPRINT rather than definition? C-CAP citywide is 36.05% against the NDVI reference's 37.7% - 1.7 pp apart, not 8.2.
  But the NDVI figure is itself computed over only 66.7% of the city. **Both references must be
  re-scored on the same city-clipped footprint before their disagreement means anything**, and
  twenty iterations of reasoning about that disagreement rest on the old numbers.
- **Q104.** Acquire the county-wide C-CAP 2021. Only the 2016 `snohfull` is on disk, so the
  properly-scoped figure exists for one year and no citywide change can be computed. This is a
  download, not an analysis.
- **Q105. ANSWERED: barely.** -0.001 to +0.019, mean +0.008 across five years. Accuracy statistics
  are robust to the footprint error; AREA statistics are not (29.5% -> 36.05%). The distinction is
  structural: recall is conditioned on reference canopy, canopy fraction is a ratio over area.
  Original question below.
  Do the per-year RECALL figures change when scored against the city-clipped reference?
  The omitted north is far more forested, and forest is where the model does best - so citywide
  recall is likely higher than every figure in `qc_indep_report.csv`. Re-running the QC against
  `ccap_2016_edmonds.tif` is one command per year.

- **Q106.** Why does the NDVI reference call canopy on 3.8x as much disputed ground as C-CAP?
  14.89% NDVI-only against 3.91% C-CAP-only on matched cells. Iteration 49's account - the NDVI
  reference is built from leaf-on imagery, C-CAP's season unknown - is the best available and is
  testable the moment Q90 is answered.
- **Q107.** The NDVI reference covers only 66.7% of the city, and the third it misses is the more
  forested part (C-CAP reads 36.07% citywide vs 31.31% on the NDVI footprint). **Any figure derived
  from the NDVI reference is a statement about the less-forested two thirds of Edmonds.** That
  includes the corrected-label workstream, which used it as the label source.

- **Q108. ANSWERED: NO, REFUTED.** Only **0.56%** of C-CAP canopy sits below 2 m by independent
  lidar - it is not counting lawns or roofs. C-CAP is the CONSERVATIVE reference, skewed tall (50%
  above 20 m); the NDVI reference is the liberal one, with 19.08% of its canopy at 2-5 m against
  C-CAP's 7.24%. **The dispute is about SHORT VEGETATION, not suburban lawns.** Consequence: STATE's
  8/8 suburban missed stands are **real misses, not reference error**. Original question below.
  Does STATE's suburban over-count hypothesis survive? It holds that C-CAP inflates
  canopy by counting lawns and roofs between yard trees as forest. But C-CAP explicitly includes an
  **impervious-under-canopy** class folded into canopy - it is attributing overhang, which is
  correct behaviour for a canopy-cover product. And on matched ground C-CAP calls **less** canopy
  than our reference, not more. The hypothesis may be backwards and should be re-examined.
- **Q109.** Is C-CAP's stereo-DSM height failing on bare deciduous crowns? Poor stereo texture on
  leaf-off broadleaf would under-recover height and under-call canopy - a physical mechanism for
  the 3.8:1 asymmetry (iteration 60) that requires no definitional difference. Testable if C-CAP's
  source imagery date for this tile can be recovered.
- **Q110.** Should we keep reporting three `canopy_def` variants? Deciduous and evergreen classes
  are absent, and forest_only vs forest_wetland differ by 0.30% of the city. The reporting implies
  a granularity the product does not have.

- **Q111. ANSWERED, PENDING ONE CONTROL: the band is 95.37% TALL by independent lidar.**
  Reclassifying tall pixels as real miss moves the split to 98.5% real / 1.5% ambiguous. **But the
  CHM includes buildings**, so part of the band could be structures C-CAP miscalled rather than
  trees the model missed - `building_footprints/data.json` settles it and has never been used.
  Until then 98.5% is an upper bound. Original question below.
  If the missed suburban stands are REAL misses rather than reference error, the
  "unmeasurable band" framing of Phase 2 needs revisiting. STATE splits the ~30% gap into real miss
  plus unmeasurable disagreement, with 64.6% landing in the disagreement band. If C-CAP is
  conservative and tall-skewed rather than over-counting, more of that band is real miss than
  assumed - and the honest recall figure is worse, not better.
- **Q112.** Does adding C-CAP Scrub/Shrub to the canopy definition reconcile the two references?
  It closes about a third of the 10.98 pp gap. Worth computing properly: the `forest_wetland_scrub`
  rows already exist in the QC CSV, so the comparison can be made without new processing.

- **Q113. ANSWERED: 57.91% of the tall band sits on building footprints** - a four-fold enrichment
  over their 14.84% share of the city. Excluding them takes real miss from 98.5% down to **80.9%**.
  Because C-CAP includes impervious-under-canopy by design, the two figures BRACKET the answer:
  **real miss is 80.9-98.5% of the shortfall**, against Phase 2's implied ~35%. Original question
  below.
  How much of the tall "unmeasurable" band is BUILDINGS rather than trees?
- **Q115. ANSWERED: mostly overhang.** Median CHM-minus-building height is **+2.10 m**; 68.4% sits
  above the roofline on a strict reading, 41% on a conservative one that allows for the building
  heights being ~2 m low. Either way the shortfall resolves to **88-93% real miss** against
  Phase 2's implied 35.4%. Original question below.
  Is a tall C-CAP-canopy pixel over a roof an overhanging crown (real miss) or a miscalled roof? The building layer carries a per-structure `height`; **canopy overhanging a
  roof sits ABOVE the building height, a miscalled roof sits AT it.** Comparing CHM height against
  building height on those exact pixels closes the 80.9-98.5% range. One run, data already loaded. The CHM is
  height-above-ground and includes structures. 37% of the band sits at 5-10 m, which overlaps
  one-to-three-storey buildings. `building_footprints/data.json` is on disk and unused - one
  exclusion run separates "trees the model missed" from "buildings C-CAP miscalled", and the answer
  determines whether the project's genuine under-detection is larger than believed or the same.
- **Q114.** Why does the NDVI reference reject tall vegetation that C-CAP accepts? It requires
  NDVI >= 0.2, so the rejected pixels are tall-but-not-green: conifer in deep shadow, bare
  deciduous, or dark foliage. Each has a different implication for the model, and the P2 partition
  cannot distinguish them - but NDVI value plus CHM height on those exact pixels could.

- **Q116. ANSWERED: YES, AND IT IS STABLE.** Recall over impervious is 0.32-0.46 against 0.69-0.83
  over pervious ground - a gap of **0.37 to 0.43 in every year tested**, across three sensors and
  eras. Canopy over impervious is 17.2% of all C-CAP canopy, and closing the gap would lift overall
  recall by ~6.4 points, about a fifth of the shortfall. Original question below.
  Is canopy OVERHANGING BUILDINGS AND ROADS the model's dominant failure mode?
- **Q118. ANSWERED: NO - two independent deficits that COMPOUND.** The staircase survives on
  pervious ground alone (spread +0.82, 0.12 to 0.94), and the overhang penalty persists at every
  height including **-0.19 above 30 m**. Worst cell: **2-5 m over impervious = 0.028**. Original
  question below.
  Is the recall-by-height staircase just the overhang deficit in disguise?
- **Q120.** Is the 2-5 m over-impervious cell real, or a C-CAP artefact? The model finds under 3% of
  it. That is extreme enough to warrant exhaustive human inspection - and the cell is small
  (6,878 sampled cells) so it can be checked completely rather than sampled. **If it is real it is
  the single highest-value annotation target in the project; if it is C-CAP error it removes a large
  slice of the apparent shortfall.** Either answer is worth having. Canopy over impervious is disproportionately short suburban crowns. Recompute
  recall-by-height **within the pervious-only subset**: if the staircase flattens, height was a
  proxy for overhang; if it survives, they are independent deficits. This would either unify or
  separate the project's two central findings.
- **Q119. ANSWERED: NO for corrected LABELS - the gain is an operating-point artefact.** At the
  deployed threshold the corrected model lifts over-impervious recall 0.3183 -> 0.5612, but its call
  rate on non-canopy triples; held at equal overall recall its over-impervious recall **falls** to
  0.3070 and the gap **widens** to -0.3895. Caveat: scored against C-CAP while corrected from
  NIR+CHM, so this is an agreement statement, not a truth statement. **A height INPUT channel
  (v045/v046) is still untested and is now the more valuable experiment.** Original question below.
  Would a height channel fix the overhang deficit?
- **Q121. [METHOD, applies to everything already measured]** How many of this project's
  year-to-year and variant-to-variant recall comparisons are operating-point artefacts? Q119 shows
  a fixed threshold can manufacture a +0.225 "improvement" that survives no matched comparison.
  **Every per-year threshold in the pipeline is calibrated separately**, so the cross-year recall
  series (.50-.78, finding 3) may be partly a threshold series. Testable by re-scoring at matched
  call rate rather than matched threshold. The CHM is precisely the signal that
  distinguishes a crown over a roof from the roof itself, and it exists. The v045/v046 aux-height
  work targeted grass rejection; **overhang is a second and possibly stronger motivation** - and it
  predicts the benefit should concentrate on the over-impervious subset, which is directly
  measurable. The
  evidence now points there: the misses concentrate on tall vegetation over impervious surfaces,
  which is the hard RGB case (dark foliage over dark roof, no ground context). If so it is
  addressable - it is a specific, nameable weakness rather than a diffuse deficit - and it would
  reframe the annotation plan around overhang cases rather than suburban stands generally.
- **Q117.** Are the building heights usable at all? Median 4.5 m and p90 6.0 m look like eaves
  rather than ridge heights, with a modelled `heightScore` of 0.55. If a better height source exists
  (or the CHM itself over building footprints), the 88-93% range would tighten. Low priority - the
  conclusion is already robust to it.

- **Q122. ANSWERED: SHADOW REFUTED.** North-side recall is +0.035/+0.022 HIGHER than south, at both
  radii and within both matched geometry types. The deficit is isotropic w.r.t. the sun, so it is
  structural, not illumination - **radiometric fixes are ruled out**.
- **Q123. [REAL GAP - ZERO COVERAGE IN 197 PAPERS]** Does RELIEF DISPLACEMENT explain part of both
  central findings? A standard orthophoto displaces elevated objects radially from nadir, **and the
  displacement scales with object height** - which is exactly the axis our staircase runs along.
  A tall crown is drawn leaning off its true ground position, by metres at our GSDs, and buildings
  lean too. C-CAP is built from a stereo DSM and may be closer to true-ortho, so **our masks and our
  reference may be systematically misregistered as a function of height**, concentrating exactly
  where the overhang deficit lives. A tracker search for `off-nadir`, `view angle`, `BRDF` and
  `orthorectif` returns **nothing across all 197 papers** - this is a genuine blind spot, not a
  question we considered and parked. Testable by cross-correlating mask against reference within
  height bands and looking for a height-dependent offset.

- **Q124.** Can the series be pushed back to 1936 and 1998 at all, and should it be? The frames
  exist and crops were cut, but a panchromatic frame breaks every greenness diagnostic we own and
  needs a colorization or texture-only route (IDs 201-203). **Wholly untouched: every one of the
  59,980 review crops is from 2020, and `high_alpha_years` starts at 2016.** **Decide before scoping, not after** -
  **STRUCK: 1936 is an empty file** - uniform fill over all of Edmonds, because these are King
  County mosaics and Edmonds is in Snohomish County. The question reduces to 1998 alone, which is
  real, covers the whole city, and buys two years rather than sixty.
- **Q121. ANSWERED: 61% of the cross-year recall spread is the OPERATING POINT.** 0.1827 at fixed
  threshold 0.5 -> 0.0721 at matched call rate 0.30. Residual is interpretable: 2000/2002 at ~0.65
  (coarse), 2005-2021 all within **0.020** of each other. **The model is far more stable across
  years than finding 3 implied.**
- **Q131. ANSWERED: the within-year caveat HOLDS from 2005 on, FAILS in 2000.** Block rank
  correlation +0.730 excluding 2000, with mid/late-year pairs at 0.84-0.90 = real land cover. But
  2000 calls 84.5% of the city green with a block range of 0.142 - **saturated**, correlating only
  +0.476 with any other year.
- **Q134.** Is 2000's saturation recoverable, or is the dynamic range genuinely gone? If GRVI in 2000
  is saturated because of a global colour balance, IR-MAD-style affine correction (ID 204) may
  restore it; if it is JPEG or gamma damage, nothing will. **This decides whether the earliest years
  can contribute spectral signal at all**, and it is the same question as Q130 asked where it bites
  hardest.
- **Q130/Q134. ANSWERED, BOTH NEGATIVE.** AUC is monotone-invariant, so no normalisation can
  rescue GRVI where AUC is near 0.5 - and that is 2000 (0.5927), **2019 King (0.5835) and 2021 King
  (0.5453)**, not just the old years. Normalisation is still worth doing for cross-year threshold
  comparability, but **not** to make greenness work.
- **Q135. ANSWERED: the model does not rely on colour.** Model AUC 0.876-0.920, **range 0.044**
  across 21 years, against GRVI's 0.182 and brightness's 0.084 - more stable than its own inputs.
  **2021 is decisive**: GRVI AUC 0.5453 and model-GRVI correlation +0.0755, yet model AUC 0.9150.
  The only dip (2000, 0.8760) is the coarsest year, so **resolution separates years and colour does
  not**. Superseded detail below.
  PARTIALLY ANSWERED (2013, 2021 pending). Model AUC 0.876-0.920 vs brightness
  0.633-0.717; gain +0.196 to +0.243. Rank correlation with brightness only 0.31-0.53, so **the
  model is not a colour detector**, and it reaches 0.8760 even in 2000 where colour is saturated.
  A channel ablation on the trained net is still the only thing that settles Q98.
- **Q136. [THE HIGHEST-VALUE FIX NOW IDENTIFIED]** Replace map-count area with reference-sample
  estimation. `phase3_semantic_dev.py:1722` counts thresholded pixels and `binary_closing` inflates
  the count further; the Olofsson/CEOS machinery is already in this tracker and P3's sample design
  already exists. **This is not new research, it is applying what we already read** - and it would
  decouple the deliverable from the per-year threshold entirely.
- **Q135b. [ties to Q98]** If brightness is the more transferable cue (0.663-0.717
  in every year vs GRVI's 0.545-0.727), is that what the model actually keys on? A channel-ablation
  or occlusion test on the trained U-Net would answer it, and the answer decides whether the
  pre-2005 and post-2017 RGB years are usable at all.
- **Q132. [DELIVERABLE-LEVEL, HIGH PRIORITY]** Does the per-year threshold shift manufacture a trend
  in the canopy AREA series? At threshold 0.5 the call rate runs 22.0% to 30.5% across years - large
  enough to create or erase a canopy trend by itself. The area series is the deliverable, and this
  has never been checked. **Compounds with the GRVI drift (it.72), which points the same way.**
- **Q133.** Why does 2007 return identical recall at call rates 0.20 and 0.25? That implies a large
  mass of pixels sharing one probability value - a degenerate or saturated raster. Cheap to check
  with a histogram, and it invalidates the cr=0.20 comparison until resolved.
- **Q129. [AFFECTS PUBLISHED-STYLE OUTPUT]** Which existing results used GRVI or any RGB-only
  greenness index ACROSS years? Those are now suspect (see above). Within-year uses survive.
  Needs a trace like the Q107 NDVI-reference trace, and it should happen before any of it is quoted.
- **Q130.** Is per-year radiometric normalisation enough to rescue cross-year greenness, or does the
  index have to be abandoned for RGB-only years? A histogram-matching or per-year standardisation
  test on the same window set would answer it cheaply, and the answer decides whether the 13 RGB
  King County years can contribute any spectral signal at all.
- **Q126. [CHEAP, HIGH LEVERAGE]** Use 1998 as the panchromatic PILOT before touching 1936. Same
  grid as 2000, well-behaved radiometry, two years apart - so the 2000 RGB result is a near-
  contemporaneous control for a single-band method. This converts "can we do panchromatic at all"
  from an open research question into a measurable one, at the cost of one inference run.
- **Q127.** Does anything in the codebase glob `*_king_rgb.tif` and assume three bands? The two
  single-band files are currently invisible to every config, so the trap is dormant - but adding
  them to a catalog without checking would spring it.
- **Q125.** Does each acquisition's displacement field differ enough to manufacture apparent canopy
  CHANGE? This is the deliverable-level version of Q123 and matters more than the accuracy-table
  version. Testable by looking for change concentrated on tall crowns near buildings, with a
  spatial pattern that follows frame layout rather than parcels.

### Known unknowns we are choosing to live with
- CHM is one ~2016 snapshot at 59.8% coverage applied 2000–2024.
- C-CAP begins 2016; every pre-2016 number is scored against a temporally displaced product.
- Purple-leaf / low-NDVI ornamentals may be missed by the model **and** the NDVI reference
  simultaneously — the `ccap_only` partition's low-height mass is consistent with this and
  is not yet resolved.

---

## Log

| iter | date | angle | new IDs | outcome |
|---|---|---|---|---|
| 1 | 2026-08-18 | Search 15 — cross-sensor/cross-era DG, historical imagery | 106–111 | VFM fine-tuning is a testable alternative to radiometric normalization; within-year NAIP drift reported; queue + open questions seeded |
| 2 | 2026-08-18 | Search 16 — test-time / source-free adaptation | 112–115 | TTA is aimed AGAINST our failure mode (entropy min hardens near-threshold misses); our setup matches all 3 of SAR's failure conditions; FREEZE_ENCODER_BN conflict surfaced |
| 3 | 2026-08-18 | Search 17 — calibration & uncertainty under domain shift | 116-119 | REFRAME: the human sample is worth more as a per-year CALIBRATION set than as an arbiter; conformal slack at n=250 is 0.40% vs +/-5.9pp for arbitration; temperature fitted on 2020 will not transfer (Ovadia) |
| 4 | 2026-08-18 | Search 18 - object-level conformal & risk control | 120-123 | Q10 answered (object-level conformal exists). BIGGEST FINDING: stop ESTIMATING the miss rate, BOUND it - CRC controls false-negative rate at ANY n. New Q12/Q13 on non-exchangeable years and the 2000/2002 floor |
| 5 | 2026-08-18 | Search 19 - conformal beyond exchangeability | 124-125 | Q12 ANSWERED: weighted conformal carries a guarantee across years using UNLABELLED target data (we have 18 yrs of it); Barber 2023 turns the 2000/02 hard floor into a stated coverage penalty. New Q14 on density-ratio estimability |
| 6 | 2026-08-18 | Search 20 - density-ratio estimability in high dimensions | 126-128 | Q14 ANSWERED, mostly NO: IW breaks in high-dim, low-overlap, spatially clustered data - all three are us. BUT ESS after reweighting is a computable go/no-go test, and kernel mean matching is the fallback. First iteration that CONSTRAINS the plan. New Q15 on which feature space |
| 7 | 2026-08-18 | Search 21 - calibration-set size, coverage variability | 129-130 | CORRECTS iteration 3: the 1/(n+1)=0.40% figure is MARGINAL; conditional on one calibration draw, n=250 gives realized coverage .868-.930 at a 90% target (Vovk Beta). 250/yr defensible IF stated. Sharpness half of Q11 still open |
| 8 | 2026-08-18 | Search 22 - does SSL/foundation pretraining help segmentation? | 131-133 | TEMPERS iteration 1: scratch-with-tuning matches pretraining IN-DOMAIN on segmentation; the FM advantage is CROSS-domain, which is the only kind that would help us. Q15 ANSWERED (intermediate layers). New Q16 (the cleanest experiment yet) + queue item on tuning budget as the real baseline |
| 9 | 2026-08-18 | Search 23 - learning from one labelled year | 134-135 | Q2 ANSWERED: NO published work spans our regime - nearest (SpADANN) transfers one year to the NEXT year, same sensor. We are past the literature's demonstrated envelope. Closest method's engine is pseudo-labelling = our finding-4 mechanism. In-archive pretraining (Qin 2025, peer-reviewed) is the best-evidenced route |
| 10 | 2026-08-18 | Search 24 - frequency domain / FDA | 136 | FDA: swap low-freq AMPLITUDE = style transfer with no training/labels; amplitude=style, phase=content. Cheapest intervention in the loop, directly attacks consensus finding (a). Also gives Q5 a concrete label-free recipe. EMPIRICAL: catalog shows FOUR sources not three, and 2020 (only labelled year) is City of Edmonds, not King County -> new Q18 |
| 11 | 2026-08-18 | EMPIRICAL - domain clustering screen (Kam's contractor correction) | - | AGENCY IS NOT THE DOMAIN AXIS: nearest neighbour shares agency 8/17 (47%, chance). 2017-CoE and 2019-KC are nearest neighbours at 0.34 = the EagleView signature. King County splits into >=3 groups. 2024 is a severe outlier (dist 4.96). New Q19/Q20 |
| 12 | 2026-08-18 | Search 25 (tuning baseline) + inventory audit | 137 | Tuning alone beat all but one specialist method (Brigato) - our history is debugging not tuning. Q19 ANSWERED: NO acquisition metadata in any raster. THREE NEW INVENTORY DEFECTS: catalog omits 2002+2012 (2002 is quoted in STATE); iteration-11 clustering therefore has a hole; 2017 has CONFLICTING agency labels across Drive vs D: |
| 13 | 2026-08-18 | Which imagery does the pipeline use? (Kam asked) | - | AUTHORITY = phase2_data_prep.py (18 entries), mirrored into phase4seg/config.py; pipeline_config.py claims to be the single source of truth but omits ALL pre-2013 years. DISCOVERY: 2017_king_rgb.tif is NOT a copy - two distinct 2017 acquisitions, same ground, 14.93cm vs 7.46cm. A matched same-year cross-source pair = the cleanest natural experiment in the project, currently unused |
| 14 | 2026-08-18 | Search 26 - paired cross-sensor & canopy-series harmonization | 138-139 | A published analogue for the whole project exists after all: Vogeler 2018, 42-yr Minnesota canopy series across Landsat sensor generations (RSE). Li 2025 independently splits RESOLUTION (positional encoding) from STYLE (amplitude mixup) - third line converging on amplitude=style. Extracted a 4-arm experimental template for the 2017 matched pair |
| 15 | 2026-08-18 | Search 27 - batch norm under domain shift | 140-141 | Q9 RESOLVED: no real conflict - freeze is right for small noisy batches, AdaBN estimates over the whole domain offline. DSBN (per-domain BN branches) does both and composes with the iteration-11 radiometric clusters - strongest candidate yet to replace agency-keyed anchors. BN-affine-only tuning may give near-parity at a fraction of Colab cost |
| 16 | 2026-08-18 | Search 28 - single-domain generalization + Search 5 rematch | 142-144 | OUR REGIME HAS A NAME: single domain generalization (SDG), TGRS 2024 - partially retracts iteration 9. Search 5 rematch verdict: randomized histogram matching beats GAN style transfer on OVERHEAD imagery (artifacts) - and needs no model, no labels, no GPU. Fourth convergence on style-separate-from-content. Generative route DEMOTED |
| 17 | 2026-08-18 | Search 29 - SDG sweep with correct vocabulary | 145-146 | FOSMix (TGRS) refines the frequency-mixing plan: keep segmentation-essential frequencies, randomize the rest - a blunt FDA swap could destroy crown texture at 7.5cm. Rafi 2024 survey gives the family map we lacked. FIFTH convergence on style/content, now at architecture level (IN removes style, BN preserves discriminability). SDG literature independently names PHENOLOGY and ILLUMINATION as primary RS shift causes - both unsearched |
| 18 | 2026-08-18 | Search 30 - PHENOLOGY | 147-148 | POSSIBLE ALTERNATIVE EXPLANATION for the conifer-only blind spot: leaf-off imagery underestimates DECIDUOUS canopy, and our one labelled year (2020) has the 4th-LOWEST scene greenness of 17. Free GRVI screen run. HEAVILY CONFOUNDED with contractor colour balance (low-GRVI group ~= the iteration-11 cluster). Discriminating test identified: greenness over known-canopy pixels split conifer vs deciduous. New Q29/Q30 |
| 19 | 2026-08-18 | Search 31 - sun angle, illumination, shadow | 149-150 | Shadow correction REVEALS hidden land-cover mapping errors (Lasko 2026) - low sun angle is both a commission and an omission risk, neither measured for us. INTERNAL INCONSISTENCY FOUND: our struct channel assumes a FIXED 315deg sun while 17 acquisitions have 17 unknown solar geometries. Flight dates now identified as the single highest-leverage missing fact (collapses Q19+Q24+Q29+illumination). New Q31/Q32 |
| 20 | 2026-08-18 | Search 32 - coverage audit + ERM corrective | 151-152 | DEFLATES MUCH OF SEARCHES 15-31: carefully implemented ERM matches/beats every DG algorithm (Gulrajani & Lopez-Paz ICLR 2021), and a DG method without a stated MODEL-SELECTION rule is incomplete. We select on projected 2020 labels = the same bias as the training signal. Meta-learning family CLOSED (needs target examples; we have one labelled domain). Ensembling/model-soups is the one family never touched. New Q33/Q34 |
| 21 | 2026-08-18 | Search 33 - model selection & unsupervised accuracy estimation | 153-154 | AGREEMENT-ON-THE-LINE (NeurIPS 2022): estimate per-year OOD accuracy from UNLABELLED data + several models' predictions. We already have 18 unlabelled years and 9 per-year models. Could give numbers for 2000/2002 - the years STATE calls unmeasurable - and it is SELF-CHECKING. Orthogonal to our existing flicker metric. New Q35/Q36 |
| 22 | 2026-08-18 | Search 34 - weight averaging & ensembling | 155-156 | WiSE-FT applies to checkpoints WE ALREADY HAVE - interpolate sem_best_2020 with each per-year fine-tune, pure weight arithmetic, no retraining, scored by existing QC. Makes label-circularity drift an explicit sweepable dial. Model soups give ensemble robustness at ZERO extra inference cost (we OOM'd at batch 160). TAXONOMY COVERAGE NOW COMPLETE. Tension: measure agreement BEFORE souping. New Q37/Q38 |
| 23 | 2026-08-18 | Search 35 - segmentation quality without ground truth | 157-158 | Q35: no agreement-on-the-line demo for dense prediction, BUT segmentation has its own instrument - Reverse Classification Accuracy (TMI 2017), needing only a small labelled reference set (we have 2020). ConfIC-RCA (TMI 2025) adds SPLIT CONFORMAL -> a prediction INTERVAL on segmentation quality. Second route (with Barber 2023) to replacing 'no number' for 2000/2002 with a bounded one. Both are MEDICAL results; transfer untested. New Q39/Q40 |
| 24 | 2026-08-18 | Search 36 - GT-free evaluation outside medical imaging | 159-160 | Q40 ANSWERED: RCA has NO remote-sensing application - medical only. CORRECTS iteration 23: the RS-native answer is LATENT CLASS (Foody 2022 = ID 80, already in our tracker since Search 10), which needs several IMPERFECT sources (we have 3) not one clean reference (ours is biased, Q39). Ranking flips to ID 80. Also: unsupervised RS segment evaluation measures FORM not CORRECTNESS - do not confuse them. New Q41 on geometric vs thematic |
| 25 | 2026-08-18 | Search 37 - latent class read properly | 161-162 | RETRACTS guidance given 3x: with THREE sources and two classes the model is JUST-IDENTIFIED (zero df, unfalsifiable), and conditional dependence OVERESTIMATES the correlated pair's sensitivity (+0.094) - our correlated pair is model+NDVI-ref, so it would flatter exactly what we doubt. Detection tools find the right pair only 10-12% of the time. FIX: a FOURTH independent source = the P3 human sample. New Q42/Q43 |
| 26 | 2026-08-18 | Search 38 - correlated reference errors | 163-164 | Q43 ANSWERED - the structural problem behind 3 retractions is recognized and DIRECTIONAL: correlated ref errors OVERESTIMATE accuracy and systematically favour that classifier; independent ones UNDERESTIMATE. So the NDVI ref flatters our model BY CONSTRUCTION and C-CAP understates it - the bracket now has a mechanism. Max-entropy correction exists (ID 163). NEGATIVE CONTROLS (water/buildings/impervious - all on disk) would measure shared bias with zero labelling. New Q44/Q45 |
| 27 | 2026-08-18 | Search 39 - crown instance segmentation, SAM era | 165-166 | WARNING ON WORK ALREADY COMMITTED: manual crown labels inflate AP50 SEVEN-FOLD vs TLS truth (0.670 -> 0.094), collapse concentrated in LOCALIZATION - correlated-error again, now in the instance stream, bearing on annotation-plan item 1. Caveat: closed canopy, ours is largely open-grown. Tree-SAM (peer-reviewed) is the urban reference point, F1 0.830, and LADDER-SIDE-TUNING adapts an FM without backprop through it = Colab-feasible. SAM out-of-the-box still loses to custom Mask R-CNN. New Q46/Q47 |
| 28 | 2026-08-18 | Search 40 - what precision does a canopy number need? | 167-168 | SHOULD HAVE BEEN ITERATION 1. Seattle (15 mi away) has MULTIPLE CONFLICTING published canopy values for IDENTICAL dates - method, not trees. Imagery source alone moves the answer 4 pp. AND: every uncertainty we have (5.9/3.3/4.0/8.2 pp) EXCEEDS the ~2.6 pp effect a decadal canopy goal implies. Paired change could rescue it, but only with a CONSTANT instrument - which our archive violates. New Q48/Q49: the project's central feasibility question |
| 29 | 2026-08-18 | Search 41 - paired / partial-replacement sampling | 169-170 | ANSWERS Q48. Paired interpretation (same points, both dates) gives ~2.9x precision because only CHANGED points contribute variance: 750 pts -> +/-1.65-2.19pp, resolving a 2.6pp effect; independent sampling never gets there at any affordable n. THE EXISTING 250x3=750 BUDGET ALREADY WORKS - it is just being spent the wrong way. Frayer & Furnival 1967 is the canonical design; Olofsson 2020 handles omission in CHANGE estimates. New Q50/Q51 |
| 30 | 2026-08-18 | Search 42 - anchoring vs false change | 171-172 | TWO-SIDED TRADE-OFF, both measured. Anchoring in paired reading is 28-38% (radiology) and biases toward NO CHANGE - the dangerous direction. But independent reading manufactures FALSE CHANGE, which directly destroys the paired precision gain: at severe rates even 750 pts cannot resolve 2.6pp. RESOLUTION: cascading main sample + BLIND INDEPENDENT SUBSET to measure anchoring - reuses Xing & Stehman ID 101. Anchoring size for canopy is UNKNOWN |
| 31 | 2026-08-18 | Search 43 - annotation-free crown segmentation | 173-174 | DIRECT ALTERNATIVE TO ANNOTATION-PLAN ITEM 1: lidar pseudo-labels + SAM2 refinement, zero manual annotation - and we hold every input, with CHM (~2016) near-contemporaneous with the 2016/2017 acquisitions. Also LESS CIRCULAR than hand labels, since lidar errors do not correlate with an RGB model's (cf ID 165 seven-fold inflation). RANKING SETTLED: pseudo-label-and-train > noisy-label training > zero-shot SAM2. New Q53/Q54 |
| 32 | 2026-08-18 | Search 44 - temporal consistency | 175-176 | THE COMPOUNDING BIAS: three mechanisms found in three separate searches ALL suppress apparent change - pseudo-labelling toward the 2020 anchor, anchoring in paired interpretation, and temporal smoothing/HMM priors. The deliverable IS a change product. HMM priors specifically would delete abrupt canopy LOSS, the policy-relevant event. Temporal-consistency losses need NO labels -> third route for the unlabelled archive. New Q55/Q56 |
| 33 | 2026-08-18 | Search 45 - trajectory segmentation & disturbance | 177-178 | THE PROTOCOL WE DERIVED ALREADY EXISTS: TimeSync (RSE 2010) has interpreters work a point's whole TRAJECTORY across all dates - operational, documented, underpins LCMAP validation. Adopt rather than invent (Q58). LandTrendr gives the right DATA STRUCTURE for per-crown intervals - trajectory with VERTEX YEARS, preserving abrupt change by design - but assumes yearly, composited, single-sensor data and we violate all three. New Q57/Q58 |
| 34 | 2026-08-18 | Search 46 - sparse/irregular series | 179-180 | Q57 ANSWERED: OUR SERIES IS NOT A SERIES. Zhu 2017 ties algorithm family to observation frequency - our density supports EPOCH-PAIR comparison, not trajectory fitting, and multi-decadal aerial studies work in decadal epochs. FOURTH independent line arriving at pairs-not-series (40, 41, 42, 46) - four literatures, four reasons, same conclusion. Multi-epoch feature matching (ID 180) is the co-registration method for exactly our archive. New Q59 (which pairs?) is now the binding design question |
| 35 | 2026-08-18 | Search 47 - interval-censored & demographic framing | 181-182 | FIRST SEARCH OF THE FRAMEWORK THE DELIVERABLE IS NAMED AFTER. Our data is interval-censored and assigning events to interval MIDPOINTS is a known bias - exactly what a loss-trend plot would do (Q61). Deliverable is a DEMOGRAPHIC product: survival curves, life tables. Street-tree mortality 3.5-5.1%/yr compounds to 10-19% over a 3-4yr gap, ABOVE the 4-6% Search 41 assumed -> paired-precision estimate may be optimistic, Q50 now urgent |
| 36 | 2026-08-18 | Search 48 - interval censoring + misclassification | 183-184 | THE TWO WORKSTREAMS ARE ONE. Interval-censored survival with imperfect sensitivity/specificity puts our MEASURED accuracy directly into the change likelihood as corrections - so P1-P4 do not produce caveats, they produce INPUTS the change product needs to be de-biased. Deng 2026 (AoAS) adds a TERMINAL event (crown removal is terminal) and accepts COVARIATES, so the height curve becomes covariate-conditional sensitivity. Scale to 222k crowns is untested (Q63); structured sensitivity may exceed the model (Q64) |
| 37 | 2026-08-18 | Search 49 - differential misclassification & rare-class trap | 185-186 | KILLS AN UNSTATED ASSUMPTION: non-differential misclassification biases toward the null, but DIFFERENTIAL misclassification biases in ANY direction - and ours is differential by height, context and era, so our loss figures are NOT provably conservative (Q67). RARE-CLASS TRAP: at 97% specificity on the unchanged class ~HALF of detected change is spurious - and we have only ever measured accuracy on the CANOPY class, never on the CHANGE class (Q66). Change uncertainty cannot be composed from per-year figures (Q68) |
| 38 | 2026-08-18 | Search 50 - accuracy assessment OF CHANGE | 187-188 | THE PROTOCOL ALREADY EXISTS: CEOS WGCV LPV *Land Cover and CHANGE Map Accuracy Assessment and Area Estimation Good Practices Protocol* v1.1 (2025), 187pp, by the same authors Phase 4 cited one at a time - and it covers CHANGE maps, the gap Search 49 exposed. Second community standard we are reinventing (first was TimeSync). Stehman 2012: area-optimal and accuracy-optimal allocations COMPETE - P3 must choose which question it answers (Q69) |
| 39 | 2026-08-18 | Search 51 - CEOS protocol section 4.3, read | 189 | PROTOCOL CORRECTS THE P3 PLAN: 'Unsure' must NOT be excluded - keep it, flag it, use it to measure reference uncertainty. MORE POINTS DO NOT FIX A BIASED RESPONSE DESIGN - 100 sites at 99% beat 10,000 at 95%; spend effort on point QUALITY not count. NEW STRUCTURAL FLAW: our NDVI ref shares imagery with the model, so geolocation error is UNMEASURABLE BY DESIGN - and it hits fragmented vertical classes hardest, i.e. crowns (Q71). Correlated-error correction needs a near-gold-standard SUBSET (Q72). Single interpreter is the worst case (Q73) |
| 40 | 2026-08-18 | Search 52 - CEOS section 2.5 (change maps), read | 190 | PROTOCOL CAUTIONS AGAINST OUR ARCHITECTURE: change should be mapped INDEPENDENTLY of land cover; post-classification comparison of maps with ~20% error 'leads to erroneous detection of change'. Second independent source after He 2024 (Q74). SPECIFIC P3 FIX: sub-strata targeting areas of potential OMISSION (Olofsson ID 169) = our 5-15m band + suburban context. NEW FREE INSTRUMENT: Pontius transition metrics on sample vs map tests whether our FLICKER is real change or model noise (Q75). Our 2000/02 hard floor is a recognized general problem |
| 41 | 2026-08-19 | Search 53 - direct change mapping from one labelled year | 191-192 | Q74 UNBLOCKED: STAR/ChangeStar (IJCV 2024) trains a change detector from SINGLE-TEMPORAL labels via pseudo-bitemporal pairs - exactly our asset (2020 labels, zero change labels). The architecture CEOS recommends is reachable without new labels. CAUTIONS: built for clean OBJECT change (buildings) not fuzzy crowns (Q76); pseudo-pairs come from one acquisition so it does NOT address era shift (Q77) - would need composing with FOSMix-style augmentation. Peng 2025 gives the label-efficient taxonomy to check cheaper options first |
| 42 | 2026-08-19 | Search 54 - weak temporal supervision | 193 | BEST MODELLING-SIDE FIT YET: uses one labelled year PLUS unlabelled repeat acquisitions - same-location cross-era pairs labelled 'no change' teach exactly the SENSOR INVARIANCE that 30 iterations identified as our core problem. The radiometric shift becomes the training signal instead of a nuisance. ONE mechanism for both problems, where Search 53 needed two. GAP-DEPENDENT: assumption safe to ~3yr, violated by ~13yr -> train on short-gap CROSS-SOURCE pairs, deploy across long gaps. The 2017 matched pair is the ideal example (Q79) |
| 43 | 2026-08-19 | EMPIRICAL - turnover measured (not a search) | - | MEASURED C-CAP 2016 vs 2021: discordance 11.16% (loss 6.44, gain 4.72), net -1.72pp. Paired precision at MEASURED rates: n=750 -> +/-2.39pp, still resolves 2.6pp but with NO margin (Search 41 assumed +/-1.65-2.19). BUT THE NUMBER FAILS ITS SANITY CHECK: implied 5.33%/yr whole-canopy loss EXCEEDS published street-tree mortality, so most of the 11% is PRODUCT REVISION not trees - Search 49's rare-class trap on our own data. C-CAP cannot serve as a change reference. Weak temporal supervision better supported than feared. New Q80/Q81 |
| 44 | 2026-08-19 | EMPIRICAL - references disagree on the SIGN of change (Q81) | - | NDVI ref 2016 vs 2021s: discordance 11.14% (vs C-CAP 11.16%) but NET +2.45pp GAIN against C-CAP's -1.72pp LOSS. TWO REFERENCES DISAGREE ON WHETHER EDMONDS GAINED OR LOST CANOPY. Each dominated by its own artefact: C-CAP by vintage revision, NDVI by phenology (static CHM = signal is pure greenness). Neither measures trees. P3 becomes the ONLY instrument that could establish the sign (Q83). BUG FOUND+FIXED: 0 is nodata in C-CAP but NON-VEG in the NDVI refs - first run gave a false 0.97%/90.6%-stable result |
| 45 | 2026-08-19 | *** Search 55 - LEAF-OFF: the acquisition spec may explain the central finding *** | 194 | PUGET SOUND CONSORTIUM SPEC (King County lead, our King imagery) = acquire during LEAF-OFF season, March-May spring. NAIP SPEC = LEAF-ON peak growing season. Our archive MIXES them and nothing accounts for it. IF 2020 CoE followed regional practice, our ONE labelled year was labelled on imagery where DECIDUOUS CROWNS ARE BARE - a PHYSICAL explanation for the conifer-only blind spot, the height curve, scrub recall .25, the 8/8 purple-leaf missed stands, and finding 3 (no architecture recovers signal absent from pixels). GRVI screen agrees: both NAIP years top-5, bottom-6 all consortium, 2020 is 4th LOWEST of 17. NOT PROVEN - 2020's actual date is recoverable from King County's photo-centre index. New Q84/Q85/Q86 |
| 46 | 2026-08-19 | *** EMPIRICAL - 2020 shows the LEAF-OFF signature (Q84) *** | - | Same canopy mask: 2020 CoE median GRVI +0.0330 with 33.02% of canopy pixels LOW-GREENNESS; NAIP 2022n (leaf-on BY SPEC) median +0.1226 with 5.23%. A THIRD of what the model calls canopy in 2020 is not green. GSD CONFOUND ELIMINATED: degrading 2020 from 7.5cm to 60cm changes nothing (+0.0331, 33.02%). Three independent lines now agree - published spec, scene-wide greenness ranking, canopy-conditional test. Remaining alternative: sensor colour balance (testable, queue #1). Remaining proof: the flight date. NOTE the test is BIASED AGAINST itself - the mask omits bare crowns, so 33% is an under-estimate |
| 47 | 2026-08-19 | *** EMPIRICAL - the split follows the SPEC, not the vendor *** | - | Four acquisitions, same mask: NAIP 2019n 0.00% and 2022n 5.23% low-greenness (LEAF-ON spec); CoE 2022 16.42% and 2020 33.02% (consortium LEAF-OFF spec). Median canopy greenness differs up to 8x BETWEEN programs. WITHIN-program variation (2020 vs 2022, same vendor, 2x apart) is what a March-May window predicts and a fixed colour balance does not. SAME-YEAR experiment: 2022 CoE vs 2022n NAIP differ 3x. AND 2020 - our ONE labelled year - is the WORST consortium year measured: we labelled on the barest imagery in the archive. New Q87/Q88 |
| 48 | 2026-08-19 | EMPIRICAL - the leaf-on test FAILS and corrects me (Q86) | - | PREDICTED the staircase would flatten on leaf-on. IT STEEPENS: 2022n LEAF-ON gives 0.062 at 0-2m vs 2013 leaf-off 0.209, and 0.985 vs 0.945 at 30m+. BUT CONFOUNDED - leaf-on is PERFECTLY confounded with 60cm in this archive (NAIP is the only leaf-on AND only coarse program; no leaf-on FINE year exists among the 18). Archive cannot settle Q86. WITHDRAWING my iteration-47 claim that the height curve is 'very likely a consequence of leaf-off labelling' - the IMAGERY finding (33% non-green canopy in 2020) stands, the CAUSAL claim does not. Height staircase now survives THREE attempts to explain it away |
| 49 | 2026-08-19 | *** EMPIRICAL - season map, and why the NDVI ref is 'more liberal' *** | - | BOTH SNOHOMISH YEARS ARE LEAF-ON (2016: 1.95% non-green, 2021s: 0.58%). Archive splits BIMODALLY: four acquisitions 0-5%, two 16-33%, nothing between. EXPLAINS A STANDING FINDING: the NDVI reference is built from LEAF-ON imagery while the model is trained on LEAF-OFF labels - so it is not 'more liberal', it is looking at trees with leaves on them. Recasts the 15-17% reference disagreement as a possible PHENOLOGY artefact (Q89). CORRECTS my iteration-44 claim that NDVI change is 'dominated by phenology' - both its dates are leaf-on, so that was too strong. New Q89/Q90/Q91 |
| 50 | 2026-08-19 | EMPIRICAL - it is a CONTINUUM, not a binary (corrects it.49) | - | Pre-2013 King years land BETWEEN the groups: 2005 10.98%, 2002 13.58%, 2000 16.86% non-green canopy. Iteration 49's 'bimodal, nothing in between' was drawn from six acquisitions and is WRONG - it is a continuum, which is what a March-May window predicts. REFRAME: this is a per-year PHENOLOGY INDEX from imagery alone, no flight dates needed - match year-pairs on the SCORE, not a binary class ({2020,2022} are both CoE yet 33.0 vs 16.4 = badly matched). 2020 still the extreme, ~2x the next barest. 2000/2002 are MID-RANGE on phenology - their problem is resolution and no NIR, not season |
| 51 | 2026-08-19 | EMPIRICAL - phenology does NOT predict recall | - | 12 of 18 acquisitions now indexed. NEGATIVE RESULT: low-greenness vs honest recall gives Pearson r=+0.03 (n=4) - 2013 is the SECOND-BAREST (22.46%) with the HIGHEST recall (.7094), 2016 nearly leaf-on (1.95%) scores LOWER (.6844). THIRD strike against the causal story (after it.48 steepening and it.50 continuum). What SURVIVES: 2020 is the barest year in the archive by ~1.5x and is our only labelled year - a real problem for the LABEL SET, distinct from between-year recall (Q93). FLAG: 2009 canopy greenness p95 +0.77 implies near-zero red - probable saturation/processing fault (Q94) |
| 52 | 2026-08-19 | *** EMPIRICAL - the index is mostly RADIOMETRY, not phenology (self-correction) *** | - | Four more King years: 2015 31.22%, 2021 64.32%, 2023 65.53%, 2019 90.65% non-green canopy (median GRVI NEGATIVE). SANITY CHECK FAILS: Puget Sound is conifer-dominated, so 90% non-green canopy is NOT credible as leaf-off. The extremes are exactly the EagleView era from it.11/it.18 - radiometry, not calendar. WITHDRAWING iteration 47's 'the split follows the SPEC not the vendor' and 'we labelled on the barest imagery' - 2020 at 33% is mid-pack, three King years exceed it. WHAT SURVIVES: canopy rendering varies 0-91% across the archive and nothing accounts for it. New Q95/Q96 |
| 53 | 2026-08-19 | EMPIRICAL - recall does NOT track canopy rendering (Q96) | - | n=10 live-scored years, rendering spans 0.00-31.22% non-green canopy, recall spans .50-.71: Pearson r = -0.057, t=-0.16 on 8df. NO RELATIONSHIP. Closes the leaf-off line NEGATIVELY on a fourth independent ground. STRONGER CONCLUSION: the model does not key on greenness - which undercuts the NDVI+CHM reference's own premise, since IT does. Model and reference measure different features, so their 15-17% disagreement is likely IRREDUCIBLE. BLOCKER FOUND: live CSV recall disagrees with STATE by 9 points on 2016 (.5937 vs .6844) - no absolute recall figure is safe to quote until reconciled (Q97) |
| 54 | 2026-08-19 | CORRECTION - the 'discrepancy' was MY extraction error (Q97) | - | RETRACTING iteration 53's claim that the CSV disagrees with STATE and that no recall figure is safe to quote. The CSV is keyed on (year, ref, canopy_def, prob); I deduped on (year, prob) and pulled the NDVI-reference row for 2016 into a C-CAP series. On a consistent slice it reproduces STATE EXACTLY - no integrity problem. Correlation redone properly (n=7): r = -0.132, still no relationship, so iteration 53's CONCLUSION survives its broken table. REAL find in passing: two live C-CAP variants (hires_lc vs snohfull) differ by 3-4 recall points on the same year - quoted figures must name which |
| 55 | 2026-08-19 | EMPIRICAL - the evaluation footprint was never pinned to the city | - | The two live C-CAP variants are NOT two versions of Edmonds: snohfull is the WHOLE COUNTY (117x64 km, 66% canopy) vs the clip (7.4x6.0 km, 27% canopy). AND THE CLIP COVERS ONLY 52% OF THE MODEL FOOTPRINT - 3.6 km of the model's northern extent has no C-CAP coverage, so every headline recall is computed on roughly the southern half. `City Boundry/Edmonds Boundry.shp` EXISTS IN THE REPO and has never been used to scope the QC. For a municipal deliverable this is the difference between a number about Edmonds and a number about a bounding box. New Q99/Q100 |
| 56 | 2026-08-19 | *** EMPIRICAL - the canonical reference OMITS 20% OF EDMONDS *** | - | City = 24.65 km2. Canonical `ccap_2016_hires_lc` covers 19.71 km2 = 80.0% of it, stopping 3.06 km short of the northern boundary. The MODEL raster covers 100% - the reference is the limitation, not the model. Every headline recall/precision figure, and the canopy fractions behind the 29.5% vs 37.7% policy dispute, are computed on FOUR FIFTHS OF THE CITY without that being stated. And the omitted fifth is where the model scores BETTER (.6303->.6749 on 2000 with snohfull). FIX IS CHEAP: clip snohfull to Edmonds Boundry.shp. New Q101/Q102 |
| 57 | 2026-08-19 | *** EMPIRICAL - city-clipped reference changes the headline number *** | - | Built ccap_2016_edmonds.tif (24.65 km2, the deliverable's own footprint). CITYWIDE C-CAP 2016 CANOPY = 36.05%, vs the 29.5% every figure has used. Omitted north is 52.58% canopy vs south 32.30% (+20.28pp) - the omission was BIASED, removing the most forested fifth. UNDERCUTS 20 ITERATIONS: the '8.2pp reference disagreement' compared a ~80% footprint against a 66.7% footprint; citywide C-CAP (36.05%) sits 1.7pp from the NDVI ref (37.7%). Policy-relevant: 6.5pp shift from footprint alone = 2.5x the whole decadal effect. BLOCKED on citywide change - no 2021 snohfull on disk. New Q103/Q104/Q105 |
| 58 | 2026-08-19 | IN FLIGHT - re-scoring 5 years on the city footprint (Q105) | - | Launched; exceeded the foreground limit and is running in background, so NO RESULT YET - reporting next iteration rather than guessing. Design: identical prob rasters, thresholds, decimation and canopy codes; ONLY the reference footprint differs (old 80% rectangle vs city-clipped 100%), so any delta is purely footprint. 2013 doubles as a harness check against the published .7094. PREDICTION ON RECORD: citywide recall should be HIGHER, since the omitted north is 52.6% canopy and forest is where the model does best |
| 59 | 2026-08-19 | EMPIRICAL - the footprint error barely moves RECALL (Q101/Q105) | - | Re-score done, harness reproduces all five published figures within .002. Citywide recall moves -0.001 to +0.019, MEAN +0.008 - my iteration-58 prediction of 'a few points' FAILED on magnitude. Q101 DECOMPOSED: of the .6303->.6749 snohfull gap, only +0.016 is missing city area, +0.029 is NON-EDMONDS rural forest - so the old clip was the BETTER reference, reversing iteration 55's implication. THE LESSON: footprint errors are devastating for AREA statistics (29.5->36.05%) and nearly harmless for ACCURACY statistics, because recall is conditioned on reference canopy while fraction is a ratio over area |
| 60 | 2026-08-19 | *** EMPIRICAL - the reference gap is REAL and BIGGER on common ground (Q103) *** | - | First like-for-like comparison. On identical cells: C-CAP 31.31% vs NDVI 42.29% = +10.98 pp, ABOVE the 8.2 pp quoted from mismatched footprints. Per-pixel disagreement 18.80% (vs 15-17% on record), NDVI-only 14.89% vs C-CAP-only 3.91% = 3.8:1. WITHDRAWING iteration 57's suggestion that footprint explained the dispute - and I made exactly the footprint error I had diagnosed two iterations earlier (C-CAP citywide vs NDVI on 66.7%). C-CAP reads 36.07% citywide but 31.31% on the NDVI footprint, so the errors cancelled into a plausible 1.7pp. New Q106/Q107 |
| 61 | 2026-08-19 | *** what C-CAP hi-res ACTUALLY is (Q90) *** | - | HISTOGRAM: zero Deciduous, zero Evergreen - ALL tree cover is class 11; no Low/Med Developed either. It is a canopy/impervious/open-space/water product wearing the C-CAP legend (InPort: 'Upland Tree, Scrub/Shrub, Background'). So our three canopy_def variants differ by 0.30% of the city (Q110). CANOPY INCLUDES IMPERVIOUS-UNDER-CANOPY OVERHANG - STATE's suburban over-count hypothesis may be BACKWARDS (Q108). BOTH references are height-informed (C-CAP uses a stereo DSM), so the 10.98pp gap is NOT spectral-vs-structural. Q90 ANSWERED AWKWARDLY: season is NOT a design parameter - 'latest available imagery' - so 2016 and 2021 vintages may differ, a direct mechanism for iteration 43's implausible loss |
| 62 | 2026-08-19 | *** EMPIRICAL - the suburban over-count hypothesis is REFUTED (Q108) *** | - | Tested against INDEPENDENT lidar height (C-CAP uses a stereo DSM, ours is 3DEP). Only 0.56% of C-CAP canopy is below 2 m - it is NOT counting lawns or roofs. C-CAP is the CONSERVATIVE reference, 50% of its canopy above 20 m; the NDVI ref is LIBERAL, 19.08% at 2-5 m vs C-CAP's 7.24%. THE DISPUTE IS ABOUT SHORT VEGETATION, not suburban lawns. REFRAMES A CENTRAL FINDING: STATE's 8/8 suburban missed stands are REAL MISSES, not reference error - so more of Phase 2's 'unmeasurable band' is real miss than assumed, and honest recall is WORSE not better (Q111) |
| 63 | 2026-08-19 | *** EMPIRICAL - the 'unmeasurable band' is 95% TALL (Q111) *** | - | Tested against 3DEP lidar, independent of both references: 95.37% of the disagreement band is >=2 m; only 4.63% is below. Reclassifying tall as real miss moves the split to 98.5% real / 1.5% ambiguous. So the band is NOT unmeasurable - it is tall vegetation the NDVI ref rejects for low greenness while lidar and C-CAP both find it. CAVEAT I CANNOT RULE OUT: the CHM includes BUILDINGS, and 37% of the band sits at 5-10 m where 1-3 storey structures live - building_footprints/data.json settles it and is unused (Q113), so 98.5% is an UPPER BOUND. Also: my 68/32 split does NOT reproduce Phase 2's 35/65 - different raster, footprint and CHM requirement; direction holds, percentages are not comparable |
| 64 | 2026-08-19 | *** EMPIRICAL - buildings explain over half the tall band (Q113) *** | - | 23,666 building polygons rasterised (unused since February). Buildings are 14.84% of the city but 57.91% of the tall band - FOUR-FOLD enrichment. Excluding them takes real miss from 98.5% to 80.9%. But C-CAP includes impervious-under-canopy BY DESIGN, so overhang over a roof is a real miss not an error - the two figures BRACKET: real miss is 80.9-98.5% of the shortfall, against Phase 2's implied ~35%. EITHER END demolishes the comfortable reading: genuine under-detection is ~2x what the project assumed. Q115 closes the range using the per-building height attribute |
| 65 | 2026-08-19 | *** EMPIRICAL - the range CLOSES: real miss is 88-93%, not 35% (Q115) *** | - | Rasterised per-building heights vs the CHM. Median delta +2.10 m; 68.4% of on-building tall-band pixels sit ABOVE the roofline = overhanging canopy the model missed, not roofs C-CAP miscalled. Building heights look ~2 m low (median 4.5 m, p90 6.0 m, heightScore 0.55), so computed both readings: real miss 93.0% liberal / 88.1% conservative. PHASE 2 IMPLIED 35.4%. Conclusion robust to the height caveat. FOUR-STEP CHAIN complete (it.62-65), each against an independent measurement. Sharpens the failure mode: canopy OVERHANGING BUILDINGS AND ROADS - the hard RGB case (Q116) |
| 66 | 2026-08-19 | *** EMPIRICAL - recall HALVES on canopy over impervious (Q116) *** | - | 2016: 0.3183 over impervious vs 0.6922 over pervious. 2013: 0.3383 vs 0.7683. 2017: 0.4570 vs 0.8279. GAP OF 0.37-0.43 IN EVERY YEAR, across three sensors and eras - far more STABLE than overall recall, which wanders .50-.78. Canopy over impervious is 17.2% of all C-CAP canopy; closing the gap would lift overall recall ~6.4 points = a fifth of the shortfall. Mechanism: dark foliage over dark roof, no ground texture, and the 2020 labels share the weakness. MAY UNIFY WITH THE HEIGHT STAIRCASE (Q118) - overhang canopy is disproportionately short suburban crowns. Suggests a STRUCTURAL fix: give the model the CHM (Q119) |
| 67 | 2026-08-19 | *** EMPIRICAL - two INDEPENDENT deficits that compound (Q118) *** | - | The height staircase SURVIVES on pervious ground alone: 0.1206 at 0-2 m to 0.9421 at 30+ m, spread +0.82. And the overhang penalty persists at EVERY height, including -0.19 above 30 m (0.7509 vs 0.9421) - so it is NOT a short-tree artefact. TWO-DIMENSIONAL BLIND SPOT: short -> bad, over-impervious -> bad, and SHORT AND OVER IMPERVIOUS -> 0.028, effectively blind. That worst cell is street/yard trees beside driveways - the most policy-relevant canopy in a residential city. Implication: height input addresses overhang but NOT the short-crown axis; annotation should target the INTERSECTION, not suburban stands generally (Q120) |
| 68 | 2026-08-19 | *** EMPIRICAL NEGATIVE - the corrected model's overhang gain is an OPERATING-POINT ARTEFACT (Q119) *** | - | At thr 0.509 prob_2016_corrected looks decisive: over-impervious recall 0.3183 -> 0.5612, worst cell 0.028 -> 0.183. But its call rate on C-CAP non-canopy TRIPLES (4.9% -> 17.3%). RE-THRESHOLDED TO EQUAL OVERALL RECALL the gain REVERSES: over-impervious 0.3070 (down), gap -0.3895 (wider), worst cell 0.0366 (nothing), and the matched gap is WORSE at 2-5 m (-0.076) and 5-10 m (-0.050). It moved its operating point, it did not learn overhang. DEPLOY WARNING: no comparison in this project matches operating points before claiming improvement (Q121). CAVEAT STATED: corrected from NIR+CHM, scored against C-CAP - an agreement statement, not a truth statement (Q120 settles it). Height INPUT channel v045/v046 still untested and now MORE valuable |
| 69 | 2026-08-19 | *** EMPIRICAL - SHADOW REFUTED as the overhang mechanism (Q122) *** | Liu 2023 RS 15:519 (ID 196) says U-Net specifically suffers shadow omission - our arch, our symptom | Shadow and contrast make OPPOSITE geometric predictions, so bearing-from-nearest-building separates them. North-side recall is HIGHER, not lower: +0.0354 within 10 m, +0.0221 within 20 m. Holds within MATCHED geometry: faces N .5071 vs S .4401 (+.067), corners +.020, E-W control flat (-.008). SIGN ERROR against the hypothesis, not a null. Flagged but NOT read into: cardinal .44-.51 vs diagonal .58-.61, spread .123 = 5x the N-S effect, almost certainly an axis-aligned-footprint artefact (wall faces vs corner wedges). CONSEQUENCE: the deficit is isotropic wrt the sun -> structural, not illumination -> RADIOMETRIC FIXES RULED OUT (shadow compensation, histogram matching). With it.68 ruling out corrected labels, the candidate list is now height channel or NIR. NEW BLIND SPOT Q123: relief displacement scales with HEIGHT and 0 of 197 tracker papers cover off-nadir/view-angle/orthorectification |
| 70 | 2026-08-19 | LITERATURE + INVENTORY (not measured) - relief displacement, and the archive starts in 1936 | Gharibi 2018 (198), Wagner 2024 (199), Chen 2014 (200), Mboga 2020 (201), Tian 2025 (202), Kostrzewa 2025 (203) | (1) A conventional orthophoto is rectified on a BARE-EARTH DTM, so only the BASE of a tree lands correctly and everything above ground is displaced radially, PROPORTIONAL TO HEIGHT. d=(h/H)*r: a 20 m crown 500 m off nadir at 3 km = 3.3 m = 33 px at our 10 cm King GSD. Runs along the SAME axis as our staircase but CUTS AGAINST it (more displacement = worse agreement, yet tall-band recall is our highest .9421), so it cannot be manufacturing the staircase - the true height effect may be STRONGER. Bigger risk is the DELIVERABLE: 17 acquisitions = 17 frame layouts = 17 displacement fields -> SPURIOUS CHANGE on tall crowns near buildings (Q125). 0 of 197 papers covered off-nadir/view-angle/BRDF/orthorectif. (2) 1936_king_rgb.tif and 1998_king_rgb.tif are ON DISK with crops already cut, in NO catalog row. Panchromatic = MISSING MODALITY not domain shift; FDA/FOSMix assume matched channels and cannot apply; GRVI/NDVI/leaf-off all UNDEFINED there. Tian 2025 uses DL COLORIZATION as the bridge - absent from all 200 prior rows (Q124) |
| 70c | 2026-08-19 | CORRECTION to it.70 - I was wrong that 1936/1998 crops exist | - | I claimed phase4/crops already held 1936 and 1998 crops. FALSE - those filename matches are CROWN IDs, not years (EDM_ + 7 digits, so EDM_0001936 = crown 0001936). manifest.json says all 59,980 crops are imagery_year 2020 and high_alpha_years starts at 2016. NOTHING in this project has ever looked at 1936 or 1998. The inventory finding stands and is STRONGER: these are wholly untouched files. Lesson: a substring match on a filename is not evidence |
| 71 | 2026-08-19 | *** EMPIRICAL - 1936 and 1998 are SINGLE-BAND and the filename lies (Q124) *** | - | Both `*_king_rgb.tif` files are literally 1 band. Every other _king_rgb is 3-band and phase1_preprocess.py is built on that convention, so any glob assuming 3 bands breaks or silently reads band 1 thrice. Dormant only because grep finds 1936/1998 in NO config (phase2_data_prep, phase4seg/config, pipeline_config). THEY SHARE THE 2000 GRID EXACTLY (18944x26880 EPSG:3857) -> already co-registered/resampled, so georeferencing may be DONE; but nominal GSD is inherited from that grid, NOT measured from film - do not quote it as resolution (the it.70 gsd_cm lesson again). RADIOMETRY BAD TWO DIFFERENT WAYS: 1936 CLIPPED (p99=255, mean 230.5, bright detail destroyed not compressed); 1998 LOW-CONTRAST (p1 76 p99 219, ~143 of 256 levels, recoverable by rescaling). So they need different preprocessing, not one historical recipe. CONSEQUENCE: 1998 is the pilot, not 1936 - same grid as 2000, two years apart, giving a near-contemporaneous RGB control for a panchromatic method (Q126) |
| 72 | 2026-08-19 | *** CORRECTION + EMPIRICAL - 1936 is an EMPTY FILE; GRVI is NOT comparable across sensors *** | - | (1) WITHDRAWN from it.71: 1936 is not 'clipped', it contains NO IMAGE DATA over Edmonds. Nine probe windows all constant - mean 253.0 std 0.00 min=max=253, or 0.0 in the north. A georeferenced empty shell; the 'p99=255 clipping' was fill in a whole-raster downsample. REASON: these are KING COUNTY mosaics and EDMONDS IS IN SNOHOMISH COUNTY - and 2000's northern probes are zero too, independently confirming the known north-coverage gap is a COUNTY LINE. 1998 IS real everywhere (std 29-44) so it is the ONLY historical option - prize is 2 years not 60, but the panchromatic test still stands. (2) GRVI over the SAME GROUND every year: frac>.02 spans 0.1146 to 0.8919. DECISIVE PAIR - 2019 King .1146 vs 2019 NAIP .8919, SAME YEAR SAME GROUND SAME SEASON, differing by 0.78. Cannot be vegetation. King series DRIFTS MONOTONICALLY .80(2000)->.35(2013)->.11(2019), GRVI mean crossing to negative ~2017, so any cross-year GRVI diagnostic reports a steady canopy DECLINE that is pure artefact. DAMAGES OUR OWN leaf-off signature: its CROSS-year comparisons are unsafe; WITHIN-year use survives because the cast is global (Q129, Q130) |
| 73 | 2026-08-19 | *** EMPIRICAL - most of the cross-year recall wander is the OPERATING POINT (Q121) *** | - | One recipe, one reference, one footprint (161,052 pts, 98.9%), 8 years. Recall spread 0.1827 at FIXED threshold 0.5 -> 0.0721 at MATCHED call rate 0.30, a 61% REDUCTION. Mechanism: thr 0.5 calls 22.0%-30.5% of the city depending on year, so a fixed threshold is NOT a fixed operating point. RESIDUAL IS INTERPRETABLE where finding 3's 0.28 wander was not: 2000/2002 (~40cm, coarsest) .6454/.6541, and 2005-2021 all within 0.020 of each other (.6974-.7174) across 16 years, 3 providers, 4x resolution change. THE MODEL IS MUCH MORE STABLE THAN CLAIMED; the instability was a calibration artefact. Credit: the 2026-08-18 recipe-controlled run is column two here - this adds the SECOND control. ANOMALY FLAGGED: 2007 gives IDENTICAL recall at cr .20 and .25 (.6189) = degenerate/saturated raster, so do not quote the cr=.20 row (Q133). DOWNSTREAM: the AREA series is thresholded per-year too, and a 22->30% call-rate shift can manufacture a canopy trend on its own (Q132) - compounds with the it.72 GRVI drift |
| 74 | 2026-08-19 | *** EMPIRICAL - the within-year GRVI caveat HOLDS, except in 2000 (Q131) *** | - | I doubted my own it.72 caveat after seeing 2013's block range of 0.664, but blocks differ in LAND COVER so that proved nothing. Separator: does the block RANKING hold across years? Mean rank corr +0.666 all pairs, +0.730 excluding 2000, +0.760 excluding 2000+2005; mid/late pairs 0.84-0.90 (2009-2013 .895). SO THE CAVEAT HOLDS - within-year GRVI is usable from 2005 on, and I was too quick to doubt it. EXCEPTION 2000: calls 84.5% of ALL pixels green with block range only 0.142 = SATURATED, no dynamic range left, and correlates just +0.476 with any other year - worse than a reshuffle. 2005 intermediate at +0.617 = suspect. CONVERGENCE: it.73 found 2000/2002 the only years still worse at matched operating point (~.65 vs .697-.717); now 2000's radiometry is independently shown saturated. COARSE RESOLUTION AND DEGRADED RADIOMETRY ARE SEPARATE DEFECTS HITTING THE SAME TWO YEARS. Three distinct verdicts, do not collapse: within-year usable 2005+, unusable 2000, cross-year unusable anywhere without normalisation (Q134) |
| 75 | 2026-08-19 | *** EMPIRICAL - normalisation CANNOT rescue GRVI, and BRIGHTNESS beats greenness (Q130/Q134) *** | - | Test chosen to need no normalisation built: AUC is INVARIANT under any monotone transform (affine/IR-MAD, gamma, histogram matching), so it separates CALIBRATION problems from LOST INFORMATION. AUC GRVI: 2013 .7273 best; 2000 .5927; **2019 King .5835 and 2021 King .5453 with separation -0.045 and -0.007**. I HAD THE WRONG YEARS - the two NEWEST King years are worse than 2000, and the C-CAP 2016 vintage confound argues the same way since it should have HELPED them. Controlled pair again: 2019 King .5835 vs 2019 NAIP .6893, same year same ground. => Q130/Q134 BOTH NEGATIVE: IR-MAD cannot recover those years, information is absent not mis-scaled; normalisation still worth doing for cross-year THRESHOLD comparability but not for greenness. ACTIONABLE: BRIGHTNESS (darker=canopy) scores .663-.717 in EVERY acquisition (range .054) vs GRVI .545-.727 (range .182), and beats GRVI outright in its 3 worst years by .041/.100/.121. Luminance is the one cue every sensor here agrees on - plausible partial reason the RGB U-Net transfers as well as it.73 shows (Q135, ties to Q98). CAVEAT: both are weak single-pixel features; this bounds what COLOUR ALONE can do, not what the model does |
| 76 | 2026-08-19 | *** EMPIRICAL (PARTIAL - 2013/2021 pending) - the model FAR exceeds colour, and the AREA SERIES is threshold-counted (Q135, Q132) *** | Geirhos 2019 (207) + the 2025 paper CONTRADICTING it (208) | AUC model .8760/.9134/.9195 for 2000/2005/2009 vs brightness .6333/.7170/.6847 - context+texture buy +0.196 to +0.243 AUC over the best colour cue. Model is NOT a colour detector: rank corr with brightness only .31-.53, with GRVI .19-.47. AND IT SURVIVES 2000's SATURATION - .8760 there despite GRVI AUC .5927 and separation .057, so whatever it uses is mostly not the broken channel. THE REFRAMING NUMBER: AUC .876-.920 vs it.73's matched recall .645-.717 - the RANKING is strong and stable, only the THRESHOLD is weak. Q132 PREMISE CONFIRMED IN CODE: phase3_semantic_dev.py:1722 canopy_area = total_canopy_px * pixel_area = MAP-COUNT off a thresholded mask, with binary_closing INFLATING it further by a threshold-dependent amount; phase4_qc_score.py:83 already calls its threshold source '(circular)'. THREE INDEPENDENT LINES CONVERGE (it.72 GRVI drift, it.73 operating point, this AUC gap): the model is better than its numbers, and the numbers are dominated by calibration + a map-count estimator. Remedy is already in the tracker - Olofsson reference-sample area, not pixel counting (Q136) |
| 77 | 2026-08-19 | *** EMPIRICAL COMPLETE - the model does NOT rely on colour, and 2021 proves it (Q135) *** | Geirhos 2019 (207) vs its 2025 refutation (208) | Model AUC .8760 (2000) .9134 (2005) .9195 (2009) .9125 (2013) .9150 (2021). RANGE 0.044 across 21 yrs, 3 providers, 4x resolution change - vs GRVI range 0.182 and brightness 0.084. THE MODEL IS ~4x MORE STABLE THAN THE COLOUR STATISTICS OF ITS OWN INPUTS, threshold-free so no calibration choice is doing the work. 2021 IS DECISIVE: worst GRVI of any year (AUC .5453, separation -.007) AND lowest model-GRVI correlation (+.0755, ~zero), yet model AUC .9150, its 2nd best. With 2000 (saturated colour, model still .8760) that is TWO independent extreme cases, not an inference from correlations. ONLY DIP IS 2000 = the COARSEST year, and 2021's colour is worse yet does not dip => RESOLUTION separates years, COLOUR DOES NOT - the exact asymmetry texture-bias predicts and what it.73 found independently. UPSHOT: the it.72/74/75 colour problems are REAL BUT NOT BINDING; effort belongs on area estimation (Q136) and coarse-end resolution. FALSIFIABLE: ID 208 argues texture-bias is itself an artefact; only a channel ablation settles Q98 |
| 78 | 2026-08-19 | *** EMPIRICAL - the MAP-COUNT area is biased -5.71 pp at the deployed threshold (Q136) *** | - | 162,786 pts, 2013, C-CAP prevalence 35.97%. MAP-COUNT area swings 33.56% -> 16.24% as thr goes .30 -> .70 = A 17.3 pp SWING FROM THE THRESHOLD ALONE; at the deployed ~.5 it under-reports by 5.71 pp. FOR SCALE: the Edmonds tree-code debate turns on a 32.4% baseline vs a 35% goal = 2.6 pp, so the threshold artefact is MORE THAN TWICE THE ENTIRE POLICY GAP. Olofsson stratified-by-map estimator returns 35.97% at EVERY threshold and, simulated at P3's n=250 with 4000 draws, is UNBIASED (35.87-36.01) with 95% halfwidth 4.42-5.09 pp. HONEST QUALIFICATION: 'strat bias +0.00' at full census is ARITHMETIC not evidence - the informative columns are map sensitivity and the n=250 sim; C-CAP stands in for truth. BUT n=250 CANNOT DISTINGUISH 32.4% FROM 35%. Needed: 543 pts for +/-3.0 pp, 781 for +/-2.5, 1221 for +/-2.0, 2171 for +/-1.5 - and a year-to-year CHANGE needs more, so these are FLOORS. NOT claiming published percentages are wrong by 5.71 pp; claiming the estimator in use is threshold-sensitive by up to 17 pp and a documented alternative works |
| 79 | 2026-08-19 | *** EMPIRICAL - nominal GSD is NOT the right axis; 1998 and 2005 are SEVERELY OVERSAMPLED (Q137) *** | - | THREW AWAY a first design that block-averaged years by different factors (1/2/4) to a common 40 cm - the factor reshapes the spectrum, so 2005 and 2013 were never comparable. CLEAN RERUN, NO RESAMPLING, each image vs ITS OWN Nyquist, 12 sites: 1998 .0010 | 2005 .0010 | 2000 .0083 | 2002 .0138 | 2013 .0172 | 2021 .0530 | 2015 .0587 | 2009 .0597 | 2023 .0691 | 2007 .0770 | 2019 .0859. (1) 2007 at 20 cm carries 4.5x the relative sharpness of 2013 at 10 cm - NOMINAL GSD IS A POOR GUIDE TO REAL DETAIL. (2) 1998 and 2005 are OVERSAMPLED (~no detail at own Nyquist); for 1998 this CONFIRMS it.71's grid-inherited-GSD suspicion, for 2005 it is NEW - a nominal 20 cm product carrying ~40 cm. (3) CORRECTS MY it.77 FRAMING: sharpness alone does NOT predict performance - 2005 is the SOFTEST year yet performs fine (AUC .9134, recall .7086) while 2000 is sharper and worst. What lines up is ABSOLUTE effective detail = grid AND sharpness together, where 2000/2002 are the only years bad on BOTH axes. STATED AS HEURISTIC: the ordering is defensible, an 'effective cm' figure is not - that needs MTF/slanted-edge (Q138). (4) tier_of(gsd_cm) assigns TRAINING RECIPES from this wrong number - same class of error as the CRS-units audit, one level deeper |
| 80 | 2026-08-19 | *** EMPIRICAL - effective resolution MEASURED; gsd_cm is wrong by up to 6x (Q138) *** | - | Automatic edge-response, 10-90% rise x true GSD, same 12 sites all years. BUG CAUGHT MID-EXPERIMENT: np.interp(0.10,e,off) requires an INCREASING x-array and an edge profile is non-monotonic, so 5 years returned EXACTLY 6.70 px = the profile half-width. The tell was the impossible coincidence. Replaced with explicit crossing search; after the fix all 12 sites resolve in all 11 years and good years land at ~1.3 px, the expected value. EFFECTIVE cm: 1998 244.7 (6.1x oversampled!) | 2000 110.8 (2.8x) | 2005 80.7 (4.0x, and COARSER THAN 2000's NOMINAL 40cm) | 2002 57.1 | 2007 25.5 | 2009 26.1 | 2013 13.7 | 2015 12.9 | 2019 12.6 | 2021 13.1 | 2023 12.9. REVISING DOWN the 1998 panchromatic-pilot recommendation: at 2.4 m effective it has no crown-scale detail. BUT STILL DOESN'T EXPLAIN PERFORMANCE - 2005 (81cm) is worse than 2002 (57cm) yet recalls .7086 vs .6541. THREE explanations for the 2000/2002 deficit have now FAILED: nominal GSD, spectral sharpness, effective resolution (Q140). CAVEAT=OPPORTUNITY: all King files are EPSG:3857 and reprojection blurs, so the softness may be OURS, not the sensor's - native-projection sources could recover detail no retraining can (Q139). tier_of(gsd_cm) assigns recipes from a number wrong by up to 6x |

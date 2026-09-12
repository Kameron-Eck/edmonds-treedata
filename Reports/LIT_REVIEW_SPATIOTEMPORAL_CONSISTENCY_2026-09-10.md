# Spatio-temporal consistency — literature review

**Status: LITERATURE REVIEW. Nothing here is a measurement on our data.** Every claim is
one of three kinds, and each is labelled: what a PAPER measured, what THIS REVIEW infers
about transfer, and what remains UNSEARCHED or ABSENT from the literature. Written
2026-09-10 to support `TEMPORAL_SPATIAL_CONSISTENCY_BRAINSTORM_2026-09-10.md` (the brief);
section numbers below (§2.3, §4.1, §6.2 …) refer to that file, which stays the source of
truth for every measured number about our own stack. Owner: Kam.

---

## 1. The answer in one paragraph

**The field has no validated fix for the laundering problem. It has better-documented
instances of it.** Across 92 verified works in eleven search threads (plus 21 adjacent-field
works in four round-3 threads, §4.12), change-stratified reporting is rare: the standard evidence offered for a consistency layer is how much *more*
the map agrees with itself after smoothing, which a strong enough prior produces regardless
of correctness. Gong et al. 2017 — verified verbatim from full text — states it plainly:
"we culled a few locations where the land cover labels changed," and that same reference
set supplies the cross-validation test folds. Its headline consistency gain
(18.91% → 73% unchanged) was scored on a pool from which changed locations had been
removed. The same algorithm shipped globally as MODIS Collection 6, whose official product
documentation still cautions against using it for change detection — not because of the
smoothing, but because per-year label uncertainty at 500 m remains too high to distinguish
real change from spectral confusion (verified verbatim, §4.1). A 2025 post-processing paper on the global
30 m product removed **74% of all mapped change** (7,537 → 1,981 Mha) while reporting a
1.2-point accuracy *gain* — the exact signature §2.3's arithmetic predicts a persistence
prior would produce, though to its credit that paper *does* also report a change/no-change
error matrix against independent reference data, and finds changed-pixel accuracy markedly
lower (§4.11). The
strongest transferable ideas are not new architectures but four cheap, specific
instruments: grading each cell by its own forward-backward joint probability (Yang et al.
2020), estimating transitions from a *certified* subset rather than from projected labels
(Miller et al. 2013; Perantoni et al. 2025), gating *whether* a cell enters the contextual
update at all by that cell's own local confidence — an admit/exclude threshold, not a
graded weight (Martinis & Twele 2010), and keeping the layer in
probability space rather than downstream of a stage that has already hardened its output
(Cheng & Liu 2020; Li et al. 2019). Two designs in the brief have **no prior art in any
domain searched**: §4.2's dated, directional, decaying development prior, and §6.2's hard
ancillary veto — for which the nearest urban-forestry convention runs the *opposite* way.

---

## 2. How to read the evidence grades

Each citation carries a grade for how strongly it was verified. This matters more than
the citation count: about a quarter of the corpus rests on bibliographic metadata plus
search-engine paraphrase, because publishers returned HTTP 403 to automated fetching.

| Grade | Means |
|---|---|
| **PRIMARY** | Full text or open-access PDF fetched and read this session; numbers taken from the paper's own tables |
| **ABSTRACT** | Record confirmed and the publisher's abstract retrieved; numbers beyond the abstract not seen |
| **METADATA** | Existence, authors, year, venue, DOI confirmed via Crossref/Semantic Scholar; no abstract retrievable |
| **⚠ NUMBERS** | A quantitative figure in this review came from a search snippet, not fetched text — treat as unconfirmed |

Every citation was confirmed to exist through a Crossref or Semantic Scholar record or a
fetched publisher page. Nothing in the bibliography is recalled from model memory. Three
entries were independently re-verified after a critic flagged them; all three are real
works, correctly attributed (Mobsite et al. 2026, Guo et al. 2018, Pedley & Morgenroth
2025). **Update, 2026-09-11:** full text was subsequently obtained for both Guo et al. 2018
and both 2025 Pedley & Morgenroth papers (§4.4, §4.8, §4.10). Guo's number is real but is a
CART split point in one pruned tree, not the removal radius it was being used as; both
Pedley & Morgenroth papers' numbers check out against their own tables. Mobsite's ablation
table remains behind a 403 and its numbers still live only in brief §2.5.

---

## 3. Decision table

| Brief item | Closest prior art | What it MEASURED | What it does NOT settle | What we would measure |
|---|---|---|---|---|
| §2.3 persistence prior beats 4 absences | Gong et al. 2017 **PRIMARY** | Unchanged-label share 18.91% → 73% under a hand-set prior | Validation set had every changed location removed first | Recall on the 42 gold losses, at our own q_loss |
| §2.3 where q_loss comes from | Miller et al. 2013 **PRIMARY**; Perantoni et al. 2025 **PRIMARY** | Transitions estimated from data while correcting for both error rates; per-year-pair matrices | Neither uses a projected-label archive like ours | q_loss/q_gain from the lidar-certified GAIN/FLAT populations |
| §4.1 joint space+time field | Hoberg et al. 2015 **METADATA** (2012 precursor **PRIMARY**); Benedek & Sziranyi 2009 **METADATA** | Joint spatial+temporal CRF/MRF energies exist and are mature; the precursor states β/γ "were found empirically" — no value given, confirming rather than merely inferring the "hand-tuned, unswept" read | No measured spatial-vs-temporal weight, no sweep, no scaling evidence | The local/global weight, swept, read against the gold |
| §4.1 whether a cell enters the contextual update at all | Martinis & Twele 2010 **PRIMARY** | Entropy-gated admit/exclude: a node only enters the spatio-temporal update if its posterior entropy exceeds the scene's own mean; admitted nodes' spatial/temporal weights are hand-fixed at 1, never swept | No numeric change-size threshold; no ablation of the gate itself exists (Table 2 runs every variant *with* it) | Whether per-cell gating by measured r,f beats one global weight |
| §4.2 dated directional loss prior | **Nothing.** Seven search angles | Every source joins construction records to change *post hoc* | The forward-fed construct has no precedent at all | The §4.2 enrichment count is the right first move — nobody has done it |
| §4.2 where-vs-when risk | Rosa et al. 2013 **PRIMARY** | Ancillary prior 80% right on WHERE (10 km, cumulative), ~2% right on WHEN (exact year) | Not urban, not permits, not a sequential update | Whether a building anchor moves the year of loss, not just the place |
| §4.3 lidar as teacher | Lang et al. 2023 **PRIMARY**; Tolan et al. 2024 **PRIMARY** | Two honest exams against reference data outside lidar coverage (independent ALS; GEDI + forest-inventory field plots). Accuracy degrades off home ground: Tolan MAE 2.8 m (NEON) → 5.1 m (São Paulo) | Four systems engineer the lidar-year/imagery-year gap away (Tolan: "<two years"); none publishes the cost of not doing so | The exam that killed H2: teacher from a lidar year, student examined on a non-lidar year |
| §4.4a deep supervision | Ma et al. 2021 **PRIMARY**; PSPNet 2017 **ABSTRACT** | A naively-specified auxiliary target scored *worse* than no deep supervision (DSC 88.74 vs 88.95) | No published ablation uses a 0/1/255 ignore convention | Our own weight sweep; the ignore-aware loss is the load-bearing part |
| §4.4b resolution curriculum | **Nothing direct.** FixRes 2019 **ABSTRACT** | Train-coarse/fine-tune-native gains exist for classification, with no label degradation | Part of any such gain can be batch-norm recalibration, not learning | Control for the recalibration confound before crediting the curriculum |
| §4.4d GSD not monotonic | Brown et al. 2022 **ABSTRACT** | At FIXED GSD, optics alone swung detector mAP by >50% | Animal detection, synthetic degradation | Independent confirmation of our own season/sensor-over-GSD finding — already aligned |
| §4.5 layer placement | Cheng & Liu 2020 **PRIMARY**; Li et al. 2019 **ABSTRACT** | Deferring argmax to the end of a soft chain: +0.8–1.5 mIoU (4 backbones); probability-domain smoothing +7.0/+6.9 pts OA | Nobody studies IGNORE-sentinel propagation through a chain | Whether reasoning over the healer's 255s loses more than it gains |
| §6.2 buildings as HARD negative context | King & Locke 2013 **PRIMARY**; Sun et al. 2022 **ABSTRACT** | One data product's mutually-exclusive GIS classification assigns canopy-over-roof to the tree class, not the building class (not a surveyed field-wide convention, contra an earlier draft here); CG-Net encodes footprints as a *soft* prior robust to positional error | *Not found* (~10 queries): any A/B test of hard veto vs soft prior on the same layer, or any measured cost of a veto at its edges | The at-risk count a hard veto needs (§3 rule 3) — none found to borrow |
| §6.3 build a buildings vision model? | Li et al. 2022 **PRIMARY** | Purpose-built CNN flagging cadastral gaps: F1 85.14%, **82.27% precision** on undocumented buildings | — | Answer: it trades error profiles, not eliminates error. Run the §4.2 count first |
| §6.1 how much may it reshape | Pasquarella et al. 2022 **PRIMARY** | BOTH LandTrendr and CCDC replace every in-segment observation with a fitted value | — | Segmentation is the *strong*-reshaping end. See §4.3 below |
| §6.1 a fill-or-veto alternative | Reiche et al. 2015/2021 **ABSTRACT** | Provisional alert held pending, confirmed or dropped as evidence accrues | Assumes 6–12 day revisit, not 12 surveys in 15 years | Whether a confirmation rule recalibrated to our r,f beats the chain |
| §2.4 the gold set | Foody 2010 **ABSTRACT**; Radoux & Bogaert 2020 **ABSTRACT** | *Argues, from simulation:* 10% reference error → 12–18% bias in producer's accuracy, worst when change is rare | Neither is a measurement on data like ours; both read at abstract level only | Whether our own r,f are biased, not merely noisy |
| §2.4 the missing FP class | **Nothing.** Field-wide | No protocol found anywhere includes a tree-on-a-roof reference class | Cannot be fixed by copying anyone's protocol | A false-positive stratum is ours to invent |

---

## 4. Findings by brief section

### 4.1 §2.3 — the persistence prior, and where transitions come from

**The trap is documented, universal, and unresolved.** Three independent instances:

- **Gong et al. 2017** (**PRIMARY**, full text read, then independently re-verified
  verbatim) is the most on-point paper in the review. It runs per-year SVM → HMM Viterbi
  with a single hand-set transition matrix across nine epochs, and reports the
  unchanged-label share rising **18.91% → 73%**, illogical transitions falling
  **29.44% → ~2.6%**, and pixels flipping more than five times falling
  **23.36% → ~0.03%** (all four figures confirmed against the paper's own text).
  On how the reference set was built, §2.2 of that paper reads:

  > "Eventually, we selected 7,308 locations and recorded their ground information… The
  > locations of the samples are basically the same from 2007 to 2015. In addition, **we
  > culled a few locations where the land cover labels changed.**"

  That same set is then split by 5-fold cross-validation, so the *test* folds are drawn
  from a pool with changed locations removed. *This review's inference:* the headline
  consistency gain was scored on ground held out from the very phenomenon the method is
  supposed to preserve. It is the same criterion structure as our no-change triples (§2.1)
  and has the same blind spot — a strong enough prior produces the number regardless of
  correctness. Note the authors' own wording is "a few," so this is a design choice stated
  in passing, not a large announced exclusion; the effect on what the number can prove is
  the same either way.
- **Sulla-Menashe et al. 2019** (**ABSTRACT**, ⚠ NUMBERS on the transition figure; **PRIMARY**
  on the caution — split grade, verified 2026-09-11) documents the same algorithm operating
  globally as MODIS Collection 6. The published abstract states spurious land cover change
  fell "1.6% in C6 and 11.4% in C5" — abstract-verbatim, one level up from the earlier
  "search snippet," but the article body stays paywalled (Unpaywall and OpenAlex both report
  no OA or repository copy), so the metric's denominator is still unverified; ⚠ stays.
  Separately, the official MCD12Q1 User Guide (Sulla-Menashe & Friedl 2018, full text read)
  is explicit and now primary-verified: "we urge users not to use the product to determine
  post-classification land cover change… uncertainty in the land cover labels for any one
  year remains too high to distinguish real change from changes between classes that are
  spectrally indistinguishable at the coarse 500-m MODIS resolution." *Correction to an
  earlier draft:* the caution is not attributed to the HMM smoothing — it is stated
  *despite* the smoothing, which the paper frames as the improvement. The cause named is
  per-year label uncertainty and 500-m spectral confusion. *Inference:* institutional
  acknowledgment of the risk, not a resolution of it — but the mechanism is coarse-pixel
  spectral ambiguity, not an artifact of temporal smoothing itself.
- **Perantoni et al. 2025** (**PRIMARY**, arXiv HTML) reports F1 70.88 → 73.59 from adding
  an HMM layer, and states that evaluating on parcels that actually changed is future
  work.

**How transitions are set, across the whole thread:** hand-set constant transition
probability (Abercrombie & Friedl 2016, **PRIMARY** — full text read 2026-09-11, Sci-Hub;
filed at `D:\edmonds-pipeline\Literture\Validation\Abercrombie_Friedl_2016_HMM_multitemporal_landcover_TGRS.pdf`);
hand-set site-knowledge tiers (Gong et al. 2017); expert "illogical transition" rules (Cai
et al. 2014, **METADATA**). Only two estimate from data:

> **Correction to an earlier draft.** The "90%/10%÷(K−1)" transition-matrix form attributed
> to Abercrombie & Friedl 2016 above does not exist in that paper. §III-A states it plainly:
> "we restricted our transition matrix to the simplest possible model: a constant transition
> probability applied to all pixels and all labels… we used a transition probability of 0.1
> for most of our experiments." The paper never writes "90%" and never divides by (K−1); the
> reference implementation (`BU-LCSC/mtlchmm`, `model.py::_transition_matrix`) sets every
> off-diagonal to 0.1 and the diagonal to 0.9, unnormalized — a 9:1 stay-vs-any-other ratio,
> not the ~144:1 that 10%÷(K−1) implies at IGBP's K=17 classes. Neither this project's own
> `crown_state_model.py::transition_matrix` (a 3-state q_gain/q_loss chain) nor the cited
> paper describes a K−1-normalized split; "90%/10%÷(K−1)" appears to be an invented gloss and
> should not be repeated. **A second correction:** the paper is not merely a source of the
> transition-matrix *form* — §III-B.3/§IV-C score it against real change (1,050 MODIS pixels
> over the Xingu basin, PRODES deforestation reference, 2001–2010): "the omission error rate
> is effectively insensitive to the value of the transition probability. The commission error
> rate… increase[s] monotonically" with p. That is a real, if narrow, change-stratified test
> — deforestation only, 3-year timing tolerance, a signal the authors call clearly separable —
> so this citation is no longer accurately described as untested against real change.

- **Bogaert et al. 2022** (**ABSTRACT**) estimates *both* transition and emission
  parameters from real classified series and explicitly handles missing dates.
  *Inference:* the missing-data handling transfers directly to our irregular calendar; the
  estimation itself would be circular here, because eleven of our twelve years are 2020
  projections (§2.3) — an EM fit would learn and reinforce the labeling error.
- **Perantoni et al. 2025** estimates a **separate transition matrix per year-pair** from
  label co-occurrence, explicitly rejecting one stationary matrix.

**The transferable form of both, and the review's single best structural find:**
**Miller et al. 2013** (**PRIMARY** — full text read 2026-09-11, journals.plos.org; all
four sub-claims below confirmed verbatim), a multi-season occupancy model from ecology
(full title: *"…Estimating the Range Dynamics of Wolves from Public Survey Data"*; note the
review's earlier citation of *PLOS ONE 8(10)* is a bibliographic error — the correct issue
is **8(6)**), is the closest mathematical object to §2.3 found anywhere. Its latent per-site
binary state sequence carries *both* a non-detection rate and a false-positive rate in the
emission — the same shape as our per-survey (r, f) — and it estimates the gain/loss
transitions (colonization/extinction) **while correcting for both error rates**, identifying
the false-positive channel from a subset of surveys treated as *certain*: "known locations of
resident wolf packs collected using radio-telemetry based monitoring of marked individuals
(i.e., certain method)." It independently reproduces our diagnosis in another field:
"Failing to account for false positives led to over estimation of both the area inhabited by
wolves and the frequency of turnover" (ΔAIC 443.2 vs. the FP-ignoring model).

> **Two cautions the paper states about itself, worth carrying forward.** The *direction* of
> the turnover bias is case-dependent, not a law: "In our study, unaccounted-for detection
> errors led to higher estimates of both colonization and extinction. In other cases
> unaccounted-for false positives will lead to underestimation of transition probabilities."
> And a notation trap for anyone mapping this onto our own (r, f): in Miller's
> multiple-detection-method design, the *uncertain* method's rates are (p11, p10); `r11` in
> that paper is the *certain* method's detection probability, not the general survey rate —
> do not align our per-survey `r` with Miller's `r11`.

> *This review's inference, stated as a design pointer:* the Edmonds analog of Miller's
> "certain subset" already exists — the lidar-certified GAIN (46,805) and FLAT (40,609)
> populations (§2.2). Estimating q_loss/q_gain from those, rather than assuming 0.02 or
> fitting to projected labels, is the one route in the literature that escapes the
> circularity Bogaert would otherwise hit. Perantoni's per-pair (non-stationary) matrices
> are the same idea reached from a different direction.

**The cheapest instrument in the whole review: Yang et al. 2020** (**ABSTRACT**) grades
each pixel by the joint probability of its observed sequence under the HMM, as a
reliability score, instead of only emitting the Viterbi label. *Inference:* our
forward-backward pass already computes what this needs; it is a companion output, not a
model change, and it can be tested against the 42 gold losses without touching the engine.
Whether the score actually correlates with real loss is untested here and untested in the
paper.

### 4.2 §4.1 — space and time as one field

Architectures exist and are mature. **Hoberg et al. 2015** (**METADATA** — the 2015 IEEE
TGRS journal version stays unreadable: Unpaywall and OpenAlex both report no OA or
repository copy, and five Sci-Hub mirrors returned nothing) is a pairwise CRF spanning
multiple epochs *and resolutions* in one energy — structurally the closest to what §4.1
wants. **Its 2012 ISPRS Annals precursor now reads in full** (Hoberg, Rottensteiner &
Heipke — no Feitosa on this earlier paper — "Context Models for CRF-Based Classification of
Multitemporal Remote Sensing Data," doi:10.5194/isprsannals-I-7-129-2012, **PRIMARY**,
open-access via Copernicus, parsed successfully 2026-09-11 with `pypdf` after an earlier
attempt reported it would not parse — the β/γ symbols sit in Symbol-font private-use
codepoints that a plain-text extractor drops). Three findings transfer directly to §4.1's
open questions:
- **"No measured local/global weight" is now a quoted fact, not an inference:** "the
  weighting factors β and γ of the spatial and temporal interaction potentials… were found
  empirically" (§2.4) — no value is printed for either, and the paper sweeps a feature-scale
  parameter and three spatial models but never β/γ. The absence is *checked*, not merely
  unfound.
- **A fourth documented instance of the laundering prior**, stated as a modelling
  assumption rather than discovered as a side effect: its transition table holds 1.0 on
  class-preserving entries and 0.05–0.2 elsewhere, "because we assume that it is most likely
  to have no changes in any region" (§6).
- **"No scaling evidence" is confirmed at the paper's own numbers:** an 8.6×5.9 km² area
  near Herne, Germany, two epochs per setup (Ikonos 4 m + Landsat 30 m) — far below
  13.3 M cells × 12 epochs.

**Benedek & Sziranyi 2009** (**METADATA**) folds a spatial layer and a
change layer into one joint mixed-Markov energy for bitemporal *aerial* imagery across
large seasonal/sensor gaps — closer in spirit to our cross-flight problem than most
Landsat-cadence work. **Melgani & Serpico 2003** (**METADATA**) is the ancestor. On the
separable side, **Liu et al. 2021** (**ABSTRACT**) stages spatial smoothing first, then an
EM-trained HMM.

**Three things §4.1 needs, and the literature does not have:**

1. **No measured local/global weight with a sensitivity sweep.** Where a spatial term
   appears at all, it is described qualitatively or hand-tuned.
2. **No change-size erasure threshold.** Targeted searches for the size below which
   spatial smoothing deletes true change returned nothing. Nobody reports it.
3. **No inference at anything near 13.3 M cells × 12 epochs.** Every demonstrated system
   runs at scene, segment, or few-epoch scale.

**The one genuine design pointer: Martinis & Twele 2010** (**PRIMARY** — full CC-BY PDF
read 2026-09-11 via a GFZ Potsdam repository mirror; MDPI's own site 403'd both a
UA-spoofed curl and WebFetch, so resolving the DOI to a repository copy is the route that
works for this publisher, not fighting the bot wall) gates *which* units enter the
contextual update at all, by an *entropy-based confidence measure*: a node is admitted to
the spatio-temporal update only where its marginal-posterior entropy exceeds a threshold
set at the scene's own mean entropy (Eq. 13); confident nodes keep their hierarchical label
untouched. *Correction to an earlier draft:* this is an admit/exclude gate, not a graded
"how much" weight — the paper is explicit that admission "decreases the computational
effort," and for admitted nodes the spatial and temporal weights (γ_sp, γ_tp) are hand-fixed
at 1 and never swept (p.2251: "fixed to 1 during the experiment"). No ablation of the gate
itself exists — Table 2 runs every tested variant *with* it. *Inference:* this is still the
mechanism §4.1 is reaching for when it says the local/global weight is "a parameter to be
MEASURED, not set" — but the literature's version answers *whether* to trust local evidence,
not *how much* to discount the prior by. The per-cell version here is to derive a graded
weight from the survey's own measured r and f, so a confident year resists the twelve-year
consensus and an unreliable one yields to it — proportionally, which is a step beyond what
Martinis & Twele's binary gate does. Nothing in the literature does the graded version with
per-survey measured rates.

**Useful negative evidence on ordering:** Liu et al. 2021 smooths spatially *before* the
temporal stage. *Inference:* that bakes spatial-consensus error into the sequence before
the temporal chain ever sees a raw per-cell observation — the same shape as the H2 failure
(§2.2), and an argument for the brief's §4.5 instinct to sit beside the healer rather than
downstream of it.

### 4.3 §6.1 — how much may the layer reshape a mask

**This is the best-answered question in the review, and the answer corrects the intuition
behind it.** **Pasquarella et al. 2022** (**PRIMARY**) confirms from primary text that
**both** canonical segmenters replace every observation inside a stable segment with a
fitted model value — LandTrendr's regression vertices, CCDC's harmonic coefficients.
Trajectory segmentation sits at the **"apply the consensus shape"** end of §6.1's
spectrum, not the conservative fill-or-veto end.

Concrete anchors from that family:

- **CCDC** (Zhu & Woodcock 2014, **PRIMARY**): a break requires **three consecutive**
  threshold-exceeding observations — a *duration* test, not a prior-versus-evidence odds
  ratio. Reported producer's 98% / user's 86% for change. *Inference:* the rule does not
  port. At our measured miss rate a naive "three consecutive absences" fires on ordinary
  label noise about as often as on real loss (§2.3 gives the arithmetic). The
  *transferable* idea is requiring several same-direction observations before acting, with
  the count re-derived from our own r and f.
- **BFAST** (Verbesselt et al. 2010, **PRIMARY**): detects steps >0.1 NDVI under stated
  noise. Needs ~23 observations/year to identify a seasonal term. Does not transfer — we
  have under one observation per year and no continuous index.
- **Murakami & Tsutsumida 2025** (**METADATA**): all three top out below 80% F1 (CCDC
  78.14%) once the domain is urban rather than forest. *Inference:* the accuracy ceiling
  drops in exactly the direction we are moving.
- **Rodman et al. 2021** (**PRIMARY** — full published PDF read 2026-09-11; bronze OA link
  dead, Unpaywall reports closed, retrieved via Sci-Hub mirror): detectability tracks
  disturbance severity and agent, confirmed with real numbers, not the qualitative
  paraphrase this entry previously carried. LandTrendr caught 74.3% of fire disturbances
  within one year vs. 26.5% of spruce-beetle mortality; even restricted to the 30.1% of
  beetle events with a confident onset year, detection was still 61.8% — 12.5 points below
  fire. The severity–detectability relationship is positive for *both* agents (β = 0.98,
  p < 0.01). Net areal effect: LandTrendr mapped 37–41% less disturbed area than
  perimeter/index-based reference methods. *Note: the earlier ⚠ NUMBERS flag pointed at no
  figure actually present in this entry — it was stale.* *Inference:* a segmentation-style
  layer trades one omission pattern for another; it is not immune.

**The fill-or-veto alternative the brief is reaching for does exist, in a different
literature.** **Reiche et al. 2015** (**ABSTRACT**) and the operational **RADD** system
(Reiche et al. 2021, **ABSTRACT**) hold a provisional change call *pending* and either
confirm or drop it as later observations arrive — evidence accumulates, and a later
observation can overturn an earlier call. RADD reports user's 97.6% / producer's 95.0% for
confirmed alerts ≥0.2 ha. *Inference:* the confirm-or-reject dynamic is the closest
published analog to "fill or veto single cells, never redraw," but its statistics assume
6–12 day revisit; only the design pattern transfers, not the thresholds.

**And the underlying theory for our exact object exists but has never been applied here.**
**Polunchenko & Tartakovsky 2012** (**PRIMARY**) surveys sequential change-point detection
for Bernoulli sequences with *known* pre- and post-change parameters — CUSUM,
Shiryaev-Roberts, GLR — which is literally the arithmetic of §2.3. A dedicated search
found **no remote-sensing paper applying formal change-point statistics to a binary
land-cover mask sequence with pre-measured per-epoch recall and false-positive rates.**
That combination appears to be genuinely absent from the indexed literature.

### 4.4 §4.2 — development as a dated, local, directional prior

**This is the largest negative finding in the review, and it should change how §4.2 is
scoped.** Every source that pairs dated construction records with canopy change uses them
as a **post-hoc explanatory join over an already-independent change map** — never as an
input that asserts or weights evidence during detection:

- **City of Seattle 2023** (**PRIMARY**, 32-page PDF read incl. appendix tables) is the
  cleanest instance and the most locally relevant source in the review. Redevelopment
  parcels are 1.0% of city land but account for 13.7% of citywide **net** loss; by zone,
  2.9% of Multifamily land carries 78% of that zone's net loss. *Inference, and it is
  load-bearing:* those are **net-over-net** ratios. Calibrating q_loss needs **gross**
  flip rates, which the report does not break out; the gross upper bound is ~4.9%
  citywide. Do not carry the 13.7–78% figures into a prior without that correction.
- **Guo et al. 2018 / 2019, Morgenroth et al. 2017** — three papers from one Christchurch
  group (Guo 2018/2019 now **PRIMARY** via the author's PhD thesis, University of Canterbury
  repository, hdl 10092/16832, read 2026-09-11; Morgenroth 2017 stays **ABSTRACT/METADATA,
  UNREADABLE** — closed in both Unpaywall and OpenAlex). This is a monoculture rather than a
  corpus; weight accordingly. *Correction to an earlier draft:* the 1.4 m tree-to-building
  figure is real and is confirmed in Guo et al. 2018 — both the publisher's own abstract
  ("trees were most likely to be removed if they were within 1.4 m of a redeveloped
  building…") and the thesis (Ch.3 §3.3.2: "The probability of tree removed was
  approximately double if a tree was closer than 1.4 m to the boundary of a building,"
  P=0.66 vs 0.35). *But it is not a removal radius* — it is a CART split point the
  classification-tree algorithm chose on one continuous predictor (crown edge to nearest
  same-property building, 2011 imagery), in one pruned tree fit to 6,966 trees on 450
  post-earthquake Christchurch properties (73.4% accuracy). It does not generalize even
  within this one research group: the 2017 study (Morgenroth et al., via a self-archived
  conference deck, since the paper itself stays unreadable) splits the same variable at
  **0.7 m**. Still do not use 1.4 m as a parameter — not because it is fabricated, but
  because it is a sample-specific decision-tree artifact, not a measured physical or
  regulatory threshold.
- **Pedley & Morgenroth 2025** (Sustainable Cities and Society, **PRIMARY** — full
  publisher-paginated PDF via the UC repository, hdl 10092/108884, read 2026-09-11) is the
  fourth paper in this group, and its own numbers cut *against* a development-loss prior at
  the citywide scale even while confirming one at the parcel scale. Table 2: redeveloped
  properties are 2.33% of the 72,671 treed residential properties studied and carry only
  **12.78%** of citywide canopy loss — 87.22% of all loss sits on unmodified land ("over 87%
  of the total loss occurred on unmodified properties with no recorded building work for new
  residential units"). Per-property severity still ranks cleanly by redevelopment intensity
  — pre-existing canopy lost: intensification 74.2%, rebuild 47.9%, minor 21.4%, no build
  13.7% — so the prior is well-founded *per parcel* but explains only a small share of the
  citywide total.
- **Ossola & Hopton 2017** (**PRIMARY**, PMC full text) tracked 28,427 lost stems at 92–97%
  detection accuracy and found loss associated with neighbourhoods developed **before the
  1970s** — standing stock and neighbourhood age, not new construction.

**What has no prior art at all:** feeding a single **dated point event** forward as a
**time-decaying, directional** prior on a transition probability. Seven search angles
across remote sensing, deforestation risk modelling, and crime/disease mapping returned
nothing. §4.2's core construct is novel.

**The sharpest warning: Rosa et al. 2013** (**PRIMARY**, PLOS ONE full page). An
ancillary-layer-modulated deforestation prior achieved AUC 0.92 and put ~80% of cumulative
deforestation within 10 km of its predicted high-probability areas — while matching the
predicted location *and* year exactly only ~2% of the time. *Inference:* this is the
where-versus-when failure in its purest form. A building anchor could be right about which
cells are at risk and still be wrong about the year — and the year is precisely what a
per-epoch chain consumes. Any §4.2 validation must score the *year*, not only the place.

**Also absent, all four of them:** no measured clearing-to-completion lag (the brief's
1–3 year, bare-graded-earth hypothesis is unvalidated in the literature); no assessor
year-built reliability assessment against imagery that could be retrieved; no
false-positive check on parcels that stayed vegetated near new construction; and no clean
decomposition of canopy loss into development versus storm, disease and single-lot
removals. *Inference:* the brief's proposed first measurement — the enrichment count at
30/60/100 m on the gold points (§4.2) — is not a shortcut past the literature. It is the
measurement the literature never made.

### 4.5 §4.3 — lidar as teacher

**The contract is well defined.** **Vapnik & Vashist 2009** (**METADATA**) and
**Lopez-Paz et al. 2016** (**ABSTRACT**) define privileged information as present at
training and *structurally absent* at inference, with generalized distillation as the
teacher/student form. *Inference:* this gives a one-line audit for why H2 died (§2.2) —
the 2016 structure channel was a live input at inference, so it never satisfied the
contract — and it is the test any §4.3 build must pass.

**Four real precedents train on lidar and deploy lidar-free:**

- **Lang et al. 2023** (**PRIMARY**, PMC mirror, numbers confirmed) — the honest exam
  design worth copying: validation on **geographically held-out** tiles, plus a check
  against fully independent airborne lidar never used in training (RMSE 7.9 m, bias
  1.7 m). That degradation is the price of losing the privileged signal.
- **Tolan et al. 2024** (**PRIMARY** — upgraded 2026-09-11 by reading the open-access
  preprint, arXiv:2304.07213; the Elsevier version stays paywalled) is a **second honest
  exam worth copying, and the numbers now attribute properly.** It is evaluated not only on
  held-out aerial lidar but against reference data from outside any aerial-lidar coverage:
  ~2×10⁴ GEDI spaceborne samples drawn globally, the Brazilian National Forest Inventory
  (1,450 10×10 m subplots across 87 plots), and 8,903 human-annotated tree/no-tree
  thumbnails. Figures by reference set: **MAE 2.8 m** on the NEON aerial-lidar test (USA);
  **MAE 2.7 m** SSL+GEDI average; **MAE 5.1 m in São Paulo**; ME 0.6 m; **RMSE 4.25 m**
  against NFI field data. *Inference:* the headline 2.8 m is the best case, on home ground
  against the same instrument it trained on — the independent-region field check is nearly
  double that. Read our own r/f the same way: the number against the reference you trained
  toward is not the number you get elsewhere.
  It also reports saturation above 30 m (GEDI RH95) and a negative bias for trees >15 m
  (ME −1.00 m) — height-regression artifacts that do not bind directly on binary presence,
  but which say the model's grip weakens exactly on mature canopy.
- **Lai et al. 2026**, **Pesonen et al. 2026** (**ABSTRACT**, both arXiv preprints) — the
  second is closest to §4.3's add-only label-correction role: lidar-derived pseudo-labels
  refined against the image itself before being used as supervision.
- **Song et al. 2026** (**ABSTRACT**) is a one-directional, lidar-anchored correction —
  architecturally close to add-only — but it trains **and evaluates only on
  lidar-intersected pixels**. It never leaves lidar coverage, so it cannot be cited as
  evidence such corrections generalize.

**The residual, and it is the whole question:** every precedent tests **cross-region**
generalization. **None tests cross-year or cross-sensor.** The precise failure that killed
H2 — one epoch's structure bleeding into a different year — has no literature precedent.

What the field does instead is **avoid** the hazard, and the pattern is now confirmed in
four independent systems. **Tolan et al. 2024** states its site-selection rule outright —
"we selected sites with imagery acquired less than two years from the observation date" —
i.e. the temporal gap is engineered *down to under two years* and then not measured;
**Kalinicheva et al. 2025** restricts training pairs to the same calendar year as the lidar
reference *by design*; **Pauls et al. 2025** uses continuously-arriving GEDI footprints so
no epoch is ever frozen; **Zhou et al. 2020** (USGS LCMAP, **ABSTRACT**) refreshes training
data per year and reports ~10 points of accuracy improvement from doing so.

> *Inference, and this is the firmest conclusion in §4.3:* four well-resourced teams all
> treat lidar-year/imagery-year mismatch as serious enough to design around, and **none of
> them publishes the cost of not doing so.** Our stack cannot use any of the four
> mitigations — one hand-labeled flight, lidar in one year, a fifteen-year span. The gap
> between a two-year tolerance and our worst case is roughly eightfold, and it is
> unmeasured everywhere. That is not a reason to abandon §4.3; it is the reason §4.3's exam
> has to be run on our own data before the teacher is trusted. **Islam et al. 2026** (**METADATA**)
is the nearest affirmative check: it tests whether a training footprint's *year* predicts
accuracy and reports no meaningful degradation (R² 0.72, 539,611 held-out footprints) —
but only for years the lidar actually flew, which is exactly not our case for ten of
twelve surveys.

Adjacent and quantified: **Capliez et al. 2023** (two papers, **PRIMARY** — full author
postprints read 2026-09-11 via HAL, `hal-04097327` and `hal-05181753`) measures source-year
→ target-year classifier transfer against per-year field ground truth. *Correction to an
earlier draft: the "7–12 F1 points" figure was misattributed.* That figure is the JSTARS paper's own
abstract claim for its proposed adaptation method's margin *over competing UDA methods* —
not the unadapted transfer loss. The actual unadapted loss (best supervised baseline, no
adaptation, same target test set): **15.0–17.9 F1 points across five transfer tasks**
(range 9.1–23.7 over all model/task pairs), with the paper's own text putting the worst case
at "around 18 points of F1-score." *Inference, corrected:* cross-year transfer degrades by
roughly 15–18 points unadapted in this setting — a double-digit margin holds for 11 of 12
model/task pairs (9.1 the exception), not by the 7–12 figure previously cited here. One
caveat on comparability: Capliez's setting is more forgiving on acquisition (same sensor,
same GSD, per-year ground truth) but *less* forgiving on change — annual crop rotation is a
larger real shift than canopy growth — so this is not a clean upper bound on our case either
way.

### 4.6 §4.4 — the two training levers

**(a) Deep supervision.** The mechanism is well established: **Lee et al. 2015**
(**ABSTRACT**) is the origin; **PSPNet** (Zhao et al. 2017, **ABSTRACT**) is the
production precedent, with an auxiliary weight of **0.4** found best in its own ablation.
The brief's proposed 0.1 comes from Mobsite et al. 2026, whose numbers live in §2.5 (Kam
read the paper; this review confirmed the record exists — DOI 10.1016/j.aiig.2026.100222 —
but could not re-fetch the ablation table behind a 403).

> *Inference: the disagreement between 0.4 and 0.1 is itself the finding.* The right
> auxiliary weight is architecture- and head-count-dependent. Neither number should be
> imported; §4.4a needs its own sweep at the 33-block tier.

**The load-bearing caution is Ma et al. 2021** (**PRIMARY**, PMC full text with ablation
tables): a **naively-specified auxiliary target scored worse than no deep supervision at
all** — DSC 88.74 vs 88.95, sensitivity 87.95 vs 89.56 — and only helped once the
auxiliary targets were made task-appropriate (89.18). *Inference:* this is direct support
for the brief's IGNORE-aware requirement. A downsampled auxiliary label that folds 255
into background is the exact shape of "naively specified," and the published expectation
is that it makes things worse, not merely neutral. **No published ablation anywhere uses a
three-state 0/1/255 convention** — that part is ours to test.

Domain-matched precedent exists: **Chen et al. 2018** (**ABSTRACT**) applies deep
supervision to true-orthophoto aerial imagery at 5–9 cm GSD — essentially our finest tier
— and reports that deep supervision contributes independently of multi-scale fusion
(qualitative; the numeric tables were not retrievable).

**(b) Resolution curriculum.** **Zero direct hits** across multiple phrasings for a
segmentation curriculum that degrades imagery *and* labels to a coarse GSD, trains, then
fine-tunes at native resolution. The nearest analogs are a *label-taxonomy* curriculum
(Chen et al. 2024, **METADATA** — a different axis entirely) and **FixRes** (Touvron et al.
2019, **ABSTRACT**), which is classification with no label degradation.

> *FixRes is nonetheless a real methodological caution:* part of any coarse-then-fine gain
> can be a train/test scale-calibration artifact — batch-norm statistics and apparent
> object size — recoverable by a cheap recalibration alone, with no curriculum learning at
> all. §4.4b must control for this, or it will credit the curriculum for a free
> normalisation fix.

This compounds a conclusion we already reached internally:
`DEGRADED_IMAGERY_RESEARCH_2026-08-27.md` established that a naive downsample→blur→noise
chain yields a model that works on the fakes, and chose a separately-trained coarse head
over a curriculum schedule. That report is the home for the degradation-synthesis
decision; §4.4b inherits its constraint rather than reopening it.

**(d) Is detectability ordered by GSD? No — independently confirmed.** **Brown et al.
2022** (**ABSTRACT**) held GSD fixed at 0.5 m/px and varied only the optical
point-spread-function: detector mAP moved by **>50%** from aperture type alone.
*Inference:* outside confirmation, in a different task, of the measured finding that
season and sensor dominate over nominal resolution (§4.4).

### 4.7 §2.4 — what the gold set can and cannot carry

Two literatures apply, and neither was written for our situation.

**Design-based accuracy assessment** — **Olofsson et al. 2014** (**PRIMARY**, full PDF),
Olofsson et al. 2013, Stehman & Czaplewski 1998, **Stehman & Foody 2019** — prescribes
stratifying toward rare classes and using design-consistent estimators for area and
confidence intervals rather than counting mapped cells. **Stehman & Wagner 2024**
(**PRIMARY**, ⚠ NUMBERS) works the rare-class regime specifically and defines it as ≲10%
prevalence; our loss class (~3.5% of gold points) and gain class (~0.16%) sit well below
that, gain by roughly 60×. Its central result: **no single sample allocation optimally
serves user's accuracy, producer's accuracy and area estimation at once.**

> *Inference:* these transfer as a design template for the *next* round of gold collection
> — deliberately oversample predicted-loss and predicted-gain cells — not as a retrofit.
> The unbiased estimators require documented per-stratum inclusion probabilities, and
> §2.4 does not record how the 1,214 points were drawn.

**Reference-data error** — and this strand bites harder, because it attacks the emission
rates themselves:

- **Foody 2010** (**ABSTRACT**): a 10% reference error rate produced ~18.5%
  underestimation or ~12.3% overestimation of producer's accuracy depending on whether
  reference and map errors were *correlated*, and the bias was worst when change was rare.
- **Radoux & Bogaert 2020** (**ABSTRACT**): if reference labels carry error correlated
  with the map's own error, the observed confusion matrix is biased in a *direction*, not
  merely noisy.
- **Radoux, Waldner & Bogaert 2020** (**ABSTRACT**): reference-label reliability is worst
  in class-mixed units.

> *Inference, and this is the sharpest thing in this section:* our r and f are scored
> against references that stare at the same ambiguous canopy edges the model does, and the
> 42 loss points are disproportionately edge-adjacent, class-mixed cases. If that error is
> correlated, the likelihood ratios in §2.3 (2.5 per absence, ~39:1 for four, ~49:1 for
> q_loss) could be systematically off rather than merely uncertain. The arithmetic that
> killed crown state v2 rests on rates whose bias direction is unmeasured.

**The missing false-positive class is field-wide, not an Edmonds defect.** No reference
protocol found in any thread — Nowak & Greenfield's point sampling, Ossola & Hopton's
200-stem check, Coupland et al.'s 342-polygon test — includes a "canopy asserted where
none exists" class. *Inference:* it cannot be fixed by adopting anyone's protocol. If the
consistency layer is allowed to *add* canopy, the stratum that would catch its
characteristic error does not exist yet, here or anywhere.

### 4.8 §1 — prior art on our actual problem: heterogeneous archives

- **Walton 2008** (**ABSTRACT**) is the mirror image of our failure and worth holding
  next to it: comparing two heterogeneously-produced canopy products manufactured apparent
  *change* where photo-interpreted truth showed little. Uncorrected survey heterogeneity
  launders in both directions — no-change into false change, and (our case) real change
  into agreement. Same root cause.
- **Blackman & Yuan 2020** (**ABSTRACT**) works an 81-year heterogeneous aerial archive
  and reports our asymmetry: an abrupt disturbance (tornado) stayed detectable while
  diffuse decline (disease) did not.
- **Coupland et al. 2022** (**PRIMARY**, full text) is the methodological standout:
  before trusting a 1949→2015 difference, they ran **both** 2015 sensors through the same
  pipeline on the **same date** and established statistical equivalence (TOST, ±5.38% TCC)
  first. They also concede plainly that resampling "cannot correct for differences in
  shadows and color." *Inference:* the same-date equivalence test is the right instrument
  and we cannot run it — no epoch in our archive has two sensors on one date.
- **MacFaden et al. 2012** and **O'Neil-Dunne et al. 2014** (**ABSTRACT**) solve
  rooftop/shadow confusion by co-acquiring lidar at **every** epoch — the resource we do
  not have and, per §2.2, cannot safely substitute.
- **Pedley & Morgenroth 2025** (ISPRS Open J. **15**:100082, CC BY, **PRIMARY** — full text
  read 2026-09-11) is the closest problem shape: fine-scale, property-level canopy *loss*,
  deliberately tuned precision-high (0.941) over recall (0.811) — verified verbatim, Table 3
  and abstract: "Precision values were higher than recall values (0.941 compared to 0.811),
  which reflected a deliberately conservative approach to avoid false positive detections."
  *One correction the fetch surfaced, worth noting even though it was inconsistent to grade
  this METADATA while quoting specific numbers — that inconsistency is now resolved by
  actually reading the paper:* the loss signal here is **2016→2021 lidar height change**
  overlaid on the 2016 canopy layer, not imagery differencing — placing its *inputs* in the
  same lidar-dependent class as MacFaden/O'Neil-Dunne above, even though its *objective*
  (fine-scale loss detection from misaligned multi-date data) is the closest match in the
  review. *Inference:* that is the mirror of our operating point — they suppress false loss
  calls, we suppress true ones. Adopting their threshold relocates the failure rather than
  fixing it, and the resource it leans on (lidar at both epochs) is exactly what §2.2 says we
  cannot safely substitute for.

### 4.9 §4.5 — where the layer sits, and why probabilities matter

**The literature supports the brief's instinct, and gives it a sharper reason than the one
§4.5 states.** §4.5 argues for sitting beside the healer because seven of ten interior
epochs carry only IGNORE. The published argument is broader: **hard decisions destroy
information that post-processing needs, and deferring them measurably wins.**

- **Cheng & Liu 2020** (**PRIMARY**, full text with tables) defers argmax to the end of a
  two-stage soft filter chain: mIoU rises across all four backbones tested — FCN
  0.5245→0.5349, FastFCN 0.6286→0.6432, DeepLab 0.6294→0.6431, PSPNet 0.7940→0.8024
  (+0.8 to +1.5 points), with pixel accuracy +0.38 to +0.62 points.
- **Li, Liu & Pfeifer 2019** (**ABSTRACT**, numbers from fetched abstract) smooths *label
  probabilities* by probabilistic relaxation instead of post-hoc on hardened labels:
  **+7.01%** overall accuracy (Vienna) and **+6.88%** (Vaihingen), and the authors note
  small/fragmented features survive better this way.
- **Wu et al. 2017** (**ABSTRACT**) and **Câmara et al. 2024** (**ABSTRACT**) are explicit
  stay-in-probability-space architectures; Câmara's is a current, shipped implementation
  (the R `sits` package) with a non-isotropic neighbourhood prior designed *not* to blur
  across real class borders.

> *Inference:* this is direct support for placing the layer where evidence is still soft.
> It also raises a question §4.5 does not ask: our masks are hardened to 0/1/255 at
> `threshold_and_clean`, so even the "raw" stack is already post-argmax. The strongest
> version of §4.5 is not merely "beside the healer" but "upstream of the hard threshold"
> — which is a bigger change than the brief currently scopes, and worth deciding
> deliberately rather than by default.

**One contrast worth recording, not glossing.** Cheng & Liu's two stacked soft filters
**composed** (a parameter sweep shows they do not cancel across a 0.5–0.8 weight range).
That is the opposite direction from our own measured finding that 3×3 opening and closing
are neutral because they cancel (§2.4). *Inference:* stacking is not universally
lossy — the cancellation we measured is a property of that operator pair, not a general
law. Do not generalise our open/close result into "stacked post-processing cancels."

**A genuine gap:** no peer-reviewed treatment was found of **no-data/IGNORE sentinel
propagation through a multi-stage raster post-processing chain** — the exact §4.5 worry
that a stage cannot distinguish "not canopy" from "not observed." Multiple phrasings
returned only GIS tooling documentation. That failure mode is ours to characterise.

### 4.10 §6.2 and §6.3 — buildings and water as hard negative context

**§6.2 asks whether a roof is a roof every year, entering as a HARD negative. The
literature's answer is more discouraging than expected.**

- Hard ancillary vetoes over a classifier's output are **standard, unremarkable practice**
  — so the technique itself is not exotic.
- **But nobody measures what the veto costs at its failure edges.** No verified paper
  quantifies the damage from a footprint offset, a demolished-but-still-registered
  structure, or canopy overhanging a roof. Searched directly; the limitations sections are
  silent.
- **And the one paper that squarely addresses canopy over buildings points the other way —
  though its framing needed correcting once read in full.** **King & Locke 2013** (**PRIMARY**
  — full text via USDA Forest Service Treesearch, read 2026-09-11) documents that a
  high-resolution NYC seven-class land-cover product, in its mutually-exclusive GIS
  classification, assigns canopy overhanging a building to the tree class rather than the
  building class: "Each class is mutually exclusive and tree canopy that hangs over
  buildings are assigned to the tree class" (p.64). The companion i-Tree field protocol
  counts both independently rather than choosing (p.63). *Correction to an earlier draft:*
  the paper never calls this a field-wide "convention" — it is a stated property of *one*
  data product's methodology (the NYC map, built on MacFaden et al. 2012), not a surveyed
  practice across the urban-forestry field. The abstract alone (the earlier grade) could
  never have supported the "field convention" framing as written — the claim outran its
  cited evidence, and happened to land close to something true. *Inference, revised:* a
  hard building veto would still put us against how at least one closely-related,
  methodologically-documented product handles this exact case, and would still delete real
  overhanging canopy — a class of error our gold set (§2.4) has no label for and therefore
  cannot detect. That is weaker support than "the field's own convention," and worth stating
  at its actual strength. (A true field-wide convention, if one exists, would need to come
  from MacFaden et al. 2012 or the UVM Spatial Analysis Lab methodology behind the ~four
  dozen urban tree canopy assessments King & Locke cites — not yet fetched.)
- **The soft alternative has a concrete precedent.** **Sun et al. 2022** (CG-Net,
  **ABSTRACT**) conditions a segmentation network on GIS footprints by feature
  normalisation rather than pixel-wise masking, and is explicitly engineered to tolerate
  positional error in the GIS layer instead of assuming the footprint is exact.

> *Inference, as a direct answer to §6.2:* the literature gives no basis for the hard
> form, one closely-related data product's methodology against it (not a surveyed field-wide
> convention — see the correction above), and a workable soft form. Under §3 rule 3, a
> hard veto is a rule that can reach a terminal absence through an ancillary layer, so it
> needs its own at-risk count — and **nobody in the literature has one to borrow**.
> Entering buildings as a soft, one-directional prior on the transition (the same shape
> §4.2 already proposes for development) is the form the evidence supports.

**§6.3 — is a buildings vision model worth building before the enrichment count? The
literature answers this one cleanly: no.** **Li et al. 2022** (**PRIMARY**, full text via
the DLR open-access mirror) is exactly this study: an FC-DenseNet detects buildings from
40 cm orthophotos plus a normalised DSM, overlays them on the official cadastral register,
and flags what the register is missing. Detection F1 **85.14% ± 0.55**; precision at
flagging genuinely undocumented buildings, ground-truthed by manual interpretation in a
held-out city, **82.27%** (1,271 of 1,545).

> *Inference:* a purpose-built detector for this exact task does not replace the assessor
> clock with ground truth — it trades our known ~2.5% coverage gap (§2.4) for a different
> error of comparable size, and adds its own false positives. That supports the brief's
> own ordering (§7 item 1): run the cheap enrichment count first. The paper also names a
> failure mode §4.2 has not budgeted for — buildings missing from the register for reasons
> **other than recency** ("old undocumented"), which a `yr_built`-driven prior would place
> at the wrong date entirely rather than merely miss.

### 4.11 Operational products — what "temporally consistent" means in print

Three shipped systems were examined because two of them sat in our own PDF library. All
three share one architecture: **carry a stable reference year forward except where an
external change mask fires.** None reports recall on confirmed real change.

- **Li et al. 2025, GLC_FCS30D post-processing** (**PRIMARY** — full text read directly to
  settle this entry; see the correction note below). Spatiotemporal majority filtering plus
  LandTrendr-based removal of "excessively frequent" transitions cut cumulative mapped
  change from **7,537 Mha to 1,981 Mha — a 74% reduction in all labelled change** — while
  overall accuracy rose 73.04% (±0.30) → 74.24% (±0.29), a 1.20-point gain. Both figures
  verified verbatim.
  **Correction to an earlier draft of this review:** it is *not* true that this paper lacks
  a change-stratified number. Its Table 6 gives a changed/unchanged error matrix against
  two independent reference sets (LCMAP_Val, LUCAS), reaching OA 91.53% (±0.33) and 91.16%
  (±0.05), and the authors state plainly that "the O.A. is primarily contributed to by
  unchanged pixels, while the P.A. and U.A. for changed pixels are relatively lower,
  indicating that land cover-change pixels are more difficult to capture."
  *Inference, revised:* this is the **best-practice example in the review**, not the worst.
  The headline pair (74% of change removed, +1.2 points OA) still cannot by itself show
  real change survived — but the paper does not stop there, and its change-stratified
  matrix is the reporting template §5 of the brief should copy. That the changed-pixel
  producer's accuracy falls well below the aggregate is exactly the effect we should expect
  to see in our own numbers, and should look for.
- **Reis et al. 2020, CMAP** (**ABSTRACT**) builds transition validity into the classifier
  so invalid trajectories are impossible by construction; the baseline produced invalid
  trajectories in >50% of images. *Inference, and it matters for our own criterion:* the
  metric is **gameable in the same way ours is** — a classifier that always repeats the
  prior label scores zero invalid transitions trivially. The paper does not test that
  degenerate case. Our impossible-triples criterion (§2.1, §5) has the same property, which
  is why §2.1 already records that the both-sides rule had **no power** at this cadence.
- **Liu et al. 2026, NAIP** (**PRIMARY**, read twice, independently) reports overall
  accuracy rising with survey quality tier, and tree-canopy F1 rising 0.702 → 0.903 across
  those tiers. **⚠ Version discrepancy, recorded rather than resolved:** the published
  *Landscape Ecology* PDF held locally gives OA 0.733 (2004) / 0.887 (2014) / 0.886 (2017),
  while the open-access PMC mirror — which is the Research Square *preprint* — gives 0.788
  / 0.874 / 0.848 for the same years. Same paper, two versions, different numbers. Prefer
  the published PDF we hold; do not cite the preprint figures. Crucially, and consistent in
  both versions, **track assignment is fixed by acquisition year and known sensor quality,
  not by a measured per-year accuracy.**
  *Inference:* that is a documented **anti-pattern** against §3 rule 4, which requires each
  survey's vote to be weighted by its *measured* eyesight. The authors concede their label
  propagation "can introduce coarse boundaries and miss fine-scale transitions such as
  small new constructions" — our failure mode, admitted and unquantified.
- **Li et al. 2026, ALCC** (**ABSTRACT**; mean OA 81.11 ± 0.67% primary-verified via the
  Zenodo release) uses ensemble change detection (CCDC + BFASTm + Chow test) to flag change
  years, then classifies only flagged pixels. *Correction to a figure worth flagging:* the
  often-quoted "8.52–34.24% improvement" measures accuracy in areas where prior *products
  disagreed with each other* — not recall on independently confirmed change. It does not
  answer the question it appears to answer, and it is ⚠ snippet-only besides.

*Inference across all three:* the ensemble-change-gate idea is attractive but depends on a
dense same-sensor series (CCDC/BFAST need it) that our twelve irregular aerial surveys do
not provide. What transfers is the reporting discipline: an aggregate accuracy number plus
a change-area-reduction number, reported *alone*, cannot show real change was preserved —
Li et al. 2025 does not stop there, and neither should we. Their change/no-change error
matrix against independent reference data is the shape to copy; the lidar-certified
GAIN/FLAT populations (§2.2) give us a denominator built from an independent instrument
rather than photo-interpretation, which is a stronger reference than they had.

There is also no standard metric to adopt: searches for a settled "trajectory validity" or
"inter-annual agreement" definition found none. The field uses ad hoc, per-paper phrasing
("illogical transition," "invalid transition," "erroneous change"). *Inference:* we will
have to define ours, and should define it against a change-stratified denominator from the
start.

### 4.12 Adjacent-field theory for four of the §5 gaps (round 3, 2026-09-11)

Rounds 1 and 2 searched remote sensing and found the gaps in §5. Round 3 (four threads,
21 new works, 16 read in full) searched the fields where the same mathematics recurs under
other names — geostatistics, total-variation image analysis, statistical process control,
biosurveillance, denoising theory, missing-data signal processing — for gaps 3, 7, 10 and
12. **No paper closes any gap. Several supply one half of one.** Every pairing of a
paper's result with our objects (r, f, the 0/1/255 mask, a probability raster) is this
review's substitution and is labelled so; none of it is measured on our data. **Convention:
throughout this review and the brief, `r` is recall, `P(x = 1 | z = 1)`, and `f` is the
false-positive rate; the miss rate is `1 − r`.** The round-3 agents wrote `r` for the miss
rate; every substitution below has been re-expressed in the brief's convention. The
framework that assembles these halves lives in
`FRAMEWORK_GAPS_SPATIOTEMPORAL_CONSISTENCY_2026-09-11.md`, which cites this section and
carries no bibliography of its own.

**4.12.1 §4.1 — the weight, and the size below which smoothing erases real change (gap 3).**

- **Strong & Chan 2003** (**PRIMARY**, UCLA CAM mirror, 23 pp) gives the erasure threshold
  in closed form — for one operator, total-variation regularisation. §3.1 is titled
  verbatim "Change in image intensity δ = α/scale," with "scale = |Ω|/|∂Ω|" (area over
  boundary length; r/2 for a disk): contrast loss is "inversely proportional to scale and
  directly proportional to α," so "TV regularization causes smaller-scaled features (such
  as noise) to be partially or entirely removed while larger-scaled image features are
  relatively unaffected." Checked on a discrete image, not only in the continuum:
  "δpredicted = α/scale = [2π(1/3)/π(1/3)²](0.01) = 0.06, so that in the circular region
  the intensity level should be 0.94 after regularization. This is nearly exactly the
  case." And the update is feature-local — "δi does not depend on the effects of the
  regularization felt in any other region" — which is what would make it tractable at
  13.3 M cells. *This review's derivation, not the paper's:* a feature is fully erased when
  δ ≥ its contrast h, i.e. when r ≤ 2α/h. In a probability raster h = p_before − p_after
  is usually well under 1, so **the same α erases a physically larger tree removal where
  the model is 60 % confident than where it is 95 % confident.** α is a free parameter in
  the paper, not estimated.
- **Gräler, Pebesma & Heuvelink 2016** (**PRIMARY**, R Journal) shows the space↔time
  exchange rate fitted rather than set: one anisotropy scalar κ "given as spatial unit per
  temporal unit," with "All temporal distances… internally re-scaled to an equivalent
  spatial distance," "numerically optimised using… fit.StVariogram and the L-BFGS-B routine
  of optim" — 189 km/day (metric), 185 km/day (sum-metric), and "The spatio-temporal
  anisotropy is estimated beforehand and fixed at 118 km/day." Table 2 sweeps five
  covariance families. **The decision-grade result is negative.** Table 3 (leave-one-out):
  RMSE 6.05–6.16 and correlation 0.84 for *every* model, the pure-spatial one included at
  6.15/6.10 — a threefold spread in variogram fit bought no held-out skill, and dropping
  time cost nothing. Domain first: daily PM10 at German stations on a 10 km grid with a
  ~6-day temporal range; not a general law. *Inference:* what transfers is the protocol —
  fit the weight, then test the fitted model against a pure-spatial (γ = 0) and a
  pure-temporal (β = 0) baseline on held-out data. That is the sensitivity test §5 item 3
  says nobody in remote sensing ran.
- **Krähenbühl & Koltun 2011** (**PRIMARY**, arXiv:1210.5644) is structurally our
  unary-plus-pairwise field and is the scaling evidence gap 4 lacked: mean-field inference
  over "billions of edges even on low-resolution images" in 0.2 s against 36 h for MCMC.
  Its parameters are measured — "use grid search on a holdout validation set for all three
  kernel parameters w(1), θα and θβ" — but the pure-smoothing weight is hand-set and
  declared inert: "The smoothness kernel parameters w(2) and θγ do not significantly affect
  classification accuracy… We found w(2) = θγ = 1 to work well in practice." The real sweep
  is over kernel *range* (θα peaking at 61 pixels, ~82 → 88 %), with "w(1) was held constant
  and w(2) was set to 0." Caution in their words: "long-range connections can also
  propagate misleading information." *Inference:* a warning to carry, not a value to
  import — on their task the weight we most want to measure was the one that did not
  matter.
- Searched and not found: bilateral filtering (its range parameter σ_r bounds a minimum
  edge *amplitude*, not a minimum feature *size*); morphological area openings (the size
  parameter is the threshold by definition, not by measurement, and they act on hard masks).

*Gap 3, restated:* the erasure threshold now has a closed form for one operator; the
weight has a fitting protocol and a documented case where it did not matter. Neither
exists for a joint spatio-temporal field on a probability stack.

**4.12.2 §2.3 / §6.1 — a change detector written in (r, f) (gap 10).**

- **Ross, Tasoulis & Adams 2012** (**PRIMARY**, arXiv:1212.6020) is the Bernoulli CUSUM
  with known pre- and post-change rates, stated in full. §5.1: `C0 = 0; Ct = max(0, C_{t−1}
  + x_t − k)`, `k = r1/r2`, `r1 = −log((1−θ1)/(1−θ0))`, `r2 = log(θ1(1−θ0)/(θ0(1−θ1)))`;
  "A change is flagged when Ct > h(θ0, θ1)," with h set for a target in-control run length
  by the Reynolds & Stoumbos (1999) approximation or by Monte Carlo. The paper's own
  scope statement: it "requires both the pre- and post-change values of θt to be known,
  and is the optimal change detector under this assumption… (Lorden, 1971)." *This
  review's substitution:* for a gain, θ0 = f_t and θ1 = r_t (r = recall); for a loss,
  relabel x → 1 − x and swap r ↔ 1 − f, f ↔ 1 − r. Three caveats, all ours: the rule is
  one-sided; it assumes θ0, θ1
  constant across t, which per-year (r_t, f_t) violate; and at n = 12 no asymptotic
  run-length formula applies, so h must be calibrated by Monte Carlo on null 12-step
  sequences drawn with the per-year rates.
- **Chen & Yang 2022** (**PRIMARY**, arXiv:2203.03384) supplies the misclassification
  correction in closed form, with π_kl = P(X* = k | X = l): eq. (2) `p*₀ = π₁₁p₀ + π₁₀q₀`;
  eq. (7) `p**₀ = (p*₀ − π₁₀)/(1 − π₁₀ − π₀₁)`; Theorem 3.1(b)
  `var{EWMA**} = p*₀(1−p*₀)λ{1−(1−λ)^2t} / [n(1−π₁₀−π₀₁)²(2−λ)]`. *This review's mapping:*
  π₁₀ = f (false positive), π₀₁ = 1 − r (miss), so the denominator is r − f. **The factor
  1/(r − f)² is the noise-floor statement §3.5 of CLAUDE.md asks for**, in one line — at the
  brief's rates r = 0.61, f = 0.05 it is ≈ 3.2, and the brief's emission gate f < r is the
  condition that keeps it finite. Not a change-point rule (an EWMA over n subjects per
  epoch). Code: `github.com/lchen723/SPC-ME-R-code`.
- **Itkin 2026** (**PRIMARY**, arXiv:2606.12476) has the same structure — a latent two-state
  chain seen through a noisy classifier — in a different domain, and gives the general
  form that admits per-year rates: eq. (2) `St = max(0, S_{t−1} + log p1(Xt)/p0(Xt))`,
  `τ = min{t : St ≥ h}`; Proposition 1: "let ω > 0 solve E0[e^{ωY}] = 1… ARL0 =
  e^{ωh}(1+o(1)) and EDD = h/E1[Y](1+o(1))"; Corollary 1(ii): the cross-entropy minimiser
  *is* the log-likelihood-ratio increment. *This review's instantiation:* increments
  log(r_t/f_t) on an observed 1 and log((1−r_t)/(1−f_t)) on an observed 0 (r = recall); for
  binary Y the equation in ω is scalar in (r, f). No (r, f) symbols appear in the paper.
- **Sandia SAND2016-7395C** (**PRIMARY**, bylined "Author 1") corroborates the Bernoulli
  CUSUM form `Bt = max(0, Bt−1 + Xt − r)` and adds nothing; support only.
- **Negatives, each a finding.** All 100 works citing Miller et al. 2013 (Semantic Scholar)
  were pulled and searched for change-point / CUSUM / stopping-rule / Shiryaev / quickest:
  zero. The nearest, Louvrier et al. 2018 (occupancy HMM with misidentification), is
  estimation without a stopping rule. Ecology occupancy + change-point (10 hits): all
  dynamic-occupancy estimation. Biosurveillance (PubMed, Crossref, two web passes): CUSUM
  is used in syndromic surveillance and sensitivity/specificity in freedom-from-disease
  design, and **no paper states a detection rule in (Se, Sp)**. Statistical-process-control
  CUSUMs with inspection error exist for count distributions — Mishra & Singh 2022,
  Chakraborty & Khurshid 2017 — both **UNREADABLE** (403 / abstract only), graded
  ABSTRACT; *Comm. Stat. Sim. Comput.* 38(7) 2009 UNREADABLE (Unpaywall closed). Fearnhead
  & Fryzlewicz arXiv:2210.07066: read, Gaussian change-in-mean only.

*Gap 10, restated:* the statistics (a Bernoulli CUSUM with known rates) and the
misclassification correction (explicit in f and r) both exist in primary sources — in two
literatures that have not been joined. A detector for a 12-epoch mask sequence with
per-year measured (r_t, f_t) still looks unpublished.

**4.12.3 §4.5 — scoring a corrector without letting it grade itself (gap 7).**

- **Ramani, Blu & Unser 2008** (**PRIMARY**, Monte-Carlo SURE) estimates a denoiser's true
  mean-squared error from the noisy input alone. Definition 1, eq. (6):
  `η = (1/N)‖y − f_λ(y)‖² − σ² + (2σ²/N)·div_y{f_λ(y)}`; Theorem 1 makes η unbiased for
  MSE; Theorem 2, eq. (14) estimates the divergence by perturbation —
  `div = lim_{ε→0} E_b′{b′ᵀ((f_λ(y+εb′) − f_λ(y))/ε)}` — so that "f_λ is treated as a
  black box, meaning that we only need access to the output of the operator." *This
  review's reading, and the sign matters:* the divergence enters *positively* and is
  Efron's degrees of freedom. A rigid persistence prior has near-zero divergence, so the
  penalty charges it almost nothing; it is caught by the *residual* term instead, where
  erased real change becomes misfit to the observed mask. (Check: f = identity ⇒ div = N ⇒
  η = σ², the identity's true error.) Blockers: Gaussian noise, known σ².
- **Efron 2004** (**PRIMARY**, JASA) is what makes the idea legal on a binary mask at an
  asymmetric cut. Optimism Theorem 1: `E{Err_i} = E{err_i + Ω_i}`, `Ω_i = 2cov(λ̂_i, y_i)`,
  which "generalizes Stein's result for squared error… to the q class of error measures";
  it explicitly covers Bernoulli y ~ Be(μ), counting error (3.3), binomial deviance (3.4),
  and (3.28) `O_i = 2λ̂_i(y_i − μ_i)`. Remark F (3.29) gives an *asymmetric* counting error
  at a boundary π₁ ≠ ½, to "compensate for unequal prior sampling probabilities" — our 49:1.
  §4, (4.8): cross-validation is a randomised version of the covariance penalty. *Verdict:*
  highest transfer in the thread, and Ω_i is per cell.
- **Batson & Royer 2019** (**PRIMARY**, Noise2Self) gives the architectural form.
  Proposition 1: for a J-invariant f, `E‖f(x)−x‖² = E‖f(x)−y‖² + E‖x−y‖²`; for the
  non-invariant median, the self-supervised loss "tells us nothing about the ground truth
  loss" — laundering in miniature. *Verdict:* the best architectural fit (make the healer
  J-invariant in *time*: the output at epoch t may not read epoch t's mask), **but both
  clauses of Proposition 1 currently fail for our stack, in the dangerous direction** —
  the HMM's whole point is that epoch t's observation is the unary evidence at t. The
  resolution is a scoring question, not an architecture question, and is taken up in the
  framework document; the proposition's additive-independent-noise assumption does not
  describe Bernoulli misclassification, so Efron, not Noise2Self, is the bridge.
- **Chernozhukov et al. 2018** (**ABSTRACT**, Econometrics Journal): "To avoid overfitting,
  our construction also makes use of the K-fold sample splitting, which we call
  cross-fitting." *Verdict:* procedural. The check it imposes: were q_loss, q_gain, the
  transition table or β/γ fit on cells that overlap the 42 gold losses or the §2.2
  GAIN/FLAT populations? If so the score is in-sample.
- **Kumar, Liang & Ma 2019** (**PRIMARY**, NeurIPS): Platt and temperature scaling are
  "(i) less calibrated than reported, and (ii) current techniques cannot estimate how
  miscalibrated they are"; a continuous corrector's "true calibration error is
  unmeasurable with a finite number of bins." *Verdict:* the documented precedent for gap 7
  outside remote sensing, plus a design rule — make the correction measurable by
  construction (a binned corrector is; a continuous one is not).
- **Two caveats bind the whole thread.** (a) SURE, Efron and Noise2Self each require the
  observation to be *unbiased* for truth; our per-year error is systematic (leaf-off
  flights, 80.7 cm effective in 2005). (b) All three estimate **average** risk, and when
  change is rare a launderer genuinely is near-optimal on average error — an unbiased
  average-risk estimate will bless it. The fix is that Efron's Ω_i is per cell: sum it over
  the lidar-certified GAIN and FLAT strata (§2.2), not citywide. Efron's (3.22) needs one
  rerun per cell, infeasible at 13.3 M unless the healer is local; the parametric bootstrap
  (3.17) is the practical route.

*Gap 7, restated:* the methodology exists and is older than the field that lacks it. What
remains open is its extension to spatially and class-correlated error, for which nothing
was found.

**4.12.4 §4.5 — propagating IGNORE through a chain of operators (gap 12).**

- **Sussner et al.** (**PRIMARY**, *J. Math. Imaging Vis.*, doi:10.1007/s10851-011-0283-1)
  defines morphology on any complete lattice — "ε(⋀Y) = ⋀_{y∈Y} ε(y), δ(⋁Y) = ⋁_{y∈Y} δ(y)
  ∀ Y ⊆ L" (eq. 1) — and the interval lattice L^I = {[x, y] ⊆ [0, 1]} ordered "[u,v] ≤ [x,y]
  ⇔ u ≤ x and v ≤ y" (eq. 26), with 0 = [0,0] and 1 = [1,1]; isomorphic to intuitionistic
  fuzzy sets via "φ([x,y]) ↦ (x, 1−y)" (eq. 28), where "the degree of membership and the
  degree of non-membership do not have to add up to 1" — the slack is ignorance. *This
  review's construction, not the paper's:* map 0 / 1 / 255 → [0,0] / [1,1] / [0,1].
  Component-wise infimum and supremum then give exactly Kleene three-valued propagation:
  inf([0,1],[0,0]) = [0,0] and sup([0,1],[1,1]) = [1,1] — IGNORE resolves *only* when
  known neighbours force it — while inf([0,1],[1,1]) = sup([0,1],[0,0]) = [0,1] stays
  IGNORE. Adjunction guarantees opening and closing are idempotent inside the same
  lattice. *Verdict:* a directly adoptable, closed-under-composition rule for the
  morphology stage, conditional on our mapping. Not remote sensing.
- **Liu et al. 2018** (**PRIMARY**, partial convolutions, arXiv:1804.07723) gives the
  renormalisation for probability-domain smoothing. Eq. (1):
  `x' = Wᵀ(X ⊙ M)·sum(1)/sum(M) + b if sum(M) > 0; 0 otherwise`; eq. (2):
  `m' = 1 if sum(M) > 0; 0 otherwise`; and, in their words, "With sufficient successive
  applications of the partial convolution layer, any mask will eventually be all ones."
  *Verdict:* eq. (1) is adoptable; eq. (2) is *optimistic* — one valid neighbour dissolves
  IGNORE — the opposite of conservative, because it was built to fill holes, not keep them.
  A conservative variant (require sum(M) = sum(1), or a fraction of it) is this review's
  inference, not theirs, and carries a free parameter.
- **Appel** (**PRIMARY**, arXiv:2208.08781, *Artif. Intell. Earth Syst.*) restates both
  equations for three-dimensional satellite raster stacks — "M has zeros for missing values
  and ones for valid observations, and we assume X is zero for missing values, too" — and
  is the Earth-observation bridge §4.9 said was absent. Same optimistic mask rule.
- **Sinopoli et al. 2004** (**PRIMARY**, IEEE TAC; text quoted from the Berkeley preprint,
  self-labelled DRAFT) is the exact rule for an unobserved epoch in a sequential
  estimator. "In reality the absence of observation corresponds to the limiting case of
  σ → ∞"; taking that limit, (14) `x̂_{t+1|t+1} = x̂_{t+1|t} + γ_{t+1}P C'(CPC'+R)⁻¹(y − Cx̂)`
  and (15) `P_{t+1|t+1} = P_{t+1|t} − γ_{t+1}P C'(CPC'+R)⁻¹CP`, with γ = 0 on a missing
  epoch: "performing this limit corresponds exactly to propagating the previous state when
  there is no observation update available at time t." The gain zeroes, the state carries
  forward, the covariance does *not* shrink. Their second result is the one to carry: below
  a critical observation rate the error covariance is unbounded. *Verdict:* yes for the
  temporal layer; the two-state-chain analogue of the critical rate is derived in the
  framework document.
- **Przewiezlikowski et al. 2022** (**PRIMARY**, MisConv, WACV) computes the expected
  convolution over a fitted density of the missing values. *Verdict:* **no** — it
  marginalises, i.e. imputes; that turns IGNORE into a class, which §3.6 of CLAUDE.md
  forbids.
- Not pursued: Rubin's MCAR/MAR/MNAR taxonomy (governs inference validity; yields no
  operator-level rule); Bloch, doi:10.1016/j.ijar.2012.05.003, bipolar morphology —
  **METADATA**, likely redundant with Sussner.

*Gap 12, restated:* closed for the morphology stage and for the missing-epoch update,
conditional on two substitutions that are ours; open on the conservative mask fraction,
which is a hand-set constant until a principle ties it to the erasure threshold.

---

## 5. What the literature does not have

Stated plainly, because these are decision-grade and each one was searched for
deliberately:

1. **Change-stratified reporting is rare, but it is not absent** — see the correction in
   §4.11. Most consistency papers in the corpus report only self-agreement. Li et al. 2025
   is the counter-example and the model to copy. No paper found reports a
   recall-on-real-change figure for a *canopy* consistency layer at our resolution, so
   there is still no like-for-like benchmark for 240/327 — but the weaker, verified claim
   is the one to rely on.
2. **No forward-fed dated event prior** (§4.2). Zero prior art in remote sensing,
   deforestation-risk modelling, and crime/disease mapping — seven search angles. **Round 3
   narrows the wording, not the finding:** a time-decaying, directional modifier on a
   transition rate is a proportional-hazards model with a time-varying covariate, and
   survival analysis was *not* searched. "Framing exists, unsearched" is the honest state;
   "no prior art" overstated it.
3. **No measured spatial-vs-temporal weight, no sensitivity sweep, no change-size erasure
   threshold** (§4.1). **Narrowed in round 3 (§4.12.1):** the erasure threshold has a
   closed form for total-variation smoothing (δ = α/scale, Strong & Chan 2003); the weight
   has a fitting protocol with a held-out test against β = 0 / γ = 0 baselines (Gräler et
   al. 2016), and one documented case where the weight did not matter (Krähenbühl & Koltun
   2011). Still absent: either result for a joint spatio-temporal field on a probability
   stack.
4. **No inference evidence near 13.3 M cells × 12 epochs** for any joint spatio-temporal
   field. **Narrowed for the spatial term only (§4.12.1):** dense-CRF mean-field inference
   runs over "billions of edges" in 0.2 s (Krähenbühl & Koltun 2011). The per-cell temporal
   chain is 13.3 M independent 12-step chains and was never the expensive part.
5. **No deep-supervision ablation using a three-state ignore label** (§4.4a).
6. **No resolution curriculum that degrades imagery and labels together** (§4.4b).
7. **No method for validating a correction layer as distinct from validating the map it
   corrects.** Searched explicitly in remote sensing; only generic post-processing papers
   returned. **Narrowed in round 3 (§4.12.3) — the method is older than the field that
   lacks it:** Stein/Efron covariance penalties score a black-box corrector from its
   degrees of freedom plus residual, and Efron 2004 covers Bernoulli outcomes at an
   asymmetric cut; Noise2Self gives the J-invariance condition; cross-fitting gives the
   procedural check. Still absent: any of it under spatially and class-correlated error,
   which is what our reference has.
8. **No reference protocol containing a false-positive class** (§2.4).
9. **No measured cross-year lidar leakage rate** — nothing of the form "X% of year Y's
   label is leftover structure from lidar epoch Z" (§4.3).
10. **No change-point method applied to a binary mask sequence with pre-measured (r, f).**
    The statistics exist; the remote-sensing application does not. **Narrowed in round 3
    (§4.12.2):** the Bernoulli CUSUM with known rates (Ross et al. 2012) and the
    misclassification correction explicit in f and r (Chen & Yang 2022) are both primary,
    in two literatures never joined; a general log-likelihood-ratio form that admits
    per-year rates exists (Itkin 2026). Still unpublished: the join, at n = 12, with
    per-year (r_t, f_t) and a Monte-Carlo-calibrated threshold.
11. **No A/B test of a hard veto against a soft prior on the same ancillary layer**, and no
    measured cost of a hard veto at its failure edges — offset footprints, demolished
    structures, canopy overhanging a roof (§6.2).
12. **No study of IGNORE/no-data sentinel propagation through a multi-stage raster
    post-processing chain** (§4.5). **Substantially narrowed in round 3 (§4.12.4):**
    interval-valued morphology gives a closed-under-composition three-valued rule for the
    morphology stage; partial convolutions give the renormalisation for probability-domain
    smoothing; Kalman filtering with intermittent observations gives the exact
    missing-epoch update and a critical observation rate. Still open: the conservative mask
    fraction is a free parameter, and the two-state-chain analogue of the critical rate is
    ours to derive.
13. **No standard temporal-consistency metric.** The field uses ad hoc per-paper
    definitions; there is nothing to adopt.

*Inference:* items 2, 5, 6, 8, 9, 10, 11 and 12 are places where the brief proposes
something this search did not find in the field. That is a reason to pre-register carefully
and measure, not a reason to abandon. After round 3, items 10 and 12 can be de-risked by
*assembling* published halves rather than by reading further; item 2 has an unsearched
statistical home (survival analysis); the rest cannot be de-risked by reading.

> **How much to trust these negatives.** They are search results, not proofs. Every item
> above means "not found by this review," never "does not exist." That distinction is not
> hypothetical: item 1 originally read "not one paper pairs a consistency metric with a
> recall-on-real-change number," and it was **falsified** when spot-checked directly against
> Li et al. 2025's full text, which contains exactly such a table (§4.11). Exactly one
> negative claim in this report was checked against full text, and it was wrong. The other
> twelve were produced the same way — an agent asserting an absence, often from an abstract
> rather than a full text — and carry the same risk. Before any of them is used to justify
> building something novel, spend the hour to read the one paper closest to the claim.
> **Round 3 (2026-09-11) then took items 3, 7, 10 and 12 to adjacent literatures: each
> narrowed and none closed (§4.12).** The negatives held as "not in remote sensing" and
> failed as "not anywhere" — which is the reading every remaining item should get.

*What does survive:* the lidar-certified GAIN (46,805) and FLAT (40,609) populations (§2.2)
give us a change-stratified denominator built from an independent instrument rather than
from photo-interpretation. Li et al. 2025 shows the reporting shape to copy; §2.2 gives us
a stronger reference than they had.

---

## 6. Actionable, cheapest first

Ordered by cost, not by importance. Each states what it would settle.

1. **Grade every cell by its own forward-backward joint probability** (Yang et al. 2020)
   and score that against the 42 gold losses. No model change; the pass already computes
   it. *Settles:* whether the chain already knows which persistence runs it should not
   trust — i.e. whether laundering is detectable from inside the model.
2. **Re-estimate q_loss/q_gain from the lidar-certified GAIN/FLAT populations** rather than
   from the pre-registered 0.02 or from projected labels (Miller et al. 2013; Perantoni et
   al. 2025). *Settles:* whether the 49:1 cost is real or an artifact of a hand-set prior.
   This is the only route found that avoids fitting to our own label error.
3. **Run the §4.2 enrichment count** as the brief already proposes. The literature does
   not contain the answer, and Rosa et al. 2013 says to score the **year**, not only the
   place. *Settles:* whether the assessor clock suffices, and whether the anchor moves
   timing at all.
4. **Check whether r and f are biased rather than merely noisy** (Foody 2010; Radoux &
   Bogaert 2020) by testing whether reference errors correlate with model errors on the
   class-mixed edge cells where the 42 losses live. *Settles:* whether the §2.3 arithmetic
   stands.
5. **Answer §6.2 as "soft, not hard."** The literature gives no basis for a hard ancillary
   veto, one closely-related product's methodology against it (King & Locke 2013 — a stated
   property of the NYC data product, not a surveyed field convention), and a working soft
   form (Sun et al. 2022). *Settles:* §6.2, unless someone is willing to produce the at-risk
   count §3 rule 3 demands — which nobody in the literature has.
6. **Answer §6.3 as "not yet."** A purpose-built detector for exactly this task reaches
   82.27% precision (Li et al. 2022); it trades our coverage gap for a comparable error.
   *Settles:* §6.3 — the enrichment count comes first, as the brief already ordered it.
7. **Derive the local/global weight per cell from measured confidence**, not as one global
   constant (Martinis & Twele 2010). *Settles:* §4.1's open parameter, in the form the
   brief already wants it — measured, not chosen.
8. **Decide deliberately how far upstream the layer sits.** The evidence for reasoning over
   probabilities rather than hardened labels is consistent and measured (Cheng & Liu 2020;
   Li et al. 2019). §4.5 currently proposes "beside the healer" on a stack that is already
   hardened at `threshold_and_clean`. *Settles:* whether §4.5's real target is the raw mask
   or the pre-threshold probability — a scope question, not a tuning one.
9. **When §4.4a is built, sweep the auxiliary weight** (0.1 vs 0.4 vs 0) and make the
   ignore handling explicit, because the published expectation (Ma et al. 2021) is that
   getting it wrong is *worse than not doing it*.

*Whatever ships, define its consistency metric against a change-stratified denominator from
the first run.* Li et al. 2025 (§4.11) shows the reporting shape — a changed/unchanged
error matrix against independent reference data, reported alongside the headline consistency
number, never instead of it. Adopt it from the first run rather than retrofitting it.

---

## 7. Coverage and limits of this review

- **Eleven threads, 92 unique verified works.** Search ran in two rounds: eight threads,
  then a completeness critique, then three targeted gap-fill threads closing the gaps it
  named (§4.5, §6.2/§6.3, and operational product consistency). Every citation was
  confirmed against a Crossref/Semantic Scholar record or a fetched page; nothing is
  recalled from memory. Papers that could not be confirmed were dropped, not guessed.
- **Two claims were adversarially spot-checked** against full text after drafting, chosen
  because the report leaned hardest on them. Gong et al. 2017's validation-culling claim,
  and all four of its numbers: **confirmed verbatim.** The claim that Li et al. 2025 lacks
  a change-stratified accuracy figure: **refuted** — see §4.11 and the box in §5. One of
  the two survived. That is a sample of two, too small to give an error rate, but it is
  enough to show the agent-derived negatives are not safe to build on unchecked — which is
  what the §5 box says and why it says it.
- **One process defect worth recording.** The round-1 agents could not read the brief: it
  lives on `work/20260906-healing-tool`, and the review branch was initially cut from
  `main`, where the file does not exist. They worked from a prose summary instead, which is
  why several round-1 entries cite brief sections loosely; every section reference in this
  report was re-mapped by hand against the actual file. Round 2 read the brief directly.
- **Verification is uneven and concentrated.** Roughly a dozen entries rest on directly
  read primary sources; a majority rest on bibliographic metadata plus abstract or
  snippet. Publisher 403s were the binding constraint. Grades are on every citation for
  this reason — weight the corpus accordingly rather than treating entries as equal.
- **Known monoculture:** the §4.2 evidence is four-sevenths one Christchurch research
  group. Treat that thread as one group's findings, not a field consensus.
- **Numbers flagged ⚠ are not primary-verified** and should not be carried into a design
  or a pre-registration without independent confirmation. **Updated 2026-09-11:** of the
  three examples named in an earlier draft, two turned out to be real once fetched — the
  Guo et al. 1.4 m figure is confirmed (though it is a CART split point, not a removal
  radius; §4.4) and the Pedley & Morgenroth 2025 percentage splits are confirmed against
  Table 2 (§4.4) — so both are removed from this list. Only the MODIS 11.4%→1.6% figure
  remains ⚠: it is now abstract-verbatim rather than search-snippet, but the article body
  stays paywalled and the metric's denominator is still unconfirmed (§4.1).
- **Abercrombie & Friedl 2016 has now been read in full** (Sci-Hub, 2026-09-11; previously
  the review's own highest-priority unread paper — the likely direct ancestor of
  `crown_state_model.py`). Two findings change what was assumed about it: it does *not* use
  a 90%/10%÷(K−1) transition matrix (that description was an invented gloss with no basis in
  the paper or in this project's own code — §4.1), and it *does* validate against real
  change, scoring omission/commission against PRODES deforestation reference data — a
  narrower test (deforestation only, 3-year timing tolerance) than the review previously
  implied was entirely absent. Full text filed at
  `D:\edmonds-pipeline\Literture\Validation\`. The open-source port `BU-LCSC/mtlchmm` was
  consulted alongside the paper and matches its method.
- **Paywalls here are usually routable, and a ⚠ grade is often just a dead end in the
  fetch, not a closed door.** Tolan et al. 2024 was upgraded **ABSTRACT ⚠ → PRIMARY** on
  2026-09-11 by reading the open-access preprint (arXiv:2304.07213) instead of the Elsevier
  version, which changed the §4.3 conclusion materially. Any remaining ⚠ or METADATA entry
  is worth one check for a preprint, an institutional-repository mirror, or a
  society-journal precursor before it is treated as unreadable. **Update, 2026-09-11 — both
  of the two leads named in the previous draft were pulled successfully:** Hoberg et al.
  2015's 2012 ISPRS Annals precursor parsed cleanly this time (`pypdf`, after `pdftotext`
  dropped its β/γ symbols, which sit in Symbol-font private-use codepoints — likely why an
  earlier attempt read the parse as failed; §4.2). Li et al. 2022 remains recovered via the
  DLR repository mirror, as previously recorded. Other repository-mirror routes that worked
  this round, worth reusing on future ⚠/METADATA entries: Unpaywall's OA-location lookup
  resolving Elsevier DOIs to University of Canterbury repository bitstreams (Guo, Pedley &
  Morgenroth — §4.4, §4.8); HAL author postprints for a French INRAE-affiliated group
  (Capliez — §4.5); a GFZ Potsdam pubman mirror for an MDPI DOI that 403'd both a
  UA-spoofed curl and WebFetch directly (Martinis & Twele — §4.2); USDA Forest Service
  Treesearch for a Forest Service co-authored paper (King & Locke — §4.10).
- **Round 3 (2026-09-11) searched adjacent fields, not remote sensing again:** four
  threads — geostatistics and total-variation theory for the weight/erasure gap;
  statistical process control and biosurveillance for change detection in (r, f);
  denoising theory (SURE, Efron, Noise2Self) for corrector validation; missing-data signal
  processing for IGNORE propagation. 21 new works, 16 read in full, 3 ABSTRACT, 2 METADATA;
  findings in §4.12, grades in the bibliography. The same rule held: every pairing of a
  paper's result with our objects is marked as the review's substitution. Two more leads
  round 3 named but did not pull: the survival-analysis framing of §4.2 (item 2), and the
  MacFaden et al. 2012 / UVM methodology that would settle whether canopy-over-roof is a
  field convention (§4.10).
- **Not searched:** §6.4 (which training lever first) is a cost/sequencing decision no
  literature settles; the material for it is in §4.6. §6.2 and §6.3 *were* searched in
  round 2 and are answered in §4.10.
- **Local library, already on disk** (`D:\edmonds-pipeline\Literture\`) was triaged
  separately and folded in above where relevant. Van den Broeck et al. 2022 is already
  cited by `DEGRADED_IMAGERY_RESEARCH_2026-08-27.md`; that report remains its home.

---

## 8. Bibliography

Grades as defined in §2. Grouped by the brief section they bear on.

### §2.3 — temporal chain, transitions, emissions
- Abercrombie, S.P. & Friedl, M.A. (2016). Improving the Consistency of Multitemporal Land Cover Maps Using a Hidden Markov Model. *IEEE TGRS* 54(2). doi:10.1109/TGRS.2015.2463689 — **PRIMARY** (full text, Sci-Hub, verified 2026-09-11; local copy in `D:\edmonds-pipeline\Literture\Validation\`)
- Bogaert, P., Lamarche, C. & Defourny, P. (2022). Hidden Markov Models for Annual Land Cover Mapping — Increasing Temporal Consistency and Completeness. *IEEE TGRS* 60. doi:10.1109/TGRS.2021.3123738 — **ABSTRACT**
- Cai, S., Liu, D., Sulla-Menashe, D. & Friedl, M.A. (2014). Enhancing MODIS land cover product with a spatial–temporal modeling algorithm. *RSE* 147. doi:10.1016/j.rse.2014.03.012 — **METADATA**
- Gong, W., Fang, S., Yang, G. & Ge, M. (2017). Using a Hidden Markov Model for Improving the Spatial-Temporal Consistency of Time Series Land Cover Classification. *ISPRS IJGI* 6(10):292. doi:10.3390/ijgi6100292 — **PRIMARY**
- Miller, D.A.W. et al. (2013). Determining Occurrence Dynamics when False Positives Occur: Estimating the Range Dynamics of Wolves from Public Survey Data. *PLOS ONE* **8(6)**:e65808. doi:10.1371/journal.pone.0065808 — **PRIMARY** (full text, verified 2026-09-11; issue number corrected from 8(10))
- Perantoni, G., Weikmann, G. & Bruzzone, L. (2025). Bayesian Modelling of Multi-Year Crop Type Classification Using Deep Neural Networks and Hidden Markov Models. arXiv:2510.07008 — **PRIMARY** (preprint)
- Sulla-Menashe, D., Gray, J.M., Abercrombie, S.P. & Friedl, M.A. (2019). Hierarchical mapping of annual global land cover 2001 to present: MODIS Collection 6. *RSE* 222. doi:10.1016/j.rse.2018.12.013 — **ABSTRACT ⚠ NUMBERS** (transition figure, abstract-verbatim); its product documentation (Sulla-Menashe & Friedl, MCD12Q1 User Guide) is **PRIMARY** (§4.1)
- Wehmann, A. & Liu, D. (2015). A spatial–temporal contextual Markovian kernel method for multi-temporal land cover mapping. *ISPRS J.* 107. doi:10.1016/j.isprsjprs.2015.04.009 — **METADATA**
- Yang, G., Fang, S., Gong, W., Zhao, Y. & Ge, M. (2020). Evaluating the reliability of time series land cover maps by exploiting the hidden Markov model. *SERRA* 35. doi:10.1007/s00477-020-01915-9 — **ABSTRACT**
- Yuan, Y. et al. (2015). Continuous Change Detection and Classification Using Hidden Markov Model: Beijing. *Remote Sensing* 7(11):15318. doi:10.3390/rs71115318 — **METADATA**

### §4.1 — joint space and time
- Benedek, C. & Sziranyi, T. (2009). Change Detection in Optical Aerial Images by a Multilayer Conditional Mixed Markov Model. *IEEE TGRS* 47(10). doi:10.1109/TGRS.2009.2022633 — **METADATA**
- Benedek, C., Shadaydeh, M., Kato, Z., Sziranyi, T. & Zerubia, J. (2015). Multilayer Markov Random Field models for change detection in optical remote sensing images. *ISPRS J.* 107. doi:10.1016/j.isprsjprs.2015.02.006 — **METADATA**
- Hoberg, T., Rottensteiner, F., Feitosa, R.Q. & Heipke, C. (2015). Conditional Random Fields for Multitemporal and Multiscale Classification of Optical Satellite Imagery. *IEEE TGRS* 53(2). doi:10.1109/TGRS.2014.2326886 — **METADATA** (confirmed unreadable 2026-09-11: no OA/repository copy, five Sci-Hub mirrors empty)
- Hoberg, T., Rottensteiner, F. & Heipke, C. (2012). Context Models for CRF-Based Classification of Multitemporal Remote Sensing Data. *ISPRS Annals* I-7:129–134. doi:10.5194/isprsannals-I-7-129-2012 — **PRIMARY** (2012 precursor to the above; full text parsed 2026-09-11, §4.2)
- Liu, C., Song, W., Lu, C. & Xia, J. (2021). Spatial-Temporal Hidden Markov Model for Land Cover Classification. *IEEE Access* 9. doi:10.1109/ACCESS.2021.3080926 — **ABSTRACT**
- Martinis, S. & Twele, A. (2010). A Hierarchical Spatio-Temporal Markov Model for Improved Flood Mapping Using Multi-Temporal X-Band SAR Data. *Remote Sensing* 2(9). doi:10.3390/rs2092240 — **PRIMARY** (full text via GFZ Potsdam repository mirror, verified 2026-09-11, §4.2)
- Melgani, F. & Serpico, S.B. (2003). A Markov random field approach to spatio-temporal contextual image classification. *IEEE TGRS* 41(11). doi:10.1109/TGRS.2003.817269 — **METADATA**

### §6.1 — reshaping, segmentation, confirm-or-veto
- Cohen, W.B., Yang, Z., Healey, S.P., Kennedy, R.E. & Gorelick, N. (2018). A LandTrendr multispectral ensemble for forest disturbance detection. *RSE* 205. doi:10.1016/j.rse.2017.11.015 — **METADATA ⚠ NUMBERS**
- Kennedy, R.E., Yang, Z. & Cohen, W.B. (2010). Detecting trends in forest disturbance and recovery using yearly Landsat time series: 1. LandTrendr. *RSE* 114. doi:10.1016/j.rse.2010.07.008 — **PRIMARY**
- Murakami, T. & Tsutsumida, N. (2025). Comparative Global Assessment and Optimization of LandTrendr, CCDC, and BFAST for Urban Land Cover Change Detection. *Remote Sensing* 17(14):2402. doi:10.3390/rs17142402 — **METADATA**
- Pasquarella, V.J. et al. (2022). Demystifying LandTrendr and CCDC temporal segmentation. *IJAEOG* 110:102806. doi:10.1016/j.jag.2022.102806 — **PRIMARY**
- Polunchenko, A.S. & Tartakovsky, A.G. (2012). State-of-the-Art in Sequential Change-Point Detection. *Meth. Comput. Appl. Probab.* doi:10.1007/s11009-011-9256-5 — **PRIMARY**
- Reiche, J., de Bruin, S., Hoekman, D., Verbesselt, J. & Herold, M. (2015). A Bayesian Approach to Combine Landsat and ALOS PALSAR Time Series for Near Real-Time Deforestation Detection. *Remote Sensing* 7(5). doi:10.3390/rs70504973 — **ABSTRACT**
- Reiche, J. et al. (2021). Forest disturbance alerts for the Congo Basin using Sentinel-1. *ERL* 16. doi:10.1088/1748-9326/abd0a8 — **ABSTRACT**
- Rodman, K.C., Andrus, R.A., Veblen, T.T. & Hart, S.J. (2021). Disturbance detection in Landsat time series is influenced by tree mortality agent and severity, not by prior disturbance. *RSE* 254:112244. doi:10.1016/j.rse.2020.112244 — **PRIMARY** (full text read 2026-09-11; title was previously truncated, dropping its third finding)
- Verbesselt, J., Hyndman, R., Newnham, G. & Culvenor, D. (2010). Detecting trend and seasonal changes in satellite image time series. *RSE* 114(1). doi:10.1016/j.rse.2009.08.014 — **PRIMARY**
- Wendelberger, L.J., Reich, B.J., Wilson, A.G. & Gray, J.M. (2026). Detecting Deforestation Using Robust Online Bayesian Monitoring. *Data Science in Science*. doi:10.1080/26941899.2026.2687150 — **METADATA**
- Zhu, Z. & Woodcock, C.E. (2014). Continuous change detection and classification of land cover using all available Landsat data. *RSE* 144. doi:10.1016/j.rse.2014.01.011 — **PRIMARY**

### §4.2 — ancillary and cadastral priors
- Cardille, J.A. & Fortin, J.A. (2016). Bayesian updating of land-cover estimates in a data-rich environment. *RSE* 186. doi:10.1016/j.rse.2016.08.021 — **METADATA ⚠ NUMBERS**
- City of Seattle OSE / University of Vermont SAL (2023). *City of Seattle Tree Canopy Assessment: Final Report (2016–2021)*. Agency report — **PRIMARY**
- Guo, T., Morgenroth, J. & Conway, T.M. (2018). Redeveloping the urban forest: the effect of redevelopment and property-scale variables on tree removal and retention. *UFUG* 35. doi:10.1016/j.ufug.2018.08.012 — **PRIMARY** (author's PhD thesis, UC repository hdl 10092/16832, read 2026-09-11 — the 1.4 m figure is real but is a CART split point, not a removal radius; see §4.4)
- Guo, T., Morgenroth, J., Conway, T.M. & Xu, C. (2019). City-wide canopy cover decline due to residential property redevelopment in Christchurch. *STOTEN* 681. doi:10.1016/j.scitotenv.2019.05.122 — **PRIMARY** (same thesis, Ch.2, read 2026-09-11; no 1.4 m figure in this paper)
- Morgenroth, J., O'Neil-Dunne, J. & Apiolaza, L.A. (2017). Redevelopment and the urban forest: tree removal and retention during demolition. *Applied Geography* 82. doi:10.1016/j.apgeog.2017.02.011 — **METADATA ⚠ NUMBERS** (confirmed still unreadable 2026-09-11: closed in Unpaywall and OpenAlex; the author's own conference deck, hdl 10092/14376, gives a 0.7 m split for the same variable, which is why the paper stays unread rather than assumed)
- Ossola, A. & Hopton, M.E. (2017). Measuring urban tree loss dynamics across residential landscapes. *STOTEN*. doi:10.1016/j.scitotenv.2017.08.103 — **PRIMARY**
- Pedley, D. & Morgenroth, J. (2025). Green vs growth: The effect of residential intensification on urban tree canopy loss in Christchurch, New Zealand. *Sustainable Cities and Society* 130:106678. doi:10.1016/j.scs.2025.106678 — **PRIMARY** (full publisher PDF via UC repository hdl 10092/108884, read 2026-09-11; drop ⚠ NUMBERS; title corrected — see §4.4)
- Rosa, I.M.D., Purves, D., Souza, C. Jr. & Ewers, R.M. (2013). Predictive Modelling of Contagious Deforestation in the Brazilian Amazon. *PLOS ONE* 8(10):e77231. doi:10.1371/journal.pone.0077231 — **PRIMARY**

### §4.3 — privileged information, lidar as teacher, cross-year transfer
- Capliez, E., Ienco, D., Gaetano, R., Baghdadi, N. & Hadj Salah, A. (2023). Temporal-Domain Adaptation for Satellite Image Time-Series Land-Cover Mapping. *IEEE JSTARS*. doi:10.1109/JSTARS.2023.3263755 — **PRIMARY** (author postprint via HAL, verified 2026-09-11 — see §4.5 correction; drop ⚠ NUMBERS)
- Capliez, E. et al. (2023). Multisensor Temporal Unsupervised Domain Adaptation for Land Cover Mapping. *IEEE TGRS*. doi:10.1109/TGRS.2023.3297077 — **PRIMARY** (author postprint via HAL, verified 2026-09-11)
- Islam, M.D. et al. (2026). High-resolution multi-temporal forest canopy height mapping in California using GEDI LiDAR and multi-sensor remote sensing. *Science of Remote Sensing*. doi:10.1016/j.srs.2026.100488 — **METADATA**
- Kalinicheva, E., Helen, F., Mermoz, S., Mouret, F. & Planells, M. (2025). Super-Resolved Canopy Height Mapping from Sentinel-2 Time Series Using Airborne LiDAR HD. arXiv:2512.11524 — **ABSTRACT** (preprint)
- Lai, Y. et al. (2026). Forest canopy height estimation from satellite RGB imagery using large-scale airborne LiDAR-derived training data. arXiv:2602.06503 — **ABSTRACT ⚠ NUMBERS** (preprint)
- Lang, N., Jetz, W., Schindler, K. & Wegner, J.D. (2023). A high-resolution canopy height model of the Earth. *Nature Ecology & Evolution*. doi:10.1038/s41559-023-02206-6 — **PRIMARY**
- Lopez-Paz, D., Bottou, L., Schölkopf, B. & Vapnik, V. (2016). Unifying distillation and privileged information. *ICLR 2016*; arXiv:1511.03643 — **ABSTRACT**
- Pauls, J. et al. (2025). Capturing Temporal Dynamics in Large-Scale Canopy Tree Height Estimation. arXiv:2501.19328 — **ABSTRACT** (preprint)
- Pesonen, J. et al. (2026). Learning Image-based Tree Crown Segmentation from Enhanced Lidar-based Pseudo-labels. arXiv:2602.13022 — **ABSTRACT** (preprint)
- Song, J., Chen, H. & Yokoya, N. (2026). Enhancing monocular height estimation via sparse LiDAR-guided correction. *ISPRS J.* 232. doi:10.1016/j.isprsjprs.2025.12.004 — **ABSTRACT**
- Tolan, J. et al. (2024). Very high resolution canopy height maps from RGB imagery using self-supervised vision transformer and convolutional decoder trained on aerial lidar. *RSE*. doi:10.1016/j.rse.2023.113888 — **PRIMARY** via the open-access preprint arXiv:2304.07213 (publisher version paywalled); inference code at `facebookresearch/HighResCanopyHeight`
- Vapnik, V. & Vashist, A. (2009). A new learning paradigm: Learning using privileged information. *Neural Networks* 22(5–6). doi:10.1016/j.neunet.2009.06.042 — **METADATA**
- Zhou, Q., Tollerud, H., Barber, C., Smith, K. & Zelenak, D. (2020). Training Data Selection for Annual Land Cover Classification for LCMAP. *Remote Sensing* 12(4):699. doi:10.3390/rs12040699 — **ABSTRACT**

### §4.4 — deep supervision and resolution
- Brown, J. et al. (2022). Automated aerial animal detection when spatial resolution conditions are varied. *Computers and Electronics in Agriculture*. doi:10.1016/j.compag.2022.106689 — **ABSTRACT**
- Chen, H., Yang, W., Liu, L. & Xia, G.S. (2024). Coarse-to-fine semantic segmentation of satellite images. *ISPRS J.* 217. doi:10.1016/j.isprsjprs.2024.07.028 — **METADATA**
- Chen, K. et al. (2018). Semantic Segmentation of Aerial Imagery via Multi-Scale Shuffling CNNs with Deep Supervision. *ISPRS Annals* IV-1. doi:10.5194/isprs-annals-IV-1-29-2018 — **ABSTRACT**
- Lee, C.Y., Xie, S., Gallagher, P., Zhang, Z. & Tu, Z. (2015). Deeply-Supervised Nets. *AISTATS*, PMLR 38 — **ABSTRACT**
- Ma, S., Tang, J. & Guo, F. (2021). Multi-Task Deep Supervision on Attention R2U-Net for Brain Tumor Segmentation. *Frontiers in Oncology* 11:704850. doi:10.3389/fonc.2021.704850 — **PRIMARY**
- Mobsite, S., Hostache, R., Berti-Équille, L., Roux, E., Catry, T. & Guérin, J. (2026). Enhancing land cover semantic segmentation with convolutional block attention modules and deep supervision. *Artificial Intelligence in Geosciences* 7:100222. doi:10.1016/j.aiig.2026.100222 — **METADATA** (numbers' home is brief §2.5)
- Touvron, H., Vedaldi, A., Douze, M. & Jégou, H. (2019). Fixing the Train-Test Resolution Discrepancy. *NeurIPS 32*; arXiv:1906.06423 — **ABSTRACT**
- Zhao, H., Shi, J., Qi, X., Wang, X. & Jia, J. (2017). Pyramid Scene Parsing Network. *CVPR 2017*. doi:10.1109/CVPR.2017.660 — **ABSTRACT**

### §2.4 — accuracy assessment for rare change
- Foody, G.M. (2010). Assessing the accuracy of land cover change with imperfect ground reference data. *RSE* 114. doi:10.1016/j.rse.2010.05.003 — **ABSTRACT**
- Olofsson, P., Foody, G.M., Stehman, S.V. & Woodcock, C.E. (2013). Making better use of accuracy data in land change studies. *RSE* 129. doi:10.1016/j.rse.2012.10.031 — **METADATA**
- Olofsson, P., Foody, G.M., Herold, M., Stehman, S.V., Woodcock, C.E. & Wulder, M.A. (2014). Good practices for estimating area and assessing accuracy of land change. *RSE* 148. doi:10.1016/j.rse.2014.02.015 — **PRIMARY**
- Radoux, J. & Bogaert, P. (2020). About the Pitfall of Erroneous Validation Data in the Estimation of Confusion Matrices. *Remote Sensing* 12(24):4128. doi:10.3390/rs12244128 — **ABSTRACT**
- Radoux, J., Waldner, F. & Bogaert, P. (2020). How Response Designs and Class Proportions Affect the Accuracy of Validation Data. *Remote Sensing* 12(2):257. doi:10.3390/rs12020257 — **ABSTRACT**
- Stehman, S.V. & Czaplewski, R.L. (1998). Design and Analysis for Thematic Map Accuracy Assessment. *RSE* 64. doi:10.1016/S0034-4257(98)00010-8 — **METADATA**
- Stehman, S.V. & Foody, G.M. (2019). Key issues in rigorous accuracy assessment of land cover products. *RSE* 231:111199. doi:10.1016/j.rse.2019.05.018 — **ABSTRACT**
- Stehman, S.V. & Wagner, J.E. (2024). Choosing a sample size allocation to strata based on trade-offs in precision when estimating accuracy and area of a rare class. *RSE* 300:113881. doi:10.1016/j.rse.2023.113881 — **PRIMARY ⚠ NUMBERS**

### §1 — heterogeneous archives, shadow and rooftop error
- Blackman, R. & Yuan, F. (2020). Detecting Long-Term Urban Forest Cover Change and Impacts of Natural Disasters. *Remote Sensing* 12(11):1820. doi:10.3390/rs12111820 — **ABSTRACT**
- Coupland, K., Hamilton, D. & Griess, V.C. (2022). Combining aerial photos and LiDAR data to detect canopy cover change in urban forests. *PLOS ONE*. doi:10.1371/journal.pone.0273487 — **PRIMARY**
- MacFaden, S.W., O'Neil-Dunne, J.P.M., Royar, A.R., Lu, J.W.T. & Rundle, A.G. (2012). High-resolution tree canopy mapping for New York City using LIDAR and object-based image analysis. *JARS* 6:063567. doi:10.1117/1.JRS.6.063567 — **ABSTRACT**
- Nowak, D.J. & Greenfield, E.J. (2012). Tree and impervious cover change in U.S. cities. *UFUG*. doi:10.1016/j.ufug.2011.11.005 — **ABSTRACT**
- O'Neil-Dunne, J.P.M., MacFaden, S.W. & Royar, A.R. (2014). A Versatile, Production-Oriented Approach to High-Resolution Tree-Canopy Mapping. *Remote Sensing* 6(12). doi:10.3390/rs61212837 — **ABSTRACT**
- Pedley, D. & Morgenroth, J. (2025). Detecting and measuring fine-scale urban tree canopy loss with deep learning and remote sensing. *ISPRS Open J. Photogramm. Remote Sens.* **15**:100082. doi:10.1016/j.ophoto.2025.100082 — **PRIMARY** (CC BY, full text read 2026-09-11 — the 0.941/0.811 precision/recall figures previously quoted from a METADATA-graded citation are now confirmed at Table 3; that inconsistency is resolved. Its loss signal is lidar height change, not imagery differencing — see §4.8)
- Walton, J.T. (2008). Difficulties with estimating city-wide urban forest cover change from national, remotely-sensed tree canopy maps. *Urban Ecosystems*. doi:10.1007/s11252-007-0040-9 — **ABSTRACT**

### §4.5 — layer placement, soft versus hard decisions
- Câmara, G. et al. (2024). Bayesian Inference for Post-Processing of Remote-Sensing Image Classification. *Remote Sensing* 16(23):4572. doi:10.3390/rs16234572 — **ABSTRACT**
- Cheng, X. & Liu, H. (2020). A Novel Post-Processing Method Based on a Weighted Composite Filter for Enhancing Semantic Segmentation Results. *Sensors* 20(19):5500. doi:10.3390/s20195500 — **PRIMARY**
- Li, N., Liu, C. & Pfeifer, N. (2019). Improving LiDAR classification accuracy by contextual label smoothing in post-processing. *ISPRS J.* 148. doi:10.1016/j.isprsjprs.2018.11.022 — **ABSTRACT**
- Papadopoulos, S., Koukiou, G. & Anastassopoulos, V. (2024). Decision Fusion at Pixel Level of Multi-Band Data for Land Cover Classification — A Review. *Journal of Imaging* 10(1):15. doi:10.3390/jimaging10010015 — **ABSTRACT**
- Wu, C., Du, B., Cui, X. & Zhang, L. (2017). A post-classification change detection method based on iterative slow feature analysis and Bayesian soft fusion. *RSE*. doi:10.1016/j.rse.2017.07.009 — **ABSTRACT**

### §6.2 / §6.3 — buildings as ancillary context, and cadastral completeness
- Abellera, L.V. & Stenstrom, M.K. (2005). Impervious Surface Detection from Satellite Imagery with Knowledge-Based Systems and GIS. *Computing in Civil Engineering 2005* (ASCE). doi:10.1061/40794(179)45 — **METADATA ⚠ NUMBERS**
- Hecht, R., Meinel, G. & Buchroithner, M. (2015). Automatic identification of building types based on topographic databases — a comparison of different data sources. *Int. J. Cartography* 1(1). doi:10.1080/23729333.2015.1055644 — **METADATA ⚠ NUMBERS**
- King, K. & Locke, D. (2013). A Comparison of Three Methods for Measuring Local Urban Tree Canopy Cover. *Arboriculture & Urban Forestry* 39(2). doi:10.48044/jauf.2013.009 — **PRIMARY** (full text via USDA Forest Service Treesearch, read 2026-09-11; the canopy-over-roof finding, §4.10 — corrected from a stated field "convention" to a property of one data product's methodology)
- Li, Q., Taubenböck, H., Shi, Y., Auer, S., Roschlaub, R., Glock, C., Kruspe, A. & Zhu, X.X. (2022). Identification of undocumented buildings in cadastral data using remote sensing. *IJAEOG* 112:102909. doi:10.1016/j.jag.2022.102909 — **PRIMARY** (full text via DLR mirror elib.dlr.de/187878)
- Sun, Y., Hua, Y., Mou, L. & Zhu, X.X. (2022). CG-Net: Conditional GIS-Aware Network for Individual Building Segmentation in VHR SAR Images. *IEEE TGRS*. doi:10.1109/TGRS.2020.3043089 — **ABSTRACT**
- Yi, S., Li, X., Liu, Y., Dong, X. & Tu, W. (2025). A sub-meter resolution urban surface albedo dataset for 34 U.S. cities based on deep learning. *Scientific Data* 12:789. doi:10.1038/s41597-025-05109-2 — **PRIMARY** (the unmeasured hard-veto instance, §4.10)

### Operational products and their consistency claims
- Li, Z., Zhang, X., Liu, W., Zhao, T., Ai, W., Wang, J. & Liu, L. (2025). Post-Processing Optimization of the Global 30 m Land Cover Dynamic Monitoring Product. *Remote Sensing* 17(9):1558. doi:10.3390/rs17091558 — **PRIMARY** (full text; §4.11 — the change-stratified reporting template, and the source of the correction in §5)
- Reis, M.S., Dutra, L.V., Escada, M.I.S. & Sant'Anna, S.J.S. (2020). Avoiding Invalid Transitions in Land Cover Trajectory Classification With a Compound Maximum a Posteriori Approach. *IEEE Access* 8. doi:10.1109/ACCESS.2020.2997019 — **ABSTRACT**
- Yang, J. & Huang, X. (2021). The 30 m Annual Land Cover Dataset and Its Dynamics in China from 1990 to 2019 (CLCD). *ESSD* 13(8). doi:10.5194/essd-13-3907-2021 — **METADATA ⚠ NUMBERS**

### Adjacent-field theory (round 3, 2026-09-11; §4.12)
Grades as in §2. None of these works is about land cover; each is cited for one result
whose pairing with our objects is this review's substitution. Author surnames are as
captured in the fetch; initials were not recorded and are deliberately not supplied here.
Every DOI / arXiv id resolves.

*§4.1 — weight and erasure threshold (§4.12.1)*
- Strong & Chan (2003). Edge-preserving and scale-dependent properties of total variation regularization. *Inverse Problems* 19(6):S165–S187. doi:10.1088/0266-5611/19/6/059 — **PRIMARY** (UCLA CAM report mirror)
- Gräler, Pebesma & Heuvelink (2016). Spatio-Temporal Interpolation using gstat. *The R Journal* 8(1):204–218. doi:10.32614/RJ-2016-014 — **PRIMARY**
- Krähenbühl & Koltun (2011). Efficient Inference in Fully Connected CRFs with Gaussian Edge Potentials. *NeurIPS 2011*; arXiv:1210.5644 — **PRIMARY**

*§2.3 / §6.1 — change detection in (r, f) (§4.12.2)*
- Ross, Tasoulis & Adams (2012). Sequential monitoring of a Bernoulli sequence when the pre-change parameter is unknown. *Computational Statistics* 28(2):463–479. doi:10.1007/s00180-012-0311-7; arXiv:1212.6020 — **PRIMARY**
- Chen & Yang (2022). A New p-Control Chart with Measurement Error Correction. arXiv:2203.03384 — **PRIMARY** (code: `github.com/lchen723/SPC-ME-R-code`)
- Itkin (2026). Quickest Detection of Hallucination Onset. arXiv:2606.12476 — **PRIMARY**
- Sandia National Laboratories (2016). An Introduction to the Bernoulli CUSUM. SAND2016-7395C, OSTI 1374023 — **PRIMARY** (bylined "Author 1"; corroboration only)
- Reynolds & Stoumbos (1999). *J. Quality Technology* 31:87–108 — **METADATA** (via Ross et al.'s bibliography; the run-length approximation; not fetched)
- Mishra & Singh (2022). doi:10.9734/ajpas/2022/v17i430430 — **ABSTRACT**, UNREADABLE (AJPAS 403; truncated negative-binomial inspection-error CUSUM)
- Chakraborty & Khurshid (2017). doi:10.12957/cadest.2017.25564 — **ABSTRACT**, UNREADABLE (abstract only served; intervened-Poisson inspection-error CUSUM)

*§4.5 — scoring a corrector (§4.12.3)*
- Ramani, Blu & Unser (2008). Monte-Carlo SURE [full title not captured]. *IEEE Trans. Image Processing* 17(9):1540–1554. doi:10.1109/tip.2008.2001404 — **PRIMARY**
- Efron (2004). The Estimation of Prediction Error: Covariance Penalties and Cross-Validation. *JASA* 99(467):619–632. doi:10.1198/016214504000000692 — **PRIMARY**
- Batson & Royer (2019). Noise2Self. *ICML 2019*, PMLR 97; arXiv:1901.11365 — **PRIMARY**
- Chernozhukov et al. (2018). *Econometrics Journal* 21(1):C1–C68. doi:10.1111/ectj.12097 — **ABSTRACT** (cross-fitting; title not captured)
- Kumar, Liang & Ma (2019). Verified Uncertainty Calibration. *NeurIPS 2019*; arXiv:1909.10155 — **PRIMARY**

*§4.5 — IGNORE propagation (§4.12.4)*
- Sussner, Nachtegael, Mélange, Deschrijver, Esmi & Kerre. Interval-Valued and Intuitionistic Fuzzy Mathematical Morphologies as Special Cases of L-Fuzzy Mathematical Morphology. *J. Math. Imaging Vis.* doi:10.1007/s10851-011-0283-1 — **PRIMARY** (year not captured; DOI resolves)
- Liu, Reda, Shih, Wang, Tao & Catanzaro (2018). Image Inpainting for Irregular Holes Using Partial Convolutions. arXiv:1804.07723v2; doi:10.1007/978-3-030-01252-6_6 — **PRIMARY**
- Appel (2022). Efficient Data-Driven Gap Filling of Satellite Image Time Series Using Deep Neural Networks with Partial Convolutions. arXiv:2208.08781; *Artif. Intell. Earth Syst.* doi:10.1175/AIES-D-22-0055.1 — **PRIMARY**
- Sinopoli, Schenato, Franceschetti, Poolla, Jordan & Sastry (2004). Kalman Filtering With Intermittent Observations. *IEEE Trans. Automatic Control* 49(9):1453–1464. doi:10.1109/TAC.2004.834121 — **PRIMARY** (Crossref-verified; text quoted from the Berkeley preprint, self-labelled DRAFT)
- Przewiezlikowski et al. (2022). MisConv. *WACV 2022* — **PRIMARY** (read; rejected — imputes)
- Bloch (2012). [bipolar morphology; title not captured]. *Int. J. Approx. Reasoning*. doi:10.1016/j.ijar.2012.05.003 — **METADATA**

### Held locally (`D:\edmonds-pipeline\Literture\`), read directly from PDF
- Li, B., Liu, X., Zhuang, H., Shi, Q., Zeng, L., Cai, Y., Zhang, H., Cai, Y., Wu, C. & Xu, X. (2026). ALCC: Temporally Consistent Annual Land Cover Maps over China from 1985 to 2022 Based on an Ensemble Change Detection Method. *J. Remote Sens.* 6:1029. doi:10.34133/remotesensing.1029 — **PRIMARY** (local PDF; record and OA figures independently re-verified in round 2)
- Liu, J., Tang, X., Wang, C., Yan, Z., Dai, Y., Zhang, Q. & Song, C. (2026). Using GeoAI and Machine Learning Tools for Consistent High-Resolution Land Cover Mapping Based on Time-Series NAIP Imagery. *Landscape Ecology* 41(6). doi:10.1007/s10980-026-02358-3 — **PRIMARY** (local PDF; full text also read in round 2 via PMC12869689)
- Artikanur, S.D. et al. (2026). Evaluating Accuracy and Temporal Consistency of Machine Learning Models for LULC Mapping in the Cimanuk Watershed. *J. Nat. Resour. Environ. Manag.* 16(3):284. doi:10.29244/jpsl.16.3.284 — **PRIMARY**
- Van den Broeck, W.A.J., Goedemé, T. & Loopmans, M. (2022). Multiclass Land Cover Mapping from Historical Orthophotos Using Domain Adaptation and Spatio-Temporal Transfer Learning. *Remote Sensing* 14(23):5911. doi:10.3390/rs14235911 — **PRIMARY** (already cited by `DEGRADED_IMAGERY_RESEARCH_2026-08-27.md`)
- Maclaurin, G.J. & Leyk, S. (2016). Temporal replication of the national land cover database using active machine learning. *GIScience & Remote Sensing*. doi:10.1080/15481603.2016.1235009 — **PRIMARY**
- Torres, D.L. et al. (2021). Deforestation Detection with Fully Convolutional Networks in the Amazon Forest from Landsat-8 and Sentinel-2 Images. *Remote Sensing* 13(24):5084. doi:10.3390/rs13245084 — **PRIMARY**
- Pearse, G.D., Watt, M.S., Soewarto, J. & Tan, A.Y.S. (2021). Deep Learning and Phenology Enhance Large-Scale Tree Species Classification in Aerial Imagery during a Biosecurity Response. *Remote Sensing* 13(9):1789. doi:10.3390/rs13091789 — **PRIMARY**

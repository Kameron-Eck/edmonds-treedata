# APPLICABILITY TO THIS PROJECT — read before using anything below

The document that follows is a **literature review produced by a separate session**. Its
research is useful; its repo-specific content is NOT ours and its premises were checked
against the actual data on 2026-08-27. Findings of that check:

## Verified WRONG for this repo (do not act on)

- **Part C's implementation prompt targets a different codebase.** `scripts/pipeline.py`,
  `configs/default.yaml`, `docs/methodology.md` do not exist here (ours: `pipeline/phase4seg/`,
  `Method_Pipeline.md`). Its 530 tiles / 180,000 crowns / `min_distance: 30` /
  `min_crown_area_m2: 2.0` are not our numbers (we have 222,435 crowns). Pasting it would
  plan against a repo that does not exist.
- **"1996-2003 is ~100 cm and may be grayscale."** Measured: `1996_snoh_1m_rgb.tif` is
  **3-band RGB at 1.00 m** (EPSG:2285, 3.28 US survey ft). The grayscale/colorization thread
  (W-Net, "Colorizing the Past", panchromatic FCN work) therefore does **not** apply to 1996.
- **Its "build a separate binary canopy head" recommendation is already our architecture.**
  Phase 4 is per-year binary canopy semantic segmentation; per-crown instances come only from
  the 2020 anchor. The reframe it argues for is what this pipeline already does.
- **"Keep the ResNet U-Net over DINOv2/transformers at this data scale"** — already true here.

## Verified RIGHT and directly applicable

- **Pre-2000 imagery exists on disk but is NOT in `YEAR_CATALOG`** — no entry, no tier, no
  path resolution. "The pipeline is limited to 2000" is literally true. Measured holdings:

  | file | bands | true GSD | note |
  |---|---|---|---|
  | `1990_snoh_10ft_pan.tif` | 1 (pan) | **3.05 m** | likely too coarse to be useful |
  | `1996_snoh_1m_rgb.tif` | **3 (RGB)** | **1.00 m** | the real 100 cm target; NOT grayscale |
  | `1998_snoh_3ft_pan.tif` | 1 (pan) | **0.91 m** | grayscale — the panchromatic literature applies HERE, not to 1996 |
  | `1998_king_pan.tif` | 1 (pan) | **~0.40 m** | EPSG:3857, 0.60 Mercator m x cos(47.8 deg); far finer than the brief assumes |

  Caution: the Snohomish files are EPSG:2285 (US survey **feet**) and the King file is Web
  Mercator — the two CRS-unit traps that produced the `gsd_cm` defect (WORKPLAN 1.5) and the
  2.215x area inflation found 2026-08-27. Any catalog entry for these must record TRUE ground
  GSD, measured, not CRS units.

- **The 100 cm regime describes our EARLY YEARS THROUGH EFFECTIVE RESOLUTION.** 2000 is
  nominally 40.1 cm but resolves at **80.7 cm** (2.8x oversampled, WORKPLAN 1.3). So the
  brief's regime applies to 2000 via effective resolution even though its nominal figure looks
  better — and to 1996 directly.

- **High-order degradation (Real-ESRGAN pattern).** A single clean shrink->blur->noise->JPEG
  chain produces degradations too regular to transfer; run the loop TWICE with independently
  randomized parameters and generalized Gaussian kernels. This is a concrete correction to the
  degradation tool specced in the parked plan.

- **The round-trip bias harness is separable and may be worth doing on its own.** Degrade a
  trusted modern year, run the coarse-year model on it, compare to the trusted answer; the gap
  is instrument bias. It attacks the calibration-multiplier blocker directly and needs no
  synthetic training to be useful.

- **Biased vs random label error.** Networks tolerate random label noise but a *systematic*
  ~5 px shift costs ~10% Dice. We MEASURED a ~5 m systematic east-side ortho-vs-CHM
  displacement on 2026-08-27 (shadow-FP probe). At metre-scale pixels that is exactly the
  described failure mode — this is a live data issue in current work, not a synthetic-data
  concern.

- **Walk the ladder rather than jump.** Pseudo-label one hop at a time (2024 -> 2021s -> ... ->
  2000 -> 1996) with change screening so imagery is never paired with labels for trees that did
  not yet exist. Our stable-groves work IS that change screening — the two compose.

- **Uncertainty-scaled targets** (Trees as Gaussians): scale target kernels by spatial
  uncertainty to absorb misregistration, crown-size variation and label noise in one mechanism.

- **Olofsson stratified estimation** for any published area/change number — already the parked
  publication plan; the brief reinforces it.

## Sourcing caveat carried from the document itself

Its own note states full-text retrieval was blocked and figures come from abstracts and search
results. Verify any number against the primary source before it appears in anything public.

---

# Semantic Segmentation of Degraded Historical Imagery for Urban Forest Mapping

**Research briefing for the Edmonds Urban Tree Crown Detection project**
Prepared 2026-08-27 · Context: extending the Edmonds canopy record back to 1996–2003 at ~100 cm resolution

> **Note on sourcing.** All findings below were gathered via literature search. Full-text PDF retrieval was blocked by this session's network egress policy (arxiv.org, mdpi.com, pmc.ncbi.nlm.nih.gov, copernicus.org, and the OpenAlex/Semantic Scholar APIs were all unreachable), so method details come from search-tool retrieval and abstracts rather than full-paper ingestion. Quantitative figures are reproduced as reported; verify against the primary sources before publishing any of them.

---

## Table of contents

- [Part A — What the latest research says about 100 cm degraded imagery](#part-a)
  - [A.1 Reality check on 100 cm](#a1)
  - [A.2 You may be able to get better pixels](#a2)
  - [A.3 Five method families](#a3)
  - [A.4 The trap that bites hardest](#a4)
  - [A.5 Recommended build for Edmonds](#a5)
- [Part B — Deep dive: synthetic labeling and degraded labeling](#part-b)
  - [B.0 Two corrections](#b0)
  - [B.1 Synthetic labeling: six families](#b1)
  - [B.2 Degraded labeling: what actually breaks](#b2)
  - [B.3 Degraded imagery, done right](#b3)
  - [B.4 The honest scoreboard on real historical imagery](#b4)
  - [B.5 What this changes about the plan](#b5)
- [Part C — Pipeline implementation prompt](#part-c)
- [Consolidated source list](#sources)

---

<a name="part-a"></a>
# Part A — What the latest research says about 100 cm degraded imagery

<a name="a1"></a>
## A.1 Reality check on 100 cm

The existing Edmonds DDT + watershed pipeline is trained at 7.5 cm. A 6 m urban crown is ~80 px across (~5,000 px of support) at 7.5 cm; at 100 cm it is ~6 px across (~28 px). That is roughly **178× less pixel evidence per crown**. The repo's `min_distance: 30` (2.25 m at 7.5 cm) becomes a 30 m seed spacing, and `min_crown_area_m2: 2.0` becomes 2 pixels.

The literature is consistent on where the wall is:

- On 60 cm NAIP, crowns under ~1.5 m diameter are **frequently missed**.
- A well-tuned U-Net on NAIP achieves **Dice 0.824 for canopy segmentation** but only **F1 0.687 for individual tree detection** ([Remote Sensing 2025](https://doi.org/10.3390/rs18121899)).

At 100 cm the individual-tree task degrades further — young street trees and ornamentals become invisible.

**Framing:** at 1996–2003 / 100 cm, nobody in the literature is doing individual crown delineation. Teams do **binary canopy semantic segmentation** (cover fraction / canopy polygons), and that is achievable. Reframe the 1996–2003 epoch as a canopy-cover backdrop for the 2002–2023 crown time series, not as an extension of it.

<a name="a2"></a>
## A.2 Before fighting the pixels: you may be able to get better pixels

For 1996–2003 Puget Sound, the 1 m DOQQ is a *derived product*, not the original data. The source film is **NAPP** (National Aerial Photography Program, 1:40,000 scale, 1987–2007, >1.3 million images, [USGS EROS](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-national-aerial-photography-program-napp)).

- USGS historically scanned CIR NAPP at **14 microns**.
- **12.5-micron rescans** are available for historical film 1951–2012, including NAPP.
- At 1:40,000, a 12.5 µm scan ≈ **50 cm GSD** — twice the linear resolution of the DOQQ.

Serious historical-imagery teams order the film scans and re-orthorectify rather than accept the 1 m derivative.

**Also verify:** Puget Sound Orthophotography 2002 and Snohomish County holdings. Note that `scripts/download_imagery.py` pulls **King County** tile services, but Edmonds is in **Snohomish County** — confirm what those tiles actually cover for the early years.

This is the single highest-leverage item on the list. Going 100 cm → 50 cm quadruples pixel support per crown.

<a name="a3"></a>
## A.3 Five method families teams are actually using

### 1. Degradation-simulation training
Train on good data, degraded to match the bad. Take existing 7.5 cm annotated tiles, simulate the 1996 acquisition (downsample to 100 cm, blur for film + scanner MTF, film grain, grayscale/CIR band collapse, JPEG artifacts), then train a canopy-segmentation head on the degraded copies. The explicit recommendation in the literature is to acquire labelled training data from modern imagery and artificially degrade it to resemble historical data. [RobustSAM](https://arxiv.org/html/2406.09627v1) formalizes this with 15 synthetic degradation types plus anti-degradation modules enforcing feature consistency between clear and degraded versions of the same scene — that consistency loss is the transferable part.

**See Part B.0 and B.3 for an important caveat and correction to this approach.**

### 2. Domain adaptation from modern → historical
[Multiclass Land Cover Mapping from Historical Orthophotos Using Domain Adaptation and Spatio-Temporal Transfer Learning](https://doi.org/10.3390/rs14235911) (RS 2022) is canonical: extract VHR multi-class land cover from historical orthophotos with *no target-domain labels*, via domain adaptation + transfer learning, including image-to-image translation with conditional GANs between recent RGB and historical monochromatic imagery.

Techniques run cheap → expensive: histogram matching and canonical correlation (already used in `temporal_inference.py`), CycleGAN style transfer, adversarial feature alignment, self-training.

**Caveat:** CycleGAN transfers style well *specifically for the vegetation class* but hallucinates — it deletes small objects and replaces them with buildings/background. Acceptable for canopy; dangerous if object counts matter.

See also [FCNs for land cover classification from historical panchromatic aerial photographs](https://www.sciencedirect.com/science/article/abs/pii/S0924271620301921) (ISPRS 2020) and the [2025 ISPRS unsupervised DA work](https://isprs-annals.copernicus.org/articles/X-4-W6-2025/17/2025/isprs-annals-X-4-W6-2025-17-2025.pdf).

### 3. Iterative pseudo-labeling / bootstrapping
[Historical habitat mapping from black-and-white aerial photography: proof of concept for post-WWII Switzerland](https://www.sciencedirect.com/science/article/pii/S1569843225001116) (2025, WSL) is the closest published analog. **16 habitat classes from 1 m grayscale 1946 imagery** across 7 case-study areas of 320–508 km²: object-based segmentation on spectral + shape homogeneity, random forest, and an **iterative sampling loop** where confident predictions seed the next training round. The stated design goal was that the historical map be *compatible with the present-day habitat map* — the same temporal-comparability problem.

Note they chose OBIA + RF over deep learning at this resolution. That is a signal about the information content of 1 m grayscale.

### 4. Anchor on the modern epoch and detect change
The most important design pattern. [Christchurch 2025](https://www.sciencedirect.com/science/article/pii/S2667393225000018): DeepLabv3+ pretrained on existing canopy data, fine-tuned on high-res imagery to delineate the *good* epoch; SAM to cut it into individual trees; then — because aerial imagery across dates was too poorly aligned to trust — **LiDAR height change, not image differencing**, supplied the change signal.

Results: **F1 0.934, IoU 0.883** for property-scale canopy loss; 14.5% of 2016 canopy lost by 2021, 74.9% of it residential. Their framing is "remote sensing data of varying type and quality with imperfect alignment."

Parallax on tall objects at 1 m orthorectification is a genuine killer — misregistration of 2–3 px is a whole crown.

### 5. Foundation-model features when labels are scarce
Frozen DINOv2/DINOv3 encoders with a light decoder show strong label-efficiency and explicit **robustness to noise** in degraded specialist domains — LoRA-tuned DINOv2 on geological imagery reaches IoU ≈0.81 with 1,000 labels and still ≈0.74 with **4** ([ScienceDirect 2025](https://www.sciencedirect.com/science/article/pii/S1674775525002677)).

**However — see Part B.0 for a direct contradiction of this recommendation in the tree-canopy-specific literature.**

### Two things more marginal than the hype suggests

- **Super-resolution preprocessing** ([SR-UGSnet](https://www.tandfonline.com/doi/full/10.1080/10106049.2025.2547928), [0.5 m aerial ITD](https://www.sciencedirect.com/science/article/pii/S0924271625001418)) genuinely helps in some pipelines, but SR invents plausible texture. For a politically sensitive canopy-loss number, hallucinated crowns are a liability.
- **Colorization** of B&W historical aerials ([Colorizing the Past](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9604844/)) is well studied and makes a good figure, but adds no information the network didn't already have.

Use both as visual aids, not evidentiary inputs.

<a name="a4"></a>
## A.4 The trap that will bite hardest

Canopy cover estimates are **strongly resolution- and method-dependent**, so a naive 1996-vs-2023 comparison measures the pipeline, not Edmonds' trees.

Documented magnitudes:
- 30 m NLCD underestimated urban canopy by up to **28.4%**.
- Across cities, product choice alone shifts estimates from **−38% to +3%** ([Nature Sci Data 2025](https://www.nature.com/articles/s41597-025-04816-0); [USGS](https://pubs.usgs.gov/publication/70278923)).

A 1996 number will be biased low against a 2023 number for purely instrumental reasons.

**The fix, non-negotiable:** degrade a modern year to 1996 specs, run the 1996 model on it, and compare against the 7.5 cm result for that same year. That gives an empirical bias correction and an honest uncertainty band.

Add **leaf-on/leaf-off acquisition-date checks** — a leaf-off spring 1996 flight versus a leaf-on July 2023 flight can manufacture a canopy "gain" larger than two decades of real growth.

<a name="a5"></a>
## A.5 Recommended build for Edmonds

1. Chase the NAPP 12.5 µm rescans for 1996/1998/2000 before writing code — 50 cm changes what's possible.
2. Add a `--degrade` mode to the tiling stage emitting 100 cm grayscale/CIR versions of the 530 existing tiles with blur + grain + JPEG.
3. Train a **separate binary canopy head** (not DDT/watershed) on those degraded tiles.
4. Validate by round-tripping a modern year through the degradation and comparing to ground truth; publish the bias correction alongside every historical number.
5. Report 1996–2003 as **canopy cover percentage with an uncertainty band**; keep the 180k individual crowns as a 2002+ product only.

---

<a name="part-b"></a>
# Part B — Deep dive: synthetic labeling and degraded labeling

<a name="b0"></a>
## B.0 Two corrections to Part A

### Correction 1 — the degradation-simulation plan has a documented failure mode

The literature is explicit that training on artificially degraded modern imagery and testing on real historical imagery has a real generalization gap:

- Models trained on *regularized* degradations "exhibit weaker generalization when confronted with complex, real-world variations… degradation patterns in synthetic data are more regular with lower noise levels."
- Real archival-film low-resolution data "better represent physically induced degradations compared to artificially generated pseudo degradations."

Sources: [DA-CycleGAN (2026)](https://www.mdpi.com/2313-433X/12/4/155); [real-world degradation patterns (2025)](https://arxiv.org/html/2506.17027).

The plan is not wrong, but a naive downsample→blur→noise chain produces a model that works beautifully on the fakes and mediocrely on 1996. **Fix in B.3.**

### Correction 2 — the DINOv2 recommendation is contradicted by the closest-matching experiment

[Sparse Data Tree Canopy Segmentation: Fine-Tuning Leading Pretrained Models on Only 150 Images](https://arxiv.org/abs/2601.10931) fine-tuned five architectures on the Solafune tree canopy dataset — **150 annotated images** — and found:

> Pretrained **convolutional** models (YOLOv11, Mask R-CNN) generalize significantly better than transformer-based models. DeepLabv3, Swin-UNet and DINOv2 underperformed — attributed to differences between semantic and instance segmentation tasks, ViTs' high data requirements, and lack of strong inductive biases.

With 530 tiles, Edmonds is in that regime. **Keep the ResNet-101 U-Net.**

<a name="b1"></a>
## B.1 Synthetic labeling — six families of "where do labels come from"

### 1.1 Temporal label transfer (backdating)

The cleanest formalism: augment training with pairs **(X^(t−k), Y^t)** — old imagery, new labels — exploiting that most labels are time-invariant, with an unsupervised step to **estimate construction/change dates so imagery is never paired from before the feature existed** ([Mapping industrial poultry operations at scale](https://arxiv.org/pdf/2112.10988)).

That date-screening step is the whole ballgame, and a tree application needs it in reverse: don't pair 1996 imagery with a 2020 crown planted in 2005.

[Segmenting France Across Four Centuries](https://arxiv.org/abs/2505.24824) — 548,305 km², three map collections (18th/19th/20th c.), 22,878 km² of manual historical labels as a check — ran the decisive ablation across three approaches:

| Approach | Result |
|---|---|
| Fully-supervised on historical labels | baseline |
| Weakly-supervised, modern labels used directly | worse |
| Modern labels **+ image-to-image translation** to modern style | **significantly best** |

They reason explicitly that permanent landscape features — old-growth forest, transport corridors, waterways — carry the supervisory signal through the temporal gap.

[Semantic Segmentation for Sequential Historical Maps by Learning from Only One Map](https://arxiv.org/html/2501.01845) chains it: train on the one labeled epoch, pseudo-label the adjacent epoch, fold it in, step again — walking backward through time one hop at a time rather than jumping decades.

**Relevance:** with epochs at 2023, 2021, 2019, 2017, 2015, 2013, 2012, 2009, 2007, 2005, 2002, Edmonds has an unusually dense ladder to walk down toward 1996.

### 1.2 Cross-resolution label transfer (label super-resolution)

[Label Super-Resolution Networks](https://openreview.net/pdf?id=rkxwShA9Ym) (ICLR 2019) is foundational and was built on **exactly these data types**: NAIP 1 m 4-band imagery supervised by NLCD 30 m coarse labels, over the Chesapeake Land Cover dataset (160,000 km², four HR classes including forest).

Mechanism: a loss matching the *distribution* of model outputs within a coarse block to the distribution the coarse label implies. Critically, **the HR classes do not have to match the LR classes**.

Extensions: [inter-instance loss](https://arxiv.org/pdf/1904.04429), [epitomic representations](https://arxiv.org/pdf/2004.11498).

[Paraformer](https://arxiv.org/html/2403.02746v3) (CVPR 2024) is the modern version: parallel downsampling-free CNN + Transformer branches, plus a pseudo-label-assisted training (PLAT) module refining LR labels into HR supervision.

[SCDWSL](https://www.sciencedirect.com/science/article/abs/pii/S0924271625000644) (ISPRS J. 2025) contributes the most useful **diagnosis** in this literature. It decomposes historical-product label noise into two kinds:

- **Scale-response noise** — from the resolution mismatch itself
- **Model-cognitive noise** — from misclassification *or genuine temporal change*

and handles them at different levels, using **superpixels rather than pixels as training units** to absorb the scale-response component.

**Relevance:** when a 2020-trained model is pushed onto 1996 imagery, errors are exactly these two things braided together. Separating them is the difference between a measurement and a guess.

### 1.3 Physical proxy labels (LiDAR → labels)

The most mature family for trees, and the most brutally honest.

[Counting Trees from Satellite Imagery with Noisy Supervision](https://arxiv.org/pdf/2606.24786) generates pseudo-labels the obvious way — local maxima on a LiDAR canopy height model, tuned by minimum height and minimum inter-peak distance — then reports:

> "This simplistic procedure produces a highly noisy signal. When compared with field-collected tree positions, the resulting labels yield an **R² close to zero**. In isolation, this signal is therefore largely insufficient for accurate tree counting."

They recover by combining **strong** annotations (photo-interpreted/field, precise but tiny coverage) with **weak** ones (automatic, vast, noisy). Released TINYTREES: 3 continents, 3 sensors, 0.8–4.2 m GSD, >25k km², **216 million tree annotations**.

[Trees as Gaussians](https://spj.science.org/doi/10.34133/remotesensing.1049) is the one worth studying hardest:

- U-Net + ResNet50 on 3 m PlanetScope
- Trained on *billions* of points auto-extracted from airborne LiDAR
- Predicts a heatmap **plus a spatial uncertainty map**
- **Gaussian kernels scaled according to spatial uncertainty** — one mechanism absorbing crown-size variation, pseudo-label noise, *and* imperfect LiDAR↔imagery alignment simultaneously
- Fractional cover **R² = 0.81** against aerial LiDAR

**Relevance:** structurally similar to the Edmonds DDT — already predicting a continuous field with a peak at crown center. Making peak width a function of *confidence* rather than crown geometry is a small change with large consequences at coarse resolution.

[Monitoring Urban Forests from Auto-Generated Segmentation Maps](https://arxiv.org/abs/2206.06948) (Albrecht, Liu, Wang, Klein, Zhu) is the urban-specific one: LiDAR as a source of noisy labels for tree localization in orthophotos, "close-to-zero human interaction," demonstrated on Hurricane Sandy's impact in Coney Island against a Brooklyn control.

[Tolan et al.](https://www.sciencedirect.com/science/article/pii/S003442572300439X) trained a self-supervised ViT + convolutional decoder on ~0.59 m Maxar imagery against 1 m LiDAR CHM labels — the template for "modern LiDAR teaches a model that reads optical imagery."

### 1.4 Foundation-model auto-labeling

[SAM2-ELNet](https://ieeexplore.ieee.org/document/11143946/) is the honest version: SAM2 "struggles to perform effectively on heterogeneous, low-contrast remote sensing imagery" — which describes 1996 panchromatic precisely. They freeze the Hiera backbone and fine-tune an adapter + decoder, targeting the three failure modes of naive auto-labels: **label detail loss, fragmentation, boundary inaccuracy**.

The Christchurch canopy-loss study used SAM only *downstream* of a supervised DeepLabv3+, to cut an already-correct canopy mask into individual trees. SAM supplied instance boundaries, not semantics. **That ordering is deliberate and worth copying.**

### 1.5 Rendered synthetic imagery with free perfect labels

[SPREAD](https://www.sciencedirect.com/science/article/pii/S1574954125000949) (Unreal Engine + AirSim forest scenes) and successor [CAMP3D / Scaling Up Forest Vision with Synthetic Data](https://arxiv.org/abs/2509.11201) (game engine + physics-based LiDAR simulation) report the headline sim-to-real result:

> After fine-tuning on **a single real forest plot of less than 0.1 hectare**, the synthetically-pretrained model matches a model trained on full-scale real data.

Their stated critical factors: **physics, diversity, and scale** — in that order. Physics first is the recurring lesson.

### 1.6 Generative synthesis and compositing

Diffusion has displaced GANs: synthetic data from diffusion models "can effectively approximate real data, while performance with GAN-based data is visibly worse," with GANs hampered by training instability and mode collapse ([review](https://www.tandfonline.com/doi/full/10.1080/01431161.2025.2527373); [AeroGen](https://arxiv.org/html/2411.15497v2)).

[Data Augmentation and Resolution Enhancement using GANs and Diffusion Models for Tree Segmentation](https://arxiv.org/abs/2505.15077) (2025) is the direct hit: domain adaptation + GANs + diffusion to enhance *low-resolution aerial images* for tree segmentation without large manual annotation.

Plain [copy-paste](https://www.researchgate.net/publication/355864719_Simple_Copy-Paste_is_a_Strong_Data_Augmentation_Method_for_Instance_Segmentation) remains stubbornly strong and nearly free. The most relevant validation is ecological: copy-paste improved species ID **in new, unseen locations by 8% ± 2%** ([camera trap study](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12588685/)).

**Relevance:** cross-*site* generalization is the actual Edmonds problem — 5 training sites, whole-city inference — and that is what copy-paste demonstrably buys.

<a name="b2"></a>
## B.2 Degraded labeling — what actually breaks

### 2.1 The taxonomy that matters

[Benchmarking Label Noise in Instance Segmentation: Spatial Noise Matters](https://arxiv.org/html/2406.10891v2) splits label noise into **class noise** (wrong category) and **spatial noise**, subdividing spatial into:

- **Scale noise** — instances annotated systematically larger or smaller than truth
- **Localization noise** — random boundary displacement
- **Approximation noise** — simplified boundaries, fewer polygon vertices

Benchmarks released: COCO-N, Cityscapes-N, VIPER-N, COCO-WAN.

| Condition | Performance retained |
|---|---|
| Mask R-CNN / ResNet50 on COCO-N, Easy / Medium / Hard | ~91% / 85% / 79% |
| Mask R-CNN / ResNet50 on **Cityscapes-N**, Easy / Medium / Hard | **85% / 74% / 68%** |
| Moderate noise, worst case | up to **35% mask mAP drop** |
| 20% symmetric **class** noise | only **2.7 mAP** drop; 0.9 fg/bg mAP |

Dense, cluttered, small-object scenes (Cityscapes) are far more fragile — which is what urban canopy is.

> **Read those last two rows together: spatial noise is roughly an order of magnitude more expensive than class noise.** For a binary canopy task, class noise is nearly irrelevant and geometry is everything.

### 2.2 The bias distinction — the single most important finding

[Label noise in segmentation networks: mitigation must deal with bias](https://ar5iv.labs.arxiv.org/html/2107.02189):

> Networks are robust, or partially robust, to **unbiased** errors and **sensitive to biased** ones.

The experiment: shift the entire mask by n pixels to create consistent misalignment. At **n = 5 pixels, ~10% Dice is lost.**

Applied to Edmonds imagery:

| Resolution | 5 px equals | Interpretation |
|---|---|---|
| 7.5 cm | 37 cm | noise |
| 100 cm | **5 metres** | **most of a crown** |

Orthorectification error between a 1996 DOQQ and a 2020 ortho is routinely that size, and it is *biased*, not random: parallax on tall objects displaces systematically with look angle.

**This is the mechanism by which historical canopy numbers get quietly wrong** — and precisely why the Christchurch team abandoned image alignment for LiDAR height change.

[The Bayesian spatially-correlated approach](https://arxiv.org/html/2504.14795v2) adds the compounding factor: remote sensing label errors "are not independently distributed, but usually appear in spatially connected regions where adjacent pixels are more likely to share the same errors" — so the i.i.d. assumption underneath most noise-robust methods is violated from the start.

### 2.3 Why it works at all: early-learning dynamics

Networks "prioritize learning simple and general patterns before fitting the noise" — clean samples are fit first and produce small losses; noisy ones lag with high losses. Every sample-selection method exploits this window.

**Corollary: early stopping is a noise-robustness technique.** The repo's `early_stop_patience: 25` is doing more work than it looks like.

### 2.4 The mitigation toolkit, cheapest first

| Method | Mechanism | Source |
|---|---|---|
| Early stopping | Exit before memorization | [robustness study](https://arxiv.org/pdf/2003.06240) |
| Symmetric CE / GJS / ELR | Bound the loss so confident-wrong labels can't dominate | [all-weather land cover](https://arxiv.org/html/2504.13458v1) |
| Superpixels as training units | Absorbs scale-response noise structurally | [SCDWSL](https://www.sciencedirect.com/science/article/abs/pii/S0924271625000644) |
| Uncertainty-scaled targets | Widen the target where the label is less trusted | [Trees as Gaussians](https://spj.science.org/doi/10.34133/remotesensing.1049) |
| Label-only elastic deformation | Perturb *labels* each epoch so the net can't memorize a boundary | [arXiv 2508.10383](https://arxiv.org/pdf/2508.10383) |
| Co-teaching / JoCoR | Two nets exchange small-loss samples; JoCoR adds co-regularization | [survey](https://arxiv.org/pdf/2404.04159) |
| AIO2 | Adaptive Correction Trigger reads the training-accuracy curve to know *when* to correct; Online Object-wise Correction fixes whole objects, not pixels | [arXiv 2403.01641](https://arxiv.org/html/2403.01641) |
| Curriculum confidence thresholds | Start high-confidence, decay the threshold, per-class adaptive | [semi-supervised transformer](https://doi.org/10.3390/rs18030480) |

AIO2's **object-level** correction is the right granularity for trees — a crown is an object, and pixel-wise correction on a 6-pixel crown is meaningless.

<a name="b3"></a>
## B.3 Degraded imagery, done the way that survives contact with 1996

### 3.1 Real-ESRGAN's high-order model is the template

Why the naive chain is too clean: [Real-ESRGAN](https://arxiv.org/abs/2107.10833) trains real-world blind SR **with pure synthetic data** and gets away with it via a **high-order degradation model** — *repeated* blur → downsample → noise → JPEG loops (two, in their case) with independently randomized parameters each pass, plus **generalized Gaussian blur kernels** because "simple kernels may not well approximate real camera blur."

One pass of each operation produces a degradation manifold that is too narrow and too regular. Two randomized passes produce the messy, compounded degradation an actual archival chain applied:

```
camera optics → film emulsion → storage/aging → scanner optics
    → resampling → JPEG storage in the tile service
```

The physics of each stage is documented: PSF and MTF are Fourier duals; the PSF "can encapsulate many degradation processes such as atmospheric turbulence, motion blur, and optical system effects"; film scanners add "resolution, focus, and diffraction issues along with movement" on top of the film's own MTF ([MTF for film scanners](https://www.imaging.org/common/uploaded%20files/pdfs/Papers/1999/PICS-0-42/1033.pdf); [Koren](https://www.normankoren.com/Tutorials/MTF2.html)).

### 3.2 Or stop guessing the degradation and learn it

[DA-CycleGAN](https://www.mdpi.com/2313-433X/12/4/155) adds a **degradation-adaptive module** to CycleGAN to learn historical degradation patterns from unpaired data, on the premise that historical degradations "are typically much more complex and less well understood compared to modern digital imagery."

Edmonds has the ingredients: unlabeled 1996 imagery in quantity, and labeled 2020 imagery — the classic unpaired setup. **Strictly better than hand-tuning a blur sigma**, and the approach to take if the round-trip check shows a large gap.

### 3.3 Colorization: read the numbers carefully

[W-Net](https://onlinelibrary.wiley.com/doi/10.1111/exsy.12622) (Dias et al., 2020) stacks two U-Nets — one segments, the second uses the mask to colorize — and beats a U-Net baseline on grayscale *and* color.

[Colorizing the Past](https://doi.org/10.3390/jimaging8100269) motivates it correctly: legacy grayscale photographs "lack spectral information that hinders their use in current remote sensing approaches relying on spectral data."

The most complete pipeline is [Reconstructing a Century of Urban Growth](https://dx.doi.org/10.3390/rs18101517) (Les Sables-d'Olonne, 1920–2024): attention-enhanced Pix2Pix colorization → few-shot U-Net++ segmentation, spanning panchromatic 1920–1971, digital aerial 1997, and VHR satellite 2024.

Reported: colorization PSNR 35.21 dB / SSIM 0.9762; segmentation **mIoU 0.9789 — on modern imagery.**

> They report a headline accuracy figure from the easy end of their own century-long domain gap. That is the tell, and it is the pattern to watch across this entire literature: **the impressive number is usually measured where the data is good.**

<a name="b4"></a>
## B.4 The honest scoreboard on *real* historical imagery

| Study | Data | Method | Result |
|---|---|---|---|
| [HistAerial / Ratajczak](https://dl.acm.org/doi/abs/10.1109/TIP.2019.2896492) (IEEE TIP 2019) | 81 B&W aerials, France 1970–90, 4.9M patches, 7 classes | 59 methods benchmarked | 45–89%; **best was a handcrafted filter combination at 89.3%**, not learned features |
| [Swiss 1946](https://www.sciencedirect.com/science/article/pii/S1569843225001116) (2025) | swisstopo 1946 US-Army composite, **1 m grayscale**, 7 areas 320–508 km² | OBIA + random forest + iterative sampling, 16 habitat classes | Feasible area-wide; designed for compatibility with the modern habitat map |
| [Adelaide Island](https://www.sciencedirect.com/science/article/pii/S2667393223000273) (ISPRS OJPRS 2024) | TMA Antarctic archive, scanned grayscale, 1940–2000 | U-Net, **80 training images** | **73%** on 20 validation images (land/water/ice) |
| [Segmenting France](https://arxiv.org/abs/2505.24824) (2025) | 3 map collections, 18th–20th c. | Modern labels + image-to-image translation | Translation-first ≫ modern-labels-direct |
| [WakeupUrban](https://arxiv.org/abs/2506.09476) (2025) | Declassified Keyhole satellite, 4 cities, 2 continents | Fully unsupervised; confidence-aware alignment + focal-confidence loss | First professionally annotated mid-century RS segmentation benchmark |
| [Namibia](https://arxiv.org/pdf/2404.08544) (2024) | Sub-meter grayscale, **1943 & 1972** | Object detection: waterholes, homesteads, **individual trees** | Measured mean tree size ↑, homesteads ↓ across the interval |
| [ISPRS 2020](https://www.sciencedirect.com/science/article/abs/pii/S0924271620301921) | Historical panchromatic aerials | FCN land cover | Foundational reference |
| [IGARSS 2023](https://ieeexplore.ieee.org/document/10281819/) | Turkey/Bulgaria panchromatic, 1950s–70s | U-Net++ / DeepLabv3 | New benchmark dataset |

### Two patterns worth naming

**1. On genuinely old grayscale imagery, classical methods are still competitive or winning.** HistAerial's best of 59 methods was handcrafted; the 2025 Swiss study chose OBIA + RF over deep learning at 1 m. That is a statement about the information content of the pixels, not about the researchers.

**2. Nobody in this table delineates individual tree crowns at ~1 m from historical imagery.** Namibia detects individual trees in sub-meter *desert* imagery where crowns are isolated against bare ground — the easiest possible case, not analogous to a closed Pacific Northwest urban canopy.

<a name="b5"></a>
## B.5 What this changes about the plan

### The 530 tiles are not the main asset
The main asset is eleven epochs of already-computed model output from 2002–2023 at known quality, plus the imagery ladder connecting them. The literature's best results come from label *transfer down a chain* (sequential historical maps, Segmenting France), not from one degraded jump.

**Action:** walk 2023 → 2021 → 2019 → … → 2002 → 1996 with pseudo-labeling at each hop, screening pairs for actual change the way the poultry paper screens by construction date.

### Reframe the target as label super-resolution, not degraded-image segmentation
Coarse 1996 imagery + a fine 2020 answer is the LSRN/Paraformer setup, on the exact data types LSRN was built for (NAIP-class imagery, coarse labels, forest class).

**Action:** adopt SCDWSL's decomposition — separate scale-response noise from model-cognitive noise, because only the second contains real canopy change and the first is pure instrument artifact.

### Make the degradation high-order and randomized, or learn it
Two Real-ESRGAN-style loops with generalized Gaussian kernels, not one clean chain. If the round-trip gap is large, go to DA-CycleGAN and learn the degradation from the unlabeled 1996 tiles.

### Predict uncertainty alongside canopy, and use it in the loss
Trees as Gaussians scales its target kernels by spatial uncertainty and thereby absorbs misregistration, crown-size variation, and label noise in one mechanism. This yields a defensible per-pixel confidence layer for free — which the board will want.

### Budget for the 5-pixel problem
At 100 cm a 5 m ortho offset costs ~10% Dice and it is biased, not random. Either co-register carefully and measure the residual, or follow Christchurch and derive change from a source that doesn't depend on image alignment.

### The calibration harness is the actual scientific contribution — and there is established machinery for it

[Olofsson et al., *Good practices for estimating area and assessing accuracy of land change*](https://www.sciencedirect.com/science/article/abs/pii/S0034425714000704) (RSE 2014) is the standard:

1. Implement a **probability sampling design** meeting accuracy and area-estimation objectives within practical constraints.
2. Implement a **response design protocol** on reference data with sufficient spatial and temporal representation.
3. Implement an **analysis consistent** with the sampling and response designs.
4. Report the **estimated error matrix in proportion of area**, plus overall, user's, and producer's accuracy.

> "The area of land use or land cover change obtained directly from a map may differ greatly from the true area of change because of map classification error, but an **error-adjusted estimator of area** can be easily produced once an accuracy assessment has been performed and an error matrix constructed."

That is the 1996 problem stated formally, and the fix is a **stratified estimator**, not a fudge factor. See also [Olofsson et al. 2013 on stratified estimation](https://www.sciencedirect.com/science/article/abs/pii/S0034425712004191) and the R implementation in [`mapaccuracy::olofsson`](https://search.r-project.org/CRAN/refmans/mapaccuracy/html/olofsson.html).

Citing this makes the numbers defensible to anyone with a remote sensing background.

### One label-efficiency lever worth knowing about

[iSAGE](https://arxiv.org/abs/2606.10136) is a human-in-the-loop framework built on the hypothesis that **confident model errors are the most valuable pixels to label**. Sparse clicks land only on visually unambiguous pixels; an error-weighted loss amplifies the gradient there; **the annotator is never asked to make a boundary decision.**

That last property is what makes it usable on 1996 imagery, where a human genuinely cannot see where a crown ends. Open source ([GitHub](https://github.com/osmarluiz/iSAGE)), and probably the cheapest way to get real 1996 labels if some turn out to be necessary.

---

<a name="part-c"></a>
# Part C — Pipeline implementation prompt

Paste this into a fresh Claude Code session on the repo. Written to make the agent stop and explain itself in plain English at each stage, since the output has to be relayed to the Climate Advisory Board.

**Two notes on using it:**
- The `--degrade` realism check in Step 1 is the one place worth squinting at the output personally rather than trusting metrics. If the fake 1996 tiles don't look like 1996, everything downstream measures a fiction.
- NAPP film rescans are deliberately left out — that's a procurement task (ordering 12.5 µm scans from USGS EROS / APFO), not something the agent can do. If those come through at 50 cm, tell it: the degradation target changes from 100 cm to 50 cm and the whole picture improves.

```
We're extending the Edmonds tree crown pipeline back in time, and I need you to
teach me as you build it. Read this whole brief before touching anything.

## Who I am / how to talk to me

I'm on the Edmonds Climate Advisory Board. I understand this project well but I
am not a machine learning engineer, and everything I build here I have to
explain to city staff and volunteers who know even less. So:

- Before you start each stage, tell me in plain English what you're about to do
  and WHY, as if explaining to a city council member. Use analogies. Define
  every piece of jargon the first time you use it.
- After each stage, show me the result in a way I can actually look at — save
  side-by-side PNGs to outputs/, print real numbers, don't just say "done."
- When you hit a genuine fork in the road, stop and ask me. Give me 2-3 options
  in non-technical terms with the tradeoff spelled out. Don't just pick one and
  bury it in a commit.
- If something I asked for is a bad idea, say so plainly and tell me what you'd
  do instead. I'd rather be corrected than get a confident wrong answer.
- No walls of code dumped into chat. Write the files, then explain what you
  wrote.

## Context: what already exists

This repo detects individual tree crowns from 7.5 cm aerial imagery using a
"Deep Distance Transform" method — a U-Net with a ResNet-101 encoder predicts a
distance field, then watershed segmentation cuts it into individual crown
polygons. 530 hand-annotated 512x512 tiles across 5 sites. ~180,000 crowns
found citywide. F1 around 0.74-0.80.

Read scripts/pipeline.py, configs/default.yaml, docs/methodology.md, and
scripts/temporal_inference.py before planning. temporal_inference.py already
runs the model back to 2002 at 20 cm with histogram matching between years.

## The problem I'm trying to solve

I want to push the canopy record back to 1996-2003. The only imagery that
exists for those years is roughly 100 cm per pixel, and it may be grayscale
(black and white) or color-infrared rather than normal RGB.

Here's the thing I already understand and want you to design around: at 7.5 cm
a 6-meter tree crown is about 80 pixels across. At 100 cm it's about 6 pixels
across — roughly 178x less information per tree. Published work says that even
at 60 cm, crowns under 1.5 m diameter get missed routinely, and individual-tree
F1 drops to ~0.69 while canopy-area segmentation still holds around 0.82 Dice.

So I am NOT asking you to make the crown detector work at 100 cm. I accept that
individual trees are gone at that resolution. What I want is a separate, simpler
model that answers "is this pixel canopy or not" — total canopy cover, not
individual trees. Please push back if you think I've got that framing wrong.

## What to build

Do these in order. Commit after each one with a clear message. Work on branch
claude/semantic-segmentation-degraded-imagery-3hln6t.

### Step 1 — A "degrade" mode in the tiling stage

Add a way to take my existing 530 good tiles and make fake-1996 versions of
them. The labels stay the same; only the imagery gets worse. The point is that
I already have hand-annotated truth at 7.5 cm, so if I can convincingly fake
what those same trees looked like through a 1996 camera and a film scanner, I
get free training data for the old imagery without annotating a single 1996
tile by hand.

The degradation should simulate the real physical chain, roughly in this order:
downsample 7.5 cm to 100 cm, blur (film and scanner optics aren't sharp), add
film grain noise, collapse to grayscale or CIR, then JPEG-compress. Make each
piece configurable in the YAML with sensible defaults, and make the whole thing
reproducible from a seed.

IMPORTANT: do not apply each step only once. Published work on real-world
degradation (Real-ESRGAN) shows that a single clean chain produces degradations
that are too regular, and models trained on them generalize poorly to real
historical imagery. Use a "high-order" model: run the blur/downsample/noise/JPEG
loop TWICE with independently randomized parameters each pass, and use
generalized Gaussian blur kernels rather than plain Gaussian.

Before you write it: walk me through what each of those steps is physically
simulating, in plain language. I want to be able to defend this to someone who
asks "aren't you just making up old photos?"

When it's done, show me a grid of before/after tiles so I can eyeball whether
the fakes actually look like 1996 imagery. This is the step most likely to
quietly ruin everything downstream, so I want to look at it myself.

### Step 2 — A binary canopy model

Train a separate model on the degraded tiles that just does canopy / not-canopy.
Not the distance transform. Not watershed. Do not modify or break the existing
DDT pipeline — this is a parallel path.

Use the existing U-Net + ResNet-101 with a binary target. I looked into frozen
DINOv2 encoders and the evidence is against it at my data scale: a 2026 study
fine-tuning five architectures on a 150-image tree canopy dataset found
pretrained convolutional models (YOLOv11, Mask R-CNN) beat DINOv2, Swin-UNet
and DeepLabv3, because vision transformers need more data and lack inductive
bias. With 530 tiles I'm in that regime. Tell me if you disagree.

Two things I want in the training setup because the labels will be imperfect:
  - Keep early stopping aggressive. Networks fit clean labels before they
    memorize noisy ones, so stopping early IS a noise-robustness technique.
  - Consider a bounded/robust loss (symmetric cross-entropy) rather than plain
    BCE, and explain to me in plain language what that buys.

Report IoU and Dice on a held-out split, and show me predicted canopy masks
overlaid on the degraded tiles.

### Step 3 — The round-trip honesty check

This is the part I care most about and the part nobody does. Build a
calibration harness that:

  1. Takes a modern year where I have a trusted 7.5 cm answer.
  2. Runs that year's imagery through the degradation to fake 100 cm.
  3. Runs the new binary canopy model on the faked version.
  4. Compares the canopy-cover percentage from step 3 against the trusted
     answer from step 1.

The gap between those two numbers is my measurement bias, and I need it because
published work shows canopy estimates swing wildly with resolution and method —
30 m data underestimated urban canopy by up to 28.4%, and product choice alone
moves city estimates from -38% to +3%. If I report "1996 canopy was X%" without
this, I'm reporting my pipeline's blind spots as if they were Edmonds' trees.

Structure the output following Olofsson et al. 2014, "Good practices for
estimating area and assessing accuracy of land change" — probability sampling
design, an error matrix reported in PROPORTION OF AREA with user's and
producer's accuracy, and an error-adjusted estimator of area with confidence
intervals. Output a CSV plus a chart, structured so it can be printed next to
every historical number I publish.

Explain to me in plain language what "bias correction" means here and how I
should describe it in a public document without either overclaiming or making
the whole thing sound worthless.

## Things I want you to flag, not silently handle

- Leaf-on vs leaf-off: if a 1996 flight was in early spring and a 2023 flight
  was in July, deciduous trees alone could fake a canopy "gain" bigger than two
  decades of real growth. Tell me where in the pipeline this needs handling.
- Misregistration: published work shows that shifting a mask by just 5 pixels
  costs about 10% Dice, and that networks are robust to RANDOM label error but
  sensitive to BIASED error. At 100 cm, 5 pixels is 5 metres — most of a crown —
  and ortho/parallax error is biased, not random. Tell me if you see this biting
  the change analysis, and what you'd do about it.
- Anything in configs/default.yaml that becomes nonsense at 100 cm. I know
  min_distance: 30 and min_crown_area_m2: 2.0 are two of them. Find the rest.

## Start here

Don't write code yet. First read the repo, then come back and give me:
  1. Your plain-English summary of what we're building and why, in about a
     paragraph — I'll reuse this with the board.
  2. Your assessment of whether the U-Net-with-binary-target choice is right.
  3. Anything in my plan you think is wrong.

Then we'll go step by step.
```

---

<a name="sources"></a>
# Consolidated source list

## Urban canopy mapping and change detection
- [An Open and Transferable Deep Learning Framework for Mapping Urban Tree Canopy Using NAIP Imagery](https://doi.org/10.3390/rs18121899)
- [Detecting and measuring fine-scale urban tree canopy loss with deep learning and remote sensing](https://www.sciencedirect.com/science/article/pii/S2667393225000018) (Christchurch)
- [Deep Learning for Urban Tree Canopy Coverage Analysis: A Comparison and Case Study](https://doi.org/10.3390/geomatics4040022)
- [Combining aerial photos and LiDAR data to detect canopy cover change in urban forests](https://pmc.ncbi.nlm.nih.gov/articles/PMC9473407/)
- [An enhanced national-scale urban tree canopy cover dataset for the United States](https://www.nature.com/articles/s41597-025-04816-0)
- [The influence of tree canopy cover data choices on urban ecosystem accounting (USGS)](https://pubs.usgs.gov/publication/70278923)
- [Tree semantic segmentation from aerial image time series](https://arxiv.org/abs/2407.13102)
- [Sparse Data Tree Canopy Segmentation: Fine-Tuning Leading Pretrained Models on Only 150 Images](https://arxiv.org/abs/2601.10931)

## Historical imagery segmentation
- [Historical habitat mapping from black-and-white aerial photography: post-WWII Switzerland](https://www.sciencedirect.com/science/article/pii/S1569843225001116)
- [Fully convolutional networks for land cover classification from historical panchromatic aerial photographs](https://www.sciencedirect.com/science/article/abs/pii/S0924271620301921)
- [Multiclass Land Cover Mapping from Historical Orthophotos Using Domain Adaptation and Spatio-Temporal Transfer Learning](https://doi.org/10.3390/rs14235911)
- [Analyzing Decades-Long Environmental Changes in Namibia Using Archival Aerial Photography and Deep Learning](https://arxiv.org/pdf/2404.08544)
- [Unsupervised Domain Adaptation for semantic segmentation (ISPRS Annals 2025)](https://isprs-annals.copernicus.org/articles/X-4-W6-2025/17/2025/isprs-annals-X-4-W6-2025-17-2025.pdf)
- [Revisiting the Past: semantic segmentation of historical images of Adelaide Island using U-nets](https://www.sciencedirect.com/science/article/pii/S2667393223000273)
- [HistAerial dataset](http://eidolon.univ-lyon2.fr/~remi1/HistAerialDataset/) · [Ratajczak et al., IEEE TIP 2019](https://dl.acm.org/doi/abs/10.1109/TIP.2019.2896492)
- [WakeupUrban: Unsupervised Semantic Segmentation of Mid-20th century Urban Landscapes](https://arxiv.org/abs/2506.09476)
- [Deep Learning-Based Land Use Land Cover Segmentation of Historical Aerial Images (IGARSS 2023)](https://ieeexplore.ieee.org/document/10281819/)
- [Segmenting France Across Four Centuries](https://arxiv.org/abs/2505.24824) · [code](https://github.com/Archiel19/FRAx4)
- [Semantic Segmentation for Sequential Historical Maps by Learning from Only One Map](https://arxiv.org/html/2501.01845)

## Synthetic labeling — temporal and cross-resolution transfer
- [Mapping industrial poultry operations at scale with deep learning and aerial imagery](https://arxiv.org/pdf/2112.10988) (temporal augmentation formalism)
- [Label Super-Resolution Networks (ICLR 2019)](https://openreview.net/pdf?id=rkxwShA9Ym) · [Chesapeake Land Cover](https://lila.science/datasets/chesapeakelandcover)
- [Label SR with Inter-Instance Loss](https://arxiv.org/pdf/1904.04429) · [Epitomic label SR](https://arxiv.org/pdf/2004.11498)
- [Learning without Exact Guidance / Paraformer (CVPR 2024)](https://arxiv.org/html/2403.02746v3)
- [Superpixel-aware credible dual-expert learning (ISPRS J. 2025)](https://www.sciencedirect.com/science/article/abs/pii/S0924271625000644)
- [Weakly supervised land-cover classification with low-resolution labels through optimized label refinement](https://www.tandfonline.com/doi/full/10.1080/01431161.2024.2443612)

## Synthetic labeling — LiDAR proxy labels
- [Trees as Gaussians: Large-Scale Individual Tree Mapping](https://spj.science.org/doi/10.34133/remotesensing.1049)
- [Counting Trees from Satellite Imagery with Noisy Supervision (TINYTREES)](https://arxiv.org/pdf/2606.24786)
- [Monitoring Urban Forests from Auto-Generated Segmentation Maps](https://arxiv.org/abs/2206.06948)
- [Very high resolution canopy height maps from RGB imagery trained on aerial lidar (Tolan et al.)](https://www.sciencedirect.com/science/article/pii/S003442572300439X)
- [LiDAR Remote Sensing Meets Weak Supervision](https://arxiv.org/pdf/2503.18384)
- [Predicting urban tree cover from incomplete point labels and limited background information](https://arxiv.org/abs/2311.11592)

## Synthetic labeling — rendered, generative, compositing
- [SPREAD: synthetic dataset for forest vision tasks](https://www.sciencedirect.com/science/article/pii/S1574954125000949)
- [Scaling Up Forest Vision with Synthetic Data (CAMP3D)](https://arxiv.org/abs/2509.11201)
- [A comprehensive review of synthetic image generation methods in remote sensing](https://www.tandfonline.com/doi/full/10.1080/01431161.2025.2527373)
- [AeroGen: diffusion-driven data generation for RS object detection](https://arxiv.org/html/2411.15497v2)
- [Data Augmentation and Resolution Enhancement using GANs and Diffusion Models for Tree Segmentation](https://arxiv.org/abs/2505.15077)
- [Simple Copy-Paste is a Strong Data Augmentation Method](https://www.researchgate.net/publication/355864719_Simple_Copy-Paste_is_a_Strong_Data_Augmentation_Method_for_Instance_Segmentation)
- [Copy-Paste Augmentation Improves Automatic Species Identification in Camera Trap Images](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12588685/)

## Degraded / noisy labeling
- [Benchmarking Label Noise in Instance Segmentation: Spatial Noise Matters](https://arxiv.org/html/2406.10891v2)
- [Label noise in segmentation networks: mitigation must deal with bias](https://ar5iv.labs.arxiv.org/html/2107.02189)
- [Robustness study of noisy annotation in deep learning based medical image segmentation](https://arxiv.org/pdf/2003.06240)
- [A Bayesian Approach to Segmentation with Noisy Labels via Spatially Correlated Distributions](https://arxiv.org/html/2504.14795v2)
- [Unlocking Robust Semantic Segmentation via Label-only Elastic Deformations](https://arxiv.org/pdf/2508.10383)
- [AIO2: Online Correction of Object Labels](https://arxiv.org/html/2403.01641)
- [SAM2-ELNet: Label Enhancement and Automatic Annotation](https://ieeexplore.ieee.org/document/11143946/)
- [Learning from Noisy Pseudo-Labels for All-Weather Land Cover Mapping](https://arxiv.org/html/2504.13458v1)
- [Noisy Label Processing for Classification: A Survey](https://arxiv.org/pdf/2404.04159)
- [Data-Centric Benchmark for Label Noise Estimation and Ranking in RS Image Segmentation](https://arxiv.org/html/2603.00604v1)
- [A Semi-Supervised Transformer with a Curriculum Training Pipeline](https://doi.org/10.3390/rs18030480)

## Degraded imagery — simulation, restoration, colorization
- [Real-ESRGAN: Training Real-World Blind Super-Resolution with Pure Synthetic Data](https://arxiv.org/abs/2107.10833)
- [DA-CycleGAN: Degradation-Adaptive Unpaired Super-Resolution for Historical Image Restoration](https://www.mdpi.com/2313-433X/12/4/155)
- [Unsupervised Image Super-Resolution Based on Real-World Degradation Patterns](https://arxiv.org/html/2506.17027)
- [RobustSAM: Segment Anything Robustly on Degraded Images](https://arxiv.org/html/2406.09627v1)
- [An Evaluation of MTF Determination Methods for 35mm Film Scanners](https://www.imaging.org/common/uploaded%20files/pdfs/Papers/1999/PICS-0-42/1033.pdf)
- [Scanners and sharpening: resolution and MTF (Koren)](https://www.normankoren.com/Tutorials/MTF2.html)
- [Enhancing Historical Aerial Photographs: Non-Reference Metric and Photo Interpretation Elements](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11991374/)
- [Semantic segmentation and colorization of grayscale aerial imagery with W-Net models](https://onlinelibrary.wiley.com/doi/10.1111/exsy.12622)
- [Colorizing the Past: Automatic Colorization of Historical Aerial Images](https://doi.org/10.3390/jimaging8100269)
- [Reconstructing a Century of Urban Growth (Les Sables-d'Olonne, 1920–2024)](https://dx.doi.org/10.3390/rs18101517)
- [A novel super-resolution urban green space segmentation network](https://www.tandfonline.com/doi/full/10.1080/10106049.2025.2547928)
- [Super-resolution supporting individual tree detection using half-meter aerial data](https://www.sciencedirect.com/science/article/pii/S0924271625001418)
- [DINOv2 rocks geological image analysis](https://www.sciencedirect.com/science/article/pii/S1674775525002677)

## Annotation efficiency
- [iSAGE: Human-in-the-Loop Framework for RS Semantic Segmentation via Sparse Point Supervision](https://arxiv.org/abs/2606.10136) · [GitHub](https://github.com/osmarluiz/iSAGE)
- [Sparse point annotations for remote sensing image segmentation](https://www.nature.com/articles/s41598-025-12969-6)

## Statistical validity of area estimates
- [Olofsson et al., Good practices for estimating area and assessing accuracy of land change (RSE 2014)](https://www.sciencedirect.com/science/article/abs/pii/S0034425714000704)
- [Olofsson et al., Making better use of accuracy data: stratified estimation (RSE 2013)](https://www.sciencedirect.com/science/article/abs/pii/S0034425712004191)
- [R implementation: mapaccuracy::olofsson](https://search.r-project.org/CRAN/refmans/mapaccuracy/html/olofsson.html)

## Imagery sources
- [USGS EROS Archive — NAPP (National Aerial Photography Program)](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-national-aerial-photography-program-napp)
- [USGS EROS Archive — Digital Orthophoto Quadrangles (DOQs)](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-digital-orthophoto-quadrangle-doqs)
- [USGS EROS Archive — NAIP](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-national-agriculture-imagery-program-naip)
- [WAGDA — Washington digital aerial photography holdings](https://wagda.lib.washington.edu/data/type/photography)

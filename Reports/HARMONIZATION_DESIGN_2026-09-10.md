# HARMONIZATION DESIGN — 2026-09-10

**Goal (Kam, 2026-09-10):** "bring all the imageries closer to each other to be able to do
a time series analysis of the tree canopy."

**Status of this document:** a DESIGN, written under CLAUDE.md §3.4c. Every number below
is read from a tracked file and cited to it. Nothing here has been validated by a run of
its own; the two experiments in §3 are pre-registered so that they can be, and the kill
criteria in each were chosen because the record predicts they will FIRE if the mechanism
is wrong.

**Read-only session.** Nothing in the repo or the lake was modified to write this.

---

## 1. What the record already establishes about why surveys disagree

Ranked by how much of the disagreement each mechanism is measured to carry.

### 1.1 It is DETECTION, not delineation — the model finds different trees, not different outlines

On the 137,901 crowns every epoch sees, mean measured cover spans 0.9699 (2015) to
0.9926 (2021) — a 2.3% systematic difference — and 2011s at 38.1 cm effective reads 0.978
against 2024 at 6.8 cm reading 0.9707.
`phase4/qc/detectability_curve.csv` (`recall@epoch=2015;kind=conditional_cover`), digested
at `Scripts/SCIENCE.md:33`.

**Consequence for this design:** harmonization must move *which crowns are detected*. Any
intervention framed as sharpening or scale-matching outlines is aimed at a difference of
2.3%, and is not where the problem lives.

### 1.2 Detectability is NOT ordered by ground resolution

At a 6 m minimum crown diameter, 2011s (38.1 cm effective) recalls 0.973 of bracketed
crowns while 2015 (13.7 cm, nearly 3× finer) recalls 0.915.
`phase4/qc/detectability_curve.csv` (`recall@epoch=2015;kind=cumulative_ge;diam_lo_m=6`),
`Scripts/SCIENCE.md:31`.

**Consequence:** "degrade everything to the coarsest GSD" is not supported by our own
archive. Resolution is a real axis (§1.5) but it does not order the years.

### 1.3 Cross-survey colour differences are DELIVERY RADIOMETRY, not phenology

`experiments/greenness_gradient_correction.yaml` — verdict *"THE GRADIENT IS DELIVERY
RADIOMETRY, NOT PHENOLOGY, AND THE LEAF-OFF IGNORE EXPERIMENT IS DEAD AS PREMISED."* The
flight-window table breaks the seasonal reading (the two lowest-greenness years fall in
June and in deep winter; all three highest in April), and the per-bin GRVI histograms over
canopy are unimodal — a real leaf-off signal would be bimodal, because conifers do not stop
being green. `experiments/leafoff_recall_gradient.yaml` is *"A DIRECTION, NOT A GRADIENT —
and the direction was later re-attributed away from season"* (`Scripts/SCIENCE.md:96-97`).

The magnitude of the delivery difference is measured. On pseudo-invariant hardscape, before
correction, the acquisition-to-reference spine RMS reaches **67.5 DN** (2007s red) and
**47.4 DN** (2000 red); a per-band gain/offset fitted on invariant ground brings those to
13.0 and 5.7 DN. 2006s needs gain 1.606 / offset −117.0 in red alone.
`phase4/qc/radiometry_norm.csv` rows `2007s,R` / `2000,R` / `2006s,R`
(`pre_rms`, `fit_quality`, `gain`, `offset`).

### 1.4 Registration is small, and already separated from the thing it is confused with

Median inter-year offsets against the 2020s anchor are sub-metre for almost every
acquisition (worst median 1.951 m, 2013s); p95 magnitudes run 6–8 m on the oldest years.
`phase4/qc/coregistration.csv`. `experiments/coregistration_2020s_anchor.yaml` —
*"THE ANCHOR CHAIN IS CERTIFIED, AND REGISTRATION IS SEPARABLE FROM THE THING IT IS USUALLY
CONFUSED WITH"* (`Scripts/SCIENCE.md:99`). The local displacement field composes across
epoch pairs (median r 0.5857) but its magnitude sits under the noise of a per-cell median
(composed residual 0.452 m vs a global-constant 0.433 m, beating global in 15 of 56
triples) — **so it is not exploitable** (`Scripts/SCIENCE.md:39`).

**Consequence:** registration is not tonight's lever.

### 1.5 There is a hard PROCESSING-CHAIN FLOOR that no downstream algorithm removes

One flight delivered two ways, scored by one frozen model, agrees at **IoU 0.7376**
(`phase4/qc/sameflight_consistency.csv`, row `grid_px_m=1.0`; `Scripts/SCIENCE.md:17`).
`experiments/sameflight_floor_c3.yaml` — *"THE FLOOR EXISTS AND IT IS LARGE ENOUGH TO
MATTER."*

The same pair, scored at each arm's own deployed cut and aggregated onto one common grid,
differs in recall by **0.0563 / 0.0577 / 0.0571** at 1 / 2 / 4 m support
(`phase4/qc/support_matched_2019_pair.csv`). The gap is flat across support, so it is
**not** a support artifact — it survives the measurement fix that was built to kill it
(`qc/instruments/support_matched_rescore.py` header). This is the cleanest convergence
target in the archive: same date, same ground, same distance to every reference.

### 1.6 Matched cuts fix the SIGN of the trend, not the jitter

Reported canopy fraction tracks the model's recall at r = **0.9089** (exact permutation
p = 0.0018). Matching the operating point moved mean absolute year-to-year step from 3.06 pp
(delivered cuts) to **3.29 pp** (matched) — it did not shrink.
`phase4/qc/sensitivity_sawtooth.csv` (`pearson_r_recall_vs_frac`,
`matched_mean_abs_step_pp`); `Scripts/SCIENCE.md:27-29`.
`experiments/trend8_uniform_rgb.yaml` retracted the delivered-cut series as a trend read.

**This is the whole argument for tonight.** Threshold harmonization is already done and it
is not enough. The remaining jitter is per-survey *detector sensitivity*, and the only way
to remove it is to make the detector respond to the surveys more alike.

### 1.7 The reference is part of the disagreement

Two separate findings. First, support: `experiments/chm_roc_support_confound.yaml` —
*"SUPPORT IS MOST OF IT, AND THE REFERENCE REWARDS BLUR REGARDLESS OF WHICH PRODUCT IS
BLURRED"* (`Scripts/SCIENCE.md:108`). Second, epoch distance:
`experiments/metric_tolerance_c2b.yaml` — *"THE STRICT SCORE WAS MEASURING PIXEL SIZE, NOT
DETECTION"* (`Scripts/SCIENCE.md:93`), and the direct measurement, one frozen 2006s mask
scored twice: recall **0.7278** against `ccap_2016_hires_lc.tif` and **0.6308** against
`ccap_2021_hires_lc.tif` (`phase4/qc/arm_metrics.csv`, curves `3b1fa50cef4d` and
`248fff8a9689`, both `t1_2006s_in16`, both `sample-test`, both `matched_p75`).

**Consequence, and it is the sharpest constraint on tonight's metric:** a 0.097 recall
swing on the same mask from changing only the reference year. "Recall vs C-CAP 2021"
confounds detector sensitivity with 15 years of real canopy change. Driving 2006s recall
toward 2020's *is* laundering under that metric. §3 handles this by making the same-flight
pair the primary convergence read and by scoring every arm against both references.

### 1.8 How large is the disagreement, in the units tonight uses?

`matched_p75` recall vs `ccap_2021_hires_lc.tif`, `eval_scope sample-test` — the
pre-registered basis:

| year | resnet101 base (`backbone_benchmark.csv`) | resnet18 warm-start (`arm_metrics.csv`) |
|---|---|---|
| 2006s | 0.5847 | *not run* |
| 2011s | 0.7253 / 0.7201 / 0.7168 (3 seeds) | 0.7204 / 0.7250 / 0.7273 |
| 2016  | 0.6693 | 0.7428 |
| 2019n | 0.6749 | *not run* |
| 2020  | 0.6402 | 0.7396 |

Seed floor (max pairwise |Δ| among the three 2011s seeds): **0.0085** on resnet101
(`backbone_benchmark.csv`, `NOISE_FLOOR_2011s / spread / matched_p75`), **0.0069** on
resnet18 (`experiments/backbone_sweep.yaml` verdict). Brief says 0.007–0.009: confirmed.

Cross-survey spread, five years, resnet101: **0.1406** — 16× the floor, and dominated by
2006s. On resnet18 only three years exist and their spread is **0.0224** (3.2× the floor).
**The two years that carry the spread — 2006s and 2019n — have never been run on the
encoder recipe search now lives on.** That is the first thing to fix (§3, EXP-H1).

---

## 2. Candidate interventions, ranked by evidence and cost

**A statement that has to come first, because it is the honest answer to Kam's question as
literally posed: there is no engine path tonight to harmonizing the IMAGERY.** Verified in
source, not assumed:

- The training raster is fixed by `native_file` in `YEAR_CATALOG`
  (`pipeline/phase4seg/config.py:368+`), resolved by
  `pipeline/phase4seg/common.py:164 resolve_native_path`. **There is no CLI override** —
  `pipeline/phase4seg/cli.py` has no `--native-file`, `--imagery`, `--norm`, `--radiometry`,
  `--gsd` or `--target-gsd` (full flag list read at `cli.py:125-413`).
- `qc/instruments/radiometry_norm.py` writes a TABLE and its POLICY block explicitly
  **forbids** wiring normalization into "phase4seg tiling or training input"; nothing in the
  pipeline calls it (module header). Overriding that is a Kam decision, not a Claude one.
- `qc/instruments/degrade_synth.py` writes correctly-labelled `synth_{source}_as_{target}`
  rasters — and **nothing can consume them**, because consumption requires either a
  `YEAR_CATALOG` append (that file is PURE-MOVE PROTECTED, and an append re-signatures
  tiling) or the `--native-file` flag that does not exist.
- Photometric augmentation is **hard-coded**, not a flag: `A.RandomBrightnessContrast(0.3,
  0.3, p=0.6)`, `A.HueSaturationValue(15,30,15, p=0.5)`, `A.RandomGamma((70,130), p=0.4)`,
  `A.RandomShadow(p=…)`, `A.RandomFog`, `A.Downscale((0.5,0.75))` at
  `pipeline/phase4seg/core.py:90-103` (and the 4-band twin at `core.py:191-202`). No
  strength or on/off flag reaches them. Note also `core.py:613-656`: the albumentations 2.x
  stream is **UNSEEDED** — `augmentation-seeding` is an open decision
  (`Scripts/SCIENCE.md:137`), so any photometric-augmentation experiment run tonight would
  have an unseeded treatment, which is a second reason not to run one.
- `--tier` is **not** a resolution knob. `TIER_TILE_PARAMS`
  (`pipeline/phase4seg/config.py:628-631`) sets stride / negative rate / test fraction only,
  and `tier_for` (`config.py:606-627`) documents that re-tiering 2016 or 2021s would switch
  them off the citywide label path onto the crown polygons CLAUDE.md §4 records as
  overwritten with accept-all test data. Ruled out as a lever, and ruled out as a mistake.

So tonight tests **model-side surrogates for harmonization**. Imagery-side harmonization is
a code change plus a policy decision. Ranked:

| # | Intervention | Mechanism | What the record predicts | Engine cost | GPU cost |
|---|---|---|---|---|---|
| 1 | **Complete the wb18 baseline (2006s, 2019n)** | Not a treatment — the spread cannot be measured on the working encoder without the two years that carry it (§1.8) | r101 spread 0.1406; r18 may differ, since r18 already beat r101 by +0.074 on 2016 and +0.100 on 2020 | **Existing flags** — byte-identical to `pipeline/queue_wb18_a.yaml` with the year swapped | ~2.5 A100-h (2 arms train+eval+inference+score) |
| 2 | **Shared structure channel, `--hs-source chm2`** ("in16") | A survey-invariant 4th band the model can lean on when a survey's colour is unlike the training survey. It is the same raster for every year, so per-survey radiometry has less to carry | r101 base→in16: 2006s +0.046, 2011s +0.021, 2016 +0.066, 2020 +0.019 → 4-year spread 0.1406 → **0.1153** (`arm_metrics.csv` / `backbone_benchmark.csv`). Prediction: worst years gain most, spread compresses ~0.025 (≈3× floor). **Caveat, load-bearing:** the r101 "3/3 confirmed" lidar-input verdict (`experiments/tier1_science_sample.yaml` verdict) has NOT reproduced on the small encoders — r50 in05−base = +0.0066, r18 in05−base = 0.7509−0.7428 = +0.0081, both ~1× floor — and `experiments/backbone_sweep.yaml` verdict attributes that to `t1_2016_base` (0.6693) being a suspect-low baseline. So the surviving untested prior is 2006s +0.046 and 2011s +0.021, on one encoder | **Existing flag** (`cli.py:198`, `HS_STATS["chm2"]` at `config.py:756`) | ~1.2 A100-h per arm incl. inference+scoring |
| 3 | **Epoch-swap placebo, `--hs-source chm2005` vs `chm2`** | If a *2005* CHM and a *2016* CHM help a 2006 image equally, the channel is a generic structure prior. If the 2016 one wins, the channel is **dating the imagery** — fatal for a time series | r101 on 2006s: in05 +0.023, in16 +0.046. Read naively that says the further-in-time CHM wins, arguing *against* leak — **but the reference is C-CAP 2021, so a 2016 CHM is closer to the reference epoch and that read is confounded (§1.7).** The placebo therefore has to be read together with a direct change-cell count, not alone | **Existing flag** | ~1.2 A100-h |
| 4 | **Same-flight convergence pair (2019s vs 2019n)** | The only zero-circularity convergence read in the archive: same date, same ground, same reference distance; the disagreement is *purely* delivery + sensor | Baseline gap 0.0563 recall at 1 m support, flat to 4 m (§1.5), ≈8× floor. If a treatment is harmonizing delivery, this gap must shrink | **Existing flags** — but 2019s has no sample manifest; `pipeline/builders/build_sample_manifests.py --years 2019s` must run first (CPU, minutes; writes `{lake}/phase4/qc/sample_tiles_2019s.csv`) | ~2.4 A100-h (2 arms) |
| 5 | Per-survey radiometric normalization of training imagery | Remove the measured 47–68 DN delivery offsets (§1.3) at the source | The most direct attack on the largest measured cross-survey difference | **NOT TONIGHT** — forbidden by `radiometry_norm.py`'s POLICY block; needs a `--native-file` flag or a catalog append, plus Kam's decision | n/a |
| 6 | Train on `degrade_synth` products (label-rich year pushed to a poor year's look) | Gives the poor years real labels instead of projected ones | Untested; the tool exists and is policy-clean | **NOT TONIGHT** — same consumption gap as #5 | n/a |
| 7 | Stronger / seeded photometric augmentation | Make the detector invariant to the delivery differences instead of removing them | Untestable as a clean arm tonight: hard-coded (`core.py:90-103`) **and** unseeded (`core.py:651`) | **NOT TONIGHT** — small code change + the open `augmentation-seeding` decision | n/a |
| 8 | `--vi` (6-channel RGB+VI) | Band ratios partially cancel a per-band *gain*; they do not cancel an *offset*, and the fitted offsets here are large (2006s red −117 DN) | Mechanism is half-right at best | **NOT TONIGHT** — `cli.py:189` says the ckpt must match; `sem_best_2020_base18.pt` was verified only at `in_channels` 3 and 4 (`backbone_sweep.yaml` extra), never 6 | n/a |
| 9 | Coregistration correction | §1.4 | Sub-metre medians; the exploitable local field is under its own noise | Not worth an arm | n/a |

---

## 3. The two pre-registered experiments for tonight

Both run **ResNet-18 warm-started from `phase4/models/sem_best_2020_base18.pt`**, on the
33-block science sample (30 test / 2 train / 1 selection, LOSO,
`phase4/qc/science_sample_manifest.csv`), scored at `matched_p75` vs C-CAP 2021,
`eval_scope sample-test`, by the `pipeline/queue_wb18_*.yaml` +
`qc/instruments/score_wb50_loso.py --prefix wb18` pattern.

**Noise floor, pre-registered for both:** **0.0069** recall (wb18 three-seed 2011s spread,
`experiments/backbone_sweep.yaml` verdict). Conservative alternative 0.0085 (r101,
`backbone_benchmark.csv`). Any per-arm delta inside the floor is **UNDETERMINED**, never
"no difference" (CLAUDE.md §3.5). A **spread** is a max−min of five draws and is noisier
than a single delta: a spread change must exceed **2× floor = 0.014** to count.

**Two-step queue shape, as the record requires.** `steps: [labels, tile, train, evaluate]`
first (labels+tile on FREE CPU runtimes, the proven split, commit 7ef2f11), then a second
queue with `steps: [inference]` carrying `--infer-aoi
/content/drive/MyDrive/treedata/phase4/qc/science_sample_blocks.gpkg` and **no**
`--sample-manifest` (the Tier-1 ac0e79e shape, restated in `backbone_sweep.yaml`
`decision_rule` "SECOND QUEUE SHAPE"), then the scoring pass. **2020 runs last and
unbounded** — the Tier-1 conveyor died at 1200 s on the 2020 arm
(`score_wb50_loso.py` header).

---

### EXP-H1 — Cross-survey spread baseline on the working encoder

**Question.** What *is* the cross-survey spread on resnet18? It cannot currently be stated:
the two years that carry the r101 spread (2006s at 0.5847, 2019n at 0.6749) have never been
run on resnet18. Every harmonization claim tonight is a claim about a number that does not
yet exist.

**Arms.** Two NEW; three reused unchanged from the landed wb18 set (`wb18_2011s_base`
0.7204, `wb18_2016_base` 0.7428, `wb18_2020_base` 0.7396). Single seed — the seed floor is
already measured on 2011s and does not need re-measuring per year.

    - id: harmonize_wb18_2006s_base
      year: 2006s
      tag: wb18_2006s_base
      extra: [--force-citywide, --encoder, resnet18, --no-hillshade,
              --ckpt, /content/drive/MyDrive/treedata/phase4/models/sem_best_2020_base18.pt,
              --sample-manifest, /content/drive/MyDrive/treedata/phase4/qc/sample_tiles_2006s.csv]
      steps: [labels, tile, train, evaluate]

    - id: harmonize_wb18_2019n_base
      year: 2019n
      tag: wb18_2019n_base
      extra: [--force-citywide, --encoder, resnet18, --no-hillshade,
              --ckpt, /content/drive/MyDrive/treedata/phase4/models/sem_best_2020_base18.pt,
              --sample-manifest, /content/drive/MyDrive/treedata/phase4/qc/sample_tiles_2019n.csv]
      steps: [labels, tile, train, evaluate]

Then the `[inference]` twin of each with `--infer-aoi …/science_sample_blocks.gpkg` and no
`--sample-manifest`, then:

    py -3.12 qc/phase4_qc_indep.py --year <label> --ref ccap_2021_hires_lc.tif \
        --prob <BASE>/phase4/masks/edmonds_canopy_prob_<label>_<tag>.tif \
        --aoi phase4/qc/science_sample_manifest.csv --aoi-roles test
    # and the SAME command with --ref ccap_2016_hires_lc.tif   (era-matched second read)
    py -3.12 qc/instruments/harvest_arm_metrics.py

**Primary metric.** `matched_p75` recall per year, and
**SPREAD = max − min over {2006s, 2011s, 2016, 2019n, 2020}**.

**Secondary, and it is what keeps the spread honest.** Every arm scored against BOTH
`ccap_2021_hires_lc.tif` and `ccap_2016_hires_lc.tif`, the `era_matched_rescore` pattern.
The 2006s in16 mask already shows a 0.097 recall swing from the reference alone (§1.7).
Report the 2021-referenced spread and the 2016-referenced spread side by side; the part of
the spread that moves with the reference is **reference-epoch distance, not detector
sensitivity**, and must never be counted as harmonizable.

**Decision rule, pre-registered.**
- **K1 (kills the workstream, and can fire):** if the five-year spread on resnet18 is
  **≤ 0.014** (2× floor), there is no cross-survey detection disagreement to harmonize at
  this sample and this encoder, and EXP-H2's premise is dead. The r101 prior says 0.1406,
  but the r18 three-year spread is only 0.0224 and r18 gained +0.074 / +0.100 over r101 on
  exactly the two years that were worst — so this is not a formality.
- **K2 (kills the metric, not the workstream):** if ≥ 60% of the spread is attributable to
  reference epoch — i.e. the 2016-referenced spread is ≤ 0.4× the 2021-referenced spread —
  then `matched_p75` recall vs C-CAP 2021 is not a convergence metric, and EXP-H2 must be
  read on the same-flight gap alone. (The 0.4 is an arbitrary but pre-registered cut; it
  is fixed here before any number exists precisely so it cannot be chosen afterwards.)
- Otherwise: the spread is the pre-registered baseline against which EXP-H2 is read, and
  the two years' recalls are recorded in `phase4/qc/arm_metrics.csv` as the wb18 record.

**Time-series consequence if it works.** This is the measurement that converts "the years
disagree" into a number with a floor beside it. Canopy fraction tracks recall at r = 0.9089
(§1.6), so a spread of *s* in recall is roughly a *s*-scaled band of un-real variation in
the reported annual canopy fraction — which is what today's 3.29 pp matched-cut sawtooth is
made of.

**Cost.** 2 arms. Train+evaluate 20–35 min each on r18 (`backbone_sweep.yaml` verdict:
14–31 min), inference+score 15–40 min. Labels+tile (5–15 / 7–53 min) on FREE CPU runtimes.
**≈ 2.5 A100-hours.**

---

### EXP-H2 — Shared structure channel as a survey-invariance surrogate, with an epoch-leak placebo

**Hypothesis.** Per-survey detection differences are driven by per-survey *appearance*
(delivery radiometry, §1.3; the processing-chain floor, §1.5). Giving every year the SAME
survey-invariant 4th band (`--hs-source chm2`) gives the detector a cue that does not vary
by survey, so the cross-survey spread should compress — most on the years whose appearance
is furthest from the training survey.

**What would change our mind, stated before running:** if the channel compresses the spread
by *importing 2016 canopy* rather than by supplying generic structure, it manufactures
false temporal stability, which is the precise failure this project exists to avoid. K1 and
K2 below are built to catch that, and the record predicts K1 will fire.

**Arms (7 new).** Identical to the EXP-H1 shape with `--no-hillshade` replaced by
`--hs-source chm2`; everything else held.

    treatment (5): tag wb18_<year>_in16, for year in {2006s, 2011s, 2016, 2019n, 2020}
      extra: [--force-citywide, --encoder, resnet18, --hs-source, chm2,
              --ckpt, /content/drive/MyDrive/treedata/phase4/models/sem_best_2020_base18.pt,
              --sample-manifest, /content/drive/MyDrive/treedata/phase4/qc/sample_tiles_<year>.csv]
      steps: [labels, tile, train, evaluate]      # then the [inference] twin, as EXP-H1

    placebo (1): tag wb18_2006s_in05        — as above but  --hs-source chm2005
      (the 2016 twin already exists: wb18_2016_in05 = 0.7509 vs wb18_2016_base = 0.7428)

    same-flight pair (2): tag wb18_2019s_base  (--no-hillshade, --tier, coarse)
                          tag wb18_2019s_in16  (--hs-source, chm2, --tier, coarse)
      PRE-STEP, must land first (CPU, minutes, writes to the lake):
        py -3.12 pipeline/builders/build_sample_manifests.py --years 2019s
      (SAMPLE_YEARS in that builder does not include 2019s; --years accepts any label.)

      WHY --tier coarse, and it is not optional. MEASURED THIS SESSION:
      tier_for(entry_for("2019s")) = "medium" (30.5 cm); 2019n = "coarse". Medium
      and coarse differ in tiling stride AND in early-stop metric — TIER_EARLYSTOP
      = {"medium": "val_bce", "coarse": "val_iou_bt"} (config.py:651). Left alone
      the "same flight" pair would differ in RECIPE as well as in delivery, and the
      gap would not be attributable. --tier is cli.py:129.
      CONSEQUENCE FOR THE PRIOR: sameflight_consistency.csv names its masks
      2019s_pilot_e2_MEDIUM and 2019n_pilot_e2_COARSE, so the 0.0563 gap and the
      0.7376 IoU are THEMSELVES tier-confounded. They are cited as priors only.
      K3's comparator is wb18_2019s_base vs wb18_2019n_base, both measured tonight
      on one recipe.

**Primary metric — and it is a spread, not a recall, because the goal is convergence.**

1. **ACROSS-SURVEY SPREAD** of `matched_p75` recall over the five sample years:
   in16 spread minus base spread (base spread from EXP-H1).
2. **SAME-FLIGHT GAP**, |recall(2019s) − recall(2019n)| at the matched cut: in16 vs base.
   Baseline **0.0563** at 1 m support, flat to 4 m
   (`phase4/qc/support_matched_2019_pair.csv`) — cited as a PRIOR only; it comes from
   r101 pilot arms on mismatched tiers (see the arm block above). Tonight's comparator
   is `wb18_2019s_base` vs `wb18_2019n_base`, both `--tier coarse`. This is the
   zero-circularity read: same date, same ground, same reference distance, so nothing
   here can be satisfied by laundering change.

Per-arm recalls are secondary and every one is reported with the 0.0069 floor beside it.

**Decision rule, pre-registered. PROMOTE only if (P) holds AND K1–K3 all pass.**

- **(P) CONVERGENCE:** the five-year spread shrinks by **≥ 0.014** (2× floor). Prior from
  r101: 0.1406 → 0.1153, a shrink of 0.025.
- **K1 — EPOCH LEAK, AS AN INTERACTION (this criterion has power; the record predicts it
  fires).** Stated naively as "in16 > in05 on 2006s", this criterion is broken: chm2005 and
  chm2 differ in lidar density and product as well as in epoch — `experiments/old_chm_defect.yaml`,
  *"THE SIGN WAS BACKWARDS AND THE DEFECT IS LARGE"* — so a uniform in16 advantage on every
  year is a CHM-QUALITY effect, not a leak. The leak signature is the INTERACTION: the 2016
  CHM should help a 2006 image *more than* it helps a 2016 image only if it is carrying 2016
  canopy.

      K1 = [(in16 − in05) @ 2006s]  −  [(in16 − in05) @ 2016]   >   floor   →  LEAK

  Both 2016 terms are already on disk or in the arm list (`wb18_2016_in05` = 0.7509,
  `wb18_2016_base` = 0.7428, `wb18_2016_in16` is arm 3), so the interaction costs nothing
  extra. r101 prior: 2006s in05 +0.023 / in16 +0.046 → +0.023; 2016 in05 +0.075 / in16
  +0.066 → −0.009; interaction **+0.032 = 4.6× floor — on the r101 prior this FIRES**, and
  a pure quality effect (equal on both years) would not. A leak verdict **disqualifies in16
  for time series regardless of (P)**. Scored against BOTH references, since C-CAP 2021 is
  itself nearer the 2016 CHM epoch (§1.7): an interaction that appears only against C-CAP
  2021 and vanishes against C-CAP 2016 is reference-epoch confounding, reported UNDETERMINED
  rather than as a pass.
- **K2 — CHANGE LAUNDERING (direct, non-circular). REQUIRES A SMALL SCRIPT THAT DOES NOT
  EXIST — write it before the arms land or K2 cannot fire.** `phase4/qc/certified_change_cells.csv`
  is a four-column COUNT table (`quantity,cells,km2,definition`), not a per-cell raster, so
  it cannot be intersected with anything. The gain population is defined inside its writer,
  `qc/instruments/certified_flat_scoring.py:122` — `gain = both & (h05 < 2.0) & (h16 >= 5.0)`
  on the chm2005 2 m grid, `both` = dual-covered (8,866,539 cells / 35.466 km², the
  `dual_covered` row). The new instrument reuses that file's `warp_max` (line 48) to
  rebuild the gain mask, then compares, **over the sample-test blocks only** (inference is
  AOI-limited to `science_sample_blocks.gpkg` — there is no citywide rate to compare
  against): canopy-call rate of `wb18_2006s_in16` inside gain cells minus that of
  `wb18_2006s_base`, against the same difference over all sample-test cells. If the
  gain-cell rise exceeds the all-cell rise beyond the floor, the channel is painting 2016
  trees onto 2006 imagery → **kill**, whatever (P) says. The precedent is in the record: on
  the *adder*
  path, "2016-epoch additions on 2006 imagery poison the labels" (add16 −0.503,
  `experiments/tier1_science_sample.yaml` verdict) — that is the adder, not the input band,
  but it is why the input band must be checked and not assumed clean.
- **K3 — MECHANISM.** If the same-flight 2019s/2019n gap does not shrink beyond the floor,
  the treatment is **not** harmonizing delivery differences. A cross-year spread that
  compresses while the same-flight gap holds is evidence the compression came from
  reference-epoch effects, not from harmonization → report the cross-year result as
  UNINTERPRETABLE for this goal.
  **If `sample_tiles_2019s.csv` does not land in time, drop these two arms — and then K3 is
  UNMEASURED and the mechanism claim is UNDETERMINED for the night.** It is not permitted
  to promote on (P) alone.
- **K4 — PRE-REGISTERED NON-EVENT (so it is not read after the fact).** The 2016 in16−base
  delta is *expected* to land inside the floor: r18 already read in05−base = +0.0081 and
  r50 read +0.0066, and `backbone_sweep.yaml`'s verdict attributes the r101's +0.075 to a
  suspect-low `t1_2016_base`. A null on 2016 is neither a win nor a failure.

**Time-series consequence if it works.** Reported canopy fraction tracks recall at
r = 0.9089 (§1.6). Today's matched-cut series carries a 3.29 pp mean absolute annual step
that is detector sensitivity, not canopy. Compressing the cross-survey recall spread by
0.025 removes roughly the same order of spurious step from
`phase4/qc/trend8_harmonized_fractions.csv` (which currently swings 0.3262 → 0.3755 →
0.3282 across 2015/2021/2024). It does **not** license a published number: the correction is
one-sided (the model misses real trees, it does not invent them —
`Scripts/SCIENCE.md:27`), and the only human-measured trend statement remains Panel A's
−2.21 ± 1.10 pp.

**Cost.** 7 arms × ~1.2 A100-h ≈ **8.4 A100-hours**, labels+tile offloaded to free CPU
runtimes. On the 2-A100 cap with one runtime free now and one at +3.5 h, that is tight but
fits if 2020 is scheduled last and unbounded. **If it does not fit, cut in this order:**
2020 in16 (its base is the least survey-atypical year and its inference is the slow one),
then 2011s in16. Never cut the 2006s arms — 2006s is where the spread lives — and never
cut the placebo, because an in16 promotion without K1 is exactly the kind of unvalidated
design CLAUDE.md §3.4c exists to stop.

**QUEUE-SPLIT RULE, and it is operational, not stylistic: ALL ARMS OF ONE YEAR GO ON ONE
RUNTIME.** `backbone_sweep.yaml` `extra.cross_vm_eval_report_clobber` records the defect —
two A100 runtimes rewrite the shared `phase4/eval/semantic_eval_report.csv` on every
`evaluate` behind an async write cache, and on 2026-09-09 one arm's rows landed in neither
the live report nor the archive. Tonight this bites three times: **2006s** has three arms
(base from EXP-H1, in16, in05), **2019s** has two, **2016** has two. Keep each year's arms
in one queue file. Nothing scientific is lost if it happens anyway — every `evaluate`'s
metrics are also in its step log — but the registry and the ledger will read the wrong arm.
The cut order above respects this: it drops whole years, never one arm of a pair.

---

## 4. What NOT to run tonight, and why

- **Leaf-off IGNORE / any seasonal treatment. DEAD AS PREMISED, not deprioritised.**
  `experiments/greenness_gradient_correction.yaml` verdict, in those words. The greenness
  gradient the seasonal-IGNORE experiment was promoted on is delivery radiometry: the flight
  windows contradict the calendar story, the per-bin canopy GRVI histograms are unimodal
  where a real leaf-off signal must be bimodal (conifers do not stop being green), and Kam's
  own independent observation the same day was that no leaf-off variation was visible.
  Re-running it would spend GPU to re-measure a radiometric effect under a seasonal label.
- **Shadow masks / shadow-specific handling.** Two reasons. `shadow_fp_fn_2016` is in the
  "documented but UNSIGNED" list (`Scripts/SCIENCE.md:124`) — there is no signed measured
  shadow effect to build on. And `A.RandomShadow(shadow_roi=(0,0,1,1),
  num_shadows_limit=(1,3))` is **already in the training augmentation unconditionally**
  (`pipeline/phase4seg/core.py:96`, and `core.py:197` for the 4-band path), so a shadow-mask
  arm would be layered on an uncontrolled shadow augmentation whose RNG is unseeded
  (`core.py:651`). The delta would not be attributable.
- **Normalizing real training imagery with `radiometry_norm`.** Forbidden by that module's
  own POLICY block, and there is no flag to do it. It is a good idea for a later night; it
  needs a `--native-file` override (or a `YEAR_CATALOG` append) plus Kam's ruling on the
  policy. Do not smuggle it in.
- **`--vi`.** `cli.py:189` requires the ckpt to match; `sem_best_2020_base18.pt` was verified
  at `in_channels` 3 and 4 only. An unverified 6-channel conv1 inflation is a way to waste an
  A100 on a load error, and band ratios do not cancel the large fitted *offsets* anyway.
- **Photometric-augmentation strength arms.** Hard-coded and unseeded (§2). `augmentation-
  seeding` is an open decision on the board (`Scripts/SCIENCE.md:137`); it should be closed
  before any arm turns on a knob in that stack.
- **Re-tiering years to a common `--tier`.** `--tier` sets stride / negative rate / test
  fraction, not ground support (`config.py:628-631`), and moving 2016 or 2021s off "coarse"
  would switch them onto the crown polygons overwritten with accept-all test data
  (`config.py:606-627`, CLAUDE.md §4). It is not a harmonization lever and it is an active
  hazard.
- **Global GSD degradation to the coarsest year.** Detectability is not ordered by GSD in
  this archive (§1.2) and epochs already agree to 2.3% on delineation (§1.1). There is no
  measured basis for it.

---

## 5. The healer's 12-epoch stack, tonight

`heal_2022` is the one arm of `experiments/heal_infill_2017_2023.yaml` never started
(`extra.tabled`); the campaign currently stands at **eleven** epochs (8 trend8 +
heal_2017 / heal_2020 / heal_2023), cached by `qc/instruments/heal_stack_build.py` at its
default `D:\edmonds-pipeline\heal_stack_2m.npz`. **No verdict exists**: the decision rule's
tests have never been run on the dense stack — only a 10-epoch scratch trial that exposed
and fixed two instrument unit defects (802a0c8).

**Order of operations when heal_2022 lands (~4 h from now):**

1. **Verify the arm before it enters the stack.** `heal_2017` came out
   WEAK_CALIBRATION (maxprob < 0.75, probabilities compressed around 0.5; held-out F1 0.763
   at 0.490 vs 0.377 at 0.500 — `extra.arm_notes`). Read `heal_2022`'s step log from
   `{BASE}/phase4/logs/` (CLAUDE.md §3.11 — do not ask for pasted stdout) and record its
   best-F1 threshold and held-out IoU/F1 before anything downstream. A second
   weak-calibration layer changes how every gap read below is interpreted.
2. **Rebuild the stack:** `py -3.12 qc/instruments/heal_stack_build.py` → the 12-epoch
   `.npz`. Check parity against the published trend8 cache on the eight shared epochs, as
   the 11-epoch build did.
3. **`qc/instruments/temporal_heal.py`** on the new stack → `phase4/qc/temporal_heal.csv`.
   The arithmetic check first: **BLIND brackets inside 2016–2024 must fall to zero**
   (decision_rule (c)). This is a check on the run, not a finding — if it does not hold, the
   stack is wrong and everything after it is void.
4. **`qc/instruments/heal_vs_gold.py`** against the frozen `phase4/qc/panel_a_gold.csv`
   (1,170 no-change / 42 loss / 2 gain) → laundered, terminal-censored, and impossible-triple
   counts.
5. **`qc/instruments/heal_closing_baseline.py`** — the closing-operator baseline the fill has
   to beat; a fill that a morphological closing reproduces is not a temporal operator.
6. **`qc/instruments/heal_gap_spectrum.py`** → `phase4/qc/heal_gap_spectrum.csv`, the
   per-gap-bucket read that established the amendment below.
7. **`qc/instruments/heal_fill_audit_sample.py`** — ~300 fills sampled from the healer
   output with a null-change control, human-read, k/300 with its exact upper bound. **This
   is the operative laundering test**, and it needs a human, so draw the sample tonight and
   leave it for Kam.

**What counts, read from the decision rule as amended (2026-09-08):**

- The **PRIMARY KILL as originally written — "launder zero of the 42 verified losses" —
  CANNOT FIRE**, and the amendment says so in the file: a verified loss has a terminal
  absence running to the end of the series, so the epoch after any interior epoch inside it
  also reads absent and a both-sides fill can never touch it. `laundered_at_risk` is 0 in
  every gap bucket on the 8-epoch stack. **0 of 42 is a criterion with no power, not a
  bound**, and it must not be reported as a pass. (Per CLAUDE.md §3.4c: a gate that has
  never fired is not known to work.)
- **PROMOTE requires all three:** (a) laundered = 0 **and** terminal-censored = 0 against the
  frozen gold; (b) impossible-triple removal at verified no-change points **no worse than
  99 of 124** measured on 8 epochs; (c) BLIND brackets inside 2016–2024 = 0.
- Report every recall figure with the gold's measured **± 7.3 pp** (42 positives). The gold
  is a development set forever; a promote licenses the enriched confirmatory draw, **not** a
  published number.
- **Recipe discipline is not negotiable:** the existing `of_2017` / `of_2020` / `of_2022`
  masks are on disk with matched cuts and must NOT be substituted. Matched cuts are measured
  to collapse *delivery* differences to ~0.15 pp; nothing in the repo says they collapse
  *recipe* differences.
- **What a promote does not license:** healed masks feeding the annual canopy fraction.
  Endpoints cannot be healed, so the bias never cancels. Healed output feeds trajectories,
  validity intervals and change maps only (`extra.what_this_does_not_do`).

**Interaction with §3, flagged deliberately:** EXP-H2's K1/K2 and the healer's fill audit
are the same question in two places — *is a temporally-mismatched prior importing canopy
from the epoch it came from?* If K1 fires on the 2016 CHM channel, that is independent
evidence bearing on how much to trust a temporal fill, and it should be carried into the
healer's write-up rather than kept in the recipe lane.

---

*Written 2026-09-10, read-only session. Every claim above carries its file pointer. The two
experiments are pre-registered; neither has been run, and no number in §3 that describes an
outcome is anything but a prior read from a landed arm.*

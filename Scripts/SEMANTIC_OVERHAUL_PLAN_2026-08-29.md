# Semantic canopy overhaul — plan of record

**SUPERSEDED 2026-09-02 by `TIER1_SCIENCE_SAMPLE_PLAN_2026-09-02.md`.** This plan's
architecture direction was executed (EPOCH 3, policy C, the hard-year pilot, the
recipe audit); the full-36 campaign it pointed toward was deliberately deferred by
Kam in favor of the Tier-1 science sample. Kept for the record — read the active
plan for current direction.

**Owner:** Kam. **Scope:** SEMANTIC canopy mask per acquisition, all 36. Instance is
deferred, not cancelled (see `CLAUDE.md` Project Purpose).
**Status:** plan only. Nothing here has been built or run. No GPU has been spent.

This plan exists because Kam proposed a four-part overhaul on 2026-08-29. Rather than
implement it, the day was spent establishing what the repo already has, what the
proposal's premises actually measure, and what the held literature supports. Three of
the four parts survive largely intact. One does not, and the reason is geometric rather
than a matter of taste.

---

## 0. Corrections that came out of checking, recorded first

Each of these was believed by someone at the start of the day and is now measured.

| believed | measured | source |
|---|---|---|
| 18 acquisitions, 15 calendar years | **36 acquisitions, 20 calendar years** | `config.py:YEAR_CATALOG` |
| NIR years: 2016, 2019n, 2021s, 2022n | **10 NIR years**; `2022n` has not existed since `5a12da5` relabelled it `2023n` | same |
| lidar anchors ~44% of the city | **83.5% of imaged pixels**; the missing 16.5% is 99.8% negative-NDVI open water, hiding at most **+0.02 pp** canopy | `phase4/qc/chm_gap_2016.txt` |
| "drop NIR" is work to do | **already deployed** — `common.read_rgb_window` reads bands `[1,2,3]`; the per-year models never see NIR | `common.py:1096`, `config.py:681` |
| LP-FT is work to do | **already the method of record**, patience already 15 | `core.py` phase A/B, `config.py:171` |

`CLAUDE.md`'s Key Data Facts carried the first two for an unknown period and were
corrected in `ad5c3fb`; they are now marked DERIVED with the command that regenerates
them.

---

## 1. What is already built — do not rebuild

| proposal element | status | evidence |
|---|---|---|
| RGB-only, NIR dropped | **BUILT** — `--no-hillshade`; 4-band orthos tile cleanly as RGB | `tiling.py:1262`, `common.py:1096` |
| Two-phase LP-FT | **BUILT** — Phase A freezes encoder + pins BN, Phase B unfreezes | `core.py`, `config.py:181` |
| Early stopping, patience 15 | **BUILT** — already exactly 15 | `config.py:171` |
| Pure Dice loss | **BUILT** — `--bce-weight 0` | `cli.py` |
| Phase-A learning rate | **BUILT** — `--lr-phase-a` | `cli.py:183` |
| Three-state labels (0/1/255 IGNORE) | **BUILT**, and it is the vehicle for every label idea below | CLAUDE.md rule 6 |
| U-Net skips already bypass the bottleneck | **BUILT** — decoder consumes the full feature list, so an ASPP on `feats[-1]` leaves skips untouched | verified against installed smp 0.5.0 |
| Stratified accuracy design (Olofsson/Stehman) | **BUILT** — real stratum weights, Monte-Carlo achieved CI | `qc/instruments/phase4_accuracy_sample.py --step design` |
| Canopy area with GSD carried | **BUILT** | `qc/instruments/phase4_sector_series.py` |
| 36-year scale-up | **BUILT** — YAML per year, no hardcoded year list | `phase4_train_queue.py` |

**Genuinely absent:** `--lr-phase-b` (Phase B is hardcoded `5e-6`), a boundary loss term,
and an ASPP module.

---

## 2. Item 1 — the architecture. DO NOT BUILD AS SPECIFIED.

### 2.1 Two of the four dilation rates do not fit the feature map

Measured directly on the live model (`resnet101`, `TILE_SIZE=512`, `decoder_channels`
5 stages → output stride 32):

```
bottleneck feature map: 16 x 16
r=1   span  3 cells  FITS
r=6   span 13 cells  FITS (barely)
r=12  span 25 cells  EXCEEDS THE MAP
r=18  span 37 cells  EXCEEDS THE MAP
```

At r=18 no position ever has a valid three-tap footprint; those branches are
zero-padding-dominated and degenerate toward 1x1 convolutions carrying extra parameters.
**Only r <= 7 fits at all.** This depends only on output stride and tile size, so
**swapping to ResNet-50 or EfficientNet does not rescue it** — smp keeps stride 32.

### 2.2 It repairs a deficit this network does not have

DeepLab dilates its *backbone* to hold the feature map at stride 8-16 instead of 32. That
preserves detail and **shrinks the receptive field**; ASPP exists to put the reach back.
Our U-Net never made that trade. A resnet101 at stride 32 has a theoretical receptive
field well over 1000 px against a 512 px tile — **the bottleneck already sees the whole
tile.** ASPP would add reach where reach is saturated.

### 2.3 The one matching configuration in the literature measures zero-to-negative

RTAS-Net (Wang, Li & Ma 2026, PLoS One) is the only held paper using `{1,6,12,18}` at a
bottleneck with an isolated number: +0.72 / +0.36 / +0.55 mIoU. Every one is measured on
a network **already carrying two global-context modules** (MobileViT + Swin). Its own
baseline row shows ASPP added to a plain U-Net giving **+0.00 mIoU (Potsdam) and −0.60
(Vaihingen)**. The same Vaihingen baseline is reported as 91.14 in one table and 90.54 in
another — a 0.60 pp instability exceeding the 0.36 pp gain it is cited for.

### 2.4 A fixed rate set cannot serve a 20x GSD span

Ground footprint = `(1 + 2r) x stride x GSD`. At stride 32:

| | r=1 | r=6 | r=12 | r=18 |
|---|---|---|---|---|
| 5 cm | 4.8 m | 20.8 m | 40 m | 59.2 m |
| 100 cm | 96 m | 416 m | 800 m | **1184 m** |

Crowns are 5-15 m. Soto Vega et al., the corpus's one practitioner data point, cut
DeepLab's rates ~6x to match a 64x64 patch, stating explicitly that rates track
feature-map scale. **Rates would have to be per resolution tier** — an axis no held paper
varies.

### 2.5 It is aimed at a failure we have not measured having

The measured failure is **crown perimeters and small crowns** — high-frequency and local
(41.8% of misses in 16.3% of the area; height-channel benefit concentrated at 0-25 m²
crowns). A bottleneck context module is a low-frequency, global instrument.

### 2.6 What to do instead

1. **Build the boundary loss, not the ASPP.** Under semantic-only scope, boundary
   sharpness matters because **canopy area is an integral over the mask edge** — a blobby
   border systematically inflates the deliverable. This targets the measured failure.
   It must be IGNORE-aware (255 excluded) exactly as `_masked_bce/_masked_dice` are, or
   it will silently train on IGNORE pixels. Touches `_seg_loss`, its call sites, and
   `cli.py`'s `--loss-mode` choices.
2. **If an ASPP arm is built anyway, pre-register it as null-expected**, with rates
   recalculated for a 16x16 map (r <= 7), not as an improvement being banked on.
3. **Keep resnet101.** See §3.

---

## 3. The encoder decision — a separate, much larger bet

**Scenario A (ASPP only, resnet101 retained):** the 2020 warm start survives; every
`encoder.*`, `decoder.*`, `segmentation_head.*` key still loads. One named edit —
`allow_missing=("aspp.",)`. **Days. Existing per-year numbers stay in-family.**

**Scenario B (encoder swap):** Phase 3 must be re-earned — 6 trainings, wall-clock
**unmeasured** (`run_registry.csv` carries `step_minutes` on 20 of 88 rows). The published
LOSO IoU **0.7299** / AUROC **0.9396** stop describing the model. **172 live rows across
23 years** lose like-for-like status; re-scoring is **35-104 A100-h**. 161 checkpoints /
160 GB become a different family. `champion_arms.csv` (17 rows, 16 justified as "only
live arm") needs re-adjudicating.

Neither costs re-tiling — `ENCODER` and `DECODER_CHANNELS` are absent from
`_tile_signature`.

**Recommendation: Scenario A.** Revisit B only with evidence the backbone is the limit.

### 3.1 The franken-load, and why it is now safe

Measured on smp 0.5.0: a **resnet101 checkpoint loaded into a resnet50 U-Net matches
380/380 target keys** — encoder 318/318, decoder+head 62/62, **zero missing**. Before
`50006ce` that load was 100% silent and would have trained a scrambled model reporting
plausible numbers. It is caught only by the 306 *unexpected* keys.

All four load paths now refuse a misfit (`50006ce`, `51b2aa4`), including
`step_inference`, which writes the deliverable rasters. `phase3_semantic_dev.py:863`
remains unguarded and belongs with whatever re-runs Phase 3.

---

## 4. Item 2 — labels. WELL SUPPORTED. Build it.

Soto Vega et al. 2023 is the closest structural precedent: two signals agree → confident
label, disagree → **void, excluded from loss and sample selection**. Identical in shape to
the proposed CHM gate and to the 0/1/255 discipline already running. Their network **beat
the label generator that supervised it** (F1 64.3 vs 55.0 Pará; 55.0 vs 42.0 Rondônia) —
the best-isolated justification in the corpus for training on projected labels at all.

**We are on stronger footing than the paper:** their confirming signal was derived from
the same images being classified. A CHM is an independent physical measurement.

**Coverage is not the objection it was thought to be:** 83.5% of imaged pixels carry CHM.

**Open, and to be checked before building:** the literal filter
`canopy-in-2020 AND CHM>3m → confident canopy` was reported by the readiness audit as a
**measured no-op** — the pixels 2020 calls canopy are overwhelmingly already tall. The
informative half is the *disagreement* cell. Read the existing measurement first.

---

## 5. Item 3 — training protocol. Mostly built. Decide the numbers.

| | proposal | repo | delta |
|---|---|---|---|
| Phase A LR | 1e-3 | 5e-5 | **20x** |
| Phase B LR | 1e-5 | 5e-6 (hardcoded) | 2x, and **needs `--lr-phase-b`** |
| Patience | 15 | 15 | none |
| Degradation aug | blur, downsample to 100 cm, radiometric noise | blur + `Downscale(0.5-0.75)` | **far below 20x**; no additive sensor noise, no JPEG artefacts |

**A caution that must travel with the augmentation plan:** Pearse et al. measured that
**pooling imagery across a phenological contrast did not help** — the pooled model landed
*between* the two single-epoch models and gained false negatives. Training across 36
acquisitions should not be assumed to average domain differences away.

**Raise `STEP_TIMEOUT_MIN["train"]` before the first launch** (`phase4_train_queue.py:122`,
currently 300). The proposal specifies patience with no epoch cap; a contended uncapped
run will exceed 300 min and be killed as a hang.

---

## 6. Item 4 — validation. Supported, but two tiers need rework.

### (a) Golden micro-set — SURVIVES; merge into existing machinery
Van den Broeck et al. 2022 faced the same no-ground-truth problem and answered with
labour: 115 hand-digitised patches, ~2.2% of the study area, **~3 person-days per
acquisition**. Copy: same plot footprints in every acquisition; Latin-hypercube plus
purposive plots for hard classes (small crowns, deciduous marsh, the sparse suburban
region at .332 precision). **Do not build a parallel instrument** —
`phase4_accuracy_sample.py --step design` already implements the stratified estimator.
With n<=10, report the between-tile spread; the spread is the result.

**The strongest single finding in the whole review:** Van den Broeck got **three rank
inversions out of three** between a modern-year validation set and a historical test set
— including U-Net best on validation, **worst** on the historical test. We score per-year
models against 2020-derived references. By this evidence that cannot rank recipes for old
acquisitions. **The micro-set is not a report line; it is the only instrument that can
choose which recipe to ship for 2002.**

### (b) 500 old-growth points — TRIPWIRE ONLY
Lidar local maxima select the largest, highest-contrast, **evergreen** crowns — the one
stratum that stays near ceiling at 100 cm and in February, i.e. it cannot exhibit the
deciduous failure we most suspect. Torres measured recall's steep dependence on object
size: 62.2% overall, **21.9%** below the minimum mapping unit. Fixes: add a matched
deciduous cohort of comparable crown size and track the **conifer-minus-deciduous recall
gap by month**; report per size stratum; and size a tolerance buffer against measured
co-registration offsets (2024 CoE displaced **1.28 m**; 2013 King vs Snoh **2.76 m, still
uninvestigated**) or this tier measures orthorectification history.

### (c) Time-series smoothness — CONTRADICTED AS SCOPED
Three fixes, all using instruments already in the repo:

1. **Plot against `effective_cm`, not nominal GSD.** `qc/imagery_pixelsize_and_date.csv`
   already carries measured effective resolution and it **reorders the archive** — 2005 is
   nominal 20.05 cm but resolves at **80.7 cm**, coarser than every 30 cm product. Pearse's
   two epochs had *identical* nominal GSD and moved 4.7 points.
2. **Plot the full predicted-fraction-vs-threshold curve per acquisition**, not one area
   number. Area at 0.5 cannot separate "saw less canopy" from "less confident about the
   same canopy" — and litwatch already measured area swinging **17.3 pp** across
   thresholds against a 2.6 pp policy gap. Needs no labels, and the outliers identify
   themselves, which is also how to pick the "worst acquisitions" for (a) on evidence.
3. **Disentangle season from resolution** — see §7.

---

## 7. The seasonal confound — new, and it cuts across items 2 and 4

The archive is **not seasonally comparable**, and every label comes from one season.

```
Feb-Mar : 2015 King (Feb 15-Mar 8), 2012 (Mar 23 + Apr 7), 2024 (Mar 31-)
Apr-May : 2019, 2021, 2023 King; 2009; 2017; 2022; and THE 2020 ANCHOR (Apr 13-Jul 13)
Jun-Jul : 2000, 2002, 2007, 2013, 2005, 2021n
Aug     : 2016, 2015n/s, 2017n/s, 2018m/s
Oct     : 2019n, 2019s, 2023n
```

PNW: Feb-Mar leaf-off, Jun-Aug leaf-on, Oct senescence. Projecting April-July labels onto
February imagery labels bare deciduous branches as canopy — a **systematic,
species-correlated** error, categorically unlike the scattered growth/removal error the
project has treated as the label problem, and landing on the model's known weak spot.

**This is partly a RE-discovery and must be cited as such.** Search 55 (ID 194) already
established the King leaf-off / NAIP leaf-on specs, and CHATLOG result (17) attributed the
2015 anomaly to leaf-off then **withdrew it the same day** because the cross-year GRVI
ranking it rested on is destroyed by sensor colour cast (2019 King .1146 vs 2019 NAIP
.8919, same day, same ground). What is new is month-level dates plus a *within-sensor*
instrument:

| frame | date | nominal cm | ExG-AUROC |
|---|---|---|---|
| 2013 King | Jun 2-6 | 10.03 | .7368 |
| **2015 King** | **Feb 15-Mar 8** | 10.03 | **.6415** |
| 2015s Snoh | Aug 7 | 30.48 | .7867 |
| 2015n NAIP | Aug 7 | 100.0 | .8416 |

Same program, same GSD, and 2013 is *further* from the 2020 labels so real change should
hurt it more. Within calendar 2015 real change is exactly zero, yet the coarse August
frames beat the fine February one by .145 and .201.

**PRODES, mapping Amazon deforestation annually since 1988, never compares across seasons
— dry season to dry season, forever.** No seasonal correction exists in that literature
because the acquisition window is locked. Any argument citing deforestation work as
precedent for projected labels must state that the precedent controls season by
construction and we cannot.

**The usable inversion:** February leaf-off is the most *discriminative* imagery held for
separating conifer from deciduous. The best deciduous stratifier is currently treated as
a contaminant.

### 7.1 How to disentangle season from resolution (dates verified)

**Step 1 — freeze season, vary GSD.** Same-flight pairs: **2019s (30.48) vs 2019n (60.0),
both 2019-10-11, recorded as the same Hexagon flight**; 2015n/2015s (both 2015-08-07);
2017n/2017s (2017-08-15/21). Exclude 2021s — its window is 140 days. Run the deployed
model on each rung over the intersected footprint.

**Step 2 — apply to same-year cross-season pairs:** 2015 Feb/Aug, 2017 May/Aug, 2019
Apr/Oct, 2023 Apr/Oct. Real change within a calendar year is zero; subtract the calibrated
resolution term and the residual is season.

**Step 3 — what cannot be done.** Every dated *coarse* acquisition is June-October; the
only dated leaf-off frames are fine or medium. **The leaf-off x coarse cell is empty and
cannot be filled from real imagery.** The only route is synthetic degradation, which
touches the parked synthetic-imagery decision and needs Kam's sign-off.

---

## 8. Sequence

**Gates — nothing that writes a comparable number runs before its gate.**

1. **Architecture provenance** — stamp the encoder name into the checkpoint payload
   (15 keys today, zero architecture keys) before any non-resnet101 or ASPP run.
2. **`--lr-phase-b`** and the raised train timeout before the first protocol launch.
3. **Plot against `effective_cm`** before any GSD-alignment claim.

**Then, in order:** boundary loss → label-gate measurement (§4 open question) → the
season/resolution ladder (§7.1, cheap, inference-only) → micro-set design → protocol runs.

**Parallel, blocked by nothing:** deciduous-fraction measurement; the threshold-curve
plot; the contact sheet of one crown across all 36 acquisitions.

---

## 9. Open decisions for Kam

1. **Scenario A or B** (§3). Recommendation: A.
2. **Phase-A LR 1e-3 vs 5e-5** (§5) — a 20x jump, one flag, real consequences.
3. **Synthetic degradation** for the empty leaf-off x coarse cell (§7.1 step 3).
4. **Seeds per arm.** The proposal specifies none. n=1 cannot resolve anything near the
   ~.0047 AUROC rerun band.
5. **Interpreter hours** for the micro-set — ~3 person-days per acquisition.

## 10. What would make this plan wrong

- If the deciduous fraction of Edmonds canopy is small, §7 is a bounded correction rather
  than a first-order problem. **Unmeasured — cheap to settle from C-CAP.**
- If the ASPP's value is in *training dynamics* rather than receptive field, §2's geometric
  argument does not reach it. No held paper tests that.
- If the 2020 labels are the binding constraint, no architecture change converts into a
  better score, and §2/§3 are both beside the point.
- The GPU estimates disagree (~105 VM-h vs 46.8 A100-h as an explicit floor) and measure
  different things. **Do not budget against either until reconciled.**

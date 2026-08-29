# The cheap prior: are the corrected height rasters better canopy discriminators?

**2026-08-29 · LIDAR lane · local CPU, no GPU, no training.**
Tool: `Scripts/qc/phase4_chm_standalone_roc.py`. Reference:
`ccap_2016_hires_lc_snohfull.tif`, canopy definition `forest_wetland`.
Every raster compared is scored on the INTERSECTION of the rasters in that run, so
coverage is never charged as accuracy. Compare numbers only *within* a run.

---

## READ THIS FIRST — the raw ranking inverts if you skim it

The bare standalone table says the OLD, inflated raster wins:
`chm` AUROC **0.9059** vs the 2016 rebuild `chm2` **0.8429**, a gap of +0.0630 with a
95% CI of [+0.0597, +0.0664] and 100% sign stability. Skimmed, that reads as *the
corrected raster is worse*.

**It is not a property of the rasters.** It is reproducible from the old raster's
FORM alone. `lidar_snoh_chm.tif` is USGS 3DEP HAG at ~2 m GSD bilinear-upsampled onto
a 0.67 m grid (`pipeline/fetch_build_chm.py:17,132`), which `build_chm2_2016.py` [2b]
measured as behaving like a **neighbourhood maximum**, +4.1 to +5.4 m nearly
everywhere. The reference is a *generalized* 1 m product that labels forest patches
wall to wall, gaps included. Apply the old product's own two-step mechanism —
dilate, then blur — to the sharp new raster and the entire gap closes:

| arm | AUROC | PR-AUC | best-F1 height | F1 |
|---|---|---|---|---|
| `chm` (old, inflated) | 0.9059 | 0.8721 | 9.8 m | 0.7921 |
| `chm2` (2016 rebuild, sharp) | 0.8429 | 0.8194 | 6.4 m | 0.7147 |
| `max1(chm2)` — dilate 3 m | 0.8843 | 0.8555 | 7.8 m | 0.7669 |
| `max2(chm2)` — dilate 5 m | 0.8949 | 0.8608 | 9.4 m | 0.7798 |
| `smooth1(max1(chm2))` — dilate 3 m + blur 3 m | 0.8964 | 0.8675 | 7.8 m | 0.7780 |
| **`smooth2(max2(chm2))` — dilate 5 m + blur 5 m** | **0.9073** | **0.8754** | 9.4 m | **0.7941** |

`chm` vs `smooth2(max2(chm2))`: dAUROC **-0.0014**, 95% CI [-0.0023, -0.0005]
(1024 px blocks; [-0.0020, -0.0007] at 512 px), sign stable 100%.

**Form — spatial support plus smoothness, matched to a generalized 1 m reference —
accounts for the whole of the old raster's standalone lead.** `chm2` carries at least
as much canopy information; it is being scored at a granularity the reference cannot
reward.

That last row is the best of four form-variants tried, so treat the sign of the
-0.0014 as post-hoc. The supported claim is *form explains the gap*, **not** "chm2 is
better than chm".

---

## Power, stated before the verdicts

Paired spatial block bootstrap over 512x512 m blocks (**201 non-empty blocks** on the
chm/chm2 footprint; 174 on the three-raster footprint), 400 replicates, every
replicate scoring every arm on the same resampled blocks. Effective sample size is
the block count, not the 42.0 M pixels — neighbouring pixels are the same tree.

Resolving power (half-width of the 95% interval on the paired gap) is **±0.0033** for
`chm` vs `chm2` and ±0.0005–0.0053 across all pairs in all runs. At 1024x1024 m blocks (57 blocks)
it widens to ±0.0051 for the same pair — intervals grow ~1.5x with block size and no
verdict changes. **Every gap reported here exceeds its own interval; nothing in this
exercise was measured at a resolution finer than the test can see.** Where a gap had
not cleared its interval the script would print `UNDETERMINED` — its verdict
vocabulary has no "no difference" in it.

This interval covers uncertainty from *where we looked*, under one reference. It is
not retrain noise and not reference error.

---

## The +4.43 m inflation is invisible to this kind of test — by construction

AUROC and PR-AUC are invariant under any strictly monotone transform of the score,
and subtracting a constant is monotone. So the constant component of the ground
inflation **cannot** move AUROC. Measured, `chm-4.43m` scores 0.8981 vs `chm` 0.9059
(dAUROC +0.0078): the small loss is entirely the DN-1 floor clamp turning everything
below the shift into a tie (DN-1 mass rises 8.73% → 34.70%), and ties only ever lower
AUROC. Its best-F1 **F1 is identical to four decimals (0.7921)**; only the height at
which it occurs moves, 9.8 m → 5.4 m — i.e. exactly the offset, and nothing else.

This is the same fact the audit stated in the training domain: a per-source
standardisation that differs by the inflation makes `z_chm = 0.869 * z_chm2`, a scalar
gain a zero-initialised conv-1 channel absorbs for free. **Level is not the treatment.
Shape is.** Any future A/B on this axis is testing form at training resolution and
nothing else.

**The most actionable number here is for a different consumer.** The best operating
height differs by 3.4 m between the two rasters (9.8 m vs 6.4 m). The training channel
is standardised and never sees it, but anything that thresholds the *old* chm at an
absolute height — stable-label mining, lidar-background gating, the NDVI+CHM
reference — inherits the +4–5 m bias directly.

---

## Confounds tested and excluded

**Grid resolution.** Scoring at 0.5 m (chm2's native cell, 168 M reference px) instead
of 1 m: `chm` 0.9053, `chm2` 0.8453, gap +0.0600 vs +0.0630 at 1 m. Nearest
downsampling to 1 m is not what costs chm2 anything.

**Registration.** A dilation test cannot separate *the reference is blobbier* from
*the reference is offset* — a max filter hides both. Sampling each raster from a
translated window:

*Run `registration` (chm2 alone, so its own footprint):*

| shift (m) | 0 | +2 E | -2 E | +2 N | -2 N |
|---|---|---|---|---|---|
| `chm2` AUROC | 0.8448 | 0.8231 | **0.8512** | 0.8425 | 0.8275 |

*Run `registration_pair` (both rasters, common footprint — a separate run, do not
compare across the two tables):*

| shift (m) | 0 | -2 E | -4 E |
|---|---|---|---|
| `chm2` AUROC | 0.8427 | **0.8494** | 0.8360 |
| `chm` AUROC | **0.9058** | 0.9020 | 0.8866 |

`chm2` peaks about 2 m west of nominal (+0.0064 in the first run, +0.0067 in the
second); `chm` peaks at zero and only loses 0.0038 at -2 E, but its blur makes it a
poor probe of position. Direct
raster-to-raster cross-correlation over a 3000x3000 m window (no reference involved)
puts the two height fields' best alignment at **-1 m easting / +1 m northing**
(Pearson r 0.87970 at -1 E vs 0.87407 at 0 and 0.86069 at +1 E), with
**mean(chm - chm2) = +5.07 m** — an independent confirmation of the documented
inflation. So a real sub-2 m offset exists between the two products, in the direction
C-CAP prefers, worth ~0.006 AUROC — **an order of magnitude below the granularity
effect and not what ranks these rasters.** Flagged as a chm2 QA item, not a result.

**Not excluded — the one open confound.** Whether NOAA C-CAP's production chain used
3DEP-derived height would make the *old* raster partly circular with the reference.
Nothing in this repo states C-CAP's inputs. It does not change the conclusion — the
dilate-and-blur reconstruction explains the gap without invoking circularity — but a
non-lidar reference (hand-drawn crowns, photo-interp points) would settle it.

---

## The three-raster comparison, and the 2005 product

On the triple intersection (33,933,949 px, 54.90% of scorable, 174 blocks):

| arm | AUROC | PR-AUC | best-F1 height | F1 | own valid / grid |
|---|---|---|---|---|---|
| `chm` | 0.9019 | 0.8696 | 9.4 m | 0.7893 | 68.94% |
| `chm2` | 0.8385 | 0.8168 | 6.0 m | 0.7095 | 66.39% |
| `chm2005` | 0.7979 | 0.7640 | 6.4 m | 0.6694 | 55.12% |
| `max2(chm2)` | 0.8900 | 0.8569 | 9.0 m | 0.7761 | 66.39% |
| `max1(chm2005)` | 0.8311 | 0.7897 | 7.6 m | 0.7142 | 55.12% |
| `max(chm2,chm2005)` | 0.8440 | 0.8091 | 7.0 m | 0.7274 | 54.91% |

`chm2` vs `chm2005`: +0.0406, CI [+0.0373, +0.0435] — **epoch-handicapped**. Scoring
2005 heights against a 2016 reference charges 11 years of real growth and removal to
the raster as classification error, so 0.7979 is a **lower bound** on chm2005's
discrimination in its own epoch, which is the epoch it would be used in. Reaching
within 0.041 of a raster four times finer, while carrying that handicap, is a pass.
Its DN-1 mass (1.37%) and its response to a 3 m dilation (+0.0331) behave exactly like
chm2's, which is what a correctly built product should do.

**Fusion buys discrimination nothing.** `max(chm2,chm2005)` vs `chm2`: dAUROC +0.0055
[+0.0036, +0.0074] but dPR-AUC **-0.0077** [-0.0121, -0.0035] — a wash, and the
PR-AUC loss is exactly what a cross-epoch maximum should cost (2005 trees felled by
2016 become false positives). Fusion's only real value is coverage union, which this
intersection-scored design deliberately cannot credit.

---

## Answering "the best lidar product we can get out of the data we have"

1. **Per-epoch assignment, not a merge.** `CHM_BY_YEAR` (chm2005 for early years,
   chm2 default) is the right architecture and this measurement supports it. A fused
   max over epochs measurably costs precision. Use fusion only to fill coverage holes,
   never as the height value where both epochs exist.
2. **Do not "fix" the old raster and do not resurrect it.** Its standalone advantage
   is dilate-and-blur against a coarse reference, and a subtractive de-biasing changes
   no ranking metric at all.
3. **The one concrete product lead is the registration offset** — chm2 sits ~1–2 m
   east of both C-CAP and the old chm. Worth a look at the build's grid origin
   (`build_chm2_2016.py`, 0.5 m grid from `from_origin`) before chm2 becomes the
   default height source everywhere.
4. **The reference is now the binding constraint, not the lidar.** Three products,
   all scored against a generalized 1 m map that rewards blur; the sharpest product
   scores worst. Any further height-product work is measuring the reference unless a
   sharper reference (hand crowns, photo-interp) comes first.

---

## What remains UNDETERMINED

This test measures **marginal** discrimination — each raster on its own. It does not
measure **conditional** value: the height raster enters training as a 4th channel
beside RGB, and a weaker marginal discriminator can still carry information RGB lacks.

So the cheap prior returns: **no information deficit in chm2** — the screen's stated
purpose ("if a corrected raster is not a better discriminator on its own, no training
arm will find it") does not fire, and the training question is not closed by it.
Whether the sharpness of chm2 helps *training* is still **UNDETERMINED**: this
evaluation structurally cannot see it (a 1 m generalized reference rewards the blur),
and a conv absorbs dilation and blur about as easily as it absorbs a scalar gain, so
the form difference is itself learnable. The A100 question stays open — but it is now
bounded: anyone rerunning that A/B is testing form at training resolution, and needs
enough power to resolve an effect that this reference cannot even score.

---

## Artifacts

| file | run |
|---|---|
| `chm_standalone_roc_chm_vs_chm2.md` / `_arms.csv` / `_pairs.csv` | chm, chm2, chm-4.43 m — the offset test |
| `chm_standalone_roc_mechanism.md` (+csv) | dilate / dilate+blur reconstruction — the headline |
| `chm_standalone_roc_support_confound.md` (+csv) | first dilation test, incl. max1(chm) |
| `chm_standalone_roc_all_three.md` (+csv) | chm, chm2, chm2005, fusion |
| `chm_standalone_roc_registration.md`, `..._registration_pair.md` (+csv) | spatial-shift tests |
| `chm_standalone_roc_res_sensitivity_50cm.md` (+csv) | 0.5 m grid |
| `chm_standalone_roc_blocksize_1024.md` (+csv) | block-size sensitivity |

Seven runs, well under an hour of local CPU in total. The alternative was ~6 A100-hours.

The cross-correlation in the registration section was a one-off scratch computation,
not a committed script; its numbers are transcribed above in full.

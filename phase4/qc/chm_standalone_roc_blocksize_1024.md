# Height rasters as STANDALONE canopy classifiers — `blocksize_1024`

The cheap prior. No training, no GPU. Every height raster is already a 254-level canopy score under the shared encoding `DN = 1 + round(clip(h,0,50.6)/0.2)`, `0 = nodata`, so sweeping the cut over every DN enumerates every *canopy is taller than h metres* classifier there is.

Reference: `ccap_2016_hires_lc_snohfull.tif` (epoch 2016) · canopy definition `forest_wetland` · scored on the INTERSECTION of every raster below, so coverage is never charged as accuracy.

## Inputs

| arm | source | CRS | native res (m) | epoch |
|---|---|---|---|---|
| `chm` | `lidar_snoh_chm.tif` | EPSG:3857 | 1.00 x 1.00 | 2016 |
| `chm2` | `lidar_chm2_2016_50cm.tif` | EPSG:26910 | 0.50 x 0.50 | 2016 |
| `max2(chm2)` | derived: `chm2` under a 5x5 px (5 m) neighbourhood MAXIMUM — the support/dilation confound test | — | — | — |
| `smooth2(max2(chm2))` | derived: `max2(chm2)` under a 5x5 px (5 m) box MEAN — the second half of the old product's dilate-and-blur mechanism | — | — | — |

A `maxN(...)` arm exists to test ONE hypothesis: the old product is ~2 m HAG bilinear-upsampled and measurably behaves as a neighbourhood maximum (`build_chm2_2016.py` [2b]), while the reference labels forest patches wall to wall. If a SHARP raster catches up once it is dilated to the same support, the gap between them was granularity, not information — and granularity matched to a 1 m reference is not evidence about a channel the engine consumes at 10-15 cm. The filter is truncated at I/O strip boundaries (2048 rows), which touches ~0.20% of rows.

## Footprint and coverage

Analysis grid: **7055 x 9813 @ 1 m** in EPSG:26910 = 69.2 Mpx, the intersection of every raster's own extent with the reference's, snapped to the reference lattice.

Reference-scorable on that grid: **69,198,289 px**. Common valid (all arms x scorable): **41,975,356 px** (60.66% of scorable).

| arm | own valid / grid | own valid & ref-scorable | share of the common footprint it alone would add | DN 1 (h = 0 m) inside common |
|---|---|---|---|---|
| `chm` | 71.49% | 49,480,525 | 15.17% dropped by the intersection | 8.73% |
| `chm2` | 60.82% | 42,103,555 | 0.30% dropped by the intersection | 28.27% |
| `max2(chm2)` | 60.82% | 42,103,555 | 0.30% dropped by the intersection | 7.56% |
| `smooth2(max2(chm2))` | 60.82% | 42,103,555 | 0.30% dropped by the intersection | 3.70% |

The DN-1 column is also an encoding check: DN 1 is *flat ground*, not nodata. An arm reporting ~0% there would mean its zero-height mass had been swallowed by the nodata code and every metre label below would be wrong.

## Standalone discrimination

Reference canopy px: 16,785,766 · non-canopy: 25,189,590 · prevalence 39.99%

| arm | AUROC | 95% CI (own) | PR-AUC | best-F1 height | F1 | best-Youden height | J |
|---|---|---|---|---|---|---|---|
| `chm` | 0.9059 | [0.8976, 0.9135] | 0.8721 | 9.8 m | 0.7921 | 9.8 m | 0.6536 |
| `chm2` | 0.8429 | [0.8303, 0.8551] | 0.8194 | 6.4 m | 0.7147 | 6.8 m | 0.5402 |
| `max2(chm2)` | 0.8949 | [0.8853, 0.9038] | 0.8608 | 9.4 m | 0.7798 | 9.4 m | 0.6331 |
| `smooth2(max2(chm2))` | 0.9073 | [0.8981, 0.9155] | 0.8754 | 9.4 m | 0.7941 | 9.4 m | 0.6570 |

## Performance by height threshold — where does each raster discriminate?

Recall / precision / F1 of the rule *canopy iff height >= h*.

| h (m) | `chm` R/P/F1 | `chm2` R/P/F1 | `max2(chm2)` R/P/F1 | `smooth2(max2(chm2))` R/P/F1 |
|---|---|---|---|---|
| 0.0 | 1.000/0.400/0.571 | 1.000/0.400/0.571 | 1.000/0.400/0.571 | 1.000/0.400/0.571 |
| 1.0 | 0.999/0.456/0.626 | 0.850/0.592/0.698 | 0.994/0.474/0.642 | 0.999/0.449/0.619 |
| 2.0 | 0.995/0.486/0.653 | 0.812/0.617/0.701 | 0.987/0.505/0.668 | 0.996/0.481/0.649 |
| 3.0 | 0.985/0.512/0.674 | 0.770/0.642/0.700 | 0.969/0.529/0.685 | 0.985/0.514/0.676 |
| 4.0 | 0.964/0.552/0.702 | 0.725/0.693/0.709 | 0.941/0.566/0.707 | 0.963/0.558/0.706 |
| 5.0 | 0.936/0.598/0.729 | 0.689/0.737/0.712 | 0.910/0.607/0.728 | 0.931/0.608/0.736 |
| 6.0 | 0.905/0.644/0.753 | 0.654/0.787/0.714 | 0.877/0.652/0.748 | 0.897/0.659/0.760 |
| 8.0 | 0.843/0.738/0.787 | 0.596/0.866/0.706 | 0.815/0.741/0.776 | 0.830/0.754/0.790 |
| 10.0 | 0.788/0.796/0.792 | 0.548/0.907/0.683 | 0.763/0.795/0.779 | 0.770/0.818/0.793 |
| 12.0 | 0.734/0.851/0.788 | 0.503/0.932/0.654 | 0.713/0.849/0.775 | 0.714/0.862/0.781 |
| 15.0 | 0.661/0.886/0.757 | 0.438/0.947/0.599 | 0.643/0.881/0.743 | 0.638/0.896/0.745 |
| 20.0 | 0.533/0.920/0.675 | 0.328/0.961/0.489 | 0.518/0.914/0.661 | 0.508/0.929/0.657 |

## POWER OF THIS TEST — read before any verdict below

Paired spatial block bootstrap: **57 non-empty blocks** of 1024 x 1024 px (1024 m x 1024 m) · 400 replicates · every replicate scores every arm on the SAME resampled blocks, so the shared ground cancels and the interval is on the DIFFERENCE.

Effective sample size is the BLOCK count, not the pixel count — neighbouring pixels are the same tree. `resolving power` below is the half-width of the 95% interval on the paired gap: **a difference smaller than that number is not measurable by this evaluation and is reported UNDETERMINED, not as absence of an effect.**

| pair | observed dAUROC | resolving power (+-) | measurable? |
|---|---|---|---|
| `chm` vs `chm2` | +0.0630 | 0.0051 | yes |
| `chm` vs `max2(chm2)` | +0.0110 | 0.0014 | yes |
| `chm` vs `smooth2(max2(chm2))` | -0.0014 | 0.0009 | yes |
| `chm2` vs `max2(chm2)` | -0.0520 | 0.0041 | yes |
| `chm2` vs `smooth2(max2(chm2))` | -0.0644 | 0.0047 | yes |
| `max2(chm2)` vs `smooth2(max2(chm2))` | -0.0124 | 0.0009 | yes |

## Verdicts

| pair | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | verdict |
|---|---|---|---|---|---|---|
| `chm` vs `chm2` | +0.0630 | [+0.0577, +0.0679] | 100.0% | +0.0527 | [+0.0450, +0.0601] | `chm` **BETTER** than `chm2` |
| `chm` vs `max2(chm2)` | +0.0110 | [+0.0097, +0.0125] | 100.0% | +0.0113 | [+0.0090, +0.0140] | `chm` **BETTER** than `max2(chm2)` |
| `chm` vs `smooth2(max2(chm2))` | -0.0014 | [-0.0023, -0.0005] | 100.0% | -0.0033 | [-0.0046, -0.0018] | `chm` **WORSE** than `smooth2(max2(chm2))` |
| `chm2` vs `max2(chm2)` | -0.0520 | [-0.0556, -0.0474] | 100.0% | -0.0414 | [-0.0469, -0.0356] | `chm2` **WORSE** than `max2(chm2)` |
| `chm2` vs `smooth2(max2(chm2))` | -0.0644 | [-0.0686, -0.0593] | 100.0% | -0.0560 | [-0.0628, -0.0482] | `chm2` **WORSE** than `smooth2(max2(chm2))` |
| `max2(chm2)` vs `smooth2(max2(chm2))` | -0.0124 | [-0.0133, -0.0116] | 100.0% | -0.0146 | [-0.0167, -0.0126] | `max2(chm2)` **WORSE** than `smooth2(max2(chm2))` |

`UNDETERMINED` means the gap is inside this test's own resolving power. It is **not** a null: this evaluation could not tell the two apart, which is a statement about the evidence, not about the rasters.

## What this test licenses

* It measures MARGINAL discrimination — how well each raster separates canopy from non-canopy **on its own**. An arm that wins here is strictly more informative about canopy, and that is a green light.
* It does **not** measure CONDITIONAL value. The height raster enters training as a 4th channel beside RGB; a weaker marginal discriminator can still carry information RGB lacks. A gap this test cannot resolve therefore does not license the claim that training cannot benefit.
* AUROC and PR-AUC are invariant under any strictly monotone transform of the score, and subtracting a constant is monotone. **The constant component of a ground-height inflation cannot move AUROC by construction** — it moves only the height at which the best operating point sits. Any offset arm above therefore tests the machinery, and the surviving old-vs-new gap is RANK-ORDER difference: real discrimination, not level.
* The reference is C-CAP: a 1 m classified product with its own errors, not hand truth. It cannot resolve crowns below its own cell, so every raster here is scored at C-CAP's information limit.


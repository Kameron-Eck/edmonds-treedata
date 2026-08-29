# Height rasters as STANDALONE canopy classifiers — `all_three`

The cheap prior. No training, no GPU. Every height raster is already a 254-level canopy score under the shared encoding `DN = 1 + round(clip(h,0,50.6)/0.2)`, `0 = nodata`, so sweeping the cut over every DN enumerates every *canopy is taller than h metres* classifier there is.

Reference: `ccap_2016_hires_lc_snohfull.tif` (epoch 2016) · canopy definition `forest_wetland` · scored on the INTERSECTION of every raster below, so coverage is never charged as accuracy.

## Inputs

| arm | source | CRS | native res (m) | epoch |
|---|---|---|---|---|
| `chm` | `lidar_snoh_chm.tif` | EPSG:3857 | 1.00 x 1.00 | 2016 |
| `chm2` | `lidar_chm2_2016_50cm.tif` | EPSG:26910 | 0.50 x 0.50 | 2016 |
| `chm2005` | `lidar_chm2005_2m.tif` | EPSG:3740 | 2.00 x 2.00 | 2005 |
| `max2(chm2)` | derived: `chm2` under a 5x5 px (5 m) neighbourhood MAXIMUM — the support/dilation confound test | — | — | — |
| `max1(chm2005)` | derived: `chm2005` under a 3x3 px (3 m) neighbourhood MAXIMUM — the support/dilation confound test | — | — | — |
| `max(chm2,chm2005)` | derived: per-pixel max(`chm2`, `chm2005`) | — | — | — |

A `maxN(...)` arm exists to test ONE hypothesis: the old product is ~2 m HAG bilinear-upsampled and measurably behaves as a neighbourhood maximum (`build_chm2_2016.py` [2b]), while the reference labels forest patches wall to wall. If a SHARP raster catches up once it is dilated to the same support, the gap between them was granularity, not information — and granularity matched to a 1 m reference is not evidence about a channel the engine consumes at 10-15 cm. The filter is truncated at I/O strip boundaries (2048 rows), which touches ~0.20% of rows.

## Footprint and coverage

Analysis grid: **6302 x 9813 @ 1 m** in EPSG:26910 = 61.8 Mpx, the intersection of every raster's own extent with the reference's, snapped to the reference lattice.

Reference-scorable on that grid: **61,812,619 px**. Common valid (all arms x scorable): **33,933,949 px** (54.90% of scorable).

| arm | own valid / grid | own valid & ref-scorable | share of the common footprint it alone would add | DN 1 (h = 0 m) inside common |
|---|---|---|---|---|
| `chm` | 68.94% | 42,623,443 | 20.39% dropped by the intersection | 8.19% |
| `chm2` | 66.39% | 41,058,477 | 17.35% dropped by the intersection | 27.25% |
| `chm2005` | 55.12% | 34,067,959 | 0.39% dropped by the intersection | 1.37% |
| `max2(chm2)` | 66.39% | 41,058,477 | 17.35% dropped by the intersection | 6.89% |
| `max1(chm2005)` | 55.12% | 34,067,959 | 0.39% dropped by the intersection | 0.16% |
| `max(chm2,chm2005)` | 54.91% | 33,956,096 | 0.07% dropped by the intersection | 1.02% |

The DN-1 column is also an encoding check: DN 1 is *flat ground*, not nodata. An arm reporting ~0% there would mean its zero-height mass had been swallowed by the nodata code and every metre label below would be wrong.

## Standalone discrimination

Reference canopy px: 13,835,923 · non-canopy: 20,098,026 · prevalence 40.77%

| arm | AUROC | 95% CI (own) | PR-AUC | best-F1 height | F1 | best-Youden height | J |
|---|---|---|---|---|---|---|---|
| `chm` | 0.9019 | [0.8963, 0.9073] | 0.8696 | 9.4 m | 0.7893 | 9.8 m | 0.6442 |
| `chm2` | 0.8385 | [0.8304, 0.8461] | 0.8168 | 6.0 m | 0.7095 | 6.8 m | 0.5294 |
| `chm2005` | 0.7979 | [0.7883, 0.8077] | 0.7640 | 6.4 m | 0.6694 | 7.6 m | 0.4695 |
| `max2(chm2)` | 0.8900 | [0.8836, 0.8959] | 0.8569 | 9.0 m | 0.7761 | 9.4 m | 0.6219 |
| `max1(chm2005)` | 0.8311 | [0.8219, 0.8399] | 0.7897 | 7.6 m | 0.7142 | 8.2 m | 0.5266 |
| `max(chm2,chm2005)` | 0.8440 | [0.8353, 0.8523] | 0.8091 | 7.0 m | 0.7274 | 7.8 m | 0.5484 |

## Performance by height threshold — where does each raster discriminate?

Recall / precision / F1 of the rule *canopy iff height >= h*.

| h (m) | `chm` R/P/F1 | `chm2` R/P/F1 | `chm2005` R/P/F1 | `max2(chm2)` R/P/F1 | `max1(chm2005)` R/P/F1 | `max(chm2,chm2005)` R/P/F1 |
|---|---|---|---|---|---|---|
| 0.0 | 1.000/0.408/0.579 | 1.000/0.408/0.579 | 1.000/0.408/0.579 | 1.000/0.408/0.579 | 1.000/0.408/0.579 | 1.000/0.408/0.579 |
| 1.0 | 0.999/0.462/0.632 | 0.849/0.597/0.701 | 0.859/0.542/0.665 | 0.995/0.480/0.648 | 0.948/0.503/0.657 | 0.928/0.533/0.677 |
| 2.0 | 0.995/0.491/0.657 | 0.810/0.621/0.703 | 0.805/0.568/0.666 | 0.987/0.510/0.673 | 0.915/0.532/0.673 | 0.895/0.564/0.692 |
| 3.0 | 0.985/0.517/0.678 | 0.766/0.646/0.701 | 0.752/0.591/0.662 | 0.969/0.534/0.689 | 0.872/0.558/0.680 | 0.856/0.590/0.698 |
| 4.0 | 0.963/0.556/0.705 | 0.719/0.696/0.707 | 0.699/0.635/0.666 | 0.939/0.571/0.710 | 0.822/0.596/0.691 | 0.809/0.633/0.710 |
| 5.0 | 0.933/0.602/0.732 | 0.681/0.738/0.709 | 0.660/0.676/0.668 | 0.906/0.610/0.730 | 0.779/0.637/0.701 | 0.770/0.673/0.718 |
| 6.0 | 0.901/0.648/0.754 | 0.645/0.789/0.709 | 0.624/0.721/0.669 | 0.871/0.655/0.748 | 0.740/0.678/0.708 | 0.732/0.716/0.724 |
| 8.0 | 0.836/0.742/0.786 | 0.585/0.868/0.699 | 0.568/0.797/0.664 | 0.807/0.744/0.774 | 0.676/0.757/0.714 | 0.668/0.793/0.725 |
| 10.0 | 0.779/0.799/0.789 | 0.537/0.907/0.674 | 0.525/0.838/0.646 | 0.753/0.797/0.774 | 0.627/0.801/0.704 | 0.618/0.835/0.710 |
| 12.0 | 0.724/0.853/0.783 | 0.492/0.931/0.643 | 0.486/0.859/0.620 | 0.701/0.850/0.768 | 0.584/0.827/0.684 | 0.571/0.862/0.687 |
| 15.0 | 0.650/0.887/0.750 | 0.426/0.946/0.587 | 0.426/0.877/0.573 | 0.631/0.881/0.735 | 0.518/0.849/0.644 | 0.502/0.883/0.640 |
| 20.0 | 0.520/0.921/0.664 | 0.315/0.960/0.474 | 0.324/0.902/0.476 | 0.504/0.914/0.650 | 0.405/0.879/0.554 | 0.382/0.908/0.538 |

## POWER OF THIS TEST — read before any verdict below

Paired spatial block bootstrap: **174 non-empty blocks** of 512 x 512 px (512 m x 512 m) · 400 replicates · every replicate scores every arm on the SAME resampled blocks, so the shared ground cancels and the interval is on the DIFFERENCE.

Effective sample size is the BLOCK count, not the pixel count — neighbouring pixels are the same tree. `resolving power` below is the half-width of the 95% interval on the paired gap: **a difference smaller than that number is not measurable by this evaluation and is reported UNDETERMINED, not as absence of an effect.**

| pair | observed dAUROC | resolving power (+-) | measurable? |
|---|---|---|---|
| `chm` vs `chm2` | +0.0634 | 0.0035 | yes |
| `chm` vs `chm2005` | +0.1039 | 0.0053 | yes |
| `chm` vs `max2(chm2)` | +0.0119 | 0.0010 | yes |
| `chm` vs `max1(chm2005)` | +0.0708 | 0.0041 | yes |
| `chm` vs `max(chm2,chm2005)` | +0.0579 | 0.0036 | yes |
| `chm2` vs `chm2005` | +0.0406 | 0.0031 | yes |
| `chm2` vs `max2(chm2)` | -0.0515 | 0.0027 | yes |
| `chm2` vs `max1(chm2005)` | +0.0074 | 0.0030 | yes |
| `chm2` vs `max(chm2,chm2005)` | -0.0055 | 0.0019 | yes |
| `chm2005` vs `max2(chm2)` | -0.0921 | 0.0047 | yes |
| `chm2005` vs `max1(chm2005)` | -0.0331 | 0.0015 | yes |
| `chm2005` vs `max(chm2,chm2005)` | -0.0460 | 0.0023 | yes |
| `max2(chm2)` vs `max1(chm2005)` | +0.0589 | 0.0035 | yes |
| `max2(chm2)` vs `max(chm2,chm2005)` | +0.0461 | 0.0028 | yes |
| `max1(chm2005)` vs `max(chm2,chm2005)` | -0.0129 | 0.0016 | yes |

## Verdicts

| pair | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | verdict |
|---|---|---|---|---|---|---|
| `chm` vs `chm2` | +0.0634 | [+0.0599, +0.0669] | 100.0% | +0.0528 | [+0.0473, +0.0582] | `chm` **BETTER** than `chm2` |
| `chm` vs `chm2005` | +0.1039 | [+0.0987, +0.1093] | 100.0% | +0.1056 | [+0.0948, +0.1157] | `chm` **BETTER** than `chm2005` · epoch-handicapped |
| `chm` vs `max2(chm2)` | +0.0119 | [+0.0109, +0.0128] | 100.0% | +0.0128 | [+0.0110, +0.0145] | `chm` **BETTER** than `max2(chm2)` |
| `chm` vs `max1(chm2005)` | +0.0708 | [+0.0666, +0.0748] | 100.0% | +0.0799 | [+0.0706, +0.0891] | `chm` **BETTER** than `max1(chm2005)` |
| `chm` vs `max(chm2,chm2005)` | +0.0579 | [+0.0542, +0.0614] | 100.0% | +0.0605 | [+0.0533, +0.0679] | `chm` **BETTER** than `max(chm2,chm2005)` |
| `chm2` vs `chm2005` | +0.0406 | [+0.0373, +0.0435] | 100.0% | +0.0529 | [+0.0456, +0.0599] | `chm2` **BETTER** than `chm2005` · epoch-handicapped |
| `chm2` vs `max2(chm2)` | -0.0515 | [-0.0542, -0.0487] | 100.0% | -0.0400 | [-0.0445, -0.0357] | `chm2` **WORSE** than `max2(chm2)` |
| `chm2` vs `max1(chm2005)` | +0.0074 | [+0.0042, +0.0101] | 100.0% | +0.0271 | [+0.0209, +0.0335] | `chm2` **BETTER** than `max1(chm2005)` |
| `chm2` vs `max(chm2,chm2005)` | -0.0055 | [-0.0074, -0.0036] | 100.0% | +0.0077 | [+0.0035, +0.0121] | `chm2` **WORSE** than `max(chm2,chm2005)` |
| `chm2005` vs `max2(chm2)` | -0.0921 | [-0.0969, -0.0875] | 100.0% | -0.0929 | [-0.1023, -0.0835] | `chm2005` **WORSE** than `max2(chm2)` · epoch-handicapped |
| `chm2005` vs `max1(chm2005)` | -0.0331 | [-0.0347, -0.0316] | 100.0% | -0.0258 | [-0.0281, -0.0235] | `chm2005` **WORSE** than `max1(chm2005)` · epoch-handicapped |
| `chm2005` vs `max(chm2,chm2005)` | -0.0460 | [-0.0485, -0.0439] | 100.0% | -0.0452 | [-0.0492, -0.0410] | `chm2005` **WORSE** than `max(chm2,chm2005)` · epoch-handicapped |
| `max2(chm2)` vs `max1(chm2005)` | +0.0589 | [+0.0554, +0.0624] | 100.0% | +0.0671 | [+0.0592, +0.0752] | `max2(chm2)` **BETTER** than `max1(chm2005)` |
| `max2(chm2)` vs `max(chm2,chm2005)` | +0.0461 | [+0.0432, +0.0488] | 100.0% | +0.0477 | [+0.0420, +0.0537] | `max2(chm2)` **BETTER** than `max(chm2,chm2005)` |
| `max1(chm2005)` vs `max(chm2,chm2005)` | -0.0129 | [-0.0145, -0.0112] | 100.0% | -0.0194 | [-0.0221, -0.0169] | `max1(chm2005)` **WORSE** than `max(chm2,chm2005)` |

`UNDETERMINED` means the gap is inside this test's own resolving power. It is **not** a null: this evaluation could not tell the two apart, which is a statement about the evidence, not about the rasters.

`epoch-handicapped`: an arm in that pair is from a different epoch than the 2016 reference, so real canopy growth and removal between the two dates is charged to the raster as classification error. Its score is a LOWER BOUND on its discrimination in its own epoch — which is the epoch it would actually be used in.

## What this test licenses

* It measures MARGINAL discrimination — how well each raster separates canopy from non-canopy **on its own**. An arm that wins here is strictly more informative about canopy, and that is a green light.
* It does **not** measure CONDITIONAL value. The height raster enters training as a 4th channel beside RGB; a weaker marginal discriminator can still carry information RGB lacks. A gap this test cannot resolve therefore does not license the claim that training cannot benefit.
* AUROC and PR-AUC are invariant under any strictly monotone transform of the score, and subtracting a constant is monotone. **The constant component of a ground-height inflation cannot move AUROC by construction** — it moves only the height at which the best operating point sits. Any offset arm above therefore tests the machinery, and the surviving old-vs-new gap is RANK-ORDER difference: real discrimination, not level.
* The reference is C-CAP: a 1 m classified product with its own errors, not hand truth. It cannot resolve crowns below its own cell, so every raster here is scored at C-CAP's information limit.


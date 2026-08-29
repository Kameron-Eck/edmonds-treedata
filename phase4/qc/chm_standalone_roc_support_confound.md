# Height rasters as STANDALONE canopy classifiers — `support_confound`

The cheap prior. No training, no GPU. Every height raster is already a 254-level canopy score under the shared encoding `DN = 1 + round(clip(h,0,50.6)/0.2)`, `0 = nodata`, so sweeping the cut over every DN enumerates every *canopy is taller than h metres* classifier there is.

Reference: `ccap_2016_hires_lc_snohfull.tif` (epoch 2016) · canopy definition `forest_wetland` · scored on the INTERSECTION of every raster below, so coverage is never charged as accuracy.

## Inputs

| arm | source | CRS | native res (m) | epoch |
|---|---|---|---|---|
| `chm` | `lidar_snoh_chm.tif` | EPSG:3857 | 1.00 x 1.00 | 2016 |
| `chm2` | `lidar_chm2_2016_50cm.tif` | EPSG:26910 | 0.50 x 0.50 | 2016 |
| `max1(chm2)` | derived: `chm2` under a 3x3 px (3 m) neighbourhood MAXIMUM — the support/dilation confound test | — | — | — |
| `max2(chm2)` | derived: `chm2` under a 5x5 px (5 m) neighbourhood MAXIMUM — the support/dilation confound test | — | — | — |
| `max1(chm)` | derived: `chm` under a 3x3 px (3 m) neighbourhood MAXIMUM — the support/dilation confound test | — | — | — |

A `maxN(...)` arm exists to test ONE hypothesis: the old product is ~2 m HAG bilinear-upsampled and measurably behaves as a neighbourhood maximum (`build_chm2_2016.py` [2b]), while the reference labels forest patches wall to wall. If a SHARP raster catches up once it is dilated to the same support, the gap between them was granularity, not information — and granularity matched to a 1 m reference is not evidence about a channel the engine consumes at 10-15 cm. The filter is truncated at I/O strip boundaries (2048 rows), which touches ~0.20% of rows.

## Footprint and coverage

Analysis grid: **7055 x 9813 @ 1 m** in EPSG:26910 = 69.2 Mpx, the intersection of every raster's own extent with the reference's, snapped to the reference lattice.

Reference-scorable on that grid: **69,198,289 px**. Common valid (all arms x scorable): **41,975,356 px** (60.66% of scorable).

| arm | own valid / grid | own valid & ref-scorable | share of the common footprint it alone would add | DN 1 (h = 0 m) inside common |
|---|---|---|---|---|
| `chm` | 71.49% | 49,480,525 | 15.17% dropped by the intersection | 8.73% |
| `chm2` | 60.82% | 42,103,555 | 0.30% dropped by the intersection | 28.27% |
| `max1(chm2)` | 60.82% | 42,103,555 | 0.30% dropped by the intersection | 13.74% |
| `max2(chm2)` | 60.82% | 42,103,555 | 0.30% dropped by the intersection | 7.56% |
| `max1(chm)` | 71.49% | 49,480,525 | 15.17% dropped by the intersection | 5.50% |

The DN-1 column is also an encoding check: DN 1 is *flat ground*, not nodata. An arm reporting ~0% there would mean its zero-height mass had been swallowed by the nodata code and every metre label below would be wrong.

## Standalone discrimination

Reference canopy px: 16,785,766 · non-canopy: 25,189,590 · prevalence 39.99%

| arm | AUROC | 95% CI (own) | PR-AUC | best-F1 height | F1 | best-Youden height | J |
|---|---|---|---|---|---|---|---|
| `chm` | 0.9059 | [0.8999, 0.9123] | 0.8721 | 9.8 m | 0.7921 | 9.8 m | 0.6536 |
| `chm2` | 0.8429 | [0.8344, 0.8525] | 0.8194 | 6.4 m | 0.7147 | 6.8 m | 0.5402 |
| `max1(chm2)` | 0.8843 | [0.8773, 0.8923] | 0.8555 | 7.8 m | 0.7669 | 8.0 m | 0.6136 |
| `max2(chm2)` | 0.8949 | [0.8884, 0.9024] | 0.8608 | 9.4 m | 0.7798 | 9.4 m | 0.6331 |
| `max1(chm)` | 0.9017 | [0.8956, 0.9081] | 0.8621 | 12.0 m | 0.7939 | 12.0 m | 0.6567 |

## Performance by height threshold — where does each raster discriminate?

Recall / precision / F1 of the rule *canopy iff height >= h*.

| h (m) | `chm` R/P/F1 | `chm2` R/P/F1 | `max1(chm2)` R/P/F1 | `max2(chm2)` R/P/F1 | `max1(chm)` R/P/F1 |
|---|---|---|---|---|---|
| 0.0 | 1.000/0.400/0.571 | 1.000/0.400/0.571 | 1.000/0.400/0.571 | 1.000/0.400/0.571 | 1.000/0.400/0.571 |
| 1.0 | 0.999/0.456/0.626 | 0.850/0.592/0.698 | 0.968/0.521/0.677 | 0.994/0.474/0.642 | 1.000/0.434/0.606 |
| 2.0 | 0.995/0.486/0.653 | 0.812/0.617/0.701 | 0.945/0.554/0.699 | 0.987/0.505/0.668 | 0.999/0.457/0.627 |
| 3.0 | 0.985/0.512/0.674 | 0.770/0.642/0.700 | 0.913/0.581/0.710 | 0.969/0.529/0.685 | 0.995/0.477/0.645 |
| 4.0 | 0.964/0.552/0.702 | 0.725/0.693/0.709 | 0.872/0.625/0.728 | 0.941/0.566/0.707 | 0.983/0.507/0.669 |
| 5.0 | 0.936/0.598/0.729 | 0.689/0.737/0.712 | 0.835/0.668/0.742 | 0.910/0.607/0.728 | 0.964/0.546/0.697 |
| 6.0 | 0.905/0.644/0.753 | 0.654/0.787/0.714 | 0.798/0.716/0.755 | 0.877/0.652/0.748 | 0.940/0.588/0.724 |
| 8.0 | 0.843/0.738/0.787 | 0.596/0.866/0.706 | 0.735/0.801/0.767 | 0.815/0.741/0.776 | 0.887/0.678/0.769 |
| 10.0 | 0.788/0.796/0.792 | 0.548/0.907/0.683 | 0.682/0.850/0.757 | 0.763/0.795/0.779 | 0.838/0.739/0.785 |
| 12.0 | 0.734/0.851/0.788 | 0.503/0.932/0.654 | 0.632/0.892/0.740 | 0.713/0.849/0.775 | 0.787/0.801/0.794 |
| 15.0 | 0.661/0.886/0.757 | 0.438/0.947/0.599 | 0.563/0.916/0.697 | 0.643/0.881/0.743 | 0.718/0.843/0.776 |
| 20.0 | 0.533/0.920/0.675 | 0.328/0.961/0.489 | 0.441/0.939/0.600 | 0.518/0.914/0.661 | 0.593/0.887/0.711 |

## POWER OF THIS TEST — read before any verdict below

Paired spatial block bootstrap: **201 non-empty blocks** of 512 x 512 px (512 m x 512 m) · 400 replicates · every replicate scores every arm on the SAME resampled blocks, so the shared ground cancels and the interval is on the DIFFERENCE.

Effective sample size is the BLOCK count, not the pixel count — neighbouring pixels are the same tree. `resolving power` below is the half-width of the 95% interval on the paired gap: **a difference smaller than that number is not measurable by this evaluation and is reported UNDETERMINED, not as absence of an effect.**

| pair | observed dAUROC | resolving power (+-) | measurable? |
|---|---|---|---|
| `chm` vs `chm2` | +0.0630 | 0.0033 | yes |
| `chm` vs `max1(chm2)` | +0.0217 | 0.0017 | yes |
| `chm` vs `max2(chm2)` | +0.0110 | 0.0010 | yes |
| `chm` vs `max1(chm)` | +0.0042 | 0.0007 | yes |
| `chm2` vs `max1(chm2)` | -0.0414 | 0.0019 | yes |
| `chm2` vs `max2(chm2)` | -0.0520 | 0.0026 | yes |
| `chm2` vs `max1(chm)` | -0.0588 | 0.0035 | yes |
| `max1(chm2)` vs `max2(chm2)` | -0.0106 | 0.0009 | yes |
| `max1(chm2)` vs `max1(chm)` | -0.0174 | 0.0019 | yes |
| `max2(chm2)` vs `max1(chm)` | -0.0068 | 0.0012 | yes |

## Verdicts

| pair | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | verdict |
|---|---|---|---|---|---|---|
| `chm` vs `chm2` | +0.0630 | [+0.0597, +0.0664] | 100.0% | +0.0527 | [+0.0484, +0.0575] | `chm` **BETTER** than `chm2` |
| `chm` vs `max1(chm2)` | +0.0217 | [+0.0200, +0.0234] | 100.0% | +0.0165 | [+0.0144, +0.0190] | `chm` **BETTER** than `max1(chm2)` |
| `chm` vs `max2(chm2)` | +0.0110 | [+0.0101, +0.0120] | 100.0% | +0.0113 | [+0.0098, +0.0131] | `chm` **BETTER** than `max2(chm2)` |
| `chm` vs `max1(chm)` | +0.0042 | [+0.0035, +0.0049] | 100.0% | +0.0100 | [+0.0086, +0.0115] | `chm` **BETTER** than `max1(chm)` |
| `chm2` vs `max1(chm2)` | -0.0414 | [-0.0433, -0.0395] | 100.0% | -0.0361 | [-0.0390, -0.0337] | `chm2` **WORSE** than `max1(chm2)` |
| `chm2` vs `max2(chm2)` | -0.0520 | [-0.0547, -0.0494] | 100.0% | -0.0414 | [-0.0451, -0.0381] | `chm2` **WORSE** than `max2(chm2)` |
| `chm2` vs `max1(chm)` | -0.0588 | [-0.0623, -0.0554] | 100.0% | -0.0427 | [-0.0473, -0.0387] | `chm2` **WORSE** than `max1(chm)` |
| `max1(chm2)` vs `max2(chm2)` | -0.0106 | [-0.0115, -0.0097] | 100.0% | -0.0053 | [-0.0063, -0.0042] | `max1(chm2)` **WORSE** than `max2(chm2)` |
| `max1(chm2)` vs `max1(chm)` | -0.0174 | [-0.0193, -0.0155] | 100.0% | -0.0066 | [-0.0089, -0.0041] | `max1(chm2)` **WORSE** than `max1(chm)` |
| `max2(chm2)` vs `max1(chm)` | -0.0068 | [-0.0080, -0.0056] | 100.0% | -0.0013 | [-0.0029, +0.0002] | `max2(chm2)` **WORSE** than `max1(chm)` |

`UNDETERMINED` means the gap is inside this test's own resolving power. It is **not** a null: this evaluation could not tell the two apart, which is a statement about the evidence, not about the rasters.

## What this test licenses

* It measures MARGINAL discrimination — how well each raster separates canopy from non-canopy **on its own**. An arm that wins here is strictly more informative about canopy, and that is a green light.
* It does **not** measure CONDITIONAL value. The height raster enters training as a 4th channel beside RGB; a weaker marginal discriminator can still carry information RGB lacks. A gap this test cannot resolve therefore does not license the claim that training cannot benefit.
* AUROC and PR-AUC are invariant under any strictly monotone transform of the score, and subtracting a constant is monotone. **The constant component of a ground-height inflation cannot move AUROC by construction** — it moves only the height at which the best operating point sits. Any offset arm above therefore tests the machinery, and the surviving old-vs-new gap is RANK-ORDER difference: real discrimination, not level.
* The reference is C-CAP: a 1 m classified product with its own errors, not hand truth. It cannot resolve crowns below its own cell, so every raster here is scored at C-CAP's information limit.


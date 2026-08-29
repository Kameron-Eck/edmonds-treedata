# Height rasters as STANDALONE canopy classifiers — `res_sensitivity_50cm`

The cheap prior. No training, no GPU. Every height raster is already a 254-level canopy score under the shared encoding `DN = 1 + round(clip(h,0,50.6)/0.2)`, `0 = nodata`, so sweeping the cut over every DN enumerates every *canopy is taller than h metres* classifier there is.

Reference: `ccap_2016_hires_lc_snohfull.tif` (epoch 2016) · canopy definition `forest_wetland` · scored on the INTERSECTION of every raster below, so coverage is never charged as accuracy.

## Inputs

| arm | source | CRS | native res (m) | epoch |
|---|---|---|---|---|
| `chm` | `lidar_snoh_chm.tif` | EPSG:3857 | 1.00 x 1.00 | 2016 |
| `chm2` | `lidar_chm2_2016_50cm.tif` | EPSG:26910 | 0.50 x 0.50 | 2016 |

## Footprint and coverage

Analysis grid: **14110 x 19625 @ 0.5 m** in EPSG:26910 = 276.9 Mpx, the intersection of every raster's own extent with the reference's, snapped to the reference lattice.

Reference-scorable on that grid: **276,779,178 px**. Common valid (all arms x scorable): **167,901,855 px** (60.66% of scorable).

| arm | own valid / grid | own valid & ref-scorable | share of the common footprint it alone would add | DN 1 (h = 0 m) inside common |
|---|---|---|---|---|
| `chm` | 71.49% | 197,921,885 | 15.17% dropped by the intersection | 9.12% |
| `chm2` | 60.82% | 168,411,326 | 0.30% dropped by the intersection | 28.28% |

The DN-1 column is also an encoding check: DN 1 is *flat ground*, not nodata. An arm reporting ~0% there would mean its zero-height mass had been swallowed by the nodata code and every metre label below would be wrong.

## Standalone discrimination

Reference canopy px: 67,149,465 · non-canopy: 100,752,390 · prevalence 39.99%

| arm | AUROC | 95% CI (own) | PR-AUC | best-F1 height | F1 | best-Youden height | J |
|---|---|---|---|---|---|---|---|
| `chm` | 0.9053 | [0.8993, 0.9123] | 0.8714 | 9.8 m | 0.7914 | 9.8 m | 0.6523 |
| `chm2` | 0.8453 | [0.8371, 0.8547] | 0.8221 | 6.4 m | 0.7171 | 6.8 m | 0.5436 |

## Performance by height threshold — where does each raster discriminate?

Recall / precision / F1 of the rule *canopy iff height >= h*.

| h (m) | `chm` R/P/F1 | `chm2` R/P/F1 |
|---|---|---|
| 0.0 | 1.000/0.400/0.571 | 1.000/0.400/0.571 |
| 1.0 | 0.998/0.457/0.627 | 0.853/0.594/0.700 |
| 2.0 | 0.995/0.486/0.653 | 0.815/0.619/0.703 |
| 3.0 | 0.984/0.513/0.674 | 0.772/0.644/0.702 |
| 4.0 | 0.963/0.552/0.701 | 0.727/0.696/0.711 |
| 5.0 | 0.935/0.597/0.729 | 0.691/0.739/0.714 |
| 6.0 | 0.904/0.644/0.752 | 0.656/0.790/0.717 |
| 8.0 | 0.842/0.737/0.786 | 0.598/0.869/0.708 |
| 10.0 | 0.788/0.795/0.791 | 0.550/0.909/0.685 |
| 12.0 | 0.734/0.850/0.788 | 0.505/0.934/0.655 |
| 15.0 | 0.661/0.885/0.757 | 0.439/0.948/0.600 |
| 20.0 | 0.533/0.919/0.675 | 0.328/0.963/0.490 |

## POWER OF THIS TEST — read before any verdict below

Paired spatial block bootstrap: **201 non-empty blocks** of 1024 x 1024 px (512 m x 512 m) · 200 replicates · every replicate scores every arm on the SAME resampled blocks, so the shared ground cancels and the interval is on the DIFFERENCE.

Effective sample size is the BLOCK count, not the pixel count — neighbouring pixels are the same tree. `resolving power` below is the half-width of the 95% interval on the paired gap: **a difference smaller than that number is not measurable by this evaluation and is reported UNDETERMINED, not as absence of an effect.**

| pair | observed dAUROC | resolving power (+-) | measurable? |
|---|---|---|---|
| `chm` vs `chm2` | +0.0600 | 0.0032 | yes |

## Verdicts

| pair | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | verdict |
|---|---|---|---|---|---|---|
| `chm` vs `chm2` | +0.0600 | [+0.0569, +0.0632] | 100.0% | +0.0493 | [+0.0454, +0.0539] | `chm` **BETTER** than `chm2` |

`UNDETERMINED` means the gap is inside this test's own resolving power. It is **not** a null: this evaluation could not tell the two apart, which is a statement about the evidence, not about the rasters.

## What this test licenses

* It measures MARGINAL discrimination — how well each raster separates canopy from non-canopy **on its own**. An arm that wins here is strictly more informative about canopy, and that is a green light.
* It does **not** measure CONDITIONAL value. The height raster enters training as a 4th channel beside RGB; a weaker marginal discriminator can still carry information RGB lacks. A gap this test cannot resolve therefore does not license the claim that training cannot benefit.
* AUROC and PR-AUC are invariant under any strictly monotone transform of the score, and subtracting a constant is monotone. **The constant component of a ground-height inflation cannot move AUROC by construction** — it moves only the height at which the best operating point sits. Any offset arm above therefore tests the machinery, and the surviving old-vs-new gap is RANK-ORDER difference: real discrimination, not level.
* The reference is C-CAP: a 1 m classified product with its own errors, not hand truth. It cannot resolve crowns below its own cell, so every raster here is scored at C-CAP's information limit.


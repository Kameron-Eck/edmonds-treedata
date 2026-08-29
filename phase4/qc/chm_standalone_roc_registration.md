# Height rasters as STANDALONE canopy classifiers — `registration`

The cheap prior. No training, no GPU. Every height raster is already a 254-level canopy score under the shared encoding `DN = 1 + round(clip(h,0,50.6)/0.2)`, `0 = nodata`, so sweeping the cut over every DN enumerates every *canopy is taller than h metres* classifier there is.

Reference: `ccap_2016_hires_lc_snohfull.tif` (epoch 2016) · canopy definition `forest_wetland` · scored on the INTERSECTION of every raster below, so coverage is never charged as accuracy.

## Inputs

| arm | source | CRS | native res (m) | epoch |
|---|---|---|---|---|
| `chm2` | `lidar_chm2_2016_50cm.tif` | EPSG:26910 | 0.50 x 0.50 | 2016 |
| `chm2@+2E+0N` | `chm2` sampled at (x+2 m, y+0 m) — the registration test | — | — | 2016 |
| `chm2@-2E+0N` | `chm2` sampled at (x-2 m, y+0 m) — the registration test | — | — | 2016 |
| `chm2@+0E+2N` | `chm2` sampled at (x+0 m, y+2 m) — the registration test | — | — | 2016 |
| `chm2@+0E-2N` | `chm2` sampled at (x+0 m, y-2 m) — the registration test | — | — | 2016 |

A `@dxE dyN` arm is the same file sampled from a translated window. A dilation test alone cannot separate *the reference is blobbier than the raster* from *the reference is offset from the raster* — a neighbourhood maximum hides both. If AUROC peaks at a NONZERO shift, the reference sits that far from the lidar and every sharp raster is being charged for a registration error rather than for its own accuracy. If it peaks at zero, registration is excluded and granularity is left holding the result.

## Footprint and coverage

Analysis grid: **7178 x 10942 @ 1 m** in EPSG:26910 = 78.5 Mpx, the intersection of every raster's own extent with the reference's, snapped to the reference lattice.

Reference-scorable on that grid: **77,814,055 px**. Common valid (all arms x scorable): **43,594,337 px** (56.02% of scorable).

| arm | own valid / grid | own valid & ref-scorable | share of the common footprint it alone would add | DN 1 (h = 0 m) inside common |
|---|---|---|---|---|
| `chm2` | 55.69% | 43,742,511 | 0.34% dropped by the intersection | 27.83% |
| `chm2@+2E+0N` | 55.69% | 43,742,511 | 0.34% dropped by the intersection | 27.83% |
| `chm2@-2E+0N` | 55.69% | 43,742,511 | 0.34% dropped by the intersection | 27.87% |
| `chm2@+0E+2N` | 55.69% | 43,742,483 | 0.34% dropped by the intersection | 27.85% |
| `chm2@+0E-2N` | 55.69% | 43,742,207 | 0.34% dropped by the intersection | 27.83% |

The DN-1 column is also an encoding check: DN 1 is *flat ground*, not nodata. An arm reporting ~0% there would mean its zero-height mass had been swallowed by the nodata code and every metre label below would be wrong.

## Standalone discrimination

Reference canopy px: 17,644,889 · non-canopy: 25,949,448 · prevalence 40.48%

| arm | AUROC | 95% CI (own) | PR-AUC | best-F1 height | F1 | best-Youden height | J |
|---|---|---|---|---|---|---|---|
| `chm2` | 0.8448 | [0.8369, 0.8528] | 0.8242 | 6.4 m | 0.7188 | 6.8 m | 0.5444 |
| `chm2@+2E+0N` | 0.8231 | [0.8134, 0.8325] | 0.8011 | 6.4 m | 0.6980 | 7.2 m | 0.5146 |
| `chm2@-2E+0N` | 0.8512 | [0.8439, 0.8586] | 0.8310 | 6.2 m | 0.7249 | 6.8 m | 0.5532 |
| `chm2@+0E+2N` | 0.8425 | [0.8342, 0.8506] | 0.8225 | 6.4 m | 0.7166 | 7.0 m | 0.5414 |
| `chm2@+0E-2N` | 0.8275 | [0.8184, 0.8362] | 0.8049 | 6.4 m | 0.7021 | 7.2 m | 0.5201 |

## Performance by height threshold — where does each raster discriminate?

Recall / precision / F1 of the rule *canopy iff height >= h*.

| h (m) | `chm2` R/P/F1 | `chm2@+2E+0N` R/P/F1 | `chm2@-2E+0N` R/P/F1 | `chm2@+0E+2N` R/P/F1 | `chm2@+0E-2N` R/P/F1 |
|---|---|---|---|---|---|
| 0.0 | 1.000/0.405/0.576 | 1.000/0.405/0.576 | 1.000/0.405/0.576 | 1.000/0.405/0.576 | 1.000/0.405/0.576 |
| 1.0 | 0.852/0.597/0.702 | 0.829/0.581/0.683 | 0.859/0.602/0.708 | 0.849/0.595/0.700 | 0.834/0.584/0.687 |
| 2.0 | 0.815/0.622/0.705 | 0.793/0.605/0.686 | 0.822/0.628/0.712 | 0.812/0.620/0.703 | 0.798/0.609/0.690 |
| 3.0 | 0.773/0.647/0.704 | 0.752/0.629/0.685 | 0.779/0.653/0.710 | 0.769/0.644/0.701 | 0.757/0.634/0.690 |
| 4.0 | 0.729/0.698/0.713 | 0.708/0.678/0.693 | 0.735/0.704/0.720 | 0.726/0.695/0.710 | 0.713/0.683/0.697 |
| 5.0 | 0.693/0.740/0.716 | 0.673/0.719/0.695 | 0.699/0.747/0.722 | 0.690/0.738/0.713 | 0.678/0.724/0.700 |
| 6.0 | 0.658/0.791/0.718 | 0.639/0.768/0.698 | 0.664/0.798/0.725 | 0.656/0.788/0.716 | 0.643/0.773/0.702 |
| 8.0 | 0.601/0.870/0.711 | 0.585/0.846/0.692 | 0.605/0.877/0.716 | 0.599/0.868/0.709 | 0.588/0.850/0.695 |
| 10.0 | 0.554/0.910/0.688 | 0.540/0.888/0.672 | 0.557/0.916/0.693 | 0.553/0.909/0.687 | 0.542/0.892/0.675 |
| 12.0 | 0.509/0.934/0.659 | 0.498/0.914/0.645 | 0.512/0.940/0.663 | 0.508/0.934/0.658 | 0.500/0.917/0.647 |
| 15.0 | 0.444/0.948/0.605 | 0.436/0.932/0.594 | 0.446/0.953/0.607 | 0.444/0.949/0.604 | 0.437/0.934/0.595 |
| 20.0 | 0.333/0.963/0.495 | 0.329/0.950/0.489 | 0.334/0.966/0.497 | 0.333/0.963/0.495 | 0.329/0.951/0.489 |

## POWER OF THIS TEST — read before any verdict below

Paired spatial block bootstrap: **212 non-empty blocks** of 512 x 512 px (512 m x 512 m) · 200 replicates · every replicate scores every arm on the SAME resampled blocks, so the shared ground cancels and the interval is on the DIFFERENCE.

Effective sample size is the BLOCK count, not the pixel count — neighbouring pixels are the same tree. `resolving power` below is the half-width of the 95% interval on the paired gap: **a difference smaller than that number is not measurable by this evaluation and is reported UNDETERMINED, not as absence of an effect.**

| pair | observed dAUROC | resolving power (+-) | measurable? |
|---|---|---|---|
| `chm2` vs `chm2@+2E+0N` | +0.0217 | 0.0016 | yes |
| `chm2` vs `chm2@-2E+0N` | -0.0064 | 0.0011 | yes |
| `chm2` vs `chm2@+0E+2N` | +0.0023 | 0.0004 | yes |
| `chm2` vs `chm2@+0E-2N` | +0.0173 | 0.0009 | yes |
| `chm2@+2E+0N` vs `chm2@-2E+0N` | -0.0280 | 0.0025 | yes |
| `chm2@+2E+0N` vs `chm2@+0E+2N` | -0.0193 | 0.0014 | yes |
| `chm2@+2E+0N` vs `chm2@+0E-2N` | -0.0044 | 0.0010 | yes |
| `chm2@-2E+0N` vs `chm2@+0E+2N` | +0.0087 | 0.0013 | yes |
| `chm2@-2E+0N` vs `chm2@+0E-2N` | +0.0236 | 0.0017 | yes |
| `chm2@+0E+2N` vs `chm2@+0E-2N` | +0.0149 | 0.0009 | yes |

## Verdicts

| pair | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | verdict |
|---|---|---|---|---|---|---|
| `chm2` vs `chm2@+2E+0N` | +0.0217 | [+0.0202, +0.0233] | 100.0% | +0.0231 | [+0.0204, +0.0259] | `chm2` **BETTER** than `chm2@+2E+0N` |
| `chm2` vs `chm2@-2E+0N` | -0.0064 | [-0.0075, -0.0053] | 100.0% | -0.0068 | [-0.0084, -0.0054] | `chm2` **WORSE** than `chm2@-2E+0N` |
| `chm2` vs `chm2@+0E+2N` | +0.0023 | [+0.0019, +0.0027] | 100.0% | +0.0016 | [+0.0011, +0.0022] | `chm2` **BETTER** than `chm2@+0E+2N` |
| `chm2` vs `chm2@+0E-2N` | +0.0173 | [+0.0163, +0.0182] | 100.0% | +0.0193 | [+0.0173, +0.0215] | `chm2` **BETTER** than `chm2@+0E-2N` |
| `chm2@+2E+0N` vs `chm2@-2E+0N` | -0.0280 | [-0.0306, -0.0256] | 100.0% | -0.0299 | [-0.0343, -0.0261] | `chm2@+2E+0N` **WORSE** than `chm2@-2E+0N` |
| `chm2@+2E+0N` vs `chm2@+0E+2N` | -0.0193 | [-0.0208, -0.0180] | 100.0% | -0.0215 | [-0.0239, -0.0191] | `chm2@+2E+0N` **WORSE** than `chm2@+0E+2N` |
| `chm2@+2E+0N` vs `chm2@+0E-2N` | -0.0044 | [-0.0054, -0.0035] | 100.0% | -0.0038 | [-0.0053, -0.0024] | `chm2@+2E+0N` **WORSE** than `chm2@+0E-2N` |
| `chm2@-2E+0N` vs `chm2@+0E+2N` | +0.0087 | [+0.0075, +0.0100] | 100.0% | +0.0085 | [+0.0067, +0.0103] | `chm2@-2E+0N` **BETTER** than `chm2@+0E+2N` |
| `chm2@-2E+0N` vs `chm2@+0E-2N` | +0.0236 | [+0.0220, +0.0254] | 100.0% | +0.0261 | [+0.0230, +0.0292] | `chm2@-2E+0N` **BETTER** than `chm2@+0E-2N` |
| `chm2@+0E+2N` vs `chm2@+0E-2N` | +0.0149 | [+0.0140, +0.0158] | 100.0% | +0.0177 | [+0.0158, +0.0195] | `chm2@+0E+2N` **BETTER** than `chm2@+0E-2N` |

`UNDETERMINED` means the gap is inside this test's own resolving power. It is **not** a null: this evaluation could not tell the two apart, which is a statement about the evidence, not about the rasters.

## What this test licenses

* It measures MARGINAL discrimination — how well each raster separates canopy from non-canopy **on its own**. An arm that wins here is strictly more informative about canopy, and that is a green light.
* It does **not** measure CONDITIONAL value. The height raster enters training as a 4th channel beside RGB; a weaker marginal discriminator can still carry information RGB lacks. A gap this test cannot resolve therefore does not license the claim that training cannot benefit.
* AUROC and PR-AUC are invariant under any strictly monotone transform of the score, and subtracting a constant is monotone. **The constant component of a ground-height inflation cannot move AUROC by construction** — it moves only the height at which the best operating point sits. Any offset arm above therefore tests the machinery, and the surviving old-vs-new gap is RANK-ORDER difference: real discrimination, not level.
* The reference is C-CAP: a 1 m classified product with its own errors, not hand truth. It cannot resolve crowns below its own cell, so every raster here is scored at C-CAP's information limit.


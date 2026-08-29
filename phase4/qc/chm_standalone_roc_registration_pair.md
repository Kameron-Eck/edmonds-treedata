# Height rasters as STANDALONE canopy classifiers — `registration_pair`

The cheap prior. No training, no GPU. Every height raster is already a 254-level canopy score under the shared encoding `DN = 1 + round(clip(h,0,50.6)/0.2)`, `0 = nodata`, so sweeping the cut over every DN enumerates every *canopy is taller than h metres* classifier there is.

Reference: `ccap_2016_hires_lc_snohfull.tif` (epoch 2016) · canopy definition `forest_wetland` · scored on the INTERSECTION of every raster below, so coverage is never charged as accuracy.

## Inputs

| arm | source | CRS | native res (m) | epoch |
|---|---|---|---|---|
| `chm` | `lidar_snoh_chm.tif` | EPSG:3857 | 1.00 x 1.00 | 2016 |
| `chm2` | `lidar_chm2_2016_50cm.tif` | EPSG:26910 | 0.50 x 0.50 | 2016 |
| `chm@-2E+0N` | `chm` sampled at (x-2 m, y+0 m) — the registration test | — | — | 2016 |
| `chm2@-2E+0N` | `chm2` sampled at (x-2 m, y+0 m) — the registration test | — | — | 2016 |
| `chm@-4E+0N` | `chm` sampled at (x-4 m, y+0 m) — the registration test | — | — | 2016 |
| `chm2@-4E+0N` | `chm2` sampled at (x-4 m, y+0 m) — the registration test | — | — | 2016 |

A `@dxE dyN` arm is the same file sampled from a translated window. A dilation test alone cannot separate *the reference is blobbier than the raster* from *the reference is offset from the raster* — a neighbourhood maximum hides both. If AUROC peaks at a NONZERO shift, the reference sits that far from the lidar and every sharp raster is being charged for a registration error rather than for its own accuracy. If it peaks at zero, registration is excluded and granularity is left holding the result.

## Footprint and coverage

Analysis grid: **7055 x 9813 @ 1 m** in EPSG:26910 = 69.2 Mpx, the intersection of every raster's own extent with the reference's, snapped to the reference lattice.

Reference-scorable on that grid: **69,198,289 px**. Common valid (all arms x scorable): **41,880,877 px** (60.52% of scorable).

| arm | own valid / grid | own valid & ref-scorable | share of the common footprint it alone would add | DN 1 (h = 0 m) inside common |
|---|---|---|---|---|
| `chm` | 71.49% | 49,480,525 | 15.36% dropped by the intersection | 8.67% |
| `chm2` | 60.82% | 42,103,555 | 0.53% dropped by the intersection | 28.21% |
| `chm@-2E+0N` | 71.49% | 49,481,447 | 15.36% dropped by the intersection | 8.69% |
| `chm2@-2E+0N` | 60.81% | 42,100,775 | 0.52% dropped by the intersection | 28.22% |
| `chm@-4E+0N` | 71.49% | 49,482,364 | 15.36% dropped by the intersection | 8.72% |
| `chm2@-4E+0N` | 60.81% | 42,097,995 | 0.52% dropped by the intersection | 28.25% |

The DN-1 column is also an encoding check: DN 1 is *flat ground*, not nodata. An arm reporting ~0% there would mean its zero-height mass had been swallowed by the nodata code and every metre label below would be wrong.

## Standalone discrimination

Reference canopy px: 16,768,579 · non-canopy: 25,112,298 · prevalence 40.04%

| arm | AUROC | 95% CI (own) | PR-AUC | best-F1 height | F1 | best-Youden height | J |
|---|---|---|---|---|---|---|---|
| `chm` | 0.9058 | [0.8998, 0.9128] | 0.8721 | 9.8 m | 0.7922 | 9.8 m | 0.6534 |
| `chm2` | 0.8427 | [0.8343, 0.8523] | 0.8195 | 6.4 m | 0.7147 | 6.8 m | 0.5400 |
| `chm@-2E+0N` | 0.9020 | [0.8962, 0.9087] | 0.8670 | 9.8 m | 0.7876 | 9.8 m | 0.6458 |
| `chm2@-2E+0N` | 0.8494 | [0.8415, 0.8578] | 0.8268 | 6.2 m | 0.7213 | 6.8 m | 0.5495 |
| `chm@-4E+0N` | 0.8866 | [0.8805, 0.8937] | 0.8481 | 9.6 m | 0.7709 | 10.4 m | 0.6181 |
| `chm2@-4E+0N` | 0.8360 | [0.8278, 0.8448] | 0.8134 | 6.2 m | 0.7100 | 6.8 m | 0.5331 |

## Performance by height threshold — where does each raster discriminate?

Recall / precision / F1 of the rule *canopy iff height >= h*.

| h (m) | `chm` R/P/F1 | `chm2` R/P/F1 | `chm@-2E+0N` R/P/F1 | `chm2@-2E+0N` R/P/F1 | `chm@-4E+0N` R/P/F1 | `chm2@-4E+0N` R/P/F1 |
|---|---|---|---|---|---|---|
| 0.0 | 1.000/0.400/0.572 | 1.000/0.400/0.572 | 1.000/0.400/0.572 | 1.000/0.400/0.572 | 1.000/0.400/0.572 | 1.000/0.400/0.572 |
| 1.0 | 0.999/0.456/0.626 | 0.850/0.592/0.698 | 0.998/0.456/0.626 | 0.857/0.597/0.704 | 0.994/0.454/0.624 | 0.841/0.587/0.691 |
| 2.0 | 0.995/0.486/0.653 | 0.812/0.617/0.701 | 0.994/0.485/0.652 | 0.820/0.623/0.708 | 0.987/0.482/0.648 | 0.806/0.612/0.696 |
| 3.0 | 0.985/0.512/0.674 | 0.770/0.642/0.700 | 0.983/0.511/0.673 | 0.777/0.648/0.707 | 0.973/0.507/0.667 | 0.765/0.638/0.696 |
| 4.0 | 0.964/0.552/0.702 | 0.725/0.693/0.709 | 0.961/0.550/0.700 | 0.732/0.700/0.716 | 0.950/0.544/0.692 | 0.720/0.689/0.704 |
| 5.0 | 0.936/0.598/0.729 | 0.689/0.737/0.712 | 0.933/0.596/0.728 | 0.695/0.744/0.719 | 0.919/0.588/0.717 | 0.684/0.732/0.707 |
| 6.0 | 0.905/0.644/0.753 | 0.654/0.787/0.715 | 0.902/0.643/0.750 | 0.660/0.795/0.721 | 0.887/0.632/0.738 | 0.650/0.783/0.710 |
| 8.0 | 0.843/0.738/0.787 | 0.596/0.866/0.706 | 0.839/0.734/0.783 | 0.601/0.873/0.712 | 0.821/0.720/0.767 | 0.592/0.861/0.702 |
| 10.0 | 0.788/0.796/0.792 | 0.548/0.907/0.684 | 0.783/0.792/0.787 | 0.552/0.914/0.688 | 0.766/0.775/0.771 | 0.545/0.902/0.680 |
| 12.0 | 0.734/0.851/0.788 | 0.504/0.932/0.654 | 0.730/0.846/0.784 | 0.507/0.938/0.658 | 0.714/0.829/0.767 | 0.501/0.928/0.651 |
| 15.0 | 0.662/0.886/0.757 | 0.438/0.947/0.599 | 0.657/0.881/0.753 | 0.440/0.952/0.602 | 0.645/0.864/0.738 | 0.436/0.943/0.597 |
| 20.0 | 0.533/0.920/0.675 | 0.328/0.961/0.489 | 0.530/0.915/0.672 | 0.329/0.965/0.491 | 0.521/0.900/0.660 | 0.327/0.959/0.487 |

## POWER OF THIS TEST — read before any verdict below

Paired spatial block bootstrap: **201 non-empty blocks** of 512 x 512 px (512 m x 512 m) · 200 replicates · every replicate scores every arm on the SAME resampled blocks, so the shared ground cancels and the interval is on the DIFFERENCE.

Effective sample size is the BLOCK count, not the pixel count — neighbouring pixels are the same tree. `resolving power` below is the half-width of the 95% interval on the paired gap: **a difference smaller than that number is not measurable by this evaluation and is reported UNDETERMINED, not as absence of an effect.**

| pair | observed dAUROC | resolving power (+-) | measurable? |
|---|---|---|---|
| `chm` vs `chm2` | +0.0631 | 0.0033 | yes |
| `chm` vs `chm@-2E+0N` | +0.0037 | 0.0007 | yes |
| `chm` vs `chm2@-2E+0N` | +0.0564 | 0.0029 | yes |
| `chm` vs `chm@-4E+0N` | +0.0192 | 0.0014 | yes |
| `chm` vs `chm2@-4E+0N` | +0.0698 | 0.0033 | yes |
| `chm2` vs `chm@-2E+0N` | -0.0593 | 0.0036 | yes |
| `chm2` vs `chm2@-2E+0N` | -0.0067 | 0.0012 | yes |
| `chm2` vs `chm@-4E+0N` | -0.0439 | 0.0035 | yes |
| `chm2` vs `chm2@-4E+0N` | +0.0067 | 0.0016 | yes |
| `chm@-2E+0N` vs `chm2@-2E+0N` | +0.0527 | 0.0029 | yes |
| `chm@-2E+0N` vs `chm@-4E+0N` | +0.0154 | 0.0010 | yes |
| `chm@-2E+0N` vs `chm2@-4E+0N` | +0.0660 | 0.0033 | yes |
| `chm2@-2E+0N` vs `chm@-4E+0N` | -0.0372 | 0.0027 | yes |
| `chm2@-2E+0N` vs `chm2@-4E+0N` | +0.0134 | 0.0009 | yes |
| `chm@-4E+0N` vs `chm2@-4E+0N` | +0.0506 | 0.0028 | yes |

## Verdicts

| pair | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | verdict |
|---|---|---|---|---|---|---|
| `chm` vs `chm2` | +0.0631 | [+0.0598, +0.0665] | 100.0% | +0.0526 | [+0.0484, +0.0575] | `chm` **BETTER** than `chm2` |
| `chm` vs `chm@-2E+0N` | +0.0037 | [+0.0031, +0.0044] | 100.0% | +0.0051 | [+0.0040, +0.0063] | `chm` **BETTER** than `chm@-2E+0N` |
| `chm` vs `chm2@-2E+0N` | +0.0564 | [+0.0535, +0.0594] | 100.0% | +0.0453 | [+0.0418, +0.0493] | `chm` **BETTER** than `chm2@-2E+0N` |
| `chm` vs `chm@-4E+0N` | +0.0192 | [+0.0178, +0.0206] | 100.0% | +0.0240 | [+0.0211, +0.0270] | `chm` **BETTER** than `chm@-4E+0N` |
| `chm` vs `chm2@-4E+0N` | +0.0698 | [+0.0664, +0.0731] | 100.0% | +0.0588 | [+0.0545, +0.0640] | `chm` **BETTER** than `chm2@-4E+0N` |
| `chm2` vs `chm@-2E+0N` | -0.0593 | [-0.0631, -0.0559] | 100.0% | -0.0475 | [-0.0530, -0.0431] | `chm2` **WORSE** than `chm@-2E+0N` |
| `chm2` vs `chm2@-2E+0N` | -0.0067 | [-0.0079, -0.0055] | 100.0% | -0.0073 | [-0.0091, -0.0056] | `chm2` **WORSE** than `chm2@-2E+0N` |
| `chm2` vs `chm@-4E+0N` | -0.0439 | [-0.0477, -0.0407] | 100.0% | -0.0286 | [-0.0336, -0.0244] | `chm2` **WORSE** than `chm@-4E+0N` |
| `chm2` vs `chm2@-4E+0N` | +0.0067 | [+0.0050, +0.0082] | 100.0% | +0.0061 | [+0.0037, +0.0081] | `chm2` **BETTER** than `chm2@-4E+0N` |
| `chm@-2E+0N` vs `chm2@-2E+0N` | +0.0527 | [+0.0498, +0.0557] | 100.0% | +0.0402 | [+0.0368, +0.0442] | `chm@-2E+0N` **BETTER** than `chm2@-2E+0N` |
| `chm@-2E+0N` vs `chm@-4E+0N` | +0.0154 | [+0.0145, +0.0165] | 100.0% | +0.0189 | [+0.0169, +0.0209] | `chm@-2E+0N` **BETTER** than `chm@-4E+0N` |
| `chm@-2E+0N` vs `chm2@-4E+0N` | +0.0660 | [+0.0627, +0.0693] | 100.0% | +0.0536 | [+0.0497, +0.0582] | `chm@-2E+0N` **BETTER** than `chm2@-4E+0N` |
| `chm2@-2E+0N` vs `chm@-4E+0N` | -0.0372 | [-0.0401, -0.0346] | 100.0% | -0.0213 | [-0.0248, -0.0180] | `chm2@-2E+0N` **WORSE** than `chm@-4E+0N` |
| `chm2@-2E+0N` vs `chm2@-4E+0N` | +0.0134 | [+0.0125, +0.0142] | 100.0% | +0.0134 | [+0.0120, +0.0149] | `chm2@-2E+0N` **BETTER** than `chm2@-4E+0N` |
| `chm@-4E+0N` vs `chm2@-4E+0N` | +0.0506 | [+0.0477, +0.0534] | 100.0% | +0.0348 | [+0.0317, +0.0381] | `chm@-4E+0N` **BETTER** than `chm2@-4E+0N` |

`UNDETERMINED` means the gap is inside this test's own resolving power. It is **not** a null: this evaluation could not tell the two apart, which is a statement about the evidence, not about the rasters.

## What this test licenses

* It measures MARGINAL discrimination — how well each raster separates canopy from non-canopy **on its own**. An arm that wins here is strictly more informative about canopy, and that is a green light.
* It does **not** measure CONDITIONAL value. The height raster enters training as a 4th channel beside RGB; a weaker marginal discriminator can still carry information RGB lacks. A gap this test cannot resolve therefore does not license the claim that training cannot benefit.
* AUROC and PR-AUC are invariant under any strictly monotone transform of the score, and subtracting a constant is monotone. **The constant component of a ground-height inflation cannot move AUROC by construction** — it moves only the height at which the best operating point sits. Any offset arm above therefore tests the machinery, and the surviving old-vs-new gap is RANK-ORDER difference: real discrimination, not level.
* The reference is C-CAP: a 1 m classified product with its own errors, not hand truth. It cannot resolve crowns below its own cell, so every raster here is scored at C-CAP's information limit.


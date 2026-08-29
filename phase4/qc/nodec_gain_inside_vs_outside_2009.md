# Block-bootstrap CI on arm gaps — 2009

Resampling unit: 512x2048 px blocks · **235 non-empty blocks** · 300 replicates · paired (same blocks per replicate)

Effective sample size is the BLOCK count, not the pixel count — neighbouring
pixels are the same tree. This interval covers uncertainty from WHERE WE
LOOKED only: not retrain noise, not reference error.

Split mask: `add_nodec_2009.tif`, buffer 75 px. **inside** = where labels were added (plus buffer); **outside** = the rest.
A gain confined to *inside* is close to tautological — the model was told the
answer there. A gain that survives *outside* is transferable, and is the only
version of the result that scales beyond the labelled area.

## Region: all

| arm | AUROC | PR-AUC |
|---|---|---|
| `rgb3_nodeb` | 0.9063 | 0.8365 |
| `nodec_v1` | 0.9179 | 0.8588 |

Gaps vs `rgb3_nodeb` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `nodec_v1` | +0.0116 | [+0.0095, +0.0136] | 100.0% | +0.0223 | [+0.0184, +0.0268] | 100.0% |

## Region: inside

| arm | AUROC | PR-AUC |
|---|---|---|
| `rgb3_nodeb` | 0.8855 | 0.8845 |
| `nodec_v1` | 0.8898 | 0.8954 |

Gaps vs `rgb3_nodeb` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `nodec_v1` | +0.0043 | [+0.0032, +0.0052] | 100.0% | +0.0109 | [+0.0087, +0.0136] | 100.0% |

## Region: outside

| arm | AUROC | PR-AUC |
|---|---|---|
| `rgb3_nodeb` | 0.8416 | 0.2747 |
| `nodec_v1` | 0.8720 | 0.3005 |

Gaps vs `rgb3_nodeb` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `nodec_v1` | +0.0303 | [+0.0221, +0.0378] | 100.0% | +0.0259 | [+0.0057, +0.0380] | 99.0% |

`sign stable` = share of replicates where the gap kept the sign of the
point estimate. Below ~95% the ordering is not established by this evidence.

## READ THIS BEFORE QUOTING A CI THAT EXCLUDES ZERO

A tight interval here proves the two RASTERS differ on this ground. It does
NOT prove the two RECIPES differ, because retrain noise is not in it: train
the same recipe twice and you get two different rasters, and this tool would
call that gap significant too. Compare the gap against BOTH numbers — this
interval AND the measured retrain spread for the branch — and quote the
larger. A gap that clears spatial sampling but sits at the retrain scale is
trajectory noise wearing a confidence interval.


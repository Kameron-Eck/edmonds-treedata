# Block-bootstrap CI on arm gaps — 2009

Resampling unit: 2048x512 px blocks · **342 non-empty blocks** · 200 replicates · paired (same blocks per replicate)

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
| `seedENS3` | 0.9206 | 0.8642 |
| `seedMAX3` | 0.9176 | 0.8596 |

Gaps vs `seedENS3` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `seedMAX3` | -0.0030 | [-0.0035, -0.0025] | 100.0% | -0.0046 | [-0.0056, -0.0037] | 100.0% |

## Region: inside

| arm | AUROC | PR-AUC |
|---|---|---|
| `seedENS3` | 0.9007 | 0.9006 |
| `seedMAX3` | 0.8983 | 0.8980 |

Gaps vs `seedENS3` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `seedMAX3` | -0.0024 | [-0.0027, -0.0021] | 100.0% | -0.0027 | [-0.0034, -0.0019] | 100.0% |

## Region: outside

| arm | AUROC | PR-AUC |
|---|---|---|
| `seedENS3` | 0.8590 | 0.3051 |
| `seedMAX3` | 0.8455 | 0.2888 |

Gaps vs `seedENS3` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `seedMAX3` | -0.0134 | [-0.0162, -0.0108] | 100.0% | -0.0163 | [-0.0207, -0.0128] | 100.0% |

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


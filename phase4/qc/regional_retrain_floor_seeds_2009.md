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
| `fullext_sectors_v1` | 0.9210 | 0.8632 |
| `seed1234` | 0.9194 | 0.8620 |
| `seed777` | 0.9163 | 0.8464 |

Gaps vs `fullext_sectors_v1` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `seed1234` | -0.0017 | [-0.0023, -0.0010] | 100.0% | -0.0011 | [-0.0029, +0.0007] | 88.3% |
| `seed777` | -0.0048 | [-0.0058, -0.0038] | 100.0% | -0.0168 | [-0.0192, -0.0146] | 100.0% |

## Region: inside

| arm | AUROC | PR-AUC |
|---|---|---|
| `fullext_sectors_v1` | 0.9005 | 0.9013 |
| `seed1234` | 0.9007 | 0.9022 |
| `seed777` | 0.8946 | 0.8876 |

Gaps vs `fullext_sectors_v1` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `seed1234` | +0.0002 | [-0.0004, +0.0008] | 67.3% | +0.0009 | [-0.0003, +0.0022] | 92.3% |
| `seed777` | -0.0059 | [-0.0068, -0.0050] | 100.0% | -0.0137 | [-0.0156, -0.0118] | 100.0% |

## Region: outside

| arm | AUROC | PR-AUC |
|---|---|---|
| `fullext_sectors_v1` | 0.8607 | 0.3229 |
| `seed1234` | 0.8572 | 0.3080 |
| `seed777` | 0.8450 | 0.3000 |

Gaps vs `fullext_sectors_v1` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `seed1234` | -0.0035 | [-0.0063, -0.0010] | 100.0% | -0.0149 | [-0.0219, -0.0081] | 100.0% |
| `seed777` | -0.0157 | [-0.0200, -0.0121] | 100.0% | -0.0229 | [-0.0371, -0.0110] | 100.0% |

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


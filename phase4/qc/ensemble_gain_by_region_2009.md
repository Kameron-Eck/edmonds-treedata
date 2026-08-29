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
| `fullext_sectors_v1` | 0.9210 | 0.8632 |
| `seedENS3` | 0.9206 | 0.8642 |

Gaps vs `fullext_sectors_v1` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `seedENS3` | -0.0005 | [-0.0008, -0.0001] | 99.0% | +0.0010 | [+0.0003, +0.0017] | 99.5% |

## Region: inside

| arm | AUROC | PR-AUC |
|---|---|---|
| `fullext_sectors_v1` | 0.9005 | 0.8995 |
| `seedENS3` | 0.9007 | 0.9006 |

Gaps vs `fullext_sectors_v1` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `seedENS3` | +0.0002 | [-0.0002, +0.0005] | 80.0% | +0.0011 | [+0.0004, +0.0016] | 100.0% |

## Region: outside

| arm | AUROC | PR-AUC |
|---|---|---|
| `fullext_sectors_v1` | 0.8623 | 0.3101 |
| `seedENS3` | 0.8590 | 0.3051 |

Gaps vs `fullext_sectors_v1` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `seedENS3` | -0.0033 | [-0.0054, -0.0016] | 100.0% | -0.0050 | [-0.0103, -0.0004] | 98.0% |

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


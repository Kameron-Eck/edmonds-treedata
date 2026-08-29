# Block-bootstrap CI on arm gaps — 2009

Resampling unit: 512x2048 px blocks · **235 non-empty blocks** · 400 replicates · paired (same blocks per replicate)

Effective sample size is the BLOCK count, not the pixel count — neighbouring
pixels are the same tree. This interval covers uncertainty from WHERE WE
LOOKED only: not retrain noise, not reference error.

## Point estimates

| arm | AUROC | PR-AUC |
|---|---|---|
| `rgb3_nodeb` | 0.9063 | 0.8365 |
| `rgb3_ep60` | 0.9086 | 0.8322 |
| `nodec_v1` | 0.9179 | 0.8588 |

## Gaps vs `rgb3_nodeb` (95% percentile CI of the paired difference)

| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |
|---|---|---|---|---|---|---|
| `rgb3_ep60` | +0.0023 | [+0.0012, +0.0033] | 100.0% | -0.0044 | [-0.0067, -0.0023] | 100.0% |
| `nodec_v1` | +0.0116 | [+0.0094, +0.0136] | 100.0% | +0.0223 | [+0.0181, +0.0266] | 100.0% |

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

- `rgb3_ep60`: AUROC gap +0.0023, CI excludes zero — NOT explained by spatial sampling.
- `nodec_v1`: AUROC gap +0.0116, CI excludes zero — NOT explained by spatial sampling.

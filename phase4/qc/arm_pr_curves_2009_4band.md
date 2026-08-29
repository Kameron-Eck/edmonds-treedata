# Arm comparison — 2009, threshold-free

Common valid footprint (intersection of all arms x scorable reference): **198,770,664 px**
Reference canopy px (`forest_wetland`): 67,163,946 · non-canopy: 131,606,718

## Curve metrics (threshold-free — the actual 'is it better' answer)

| arm | AUROC | PR-AUC (AP) | recall@0.5 | precision@0.5 |
|---|---|---|---|---|
| `fullext_sectors_v1` | 0.9210 | 0.8632 | 0.6989 | 0.8472 |
| `corrupt10` | 0.9215 | 0.8653 | 0.7648 | 0.8131 |
| `corrupt25` | 0.9210 | 0.8575 | 0.5653 | 0.8891 |
| `corrupt50` | 0.9218 | 0.8568 | 0.6436 | 0.8543 |
| `chm2_v1` | 0.9153 | 0.8654 | 0.6790 | 0.8617 |
| `seed1234` | 0.9194 | 0.8620 | 0.6680 | 0.8590 |

## Matched operating points (vs `fullext_sectors_v1` @0.5: precision 0.8472, recall 0.6989)

| arm | recall @ precision>=0.8472 | thr | precision @ recall>=0.6989 | thr |
|---|---|---|---|---|
| `fullext_sectors_v1` | 0.6989 | 0.5000 | 0.8472 | 0.5000 |
| `corrupt10` | 0.6951 | 0.5157 | 0.8460 | 0.5118 |
| `corrupt25` | 0.6673 | 0.2323 | 0.8303 | 0.1575 |
| `corrupt50` | 0.6436 | 0.5000 | 0.8190 | 0.4961 |
| `chm2_v1` | 0.6953 | 0.4961 | 0.8432 | 0.4921 |
| `seed1234` | 0.6680 | 0.5000 | 0.8297 | 0.4961 |

## Calibration (fraction of common-valid px)

| arm | p in [0,0.01] | p in [0.49,0.51] | p in [0.99,1.0] |
|---|---|---|---|
| `fullext_sectors_v1` | 0.0000 | 0.1089 | 0.0000 |
| `corrupt10` | 0.0000 | 0.0437 | 0.0000 |
| `corrupt25` | 0.0000 | 0.0637 | 0.0000 |
| `corrupt50` | 0.0000 | 0.1229 | 0.0000 |
| `chm2_v1` | 0.0000 | 0.0903 | 0.0000 |
| `seed1234` | 0.0000 | 0.0994 | 0.0000 |

Noise floor for interpretation: recall sd .0100, precision sd .0052 (n=5, same seed — a LOWER bound).
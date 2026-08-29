# Arm comparison — 2009, threshold-free

Common valid footprint (intersection of all arms x scorable reference): **198,770,664 px**
Reference canopy px (`forest_wetland`): 67,163,946 · non-canopy: 131,606,718

## Curve metrics (threshold-free — the actual 'is it better' answer)

| arm | AUROC | PR-AUC (AP) | recall@0.5 | precision@0.5 |
|---|---|---|---|---|
| `fullext_sectors_v1` | 0.9210 | 0.8632 | 0.6989 | 0.8472 |
| `rgb3_nodeb` | 0.9063 | 0.8365 | 0.6567 | 0.8306 |

## Matched operating points (vs `fullext_sectors_v1` @0.5: precision 0.8472, recall 0.6989)

| arm | recall @ precision>=0.8472 | thr | precision @ recall>=0.6989 | thr |
|---|---|---|---|---|
| `fullext_sectors_v1` | 0.6989 | 0.5000 | 0.8472 | 0.5000 |
| `rgb3_nodeb` | 0.5990 | 0.5039 | 0.8007 | 0.4961 |

## Calibration (fraction of common-valid px)

| arm | p in [0,0.01] | p in [0.49,0.51] | p in [0.99,1.0] |
|---|---|---|---|
| `fullext_sectors_v1` | 0.0000 | 0.1089 | 0.0000 |
| `rgb3_nodeb` | 0.0000 | 0.1301 | 0.0000 |

Noise floor for interpretation: recall sd .0100, precision sd .0052 (n=5, same seed — a LOWER bound).
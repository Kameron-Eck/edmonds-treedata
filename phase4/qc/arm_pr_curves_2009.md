# Arm comparison — 2009, threshold-free

Common valid footprint (intersection of all arms x scorable reference): **149,225,448 px**
Reference canopy px (`forest_wetland`): 42,630,919 · non-canopy: 106,594,529

## Curve metrics (threshold-free — the actual 'is it better' answer)

| arm | AUROC | PR-AUC (AP) | recall@0.5 | precision@0.5 |
|---|---|---|---|---|
| `hybrid_v1` | 0.8946 | 0.7825 | 0.5625 | 0.8149 |

## Matched operating points (vs `hybrid_v1` @0.5: precision 0.8149, recall 0.5625)

| arm | recall @ precision>=0.8149 | thr | precision @ recall>=0.5625 | thr |
|---|---|---|---|---|
| `hybrid_v1` | 0.5625 | 0.5000 | 0.8149 | 0.5000 |

## Calibration (fraction of common-valid px)

| arm | p in [0,0.01] | p in [0.49,0.51] | p in [0.99,1.0] |
|---|---|---|---|
| `hybrid_v1` | 0.0000 | 0.0942 | 0.0000 |

Noise floor for interpretation: recall sd .0100, precision sd .0052 (n=5, same seed — a LOWER bound).
# Arm comparison — 2009, threshold-free

Common valid footprint (intersection of all arms x scorable reference): **198,770,664 px**
Reference canopy px (`forest_wetland`): 67,163,946 · non-canopy: 131,606,718

## Curve metrics (threshold-free — the actual 'is it better' answer)

| arm | AUROC | PR-AUC (AP) | recall@0.5 | precision@0.5 |
|---|---|---|---|---|
| `rgb3_nodeb` | 0.9063 | 0.8365 | 0.6567 | 0.8306 |
| `nodec_v1` | 0.9179 | 0.8588 | 0.7372 | 0.8073 |
| `nodec_s1234` | 0.9116 | 0.8516 | 0.7653 | 0.7752 |
| `nodecENS` | 0.9149 | 0.8558 | 0.7407 | 0.8033 |

## Matched operating points (vs `rgb3_nodeb` @0.5: precision 0.8306, recall 0.6567)

| arm | recall @ precision>=0.8306 | thr | precision @ recall>=0.6567 | thr |
|---|---|---|---|---|
| `rgb3_nodeb` | 0.6567 | 0.5000 | 0.8306 | 0.5000 |
| `nodec_v1` | 0.6925 | 0.5197 | 0.8469 | 0.5354 |
| `nodec_s1234` | 0.6706 | 0.5433 | 0.8374 | 0.5512 |
| `nodecENS` | 0.6791 | 0.5315 | 0.8428 | 0.5433 |

## Calibration (fraction of common-valid px)

| arm | p in [0,0.01] | p in [0.49,0.51] | p in [0.99,1.0] |
|---|---|---|---|
| `rgb3_nodeb` | 0.0000 | 0.1301 | 0.0000 |
| `nodec_v1` | 0.0000 | 0.0206 | 0.0000 |
| `nodec_s1234` | 0.0000 | 0.0254 | 0.0000 |
| `nodecENS` | 0.0000 | 0.0166 | 0.0000 |

Noise floor for interpretation: recall sd .0100, precision sd .0052 (n=5, same seed — a LOWER bound).
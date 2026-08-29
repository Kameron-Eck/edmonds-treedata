# FP/FN balance by region — 2009, threshold 0.5

FP = reference says NOT canopy, model says canopy (over-prediction).
FN = reference says canopy, model says not (under-prediction).
`FP:FN` above 1 means the region OVER-predicts; below 1, under-predicts.

| arm | region | TP | FP | FN | FP:FN | recall | precision |
|---|---|---|---|---|---|---|---|
| `rgb3_nodeb` | all | 44,104,262 | 8,993,098 | 23,059,679 | 0.39 | 0.6567 | 0.8306 |
| `rgb3_nodeb_s1234` | all | 43,661,151 | 8,314,614 | 23,502,790 | 0.35 | 0.6501 | 0.8400 |
| `nodec_v1` | all | 49,511,053 | 11,820,312 | 17,652,888 | 0.67 | 0.7372 | 0.8073 |
| `nodec_s1234` | all | 51,401,539 | 14,904,559 | 15,762,402 | 0.95 | 0.7653 | 0.7752 |

CAUTION: one reference (C-CAP 2016) applied to a 2009 raster, at one
threshold. Real 2009->2016 change lands in FP/FN too, and the reference's own
errors are not modelled. Read the DIRECTION, not the magnitude.


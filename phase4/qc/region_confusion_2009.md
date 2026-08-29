# FP/FN balance by region — 2009, threshold 0.5

FP = reference says NOT canopy, model says canopy (over-prediction).
FN = reference says canopy, model says not (under-prediction).
`FP:FN` above 1 means the region OVER-predicts; below 1, under-predicts.

| arm | region | TP | FP | FN | FP:FN | recall | precision |
|---|---|---|---|---|---|---|---|
| `rgb3_nodeb` | all | 44,104,262 | 8,993,098 | 23,059,679 | 0.39 | 0.6567 | 0.8306 |
| `rgb3_nodeb` | inside | 42,747,365 | 6,259,686 | 20,048,523 | 0.31 | 0.6807 | 0.8723 |
| `rgb3_nodeb` | outside | 1,356,897 | 2,733,412 | 3,011,156 | 0.91 | 0.3106 | 0.3317 |
| `nodec_v1` | all | 49,511,053 | 11,820,312 | 17,652,888 | 0.67 | 0.7372 | 0.8073 |
| `nodec_v1` | inside | 47,892,956 | 8,862,327 | 14,902,932 | 0.59 | 0.7627 | 0.8439 |
| `nodec_v1` | outside | 1,618,097 | 2,957,985 | 2,749,956 | 1.08 | 0.3704 | 0.3536 |

CAUTION: one reference (C-CAP 2016) applied to a 2009 raster, at one
threshold. Real 2009->2016 change lands in FP/FN too, and the reference's own
errors are not modelled. Read the DIRECTION, not the magnitude.


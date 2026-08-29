# FP/FN balance by region — 2009, threshold 0.5

FP = reference says NOT canopy, model says canopy (over-prediction).
FN = reference says canopy, model says not (under-prediction).
`FP:FN` above 1 means the region OVER-predicts; below 1, under-predicts.

| arm | region | TP | FP | FN | FP:FN | recall | precision |
|---|---|---|---|---|---|---|---|
| `rgb3_nodeb` | all | 44,104,262 | 8,993,098 | 23,059,679 | 0.39 | 0.6567 | 0.8306 |
| `rgb3_nodeb_s1234` | all | 43,661,151 | 8,314,614 | 23,502,790 | 0.35 | 0.6501 | 0.8400 |
| `rgb3_ep60` | all | 46,997,725 | 10,900,788 | 20,166,216 | 0.54 | 0.6997 | 0.8117 |
| `rgb3_ep60_s1234` | all | 45,513,460 | 9,410,428 | 21,650,481 | 0.43 | 0.6776 | 0.8287 |

CAUTION: one reference (C-CAP 2016) applied to a 2009 raster, at one
threshold. Real 2009->2016 change lands in FP/FN too, and the reference's own
errors are not modelled. Read the DIRECTION, not the magnitude.


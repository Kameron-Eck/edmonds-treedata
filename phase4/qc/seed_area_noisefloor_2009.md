# FP/FN balance by region — 2009, threshold 0.5

FP = reference says NOT canopy, model says canopy (over-prediction).
FN = reference says canopy, model says not (under-prediction).
`FP:FN` above 1 means the region OVER-predicts; below 1, under-predicts.

| arm | region | TP | FP | FN | FP:FN | recall | precision |
|---|---|---|---|---|---|---|---|
| `fullext_sectors_v1` | all | 46,943,745 | 8,465,526 | 20,220,196 | 0.42 | 0.6989 | 0.8472 |
| `seed1234` | all | 44,868,045 | 7,362,202 | 22,295,896 | 0.33 | 0.6680 | 0.8590 |
| `seed777` | all | 47,089,135 | 8,611,202 | 20,074,806 | 0.43 | 0.7011 | 0.8454 |

CAUTION: one reference (C-CAP 2016) applied to a 2009 raster, at one
threshold. Real 2009->2016 change lands in FP/FN too, and the reference's own
errors are not modelled. Read the DIRECTION, not the magnitude.


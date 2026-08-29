# FP/FN balance by region — 2009, threshold 0.5

FP = reference says NOT canopy, model says canopy (over-prediction).
FN = reference says canopy, model says not (under-prediction).
`FP:FN` above 1 means the region OVER-predicts; below 1, under-predicts.

| arm | region | TP | FP | FN | FP:FN | recall | precision |
|---|---|---|---|---|---|---|---|
| `fullext_sectors_v1` | all | 46,943,745 | 8,465,526 | 20,220,196 | 0.42 | 0.6989 | 0.8472 |
| `corrupt10` | all | 51,364,093 | 11,807,011 | 15,799,848 | 0.75 | 0.7648 | 0.8131 |
| `corrupt25` | all | 37,970,649 | 4,736,761 | 29,193,292 | 0.16 | 0.5653 | 0.8891 |
| `corrupt50` | all | 43,229,573 | 7,373,601 | 23,934,368 | 0.31 | 0.6436 | 0.8543 |

CAUTION: one reference (C-CAP 2016) applied to a 2009 raster, at one
threshold. Real 2009->2016 change lands in FP/FN too, and the reference's own
errors are not modelled. Read the DIRECTION, not the magnitude.


# FP/FN balance by region — 2009, threshold 0.5

FP = reference says NOT canopy, model says canopy (over-prediction).
FN = reference says canopy, model says not (under-prediction).
`FP:FN` above 1 means the region OVER-predicts; below 1, under-predicts.

| arm | region | TP | FP | FN | FP:FN | recall | precision |
|---|---|---|---|---|---|---|---|
| `fullext_sectors_v1` | all | 46,943,742 | 8,465,529 | 20,220,204 | 0.42 | 0.6989 | 0.8472 |
| `seed1234` | all | 44,868,045 | 7,362,202 | 22,295,901 | 0.33 | 0.6680 | 0.8590 |
| `seed777` | all | 47,089,131 | 8,611,206 | 20,074,815 | 0.43 | 0.7011 | 0.8454 |
| `chm2_v1` | all | 45,602,001 | 7,320,342 | 21,561,945 | 0.34 | 0.6790 | 0.8617 |
| `corrupt10` | all | 51,364,092 | 11,807,012 | 15,799,854 | 0.75 | 0.7648 | 0.8131 |
| `corrupt25` | all | 37,970,650 | 4,736,760 | 29,193,296 | 0.16 | 0.5653 | 0.8891 |
| `corrupt50` | all | 43,229,571 | 7,373,603 | 23,934,375 | 0.31 | 0.6436 | 0.8543 |
| `rgb3_nodeb` | all | 44,104,258 | 8,993,102 | 23,059,688 | 0.39 | 0.6567 | 0.8306 |
| `rgb3_nodeb_s1234` | all | 43,661,147 | 8,314,618 | 23,502,799 | 0.35 | 0.6501 | 0.8400 |
| `rgb3_ep60` | all | 46,997,719 | 10,900,794 | 20,166,227 | 0.54 | 0.6997 | 0.8117 |
| `nodec_v1` | all | 49,511,050 | 11,820,315 | 17,652,896 | 0.67 | 0.7372 | 0.8073 |
| `nodec_s1234` | all | 51,401,537 | 14,904,561 | 15,762,409 | 0.95 | 0.7653 | 0.7752 |
| `hybrid_v1` | all | 41,996,864 | 5,772,683 | 25,167,082 | 0.23 | 0.6253 | 0.8792 |

CAUTION: one reference (C-CAP 2016) applied to a 2009 raster, at one
threshold. Real 2009->2016 change lands in FP/FN too, and the reference's own
errors are not modelled. Read the DIRECTION, not the magnitude.


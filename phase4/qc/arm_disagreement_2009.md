# Where same-recipe arms disagree — 2009

Arms: `fullext_sectors_v1`, `seed1234`, `seed777` · class threshold 0.5

`mean spread` = average (max-min) of the arms' DN on that ground, in DN units
(0-254, so 2.54 DN = 1 percentage point of probability).
`disagree` = share of pixels the arms do not all put on the same side of the
threshold — the disagreement that actually changes a map.

| region | ref class | pixels | mean spread (DN) | disagree |
|---|---|---|---|---|
| all | canopy | 67,163,941 | 17.35 | 7.59% |
| all | non-canopy | 131,606,723 | 12.52 | 2.85% |
| inside | canopy | 62,795,888 | 17.24 | 7.45% |
| inside | non-canopy | 60,027,271 | 13.65 | 4.35% |
| outside | canopy | 4,368,053 | 18.94 | 9.60% |
| outside | non-canopy | 71,579,452 | 11.58 | 1.59% |

Reading it: disagreement on reference CANOPY means the runs cannot agree on
real trees; disagreement on NON-CANOPY means they cannot agree on what is not a
tree. Different problems, different fixes — which is why the split is here.


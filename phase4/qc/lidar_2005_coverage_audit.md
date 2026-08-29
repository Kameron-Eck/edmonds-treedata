# 2005 lidar — coverage and cell-size gate (S3.1)

## Q1 — coverage and density (header-only)

| | 2005 (PSLC) | 2016 (USGS) |
|---|---|---|
| tiles | 47 | 41 |
| total returns | 71,972,507 | 863,525,719 |
| bbox-union area | 40.08 km² | 47.91 km² |
| density, median | **1.61 pts/m²** | 17.39 |
| density, range | 0.00 – 2.35 | 0.00 – 29.47 |

2005 bbox-union covers **83.6%** of the 2016 union area.

> Coverage is comparable; the gate does not block on Q1.

## Q2 — ground-return occupancy by cell size (2005, measured)

`build_chm2_2016.py` chose a 2.0 m ground grid because ~80% of 2 m cells
held a ground return in the 2016 cloud. This is that same measurement for
2005 — it must not be assumed.

| cell | cells | any return | >= min-pts | **any GROUND return** |
|---|---|---|---|---|
| 1 m | 69,418,389 | 49.1% | 12.2% | **44.6%** |
| 2 m | 17,350,275 | 51.3% | 50.6% | **69.5%** |
| 3 m | 7,712,450 | 51.3% | 51.3% | **80.3%** |
| 4 m | 4,335,408 | 51.4% | 51.3% | **86.5%** |
| 5 m | 2,774,730 | 51.4% | 51.4% | **90.5%** |

`any GROUND return` is computed over cells the cloud actually covers,
not over the whole bbox — the bbox includes water and out-of-swath area.

**Read it against the 2016 precedent (~80% at 2 m).** The smallest cell
reaching a comparable fraction is the defensible ground-grid size for a 2005
build; the canopy grid can be finer, since a canopy cell needs any return,
not a ground return.

## What this does NOT establish

- Vertical accuracy. The 2005 record carries two figures that must both be
  recorded and never averaged: 6.3 cm fundamental (Digital Coast) and
  25 cm avg / 15-25 cm soft-vegetated (InPort).
- Whether a 2005 CHM improves the model. That is S3.5, and it needs shared
  normalisation stats and 3 seeds per arm, or it repeats the underpowered
  chm2 test.


## Verdict (added after reading Q2)

**Build is justified, at 2 m canopy / 3 m ground — NOT the 2016 build's 0.5 m / 2.0 m.**

- **Ground grid 3 m.** 80.3% occupancy, matching the ~80% at 2 m that justified the
  2016 choice. At 2 m the 2005 cloud gives only 69.5% — thinner than the precedent it
  would have been copied from.
- **Canopy grid 2 m.** Only 12.2% of 1 m cells hold the >= 3 returns needed to trust a
  per-cell maximum; 50.6% at 2 m.

### The limitation this exposes, stated before building

A 2005 CHM would be **4x coarser than chm2**, and that lands in the worst place: the
height channel's ~10 pp is *concentrated in small crowns* (+7.3 pp under 5 m2, ~2.2 m
across). A 2 m cell is the size of the crowns it most needs to resolve. So the trade is
**temporally native but 4x coarser**, and whether a correct-era 2 m height beats a
7-years-wrong 0.5 m height is empirical — it should not be assumed in either direction.

### Caveats on Q1

- The 83.6% coverage figure is a **bounding-box** ratio. Q2 shows "any return" plateaus
  at ~51%, i.e. roughly half the 2005 bbox is water or out-of-swath (Puget Sound is on
  the western edge). The bbox ratio is only the right comparison if 2016's bbox has a
  similar water fraction, which was not measured here.
- 2016's local density measures **17.39 pts/m²**, not the 4-5 recorded in IMAGERY_FACTS
  (which is a dataset-wide average over 13,205 tiles, not these 41). The real
  inter-epoch density gap is therefore **~10.8x**, not the ~3x concluded when only the
  2005 side had been measured locally.

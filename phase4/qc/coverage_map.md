# COVERAGE MAP — how far each acquisition has travelled — GENERATED

Regenerate: `py -3.12 qc/coverage_map.py` (drift-gated by `test_run_context.py::test_coverage_map_is_fresh`).

A blank cell means **no record**, never *should have been done*. Some
acquisitions are deliberately out of scope — the Atlas trend is 2016→2024,
and several deliveries exist only as overlap controls. Telling deliberate
from overlooked is a decision, not a measurement, and this file does not
make it. `py -3.12 qc/ask.py <label>` opens any single row in full.

| acq | gsd | bands | tile sets | tiles | tile dirs | train runs | arms scored | matched cut | best AP | champion | entries |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2000 | 40.1 | 3 | 1 | 584 | 1 | 1 | 2 |  |  |  | 4 |
| 2002 | 30.0 | 3 | 1 | 304 | 1 |  | 1 |  |  |  | 2 |
| 2002s | 30.5 | 3 |  |  |  |  |  |  |  |  |  |
| 2003s | 30.5 | 3 |  |  |  |  | 1 |  |  | sectors_v1 | 2 |
| 2005 | 20.1 | 3 | 1 | 605 | 1 |  | 1 |  |  | citywide_rgb | 1 |
| 2006s | 100.0 | 3 | 8 | 1464 | 11 | 15 | 7 | 17 | 0.8249 | sectors_v1 | 9 |
| 2007 | 20.1 | 3 | 1 | 567 | 1 | 2 | 2 |  |  | citywide_rgb | 1 |
| 2007s | 30.5 | 3 |  |  |  |  |  |  |  |  |  |
| 2009 | 20.1 | 3 | 10 | 6124 | 18 | 24 | 14 | 1 | 0.8100 | citywide_rgb | 5 |
| 2009s | 30.5 | 3 |  |  |  |  |  |  |  |  |  |
| 2011s | 30.5 | 3 | 11 | 3707 | 23 | 27 | 16 | 30 | 0.8660 | sectors_v1 | 11 |
| 2012s | 22.9 | 3 |  |  |  |  | 1 |  |  | sectors_v1 | 2 |
| 2013 | 10.0 | 3 | 2 | 1256 | 2 | 2 | 3 | 1 | 0.8116 |  | 6 |
| 2013s | 100.0 | 3 |  |  |  |  |  |  |  |  |  |
| 2015 | 10.0 | 3 | 2 | 934 | 2 | 1 | 2 | 1 | 0.7746 |  | 5 |
| 2015n | 100.0 | 4 |  |  |  |  |  |  |  |  |  |
| 2015s | 30.5 | 3 |  |  |  |  |  |  |  |  |  |
| 2016 | 30.5 | 4 | 10 | 5311 | 14 | 17 | 11 | 20 | 0.9069 |  | 17 |
| 2017 | 5.0 | 3 | 2 | 1291 | 3 | 3 | 3 | 2 | 0.7962 |  | 1 |
| 2017k | 10.0 | 3 | 1 | 632 | 3 | 3 | 1 | 1 | 0.8223 |  | 2 |
| 2017n | 100.0 | 4 | 1 | 582 | 1 | 1 | 1 | 1 | 0.7012 |  |  |
| 2017s | 30.5 | 4 | 1 | 557 | 1 | 1 | 1 | 1 | 0.8191 |  |  |
| 2018s | 15.2 | 4 | 1 | 599 | 1 | 1 | 2 |  |  | sectors_v1 | 1 |
| 2019 | 10.0 | 3 | 3 | 1792 | 3 | 3 | 3 | 1 | 0.8093 | citywide_rgb | 5 |
| 2019n | 60.0 | 4 | 5 | 1929 | 6 | 6 | 5 | 4 | 0.8105 | p2nir | 7 |
| 2019s | 30.5 | 4 | 1 | 561 | 1 | 1 | 1 |  |  |  | 3 |
| 2020 | 5.0 | 3 | 8 | 5241 | 12 | 11 | 7 | 12 | 0.8064 |  | 6 |
| 2020s | 7.6 | 3 |  |  |  |  | 1 |  |  | sectors_v1 | 1 |
| 2021 | 10.0 | 3 | 2 | 1220 | 2 | 1 | 2 | 1 | 0.8391 | citywide_rgb | 4 |
| 2021n | 60.0 | 4 |  |  |  |  |  |  |  |  |  |
| 2021s | 15.2 | 4 | 1 | 705 | 1 | 8 | 7 |  |  | p2nir | 2 |
| 2022 | 5.0 | 3 | 2 | 1226 | 2 | 2 | 2 | 1 | 0.7848 | citywide_rgb | 1 |
| 2022s | 7.6 | 3 |  |  |  |  |  |  |  |  |  |
| 2023 | 10.0 | 3 | 2 | 1181 | 2 | 1 | 1 |  |  | citywide_rgb | 3 |
| 2023n | 60.0 | 4 |  |  |  |  | 1 |  |  |  | 2 |
| 2024 | 5.0 | 3 | 2 | 1254 | 2 | 4 | 3 | 1 | 0.7449 | citywide_rgb | 3 |
| 2024s | 7.6 | 3 |  |  |  |  |  |  |  |  |  |

**37 acquisitions.** No tile set: **13** · never scored: **9** · no matched-cut read: **21** · no champion: **21**.

Columns: *tile sets* counts distinct `tileset_id` in `tileset_registry.csv`; *tiles* sums `n_tiles` over those DISTINCT sets. *tile dirs* counts registry ROWS — one per tile directory, so one set materialised under two run tags is one set and two directories (archive-wide: 80 sets in 115 directories). Summing over rows instead double-counts — why, and what it once got wrong, is in `docs/SCHEMAS.md`. *train runs* counts `step=train` rows in `run_passport.csv`. *arms scored* and *matched cut* count distinct arms in `arm_metrics.csv`; *best AP* is the highest average precision recorded at any cut. *champion* is `pipeline/champion_arms.csv`. *entries* counts registry entries naming this acquisition.

# EXPERIMENT REGISTRY INDEX — GENERATED, do not edit

Regenerate: `py -3.12 qc/experiments_index.py` (drift-gated by `test_experiments.py::test_index_is_fresh`).
Authored layer + schema: this directory's `README.md`. 11 entries: 7 complete · 3 queued · 1 tabled.

## All entries (newest decided first)

| entry | kind | status | decided | N | imagery | headline |
|---|---|---|---|---|---|---|
| overlap_floor | experiment | complete | 2026-09-06 | — | — | All three pre-registered reads complete, at policy-C matched cuts (the rule as written; delivered-cut fractions were never valid inputs). |
| trend8_uniform_rgb | experiment | complete | 2026-09-06 | — | — | DELIVERED-CUT SERIES RETRACTED as a trend read (per-arm best-F1 cuts on 650x-skewed eval populations; the 2026-09-06 attack). |
| panel_a_direction | measurement-campaign | complete | 2026-09-04 | 1250 | 2016,2024 | DIRECTION IS DOWN, and it is the project's only human-measured trend statement. |
| sameflight_floor_c3 | instrument-finding | complete | 2026-09-04 | 1 | 2019s,2019n | THE FLOOR EXISTS AND IT IS LARGE ENOUGH TO MATTER. |
| tier1_science_sample | experiment | complete | 2026-09-03 | — | — | Floor (max pairwise /delta/ among 2011s base/s2/s3, recall@prec0.75 test blocks) = 0.0085. |
| hard_year_pilot | experiment | complete | 2026-09-01 | — | — | MIXED, read per the rule. |
| deeplab_arm | experiment | tabled | 2026-08-31 | — | — | TABLED by Kam 2026-08-31 before any GPU run. |
| pilot_2019 | experiment | complete | 2026-08-31 | — | 2019,2019s,2019n | 3/3 GATE PASS 2026-08-31 04:36Z. |
| degradation_synth_2000 | experiment | queued | — | — | — | Training on 2020 imagery synthetically degraded to 2000's measured resolution and radiometry (resample-first, gain-only — qc/instruments/degrade_synth.py) beats the plain citywide-projection arm on 20… |
| full_archive_e3 | experiment | queued | — | — | — | The hard-year pilot confirmed the unified citywide EPOCH-3 recipe explains the historical weak tail (2011s 0.471 -> 0.756; 2006s 0.470 -> 0.707 with three measured imagery strikes). |
| resolution_1x2x4 | experiment | queued | — | — | — | The measured coarse-over-medium gap (support-matched, program-confound narrowed to one flight processed two ways) is a genuine resolution effect: ONE acquisition trained at native, 2x and 4x downsampl… |

★ = owns a champion arm (pipeline/champion_arms.csv). N = the gated n/n_source pair. Full join: `index.json`; provenance + pointers: each entry's yaml.

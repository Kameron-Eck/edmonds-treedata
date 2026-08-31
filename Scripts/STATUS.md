# Project status - GENERATED, do not hand-edit

Regenerate: `py -3.12 qc/pipeline_status.py --markdown`

<!-- STATUS:code:begin -->
### Derived from the code — regenerated and gated in CI

| fact | value |
|---|---|
| engine | `phase4seg v048` |
| acquisitions | **36** |
| calendar years | **20** (2000-2024) |
| GSD span | **5 - 100 cm** |
| GSD histogram | 5x4  7.6x3  10x5  15.2x2  20.1x3  22.9x1  30x1  30.5x9  40.1x1  60x3  100x4 |
| NIR-bearing (`bands>=4`) | **10** - 2015n 2016 2017n 2017s 2018s 2019n 2019s 2021n 2021s 2023n |
| RGB-only | **26** |
| seg tiers | coarse 10  fine 12  medium 14 |
| DAG stages | 16 (0 with a missing script) |

Every number above is read from `pipeline/phase4seg/config.py:YEAR_CATALOG` and
`pipeline/dag.yaml` at generation time. Do not hand-edit this block - regenerate
with `py -3.12 qc/pipeline_status.py --markdown`.
<!-- STATUS:code:end -->

### Derived from the data lake - generated 2026-08-30 21:45

**This half is only as current as the last run of this script.** CI cannot
regenerate it (no Drive mount), so it is NOT gated. Treat every number below
as of the timestamp above, not as of now.

#### Scored results - repo copy vs lake

| copy | rows | live | years | newest |
|---|---|---|---|---|
| repo | 217 | 181 | 24 | 2026-08-30 21:36:10 |
| lake | 217 | 181 | 24 | 2026-08-30 21:36:10 |

_per-year table unavailable: ImportError: `Import tabulate` failed.  Use pip or conda to install the tabulate package._


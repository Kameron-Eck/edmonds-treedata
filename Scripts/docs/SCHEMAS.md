# SCHEMAS — the data contracts, one home

**Why this file exists**: agents (and people) misread columns when the meaning lives
only in writer code — two real misreads on 2026-08-31 alone (`source` read for
`date_shot`; `n_targets` read as the fit's point count). Each table below names the
WRITER by symbol, so `test_citations_resolve` fails this doc the day a writer moves
or is renamed. Column lists are copied from live headers, not from memory. This doc
describes SHAPE and MEANING; it never restates values (one fact, one home).

## run_registry.csv (Scripts/, authored+appended per landed run)

One row per engine step that produced a result worth provenance. Appended by hand or
by the session that ran the step; CHATLOG rule 3.12(c).

| column | meaning |
|---|---|
| `run_id` | `{UTC}_{year}_{tag}_{step}` — unique, sortable |
| `date` | calendar date of the run |
| `year` | acquisition label (`2019n`, not the calendar year) |
| `step` | one of the six per-year steps |
| `gpu_name` | as reported by the runtime (`NVIDIA L4`, …) |
| `step_minutes` | wall-clock of the step alone |
| `script_version` | `vNNN (shortsha on branch)` — the CODE identity |
| `args` | the exact engine flags |
| `headline_metrics` | short human summary; the authoritative numbers stay in qc_indep |
| `model_path` / `mask_path` | lake-relative artifact pointers |
| `notes` | queue/VERIFY outcome, seed, anything a reader needs to trust the row |

## train_queue_status_*.csv (lake `phase4/qc/`, the LEDGER)

Written by `phase4_train_queue.py::run_step` (RUNNING row first, terminal row after);
one file per launch, and every reader must merge ALL of them —
`names.py::status_files` is the ONE discovery rule, `names.py::job_key` the ONE row
key `(job, year, tag, step)`. State vocabulary: `names.py::BAD_STATES` and friends —
never restate the set. Columns: `job, year, tag, step, state, exit, minutes, detail,
host, session, ts`. `VERIFY:{step}` rows carry artifact verification verdicts;
resume credit logic is `phase4_train_queue.py::_completed_steps`.

## qc_indep_report.csv (lake `phase4/qc/`, honest scores)

Written by `phase4_qc_indep.py::main`. One row per (year, ref, canopy_def, thresh).
**Reader rules that are not optional**: filter `live == 1`; `primary` marks the
headline row; `canopy_def == "forest_wetland"` is the primary class mapping.
Columns: `year, ref, prob, canopy_def, thresh, recall, precision, grass_reject, tp,
fn, fp, ref_canopy, valid, indep_1m_cells, primary, live, run_tag, ts`.
`prob` is the scored raster's name — `champion.py::prob_arm` recovers the arm tag.

## champion_arms.csv (Scripts/pipeline/, AUTHORED decision)

The machine-readable answer to "which arm is the deliverable for year Y".
Columns: `year, tag, run_id, why`. Promotion = editing this file in a commit;
history = its git log. Years with multiple live arms are ABSENT until Kam names
them — `champion.py::load_champions` and every consumer list them, never guess.

## imagery_pixelsize_and_date.csv (Scripts/qc/, evidence-graded facts)

One home for GSD + acquisition dates (memory: never rerun its builder). Key columns:
`file, year_label, …, true_ground_cm, effective_cm, native_flight_cm, date_shot,
date_precision, …, evidence_grade, source_url, verbatim_quote, …, row_type`.
**`effective_cm` is the measured resolution — nominal GSD lies** (2005: nominal 20,
resolves at 80.7). `date_shot` is the flight date; `source` columns are provenance
URLs, not dates. `verbatim_quote` carries the exact source text behind the grade.

## STATUS.json (Scripts/, GENERATED — regenerate, never edit)

Written by `pipeline_status.py::write_status_json`. Top-level: `generated_utc`,
`lake_mounted`, `code` (repo-derived facts, gated by
`test_status_discovery.py::test_status_json_code_block_matches_the_code`),
`champions` (year → tag; null when the lake is unmounted), `years` (one object per
acquisition: artifact presence, VERIFY states, honest champion numbers), `note`.
Agents: query this file; do not parse STATUS.md.

## imagery_geometry.csv (phase4/qc/, GENERATED — regenerate, never edit)

Written by `imagery_geometry.py::measure_one` over every YEAR_CATALOG raster; one
row per acquisition, measured with rasterio from the file itself. Key columns:
`crs_auth` (measured EPSG), `unit_name` (metre vs **US survey foot** — 17 of 36),
`px_x_m_naive` (CRS-units×factor: what unit-blind code computes) vs
`px_ground_x_m` (warped into the analysis grid: what the ground says) and
`crs_metric_inflation_pct` (their gap: +48.7% for every EPSG:3857 file here);
`origin_aligned_to_px` (grid congruence — the measurable half of same-flight/
different-delivery questions); `epsg_match` / `gsd_vs_catalog_pct` (disagreement
flags vs YEAR_CATALOG — 0 flagged 2026-09-01). Plus the statistics columns (2026-09-01): `city_bounds_coverage_pct` (footprint
vs the dissolved city polygon on the analysis grid — the denominator question),
`black_px_pct_in_city` (decimated collar/void estimate; `SKIPPED(drive)` for the
rasters only Drive holds), `mmu_effective_m2` (what the CRS-unit sieve removes in
true m² for THIS year). Gate:
`test_analysis_grid.py::test_geometry_table_exists_with_the_contract_columns`.

## acquisition_passport.csv (phase4/qc/, GENERATED — regenerate, never edit)

Written by `acquisition_passport.py::main`: ONE row per acquisition, joining the five
fact homes (catalog, geometry table, pixelsize/date table, champion_arms, live
qc_indep scores). A reading view — fixes go to the SOURCE, then regenerate; the
freshness gate (`test_analysis_grid.py::test_passport_is_fresh`) fails when the view
disagrees with a home. Rendered with the stage DAG and the stats pre-flight on the
Pipeline Atlas artifact page.

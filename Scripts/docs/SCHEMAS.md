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
fn, fp, ref_canopy, valid, indep_1m_cells, primary, live, run_tag, aoi, ts`.
`prob` is the scored raster's name — `champion.py::prob_arm` recovers the arm tag.
`aoi` (Tier 1, 2026-09-02): non-empty means the score is RESTRICTED to sample
ground blocks (`--aoi` + manifest CSV) — AOI is part of the live-row lineage and
restricted rows must NEVER be pooled or compared with citywide rows. Dense-sweep
files for restricted runs carry the aoi name as a filename suffix for the same
reason.

## qc_indep_sweep_{year}_{arm}_{refstem}.csv (lake `phase4/qc/`, GENERATED dense curve)

Written by `phase4_qc_indep.py::_write_dense_sweep` on every scoring run. One row
per integer cut `k` = 1..254 — the EXACT recall/precision/F1 curve on the primary
canopy definition, from two 256-bin histograms (raw prob, no morphology — measured
neutral, `Reports/RECIPE_AUDIT_2026-09-01.md`). File per (year, arm, ref): a re-run
overwrites its own lineage only. Columns: `year, run_tag, ref, prob, canopy_def, k,
thresh, tp, fn, fp, recall, precision, f1, ts`. `thresh = k/254` round-trips through
postproc's `int(round(thr*254))` to the same integer — selected cut == deployed cut.
This file is the INPUT to threshold policy C; publish it beside any score it selected.

## indep_thresholds.csv (lake `phase4/qc/`, the policy-C selection registry)

Written by `select_indep_threshold.py::main` (policy C — Kam, 2026-09-01). One row
per (year, run_tag, ref), replace-by-key. Columns: `year, run_tag, ref, criterion,
k, thresh, f1, recall, precision, edge_flag, sweep_file, ts`. `criterion` is the
pre-registered rule (`f1_plateau_hi_d005`: highest k within 0.005 of peak F1 —
the precision-most end of the metric-indifferent plateau);
`edge_flag == "EDGE"` means the peak sat within 5 steps of the grid edge — inspect
before deploying. `thresh` is k/254 FLOOR-truncated to 6 dp so production's
`int(round(thr*254))` and the scorer's `pr >= thr*254` both cut at exactly k.
Deployment: `--step postproc --infer-thresh <thresh>`.
**Reader rule**: never pool scores across threshold policy — an arm cut at a
policy-C threshold and a champion cut at the circular `best_f1_thresh` are
different operating-point populations; this registry (plus `run_tag`) is what
separates them. Non-default `ref` rows are sensitivity checks, not deployments.

## hw_{session}.csv (lake `phase4/logs/`, RAW hardware telemetry)

Written by `pipeline/vm_hwlogger.py::main` (launched by every bootstrap from
2026-09-02; 5 s samples, one buffered Drive write per minute). Kernel + NVIDIA
counters only — no pipeline code in the measurement path. **LEGACY (v1)
columns**: `ts_utc, gpu_util_pct, gpu_mem_util_pct, gpu_mem_used_mb,
gpu_power_w, cpu_pct, disk_read_mb_s, disk_write_mb_s, net_rx_mb_s,
net_tx_mb_s, disk_used_gb, disk_free_gb`. Reader notes: net rx/tx IS the Drive
traffic (rclone is HTTPS); disk_* is local NVMe; blank cells mean the sampler
failed that tick (CPU runtimes have blank GPU columns) — blanks are honest,
never zeros.

**v2 appends three columns**, in this order: `cpu_iowait_pct, step, run_tag`.
`cpu_iowait_pct` is `100 * delta(iowait ticks) / delta(total ticks)` over the
sample interval — the counter the v1 schema could not see, because
`vm_hwlogger.py::cpu_ticks` folds iowait into idle, so a process blocked on
Drive FUSE reads as an idle CPU. **`cpu_pct` keeps its v1 definition** (busy =
total − idle − iowait) so the two schemas remain comparable on that column.
`step` / `run_tag` are read at each sample from the step marker file
(`phase4seg/names.py::hw_step_marker_path`), written by `StepLogger.start()`
and deleted by `.finish()`: **the marker's absence means between steps**, and
blank `step` cells mean exactly that. `step` carries the year suffix as passed
(`train_2017`), never normalised at write time.

**One file, one schema.** If `hw_{session}.csv` exists with a v1 first line the
logger writes `hw_{session}_v2.csv` instead rather than appending rows of a
different width — so one session can own two files, and `_v2` in a filename is
the SCHEMA, not the session name.

## hw_step_attribution.csv (phase4/qc/, HARVESTED — re-harvest, never edit)

Written by `qc/instruments/harvest_hw_attribution.py::build_rows` from the raw
`hw_*.csv` above plus the step logs. One row per `(session, step, basis)` and one
`step = ALL` row per `(session, basis)`; `step` values are the engine step with
its year label stripped (`train_2017` → `train`), plus `(between)` for samples
with no step running. The basis is decided PER FILE, so a session owning both a
v1 and a v2 file (see the fork rule above) emits two independent sets of rows —
the marker samples keep their own per-machine `step` instead of being re-guessed
by time against another VM's step log. Columns: `session, step, basis,
gpu_present, samples, hours, gpu_busy_frac, gpu_util_mean, cpu50_frac,
iowait10_frac, tx1_frac, rx1_frac, disk5_frac, nothing_frac, ambiguous_dropped,
samples_parsed, span_hours, source_file`. Fractions are of the row's samples (GPU
fractions of the samples that HAVE a GPU reading), and are BLANK on a row with no
samples.

`gpu_present` is the fraction of the row's samples that carry a **non-blank
`gpu_util_pct`** — 1.0000 on a GPU runtime, 0.0000 on a CPU one, and blank on a
row with no samples. It is the column that tells a CPU-only session apart from a
GPU session whose sampler failed, which is why `nothing_frac` may treat an absent
GPU reading as idle and must treat every other absent reading as unknown.

**Per-row vs group constant.** `samples, hours, gpu_present, gpu_busy_frac,
gpu_util_mean` and every `*_frac` describe THAT row's samples. `basis,
ambiguous_dropped, samples_parsed, span_hours` and `source_file` are constants of
the whole `(session, basis)` group, **repeated on every one of its rows** so a
reader who slices to a single step still sees the denominators — never sum them
across a group's rows.

**READER RULE: three denominators, and two of them are missing time.** The `ALL`
row pools ATTRIBUTED samples only — `samples_parsed` = `ALL.samples` +
`ambiguous_dropped` — so **`ALL.hours` is not the session's wall clock and must
not be summed as "VM time"**. `hours` is SAMPLED time (samples × the file's own
measured cadence), so a stalled logger under-counts it; `span_hours` is the
covered wall clock (last − first `ts_utc` over that `(session, basis)` group's
parsed rows, NOT over the session — a dual-schema session owns two groups, and
summing their spans would double its run) and `span_hours − hours` is time the
logger never sampled. Measured 2026-09-07 across the 18 archived sessions the
three read 72.63 h covered / 60.35 h sampled / 48.82 h attributed, so ALL.hours
is a third below the wall clock. A session whose every sample was
ambiguity-dropped still gets its `ALL` row, with `samples = 0` and blank
fractions: a machine that ran is never absent from the table. Since 2026-09-07
that also holds when the file parses to no samples AT ALL (header-only, or every
`ts_utc` unreadable): `samples_parsed = 0`, `hours = span_hours = 0.0000`, blank
fractions. Zero samples is a finding about the logger; an absent row is
indistinguishable from a VM that never existed.

**READER RULE: `basis` gates how much a row is worth**, the same way
`join_basis` gates `run_passport`. `marker` = the v2 `step` column **with at
least one non-blank cell in it**, so each sample names its own step on its own
machine — trustworthy. A v2 file whose `step` column is present but entirely
blank is DEMOTED to `interval` and says so in its `source_file` cell (`[v2 step
column present but blank -> interval basis: …]`): blank has two causes the column
cannot separate — genuinely between steps, or a VM where
`pipeline_log.py::StepLogger` never managed to publish a marker — and a file that
never once carried one has demonstrated nothing about the mechanism. Choosing the
basis on the column's mere PRESENCE (the rule until 2026-09-07) published such a
file as a 100% `(between)` machine on the trusted tier. `interval` = the
legacy files, joined by TIME to the step LOGS, which carry no session or host
field; the queue status CSVs that do carry `session` cover only 1 of the 18
archived hw sessions (`of2017k2`, 13 rows; the repo-tracked copies carry none —
measured 2026-09-07), so they cannot rescue the legacy archive, though that one
session is an independent per-machine record the interval rule could be checked
against. Samples whose concurrently-open intervals disagree are DROPPED and
counted in `ambiguous_dropped` (repeated on every row of that `(session,
basis)` group, so a reader slicing to one step still sees it); the sessions
overlap heavily, so this is a large share of the archive — 8,304 of the 29,001
samples in the 12 GPU-bearing sessions, measured 2026-09-07. What survives the drop can still be another
VM's step — an `interval` row can attribute `train` hours to a CPU-only runtime
that cannot run torch at all. Interval rows are indicative; marker rows are
measured.

`nothing_frac` is the finding, not a residual: GPU < 5% AND CPU < 15% AND
disk < 5 MB/s AND **both** network directions < 1 MB/s at once. That is a
process blocked on Drive FUSE per-file latency — round-trips cost no bandwidth,
and iowait is charged to idle in v1 — not a machine with nothing to do. The
network test covers TX as well as RX because checkpoint uploads are the single
largest thing train does that is not training. `iowait10_frac` is blank for
every v1 file: the column did not exist, which is not the same as zero.

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

## coregistration.csv (phase4/qc/, GENERATED — regenerate, never edit)

Written by `coregistration.py::measure_pair`: one row per acquisition vs the 2020s
anchor (constant ~64 m ground chips on the analysis grid, phase correlation,
self-rejecting anchors — `n_used`/`n_tried` records selectivity). READER RULES:
`median_dx_m`/`median_dy_m` is registration proper (systematic offsets are
correctable at comparison time — six years flagged >=1 m incl. 2013s at 2.2 m and
2024 at 1.2 m); `p95_mag_m` is a CONSERVATIVE bound that includes building lean,
parallax and real change inside the chip, not pure georeferencing. The 2020 row is
the BRIDGE to the label source (p95 0.014 m) and is gated near-zero. Gate:
`test_analysis_grid.py::test_coregistration_table_contract`.

## The run-context layer (phase4/qc/, HARVESTED — re-harvest, never edit)

Four artifacts that answer "what did this run actually do, on which tiles, and how
well" from a checkout, with no lake mounted. All are DERIVED VIEWS: fixes go to the
source (a manifest, a sidecar, a sweep) and then re-harvest. Their gates are in
`qc/test_run_context.py` and are STRUCTURAL, not freshness — CI has no lake, so
"re-harvest and diff" cannot pass there. The one exception is
`year_scoreboard.md`, whose inputs are all tracked and which IS byte-compared.

### tileset_registry.csv + tilesets/{tileset_id}.csv

Written by `qc/instruments/harvest_tilesets.py`. ONE row per tile set, keyed by
`tileset_id` — 12 hex, the sha256 of the STORED `_tile_signature` (split_status
stripped by name via `config.META_NONSIG_KEYS`). The engine's own definition lives at
`phase4seg.tiling.tileset_id()` and the harvester imports it, so the two cannot drift
(`test_tileset_id_matches_the_engine`).

**Same ID means the same tiles.** That is what makes "these ten years ran on one tile
set" checkable rather than assumed, and `test_one_id_means_one_tile_set` enforces it.
`tilesets/{id}.csv` is the tile LIST — `row_off, col_off, split, block`, one row per
tile — written once and never rewritten, because a re-tile changes the signature and
therefore the ID. Lake-absolute image/mask paths are deliberately dropped: they say
where bytes live today, not what the set is. `id_basis: none` with a stated `note`
marks a directory whose sidecar is absent (the 6-site path writes none) — an empty ID
is legitimate, a fabricated one is not.

### run_passport.csv

Written by `qc/instruments/harvest_run_passport.py` from every
`phase4/runs/{run_id}/manifest.json`: commit + dirty flag + branch, GPU, seed AND
split_seed, arch/encoder, the imagery file each year resolved to with its GSD, label
sources with sizes, argv, and `env_sha` (a hash of pip freeze — the archive holds 37
distinct environments). READER RULE: **`join_basis` gates how much the `tileset_id`
column is worth.** `manifest` = the run stamped its own tile set after its steps ran,
trustworthy. `inferred_current` = inferred from `(year, run_tag)` → whatever that tile
dir holds TODAY, and a dir re-tiles in place, so it can name a set the run never saw.
`none` = no join. Historical runs are permanently `inferred_current`; only runs from
engines calling `cli._record_tilesets` earn `manifest`. `in_run_registry` flags the 16
manifests with no `run_registry.csv` row.

### arm_metrics.csv + curves/{curve_id}.csv

Written by `qc/instruments/harvest_arm_metrics.py`. **A precision/recall pair with no
operating point is not a measurement** — three deliveries of one 2017 flight read
10.09 pp apart at per-arm cuts and 1.07 pp apart at matched ones. So every row carries
`thresh`, the `policy` that chose it, `tp/fn/fp`, and `population`.

`curve_id` keys `(year, run_tag, ref, prob, canopy_def, eval_scope)`. **`eval_scope` is
load-bearing**: the LOSO `sample-selection` and `sample-test` halves are different
populations of the same arm, and omitting it collapsed 87 sweeps into 58 with the
first-written silently winning (found and fixed 2026-09-06;
`test_one_curve_id_means_one_population`).

`policy` is a CLOSED set (`harvest_arm_metrics.POLICIES`, gated):
`best_f1` is what shipped and is never valid for cross-arm comparison;
`matched_p50`/`p75`/`p90` are the steady points — highest recall at a held precision —
each with `n_eligible_cuts`, because a match found among a handful of cuts is a corner
artifact; `scored_live` is the cut the shipped mask was actually made at.
`pr_auc` is average precision, NOT AUROC: a sweep has no `tn`, and at ~650x class skew
AUROC reads optimistically high for everything. Real AUROC with CIs lives in
`chm_standalone_roc_*_arms.csv`. `curves/{id}.csv` is the full 254-cut sweep — the
primitive every scalar projects from.

### year_scoreboard.md (GENERATED — byte-compared)

Written by `qc/year_scoreboard.py`: best arm per year at ONE held policy
(`matched_p75` by default, printed in the file). Arms are grouped by `(ref,
eval_scope)` and ranked only within a group, with `population` shown — ranking across
populations is how a coverage gap gets misread as a skill gap (2017's deliveries span
15.8 M to 5.7 B scored pixels). Joins the tile counts and the champion star.
Gate: `test_run_context.py::test_year_scoreboard_is_fresh`.

## failure_registry.csv (phase4/qc/, HARVESTED) + qc/known_failures.yaml (AUTHORED)

Written by `qc/instruments/harvest_failures.py` from step logs with `errors: N>0`.
Two layers, deliberately: the CSV holds SYMPTOMS (exception class, normalised
signature, occurrence count, first/last seen, steps/years/tags, an example log);
`qc/known_failures.yaml` holds the CAUSE and the FIX, matched onto a symptom by regex.
No script can derive a mechanism, and the mechanism is the part worth keeping.

Signatures are normalised (paths, hex ids, timestamps, large integers, line numbers →
placeholders) so one bug is one row across runs. READER RULE: a row with
`status: undiagnosed` has an EMPTY `cause` by contract — it is a real finding, not a
gap in the file, and it surfaces in `py -3.12 qc/ask.py --gaps` until someone writes
the mechanism down. A status other than `undiagnosed` with no cause fails the gate
(`test_failure_registry_states_a_cause_or_says_it_has_none`).

## coverage_map.md (phase4/qc/, GENERATED — byte-compared)

Written by `qc/coverage_map.py`: one row per acquisition — tile sets, tiles, train
runs, arms scored, arms with a matched-cut read, best AP, champion, registry entries.
READER RULE: **a blank cell means "no record", never "should have been done."** Some
acquisitions are deliberately out of scope (the Atlas trend is 2016→2024; several
deliveries exist only as overlap controls), and separating deliberate from overlooked
is a decision this file does not make. Gate:
`test_run_context.py::test_coverage_map_is_fresh` plus a gate pinning that caveat.

## decisions.yaml + claims.yaml (Scripts/, AUTHORED)

**`decisions.yaml`** is the open-decision stack that used to be eight prose bullets on
the board: one entry each with `owner`, `status`, `why`, `evidence`, and the dependency
edges `blocks`/`blocked_by`. WORKPLAN.md now points here rather than restating it —
two homes for one stack is how the board and the ledger drifted apart before. READER
RULE: edges must be symmetric (if A blocks B, B is blocked_by A) and the graph acyclic;
both are gated, and the symmetry gate caught two one-sided edges on the first run.
A `decided` entry must carry BOTH a date and the decision text. View:
`py -3.12 qc/ask.py --decisions` (ready-first), or `ask.py <decision-id>` for one.

**`claims.yaml`** closes the claim↔evidence asymmetry: entries pointed AT evidence, but
no published number pointed BACK at the row that proves it, which is why the ledger's
era F-numbers stayed stale for three days after the recalibration superseded them. Each
claim carries the `statement`, the `value` as claimed, ONE `evidence` pointer, and
`stated_in` — every file that would have to change if it drifts. `qc/claims.py`
resolves pointers using a superset of the `n_source` grammar (adds `csv:<col>@<filters>`
for a single cell, `regex:`, and `dir_csv_count`), and a `csv:` selector matching zero
or many rows is an ERROR, never a silent first-match.

READER RULE: **a drifted claim is reported, never auto-corrected** — which side is
wrong, the measurement or the sentence built on it, is a judgement. Check with
`py -3.12 qc/verify_claims.py` (exit 1 on drift, so it can gate a commit); gated by
`qc/test_claims.py` and run as a `landed.py` rung.

## SCIENCE.md (Scripts/, GENERATED — byte-compared, size-capped)

Written by `qc/science_digest.py`: every conclusion the project has reached, in one
file of ~2,600 tokens. Sections are the answer (verified claims), best arm per year at
one held cut, what the completed investigations concluded, what is NOT known, and what
is blocked on whom.

WHY IT EXISTS. The measured split, 2026-09-06: the science is ~10,600 tokens across
five artifacts; the audit trail (`run_passport` + `arm_metrics` + `tileset_registry`)
is ~107,600 — **10.1x larger than the science it supports**. The CSVs are big because
they are denormalised for joining and complete rather than selected: 54-76% of their
cell bytes repeat a value already present in another row, and gzip crushes 420 KB to
44 KB. READER RULE: **SCIENCE.md is the KNOW half, the CSVs are the CHECK half.** Read
the digest; query the CSVs through `qc/ask.py` when a claim needs checking. Reading
them raw is never the right move.

`test_science_digest_stays_loadable` caps it at ~12k tokens, so it cannot quietly
become another dump.

## offload_pilot_2017k.csv (phase4/qc/, GENERATED)

Written by `qc/instruments/offload_pilot_compare.py`: the offload pilot's pre-registered
reads (`experiments/offload_pilot_2017k.yaml`) joined from five homes into one file, so
the verdict is written FROM A FILE. Long format — `metric, step, baseline, pilot, unit,
baseline_source, pilot_source, note` — with `of_2017k` and `spd_2017k` side by side.
Metrics: `step_minutes` (the queue ledger's OK-row `minutes`, orchestrator wall clock,
1dp), `step_elapsed_log` (the engine's own `elapsed:` from the step log matched on
`--run-tag`, normalised to minutes, 2dp — these two measure different brackets and
differ by 1-3 min per step), `machine`, `a100_span_min` / `total_span_min`,
`sem_best_mb` / `prob_raster_mb` / `mask_mb` / `gpkg_mb` (decimal MB, bytes/1e6),
`tileset_id` / `n_tiles` / `tileset_id_match`, `eval_ap` / `eval_auroc`, and
`hw_nothing_frac` / `hw_gpu_busy_frac` per step.

READER RULE: **a blank cell means NOT MEASURED — never zero.** Every row is emitted
whether or not the arm has run. The one exception is a step that ran and FAILED (kill
criterion K1): the value is still blank, but `note` carries `latest state FAIL`, so a
failure cannot read as an absence. `machine` is not in the queue's status CSV at all —
`_gpu_line()` prints the tier to the launch header on stdout and `host` is a container
hostname — so it is resolved from the run manifest's `gpu` via `run_passport.csv`, then
the per-session `heartbeat_<session>.json`, then the train log's `Device:` line, and
`note` names which of the three answered. `eval_ap`/`eval_auroc` read the superseded
archive as well as the live report, because step_evaluate's replace key is
(year, channels) and NOT run_tag: the pilot evaluating the same year and channels
displaces the baseline's rows. Gate: `qc/test_offload_pilot_compare.py`.

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
2026-09-02; 5 s samples). Since e8dec13 every sample goes to a LOCAL spool,
flushed per row, and `vm_hwlogger.py::mirror_once` republishes the whole spool
onto this path every 12th sample — one Drive write a minute, temp +
`os.replace`, cut at the last newline. **Nothing is buffered**: this file is the
previous complete file until the instant it is the new complete file, and a
failed publish needs no recovery because the next tick republishes the same
local file. Kernel + NVIDIA counters only — no pipeline code in the measurement
path. **LEGACY (v1)
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
`hw_*.csv` above plus the step logs. One row per `(session, step, basis, phase)`
and one `step = ALL` row per `(session, basis)`; `step` values are the engine
step with its year label stripped (`train_2017` → `train`), plus `(between)` for
samples with no step running. The basis is decided PER FILE, so a session owning both a
v1 and a v2 file (see the fork rule above) emits two independent sets of rows —
the marker samples keep their own per-machine `step` instead of being re-guessed
by time against another VM's step log. Columns: `session, step, basis,
gpu_present, samples, hours, gpu_busy_frac, gpu_util_mean, cpu50_frac,
iowait10_frac, tx1_frac, rx1_frac, disk5_frac, nothing_frac, ambiguous_dropped,
samples_parsed, span_hours, source_file, phase`. Fractions are of the row's
samples (GPU fractions of the samples that HAVE a GPU reading), and are BLANK on
a row with no samples. `phase` was appended (last position, so no column moved)
on 2026-09-07 and makes the row key `(session, step, basis, phase)` — semantics
in **The step-phase layer**, at the end of this file.

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

Written by `qc/instruments/harvest_tilesets.py`. ONE row per tile DIRECTORY (label, run_tag) - several directories can share one id (2017k: two directories, one set; see the tileset-directories claim) - each carrying its
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

Written by `qc/coverage_map.py`: one row per acquisition — tile sets, tiles, tile
dirs, train runs, arms scored, arms with a matched-cut read, best AP, champion,
registry entries.
READER RULE: **a blank cell means "no record", never "should have been done."** Some
acquisitions are deliberately out of scope (the Atlas trend is 2016→2024; several
deliveries exist only as overlap controls), and separating deliberate from overlooked
is a decision this file does not make. Gate:
`test_run_context.py::test_coverage_map_is_fresh` plus a gate pinning that caveat.

READER RULE: **a tile SET is not a tile DIRECTORY.** A `tileset_registry.csv` row is
one directory, keyed (`label`, `run_tag`); several rows can share one `tileset_id`
— the same tiles materialised under two tags, which is exactly what makes those arms
comparable. *tile sets* counts distinct ids and *tiles* sums `n_tiles` over those
distinct ids; *tile dirs* counts rows. Summing over rows double-counts: it read 2009
as 18 sets / 11,036 tiles against 10 / 6,124, and made 2017k's offload pilot — whose
result is that the CPU-tiled set reproduces the A100-tiled one byte-for-byte — look
like a doubling (fixed 2026-09-07). The census is
`qc/coverage_map.py::tileset_census`, one home for both generators, gated by
`test_run_context.py::test_tileset_census_counts_a_shared_id_once` and
`::test_coverage_map_tiles_column_is_distinct_sets`. SCIENCE.md §2 has room for one
column and prints the distinct-set number under the header `tiles (distinct sets)`.

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
`hw_nothing_frac` / `hw_gpu_busy_frac` per step. Six rows read off the pinned postproc
step log describe WHAT that step produced, not just how long it took —
`operating_threshold` (each arm picks its own cut from its own eval report),
`canopy_pct`, `canopy_ha`, `n_polygons`, `polygonize_s`, and `stage_prob_s` (blank on an
arm that printed no staging line, i.e. read the probability raster over FUSE).

READER RULE: **a blank cell means NOT MEASURED — never zero.** Every row is emitted
whether or not the arm has run. Since 7a60226 there are THREE blanks that mean something
else, and `note` is the only thing that separates them from an absence — read it before
reading a blank:

- **the step ran and FAILED** (kill criterion K1): `note` carries `latest state FAIL`
  (`offload_pilot_compare.py::step_minutes`). Otherwise K1 would read exactly like
  "not run".
- **the step's own row does not survive the arm's pin**: `note` carries `NO SURVIVING
  ROW under this arm's pin — N row(s) … belong to another launch and were refused; the
  step is not known to have been skipped` (same symbol). Measured on the baseline's
  `labels` and `tile`: two earlier failed launches had already written rows under this
  tag, so the ledger recovery suppressed of2017k2's own; those minutes live in the nohup
  log and in the yaml's pre-registration, not in the ledger.
- **a span whose ENDPOINT is a recovered row**: `note` carries `NOT PUBLISHED: the span
  opens/closes on a RECOVERED-FROM-LOGS row…` plus the number it would otherwise have
  printed (`offload_pilot_compare.py::_endpoint_guard`). A recovered row's `ts` is the
  engine's `completed:`, not the queue-side start the span rows assume, and on the
  baseline that would have printed 41.7 min against a real 113.0 — inverting R1 for
  anyone who read only the value column.

`baseline_source` / `pilot_source` name the FILE **and the pin rule that admitted the
row** (`offload_pilot_compare.py::_src`), because "this is the pre-registered session"
(`session=of2017k2`) and "this is a blank-session recovered row I took on trust from a
time window" (`blank-session, in-window`) are different grades of evidence and the CSV
alone has no other way to say which. Rows the pin refuses are counted and printed, never
dropped silently.

`machine` is not in the queue's status CSV at all —
`_gpu_line()` prints the tier to the launch header on stdout and `host` is a container
hostname — so it is resolved from the run manifest's `gpu` via `run_passport.csv`, then
the per-session `heartbeat_<session>.json`, then the train log's `Device:` line, and
`note` names which of the three answered. `eval_ap`/`eval_auroc` read the superseded
archive as well as the live report, because step_evaluate's replace key is
(year, channels) and NOT run_tag: the pilot evaluating the same year and channels
displaces the baseline's rows. Gate: `qc/test_offload_pilot_compare.py`.

## timing_events.csv (phase4/qc/, GENERATED)

Written by `qc/instruments/harvest_timing_events.py::harvest`: one row per
`⏱ <label>: <N>s` line the engine printed, joined to the SIZE of the file that line
moved. Columns: `run_id, year, run_tag, step, label, seconds, bytes, mb_per_s,
log_file`. The first four come from the step log's own header block, so every event
carries the arm that produced it; `step` is the command line's bare `--step`
(`evaluate`), never the banner's year-suffixed `evaluate_2006s`. Order is `run_id`,
then log line order — the within-log sequence is itself evidence (stage, then the work,
then copy). `seconds` is the log's verbatim string; `bytes` is an integer;
`mb_per_s` is `bytes/1e6/seconds` to 2dp.

WHY IT EXISTS. `phase4seg/common.py::tock` has been printing these lines since phase 1
and nothing read them, because the number that turns a duration into a RATE — the size
of the file — is not printed beside the duration. For `copy` events the log does carry it
one line down (`common.py::_copy_to_drive` prints `✓ verified|staged write: X (N MB…)`;
2,228 of
2,233 copy events have it, to the nearest whole MB); for `stage` events — the half the
storage argument rests on — nothing in the log carries it, which is why `bytes` is joined
from the lake. So `Reports/
PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md` §1 priced its whole storage argument on
"Drive gives 40 MB/s on one big sequential file", a figure with no instrument behind it.
Measured 2026-09-07 over 2,823 events in 362 step logs: `stage` median **39.0 MB/s**
(n=281, p10 7.4, p90 87.2), and for files ≥1 GB **39.7 MB/s** (n=145). The claim holds.

READER RULES.

- **THE ROWS OVERLAP — SUM WITHIN ONE FAMILY, NEVER ACROSS.** "One row per `⏱` line" is
  still true of the file, but since 2026-09-07 the lines themselves NEST, so a total over
  every row in a step double-counts. Three families now share a log. (1) The pre-existing
  POINT events: `stage <file>`, `stage tiles <label>`, `copy <file>`, `inference`,
  `postproc`, `bundle copy <label>`. (2) The per-epoch BUCKETS
  `epoch <A|B><n> <bucket>`, bucket ∈ `data` / `gpu (sync at epoch end)` / `val` /
  `save` / `other`, written by `core.py::_publish_epoch_phases` (the `data` bucket is
  measured by `core.py::_timed_batches`). (3) The five `eval` SPANS
  `core.py::step_evaluate` opens: `eval tiles local`, `eval model load`, `eval forward`,
  `eval metrics`, `eval report`.
  Families (2) and (3) ENCLOSE members of (1): `epoch <A|B><n> save` contains the
  `copy sem_best_*.pt` row `common.py::_copy_to_drive` prints (and `copy sem_latest_*.pt`
  where that file is still Drive-backed — see `core.py::step_train`'s `LATEST_CKPT_LOCAL`
  branch); `eval report` contains both `copy semantic_eval_report*.csv` rows; and on a
  COLD run `eval tiles local` contains `stage tiles <label>`. Those seconds are in two
  rows each, by design.
- **The buckets do not partition the STEP either, so they under-cover as well as
  overlap.** The five epoch buckets sum to Σ(epoch walls), not to the train step: tile
  staging sits before the loops (it publishes its own `stage tiles` row), and the
  DataLoader plus `ckpt.py::build_model` construction and the deploy publish emit NO row
  at all. The `eval` spans are disjoint from one another but leave gaps between them.
  `gpu (sync at epoch end)` is kernel launch + host-side python + device WAIT, **not**
  GPU-busy time — `loss.item()` already syncs every batch — which is why the caveat is
  in the harvested label itself and not only in the source. Do not reconcile a bucket
  against `hw_step_attribution.csv`'s step-scoped fractions without adding the staging
  row back and allowing for the two unrowed costs.
- **`⏱ train epoch phases: …` is a summary line the parser deliberately does not
  match.** `core.py::_print_phase_summary` restates numbers already published one row
  each; if it parsed it would double every bucket in this CSV. `_EVENT`'s end anchor is
  what rejects it (the line ends in a parenthetical, not in `<N>s`), and
  `qc/test_train_timing.py::test_summary_line_is_not_harvested` pins that negative.
  `core.py::_tock_total` prints the buckets in `common.py::tock`'s exact format — it has
  to restate the format string, so `::test_tock_total_is_byte_identical_to_common_tock`
  pins the restatement rather than trusting it.
- **`stage` and `copy` measure opposite directions and different media.**
  `common.py::_stage_imagery_local` and `staging.py::_stage_tiles_local` copy
  Drive → local NVMe: that is a Drive READ and the only rows that are Drive throughput.
  `common.py::_copy_to_drive` writes local NVMe → a `.part` on the rclone FUSE mount,
  which lands in the VFS cache and returns before anything reaches Google, so whatever
  its value, it is a cache-write rate and not upload bandwidth. Never quote a `copy` row
  as Drive throughput; that exact error produced the inflated checkpoint estimate the
  speedup report corrects in its §2. THE MEDIAN DEPENDS ON WHICH SIZE YOU USE, and both
  belong in the same sentence: **463.9 MB/s** all-copy / **484.0 MB/s** `sem_best` from
  this file's joined lake `bytes` (n=2,107 / n=1,375 rows with a rate), against
  **429.4 MB/s** for both from the size the engine LOGGED at copy time (n=2,108 /
  n=1,376). **Prefer 429.4** — see the `bytes` rule below for why the joined `sem_best`
  figure runs 12.7% high (all-copy, 8.0%).
- **`bytes` is the file's size in the lake NOW, joined by BASENAME — not the size at the
  time of the event.** EXACT for the `stage` population, which is the whole of the
  published throughput: the orthos and `phase3`'s 2020 mask are write-once, all 28
  distinct sized `stage` basenames resolve in those two roots, and 24 cross-check exactly
  against the independent `size_mb` column of `imagery_geometry.csv` (0 disagreements).
  NOT exact for `copy`, and the error is systematic rather than churn — measured
  2026-09-07 against the size the same call logged (`round(bytes/1e6)` vs the engine's
  `{want_size/1e6:.0f}` integer MB; the rounding is not optional, a byte-exact comparison
  disagrees on all 2,173 rows and means nothing): **1,025 of 2,173 comparable rows
  disagree, 47%, median 44%, max 67%, the lake file larger in 984 of them**, because
  `sem_best_*.pt` is overwritten every improving epoch and the architecture grew.
  So **`copy` `mb_per_s` is not usable at the row level** — only its median is, and even
  that shifts 463.9 → 429.4. It would be outright wrong for append-mode artifacts like
  `semantic_eval_report.csv`, which grows with every run (those rows blank anyway).
- **A blank `bytes` has three causes and the row does not distinguish them:** the label
  names no file (`inference`, `postproc`, `polygonize`, and `stage tiles 2009`, whose
  tail is a directory description); no such basename in the five scanned roots
  (`Full_Image/Pipeline Imagery`, `phase4/models`, `phase4/masks`, `phase4/eval`,
  `phase3` — `phase4/labels_corrected` is deliberately outside, so the `add_chm*.tif`
  overlays miss); or two DIFFERENT sizes answer to one basename (`phase4/masks/` vs
  `_prerefactor_backup/`, `eval/viz_2000/` vs `eval/viz_2016/`), in which case the join
  refuses to pick a side. The same size in several directories is not ambiguous.
- **`mb_per_s` is blank unless `bytes` resolved AND `seconds` > 0.** 120 of the 2,823
  events are sub-cadence zeros — all 43 `copy semantic_eval_report.csv` events among
  them. A sub-cadence operation is real; a division by zero is not a rate.
- **A `stage` row is a COLD Drive read only the first time a runtime touches the file.**
  Every row in the archive to date predates the scratch cache, when
  `common.py::_unstage_imagery_local` DELETED the scratch copy after each step, so a
  later step re-staging the same file reads it back out of the warm rclone VFS / OS page
  cache: 3 of 281 sized rows exceed 500 MB/s for that reason (max
  `stage 2006_snoh_1m_rgb.tif` at 1092.72 MB/s, the same basename that read 156.10 MB/s
  three minutes earlier in the same session). Drop the >300 MB/s tail before quoting
  `stage` as Drive throughput — it moves the median 39.0 → 38.3 and p90 87.2 → 84.1, so
  the headline figures above stand either way. THAT WARM-CACHE TAIL SHOULD NOW THIN, and
  the reason is a change in what a missing row means: `_unstage_imagery_local` releases
  instead of deleting, and a same-VM re-stage is a cache HIT that publishes NO row at all
  (`scratchcache.py::stage` — emitting `⏱ stage <file>: 0.0s` under the event name this
  saving is measured from would fabricate the win). So after 2026-09-07 an absent second
  `stage` row for a file is evidence of a hit, not of a step that never staged it.
- **Per-event rates are throughput UNDER CAMPAIGN CONCURRENCY, not a clean single-stream
  number.** The P11.4 staging lock serialises bulk copies within one VM, but concurrent
  VMs share the Drive link — `2017_king_rgb.tif` (11.55 GB) staged at 93.5 and
  132.6 MB/s on 2026-09-06 and at 37.3 MB/s on 2026-09-07, same file, same code.
- `_copy_to_drive` also calls `tock` inside its `except OSError` retry branch, so a
  `copy` row CAN time a FAILED partial transfer — but measured 2026-09-07, **0 of 2,233
  do** (no `⏱ copy` line in the 507 archived step logs is followed by `! copy raised`).
  Re-count before discarding an absurdly fast or slow `copy` row as a failure.
- **A harvest that finds ZERO events refuses to overwrite a populated file and exits 2**
  (`--allow-empty` overrides). Both the log listing and the size scan go through
  `lake.py::read_retry`, because a blinking mirror listing would otherwise publish a
  header-only CSV over the whole archive and report success.

Gate: `qc/test_timing_events.py`.

## The step-phase layer (`hw_*.csv` `step` cell, `hw_step_attribution.csv` `phase`)

Added 2026-09-07; the vocabulary has one home,
`pipeline/phase4seg/names.py::hw_step_marker_path`. The step marker may carry an
optional `phase`:

| phase | meaning | written by |
|---|---|---|
| `open` | a StepLogger step is running — **also what an ABSENT key means** | `pipeline_log.py::StepLogger.start` (which writes no phase at all) |
| `launching` | the queue has spawned the engine process, StepLogger has not opened yet | reserved for `phase4_train_queue.py` |
| `verifying` | the queue's post-step VERIFY; the engine has already exited | reserved for `phase4_train_queue.py` |

**Only `open` is written today**, so every row in the current harvest reads `open`
or blank — a fact about the writers, not about the readers, which honour all three.

**On the raw side the phase rides INSIDE the existing `step` cell**, as
`<step>#<phase>`, for any phase but `open`
(`vm_hwlogger.py::read_marker`). No column was added to `hw_{session}.csv`: a
second widening would have forked a `_v3` file per the one-file-one-schema rule
above, splitting live sessions in half to carry a field that is blank in almost
every row.

**On the harvested side it is its own last column.**
`harvest_hw_attribution.py::split_step` splits the cell, so `step` keeps exactly
the value it has always had (`train_2017#verifying` → `train`, phase
`verifying`) and the row key becomes `(session, step, basis, phase)` — **one step
may legitimately appear on several rows; sum them before quoting a step total.**
`(between)` and `ALL` rows carry a BLANK phase: neither names a step whose phase
could be reported, and `ALL` pools every phase. `interval`-basis rows can only
ever read `open`, because a step LOG exists only for a step that opened.

**Why**: `(between)` is this table's residual and it is one of the largest
buckets in it — see §7 of
`Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md` — and it is attributable to
nothing at all. Part of it is the queue, not an idle machine: the
`spdc1,(between),marker` row of `hw_step_attribution.csv` is a CPU runtime whose
between-steps time reads `cpu50_frac` at zero with `iowait10_frac` dominant,
i.e. **blocked on I/O** — queue-side input staging, before its first marker
opened. (That session is LIVE: its counts and fractions move between harvests, so
read the row, never a number restated about it.) Phases move that time out of the
residual and onto a row that names it.

**Writer requirement, because the reader gates on liveness**: the marker's `pid`
must be the pid of whatever WROTE it. `read_marker` discards a marker whose pid
is dead (so a SIGKILLed step cannot keep claiming later samples), and `verifying`
runs after the engine has exited — a queue that copied the engine's pid in would
have every verifying sample silently blanked.

## hw_meta_{session}.json (lake `phase4/logs/`, one file per session)

Written ONCE by `pipeline/vm_hwlogger.py::write_meta` from
`vm_hwlogger.py::runtime_facts`, at logger start, beside the session's
`hw_{session}.csv`. Never rewritten: an existing file always wins, so
`started_utc` stays on the session's first sample even if the logger is
restarted. Keys: `session, started_utc, hostname, vcpus, ram_gb, disk_total_gb,
gpu_name, gpu_mem_mb, kernel, python, marker_path` and, since 2026-09-08,
`cpu_model, cpu_mhz, bogomips`.

`vcpus` is `os.cpu_count`, `ram_gb` is `/proc/meminfo` `MemTotal` converted from
kB, `disk_total_gb` is `statvfs("/content")`, `gpu_name`/`gpu_mem_mb` are the
FIRST line of `nvidia-smi --query-gpu=name,memory.total` (blank on a CPU
runtime, where the binary is absent), `kernel` is `os.uname().release`, `python`
is `sys.version.split()[0]`.

`cpu_model`, `cpu_mhz` and `bogomips` are the FIRST stanza's `model name`,
`cpu MHz` (a number rounded to one decimal, like `ram_gb`) and `bogomips` in
`/proc/cpuinfo` — read once, keys matched case-folded because ARM spells it
`BogoMIPS`, first occurrence only because the file repeats its keys per core.
Each is blank on its own: an absent file, an absent key or an unparseable number
costs that field and no other.

**Why the CPU identity was added (2026-09-08).** The eleven original keys SIZE a
runtime and never name it, and two CPU runtimes that size the same do not run the
same. Sessions `spdc1` and `spdvc1` ran the identical 632-tile `tile` step over
the same ortho with the same recipe: the hw samples carrying that step number 252
vs 469 — 21.0 vs 39.1 min at the 5 s cadence — at a median `cpu_pct` of 28.9 vs
21.3 (computed over the `step = tile_2017k` rows of each `hw_{session}.csv` on
the lake, 2026-09-08; the ledger's own `minutes` on the two `tile` rows reads
34.1 vs 53.6, and a `harvest_hw_attribution.py` run the same day put their `hours`
at 0.3500 vs 0.6514 with `cpu50_frac` 0.3056 vs 0.2111 — `spdvc1` was a live
session and its attribution rows were untracked when this was written). A step
1.9x longer at LOWER CPU is what a slower host core looks like, and no tracked
file could confirm or refute that: `spdvc1`'s meta stops at `vcpus` 2 and
`ram_gb` 13.6, and `spdc1` has no meta at all.

**Both metas on the lake predate these keys** — `hw_meta_spdvc1.json` and
`hw_meta_spdvg.json`, read 2026-09-08 — so the three are blank everywhere until a
runtime launches from a repo carrying this change. A VM clones the code at launch,
so no existing session gains them retroactively.

**Every field is independently best-effort and BLANK when it could not be
read** — never 0, and never a guess; the logger must reach its sampling loop
whatever the environment denies it.

**Why it exists**: every column of `hw_{session}.csv` says what the runtime was
DOING and nothing anywhere said what it WAS. A session reading 0% GPU for six
hours could not be told from a session that had no GPU (`gpu_present` in
`hw_step_attribution.csv` INFERS it from blank cells — an inference, not a
reading), and hours could not be priced: an A100 hour and a free CPU hour are
the same number and different money.

Gate: `qc/test_vm_hwlogger.py`, `qc/test_hw_marker.py`, `qc/test_hw_attribution.py`.

## runtime_sessions.csv (phase4/qc/, GENERATED)

Written by `qc/instruments/harvest_runtime_sessions.py`: ONE ROW PER RUNTIME —
`session, queue, gpu_name, vcpus, ram_gb, hw_first_utc, hw_last_utc, hw_hours,
gpu_present, heartbeat_first_utc, heartbeat_last_utc, queue_first_row_ts,
queue_last_row_ts, n_queue_rows, startup_min, idle_tail_min, sources`, and since
2026-09-08 the three trailing columns `cpu_model, cpu_mhz, bogomips`. `hw_hours`
is the SPAN of the hw stamps (last − first), not sampled time — cf.
`hw_step_attribution.csv`, which carries `span_hours` and `hours` as separate
columns because a stalled logger leaves gaps inside the span.

**Why it exists.** `hw_step_attribution.csv` is keyed on the STEP, so the two
kinds of wasted VM time both land in its one `(between)` bucket: START-UP (the
machine is billed, the queue has not written its first row — bootstrap, pip,
clone, mount) and the IDLE TAIL (the queue wrote its last row and the runtime is
still alive). Only the first is fixable by editing the pipeline; the second is
fixable only by stopping the runtime, which CLAUDE.md 3.4 already calls a defect.
This table splits them, by putting the machine's clock (hw samples, heartbeats)
next to the queue's clock (status rows) per session.

A session is admitted if it appears in ANY of four homes, and `sources` names
which: `hw` (`hw_{session}.csv`, `_v2` being the schema and not the name),
`hw_meta` (`hw_meta_{session}.json`), `heartbeat` (the `session` FIELD inside any
`heartbeat_*.json`, including a `__conflict-` copy and a stranded
`.json.prev.{tok}.json` — a bare `.json.prev.{tok}` is NOT read, because the
writer promised every reader filters on a `.json` suffix — never the filename)
and `queue_rows` (the `session` column `queue_ledger.py::_status_write` stamps, discovered through
`phase4seg.names.status_files`). `train_queue_nohup_*.log` filenames carry no
session — `vm_ops.py::launch_queue` names them after the QUEUE — so they feed
only the `queue` column.

READER RULES, each earned on a measured row:

- **BLANK IS NEVER ZERO.** `n_queue_rows` blank means the ledger rows are not on
  the lake, not that the runtime ran no steps. `gpu_present` is `1`/`0`/blank,
  where blank means no hw sample was parsed at all and `0` means samples exist
  with every GPU column empty — a CPU runtime. `gpu_name`/`vcpus`/`ram_gb` come
  from `hw_meta` ONLY and are blank for every session logged before that file
  existed; `gpu_present` is the measured answer for those.
- **`cpu_model`/`cpu_mhz`/`bogomips` say WHICH machine — and are blank on every
  row today.** They too come from `hw_meta` alone
  (`vm_hwlogger.py::runtime_facts`, which began writing them 2026-09-08), and both
  metas on the lake were written before those keys existed, so blank here reads
  "the logger predates the keys", never "the host was not identified". They exist
  because `vcpus` + `ram_gb` could not tell `spdc1` from `spdvc1`: two CPU
  runtimes that ran one 632-tile `tile` step 21.0 vs 39.1 sampled minutes apart at
  a median `cpu_pct` of 28.9 vs 21.3, with no tracked field able to say whether
  the host CPU differed. Derivation in the `hw_meta_{session}.json` section above.
- **`queue` is blank rather than guessed.** Three links, in precedence order.
  (1) The heartbeat's own `queue_file` — the `--queue` argument the queue process
  publishes about itself (`vm_heartbeat.py::sample`, D11) — basename, `.yaml`
  stripped. It wins: it is the only link that cannot name another VM's queue.
  (2) For pre-D11 records that declare none, the heartbeat's `newest_nohup.name`,
  admitted only when `queue_proc` is non-null (`vm_heartbeat.py::_newest` drops
  its own-stem filter without one and then reports the newest nohup log on the
  whole shared mount, routinely another VM's). **A live `queue_proc` is NECESSARY
  BUT NOT SUFFICIENT**: that filter matches by SUBSTRING, so a stem which is a
  strict prefix of another queue's stem returns the LONGER queue's log. Measured
  2026-09-07 on `hardyear` — declared `queue_hard_year_pilot`, `newest_nohup`
  named `queue_hard_year_pilot_only2006s`, and this table published the longer
  stem until (1) existed. A stem reached this way is dropped when another nohup
  stem on the lake is a prefix of it, flagged
  `queue_prefix_collision(shorter,longer)`. (3) The stem of a status FILE holding
  this session's rows, **only when that file is a LAUNCH**
  (`names.parse_status_name` returns a non-None ts): a `_seed` file's stem would
  collide with its own queue's launches, and the ledger-recovery candidate's stem
  is a filename artifact — reproduced, it published
  `queue = recovered_20260901_20260907` for four sessions. The links agree or the
  cell is blank with `queue_ambiguous(a,b)` in `sources`.
- **`queue_last_row_ts` is the last step's START, not its end.**
  `phase4_train_queue.py::run_step` stamps `ts` when it appends the row in state
  `RUNNING` and never re-stamps it. So `idle_tail_min` INCLUDES that final step's
  run time whenever the last row is a step row. A `VERIFY:{step}` row is the
  exception, on the STAMP rather than the ordering: `queue_verify.py::verify_step`
  builds its record — `ts` included — after the check has run, so that cell is a
  completion time (the job-end `VERIFY` row is the other way round;
  `phase4_train_queue.py::verify` stamps `ts` before `_check_prob_raster`). **How
  long a VERIFY takes was UNRECORDED until 2026-09-07**: all 278 VERIFY rows in
  `phase4/qc/ledger_recovery/train_queue_status_recovered_20260901_20260907.csv`
  carry a blank `minutes`, and the archive's only bound is the adjacent stamps on
  session `spdc1` — `labels` stamped 21:51:58 with `minutes` 6.8 (ending 21:58:46),
  `VERIFY:labels` stamped 21:58:49, the next step's row on the same second.
  Commit c5dc91c stamps `minutes` on all four VERIFY write sites, so it is now read
  rather than assumed: the first rows to carry it read 0.0 and 0.0 (session `spdc2`,
  in the LAKE copy of `train_queue_status_pilot_offload_2017k_cpu2_20260907T235535Z.csv`
  — live, untracked, so not a path this repo can resolve; read 2026-09-08). Read
  `idle_tail_min` as an UPPER BOUND; the row's own `minutes` is the correction,
  still deliberately not joined here.
- **`idle_tail_min` is not a tail at all while the queue is still running.**
  `run_step` appends its row in state `RUNNING`, so a session whose newest row is
  `RUNNING` has a value that grows with the current step: measured on the live
  campaign 2026-09-07, `spdg` read 4.4 min and then 10.4 min off the same
  unchanged row six minutes later. Those rows carry `queue_last_row_RUNNING` in
  `sources` and are excluded from the instrument's own headline sum.
- **A NEGATIVE `idle_tail_min` means the beacon stopped before the queue did**,
  which is a telemetry failure and not an idle tail. It is
  published rather than clipped, flagged `beacon_ended_before_queue` in `sources`.
  Measured 2026-09-07 on `pilotcoarse`: the last surviving heartbeat stamp is
  42.8 min BEFORE the queue's last row and sits INSIDE the queue's span, so the
  beacon stopped while the work continued (a clock offset would push the stamp
  outside the span, by a whole hour), and `pilotcoarse2` reports a different
  `host` and a different GPU, so it is not the same runtime re-bootstrapped under
  a new session name either. WHY the beacon stopped is not established. Exclude
  those rows from any sum.
- **`later_rows_unattributed(tag)` means the ledger stopped NAMING the session
  before the work stopped, so that row's gap is mostly work.**
  `queue_last_row_ts` is the last row saying `session=<s>`, which is the run's
  last row only while every row is attributed. Since the ledger-recovery
  candidate reached the lake (2026-09-07 — it is now IN `phase4/qc/` and every
  reader merges it, as `names.status_files` promises), that no longer holds: its
  252 snapshot-native rows carry a `session` and its 244 log-synthesised rows
  carry an EMPTY one, and the synthesised rows are exactly the events no snapshot
  captured — the later ones. Measured on `ofB`: last session-stamped row
  `evaluate` 16:33:53, rows for the same tag continuing to 18:58:23, and a
  published 351.6 min "idle tail" across hours of work. Any blank-session row
  bearing one of the session's tags and dated after its last row raises this
  flag, and those rows leave the instrument's headline sum. **Necessary, not
  sufficient**: the check only sees tags the session already has an attributed
  row for, so a ledger that cut before its next tag began passes unflagged —
  absence of the flag is not proof of completeness.
- **`heartbeat_not_listed` means no beacon record was found for a session another
  writer knows about** — not that the beacon columns are merely empty. The
  heartbeat listing is not evidence of absence: reproduced 2026-09-07, one
  `glob("heartbeat_*")` returned 143 entries with a live runtime's file missing
  and readable by name seconds either side, and `vm_heartbeat.py::write_atomic`
  renames the live file aside before replacing it, so the canonical name is
  genuinely absent for a window every 60 s. Every session known elsewhere and
  absent from the listing is therefore RE-PROBED by name (including the bare
  `.json.prev.{tok}` aside, the only copy inside that window) before its beacon
  columns are published blank. Sessions that predate the beacon carry this flag
  permanently, which is the same true statement about them.
- **`heartbeat_first_utc` is a ceiling on the beacon's start, not the start.**
  `vm_heartbeat.py::write_atomic` OVERWRITES one file per session every 60 s, so
  what survives is the last cycle plus its `prev_ts_utc` plus any stranded
  `.prev.` file that still ends in `.json`. The earliest of those is the earliest stamp that still exists.
- **The two clocks are ASSUMED to be one.** hw and heartbeat stamp `...Z`; status
  rows are `_dt.datetime.now()` on the VM — naive local. Colab runtimes run UTC,
  so they are compared directly. A whole-hour `startup_min` or `idle_tail_min` is
  the symptom to check before believing a large value.

**What it measures today (2026-09-08, re-measured when the CPU columns were
added).** 79 sessions; 23 carry hw samples, 14 of those GPU ones; 21 carry
session-stamped ledger rows. TWENTY sessions get an `idle_tail_min` value, and
sixteen of them are excluded from the headline by a flag they earned (the flags
overlap): two `beacon_ended_before_queue` (`hardyear4`, `pilotcoarse`), three
`queue_last_row_RUNNING` (`pilotcoarse`, `trend8A2`, and `spdvg` — an A100 that
was still running when this was harvested, so its row moves on every harvest) and
fourteen `later_rows_unattributed`. What survives is `pilotfine` 2.3 +
`pilotmed` 11.1 + `spdc2` 1.9 + `spdvc1` 1.6 = **16.9 min**, and it is a LOWER
BOUND over the only fully-attributed ledgers on the lake — the pilot-era launch
files plus the two 2026-09-08 CPU runtimes — not a campaign total.

The unflagged sum would read **1918.1 min over 18 sessions, and it is mostly
work, not idleness**: fourteen of those are the runtimes whose ledger rows survive
only in the recovery candidate, whose later events carry no `session`. Do not
quote it — and note that it is not even stable, because `spdvg`'s `RUNNING` row
grows between harvests (1916.1 two minutes earlier). The `ts` semantics the candidate's sidecar publishes
(`phase4/qc/ledger_recovery/recovery_report.md`: a synthesised row carries a
RECONSTRUCTED step start, and its `detail` prefix names which of three rungs dated
it) do NOT bite this table — measured, all 244 synthesised rows carry an empty
`session`, so only the 252 snapshot-native, queue-stamped rows ever join here. The
loss is attribution, not timing.

The underlying ledger loss is recorded rather than fixed: every per-launch status
file written between 2026-09-01 and 2026-09-07 is absent from the lake
(`hard_year`, `tier1`, `trend8`, `overlap_floor`, `offload` — measured absent),
and the shared `train_queue_status.csv` holds only the latest launch's rows.
`queue_ledger.py::_flush` records the mechanism itself — the `__main__` defect in
`::_q` made `STATUS_OUT` resolve to the shared file, so each flush replaced the
whole ledger with one launch's rows. Absence measured here; cause quoted from
that docstring, not re-verified. Until per-launch status files are written again,
a campaign-wide idle-tail number cannot be had from this table, and the 16.9 min
headline is provisional.

`gpu_name`/`vcpus`/`ram_gb` are filled on exactly two rows — `spdvc1` and
`spdvg`, the first sessions to write an `hw_meta_*.json` — and blank on the other
77, where the file does not exist. `pilotfine` and `pilotmed` have `gpu_present`
BLANK — no hw CSV was written for them — and the other two usable tails
(`spdc2`, `spdvc1`) are CPU runtimes, so the instrument's GPU-confirmed line
reports 0.0 min over 0 sessions. Read that line as "no session CONFIRMED FROM
HARDWARE SAMPLES has a usable tail", never as "no tail was measured"; `pilotfine`
and `pilotmed` are both A100s according to
`heartbeat_{session}.json`'s `gpu.name`, which this table deliberately does not
admit into `gpu_name` (hw_meta only, per its writer).

Gate: `qc/test_runtime_sessions.py`. Regenerate:
`py -3.12 qc/instruments/harvest_runtime_sessions.py` (a `landed.py` harvest rung).

## train_queue_status_recovered_20260901_20260907.csv (phase4/qc/ledger_recovery/, GENERATED — a CANDIDATE, not a ledger)

Writer: `qc/instruments/rebuild_queue_ledger.py::main` (rows: `::merge_rows`,
synthesis: `::synthesise`, write: `::write_csv`). Sidecar:
`phase4/qc/ledger_recovery/recovery_report.md`, same writer.

**It is not part of any ledger.** The file lives in the REPO. `::assert_not_lake`
refuses any output path under `lake.BASE`, `lake.COLAB_BASE` or `lake.LOCAL_BASE`,
so the instrument cannot write it to the lake even by argument. It becomes real
only if a human copies it into `phase4/qc/` on the lake, at which point every
reader merges it — the name satisfies `phase4seg/names.py::is_status_file`, which
is the point of the name and is gated in `qc/test_rebuild_queue_ledger.py`. Do not
quote its rows as ledger history until that copy happens; quote them as *recovered
evidence* and say so.

**Columns: exactly the eleven `queue_ledger.py::_status_write` writes** — `job`,
`year`, `tag`, `step`, `state`, `exit`, `minutes`, `detail`, `ts`, `host`,
`session`. There is deliberately NO provenance column: a twelfth field would hand
every reader's `DictReader` a schema it does not know. Provenance is the `detail`
prefix plus the report.

**Two kinds of row, and `detail` is what tells them apart.** 496 rows as rebuilt
2026-09-07: 252 snapshot-native, 244 synthesised from logs.
- *Snapshot-native* — copied byte-for-byte from the orphaned
  `train_queue_status.csv.part.*` / `.prev.*` temps in the same directory. Queue-written,
  unmodified, no prefix.
- *Recovered* — `detail` begins `RECOVERED-FROM-LOGS(ts=start): `,
  `RECOVERED-FROM-LOGS(ts=completed-minutes): ` or `RECOVERED-FROM-LOGS(ts=completed): `
  — the parenthesis names which rung dated the row (below), so the mode is visible in
  the row itself and not only in the report — and then quotes the nohup line that is
  the evidence plus the step log that dated it. A reader that only asks "was this
  recovered?" still matches the stem `RECOVERED-FROM-LOGS`, which is the constant
  every reader and test keys on (`rebuild_queue_ledger.py::PREFIX`). Synthesised only
  where no snapshot row **of the same LAUNCH** covers `(year, tag, step)`:
  suppression is keyed `(year, tag, step, LAUNCH)`, and a snapshot session is
  attributed to a launch by evidence — the launch's window must contain the session's
  earliest surviving row, and the launch log's printed step outcomes must match that
  session's rows EXACTLY on `(job, year, tag, step, state, minutes)` — on
  `(…, verdict)` for a VERIFY (`::attribute_launches`; no match leaves the session
  unattributed, covering nothing). Keying on `(year, tag, step)` alone is what the first version did, and it
  erased the very rows it exists to recover: `of_2017k` ran three times, and the two
  earlier FAILED launches' surviving `labels`/`tile` rows suppressed the successful
  launch's. So a recovered row CAN share a key with a queue-written row from an
  earlier launch of the same tag — that collision is the recovery working, and
  readers resolve it the ordinary way, by taking the latest `ts`.

**`ts` is the step's START in both kinds — but a recovered row's is RECONSTRUCTED,
and the row says how.** A queue-written row carries the start outright:
`phase4_train_queue.py::run_step` stamps `ts` when it appends the `RUNNING` row and
mutates that same dict on completion (the same property `runtime_sessions.csv`'s
`queue_last_row_ts` note records). A recovered row is dated by a three-rung ladder,
and the `detail` prefix names the rung used:
- `ts=start` — the block's own `run_id: 20260906T014036Z_…` stamp, which the engine
  mints at startup and the queue prints inside the block. Sanity-gated: it must lie
  within [`completed:` − `minutes` − 60 s, `completed:` + 60 s], or the rung is
  refused, so a run_id from a differently-zoned clock cannot pass itself off as a
  start. The engine's own `started:` is NOT a rung — `StepLogger` opens the step only
  after footprint discovery and staging, measured five minutes late on
  `hy_e3_2011s/labels`.
- `ts=completed-minutes` — no usable run_id: the step log's `completed:` minus the
  queue's own elapsed.
- `ts=completed` — neither: the step log's `completed:`, unchanged. Also what every
  recovered VERIFY row gets, since `verify_step` stamps when the check ENDS and the
  log prints no duration for it.

Carrying `completed:` on every row is what the first version did, and it made a
recovered session look like it started up to `minutes` late: of2017k2's A100 span read
41.7 min against the 113.1 the queue itself printed. Which rung is right is MEASURED
every run against the surviving queue-written rows, never asserted — the sidecar's
rung table carries n, median and max per rung. Reshaped to the ledger's
`%Y-%m-%d %H:%M:%S`, never re-precisioned.

**`minutes` is the queue's own number in both kinds, never the step log's
`elapsed`.** That field is a formatted string whose unit varies with magnitude —
`pipeline_log.py::StepLogger._write` emits `0.0s`, `1.1min` or `1.10h` — and it
spans the ENGINE's `started:`→`completed:`, while the queue's clock also covers
spawning the child, its pip bootstrap and its imports. Measured on the window:
labels/2011s reads `0.0s` against the queue's `5.4`; postproc/2017 reads `1.10h`
against the queue's `66.6`. `cost_report` sums this column. A recovered `TIMEOUT`
row, whose print carries no minutes, leaves the cell BLANK rather than borrowing a
number that means something else.

**`host` and `session` are blank on recovered rows.** Neither is derivable from a
nohup or step log; the nohup filename carries the queue stem and the launch stamp,
not the session. Blank is the honest value.

**A recovered VERIFY verdict is quoted, never reconstructed** — no printed verdict,
no row. One consequence, recorded rather than hidden:
`queue_verify.py::_mb_from_verdict` anchors `(\d+)MB` at the START of a VERIFY
`detail`, so the prefix defeats that parse and a later fully-skipped-job re-check
degrades from `OK_CACHED`/`SIZE_CHANGED` to `UNVERIFIED` (existence only). That
keeps the step's resume credit and forces a re-verify; it cannot produce a false OK.

**Not present at all, by design:** `GUARD:runtag` rows (not step outcomes, and the
log carries no timestamp for them), resume skips (`- skip job/step (already OK)`
writes no row), D7 re-verifies of skipped steps, and any `$` command block the
queue never closed with an outcome line — the runtime died mid-step and no terminal
state exists to record. The report lists each refusal with its evidence.

**ROW ORDER IS PART OF THE CONTRACT HERE, which it is not in a per-launch file.**
`run_step` keeps ONE dict per step — flushed as `RUNNING`, mutated in place on
completion — so a per-launch file holds one row per step and only its terminal
state. This file is assembled from ORPHANS, and an orphan snapshotted mid-step
preserves the `RUNNING` half, so both halves can survive **at the same `ts`**.
`queue_ledger.py::_merged_rows` sorts by `ts` alone with a stable sort, so which of
two equal-`ts` rows a reader consumes LAST — and therefore which one
`_completed_steps` believes — is decided by row order.
`rebuild_queue_ledger.py::_sort_key` orders non-terminal states FIRST within an
equal `(ts, job, year, tag, step)` group so the terminal row has the final word,
reproducing what the queue's own file would have shown. Do not re-sort this file on
the plain column tuple: `"OK" < "RUNNING"` alphabetically, which reverses it and
revokes a step that finished. The report counts the affected keys.

Two diagnostics in the report exist because suppression withholds them from the
CSV, and both are resume-relevant: a key the logs show FAILING later than its
newest surviving row (with the later state, if any, that superseded it), and a key
whose newest surviving row is still `RUNNING` while a log shows it finished — the
second reads as a revocation to `_completed_steps`, so the candidate still says
"re-run".

Gate: `qc/test_rebuild_queue_ledger.py`. Regenerate:
`py -3.12 qc/instruments/rebuild_queue_ledger.py` (reads the lake's
`phase4/logs/` read-only; deterministic — two runs are byte-identical).

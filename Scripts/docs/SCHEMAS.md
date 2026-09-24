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
**Tracked copy** (`phase4/qc/qc_indep_report.csv` + the per-year `qc_indep_{year}.txt`
and `qc_indep_surfaces_{year}.csv` breakouts) is written ONLY by
`qc/instruments/harvest_qc_indep.py` (a `landed.py` rung, 2026-09-08): byte copy of the
lake, refusing a shrinking report and a re-shaped header, reporting any lineage with
two live generations. It was hand-copied before and fell 285 rows behind twice.

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
onto this path every 12th sample — one Drive write a minute, temp + rename-aside
+ `os.replace` onto the now-absent name, cut at the last newline. **Nothing is
buffered**: this file is the
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

**A trailing ` (N)` is DRIVE, not a session.** Google Drive permits two objects
with one name in one folder ([rclone.org/drive, "Duplicated
files"](https://rclone.org/drive/)) and the desktop client renders the second as
`hw_healA (1).csv` — one such pair sat on the lake 2026-09-08, the twin a strict
byte prefix of the file that kept growing. Both readers strip the suffix
(`.csv` → ` (N)` → `_v2`) so the samples land on the real session:
`harvest_hw_attribution.py::merge_files` unions the group by `ts_utc` behind the
longest file (so a prefix twin moves no number and a diverging one still lands
its unique samples) and names the merge in `source_file`;
`harvest_runtime_sessions.py` needs no merge — its hw columns are min/max/any —
and flags the row `hw_drive_duplicate(<file>)`. Writer side,
`vm_hwlogger.py::mirror_once` now renames the destination aside so the publish
never replaces a name that exists.

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

#### Materialized tile sets — `tile_index_2020.meta.json` under `phase4/tiles/2020__{tag}/` (lake, written by `qc/instruments/phase3_tiles_as_tileset.py`)

The one tile-set writer that is not the engine. It copies the tiles the Phase-3 index
(`phase3/tiles/tile_index_semantic.csv`) names — the rows, never the directory: the
directories hold tiles no row names, and Phase-3 train/evaluate read the index — into a
tagged phase4 tile directory and writes the index in the engine's exact column shape
(`tile_name, site, split, row_off, col_off, canopy_frac, block, split_mode, img_path,
mask_path, height_path`; `block`/`height_path` empty, `split_mode` =
`config.SPLIT_MODE_SITEWISE`, paths Colab-absolute under the new directory; gated
against `tiling.py` by `test_phase3_tiles_as_tileset.py::test_index_columns_match_the_engine`).
The sidecar is the same file the engine writes and the harvest above reads, so the set
gets a registry row and `cli._record_tilesets` stamps run manifests with its id. Its
keys, and which side of the hash each sits on:

| key | hashed into `tileset_id`? | meaning |
|---|---|---|
| `label`, `materializer` | yes | `"2020"`; the writer's name, so a reader never mistakes this for an engine signature |
| `citywide`, `stride`, `max_tiles`, `tile_size`, `use_hillshade`, `hs_source`, `use_vi` | yes | the engine's own knob names, with the values the source tiles were cut at (`stride` MEASURED from the index offsets, never assumed) |
| `label_masks` | yes | `[{name, size}]` of `phase3/labels/*_canopy_mask.tif` — the label rasters the tiles were cut from, in the engine's 6-site shape, so the registry's `label_source` column names them |
| `provenance` | yes | `source`, `source_index`, `source_index_sha256`, `source_imagery`, `source_labels`, `n_train`, `n_test` |
| `split_status` | **no** (`config.META_NONSIG_KEYS`) | the engine's fields (`mode`, `degraded`, `stride`, `tile_size`, `overlapping`, `test_frac` computed, `train`/`val`/`test`/`dropped`) PLUS the per-run fields: `materialized_utc`, `materialized_by`, `run_tag`, `orphan_tiles_not_indexed` |

READER RULES. **Same source ⇒ same id across tags**, by construction: everything per-run
sits under `split_status`, so two directories materialized from one index (2026-09-09:
`2020__base50` and `2020__base18`, both `523f021cba6b`) are one tile set in the registry —
which is what makes "both bases trained on the same tiles" a checkable claim rather than
an assumption. An idempotent re-run keeps the original `materialized_utc`. The recorded
split is `sitewise_random_test`: non-overlapping at stride 512 but NOT spatially blocked
and NOT LOSO — evaluate rows on it are training sanity numbers, not honest hold-outs.
**Never run `--step tile` under one of these tags**: the meta can never equal a live
`_tile_signature`, so the engine would judge the cache invalid and re-tile over the set.

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

### backbone_benchmark.csv (GENERATED — byte-compared)

Written by `qc/instruments/backbone_benchmark.py`: the resnet101 reference table the
backbone sweep (`experiments/backbone_sweep.yaml`) has to reproduce on a smaller
encoder. A PROJECTION of `phase4/qc/arm_metrics.csv` — no lake, no GPU — copying, for
each of the nine benchmark arms (`BENCHMARK_ARMS` in the instrument: the five Tier-1
base arms, the two 2011s seed replicates, the confirmed-positive `t1_2016_in05` and
the null `t1_2011s_cor05`), the `matched_p75` and `best_f1` rows measured on ONE
population: `ref = ccap_2021_hires_lc.tif`, `canopy_def = forest_wetland`,
`eval_scope = sample-test` — the same basis as `phase4/qc/tier1_results.csv` and the
Tier-1 verdict. Values are copied as strings, never re-rounded, so the file is
byte-identical across runs. Columns: `arm, year_label, treatment, encoder, policy,
population, recall, precision, f1, pr_auc, thresh, n_eligible_cuts, curve_id, source`.
`treatment` is the tag with its `t1_{year}_` prefix removed; `curve_id` joins back to
`curves/{id}.csv`.

READER RULE: **the population is fixed by construction, so a second `ref` never
appears here** — that is the point. `arm_metrics.csv` holds 2-3 rows per arm-policy
(one per reference raster), and picking 2016's `ccap_2016` row over its `ccap_2021`
row moves matched recall by 5 pp; the instrument refuses anything but exactly one hit.

The **noise-floor block** (`arm = NOISE_FLOOR_2011s`, `treatment` in `min | max |
spread`) is derived in the same run from the three 2011s seeds
(`t1_2011s_base`, `_s2`, `_s3`), per policy, for recall / precision / f1 / pr_auc;
`population`, `thresh`, `n_eligible_cuts`, `curve_id` are blank and `source` names the
three tags. `spread` of recall at `matched_p75` is the max pairwise |delta| the Tier-1
verdict used as its floor; the gate pins it to the verdict text. An encoder's own
floor comes from ITS three seeds, never from this block. Gates:
`test_backbone_benchmark.py::test_benchmark_csv_is_fresh` (byte-compare),
`::test_noise_floor_rows_are_derived_from_the_three_seeds`,
`::test_the_recall_floor_matches_the_tier1_verdict`,
`::test_benchmark_encoder_matches_the_run_passports` (the `encoder` column is what
the Tier-1 train manifests recorded, via `run_passport.csv`), and
`::test_sweep_arms_are_derived_from_the_benchmark_list`.

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

## The scratch cache journal (VM `LOCAL_SCRATCH/.cache/`, EPHEMERAL — lives as long as the runtime)

Written and read only by `pipeline/phase4seg/scratchcache.py`; nothing here reaches
the lake or the repo, and the whole tree dies with `/content`. Documented because two
processes on one VM and many threads in one process all read it, and its semantics are
what decide whether a multi-GB payload is still there when a step opens it.

| file | writer | meaning |
|---|---|---|
| `{key}.json` | `stage` (temp + os.replace), `adopt`, `sweep` | one entry record. `key` = 8-hex sha256 of the FULL source path (`_key`; the same hash `common.py::_scratch_name` puts in the payload name). Fields: `state` (`copying` \| `ready`), `key`, `src`, `src_size`, `src_mtime`, `payload` (basename under `LOCAL_SCRATCH`), `bytes`, `pid`, `host`, `ts_start`, `ts_ready`, `last_use`, optional `adopted`. A hit re-validates `src`, `bytes`, `src_size` and `src_mtime` (±`MTIME_TOL_SEC`) against a live stat of the source — a size/mtime check, NOT a content check |
| `pins/{key}.{pid}.pin` | `_lookup` (hit), `stage` (after publish), `pin`, `adopt` | a reader's claim on the entry. Dropped by `release` / `common.py::_unstage_imagery_local`, by `_delete_entry`, or by the reaper when its pid is dead (`names.pid_alive`) or it is older than `PIN_MAX_MIN` |
| `cache.lock` | `_cache_lock` | the flock serialising metadata work between processes (a no-op off POSIX) |
| `{payload}.part.{pid}.{hex}` | `stage` | an in-flight copy; swept by pid on the next `stage()`, or by age (24 h) |

READER RULES.
- **The sidecar defines ownership.** The evictor may delete only a payload with a
  `ready` record; everything else under `LOCAL_SCRATCH` (`tiles/`, `bundles/`, write
  artifacts, stumps) is un-owned and untouchable.
- **A live pin protects the entry from `reserve()` / `stage()` eviction, from
  `invalidate()` and from the pre-clear — whoever holds it, this pid included.** The
  one place an OWN pin is not honoured is `_lookup`'s stale-entry delete, where that pin
  is `adopt`'s keep-for-postproc claim and refusing would cost a 60-100 min FUSE read.
- **Pins are per PID, so one process's threads share one pin and cannot see each
  other through it.** `stage()` therefore serialises same-key callers within a process
  (`_key_lock`, held for its whole body): the first copies, the rest hit. Before that
  lock existed, step_inference's 8 reader threads staged the CHM concurrently, 7 of them
  copied, and each publish unlinked the name a sibling had just been handed
  (2026-09-09, `qc/known_failures.yaml` "No such file or directory" scratch entry).
- **The publish is a bare atomic `os.replace`.** The canonical name is made absent once,
  by `_clear_destination` BEFORE the `copying` record is journalled (that is what keeps
  `sweep`'s size-based promotion sound); it is never unlinked again, so a name that
  resolved once keeps resolving — to the old bytes or the new, never to nothing.
- `reserve()` is advisory: it evicts toward the floor and reports whether the bytes fit,
  and no caller gates on it. Its eviction ladder and the floor are in the module
  docstring, one home.

Gate: `qc/test_scratch_cache.py` (every guard in a mutation pair).

## semantic_eval_<run_id>.csv (lake `phase4/eval/runs/`, WRITE-ONCE per evaluate)

Written by `phase4seg/core.py::_write_per_run_eval`, called from `step_evaluate` BEFORE
the shared `semantic_eval_report.csv` is read or rewritten. One file per evaluate run,
named by the run's `run_id` (`cli.py`: `<utc>_<years>_<tag>_<step>`;
`unrecorded_<utc>_<label>_<tag>_evaluate` when the engine is driven with no manifest).
Path rule and glob live in `phase4seg/names.py` (`EVAL_RUNS_DIRNAME`, `eval_run_name`,
`eval_run_files`) — three readers, one spelling.

WHY IT EXISTS (2026-09-09, `experiments/backbone_sweep.yaml`
`extra.cross_vm_eval_report_clobber`). The shared report is read-modify-written by every
evaluate step through rclone's async upload cache; two runtimes evaluating one year
minutes apart each read a copy lacking the other's rows and the last upload wins.
bb18_2006s_base's rows vanished from both the live report and the superseded archive.
This file cannot be clobbered: nothing but its own run ever opens it for writing, and
a second write under an existing name is refused (the file is left as written).

COLUMNS: exactly the shared report's, for the same run — `year gsd_cm tier channels
eval_scope scope site` + the metric columns + `op_thresh *_op` + `run_tag run_id
written_utc encoder warm_start` — both the `site` rows and the single `OVERALL` row.
It is the report's rows for this run, verbatim, in a file of their own.

READER RULES. (1) `VERIFY:evaluate` (`queue_verify.py::_verify_eval_rows`) asks the
shared report first; when that reads MISSING or STALE_EVAL it accepts a per-run file
under this year and tag written since the step started, records OK, and its `detail`
NAMES the file (`… in runs/semantic_eval_<run_id>.csv …`) — so a ledger row says which
home the pass stands on. Neither home → still MISSING. (2) The shared report is STILL the
deployed-threshold source (`postproc._operating_threshold` reads its last row per
arm); this file is evidence and archive, never a threshold input. (3)
`eval_rows_from_logs.py --compare` counts these files: a gap whose run_id has one is
`per_run_file`, on record in full. Gates: `qc/test_eval_per_run.py` (write side,
ordering), `qc/test_queue_verify.py` (accept / still-MISSING),
`qc/test_eval_rows_from_logs.py` (verdict).

## eval_from_logs.csv + eval_report_gaps.csv (phase4/qc/, HARVESTED — re-harvest, never edit)

Written by `qc/instruments/eval_rows_from_logs.py` (`--compare` for the second file).

WHY THE FILE EXISTS. `phase4/eval/semantic_eval_report.csv` is one shared lake file that
every evaluate step read-modify-writes through Drive's async upload cache. Two Colab
runtimes evaluating minutes apart each read a copy lacking the other's rows, and the
last upload wins: observed 2026-09-09 05:44Z, bb18_2006s_base and bb50_2006s_base on
two VMs, the report kept bb50 and lost bb18. The per-step log
`phase4/logs/phase4_semantic_finetune_evaluate_<year>_<stamp>.log` is one file per run
and carries the same headline metrics, so it is the record that survives.

`eval_from_logs.csv` — one row per evaluate log, sorted by `run_id` then `log_file`,
byte-identical across runs. `run_id` may be `unrecorded` (filter the column to see which).
`encoder` is the `--encoder` flag, `resnet101` when absent. `warm_start` is the
`--warm-start` flag if ever present — empty on every row by observation (no log prints
it), not by bug. `eval_scope` is the bracketed text after `Eval tiles:` (`held-out test`
or `IN-SAMPLE (no held-out test at this GSD)`); `n_eval_tiles` the count before it.
`model_file`, `phase`, `val_bce` from the `Model:` line. `iou dice acc prec rec` are the
headline line at the 0.50 cut; `op_thresh iou_op dice_op prec_op rec_op` the
`@ operating thresh` line; `auroc`, `best_f1_thresh` their own lines. `written_utc` is
the log's `completed:` stamp (Colab clock, UTC) in the report's own `…Z` form, the
filename time if no stamp line. `note` is `no metrics line` when the step died before
scoring (metrics blank), else empty.

`eval_report_gaps.csv` — `run_id year run_tag encoder iou log_file verdict`: the logged
run_ids the live report's OVERALL rows lack. READER RULE: a gap is not a clobber; read
`verdict`. `superseded` = the run_id sits in `semantic_eval_report_superseded.csv`: a
later evaluate's write archived it (the archive key is year/channels, e.g. `2006s/rgb`,
not the arm — observed in the bb18 log, which archived 8 rows). On record, not lost.
`per_run_file` = the run_id has its own `phase4/eval/runs/semantic_eval_<run_id>.csv`
(section above; every evaluate since 2026-09-09, written before the shared report):
on record in full, the shared report merely never received or later dropped it.
`--runs-dir` overrides the default `<eval report dir>/runs`.
`pre_run_id_era` = the run_id
sorts before the earliest run_id either report file carries (the report gained the column
2026-08-31); those rows cannot be joined and their absence is a schema gap, not a loss.
`clobber_candidate` = in neither file and inside the recorded era — the log is the only
copy of those metrics. Blank / `unrecorded` run_ids are skipped and counted on stdout.
The instrument never writes the eval report; recovering a row into it is a separate,
deliberate act.

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
  `postproc`, `discover sites <label>`, `bundle copy <label>`, and
  `bundle stall <label>@<N>MiB` — which is NOT a
  point event but a member of family (1) enclosed by its own `bundle copy` row, one per
  chunk of the bounded read (`staging.py::_bounded_copy`) that took ≥ its `STALL_S`, with
  the byte offset in the LABEL because `_EVENT` anchors on the line ending in `<N>s`. Two
  consequences for a reader: sum-within-family applies (the stall seconds are already
  inside the copy row), and **a `bundle copy` row can time an ABORTED read** — the
  bounded read refuses on a throughput floor or a stall ceiling and the row is still
  published, deliberately, because the seconds were really spent. What says it was an
  abort is the `(tile bundle not used: … MB/s … budget …)` line immediately after it, not
  anything in this CSV, so never average `bundle copy` without checking the log for that
  line. `discover sites <label>` (2026-09-08) times `common.py::discover_site_footprints`
  — the PHOTOS_DIR site-photo listing plus one crown-layer read per training site, all of
  it over FUSE — and takes no `bytes` by construction. Where it comes from decides
  whether it is here at all: `tiling.py::step_tile`'s late citywide discovery prints
  inside the tile step's own StepLogger and IS harvested (`<label>` is that year), while a
  SITE-recipe run discovers once in `cli.py::main` before any StepLogger opens, so that
  line — same shape, `<label>` the comma-joined years the one call serves — reaches only
  the queue's `train_queue_nohup_*.log`. An absent `discover sites` row is therefore not
  evidence that discovery was skipped. Until 6276207 there was no row at all and the
  seconds sat in the queue's `launching` phase, attributed to no step; since 6276207 the
  citywide call has been inside the tile step's wall-clock but with nothing separating it
  from the rest of the step. The duration is UNMEASURED until the next tile step reads it.
  (2) The per-epoch BUCKETS
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

## The `_12ep` healer files (phase4/qc/, GENERATED — the dense-stack reads)

`temporal_heal_12ep.csv`, `heal_vs_gold_12ep.csv`, `heal_closing_baseline_12ep.csv`,
`heal_gap_spectrum_12ep.csv`, `heal_fill_audit_sample_12ep.csv` and
`heal_fill_audit_design_12ep.txt` are the SAME instruments, SAME columns (headers
byte-identical to their un-suffixed siblings, checked 2026-09-10), run on the twelve-epoch
stack `D:\edmonds-pipeline\heal_stack_2m.npz` (built by `qc/instruments/heal_stack_build.py`;
8 trend8 epochs + heal_2017/2020/2022/2023; parity gate: the 8 shared epochs identical to
`trend8_stack_2m.npz`). The un-suffixed files stay the published 8-epoch reads — the
trend8 series the recalibration campaign ruled on — and are NOT overwritten, because the
two stacks answer different questions: 8 epochs is what the annual fraction series was
built from, 12 is what the healer's decision rule (`experiments/heal_infill_2017_2023.yaml`)
is scored on. Read the suffix as "which stack", never as a version. Reproduce:

    py -3.12 qc/instruments/temporal_heal.py        --stack <stack> --out phase4/qc/temporal_heal_12ep.csv
    py -3.12 qc/instruments/heal_vs_gold.py         --stack <stack> --out phase4/qc/heal_vs_gold_12ep.csv
    py -3.12 qc/instruments/heal_closing_baseline.py --stack <stack> --heal phase4/qc/temporal_heal_12ep.csv --out ..._12ep.csv
    py -3.12 qc/instruments/heal_gap_spectrum.py    --stack <stack> --heal-vs-gold phase4/qc/heal_vs_gold_12ep.csv --out ..._12ep.csv
    py -3.12 qc/instruments/heal_fill_audit_sample.py --heal <stack> --out ..._12ep.csv --design-out ..._12ep.txt

One column is EMPTY by construction on the 12-epoch spectrum: `crowns_eligible` /
`crowns_deleted` (the crown rasters are 8-epoch; the instrument prints the SKIP).


## heal_fill_audit_sample.csv + heal_fill_audit_design.txt (phase4/qc/, GENERATED then HAND-LABELLED)

Written by `qc/instruments/heal_fill_audit_sample.py::main` (columns:
`heal_fill_audit_sample.py::COLS`; the draw: `::build`). The CSV is a **worksheet**: the
instrument writes every column except the last two, a human fills those two in, and
nothing else in the file may be edited — the estimator reads the design columns back.
`heal_fill_audit_design.txt` is its metadata sidecar (this instrument's equivalent of
`phase4_accuracy_sample.py`'s `sample_{year}_meta.json`), carrying strata populations,
Olofsson weights, the refusal list and the detectable-effect table. **The manifest
deliberately carries no `#` trailer** — a human edits it, and trailing comment rows do
not survive a spreadsheet round-trip.

One row per AUDIT UNIT. The unit is a **fill component**, a connected patch of the
healer's own output at or above `temporal_heal.py::MIN_AREA_M2` (28 m2, one mature
crown) — not a 2 m cell. Every count and bound in the sidecar is per component.

| column | meaning |
|---|---|
| `unit_id` | `F`/`C` + filled epoch + zero-padded `row`_`col` of the anchor cell — stable across reruns of the same stack |
| `blind_order` | seeded presentation order, 1..N. Reading in `unit_id` order would present all fills before all controls |
| `is_control` | 1 = a control unit the healer did NOT touch; 0 = a fill |
| `stratum_id` | index into the DECLARED stratum universe (tier x gap bucket x size class), stable as populations change |
| `stratum_name` | the three stratum axes joined by a pipe: tier, gap bucket, size class |
| `tier` | `HEAL` / `REVIEW` / `BLIND`, from `temporal_heal.py::tier_for` |
| `gap_left_yr` | years from `epoch_prev` to `epoch_filled` |
| `gap_right_yr` | years from `epoch_filled` to `epoch_next` |
| `gap_years` | `max(gap_left_yr, gap_right_yr)` — the quantity the tier rule itself keys on |
| `gap_bucket` | `1-2` / `3` / `4+` on `gap_years` |
| `size_class` | crown-diameter bin from `detectability_curve.py::BINS`, on the component's equivalent-area diameter |
| `bracket_years` | `epoch_next - epoch_prev`, the unobserved span a cut-and-regrow could hide in |
| `epoch_prev` | the epoch BEFORE the gap — first of the three the reader views |
| `epoch_filled` | the epoch judged: was canopy truly there? |
| `epoch_next` | the epoch AFTER the gap |
| `x` | easting of the anchor cell centre |
| `y` | northing of the anchor cell centre |
| `epsg` | `config.ANALYSIS_GRID_EPSG` — the analysis grid, never a native acquisition grid |
| `row` | anchor cell's row on the 2 m stack lattice |
| `col` | anchor cell's column. The anchor is the member nearest the centroid, so it is always INSIDE the component — a concave patch's centroid can fall outside it |
| `n_cells` | component size in 2 m cells |
| `area_m2` | `n_cells` x 4 |
| `equiv_diam_m` | `2*sqrt(area/pi)` — the same estimator `pipeline/frozen/phase0_instance_seg.py` used for the crowns' `diameter_m`, so the bins transfer |
| `control_flank` | controls only: which flank showed canopy (`prev` / `next`). Blank on a fill |
| `adjudicable` | 1 = an independent modality covers this point within `ADJ_MAX_DYEAR` of `epoch_filled` |
| `adjudicator` | the modality's name (lidar CHM), blank when none |
| `adjudicator_dyear` | `epoch_filled - modality year`; 0 means temporally native |
| `adjudicate` | 1 = in the adjudicator sub-draw, stratified by tier AND `is_control` |
| `present_in_filled_epoch` | **THE HUMAN COLUMN.** `yes` / `no` / `unsure`. `no` at a fill is a laundering event; `unsure` is first-class and excluded from the rate, never coerced (CLAUDE.md 3.6) |
| `notes` | free text from the reader |

READER RULES.

**A `no` on a `REVIEW` or `BLIND` row is not a laundered mask.** Those tiers write
IGNORE, not canopy (`temporal_heal.py::build`). A `no` there says what the both-sides
rule WOULD have laundered had the tier been promoted — evidence about the tier policy,
not about delivered output. Only `HEAL` rows score written canopy.

**The control is a DISCRIMINATION control, not a blinded error-rate control.** It is
drawn from absences with exactly ONE aligned flank present, because the literal
population (untouched absences with BOTH flanks present) is empty by the operator's own
definition — a count the sidecar MEASURES rather than asserts. Its flanks look different
from a fill's, so `blind_order` randomises order but cannot blind the reader to which is
which. The only independent evidence in the file is the `adjudicate` sub-draw.

**No CHM value appears here, deliberately.** `adjudicable` is a coverage flag. Writing
the height would hand the reader the answer the adjudication step exists to check
independently.

Gate: `qc/test_heal_fill_audit_sample.py` (which also holds this column list to
`heal_fill_audit_sample.py::COLS`). Regenerate:
`py -3.12 qc/instruments/heal_fill_audit_sample.py` — deterministic under its seed;
**regenerating discards any labels already entered.**

## heal_gap_spectrum.csv (phase4/qc/, GENERATED)

Written by `heal_gap_spectrum.py::main` from `heal_gap_spectrum.py::spectrum`. One row
per GAP-LENGTH BUCKET, plus one negative-control row. The bucket key `L_years` is the
bracket span in whole calendar years, `int(next) - int(prev)` via
`temporal_heal.py::_year_int` — the healer's own arithmetic, and the same quantity
`temporal_heal.py::tier_for` thresholds on, so a row's tier composition and its L are
derived from one definition rather than two.

Why the file exists: the healer's safety number was one scalar (zero of 42 verified
losses laundered) and the fill-odds expression four fields converge on carries
`(1-gamma)^(k-1)` in its change-path denominator, so the risk per fill is a function of
bracket length and must be published as one
(`Reports/LIT_HEALING_ANALOGUES_2026-09-08.md`, G3). The scalar also had no denominator,
and a zero with no denominator cannot distinguish an operator that refused from a
population that could not contain the event.

| column | meaning |
|---|---|
| `row_kind` | `spectrum` (one per bucket) or `negative_control` (median-L bucket, gold labels permuted) |
| `L_years` | bracket span in whole calendar years — the bucket key |
| `n_epochs` | interior epochs whose bracket spans this L |
| `epochs` | those epoch labels, `\|`-joined |
| `L_days_measured` | median span in DAYS over the epochs in the bucket whose BOTH endpoints resolve in `qc/imagery_pixelsize_and_date.csv`; blank when none do |
| `n_epochs_dated` | how many of `n_epochs` contributed to it — read this before `L_days_measured` |
| `tier_HEAL` | epochs in this bucket the healer let assert canopy — a lidar epoch could have vetoed a real removal and did not |
| `tier_REVIEW` | epochs post-lidar with gaps under three years: flagged, IGNORE-written, never silently healed |
| `tier_BLIND` | epochs whose bracket has a gap wide enough for coppice to cross. L does NOT determine the tier — `temporal_heal.py::tier_for` keys BLIND on the LARGER single gap, so one L can hold both |
| `n_eligible` | 2 m cells that COULD have been filled at this L — absent at the epoch, canopy on both aligned flanks, all three epochs valid. The bracketed-absence denominator |
| `n_fills` | cells the healer actually wrote (canopy + IGNORE), read off the healed array rather than the overlay |
| `n_fills_canopy` | of those, written 0 -> 1. Only the HEAL tier asserts canopy |
| `n_fills_ignore` | of those, written 0 -> 255 (REVIEW and BLIND mark the cell unknowable) |
| `fill_rate` | `n_fills / n_eligible` — what the size floor let through, not a probability |
| `fills_outside_eligible` | cells written where the bracket predicate is FALSE. Must be 0; non-zero means the candidate reconstruction has drifted from `temporal_heal.py::build` |
| `gold_loss_n` | verified losses scored on this run (on-grid) |
| `laundered` | point-epochs at this L where a verified loss's TERMINAL absence was filled to canopy — the harm, attributed to the bracket that made it |
| `laundered_points` | distinct verified losses behind `laundered` |
| `laundered_eligible` | POSITIONAL denominator: verified losses whose terminal absence overlaps a bracket of this L |
| `laundered_at_risk` | the denominator with teeth: of those, the ones where the bracket predicate actually fires at the cell. Zero here means `laundered = 0` is pinned by trajectory shape, not earned |
| `laundered_rate_ci95_upper` | one-sided 95% ceiling on the laundering rate over `laundered_at_risk`; `1-0.05^(1/n)` when the count is 0. BLANK when nothing is at risk — a ceiling over an empty denominator is not a ceiling |
| `censored` | terminal absences marked 255 instead: the event is not erased but a change detector can no longer see it |
| `triples_present` | raw present-absent-present triples centred on an epoch of this L, at the verified no-change points |
| `triples_removed` | of those, the ones healing closed. The win side |
| `crowns_eligible` | crowns whose RAW ladder holds a SINGLE-epoch ABSENT at this L flanked by PRESENT — a validity-interval boundary pair. BLANK, never 0, when the comparison was skipped: `--no-crowns`, no gpkg on the local mirror, or a `--stack` whose epochs are not the crown rasters' (the trailer's `crowns_note` says which) |
| `crowns_deleted` | of those, the ones healing closed, merging two presence episodes into one. Blank on the control row (crowns do not depend on the gold labels) and blank whenever `crowns_eligible` is |
| `notes` | free text; carries the shuffle seed on the control row |

**Read `laundered_at_risk` before `laundered`.** A verified loss's terminal absence runs
to the END of the series (`heal_vs_gold.py::build` defines it by walking back from the
last epoch), so the epoch after any interior epoch inside that run also reads absent and
a both-sides fill predicate cannot fire there. Every alignment shift on the trend8 stack
rounds to zero cells — `temporal_heal.py::shift_mask` quantises to whole 2 m cells and
the largest published shift is 1.0 m — so nothing rescues it. `laundered = 0` on this
stack is therefore a criterion with no power rather than a bound, and the file publishes
both denominators so a reader cannot mistake one for the other.

**A non-zero `crowns_deleted` in an all-BLIND bucket is not a fill.** BLIND epochs write
255, and `detectability_curve.py::per_crown_cover` divides by the VALID cell count, so an
IGNORE write shrinks the denominator and can lift a crown out of ABSENT with no canopy
asserted anywhere. Multi-epoch absent runs sit inside more than one bracket and are held
out of the per-L attribution entirely; the trailer counts them as
`crown_multi_epoch_runs`.

**Trailer.** `epochs`, `n_gold_points_on_grid`, `off_grid`, `median_L_years`,
`shuffle_seed`, the `*_total` sums, `crown_multi_epoch_runs`, `analytic_null` (the base
rate scaled to the verified-loss count — exact, where one permutation of 42 from 1,214 is
not), one `date_basis_{epoch}` per epoch (`measured` / `undated` / `ambiguous` /
`no-row`), `crowns_note` when the crown comparison was skipped (e.g. `SKIPPED (crown
rasters are 8-epoch, bundle is 10-epoch)` — the crown rasters live on the published
8-epoch cache; `crown_multi_epoch_runs` is then BLANK, not 0), and `crosscheck_heal_vs_gold`, which reports whether the per-L triple
attribution sums to the aggregate the `--heal-vs-gold` file published (default: the
tracked `heal_vs_gold.csv`; a `--stack` run must pass the one produced on that stack, or
the line compares two archives). Reported rather than asserted: a stale
`heal_vs_gold.csv` is a reason to re-run that instrument, not to fail this one — the
assertion lives in
`qc/test_heal_gap_spectrum.py::test_real_csv_agrees_with_heal_vs_gold_on_the_totals_it_shares`.

Gate: `qc/test_heal_gap_spectrum.py`, whose two mutation tests are the only evidence the
laundering counter can move at all (CLAUDE.md 3.4c). Regenerate:
`py -3.12 qc/instruments/heal_gap_spectrum.py` (~100 s local; `--no-crowns` drops to
~12 s by skipping the 2020 crown raster). Deterministic — two runs are byte-identical.

## heal_fill_odds.csv (phase4/qc/, GENERATED — an AUDIT column, never a licence)

Written by `qc/instruments/heal_fill_odds.py::build`, one row per fill the healer made —
the connected component `temporal_heal.csv` counts as `n_components`, re-labelled from
the healer's own kept mask with the same 8-connectivity, so the per-epoch counts match
that file exactly (the instrument prints the comparison). Carries the fill odds four
literatures converge on (`Reports/LIT_HEALING_ANALOGUES_2026-09-08.md` §3, §6 G7;
requested as §14 (d) of `Reports/HEALING_TOOL_REASONING_2026-09-07.md`):

    Λ = ∏(1-ε_i) · ∏_{t in gap}(1-p_t) / [ ε_first · γ · (1-γ)^(k-1) ]

Columns: `fill_id, epoch, prev_epoch, next_epoch, tier, k, gap_years, dt_left_yr,
dt_right_yr, dt_basis, n_cells, area_m2, crown_id, crown_diam_m, size_class, crown_cells,
fill_cells_in_crown, fill_share_of_crown, crown_cover_raw, p_t_list, p_t_source,
miss_product, epsilon_interval, epsilon_interval_next, gamma_interval_colonisation,
gamma_interval_emptysite, lambda_colonisation, lambda_colonisation_emptysite,
lambda_rule, log10_lambda_colonisation, log10_lambda_rule, posterior_fill_colonisation,
posterior_fill_colonisation_emptysite, posterior_fill_rule`

**READER RULE, and it is the whole point of the file: Λ IS NOT A LICENCE.** The `tier`
column is what licensed the fill. Λ's denominator needs γ_conditional =
P(regain | recent removal), which is UNMEASURED; the two γ columns are stand-ins of
different kinds and are never interchangeable:

- `*_colonisation` — MEASURED, WRONG QUANTITY. P(colonisation | empty site) from the
  panel's gains, on two denominators: all gold points (`lambda_colonisation`) and
  empty sites only (`lambda_colonisation_emptysite`). §3's ~422 empty sites is
  `[inferred]` in `Reports/CHANGE_DETECTOR_DESIGN_2026-09-06.md`; the trailer publishes
  BOTH it (`empty_site_denom_reported`) and the count measured here from the gold's own
  trajectories at the interval's first epoch (`empty_site_denom_measured`), and names
  which one the column used (`empty_site_denom_used`). Under either, the posterior is
  ~1 for every fill — §3's finding reproduced, not a result about any given fill.
- `*_rule` — RULE-IMPLIED, NOT MEASURED, and the trailer says so in a machine-readable
  cell (`gamma_rule_is_measured,0`). γ = 0.20 is the value at which §3's sensitivity says
  the posterior reproduces the project's tier logic. It is NOT Δt-scaled, because §3 uses
  it directly at k = 1 (pinned by
  `qc/test_heal_fill_odds.py::test_reproduces_the_reports_gamma_rule_crossing`), while ε
  IS per-interval — the two sit on different bases, deliberately and visibly.

`p_t_list` is the detection probability per absent acquisition and `p_t_source` names the
exact row it came from, `{epoch}|bin|{size_class}` in the file the trailer's
`p_t_source_file` points at (`phase4/qc/detectability_curve.csv`, `kind=bin`). **A blank
Λ means the curve had no value — never a default.** That happens when the fill overlaps no
2020 crown, so no size class exists; `qc/test_heal_fill_odds.py` pins that a blank Λ never
sits beside a populated `p_t_list`, and that a populated Λ always names its source.

`k = 1` on every row on this stack: `temporal_heal.py::build` only ever tests a single
absent epoch, so `(1-γ)^(k-1)` is inert here. The column is kept because the formula is
general and the healer's candidate rule is not a property of the formula.

**The fill is not the crown, and the curve only models crowns.** `p_t` is
P(a crown reads ≥ 0.50 cover | both flanks saw it) — crown-level — while a fill may be a
sliver of an otherwise-detected crown. Read `crown_cover_raw` (the dominant 2020 crown's
RAW canopy fraction at the gap epoch) and `fill_share_of_crown` before reading Λ: near 0
cover is the whole-crown miss the curve models, mid-range cover is a partial miss it does
not. Crown attribution is max-overlap against the 2020 delineation rasterised by
`detectability_curve.py::load`, the same geometry the curve itself was measured on.

`dt_basis` says whether each side's Δt came from acquisition dates
(`qc/imagery_pixelsize_and_date.csv`, midpoint of the flight window) or fell back to the
year labels. 2011s has no date in that table at all, so both of its intervals fall back.
Dated, 2013→2015 is 1.73 yr and 2015→2016 is 1.46 yr because the 2015 acquisition is a
February–March flight — the same leaf-off flight behind that epoch's low measured recall,
which is why Λ argues loudest for filling where the SEASON changed. The formula has no
term for that, and none of the four biases in the instrument's docstring is corrected.

Gate: `qc/test_heal_fill_odds.py`, whose mutation pair is the evidence the statistic's
kill direction works at all (CLAUDE.md 3.4c): p_t → 1 must drive Λ → 0 and the posterior
below 0.5; p_t → 0 must drive it up. Regenerate:
`py -3.12 qc/instruments/heal_fill_odds.py` (~95 s local; reads the trend8 stack and the
2020 crown GPKG read-only, writes nothing outside `phase4/qc/`).

## heal_closing_baseline.csv (phase4/qc/, GENERATED — the comparator baseline)

Written by `qc/instruments/heal_closing_baseline.py::build`: the plain 1-D temporal
closing §4.9 of `Reports/LIT_HEALING_ANALOGUES_2026-09-08.md` holds as the baseline "any
learned or tiered heal must beat" (M3, STANDS as comparator), swept over gap caps and put
beside the healer's own row. One row per arm.

Columns: `arm, rule, K, K_unit, n_gold_points, gold_cells_filled, gold_points_filled,
loss_cells_filled, loss_points_filled, laundered_terminal, n_eligible_terminal,
laundered_in_interval, n_eligible_in_interval, terminal_censored, nochange_triples_raw,
nochange_triples_after, nochange_triples_removed, nochange_triples_removed_canopy_only,
loss_triples_raw, loss_triples_after, citywide_cells_filled, citywide_ha,
citywide_cells_ignored`

`rule` is the cap's unit, because the units disagree and the disagreement is §4.9's
central objection: `acq` caps the run in acquisitions (the literal closing), `step_years`
caps the largest inter-acquisition step in the bracket — the unit
`temporal_heal.py::tier_for` actually uses — `span_years` caps the total bracket span, and
`tier_matched` is `acq ≤ 1 AND step ≤ 2 yr`, the healer's non-BLIND candidate set with no
floor, no alignment and no tier. `arm=healer` is the healer's own row, scored through the
same function from the trajectories `heal_vs_gold.csv` publishes.

**READER RULE: `laundered_terminal` CANNOT FIRE, and `n_eligible_terminal` is why.** A
both-sides rule needs a detection AFTER the cell it fills; a terminal absence
(`heal_vs_gold.py::build`, walking back from the last epoch) has none. So the count is
structurally pinned at 0 for the closing at every K, for the healer, and for any
both-sides rule — `0 of 42 laundered` certifies nothing about this family (§6 G2, §4.9
M7). `laundered_in_interval` is the counter that can move: verified LOSS POINTS filled at
one or more epochs strictly inside the panel's own interval (read from
`panel_a_meta.json`; 2019 and 2021 on this stack), with `n_eligible_in_interval` — the
losses an UNBOUNDED both-sides rule could fill there — as its denominator. Publish the
pair, never the count. **Both pairs are PER POINT** (`laundered_terminal` too; only
`terminal_censored` stays in cells): a point filled at two interior epochs counts once,
so the count is ≤ its denominator by construction (every closing arm fills
only both-flanked runs and the unbounded closing fills all of them; the healer row, whose
flanks are aligned, is checked in `build()` and the table refused on overflow). Until
2026-09-08 the numerator counted per (point, epoch) fill EVENT — invisible on 8 epochs,
13 of 12 on the 10-epoch trial. The cells are in `loss_cells_filled`.
Both denominators come from `heal_closing_baseline.py::eligibility`, which uses the
unbounded rule so a narrow cap cannot flatter itself by shrinking its own at-risk set.

**`laundered_in_interval` is an UPPER BOUND, not an erasure count.** Asserting canopy at an
interior epoch of a verified loss is a NECESSARY signature of laundering, not a sufficient
one: if the trajectory still ends absent, the removal event survives and a change detector
still sees it — the same reasoning `heal_vs_gold.py` applies to the 5 upstream fills it
refuses to call harm. Read the shapes in `heal_vs_gold.csv` wherever the count fires. On
the trend8 stack all 4 eligible losses carry the identical shape `CCCCC.C.` (2016 canopy,
2019 absent, 2021 canopy, 2024 absent), so every in-interval fill available to any arm here
lands on 2019 and leaves the 2024 removal standing.

**`nochange_triples_removed` credits an IGNORE mark; `nochange_triples_removed_canopy_only`
does not.** `triples` tests `t[i] == 0`, so a cell marked 255 stops being a triple's
middle with no tree asserted anywhere. The healer's REVIEW/BLIND tiers write 255 by design
and the closing has no such state, so only the `_canopy_only` column compares like with
like (`heal_closing_baseline.py::canopy_only`). The two are equal by construction on every
`arm=closing` row.

`citywide_cells_filled` counts 0 → 1 writes over the whole city
(`heal_closing_baseline.py::citywide_fills`, enumerating every interior window through the
same `admits` the trajectory closing uses). For `arm=healer` it is `heal_tier_cells` from
`temporal_heal.csv` — HEAL-tier canopy only — and `citywide_cells_ignored` is what its
REVIEW/BLIND tiers marked unknowable instead. The closing has no IGNORE state, so that
column is 0 on every closing row.

**The closing runs on the UNALIGNED stack**; the healer shifts each flank by its validated
global offset first. On this stack that difference is nil and the file measures it rather
than assuming it: the instrument prints the largest whole-cell translation per epoch from
`temporal_heal.csv`'s own published shifts, and every one rounds to zero at 2 m
(`temporal_heal.py::shift_mask` translates whole cells). At an equal cap, therefore, the
healer minus the closing is the 28 m² size floor and the tier — not the transform, whose
claim is about native-resolution masks.

**Scoring is `heal_vs_gold.py`'s, re-implemented rather than re-factored** — that module
computes its scores inline inside `build()` and exposes no scoring function, so this file
calls it the way its own `main()` does (`heal_vs_gold.build()`) and re-scores the
trajectories it publishes. `build()` checks the re-implementation against
`heal_vs_gold.py`'s OWN per-row numbers for every gold point first and REFUSES to print or
write the table on any mismatch; the trailer records
`scoring_parity_mismatches`. Trailer also carries `panel_interval`, `interior_epochs`,
both `n_eligible_*`, and `closing_runs_on_the_unaligned_stack`.

Gate: `qc/test_heal_closing_baseline.py`, whose mutation pair pins both directions
(CLAUDE.md 3.4c): an injected in-interval loss registers at the cap that first admits its
run and not at the cap below, and the terminal counter stays at zero on adversarial input
built to trip it — the second is a criterion documented as unable to fire, not a pass.
Regenerate: `py -3.12 qc/instruments/heal_closing_baseline.py` (~22 s local).

---

## harm_spread.csv (phase4/qc/, GENERATED — byte-compared)

Written by `qc/instruments/harm_spread.py::render`, the cross-survey CONVERGENCE read for
`experiments/harmonization_h1_h2.yaml` (design: `Reports/HARMONIZATION_DESIGN_2026-09-10.md`).
A projection of `arm_metrics.csv`, so it cannot drift from it; regenerate, never edit:
`py -3.12 qc/instruments/harm_spread.py`.

Columns: `prefix, encoder, warm_start, treatment, ref, quantity, year, value, n_years,
years, floor, flag, note`

**The row's meaning is in `quantity`, and the file is long-format on purpose** — a spread
over four years and a spread over five are different statistics, so every derived number
carries the exact `years` it was computed on rather than an implied year set. Every
aggregate (`spread`, `h1_premise`, `ref_epoch_share`, `convergence_p`) is computed on the
FIVE pre-registered EXP-H1 years and on nothing else: a sixth acquisition — and the design
queues 2019s — keeps its `recall` row and never enters the statistic. Reading "whatever
years are present" instead once turned a 0.1400 base spread into 0.3400 and a promoting
(P) into a null, unflagged.

| `quantity` | value |
|---|---|
| `recall` | one arm's `matched_p75` recall at `year` |
| `spread` | max − min over `years` |
| `same_flight_gap` | \|recall(2019n) − recall(2019s)\| |
| `h1_premise` | the base spread, read as EXP-H1's K1 |
| `ref_epoch_share` | 1 − spread(C-CAP 2016)/spread(C-CAP 2021) on the common years — EXP-H1's K2 |
| `k1_interaction` | [(in16−in05)@2006s] − [(in16−in05)@2016] — EXP-H2's K1 |
| `k1_ref_verdict` | the two-reference clause of K1 APPLIED: fires against both references → leak; against one only → UNDETERMINED |
| `k3_gap_change` | gap(in16) − gap(base) — EXP-H2's K3, the mechanism read |
| `k4_2016_null` | (in16−base)@2016 — EXP-H2's K4, the pre-registered non-event |
| `convergence_p` | spread(in16) − spread(base) on the common years — EXP-H2's (P) |

**READER RULE — `prefix` is the population, not `encoder`.** `bb18` and `wb18` are the same
encoder from different starts (ImageNet vs the Phase-3 base checkpoint) and are not one
population; `warm_start` records which. Rows are keyed on the run tag parsed as
`<prefix>_<year>_<treatment>` with `treatment` in {`base`, `in05`, `in16`} — seed
replicates (`_base_s2`), corruption doses (`cor05`), adders (`add16`) and other inputs
(`nir`) are SKIPPED, never coerced into a treatment.

**READER RULE — `flag` is a pre-registered kill, and an empty `flag` is not a pass.**
`INCOMPLETE` means the year set is short of the five EXP-H1 years and the criterion cannot
be read at all; per CLAUDE.md §3.5 that is UNDETERMINED, never "no difference". Only
`h1_premise` on a complete five-year set can read `H2 premise dead`. Thresholds are the
design's, fixed before any arm ran: floor **0.0069** (the wb18 three-seed 2011s spread,
`experiments/backbone_sweep.yaml` verdict), spread floor **0.014** (2× floor, because a
spread is a max−min of five draws), reference-epoch cut **0.4**.

**READER RULE — `same_flight_gap` is a RECIPE-MATCHED number, and what differs is sampling
support.** `--tier` is inert for a queued arm (`cli.py::_resolve_years` filters rather than
overrides, and only when `--year` is absent), but the arms carry `--force-citywide`, which
applies the citywide COARSE recipe to every tier: the early-stop metric and the pos_weight
channel key on `use_blocked_val`, not the tier (`core.py::step_train`), `TIER_LOSS_MODE` is
one value at all tiers, and both years split through `tiling.py::_block_partition` at
0.20/0.20. So the two 2019 arms train alike; a 512 px tile is still 156 m of ground at
2019s and 307 m at 2019n, with 412 and 306 manifest tiles. Before quoting the ABSOLUTE gap,
confirm from the tile step logs that both arms recorded the same split mode — a
`_block_partition` degrade on one year only is a real recipe divergence. K3 reads the
CHANGE from `base` to `in16` (`k3_gap_change`), as the design writes it.

Gate: `qc/test_harmonization.py` — byte-freshness, parser strictness, and every kill shown
to FIRE on a known-bad synthetic input and stay silent on the matched control, plus a
REAL-DATA pin that the instrument reproduces the spreads the design cites from
`arm_metrics.csv`.

---

## harm_change_laundering.csv (phase4/qc/, GENERATED — UNVALIDATED on real rasters)

Written by `qc/instruments/harm_change_laundering.py::render`: EXP-H2's **K2**, the direct
non-circular test of whether `--hs-source chm2` compresses the cross-survey spread by
supplying generic structure or by PAINTING 2016 TREES onto older imagery.

Columns: `year, base_tag, in16_tag, ref, population, n_cells, base_thresh, in16_thresh,
base_call_rate, in16_call_rate, rise, floor, flag, note`

`population` is `gain` (certified 2005→2016 canopy gain), `flat` (certified-flat ground —
an absolute false-positive control), `all` (every valid sample-test cell), or
`gain_minus_all` — the K2 row, whose `rise` is `rise(gain) − rise(all)` and whose `flag`
reads `H2-K2 CHANGE LAUNDERING` above the floor, `K2 PASSES` below it.

**The GAIN population is REBUILT, not read.** `certified_change_cells.csv` is a four-column
COUNT table and cannot be intersected with a prediction, so this instrument re-derives the
mask from the rule inside its writer (`qc/instruments/certified_flat_scoring.py`):
`both & (h05 < 2 m) & (h16 ≥ 5 m)` with `h = (DN − 1) × 0.2`, on the **chm2005 2 m grid** —
the grid the rule is defined on. Probability rasters warp onto it with `Resampling.max`
(that file's stated convention, "asserts vegetation anywhere in the cell"); the
certified-flat mask warps with `nearest`, because it is an already-eroded binary that `max`
would regrow.

**READER RULE — every rate is inside the LOSO sample-TEST blocks and nowhere else.** These
arms infer only within `science_sample_blocks.gpkg`; outside it the prob raster is
`PROB_NODATA`, so there is no citywide rate to compare against. Both arms are scored on the
intersection of their valid cells, each at its OWN deployed `matched_p75` cut read from
`arm_metrics.csv` — the instrument REFUSES rather than inventing a cut for an unscored arm.
`--thresh` applies one cut to both arms and is for tests and diagnostics only.

**READER RULE — nothing in this file may be cited yet.** As of 2026-09-10 no `in16` arm
exists on resnet18, so the instrument has never run against a real pair. Its arithmetic,
its grid handling and its kill firing are gated on synthetic rasters
(`qc/test_harmonization.py`), which tests the CODE and not the CLAIM — CLAUDE.md §3.4c:
a design validated only on synthetic data is UNVALIDATED, in those words.
`--dry-run` lists every input and writes nothing.

## crown_state_vs_gold.csv + crown_state_placebo.csv (phase4/qc/, GENERATED — the referee's files)

Written by `qc/instruments/crown_state_vs_gold.py` (the independent referee's scorer for
`experiments/crown_state_model.yaml` and its successors). One row per Panel A gold point
(`phase4/qc/panel_a_gold.csv`, 1,214), scored through the crown state model's per-crown
trajectory (`qc/instruments/crown_state_model.py` → `phase4/qc/crown_state_posterior.npz`,
untracked: 6.6 MB binary, rebuilt in ~100 s) with the SAME definitions as `heal_vs_gold.py`
— laundered (terminal absence of a verified loss asserted as canopy), terminal-censored,
impossible triples raw / after / fixed — so the two trailers read side by side. Points
outside every 2020 crown are OFF-CROWN (`offcrown_n` in the trailer; 726 of 1,214 on the
first run) and are excluded from every kill denominator: the crown unit is scored on the
on-crown subset only, and any verdict must say so. Trailer keys mirror `heal_vs_gold.csv`
(`nochange_triples_raw/_healed/_fixed`, `loss_laundered`, `loss_laundered_points`,
`loss_has_terminal_absence` = the K1 at-risk denominator, `loss_term_censored` — zero by
construction, the model has no IGNORE state — plus `laundered_crown_obs0`, the count of
laundered epochs where the crown itself observed ABSENT).

`crown_state_placebo.csv`: one row per shuffled-rate draw (`--placebo-seed` 1..20) with
that draw's K1 and K2 counts and wall time (`secs`), and a trailer with `k3_true`,
`k3_p95` (nearest-rank 19/20), `k3_true_above_p95`, `k3_n_draws_ge_true`. This is kill K3.

`crown_state_intervals.csv` (18 MB, one row per crown: first_seen / last_seen and their
interval bounds) is a product, not evidence, and is NOT tracked; regenerate with the model.
Version suffixes: the v2 pre-registration writes `crown_state_v2_vs_gold.csv` and
`crown_state_v2_placebo.csv` so the killed v1 numbers stay on the record beside them.

## LITKB_SOAK.csv (Reports/, APPEND-ONLY — one row per night, header FIXED in S1)

Written by `pipeline/litkb/ops/nightly_soak.py` (`run()` then `append_row()`), from the scheduled
task `litkb-nightly-soak`, daily at 03:17 local — after the 02:30 `litkb-nightly-dump`, so a
night's dump is already on disk when the soak reads the database. One row per run, appended,
never rewritten. `--once` runs it by hand against live; the path is resolved from `__file__` and a
CSV outside the repository is REFUSED (`guard_path`), because an unattended nightly job with a
free `--csv` is an unbounded write primitive.

**The header is fixed here, in S1, and may not gain a column.** The soak clock starts in S1 by
Kam's ruling of 2026-09-20 (`LITKB_WORKPLAN.md` S7) so the nights accumulate while S2-S6 proceed;
S7's `qc/instruments/litkb_acceptance.py soak` has to read **every night from S1 onward**, and a
column added in S7 would split the log in two with the first nights in the unreadable half. That
is why `doctor_ok` and `doctor_detail` exist now and are written EMPTY: they are S7's two columns,
reserved.

| column | meaning |
|---|---|
| `ts_utc` | run start, `%Y-%m-%dT%H:%M:%SZ` |
| `host` | `socket.gethostname()` — litkb is local-only (`decisions.yaml` `litkb-p0-foundation`) |
| `repo_head` | `git rev-parse HEAD` in the MAIN tree; empty when git fails |
| `migration_tip` | the highest migration version **APPLIED to the database**, read as `litkb_owner` through the passfile. EMPTY when it cannot be read — `litkb_meta` is readable by the owner alone (measured 2026-09-20: `litkb_reader` and `litkb_writer` both get `permission denied for schema litkb_meta`, `litkb_ingest` refuses the login). It is never silently replaced by the on-disk tip: "what the repo holds" and "what the DB has applied" are different facts, and S7's `doctor` compares them |
| `search_ok` | `true`/`false`. FALSE on zero hits as well as on a refusal — the query is fixed against a work known to be extracted, so a zero-hit night is a defect, not a rephrasing |
| `search_ms` | wall milliseconds for `litkb.mcp.server._search`, the Python side of `litkb_search` (there is no `litkb.search` module; the implementation lives in the MCP module and the tool is a thin wrapper over it) |
| `search_hits` | blocks returned, capped at the limit (5) |
| `hunt_ok` | `true` **only when `hunt_state` is `extracted`**. Not `res["ok"]`: a hunt that correctly reports a database which has LOST the work returns `ok: true`, and that is precisely the regression this row exists to catch |
| `hunt_ms` | wall milliseconds for the cached-answer `hunt(spend=False, extract=True)` |
| `hunt_state` | the ladder state reached, or the refusal code, or `error` |
| `hunt_key` | the smoke target's work key — a module constant, so a row always says what it smoked |
| `doctor_ok` | EMPTY until S7 |
| `doctor_detail` | EMPTY until S7 |
| `error` | `search: …` / `hunt: …` joined by a pipe; empty on a clean night. A failing smoke still writes its row, and the process exits non-zero |

The smoke target is `Kaiser_2017_learning-aerial-image-segmentation` (DOI
`10.1109/tgrs.2017.2719738`), chosen from the live database on 2026-09-20: `extracted`, 254
blocks, one bound file, DOI verified by Crossref. The hunt is the CACHED-ANSWER path —
`spend=False`, so no route is chosen and no quota is touched — which exercises resolve, look_up
and report, the path every hunt takes before it decides whether to spend. The standing workstream
`soak` its writes name lives outside every repository, at
`D:\edmonds-pipeline\secrets\litkb-tokens\soak-ws\`; `LITKB_WORKTREE` is pinned to it on every run,
because the search's worktree resolution otherwise shells out to git from whatever directory the
scheduler started in, and a stray `.litkb-workstream` would widen the query to another
workstream's proposals. A baseline that moves is not a baseline.

## LITKB_SCOUT_RUN_&lt;date&gt;.csv (Reports/, GENERATED — the drop-off follow-up ledger)

Written by `qc/instruments/litkb_scout_run.py` from the manifest that
`qc/instruments/litkb_acceptance.py scout --freeze` wrote BEFORE the run. One row per drop-off the
scout left after the freeze, resolved through `hunt(spend=False)`: `hr_id`, `ref`, `ref_scheme`,
`claimed_title`, `claimed_year`, `fields_missing`, `hunt_ok`, `hunt_state_or_refusal`, `message`,
`seconds`.

The CSV is also the RESUME LEDGER — a drop-off whose `hr_id` already has a row is skipped and its
row preserved byte for byte — so the file is idempotent and a run interrupted after seven of
fifteen hunts costs those seven nothing. `fields_missing` is a semicolon list of the eight
required fields (`.claude/skills/literature/SKILL.md`, "Stage 1 — discover") the drop-off left
null or blank. A `hunt_state_or_refusal` outside `litkb_acceptance.CLOSED_STATES` is what the
acceptance counter `unknown_states` refuses; `error` is deliberately OUTSIDE that vocabulary, so a
driver that crashed on every row cannot report a full set of known states.

The driver hunts each drop-off **by `hunt_request_id` alone** (plus the row's `ref_scheme`): given
the id, `hunt` fills `title`/`author`/`year` from the row's `claimed_*` columns itself
(`litkb.hunt.fill_from_request`), so a title row that lacks its author or year is refused
`malformed-ref` naming the blank COLUMN, and the driver never carries a second copy of those facts.

## `litkb.acquisition_attempts` (litkb, migration 0001 widened by 0013 and 0028)

Where the knowledge base answers **where did this file come from**. One row per attempt, success or
failure, written ONLY through the SQL function `litkb.record_acquisition_attempt` presenting the
workstream token — `litkb_writer` holds no direct INSERT on the table (migration 0011) and the
function's EXECUTE is granted to that role alone. The Python door is
`litkb.acquire.run.record_attempt`, which redacts the `detail` on the way in (`run._redacted`,
mutation rows RD14/RD16).

`route` is the closed set `open_access · annas · scihub · browser · hunt-url`. `browser` means a
HUMAN fetched the file and handed it in (`litkb acquire --from-file`, and the `manual-step`
instruction row); `hunt-url` (migration 0028) is the AUTOMATED URL fetch `litkb hunt` makes for a
web source. They are separate values because `qc/instruments/litkb_acceptance.py first-work` reads
a manual route as an `operator_intervention`, and folding the two together would make every hunted
web source read as a human having stepped in. `status` is the vocabulary migration 0013 states.

**THE ACQUISITION-EVENT CONTRACT (S2).** Every BOUND file has an `ok` row whose `detail->>'sha256'`
is that file's sha256 **and whose `work_id` is the work the file is bound to**. The join is the
BYTES rather than a file id because the route path records the attempt before `attach_file` has
returned one; the work is the second half of it because an `ok` attempt for some OTHER work — in
another workstream, in another year — says nothing about how THIS binding got its file. The route path's `detail` carries `sha256`, `md5`,
`bytes`, `binding`, `source_url`, `attach`, `filed`; the `hunt-url` route writes the same five
facts plus `http_status` (`litkb.acquire.events.DETAIL_KEYS`) and no `binding`/`attach`, because
`admit_web` performs the binding and the admission together. `identifier_used` is the work's DOI
(or its arXiv id, where the route takes one) on the route path, and the REDACTED URL on the
`hunt-url` path — `record_attempt` redacts the DETAIL and not that column, so the redaction happens
at the one call site that needs it (mutation row RD19).

A refusal BEFORE admission on the URL path leaves no row, by construction rather than by
exemption: the table's own CHECK is `work_id IS NOT NULL OR candidate_id IS NOT NULL`, and on that
path the candidate is created by the admission. `fetch-failed`, `not-a-pdf` / `truncated-pdf`
(quarantined with a `.reason.json`), `incomplete-record` and `admission-refused` each bind no file,
so the contract — which is about bound files — is not reached.

`bound_without_event(conn, workstream_id, since_utc)` in `litkb.acquire.events` is the verifier
that makes that checkable: every file version the workstream bound after the instant with no `ok`
attempt naming its bytes for its work. Empty is the only passing answer, and what it returns is
what `qc/instruments/litkb_acceptance.py first-work` counts as `operator_interventions`.

The `hunt-url` write is BEST-EFFORT and the verifier is the gate: a write that fails leaves the
file bound (losing an admitted work because its provenance row could not be written would trade a
missing record for a lost one) and reports itself in the hunt result's `refusals` under
`acquisition-event-failed`, with the file then returned by `bound_without_event` until an event
exists for it. A database that has not applied 0028 is exactly that case.

## `hunt_requests.ref_scheme` (litkb, migration 0023 widened by 0027)

The one vocabulary, stated by the CHECK constraint `hunt_requests_ref_scheme_check` and by its
Python twin `litkb.hunt_request.REF_SCHEMES`; the two are held equal by
`qc/test_litkb_hunt_request.py::test_the_sql_check_and_the_python_vocabulary_agree`, which reads
the highest-numbered migration that states the CHECK. Values: `doi arxiv jstor isbn pmid pmcid
openalex s2 handle url tracker legacy_stem title other`. `title` (0027) is a reference carried as
title + author + year with no identifier. A scheme being RECORDABLE is not a promise a hunt can
follow it: `litkb.hunt.HUNTABLE` is `doi arxiv url title`, and everything else is refused
`unsupported-ref-scheme` (S3 owns those routes). The scout's own contract is narrower still —
`ALLOWED_SCHEMES` in `qc/instruments/litkb_acceptance.py` equals `HUNTABLE`, and a drop-off outside
it counts as `ref_scheme_outside_set`.

A hunt that cannot follow a reference ends in one of `litkb.hunt.REF_REFUSALS` — `malformed-ref`
(the string is not a well-formed DOI / arXiv id / URL, or a `title` row lacks author or year),
`unknown-ref-scheme` (a scheme outside `REF_SCHEMES`), `unsupported-ref-scheme` (recordable, not
huntable), `ref-scheme-mismatch` (the caller's scheme disagrees with the request row's),
`unresolved-title` (no registry candidate), `ambiguous-title` (a candidate the confirm gate
refused). Each is a RESULT in the hunt's return dict, never a traceback; since S3 they are the
reason classes of the `refused` state, and the table below is their home.

## `litkb.hunt` terminal states (litkb, S3)

Every `litkb.hunt.hunt()` result carries exactly one `state` from `litkb.hunt.STATES` and exactly
one `reason` from that state's own closed tuple in `litkb.hunt.REASONS`. `ok` is True for the three
ladder rungs and False for the four ways a hunt stops short of one. The legacy `outcome` key is
kept for one session and is DERIVED from the pair (`litkb.hunt.outcome_of`), never typed at a
return site — which is how `held-spend-exhausted`, `already-extracted` and `bound` came to be
outcome words no constant in the module that produced them held.

| state | `ok` | reason classes | meaning | who acts next |
|---|---|---|---|---|
| `extracted` | yes | `fresh` · `already-extracted` · `docling-only` · `grobid-only` | the work is in view, a file is bound and its blocks are searchable | the caller records uses |
| `bound-unextracted` | yes | `fresh-bound` · `already-bound` | a file is bound and no blocks exist for it (only reachable with `extract=False`; the reason says whether this hunt landed the file or the database already held it) | the readability queue, or hunt again without `--no-extract` |
| `held` | yes | `no-spend` · `no-file` · `not-acquired` · `duplicate-held` · `not-in-main` | the work is admitted and no file is bound | `litkb acquire --key <key>`, or `--from-file <PDF>` |
| `refused` | no | `REF_REFUSALS` + `HUNT_REFUSALS` (the sixteen codes above and in `litkb.hunt`) | a terminal refusal: the reference, the record or the claim is wrong, and hunting it again changes nothing | the caller fixes the reference or the claim |
| `api-error` | no | `registry-transient` · `route-raised` · `fetch-transient` · `empty-response` | a registry or a route answered transiently (0/406/408/429/5xx) or raised — NOT a verdict on the reference | retry after a back-off |
| `blocked` | no | `403` · `challenge` · `quota-stop` | a host refused this client, or spending stopped | another route, a browser session and `--from-file`, or Kam |
| `crashed` | no | `<stage>:<ExceptionClass>`, stage ∈ `litkb.hunt.STAGES` | an unexpected exception at a named stage | the operator; then retry |

`crashed` is the one reason that is a SHAPE rather than a membership — the exception class belongs
to the program, not to this vocabulary — and it is VALIDATED (`litkb.hunt.reason_ok`) so that the
reason can never carry the exception's message. The message is one line, in `message`; there is
never a traceback in a hunt result. `STAGES` is `validate resolve admit download bind acquire
extract ingest`; `record` is not among them because both recording call sites catch their own
exceptions by design, so a failure there is a `refusals[]` entry and never a state.

**`absent` IS NOT A HUNT RESULT.** It is `litkb_work`'s miss rung — the MCP ladder's word for "no
such work" — and `hunt()` has never returned it. It was in `STATES` until S3 and left with it.

**PRECEDENCE, when acquisition ends with no file bound.** Most actionable first: any route that
recorded `quota-stop` → `blocked/quota-stop`; else any route `blocked` → `blocked/403` when that
attempt's `http_codes` hold a 403, otherwise `blocked/challenge`; else any route `api-error` →
`api-error/route-raised`; else `held/not-acquired`. A route skipped by `DEAD_STATUSES` is not an
attempt and does not enter the rule. `acquire()` hands the hunt the per-route `route_detail` this
reads (`litkb.acquire.run`); `attempts` keeps its `(route, status)` shape.

**WHERE AN OUTCOME LIVES.** Nowhere in the schema: no table holds a hunt outcome, and S3 adds no
migration. The run-level homes are CSVs — the scout-run ledger above, and the edge-run ledger
below (`LITKB_EDGE_RUN_<date>.csv`, which records the STATE and the REASON as two columns) — and
`litkb.hunt.ledger_word` is the ONE function that
chooses the word either writes: the refusal code where there is one, the reason where the reason is
a closed word, the state where it is not. `CLOSED_STATES` in `qc/instruments/litkb_acceptance.py`
is derived from `STATES` + every enumerable member of `REASONS` (plus `held-no-spend`, which older
ledgers carry), and `qc/test_litkb_acceptance.py` holds the two equal. A DATABASE home for a hunt
outcome is S5's carry-in.

**`litkb_work`'s miss, split three ways (S3).** When `main_*` does not hold the work the tool
answers `state: absent` with `absent_kind` from the closed set in `_ABSENT_KINDS`
(`pipeline/litkb/mcp/server.py`): `never-admitted` (nothing in main, nothing in the caller's own
workstream view — the only kind where fetching is the right move) · `in-this-workstream` (the
caller's own unapproved proposal; `ws_state` is its rung, `ws_files` its bound-file count) ·
`in-another-workstream` (some OTHER workstream holds a `proposed` version of the identifier;
`holder_state` is that workstream's state — `open`, `merged`, `abandoned`; nothing else of it is
readable here). The third bucket reads the same rows admission's check 2 refuses on
(`iv.state = 'proposed'`, blind to the holder's state), so the tool never invites an admission
check 2 would refuse.

**A WEB SOURCE THAT IS A PAGE, NOT A DOCUMENT (S3).** `hunt(ref="https://…", ref_scheme="url")`
whose response is HTML lands a TEXT SNAPSHOT instead of quarantining the bytes, and ends
`extracted` / `fresh` with `in_main: false`. The page's readable text
(`pipeline/litkb/extract/text_snapshot.py`, stdlib `html.parser`, script/style/nav and every
container whose `id`/`class` names it furniture dropped) is written to
`_litkb_staging/web/<key>.txt` through `Store.write_new` — create-only, so a second retrieval
lands `<key>.2.txt` and never overwrites the first — with a `<key>.txt.snapshot.json` beside it
carrying `source_url`, `retrieved`, `content_type`, `sha256_raw` (the bytes the server sent),
`sha256_text` (what the parse made of them), both lengths and the block counts. `admit_web` binds
that `.txt` as `copy_kind = 'web snapshot'` (migration 0020) and the admission is a manual
PROPOSAL: a SECOND session approves it, `promote prepare` holds every chain that quotes it until
then, and `litkb_search` reaches its blocks from THIS workstream and from no other
(`litkb/visibility.py`, decisions.yaml `litkb-web-source-gate`). The blocks are ingested by
`litkb.extract.ingest.ingest_text_snapshot` under a run key of its own — stage `5-text-snapshot`,
tool `litkb-text-snapshot`, version `snapshot-1` — with `page_no = 1`, `bbox` NULL,
`extractor = 'text-snapshot'`, `text_source = 'native'` and `source` NULL, so a page can never be
read as a reconciliation of a PDF. The acquisition event is the route path's, route `hunt-url`,
whose `detail` gains `snapshot: true`, `content_type`, `sha256_raw` and `bytes_raw`; its `sha256`
is the SNAPSHOT's, because that is the file that is bound and the key
`events.bound_without_event` joins on. **The 2026-09-15 guard is unchanged**: the routing decision
is made on the media type the SERVER declared, so a body that declared none — the sign-in-page
shape — still reaches `hunt.land_download` and `_quarantine/` as `refused` / `not-a-pdf`, and a
DOI whose acquisition route serves HTML is a landing page, stays an acquisition `bad-file` and
leaves the hunt at `held`. S3 adds no state and no reason for this path: a page that yields no
claimed title, author and year is `refused` / `incomplete-record`, and one whose text does not
bind the claimed title is `refused` / `admission-refused`.

**The staging reaper (S3).** `litkb reap` (`pipeline/litkb/ops/reaper.py`) walks
`_litkb_staging/{incoming,filed,web}` and gives every file ONE verdict from `owned` (its sha256 is
a `litkb.files` row, OR a `file_versions.rel_path` names its path, OR an admission's checks name
it — `checks->'web'->>'snapshot'` / `->>'document'`, the evidence of a proposal that has no file
row of its own; the first live dry run called the FPGA proposal's snapshot an orphan,
2026-09-21) · `young` (a sibling lock
suffix holds it open, or its mtime is under `--min-age-hours`, default 72) · `orphan` (neither).
Only an `orphan` under `--apply` moves, and it moves to `_quarantine/` with a reason file
(`Store.to_quarantine` + `write_reason`) — the reaper never deletes. **Since S4 it writes ONE
database row per move** (corrected 2026-09-22; until then this paragraph said "never writes the
database", which was true): a `litkb.quarantine_payloads` row, origin `reaper`, reason
`staging-orphan`, through `record_quarantine_system` on the INGEST login, which `litkb reap
--apply` opens for that alone. The row is written after the move; a row that cannot be written is
listed in `errors` (exit 1) and the bytes stay moved. `--dry-run` is the default and writes nothing,
to the disk or the database. Counters, one line: `scanned owned young orphans quarantined recorded
skipped_errors`.

## `litkb.run_retirement_ops` · `litkb.run_retirements` (litkb, migration 0031)

Where the knowledge base answers **which superseded extraction runs a deliberate op has
retired**. Retirement MARKS, it never deletes (S4 run 3 decision D6): the run row and its blocks,
pages and references stay, `files.current_run_id` is untouched, and every reader that already
reads only a file's current run (search, `use.locate_quote`, promotion's `run_is_current`) keeps
its meaning. Both tables grant INSERT to nobody; their ONE writer is the SECURITY DEFINER function
`litkb.retire_extraction_runs(runs uuid[], session text, reason text, keys jsonb)`, EXECUTE to
`litkb_ingest` alone. SELECT to `litkb_reader` and `litkb_ingest`.

| table | column | meaning |
|---|---|---|
| `run_retirement_ops` | `op_id` | one id per `--apply` (uuidv7) |
| | `retired_at` · `retired_by` | when, and the LOGIN (`session_user`, never the definer) |
| | `session_label` · `reason` | who (the `LITKB_SESSION` label) and why; both non-blank |
| | `runs` | how many runs the op retired (>= 1) |
| | `keys` | the stage keys the op was given, so the verdict can be re-read |
| `run_retirements` | `run_id` (PK) · `op_id` | a run is retired at most once, by one op |
| | `file_id` · `stage` | whose run, at which stage |
| | `superseded_by` | the run that superseded it when it was retired (never itself) |
| | `blocks` · `pages` · `reference_rows` | the run's rows at retirement — marked, not moved |

**THE VERDICT, one home: `litkb.run_retirement_status(keys jsonb, runs uuid[])`** (SECURITY
INVOKER, EXECUTE to `litkb_reader`): one row per run with `is_current`, `was_current`,
`evidence_rows`, `superseded_by`, `retired_op` and `refusal`. SUPERSEDED means, for a run that
was EVER current (a `file_current_run` row names it — every `5-reconcile` run the pointer left),
that the file's pointer now names ANOTHER ok run of the SAME stage; for a run that was NEVER
current (stage `6-references`, which never moves the pointer), that the file holds a NEWER ok run
at the stage's CURRENT key, which the caller names in `keys` (the CLI reads it from
`litkb.extract.references_ingest.run_key`). A key naming an OLDER run as current supersedes
nothing. Only ok runs are ever superseded. `refusal` is the closed vocabulary, first match wins:
`current` · `evidence` (a `use_evidence` row cites the run or one of its blocks) ·
`already-retired` · `not-superseded`; NULL means retirable now (`litkb.ops.retire.REFUSALS` is a
read of it, pinned by `qc/test_litkb_retire.py`). `retire_extraction_runs` re-checks the facts
guard by guard before it writes and refuses the whole op on any one run.

**The op: `py -3.12 -m litkb runs retire [--apply --reason R] [--json] [--out PATH]`**
(`litkb.ops.retire`). The dry run is the default and writes nothing; it reads as `litkb_reader`
and lists what an op would retire PER STAGE (runs, files, blocks, pages, references, versions),
what it EXCLUDES by refusal, and names each evidence-held run by work key. `--apply` needs a
session label and `--reason`, sends the whole eligible list in ONE call (one op id) through the
ingest login. REPORTED counters, never gated (orchestrator ruling Q3): `superseded_runs_unretired`
(retirable now; `litkb.ops.retire.superseded_runs_unretired(conn)`; an `--apply` takes it to 0)
and `superseded_runs_held_by_evidence` (superseded but cited by `use_evidence`, so no op may
retire them; `litkb.ops.retire.superseded_runs_held_by_evidence(conn)` -> `{count, works}`, the
works named by key); the dry run also prints `runs_already_retired` and `current_runs`.

**A retired run never becomes current again.** 0031 re-creates `litkb.set_current_run` as 0017's
definition byte for byte plus one guard: a `p_new_run` named in `run_retirements` is refused
(SQLSTATE 22023). Grants and the role matrix are unchanged (CREATE OR REPLACE keeps the ACL).

## `litkb.blocks.provenance.page_text` and reconcile `stage5-4` (litkb, S4 run 3)

`reconcile.PIPELINE_VERSION` moved `stage5-3` -> `stage5-4` (2026-09-22): a FRAGMENT of a
multi-page or multi-column element whose text comes from the TOOL — an OCR page, or a page whose
native slice is empty — now carries its own boxes' share of the element's text, not the whole
element's. What changes: files extracted from now on get a `stage5-4` run key. What does not:
every existing run keeps its key, rows and place, no pointer moves, nothing is re-extracted. A
fragment on the tool path records which text it holds in `provenance.page_text`, closed
vocabulary (`reconcile.PAGE_TEXT`):

| value | the fragment's text is |
|---|---|
| `charspan` | its own Docling `prov` slice, read from `charspan` (`docling.prov_pieces`) |
| `sentence` | the GROBID `<s>` sentences that BEGIN in its line boxes; a sentence over the break stays whole where it begins, and a fragment in which none begins is EMPTY (`grobid.sentence_pieces`) |
| `element` | the element's WHOLE text: the tool's record could not be read back exactly (the stage5-3 behaviour, now labelled) |

Absent on a fragment whose text is the native-layer slice, and on any non-fragment. The run's
`metrics.fragment_page_text` counts the three.

**THE LIMIT of `sentence` (orchestrator ruling Q1).** GROBID fragment text is placed by SENTENCE
START: a sentence that runs from page 27 onto page 28 is stored — and so cited — on page 27, and
page 28's fragment begins with the next sentence. GROBID records no position inside a sentence,
so no finer cut is available from it. An EMPTY `sentence` fragment is KEPT as it is: it keeps the
page span, its box and the fragment chain (`continues_from` / `continues_to`), and holds nothing
to misquote. How many there are, MEASURED on all 229 stored P5 artifact pairs (2026-09-22,
LITKB_FRAGMENT_TEXT_CORPUS_2026-09-22.csv): empty-text fragments 0 under stage5-3, 97 under stage5-4
(every one `sentence`), in 33 files; empty-text blocks of any kind 142 -> 239.

**Merges move with the text.** `_merge_regions` merges two readings of a region only when their
text is the same (`_text_same`), so a fragment whose text changed can merge where it did not, or stop
merging where it did. On the 229 files: blocks 82,166 -> 82,181 in 13 files, `merged_regions`
21,000 -> 20,985, and in every one of the 13 the block change is exactly minus the merge change
(`dropped_overmerges` unchanged); 22 boxes exist only under stage5-4 (15 of them empty-text
fragments that no longer merge into a reading with words) and 7 only under stage5-3.

## LITKB_FRAGMENT_TEXT_&lt;date&gt;.csv (Reports/, GENERATED — the stage5-4 before/after)

Written by `qc/instruments/litkb_fragment_text.py --compare`, from two runs of the same
instrument over the SAME stored artifacts, once on main's `pipeline/` (`before`, `stage5-3`) and
once on the branch's (`after`, `stage5-4`). Population, read from live current runs as
`litkb_reader`: `why=identical` (fragment blocks > 40 characters whose text is identical on two or
more pages of one run — survey-code C3's set) and `why=tool-cross-page` (every cross-page fragment
whose text came from the tool). One row per DB block: `work_key`, `group`, `page`, `source`,
`db_text_source`, `db_len` (the stored block), `tei_on_disk` (False: a hunt-path file whose TEI
was never written, re-run Docling-only, so its rows are `unmatched`), then per side `*_match`
(`matched` / `unmatched` / `ambiguous`, by page and box within 0.01 pt), `*_len`, `*_page_text`,
`*_group_identical` (all members matched and one text), `*_blocks_in_file`, and
`before_reproduces_db` (the re-run's length equals the stored block's).

## LITKB_FRAGMENT_TEXT_CORPUS_&lt;date&gt;.csv (Reports/, GENERATED — stage5-4 corpus-wide)

Written by `qc/instruments/litkb_fragment_text.py --compare-corpus` from two `--corpus` runs over
EVERY stored P5 artifact pair (TEI + Docling JSON + the PDF the census names), on main's `pipeline/`
(before) and the branch's (after). One row per file plus a `TOTAL` row: `name`, `error`,
`before_blocks` / `after_blocks`, `before_merged` / `after_merged` (reconcile's `merged_regions`),
`*_dropped_overmerges`, `*_empty_text_blocks` (a text-bearing kind — not table or figure — whose
text is empty), `*_empty_text_fragments` (those that are fragments), `after_empty_sentence_fragments`,
`new_boxes` / `gone_boxes` (page + box, to 0.01 pt, present on one side only), `new_boxes_empty`,
`after_page_text` (the run's `fragment_page_text` counts), and on the TOTAL row
`files_blocks_changed`.

## LITKB_EDGE_RUN_&lt;date&gt;.csv (Reports/, GENERATED — the edge-case register's ledger)

Written by `qc/instruments/litkb_edge_run.py` from the manifest that
`qc/instruments/litkb_acceptance.py edges --freeze` wrote BEFORE the run, and graded by
`litkb_acceptance.py edges --manifest`. One row per row of the register
(`qc/fixtures/litkb_hunt_edge_cases.json`), resolved through `litkb.hunt.hunt`. Columns, in order:
`row_id`, `class`, `mode`, `ref`, `ref_scheme`, `expected_state`, `expected_reason`,
`observed_state`, `observed_reason`, `ok`, `refusal_codes`, `work_id`, `admission_id`, `file_id`,
`run_id`, `attempt_statuses`, `route_detail`, `new_admissions`, `report`, `seconds`, `traceback`,
`started_at`, `message`. The `_replay.csv` beside it is the same shape, written by `--replay`.

**STATE AND REASON ARE TWO COLUMNS, and that is the difference from the scout ledger above.** The
scout CSV records one closed word (`litkb.hunt.ledger_word`), which is all a drop-off follow-up
needs. The four states S3 added are only legible as a PAIR: `api-error/registry-transient` and
`api-error/route-raised` are one word in a one-column ledger and two different next moves for the
operator. `route_detail` carries what `acquire()` returns per route (`route`, `status`, `codes`,
`exception`) so a `blocked/403` row can be told from a `blocked/challenge` row after the fact —
the codes are what the precedence rule read. `report` is a small JSON object (`in_main`,
`admission_state`, `blocks`) holding the facts `state` deliberately does NOT carry, because a web
source's proposal-ness lives in `in_main` plus the admission's outcome rather than in the rung
(see the hunt's terminal states above). `mode` is the mode this row RAN in, and `traceback=1` is a
raise out of `hunt()` — the thing the whole vocabulary exists to make impossible, recorded as a
row rather than as a dead run.

**The register is an ADJUDICATED table, not a list of tests.** Every row names a real carrier from
the corpus, cites where it came from, and states from code and from the attempts history why its
`(state, reason)` is the right one. A row whose expected state needs a human carries
`held_for_ruling` with the question and the evidence instead of an expectation, and is NOT a
manifest row. **A ruled row keeps the ruling in the row** (`ruling`: `ruled_by`, `date`, the
`question` and `evidence_at_ruling` it answered, the `ruling` text, and `measured` — the live
pair the ruling produced, with its ledger): from 2026-09-21 E20/E21/E22 carry a ruling AND an
expectation (their pairs were MEASURED by a first live hunt, never derived), E25 carries a ruling
and `live.mode = "not-a-hunt"` (a binding-gate question no reference form reproduces), and
E23/E24 carry a ruling AND stay `held_for_ruling` because the ruling's residue is a new question
(the rows the title-resolution run left unresolved). A row the hunt vocabulary does not cover at all — a scout-side tool fault — carries
`live.mode = "not-a-hunt"` and is excluded from `executed`. A row whose replay cannot hold a
precondition only the live corpus has carries `replay.expected`, which overrides for the replay
alone; both expectations are in the register and both are graded.

`edges` prints one line — `executed skipped state_or_reason_mismatches tracebacks held_for_ruling
waits_on_migration` — and exits 0 only when `executed` equals the manifest's own non-held,
non-waiting row count and the other three are zero. A MISMATCH is an observed pair differing from
the expected one, an `asserts` entry failing, or an observed state outside
`litkb_acceptance.CLOSED_STATES`; **membership alone cannot pass**, which is what separates this
counter from the scout's `unknown_states`. The manifest freezes the register's sha256 and the
grader refuses a register that changed since — the register is what the run is graded against, so
a register edited afterwards grades a different question. **`fixture_sha256` is a hash of the
register's CONTENT — its bytes with every CRLF folded to LF (`litkb_acceptance._register_sha256`)
— not of the bytes on disk.** The register is `* text=auto`, so one commit is CRLF on a Windows
checkout and LF on Linux; a byte hash refused S3's own frozen manifest on a fresh checkout
(2026-09-21) with nothing edited. Every manifest frozen before the change hashed LF bytes and stays
valid. The HTML fixtures are the opposite case — recorded bytes, `binary` in `.gitattributes`,
hashed as bytes. `fixture_committed` (from the same date; absent in S3's manifest) is `git diff
--quiet HEAD` on the register at freeze: `false` means the register was frozen from the working
tree ahead of its commit, so `repo_head` is not the commit that holds it — S3's manifest names
`568988b` for a register committed as `06c42f6`.

`waits-on-migration` is MEASURED at freeze (`db_migration_tip` against a row's own
`needs_migration`), never written into the register: 0028 was unapplied when S3 opened and applied
the same night, and a hard-coded wait would still be waiting. `--replay` re-runs every non-held
row on `LITKB_TEST_DB` — reset and migrated under the suite's advisory lock, with every route,
registry, fetch and extractor replaced at the seams `qc/test_litkb_hunt.py` uses — so a waiting row
is proven there while the live run waits. It refuses the database name `litkb`.

## litkb Codex report JSON (`qc/fixtures/litkb_codex_report.schema.json`, GENERATED per review)

The Codex review stage's output, and the one thing the stage's gate reads. Written by
`qc/instruments/litkb_codex_review.py` (which launches Codex with that file as
`--output-schema`), graded by `qc/instruments/litkb_acceptance.py codex`. JSON Schema
2020-12, `additionalProperties: false` at every level.

Top level: `review_sha256`, `context_sha256` (64 lower-case hex each), `citations` (array),
`editorial` (array), and the optional `session_id` / `session_id_key`. A `citations` row is
`{n, block_id, quote_head, verdict, reason}`; an `editorial` row is `{where, finding}`. `verdict`
is one of `SUPPORTED`, `OVERREACH`, `UNSUPPORTED` — the same three strings as
`litkb_acceptance.CODEX_VERDICTS`, held equal by
`qc/test_litkb_codex_stage.py::test_the_schema_is_the_file_the_wrapper_and_the_gate_both_name`.

**`n` counts OCCURRENCES, not blocks.** It is the 1-based index of the citation in document
order, as `litkb.review_check.citations` enumerates them — the proving run's review carried 13
citations over 6 distinct blocks, and a report keyed by block would leave 7 sentences ungraded
while looking complete. The distinct-block collapse belongs to the CONTEXT file
(`py -3.12 -m litkb review-context`), which prints each block once, and to nothing else.

**The two digests are STAMPED, never trusted.** The wrapper overwrites whatever the model wrote
with sha256 of the RAW BYTES of the two files it actually read, and the gate recomputes the same
two and counts `hash_mismatch`. Raw bytes, not canonicalised text: this checkout carries CRLF
where the repository stores LF (`.gitattributes`, deliberately), and the question these digests
answer is "is this the report for THIS file on THIS machine", not "is this the same document as
in the repository". Do not canonicalise them into agreement with a cross-platform pin.

`session_id` is the Codex session, stamped from the `--json` event stream so a follow-up can
resume the same worker; `session_id_key` records WHICH key it was read from, because `codex exec
--help` (codex-cli 0.155.1) documents `--json` only as "Print events to stdout as JSONL" and says
nothing about the event shape. A hardcoded key that stopped matching would stamp `session_id:
null`, which reads exactly like a run that had no session.

Validation is `litkb_codex_review.validate`, a stdlib validator covering exactly the keywords this
schema uses and REFUSING any keyword it does not implement — `jsonschema` is installed on this
machine but is in neither requirements file, and the same-commit rule forbids a runtime dependency
that a bootstrap does not install. `qc/test_litkb_codex_stage.py` cross-checks the two on every
accept and reject case and skips where `jsonschema` is absent.

## litkb stage-6 coverage counters (`litkb.extract.references_coverage`, S4 run 3)

`reference_counters(conn, file_ids=None)` returns the S4 block's two REPORTED counters and their
companions; `format_counters` prints them on one line, every ratio as `num/den(pct)`. Read-only (a
`litkb_reader` connection is enough). The closed set of names:

| name | numerator / denominator |
|---|---|
| `files_without_reference_stage` | files whose current run is an ok `5-reconcile` run with blocks and NO ok `6-references` run at the current run key / all such files |
| `reference_anchor_rate` | references with `resolved_work_id` whose resolved DOI is a held work's ACTIVE DOI / references whose resolved DOI is a held work's ACTIVE DOI (R4's real denominator) |
| `references_anchored` | references with `resolved_work_id` / all references |
| `anchored_with_citation_edge` | anchored references that carry a `citation_edges` row / anchored references |
| `citation_edges` | count of edges on the counted runs |
| `anchored_outside_held_doi` | anchored references whose DOI is no longer a held active DOI (0 unless an identifier was retired after the ingest) |
| `text_snapshot_files_with_blocks` | files whose current run is `5-text-snapshot` — out of stage 6's reach (no PDF), reported, never counted as owing |

"The current run key" is `references_ingest.run_key` (stage, tool, tool_version, params_hash,
pipeline_version); a `failed` run, or an ok run under another params hash or version, is NOT the
stage having run. The reference population is the references of ok stage-6 runs at that key. The
held-DOI set is `references_ingest.doi_index`. The driver's selector `pending_files` reads the SAME
predicate (`_OWES_STAGE6`), so the driver takes exactly the files the first counter counts.

## litkb stage-6 driver progress JSONL (`<LITKB_DERIVED>/p6/driver_progress.jsonl`, APPEND-ONLY, untracked)

Written by `qc/instruments/litkb_references_stage.py`, one line per file as it finishes, so a
detached run is followed by reading the file. Keys: `at` (UTC ISO), `rel_path` (the file's
`main_files.rel_path`), `file_id`, `sha256`, `status`, `tei` (`cached` = the TEI came from
`p6/tei/<sha256>.tei.xml` with a matching `.sha256` sidecar; `grobid` = posted now, with
`includeRawCitations=1`), `seconds`, `references`, `resolved`, `anchored`, `citation_edges`,
`error`. `status` is closed: `ok` (a stage-6 run was committed), `already` (the ingest found an ok
run at the key — a race with another writer), `error` (`error` names the refusal: `file-missing`,
`sha-mismatch` — the bytes at the rel_path no longer hash to the file row, so nothing is posted —
`grobid: …`, or the exception), `aborted` (GROBID could not be started; the batch stops). The LAST
line of a batch is `{"summary": {...}}`: `selected`, `files` (per-status tallies plus summed
`references`/`resolved`/`anchored`/`citation_edges`), `seconds`, `aborted`,
`grobid_started_here`, `grobid_stopped`, `stages_tripped` (a tripped Semantic Scholar/arXiv stage
makes the resolution rate Crossref-only), `network_calls`, `counters` (the table above). Beside it,
`p6/files/<sha256>/` holds each file's four stage-6 artifacts under the names
`references_ingest.ARTIFACTS` reads.

## litkb_preprint_stamp.csv (phase4/qc/, GENERATED — the bioRxiv stamp strip, measured)

Written by `qc/instruments/litkb_preprint_stamp.py`: one row per (page, `pdftotext` program) of
every held file whose active DOI starts `10.1101/` (one on 2026-09-22). Columns: `rel_path`,
`pdftotext` (the program path — every distinct `pdftotext` on PATH is run, because a bare call
resolves to different programs under different launchers), `pdftotext_version`, `page`,
`stamp_present` (the INDEPENDENT detector: the page's pypdfium2 text contains `biorxiv`/`medrxiv`
AND the file's own DOI), `detector_word`, `detector_doi`, `regex_hit` (`binding._PREPRINT_STAMP`
matched at the start of a line of the page as the binder reads it), `regex_hit_lines`,
`chars_stripped` (what `binding.title_text` removed), `regex_search_anywhere`, `lines_on_page`,
`first_line_printed`, `first_line_scored` (each cut at 160 characters), and on page 1 only
`p1_best_ratio_scored` / `p1_best_ratio_printed` (the best 1-3 line title window against the
work's title, on the stripped vs the printed lines). The ratio is pages with `regex_hit` / pages
with `stamp_present`, per program.

## litkb_web_title_region.csv (phase4/qc/, GENERATED — TITLE_REGION_LINES on web snapshots)

Written by `qc/instruments/litkb_web_title_region.py`: one row per `*.txt` under
`_litkb_staging/web/` plus every `file_versions` row with `copy_kind = 'web snapshot'`. Columns:
`rel_path`; `kind` (closed: `html-snapshot` — the `text_snapshot` sidecar sits beside it;
`page1-text` — no sidecar, a PDF's page-1 text; `missing-on-disk`); `bytes`; `sha256_12`;
`title_source` (closed: `binding.registry_title`, `printed-doi`, `file-stem`, `works.key`,
`none`); `title`; `n_lines` (`binding.page_lines`); `first_index` (the smallest window start at
which a 1-3 line window, scored the binder's way, reaches `BIND_RATIO`); `first_window_lines`;
`first_ratio`; `within_region` (`first_index < TITLE_REGION_LINES`); `refusal_at_first`
(`binding.window_refusal` of that window, empty when admissible); `best_index`; `best_ratio`;
`binding_line` / `binding_ratio` (what a stored binding recorded, for the cross-check);
`title_region_lines` (the constant's value when measured).

## `litkb.quarantine_payloads` (litkb, migration 0030 — S4, the database-visible quarantine state)

One row per REFUSED PAYLOAD, keyed by its path relative to the literature root (UNIQUE). Until S4
`_quarantine/` was a directory only: the reason lived in a filename no code read back, and the
reaper and `hunt.land_download` left no row at all. A path under `_quarantine/` is where the refused
bytes were moved; any other path is a file REFUSED WHERE IT LIES — a bound file the readability
classifier refuses, or an admission file whose page count could not be read — and there the row
IS the state (the bytes are never moved). `file_versions` is not touched: its `work_id` is NOT NULL
and most refused bytes have no admitted work (S4 run 3 decision D5).

Columns: `id`, `rel_path` (UNIQUE), `sha256` of the refused bytes, `bytes`, `reason`, `origin`,
`work_id` / `file_id` / `attempt_id` / `workstream_id` (nullable links), `detail` (jsonb, run
through `textnorm.jsonb_safe`, mutation row S4Q1), `recorded_at`, and `cleared_at` / `cleared_by` /
`cleared_reason` (all three set or none).

**Clearing.** Only a `classifier` row on a BOUND file (a path outside `_quarantine/`, with a
`file_id`) can be cleared (CHECK `quarantine_payloads_cleared_only_in_place`). When `litkb
readability --record` classes that file `extracted`, it clears its own row through
`litkb.clear_quarantine_system(id, session, reason)` (SECURITY DEFINER, EXECUTE to `litkb_ingest`,
once only). A moved-payload row — acquisition guard, bind refusal, hunt-url, reaper, backfill — is
NEVER cleared: those bytes stay refused. A cleared row the classifier refuses again is RE-OPENED by
the same idempotent write (its cleared columns go back to NULL). `litkb_work` lists only uncleared
rows; the read-only classifier REPORTS `stale_quarantine_rows` (uncleared classifier rows on files
it now classes `extracted`, plus uncleared rows at a file's path whose sha256 is NOT the file's).
**A row classes a file only when its sha256 is the file's `files.sha256`**: a row about other bytes
at the same path (corrupt bytes refused in place, then a good copy bound there) never does
(auditor-B F2). `quarantined_without_db_state` is unaffected: it counts payloads under
`_quarantine/` only. Two CHECKs besides the
vocabularies: a row outside `_quarantine/` must be the classifier's with a `file_id`, or an
admission's `probe-error` (`quarantine_payloads_in_place_rule`); a system origin has no
workstream and a writer origin always one (`quarantine_payloads_workstream_rule`).

**`reason`** (closed; one home `litkb.quarantine.REASONS`, held equal to the CHECK by
`qc/test_litkb_quarantine.py`): the shapes `not-a-pdf · truncated-pdf`; the route statuses a route
returns WITH bytes `blocked · bad-file · not-in-archive · partner-404 · hash-mismatch`; the binding
and attach outcomes `binding-failed · binding-pending · duplicate-held`; the legacy
`annas.fetch_one` labels `duplicate-hash · content-mismatch`; the reaper's `staging-orphan`; the S4
refusals `probe-error · zero-content`; `legacy` for a pre-litkb name with no label.

**`origin`** (closed; `litkb.quarantine.ORIGINS`): `acquisition-guard` (`acquire.run`'s shape and
route-refusal quarantines, `--from-file`), `bind-refusal` (`land_and_attach`'s binding verdict,
attach refusal and page probe; an admission's probe refusal in place), `hunt-url`
(`hunt.land_download` and the URL path's probe refusal), `reaper`, `classifier`, `legacy-backfill`.
The legacy `acquire.annas.fetch_one` writes no row: it holds no database connection and no
workstream; what it quarantines is picked up by the backfill and, until then, counted.

**Writers.** `litkb.record_quarantine(ws, token, …)` — SECURITY DEFINER, presents the workstream
token, EXECUTE to `litkb_writer` only, takes the three workstream origins and links only an attempt
of the SAME workstream. `litkb.record_quarantine_system(…)` — SECURITY DEFINER, no token, EXECUTE to
`litkb_ingest` only, takes `reaper · classifier · legacy-backfill`. Both are IDEMPOTENT ON THE PATH
(the same path and sha256 returns the existing id; the same path with other bytes is refused,
SQLSTATE 23505). No role holds a direct write; SELECT to `litkb_reader`, `litkb_writer`,
`litkb_ingest`.

**Every quarantine write leaves a row, best-effort.** The row is written AFTER the move, inside a
savepoint (`quarantine.try_record`), and a failure is returned, never raised — the bytes are kept
either way. `acquire()` returns them in `quarantine_rows`; hunt adds a `quarantine-state-failed`
entry to `refusals[]` (its state and reason are unchanged); the reaper lists them in `errors`.
THE COUNTER IS THE GATE: `quarantine.quarantined_without_db_state(conn, root=…)` counts every
payload under `_quarantine/` — every file except `.reason.json` sidecars and the `.txt` companion of
a payload stem — with no row for its path. Its known-bad is `quarantine.fire_quarantine` (a
CONSTRUCTED payload planted in a temp root with no row moves it by one).

**Backfill.** `py -3.12 -m litkb quarantine backfill [--apply]` gives every payload already on disk
a row, origin `legacy-backfill`: reason from the `.reason.json` sidecar (`label`, else a reaper
sidecar → `staging-orphan`, else its `shape`), else the name's `<stem>__<label>__<token>` label,
else `legacy`. `attempt_id` is the attempt whose `detail->>'quarantined'` is the path, else the ONE
attempt whose `detail->>'sha256'` matches (several → none, candidates listed in `detail`);
`file_id` is the `files` row with the same sha256. One sha under several names is one row PER
PATH. The dry run (default) reads on the reader login and writes nothing; `--apply` writes on the
ingest login. A label outside `REASONS` is counted `unmapped` and NOT written.

## litkb readability classes (`pipeline/litkb/readability.py`, S4 — decision D8)

The ONE home of the closed classes. **File classes**: `extracted` with a reason `full ·
docling-only · grobid-only · ocr · snapshot`, and the residue classes `scan-needs-ocr ·
over-page-cap · zero-content · bad-file · probe-error · book · refused-registry`. **Work classes**:
`no-file-any-route`, and `mixed` for a work whose files disagree (a work with an extracted file and
a residue file is `mixed`, never `extracted`). `not-attempted` is REPORTED for a file-less work some
applicable route never ran for, outside the gated universe. A file with no class is UNCLASSIFIED —
never defaulted; `queued` / `leased` are not classes.

The universe, the evidence and the rule order are the module docstring's (one home; not restated
here). In one line each: `bad-file` = not on disk, sha256 ≠ `files.sha256`, or no `%PDF-` magic;
`probe-error` = `probe.probe_pages` / `page_text_chars` raised; `book` = work `type = 'book'`;
`over-page-cap` = pages > `probe.EXTRACT_PAGE_CAP` (Kam ruling litkb-extract-page-cap);
`zero-content` = a text-layer file whose current run's canonical blocks carry no text;
`scan-needs-ocr` = image pages (`probe.image_page_numbers`, decision D13: zero native characters
AND at least one raster image) that no text block and no OCR'd run covers, or image pages and no
run; `refused-registry` = unbound bytes in `_litkb_staging/` that only a
REFUSED admission's checks name; `extracted` reasons from the run: stage `5-text-snapshot` →
`snapshot`, metrics `ocr: true` or text on a zero-native-character page → `ocr`, else
`docling_regions` / `grobid_regions` → `full` / `docling-only` / `grobid-only`.

**The queue step** (`readability.with_queue`, S4 run 3 builder-C item 1c). For a file with NO current
run, the verdict above is read against its `litkb.extraction_jobs` (at its most recently enqueued run
key; `dead` read first, then waiting, refused, done): a queued / leased / staged job → UNCLASSIFIED
(waiting); a `refused` job → its refusal, only when the evidence names the SAME class, else
UNCLASSIFIED with both named (a stale refusal is never picked over the file's present); a `dead` job →
`zero-content` when it died as `queue.ZeroContent`, else UNCLASSIFIED (an extractor error is a finding,
never a class). Without migration 0029 the step reads nothing and `queue_table` = 0 says so.
**A file with a dead page range** (orchestrator ruling Q2, S4 run 3): `dead` is final for that JOB,
and the FILE takes the dead range's class — `zero-content` if it produced no block, else UNCLASSIFIED
with flag `dead-error`. Its other ranges stay `staged` and never assemble (`stage_chunk` assembles only
when every sibling is staged), so such a file holds no ok run; `dead` is read before `waiting` for
exactly that reason (test `test_a_file_with_one_dead_range_takes_the_dead_ranges_class_…`, mutation S4C4).

Counters (`readability.counters`): `unclassified_acquired_files` (file and staging rows with no
class — the gated one) and the REPORTED `queue_table` (1 = the queue was read), `files_queue_waiting`,
`files_queue_dead-error`, `files_queue_disagreement` (the files the queue step left unclassified, by
why), `stale_quarantine_rows`, `acquired_files`, `files_<class>`, `extracted_<reason>`,
`works`, `works_<class>`, `works_not-attempted`, `works_extracted`, `works_residue`,
`works_unclassified`. Known-bads: `readability.fire_unclassified` (one rule dropped by name → a real
file goes unclassified and the counter moves) and `readability.fire_probe` (a CONSTRUCTED
unopenable PDF through `land_and_attach` on a worker database: refused and never bound; with the
probe guard mutated off it binds with `pages` NULL).

`litkb_work` (MCP) adds, beside its unchanged keys and four-state ladder: `files[].file_id`,
`files[].readability` `{class, reason, evidence}`, `readability` (the work's rollup) and
`quarantine` (every UNCLEARED `quarantine_payloads` row naming the work or one of its files; `null`
on a database without migration 0030). `py -3.12 -m litkb readability [--workstream ID]
[--all-workstreams] [--record]` writes the CSV below; `--record` (ingest login) records a
`classifier` row for each bound file classed `bad-file`, `zero-content` or `probe-error`.

## LITKB_READABILITY_&lt;date&gt;.csv (Reports/, GENERATED — the classifier's scored bed)

Written create-only (never overwritten) by `py -3.12 -m litkb readability` from
`readability.classify`. One row per acquired file (`row_kind = file`), per refused-admission
staging payload (`staging`) and per main work (`work`). Columns, in order: `row_kind`, `key`,
`work_id`, `file_id`, `rel_path`, `pages` (the probe's count, empty when it could not be read or the
file is not a PDF), `image_pages` (how many image pages, decision D13), `class`
(empty = UNCLASSIFIED), `reason` (the `extracted` reason; for a work, the reasons its files share),
`evidence` (the rule's sentence), `quarantine_ids` (space-separated ids of the UNCLEARED
`quarantine_payloads` rows naming the file),
`current_run_id`, `blocks` (canonical blocks with text in the current run), `text_chars`, `scope`
(`main`, or the workstream id a file was read from).

## `litkb.extraction_jobs` + `litkb.extraction_job_leases` (litkb, migration 0029)

The extraction queue of design §12.3-12.5 (LITKB_WORKPLAN.md "### S4"). One `extraction_jobs` row
per (file, run key, page range); UNIQUE `NULLS NOT DISTINCT` on (file_id, stage, tool,
tool_version, params_hash, pipeline_version, page_start, page_end), so a repeated sweep inserts
nothing. `page_start`/`page_end` NULL = the whole file. The run key is stage 5's
(`litkb.extract.ingest.run_key` with `CORPUS_PARAMS`) — the same key `litkb hunt` and the P5 bulk
pass write, so an `ok` run either wrote marks the job `done` without running anything. `stage` is
CHECKed to `5-reconcile` (S4 run 3 decision D7: stage 6 is not queued). No role holds a direct
write on either table: the only writers are nine SECURITY DEFINER functions, EXECUTE to
`litkb_ingest` alone and presenting no workstream token (files are main-owned):
`enqueue_extraction`, `claim_jobs`, `renew_lease`, `record_artifact`, `stage_chunk`, `finish_job`,
`fail_job`, `refuse_job(job, token, refusal, error, stage)`, `reopen_job` (pinned by
`qc/test_litkb_p1.py`'s role matrix). SELECT for
`litkb_reader`, `litkb_writer`, `litkb_ingest`. Driver: `pipeline/litkb/extract/queue.py`,
`py -3.12 -m litkb queue sweep|work|status`; tests `qc/test_litkb_queue.py`.

**`state`** (closed, `queue.STATES`): `queued` (claimable) · `leased` (a worker holds a live or
expired lease) · `staged` (a page-range job whose artifact is recorded, waiting for the LAST range
of its file to assemble all of them into ONE run) · `done` (`run_id` and `blocks_digest` set) ·
`dead` (failed `litkb._job_max_attempts()` = 3 times, Kam's ruling litkb-extract-page-cap; the
ceiling's one home is that SQL function) · `refused` (a guard's verdict; terminal, never claimed).
`queued`, `leased` and `staged` are waiting states, not readability classes (S4 run 3 decision D8).

**`refusal`** (closed, `queue.REFUSALS`; set iff `state = 'refused'`): `book` (the work's type is
`book`, litkb-book-policy — decided in Python AND in SQL at enqueue and at claim) · `bad-file` (not
on disk, no `%PDF-` in the first 1,024 bytes, or sha256 on disk ≠ `files.sha256`) · `probe-error`
(`litkb.extract.probe.probe_pages` / `page_text_chars` raised) · `over-page-cap` (more than
`probe.EXTRACT_PAGE_CAP` = 400 pages, litkb-extract-page-cap) · `scan-needs-ocr` (an OCR-routed file
with OCR off, or the scan post-condition below). The same guard (`queue.guard_file`) runs at
ENQUEUE and again at CLAIM. **`refusal_stage`** (set iff `refusal` is): `enqueue` (the sweep's
guard) · `claim` (the claim-time re-check, the SQL book guard at claim) · `result` (the scan
post-condition — OCR ran and read nothing).

**Reopening a refusal** (auditor-A F1, S4 run 3 round 2). A refusal is terminal for the WORKER, not
for ever. A sweep re-guards a file whose EVERY job at the key is `refused` at `enqueue` or `claim`;
when `queue.guard_file` now passes, each refused job whose range the file still needs goes back to
`queued` through `litkb.reopen_job(job, refusal, actor, why, route, pages, page_chars, image_pages)`
— a compare-and-set on the refusal, refreshing the probe facts — and a range with no job at all (a
whole-file refusal made with OCR off, the file now OCR-routed into ranges) is enqueued. A refusal
the guard still gives is left alone — that rule lives in the SWEEP (it re-runs `guard_file`), not in
the database: a direct `reopen_job` call can reopen e.g. an over-page-cap job, and the claim-time
re-check then refuses it again. The database itself refuses (22023) to reopen a `result` refusal and a
`book` refusal while the work is a book. `attempts` is RESET to 0 (a new life; the prior count is the
audit row's `prior_attempts`). Every reopen appends one
row to **`litkb.extraction_job_reopens`** (append-only: trigger refuses UPDATE/DELETE; no agent role
may INSERT; SELECT for reader, writer, ingest): `id`, `job_id`, `reopened_at`, `actor` (the
caller's worker id, `sweep@<host>:<pid>` by default), `db_login` (`session_user`), `why`, `refusal`,
`refusal_stage`, `refused_error` (the `last_error` the refusal carried), `prior_attempts`.

**`--redo`** (`litkb queue sweep --file <id> --redo`): the named files whose CURRENT run sits at an
OLDER key than today's stage-5 run key are swept like files with no run (every guard applies); a file
whose current run is at today's key is never re-extracted. The new run becomes current by
`set_current_run`'s compare-and-set; the old run stays.

**Routing** (`route`: `native` · `ocr`). A file is OCR-routed when ANY page is an IMAGE page: zero
native characters AND at least one raster image (S4 run 3 decision D13, `probe.image_pages`; its
docstring holds the measured basis). The probe facts are stored on the job: `page_chars` (normalised
native characters per page) and `image_pages` (their 1-based numbers). Never the page-1
`file_versions.has_text_layer`. An OCR-routed file is split
into ranges of at most `queue.OCR_CHUNK_PAGES` = 22 pages (S4 run 3 decision D3); a native file is
one whole-file job. Docling emits ABSOLUTE page numbers for a page range (measured 2026-09-22), so
assembly shifts no page; `queue.assemble` refuses ranges that do not tile 1..`pages` or that name a
page outside themselves.

**Scan post-condition.** An OCR-routed file whose image pages ALL come back with no text
(`queue.ocr_read_nothing`) is refused `scan-needs-ocr`, never finished `ok` — WHEN IT IS A SCAN:
its image pages outnumber its native-text pages (`queue.is_scan`; native-text page = more than zero
native characters in the job's `page_chars`; a blank page counts on neither side). A definition, not
a tuned number (the orchestrator's ruling on builder-A Q1, S4 run 3). A file that is NOT a scan — a
native paper whose one image page is a caption-less picture — finishes: its textless image pages are
REPORTED in the run's metrics (`textless_image_pages`), never a refusal of the whole file. An image
page has no native text, so every character on it is OCR's.

**A dead job leaves a `failed` run** (design §12.3; builder-A Q2). At `dead` — `fail_job` at the
ceiling, or `claim_jobs` finding every lease expired — `litkb._job_dead_run` (0029, granted to no
role) writes a `failed` `extraction_runs` row at the job's OWN run key through 0017's
`open_extraction_run` / `finish_extraction_run`, never current, with metrics `queue`, `job_state`
(`dead`), `last_error` and `dead_jobs` (one entry per dead range: `job_id`, `page_start`, `page_end`,
`attempts`, `last_error`, `died_at`). An `ok` run already at the key is left alone. A later successful
ingest at that key reuses the run id and turns it `ok`, so the failure record stands exactly until the
file is extracted. An extraction that produced NO block fails as `queue.ZeroContent`, whose
`last_error` begins `ZeroContent:` (`queue.ZERO_CONTENT_ERROR`) — the evidence the readability
classifier reads for `zero-content`; any other death is an extractor error it leaves unclassified.

**The lease.** `claim_jobs(worker, n, lease_seconds, files uuid[] DEFAULT NULL)` takes queued jobs
or jobs whose lease has EXPIRED, one row at a time under `FOR UPDATE SKIP LOCKED`, shortest file
first; each claim increments `attempts` and `lease_seq`, and returns a TOKEN in plaintext once —
only its sha256 is stored, in `extraction_job_lease_tokens` (job_id, seq, token_hash; written once,
never changed), on which NO agent role holds any privilege (the rule `qc/test_litkb_p1.py` pins for
every relation with a `token_hash` column). A job whose lease expired at every one of the
ceiling's attempts is `dead` at the next claim. Every holder call presents the token; a token that
is not the job's CURRENT lease, or whose lease a later claim superseded, is refused with
**SQLSTATE `LKL01`** ("litkb lease refused"; `queue.LEASE_REFUSED`, raised in Python as
`queue.LeaseLost`). `finish_job` is the ownership gate: the worker calls it INSIDE the ingest
transaction (`extract.ingest.ingest_file(before_commit=…)`), so a refused finish rolls the blocks
back. `queue.LEASE_SECONDS` = 375 (the longest single-job wall-clock in the existing metrics
JSONL); the heartbeat renews at half of it. `metrics` (jsonb) holds the JOB's own measurements.

**`extraction_job_leases`** — append-only history, one row per claim: `job_id`, `seq`, `owner`,
`lease_seconds`, `claimed_at`, `expires_at` (moved by `renew_lease` while the lease is
live), `superseded_at` (set when a later claim took an expired lease), `released_at` + `outcome`
(`finished` · `staged` · `failed` · `dead` · `refused`, set by the holder's own call). A trigger
refuses DELETE and every rewrite (identity columns never change; `superseded_at`, `released_at`,
`outcome` are written once). A claim a worker never came back from reads `superseded_at` set,
`released_at` NULL.

**`blocks_digest`** (sha256 hex; `queue.blocks_digest` is its one implementation). Over every block
of the run: the tuples `(page_no, reading_order, type, text)` sorted by (page_no, reading_order),
each serialised as `json.dumps([page_no, reading_order, type, text or ""], ensure_ascii=False,
separators=(",", ":"))`, joined by `\n`, UTF-8 encoded. Computed inside the ingest transaction from
the rows just written, and again by a cold session from the database (`queue.run_rows`) or from
the stored artifacts (`queue.reference_blocks`, which re-runs `extract.ingest.prepare` on the CPU).

**Artifacts** go to `<references.DERIVED_ROOT>/<sha256>/5-reconcile/<tool>@<version>_<params_hash>/`
as `<range>.s<lease_seq>.{docling.json,tei.xml,manifest.json}` (`<range>` is `whole` or
`pNNN-NNN`), each written `.partial` + fsync + rename. `artifact_path` / `artifact_sha256` name the
MANIFEST, which lists every tool output with its sha256; a reclaimed job whose manifest and files
still hash as recorded is not extracted again.

**`extraction_runs.metrics` keys the queue adds** (beside the reconciler's own): `seconds`
(extraction + reconcile wall-clock), `pages`, `pages_per_s`, `peak_rss_bytes` (Docling's sampled
peak), `peak_vram_mib` and `vram_baseline_mib` (whole-card `nvidia-smi` at 1 Hz; NULL off CUDA),
`device`, `interpreter`, `ocr` (a JSON boolean on EVERY run the worker finishes — the key builder B's
classifier reads for `extracted/ocr`), `ocr_engine`, `image_pages` (count),
`ocr_chars_on_image_pages`, `textless_image_pages` (the image pages that came back with no text, in
page order; `[]` when none — REPORTED for a file that is not a scan), `grobid_error`,
`reconcile_seconds`, `jobs` (one entry
per job: `job_id`, `page_start`, `page_end`, `attempts`, …), `attempts` (their sum), `chunks` (the
page ranges; `[]` for a whole-file job), `queue`.

**The S4 counters** (`queue.counters`, each a plain function of a connection; a reader login
suffices): `stale_leases` (jobs `leased` with `lease_expires_at` past) · `mutated_leases_accepted`
(done jobs whose `finished` lease row was superseded or followed by a later claim; the
superseded clause alone sees a job that died at the attempt ceiling and was then finished by its
stale holder — load-bearing, with its own known-bad; auditor-C re-check) ·
`duplicate_blocks` (in the current runs the queue finished: blocks beyond the first at one
(page_no, reading_order); plus, for runs a RESUMED job — attempts > 1 — finished, blocks per
(page_no, text) beyond the count the clean reference recomputed from the artifacts produces; a
bare (page_no, text) repeat is not counted because correct current runs repeat a string on a page
16,295 times live) · `resumed_content_hash_mismatches` (runs a resumed job finished whose committed
digest differs from the database's blocks or from the reference; an unrecomputable reference
counts) · `books_extracted` (files of a `type='book'` work with any block — a book in main OR in
any workstream `queue.counters(conn, root, workstreams)` is given: the manifest's, auditor-C N5) ·
`over_cap_bound`
(files over `EXTRACT_PAGE_CAP` by `file_versions.pages` or `extraction_jobs.pages` with any block) ·
`scans_ocr_unrouted` (OCR-routed files that are SCANS by `queue.is_scan` — the post-condition's own
definition — whose current run carries no text on any image page). Known-bads that move each
one: `pipeline/litkb/extract/queue_fire.py`; `qc/instruments/litkb_acceptance.py readability --fire`
re-fires them by name (section below).

## LITKB readability acceptance manifest (`qc/instruments/litkb_acceptance.py readability`, S4)

The plan's "### S4" (b) as a command. `readability --freeze --workstream <slug> [--workstream …]
--out <manifest.json>` writes a JSON manifest BEFORE the drain; `readability --manifest
<manifest.json>` grades it; `readability --fire <name>` re-runs one (c) known-bad. Tests and the
known-bad table: `qc/test_litkb_acceptance.py` (the `test_readability_*` rows); mutation rows S4R1-S4R14
in `qc/instruments/litkb_p2_mutations.py`.

**Manifest fields** (kind `litkb-readability`): `frozen_at` (the DATABASE's `now()`, read in the
same REPEATABLE READ snapshot as the bed; `frozen_at_source` = `db`) · `repo`, `repo_head`,
`code_committed` (`git status --porcelain` over the litkb package and the instrument is empty: true;
dirty: false; git cannot say: null) · `db`, `db_name`, `db_oid` (`pg_database.oid`: a DROP + CREATE
under the same name changes it) · `reader_role` · `repo_migration_tip`, `db_migration_tip` (the
OWNER read, `litkb_owner` through `connect_admin`; `--passfile` sets PGPASSFILE for it, and without it
libpq's own default resolution applies — the code names no owner passfile of its own, the `edges`
freeze included (`db.connect`: the admin passwords stay in the shared pgpass file); null with
`db_migration_tip_note` when unreadable),
`required_migration` (31) · `workstreams` (`[{slug, id}]`, `main` first with id null — main is always
graded) · `literature_root`, `quarantine_root` · `derived_root` (`queue.derived_root()`, the job
artifact root) and `references_derived_root` · `extract_page_cap`, `ocr_chunk_pages`, `lease_seconds`
(the code's constants at freeze) · `gated` (the nine names) · `bed` (every active current file in main
and the named workstreams holding no block — `file_id`, `rel_path`, `sha256`, `scope`, `pages` and
`image_pages` MEASURED by the page probe, `probe_error`) · `manifest_sha256` (sha256 of the sorted,
compact JSON of every other field).

**Grading refuses** (exit non-zero, nothing graded): a `manifest_sha256` that does not match the
content; a constant the code no longer has; another database (name or oid); a workstream id that
does not name its slug. The counters always use the code's constants, never the manifest's.

**The one printed line** — GATED, in the plan's order, each read by the function that owns it:
`unclassified_acquired_files` (`readability.classify(reader, workstreams, root=literature_root)` →
file and staging rows with no class, the queue step included) · `stale_leases`, `duplicate_blocks`,
`resumed_content_hash_mismatches`, `books_extracted`, `over_cap_bound`, `scans_ocr_unrouted`,
`mutated_leases_accepted` (`queue.counters(reader, literature_root, manifest workstreams)`, definitions in the
`litkb.extraction_jobs` section above) · `quarantined_without_db_state`
(`quarantine.quarantined_without_db_state(reader, root=literature_root)`: payloads under `_quarantine/`
with no row for their path). Then REPORTED: `files_without_reference_stage` and
`reference_anchor_rate` (each numerator/denominator, `references_coverage.reference_counters`) ·
`acquired_files`, `stale_quarantine_rows`, `queue_table`, `files_queue_waiting`,
`files_queue_dead-error`, `files_queue_disagreement`, `files_<class>`, `extracted_<reason>`,
`works…` (`readability.counters`) · `superseded_runs_unretired`, `superseded_runs_held_by_evidence`
(`ops.retire`) · `bed_files`, `bed_without_blocks` (bed files that still hold no block) ·
`waits_on_migration` (1 when any of `litkb.extraction_jobs` (0029), `litkb.quarantine_payloads` (0030),
`litkb.run_retirements` (0031) is absent to the reader — the db tip below 31, measured without the owner
credential; the counters those relations carry then print `unread`). Exit 0 only when every gated
counter is 0 and `waits_on_migration` is 0.

**`--fire <name>`** runs only when `LITKB_TEST_DB` is set EXPLICITLY to a worker database
`litkb_test_w<N>` (unset, or the shared `litkb_test`, is refused — round 2, auditor-C DB SAFETY) that is
NOT one of the RESERVED workers (read from LITKB_WORKPLAN.md's per-session protocol line by
`litkb_acceptance.reserved_worker_dbs`, today w2, w8, w10, w11), and
`readability_fire` itself REFUSES `litkb` (and any name outside `litkb_test*`) before a connection opens. It owns that database: the suite's advisory lock, reset, migrate — so the
control reads 0 by construction, and all seven names can be fired back to back in one worker database
(ruling Q3). The fixtures are also salted per call (`queue_fire._salt`), so the fires run back to back
WITHOUT a reset too (`test_readability_every_fire_runs_back_to_back_in_one_worker_db_without_a_reset`). It prints the guard-ON control line and the known-bad line and exits 0
only on FIRED — the counter's move AND the control arm's own plan clause (round 2, auditor-C
N1/N2): cap refused `over-page-cap`, never claimed, 0 blocks; scan refused `scan-needs-ocr`, no ok run;
book refused `book` AND classed `book` by the classifier; lease refused by the ownership gate (LKL01),
nothing landed; probe never bound, its quarantine row's reason `probe-error`, and
`unclassified_acquired_files` unchanged across the fire. Names: `kill` (a `litkb queue work` subprocess tree killed mid-batch on the synthetic
extractor and rerun: FIRED when the killed worker left exactly one stale lease, the rerun exits 0, a job
was resumed, every file's content digest equals an uninterrupted run's and every counter is back at its
baseline — 0 duplicates) · `lease` (`mutated_leases_accepted` 0 → 1) · `cap` (`over_cap_bound` 0 → 1) ·
`probe` (control: refused `probe-error`, 0 bound; known-bad: bound 1 with pages NULL) · `scan`
(`scans_ocr_unrouted` 0 → 1; needs Anderson 1957 and its recorded no-OCR artifact on the machine) ·
`book` (`books_extracted` 0 → 1) · `quarantine` (`quarantined_without_db_state` 0 → 1). `--manifest`
beside `--fire` is checked (content hash and constants) and named in the output; it grades nothing.

<!-- S4.5 builder A (hardening subcommand + cassette/replay layer): its SCHEMAS rows go between this marker and the next; the orchestrator removes the markers at landing -->

## LITKB hardening manifest (`qc/instruments/litkb_acceptance.py hardening`, S4.5)

The plan's "### S4.5" (b) as a command over counters SIX builders own. `hardening --freeze --workstream
<slug> --out <manifest.json> [--date YYYY-MM-DD]` writes the manifest BEFORE the run; `hardening
--manifest <m>` grades it; `hardening --fire <name|all> --db litkb_test_w<N>` re-runs module fires on a
worker database; `hardening --replay --manifest <m> --db litkb_test_w<N>` writes the replay summary.
Tests: `qc/test_litkb_hardening.py`; mutation rows S45A1-S45A47 in `qc/instruments/litkb_p2_mutations.py`.

**NOTHING IN THE COMMAND COMPUTES A COUNTER.** Each counter is a function in a counter module
`qc/instruments/litkb_hardening_<builder>.py`, loaded BY PATH (qc/instruments is not a package). A
module defines `COUNTERS` and `REPORTED` (`{name: fn(conn, manifest) -> int}`), `FIRES` (`{name:
{"counter": <counter>, "run": fn(conn, arm, workdir) -> int, optional "bound"}}`, `arm` = `control` |
`known_bad`) and optionally `DETAILS` (`{name: fn(conn, manifest) -> [line]}`, printed on stderr beside
a non-zero counter). Two modules defining one counter or one fire name are refused (a counter has ONE
home); a module that fails to import is named and its counters read `unread`.

**Manifest fields** (kind `litkb-hardening`): `frozen_at` (the DATABASE's `now()`, the run rows read in
the same REPEATABLE READ snapshot; `frozen_at_source` = `db`) · `repo`, `repo_head`, `code_committed` ·
`db`, `db_name`, `db_oid`, `reader_role` · `repo_migration_tip`, `db_migration_tip`(+`_note`) ·
`workstream_slug`, `workstream_id`, `run_workstream_ids` (list; one today) · `worktree` (where the
workstream token is) · `literature_root` (the store root the counters read: builder C1b's
`quarantines_without_reason`, `stubs_bound`, `volumes_bound_as_article`; added by integrator-w1) · `ladder_budget`
(`{seconds, attempts}` of `litkb.acquire.policy.LadderBudget()` at freeze — `attempts` null, derived per ladder; the
threshold builder C1a's `budget_exceeded_silently` grades against, held OUTSIDE the ladder: Codex X2; added by
integrator-w2) · `probe_csvs` (`{basename: repo-relative path}` for every
`phase4/qc/litkb_acq_probe_*` file on disk — brief-CONTRACTS' shape) and `probe_csvs_sha256` (`{basename:
content sha256}`, CRLF folded) · `register` and `ruled_hunts` (`{path, sha256}`, content hashes of the
edge register and Reports/LITKB_RULED_HUNTS_2026-09-21.csv) · `report_path` (promised,
Reports/LITKB_LADDER1_<date>.md) · `referee_reports` (`{class: promised path}`,
Reports/LITKB_REFEREE_S45_<CLASS>_<date>.md for each of the nine classes of decision D13; the date is
`--date`, default the freeze instant's local date) · `cassette_index` (`{path, sha256 (bytes; null
before the run records it), bodies, inline_max_bytes}`) · `constructed_register` (`{path, sha256}`,
content hash of qc/fixtures/litkb_hardening_constructed_register.json — the CONSTRUCTED rows `--replay`
replays beside the register; `--constructed` names another) · `run_csv`, `recording_report` (the run
driver's report on the finished recording, below), `replay_csv`, `replay_report`
(promised, under `_derived/hardening/`) · `gated` (`[{name, bound}]`, the code's `HARDENING_GATED`) ·
`reported` (the plan's reported names + `operator_binds_historical`, decision D8) · `selectors`
(`{name: rows it chose}`) · `rows` (below) · `unhuntable` (works a selector chose that hold neither a DOI
nor an arXiv id, with `reason`) · `manifest_sha256`.

**The run rows** (`rows`, S4.5 decision D9): `id` (`L001`…, assigned after sorting by the first
selector that chose the row, then the reference), `ref`, `ref_scheme`, `mode` (`hunt` — the work holds
no active file, or no main work holds the reference; `measure` — the work already holds one: every rung
is asked, nothing lands twice), `source` (EVERY selector that chose it, in selector order), `why` (each
selector's reason, `;`-joined), `work_id`, `key`. Deduplicated BY WORK; a resolved work is hunted by its
own stored identifier (DOI, else arXiv). The selectors, in order: `register` (register rows E13 E21 E06
E20) · `pending-recording` (every register row carrying `replay.routes.pending_recording` whose live mode
is `execute` — E03 E07 E13 E20 today: each must be RECORDED to come off the synthetic acquirer; E16 is
replay-only) · `ruled` (ruled-run tracker rows 187, 194 — every leg) · `ruled-registry-transient` (ruled-run rows
that ended `api-error/registry-transient`) · `post-freeze-probe` (10.1016/j.rse.2024.114101, named by
the plan) · `free-pdf` (head probe `verdict` FREE-PDF) · `wayback` (head probe `status` 404: an advertised
URL gone dead) · `bronze-landing` (no-oa-copy probe `unpaywall_url` on doi.org) · `no-oa-copy` (every
row of the no-oa-copy probe) · `bad-file`, `blocked` (every work with an attempt in that status) · `bban`
(every row of the bban probe) · `preprint-archive-miss` (works with an `annas/not-in-archive` attempt
whose `main_works.type` is `preprint` or whose crosswalk `cr_type` is `posted-content`) · `crosswalk`
(crosswalk probe works with no active file and an `s2_arxiv`, `cr_isbn` or `cr_relation_types`).

**Grading refuses** (exit non-zero, nothing graded): a manifest of another kind; a `manifest_sha256`
that does not match its content; a `gated` list that is not the code's `HARDENING_GATED`; another
database (name or oid). The grading connection is `litkb_reader` in READ ONLY session mode.

**The freeze's one admin read.** Every freeze read is on `--role` (default `litkb_reader`) EXCEPT the DB
migration tip: `litkb_meta.schema_migrations` is readable by `litkb_owner` alone, so `db_migration_tip`
opens the owner login (readability's freeze does the same). `--no-admin-read` skips it: the tip is
recorded null, `db_migration_tip_note` says why. **Paths in the manifest** (`probe_csvs`, `register`,
`constructed_register`, `report_path`, `referee_reports`, `cassette_index`, `run_csv`, `recording_report`,
`replay_csv`, `replay_report`) are RELATIVE TO `repo` unless absolute: a counter module joins them to
`manifest["repo"]` (`litkb_hardening_a._resolve`), never to its own working directory.

**The one printed line**: every GATED counter in the plan's (b) order, then the REPORTED ones, then any
reported counter a module adds. A value is an integer or `unread` (no module defines it, its module
failed to load, or its function raised — the reason goes to stderr). Exit 0 only when every gated
counter is read and inside its bound: `=0` for all but `relation_probe_rows>=1` and
`promotions_prepared>=1`. The loaded and failed modules are named on stderr. The gated list is the plan's
(b) plus `replay_rows_disagreeing=0`, builder A's addition (below).

**`--fire`** refuses `litkb`, the shared `litkb_test*` names, a RESERVED worker (the per-session protocol
line of LITKB_WORKPLAN.md) and a `--db` that is not `LITKB_TEST_DB`; takes the suite's advisory lock;
per fire: reset + migrate, `control` arm, reset + migrate, `known_bad` arm, reset + migrate; prints one
line per arm (`fire=<name> (<module>) arm=<arm> <counter>=<value> (bound <bound>)`) and a verdict line:
`FIRED` (the control inside the bound AND the known-bad outside it), `DID-NOT-FIRE`, or
`DID-NOT-FIRE (error)` (an arm raised; never FIRED). Exit 0 only when every requested fire FIRED.

## LITKB_LADDER1_&lt;date&gt;_run.csv (`_derived/hardening/`, GENERATED — the ladder-1 run's ledger)

Written by `qc/instruments/litkb_ladder_run.py` from a frozen hardening manifest (refused if edited),
one row per manifest row, rewritten whole after every row, resumable (a row already in it is not run
again unless `--redo` names it). Columns, in order: `row_id`, `ref`, `ref_scheme`, `mode`, `source`
(`;`-joined selectors), `state`, `reason` (the hunt's pair for `hunt` rows; `measured`/<outcome> or
`skipped`/`measure-hook-absent` or `skipped`/`work-not-in-main` for `measure` rows), `attempts_written`
(the workstream's `acquisition_attempts` count after the row minus before, on the reader login),
`wall_seconds`, `traceback` (`1` = the hunt or the measure raised; the exception is in `message`),
`started_at`, `message`. RECORD mode is on for the whole run (the cassette below); each row's requests
are tagged with its `ref`.

**The measure hook** (`litkb.acquire.run.measure`, built on the merged candidate by integrator-w1 as
`acquire(..., mode="measure")`): `measure(conn, ws, token, work, *, store, agent, session)` → `{"outcome":
"measured", "attempts": [(route, status)], "route_detail": [...]}` — asks EVERY rung for a work that may
already hold a file (a route's earlier `DEAD_STATUSES` miss does not skip it, nor the held-file
short-circuit; `blocked` earlier in the run and the back-off window still do — they protect a host, and
`rehunt_route_spends` grades them), records every answer as an attempt row judged by the acceptance test,
and lands, binds and quarantines NOTHING. Were it absent, a `measure` row would be
`skipped`/`measure-hook-absent`.

## litkb cassette index (`qc/fixtures/litkb_cassettes/<name>/index.jsonl`; `pipeline/litkb/cassette.py`)

Recorded HTTP for the hermetic replay (S4.5 item 7), at litkb's one socket path `netutil.Client._raw_get`.
Activated by environment (so an MCP hunt's child process inherits it): `LITKB_CASSETTE` = `off` |
`record` | `replay`; `LITKB_CASSETTE_INDEX` (REQUIRED in record/replay); `LITKB_CASSETTE_BODIES` (the body
store; default `cassette_bodies/` under `litkb.extract.references.DERIVED_ROOT`, i.e. `LITKB_DERIVED`);
`LITKB_CASSETTE_ROW` (a child's row tag). Marked `binary` in the repo-root .gitattributes; its identity
is the sha256 of its BYTES.

**Format**: JSON Lines. Line 1, the header: `kind` (`litkb-cassette`), `version` (1),
`inline_max_bytes` (65536), `key_headers`, `scrub_params`, `created_at`, and `constructed` (text) on a
CONSTRUCTED index. Every other line is one interaction: `row` (the lower-cased reference the request was
made for), `take` (the recording session; a row's LATEST take is the only one replayed — a re-recorded
row supersedes its old entries whole), `seq` (0-based: the n-th request for this key in this row),
`key` (`method` GET|POST, `url`, `follow`, `accept`, `range`, `referer`, `body_sha256` — the empty
string for a GET), `key_sha256` (sha256 of the key's sorted compact JSON), `recorded_at`, `response`
(`status`, `headers` without `Set-Cookie`, `cookies_set` — the NAMES of the cookies this response set,
never a value — and `body`: `sha256` and `length` of the bytes stored, `served_sha256` of the bytes the
host sent, `scrubbed` (a registered secret was masked out of them), then `inline_b64` (base64) or
`stored: true`). **Scrubbing**: every URL and header value passes `netutil.redact` and a query-parameter
mask (`key`, `email`, `mailto`, `api_key`, `apikey`, `token`, `access_token`, `secret`, `password` → the
value becomes `<KEY>`; the mask is IDEMPOTENT — a value that is already `<KEY>` stays `<KEY>`, so a link the
ladder reads out of a replayed, masked body, or a masked `Location` it follows, keys to the URL the
recording was keyed on); a request body is hashed after the registered secrets are masked; a response body
has every registered secret replaced by `<KEY>`; a body the index INLINES (below) also passes the
query-parameter mask, so a 404 page that echoes its request URL carries no `mailto=`/`email=`/`key=`
value into the tracked file. **Bodies**: inline up to 64 KiB; above it, and EVERY PDF whatever its size
(`%PDF-` anywhere in the first 1 KiB — a byte-order-marked PDF is a PDF), in the store at
`<bodies>/<sha[:2]>/<sha>.bin`. **Recording never fails a request**: a recording that cannot be written
(the store unwritable, the index unwritable) is kept in the cassette's `record_errors` (`<Exception>:
<text>`) and the live answer still goes back to the ladder. **Replay**: the n-th request for
a key in a row gets the n-th recording; one more request than recorded, a request never recorded, a
stored body missing or no longer hashing to its name — each is a named `CassetteMiss` (kept in the
cassette's `misses`), never a fall-through to the network.

**Staleness diff** (`Cassette.stale()`): `unplayed` (every live entry OF A ROW THE REPLAY BEGAN OR ASKED
FOR that no replay requested: `row`, `seq`, `url`) and `misses` (every request the index could not answer:
`row`, `url`, `why`). Scoped to the replayed rows because the live pass records every manifest row into
one index and a replay grades a subset: `Cassette.rows_not_replayed()` lists the other rows (`row`,
`entries`), which are never stale. A row the replay BEGAN (`Cassette.begin_row` in replay mode) is in the
scope even when it asks nothing, so a replayed row that skipped every route leaves all its entries stale.

**The socket guard** (`litkb.cassette.SocketGuard`): patches `socket.socket.connect`/`connect_ex`,
`socket.getaddrinfo` and `socket.gethostbyname`/`gethostbyname_ex`; each connect to a host outside
`allow_hosts` and each lookup of a non-loopback name is recorded in `attempts` (`host`, `port`, `how`,
`allowed`, `refused`) and then refused with `NetworkBlocked` (an OSError). `allow_hosts` = `loopback`
(qc/conftest.py's autouse `_no_network`, which FAILS any test with a non-allowed attempt; `litkb_live`
tests are excepted under LITKB_LIVE=1) or a tuple — `()` in every replay. With `loopback`, `allow_ports`
makes the allowlist HOST AND PORT (Codex finding X3): a loopback connect is allowed only to a listed port
or to a port this process bound on a loopback or wildcard address (`litkb.cassette.watch_loopback_binds`,
a process-lifetime recorder of `socket.socket.bind`; `None` = every loopback port). `_no_network` lists
PostgreSQL's port (`litkb.db.connect.PORT`, 5433) and a loopback GROBID's (`litkb.extract.grobid.DEFAULT_URL`,
8070), each read from its one home (an unreadable home adds nothing: the guard is then stricter), and
installs the bind recorder at configure time, so a test's own server and asyncio's self-pipe socketpair are
known. A test that needs a port nothing listens on binds one and does not listen. libpq's PostgreSQL socket
is opened in C and never seen. `_no_network` also runs every test with `HTTP_PROXY`, `HTTPS_PROXY`,
`ALL_PROXY`, `FTP_PROXY` (either case) and `FLARESOLVERR_URL` unset and `NO_PROXY=*` (a proxy or solver on
a loopback port would carry a request off the machine through an allowed connect; `NO_PROXY=*` also stops
urllib reading a Windows registry proxy), and FAILS CLOSED — every test errors, named — when the litkb
package imports but `litkb.cassette` does not (a worktree run without `PYTHONPATH=pipeline`).

## LITKB_LADDER1_&lt;date&gt;_recording.json (`_derived/hardening/`, GENERATED — the recording report)

Written by `qc/instruments/litkb_ladder_run.py` (`write_recording_report`) at the end of every RECORD pass
(a resumed pass rewrites it), at the manifest's `recording_report`. Fields: `kind`
(`litkb-hardening-recording`), `manifest_sha256`, `index` + `index_sha256` (the recorded index's BYTES
as the pass left them), `entries` (live interactions), `rows` (the row tags recorded), `rows_run_this_pass`,
`record_errors` (recordings that could not be written), `finished_at`, `recording_sha256` (self-hash of the
rest, `litkb_hardening_a.summary_sha`). The replay counters refuse an index that is not this one, and every
reader (`litkb_hardening_a.load_recording`) refuses a report whose `recording_sha256` does not match its
content (edited after the run driver wrote it).
`--no-extract` passes `extract=False` to every hunt of the pass (default: the hunt's own, extract on).

## LITKB_LADDER1_&lt;date&gt;_replay.json (`_derived/hardening/`, GENERATED — the replay summary)

Written by `hardening --replay` (`litkb_hardening_a.build_replay_summary`): the manifest's register AND
its CONSTRUCTED register (`constructed_register`: rows C403, CTRUNC, CHTML — plan item 7's "a cassette's
403 edited to 200, a truncated body, an HTML body") replayed on a worker database, every `ladder` row
through the REAL `litkb.acquire.run.acquire` against the recorded index (or its own CONSTRUCTED cassette),
inside a socket guard that allows nothing, graded by the `edges` grader. Fields: `kind`
(`litkb-hardening-replay`), `db`, `register` + `register_sha256` (content), `constructed_register` +
`constructed_register_sha256` (content), `cassette_index` + `index_sha256` (bytes; null when the index
is not on disk), `replay_csv`, `rows` (per row: `row_id`, `acquirer`, `network_calls`,
`cassette_misses`, `expected_state`/`_reason`, `observed_state`/`_reason`, `traceback`, `message`),
`edges` (the grader's counters over the replay CSV) and `edges_offences`, `network_calls` (the guard's
non-allowed attempts) and `network_attempts`, `stale` (the staleness diff over EVERY cassette a row
replayed from — the run's index and each row's own — each entry naming its `index`), `rows_not_replayed`
(the run index's rows the replay never began), `row_cassette_misses` (the CSV's per-row misses summed,
the cross-check), `summary_sha256` (self-hash of the rest). **The replay counters refuse (read `unread`)
a summary whose register, CONSTRUCTED register or index is not the one on disk now, a summary edited
after the replay wrote it, and — when the manifest names a `recording_report` and the index exists — an
index the recording report does not name (or no recording report at all, or one edited after the run
driver wrote it).**

**The edge CSV gains three columns** (after `message`; LITKB_EDGE_RUN_<date>.csv and its `_replay.csv`):
`acquirer` — what the row's replay actually INSTALLED, read off the acquirer function's tag, never off
the register: `none` · `stub` (the synthetic `_acquirer_stub` return) · `ladder` (the real ladder
against a cassette) · `real-oa-raises` · `network_calls` (the replay guard's non-allowed attempts during
the row; empty outside a guarded replay) · `cassette_misses` (the row's cassette misses; a miss makes the
row `traceback=1`, message `CassetteMiss: …`). **The register gains** `replay.routes.kind` = `ladder`
(`cassette`: a fixture index path under qc/fixtures or absolute, else the run's recorded index; `routes`:
the routes the live pass reached; `mirrors`: the Sci-Hub mirrors it was recorded against),
`replay.registry` `record` fields `title`/`author`/`year` (the real record's, for a ladder row that binds
a recorded PDF), and `replay.routes.pending_recording` (`why`, `until`) on every row still on the
synthetic acquirer (E03 E07 E13 E16 E20; E16's says no live recording can exist).

## Builder A's hardening counters (`qc/instruments/litkb_hardening_a.py`)

GATED: `unvalidated_items` — of the nine rung classes of decision D13 (`REFEREE_CLASSES`: substrate,
vocabulary, stage-a, stage-b, stage-c, scihub-1, stage-e, replay, badfile-read), those whose referee
report the manifest does not name, or names but is not on disk, or holds no line matching
`^fired: \S+=\S+ on .+` · `stage_b_rungs_unmeasured` — of the Stage B routes (`litkb.acquire.policy.STAGE_OF`
value `B` over `ROUTES_ALL`: builder C1a's one home, never a list in the counter module), a rung the ladder's
registry HOLDS (`litkb.acquire.run.RUNGS`) with no YIELD LINE, and a route no rung registers with no
NOT-BUILT LINE, in the manifest's `report_path` (`stage_b_rungs`; the registry-read rule is
brief-CONTRACTS.md's 2026-09-23 amendment, applied by integrator-w1 — a rung module `litkb.acquire.run`
does not import is UNBUILT to the counter and owes a not-built line: fail closed) · `replay_rows_graded_against_stubs` — replay summary rows
whose `acquirer` is `stub` · `replay_network_calls` — the summary's `network_calls` · `cassettes_stale` —
the summary's unplayed entries (of the rows the replay replayed) + misses (the larger of every cassette's
misses and the CSV's per-row misses); UNREAD when the summary names a recorded index that is not on disk
(no recording was replayed, so 0 would be vacuous) ·
`replay_rows_disagreeing` (builder A's addition to the plan's (b): the gate its (c) row "a cassette's 403
edited to 200 → the replay disagrees with the register → RED" needs) — the replay's
`state_or_reason_mismatches` + `tracebacks` + `skipped`. REPORTED: `replay_rows_pending_recording`
(register rows carrying `pending_recording`) · `cassette_interactions` (live entries in the recorded
index) · `cassette_rows_not_replayed` (row tags the live pass recorded and the replay never began: the
other half of the index, reported, never gated; UNREAD, like `cassettes_stale`, when the recorded index is
not on disk) · `cassette_record_errors` (the recording report's `record_errors`: recordings the live pass
could not write — a register row's lost recording is also a replay miss, a run row's is visible only here;
UNREAD when there is no recording report or it was edited).

**The yield-line grammar** (the LITKB_LADDER1 report): one line per REGISTERED Stage B rung, matching
`^yield: <route>=<converted>/<asked>[ \t]*$` exactly — `<route>` a route word (`[a-z0-9_-]`: `open_access`
is one), `<converted>` and
`<asked>` non-negative integers, `converted <= asked` (a line with more converted than asked is not a
measurement and does not count). `yield: core=0/35` is a MEASURED zero and counts as measured. A route
is converted when its rung LANDED bytes for the row, read from the attempt rows (decision D1: never from
the work's file state). **The not-built grammar**: one line per Stage B route no rung registers,
`^not-built: <route> <reason>$` — the reason is required (a bare `not-built: core` states nothing); a
not-built line for a REGISTERED rung, or a yield line for an unregistered route, answers neither question.

**Fires** (`FIRES`, each also a test in `qc/test_litkb_hardening.py`): `referee_report_dropped`
(`unvalidated_items` 0 → 1) · `yield_line_deleted` (`stage_b_rungs_unmeasured` 0 → 1: the CONSTRUCTED
report measures every Stage B route the registry names; the known-bad deletes the first registered rung's
yield line) ·
`cassette_403_edited_to_200` (`replay_rows_disagreeing` 0 → 1) · `socket_opened_during_replay`
(`replay_network_calls` 0 → 1) · `synthetic_acquirer_reinstated` (`replay_rows_graded_against_stubs`
0 → 1). The last three replay the CONSTRUCTED register qc/fixtures/litkb_hardening_constructed_register.json
through the real ladder, each row against its own CONSTRUCTED cassette under qc/fixtures/litkb_cassettes/
(`constructed_scihub_403`, `constructed_scihub_truncated` — its PDF body stored in a tracked `bodies/`
folder beside the index, `constructed_scihub_html`); the known-bads mutate row C403.

**A yield line that asked no row** (`yield: <route>=<converted>/0`) is not a measurement and does not
count: the plan asks every Stage B rung of every `no-oa-copy` row, so `=0/0` says the rung was asked of
nobody (`litkb_hardening_a.yields`). `=0/35` is a measured zero.

<!-- S4.5 builder B1 (identifier model, migration 0032): its SCHEMAS rows go between this marker and the next; the orchestrator removes the markers at landing -->

## `litkb.scheme_registry` (litkb, migration 0032 — S4.5 builder B1, the identifier model)

One row per identifier SCHEME. It replaces 0001's closed `identifiers.scheme` CHECK: `identifiers.scheme` is now a
foreign key to it (`identifiers_scheme_registered`), so a new scheme is a row, not a constraint rewrite. Written only
by migrations; SELECT to `litkb_reader`, `litkb_writer`, `litkb_promoter`. Its Python twin is
`litkb.identifiers.SCHEMES` (`pipeline/litkb/identifiers.py`), held equal to the table by
`qc/test_litkb_s45_identity.py`. Every value below is a RELAYED design (the linkage survey, round 3, §3),
UNVALIDATED until the "substrate" referee scores it.

Columns: `scheme` (PK, `^[a-z][a-z0-9_]*$`), `label`, `url_template` (holds `{value}`, or NULL), `regex` (the
normalised value's shape, or NULL — data for `identifiers.valid`, not enforced on insert), `normaliser` (which
branch of `litkb.norm_identifier` applies: `doi arxiv isbn pmcid pmid issn pii lower upper upper_last_segment
handle oclc lccn hal trim`), **`distinct_values`** (a value names at most ONE work), `identity_strong` (check 2:
a candidate holding a confirmed value of this scheme that no work holds is a DIFFERENT record, never a title
duplicate — 0014's list `doi arxiv isbn pmid pmcid jstor` less `handle`, which the plan makes non-distinct and so
cannot show that two records are different works; CHECK `scheme_registry_strong_is_identity`: a strong scheme is
distinct or type-scoped; check 2 counts it strong only where it is the CANDIDATE's identity — distinct, or its
`identity_types` include the candidate's type, so an ISBN on a report or a chapter is not strong for it and the
title review still runs), `registry_confirmed`
(check 1 confirms it against a registry record — 0020's `doi arxiv isbn`, unchanged), `identity_types` (a match is
identity only between two works of these types: `isbn` -> `{book}`, the plan's "type-scoped ISBN-13"; a scheme
with identity types is never distinct, CHECK `scheme_registry_type_scope_not_distinct`), `tier` (0 = in 0001's
CHECK, 1 = a rung cannot fire without it, 2 = cheap, arrives unasked), `why` (the source of the distinct decision).

**The schemes and the distinct split, as landed.** Tier 0: `doi` `arxiv` `jstor` `pmid` `pmcid` `openalex` `s2`
`url` `tracker` `legacy_stem` distinct; `isbn` `handle` NOT distinct (`handle` not strong either). Tier 1: `pii` `core` `bibcode` `ocaid`
distinct; `md5` `oai` NOT distinct. Tier 2: `wikidata` `mag` `dblp` `hal` distinct; `issn` `oclc` `lccn` `olid`
`htid` `gbooks` `sha1` `sha256` `zlib` `lgrsnf` `lgrsfic` `lgli` `nexusstc` NOT distinct. The plan fixed `doi arxiv
pmid pmcid openalex s2 mag bibcode` true and `isbn issn oai handle md5` false; every other row's `why` says what
decided it (a book-level key, a file digest, a shadow-library FILE record: not distinct; one record per publication:
distinct; `url`/`tracker`/`legacy_stem`/`jstor` keep 0001's behaviour).

**The unique index is per-scheme DATA.** `identifiers_active_scheme_value` is `UNIQUE (scheme, value_norm) WHERE
active AND scheme IN (<the distinct schemes>)` — a partial predicate cannot read a table, so the list is generated
from the registry and the migration refuses to finish unless the predicate and the registry agree. A book's ISBN on
its chapters is data, not a violation. Counter `nondistinct_schemes_in_unique_index` re-reads the predicate from the
catalog on every grade.

**`litkb.norm_identifier(scheme, value)`** gains a branch per normaliser (0014's DOI and arXiv branches unchanged):
`isbn` drops an `ISBN`/`ISBN-10:`/`ISBN-13:` label and every character but 0-9 and X, and stores a VALID ISBN-10 as
its ISBN-13 (anything else stays its cleaned characters, never coerced); `pmcid` is stored WITH `PMC`; `pmid` drops
`pmid:`; `issn` is `NNNN-NNNX`; `pii` keeps only [0-9A-Z]; `handle` drops `hdl:` / `hdl.handle.net/`; `oclc` drops
`(OCoLC)`/`ocm`/`ocn`/`on`; `lccn` lower-cased without spaces; `hal` drops a `vN` suffix; `md5 sha1 sha256 s2` lower;
`olid` upper; `openalex wikidata` the last URL segment, upper. Python twin: `litkb.identifiers.norm`, driven over
one table with the SQL by `qc/test_litkb_s45_identity.py` (mutation row B1S1 on its DOI call).

## `litkb.identifier_versions` provenance (litkb, migration 0032)

- `verified_by` widens to the linkage survey's service list (§3.2 item 1): `crossref datacite arxiv s2 openalex
  opencitations pubmed pmc_idconv europepmc unpaywall core doaj openaire ads wikidata handle isbnlib openlibrary
  internetarchive hathitrust gbooks worldcat fatcat annas libgen nexusstc deterministic manual` (one home:
  `litkb.admit.harvest.VERIFIERS`). A harvested value is ASSERTED, not verified: harvest rows leave it NULL.
- **`asserted_by`** — the SOURCE that put this (scheme, value) on this work (Invenio's provider/client split): every
  verifier, plus `caller` (the admitting caller handed it in — a hunt reference, a CLI flag; its confirmation is
  `verified_by`), `tracker` (a literature tracker row), `legacy` (a legacy corpus file stem). One home:
  `litkb.admit.harvest.ASSERTERS`. NULL on every row written before 0032 until the backfill fills it.
  `litkb.admit` sets it on every identifier it writes (caller's value, else `manual` for a manual admission,
  `tracker`/`legacy` by scheme, else `caller`); `litkb.record_identifiers` refuses a row without one.
- **`derived_from_scheme` / `derived_from_value`** — the INPUT identifier the value was derived from (the DOI whose
  Crossref record carried the PII; the md5 whose archive record carried the ISBN). Both or neither.
- **`provenance_backfilled`** — true only on a row whose `asserted_by` the reviewed backfill filled.
- `deterministic` is a first-class source (`asserted_by`, and `verified_by` where the derivation is an arithmetic
  identity — ISBN-10 -> ISBN-13): the Wave-0 zero-request derivations of `litkb.identifiers` (`arxiv_to_doi` — a
  CANDIDATE, `evidence.candidate`, `verified_by` NULL until DataCite confirms — `doi_to_arxiv`, `isbn10_to_13`,
  `isbn_a_doi` from a hyphenated ISBN only, `pmcid_forms`, `parse_hs_alias`).
- The views `main_identifiers` and `ws_identifiers` carry the four new columns (appended) and, because 0032
  re-states them with `v.*`, 0008's `rebased_from_version_id` too — five appended columns (auditor-cand2 N4).

**The backfill.** `litkb.backfill_identifier_provenance(p_apply, p_session)` (SECURITY DEFINER, EXECUTE to
`litkb_ingest`): FILLS each NULL `asserted_by` from the row itself (`tracker` -> `tracker`, `legacy_stem` ->
`legacy`, `verified_by='manual'` -> `manual`, else `caller`), sets `provenance_backfilled`, overwrites nothing;
`p_apply` false is a dry run returning the plan. Driver: `qc/instruments/litkb_identifier_provenance_backfill.py`
(dry run by default; `--apply --session <label>` is the orchestrator's live write). It connects through
`litkb.extract.references_ingest.connect` — `litkb` through `litkb.ingest.connect()`, a worker database through its
owner login + `SET ROLE litkb_ingest` (`--db`); `litkb.db.connect.connect` refuses the ingest login by design.

## `litkb.works` parent columns (litkb, migration 0032)

`part_of_work_id` (chapter -> book, article -> proceedings volume) and `version_of_work_id` (preprint -> version of
record, arXiv version -> concept), both FK `works(id)`, never the work itself. Filled ONLY by
`litkb.record_work_relations` from a relation whose direction the registry stated and whose target is a work in the
base — a target named by a TYPE-SCOPED scheme (a chapter's `is_part_of` its book's ISBN) is the work of one of that
scheme's identity types holding the value, whatever the source work's own type (`is_part_of`/`has_part` -> part_of; `is_preprint_of`/`is_version_of`/`has_preprint`/`has_version` ->
version_of), and MONOTONE: trigger `works_parent_monotone` refuses to overwrite a set parent (fatcat's merge — a
later source fills a NULL and never overwrites). `main_works` / `ws_works` carry both (appended), and 0008's
`rebased_from_version_id` beside them (the `v.*` re-statement; auditor-cand2 N4).

## `litkb.work_relations` (litkb, migration 0032 — the edge table, with the third state)

One row per relation FACT a source stated about a work: `work_id` (the work whose record carried it), `relation`,
`state`, `source_relation` (the registry's own word, e.g. `has-preprint`, `IsVersionOf`, `externalIds.ArXiv`),
`target_scheme` / `target_value` / `target_value_norm` (the identifier the source named), `target_work_id` (the
work in the base holding it, when one does — filled later, never overwritten, when the target arrives after the
edge), `asserted_by` (every `ASSERTERS` value plus `conflict-resolution`), `derived_from_scheme` /
`derived_from_value` (the input identifier), `conflict_source` (the scheme that collided; set exactly when
`asserted_by = 'conflict-resolution'`), `evidence`, `workstream_id`, `agent`, `session_id`, `created_at`. Writer:
`litkb.record_work_relations` alone (SECURITY DEFINER, token-checked, EXECUTE to `litkb_writer`); INSERT to nobody.

**`state` — the THIRD STATE** (the plan's "edges with a third state"; its source is the 2026-09-21 revision's
linkage row, "a third state for an empty field"): `asserted` (the source returned this relation) · `none_returned`
(the source was asked and its relation field was EMPTY — recorded because "absence of the field is not evidence of
absence"; no relation, no target) · and, by the absence of any row, NOT ASKED. One `none_returned` row per (work,
source, input identifier).

**`relation`** (closed; one home `litkb.admit.harvest.RELATIONS`; inverse pairs `litkb._relation_inverse` /
`harvest.INVERSE`): `is_part_of has_part is_version_of has_version is_new_version_of is_previous_version_of
is_preprint_of has_preprint is_manuscript_of has_manuscript is_identical_to is_same_as is_variant_form_of
is_original_form_of is_supplement_to is_supplemented_by is_correction_of has_correction is_review_of has_review
is_translation_of has_translation is_replaced_by replaces is_derived_from has_derivation is_expression_of
has_expression is_manifestation_of has_manifestation other` — DataCite's identity and grouping relations in
snake_case plus Crossref's preprint/manuscript words; `other` for a non-citation relation neither names. CITATION
relations (`references`, `is-referenced-by`, `Cites`, `IsCitedBy`) are NOT edges here: they are the citation
graph's. One fact is recorded once: an edge whose inverse the other work already asserted is not written again
(its NULL `target_work_id` is filled instead).

S2's `externalIds.ArXiv` on a work whose DOI is not arXiv's own is an EDGE (`has_version`, target the arXiv id),
never the work's `arxiv` identifier: S2 merges editions, and an alias would break `litkb-sibling-edition` (check 2
would then refuse the preprint's own admission as a duplicate).

## `litkb.identifier_conflicts` (litkb, migration 0032 — fatcat's collision rule, COUNTED)

When `litkb.record_identifiers` is offered a DISTINCT-valued identifier (or a type-scoped one between two works of
its identity types) that ANOTHER work already holds, it writes no identifier row, asserts a work-level edge
(`is_version_of` for a distinct scheme, `is_identical_to` for a type-scoped one — or the row's `conflict_relation`)
with `asserted_by='conflict-resolution'`, and writes ONE row here: `scheme`, `value`, `value_norm`,
`claimed_by_work_id` (the work it was offered to), `held_by_work_id`, `edge_id` (NOT NULL -> the edge), `asserted_by`
(the dropped row's source), `derived_from_*`, `resolution` (`dropped`), `evidence`, `workstream_id`, `agent`,
`session_id`, `created_at`. UNIQUE per (scheme, value_norm, claimed_by, held_by): a re-harvest is `already_counted`.
Counter `conflicts_uncounted` reads it against `litkb.identifier_claims` (below) and the conflict edges.

## `litkb.identifier_claims` (litkb, migration 0032 — every claim `record_identifiers` weighs, with its outcome)

One row per identifier row `litkb.record_identifiers` reaches the conflict decision with (a registered scheme, a
value that normalises, `asserted_by` named, not a waiting candidate), INSERTED BEFORE the claim is resolved and
given its outcome after: `work_id` (the claiming work), `scheme`, `value`, `value_norm`, `asserted_by`,
`derived_from_scheme` / `derived_from_value`, **`outcome`** (closed: `written` — a new identifier version ·
`held` — the work already holds it · `conflict` — another work holds it as identity: dropped, edge, conflict row ·
`collided` — the unique index refused the write although the conflict rule saw no holder: a conflict the rule did
NOT resolve, kept here instead of vanishing into a rolled-back error; NULL only inside one call, and a committed NULL
is a claim whose resolution was never recorded), `held_by_work_id` (set exactly when `conflict`), `error` (the index
error, set exactly when `collided`), `workstream_id`, `agent`, `session_id`, `created_at`. INSERT to nobody (the
SECURITY DEFINER writer alone); SELECT to `litkb_reader`, `litkb_writer`, `litkb_promoter`. Why it exists (Codex
X4, auditor-B1 F4): a unique index keeps a duplicate from ever persisting, so a counter that looks for surviving
duplicates is blind to a broken conflict rule; this table records the conflict EVENT durably.

## `litkb.record_identifiers` / `litkb.admit` identifier rules (litkb, migration 0032)

`litkb.record_identifiers(ws, token, work, identifiers jsonb, agent, session) -> {written, held, conflicts, refused,
collided}`
— the ONE write path of HARVESTED identifiers (SECURITY DEFINER, token-checked, EXECUTE to `litkb_writer`). Each row
`{scheme, value, asserted_by, verified_by?, evidence?, derived_from?: {scheme, value}, conflict_relation?}`: an
unregistered scheme or a value normalising to nothing is `refused`; a row with no `asserted_by` RAISES; a
CANDIDATE row (`evidence.candidate` true — `litkb.identifiers.arxiv_to_doi`'s 10.48550 DOI) with no `verified_by` is
`refused` until its caller names the registry that confirmed it; every other row is an `identifier_claims` row
first; a value the work already holds is `held` (monotone); a value another work holds as identity is a counted
conflict (above); else a version is written — FACT mode for a work in main (as registry admission writes), PROPOSAL
mode for this workstream's own unapproved work — and a write the unique index refuses is `collided` (kept, not
raised; only `unique_violation` is caught). `litkb.admit.harvest.record` runs it and `record_work_relations` in ONE
transaction block (`conn.transaction()`: a SAVEPOINT inside a caller's open transaction), so a failed harvest never
aborts a transactional caller's admission. `litkb.admit` (replaced from 0014): refuses a row carrying `derived_from` (harvest goes through
`record_identifiers`), refuses an unregistered scheme, runs check 2 over DISTINCT schemes only (plus type-scoped
`isbn` between two books), reads its strong schemes from `identity_strong` — counted only where the scheme is the
candidate's identity (distinct, or the candidate's type among its `identity_types`) — and writes `asserted_by` on every
identifier. `litkb._check_registry` (replaced from 0020) reads its schemes from `registry_confirmed`.

## `litkb.acquire.annas.fetch_for_litkb` result key `identifiers_unified` (S4.5 builder B1)

The archive route's result dict gains `identifiers_unified`: gate 2's record's whole
`file_unified_data.identifiers_unified` dictionary once gate 2 has passed, else `{}` (until S4.5 all but its `doi`
key was dropped). `litkb.admit.harvest.from_annas` maps its keys to schemes (`md5 isbn13 isbn10 sha1 sha256 zlib
lgrsnf lgrsfic lgli oclc lccn ol ocaid nexusstc`) and returns every other key in `skipped` (never its `doi` list,
never storage keys like `ipfs_cid`); `harvest.record_route_identifiers` writes them. Admission's harvest
(`litkb.admit.front.harvest_admission`) writes the Crossref / DataCite record `confirm_doi` already fetched:
`alternative-id` -> `pii` (Elsevier only), `ISBN`/`isbn-type` -> `isbn`, `ISSN`/`issn-type` -> `issn`, `relation`
/ `relatedIdentifiers` -> edges or the third state. OpenAlex (`from_openalex`) and Semantic Scholar (`from_s2`) are
parsers only: their calls are Stage B's (S4.5 decision D2).

## litkb_acq_probe_relation.csv (phase4/qc/, GENERATED — the Crossref `relation` probe, S4.5 item 1)

Written by `qc/instruments/litkb_acq_probe_relation.py` (a LIVE instrument: one Crossref request per DOI-bearing work
in main, through `litkb.netutil.Client`, paced 1 s; `--responses <dir>` replays recorded answers with no socket).
One row per relation edge Crossref's record states, or one `none_returned` row (the third state) when the field is
empty, or one `unanswered` row when Crossref did not answer 200. Columns: `key`, `doi`, `cr_status`, `state`
(`asserted` · `none_returned` · `unanswered`), `relation` (the `work_relations.relation` vocabulary), `source_relation`
(Crossref's word), `target_scheme`, `target_value`, `crossref_asserted_by` (Crossref's own `asserted-by`: `subject` /
`object`). Its data rows are the gated counter `relation_probe_rows`. Not yet run: its first run is the
orchestrator's live pass.

## S4.5 builder B1 counters (`qc/instruments/litkb_hardening_b1.py`, read by `litkb_acceptance.py hardening`)

GATED: `relation_probe_rows>=1` (ANSWERED data rows — state `asserted` or `none_returned` — of the relation probe
CSV the manifest names; `unanswered` rows measure nothing and are reported in the detail line, never counted; none
named reads 0) · `key_derivation_crashes=0` (run-CSV rows ending `crashed` with reason `admit:CheckViolation` — the
pre-S4.5 cut key — or `admit:KeyUnderivable` — `make_key` refusing by name, `litkb.admit.front.KeyUnderivable`;
UNREAD with no `run_csv`) ·
`crosswalk_rows_without_identifier=0` (ALL-TIME: of the manifest's crosswalk-selected rows, those whose work lacks
the probe's `s2_arxiv` as an `arxiv` identifier or an asserted edge to it, any `cr_isbn` as an `isbn`
identifier, or — for each NON-citation `cr_relation_types` word — an asserted edge of THAT relation
(`harvest.relation_of`) with the work as subject, or its inverse with the work as target; the CSV holds relation
WORDS, not targets, so this clause proves an edge of the stated type exists and CANNOT prove it points where
Crossref meant) ·
`identifiers_without_provenance=0` (ALL-TIME: identifier_versions rows with `asserted_by` NULL) ·
`conflicts_uncounted=0` (ALL-TIME conflict EVENTS with no resolution record, one per (scheme, value, claiming
work): `identifier_claims` rows `collided`, unresolved (NULL), or `conflict` with no `identifier_conflicts` row, and
conflict-resolution edges with no conflict row; plus distinct-scheme values two works' active versions hold with no
conflict row between them) · `nondistinct_schemes_in_unique_index=0` (schemes the
index covers that the registry or the plan — `isbn issn oai handle md5` — call non-distinct, united with plan
non-distinct schemes the registry marks distinct). REPORTED: `relation_edges_missing` (works the relation probe
gives an asserted relation that hold no asserted edge), `identifier_first_refusals` (run admissions refused
`duplicate-review` whose candidate carried an identifier of an `identity_strong` DISTINCT scheme; a type-scoped one
is strong only for its types, which the candidate row does not carry), `books_without_isbn` (main works of
type book or chapter with no active `isbn`). Manifest keys read: `probe_csvs` (`litkb_acq_probe_relation.csv`,
`litkb_acq_probe_crosswalk.csv`), `run_csv`, `rows` (with `source`), `frozen_at`, `run_workstream_ids`, `repo`;
`scope_workstream_ids` is set by a fire or a test only, never by `--freeze`. DETAILS (detail lines):
`relation_probe_rows` (the unanswered count), `conflicts_uncounted` (each uncounted event and why),
`crosswalk_rows_without_identifier`, `nondistinct_schemes_in_unique_index`.

FIRES (each also a test in `qc/test_litkb_s45_identity.py`): `relation_probe_emptied` (control: the probe over
E21's CONSTRUCTED Crossref records -> 2 rows; known-bad: the CSV emptied -> 0) · `relation_probe_unanswered`
(known-bad: every request failed, status 0 -> the probe writes 2 `unanswered` rows -> 0) · `key_guard_deleted`
(known-bad: `make_key`'s surname guard removed in-process from its live source -> 187 ends
`crashed / admit:KeyUnderivable` -> 1) · `harvest_disabled_crosswalk_isbn` / `harvest_disabled_crosswalk_relation`
(one CONSTRUCTED crosswalk row carrying only `cr_isbn` / only `cr_relation_types`, its CONSTRUCTED Crossref answer
harvested through `from_crossref` + `record`: 0; known-bad: the harvest not written -> 1 — each clause its own fire) ·
`conflict_detection_removed` (known-bad: `record_identifiers` without its conflict detection -> the claim meets the
unique index and is kept `collided` -> 1) · `key_rule_reverted` (row 187's
DOI hunted against its CONSTRUCTED DataCite record: control `held`, key `LPVSWGCV_2025_land-cover-change-map`;
known-bad: the pre-S4.5 `key[:59]` rule -> `crashed / admit:CheckViolation` -> 1) · `harvest_disabled_crosswalk`
(three real crosswalk arXiv-id rows re-hunted against CONSTRUCTED S2 answers built from their own columns: 0;
known-bad: the harvest disabled -> 3) · `null_asserted_by` (known-bad: the admission's provenance guard removed ->
1) · `constructed_second_work_claims_doi` (control: the DOI dropped, an `is_version_of` conflict edge, one conflict
row -> 0; known-bad: the count skipped -> 1) · `isbn_in_distinct_set` (known-bad: the registry's isbn row made
distinct and the index rebuilt from it where the held rows allow -> 1) · `e21_pair_two_works_one_edge` (bound `=0`:
the pair admitted through `admit_registry` is two works, ONE `has_preprint` edge, the preprint's
`version_of_work_id` the article; known-bad: the admission harvest disabled -> 2 unlinked) ·
`e06_still_duplicate_review` (bound `=0`: E06's URL, title-near its carrier, refused `duplicate-review`; known-bad:
`url` made identity-strong -> admitted -> 1). CONSTRUCTED registry answers: `qc/fixtures/litkb_b1_constructed_registry.json`.

<!-- S4.5 builder B2 (adjudication: refuse verb, decision log, withdraw, operator-bind gate, migration 0034): its SCHEMAS rows go between this marker and the next; the orchestrator removes the markers at landing -->

## `litkb.adjudications` — the decision log, and the verbs that write it (litkb, migration 0034)

Where the knowledge base answers **who decided a proposal, with which verb, when, and why**
(LITKB_WORKPLAN.md "### S4.5" item 1). APPEND-ONLY for every role: no agent role holds INSERT,
UPDATE, DELETE or TRUNCATE on it, and the triggers `adjudications_append_only` /
`adjudications_no_truncate` refuse UPDATE, DELETE and TRUNCATE to the OWNER too (SQLSTATE 42501) —
a decision is corrected by a NEW decision, never by rewriting the old one. Its only writers are the
three SECURITY DEFINER verbs below (EXECUTE to `litkb_writer`); SELECT to `litkb_reader`,
`litkb_writer`, `litkb_promoter`. Every row is written in the SAME transaction as the state change
it records, so a refused decision leaves nothing but its error. A RELAYED design
(Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md §1.8 R1/R2/R4), UNVALIDATED until the
substrate referee scores it on the real rows (194's proposal; the 17 operator binds).

| column | meaning |
|---|---|
| `id` | one decision (uuidv7) |
| `verb` | `refuse` · `approve` · `withdraw` (closed) |
| `admission_id` | the subject when it is an ADMISSION — `refuse` only (an admission's APPROVAL stays recorded on `admissions.approver_*`, its one home; it is not duplicated here) |
| `entity` · `version_id` | the subject when it is a VERSION (`work` · `identifier` · `file` · `gap` · `use`); exactly one subject per row (`adjudications_one_subject`) |
| `versions` | JSON array, every version row the decision changed: `{entity, id, version, from, to}` |
| `proposer_workstream` · `proposer_agent` · `proposer_session` | who PROPOSED the subject (the admitter, or the version's writer) |
| `reason` | why; non-blank after invisible characters are removed for `refuse` and `withdraw` (`adjudications_reason_given`), optional for `approve` |
| `workstream_id` · `agent` · `session_id` | who DECIDED (labels normalised, `litkb.textnorm.norm_label`) |
| `decided_by` · `decided_at` | the LOGIN (`session_user`, never the definer) and when |

**The two-session rule** (`adjudications_second_session_decides`): `refuse` and `approve` are refused
(23514) when the deciding session IS the proposing session after invisible characters are removed —
the shape of `admissions_second_session_signs_off` (0014). `withdraw` is the proposer's own and must
come from the proposing WORKSTREAM (`adjudications_withdraw_is_the_proposers`). The Python front
(`litkb.admit.front`) compares the labels again BEFORE each call: the plan's "both guards".

**The verbs** (every one CLI-only; the MCP server has none):

| verb (SQL · Python · CLI) | subject | what moves | refused when |
|---|---|---|---|
| `litkb.refuse_admission` · `front.refuse` · `litkb refuse <admission-id> --reason R [--dry-run]` | a `proposed` MANUAL admission | admission → `declined`; every `proposed` work / identifier / file version of it in the admitter's workstream (the whole chain, head to base — no API writes a chain longer than one version for an admission's work today, so the walk is pinned by a CONSTRUCTED owner-level chain in the suite) → `rejected`; the admitter's heads for them removed. Main never moves. NOT moved: the admitter's proposed USES of the declined work (a use is the proposer's own claim) — the result and the dry run list them as `left_proposed` with the verb that clears them (the proposer's `withdraw --entity use`), because `promote_prepare` would hold them for ever ("the work is not admitted in main") | not manual+proposed (55000) · the admitter's workstream not open (22023, D3 as `approve_admission`) · the admitter's own session (23514) · no reason |
| `litkb.withdraw_version` · `front.withdraw` · `litkb withdraw <version-id> [--entity file] --reason R [--dry-run]` | the proposer's own `proposed` version | version → `withdrawn`; the workstream's head falls back to the version it was based on when that is this workstream's own proposal (`proposed` or `prepared` — the set `_ws_chains` walks: a prepared version stays in its promotion's chain; auditor-B2 round 3 F1, integrator-w2), else the head is removed and the workstream's view follows main again (a base that is main's `promoted` version, or another workstream's, is never pinned as this workstream's head); the dry run's `head_falls_back_to` says the same, `null` when the head is removed. Main never moves | not `proposed` (a `prepared` head included) · not its workstream's head (withdraw from the top down) · a version an open manual admission proposed (a second session refuses that) · another workstream · no reason |
| `litkb.decide_file_versions(verb)` · `front.decide_files` · `litkb approve-files` / `litkb refuse-files` `[<version-id> ...] [--pending] [--reason R] [--dry-run]` | LONE `proposed` FILE versions on works ALREADY in main (an `acquire --from-file` bind, a refused-duplicate URL landing) | `approve`: `files.current_version_id` moved by compare-and-set from the version's base, state → `promoted`; `refuse`: state → `rejected`, main untouched. Heads removed. BATCHED, ALL OR NOTHING, one decision row per version | a named version that does not exist (P0002; the whole batch, nothing decided — naming one version twice is one version) · a version not its workstream's `proposed` head · its work not in main (that is an admission) · its workstream not open (22023) · the proposing session (23514) · `refuse` with no reason |

`--dry-run` prints what the verb WOULD do and every reason the database would give (`front.refuse_plan`,
`front.withdraw_plan`, `front.decide_plan`) and writes nothing; `approve-files --pending` names every
lone file proposal (`front.pending_file_proposals`) and never sends one the plan already refuses.

**The new states.** `admissions.state` gains `declined` — the REVIEWER's refusal. `refused` keeps its
0013 meaning, the MACHINE's check failure (`_refuse_admission`); the two are counted apart. The version
tables' `rejected` and `withdrawn` (0001) gain their first writers: `rejected` ← `refuse_admission`,
`decide_file_versions('refuse')`; `withdrawn` ← `withdraw_version`. `candidates.state = 'rejected'`
remains the refusal function's own word and is not written by any verb here — so a DECLINED proposal's
candidate row keeps `candidates.state = 'admitted'` (the word `admit` wrote; 0001's candidates CHECK has
no word for a reviewer's refusal, and giving it one is a ruling), and `litkb_candidates` lists it among
the admitted: `admissions.state` is where the decision is read. Known consequences, not
fixed here: a `rejected` version's title still takes part in check 2's `_title_duplicates` (global,
every version), and its file's sha256 row still answers `duplicate-file`/`file_duplicate`, so the SAME
bytes cannot be re-proposed.

**In the promotion report** (`promote.chain_why`). `_ws_chains` (0019) holds EVERY work / identifier /
file chain with the sentence "enters main only through litkb.approve_admission". For a LONE file chain —
a file proposal on a work main already holds (`promote.chain_rows`' `lone_file`: every operator bind and
refused-duplicate landing since this migration) — that verb refuses it (55000: the work's admission is
not a proposed manual one), so the report and the `promote prepare` JSON print `promote.LONE_FILE_WHY`
in its place: `lone-file: … litkb approve-files <head version> or litkb refuse-files <head version>`.
An admission's own file chain (its work not in main) keeps the admission sentence.

**The operator-bind gate** (`litkb-from-file-version-state`, Kam 2026-09-22). `litkb.attach_file` (0034
re-creates 0013's body with one guard) writes a file whose `source_route` is in
`litkb._proposal_source_routes()` — `browser` (`acquire --from-file` landing a copy), `held-in-place`
(`--from-file` of a topic-folder file) and `web` (a refused-duplicate URL landing, below) — as a
`proposed` version in the binding workstream's heads, NEVER as main's version of record. Its result says
`outcome: attached` either way (`acquire.run` reads only that word; the attempt stays `ok`) and
`state: proposed` / `promoted`. Every automated route (and no route) still binds a fact. `litkb acquire
--from-file` prints the proposed version and the `approve-files` line that clears it. The 17 historical
operator binds (6 `browser`, 11 `held-in-place`, all `promoted`) are untouched (S4.5 decision D8).
`litkb.admit.front.PROPOSAL_SOURCE_ROUTES` mirrors the route list; `qc/test_litkb_adjudicate.py` holds
them equal.

**The refused-duplicate landing** (`hunt._offer_refused_landing`, the URL path). When a URL landing's own
admission is refused `duplicate` (check 2 names the work) or `duplicate-review` (the title-near works,
most similar first), the filed PDF is OFFERED to that work through check 3 (`litkb.attach_file`, binding
against the work's MAIN title and first author) with `source_route = 'web'`: it binds → a PROPOSED file
version of that work plus its `hunt-url` acquisition event; it does not → moved to `_quarantine/` with a
`.reason.json` and a `quarantine_payloads` row (origin `hunt-url`, the work named) under the existing
reason words — `binding-failed` / `binding-pending` (check 3), `duplicate-held` (the bytes are already
held, or no matched work is in main), `probe-error`. A refusal at `file_duplicate` quarantines the stray
copy `duplicate-held`. The hunt still ends `refused/admission-refused` (the closed `STATES`/`REASONS` do
not grow); the result carries `offered` and `quarantined` or `landed`. Every other refusal (check 3 on
the claim, a key collision) leaves the file where it lies, as before, and is counted below.

**The counters** (`qc/instruments/litkb_hardening_b2.py`, loaded by path by `litkb_acceptance.py
hardening`; S4.5 decisions D1/D6/D8):

| counter | kind | scope | meaning |
|---|---|---|---|
| `proposals_unadjudicated` | GATED `=0` | all time | `proposed` manual admissions older than `frozen_at` (neither `approved` nor `declined`); live baseline 1 (194) |
| `operator_binds_unproposed` | GATED `=0` | run | `browser`/`held-in-place` file versions created after `frozen_at` by the run's workstreams that are `promoted` with no `approve` decision row |
| `promotions_prepared` | GATED `>=1` | run | promotions prepared after `frozen_at` for the run's workstreams (2 historical prepared promotions exist on live) |
| `promotions_committed` | reported | run | committed after `frozen_at`; cannot move inside S4.5 (`promote.commit` needs Kam's merge, `verify_merge`) |
| `operator_binds_historical` | reported | all time ≤ `frozen_at` | promoted operator binds with no approval (live 17) |
| `unowned_landings` | reported | disk | PDFs under `_litkb_staging/filed/` whose sha256 is in no `files` row and no `quarantine_payloads` row (every PDF hashed; `manifest.literature_root`, else `LITERATURE_ROOT`; live 3 on 2026-09-23) |
| `self_adjudications` | reported | — | `approve`/`refuse` rows whose deciding session is the proposing session (0 by the constraint) |
| `decision_log_unguarded` | reported | catalog | agent-role INSERT/UPDATE/DELETE/TRUNCATE grants on the log + missing/disabled append-only triggers (0) |

`manifest.scope_workstream_ids` narrows the all-time counters to named workstreams; only the fires set
it. Each fire (`FIRES`, with an extra `bound` key) runs a control and a known-bad arm on a worker
database, mutating the REAL guard in a rolled-back transaction: `refuse_verb_removed`,
`operator_bind_as_version_of_record`, `promotion_prepared_by_the_run`, `self_refusal`,
`decision_log_rewrite`. Every SCOPING clause of the three gated counters (time and workstream) is its
own guard block, and each fire's arms hold the row that clause exists to exclude — a proposal made
AFTER the freeze (`refuse_verb_removed`), a pre-freeze operator bind that is a fact
(`operator_bind_as_version_of_record`), a promotion the run's workstream prepared BEFORE the freeze and
one another workstream prepared AFTER it (`promotion_prepared_by_the_run`) — so deleting any one clause
alone turns an arm red.

<!-- S4.5 builder C1 (ledger vocabulary + acquisition substrate, migration 0033): its SCHEMAS rows go between this marker and the next; the orchestrator removes the markers at landing -->

### `litkb.acquisition_attempts` — the 0033 ledger vocabulary (S4.5 builder C1a)

Migration 0033 (`pipeline/litkb/db/migrations/0033_acquisition_ledger_vocabulary.sql`) supersedes the route and status
sets stated in the section above; the ONE Python home of every vocabulary below is `pipeline/litkb/acquire/policy.py`,
held equal to the CHECKs by `qc/test_litkb_ledger.py` (`test_the_0033_checks_are_the_python_vocabularies`). The
writer is still `litkb.record_acquisition_attempt` alone, re-created with the new facts as DEFAULTed parameters
(one signature; the nine-argument calls resolve unchanged); the Python door is still
`litkb.acquire.run.record_attempt`, which now also redacts `terminal_url`.

| column | type | meaning |
|---|---|---|
| `route` | text, CHECK | `policy.ROUTES_ALL`: `open_access annas scihub browser hunt-url` (0001/0028), `ladder` (a row no single rung owns: a `budget-stop`, and only a `skipped` or `budget-stop`), the Stage A/B rungs `arxiv openalex crossref-link s2 datacite core doaj openaire osf europepmc venue zenodo hal figshare opencitations ncbi-idconv eartharxiv publisher-url`, Stage C `landing`, the shadow front `bban`, Stage E `wayback ia commoncrawl`. Which stage a rung route runs in: `policy.STAGE_OF` |
| `status` | text, CHECK | 0013's fifteen plus four ATTEMPT words (never hunt states — the hunt's closed STATES/REASONS and the acceptance instrument's `CLOSED_STATES` pin are unchanged): `skipped` (a rung the ladder did not ask; its reason is the sub-status — guard 14), `budget-stop` (the ladder budget ran out before this point; route `ladder` — guard 12), `measured` (a rung answered a hit in MEASURE mode and nothing was landed — S4.5 decision D9), `known-bad` (a route served bytes whose sha256 matches refused bytes; nothing was written) |
| `sub_status` | text, CHECK consistent with `status` | WHY. `bad-file`: `html_response too_small missing_pdf_header corrupt_pdf_header early_eof_with_trailing_payload stub_not_article volume_not_article cited_document_not_this_article compressed_or_archived_payload`; `blocked`: `identity_required challenge_or_bot_check not_found html_or_reader`; `not-in-archive`: `not_in_corpus no_pdf_link`; `skipped`: `dead_route` (a prior terminal miss, `run.DEAD_STATUSES`) · `dead_in_run` (a prior `blocked` in THIS workstream — plan item 2) · `no_identifier` (the rung needs an identifier the work does not hold) · `policy_refused` (the pre-fetch PolicyDecision) · `backoff_window` (the refusal ladder has not reopened); `budget-stop`: `budget_seconds budget_attempts`; `ok` / `measured`: `unverified_keep` (guard 17: landed although a check that needs metadata could not run). NULL for every other status, and on history until the reviewed backfill types it. A `skipped` or `budget-stop` row with NULL is refused (`acquisition_attempts_skip_has_reason`) |
| `sub_status_basis` | text, CHECK | how the sub-status was decided: `live` (every row the ladder writes; the function forces it), `bytes` / `detail` / `inferred` (the reviewed backfill only). NULL exactly when `sub_status` is |
| `served_sha256` | text, hex CHECK | sha256 of the bytes the route SERVED on this attempt, landed or not (item 1). NULL when nothing was served — a transport failure's `(0, "<Class>: <message>")` answer is the client's own error text, not served bytes, and is noted in `detail` |
| `terminal_url` | text | the response that decided the attempt (redacted). For the Unpaywall lookup it is the API URL WITHOUT its query (the account email never reaches the ledger). PRE-REDIRECT: `netutil.Client` does not expose the post-redirect URL (open question for the client's owner) |
| `terminal_status_code` | integer 0..999 | that response's HTTP status (0 = the client's transport failure) |
| `terminal_dt` | timestamptz | when that response arrived |
| `retriable` | boolean | per attempt (guard 15): would asking again soon plausibly change the answer — a transient code (0, 408, 429, 5xx; guard 13 + `admit/registry.py::is_transient`; one home `backoff.is_transient_code`), or a route that RAISED an OSError. A refusal or a miss is not, and a `blocked` row never is, whatever its code (guard 3: a Cloudflare challenge at 503 is a refusal; `backoff.classify`) and whatever the rung says (`run._record_result`; fix round 3, auditor-C1a r2 F5). A no-byte answer whose every request was a transport failure is always true (S4.5 decision D15). NULL on skip/stop rows. THE DEAD CHECKS READ IT (fix round 2, auditor-C1a F1): a prior row whose `retriable` is true is never evidence that its route is dead (`dead_route`, `dead_in_run`); a row with NULL (every row before 0033) keeps the status-word rule |
| `kind` | text, CHECK | `pdf jats text html-doc cached_text snippet` (survey §3.4): what the attempt obtained; set `pdf` when the served bytes are a PDF |
| `retry_of` | uuid → attempts | a SCHEDULED in-run transient retry names the attempt it retries (same work, route and workstream — refused otherwise); never a re-spend |

`detail` keys the ladder adds: `policy` (the PolicyDecision(s) taken BEFORE the request: route, host, tier,
allowed, reason, line index), `ladder` (`elapsed_s`, `spent_before`, `budget` at the rung's LAUNCH — what
`budget_exceeded_silently` reads), `known_bad` (the matched refused-bytes record: source, id, rel_path, reason,
recorded_at), `not_landed` / `not_quarantined` (MEASURE mode, or a later concurrent hit), `version` (the article
version the route knew), `sub_status_cause` (the classifier's cause word), `reason` (quota-stop / login failure),
`no_byte_served` (the ladder re-booked a rung's no-byte `bad-file` whose every request was a transport failure,
status 0, as `api-error`; the codes).
A `budget-stop` row's detail: `budget`, `spent`, `elapsed_s`, `not_asked`.

**Answers that served no byte are never an untyped `bad-file`** (S4.5 decision D15; fix rounds 2-3, auditor-C1a
F1/F2 and round-2 F1; integrator-w1 Q1). Both rules are THE LADDER's, for every rung. (1) `run._record_result`: a
`bad-file` with no bytes handed back and EVERY request a transport failure (every HTTP code 0) → `api-error`,
`retriable` true (one scheduled retry for rungs that opt in); an answer with any server code (404, 403, an empty
503) stays `bad-file`, and its own codes decide `retriable`. (2) `run._type_attempt` → `ledger.no_byte_bad_file_sub`:
a `bad-file` that kept no byte is typed from its TERMINAL response — a Content-Type naming html → `html_response`;
a length of 0 (a declared Content-Length of 0, or none declared: nothing was handed back) → `too_small`, under
every byte floor; basis `live`. One answer stays untyped and `bad_file_untyped` counts it, fail closed: a declared
Content-Length above 0 with no byte handed back (a rung discarding served bytes; typing it would need the
acceptance test's byte floor). THE OPEN-ACCESS ROUTE (`open_access.fetch_open_access`): an Unpaywall lookup that
did not ANSWER about the DOI (no email, a transport failure, 429 / 5xx, 422, any other code, a body that is not a
JSON record; `unpaywall_locations` meta `lookup = failed`) → `api-error` with the lookup's code — never
`no-oa-copy`, which is dead for the route; `no-oa-copy` means Unpaywall answered (404 "no record", or a record
listing no location) or there is no identifier. Locations that answered with EMPTY bodies are `bad-file`, typed
by rule (2) (fix round 2 had booked them `not-in-archive` / `no_pdf_link`; D15 types them instead).

### `litkb.file_versions` — 0033 (S4.5 builder C1a)

| column | meaning |
|---|---|
| `word_count` | integer ≥ 0: whitespace-separated tokens in the version's text extract (`txt_extract_path`), `litkb.acquire.ledger.word_count_of` — written by every landing (`run.land_and_attach`, `front.file_evidence`) and filled for history by the word-count backfill |
| `copy_kind` | NOT a new column and NO new value (plan item 2, guard 23): `publisher` / `author manuscript` / `preprint` ARE the article versions published / accepted / submitted, now WRITTEN on every landing whose route knows the version (`policy.COPY_KIND_OF_VERSION`: Unpaywall `publishedVersion` → `publisher`, `acceptedVersion` → `author manuscript`, `submittedVersion` → `preprint`; the arXiv copy is `preprint`). NULL where the route does not know it (the archive, Sci-Hub, `--from-file`) |

### `litkb.route_backoff` (migration 0033, S4.5 builder C1a)

The per-(route, work) REFUSAL LADDER, persisted (guard 2) so a second hunt inside the window does not re-spend.
One row per (route, work) — NEVER per host (guard 29). Written only by `litkb.record_route_backoff(ws, token,
attempt_id, refusals, window_started_at, next_allowed_at)` (writer; the token; the attempt must be the CALLER's
workstream's; an older attempt never rolls the row back). Readers: the ladder (`litkb.acquire.backoff.load`) and
nobody's counter — `rehunt_route_spends` replays the LEDGER with the reference policy instead, so a run that set
its own window to zero is graded against the window it should have kept.

| column | meaning |
|---|---|
| `route`, `work_id` | the key (route CHECK = `policy.ROUTES_ALL`) |
| `refusals` | consecutive refusals inside the window (0 = open; a success resets) |
| `window_started_at` | the first refusal of the current 7-day window |
| `next_allowed_at` | before this instant the route is `skipped/backoff_window` for this work |
| `last_attempt_id`, `last_status`, `last_http_codes`, `last_at` | the attempt that last moved the row |
| `updated_at` | wall clock of the write |

The rule (`backoff.BackoffPolicy.step`): a refusal is a `blocked` row or any HTTP code in {202, 403, 429, 503};
inside the window it climbs 15 min → 6 h → 48 h; a success (`ok measured duplicate-held`) resets; a retried
original is superseded by its retry. ALL constants UNCALIBRATED on the ledger, with the reason MEASURED (the
module docstring of `pipeline/litkb/acquire/backoff.py`): no refusal on the live ledger was ever followed by a
recovery (7 of 7 re-asked inside 362 s .. 4.2 days were refused again), and the ledger holds no 429 or 503.

### `litkb.acquisition_backfills` (migration 0033, S4.5 builder C1a)

The reviewed backfills' decision log: ONE row per APPLIED run of `litkb.backfill_attempt_sub_status(session,
source, rows)` or `litkb.backfill_file_word_count(session, source, rows)` (both ingest-only, fill-null only —
a typed row or a recorded count is never overwritten; a sub-status outside the row's status family is skipped
per row, never forced). Columns: `id`, `op` (`sub_status | word_count`), `session`, `source` (the CSV path and its
sha256, or the extract root), `offered`, `applied`, `skipped` (jsonb: `missing already_typed wrong_family
bad_basis` or `missing_or_already_counted`), `at`. The CLI (dry run unless `--apply`):
`py -3.12 -m litkb.acquire.ledger backfill-sub-status --csv <file> --session <label> [--apply]`,
`... backfill-word-count --session <label> [--apply]`, `... type-blocked --out <csv>`.

### The typing CSV (`litkb.acquire.ledger.TYPING_COLUMNS`; S4.5 CONTRACTS)

The shape the sub-status backfill applies, shared with builder C1b's item-8 bad-file CSV:
`attempt_id, sub_status, basis, free_to_fix, cause`. `basis` ∈ `bytes detail inferred`; an EMPTY `sub_status` is
the classifier saying "untypable" and is not offered (the counter keeps counting it); a row whose `cause` is
`misbooked` (`ledger.MISBOOKED_CAUSE`, S4.5 decision D29) is refused BY NAME and never typed. `type-blocked` adds review
columns after those five: `route, http_codes, kept, kept_bytes, at`. The blocked classifier
(`ledger.type_blocked`, strongest evidence first): a challenge signature in the kept bytes or headers →
`challenge_or_bot_check`; a terminal 401 → `identity_required`; 404/410 → `not_found`; a kept page with no
signature → `identity_required` at 403 else `html_or_reader`; no bytes: a route's `=blocked` token →
`challenge_or_bot_check` (inferred — S4.5 decision D30: the route's own word, with no body marker and no kept bytes
behind it); a 200 among the codes → `html_or_reader` (inferred); a 403 →
`challenge_or_bot_check` (inferred — 12 of 12 kept 403 bodies on the ledger were challenge pages, survey-data
§2.5). `free_to_fix` is left empty for blocked rows (not assessed here).

`phase4/qc/litkb_acq_probe_blocked.csv` (tracked, MEASURED read-only on live by builder C1a on 2026-09-23 with
`py -3.12 -m litkb.acquire.ledger --role litkb_reader type-blocked --out ../phase4/qc/litkb_acq_probe_blocked.csv`
from `Scripts/`): the historical `blocked` typing in this shape — 39 rows, all `challenge_or_bot_check` (scihub
25 by `inferred` — the route's token alone, S4.5 decision D30; open_access 11 by `bytes`, 1 by `detail` — the
route's own rule over its kept first body — and 2 by `inferred`, the same rule with no bytes kept). The file the orchestrator's live
`backfill-sub-status --csv` applies for `blocked_untyped`; `write_csv` creates it and never overwrites one.

### The acquisition ladder (`pipeline/litkb/acquire/run.py`, S4.5 builder C1a)

A staged RUNG REGISTRY (`run.RUNGS`, `run.register`): stages `A B C E shadow` in that order; Stage B's rungs run
concurrently (wall-clock = the slowest), every database write on the caller's thread in registry order. The rung
interface: `fn(work, ctx) -> route dict` (keys listed on `run.Rung`). A rung module registers with its OWN
pre-fetch lines: `run.register(rung, policy_lines=(policy.PolicyLine(route, host, tier, why), ...))` adds them to
the one `policy.POLICY` through `policy.add_lines`, which refuses a line for another route, a tier that is not
its route's STAGE's (a shadow-stage route is `shadow`, every other `legitimate` — a shadow front can never be
declared legitimate) and a (route, host) lined twice; `register` REFUSES a rung that ends with no line (it would
be `policy_refused` on every work). Around every rung: the skip checks (each a `skipped` row; the dead checks
read each prior row's `retriable`), the pre-fetch `policy.decide` (one `policy.POLICY` line per rung/host; the
shadow tier's one switch `policy.SHADOW_TIER_ENABLED`; the shadow tier refused once a legitimate rung has hit),
the budget (`policy.LadderBudget`: `seconds` 505 — the OBSERVED MAXIMUM of 17 tracked three-route hunts that
landed nothing, one outlier, E13's 504.76 s (median 52.77 s, next largest 62.09 s): no historical hunt would
have hit it, and the run's manifest `ladder_budget` is where a re-measured value belongs; `attempts` DERIVED =
rungs × (1 + one scheduled retry); `concurrency` DERIVED = the widest concurrent stage), one scheduled retry for
a transient answer (rungs that opt in; the budget is checked AGAIN after the retry's wait — Retry-After or the AIMD
delay, up to 300 s — and a retry the wait has put past the budget is not launched: the original stays `retriable`
and unretried, and the next stage or rung writes the `budget-stop`; in a concurrent stage the siblings launched
beside the rung count as spent in both checks and in the retry's `spent_before`, because they are asked before any
is settled — fix round 3, auditor-C1a r2 F2), the rejected-hash lookup (`ledger.rejected_match`: every uncleared
`quarantine_payloads` sha plus every rejected/withdrawn file version's — EXCEPT that a DOWNLOADED match the
corpus HOLDS for this work's purposes, `ledger.held_file(conn, sha, work_id)` (a `files` row whose current version
is `active` and neither `rejected` nor `withdrawn`, and which is THIS work's or one no refused-bytes record names
for this work), is a hit: `duplicate-held` in acquire mode, `measured` in MEASURE mode; auditor-C1a F3, the five
live payloads refused once and bound later, which 0030 never clears; bytes refused FOR this work stay
`known-bad` for it whoever holds them — fix round 3, auditor-C1a r2 F3), the typing (`ledger.sub_status_for`; a `bad-file` row's word is THE acceptance test's,
`ledger.bad_file_verdict` — integrator-w1; then `ledger.no_byte_bad_file_sub` for a no-byte `bad-file`,
D15), and the per-(route, work) back-off write. A rung's DOWNLOADED bytes land through THE ACCEPTANCE TEST
(`run._land` → `accept.offer_to_bind`, then the bind): a refusal is a `bad-file` row carrying the verdict's
sub-status and `detail.acceptance`, its bytes in _quarantine/ with the verdict in the sidecar; bytes a route
itself refused are typed by the same test and keep its summary in `detail.acceptance` (the landing pointers
Stage C reads). `mode="measure"` (`run.measure`, the run driver's hook) asks every rung — a route's earlier
terminal miss does not skip it there — judges every hit by the acceptance test (`measured` or `bad-file`),
writes nothing to the store, and records every answer.

### C1a's acceptance counters (`qc/instruments/litkb_hardening_c1a.py`, loaded by `hardening`)

| counter | gated | scope (S4.5 decision D1) | what it counts |
|---|---|---|---|
| `rehunt_route_spends` | = 0 | run | spent attempts (not a skip/stop, not a `retry_of`) on a (route, work) inside the refusal window the REFERENCE policy replays from every earlier attempt |
| `known_bad_relands` | = 0 | run | route attempts (not `browser`) that wrote their bytes into the store (`ok`, or `detail.quarantined`) although their `served_sha256` matched refused bytes recorded before them |
| `bad_file_untyped` | = 0 | all-time | `bad-file` rows with NULL `sub_status`, less exactly the attempt ids the manifest's item-8 CSV (`probe_csvs["litkb_acq_probe_badfile.csv"]`) names cause `misbooked` (S4.5 decision D29; no CSV named or found → none excused) |
| `bad_file_misbooked` | reported | all-time | the excused rows: untyped `bad-file` rows the item-8 CSV names `misbooked` (D29) |
| `blocked_inferred` | reported | all-time | `blocked` rows typed on basis `inferred` — the share the report states (D30) |
| `blocked_untyped` | = 0 | all-time | `blocked` rows with NULL `sub_status` |
| `budget_exceeded_silently` | = 0 | run | ladders (work × workstream) that launched a spent rung past a budget with no `budget-stop` row before it. The launch's MEASUREMENTS are the row's `detail.ladder` (`spent_before`, `elapsed_s`); the THRESHOLD is read twice — the budget FROZEN outside the ladder (manifest key `ladder_budget` = {`seconds`, `attempts`}, the run's own budget recorded at freeze; absent, the reference `policy.LadderBudget().seconds`) and the budget the row declares — past either counts (Codex X2: removing the budget object cannot remove the threshold). A spent rung row with NO `detail.ladder` escaped the ladder's accounting and counts |
| `transient_rows_unretried` | reported | run | `retriable` rows, not themselves a retry, that no retry names |
| `attempts_without_sha` | reported | run | rows that received bytes with no `served_sha256` |
| `attempts_without_terminal` | reported | run | spent rung rows with no `terminal_status_code` |
| `files_without_word_count` | reported | all-time | files whose current active version has no `word_count` |
| `hits_without_version` | reported | run | `ok`/`measured` rows with neither a `copy_kind` on the landed version nor `detail.version` |

Fires (`FIRES`, each also `qc/test_litkb_ledger.py::test_every_c1a_fire_fires`): `backoff_window_zero` →
`rehunt_route_spends`, `known_bad_lookup_disabled` → `known_bad_relands`, `typing_disabled_bad_file` →
`bad_file_untyped`, `typing_disabled_blocked` → `blocked_untyped`, `budget_removed` → `budget_exceeded_silently`.
Their inputs: E13's REAL recorded challenge page (`qc/fixtures/litkb_e13_challenge_b65a33b17354.html`, sha256
b65a33b1…, `binary` in `.gitattributes` by the existing `Scripts/qc/fixtures/*.html` rule) served by stub clients to
CONSTRUCTED admissions on a worker database.

### S4.5 builder-C1b: THE acceptance test's verdict (`litkb.acquire.accept`, LITKB_WORKPLAN.md "### S4.5" item 5)

`accept.accept(data, *, headers, url, terminal_url, doi, record_pages, metadata_fetched, qpdf_runner)` returns a
`Verdict`; `Verdict.summary()` is the JSON-safe record a caller stores (never the bytes). `accept.offer_to_bind`
puts it in the attempt detail as `detail.acceptance` (and, for a refusal, in the quarantine sidecar), so a counter
can re-read what the gate saw.

| field | meaning |
|---|---|
| `verdict` | `accept` · `refuse` |
| `sub_status` | NULL on accept; on refuse ONE `bad-file` sub-status: `html_response` · `too_small` · `missing_pdf_header` · `corrupt_pdf_header` · `early_eof_with_trailing_payload` · `stub_not_article` · `volume_not_article` · `cited_document_not_this_article` · `compressed_or_archived_payload` (`accept.SUB_STATUSES`, held equal to the S4.5 CONTRACTS list by `qc/test_litkb_accept.py`; the vocabulary's one home and its storage are builder-C1a's) |
| `reason` | one sentence; never quotes the bytes |
| `complete` | false when a step could not run: `qpdf-unavailable` (neither pikepdf nor the qpdf CLI), `qpdf-error:<why>`, `encrypted` (the checker cannot open it without a password), or `unreadable` text |
| `steps` | `[step, outcome]` in order: `unwrap` · `repair` · `magic` · `header` · `floor` · `mime` · `eof` · `qpdf` · `text` · `stub` · `volume` · `cited` · `identity` (a refusal ends the list at its step, outcome `fail`) |
| `facts.served_bytes`, `facts.served_sha256` | the bytes as served |
| `facts.bytes`, `facts.sha256` | the bytes that would land (unwrapped, header repaired) |
| `facts.evidence` | what the stub detector read: `headers` (`x-els-status`, `content-disposition`, `content-type` when served), `url`, `terminal_url` with its query and fragment dropped (a signed URL carries a session token) |
| `facts.unwrapped` | `gzip`, `tar:<member>`, `gzip+tar:<member>` when a wrapper was opened |
| `facts.repaired_offset` | bytes skipped before `%PDF-` (a BOM is 3) |
| `facts.landing` | on `html_response`: `citation_pdf_url` · `bepress` · `eprints` · `link_alternate_pdf` · `pdf_pointer` (booleans; Stage C's `landing_pages_booked_bad_file` reads `pdf_pointer`) |
| `facts.mime`, `facts.mime_source` | `libmagic` when python-magic imports, else `fallback-sniff` (this module's signature sniff) |
| `facts.qpdf` | `clean` (exit 0) · `recoverable` (3: warnings only, accepted) · `damaged` (2, refused `corrupt_pdf_header`) · `encrypted` · `qpdf-unavailable` · `qpdf-error:<why>`. The checker is libqpdf through pikepdf (`accept.libqpdf_check`, `Pdf.check_pdf_syntax`: an error RAISES -> `damaged`, warnings returned -> `recoverable`, nothing -> `clean`; S4.5 decision D14), the qpdf CLI only when pikepdf does not import |
| `facts.qpdf_checker` | `libqpdf <version> via pikepdf <version>` · `qpdf-cli <path>` · `none` · `injected runner` (a test's seam) |
| `facts.qpdf_unchecked` | present when pikepdf said it could not decode some streams (its UserWarning, e.g. no jbig2dec for JBIG2 images): those streams were not checked |
| `facts.pages`, `facts.chars`, `facts.words`, `facts.has_reference_section` | read by pdfium from the bytes in memory; `words` is the plan's `word_count` |
| `facts.image_pages` | how many pages are IMAGE pages (decision D13's rule, `litkb.extract.probe.image_pages`: zero native characters AND a raster image) |
| `facts.stub_signals` | any of `chars_no_refs` (<3,000 characters, no reference heading — NOT ASKED when `image_pages` > 0: a scan's words are pixels; auditor-C1b F1. The stated limit: ANY document with at least one image page is not judged by `chars_no_refs` — a short text stub followed by one image-only page (a cover, an advertisement, a full-page figure) included; auditor-C1b round 2 F1) · `x_els_status` (a non-OK `X-ELS-Status`) · `preview_url` ("preview" in a URL path or the Content-Disposition). The last two are `accept.evidence_signals`: read from the headers and URLs alone, no bytes |
| `facts.metadata` | `fetched` · `unfetched` (guard 18: the record-reading rules abstain) |
| `facts.volume` | `volume` · `article` · `unparsed` · `absent` · `no-page-count` (the record range read from an `a-b` digit form ONLY) |
| `facts.doi_position` | `first-pages` · `only-after` (refused) · `absent` · `no-doi` |
| `facts.page_range_identity` | `match` · `short` · `long` · `span-too-small` · `unparsed` · `absent` — recorded, never a refusal |
| `facts.rests_on_metadata` | true when the refusal read the record (volume, cited) |

**The quarantine name label** of a refused payload stays inside `litkb.quarantine.REASONS` (the 0030 CHECK):
`truncated-pdf` for `early_eof_with_trailing_payload`; `not-a-pdf` for the byte-shape sub-statuses; `bad-file` for
`stub_not_article` · `volume_not_article` · `cited_document_not_this_article`. The sub-status itself is in the
sidecar (`sub_status`, `acceptance`).

**`store.pdf_shape`** keeps its three answers (`pdf` · `not-a-pdf` · `truncated-pdf`) and now asks the acceptance
test's header and trailer rules only (`accept.shape`): a signature after leading bytes inside the first 1,024 is a
PDF, and `%%EOF` is looked for in the last 8,192 bytes (was 4,096).

### S4.5 builder-C1b: the quarantine sidecar (`<payload>.reason.json`)

Since S4.5 `Store.to_quarantine` writes the sidecar itself (item 8), so every quarantine has one; before it only
`Store.quarantine_new` did. Shapes on disk, all JSON objects:

| writer | fields |
|---|---|
| `run._reason` (route refusals, binding and attach refusals, the page probe, `--from-file`) | `status` · `label` · `shape` · `reason` · `route` · `source_url` · `sha256` · `bytes` · `work_key` · `at`, plus the caller's extras (`binding`, `attach`, `probe_error`, `moved_from`, `sub_status`, `acceptance`) |
| `hunt.land_download`, `hunt._hunt` (URL path) | `status` · `shape` · `reason` · `route` · `sha256` · `bytes` · `moved_from` · `at` (+ `label`, `probe_error` on the probe refusal) |
| `ops.reaper.reap` | `why` · `census_run` · `at` · `rule` · `sha256` · `bytes` · `mtime` · `age_hours` · `min_age_hours` · `was` · `recover` |
| `Store.to_quarantine` with no reason given | `status` · `label` · `sha256` · `stem` · `moved_from` · `at` · `reason_source` = `Store.to_quarantine (the caller passed no reason)` |
| `annas._quarantine` (legacy filing path) | `status` · `label` · `md5` · `stem` · `moved_from` · `route` = `annas.fetch_one` · `at` · `reason` |
| `quarantine.backfill_sidecars` (after the fact) | `backfilled` = true · `backfilled_at` · `reason_source` (`quarantine_payloads` · `quarantine_payloads+attempt` · `name (<source>)`) · `label` · `reason`, and from the row: `origin` · `sha256` · `bytes` · `work_id` · `attempt_id` · `recorded_at` · `note`; from its attempt: `status` · `route` · `attempt_at` · `attempt_note` · `attempt_source_url` · `attempt_probe_error` |

`quarantine.without_reason(root)` is the counter `quarantines_without_reason`: payloads (the `quarantine.payloads`
rule) with no sidecar. `qc/instruments/litkb_quarantine_sidecars.py` runs the backfill (dry run unless `--apply`).

### `phase4/qc/litkb_acq_probe_badfile.csv` (S4.5 item 8; writer `qc/instruments/litkb_acq_probe_badfile.py`, read-only)

One row per `bad-file` acquisition attempt, typed. It is builder-C1a's backfill input for
`acquisition_attempts.sub_status`.

| column | meaning |
|---|---|
| `attempt_id`, `work_key`, `route`, `identifier`, `year`, `at`, `workstream`, `http_codes`, `tried` | the attempt row (`tried` joined by ` \| `, 400 characters) |
| `detail_excerpt` | the detail's `note` · `via` · `probe_error` · `shape`, 300 characters |
| `bytes_recorded`, `sha256_recorded` | what the attempt's detail says it received |
| `bytes_kept` | `y` · `n` — this attempt's own bytes were found on disk |
| `bytes_kept_path`, `bytes_kept_length` | where, relative to the literature root, and how long |
| `match_method` | `sha256` · `sha256+qp.attempt` · `qp.attempt` · `was+mtime` · `sibling:<attempt id>` · `none` |
| `sub_status` | ONE CONTRACTS `bad-file` sub-status, on every row but a `misbooked` one (empty there: S4.5 decision D29) |
| `basis` | `bytes` (typed by `accept.accept` on the kept bytes) · `detail` (the detail records the body's kind) · `inferred` (codes and hosts, or a later sibling's bytes) |
| `cause` | closed: `landing_page` · `html_is_the_work` · `html_no_pointer` · `mirror_sweep_no_pdf` · `other` · `misbooked` — the last for a row whose ledger STATUS is wrong (S4.5 decision D29; `finalize`): its finer cause — `challenge_interstitial` · `blocked_not_bad_file` · `transport_error_string` · `mirror_miss_page` — leads `reason`, and `sub_status` and `basis` are empty (a vocabulary fix, no file, never typed) |
| `free_to_fix` | `y` · `n`; `html_is_the_work` is always `n` (decision D12: reported on its own line) |
| `fix_grade` | on `y`: `measured` · `estimated` · `inferred` |
| `fix`, `reason` | the converting rung, and why the row was typed so |
| `landing_pdf_pointer` | `y` · `n` on kept HTML; empty with no bytes |
| `work_has_file_now` | `y` · `n` |

### S4.5 builder-C1b counters (`qc/instruments/litkb_hardening_c1b.py`, loaded by `hardening`)

Gated: `quarantines_without_reason` (ALL TIME) · `stubs_bound` · `volumes_bound_as_article` (RUN-SCOPED: file
versions `active` created after the manifest's `frozen_at` in its `run_workstream_ids`, re-classified by the
acceptance test's own detectors from the bytes on disk, the landing attempt's `detail.acceptance.facts.evidence`
(joined by the file's sha256) and the record's page range as the gate reads it, `accept.record_pages_of`).
Reported: `page_ranges_unparsed` (the same files with at least 60 pages whose record range is not `a-b` digits,
empty included) · `stub_rule_abstained_image_pages` (the same files holding an image page with under 3,000
characters and no reference heading: what `chars_no_refs` did not judge — a scan, or any short document with one image page) · `bound_files_unreadable` (the same files the counters could not read from disk: they are still asked the evidence signals, `accept.evidence_signals`, but not the text or the bytes' page count). Manifest keys read: `frozen_at`,
`run_workstream_ids`, `literature_root` (a key the CONTRACTS list does not name; absent, the default literature
root). Fires: `sidecar` · `stub_constructed` · `stub_e20` · `volume` (control 0, known-bad 1) · `bom_repair`
(counter `bom_valid_pdfs_refused`, this fire's own, bound `=0` in the harness's grammar).

<!-- S4.5 builder C2A (Stage A + Stage B rungs): its SCHEMAS rows go between this marker and the next; the orchestrator removes the markers at landing -->

### Stage A and Stage B rungs (`pipeline/litkb/acquire/stage_a.py`, `stage_b.py`, `stage_b_repos.py`; S4.5 builder C2a)

Registered through C1a's rung registry when `litkb.acquire.run` is imported (S4.5 decision D19); the table
`stage_b.RUNG_TABLE` is their one home and its order IS the wave order. Every rung opts in to C1a's one scheduled
transient retry. `metadata_only` is a new `run.Rung` field (default false): such a rung yields identifiers, never
a file. `ask_condition` is a new `run.Rung` field (default ''): the condition under which a rung asks at all, in
words (`stage_b.ASK_CONDITIONS`, its one home) — set for `publisher-url`, `osf`, `datacite`, `zenodo`, `figshare`,
`ncbi-idconv`, `europepmc`, `arxiv` and `venue`; a rung with none asks every row that reaches it. It is what the
report's `not-asked:` line states (below; auditor-C2a round 2 F3).

| route | stage | needs | concurrent | metadata_only | what it asks (plan item / survey rung) |
|---|---|---|---|---|---|
| `eartharxiv` | A | doi | no | no | A7: the offline-harvested EarthArXiv map (below), then ONE request for the preprint PDF on a hit |
| `publisher-url` | A | doi | no | no | A4: the Atypon-family `/doi/pdf/{doi}` template for 10.1080 / 10.1145 / 10.1177 (`stage_a.PUBLISHER_TEMPLATES`; the other publishers' templates are Stage C's) |
| `opencitations` | B | doi | yes | yes | Wave 1: OpenCitations META `…/meta/v1/metadata/doi:{doi}` |
| `crossref-link` | B | doi | yes | no | B4: Crossref `works/{doi}` — `link[]` (pdf in content type OR path), `alternative-id`, ISBN, `issn-type`, `relation` |
| `openalex` | B | doi | yes | no | B3: OpenAlex `works/doi:{doi}` — `best_oa_location` + every `pdf_url`, `ids`, `pmh_id` |
| `doaj` | B | doi | yes | no | B8: DOAJ `api/search/articles/doi:{doi}` — `bibjson.link[type=fulltext]` |
| `openaire` | B | doi | yes | no | B9: OpenAIRE `search/publications?doi=` (XML) — PDF-naming instance URLs |
| `hal` | B | doi | yes | no | B14: HAL search `doiId_s` — `fileMain_s` |
| `osf` | B | doi | yes | no | B11: OSF APIv2 preprint → primary file → download (OSF prefixes only) |
| `datacite` | B | doi, arxiv | no | no | B6: DataCite `dois/{doi}` — only for 10.48550 / 10.5281 / 10.6084, a Crossref 404 in the run, or Stage A's arXiv candidate |
| `zenodo` | B | doi | no | no | B14: Zenodo record API for a `10.5281/zenodo.<n>` DOI |
| `figshare` | B | doi | no | no | B14: figshare article API for a `10.6084/m9.figshare.<n>` DOI |
| `ncbi-idconv` | B | doi | no | yes | Wave 2: NCBI ID Converter — only while pmid or pmcid is absent |
| `s2` | B | doi, arxiv | no | no | B5 + B1: Semantic Scholar `paper/DOI:{doi}?fields=externalIds,openAccessPdf,title,year` (LAST among the services) |
| `europepmc` | B | doi | no | no | B12 / B21: Europe PMC `resultType=core` — only once a PMCID appeared; then `?pdf=render` |
| `arxiv` | B | doi, arxiv | no | no | B1: every arXiv id the run holds (own, edition edge, or discovered in the run), at `arxiv.org/pdf/<id>` |
| `venue` | B | doi, arxiv | no | no | B13: ACL Anthology by id; OpenReview by title (title, first author and year agreeing) |

`core` (B7) is NOT BUILT (no rung registers it; `CORE_API_KEY` blank). One `policy.POLICY` line per route (appended
as a statement after the tuple, `legitimate` tier). A legitimate rung never asks a host a SHADOW line names and
never asks one URL twice in a ladder run (`work["asked_urls"]`: URL -> the route that asked it, named in the
skipping rung's note "already asked in this ladder run by <route>"). A TRANSIENT answer releases its URL, so the
rung's one scheduled retry asks it again rather than booking `no-oa-copy` over it (auditor-C2a round 2 F1);
transient is C1a's in-run retry rule (`backoff.classify`) applied to the answer as its own row — status 0, 408, 429
or a 5xx as `api-error`, a challenge page as `blocked`, which C1a's final rule never retries, so a challenge URL
stays asked. The arxiv.org PDF
C1a's `open_access` rung asked in the same run (the work's own arXiv id, or a `10.48550/arxiv.` DOI's: an ALLOWED
`open_access` decision in `RungContext.decisions`) is booked as asked by `open_access`, so the `arxiv` rung asks
only the other arXiv ids it holds (`stage_b.open_access_arxiv`; auditor-C2a round 2 F10).

The statuses a rung writes (`stage_b.fetch_candidates`, `stage_b.service_miss`): a PDF → `downloaded` (the ladder
lands it through the acceptance test); every request a transport failure → `api-error`, `retriable`; a challenge
page → `blocked` / `challenge_or_bot_check`; a page served where a file was expected → `bad-file` (typed by the
acceptance test: `html_response`) — `publisher-url` books it `blocked` / `html_or_reader` instead (survey A4-RG);
401/403 → `blocked` (typed `identity_required`); 404/410 on every candidate → `blocked` / `not_found`; a service that
answered and lists no free copy → `no-oa-copy`; a service with no record → `unresolved`; 0 / 429 / 5xx from a
service → `api-error`; a Wave-2 closure condition that fails → the rung asks nothing and the ladder writes
`skipped` with `no_identifier` or `policy_refused`, the condition in `detail.policy.closure`.

Two keys a rung's route dict adds, both copied onto the attempt's `detail` by the ladder (`run._record_result`):

| detail key | written | meaning |
|---|---|---|
| `harvest` | when the rung harvested | the result of writing the rung's identifier rows and relation edges through `litkb.admit.harvest.record` (`stage_b.write_harvest`): `{rows, relations, identifiers, edges}` counts and `record_identifiers`' own answer, or `{error}` — a harvest never fails an acquisition |
| `stage_b` | Stage B rungs | `gained` (the `scheme:value` pairs NEW to the run, the kill criterion's evidence), `closure_pending` (earlier rungs that key on a scheme discovered here — the one-pass cap, reported), and per rung `record_class` (A0), `crossref_class` / `work_class` (A2), `confirmed_candidate` (DataCite), `open_access_pdf` (S2) |
| `stage_a` | the FIRST attempt row the ladder writes for a work in one `run.acquire` call (a rung's answer, a skip, a `budget-stop`, or the `browser` manual-step row — whichever comes first; `stage_a.onto_first_row`), and only that row | `stage_a.prepare`'s summary: `rejected_ids` (A1: `{scheme, value, via, why}`, never coerced), `derived` / `written` (the Wave-0 rows and `record_identifiers`' answer), `candidates` (held for DataCite), `write_error` (a Wave-0 write that failed — the acquisition went on), `shortdoi`, `class` (A2), `native` (A3's server), `record_class` (A0 on the work's type). `run.acquire`'s answer carries the same dict under `stage_a` (auditor-C2a F1) |

`RungContext.work_class` (new, default ''): the A2 class `stage_a.prepare` computed; `RungContext.decide` passes
every PolicyDecision through `stage_a.routed`, which REFUSES a shadow line for a class in
`stage_a.SHADOW_REFUSED_CLASSES` (`preprint`, `book`, `html-only`). `stage_a.prepare` runs once in `run.acquire`
before any rung and leaves on the work dict: `type`, `ids` ([(scheme, value_norm, via)]: `own`, an edition relation,
or the route that discovered it in this run), `candidates` (Wave-0 CANDIDATE rows held for DataCite), `class`,
`native` (A3), `stage_a` (the summary: rejected ids, derived rows, candidates, class, record class — recorded on
the ladder's first attempt row, above). The Wave-0 rows it writes carry `asserted_by = 'deterministic'`. Wave 0
builds arXiv id <-> `10.48550` DOI and ISBN-10 -> 13; ISBN-13 -> ISBN-A is NOT built (it needs a hyphenated
ISBN, which A1's normaliser strips, and its DOI is a candidate nothing in this session confirms); the PMCID prefix
is A1's normaliser.

### The EarthArXiv map (phase4/qc/litkb_eartharxiv_map.csv; S4.5 builder C2a, A7)

Written by `qc/instruments/litkb_eartharxiv_map.py --live` (the orchestrator's pass: OAI-PMH `ListRecords`,
`oai_dc`, every resumption token, 1 s apart); read by the `eartharxiv` rung (`stage_a.eartharxiv_map`;
`config.EARTHARXIV_MAP`, `LITKB_EARTHARXIV_MAP` overrides). Not harvested by C2a (no grant): absent, the rung
answers `api-error` and asks nothing. Only a COMPLETE walk (the last page 200 with no resumption token, and no
OAI-PMH `<error>` on any page — the protocol serves its errors, e.g. an expired `badResumptionToken`, INSIDE an HTTP
200; `noRecordsMatch` on the FIRST page is the empty list, a complete walk of nothing; an unparseable 200 page stops
the walk: `litkb_eartharxiv_map.oai_error`, auditor-C2a round 2 F4) writes the map; a walk that stops early writes
nothing at the map path — the rows read go to `litkb_eartharxiv_map.partial.csv` beside it, which no rung reads —
and exits 1 (a map missing pages would book `no-oa-copy` for the works on them).

| column | meaning |
|---|---|
| `published_doi` | a non-EarthArXiv DOI the record names (dc:identifier / relation / source) — the published version's |
| `preprint_doi` | the record's own `10.31223/…` DOI |
| `pdf_url` | the record's http identifier containing `/download` or ending `.pdf` |
| `oai_identifier` | the OAI record identifier |
| `datestamp` | the OAI datestamp |
| `rights` | `dc:rights` |

### Stage A/B's recorded answers (`qc/fixtures/litkb_cassettes/stage_ab/index.jsonl`)

Builder A's cassette index format, recorded ONCE by `qc/instruments/litkb_stage_ab_record.py --live` under the
brief's grant (2026-09-23): row tags `c2a:<doi>`; the four FREE-PDF rows' and E13's Crossref / OpenAlex / Semantic
Scholar records and the OSF preprint 10.31235/osf.io/cxp4q's two APIv2 records — JSON only, inline, the contact
email masked. The one arXiv PDF request was recorded into an untracked scratch cassette (a PDF never enters the
repository).

### C2a's acceptance counters (`qc/instruments/litkb_hardening_c2a.py`, loaded by `hardening`)

| counter | gated | scope (S4.5 decision D1) | what it counts |
|---|---|---|---|
| `preprints_sent_to_shadow` | = 0 | run | attempts on a shadow route (`annas scihub bban`) that SPENT (status outside `backoff.NON_SPEND_STATUSES`) for a work typed `preprint` or typed `posted-content` by the crosswalk probe CSV (key or DOI); a manifest naming no crosswalk CSV is refused |
| `free_ceiling_measured_unconverted` | = 0 | all-time | the head probe CSV's FREE-PDF DOIs, plus the Wayback positive (10.1002/wics.1317, its census.gov row; manifest `wayback_positive_dois` overrides), whose work holds no HELD file: a `main_files` row with `status` `active` whose version `state` is neither `rejected` nor `withdrawn` (a quarantined, refused or withdrawn file is no conversion; auditor-C2a round 2 F6) |
| `rung_conversions_<route>` | reported | run | works with an `ok` or `measured` attempt on a Stage A/B route of this builder |
| `kill_gain_<scheme>` | reported | run | works that gained `arxiv` / `pii` / `dblp` / `isbn` / `md5` from a Stage B service (identifier version or asserted edge) |

The script form prints the LITKB_LADDER1 report's lines: `yield: <route>=<converted>/<asked>` for every built Stage
B rung (and every Stage A rung of this builder) — `asked` counts works with a row that is neither `skipped` nor
`budget-stop`, so a skip is never an ask; for a metadata-only rung ALSO `identifiers: <route>=<works
gaining>/<asked>` (S4.5 decision D19); for a rung with an `ask_condition` that asked NO row, reached at least one,
and was skipped on EVERY row it reached by that condition (a row the rung itself skipped with its condition in
`detail.policy.closure`, or the ladder's `no_identifier` skip with `detail.needs` — never a policy refusal, a
back-off window or a dead route: `condition_skips`), ALSO `not-asked: <route> <works reached> <condition>` in the
registry's own words (auditor-C2a round 2 F3: on live 0 works hold a zenodo or a figshare DOI or a PMCID, and a
`=0/0` yield line asked nobody; builder A's `stage_b_rungs_unmeasured` accepts the not-asked line for such a rung
under S4.5 decision D32's four conditions, "The not-asked line" below); `not-built: <route> <reason>` for each Stage B
route no rung registers;
`kill: <scheme>=<gained>/<asked> eligible=<n|n/a>` for each kill-criterion scheme; `kill-note: <text>` (md5 is
structurally 0 in this session: no Stage B service returns one, Anna's `identifiers_unified` is not written);
`kill-criterion: KEEP|KILL (…)`, the survey's S6 majority bar re-applied per scheme — the proposer's bar applied
mechanically, NOT a score; a non-proposer scores it. Fires (`FIRES`, each also
`qc/test_litkb_stage_ab.py::test_every_c2a_fire_fires`): `b1_disabled_kats` → `free_ceiling_measured_unconverted`,
`router_disabled_preprint` → `preprints_sent_to_shadow` (the shadow tier's switch pinned ON in both arms, so the fire
grades the router whatever `policy.SHADOW_TIER_ENABLED` says), `harvest_disabled_crosswalk_c2a` → builder B1's
`crosswalk_rows_without_identifier`.

<!-- S4.5 builder C2B (Stage C + Stage E + Sci-Hub part 1 rungs): its SCHEMAS rows go between this marker and the next; the orchestrator removes the markers at landing -->

### Stage C, route `landing` (`pipeline/litkb/acquire/landing.py`, S4.5 builder-C2b)

The rung `landing.fetch_landing(work, ctx)`, registered at import as a Stage C `run.Rung` (`needs=("doi", "arxiv")`:
a DOI, or an arXiv id so an arXiv-only work's leads are followed; not concurrent, `retry_transient=True`);
`litkb.acquire.run` imports the module (S4.5 decision D19), and a ladder runs
it when its `routes` name `landing`. The pre-fetch policy line is `policy.POLICY`'s `landing` / `*` / legitimate; a
candidate on any host a SHADOW line names is never asked (`landing.shadow_host`). A RELAYED design (CLAUDE.md §3.4c),
UNVALIDATED until the stage-c referee scores it.

One attempt row per call. What it can say:

| status | sub_status | when |
|---|---|---|
| `ok` / `bad-file` (the acceptance test's word) | per the loop | a candidate's bytes were downloaded; the loop's acceptance test and bind decide (`run._land`) |
| `measured` / `bad-file` | per the loop | the same in MEASURE mode (nothing landed) |
| `bad-file` | the acceptance test's word | the Range probe saw the PDF magic and the WHOLE answer was not a PDF and not a typed refusal (the answer kept as `rejected`); a whole answer the classifier types `challenge_or_bot_check` / `identity_required` / `not_found` is a refusal, never a bad file |
| `blocked` | `challenge_or_bot_check` · `identity_required` · `html_or_reader` · `not_found` | no candidate served a PDF; the strongest refusal any request met decides, in `landing.REFUSAL_ORDER` (challenge > identity > html_or_reader > not_found); the deciding answer is kept as `rejected`. With no typed refusal at all, `html_or_reader` is the default, and `detail.detail` says whether a landing page was read (every candidate then answered something the probe could not type: a 400, a 406, a non-PDF binary, a guard-9 refusal) or none could be |
| `not-in-archive` | `no_pdf_link` | a landing page WAS read (citation metadata) and neither it nor any rule offered a candidate; or the work was asked WITHOUT a DOI (an arXiv-only work) and no earlier rung of the run was served a page — nothing to follow, no request made |
| `api-error` | — | a transient answer (0, 408, 429, 5xx) stopped the rung; `retriable` true; the terminal response (its `Retry-After` included) is that answer, so the ladder's one scheduled retry honours it (decision D15) |
| `skipped` | the ladder's reasons | builder-C1a's skip rows (`policy_refused`, `dead_in_run`, `backoff_window`, `no_identifier`) |

`detail.landing` (the rung's evidence; `run.DETAIL_KEYS` carries it): `landing_page` (the page READ as the article's
landing page — never an interstitial, C6-RG; else null), `resolved_url` (the DOI walk's final URL), `doi_page`
{url, status, verdict, why}, `leads` [{route, url, verdict, why}], `candidates` [{url, source
`<rule>.<candidate>[:<pointer source>][+rewrite:<id>]`, rule, score, verdict, why, status, requests}], `rules`
[{id, lastUpdated, age_days}] (guard 25: the freshness PRIOR of every rule selected; it orders nothing yet),
`terminal_headers` (decision D22: `content-type`, `content-length`, `x-els-status`, `content-disposition` of the
deciding response), `source` (a download's candidate source) or `stopped` (a transient stop). A signed URL (an
`X-Amz-*` / `Signature` / `Expires` / `Policy` / `Key-Pair-Id` / `token` parameter) is kept without its query
(`landing.evidence_url`). `detail.detail` is a one-line note.

Requests (all through the injected `netutil.Client`, so a cassette records and replays them): the DOI page
`https://doi.org/<doi>` (`landing.doi_url`) with `Accept: text/html`, redirects walked by hand (`landing.walk`:
at most 10 hops, a meta refresh followed like a redirect, a redirect INTO a bot check never followed, no hop to a
private / loopback / link-local address — guard 9); a candidate's 4 KB probe with `Range: bytes=0-4095`, `Accept:
application/pdf,text/html;q=0.8,*/*;q=0.5` (survey §2.0) and the guard-24 `Referer` (`landing.referer_for`: the
landing page if same-origin, else its origin, never a search engine); the whole GET only after a probe that saw the
PDF magic, or answered 416 (the server refuses ranges) — walked hop by hop like the probe (`landing.walk`, no meta
refresh), so guard 9 and the bot-check rule hold on its redirects and the ledger names the URL that served the file;
a server that ignored the Range, answering 200 with more than 4 KB, is not asked twice. At most 6
candidates per call (`landing.MAX_CANDIDATES`). A C3 rewrite (`landing.rewrites_of`) only after its original failed.

`run.RungContext.leads` (seam builder-C2b): every non-PDF page a rung of the SAME ladder run was served, in order, as
{route, url, status, headers, body} — collected by `run._record_result` before the rejected-hash lookup. `run.work_record`
also returns `pii` (a `pii` identifier, from builder B1's harvest), `venue`, `volume`, `issue`, `pages`.

### The landing rule table (`pipeline/litkb/acquire/landing_rules.json`; interpreter `pipeline/litkb/acquire/landing.py`)

A DATA file (`landing.load_rules` refuses a malformed one whole — `landing.check_rules`): the per-publisher rules of
Reports/LITKB_PDF_SOURCES_SURVEY_2026-09-22.md §2 for this corpus's publishers, ported from the Zotero translator
corpus as that survey read it. Top level: `kind` (`litkb-landing-rules`), `version`, `status`, `global`, `rules`
(ordered), `default` (the generic citation_pdf_url rung, the C8-RG fall-through).

| `global` field | meaning |
|---|---|
| `id_patterns` | {pii, arnumber, mdpi_path: a regex with a group `v`}: the ids a `same_id` check and a `url:` variable read out of a URL |
| `login_wall_url_markers` | lower-cased substrings of a redirect chain's URLs that make an answer `identity_required` |
| `challenge_url_markers` | substrings of a chain's URLs (a Location included) that make it `challenge_or_bot_check`; the walk never follows such a redirect |
| `cookie_wall_url_markers` | cookie-wall URLs (C6), typed `challenge_or_bot_check` |
| `paywall_body_markers` | lower-cased markers read in an HTML answer to a PDF candidate (never on a landing page), typed `identity_required` |
| `waf_statuses` | statuses that ARE a challenge (202, AWS WAF) |
| `supplementary_tokens` / `demote_tokens` | C9's -100 / -40 score tokens |
| `rewrites` | C3's rewrites: [{id, match, replace, version?}] |
| `*_source` | where each list comes from |

| rule field | meaning |
|---|---|
| `id`, `publisher` | the rule's name |
| `detect` | {`doi_prefixes`, `hosts`, `hosts_suffix`}: a DOI prefix, or the host of any URL the call saw, selects the rule (prefix matches first) |
| `vars` | [{`name`, `from` [`meta:<key>` of a page read · `work:<field>` of the work record · `url:<id>` · `doi:<regex with v>`], `transform` `despace_lower`/`lower`/`upper`/`none`}]: template fields; every distinct value makes a candidate |
| `candidates` | ordered [{`name`, `technique`, `on` (`urls`: matched against every URL seen; `none`), `match`, `template` / `replace` / `then`, `bonus` (C9), `version` (guard 23), `why` (its source)}]; `technique` is `pointers` (the C2 extraction on every page read), `template` (`str.format` of named groups + vars + `doi` / `doi_suffix`), `rewrite` (`re.sub` on a matched URL), `page_regex` (a group `url` in a page read), `two_hop` (an HTML shell fetched as a page and read again with `then`, C12) |
| `not_built` | every survey §2.1 rule of this publisher's row (its PDF-URL rules in order, and the named variants: `?download=true`, `{doi_quoted}`, a keyed API, a browser step) that was NOT built, each with why; `qc/test_litkb_landing.py` pins the OUP, MDPI, Wiley and IEEE entries |
| `identity` | [{`check` `doi_in_url` · `same_id` (`id`) · `require_substring` (`value`)}] (C10), applied to page-discovered candidates — the default rule's included, which must pass every selected rule's check |
| `exclude`, `exclude_hosts` | tokens / hosts a page-discovered candidate may not carry (the §2.1 supplementary and cross-family lists) |
| `challenge_signature` | {`markers` (searched in the WHOLE body of an answer from the rule's hosts), `note`}, or null with `challenge_note` saying none was characterised (Cambridge) |
| `source` | {`translator`, `lastUpdated` (guard 25; null only with a `note`), `zotero` (the corpus commit the survey read), `survey`, `note`} |
| `example` | {`doi`, `work_key`, `fixture` (a recorded page dir, or null with `why` naming NO REAL FIXTURE), `why`, `expect` {`page`, `page_cause`, `candidates` [urls], `work`}}: the recorded page must type as `page` / `page_cause` and make exactly `candidates` (`qc/test_litkb_landing.py`) |

### The recorded landing page (`qc/fixtures/litkb_landing_pages/<rule id>/`; writer `qc/instruments/litkb_landing_record.py`)

`recording.json` + `hop<N>.body`, `binary` in the repo-root .gitattributes. One landing page per rule (its
example DOI's `https://doi.org/<doi>` walked by `landing.walk` through a real `netutil.Client`), recorded 2026-09-23
under builder-C2b's grant; `--rescrub` re-applies the scrub with no request. `recording.json`: `kind`
(`litkb-landing-recording`), `version`, `rule`, `doi`, `work_key`, `recorded_at`, `client` {class, user_agent},
`grant`, `scrub` (what was masked and how), `walk` {accept, max_hops, meta_refresh}, `hops` [{`n`, `request` {url,
accept, follow, headers}, `response` {status, headers (Set-Cookie never written), body_file, length, sha256 (of the
bytes as written), scrubbed}}], `final` {url, status, verdict, why} — the verdict the classifier gave WHEN RECORDED
(history: the current pin is the rule's `example.expect`). Scrub: `cassette.scrub_bytes` / `scrub_url` (registered
secrets, the `key=`-family parameters), then the client-address mask (`<CLIENT-IP>`, `<CLIENT-IP-B64>`) for a public
IPv4 two hosts echo or one inside a base64 token, then the page-address mask (`<PAGE-IP>`): a public IPv4 / IPv6 a
page names under an address key (`remoteAddress`, `remoteAddr`, `clientIp`, `ipAddress`, `x-forwarded-for`,
`x-real-ip`), whoever's it is — Cambridge Core's page state names other visitors' addresses (auditor-C2b F9).
`hardening_c2b.load_recording` re-checks every body's sha256.
Beside it, REAL, copied read-only from the live quarantine: `qc/fixtures/litkb_mdpi_pdf_akamai_a3b93f589df6.html`
(+ `.provenance.json`), MDPI's 413-byte Akamai answer for Chen_2023's `/pdf` URL.

### S4.5 builder-C2b counters (`qc/instruments/litkb_hardening_c2b.py`, loaded by `hardening`)

| counter | gated | scope | what it counts |
|---|---|---|---|
| `landing_pages_booked_bad_file` | = 0 | run | non-`landing` `bad-file/html_response` rows served by a rung the ladder runs BEFORE Stage C (Stage A or B, or a route no stage names) whose page carried a PDF pointer, with no `landing` row at or after them FOR THE SAME WORK in the run (a `landing` row BEFORE the page does not follow it; a `policy_refused` / `no_identifier` skip does not count as following; a `dead_in_run` / `backoff_window` one does). A row of a route staged AFTER Stage C (`policy.STAGE_OF` E or shadow: the ladder never asks Stage C after them) is `landing_pages_after_stage_c`'s, never gated (auditor-C2b round 2 F1; option (a)). The pointer fact (`accept.landing_signals`) is read, in order, from the row's own `detail.acceptance.facts.landing.pdf_pointer`; from ANY attempt row with the same `served_sha256` that carries it (a page served again after its bytes were refused skips the acceptance typing — the rejected-hash lookup); from the bytes themselves (`detail.known_bad.rel_path`, else `detail.quarantined`, under the manifest's `literature_root` — default `store.LITERATURE_ROOT` — and only when their sha256 is the row's `served_sha256`). A row that was served bytes and whose fact none of the three yields COUNTS (the gate fails closed; `DETAILS` names it unreadable); a row served no bytes (typed from the terminal response, decision D15) had no page and does not |
| `bronze_landing_unconverted` | reported | run | the Elsevier bronze landing rows (read from `phase4/qc/litkb_acq_probe_no_oa_copy.csv`, `unpaywall_url` a doi.org URL: four DOIs) with no `landing` row `ok` or `measured` in the run — from ATTEMPT rows, never file state |
| `manual_step_rows` | reported | run | `manual-step` rows the run wrote (builder-C2b's definition; the plan names the counter without one) |
| `landing_pages_after_stage_c` | reported | run | beyond the plan's (b) names (`REPORTED_BEYOND_PLAN`): the rows the gate leaves out — unfollowed `bad-file/html_response` rows of a route staged after Stage C whose page carried a PDF pointer (the same pointer-fact reading and fail-closed rule as the gate). `DETAILS` gives each row's `asked_by_stage_c`: `yes` (a `landing` row of the same work in the run asked a pointer the page carries: `landing.pointers` over the kept bytes against `detail.landing.candidates[].url`, compared by `landing._dedupe_key`), `no`, or `unknown` (the bytes are not kept — MEASURE mode keeps none — or no pointer URL could be read) |

`DETAILS` lists the rows behind the gated counter (each with where its pointer fact was read), the rows behind
`landing_pages_after_stage_c` (each with `asked_by_stage_c`), and every bronze row's landing outcome. Fires (`FIRES`, each also a
`qc/test_litkb_landing.py` test): `stage_c_disabled` → `landing_pages_booked_bad_file`; and three with their own
counter and bound `=0`: `mdpi_cdn_rule_disabled` → `mdpi_landings_unconverted` (works asked under the MDPI rule that
Stage C did not convert), `paywalled_probe_disabled` → `landing_html_booked_bad_file` (`landing` rows that spent an
HTML answer as `bad-file/html_response`), `e13_challenge_rule_disabled` → `landing_challenges_mistyped` (`landing`
blocked rows whose KEPT body carries a challenge by `ledger.challenge_cause` / `netutil.Client.is_challenge` but whose
sub-status is not `challenge_or_bot_check`; reads the payload under `literature_root`). Inputs: the recorded pages,
E13's recorded page, MDPI's kept Akamai page, and CONSTRUCTED answers (named in each fire's docstring) where the grant
recorded no PDF endpoint.

<!-- end of S4.5 builder sections -->

<!-- S4.5 builder C2C (Stage E rungs: Wayback E1, Internet Archive E3, Common Crawl E5): its SCHEMAS rows go between this marker and the next; this marker pair was SEEDED by builder-C2c because the base carries no C2C anchor (auditor-C2c F7); the orchestrator removes the markers at landing -->

### Stage E — recovery rungs `wayback` · `ia` · `commoncrawl` (S4.5 builder-C2c, LITKB_WORKPLAN.md "### S4.5" item 6)

Modules: `pipeline/litkb/acquire/wayback.py` (E1), `pipeline/litkb/acquire/ia.py` (E3),
`pipeline/litkb/acquire/commoncrawl.py` (E5), and their shared half `pipeline/litkb/acquire/recovery.py`. Each
registers ONE rung through builder C1a's registry (`recovery.register`, which keeps the Stage E order E1, E3, E5
whatever module is imported first); `litkb.acquire.run` imports all three (S4.5 decision D19). Sequential within
the stage (not concurrent), `needs` = (`doi`, `arxiv`) — the identifier the row is keyed by — and one scheduled
in-run retry of a transient answer (`retry_transient`). A route still runs only when the caller's `routes` names it.
Policy lines (`policy.POLICY`, all `legitimate`): `wayback` archive.org + web.archive.org; `ia` archive.org;
`commoncrawl` index.commoncrawl.org + data.commoncrawl.org. No `*` line: any other host is refused.

**Their input: the dead URLs** (`RungContext.recovery_urls`, a list of {`url`, `route`, `status`, `origin`}, in
memory only). Filled by the LADDER, never by a rung: `recovery.ledger_urls` before the first rung (only when a
Stage E rung is in the ladder) — every `terminal_url`, `detail.source_url`, `detail.rejected_url` and http(s) URL
inside `detail.tried` of this work's earlier attempts on a legitimate-tier route or `hunt-url`, whose status is not
a success or a skip (`recovery.LIVE_STATUSES`); then `recovery.urls_of` on every answer this ladder run records
(the route dict's `rejected_url`, `source_url`, `terminal.url` and URLs in `tried`). `recovery.candidates` keeps
the distinct ELIGIBLE ones, first met first, at most `recovery.MAX_URLS` (5, builder's choice). Never eligible: a
shadow route's URL or a shadow POLICY host; a URL carrying a registered secret, a `litkb.cassette.SCRUB_PARAMS`
parameter or the `<KEY>` mask; a SIGNED URL (a query parameter in `recovery.SIGNED_URL_PARAMS`: `X-Amz-Signature`,
`Signature` / `Policy` / `Key-Pair-Id`, `sig`, their vendors' companions — builder's reading, not checked in source);
archive.org / commoncrawl.org; doi.org; a host starting `api.`; non-http(s).

**The rows each rung writes** (0033 vocabulary; no new route, status or sub-status):

| route | status / sub_status | when |
|---|---|---|
| any Stage E | `skipped` / `no_identifier` | no eligible dead URL (E1, E5) or no DOI and no title (E3); `detail.detail` says which (a Stage E rung's identifier IS a dead document URL) |
| any Stage E | `skipped` / `policy_refused` | the pre-fetch policy refused every host the rung would ask |
| any Stage E | `api-error`, `retriable` true | a transient answer (0, 408, 429, 5xx) at any step: the rung STOPS there; the terminal carries the response headers, so the ladder's scheduled retry honours `Retry-After` |
| `wayback` | `downloaded` → `ok` / `measured` | a capture fetched with a raw-bytes modifier (`id_`, then `if_`) that starts `%PDF` |
| `wayback` | `bad-file` (typed by THE acceptance test, e.g. `html_response`) | only 200 captures that are not a PDF; the first is kept (`rejected`) |
| `wayback` | `blocked` / `not_found`, `retriable` false | a PROVEN absence of every candidate: the availability API answered 200 in its own shape, the CDX index answered 200 with no capture row (`[]`, a header row alone, or an empty body), and the closest capture was no usable 200 snapshot (the plan's words for E1's negative; `not_found` is a `blocked` sub-status). It proves NO USABLE SNAPSHOT, not "never archived": CDX is filtered to `statuscode:200` + `mimetype:application/pdf`, so a URL archived only as a redirect or a page ends here too (auditor-C2c round 3 F5) |
| `wayback` | `api-error`, `retriable` false | the absence is NOT proven for some candidate: a 401/403/404 or a body that is not the API's answer from the availability API or CDX, an indexed capture the archive would not serve, or a host the policy refused for that URL. `detail.detail` names each URL's missing proof. Never `not_found`: a refusal is not "never archived" |
| `ia` | `downloaded` → `ok` / `measured` | an identified, open item's PDF (the uploaded original first; `private` files skipped) |
| `ia` | `blocked` / `identity_required` | an identified item is lending-restricted (`access-restricted-item`, or collection `inlibrary` / `printdisabled` / `lendinglibrary`) — never downloaded |
| `ia` | `blocked` / the ledger's typing of the refusing response | an identified, open item's download answered 401 or 403: typed by `litkb.acquire.ledger.type_blocked` on that ONE response — a 401 is `identity_required`; a 403 is `challenge_or_bot_check` when it carries a challenge signature (or no body), `identity_required` for a plain page. The terminal is the refusing response |
| `ia` | `not-in-archive` / `no_pdf_link` | identified items, none with a PDF it would serve: no PDF file listed, or the listed PDF answered 404/410 |
| `ia` | `not-in-archive` / `not_in_corpus` | no identified item (a dark item, `is_dark`, is never opened further) |
| `ia` | `api-error`, `retriable` false | the item search answered a non-transient non-200 |
| `commoncrawl` | `downloaded` → `ok` / `measured` | a 200 capture with a PDF MIME whose WARC record (a 206 of exactly the indexed length, one gzip member, one `response` record, the payload de-chunked / decoded) is a PDF |
| `commoncrawl` | `bad-file` | the crawled payload is not a PDF, or the crawler truncated it (`WARC-Truncated`): kept, typed by the acceptance test. A truncated payload is kept AS SERVED and never decoded (a cut gzip or chunked stream cannot be) |
| `commoncrawl` | `api-error`, `retriable` = (the answer was a short 206) | the range was not honoured (200) or came back short, the record did not decode, or its HTTP payload did not decode under its own `Transfer-Encoding` / `Content-Encoding` (`deflate` is read as zlib, then as raw DEFLATE) |
| `commoncrawl` | `not-in-archive` / `not_in_corpus` | no PDF capture in the newest `commoncrawl.INDEXES_ASKED` crawls (3, builder's choice) |

`detail.detail` on a spent Stage E row names the URLs asked (`asked about: …`) and how many were not eligible;
`detail.tried` holds one token per request (`availability:200`, `cdx:503`, `capture <ts>id_:200`, `search:200`,
`metadata <item>:200`, `download <item>:200`, `collinfo:200`, `index <crawl>:404`, `warc <ts>:206`, or
`<step>=policy-refused`); `detail.policy` the per-host PolicyDecisions. The seam in `run.acquire`'s `settle` also
copies a self-skipping rung's own `detail` onto its `skipped` row.

**The recorded fixture** — the cassette `qc/fixtures/litkb_cassettes/stage_e/index.jsonl` (builder A's format,
recorded ONCE 2026-09-23 by `qc/instruments/litkb_stage_e_record.py` (its `--live` flag), 10 requests, the grant in
`qc/fixtures/litkb_cassettes/stage_e/provenance.json`) and its one stored body, the census.gov PDF (a U.S. federal
government work), under that directory's `bodies`. Rows (the `begin_row` tags): `stage-e:wayback:10.1002/wics.1317`
(availability 20210322000835, id_ capture = 207,538-byte PDF: Winkler's U.S. Bureau of the Census paper "Matching
and Record Linkage", 38 pages — ANOTHER WORK than 10.1002/wics.1317, the 2014 overview), `stage-e:wayback-no-raw-modifier:…`
(the bare capture served the SAME bytes), `stage-e:wayback-if:…` (the same bytes), `stage-e:wayback:10.5067/doc/ceoswgcv/lpv/lc.001`
(the plan's "never archived" NEGATIVE is archived: capture 20251206182454, a 7,689,961-byte PDF, the 188-page protocol
itself, whose body is NOT kept — its replay fails closed), `stage-e:ia:10.1002/wics.1317` (0 hits),
`stage-e:commoncrawl:10.1002/wics.1317` (128 crawls; CC-MAIN-2026-39: 404 no capture).

**The plan's two E1 rows, re-graded against that recording** (`litkb_hardening_c2c.WAYBACK_ROWS`, the one home; the
rule of S4.5 decision D10; the orchestrator confirms or overrides it there):

| DOI | the plan's role | grade | why |
|---|---|---|---|
| 10.1002/wics.1317 (census.gov copy) | positive | `wrong-work` | the capture is another work (38 pages, no citation after 1993) than the 2014 overview live holds (13 pages): an E1 hit on it is a FALSE conversion |
| 10.5067/doc/ceoswgcv/lpv/lc.001 (IIASA copy) | negative | `positive` | archived 2025-12-06, and the capture is the work (its citation line carries the DOI); live holds no file |

E1 therefore has NO real negative row until a never-archived real URL is named under a new grant.

### Builder C2c's counters (`qc/instruments/litkb_hardening_c2c.py`, loaded by `hardening`)

| counter | gated | scope (S4.5 decision D1) | what it counts |
|---|---|---|---|
| `rung_conversions_wayback` · `_ia` · `_commoncrawl` | reported | run | works with an attempt on that route that hit (`ok` or `measured`) |
| `rung_asked_wayback` · `_ia` · `_commoncrawl` | reported | run | works that route was asked for (a spent attempt: not a skip or a stop) |
| `wayback_rows_unconverted` | reported (its value is the WAYBACK HALF of C2a's gated `free_ceiling_measured_unconverted`) | all-time | Wayback POSITIVE rows (manifest `wayback_positive_dois`, else the `positive` grades: 10.5067/doc/ceoswgcv/lpv/lc.001) with no `wayback` attempt `ok`/`measured` — a work holding a file from another route still counts until E1 converts or measures it. An EMPTY list reads 1 (no positive row is never a pass) |
| `wayback_negatives_mistyped` | reported | all-time | Wayback NEGATIVE rows (manifest `wayback_negative_dois`, else the `negative` grades: none) whose latest spent `wayback` attempt is not `blocked/not_found` (none counts). An EMPTY list reads 1: E1 has no real never-archived row |
| `wayback_wrong_work_counted` | reported | all-time | WRONG-WORK rows (manifest `wayback_wrong_work_dois`, else the `wrong-work` grades: 10.1002/wics.1317) holding a `wayback` attempt `ok`/`measured` — a false conversion E1 made (MEASURE mode judges bytes, not identity; the bind checks title and first author only), which `rung_conversions_wayback` counts too |

Manifest keys read beyond the CONTRACTS list: `wayback_positive_dois`, `wayback_negative_dois`,
`wayback_wrong_work_dois` (all optional; an explicit empty list is honoured, and reads as above).
Fires (`FIRES`, each also `qc/test_litkb_stage_e.py::test_every_c2c_fire_holds_its_bound_on_control_and_breaks_it_on_the_known_bad`):
`stage_e_wayback_rung_disabled` → `wayback_rows_unconverted` (REAL recorded answers; the registry without E1);
`stage_e_raw_modifier_removed_constructed` → `wayback_rows_unconverted` (a CONSTRUCTED wrapper page at the bare
capture URL — the real one served the PDF); `stage_e_not_found_typing_removed_constructed` →
`wayback_negatives_mistyped` (a CONSTRUCTED never-archived URL). Bound `=0` each, carried on the fire.

<!-- end of S4.5 builder C2C section -->

<!-- S4.5 integrator-w2 (the orchestrator's rulings D15-D22 and the auditor notes on the final merged candidate): its SCHEMAS rows go between this marker and the next; the orchestrator removes the markers at landing -->

### The ladder's own record of what it was served (S4.5 decision D22; `pipeline/litkb/acquire/run.py`, integrator-w2)

| field | where | what it holds |
|---|---|---|
| `detail.served_headers` | `litkb.acquisition_attempts`, EVERY row whose rung was served bytes (a landing, a refusal, a MEASURE hit, a known-bad match) | `{lower-case name: value}` of the four stub-relevant response headers the terminal response carried — `content-type`, `content-length`, `x-els-status`, `content-disposition` (`litkb.acquire.accept.STUB_HEADERS`, their one home); absent headers left out. Written by `run._record_result` itself, independent of the acceptance test, so `stubs_bound` re-reads a landing the test did not judge |

`litkb.acquire.accept.evidence_of` keeps the same four headers in `detail.acceptance.facts.evidence.headers`, and both
URLs there are reduced to scheme, host, port and path (no query, fragment, userinfo or `;param` — auditor-C1b round 3
F4). C1b's `stubs_bound` / `volumes_bound_as_article` read `served_headers` and the row's `terminal_url` beside that
evidence (union of the two header sets).

### MEASURE mode's tiers (S4.5 decision D18; `litkb.acquire.policy.measure_decision`)

In MEASURE mode (`run.measure`, the run driver's hook for a work that already holds a file) every PolicyDecision
passes through `policy.measure_decision`: an allowed decision whose line is not `legitimate` becomes a refusal whose
reason is `policy.MEASURE_REFUSAL` — the rung is a `skipped` / `policy_refused` row naming D18, never asked. So MEASURE
mode never spends an archive download (`annas`) and never asks the shadow stage; it asks Stages A, B, C and E.

### Which routes the ladder asks by default (`litkb.acquire.run.ladder_routes`; S4.5 decision D19 seam)

| caller | routes |
|---|---|
| `litkb.hunt` (`hunt._default_acquire`) | `run.ladder_routes()`: EVERY registered rung, stage order then registry order (the shadow tier among them runs only as its one switch allows) |
| `run.measure` (the run driver's MEASURE hook) | `run.ladder_routes()` unless the caller names routes; the shadow tier refused by D18 |
| the replay (`qc/instruments/litkb_edge_run.py`, a `ladder` row with no `routes`) | `run.ladder_routes()` — what the live hunt asked |
| `litkb acquire` (`--routes`, default `open_access,annas,scihub`) and the S4 readability grade | `run.ROUTES`, today's three, unchanged |

### The acceptance test on every binding path (S4.5 decision D17)

| path | what runs | what a refusal does |
|---|---|---|
| the ladder (`run._land`) | `accept.offer_to_bind` (integrator-w1) | `bad-file` + the verdict's sub-status; bytes kept with the verdict in the sidecar |
| the hunt URL path (`hunt.land_download`) | `accept.accept(data, headers={Content-Type}, url=ref, metadata_fetched=False)` — no registry record exists yet, so volume and cited abstain (guard 18) | the bytes kept in _quarantine/ under the verdict's label (`accept.quarantine_label`: `not-a-pdf` / `truncated-pdf` / `bad-file`, the `quarantine_payloads` reason), sidecar keys `sub_status` + `acceptance`; the hunt refuses `hunt.ACCEPTANCE_REFUSALS[label]`: `not-a-pdf`, `truncated-pdf`, or `admission-refused` for a PDF that is not an article (a stub) — the closed REASONS unchanged |
| `--from-file` (`run.acquire(from_file=...)`) | `accept.accept(data, doi=, record_pages=)`; the verdict summary is written on the file version (`file_versions.binding.acceptance`) and on the `browser` attempt (`detail.acceptance`) | ONLY a hard byte failure refuses (`accept.hard_byte_failure`: a refusal at one of `accept.HARD_STEPS` = unwrap, magic, header, mime, eof, qpdf); a floor, stub, volume or cited verdict is recorded on the PROPOSAL for the second-session approver |

`front.pending_file_proposals` (the approver's listing, `litkb approve-files --pending --dry-run`) carries
`acceptance_verdict`, `acceptance_sub_status`, `acceptance_reason` read from `file_versions.binding.acceptance`
(NULL for a proposal no acceptance test judged).

### D15's remaining typing (integrator-w2)

- `ledger.no_byte_bad_file_sub`: a no-byte `bad-file` whose terminal response DECLARED a Content-Length above 0 but
  under `accept.MIN_PDF_BYTES` is `too_small`; at or above the floor it stays untyped and counted (a server declared a
  PDF's worth of bytes no rung handed back).
- `annas.fetch_for_litkb`: when EVERY partner-host request failed in transport (status 0) the answer carries those
  codes in `http_codes`, so the ladder books it `api-error`, retriable; otherwise `http_codes` stays empty as before
  (a partner's 403 is not read as the archive refusing). `annas.download_pdf` never keeps a status-0 body (the client's
  own transport-error text) as `rejected` bytes.
- `open_access.fetch_open_access`: a no-byte answer's `terminal` is the last location a SERVER answered (a status-0
  transport failure is not a response), else the last asked; `http_codes` and `retriable` are unchanged (auditor-C1a
  round 3 F2).

### The Stage B measure lines (S4.5 decision D19; `qc/instruments/litkb_hardening_a.py`)

`identifiers: <route>=<works gaining>/<asked>` (`IDENTIFIERS_LINE`: whole line, integers, gaining <= asked, asked >= 1)
measures a built Stage B rung the registry marks metadata-only (the rung's `metadata_only` attribute; a rung without it
is a PDF rung) — beside a `yield:` line, either answers for it. For a PDF-yielding rung an `identifiers:` line answers
nothing.

`not-asked: <route> <works reached> <condition>` (`NOT_ASKED_LINE`: whole line, `<works reached>` an integer >= 1, the
condition the registry's own words) measures a built Stage B rung the registry gives an `ask_condition` (builder C2a's
`run.Rung` field; `stage_b.ASK_CONDITIONS`) that asked NO row because that condition skipped every row it reached —
the closure rule's Wave-2 rungs (on live 0 works hold a zenodo or a figshare DOI or a PMCID, so their yield line reads
`=0/0`, which is not a measurement). For an unconditional rung, a line that reached nobody, or a condition that is not
the registry's, it answers nothing (auditor-C2a round 2 F3). S4.5 decision D32 adds two more conditions — a rung
with a yield line that asked rows AND a not-asked line is unmeasured, and the report states such a rung's yield as
UNDETERMINED — see "The not-asked line (S4.5 decision D32)" below.

### C1b's ladder-level stub fires (S4.5 decisions D21, D22; `qc/instruments/litkb_hardening_c1b.py`)

| fire | counter | known-bad |
|---|---|---|
| `stub_ladder` | `stubs_bound` | the CONSTRUCTED TDM stub served by a CONSTRUCTED rung through `run.acquire`, the landing's acceptance test removed in-process -> 1 (control 0) |
| `stub_ladder_header_only` | `stubs_bound` | a whole article announced as a stub ONLY by `X-ELS-Status`, same arm: counted only through `detail.served_headers` (D22) -> 1 (control 0) |

<!-- end of S4.5 integrator-w2 section -->

<!-- S4.5 integrator-w3 (the orchestrator's rulings D23-D28 on the w3 candidate): its SCHEMAS rows go between this marker and the next; the orchestrator removes the markers at landing -->

### THE challenge detector (S4.5 decision D24; `pipeline/litkb/netutil.py`, integrator-w3)

`netutil.Client.challenge_cause(status, url, body, headers=None)` -> the challenge family, or `''`; `is_challenge` is
its yes / no. ONE detector, one marker list: `netutil.CHALLENGE_MARKERS`, `CHALLENGE_HEADERS`, `MARKER_WINDOW` (64 KiB)
moved here from `litkb.acquire.ledger`, whose names now alias the same objects. Every caller asks it: open access (each
location, headers included), the ledger's `type_blocked` / `challenge_cause` (status unknown), the landing rung
(`landing._challenge`, before its rule table's own rows), the acceptance test, and the ladder (below).

| evidence, strongest first | answer |
|---|---|
| a header signature (`cf-mitigated: challenge`, `x-datadome: protected`), any status | `header:<name>` |
| a 403 on a `check=1` URL | `check=1` |
| PDF magic at the head of the body | `''` — a PDF is never a challenge |
| status 403 / 503 (`REFUSAL_STATUSES`): a marker in the first 64 KiB, else `CHALLENGE_RE` anywhere | the marker's family, or `challenge-re` |
| status None (a kept payload whose answer's status the caller does not hold — the ledger's typing) | a marker in the first 64 KiB |
| any other status (a 200 included): the page TITLE carries a marker or `CHALLENGE_RE` (survey G0d: a solved page names its guard in its scripts, never its title) | the first marker in the 64 KiB window, else `challenge-re` |

What moved (recorded fixtures, `challenge_probe.py` in integrator-w3's scratch): MDPI's REAL Akamai "Access Denied" 403
(`qc/fixtures/litkb_mdpi_pdf_akamai_a3b93f589df6.html`) is a challenge (`akamai`) — open access booked it
`bad-file/html_response` before; the landing rule table's `page_cause` for Wiley and OUP reads `header:cf-mitigated`
(the one detector's first evidence), where it read the retired label `netutil.CHALLENGE_RE`. No recorded page changed
verdict.

| field | where | what it holds |
|---|---|---|
| `facts.challenge` | the acceptance test's verdict (`accept.Verdict.challenge`; `detail.acceptance.facts`) | the family the one detector found in bytes the magic step refused; the refusal's sub-status is unchanged (`html_response` / `too_small` / `missing_pdf_header`: the bytes' own word) |
| `detail.challenge` | `litkb.acquisition_attempts` | the family, on a row the LADDER re-booked: a rung's `bad-file` whose served bytes the one detector calls a challenge is written `blocked` / `challenge_or_bot_check`, `retriable` false (`run._challenge_of`, first sight through the acceptance test's verdict, a known-bad match asked directly). NOT for a Stage E route (`policy.STAGE_OF` = `E`): an archive replaying a challenge page it once captured did not refuse this client — that row stays `bad-file` with `facts.challenge` |

### An operator's file through admission (S4.5 decision D25; migration `0035_admit_operator_file_proposal.sql`)

`litkb admit --doi D --file F` and the MCP `litkb_admit(doi=, file=)` call `front.admit_registry(..., operator_file=True)`:
the file JSON carries `source_route` = `front.OPERATOR_ADMIT_ROUTE` (`held-in-place`: the file is admitted where it lies
under the literature root, `acquire --from-file`'s in-place route) and `source_url` = `in place <rel_path>`. Migration
0035 re-creates `litkb.admit` from 0032's text verbatim plus ONE guard: a file whose `source_route` is on
`litkb._proposal_source_routes()` is written as a PROPOSAL, whatever the admission's mode. Checks 1-4 are unchanged (a
file that fails binding or is already held still refuses the admission).

| result key | value |
|---|---|
| `outcome` | unchanged (`admitted` for a registry admission: the work and its identifiers are facts) |
| `file_state` | `proposed` (the operator's file: `file_versions.state` `proposed`, not in `main_files`) or `promoted` (every other caller — the legacy loader passes no route); absent when no file was admitted |
| `proposed`, `next` (CLI and MCP only; `front.operator_file_note`) | the proposal's `version_id` / `file_id` / `rel_path` / `source_route`, and how a second session decides it (`litkb approve-files` / `refuse-files`) |

`operator_binds_unproposed` (`qc/instruments/litkb_hardening_b2.py`, `OPERATOR_ROUTES`) reads these binds: an admitted
operator file that became main's version of record after the freeze counts.

### The live pass's shadow switch (S4.5 decision D27; `qc/instruments/litkb_ladder_run.py`, `litkb_acceptance.py`)

| field | where | what it holds |
|---|---|---|
| `shadow_tier` | the hardening manifest (`hardening --freeze`, `_frozen_shadow_tier`) | `{"enabled": false, "code_default": <policy.SHADOW_TIER_ENABLED>, "ruling": "S4.5 decision D27 / Scope ruling ..."}` |
| `shadow_tier` | the recording report (`write_recording_report`) | `{"enabled", "overridden", "manifest"}`: the switch the pass ran with, whether `--allow-shadow-tier` overrode the refusal, and what the manifest recorded |

`run_rows` sets `policy.SHADOW_TIER_ENABLED` to the manifest's recorded `false` for the pass and restores the code
default after it (the code default stays as merged). A manifest that does not record the switch off (none recorded, or
`true`) is REFUSED before anything is recorded or run (`ShadowTierRefused`; the CLI exits 2) unless `--allow-shadow-tier`
(`allow_shadow=True`) overrides it, and then the pass runs with the switch on.

### The report's named exceptions (S4.5 decisions D11, D23; `qc/instruments/litkb_hardening_a.py`)

`exception: <counter> <item> <reason>` (`EXCEPTION_LINE`: whole line; the reason required) in the LITKB_LADDER1 report
names ONE item of ONE counter as an exception, with its refusal reason. `named_exceptions(manifest, counter)` reads them
(`{item: reason}`; a report that is not there names none). A counter that admits exceptions leaves an item out only when
the report names it AND the database holds the refusal the reason describes; an item the report does not name is counted
(never silent). `free_ceiling_measured_unconverted` (builder C2a's) admits binding refusals (D23: the IIASA Wayback
copy passes the acceptance test and the binder refuses its corporate first author — a record / binder gap, reported,
not a Stage E miss): a free-ceiling DOI with no held file is excused only when the report names it AND the ledger
holds a `binding-failed` / `binding-pending` attempt of its work (`litkb_hardening_c2a.binding_refusal`); REPORTED
`free_ceiling_named_exceptions` counts the excused rows. The Wayback row is builder C2c's re-graded positive (IIASA,
`_wayback_positive` reads `litkb_hardening_c2c.WAYBACK_ROWS`). The ladder-1 run driver prints the lines the report
carries after its pass (`litkb_ladder_run.report_lines`: C2a's Stage A/B lines, then
`free_ceiling_exception_lines` — one `exception:` line per binding refusal the ledger holds, its reason the
binder's own).

### A pending file proposal is not a held file (S4.5 decision D28)

`run.work_record.held_files` counts MAIN's active files only. A work whose only file is a pending PROPOSAL (an operator's
`--from-file` or `admit --file`, a web landing) is not held: the ladder still asks it, and bytes it lands that the
proposal already holds end `duplicate-held` (the sha256 dedupe). The proposal's identity is exactly what a second
session has not confirmed (`litkb-from-file-version-state`).

### The not-asked line (S4.5 decision D32; `qc/instruments/litkb_hardening_a.py` `NOT_ASKED_LINE`)

`not-asked: <route> <works reached> <condition>` measures a CONDITIONAL Stage B rung for `stage_b_rungs_unmeasured` only
when ALL FOUR hold, else the rung is unmeasured (fail closed): (1) the registry gives the rung an `ask_condition`
(`stage_b.ASK_CONDITIONS`) and `<condition>` is byte-equal to it — a paraphrase answers nothing; (2) `<works reached>`
>= 1 — a rung the ladder never reached is unmeasured, not not-asked; (3) the report holds no `yield:` line with asked
> 0 for that route — a rung is asked or not-asked, never both; (4) the LITKB_LADDER1 report states such a rung's yield
on this corpus as UNDETERMINED (never eligible), not zero: its condition held for no work, so the run measured nothing
about what the rung would convert.

<!-- end of S4.5 integrator-w3 section -->

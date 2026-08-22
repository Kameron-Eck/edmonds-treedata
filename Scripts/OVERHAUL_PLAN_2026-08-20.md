# MASTER PLAN — Option A Overhaul: Re-plumb the Planes
*(adopted by Kam 2026-08-20; supersedes the crashed-session draft `sleepy-rolling-pizza.md`; committed as `Scripts/OVERHAUL_PLAN_2026-08-20.md` in P0, becoming the active plan named by CHATLOG STATE)*

## EXECUTION STATUS (2026-08-22)
P0 ✔ · P1 ✔ (313 GB backed up + sha256-manifested; CoE orthos byte-verified) · P2 ✔
(Drive detached; D: repo canonical; GitHub current) · P3 ✔ (all gates green) · P4 ✔
(verified writes proved in production — the 2nd 2024 runtime death left NO stub) ·
P5 ✔ canary + cutover proven (run manifests live at git 57bc07b); 2024-finish + QUEUE3
→ P11.4 (below) · P6 partial (manifests+seeds+queue-as-data ✔; registry generator deferred) ·
P7 partial (harvest, gates, status, watcher ✔; QC provenance deferred) · P8 ✔ ·
P9/P10 pending. **NEW: P11 below (adopted 2026-08-21) — agentic GPU driving via
Colab MCP, ask-first for the first launch of each queue (P11.5).** P11.1–11.3 ✔; **P11.5 ruled 2026-08-22** (crash-recovery autonomy, A100 default, branch
workflow — prep on `work/p11-5-autonomy`); **P11.6 adopted 2026-08-22** (headless Colab
via google-colab-cli; MCP tabs = fallback); P11.4 two-runtime trial pending —
prerequisites (staging lock, ceilings, resume fix, per-queue logs, balanced queues)
landed 2026-08-22; see the P11 runbook. 2024-finish + QUEUE3 did NOT land on
2026-08-22 (the two runtimes began ortho stagings ~10 min apart and each went silent
seconds after its own staging began; cause not established — throttle suspected, wedged
mount / VM death equally consistent; stopped by Kam) — they are the P11.4 workload.

## Context — why

A first-principles audit of the four-environment workflow (local Windows / Colab GPU /
Google Drive / GitHub) found five root causes; Kam adopted Option A (orchestrator-aware)
to fix them, with Option C (owned GPU) as the deliberate later step and Option B
(frameworks) declined — no scheduler can reach a human-launched ephemeral Colab runtime,
and `phase4_train_queue.py` already is the orchestrator Colab permits.

1. **Drive does three jobs** — data lake, code transport to Colab, git working tree —
   and fails at two (phantom-M, pause-sync rituals, FUSE-speed I/O, two-sessions-one-tree,
   documented 0-byte artifact writes). Drive is also at **430/476 GB — 45.8 GB free**.
2. **Zero protection** for irreplaceable artifacts (models, masks, phase3, CoE orthos —
   single-copy on Drive; the July D: robocopy has diverged).
3. **No provenance** — runs record no commit/versions/seeds; `run_registry.csv` is
   hand-written after the fact and currently a full day behind the queue CSV; training
   unseeded; `--run-tag` the only overwrite guard.
4. **No dependency spec** — pins conflict across bootstrap blocks (cross-script:
   `phase0_instance_seg.py:96-98` pins smp==0.3.4/timm==0.9.7 with albumentations
   unpinned; `phase3_semantic_dev.py:132-134` + `phase4seg/core.py:30-33` want
   albumentations>=2,<3).
5. **Human-glued orchestration** — jobs picked by editing source; launch line typed from
   memory; per-epoch tile streaming over FUSE; "local-then-copy" is dead code
   (`phase4seg/common.py:137 _copy_to_drive`, zero call sites).

Target: **code in a normal git repo on D: with GitHub as live remote; Colab clones the
code; Drive keeps exactly one job — the data lake.** Deterministic core / agentic shell:
scripts execute, Claude prepares/verifies/records, Kam holds GPU clicks and spend.

## Project context (absorbed 2026-08-20 — what the overhaul must not break)

- **The project**: per-crown temporal validity for 222,435 crowns, Edmonds WA, 18
  acquisitions 2000–2024, anchored to the single hand-labeled 2020 dataset; built for
  the City via the Climate Advisory Board. Phase 4 (per-year semantic) is active;
  phases 5–8 unbuilt. The current bottleneck is not modelling but **measurement and
  definition**: WORKPLAN §3 U1 — a written canopy definition — is the only thing
  blocking Phase 3, and D2 (crown form) is its gating sub-decision.
- **Measurement**: the model is a high-precision under-predictor (honest recall .55–.80,
  precision .78–.92 across 9 scored years). Recall is monotonic in height (5–15 m band
  = 53% of misses); crown perimeter carries ~42% of misses; the two references disagree
  on 15–17% of pixels; recipe-matched rows are the only comparable ones. Honest numbers
  live in `phase4/qc/qc_indep_report.csv` (`live=1` rows only); circular eval is never
  headline. QUEUE3 (2019, 2017, 2022 citywide_rgb) completes the recipe-matched series
  — it is staged in `phase4_train_queue.py:142` but NOT wired (JOBS is still queue 2).
- **Doc law**: one fact, one home; docs are a linked graph (README doc-map, dated
  filenames cited by name in ≥5 files, relative `../README.md` links). Entry chain:
  WORKPLAN → CHATLOG STATE → README; WORKPLAN wins. HANDOFF files retired. CLAUDE.md
  rules are cited by number (1b, 5, 6, 9) — numbering must stay stable.
- **Load-bearing quirks**: `City Boundry/` and `bathology/` misspellings are referenced
  by scripts — never rename. `litwatch_scratch/` holds 29 safe instruments and 77
  one-shot ledger writers that must never re-run. `phase5/` is abandoned but still read
  by 3 QC scripts. `polygons/` crown reviews are provisional (accept-all overwrite) —
  which is why every queue job passes `--force-citywide`. Local GPU is actually a 4 GB
  T2000 with working CUDA (CLAUDE.md's "2 GB" is stale) — still no local training.

## Verified ground truth (measured this session)

**Git/GitHub** — `D:\edmonds-pipeline\treedata.git`: fsck clean, 48 tags v001–v048,
single branch `main`, no stashes. `main == github/main == drive-mirror/main = cf2bcbd`;
all 48 tags on GitHub; **nothing unpushed**. Not a true bare repo (`core.bare=false`,
`core.worktree=G:/My Drive/treedata`). `G:\My Drive\treedata\.git` = 40-byte gitfile.
Repo root = `treedata/`, 551 tracked files: `Scripts/` (390), `phase4/qc/` (152
measured-text), `Reports/` (5), root README/xlsx/.gitignore/.gitattributes.
**`.gitignore` is a deny-all whitelist** — moving files silently untracks them unless
the whitelist is edited in the same commit (this bug already bit once).

**Dirty paths (all known)**: `CHATLOG.md` + `Method_Pipeline.md` phantom-M (empty
diffs); real: `phase4/qc/train_queue_status.csv` + untracked `qc_indep_surfaces_2023.csv`.

**2024 is DEAD, not running.** train OK (48.1 min) → evaluate OK (IoU .7142 @5 cm,
best in file but not apples-to-apples with 10 cm neighbours) → inference row RUNNING
since 2026-08-19 20:27 UTC, but `edmonds_canopy_prob_2024_citywide_rgb.tif` is a
**2.5 MB truncated stub** (2023's twin is 2450 MB), last write Aug 19 13:38 local,
stalled ~31 h. Third instance of this failure class (2022 0-byte, 2017 96.5%-nodata).
No VERIFY row, no qc_indep row. `run_registry.csv` stops at 08-18 — none of the
08-19 queue runs have rows.

**Sizes (measured)**: phase3 ~105 GiB (102 GiB is ONE file, `edmonds_canopy_prob_2020.tif`);
Pipeline Imagery ~190 GiB (CoE orthos 127.7 GB); phase4/models ~71 GB decimal (91
files; ~half is `sem_latest_*` near-duplicate twins); masks ~29 GB; phase4/crops =
64,296 JPGs, **unmeasured** (FUSE listing timed out); phase5 1.6 GB (abandoned).
Payload before trims ≈ **417 GB decimal + unmeasured dirs**; D: free = **475 GB**.
`D:\edmonds-pipeline\Imagery` (82.9 GB) already holds byte-identical king/naip/snoh
rasters (~70 GB dedupe lever) plus D:-only files (1936/1998 pan, `2017_king_rgb.tif`,
ccap variants incl. `snohfull`) — the mirror is not a pure subset; sync must be one-way
with exceptions preserved. No `backup\` dir exists yet. Queue CSV timestamps are UTC,
file mtimes local (−7 h) — freshness checks must normalise.

## Design rules (encoded in CLAUDE.md during P3)

1. **Code and config resolve via `__file__`; data resolves via `BASE`.** Never
   `BASE / "Scripts" / …` again.
2. **Authored vs measured text**: docs authored in the repo; measured outputs
   (`phase4/qc/`, `Reports/`, registry) produced in the data lake and *harvested* by
   script. Reports default harvested (Kam may edit via Drive/Docs; edits harvested).
3. **Deterministic core, agentic shell**: agent output is a reviewable artifact
   (queue.yaml, prepared cell, proposal); scripts execute it verbatim; structural gates
   on spend and mutation (untagged overwrite refused).
   **Spend gate — REVISED by Kam 2026-08-21**: GPU launches were human-paste only;
   now Claude MAY drive Colab runtimes through the Colab MCP server, but **must ask
   Kam for explicit permission before every launch** — naming the queue file, GPU
   tier, number of runtimes, and rough cost — and may never launch, extend, or add
   runtimes un-asked. Kam still holds the keys; Claude may now turn them when handed
   over, one launch at a time.
   **Amended by P11.5 (Kam 2026-08-22)**: first launches stay ask-first; a crashed run
   is recovered autonomously (fix branch → small-GPU canary → A100 rerun, every launch
   logged, no cap tonight); `main` never moves without Kam — see P11.5.
4. Parallel sessions share the D: tree → explicit-path staging stays law; worktrees
   stay available (now cheap — no FUSE).

## Open rulings (defaults apply unless Kam overrides — none block P0–P5)

- Backup hardware beyond the $0 D: copy (4 TB disk / B2) → **defer, decide at P9**.
- Retire `drive-mirror` bare repo → **retire at P10**.
- Retire old `treedata.git` DB → **retire at P10 after one verified cycle on the clone**.
- Reports/*.md → **harvested**.
- Forwarding shims → **none** (frozen Drive copy covers legacy launches until P10).
- Backup scope trims → **defaults**: skip `sem_latest_*` twins (halves the models leg;
  `sem_best_*` is the deliverable), skip `phase4/crops/` (regenerable JPGs; measure
  first, include only if headroom allows), skip `phase5/` (abandoned), dedupe imagery
  against existing `D:\Imagery` byte-identical files.
- **GPU keys — RULED by Kam 2026-08-21**: Claude may drive Colab via MCP, ask-first
  for the first launch of each queue (amended by P11.5), cap 2 runtimes (see P11 and
  design rule 3).
- **Crash-recovery autonomy — RULED by Kam 2026-08-22**: see P11.5 (first launches
  ask-first; autonomous fix → canary → A100 rerun; `main` protected; no cap tonight).
- **D2 polarity — RULED by Kam 2026-08-20 ("Adopt")**; historical text below:
  adopted ruling per the crashed session = mid-height woody vegetation (ornamentals,
  hedgerows, ~6 m crowns) **COUNTS as canopy**, recorded as its own interpreter class
  (reversible). This REVERSES the draft recommendation
  (`canopy_definition_PROPOSAL.md:130-136`: tree form required, hedges excluded).
  Consequence stated openly: 5–15 m misses (53% of all misses) count fully against the
  model; headline lands on the NDVI-reference side (~.38-family). If Kam does not
  confirm, P0 records everything else and leaves D2 undecided.

## Phases

### P0 — Bookkeeping (current arrangement; the last old-way commits)
- Write this plan → `Scripts/OVERHAUL_PLAN_2026-08-20.md`; CHATLOG STATE names it
  active; one CHATLOG LOG entry (caveman spec).
- **2024 disposition**: mark the stub dead in `train_queue_status.csv` (close the
  RUNNING rows honestly), set `edmonds_canopy_prob_2024_citywide_rgb.tif` aside (rename
  `.stub-20260819`), note 2024 inference re-run as the tail of the next Colab window.
  Never back up or score the stub.
- **Registry backfill**: add rows for the 08-19 queue runs (2005/2007/2009/2021k/2023 +
  2024 partial) from the queue CSV + logs — the last hand-written rows ever (P6 makes
  it generated).
- Record D2 **if confirmed** (dated DECIDED block in `canopy_definition_PROPOSAL.md`
  per its own sign-off procedure :187-192, noting the reversal; the proposal stays in
  place until all of U1 signs off); WORKPLAN §3 (D2 decided, D1/D3–D6 open) + §4
  priorities: overhaul P0–P5 → imagery items 1–4 → remaining U1.
- Commit `qc_indep_surfaces_2023.csv` + `train_queue_status.csv` delta. Explicit-path
  staging only (rule 1b); phantom-M ignored.

### P1 — Interim backup, $0, BEFORE surgery
- Measure the unmeasured first (local `du` per dir via targeted listings): `phase4/crops`,
  `phase3/{checkpoints,labels,tiles}`, `Full_Image/{KingCo,USGS,WA_NAIP,USDA_NRCS}`,
  `Pipeline Imagery/{composites,test_crops,upsample}` — then fix the final copy list
  against D:'s 475 GB.
- `robocopy /Z /LOG /R:2 /W:5` Drive → `D:\edmonds-pipeline\backup\`, ordered:
  1. `phase3/edmonds_canopy_prob_2020.tif` **first, alone** — 102 GiB single file,
     highest-risk transfer; verify size before continuing.
  2. `phase4/models` (`sem_best_*` only per trim default), `phase4/masks`, all
     `*.gpkg`/`*.parquet`, `phase4/manifest.json`, rest of `phase3/`.
  3. CoE orthos (127.7 GB) → also unblocks local 2020 characterization (the D: mirror
     holds none of them, which is why 2020 — the labeled year — was never inventoried).
  4. Imagery: **skip byte-identical files already in `D:\Imagery`** (~70 GB saved).
  - **Exclude the 40-byte `.git` gitfile** (else the backup becomes a co-worktree).
  - Exclude the 2024 stub; `/MT:8` for any small-file dirs included.
- sha256 manifest per backup dir (small script, reused by `mirror_sync.py` in P9).
- Outcome: two media for every irreplaceable artifact before any surgery.

### P2 — Move the code home
- Final sweep: P0 committed everything intended; phantom-M ignored.
- `git clone --no-hardlinks D:\edmonds-pipeline\treedata.git D:\edmonds-pipeline\treedata`;
  `git remote remove origin`; add `github` (live; Claude pushes) + `drive-mirror`
  (until retired). Verify: fsck, log matches, 48 tags, clean status, `main`.
- **Detach Drive**: delete the 40-byte gitfile. Phantom-M, pause-sync,
  two-sessions-one-tree die here. (Old DB keeps stale `core.worktree` — harmless.)
- Drive `Scripts/` frozen as-is (pre-reorg): the old QUEUE nohup line
  (`phase4_train_queue.py:42-56` docstring) keeps working as fallback until P5 proves
  the new path. **Never edit the frozen copy.**
- Sessions henceforth open in `D:\edmonds-pipeline\treedata\Scripts`.
- Accepted gap P2→P7: tracked measured text updates on Drive, reaches the repo only by
  manual explicit-path copy until `harvest_results.py`.

### P3 — Repo surgery (in the D: repo, on a branch, merged normally)
**Reorg mapping (verified: 60 top-level .py, covered exactly, zero orphans):**
- `pipeline/` (20): phase0–3, shim + `phase4seg/`, train_queue, p1_colab_run,
  build_corrected_labels, pipeline_log, label_review±prep, make_*, fetch_build_chm,
  preflight, smoke.
- `qc/` (38 + 1 html): 25 `phase4_qc_*` + catalog_check, data_inventory, ref_agreement,
  accuracy_sample **+ `phase4_accuracy_review.html`** (loaded via `with_name()` at
  `phase4_accuracy_sample.py:484` — moves together), sentinel tools, ccap_sample,
  build_ccap_city, viz, qa_overlay, threshold_diagnostic, miss_examples,
  phase3_make_segmentation_png. (Sibling imports stay co-located: design_power→
  accuracy_sample, latent_class family, sentinel pair — all inside `qc/`.)
- `scratch/`: `litwatch_scratch/` whole (keep its README — the 77-writers hazard),
  `merge_measurement_branch.ps1|.sh`.
- `_archive/scripts/`: version_script.py, pipeline_config.py (zero live importers;
  `_archive/scripts/*` importing pipeline_config keeps working — they move together).
- Stay at root: docs, run_registry.csv, sentinel_sites.json, pipeline_architecture.html,
  edmonds_combined_workplan.xlsx.
- **Same commit: edit the `.gitignore` whitelist** for every moved path — the deny-all
  root means a move otherwise silently untracks files.
- **NO forwarding shims**; "no new top-level .py" holds.

**Pure-move discipline**: `phase4seg/config.py` is moved untouched — its constants
carry load-bearing narrative history and feed `_tile_signature` (`tiling.py:580`);
any constant change triggers a ~20-min full re-scan per year. No reformatting.

**Path/import fix list (all sites verified):**
1. `LOGS_DIR = BASE/"Scripts"/"logs"` — 34 scripts + `phase4seg/cli.py:260` +
   `pipeline_log.py:377` default + `phase4_sentinel_snap.py:67` → `BASE/"phase4"/"logs"`
   (logs are run artifacts = data plane; old Drive logs stay put).
2. `SCRIPTS = BASE/"Scripts"` at `phase4_train_queue.py:86` / `phase4_p1_colab_run.py:91`
   → `Path(__file__).parent`, carrying the derived `ENGINE` (`:90`/`:96`) and Popen
   `cwd` (`:257`/`:393`). **Without this the queue silently executes the Drive engine
   from a clone.**
3. `SITES_JSON` (`phase4_sentinel_snap.py:64`) → `parents[1]/"sentinel_sites.json"`.
4. Base-detection probe (`phase4_sentinel_snap.py:58`) → probe a data-plane landmark
   (`Full_Image`), not `Scripts`.
5. Sibling `sys.path` inserts moving to `qc/` that import `phase4seg`/`pipeline_log`:
   `phase4_catalog_check.py:50`, `phase4_qc_design_power.py:70`,
   `phase4_qc_latent_class_test.py:11`, `phase4_sentinel_qc_overlay.py:56` →
   `parents[1]/"pipeline"`; sweep all moved scripts for `pipeline_log`/`phase4seg`
   imports (`cli.py:259` is a flat sibling import — pipeline_log.py must live beside
   the shim in `pipeline/`, which it does). Fix the dead-worktree path in
   `phase4_qc_latent_class_adversarial.py:16` in passing.
6. `phase4_viz.py:157-158` default module path → `../pipeline/`.
7. `phase4seg_smoke.py:27-28` `BASE = HERE.parent` → `HERE.parents[1]` (+ stale comments).
8. `pipeline_log.py:77-117` — the `logs_dir.parent` script-dir lookup serves the
   RETIRED versioning system and, with the frozen Drive copy still present, would hash
   the WRONG file (provenance lies). Re-anchor candidates to the running `__main__` /
   `__file__`; keep the package-attachment loop working (shim + `phase4seg/` are
   siblings in `pipeline/`, so the 8-file SHA still folds in).
9. Docstring launch paths (`phase4_train_queue.py:42-56`, `phase4_viz.py:29`,
   `fetch_build_chm.py:31`, `make_grass_negatives.py:22`, `phase4_p1_colab_run.py:51`,
   `phase4seg_preflight.py:15`) → clone paths (P5 regenerates the real launch cell).
10. Fix the queue's spurious MISSING-INPUT check (`phase4_train_queue.py:408-411`) —
    `Path("--force-citywide").exists()` is False, so every job warns; test the last
    extra only when it looks like a path.

**Requirements**: `requirements-local.txt` + `requirements-colab.txt` recording the
live phase3/4 profile (albumentations>=2,<3; smp/timm unpinned-but-recorded); phase0's
frozen-legacy pins noted in the file; `_ensure_deps`/`_ensure_torch` read from it.

**Docs in the same merge**: CLAUDE.md rewrite (D:-repo bootstrap; new layout; placement
rules; rules that DIE: pause-sync, phantom-M lore, mirror-push ritual; STAY: explicit
paths, worktrees, rule numbering for 1b/5/6/9 citations; NEW: design rules 1–4, never
edit frozen Drive Scripts; fix stale facts: 4 GB T2000 local GPU, models ~71 GB).
README doc-map, WORKPLAN §7 table, buildtracker (its relative `../README.md` link),
Method_Pipeline, IMAGERY_* paths. Dated filenames keep their names (they are cited by
name in ≥5 files). Reports/ byte-stable; CHATLOG history untouched.

**Verify**: `py_compile` all moved; `qc/phase4_catalog_check.py` **18/18**; preflight +
smoke pass; `pipeline/phase4_train_queue.py --dry-run`; `qc/phase4_data_inventory.py`
end-to-end; `git status` clean w.r.t. tracking (no silently-untracked files).

### P4 — Engine run-protection (lands BEFORE the next GPU dollar)
Isolated, revertable commits, gated by preflight+smoke:
1. **Verified writes**: resurrect `_copy_to_drive` (`common.py:137`, dead) with
   size+sha256; route checkpoint, prob raster, mask through
   write-local(`/content`)-then-verified-copy. Kills the failure class that has now
   struck three times (2022 0-byte, 2017 96.5%-nodata, 2024 stub).
2. **Tile staging**: stage the year's tiles to `/content` at train start (pattern:
   `_stage_imagery_local`, `common.py:109`). **Must rewrite the absolute paths baked
   into `tile_index_{year}.csv`** (`tiling.py:811`; `SemanticDataset` opens them
   verbatim, `core.py:225`) — reuse the layout-reconstruction trick from
   `phase4seg_smoke.py:71-75`.
3. **VERIFY per step, all states**: move from job-end to step-end; add checkpoint
   (loadable, size), tiles (count vs index), mask checks; include a size-sanity gate
   comparing prob rasters against the expected-MB figures the queue CSV already records.

### P5 — Colab cutover
- `Scripts/pipeline/colab_launch.ipynb` (tiny, repo-tracked, THE standing cockpit):
  mount Drive → `git clone --depth 1` via PAT from Colab Secrets → `%cd
  /content/repo/Scripts/pipeline` → nohup queue launch (the `:42-56` recipe, re-homed)
  + tail/status cells.
- **Kam one-time**: fine-grained PAT (contents:read, single repo) → Colab Secrets.
  Public repo is a separate curation task — never an auth shortcut.
- **Canary window** (minutes of GPU): bootstrap → `--check` → `--dry-run` → one cheap
  real step (`--year 2000 --step labels`).
- **First real window**: finish 2024 (inference re-run + VERIFY + postproc) — closes
  QUEUE2 honestly on the new path. Then **QUEUE3 window** (wire `JOBS = QUEUE3`, or by
  then the P6 `--queue` flag): 2019 → 2017 → 2022, protected by P4. Fallback at any
  failure: frozen Drive Scripts + old nohup line.

### P6 — Provenance
- Run manifest per run_id → `phase4/runs/{run_id}/manifest.json`: git SHA + dirty flag,
  `pip freeze`, seeds, full args, resolved imagery paths + root, engine version.
  StepLogger gains run_id; log filenames carry it; status rows link to it. Timestamps
  normalised to UTC with offset recorded (the CSV-vs-mtime 7 h skew).
- Seed torch/cudnn/DataLoader workers (recorded; AMP nondeterminism accepted).
- **Queue-as-data**: `queue.yaml` + `--queue` flag; editing source to pick jobs ends.
  `run_registry.csv` becomes GENERATED from manifests.
- **De-collide untagged artifacts**: `sem_loss_history_{year}.csv` (`core.py:902`),
  `_per_year_canopy_area.csv` (`postproc.py:216`), tile index — gain the `_tag_sfx()`
  suffix or a run_id column.
- **QC provenance**: the QC family's module-local `write_step_log`s carry no
  version/SHA — route them through `pipeline_log.write_step_log` (or add the
  provenance header) so honest numbers are traceable to code.
- `_tile_signature` (`tiling.py:580`) extended to cover ortho path+size+mtime.

### P7 — Orchestrator contract (deterministic core, agentic shell)
- `qc/pipeline_status.py`: dag.yaml + artifact globs + status CSV + qc_indep live rows
  → one cold-start state table (would have caught the 2024 stub: RUNNING row + 31 h
  stale + 2.5 MB artifact = dead).
- `qc/watch_queue.py`: dumb poller of `train_queue_status.csv` → notify on
  anomaly/completion (agent judges only when signaled; never a billed polling daemon).
- `pipeline/harvest_results.py`: idempotent Drive→repo copy of tracked measured text
  (`phase4/qc/*` — 152 files today, `Reports/*`, generated registry) + explicit-path
  commit. Session-end contract updated to include it.
- Gates codified: engine refuses untagged overwrite without `--allow-overwrite`; GPU
  launches human-paste only; watcher read-only; session protocol in CLAUDE.md.

### P8 — The DAG
- `pipeline/dag.yaml`: one node per stage (0 → 1a–1d → 2 → 3 → 4 steps → qc scorers)
  with script, inputs, outputs, runs-on (local|colab). Validator checks declared files
  exist; renders Mermaid into README + `pipeline_architecture.html`.

### P9 — Backup plane, permanent
- `mirror_sync.py`: robocopy wrapper + regenerated checksum MANIFEST + assert-match
  mode for QC reads. **One-way Drive→D: with a preserved-exceptions list** (D:-only
  files: 1936/1998 pan, `2017_king_rgb.tif`, ccap variants) — never two-way. Resolve
  the diverged `edmonds_canopy_mask_{2000,2016}.tif` pairs (measure, then fix).
- Optional hardware (deferred ruling): 4 TB disk and/or B2. Note: offloading the
  102 GiB `phase3/edmonds_canopy_prob_2020.tif` off Drive (once ≥2 backup copies
  exist) would singlehandedly relieve most of the Drive quota pressure — Kam's call,
  recorded here for P9/P10.

### P10 — Cleanups & later
- Retire `drive-mirror` (default yes) and old `treedata.git` after one verified cycle
  (default yes). Clean the stray `refs/remotes/drive-mirror/main` ref on GitHub.
- Delete frozen Drive `Scripts/` after QUEUE3 + one more clean window; leave a README
  pointer. Delete the empty `D:\edmonds-pipeline\CLAUDE.md` stub.
- CHATLOG STATE compaction to ~150 lines (fresh, not tired).
- Public-repo curation (separate work item). Trim candidates from the backup survey
  (`sem_latest_*` on Drive, `_bce`/`xsensor_sample` families, phase5) → Kam's call.
- **Option C revisit trigger**: after A completes and the next GPU billing cycle.

### P11 — Agentic GPU driving via Colab MCP (adopted by Kam 2026-08-21)

**Ruling:** Kam hands Claude the option to drive Colab directly ("the keys"), with one
inviolable rule: **Claude always asks permission before driving.** Every launch is
proposed first — queue file, GPU tier, runtime count, rough cost — and executes only on
Kam's explicit yes in that conversation. No standing authorization, no silent re-launch
after a death, no adding runtimes mid-window. This supersedes "human-paste only" while
keeping its intent: spend passes through Kam's hands every time.
*Amended 2026-08-22 by P11.5 (below): the ask-first rule now covers the FIRST launch of
each queue; crash-recovery relaunches are autonomous under the protocol there.*

1. **Concurrency-safe queue status (prerequisite, code)** — today two concurrent queues
   clobber `train_queue_status.csv` (each `_status_write` rewrites the whole file from
   its own snapshot; observed 2026-08-22 01:00–01:03Z). Fix in
   `pipeline/phase4_train_queue.py`: each queue writes its own
   `phase4/qc/train_queue_status_{queue-stem}_{launch-ts}.csv`; a merged view is
   produced by `qc/pipeline_status.py` and `qc/watch_queue.py` (glob
   `train_queue_status*.csv`, concat, sort by ts; resume's `_completed_steps` reads the
   merged view so cross-queue resume still works). Every launch — single or concurrent — writes
   its own per-launch file; the legacy `train_queue_status.csv` is frozen read-only
   history; readers merge all `train_queue_status*.csv`.
2. **Colab MCP connection (Kam, one-time)** — connect the Colab MCP server to Claude
   Code (`claude mcp add …` per the server's docs, or paste its config into
   `.claude/settings`/`.mcp.json`). Claude then verifies the connection read-only
   (`claude mcp list` → Connected; a cold `tools/list` returns only
   `open_colab_browser_connection` — runtimes/notebooks are NOT listable before a
   tab is attached, see the runbook) before any driving is proposed.
3. **The permission protocol (codified in CLAUDE.md)** — before any MCP launch Claude
   states: queue file · GPU tier · # runtimes · expected wall-clock and rough cost ·
   what VERIFY success looks like; waits for Kam's yes; after launch, monitors and
   reports, and **asks again** before any relaunch/retry that costs GPU. Runtime cap
   **2 concurrent** until the Drive-throttle interaction is characterized — a
   Drive download throttle was measured from one client (390 kB/s vs ~5 MB/s healthy,
   2026-08-21); whether it is per-account or per-client is not established, and the
   2026-08-22 double-runtime silence is unexplained — bulk copies are serialized by
   the staging lock as a precaution; stagger stage-heavy jobs.
4. **Trial (P11.4, with Kam's per-launch yes)** — the remaining series work itself:
   `queue_A_2024_2017.yaml` + `queue_B_2019_2022.yaml` on two runtimes (runbook
   below); later channel-ablation / boundary-aware-supervision runs (WORKPLAN Tier 3)
   reuse the protocol. Claude driving via MCP end-to-end: propose → approved launch →
   monitor → score → report. Compare wall-clock vs serial; decide whether to raise
   the cap.
5. **Docs** — CLAUDE.md two-planes section + design rule 3 updated (ask-first
   protocol, runtime cap); CHATLOG LOG entry recording the ruling; this plan is the
   ruling's home until then.

**P11 runbook (added 2026-08-22, after the first two-runtime attempt went silent):**

*Status:* P11.1 ✔ (per-launch status files) · P11.2 ✔ 2026-08-22 (`claude mcp list`
→ colab-mcp ✔ Connected; user scope, absolute `uvx.exe` path because
`Python312\Scripts` is on neither PATH) · P11.3 ✔ (CLAUDE.md) · **P11.4 trial pending**.

*Mechanism (read from the server source, colab_mcp 1.0.1 on FastMCP 2.14.5):* cold,
the server exposes ONE tool — `open_colab_browser_connection`. Calling it opens the
default browser at `colab.research.google.com/notebooks/empty.ipynb#mcpProxyToken=…
&mcpProxyPort=…`; the Colab page connects back over a localhost websocket, and the
server then PROXIES the Colab frontend's own tools ("notebook editing tools" is all
`session.py:177` says — exact names come from the runbook's step 2 inventory) to the
agent (`tools.listChanged`). So one browser tab = one Colab session = one
runtime per connection, and the notebook tools cannot be enumerated until a tab is
attached. Nothing in the package authenticates to Google itself — the browser tab is
the credential.

*Prerequisites landed 2026-08-22 (code, no GPU; two adversarial review rounds, 29 + 19
findings fixed):* Drive staging lock (`phase4seg/common.py _StagingLock` — the design,
the constants `STAGE_LOCK_*` and their rationale live there): bulk (≥1 GiB) Drive→NVMe
copies serialize across runtimes via per-claimant files in `phase4/locks/` (no
`O_EXCL` — Drive is not POSIX); the oldest live claim holds, confirmed on a second
listing taken after `STAGE_LOCK_CONFIRM_SEC`; liveness is judged in the reader's clock;
bounded wait then proceed unlocked with a warning (claim kept so later claimants still
queue); unknown states fail closed; every lost race is logged by the holder's
heartbeat; the queue sweeps the claim of an engine it kills. Small copies (CHM, masks,
tile sets) never wait. This removes ONE suspected cause of the 08-22 silence; a wedged
mount or a dead VM is untouched. Step
ceilings per `phase4_train_queue.STEP_TIMEOUT_MIN` (its comment carries the
invariant; the old inference 240 would have killed every CoE-grid inference —
2017's took 254.9 min); resume revokes an OK when a later attempt failed/never
reported or its `VERIFY` hard-failed; per-queue nohup logs
`train_queue_nohup_{queue}_{ts}.log`; balanced queues `queue_A_2024_2017.yaml` +
`queue_B_2019_2022.yaml` (hours in their headers); cockpit cells 1–4/6 rewritten
(`phase4/locks/` pre-created at bootstrap and at queue launch — Drive keeps two
same-named folders if two VMs race to create one).
Residual risk, accepted: a Drive-file lock cannot be more than best-effort — if a
peer's claim propagates slower than `STAGE_LOCK_CONFIRM_SEC`, or the mount
wedges, both runtimes copy; the holder's heartbeat prints a WARNING so the nohup log
records it. Mitigation: launch B ≥2× `STAGE_LOCK_CONFIRM_SEC` after A (≥2 min at
today's value — `phase4seg/common.py` is the home of every `STAGE_LOCK_*` value). Tests: a 10-case local unit test plus
a two-view lagged-propagation simulation (the harness the review used to prove the
earlier version lost exclusion).

*Next-session sequence — the FIRST launch of each queue is its own ask; crash-recovery
relaunches follow P11.5:*
1. `claude mcp list` → colab-mcp connected; ToolSearch shows
   `open_colab_browser_connection` and nothing else.
2. Kam's yes → call it once; a Colab tab opens; **list the unlocked tools** (read-only
   inventory → CHATLOG). Nothing runs.
3. Zero-GPU check on that tab (CPU runtime): open `pipeline/colab_launch.ipynb`
   (Colab's GitHub opener on the private repo, or a Drive copy) → cells 1–2
   (`--dry-run`), with cell 1's `BRANCH` set to the code to run and cell 2's
   `nvidia-smi` confirming the tier; the clone is at that branch's HEAD.
4. Propose launch A (`queue_A_2024_2017.yaml`, A100 40 GB, 1 runtime, ~5 h (~10 h on
   L4), Colab's posted rate) → yes → cell 3. The staging ⏱ line is a COMPLETION tock: measured
   stagings are 12–26 min for the 48 GB 2017 ortho (six logs), 19.1 min for 2024,
   2–14 min for 2022, ≤2.5 min for King orthos. Health within the first 15 min =
   `!ls -la /content/phase4_scratch` showing the ortho growing, or the log's
   "staging lock held by … waiting" line. No growth and no tock past ~2× the
   precedent → something is wrong (throttle, mount, VM): stop the runtime (it burns
   GPU while copying); under P11.5 the relaunch follows the crash-recovery protocol
   (fix branch → small-GPU canary → A100 rerun) with no further ask.
5. One server instance = ONE Colab connection (colab_mcp 1.0.1
   `websocket_server.py:113-118` rejects a second websocket with 1013 "Server is busy";
   `session.py:166-167` returns `true` without opening a tab when already connected).
   A second runtime therefore needs a SECOND server entry — DONE 2026-08-22 03:40Z
   (`colab-mcp` + `colab-mcp-b` both ✔ Connected in `claude mcp list`); the command, for
   the record:
   `claude mcp add --scope user colab-mcp-b -- "C:\Users\Kameron\AppData\Local\Programs\Python\Python312\Scripts\uvx.exe" git+https://github.com/googlecolab/colab-mcp`
   → its own `open_colab_browser_connection` → second tab → propose launch B
   (`queue_B_2019_2022.yaml`, A100, ≥2× `STAGE_LOCK_CONFIRM_SEC` after A — ≥2 min at today's
   value; the lock confirms a fresh claim only after that window). Until that entry exists, B runs after A or by human-paste in
   a second tab. Lock lines to expect in the nohup logs: "staging lock held by … ;
   waiting", "staging lock acquired after N min"; any "WARNING: … two bulk copies"
   line = a lost race — record it in CHATLOG.
6. Monitor ARTIFACTS, not CSV content: per-launch status files, run manifests, tile
   files, prob rasters. `VERIFY:inference OK` → local scoring per the staged commands
   in CHATLOG (threshold gate: the scorer's console line must say
   `channels=rgb+chm`, else the eval row for that year has not landed — do not score).
   Also re-score 2013 citywide in the same batch: its quoted .7422 is a live=0 row
   scored at the fallback 0.5, so a tool-chosen re-score WILL move it — expected,
   not regression.
7. After the window: harvest, registry rows, CHATLOG; compare wall-clock vs serial and
   decide whether to raise the 2-runtime cap.

### P11.5 — Crash-recovery autonomy, A100 default, branch workflow (ruled by Kam 2026-08-22)

**Ruling.** Kam's answers of 2026-08-22: the FIRST launch of each queue stays
**ask-first**; a launched run that crashes is recovered **autonomously**; **no spend cap
tonight** ("we are learning") — the launch log is the control; loop intervals **back
off to a 60-min ceiling**; **A100 40 GB** for real runs, **L4/T4** for canaries; the
laptop never sleeps (the browser-based MCP bridge persists).

1. **First launch of each queue** (A, B): propose queue file · GPU tier · runtime count ·
   hours · cost line · what VERIFY success looks like; wait for Kam's yes.
2. **Crash-recovery protocol (autonomous).** Trigger = a FAIL/TIMEOUT/ERROR row, a dead
   runtime, a traceback in the nohup/step log, a status older than 2× the expected step
   time, or a "two bulk copies" lock WARNING. Then, without asking:
   - diagnose from artifacts (per-launch status files, run manifests, step logs, nohup);
   - branch `fix/<YYYYMMDD>-<slug>` from `main`; fix; local gates (`py_compile`,
     `pipeline/phase4seg_preflight.py`, `pipeline/phase4seg_smoke.py`, the lock unit test
     if the lock is touched); commit with explicit paths;
   - push the BRANCH to GitHub (`git push -u github fix/…`) — Colab clones from GitHub;
   - **canary on a small GPU (L4/T4) with a ONE-JOB queue YAML** committed on the fix
     branch (`pipeline/queue_canary_<slug>.yaml`): the failing job itself when its
     remaining steps — resume skips the OK ones — are expected to run ≤ ~1.5 h, else a
     coarse proxy year (2000/2002, ~1 h for the full path). **CLI edition (P11.6, the
     live path): `colab new -s canary --gpu L4` → ask Kam for `colab drivemount -s
     canary` (every fresh VM needs one) → `colab_cli_vmgen.py --branch fix/…` → exec
     bootstrap + launch.** (Browser fallback: cockpit cell 1 `BRANCH = 'fix/…'`, cell 3.)
     Success = the canary job's `VERIFY:<step>` rows all OK — only the
     queue writes VERIFY rows, so a cell-5 single-step run (`!python -u …`, fresh
     interpreter) is a code-path smoke (exit 0 + the manifest line `on fix/<branch>`),
     never the protocol's canary;
   - **if the canary passes: relaunch the real queue on the A100 from the fix branch**,
     no further ask; every launch writes a run manifest (now with `git_branch`, `gpu`,
     `gpu_mem_gb`) and a CHATLOG line with tier, start time, expected hours;
   - if the canary fails, or the same failure recurs after a fix: stop and ask.
3. **`main` is protected.** No push, merge, rebase or tag on `main` without Kam's
   explicit approval — enforced by deny rules (below), not only by prompt. Work branches
   (`work/…`, `fix/…`) are free to create, commit and push. At session end or loop stop,
   Claude presents `git log main..<branch> --oneline` + `git diff main...<branch> --stat`
   and asks. **Kam merges, tags (`vNNN` if a new live version landed) and pushes `main`
   in his own shell** — `git merge`, `git tag`, `git reset` and any push that could reach
   `main` are DENY rules for Claude: blocked outright, never prompted, so they cannot be
   approved per-command. To delegate for one session, Kam moves those rules from `deny`
   to `ask`.
4. **GPU tiers.** A100 40 GB for real queue runs (queue A ≈ 5 h, B ≈ 4 h; ~10 / ~8 h on
   L4); L4/T4 for canaries; RTX PRO 6000 only when memory-bound (ask). The step ceilings
   (`phase4_train_queue.STEP_TIMEOUT_MIN`) were sized on L4 and stay valid (a faster GPU
   only adds headroom). `nvidia-smi` is printed by cockpit cell 2 and in the queue header;
   the manifest records the tier. Note: the retired P1 driver
   (`pipeline/phase4_p1_colab_run.py:38-42, 210-224`) still tells users to switch DOWN
   from A100 — that is its own legacy advice, not policy, and it is not on the queue path.
5. **Loop pacing.** After the launches the `/loop` self-paces: 10 → 15 → 25 → 40 → 60 min
   while nothing changes (60-min ceiling); reset to 10 min after any event (new status
   row, artifact, lock WARNING, a scoring run). First check after a launch at ~15 min.
6. **Permission allowlist** — the unattended loop must never block on a prompt. Home =
   **user settings only** (`D:\tools\claude-config\settings.json`; applies to sessions
   opened from D: or G:). Never in the repo: the root `.gitignore` whitelists all of
   `Scripts/`, so a `Scripts/.claude/settings.json` would be TRACKED. Rules are enforced by
   Claude Code (deny → ask → allow, first match wins), so `main` stays protected even
   though branch pushes are allowed. Loop git commands run from the repo cwd in plain
   `git <verb> …` form — never `git -C <repo> …`, never `cd … && git …` — because both
   allow and deny rules are word-bounded prefix patterns; the `git -C …` deny twins below
   exist only so that form cannot escape the protection. ✔ INSTALLED 2026-08-22: the block
   below is live in user settings (verified in-session: `git push github main` denied,
   hot-reload); the stray `Bash(git push:*)` and `Bash(rm:*)` allows were removed from
   `C:\Users\Kameron\.claude\settings.json`. The `PowerShell(...)` deny twins exist because
   the PowerShell tool is a separate tool with separate rules — `Bash(...)` rules never
   gate it — so without them `main` was protected for Bash only; the loop itself uses the
   Bash tool only (no PowerShell allows). Canonicalized 2026-08-22 (Kam) to the live list.
   Loosened 2026-08-22 (Kam, "back off permissions to streamline the agentic harness"; policy
   unchanged): read-only git, shell readers, `cp`/`mkdir`, and `Edit` on the session scratchpad
   are allowed so an unattended loop never waits on the auto-mode classifier. Still no `rm`
   rule — deletions go through `py -3.12`. Leading `VAR=` assignments still fall through:
   use `py -3.12 -X utf8 …`, never `PYTHONUTF8=1 py …`.

```json
{
  "permissions": {
    "allow": [
      "Bash(py -3.12 *)",
      "Bash(git add *)",
      "Bash(git commit *)",
      "Bash(git checkout -b *)",
      "Bash(git switch *)",
      "Bash(git branch *)",
      "Bash(git fetch *)",
      "Bash(git stash *)",
      "Bash(git push github fix/*)",
      "Bash(git push -u github fix/*)",
      "Bash(git push github work/*)",
      "Bash(git push -u github work/*)",
      "Bash(claude mcp list)",
      "mcp__colab-mcp__*",
      "mcp__colab-mcp-b__*",
      "mcp__claude_ai_Google_Drive__search_files",
      "mcp__claude_ai_Google_Drive__get_file_metadata",
      "mcp__claude_ai_Google_Drive__list_recent_files",
      "WebFetch(domain:github.com)",
      "WebFetch(domain:code.claude.com)",
      "Bash(C:\\Users\\Kameron\\.local\\bin\\colab.exe *)",
      "Bash(\"C:\\Users\\Kameron\\.local\\bin\\colab.exe\" *)",
      "Bash(C:\\Users\\Kameron\\AppData\\Roaming\\uv\\tools\\google-colab-cli\\Scripts\\python.exe *)",
      "Bash(\"C:\\Users\\Kameron\\AppData\\Roaming\\uv\\tools\\google-colab-cli\\Scripts\\python.exe\" *)",
      "Bash(git status *)",
      "Bash(git log *)",
      "Bash(git diff *)",
      "Bash(git rev-parse *)",
      "Bash(git show *)",
      "Bash(git ls-files *)",
      "Bash(cat *)",
      "Bash(ls *)",
      "Bash(grep *)",
      "Bash(sed -n *)",
      "Bash(head *)",
      "Bash(tail *)",
      "Bash(wc *)",
      "Bash(diff *)",
      "Bash(find *)",
      "Bash(cp *)",
      "Bash(mkdir *)",
      "Edit(//D/tools/claude-config/jobs/**)"
    ],
    "deny": [
      "Bash(git push github main*)",
      "Bash(git push * main*)",
      "Bash(git push *:*)",
      "Bash(git push *refs/heads/*)",
      "Bash(git push *--mirror*)",
      "Bash(git push *--tags*)",
      "Bash(git push *--force*)",
      "Bash(git push -f *)",
      "Bash(git push * -f)",
      "Bash(git push *--delete*)",
      "Bash(git merge *)",
      "Bash(git rebase *)",
      "Bash(git reset *)",
      "Bash(git tag *)",
      "Bash(git switch main*)",
      "Bash(git checkout main*)",
      "Bash(git branch -f *)",
      "Bash(git branch -D *)",
      "Bash(git branch -M *)",
      "Bash(git branch -m *)",
      "Bash(git -C * push *)",
      "Bash(git -C * merge *)",
      "Bash(git -C * tag *)",
      "Bash(git -C * switch *)",
      "Bash(git -C * checkout *)",
      "Bash(git -C * reset *)",
      "Bash(git -C * branch *)",
      "Bash(git -C * rebase *)",
      "PowerShell(git push github main*)",
      "PowerShell(git push * main*)",
      "PowerShell(git push *:*)",
      "PowerShell(git push *refs/heads/*)",
      "PowerShell(git push *--mirror*)",
      "PowerShell(git push *--tags*)",
      "PowerShell(git push *--force*)",
      "PowerShell(git push -f *)",
      "PowerShell(git push * -f)",
      "PowerShell(git push *--delete*)",
      "PowerShell(git merge *)",
      "PowerShell(git rebase *)",
      "PowerShell(git reset *)",
      "PowerShell(git tag *)",
      "PowerShell(git switch main*)",
      "PowerShell(git checkout main*)",
      "PowerShell(git branch -f *)",
      "PowerShell(git branch -D *)",
      "PowerShell(git branch -M *)",
      "PowerShell(git branch -m *)",
      "PowerShell(git -C * push *)",
      "PowerShell(git -C * merge *)",
      "PowerShell(git -C * tag *)",
      "PowerShell(git -C * switch *)",
      "PowerShell(git -C * checkout *)",
      "PowerShell(git -C * reset *)",
      "PowerShell(git -C * branch *)",
      "PowerShell(git -C * rebase *)"
    ]
  }
}
```

*Prep landed 2026-08-22 on `work/p11-5-autonomy`:* cockpit cell 1 `BRANCH` (clone
`--branch`; on re-run `fetch --depth 1 origin BRANCH` + `checkout -B BRANCH FETCH_HEAD`,
because the `--depth 1` clone is single-branch), cell 0/6 A100 + branch text, cell 2
`nvidia-smi`; manifest `git_branch`/`gpu`/`gpu_mem_gb` (`phase4seg/cli.py
_write_run_manifest`, torch-free via `nvidia-smi`); queue header GPU line
(`phase4_train_queue.py _gpu_line`); queue YAML hours on A100; CLAUDE.md spend gate +
rule 1c; this section. The session-start and `/loop` prompts live in
`D:\tools\claude-config\plans\because-we-are-not-parallel-codd.md`.

### P11.6 — Headless Colab via google-colab-cli (adopted by Kam 2026-08-22; supersedes the MCP-tab launch path, which becomes fallback)

**Why.** The MCP browser path hit a structural wall: every server instance opens the same
scratch notebook (`SCRATCH_PATH = "/notebooks/empty.ipynb"`, hard-coded), Colab hands out
runtimes per notebook, so two tabs shared ONE runtime; moving a tab is a manual fragment
dance. Google's official `google-colab-cli` (PyPI, v0.6.0) is fully headless: named VMs
with the GPU chosen by flag, code exec over websocket, no browser.

**MOUNT TEST IS THE FIRST GPU-FREE STEP OF ANY SESSION.** ✔ PASSED 2026-08-22 15:4xZ
after machine-local fix #4 (below): Kam's PowerShell `colab drivemount -s mounttest`
completed (`Mounted at /content/drive`) and the agent's `colab exec` listed
`/content/drive/MyDrive/treedata` on the same VM — both unknowns proven. Before the fix
it had NOT completed anywhere (the `/dev/tty` read fails on every Windows terminal, not
only the agent shell). The rule stands for every future session: prove it on
a CPU VM before allocating a GPU: `colab new -s mounttest` → Kam runs `colab drivemount
-s mounttest` in his terminal → the AGENT verifies with a `colab exec` listing of
/content/drive/MyDrive/treedata (this also proves the mount is visible across the
Kam-terminal / agent-shell boundary, shared `~/.config/colab-cli` state) → `colab stop`.
If it fails: no A100, report, and the fallback is the MCP-tab path or an
rclone/service-account mount — Kam's call. Record the outcome in CHATLOG either way.

**Probe results (2026-08-22, CPU sessions, no compute units).** Verified working from an
agent shell on Windows: auth (one-time OAuth, token + refresh at
`~/.config/colab-cli/token.json`); `colab new -s A --gpu A100` (A100 allocated READY in
~1 min); `colab exec -s NAME -f script.py` (kernel state persists across execs;
detached `nohup` survives); `colab sessions/status/log/stop`. NOT agent-runnable:
`colab drivemount` — Colab's per-VM Drive consent prints a URL and then requires Enter
on a real TTY (`/dev/tty`), so it is a KAM step, in his own terminal, once per VM
(~1 min: URL → approve → Enter). The Drive grant does NOT carry across VMs (verified:
a fresh VM asked again). `console`/`repl` need a TTY — never used.

**Machine-local CLI fixes (this Windows box; re-apply after any `uv tool upgrade`
google-colab-cli — documented here because they live OUTSIDE the repo):**
1. Installed via `uv tool install google-colab-cli --with "jupyter-kernel-client<1.0"` —
   the CLI's dep is UNPINNED and jupyter-kernel-client 1.0 renamed `KernelClient` →
   `JupyterKernelClient`, breaking `exec`/`drivemount`.
2. Windows `termios` stub at
   `%APPDATA%\..\Roaming\uv\tools\google-colab-cli\Lib\site-packages\termios.py`
   (constants so stdlib `tty.py` imports; functions raise) — the CLI is "Linux/macOS
   only" solely because `console.py` imports termios unconditionally.
3. Two-phase OAuth helper (agent-drivable sign-in): `D:\tools\colab-cli\auth_twophase.py`.
4. `colab drivemount` Enter-read (2026-08-22, D: session): `colab_cli/commands/automation.py`
   `drivefs_hook` read the post-consent Enter via `open("/dev/tty")`, which does not exist on
   Windows; the `FileNotFoundError` was swallowed by `runtime.py` (`except Exception:
   logging.debug`), so the `dryrun=false` credentials-propagation POST and the kernel
   `input_reply` never ran and DriveFS timed out (`ValueError: mount failed`, the
   drive-timeout branch) — on EVERY Windows terminal, Kam's included. Patch: wrap the
   `/dev/tty` read in `try/except OSError` and fall back to `sys.stdin.readline()`; the
   human still consents in the browser and presses Enter. Backup beside it:
   `automation.py.orig`.

**The flow (one queue per VM; first launch of each queue = Kam's yes, per P11.5):**
1. Agent: `py -3.12 pipeline/colab_cli_vmgen.py --branch <branch> --queue <q>.yaml
   --outdir <local scratch>` → writes `vm_bootstrap.py` (clone at BRANCH with the
   gh-token templated in — token stays local + VM kernel memory, scrubbed from
   .git/config; Drive-mount assert; mkdir logs+locks; pip install; GPU print; queue
   dry-run) and `vm_launch.py` (nohup the queue, log to
   `phase4/logs/train_queue_nohup_{queue}_{ts}.log`).
2. Agent (ask-first): `colab new -s A --gpu A100`.
3. **Kam:** `colab drivemount -s A` in his terminal (URL → approve → Enter).
4. Agent: `colab exec -s A -f vm_bootstrap.py --timeout 900` → expect `BOOTSTRAP_DONE`;
   then `colab exec -s A -f vm_launch.py --timeout 60` → pid + log path. Delete the
   generated scripts (token).
5. Same for B (`colab new -s B --gpu A100`, ≥2 min after A's launch for lock ordering).
6. Monitor: Drive artifacts (per-launch status files, manifests, rasters) as always,
   plus `colab status -s A` / `colab log -s A -n 20`. `colab stop -s <name>` when a
   queue's job-end VERIFY rows land — idle VMs bill until stopped (24 h hard cap).
7. **Crash recovery (P11.5 protocol, CLI edition):** a fix is code — push the fix
   branch, re-generate with `--branch fix/…`, re-run `vm_bootstrap` + `vm_launch` on
   the SAME live VM (no new consent). Canary per P11.5 = a one-job queue YAML on a
   small GPU: `colab new -s canary --gpu L4` (this DOES need one Kam drivemount).
   Only a dead VM forces `colab new` + Kam's mount again.

**Permission notes (user scope, already granted 2026-08-22):**
`Bash(C:\Users\Kameron\.local\bin\colab.exe *)` and
`Bash(C:\Users\Kameron\AppData\Roaming\uv\tools\google-colab-cli\Scripts\python.exe *)`,
alongside the P11.5 lists. Discipline: commands must START with the literal allowed
prefix — a leading `VAR=…;` assignment breaks rule matching and falls back to the
auto-mode classifier (observed repeatedly tonight).

**Lost-session hazard + recovery (measured 2026-08-22, mid-run, both A100s live).**
`colab_cli.common.sync_sessions()` PRUNES every local session whose endpoint is absent
from the CURRENT `list_assignments()` response, and `execution.py` deletes a session on
a 401/404 ("appears to be lost. Cleaning up."). Both happened tonight: session `A`
vanished from `~/.config/colab-cli/sessions.json` while its A100 kept running the queue
(the VMs sit in different regions — A asia-southeast1, B us-central1 — so a partial list
is plausible), then `B` was cleaned up after an expired-token exec. A pruned VM keeps
BILLING but `colab exec/status/stop -s NAME` can no longer reach it: it shows as a `[?]`
orphan and only expires at the 24 h cap. **Every `colab sessions` call runs the prune**,
so a monitoring loop that polls it is the likeliest trigger.
**What actually triggers the prune (measured 18:20-18:45Z, third occurrence).** Not only a
partial `list_assignments`: `commands/execution.py` deletes a session on ANY transient
failure — a 404 from `/api/kernels` was enough — printing "appears to be lost. Cleaning
up." And the stored `runtime_proxy_info` token lives **exactly 1 h** (measured: issued
18:43:57Z, `exp` 19:43:57Z), so every session older than an hour 401s on its next `colab
exec` and prunes itself. A monitoring loop that execs every minute therefore *guarantees*
the failure on any run longer than an hour. Fix: `qc/colab_readopt.py --heal` — re-adopt
orphans, refresh tokens with >25 min of margin, respawn dead daemons — run automatically
by `qc/runtime_dashboard.py` every 2 min, and safe to run by hand at any time.

**And the prune KILLS the VM, not just the name.** `prune_session()` also kills the
session's keep-alive daemon (`colab_cli.cli keep-alive <endpoint> <name>`), and that
daemon is the ONLY thing calling `keep_alive_assignment()` to refresh Colab's idle timer
for the assignment. An unheartbeated VM is reclaimed **~15–25 min later even while it is
computing**: measured twice on 2026-08-22 — A died 14 min after its prune (2024 inference
~39%, lost), B died ~25 min after a re-adoption that restored the name but not the daemon
(2019 inference ~40%, lost). Neither wrote anything to Drive: the verified-write path
keeps the raster in `/content/phase4_scratch` until the step completes.
Recovery, no GPU spend, no new VM: `qc/colab_readopt.py` rebuilds the local entry from
the server's own assignment list (each carries a fresh `runtime_proxy_info` url+token)
**and respawns the keep-alive daemon** — run it on the CLI's own interpreter, `--list`
first, then `--endpoint … --name …`. `qc/runtime_dashboard.py` flags a session whose
daemon PID is dead, which is the early warning that precedes this failure by ~20 min.
`qc/runtime_dashboard.py` therefore reads `sessions.json` directly (never `colab
sessions`) and flags any live assignment with no local name as a billing orphan.

**Facts for cost/monitoring:** a session is a billable VM until `colab stop`; keep-alive
daemon runs locally (has a Windows branch; laptop never sleeps); CLI sessions appear in
`colab sessions`; the browser-era orphan `[?]`-entries cannot be stopped by name and
expire at the 24 h cap. MCP entries `colab-mcp`/`colab-mcp-b` stay registered as the
fallback path only.

**Relation to Option C:** MCP driving is the middle rung of the ladder (human-paste →
MCP-with-permission → owned/rented GPU with SSH). If MCP driving proves out and spend
still hurts, C's case strengthens; everything here carries over.

### Parallel track (any time after P3)
Imagery items 1–4 (per IMAGERY_FACTS/PLAN): q138b/cast2 wrappers for the nine
unmeasured acquisitions — 2020 first (wrappers in `qc/`, results → phase4/qc CSVs;
stop if any King re-print drifts from IMAGERY_FACTS §2.2); `gdaladdo` external `.ovr`
overviews; merged `imagery_inventory.csv` in data_inventory (+ band-count/fill checks,
WORKPLAN Tier-2 item 7); 2012 disposition evidence → Kam decides. The P1 CoE-ortho
copy unblocks the 2020 characterization that `phase4_data_inventory.py`'s D:-only scan
has never been able to do.

## Human checklist (everything Kam does, in order)
1. ~~Confirm or flip the **D2 polarity**~~ ✔ DECIDED 2026-08-20 ("Adopt").
2. ~~Create fine-grained PAT + add to Colab Secrets~~ ✔ done 2026-08-21.
3. Windows: canary ✔ · 2024-finish + QUEUE3 in flight (keep the tab open until done).
4. **P11**: connect the Colab MCP server to Claude Code (one-time), then answer
   Claude's per-launch permission asks. Pushes to GitHub run on your say-so.

## Risk register
- Clone path fails in a Colab window → frozen Drive Scripts + old launch line (to P10).
- Engine edits regress before QUEUE3 → isolated commits, preflight+smoke+canary gate.
- Reorg silently untracks files → `.gitignore` whitelist edited in the same commit +
  post-merge `git ls-files` count check (390 Scripts files accounted for).
- Provenance hashes the wrong tree while frozen Drive copy exists → P3 fix 8.
- Backup overruns D: (417 GB + unmeasured vs 475 free) → measure-first step, trim
  defaults, dedupe lever; nothing else lands on D: mid-copy.
- 102 GiB single-file transfer fails mid-stream → copied first, alone, `/Z`, size-verified.
- Parallel sessions on the D: tree → explicit-path staging stays law.
- PAT leakage → fine-grained, read-only, single-repo, Secrets-stored.
- History loss → 4 copies until P10 (old DB, clone, GitHub, drive-mirror).
- Muscle memory opens G:\Scripts → README pointer; frozen copy read-only in practice.
- Harvest forgotten → session-end contract; idempotent script.
- Agent-driven GPU spend (P11/P11.5) → the first launch of each queue needs Kam's yes;
  2-runtime cap; every launch stamps a run manifest (`git_branch`/`gpu`/`gpu_mem_gb`) so
  spend is always attributable; a relaunch after a failure is autonomous ONLY via the
  P11.5 protocol (fix branch → small-GPU canary with VERIFY rows → A100), logged; no cap
  tonight by Kam's ruling.
- Concurrent queues clobber the status CSV → per-queue status files + merged reader
  (P11.1); until that lands, one queue at a time.

## Definition of done
Single canonical repo on D: pushed to GitHub; Drive detached from git, serving data
only; Colab running from the clone (2024 closed + QUEUE3 landed with per-step VERIFY
OK + run manifests); every irreplaceable artifact ≥2 media with checksum manifests;
`pipeline_status.py` renders full state cold; dag.yaml renders the 0→4 DAG; CLAUDE.md
describes the new world; D2 recorded (if confirmed); imagery items 1–4 unblocked in `qc/`.

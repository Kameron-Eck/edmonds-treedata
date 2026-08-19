# Edmonds Temporal Active Learning Pipeline — Claude Code Instructions

> Read this file at the start of every session, then **read the STATE block at the top
> of `CHATLOG.md`** to see where the work actually stands — that is the single source of
> live truth. `../README.md` is the map of every doc. Read the live source files before
> touching any code; do not rely on memory or this file for specific parameters — always
> read the source.

---

## Project Purpose

Per-crown temporal validity intervals for 222,435 individual tree crowns across
Edmonds, WA. 18 aerial imagery acquisitions (15 calendar years, 2000–2024).
Outputs binary canopy masks per year (semantic, all 18 years) and per-crown
instance polygons (9 high-resolution years). Anchored to the 2020 hand-annotated
dataset.

**Current active workstream:** Phase 4 — per-year semantic canopy. The model is
precise but **UNDER-predicts** canopy (misses tall green deciduous stands the
conifer-only labels never taught). See `CHATLOG.md` STATE for the live state and
the active plan. Everything hard here stems from the fact that **only 2020 has
real hand labels**; all other years borrow them.

---

## Sources of truth (one home each)

**The full doc map lives in `../README.md`** — don't restate it here. The homes that
matter before editing:

- **Live state / next step →** `CHATLOG.md` **STATE** block (read first to resume).
- **Method / params / tiers / loss / QC →** `Method_Pipeline.md`.
- **What's built vs pending →** `pipeline_buildtracker.md`.
- **Schedule / decision gates →** `edmonds_combined_workplan.xlsx`.
- **Active plan →** the one plan file named in CHATLOG STATE.
- **The script being edited →** always read it before patching.
- **Imagery catalog + path resolution →** `phase4seg/config.py`: `YEAR_CATALOG` and
  `imagery_roots()`. `pipeline_config.py`'s catalog is frozen legacy (2013+ only) and is
  NOT authoritative — it kept a stale copy of this fact until 2026-08-19. Test with
  `py -3.12 phase4_catalog_check.py`.

**One fact, one home.** Each fact has exactly one authoritative location; every other
doc *links* to it rather than restating it. A fact written authoritatively in two places
is a bug — fix the source, not the copy. (Per-session `HANDOFF_*.md` files are **retired**;
their role is covered by CHATLOG STATE + the active plan. Superseded docs live in
`_archive/` — never current.)

**Rule: never invent hyperparameters or architectural decisions. If it is not in the
source files, ask before assuming.**

---

## Drive Layout

```
/content/drive/MyDrive/treedata/          (Colab)  ==  G:\My Drive\treedata\  (local)
├── Scripts/                        ← canonical script + doc location
│   ├── phase0_instance_seg.py            ← Phase 0 instance seg (DTM regression + watershed)
│   ├── phase1_preprocess.py … phase1d_classifier.py   ← Phase 1 spectral + active learning
│   ├── phase2_data_prep.py
│   ├── phase3_semantic_dev.py            ← 2020 base semantic model → sem_best_2020.pt
│   ├── phase4_semantic_finetune.py       ← THIN SHIM (~97L) → phase4seg/ ; preserves `%run ... --args`
│   ├── phase4seg/                        ← LIVE per-year fine-tune/inference ENGINE package
│   │     config/common/labels/tiling/core[torch]/postproc/cli — live version = CHATLOG STATE
│   ├── phase4seg_preflight.py            ← local static pre-flight (compile/imports/args) before a Colab run
│   ├── phase4seg_smoke.py                ← local CPU runtime smoke test of the engine (tiny model, real tiles)
│   ├── phase4_label_review_prep.py / phase4_label_review.py   ← crown review tool
│   ├── phase4_qc_ndvi.py                 ← independent NDVI+CHM canopy REFERENCE (NIR years)
│   ├── phase4_qc_score.py                ← score model vs the NDVI reference → qc/qc_report.csv
│   ├── phase4_qc_indep.py                ← reference-agnostic scorer vs an INDEPENDENT ref (C-CAP) → qc/qc_indep_*
│   ├── phase4_qc_forest_misses.py        ← under-prediction autopsy: why C-CAP forest is missed + stand shortlist
│   ├── phase4_qc_site.py                 ← lat/lon window FN-attribution diagnostic
│   ├── phase4_qc_flicker.py              ← temporal-stability (flicker) test on stable parcels
│   ├── phase4_miss_examples.py           ← NDVI-stratified image chips of MISSED trees
│   ├── phase4_ccap_sample.py             ← C-CAP-stratified FIXED tile locations for cross-sensor runs (locate-only)
│   ├── phase4_build_corrected_labels.py  ← NIR+CHM → ADD-ONLY corrected-label overlay
│   ├── make_positive_site.py             ← stage a positive site (crowns derived from 2020 mask)
│   ├── make_grass_negatives.py           ← stage curated grass/turf negative sites
│   ├── fetch_build_chm.py                ← builds lidar_snoh_chm.tif (3DEP HAG height)
│   ├── phase4_viz.py / phase4_qa_overlay.py / phase4_threshold_diagnostic.py
│   ├── phase3_make_segmentation_png.py   ← Phase 3 proof-of-concept figure (RGB|GT|prob|overlay grid)
│   ├── version_script.py                 ← RETIRED versioning helper (git replaced it)
│   ├── pipeline_config.py                ← LEGACY paths only; catalog FROZEN (archived scripts)
│   ├── phase4_catalog_check.py           ← tests every YEAR_CATALOG entry resolves + opens + band count
│   ├── pipeline_log.py                   ← write_step_log() / StepLogger
│   ├── run_registry.csv                  ← one row per Colab run (see rule 9)
│   ├── sentinel_sites.json / phase4_sentinel_snap.py   ← fixed-site visual progress snapshots
│   ├── CLAUDE.md  Method_Pipeline.md  CHATLOG.md  pipeline_buildtracker.md  (../README.md)
│   ├── _archive/                        ← retired handoffs, old workplan, dormant scripts,
│   │                                       audit_2026-07-08/ (NOT current — see _archive/README.md)
│   ├── logs/                             ← step run logs: {script}_{step}_{timestamp}.log
│   └── .versions/                        ← FROZEN pre-git snapshot archive (git-ignored)
├── .git (pointer file) → git repo at D:\edmonds-pipeline\treedata.git (local Windows only)
├── phase3/            ← 2020 semantic model + edmonds_canopy_mask_2020.tif (full-city PREDICTION)
├── phase4/            ← per-year semantic outputs
│   ├── models/  masks/  eval/  qc/  labels_corrected/  qa/  tiles/  crops/  review/  sites/
│   ├── eval/semantic_eval_report.csv         ← circular (2020-label) metrics
│   ├── qc/qc_report.csv                       ← honest metrics vs the NDVI reference
│   └── labels_corrected/canopy_additions_{year}.tif   ← ADD-ONLY corrected-label overlay
├── polygons/          ← crown polygon inputs (EPSG:3857); {site}_crowns_review.gpkg
├── photos/            ← training-site footprint GeoTIFFs (Forest_* / Negative_* / Positive_*)
├── Full_Image/Pipeline Imagery/
│   ├── {year}_{src}_rgb.tif / _rgbi.tif       ← native orthos (NIR years end _rgbi)
│   ├── lidar_snoh_chm.tif                      ← 3DEP HAG height — CHM 4th channel + QC height
│   ├── ccap_{2016,2021}_hires_lc.tif           ← NOAA C-CAP 1m land cover — INDEPENDENT eval ref (EVAL-ONLY, never train)
│   ├── lidar_snoh_structure.tif / _hillshade_fr.tif   ← older struct experiments (superseded)
│   └── upsample/                               ← reprojected to 2020 grid (phase1 spectral only)
└── phase5/ … phase8/  ← not yet built
```

---

## Local Mount (Windows) & where things run

- Google Drive for Desktop mounts the tree at **`G:\My Drive\treedata\`**. Claude
  Code reads/edits/deletes scripts **directly on the filesystem** — no MCP upload.
  Edits sync up to Colab in seconds. (Do **not** use the Google Drive MCP to
  "update" a script — it only duplicates; write to `G:\` instead.)
- **Imagery is mirrored locally at `D:\edmonds-pipeline\Imagery`** (byte copy of the
  Drive originals + `edmonds_canopy_mask_{2000,2016}.tif` + `lidar_snoh_chm.tif`).
  QC / label-build / diagnostic scripts read from **D:** (fast, no FUSE).
- **torch is Colab-only** (local GPU = 2 GB). But `rasterio` / `geopandas` /
  `shapely` / `fiona` / `sklearn` **pip-install locally on import** (each script has
  a bootstrap), so QC, label-building, and raster diagnostics **run locally**. Only
  tiling / training / inference must run on Colab.

---

## Phase Architecture

| Phase | Script | Status |
|-------|--------|--------|
| 0 | `phase0_instance_seg.py` | Complete — 222k crowns, `edmonds_crowns_2020.gpkg` |
| 1–1D | `phase1_*` | Complete — 18-year spectral features, `edmonds_crowns_phase1.parquet` |
| 2 | `phase2_data_prep.py` | Complete |
| 3 | `phase3_semantic_dev.py` | Complete — 2020 base, LOSO IoU 0.7299 / AUROC 0.9396, passed DG1 |
| 4 | `phase4_semantic_finetune.py` (shim) → `phase4seg/` | **Active.** Per-year semantic fine-tune; engine modularized 2026-07-08. **Live version number + current detail live ONLY in `CHATLOG.md` STATE — never restated here.** |
| 4 (review) | `phase4_label_review.py` | Built; the 14,476-crown human review was **never completed** (see Gotchas). |
| 5–8 | — | Not yet built |

> The per-year fine-tune path has resolution **tiers** (fine ≤15 cm / medium 29.9 cm
> / coarse 50–60 cm) and **two label sources**: coarse years train on the citywide
> 2020 mask; fine/medium years train on per-site crown polygons. This distinction
> drives most Phase-4 behavior — see `Method_Pipeline.md`.

---

## Mandatory Rules for Every Edit

### 1. Git is the version system; compile before writing
Code + docs live in a **private local git repo** (working tree = this Drive folder;
git database = `D:\edmonds-pipeline\treedata.git`, off the FUSE mount). Commit after
every landed change; before a risky edit, make sure the tree is committed so rollback
is one command:
```bash
git status --short                          # ALWAYS first — see rule 1b
git add <the paths you touched> && git commit -m "<what landed>"
git restore -s vNNN -- Scripts/<name>.py    # rollback a file to a tagged version
```
Tag `vNNN` (annotated) whenever CHATLOG STATE records a new live finetune version.
Then `PYTHONUTF8=1 py -3.12 -m py_compile <script>` before the edit is considered done.
**Git ops run from local Windows only — never from Colab.** Safe anytime: status/log/
diff/add/commit/tag (writes go to D:). **Pause Drive sync first** for anything that
writes the working tree: checkout, restore, `reset --hard`, stash pop, branch switch.
(`version_script.py` / `.versions/` are RETIRED 2026-07-06 — kept on disk as a frozen
pre-git archive, git-ignored; full history was imported as backdated commits v001–v044.)

**1c. The git DB has NO redundancy — mirror it.** `D:\edmonds-pipeline\treedata.git` is a
single copy on a single disk with no remote (see CHATLOG STATE correction 4). The whole
argument for versioning findings is that they "survive loss of the Drive mount" — but
nothing protects against loss of **D:**. An empty bare mirror is staged at
`G:\My Drive\_treedata_git_mirror.git` (on Drive, so it syncs to the cloud; the live DB
stays off FUSE for speed). To arm and use it — **run these yourself, Claude Code's
permission layer blocks remote/push operations**:
```bash
git remote add drive-mirror "G:/My Drive/_treedata_git_mirror.git"   # once
git push --mirror drive-mirror                                       # after each session
```
`--mirror` makes the backup an exact copy including tags, and deletes refs there that are
gone here — which is what a backup should do, but it means never commit *into* the mirror.

**1d. Housekeeping.** The repo had 1018 loose objects and zero packs (never gc'd) plus a
stale `worktrees/*/refs` garbage entry. Run `git gc` occasionally — it is safe, writes only
to D:, and needs no Drive pause. Note that `git status` on this tree reports ~40 files as
modified with **empty diffs**: Google Drive rewrites file mtimes constantly, so the stat
cache is permanently stale. `core.trustctime=false` does NOT fix it (tried 2026-08-18).
Treat a bare `M` with an empty `git diff` as noise — which is another reason rule 1b's
"stage explicit paths" is not optional here.

**1b. Two sessions share one working tree — stage PATHS, never `-A`.** Parallel Claude
sessions (and Colab) edit the same Drive folder, so `git status` at the start of your
session is already stale. `git add -A` sweeps up whatever the other session has in
flight and commits it under YOUR message — it happened 2026-08-17 (`0020f2a` swallowed
half of an unrelated `pipeline_log.py` change). Nothing is lost when it happens, but the
history lies about who changed what. So: run `git status --short` immediately before
committing, stage only the paths you edited, and if a file you did not touch shows up
dirty, leave it — it is theirs.

### 2. Log integration
Every script `write_step_log()`s at the end of each `--step` →
`Scripts/logs/{script}_{step}_{timestamp}.log`. After Colab runs a step, **read the
log from Drive** — do not ask the user to paste terminal output.

### 3. Local-then-copy writes
Large files (GPKG, Parquet, TIF) are written to local NVMe first, validated, then
copied to Drive with `shutil.copy2`. Never write large files straight to the FUSE
mount.

### 4. Colab `%run` argparse filtering
Every `main()` filters Colab's injected `-f <json>` args:
```python
filtered = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
```
Preserve this in every script you touch.

### 5. Honest evaluation only
Effective independent sample size is ~5 forest sites, not tile counts — **LOSO** is
the only honest split; random-split metrics are inflated. And metrics scored against
the **2020 mask reprojected onto another year are CIRCULAR** (real pre-2020 change
counts as model error). Report the **independent** number (NDVI+CHM reference for
NIR years via `phase4_qc_*`; Olofsson photo-interp for no-NIR years) as primary —
never circular or random-split as the headline.

### 6. Three-state mask supervision
Masks are 0 (background), 1 (canopy), 255 (IGNORE). Unsure/unreviewed pixels are
IGNORE — never assigned to either class. Corrected-label overlays are **ADD-ONLY**
(may add canopy or IGNORE; must never turn canopy into background).

### 7. Resolution
All segmentation uses **native resolution** — no upscaling. Upsampled imagery is
only for spectral feature extraction under fixed 2020 crown polygons (phase1/phase7).

### 8. Validity interval semantics
- present@2000 → `valid_from=2000, valid_to=2020`
- absent@2000 → `valid_from=2020, valid_to=2020` (out-of-interval negative)
- unsure/unreviewed → IGNORE (subtract from region polygon)

### 9. Keep the running log current (session-end checklist)
Per landed milestone: **(a)** edit the `CHATLOG.md` STATE block in place, **(b)**
append one LOG entry (caveman style per the file's spec), **(c)** append a row to
`run_registry.csv` if a Colab run landed, and **(d)** `git add <the paths you touched>
&& git commit` — **never `-A`**, see rule 1b; this line used to say `-A` and that is the
habit that produced the `0020f2a` mis-attribution
(tag `vNNN` if a new model version landed). This is how the next session resumes. **Do not create a new `HANDOFF_*.md`** (retired) or a duplicate
plan. Slow-moving docs (`pipeline_buildtracker.md`, the workplan) reconcile only on phase
boundaries or method changes, not every session.

---

## Key Data Facts

| Item | Value |
|------|-------|
| Total crowns | 222,435 |
| Training sites | 5 conifer forest + curated negative/positive sites |
| Phase 3 LOSO IoU / AUROC | 0.7299 ± 0.0413 / 0.9396 ± 0.0190 |
| CHM | `lidar_snoh_chm.tif` — USGS 3DEP HAG, ~2016, U8 DN=0.2 m/DN (0=nodata), ~60% city coverage |
| NIR-bearing years | 2016, 2019n, 2021s, 2022n (only these can build an NDVI reference) |
| C-CAP eval ref | `ccap_{2016,2021}_hires_lc.tif` — NOAA hi-res 1m land cover, EPSG:26910, EVAL-ONLY (never train); hi-res forest=11, developed collapsed |
| GPU (Colab) | Menu: **L4 24 GB** (default/cheapest, most runs) · A100 40 GB (when needed) · RTX PRO 6000 Blackwell ~95 GB (available). Memory-plan against the tier actually selected — OOM bugs bite at 24–40 GB, not 95 GB. |
| GPU (local) | 2 GB — CPU / raster / QC only, no training |

---

## Current State & Pending Work

**Do not hardcode volatile state here — it rots.** The live "what's next" is the
`CHATLOG.md` **STATE block** + the active plan it names. Read those to resume.

**Gotchas (durable):**
- `polygons/` was overwritten with accept-all test data; the 14,476-crown human
  review was never finished — treat those labels as provisional.
- The full-city `phase3/edmonds_canopy_mask_2020.tif` is a **model prediction**, not
  hand truth (hand labels exist only for the 5 conifer sites) — it shares the model's
  blind spots (e.g. deciduous marsh).
- `phase4seg/` (via the `phase4_semantic_finetune.py` shim) is **Colab-only to run** (`fork` start
  method + torch); locally, validate with `phase4seg_preflight.py` (static) and
  `phase4seg_smoke.py` (CPU runtime) before spending a Colab round-trip.

---

## Compute

| Resource | Use |
|----------|-----|
| Google Colab (L4 24GB default / A100 40GB / RTX PRO 6000 95GB) | All tiling, training, inference, heavy I/O |
| Local machine (2 GB GPU) | Claude Code, script edits, log review, **QC + label-build + raster diagnostics** |

Compute-heavy torch steps run in Colab; do not split training between local and Colab.

---

## Communication Pattern

- Terse. Confirm scope before building.
- Read live source files — never infer from memory.
- Paste targeted terminal output (tracebacks), not full stdout — the log system exists
  so full stdout need not be pasted.
- After Colab runs a step, read the log from Drive before responding.

---

*This file is the session bootstrap. It holds stable rules and pointers — the living
state lives in `CHATLOG.md` STATE and the active plan. Doc map: `../README.md`.*

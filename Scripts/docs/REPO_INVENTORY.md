# Repository & data-plane inventory (operations reference)

Moved here from the root README 2026-09-01 — the front page presents the project;
this page is the operator's map of every folder, drive, and archived document.

## Git architecture (re-plumbed 2026-08-20 — plan archived: `archive/2026-08-pre-refactor:Scripts/OVERHAUL_PLAN_2026-08-20.md`)

- **The repo lives at `D:\edmonds-pipeline\treedata`** — a normal git working tree on
  local disk. Sessions open in `D:\edmonds-pipeline\treedata\Scripts`. Tags **v001–v048+**
  plus `pre-refactor-2026-08-31`.
- **Drive is detached from git and serves data only.** `G:\My Drive\treedata\Scripts\`
  is a FROZEN pre-reorg copy kept as the Colab launch fallback — never edit it.
- **Remotes**: `github` → private `github.com/Kameron-Eck/edmonds-treedata` (the live
  mirror) and `drive-mirror` → `G:\My Drive\edmonds-git-mirror.git` (legacy).
- **`.gitignore` is a whitelist** (`/*`, then re-admit). Tracked: `Scripts/`,
  `phase4/qc/` text outputs, `Reports/*.md` + `*.csv`, `README.md`, `pyproject.toml`,
  `Literature_Tracker.xlsx`, a few root files. **Everything else on this list has NO git
  safety net** — imagery, models, rasters, GPKGs live on disk (+ the
  `D:\edmonds-pipeline\backup\` checksum mirror).
- Parallel sessions may share the working tree: **stage explicit paths, never `-A`**
  (see `Scripts/CLAUDE.md` rule 1b).

## Top-level map

*Sizes measured 2026-08-19; `du` on the Drive mount is slow, so sizes are approximate.*

### LIVE — the pipeline reads or writes these

| Item | Size | Status | What it is |
|---|---|---|---|
| `Scripts/` | 26 MB | live | All code + docs. `pipeline/phase4seg/` is the live engine package. Layout since the 2026-08-31 refactor: `pipeline/` (engine, orchestration, shared installed modules) + `pipeline/builders/` + `pipeline/frozen/` (phase0-3 provenance); `qc/` (tests, ops, VM-exec'd) + `qc/instruments/`. `pip install -e .` once (pyproject.toml) and every shared module imports anywhere. Archived material: `Scripts/docs/ARCHIVE_INDEX.md` -> the `archive/2026-08-pre-refactor` branch |
| `phase4/` | ~100k files | live | Active engine output: `models/ masks/ eval/ qc/`. `qc/` holds the honest numbers (`qc_indep_report.csv`, `live=1` rows) |
| `phase3/` | ~105 GB | live | 2020 base model + full-city 2020 prob/mask. Phase 4 depends on it |
| `Full_Image/` | 1.2 TB | live | Imagery master. `Pipeline Imagery/` = the in-scope rasters (2000–2024; King County, City of Edmonds, Snohomish, NAIP — count and GSD span in `Scripts/STATUS.md`, generated from YEAR_CATALOG) + lidar CHM + C-CAP refs. `KingCo/ USGS/ WA_NAIP/ USDA_NRCS/` = raw source archives |
| `photos/` | 1.4 GB | live | Training-site footprint GeoTIFFs (`Forest_*` / `Negative_*`) |
| `polygons/` | 102 MB | live | Hand-traced crown polygons (EPSG:3857). **Overwritten with accept-all test data; the 14,476-crown review was never finished** — treat as provisional. This is why every queue job passes `--force-citywide` |
| `phase2/` | 12 KB | live | 3 CSVs; `training_site_coverage.csv` is the live one |
| `Reports/` | 36 MB | live | The written deliverables — tracked `.md` + consultant/city source PDFs (PDFs untracked deliberately) |
| `Literature_Tracker.xlsx` | 75 KB | live | The literature ledger — the workbook is the count, never restated |
| `imagery_stats/` | 12 KB | live | `imagery_catalog.csv`, read by one QC script |
| `City Boundry/` | small | live | Edmonds boundary shapefile. **Misspelling is load-bearing** — scripts reference the path |
| `bathology/` | small | live | Waterbody shapefile — actually hydrography; **name kept**, scripts reference it |
| `impervious/` | 4.9 MB | live | `impervious_edmonds.tif` (the clip the scripts read) |
| `Admin/` | 181 KB | live | Business records — not pipeline |

### ARCHIVAL — completed-phase outputs, keep

| Item | Size | Status | What it is |
|---|---|---|---|
| `phase1/` `phase1a/` | 2.2 GB each | archival | Completed Phase-1 deliverables |
| `phase1b/` | 845 MB | archival | Completed Phase-1 deliverable |
| `phase5/` | 3.8 GB | archival, still read | Abandoned forward-experiment; kept because three qc instruments read it |
| `inference/` | 108 GB | archival, keep | `edmonds_crowns_2020.gpkg` — **THE Phase-0 deliverable** (222k crowns) — plus its two DTM tifs |
| `checkpoints/` | ~14 GB | archival | v7 detection-model weights + earlier fold files |
| `labels/` | 346 MB | archival, keep | Distance-transform GeoTIFFs per training site — Phase-0 training targets |
| `TreeCrownInventory.ipynb` | 71 KB | archival | The project's origin notebook, kept for provenance |
| `flicker_viewer/` | 16 MB | archival | Standalone HTML temporal viewers |
| `temporal_overlays/` | 24 MB | archival | One leftover figure |
| `Roads/` | 4.6 MB | unused | Ancillary shapefile |
| `building_footprints/` | 12 MB | legacy | Referenced by legacy config only |

### HELD for Kam's decision

| Item | Size | Status | What it is |
|---|---|---|---|
| `_backup_accept_all/` | 1.9 GB | HELD | Sole pre-accept-all model snapshot (2026-06-22), byte-different from live weights. **Delete only on Kam's explicit call** |

## Archived documents (read via `git show archive/2026-08-pre-refactor:<path>`)

| Doc | Note |
|---|---|
| `archive/2026-08-pre-refactor:Scripts/IMAGERY_PLAN.md` | superseded by `Scripts/WORKPLAN.md` |
| `archive/2026-08-pre-refactor:Scripts/canopy_definition_PROPOSAL.md` | `Reports/CANOPY_DEFINITION_DECISION_2026-08.md` is the ONE live canopy-definition doc |
| `archive/2026-08-pre-refactor:Scripts/honest-measurement-overhaul.md` | superseded 2026-08-19 |
| `archive/2026-08-pre-refactor:Scripts/litwatch_robustness.md` | the CLOSED literature-watch ledger (4,706 lines) |
| `archive/2026-08-pre-refactor:Scripts/scratch/litwatch_scratch/README.md` | litwatch scratchpad (29 instruments, 77 never-re-run writers) |
| `archive/2026-08-pre-refactor:Scripts/_archive/README.md` | the retired-material index; see `Scripts/docs/ARCHIVE_INDEX.md` |

Full archive map: `Scripts/docs/ARCHIVE_INDEX.md`.

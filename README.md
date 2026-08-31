# Edmonds Temporal Tree-Canopy Pipeline

**A tree canopy assessment for Edmonds, WA: a binary canopy mask per aerial acquisition
spanning 2000–2024, anchored to a 2020 hand-annotated dataset. Semantic segmentation.**

Per-crown temporal validity intervals are derived from those masks against a fixed 2020
crown layer. **Instance segmentation is deferred, not cancelled** — Phase 0 produced that
crown layer once, from 2020, and is frozen.

Solo build for the City of Edmonds via the Climate Advisory Board, funded by the
Sustainable Path Foundation.

---

## ▶ Start here — the entry-point chain

1. **[`Scripts/CLAUDE.md`](Scripts/CLAUDE.md)** — the rules and the roadmap of where
   everything lives.
2. **[`Scripts/WORKPLAN.md`](Scripts/WORKPLAN.md)** — **intent**: the goal, the stage
   board, decisions taken, what is waiting on Kam.
3. **[`Scripts/STATUS.md`](Scripts/STATUS.md)** — **facts**: generated from the code and
   the data lake. CI regenerates and diffs it, so it cannot drift.
4. **This README** — the map: what every folder and doc is.

**`Scripts/CHATLOG.md` is append-only history and is no longer read for state.** Its
STATE block is superseded by `WORKPLAN.md`; the file's own header records that STATE
"has become a TRANSCRIPT, not a reference".

**Rule of the repo:** each fact has exactly one home; other docs *link* to it rather than
restate it. A fact written authoritatively in two places is a bug — fix the source, not
the copy. **As of 2026-08-30 that rule is enforced** by `qc/test_docs_match_code.py`,
which runs in CI — because stating it was not enough. It went unenforced long enough for
the bootstrap doc to describe an archive that had not existed for weeks.

---

## Git architecture (re-plumbed 2026-08-20 — see `Scripts/OVERHAUL_PLAN_2026-08-20.md`)

- **The repo lives at `D:\edmonds-pipeline\treedata`** — a normal git working tree on
  local disk. Sessions open in `D:\edmonds-pipeline\treedata\Scripts`. Tags **v001–v048+**.
- **Drive is detached from git and serves data only.** `G:\My Drive\treedata\Scripts\`
  is a FROZEN pre-reorg copy kept as the Colab launch fallback until the cutover proves
  out — never edit it. (Its `.git` pointer file is deleted; the old detached DB
  `D:\edmonds-pipeline\treedata.git` is retained until overhaul P10.)
- **Remotes**: `github` → private `github.com/Kameron-Eck/edmonds-treedata` (the live
  mirror — push `main --tags` after each session; **Kam runs pushes**, Claude's
  permission layer blocks them) and `drive-mirror` → `G:\My Drive\edmonds-git-mirror.git`
  (legacy, retired at P10).
- **`.gitignore` is a whitelist** (`/*`, then re-admit). Tracked: `Scripts/`,
  `phase4/qc/` text outputs, `Reports/*.md` + `*.csv`, `README.md`,
  `Literature_Tracker.xlsx`, a few root files. **Everything else on this list has NO git
  safety net** — imagery, models, rasters, GPKGs are on disk (+ the
  `D:\edmonds-pipeline\backup\` checksum mirror, overhaul P1).
- Parallel sessions may share the working tree: **stage explicit paths, never `-A`**
  (see `Scripts/CLAUDE.md` rule 1b).

---

## Top-level map

*Sizes measured 2026-08-19; `du` on the Drive mount is slow, so sizes are approximate.*

### LIVE — the pipeline reads or writes these

| Item | Size | Status | What it is |
|---|---|---|---|
| `Scripts/` | 26 MB | live | All code + docs. `pipeline/phase4seg/` is the live engine package (layout since 2026-08-20: `pipeline/` engine+drivers, `qc/` measurement, `scratch/`, `_archive/`); `scratch/litwatch_scratch/` has its own README (29 instruments vs 77 never-re-run writers); `_archive/` = retired scripts/docs, own README |
| `phase4/` | ~100k files | live | Active engine output: `models/ masks/ eval/ qc/`. `qc/` holds the honest numbers (`qc_indep_report.csv`, `live=1` rows) |
| `phase3/` | ~105 GB | live | 2020 base model + full-city 2020 prob/mask. Phase 4 depends on it |
| `Full_Image/` | 1.2 TB | live | Imagery master. `Pipeline Imagery/` = the in-scope rasters (2000–2024; King County, City of Edmonds, Snohomish, NAIP — count and GSD span in `Scripts/STATUS.md`, generated from YEAR_CATALOG) + lidar CHM + C-CAP refs. `KingCo/ USGS/ WA_NAIP/ USDA_NRCS/` = raw source archives. (`temp/` was empty, removed; `Image_Scripts/` moved to `Scripts/_archive/Image_Scripts/` — both 2026-08-19) |
| `photos/` | 1.4 GB | live | Training-site footprint GeoTIFFs (`Forest_*` / `Negative_*`) |
| `polygons/` | 102 MB | live | Hand-traced crown polygons (EPSG:3857). **Overwritten with accept-all test data; the 14,476-crown review was never finished** — treat as provisional. This is why every queue job passes `--force-citywide` |
| `phase2/` | 12 KB | live | 3 CSVs; `training_site_coverage.csv` is the live one. The 1.5 GB "Copy of…gpkg" was deleted 2026-08-20 after a measured review — same 222,435 crowns, every column preserved in `phase1a/edmonds_crowns_phase1a.gpkg` |
| `Reports/` | 36 MB | live | The written deliverables — 9 tracked `.md` (measured 2026-08-30; the previous "4" predated five more landing) + consultant/city source PDFs, untracked deliberately |
| `Literature_Tracker.xlsx` | 75 KB | live | The literature ledger — the workbook is the count, not this table (it read "68 papers" against 210 rows / 61 search phases). Git-tracked since 2026-08-19 |
| `imagery_stats/` | 12 KB | live | `imagery_catalog.csv`, read by one QC script |
| `City Boundry/` | small | live | Edmonds boundary shapefile. **Misspelling is load-bearing** — scripts reference the path |
| `bathology/` | small | live | Waterbody shapefile — actually hydrography, not bathymetry; **name kept** because scripts reference it |
| `impervious/` | 4.9 MB | live | `impervious_edmonds.tif` (the clip the scripts read); the 1.48 GB statewide source deleted 2026-08-19 (re-downloadable) |
| `experiments/` | — | live, git-IGNORED | Documented sandbox, own README |
| `Admin/` | 181 KB | live | Business records (contracts, contractor tracking) — not pipeline |
| `.claude/worktrees/` | — | live | Session worktrees. Transient — do not describe specific ones here; they are pruned as sessions end |

### ARCHIVAL — completed-phase outputs, keep

| Item | Size | Status | What it is |
|---|---|---|---|
| `phase1/` `phase1a/` | 2.2 GB each | archival | Completed Phase-1 deliverables |
| `phase1b/` | 845 MB | archival | Completed Phase-1 deliverable |
| `phase5/` | 3.8 GB | archival, still read | Abandoned forward-experiment; kept because `phase4_qc_score.py`, `phase4_qc_indep.py`, `phase4_threshold_diagnostic.py` read it |
| `inference/` | 108 GB | archival, keep | Holds `edmonds_crowns_2020.gpkg` — **THE Phase-0 deliverable** (222k crowns) — plus its two DTM tifs, kept for ready analysis access (Kam, 2026-08-19) |
| `checkpoints/` | ~14 GB | archival | v7 detection-model weights (Feb era) plus earlier unversioned fold files; superseded v5 subfolder deleted 2026-08-19 |
| `labels/` | 346 MB | archival, keep | Distance-transform GeoTIFFs per training site — Phase-0 training targets derived from `polygons/`; regenerable but kept (Kam, 2026-08-19). Not hand labels — those are `polygons/`, `photos/`, and the 2020 mask |
| `TreeCrownInventory.ipynb` | 71 KB | archival | The project's origin notebook, kept for provenance (code extracted to `phase0_instance_seg.py`) |
| `flicker_viewer/` | 16 MB | archival | Standalone HTML temporal viewers, still openable |
| `temporal_overlays/` | 24 MB | archival | One leftover figure |
| `Roads/` | 4.6 MB | unused | Ancillary shapefile |
| `building_footprints/` | 12 MB | legacy | Referenced by legacy config only |
| `NB1NHAP800100076.tif`, `NHAP_1980_Edmonds_TEST.xlsx`, `Georeferenced_Test/` | ~14 MB | out of scope | 1980 NHAP georeferencing trial; project scope is 2000–2024 |

### HELD for Kam's decision

| Item | Size | Status | What it is |
|---|---|---|---|
| `_backup_accept_all/` | 1.9 GB | HELD | Sole pre-accept-all model snapshot (2026-06-22), byte-different from live weights. **Delete only on Kam's explicit call** |

A 2026-08-19 cleanup removed ~37 GB of zero-reference legacy (`temporal_results`,
`phase6`, `clips`, `near_infrared`, `Temp`, `pipeline`, `Scripts_v2`, `tiles`, v5
checkpoints, the statewide `impervious.tif`, stray notebooks, empty dirs). Deleted
items are not listed in the map above.

---

## Data flow

Imagery (`Full_Image`) + labels (`polygons`, `photos`, and the 2020 anchor mask in
`phase3`) → **Colab training** with the `phase4seg` engine → per-year probability and
mask rasters (`phase4/masks`) → **QC / honest scoring** against independent references
(`phase4/qc`; NOAA C-CAP; NDVI+CHM) → **verified numbers**
(`Reports/Edmonds_Verified_Results_2026-08-19.md`) → the city deliverable.

Torch runs on Colab only. The local mirror `D:\edmonds-pipeline\Imagery` (83 GB, curated
per its `MANIFEST.md`, no City-of-Edmonds years) serves fast local QC off the FUSE mount.

---

## Doc map — where each kind of information lives

| Doc | Purpose |
|---|---|
| `Scripts/WORKPLAN.md` | **Intent**: goal, stage board, decisions, what is waiting on Kam |
| `Scripts/STATUS.md` | **Facts**: generated from the code + lake, gated in CI. Never hand-edit |
| `Scripts/WORKPLAN_2026-08-19.md` | Superseded by `WORKPLAN.md` — a dated record of what was planned on 2026-08-19 |
| `Scripts/CHATLOG.md` | Append-only history. **No longer read for state** — that is `WORKPLAN.md`. Logging spec at the top of the file |
| `Scripts/CLAUDE.md` | Session rules, drive layout, mandatory edit rules, how to resume |
| `Scripts/Method_Pipeline.md` | The one home for method, params, tiers, loss, QC design. Rewritten to semantic-only 2026-08-30 |
| `Scripts/pipeline_buildtracker.md` | What's built vs pending, per phase |
| `Scripts/IMAGERY_FACTS.md` | Measured imagery truths (the one home for GSDs, counts, sources) |
| `Scripts/IMAGERY_PLAN.md` | The imagery workstream — open questions and plan |
| `Scripts/canopy_definition_PROPOSAL.md` | The U1 canopy-definition decision. Draft; D2 decided 2026-08-20, D1/D3–D6 open. **Overlaps `Reports/CANOPY_DEFINITION_DECISION_2026-08.md` — two live docs soliciting the same sign-off** |
| `Scripts/honest-measurement-overhaul.md` | **SUPERSEDED 2026-08-19** by the WORKPLAN; kept for provenance only |
| `Scripts/litwatch_robustness.md` | CLOSED literature-watch ledger (4,706 lines) |
| `Scripts/litreview_phase4_prompt.md` | Literature-search prompt template |
| `archive/2026-08-pre-refactor:Scripts/scratch/litwatch_scratch/README.md` | ARCHIVED — the litwatch scratchpad (29 instruments, 77 never-re-run writers) left the working tree 2026-08-31; read via `git show` |
| `archive/2026-08-pre-refactor:Scripts/_archive/README.md` | ARCHIVED — the retired-material index left the working tree 2026-08-31; see `Scripts/docs/ARCHIVE_INDEX.md` |
| `Scripts/edmonds_combined_workplan.xlsx` | The canonical schedule / Gantt / grant milestones (distinct from the WORKPLAN `.md`) |
| `Scripts/pipeline_architecture.html` | Self-contained architecture diagram — double-click to open, no network |
| `Scripts/qc/phase4_accuracy_review.html` | Photo-interpretation review UI for `phase4_accuracy_sample.py --step serve` |
| `Scripts/run_registry.csv` + `phase4/runs/{run_id}/sentinels/` | Colab run history, one row per run + fixed-site snapshot PNGs |
| `Reports/Edmonds_Verified_Results_2026-08-19.md` | The numbers this project will stand behind |
| `Reports/Measurement_Validity_Assessment_2026-08-18.md` | What the numbers can and cannot support (U1–U8) |
| `Reports/Edmonds_Report_Dossier.md` + `Reports/inventory.csv` | City/consultant canopy reports: data + method per report; PDFs alongside |
| `Reports/Edmonds_Canopy_Brief.md` | The short public-facing brief |
| `Literature_Tracker.xlsx` (root) | The literature ledger. Open it for the count — do not restate one here |
| `git log` / `git diff` | Code + doc history and rollback. The working tree **is** the repo and GitHub is the live mirror; `treedata.git` was the old detached DB from the pre-2026-08-20 era and is retired |

Per-session `HANDOFF_*.md` files are **retired** — their role is covered by the WORKPLAN
+ CHATLOG STATE.

---

*This README is the map. Rules → `Scripts/CLAUDE.md`. Intent → `Scripts/WORKPLAN.md`.
Facts → `Scripts/STATUS.md`, generated.*

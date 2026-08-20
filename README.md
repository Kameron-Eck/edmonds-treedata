# Edmonds Temporal Tree-Canopy Pipeline

Machine-learning pipeline mapping individual tree crowns and canopy change across
Edmonds, WA from aerial imagery spanning 2000–2024 (19 in-scope rasters, 4 sources),
anchored to a 2020 hand-annotated dataset. Solo build for the City of Edmonds via the
Climate Advisory Board, funded by the Sustainable Path Foundation.

---

## ▶ Start here — the entry-point chain

1. **[`Scripts/WORKPLAN_2026-08-19.md`](Scripts/WORKPLAN_2026-08-19.md)** — the entry
   point. Verified / withdrawn / blocked / next, reorganised for reading. **It wins on
   any disagreement.**
2. **[`Scripts/CHATLOG.md`](Scripts/CHATLOG.md) STATE block** — the live log: current
   model version, active work, provenance for a specific result.
3. **This README** — the map: what every folder and doc is.

*(The older claim that CHATLOG STATE is "the single source of live truth" is retired —
STATE grew into a transcript; the WORKPLAN is the reference.)*

**Rule of the repo:** each fact has exactly one home; other docs *link* to it rather than
restate it. A fact written authoritatively in two places is a bug — fix the source, not
the copy.

---

## Git architecture

- **Working tree** = `G:\My Drive\treedata` (Google-Drive-synced). **Git DB** =
  `D:\edmonds-pipeline\treedata.git` (off the FUSE mount); the repo's `.git` is a
  pointer file. Tags **v001–v048**.
- **Two remotes** (added 2026-08-19): `drive-mirror` → `G:\My Drive\edmonds-git-mirror.git`
  (bare, Drive-synced) and `github` → private `github.com/Kameron-Eck/edmonds-treedata`.
  **Kam runs `git push --mirror` to both himself** — Claude's permission layer blocks
  push.
- **`.gitignore` is a whitelist** (`/*`, then re-admit). Tracked: `Scripts/`,
  `phase4/qc/` text outputs, `Reports/*.md` + `*.csv`, `README.md`,
  `Literature_Tracker.xlsx`, a few root files. **Everything else on this list has NO git
  safety net** — imagery, models, rasters, GPKGs are on disk only.
- Two sessions share one working tree: **stage explicit paths, never `-A`** (see
  `Scripts/CLAUDE.md` rule 1b). Drive rewrites mtimes, so bare `M` with an empty diff is
  noise.

---

## Top-level map

*Sizes measured 2026-08-19; `du` on the Drive mount is slow, so sizes are approximate.*

### LIVE — the pipeline reads or writes these

| Item | Size | Status | What it is |
|---|---|---|---|
| `Scripts/` | 26 MB | live | All code + docs. `phase4seg/` is the live engine package; `litwatch_scratch/` has its own README (29 instruments vs 77 never-re-run writers); `_archive/` = retired scripts/docs, own README |
| `phase4/` | ~100k files | live | Active engine output: `models/ masks/ eval/ qc/`. `qc/` holds the honest numbers (`qc_indep_report.csv`, `live=1` rows) |
| `phase3/` | ~105 GB | live | 2020 base model + full-city 2020 prob/mask. Phase 4 depends on it |
| `Full_Image/` | 1.2 TB | live | Imagery master. `Pipeline Imagery/` = the 19 in-scope rasters (2000–2024; King County, City of Edmonds, Snohomish, NAIP) + lidar CHM + C-CAP refs. `KingCo/ USGS/ WA_NAIP/ USDA_NRCS/` = raw source archives. (`temp/` was empty, removed; `Image_Scripts/` moved to `Scripts/_archive/Image_Scripts/` — both 2026-08-19) |
| `photos/` | 1.4 GB | live | Training-site footprint GeoTIFFs (`Forest_*` / `Negative_*`) |
| `polygons/` | 102 MB | live | Hand-traced crown polygons (EPSG:3857) — the instance-training labels |
| `phase2/` | 1.5 GB | partly live | Only `training_site_coverage.csv` is live; the 1.5 GB `Copy of edmonds_crowns_phase1.gpkg` is a duplicate, disposition pending |
| `Reports/` | 36 MB | live | The written deliverables — 4 tracked `.md` since 2026-08-18 (Verified_Results, Report_Dossier, Canopy_Brief, Measurement_Validity_Assessment) + 6 consultant/city source PDFs (untracked, deliberately) |
| `Literature_Tracker.xlsx` | 75 KB | live | 68 papers. Now git-tracked (whitelist bug fixed 2026-08-19) |
| `imagery_stats/` | 12 KB | live | `imagery_catalog.csv`, read by one QC script |
| `City Boundry/` | small | live | Edmonds boundary shapefile. **Misspelling is load-bearing** — scripts reference the path |
| `bathology/` | small | live | Waterbody shapefile — actually hydrography, not bathymetry; **name kept** because scripts reference it |
| `impervious/` | 4.9 MB | live | `impervious_edmonds.tif` (the clip the scripts read); the 1.48 GB statewide source deleted 2026-08-19 (re-downloadable) |
| `experiments/` | — | live, git-IGNORED | Documented sandbox, own README |
| `Admin/` | 181 KB | live | Business records (contracts, contractor tracking) — not pipeline |
| `.claude/worktrees/` | — | live | Session worktrees; 12 stale ones pruned 2026-08-19, `ecosystem-cleanup` active |

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
| `Scripts/WORKPLAN_2026-08-19.md` | **Entry point.** Verified / withdrawn / blocked / next; wins on disagreement |
| `Scripts/CHATLOG.md` | STATE block (live, edited in place) + LOG entries (history). Logging spec at the top of the file |
| `Scripts/CLAUDE.md` | Session rules, drive layout, mandatory edit rules, how to resume |
| `Scripts/Method_Pipeline.md` | The one home for method, params, tiers, loss, QC design |
| `Scripts/pipeline_buildtracker.md` | What's built vs pending, per phase |
| `Scripts/IMAGERY_FACTS.md` | Measured imagery truths (the one home for GSDs, counts, sources) |
| `Scripts/IMAGERY_PLAN.md` | The imagery workstream — open questions and plan |
| `Scripts/canopy_definition_PROPOSAL.md` | The U1 canopy-definition decision. **Draft, awaiting Kam's sign-off — blocks Phase 3** |
| `Scripts/honest-measurement-overhaul.md` | **SUPERSEDED 2026-08-19** by the WORKPLAN; kept for provenance only |
| `Scripts/litwatch_robustness.md` | CLOSED literature-watch ledger (4,706 lines) |
| `Scripts/litreview_phase4_prompt.md` | Literature-search prompt template |
| `Scripts/litwatch_scratch/README.md` | The scratchpad's own map: 29 instruments (safe to re-run) vs 77 one-shot writers (never re-run) |
| `Scripts/_archive/README.md` | Index of retired docs, dormant scripts, the 2026-07-08 audit — never current |
| `Scripts/edmonds_combined_workplan.xlsx` | The canonical schedule / Gantt / grant milestones (distinct from the WORKPLAN `.md`) |
| `Scripts/pipeline_architecture.html` | Self-contained architecture diagram — double-click to open, no network |
| `Scripts/phase4_accuracy_review.html` | Photo-interpretation review UI for `phase4_accuracy_sample.py --step serve` |
| `Scripts/run_registry.csv` + `phase4/runs/{run_id}/sentinels/` | Colab run history, one row per run + fixed-site snapshot PNGs |
| `Reports/Edmonds_Verified_Results_2026-08-19.md` | The numbers this project will stand behind |
| `Reports/Measurement_Validity_Assessment_2026-08-18.md` | What the numbers can and cannot support (U1–U8) |
| `Reports/Edmonds_Report_Dossier.md` + `Reports/inventory.csv` | City/consultant canopy reports: data + method per report; PDFs alongside |
| `Reports/Edmonds_Canopy_Brief.md` | The short public-facing brief |
| `Literature_Tracker.xlsx` (root) | 68 academic remote-sensing papers, 8 search phases |
| `git log` / `git diff` | Code + doc history and rollback; DB on `D:\edmonds-pipeline\treedata.git`, tags v001–v048 |

Per-session `HANDOFF_*.md` files are **retired** — their role is covered by the WORKPLAN
+ CHATLOG STATE.

---

*This README is the map. Entry point → `Scripts/WORKPLAN_2026-08-19.md`. Live log →
`Scripts/CHATLOG.md` STATE.*

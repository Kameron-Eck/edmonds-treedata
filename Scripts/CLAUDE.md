# Edmonds Temporal Active Learning Pipeline — Claude Code Instructions

> Read this file at the start of every session, then **read `WORKPLAN_2026-08-19.md`
> FIRST** — it is the entry point / reference and wins on any disagreement — then
> **the STATE block at the top of `CHATLOG.md`** for the live log/state. `../README.md`
> is the map of every doc. Read the live source files before touching any code; do not
> rely on memory or this file for specific parameters — always read the source.

---

## The two planes (the 2026-08-20 overhaul — read this before anything else)

**Code plane:** this git repo, working tree `D:\edmonds-pipeline\treedata`, pushed to
GitHub (`github.com/Kameron-Eck/edmonds-treedata`, private). Sessions open in
`D:\edmonds-pipeline\treedata\Scripts`. Colab **clones the repo** (see
`pipeline/colab_launch.ipynb` once P5 lands) — it does not read code from Drive.

**Data plane:** `G:\My Drive\treedata\` (Colab: `/content/drive/MyDrive/treedata`).
Imagery, models, masks, tiles, QC outputs, logs. **Drive's only job is the data lake.**

Rules that came from Drive-as-working-tree are DEAD: pause-sync before git ops,
phantom-M mtime lore, two-sessions-one-tree hazards. Git ops are normal now.

- **Code and config resolve via `__file__`; data resolves via `BASE`.** Never
  `BASE / "Scripts" / …` again.
- **Authored vs measured text:** docs are authored in this repo; measured outputs
  (`phase4/qc/*`, `Reports/*`, the registry) are produced in the data lake and
  harvested into the repo by script (manual explicit-path copy until
  `harvest_results.py` lands).
- **Deterministic core, agentic shell:** scripts execute; Claude prepares/verifies/
  records; GPU launches are human-paste only; untagged overwrites are refused (P4+).
- **The frozen Drive copy** `G:\My Drive\treedata\Scripts\` is the pre-reorg emergency
  fallback until the Colab cutover proves out. **Never edit it.** Deleted at P10.

**Active plan:** `Scripts/OVERHAUL_PLAN_2026-08-20.md` (per CHATLOG STATE).

---

## Project Purpose

Per-crown temporal validity intervals for 222,435 individual tree crowns across
Edmonds, WA. 18 aerial imagery acquisitions (15 calendar years, 2000–2024).
Outputs binary canopy masks per year (semantic, all 18 years) and per-crown
instance polygons (9 high-resolution years). Anchored to the 2020 hand-annotated
dataset.

**Current active workstream:** the Option A overhaul (see the active plan), riding
alongside Phase 4 — per-year semantic canopy. The model is precise but
**UNDER-predicts** canopy. See `CHATLOG.md` STATE for the live state. Everything hard
here stems from the fact that **only 2020 has real hand labels**; all other years
borrow them.

---

## Sources of truth (one home each)

**The full doc map lives in `../README.md`** — don't restate it here. The homes that
matter before editing:

- **Entry point / reference, wins on disagreement →** `WORKPLAN_2026-08-19.md` (read first).
- **Live log / state →** `CHATLOG.md` **STATE** block (read after WORKPLAN to resume).
- **Method / params / tiers / loss / QC →** `Method_Pipeline.md`.
- **What's built vs pending →** `pipeline_buildtracker.md`.
- **Schedule / decision gates →** `edmonds_combined_workplan.xlsx`.
- **Active plan →** the one plan file named in CHATLOG STATE.
- **The script being edited →** always read it before patching.
- **Imagery catalog + path resolution →** `pipeline/phase4seg/config.py`: `YEAR_CATALOG`
  and `imagery_roots()`. `_archive/scripts/pipeline_config.py` is frozen legacy and NOT
  authoritative. Test with `py -3.12 qc/phase4_catalog_check.py`.
- **Dependency spec →** `requirements-colab.txt` / `requirements-local.txt`; the
  in-script bootstraps must agree with them (same-commit rule).

**One fact, one home.** Each fact has exactly one authoritative location; every other
doc *links* to it rather than restating it. A fact written authoritatively in two places
is a bug — fix the source, not the copy. (Per-session `HANDOFF_*.md` files are **retired**.
Superseded docs live in `_archive/` — never current.)

**Rule: never invent hyperparameters or architectural decisions. If it is not in the
source files, ask before assuming.**

---

## Repo Layout (code plane, since 2026-08-20)

```
D:\edmonds-pipeline\treedata\          ← THE git repo (GitHub = live remote)
├── README.md                          ← doc map (tracked at repo root)
├── Scripts\
│   ├── pipeline\                      ← the pipeline itself: engine + drivers
│   │   ├── phase0_instance_seg.py … phase3_semantic_dev.py
│   │   ├── phase4_semantic_finetune.py   ← THIN SHIM → phase4seg/ (preserves `%run ... --args`)
│   │   ├── phase4seg\                    ← LIVE fine-tune/inference ENGINE package
│   │   ├── phase4_train_queue.py         ← the Colab orchestrator (queue + VERIFY + status CSV)
│   │   ├── phase4_p1_colab_run.py  phase4_build_corrected_labels.py
│   │   ├── phase4_label_review.py ± _prep  make_*.py  fetch_build_chm.py
│   │   ├── pipeline_log.py               ← write_step_log() / StepLogger (logs → phase4/logs)
│   │   └── phase4seg_preflight.py  phase4seg_smoke.py   ← local gates before any Colab run
│   ├── qc\                            ← measurement: 25 phase4_qc_* + catalog_check,
│   │   data_inventory, ref_agreement, accuracy_sample (+ phase4_accuracy_review.html),
│   │   sentinel tools, ccap tools, viz/qa/threshold/miss diagnostics
│   ├── scratch\                       ← litwatch_scratch/ (see its README: 29 instruments
│   │   vs 77 one-shot writers — NEVER re-run writers), merge helpers
│   ├── _archive\                      ← retired scripts/docs (own README) — never current
│   ├── requirements-colab.txt  requirements-local.txt
│   ├── run_registry.csv  sentinel_sites.json  pipeline_architecture.html
│   └── CLAUDE.md  Method_Pipeline.md  CHATLOG.md  WORKPLAN_2026-08-19.md  (all docs at root)
├── phase4\qc\                         ← tracked MEASURED text (harvested from Drive)
└── Reports\                           ← tracked *.md/*.csv (harvested; PDFs untracked)
```

## Data plane (Drive; unchanged except logs)

```
G:\My Drive\treedata\   ==  /content/drive/MyDrive/treedata   (Colab)
├── Full_Image\Pipeline Imagery\      ← orthos, C-CAP refs, CHM (catalog: phase4seg/config.py)
├── phase3\                            ← 2020 base model + citywide mask/prob
├── phase4\  models/ masks/ tiles/ qc/ eval/ labels_corrected/ runs/ …
│   └── logs\                          ← step logs (moved from Scripts/logs 2026-08-20)
├── polygons\  photos\  phase5\ (abandoned; 3 QC scripts still read it)
└── Scripts\                           ← FROZEN pre-reorg copy — fallback only, never edit
```

Local imagery mirror: `D:\edmonds-pipeline\Imagery` (partial — no CoE orthos; QC reads
it first). Backup: `D:\edmonds-pipeline\backup\` (P1 of the overhaul; checksum
manifests). `D:\edmonds-pipeline\treedata.git` = the OLD detached git DB, retired at P10.

- **torch runs on Colab** (local GPU = 4 GB T2000; CUDA works but is never used for
  training). `rasterio`/`geopandas`/etc. pip-install locally on import, so QC,
  label-building, and raster diagnostics **run locally** from the repo.

---

## Phase Architecture

| Phase | Script | Status |
|-------|--------|--------|
| 0 | `pipeline/phase0_instance_seg.py` | Complete — 222k crowns (deps FROZEN-LEGACY; never same runtime as phase3/4) |
| 1–1D | `pipeline/phase1_*` | Complete — 18-year spectral features |
| 2 | `pipeline/phase2_data_prep.py` | Complete |
| 3 | `pipeline/phase3_semantic_dev.py` | Complete — 2020 base, LOSO IoU 0.7299 / AUROC 0.9396 |
| 4 | `pipeline/phase4_semantic_finetune.py` (shim) → `phase4seg/` | **Active.** **Live version + detail live ONLY in `CHATLOG.md` STATE.** |
| 4 (review) | `pipeline/phase4_label_review.py` | Built; the 14,476-crown human review was **never completed** (see Gotchas). |
| 5–8 | — | Not built. phase5/ stays on Drive — 3 QC scripts read it. |

> The per-year fine-tune path has resolution **tiers** (fine ≤15 cm / medium 29.9 cm
> / coarse 50–60 cm) and **two label sources**: coarse years train on the citywide
> 2020 mask; fine/medium years train on per-site crown polygons — but every queue job
> currently passes `--force-citywide` (see Gotchas). See `Method_Pipeline.md`.

---

## Mandatory Rules for Every Edit

### 1. Git is the version system; compile before writing
Work happens in this repo on D:. Commit after every landed change; before a risky edit,
make sure the tree is committed so rollback is one command:
```bash
git status --short                          # ALWAYS first — see rule 1b
git add <the paths you touched> && git commit -m "<what landed>"
```
Tag `vNNN` (annotated) whenever CHATLOG STATE records a new live finetune version.
Then `PYTHONUTF8=1 py -3.12 -m py_compile <script>` before the edit is considered done.
For engine edits, also run `pipeline/phase4seg_preflight.py` (static) and
`pipeline/phase4seg_smoke.py` (CPU runtime) before spending a Colab round-trip.
No sync pauses, ever — the working tree is normal local disk.

**1b. Parallel sessions may share this working tree — stage PATHS, never `-A`.**
`git add -A` once swallowed another session's in-flight work under the wrong message
(`0020f2a`, 2026-08-17). Run `git status --short` immediately before committing, stage
only the paths you edited, and if a file you did not touch shows up dirty, leave it.
For risky/parallel work, worktrees are cheap now — use them.

**1c. Push after each session.** GitHub is the live mirror:
```bash
git push github main --tags
```
**Claude's permission layer blocks push — Kam runs it** (or approves it per-command).
`drive-mirror` (`G:\My Drive\edmonds-git-mirror.git`) is retained until P10; pushing
it is optional and Kam's.

### 2. Log integration
Every script `write_step_log()`s at the end of each `--step` →
`{BASE}/phase4/logs/{script}_{step}_{timestamp}.log` (data plane; old logs remain in
the frozen Drive `Scripts/logs/`). After Colab runs a step, **read the log from
Drive** — do not ask the user to paste terminal output.

### 3. Local-then-copy writes
Large files (GPKG, Parquet, TIF) are written to local NVMe first, validated, then
copied with `shutil.copy2`. Never write large files straight to the FUSE mount.
(Engine enforcement = P4 of the overhaul: verified writes with size+sha256.)

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
NIR years; C-CAP; Olofsson photo-interp for no-NIR years) as primary — never circular
or random-split as the headline. Honest numbers: `phase4/qc/qc_indep_report.csv`,
`live=1` rows only.

### 6. Three-state mask supervision
Masks are 0 (background), 1 (canopy), 255 (IGNORE). Unsure/unreviewed pixels are
IGNORE — never assigned to either class. Corrected-label overlays are **ADD-ONLY**
(may add canopy or IGNORE; must never turn canopy into background).

### 7. Resolution
All segmentation uses **native resolution** — no upscaling. Upsampled imagery is
only for spectral feature extraction under fixed 2020 crown polygons.

### 8. Validity interval semantics
- present@2000 → `valid_from=2000, valid_to=2020`
- absent@2000 → `valid_from=2020, valid_to=2020` (out-of-interval negative)
- unsure/unreviewed → IGNORE (subtract from region polygon)

### 9. Keep the running log current (session-end checklist)
Per landed milestone: **(a)** edit the `CHATLOG.md` STATE block in place, **(b)**
append one LOG entry (caveman style per the file's spec), **(c)** append a row to
`run_registry.csv` if a Colab run landed (generated from manifests once P6 lands),
**(d)** harvest measured text if any landed (manual explicit-path copy from Drive
until `harvest_results.py`), and **(e)** `git add <the paths you touched> && git
commit` — **never `-A`** (rule 1b) — then the rule-1c push (Kam). **Do not create a
new `HANDOFF_*.md`** (retired) or a duplicate plan. Slow-moving docs reconcile only
on phase boundaries or method changes.

---

## Key Data Facts

| Item | Value |
|------|-------|
| Total crowns | 222,435 |
| Training sites | 5 conifer forest + curated negative/positive sites |
| Phase 3 LOSO IoU / AUROC | 0.7299 ± 0.0413 / 0.9396 ± 0.0190 |
| CHM | `lidar_snoh_chm.tif` — USGS 3DEP HAG, ~2016, U8 DN=0.2 m/DN (0=nodata), ~60% city coverage |
| NIR-bearing years | 2016, 2019n, 2021s, 2022n (only these can build an NDVI reference) |
| C-CAP eval ref | `ccap_{2016,2021}_hires_lc.tif` — EVAL-ONLY (never train); 2016 full-coverage variant = `_snohfull` |
| GPU (Colab) | **L4 24 GB** (default/cheapest) · A100 40 GB · RTX PRO 6000 ~95 GB. Memory-plan against the tier actually selected. |
| GPU (local) | 4 GB T2000 — CPU / raster / QC / smoke only, no training |

---

## Current State & Pending Work

**Do not hardcode volatile state here — it rots.** The live "what's next" is the
`CHATLOG.md` **STATE block** + the active plan it names. Read those to resume.

**Gotchas (durable):**
- `polygons/` was overwritten with accept-all test data; the 14,476-crown human
  review was never finished — treat those labels as provisional. This is why every
  queue job passes `--force-citywide`.
- The full-city `phase3/edmonds_canopy_mask_2020.tif` is a **model prediction**, not
  hand truth — it shares the model's blind spots (e.g. deciduous marsh).
- `phase4seg/` (via the shim) is **Colab-only to run** (`fork` start method + torch);
  locally, validate with `phase4seg_preflight.py` + `phase4seg_smoke.py` first.
- `pipeline/phase4seg/config.py` is **pure-move protected**: its constants carry the
  experimental history in comments and feed `_tile_signature` — changing a constant
  triggers a full ~20-min re-tile per year. Never reformat it.
- Data-plane dir names `City Boundry/` and `bathology/` are load-bearing misspellings
  referenced by scripts — never rename.

---

## Compute

| Resource | Use |
|----------|-----|
| Google Colab (L4 default / A100 / RTX PRO 6000) | All tiling, training, inference, heavy I/O — launched from the cloned repo |
| Local machine (4 GB T2000) | Claude Code, script edits, log review, **QC + label-build + raster diagnostics + preflight/smoke** |

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

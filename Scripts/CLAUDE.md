# Edmonds Tree Canopy — Claude Code Instructions

**This file is a ROADMAP and a RULEBOOK. It is deliberately NOT a facts store.**

Facts belong in the code and the measured outputs; this file tells you where they live
and how to re-derive them. That distinction is not stylistic — on 2026-08-29 the facts
table here read *18 acquisitions, 15 calendar years, 4 NIR years* against a catalog
holding **36 / 20 / 10**, and named a NIR year that had not existed for weeks. Every
session had been starting from it. Anything restated here rots; anything derived does not.

Read this file, then **`CHATLOG.md` STATE** (live state), then the active plan STATE names.

---

## 1. What we are building — current priority

**A tree canopy assessment for Edmonds, WA: a binary canopy mask per aerial acquisition,
across the whole archive.** That is the deliverable and the current focus.

**SEMANTIC segmentation only.** The model predicts one class (`classes=1`) — canopy or
not, per pixel. Per-year steps are `labels → tile → train → evaluate → inference →
postproc`. Nothing in the Phase 4 path runs instance segmentation.

**Instance is DEFERRED, not cancelled (Kam, 2026-08-29).** Phase 0 already produced
222,435 crown polygons ONCE, from 2020, and is frozen. Those polygons are a fixed
**lookup geometry**, not a per-year target: `qc/build_validity_intervals.py` scores each
2020 crown against each year's SEMANTIC mask (≥0.5 PRESENT / ≤0.15 ABSENT / between
UNSURE / no data UNOBSERVED) and derives per-crown validity intervals from that ladder.

**The one hard constraint behind every difficulty here:** only 2020 has hand labels.
Every other year is supervised by projecting the 2020 mask onto it, so tree growth,
removal, and — established 2026-08-29 — **seasonal difference** all enter as label error.

---

## 2. Roadmap — where to find context

### 2.1 By question

| You need… | Go to |
|---|---|
| **Live state, what's next** | `CHATLOG.md` **STATE** block, then the plan it names |
| **The active plan** | named in CHATLOG STATE (currently `SEMANTIC_OVERHAUL_PLAN_2026-08-29.md`) |
| **Entry point / reference; wins on disagreement** | `WORKPLAN_2026-08-19.md` |
| **Method, params, tiers, loss, QC design** | `Method_Pipeline.md` |
| **What's built vs pending** | `pipeline_buildtracker.md` |
| **Full doc map** | `../README.md` |
| **Imagery catalog: years, GSD, bands, CRS, paths** | `pipeline/phase4seg/config.py` → `YEAR_CATALOG`, `imagery_roots()`. Test: `py -3.12 qc/phase4_catalog_check.py` |
| **Acquisition DATES + measured effective resolution** | `qc/imagery_pixelsize_and_date.csv` (57 rows, evidence-graded, verbatim source quotes) and `IMAGERY_FACTS.md` |
| **Lidar / CHM facts, coverage** | `IMAGERY_FACTS.md`; `phase4/qc/chm_gap_2016.txt` |
| **Honest scored results** | `phase4/qc/qc_indep_report.csv`, `live=1` rows only |
| **Which arm is the champion for a year** | `pipeline/champion_arms.csv` (1 reader + 5 importers) |
| **What ran, when, on what GPU** | `run_registry.csv`; `phase4/qc/train_queue_status*.csv` (readers merge ALL of them) |
| **Dependency spec** | `requirements-colab.txt` / `-local.txt` — in-script bootstraps must match (same-commit rule) |
| **The script you are about to edit** | the script itself. Always. Never patch from memory. |

### 2.2 Re-derive, don't read from here

```bash
# acquisitions, calendar years, NIR-bearing labels
py -3.12 -c "import sys;sys.path.insert(0,'pipeline');from phase4seg import config as c;\
cat=c.YEAR_CATALOG;print(len(cat),'acquisitions');\
print('NIR:',sorted({e['label'] for e in cat if e['bands']>=4}))"

# GSD span and histogram
py -3.12 -c "import sys;sys.path.insert(0,'pipeline');from phase4seg import config as c;\
from collections import Counter;g=[e['gsd_cm'] for e in c.YEAR_CATALOG];\
print(min(g),'-',max(g),'cm');print(dict(sorted(Counter(g).items())))"
```

### 2.3 The two planes

**Code plane:** this git repo, working tree `D:\edmonds-pipeline\treedata`, pushed to
GitHub (`Kameron-Eck/edmonds-treedata`, private). Sessions open in `Scripts\`. Colab
**clones the repo** — it does not read code from Drive.

**Data plane:** `G:\My Drive\treedata\` (Colab: `/content/drive/MyDrive/treedata`).
Imagery, models, masks, tiles, QC outputs, logs. **Drive's only job is the data lake.**

- **Code and config resolve via `__file__`; data resolves via `BASE`.** Never
  `BASE / "Scripts" / …`.
- **Authored vs measured text:** docs are authored in this repo; measured outputs
  (`phase4/qc/*`, `Reports/*`, the registry) are produced in the lake and harvested here.
- `G:\My Drive\treedata\Scripts\` is a FROZEN pre-reorg copy — fallback only, **never edit**.

### 2.4 Layout, abridged

```
treedata/
├── README.md                     ← doc map
├── Scripts/
│   ├── pipeline/                 ← engine + drivers
│   │   ├── phase4_semantic_finetune.py   ← THIN SHIM → phase4seg/ (preserves `%run --args`)
│   │   ├── phase4seg/                    ← LIVE engine: cli, core, tiling, labels, postproc, config
│   │   ├── phase4_train_queue.py         ← Colab orchestrator (queue + VERIFY + status CSV)
│   │   ├── gen_vm_bootstrap.py  vm_heartbeat.py   ← runtime autonomy
│   │   └── phase4seg_preflight.py  phase4seg_smoke.py   ← LOCAL GATES before any Colab run
│   ├── qc/                       ← measurement + tests (conftest.py blocks lake writes)
│   ├── scratch/                  ← litwatch_scratch/ — see its README: instruments vs
│   │                               one-shot writers. NEVER re-run a writer.
│   └── _archive/                 ← retired. Never current.
├── phase4/qc/                    ← tracked MEASURED text (harvested from the lake)
└── Reports/                      ← tracked *.md/*.csv
```

Data lake: `Full_Image/Pipeline Imagery/` (orthos, C-CAP, CHM) · `phase3/` (2020 base) ·
`phase4/{models,masks,tiles,qc,eval,labels_corrected,logs}` · `polygons/` · `photos/`.
Local imagery mirror `D:\edmonds-pipeline\Imagery` (partial; QC reads it first).
Literature: `D:\edmonds-pipeline\Literture\{ASPP,Labeling,Validation}\`.

### 2.5 Phases

| Phase | Status |
|---|---|
| 0 instance seg | Complete — 222,435 crowns. Deps FROZEN (`smp==0.3.4`); never load in a phase3/4 runtime |
| 1–2 features / prep | Complete |
| 3 semantic base | Complete — 2020 base. Its LOSO metrics are resnet101 numbers; they describe the CURRENT architecture only |
| **4 per-year semantic** | **ACTIVE.** Live version + detail ONLY in CHATLOG STATE |
| 5–8 | Not built |

---

## 3. Essential rules

### 3.1 Git
Commit after every landed change. **`git status --short` FIRST, every time.**

```bash
git status --short                      # always
git add <the paths you touched>         # NEVER -A  (see below)
git commit
```

**Stage paths, never `-A`.** Parallel sessions may share this tree. `git add -A` once
swallowed another session's in-flight work under the wrong message (`0020f2a`). If a file
you did not touch shows up dirty, leave it.

**`main` is Kam's.** Pushing, merging, tagging or resetting `main` is a hard DENY for
Claude — blocked outright, never prompted. Claude may push `work/…` and `fix/…` branches.

**Compile before the edit is done:** `PYTHONUTF8=1 py -3.12 -m py_compile <script>`.
For engine edits also run `phase4seg_preflight.py` (static) **and** `phase4seg_smoke.py`
(CPU runtime) before spending a Colab round-trip.

### 3.2 Never invent
Never invent hyperparameters, architectural decisions, or numbers. If it is not in the
source, **ask**. Read live source files — do not infer from memory or from this file.

### 3.3 One fact, one home
Each fact has exactly one authoritative location; every other doc *links* to it. A fact
written authoritatively in two places is a bug — fix the source, not the copy.

### 3.4 GPU spend gate
Claude may drive Colab runtimes, but **asks Kam before the FIRST launch of each queue**,
stating queue file, GPU tier, runtime count, expected wall-clock and rough cost.

- **Stopping a runtime is always autonomous** — an idle runtime is a defect.
- **Creating a runtime for a queue Kam already approved by name is autonomous**, logged
  in CHATLOG with tier + purpose. Cold creation still asks.
- After a crash Claude may fix on a `fix/…` branch, canary on a small GPU, and rerun
  without asking. `main` never moves without Kam.
- **One queue per runtime.** Concurrency 3–4 (Google throttles above ~5).
- Setup / bootstrap / secrets: `COLAB_AUTONOMY_SETUP.md`.

### 3.5 Honest evaluation only
Effective independent sample size is ~5 forest sites, not tile counts — **LOSO is the
only honest split**; random-split metrics are inflated. Metrics scored against the 2020
mask reprojected onto another year are **CIRCULAR** (real change counts as model error).
Report the **independent** number as primary — never circular or random-split as headline.

**If an effect is smaller than the measured noise floor, report UNDETERMINED, not "no
difference."** That single distinction is what the chm2 lidar test got wrong, twice.

### 3.6 Three-state mask supervision
Masks are **0 background / 1 canopy / 255 IGNORE**. Unsure or unreviewed pixels are
IGNORE — never assigned to a class. Corrected-label overlays are **ADD-ONLY**: they may
add canopy or IGNORE, and must never turn canopy into background. Any new loss term must
be IGNORE-aware or it silently trains on 255.

### 3.7 Native resolution
All segmentation uses **native resolution** — no upscaling. Upsampled imagery is only for
spectral feature extraction under fixed 2020 crown polygons.

### 3.8 Validity interval semantics
- present@2000 → `valid_from=2000, valid_to=2020`
- absent@2000 → `valid_from=2020, valid_to=2020` (out-of-interval negative)
- unsure / unreviewed → IGNORE (subtract from the region polygon)

### 3.9 Local-then-copy writes
Large files (GPKG, Parquet, TIF) are written to local NVMe first, validated, then copied.
Never write large files straight to the FUSE mount.

### 3.10 Colab argparse filtering
Every `main()` filters Colab's injected `-f <json>`. Preserve it in every script you touch.

```python
filtered = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
```

### 3.11 Logging
Every script `write_step_log()`s at the end of each `--step` → `{BASE}/phase4/logs/`.
After Colab runs a step, **read the log from Drive** — do not ask Kam to paste stdout.

### 3.12 Session-end checklist
Per landed milestone: **(a)** edit the `CHATLOG.md` STATE block in place, **(b)** append
one LOG entry (caveman style, per the file's spec), **(c)** append a `run_registry.csv`
row if a Colab run landed, **(d)** harvest measured text if any landed, **(e)** stage the
paths you touched and commit — never `-A`. Kam pushes `main`.
**Do not create `HANDOFF_*.md`** (retired) or a duplicate plan.

---

## 4. Durable gotchas

- **`pipeline/phase4seg/config.py` is PURE-MOVE PROTECTED.** Its constants carry the
  experimental history in comments and feed `_tile_signature`; changing one triggers a
  ~20-min re-tile per year. **Append only. Never reformat or reorder.**
- **`polygons/` was overwritten with accept-all test data.** The 14,476-crown human
  review was never finished — those labels are provisional. This is why every queue job
  passes `--force-citywide`.
- **`phase3/edmonds_canopy_mask_2020.tif` is a model PREDICTION, not hand truth.** It
  shares the model's blind spots (e.g. deciduous marsh).
- **`phase4seg/` is Colab-only to run** (fork start method + torch). Locally, validate
  with preflight + smoke.
- **`City Boundry/` and `bathology/` are load-bearing misspellings** referenced by
  scripts — never rename.
- **Tagged runs tile to `tiles/{year}__{tag}/`** via `common.tile_dir_for()`. The
  untagged legacy `tiles/{year}/` still exists for most years and belongs to nobody —
  reading it silently returns another arm's tiles.
- **The archive spans February to October, and every label comes from an April–July
  2020 flight.** Leaf-off years carry systematic, species-correlated label error, not
  scattered noise. Dates: `qc/imagery_pixelsize_and_date.csv`.
- **Nominal GSD lies.** Use the measured `effective_cm` column — 2005 is nominal
  20.05 cm and resolves at 80.7 cm, coarser than every 30 cm product.
- **Tests must never write to the lake.** `qc/conftest.py` enforces it; a test that
  patched `BASE` alone once destroyed 69 rows of live queue history.

---

## 5. Compute

| Resource | Use |
|---|---|
| Colab **A100 40 GB** | real queue runs — tiling, training, inference, heavy I/O |
| Colab **L4 24 GB / T4** | canaries |
| Colab **RTX PRO 6000 ~95 GB** | only when memory-bound, and ask |
| Local **4 GB T2000** | Claude Code, edits, log review, QC, label build, raster diagnostics, preflight/smoke. **No training.** |

`rasterio`/`geopandas`/etc. pip-install locally on import, so QC and raster work run
locally. Compute-heavy torch runs on Colab. Do not split training between the two.

---

## 6. Working with Kam

- **Terse. Confirm scope before building.**
- **Explain mechanism, not labels.** Narrate what happened and why, in plain language —
  a named bug teaches nothing. Kam wants to learn the system, not be handed verdicts.
- **Say what is measured vs inferred vs assumed**, every time. If something was checked,
  say what was checked. If it wasn't, say that instead.
- **Correct errors plainly and move on.** No preamble, no self-flagellation.
- Paste targeted output (tracebacks), not full stdout — the log system exists for that.

---

*Session bootstrap: stable rules and pointers only. Living state is `CHATLOG.md` STATE
and the plan it names. Doc map: `../README.md`.*

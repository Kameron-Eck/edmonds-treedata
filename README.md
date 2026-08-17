# Edmonds Temporal Tree-Canopy Pipeline

Machine-learning pipeline mapping individual tree crowns and canopy change across
Edmonds, WA from 18 aerial imagery acquisitions (2000–2024), anchored to a 2020
hand-annotated dataset. Solo build for the City of Edmonds via the Climate Advisory
Board, funded by the Sustainable Path Foundation.

---

## ▶ Start here

**For where the project stands right now — current model, active work, next step —
read the STATE block at the top of [`Scripts/CHATLOG.md`](Scripts/CHATLOG.md).**
That is the single source of live truth. Everything else below is slower-moving
reference.

---

## Where each kind of information lives (one home each)

| If you want to know… | Read | Notes |
|----------------------|------|-------|
| **Current state / next step** | `Scripts/CHATLOG.md` — **STATE** block | live truth; edited in place |
| **What happened & why (history)** | `Scripts/CHATLOG.md` — **LOG** entries | newest first; decisions + dead-ends |
| **How the method works** (params, tiers, loss, QC) | `Scripts/Method_Pipeline.md` | the architecture spec |
| **What's built vs pending** (per phase) | `Scripts/pipeline_buildtracker.md` | structural status |
| **Schedule / decision gates / grant milestones** | `Scripts/edmonds_combined_workplan.xlsx` | the canonical Gantt |
| **Session rules, drive layout, how to resume** | `Scripts/CLAUDE.md` | rules + pointers |
| **The plan currently being executed** | the plan file named in CHATLOG STATE | one active plan at a time |
| **Literature / citations** | `Literature_Tracker.xlsx` (repo root) | 68 papers, 8 search phases; academic remote-sensing only |
| **City of Edmonds canopy reports** | `Reports/Edmonds_Report_Dossier.md` + `Reports/inventory.csv` | municipal/consultant reports: data + method per report; PDFs alongside |
| **Code/doc history & rollback** | `git log` / `git diff` (repo DB on `D:\edmonds-pipeline\treedata.git`) | tags v001–v044; see CLAUDE.md rule 1 |
| **Colab run history** | `Scripts/run_registry.csv` + `phase4/runs/{run_id}/sentinels/` | one row per run; fixed-site snapshot PNGs |

**Rule of the repo:** each fact has exactly one home; other docs *link* to it rather
than restate it. A fact written authoritatively in two places is a bug — fix the
source, not the copy.

---

## Directory map (short)

```
treedata/
├── README.md                 ← you are here (the front door)
├── Scripts/                  ← all code + docs (see CLAUDE.md for the full layout)
│   ├── CLAUDE.md  CHATLOG.md  Method_Pipeline.md  pipeline_buildtracker.md
│   ├── edmonds_combined_workplan.xlsx
│   ├── phase0…phase4 *.py, phase4_qc_*.py, make_*.py, fetch_build_chm.py …
│   ├── phase4seg/            ← the live Phase-4 engine package (phase4_semantic_finetune.py = shim)
│   └── _archive/             ← superseded docs + dormant scripts + the 2026-07-08 audit — NOT current
├── Literature_Tracker.xlsx   ← academic literature (68 papers, 8 search phases)
├── Reports/                  ← City of Edmonds canopy reports: dossier, inventory.csv, source PDFs
├── phase1/ … phase4/         ← per-phase outputs (models, masks, eval, qc, …)
├── polygons/  photos/        ← crown labels + training-site footprints
└── Full_Image/Pipeline Imagery/   ← orthos + lidar_snoh_chm.tif
```

Retired handoff notes, the old (Phase-4/5-swapped) workplan, 53 dormant pre-Phase-0
scripts and the completed 2026-07-08 codebase audit live in `Scripts/_archive/`
(indexed by `Scripts/_archive/README.md`) for history only — not current.

---

## Retired / consolidated (2026-07-06)

The per-session `HANDOFF_*.md` files were **retired** — their role (current narrative)
is now covered by CHATLOG STATE + the active plan file. The duplicate
`Admin/Tree Project Work Plan.xlsx` (old scheme) was archived; the canonical schedule is
`Scripts/edmonds_combined_workplan.xlsx`.

*This README is the map. Live state → `Scripts/CHATLOG.md` STATE.*

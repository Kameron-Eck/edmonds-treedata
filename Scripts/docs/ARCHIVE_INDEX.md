# Archive index — what left the working tree on 2026-08-31, and how to read it

Everything listed here is preserved **byte-identical** on the snapshot branch
`archive/2026-08-pre-refactor` (created at commit `46a340e` of `work/20260824-sectors`,
before any deletion). Nothing was destroyed; it left the working tree so the live
pipeline fits in a reader's context.

```
git show archive/2026-08-pre-refactor:<old-path>          # read one file
git diff work/20260824-sectors archive/2026-08-pre-refactor -- <old-path>
```

**Why a plain branch, not a second repo:** history already holds every byte of every past
commit; the branch pins those objects against garbage collection forever, needs no second
remote or auth, and cannot disturb `main`.

## What is archived

| Old path | What it was | Why archived |
|---|---|---|
| `Scripts/_archive/` (78 files) | Retired scripts, the 2026-07-08 audit, old handoffs. Contains 2 known SyntaxErrors. | Already retired; its own README said "never current". |
| `Scripts/scratch/litwatch_scratch/` (228 files) | 106 one-shot instruments/writers + 104 cached search JSONs for the literature-watch ledger. **77 of the writers are non-idempotent and must NEVER be re-run** — archiving makes an accidental re-run impossible. | Historical record of runs already made. |
| `Scripts/scratch/` one-shots (15 files) | Date-campaign builders and superseded probes (e.g. `imagery_pixelsize_date_build.py`, which built the date table). | Outputs are harvested and tracked; the builders are records. |
| `Scripts/litwatch_robustness.md` (4,707 lines) | The literature-watch ledger — its own header says CLOSED. The 70 `upd*.py` generators that appended to it are in litwatch_scratch above. | Closed ledger. |
| `Scripts/CHATLOG.md` body (lines 41–4,015 pre-rotation) | The 1,489-line STATE transcript + every LOG entry 2026-06-29 → 2026-08-29. | STATE superseded by `WORKPLAN.md` (2026-08-30); the stub in `Scripts/CHATLOG.md` keeps the newest entry and stays the valid append target (CLAUDE.md §3.12). |
| `Scripts/qc/imagery_date_evidence/` (47 files, 1.57 MB) | **Non-regenerable** external evidence capture behind the acquisition-date table: URL listings, Azure NAIP XML, weather records, shadow-dating JSON, a scanned flight-date JPEG. Includes the repo's two largest tracked files. | The CONCLUSIONS live on in `Scripts/qc/imagery_pixelsize_and_date.csv` + `IMAGERY_FACTS.md`; the raw capture is evidence custody, exactly what a snapshot is for. |
| `Scripts/pipeline/queue_*.yaml` (historical, ~28) | Completed experiment arms (noise, corruption curve, groves, golden-gate, seeds, sectors…). The runs they drove are in `run_registry.csv` and the status ledger. | Spent. Active queues (`pilot_2019_*`, live sector queues) remain in `Scripts/pipeline/`. |
| Dated planning docs (~13 at `Scripts/` root) | `OVERHAUL_PLAN_2026-08-20.md`, `MACHINERY_AUDIT_2026-08.md`, `honest-measurement-overhaul.md`, the dated `IMAGERY_*` plans, `canopy_definition_PROPOSAL.md`, … | Each is superseded by its own banner or by `WORKPLAN.md`. |

## What deliberately did NOT move

- `phase4/qc/` — the measured-findings ledger. Actively appended; `sample_*.csv` holds
  irreplaceable human photo-interpretation.
- The 9 gated docs, `COLAB_AUTONOMY_SETUP.md`, `WORKPLAN_2026-08-19.md` (named authority).
- `run_registry.csv`, the harvested QC tables, and everything a generator maintains.
- All live code: `pipeline/`, `qc/`, the engine, tests.

*The archive branch is local until Kam pushes it — pushing branches that are not
`work/…`/`fix/…` is his call.*

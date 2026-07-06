> **SUPERSEDED 2026-07-05 (corrected-label session).** The under-prediction fix pivoted:
> instead of the 2015-flagship substitution + a 2020-mask-derived marsh positive site (both
> below), the approved direction is to **invert the QC instrument** — use the 2016 NIR+CHM
> signal to *label* the missed canopy (ADD-ONLY overlay on the coarse 2020-mask path). Live
> script = **v042** (`--add-canopy-mask`); builder = `phase4_build_corrected_labels.py`;
> active plan = `D:\tools\claude-config\plans\drifting-swinging-dolphin.md`. Read CHATLOG STATE
> + the top LOG entry first. The honest-recall findings below still stand; only the fix changed.

# HANDOFF 2026-07-05 (QC) — honest recall instrument built; under-prediction diagnosed

**Supersedes `HANDOFF_2026-07-05_RESOLVED.md`** (that one closed the 2016 CHM "collapse";
this one opens the under-prediction workstream). Read this, then `CHATLOG.md` STATE + top 3
entries. Plan: `D:\tools\claude-config\plans\enchanted-orbiting-lecun.md`.

Conventions unchanged: scripts on `G:\My Drive\treedata\Scripts\` (edit in place). Training/
inference is **Colab-only** (local GPU 2 GB). **Imagery now mirrored locally at
`D:\edmonds-pipeline\Imagery`** — QC/diagnostics run LOCALLY from D: (rasterio/geopandas/
shapely/fiona pip-install on import; torch does NOT). `py -3.12 -m py_compile` (PYTHONUTF8=1)
before any edit. `version_script.py` before editing a PHASE script. Log to `CHATLOG.md`.

---

## The problem (user framing)

Precision is good; the model **UNDER-predicts** canopy — misses real tree patches, worst in
**2000 and 2016** (e.g. Edmonds marsh deciduous trees). Fix recall **without losing precision**.
Circular 2020-derived labels can't measure recall honestly → build a model-independent instrument.

## What was built this session (all local, torch-free)

Three QC scripts + one site-staging script; outputs under `phase4/qc/`:

- **`phase4_qc_ndvi.py`** — independent canopy reference from NIR: `canopy = NDVI≥0.2 AND
  CHM≥2 m` (excludes grass). 2016 uses its OWN NIR band and the temporally-matched 2016 CHM →
  cleanest instrument. Output `phase4/qc/ndvi_ref_{year}.tif` (0/1/2/255) + `.txt` summary.
- **`phase4_qc_score.py`** — scores the model prob raster vs the reference (prob & ref share the
  year's grid → direct pixel confusion). Reads the deployed op-threshold from the eval CSV.
  Output `phase4/qc/qc_report.csv` (separate from the circular `semantic_eval_report.csv`).
- **`phase4_qc_site.py`** — lat/lon window diagnostic; cross-tabs missed (FN) canopy by CHM
  height + NDVI. Output `phase4/qc/sites/{name}_{year}.{png,txt}`.
- **`make_positive_site.py`** — stages a POSITIVE training site with crowns **derived by
  polygonising the phase3 2020 mask** inside the footprint (safe staged → `--commit`).

## Key findings (2016)

| Metric | Circular (2020 labels) | **Honest (NDVI+CHM)** |
|---|---|---|
| Recall | 0.94 | **0.605** |
| Precision | 0.81 | **0.97** |

- Model calls 23.5% canopy; independent reference says 37.7% (matches the known ~40% prior →
  reference calibrated, not inflated). **+14.2 pp under-prediction.** FN = 201 M px.
- **Threshold is NOT the lever:** sweep gains only +2.6 pp recall from 0.50→0.20. Misses are
  confident/structural.
- **Marsh (122.3837°W 47.8027°N):** recall 0.70, precision 0.98; **60% of misses are >5 m tall**
  with mean NDVI ~0.48 → real tall green trees = **out-of-distribution DECIDUOUS canopy** the
  conifer-only training sites never taught the model. 2015 imagery there is leaf-off (a second,
  phenology mechanism).
- **2000** (no NIR): muddier — 60% of tall px not called canopy mixes OOD + RGB radiometric
  drift + genuine pre-2020 change → needs photo-interpretation, not CHM.

## Mechanism facts that constrain the fix (verified in code)

- **2016 is a COARSE year** → trains on the citywide 2020 mask (marsh labeled but rare); curated
  positive sites are ignored on that path. **2015 is FINE** → trains on per-site crown polygons
  (only conifer `Forest_*` → marsh absent). ⇒ a marsh positive site helps 2015 + other fine
  years; the "2016 deciduous" fix is really *produce the ~2016 map from the 2015 flagship + marsh
  site*.
- A positive site **without** a crown-polygon file is silently demoted to a NEGATIVE and burns
  real canopy as background — never drop a bare crop into `photos/`. `make_positive_site.py`
  derives the crowns to avoid this.

## STAGED, awaiting user review (NOT committed)

`Positive_Marsh` — 700 m box @ (-122.3837, 47.8027), **333 derived crowns, 19.8 ha**, valid
2005–2020. Files in `photos/_positive_staging/`, `polygons/_positive_staging/`; preview
`phase4/eval/positive_site_preview_Positive_Marsh.png` (verified: outlines match real canopy).
QC artifact: https://claude.ai/code/artifact/cd2a1bbd-8173-43a2-9a84-93217474ae52

## Next steps (in order)

1. **USER: review the marsh preview** → `make_positive_site.py --name Positive_Marsh --commit`.
2. **Colab: 2015 flagship run** with the committed marsh site — `--year 2015 --step labels →
   tile → train → inference → postproc → evaluate --hs-source chm`. Confirm band-4 `source=chm`.
3. **Score the lift:** `phase4_qc_ndvi.py --year 2016` already done; after 2015 inference, run
   `phase4_qc_score.py` and `phase4_qc_site.py` (marsh) on the 2015 product vs the 2016 NDVI
   reference — expect recall > 0.60 with precision held (grass rejection ~0.98).
4. **2000:** build `phase4_qc_photointerp.py` (Olofsson stratified points + area-adjusted CIs) —
   the honest recall instrument for the no-NIR year. Then CHM-as-prior-not-veto + radiometric
   normalization (plan Phase C).
5. **Precision guard after every recall change:** grass rejection stays ~0.98, precision vs NDVI
   does not fall — else reject the change.

## Don't redo / already correct
- The v039 sampler/metric/BN/Phase-B fixes (see the RESOLVED handoff) — validated, don't revert.
- The NDVI reference is calibrated (37.7% ≈ the ~40% prior). The marsh derived labels look correct.
- Threshold-tuning as the 2016 fix — refuted by the flat sweep.

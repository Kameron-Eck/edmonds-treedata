# Plan — Honest Measurement Overhaul (Phase 4 evaluation)

**Status:** ACTIVE — opened 2026-08-17. Named by `CHATLOG.md` STATE.
**Goal:** replace "the AI says it's fine" with numbers Kam can defend, and visuals that
show where the model actually fails. Four phases; order = 1 → 2 → 4 → 3.

---

## 0. Baseline — where the model stands TODAY (measured, not asserted)

Independent reference = NOAA C-CAP hi-res (never trained on). Primary canopy
definition = `forest_wetland`, each year at its deployed operating threshold.
Source: `phase4/qc/qc_indep_report.csv`.

| year | prob raster | recall | precision | grass reject |
|------|-------------|--------|-----------|--------------|
| 2016 | native (NIR era)   | 0.684 | 0.865 | 0.935 |
| 2013 | xsensor_rgb        | 0.709 | 0.855 | 0.917 |
| 2015 | xsensor_rgb        | 0.622 | 0.884 | 0.947 |
| 2000 | xsensor_rgb        | 0.630 | 0.775 | 0.840 |
| 2002 | xsensor_rgb        | 0.507 | 0.838 | 0.921 |
| 2017 | xsensor_rgb        | — FAILED RUN, see P1 |

vs the NDVI+CHM reference, 2016: recall 0.594 / precision 0.959.

**Read:** high-precision, low-recall canopy detector. Misses ~30–35% of reference
forest (2002: ~half). The miss is STRUCTURAL, not a threshold artifact — the 2016
sweep only moves recall 0.669 → 0.747 across the whole 0.5 → 0.2 range. Scrub
recall is 0.25 vs forest 0.68 → failure concentrates on non-conifer / lower /
mixed-structure vegetation. Matches the known conifer-only-label blind spot.

**Caveat that must ride with every number above:** both references are PROXIES.
CHM is ~2016 vintage at ~60% city coverage; C-CAP is a 1 m generalized product from
2016/2021 applied to 2000/2002/2013 imagery. An unknown share of that 30% gap is
reference error + real land-cover change, NOT model error. Phase 2 bounds it;
Phase 3 measures it.

---

## Phase 1 — Trust the instruments  (local, no GPU)

The QC layer currently fails silently. Three confirmed defects:

1. **2017 inference is a failed run, not a scorer bug.**
   `edmonds_canopy_prob_2017_xsensor_rgb.tif` (EPSG:3857, 211968×148736) is
   **96.5% nodata**, and where valid, probabilities are collapsed near zero
   (DN 7–15 ≈ p 0.03–0.06). CRS/bounds are correct and DO overlap C-CAP — the
   raster content is the problem. `phase4_qc_indep.py` wrote `nan` + `0 valid px`
   instead of raising.
2. **`edmonds_canopy_prob_2022_xsensor_train.tif` is 0 bytes** — silent write failure
   sitting in `phase4/masks/`.
3. **Stale rows in the headline CSVs.** `qc_report.csv` has 4 rows for 2016 (2 of
   them NaN); `qc_indep_report.csv` carries a superseded 2015 run at recall 0.257
   next to the live 0.62 xsensor run, with nothing marking which is current.

**Work:**
- [ ] `phase4_qc_indep.py` + `phase4_qc_score.py`: **fail loudly**. Abort with a clear
      message when valid-overlap px is 0, or when the prob raster's valid fraction is
      below a floor (`--min-valid-frac`, default 0.5). Never write a NaN row.
- [ ] Add a `run_tag` + `superseded` column to both QC CSVs; add a small helper that
      marks prior rows for the same (year, ref, canopy_def) superseded on new write.
      One live row per year, queryable.
- [ ] Sweep `phase4/masks/` for zero-byte and mostly-nodata rasters; report a manifest
      (`phase4/qc/mask_inventory.csv`: year, tag, size, valid-frac, CRS, bounds).
- [ ] **COLAB SESSION (one run covers both):** re-run 2017 inference AND produce a
      citywide 2022 prob raster. 2022 is a **Phase 3 blocker** — see below; batching it
      here means Phase 3 never stalls waiting on GPU.
- [ ] Re-run 2017 inference on Colab; re-score. Investigate the near-zero-probability
      collapse — likely the same class of bug as the v044 inference OOM (empty/partial
      prob raster), so check the inference log first before re-running blind.

**Exit:** every year in `qc_indep_report.csv` has exactly one live, non-NaN row, or an
explicit recorded reason it cannot be scored.

---

## Phase 2 — Reference disagreement map  (local raster op)

Neither reference is truth, so stop treating disagreement with them as model error.

**Work:**
- [ ] New `phase4_ref_agreement.py`: score NDVI+CHM ref against C-CAP directly on the
      NIR years (2016 first), on the common valid footprint.
- [ ] Partition every pixel into: **both-canopy**, **both-non-canopy**, **refs disagree**.
- [ ] Re-score the model within each partition. Deliverables:
      - recall/precision on the **both-agree** subset = high-confidence honest number
      - the fraction of the current 30% "miss" that lands in **refs-disagree** =
        the unmeasurable band, excluded rather than blamed on the model
- [ ] Write `phase4/qc/ref_agreement_{year}.txt` + `.csv` in the existing QC report style.

**Exit:** the headline gap is split into *real miss* / *unmeasurable*, with a number on each.

---

## Phase 4 — Visuals  (local; do BEFORE Phase 3 per Kam)

Read `phase4_viz.py` (314 L), `phase4_qa_overlay.py` (381 L), `phase4_sentinel_snap.py`
(244 L) FIRST — much of this may already exist; extend rather than duplicate.

**Work:**
- [ ] Per-year TP / FN / FP overlay rasters at the fixed `sentinel_sites.json` sites, so
      the same ground is eyeballed every year. Colour-code against the Phase-2 partition
      (real miss vs unmeasurable) rather than raw FN.
- [ ] One summary dashboard: recall / precision / model canopy-fraction across all 18
      years, with reference provenance + caveat attached to each point (NIR vs no-NIR,
      C-CAP vintage distance, xsensor vs native).
- [ ] Keep the existing `forest_miss_*` stand-shortlist outputs wired in — they already
      answer "which stands".

**Exit:** Kam can look at one page and one image strip and say where the model fails.

---

## Phase 3 — Human ground truth, no model in the loop  (the real deliverable)

**Scope (Kam's call, 2026-08-17): 250 points × 3 years — 2000, 2016, 2022.**
~5 hrs labeling. Gives a temporal trend and tests whether accuracy degrades on
no-NIR / off-sensor years, accepting wider CIs per year than a single-year 400.

Olofsson-protocol stratified random sample. This is the ONLY measurement in the
pipeline where neither a model nor a proxy product sits between Kam and the answer.

**BLOCKER — 2022 has no citywide prob raster.** `phase4/masks/` holds only the
0-byte `edmonds_canopy_prob_2022_xsensor_train.tif`. The sample design stratifies by
model output, so `--step design` for 2022 CANNOT run until a citywide 2022 inference
lands. Batched into the Phase 1 Colab session alongside the 2017 re-run — verify that
raster exists before starting Phase 3. (2000 and 2016 are on disk and unblocked;
2019 likewise has only a partial `_xsensor_train` raster if it is ever substituted in.)

**Work:**
- [ ] New `phase4_accuracy_sample.py`. **Reuse the `phase4_label_review.py` server
      pattern** (no-Flask ThreadingTCPServer, crop JPEGs + manifest, Present/Absent/
      Unsure) — do not write a new web stack.
- [ ] `--step design`: stratified random points per year, strata = model output
      (canopy / non-canopy / **near-threshold**), with stratum weights recorded for
      unbiased estimation. Fixed seed, written to `phase4/qc/sample_{year}.gpkg`.
- [ ] `--step serve`: Kam photo-interprets each point against that year's ortho.
      Unsure is a first-class option and is EXCLUDED from estimation, never coerced.
- [ ] `--step estimate`: Olofsson stratified estimators → unbiased recall, precision,
      and **canopy AREA with 95% confidence intervals**. Output
      `phase4/qc/accuracy_{year}.txt` + a combined `accuracy_report.csv`.
- [ ] Cross-tab the 2016 sample against C-CAP → **calibrates how wrong C-CAP itself is**,
      which retro-corrects every Phase-0/2 number in this document.

**Exit:** three defensible per-year accuracy + area figures with CIs, and a measured
error rate for the C-CAP reference.

---

## Rules this plan honors

- Honest evaluation only (CLAUDE.md rule 5) — no circular 2020-label metrics, no
  random-split numbers as headline. LOSO / independent ref / human sample only.
- Three-state supervision (rule 6) — Unsure → IGNORE, never coerced to a class.
- QC / label-build / raster work runs LOCAL off `D:`; only inference re-runs go to Colab.
- Session-end checklist (rule 9): CHATLOG STATE edited in place + one LOG entry +
  `run_registry.csv` row if a Colab run lands + git commit.

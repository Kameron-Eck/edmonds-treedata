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
<!-- 2016 = 0.6821 full-forest. Any 0.7623 you see in forest_miss_2016.txt is a
     stable∩2021 SUBSET, not comparable — see P1b. -->

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
- [x] **DONE 0020f2a** `phase4_qc_indep.py` + `phase4_qc_score.py`: **fail loudly**. Abort with a clear
      message when valid-overlap px is 0, or when the prob raster's valid fraction is
      below a floor (`--min-valid-frac`, default 0.5). Never write a NaN row.
- [x] **DONE 0020f2a** (shipped as `live` + `run_tag`; both CSVs migrated, backups kept) Add a `run_tag` + `superseded` column to both QC CSVs; add a small helper that
      marks prior rows for the same (year, ref, canopy_def) superseded on new write.
      One live row per year, queryable.
- [x] **DONE** `phase4_qc_inventory.py` -> `qc/mask_inventory.csv` (d6c69b4). Real problems = 2: prob_2017_xsensor_rgb (MOSTLY_NODATA), prob_2015_citywide_rgb (SUSPECT_PARTIAL). Sweep `phase4/masks/` for zero-byte and mostly-nodata rasters; report a manifest
      (`phase4/qc/mask_inventory.csv`: year, tag, size, valid-frac, CRS, bounds).
- [ ] **BLOCKING / IN PROGRESS — first attempt FAILED 2026-08-17 (~4h, zero output; registry 20260817_p1_driver_abort). Driver rewritten 9c205ab/3be1faa; stage 1 retargeted to 2022n. NOT YET RE-RUN.** **COLAB SESSION — driver: `phase4_p1_colab_run.py`** (L4 24 GB; `--stage 0` first,
      it is free and can veto).
      - stage 1 — **2022n** (60 cm NAIP, 0.1 Gpx, carries NIR). **Phase 3 blocker.**
        NOT inference-only: no 2022n checkpoint exists, so this runs the FULL
        labels->tile->train->evaluate->inference path (~20-30 min train, by analogy
        with 2002=27.7 min / 2022=20.7 min). Chosen over label `2022`
        (2022_coe_rgb.tif, 7.5 cm, 31.5 Gpx, 25.2 GB ortho) which is ~300x costlier;
        60 cm also matches 2000's 59.7 cm, making the Phase-3 trend like-for-like.
      - stage 2 — **2017** citywide, costly/fine. Replaces the 96.5%-nodata failed run.
      - stage 3 — **2015** citywide, costly/fine. Replaces `edmonds_canopy_prob_2015_
        citywide_rgb.tif` (7.4% valid vs 90.8% for siblings on the SAME grid — an
        unfinished run, found by `phase4_qc_inventory` SUSPECT_PARTIAL 2026-08-17).
        Lowest priority: the live 2015 QC row uses `_xsensor_rgb`, so nothing currently
        quoted depends on it. Note this stage OVERWRITES the broken file by design.
- [ ] Re-run 2017 inference on Colab; re-score. Investigate the near-zero-probability
      collapse — likely the same class of bug as the v044 inference OOM (empty/partial
      prob raster), so check the inference log first before re-running blind.

**Exit:** every year in `qc_indep_report.csv` has exactly one live, non-NaN row, or an
explicit recorded reason it cannot be scored.

### P1b — PROVENANCE IS MANDATORY  (found 2026-08-17 auditing "can I trust forest_miss")

**Defect:** `phase4_qc_forest_misses.py::_report()` (~L388) omits `stable_path` from the
per-year report header. `analyse()` prints it to stdout (L209) and `_write_compare()`
records it (L511) — the per-year `.txt` does not.

**Consequence:** `forest_miss_2016.txt` reports `forest px 309,338,104 / RECALL 0.7623`.
That run used `--stable-with ccap_2021` (proven by `forest_miss_sensor_compare.txt`
header: `stable∩ccap_2021_hires_lc.tif`), so forest = C-CAP forest in BOTH 2016 AND
2021 = a 78% "stable" SUBSET. Its own run logs
(`logs/phase4_qc_forest_misses_2016_*.log`) say `recall=0.6821 tp=268789495` — full
forest, matching `qc_indep`. Two contradictory numbers, same script, same session,
indistinguishable from the artifacts.

**HONEST 2016 RECALL = 0.6821**, not 0.7623. Independently confirmed: decimated
(ds=16) recompute → 0.6832, denominator 1,538,657 × 16² = 394M = qc_indep exactly.

**Also disproven:** the hypothesis that `qc_indep` is pessimistic for lacking an
imagery-footprint mask (it defines valid as `(gid != ignore_id) & (pr != 255)`, L268,
never opening the imagery, while forest_miss adds `cover = (r+g+b) > 0`, L249).
Tested: **0 px dropped** — the 2016 ortho has no blank regions inside C-CAP forest.
`qc_indep` is CORRECT. Do not "fix" it.

- [x] **DONE e9de54b/0020f2a** `_report()` must print every mask-narrowing parameter (stable_path, forest_codes,
      thresh, cover rule) into the per-year `.txt` AND `.csv`. No silent denominators.
- [ ] Re-run the per-year `forest_miss_*` WITHOUT `--stable-with` so the autopsy is on
      the same full-forest denominator as `qc_indep`, or emit both and label them.
- [ ] Audit the other `forest_miss_{2000,2002,2013,2015}.txt` the same way — the
      sensor_compare table used stable∩2021, so those per-year files are suspect too.

### P1c — the "structural miss" claim does NOT generalize (correct the record)

`conf%` = fraction of missed forest with prob < 0.12, from `forest_miss_sensor_compare.txt`:

| year | recall | conf% |
|------|--------|-------|
| 2016 | 0.76 (stable subset) | **~60%** |
| 2000 | 0.6803 | 24.1% |
| 2002 | 0.6825 | 19.4% |
| 2013 | 0.7333 | **9.3%** |

2016's deep-confident-miss profile is an OUTLIER. For 2013, 91% of misses sit between
0.12 and threshold → **near-threshold and potentially recoverable by calibration**, NOT
the out-of-distribution structural miss diagnosed for 2016. CONFOUND: 2016 is a native
NIR-era raster, the other three are cross-sensor RGB — recipe/sensor is tangled with
year, as sensor_compare's own closing note warns.

- [ ] Recompute the miss-depth histogram per year on the FULL-forest denominator, one
      recipe (`--force-citywide` rasters), before concluding labels-vs-calibration.
      This decides the NEXT workstream after P1–P4 — do not commit to hand-tracing
      stands on 2016's number alone.

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

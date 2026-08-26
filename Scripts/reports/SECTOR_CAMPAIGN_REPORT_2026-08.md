# Sector Campaign — Report (2026-08)

Campaign: `sector_campaign_v1`, branch `work/20260824-sectors`, 2026-08-24 → 2026-08-26.
Design: `reports/sector_campaign_design.md`. Executable spec: `pipeline/sector_campaign_checklist.yaml`.
Execution ledger: `data:phase4/qc/sector_campaign/state_20260825T044145Z.jsonl` + `RESUME_NOTES.md`.

Every number below is quoted from a CSV/JSON on disk, with its reference and operating point
attached, or derived from those values and labelled as derived. Where a number comes from a
series/matrix currently being regenerated with the
fullext arms, it is either labelled **pre-fullext run** (the value on disk, citable as such)
(All former [[PENDING-REGEN]] placeholders were filled 2026-08-26 after the regeneration completed. Nothing in this report is provisional.)

---

## 1. Executive summary

**What was built.** A sampled-inference harness: five west–east sector strips (`sectors_v1`)
stand in for the whole city — `pipeline/make_sectors.py`, `pipeline/aoi/sectors_v1.json`, an
`--infer-aoi` mode in `phase4seg/{config,cli,core}.py`, two queue YAMLs, an autonomous executor
(`qc/sector_campaign_loop.py`), a design-based estimator (`qc/phase4_sector_series.py`) and a
per-crown cover matrix (`qc/phase4_crown_cover_matrix.py`).

The strips hold **563.0 ha of land** (sector ∩ city − water, true ground area) out of the city's
**2,285.6 ha** — **24.6% of the land**, but only **10.7%–16.7% of each year's raster pixels**
(measured VERIFY valid fractions), because the raster grid also carries water, out-of-city area
and bounding-box margin. Both denominators are stated so neither can be quoted loose. The
measured inference cut is **~6–9×**, against the design note's predicted "~10×".

**What ran.** Eight arms, all VERIFY OK, all scored against epoch-matched C-CAP through
`qc/phase4_qc_indep.py`, postprocessed to masks + GPKGs, and folded into the series and matrix:

- **6 base2020 baseline arms** — 2003s, 2006s, 2011s, 2012s, 2018s, 2020s, tag `sectors_v1`.
  Not fine-tunes: the checkpoint is a byte-for-byte copy of `phase3/sem_best_2020.pt`
  (1,113,161,289 B each, size-verified), so they measure what the un-adapted 2020 RGB model does
  on six previously unscored acquisitions.
- **2 fullext fine-tunes** — `2016_fx`, `2021s_fx`, tag `fullext_sectors_v1`. Full citywide
  recipe on the *full-extent* orthos (killing the 41.9% / 39.5% study-clip ceilings), with
  inference restricted to the sectors.

**What it cost.** No dollar figure exists and none is invented: `pipeline/colab_rates.csv` ships
with zero GPU rate rows on purpose, so `Reports/gpu_launches.csv` correctly leaves every cost
column blank. In GPU time, from the per-launch status CSVs:

| launch | queue | measured step-min | span-min | note |
|---|---|---|---|---|
| 20260825T054717Z | base2020 | 0.6 | 0.6 | aborted (seed defect) |
| 20260825T054959Z | base2020 | 1.9 | 1.9 | aborted (seed defect) |
| 20260825T055323Z | base2020 | 25.1 | 25.1 | 6/6 inference OK |
| 20260825T061928Z | fullext | 8.6 | 8.7 | labels+tile OK, then VM death |
| 20260825T221901Z | fullext | 104.5 | 104.9 | 2/2 OK (train 45.2 + 43.9) |
| **total** | | **140.7** | **141.2** | ≈ **2.35 A100-hours** |

That total is an **estimate and a lower bound**: spans begin at the first step row and exclude VM
setup, clone, pip, Drive staging, teardown and idle. Two known losses sit outside it — ~6.2 min of
A100 wall-clock burned by the seed-CSV chain (05:47:08 → 05:53:23) and ~9 min of 2016 training
killed by the first VM death, which wrote no `minutes` row because the step never closed. Against
the design's "≈ 5–7 A100-hours" the campaign came in at roughly half: base inference ran long
(25.1 min vs ~15 predicted), fullext training short (89.1 min vs 2.5–3 h predicted).

**Headline findings.**

1. The un-adapted 2020 model does not degrade smoothly with acquisition age. Recall on the six
   baseline arms spans **0.3399 (2003s) to 0.6378 (2006s)**, precision **0.4415 (2006s) to
   0.8172 (2020s)**, all at threshold 0.5 vs epoch-matched C-CAP. The two collapsed-precision arms
   (2006s .4415, 2011s .4514) are the two that **over**-predict — the opposite of the model's
   documented defect — and are *not* the two with the largest reference epoch gap.
2. Both fullext fine-tunes produced usable full-coverage models, and both are **undecidable as
   promotions**: three confounds (footprint, operating point, unmeasured run-to-run noise) each
   independently exceed the observed effect sizes (§4).
3. The design-based city canopy fraction across 16 champion arms spans **0.35339 to 0.41819**
   (6.5 pp) while the narrowest 95% CI half-width is **±0.0735** and the widest **±0.2294**. Every
   interval overlaps every other: at L = 5 strata the estimator **cannot resolve the canopy
   trajectory**. That is the honest result, not a failure of the run. (pre-fullext run)
4. At crown scale the under-prediction is stark: **42.4%–53.5%** of 2020-vintage crowns in the
   sectors receive **exactly zero** modelled cover in the modern years (2020s, 2021, 2022, 2024) —
   years at or after the label anchor, where zero cannot be real change. (pre-fullext run)

**What is not yet decidable, and why.** No arm can be promoted until a **noise arm** (identical
recipe, different seed) measures run-to-run sigma. The project's only arm-vs-arm measurement —
2013, `xsensor_rgb` .7395 vs `citywide_rgb` .7422 against the same reference — is a recall
difference of **0.0027**, essentially the same as **0.0023**, the difference the *same raster*
shows between thresholds 0.5 and 0.5026. One measurement is not a sigma, but it is the only
empirical bound that exists, and it sits at the magnitude of several deltas this campaign produced.

---

## 2. The harness

**Geometry (`pipeline/aoi/sectors_v1.json`, generated at `cc3a94a`, 2026-08-25T04:29:38Z).**
Five strips, EPSG:3857, on the anchor lattice (origin −13625893.9732 / 6084272.7960,
px 0.07464553543473991 m, 512-px tiles, 4-tile blocks), each 4 block-rows tall, spanning the
city west→east at that latitude, with a 150 m water extension:

| sector | block_row0 | land ha (true) | weight W_h | water frac | crowns | sites |
|---|---|---|---|---|---|---|
| S1 (north) | 11 | 33.03 | 0.059 | 0.2869 | 3,410 | — |
| S2 | 29 | 98.84 | 0.176 | 0.1349 | 9,646 | — |
| S3 | 46 | 118.59 | 0.211 | 0.1973 | 7,034 | Forest_1 (partial) |
| S4 | 64 | 181.25 | 0.322 | 0.0708 | 10,406 | Forest_4 |
| S5 (south) | 83 | 131.29 | 0.233 | 0.0246 | 8,146 | Forest_3, Negative_Edmonds_Heights_K_12 (partial) |
| **total** | | **563.00** | 1.000 | | 38,642 | |

Areas are true ground areas (3857 area × cos²47.81°); the weight column is rounded to 3 dp and
its printed values sum to 1.001. S1 is small for two measured reasons: its rectangle spans 11
lattice columns (west_col 47 → east_col 58) against S4's 52, and it is 28.7% water.

**Engine mode.** `--infer-aoi aoi/sectors_v1.json` restricts *inference only*. Tiling, training
and evaluation run the standard citywide recipe, so a fullext arm is comparable to every prior
fine-tune in how it was built and differs only in where it was asked to predict. The written
prob raster is nodata (255) outside the rectangles plus a write-crop overhang of up to ~19 m,
which is why the series clips by the sector **polygon**, not by "valid prob pixels".

**Estimator (`qc/phase4_sector_series.py`).** Strata = the 5 bands; W_h = band true land area /
sampled land area. City fraction P̂ = Σ W_h · p_adj,h. Variance by the successive-difference
(Wolter) estimator for a systematic sample of L = 5:

```
V = (Σ W_h²) · [ 1/(2(L−1)) · Σ_{h=1..L−1} (p_{h+1} − p_h)² ] ,  CI95 = t(0.975, 4)·√V , t = 2.776
```

`p_adj = p_raw · precision / recall` from the year's own qc_indep live row (an error-adjusted
ratio estimator). Thresholds come only from `qc_indep_report.csv` live=1 primary=1; a year with
no live row is skipped and listed — there is no 0.5 fallback anywhere in this path.

**Why sampled inference.** Design-based sampling with a stated estimator and interval is the
standard practice for land-cover area reporting (it is what the Olofsson-family guidance
prescribes); wall-to-wall inference buys map product, not a better area estimate, and costs
~6–9× more compute per iteration.

**One correction to the design note.** The estimator writes `area_ha = P̂ × A`, where `A` is the
**sampled** 563.0 ha — not city land area, despite the docstring naming it `A_land_city` and the
file being called `city_canopy_totals_design.csv`. P̂ is a legitimate design-based estimate of the
*city* canopy fraction; `area_ha` is canopy hectares *within the sample*. Quote P̂; treat
`area_ha` accordingly. (Filed in §9.)

---

## 3. Baseline results — the 6 base2020 arms

All six are the 2020 phase-3 RGB checkpoint applied unchanged, inference-only, at threshold
**0.5**, scored against **epoch-matched C-CAP** (`ccap_2016_hires_lc_snohfull.tif` for the
2003–2018 arms, `ccap_2021_hires_lc.tif` for 2020s), canopy definition `forest_wetland`.
Source: `qc_indep_report.csv`, live=1 primary=1.

| arm | GSD cm | ref | ref epoch gap | thr | recall | precision | grass_reject | ref canopy frac | scored cells (`indep_1m_cells`) |
|---|---|---|---|---|---|---|---|---|---|
| 2003s | 30.48 | ccap2016 snohfull | 13 yr | 0.5 | 0.3399 | 0.8153 | 0.9386 | 0.3400 | 9,585,478 |
| 2006s | 100.00 | ccap2016 snohfull | 10 yr | 0.5 | 0.6378 | **0.4415** | 0.4625 | 0.3414 | 13,762,560 |
| 2011s | 30.48 | ccap2016 snohfull | 5 yr | 0.5 | 0.5727 | **0.4514** | 0.5540 | 0.3402 | 9,589,416 |
| 2012s | 22.86 | ccap2016 snohfull | 4 yr | 0.5 | 0.4725 | 0.6985 | 0.8651 | 0.3387 | 9,883,948 |
| 2018s | 15.24 | ccap2016 snohfull | 2 yr | 0.5 | 0.4611 | 0.8024 | 0.9107 | 0.3399 | 9,091,679 |
| 2020s | 7.62 | ccap2021 | 1 yr | 0.5 | 0.5483 | 0.8172 | 0.9473 | 0.2865 | 6,772,715 |

**What 0.5 is, exactly.** The base arms have **no eval rows** — training was seeded away by the
resume CSV, by design — so `qc_indep`'s eval-CSV threshold lookup fell through to its 0.5
fallback. 0.5 is therefore:

- **is** a single fixed operating point applied identically to all six arms, fixed *before* any
  of them were scored, and within 0.0026 of the phase-3 base model's own deployed calibration
  (0.5026) — a defensible pre-registered baseline point;
- **is not** a max-F1 point fitted on these years, **not** an independently-derived operating
  point in the M01 sense, and **not** matched to the fullext arms' val-tuned thresholds.

Audit item **M01_INDEP_OPERATING_POINTS** replaces this protocol; until it lands, every
cross-arm recall comparison in this report carries an operating-point term.

**Valid-pixel footprints (queue VERIFY, `train_queue_status_queue_sectors_base2020_20260825T055323Z.csv`).**

| arm | prob bytes | valid % of raster | maxprob | p99.9 | inference min |
|---|---|---|---|---|---|
| 2006s | 8,820,860 | 16.7 | 1.000 | 0.894 | 1.2 |
| 2011s | 62,109,313 | 11.6 | 1.000 | 0.906 | 2.7 |
| 2003s | 43,643,646 | 11.6 | 1.000 | 0.933 | 2.6 |
| 2012s | 89,656,084 | 12.0 | 1.000 | 0.972 | 3.1 |
| 2018s | 156,864,508 | 11.0 | 1.000 | 1.000 | 4.8 |
| 2020s | 562,868,731 | 10.7 | 1.000 | 1.000 | 10.7 |

The reference canopy fraction is **0.3387–0.3414** on all five 2016-referenced arms — a footprint
sanity check: the scored ground is effectively the same across them (2006s's larger cell count is
its 1 m grid overshooting the tile snap, not a different area). All six probs saturate
(`maxprob = 1.000`); the two fullext arms do not (0.913, 0.961) — a calibration difference between
the base checkpoint and the fine-tuned ones, worth remembering whenever thresholds are compared.

**The old-year precision story, stated honestly.** Precision does **not** track the reference
epoch gap: 2003s has the *largest* gap (13 yr) and the *second-highest* precision (0.8153);
2011s has a 5-year gap and 0.4514. What does hold is directional — 2006s and 2011s are the two
arms that **over**-predict. Their per-sector raw canopy fractions run 0.515–0.792 and 0.399–0.656
(`sector_canopy_series.csv`, pre-fullext run) against 0.164–0.438 for 2020s on the same ground,
where C-CAP says ~34% canopy. On those two acquisitions the base model fails in the *opposite*
direction from its documented citywide defect — a per-acquisition radiometry effect, not an
ageing effect, and a new fact: neither acquisition had ever been scored. 2003s and 2011s share a
GSD (30.48 cm) and split completely (.3399/.8153 vs .5727/.4514), which rules out pixel size as
the explanation for that pair.

---

## 4. Fine-tune results — 2016_fx and 2021s_fx

Both trained the standard citywide recipe on the full-extent orthos
(`2016_snoh_1ft_rgbi.tif`, `2021_snoh_6in_rgbi.tif`) from `phase3/sem_best_2020.pt`, then
inferred inside the sectors. Queue timings
(`train_queue_status_queue_sectors_fullext_20260825T221901Z.csv`): 2016_fx tile 616 tiles,
train **45.2 min**, evaluate 1.7, inference 3.6, prob 61 MB, valid 11.6%; 2021s_fx tile 705
tiles, train **43.9 min**, evaluate 1.3, inference 7.2, prob 182 MB, valid 11.0%. Both VERIFY OK.

**Scored (qc_indep, live=1 primary=1):**

| year | arm | ref | footprint | thr | recall | precision | grass_reject | ref canopy frac | scored cells |
|---|---|---|---|---|---|---|---|---|---|
| 2016 | `fullext_sectors_v1` | ccap2016 snohfull | sectors | 0.5223 | 0.6163 | **0.9119** | **0.9693** | 0.3402 | 9,589,416 |
| 2016 | (untagged citywide) | ccap2016 snohfull | 41.9% clip | 0.5090 | 0.6636 | 0.8736 | 0.9423 | 0.2953 | 31,323,256 |
| 2016 | `corrected` | ccap2016 **hires_lc** | 41.9% clip | 0.5090 | 0.8718 | 0.7296 | 0.7191 | 0.2953 | 31,323,256 |
| 2021s | `fullext_sectors_v1` | ccap2021 | sectors | 0.5000 | 0.6568 | 0.8276 | 0.9332 | 0.2871 | 6,945,477 |
| 2021s | `p2nir` | ccap2021 | 39.5% clip | 0.4990 | 0.6851 | 0.8547 | 0.9412 | 0.2650 | 32,586,786 |

`2016_corrected` is scored against a **different reference** (`ccap_2016_hires_lc.tif`, not the
`_snohfull` variant) and cannot be placed in the same comparison as the other two at all.

### The three confounds, as first-class findings

**(a) The scored footprints are different, and the sector footprint is harder.**
2016_fx was scored on 9,589,416 cells — **30.6%** of the 31,323,256 the citywide 2016 arm was
scored on. 2021s_fx on 6,945,477 — **21.3%** of p2nir's 32,586,786. (These are above the ~10%
pixel fraction because the citywide 2016/2021s arms were themselves 41.9% and 39.5% clips;
0.10/0.419 ≈ 24% and 0.10/0.395 ≈ 25%, approximately consistent with what is measured.)

More important than the size difference is the *content* difference: the reference canopy
fraction on the sector footprint is **0.3402 for 2016_fx vs 0.2953** citywide (+4.5 pp) and
**0.2871 for 2021s_fx vs 0.2650** for p2nir (+2.2 pp). The sector arms are scored on greener
ground. Recall and precision both move with reference prevalence; neither comparison is
controlled.

**(b) The operating points differ, and thresholds are known to dominate cross-year recall.**
The audit's M01 finding is that **~61% of the cross-year recall spread is operating point, not
model skill** (Q121: spread 0.1827 → 0.0721 at a matched call rate of 0.30). Here:

- **2021s**: 0.5000 vs 0.4990 — a 0.001 gap. The operating-point term is negligible; the
  footprint term is not.
- **2016**: 0.5223 vs 0.5090 — a 0.0133 gap. The one *measured* threshold sensitivity the
  project owns (2013: +0.0026 threshold → −0.0023 recall on the same raster) linearly
  extrapolates to roughly **−0.012 recall** across a 0.0133 gap. That is an order-of-magnitude
  bound derived from a single measurement on a different year and sensor — not a correction to
  be applied — but it suggests the threshold accounts for roughly a quarter of 2016_fx's
  0.0473 recall deficit.

**(c) No run-to-run sigma has ever been measured.** The project has exactly one arm-vs-arm
measurement, on 2013 against `ccap_2016_hires_lc_snohfull.tif`:

| comparison | recall | Δ |
|---|---|---|
| 2013 `xsensor_rgb` @0.5209 vs 2013 `citywide_rgb` @0.5000 | 0.7395 vs 0.7422 | **0.0027** |
| 2013 `citywide_rgb` @0.5000 vs same raster @0.5026 | 0.7422 vs 0.7399 | **0.0023** |

Two different training recipes and two different rasters separated by the same amount as a
0.0026 threshold nudge on one raster. n = 1 is not a sigma, but any claimed improvement smaller
than ~0.003 recall is inside the only noise bound that exists.

### Verdict

**Promotion of either fullext arm is UNDECIDABLE until the noise arm runs.** Stated plainly:

- **2021s_fx is worse than p2nir on all three headline metrics** — recall −0.0283,
  precision −0.0271, grass_reject −0.0080 — at near-matched thresholds. The recall gap is ~10×
  the 2013 arm-vs-arm delta, which makes it *plausible* that the gap exceeds run-to-run noise;
  but it is measured on a footprint with 2.2 pp more reference canopy and 21.3% of the cells,
  so it is not a controlled result in either direction.
- **2016_fx trades recall for precision**: −0.0473 recall, **+0.0383 precision**, **+0.0270
  grass_reject**, at a threshold 0.0133 higher, on a footprint with 4.5 pp more reference canopy.

### What fullext *did* deliver (not undecidable)

1. **Coverage.** 2021s went from a **39.5%** study clip to **100%**; 2016 from **41.9%** to
   **100%**. Those ceilings are gone, permanently, and the checkpoints
   (`sem_best_{2016,2021s}_fullext_sectors_v1.pt`, 1,113 MB, zip magic verified) exist to
   re-infer citywide whenever that is wanted.
2. **Best-in-year grass rejection for 2016.** `2016_fx` grass_reject **0.9693** is the highest
   any 2016 arm has recorded, against any reference: citywide is 0.9423 on the same `_snohfull`
   reference, 0.9119 on `ndvi_ref_2016.tif`, and `corrected` is 0.7191 on `ccap_2016_hires_lc.tif`.
   Grass rejection is the specific failure mode the fullext orthos were expected to help, and on
   the sector footprint it moved in the predicted direction.
3. **Precision against the C-CAP reference.** `2016_fx` precision **0.9119** is the highest any
   2016 arm has recorded against `ccap_2016_hires_lc_snohfull.tif` (citywide 0.8736). It is
   *not* the highest 2016 precision on record — the citywide arm scores 0.9593 against
   `ndvi_ref_2016.tif`, a different reference under the `canopy_only` definition, which is not
   comparable to either C-CAP row.

### Golden gate (frozen-window regression) — reported, NOT comparable

`golden_gate_history.csv`, post-fullext sweep at `37bdb6b`. This is a **report-only regression
gate on 12 hand-picked sentinel windows scored only where C-CAP and NDVI agree** — a
deliberately easy, deliberately unrepresentative slice. **Never quote these as accuracy.**

| year | tag | thr | windows scored / skipped | pooled recall | pooled precision | pooled IoU |
|---|---|---|---|---|---|---|
| 2016 | (untagged) | 0.509 | 10 / 2 | 0.7512 | 0.8793 | 0.6810 |
| 2016 | corrected | 0.509 | 10 / 2 | 0.8794 | 0.7957 | 0.7174 |
| 2016 | **fullext_sectors_v1** | 0.5223 | **1 / 11** | 0.7970 | 0.9617 | 0.7725 |
| 2019n | p2nir | 0.495 | 12 / 0 | 0.8072 | 0.9478 | 0.7728 |
| 2021s | p2nir | 0.499 | 10 / 2 | 0.7404 | 0.9014 | 0.6850 |
| 2021s | **fullext_sectors_v1** | 0.500 | **1 / 11** | 0.8369 | 0.9574 | 0.8068 |

The two fullext rows scored **1 of 12 windows** — eleven windows fall outside the sectors and
the gate correctly refuses them (its 80%-valid rule). A 1-window pooled number and a
10–12-window pooled number are computed on **disjoint ground**; the fullext rows being higher
is not evidence of anything and must not be put in a shared table with the others without this
sentence attached. The gate is report-only in v1 precisely because no noise arm has established
how much a pooled number moves between two identical runs.

---

## 5. Canopy trajectory

> **Regeneration in flight.** `sector_canopy_series.csv`, `city_canopy_totals_design.csv` and
> `crown_cover_matrix.parquet` are being rebuilt with the two fullext arms as this is written.
> Values below are the **pre-fullext run** (series written 11:42, matrix 11:45, 2026-08-25) and
> are citable as such. Final values are marked pending.

**Scale (pre-fullext run):** `sector_canopy_series.csv` 139 rows = 29 arms × up to 5 sectors;
`city_canopy_totals_design.csv` 26 rows, of which **16 carry `is_champion=1`**;
`crown_cover_matrix.parquet` **38,642 crowns × 29 cover columns** (33 columns total incl.
`crown_id`, `sector`, `area_m2`, `n_cells`).
Final (regeneration completed 2026-08-26): `sector_canopy_series.csv` **149 rows**, `city_canopy_totals_design.csv` **28 rows**, `crown_cover_matrix.parquet` **38,642 crowns × 35 columns** (31 cover arms + 4 metadata columns). Champion-arm rows regenerated bit-consistent with the pre-fullext run (same rasters, same thresholds — e.g. 2003s P̂ 0.39041 unchanged).

**Design-based city canopy fraction, champion arms only (pre-fullext run):**

| year | tag | P̂ | se | CI95 lo | CI95 hi | half-width |
|---|---|---|---|---|---|---|
| 2003s | sectors_v1 | 0.39041 | 0.08265 | 0.16098 | 0.61983 | ±0.2294 |
| 2005 | citywide_rgb | 0.37300 | 0.07456 | 0.16601 | 0.57999 | ±0.2070 |
| 2006s | sectors_v1 | **0.41819** | 0.04710 | 0.28743 | 0.54896 | ±0.1307 |
| 2007 | citywide_rgb | 0.36926 | 0.05407 | 0.21915 | 0.51937 | ±0.1501 |
| 2009 | citywide_rgb | 0.37411 | 0.07084 | 0.17746 | 0.57076 | ±0.1967 |
| 2011s | sectors_v1 | 0.39877 | 0.02646 | 0.32533 | 0.47222 | **±0.0735** |
| 2012s | sectors_v1 | 0.38264 | 0.05816 | 0.22119 | 0.54409 | ±0.1615 |
| 2018s | sectors_v1 | 0.38891 | 0.05861 | 0.22622 | 0.55160 | ±0.1627 |
| 2019 | citywide_rgb | 0.35835 | 0.05532 | 0.20477 | 0.51193 | ±0.1536 |
| 2019n | p2nir | 0.36322 | 0.05185 | 0.21930 | 0.50715 | ±0.1439 |
| 2020s | sectors_v1 | 0.38741 | 0.05491 | 0.23497 | 0.53984 | ±0.1524 |
| 2021 | citywide_rgb | 0.36560 | 0.06370 | 0.18878 | 0.54243 | ±0.1768 |
| 2022 | citywide_rgb | **0.35339** | 0.05009 | 0.21435 | 0.49243 | ±0.1390 |
| 2023 | citywide_rgb | 0.36560 | 0.05238 | 0.22020 | 0.51100 | ±0.1454 |
| 2023n | (untagged) | 0.36988 | 0.05547 | 0.21589 | 0.52387 | ±0.1540 |
| 2024 | citywide_rgb | 0.40605 | 0.06056 | 0.23793 | 0.57417 | ±0.1681 |

**The result is that there is no resolvable trajectory.** The full spread across the 16 champion
arms (2003s–2024) is 0.35339 → 0.41819 = **6.5 pp**, while the *narrowest* single interval is
±7.35 pp — wider than the entire 21-year spread it would have to resolve. The intersection
of all sixteen intervals is [0.32533, 0.47222] — non-empty, so **every champion year's CI overlaps
every other's**. No year-over-year change, and no trend, is statistically distinguishable at
L = 5 strata. Reporting a canopy trend from this table would be reading noise.

Final: **YES — the fine-tunes give both years their first full 5-sector design-based estimates**, the campaign's most tangible trajectory deliverable. 2016_fx: **P̂ 0.383, CI [0.208, 0.558]**, n=5. 2021s_fx: **P̂ 0.385, CI [0.237, 0.532]**, n=5. (The pre-existing 2016/2016_corrected/2021s_p2nir clips still write series rows for their 3 southern sectors and correctly receive no total.) Both fx rows carry `is_champion` 0/blank per the full-footprint eligibility rule — these are sector-footprint estimates of the city fraction, quoted with their CIs, not deliverable rasters.

**`area_ha` caveat.** The `area_ha` column multiplies P̂ by the **sampled** 563.0 ha, so
e.g. 2024's 228.6 ha is canopy *within the sample*, not city canopy. A city-scale figure would be
P̂ × 2,285.6 ha ≈ 928 ha for 2024 — **derived by this report**, not present in any CSV, and
carrying the same ±0.168 fractional interval (≈ ±384 ha). It is quoted here only to show why the
column must not be read as a city total.

**Per-crown matrix (pre-fullext run).** 38,642 crowns, median crown area 64.06 m², p90 171.48 m²;
per-sector counts S1 3,410 / S2 9,646 / S3 7,034 / S4 10,406 / S5 8,146. Cover is the crown's
mean value in the 1-m cover sidecar (the fraction of native pixels above the arm's deployed
threshold).

**Two crown-scale observations, both flagged to-investigate, neither asserted:**

1. **Zero-cover crowns.** In the years at or after the label anchor, where a zero cannot be real
   change: 2020s 47.0% of crowns at exactly 0, 2021 53.5%, 2022 42.4%, 2024 42.9%. This is the
   citywide under-prediction defect made visible at the object scale. It is not yet a clean
   measurement — the crown polygons are the phase-0 2020 instance set, whose own precision has
   never been audited, and small crowns (median 64 m²) straddle few 1-m cells.
2. **The high-cover cluster is a GSD/precision pattern, not a NIR pattern.** `RESUME_NOTES.md`
   records this as "a large NIR-vs-RGB cover spread (0.97–0.98 vs 0.00–0.07)". The matrix does
   not support the NIR framing: `cover_2021s_p2nir`, a NIR arm, has median **0.0000**. What the
   table shows is that the only four arms with median crown cover above 0.5 are exactly the four
   satisfying **GSD ≥ 60 cm or precision < 0.55** — and no arm outside that set does:

   | arm | GSD cm | precision | median cover | frac ≥ 0.99 |
   |---|---|---|---|---|
   | 2019n p2nir | 60.00 | 0.8540 | 0.9707 | 0.4695 |
   | 2023n | 60.00 | 0.8630 | 0.9844 | — |
   | 2006s sectors_v1 | 100.00 | 0.4415 | 0.6948 | 0.4650 |
   | 2011s sectors_v1 | 30.48 | 0.4514 | 0.5944 | — |
   | *(all 25 other arms)* | 5.01–40.10 | 0.6985–0.9177 | 0.0000–0.3428 | — |

   Mixed pixels at coarse GSD and over-calling at low precision both plausibly produce this;
   so does the `p_adj` err-adjustment at low recall. Distinguishing them is a task, not a
   finding. **Do not report a NIR advantage from this table.**

---

## 6. Incidents and engineering

**The seed-CSV chain — three launches for one queue.** The base2020 queue was supposed to resume
past labels/tile/train/evaluate from a pre-written seed CSV (24 OK rows). It did not, twice.
Root causes, from the CHATLOG entry: the seed wrote column `job_id` where the queue reads `job`;
the timestamps were local, not UTC, so the merge picked the wrong row; and a Drive-lag race meant
the VM read the seed before it had propagated. Fixes: `63a0276` (AOI path resolution, cwd first)
and `1d35832` (seed ts in UTC), plus a VM-side self-seeded launch. Measured cost: launches
20260825T054717Z (0.6 step-min) and 20260825T054959Z (1.9 step-min), and **6.2 minutes of A100
wall-clock** between the S11 start (05:47:08) and the third launch's first step (05:53:23). Prior
prose put this at "~8 wasted A100-min"; the status CSVs support ~6.2. The third launch ran clean:
6/6 inference VERIFY OK in 25.1 min.

**Two VM deaths, neither a code crash.**
- *GPU session, ~06:37 UTC*, ~9 minutes into 2016_fx training (Phase A epoch 2, IoU still
  climbing, no traceback). The status CSV was left with `train,RUNNING` and never closed — which
  is why those ~9 GPU-minutes appear in no sum anywhere, and why `n_ok`/`n_failed` in
  `gpu_launches.csv` both exclude the row. The loop's S12 hit `timeout_min: 420` at 13:20:09,
  retried once, and got `[colab] Session 'gpu' not found.`; `_loop` recorded
  `failed: blocked on ['S12_fullext_queue']`. Labels and tile from that launch survived and were
  reused by the relaunch (the relaunch's first row is `train`), so 8.6 of its 8.7 minutes were not
  wasted.
- *qc CPU session, ~14:2x UTC*, mid-2020s postproc. 5 of 6 masks had landed; the 2020s mask was
  absent with no truncated file — it died before the copy. Local fallback was impossible on
  Windows (the shim sets the multiprocessing `fork` start method at module level). It was rerun on
  the next Drive-mounted CPU VM; `edmonds_canopy_mask_2020s_sectors_v1.tif` (101,445,348 B) landed
  15:40, its GPKG 15:58. **All 8 arms now have masks and GPKGs.**

**The qc_indep lineage near-miss — caught before damage.** Supersession in
`qc_indep_report.csv` had been per (year, ref). Scoring `2016_fx` and `2021s_fx`, which share the
year labels 2016 and 2021s with existing citywide arms, would have flipped the citywide live rows
to `live=0` and silently destroyed the project's honest numbers for two years. Commit **`3e7ac30`**
made supersession per **(year, ref, arm)**, with the arm parsed from the prob filename. It landed
*before* fullext scoring. Post-scoring verification confirmed zero citywide rows clobbered: 2016
(untagged) and 2021s p2nir remain live=1 primary=1 alongside the new fullext rows. Fullext
scoring is safe only on code ≥ `3e7ac30`.

**An accidental interlock that worked.** The GitHub mirror was behind (the remote rejects
`.github/workflows/` from a token without `workflow` scope), so the fullext VM cloned the last
*pushed* commit. Every fullext run manifest records `git_sha
3e7ac30a46194b06a465f1edd879d5f443521d37`, branch `work/20260824-sectors`, `git_dirty false` —
the run used **pre-E02, pre-E06** engine code, exactly the "SAFE" path the resume notes predicted.
The E02 atomic-`os.replace` publish therefore never touched drivefs during the campaign —
and separately, the E02 drivefs smoke DID run on the morning qc VM (2026-08-26): PASS on both
dest-absent and dest-present with a 1.11 GB checkpoint (rename 0.00/0.01 s), so E02 is
validated for future pushes. Two consequences: (a) the E06a check the resume notes
asked for — "confirm the first post-resume manifest contains the new `labels` block" — **cannot be
performed on these runs**, because 3e7ac30 predates commit `287add8`; the manifests are otherwise
complete (run_id, ts_utc, engine_version v048, git_sha/branch/dirty, gpu + gpu_mem_gb, argv,
run_tag, step, seed, years, python, pip_freeze). Not a defect; a check still outstanding.
(b) The base2020 arms ran at `1d35832` and the fullext arms at `3e7ac30`, and
`git diff 1d35832 3e7ac30 -- pipeline/phase4seg pipeline/phase4_semantic_finetune.py` is
**empty** — the only intervening commit touched `qc/phase4_qc_indep.py`. The engine was
byte-identical across both queues, so engine drift is *not* among the confounds in §4.

**E-backlog Lane 1 landed alongside** (`275511e a238264 287add8 c64a408 2288159 890e97e b917834`):
E01 registry joins on `year` not job id and never lets SEEDED rows suppress real ones — without
which this campaign would have had **zero** timing data; E02 atomic `.part` publish; E03 CI gates
(16 tests green, push blocked on the token scope); E05 `champion_arms.csv` with four fail-loud
consumers, which fixed a live bug where last-wins plotted the wrong 2013 arm; E06 label lineage;
E07 the golden gate; E08 audit corrections. Cost accounting landed as `pipeline/cost_report.py` +
`Reports/gpu_launches.csv` + a schema-only `colab_rates.csv`.

**Runtime autonomy proven.** Service-account + rclone mount canary PASS (read-hash-identical, E02
atomic publish works through rclone, raster reads OK); `fuse3` auto-install and the
`--allow-other` removal are encoded in `pipeline/gen_vm_bootstrap.py`; a full unattended lifecycle
ran on a virgin VM to `BOOTSTRAP_READY` with zero clicks; both sessions were stopped afterward.
P11.6 policy text is pending Kam's merge. The permission boundary held: at 03:00 with the campaign
blocked, the loop did **not** route `colab new` through a background process to dodge the
classifier and did **not** click Google OAuth consent — it wrote the resume notes and waited.

---

## 7. Decisions needed from Kam

### 7.1 Champion designations — 6 years (blocking every downstream consumer)

`pipeline/champion_arms.csv` fails loud for years with multiple live arms. Six are absent and
must be named. Evidence per year, all qc_indep live=1 primary=1:

| year | arm | rec / prec / grass_rej | thr | reference | note |
|---|---|---|---|---|---|
| 2000 | `citywide_rgb` | .5480 / .8534 / .9136 | 0.5133 | snohfull | fuller reference |
| 2000 | `xsensor_rgb` | .6303 / .7745 / .8399 | 0.5133 | hires_lc | different reference |
| 2002 | `citywide_rgb` | .6136 / .8372 / .8902 | 0.4988 | snohfull | |
| 2002 | `xsensor_rgb` | .5069 / .8377 / .9214 | 0.5700 | hires_lc | different ref **and** 0.071 thr gap |
| 2013 | `citywide_rgb` | .7399 / .8681 / .9140 | 0.5026 | snohfull | CHATLOG implies this arm |
| 2013 | `xsensor_rgb` | .7094 / .8551 / .9171 | 0.5209 | hires_lc | same-ref delta is 0.0027 — nothing measurable |
| 2015 | `citywide_rgb` | .7401 / .8823 / .9226 | 0.5011 | snohfull | |
| 2015 | `xsensor_rgb` | .6222 / .8835 / .9473 | 0.5760 | hires_lc | 0.075 thr gap likely explains most of the recall gap |
| 2016 | (untagged) | .6636 / .8736 / .9423 | 0.5090 | snohfull | |
| 2016 | `corrected` | .8718 / .7296 / .7191 | 0.5090 | hires_lc | different reference |
| 2016 | `fullext_sectors_v1` | .6163 / .9119 / .9693 | 0.5223 | snohfull | **sector footprint only** |
| 2017 | `citywide_rgb` | .7058 / .9007 / .9505 | 0.4986 | snohfull | |
| 2017 | `xsensor_train` | .7784 / .8083 / .8834 | 0.4759 | hires_lc | different ref **and** 0.023 thr gap |

One row per (year, arm); `snohfull` = `ccap_2016_hires_lc_snohfull.tif`, `hires_lc` =
`ccap_2016_hires_lc.tif`. The untagged 2016 arm carries a second live+primary row against
`ndvi_ref_2016.tif` (.5937 / .9593 / .9119 @0.4615, `canopy_only` definition) which is not
comparable to any C-CAP row. Standing labels that must travel with any pick: **2013 is an
RGB-ONLY model** and must never share a table with the rgb+chm years unlabelled; **2016 is
undecidable on metrics** per §4, so if a deliverable is needed now, coverage may be the deciding
criterion rather than accuracy.

**Also newly stale:** `champion_arms.csv` records `2021s,p2nir,,only live arm`. True at the
2026-08-25 auto-backfill; `2021s_fullext_sectors_v1` has since landed a live row, so **2021s now
has two live arms** and the auto-backfilled justification no longer holds. Whether a
sector-footprint arm is even *eligible* to be a champion is a policy question this report does not
adjudicate — it needs a written rule.

### 7.2 Noise arm — the gate for every promotion band

**Ask:** one A100 launch, one arm, identical recipe and data to an existing fullext arm, different
seed; score it through the same qc_indep path on the same footprint. Reference cost from this
campaign: a fullext train is 43.9–45.2 min plus 3.6–7.2 min inference, so **~1 A100-hour**.

**Why it gates everything:** without a measured σ there is no threshold below which a delta is
noise. Today the only bound is 2013's 0.0027 recall — a single observation whose magnitude
happens to equal a threshold-rounding artifact. Every arm-vs-arm claim in §4, every future
M06/M07/M08/M12 verdict, and the golden gate's ability to *arm* a tolerance (it is report-only in
v1 for exactly this reason) all wait on it. It is the cheapest unblocking spend available.

### 7.3 Production-rollout decision framework

Sampled inference proved out: ~6–9× cheaper per iteration, VERIFY-clean, and the design-based
estimator runs on it. The open question is what the sectors are *for*, and the two answers imply
different spending:

- **Sectors as the experiment bench** (recommended by the evidence): all A/B work — M06 NIR
  channel, M07 BN adaptation, M08 CHM-stratified sampling, M12 WiSE-FT — runs sector-only,
  paid at ~1 A100-h per arm; citywide inference is spent **once**, on the winner, after the noise
  arm establishes what "winner" means.
- **Sectors as the deliverable** — requires accepting an estimator whose CIs (§5) cannot resolve
  a 6.5 pp spread. Widening those intervals is a *sampling design* problem (more, thinner strata),
  not a model problem, and would need its own design pass before any spend.

Preconditions that are not model work and should be sequenced first, per the audit: **M01**
(independent operating points — removes the confound that dominates §4), **M05** (co-registration
to the anchor — the 2024 primary is displaced 1.29 m, and no per-crown change claim survives
that), and **M02/M03** (the interpreted-point study that gives the area series an unbiased
headline). None need a GPU.

---

## 8. Limitations

1. **Borrowed labels.** Only 2020 has hand labels. Every arm here — the six baselines and both
   fullext fine-tunes — ran `--force-citywide`, i.e. trained or was selected against the 2020
   citywide mask projected onto another year. That mask is itself a *model prediction*, not
   ground truth, and shares the model's blind spots. Real pre-2020 change scores as model error.
2. **C-CAP epoch gaps.** The 2016 reference is 2–13 years from the acquisitions scored against
   it (2003s at 13 yr, 2018s at 2 yr); the 2021 reference is 1 year from 2020s. Real change in
   those windows is charged to the model. §3 shows the effect is not even monotonic in the gap,
   which means it cannot be corrected by a simple ageing term.
3. **Five strata is a hard CI floor.** t(0.975, 4) = 2.776 and the successive-difference variance
   over L = 5 give half-widths of ±0.07 to ±0.23. Every champion interval overlaps every other
   (§5). Nothing about the model changes this; only a different sampling design would.
4. **The err-adjustment amplifies at low recall.** `p_adj = p_raw · precision / recall` is a
   ratio estimator with no variance term of its own. For 2003s (recall 0.3399, precision 0.8153)
   the multiplier is **×2.40**, turning per-sector raw fractions of 0.076–0.320 into adjusted
   0.182–0.768. An adjusted "canopy fraction" of 0.76801 in S2 (raw 0.32019) is an artifact of
   the correction, not an observation. The correction's own uncertainty is nowhere in the
   reported CI.
5. **Golden gate coverage for the fullext arms is 1 of 12 windows.** Their pooled numbers stand
   on ground disjoint from every other row in that file and are not comparable to the 10–12-window
   rows. The gate is also an *easy slice* (two-reference agreement only) and is never an accuracy
   measurement for any arm.
6. **Tiered quality for the old years is real and unquantified.** The baseline arms span GSD
   7.62 cm to 100 cm across four source agencies and 17 calendar years. 2006s at 1 m has precision
   0.4415 and 2003s at 30 cm has recall 0.3399; these are not the same product as 2020s at 7.62 cm.
   Any citywide series built from them is a mosaic of qualities, and no per-acquisition
   co-registration table to the 2020 anchor exists (M05) — a measured 1.29 m displacement on the
   2024 primary shows the exposure is not hypothetical.
7. **Sector-vs-citywide footprints are not interchangeable.** The sector footprint carries 4.5 pp
   (2016) and 2.2 pp (2021s) more reference canopy than the citywide clips it is being compared
   with. Until a citywide arm is re-scored *on the sector polygons*, no fullext-vs-citywide
   number in §4 is a controlled comparison.
8. **Crown-scale results inherit an unaudited crown set.** The 38,642 crowns are the phase-0 2020
   instance polygons, whose own precision has never been measured, and the 14,476-crown human
   review was never completed. Zero-cover fractions in §5 measure model *and* crown-set error
   together.

---

## 9. Data inconsistencies found while cross-checking

Recorded so they are fixed at the source rather than carried forward.

1. **`city_canopy_totals_design.csv` `area_ha` is not a city area.** It is P̂ × sampled 563.0 ha.
   The script docstring calls the multiplier `A_land_city`, and the code names the variable
   `A_city`, but it is computed as the sum of the five sector land polygons — which the script's
   own stdout correctly prints as "sampled land". Either rename the column/variable or multiply
   by city land area.
2. **`RESUME_NOTES.md`'s "NIR-vs-RGB cover spread" does not hold.** `cover_2021s_p2nir` (a NIR
   arm) has median crown cover 0.0000. The four high-cover arms are exactly those with GSD ≥ 60 cm
   **or** precision < 0.55 (§5).
3. **`RESUME_NOTES.md`'s temporal-gap explanation for the precision collapse is non-monotonic.**
   2003s (13-yr gap) precision 0.8153 vs 2011s (5-yr gap) 0.4514 (§3).
4. **`pipeline/champion_arms.csv` 2021s row is stale.** `2021s,p2nir,,only live arm` — 2021s now
   has two live arms; 2016 now has three. The auto-backfill's "forced, not a judgment" note
   should be re-run or the row amended.
5. **`Reports/gpu_launches.csv` is stale.** It is missing the `20260825T221901Z` fullext
   relaunch — the largest GPU launch of the campaign (104.5 step-min). It is a regenerable
   harvest; re-run `pipeline/cost_report.py --launches`.
6. **`run_registry.csv` is missing the completed fullext GPU steps.** The 26 campaign rows stop
   at `20260825T062002Z_2016_fullext_sectors_v1_tile` plus the six CPU postproc rows. The
   `2016_fx` and `2021s_fx` train / evaluate / inference steps — all eight of them, including
   both 45-minute trains — have no registry row, so the campaign's largest spend is absent from
   the spend ledger.
7. **The state ledger says the campaign failed.** Only one state file exists
   (`state_20260825T044145Z.jsonl`); its last two lines are `S12_fullext_queue failed` and
   `_loop failed: blocked on ['S12_fullext_queue']`. S12 in fact completed at 00:04 UTC on
   2026-08-26 via a Kam-assisted relaunch outside the loop, and S13/S20–S23 followed. The
   authoritative record of the second half of the campaign is `RESUME_NOTES.md` + the status
   CSVs + the run manifests, not the ledger the checklist names as its measured state.
8. **`RESUME_NOTES.md` says the matrix is "38,642 crowns x 28 arms"; the parquet has 29 cover
   columns** (33 columns total). Likewise the cover sidecar directory holds 30 rasters at the
   time of writing, mid-regeneration.
9. **`vm_e02_rename_smoke.py` lives in LOCAL SCRATCH, not the repo** (the VM-script staging
   dir under %LOCALAPPDATA% — deliberately outside git, like every VM script). The smoke it
   implements RAN and PASSED on 2026-08-26 (dest-absent AND dest-present, 1.11 GB, E02_SMOKE
   PASS); the campaign itself never needed it because the VMs cloned pre-E02 code (§6).
10. **Prior prose says "~8 wasted A100-min" for the seed-CSV chain**; the status CSVs support
    **6.2 min** of wall-clock (2.5 min of it in completed steps).

---

## 10. Provenance

- Honest metrics: `data:phase4/qc/qc_indep_report.csv`, live=1 primary=1 rows only. Arm parsed
  from the prob filename (`edmonds_canopy_prob_{year}_{tag}.tif`). 121 rows total, 94 live,
  32 live+primary at the time of writing.
- Regression: `data:phase4/qc/golden_gate_history.csv`, post-fullext sweep rows at `37bdb6b`.
- Timings: `data:phase4/qc/train_queue_status_queue_sectors_*.csv` (6 files),
  `Reports/gpu_launches.csv`, `Scripts/run_registry.csv` (26 campaign rows).
- Series / totals / matrix: `data:phase4/qc/sector_campaign/` — **regenerating**, values here are
  the pre-fullext run.
- Execution history: `data:phase4/qc/sector_campaign/state_20260825T044145Z.jsonl`,
  `RESUME_NOTES.md`, `pipeline/sector_campaign_checklist.yaml`.
- Lineage: run manifests under `data:phase4/runs/` — base2020 arms at `1d35832`, fullext arms at
  `3e7ac30`, engine byte-identical between the two.
- Audit context: `Scripts/MACHINERY_AUDIT_2026-08.md` (M01, M03, M04, M05), `CHATLOG.md` STATE
  blocks `sectors:` and `ebacklog:`.

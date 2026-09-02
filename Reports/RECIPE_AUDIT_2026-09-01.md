# Recipe deep-dive — what is actually on the table before the 36-run

*2026-09-01. Requested by Kam ("make sure we are leaving anything obvious on the
table like sieve that has a large impact"). Every claim below is labeled
MEASURED (instrument + CSV exist), INSPECTED (read in source, no number needed),
or UNMEASURED (needs GPU to answer). Numbers: `phase4/qc/postproc_variant_scores.csv`
(instrument: `Scripts/qc/instruments/postproc_variant_score.py`) and the live
`qc_indep_report.csv` rows on the lake. Scope: the citywide EPOCH-3 recipe the
36-run would use, examined stage by stage — labels → tile → train → evaluate →
inference → postproc.*

## The one large knob: the operating threshold — MEASURED

`postproc._operating_threshold` deploys the max-F1 threshold from
`semantic_eval_report.csv`, which is computed on **2020-projected labels**. Real
change between the imaged year and 2020 counts as error during selection, so the
chosen cut can wander far from the real-world optimum, and nothing catches it.

Measured on 2011s against C-CAP (raw prob, forest_wetland):

| thresh | recall | precision | F1 | canopy area |
|---|---|---|---|---|
| 0.45 | 0.734 | 0.772 | 0.753 | 1942 ha |
| 0.50 | 0.714 | 0.783 | 0.747 | — |
| **0.643 (chosen)** | **0.499** | **0.868** | **0.634** | **1264 ha** |

The circular selection cost 2011s **23 recall points**. Fleet context: chosen
thresholds span 0.332 (2019) to 0.643 (2011s) — the mechanism usually lands
near 0.5 but is unguarded in both directions.

**The area-trend consequence is the part that matters most for the deliverable:**
the same model, same imagery, same everything reports 1264 ha or 1942 ha of
canopy — a 54% swing — depending on where the unguarded knob lands. The
cross-year consistency check flags ±40% deviations; threshold wander alone can
exceed that. Fixing threshold policy is not just an accuracy fix, it is the
prerequisite for any cross-year canopy trend.

**DECIDED: C (Kam, 2026-09-01 — "Let's go with C").** Implemented same day:
dense u8 sweep in `phase4_qc_indep._write_dense_sweep` (exact curve at all 254
integer cuts, selected cut == deployed cut by construction), selector
`qc/instruments/select_indep_threshold.py` → registry
`phase4/qc/indep_thresholds.csv`, pre-registered in
`experiments/full_archive_e3.yaml`. Engine untouched — deployment rides the
existing `--infer-thresh` override. Caveat that travels with C: C-CAP 2021 carries
its own temporal gap and a broad canopy definition, so variant *deltas* against
it are trustworthy while the *absolute* optimum inherits its canopy definition —
publish the curve, don't bless a single number.

## The knobs that measured NEUTRAL — morphology and sieve

**Morphology (3×3 open+close) — MEASURED, both pilot years.** The kernel is
specified in **pixels**, so its physical size spans 0.15 m (5 cm years) to
3.0 m (2006s) — a 20× spread, same un-normalized-units shape as the pre-EPOCH-3
sieve; 7 of 36 acquisitions get a ≥1.5 m element. But measured effect, even at
the 3 m extreme:

| variant | recall | precision |
|---|---|---|
| 2011s raw@0.643 | 0.4994 | 0.8680 |
| 2011s morph@0.643 | 0.5050 | 0.8662 |
| 2006s raw@0.4743 | 0.6544 | 0.7213 |
| 2006s morph@0.4743 (3 m kernel) | 0.6575 | 0.7196 |

Opening and closing roughly cancel; deltas are ≤0.6 pt and partly explained by
a one-u8-step threshold difference between scorer and production (see nits).
**Verdict: not on the table.** Normalizing the kernel to ground units is right
on principle, zero-GPU, but its priority is low because its measured impact is
nil.

**Sieve — MEASURED.** morph vs morph+sieve: identical to four decimals at both
thresholds; 0.016% of canopy pixels move. Post-EPOCH-3 the sieve is clean and
essentially decorative at these GSDs. **Verdict: nothing left on this table** —
the EPOCH 3 re-baseline already collected what there was.

**Equivalence anchor:** the shipped `edmonds_canopy_mask_2011s_hy_e3_2011s.tif`
scored **pixel-identical** (tp=60,497,713 fp=9,344,235) to the instrument's
morph@0.643 replica — the variant apparatus measures exactly what production
ships.

## The scored artifact is not the shipped artifact — INSPECTED, now bridged

Every honest number to date (mining table, pilot verdict, sweeps) scores the
**raw prob raster**. The shipped mask adds morphology; the shipped GPKG adds
the sieve and a vector filter. Three artifacts, three canopy definitions in one
step — and the per-year area summary counts pixels **before** the sieve while
the polygons come after it. Measured above, the bridge is now known: mask ≈
prob-at-cut within 0.6 pt. Keep dual-reporting via the variant instrument
whenever postproc semantics change again.

## Attribute-integrity bugs in the GPKG path — INSPECTED, not yet fixed

Pre-EPOCH-3 residue in `step_postproc`'s polygonize stage (the raster mask is
unaffected):

1. **`area_m2` is CRS-unit area labeled m²** — wrong on ~30/36 acquisitions
   (10.76× inflated on survey-foot years, 2.2× on Web-Mercator).
2. The vector filter `areas >= MIN_CANOPY_PATCH` compares CRS units to a m²
   constant — but is **provably redundant** (the raster sieve already enforces
   3 m² true everywhere: survey-foot years the vector cut is 0.28 m² true,
   Mercator 1.35 m² — both weaker than the sieve).
3. `SIMPLIFY_TOLERANCE_M = 0.5` is applied in CRS units (0.15 m on survey-foot
   years, 0.74 m-equivalent on Mercator).
4. The stale comment block above `pixel_area_true` still says the conversion is
   "DELIBERATELY NOT APPLIED to min_px" — contradicted by the EPOCH 3 line
   directly beneath it.

No downstream consumer reads GPKG `area_m2` yet (checked: buildings/crown
layers are separate artifacts; `build_validity_intervals` is unbuilt and will
read the mask raster). Fix before anyone does. All zero-GPU.

## Labels: hard binary projection of a model that was often unsure — MEASURED band, UNMEASURED effect

The citywide recipe labels every tile from the 2020 **mask** via
nearest-neighbour point sampling — hard 0/1, no uncertainty. Measured on the
2020 prob raster (211 sampled rows): **5.2% of valid pixels sit in the 2020
model's own 0.4–0.6 band** — about a third the size of the entire canopy class
— and each becomes a confident training label on every other year, concentrated
exactly where projection error lives (crown edges). The remedy already exists
in the engine and is unused by the recipe: `--anchor-labels` (2020 prob ≥0.6 →
canopy, ≤0.4 → background, between → IGNORE, area-weighted resampling).

This is the one candidate improvement that needs GPU to evaluate: a
pre-registered A/B on 2011s (~2–3 A100-hr), decision rule written first.
Queued behind the threshold-policy decision; not a 36-run blocker.

## Inspected and clean

- **Inference stitching**: centre-crop per tile (stride 256, 128 px context
  pad), no overlap blending — each output pixel from exactly one forward. The
  prob ceiling (max 0.913 on 2011s) is model calibration under noisy labels,
  not a stitching artifact; it further argues for per-year threshold selection.
- **Training**: bce_dice all tiers, blocked-val early stop on `val_iou_bt` for
  citywide — circular labels but IoU-based *ranking* of checkpoints is far less
  exposed than the threshold *value* selection.
- **Nits, recorded**: production cuts at `int(round(thr*254))`, qc_indep at
  `thr*254.0` unrounded — comparisons shift by at most one u8 step (~0.004);
  morphology runs in 4096-row chunks with no halo (seam pixels every 4096 rows;
  immaterial at measured effect sizes).

## What changes before the 36-run

1. **Threshold policy decision (Kam)** — the only recipe change gating launch.
2. Everything else in postproc is **post-GPU and re-derivable**: masks re-cut
   from prob rasters on free CPU. The A100 spend buys prob rasters and is
   insulated from every finding above.
3. Attribute fixes (kernel units, area_m2, vector filter, simplify, stale
   comment) — zero-GPU cleanup, before anything consumes GPKG attributes.
4. Anchor-labels A/B — pre-registered experiment, after the 36-run or in
   parallel on a spare window; would apply to a future epoch, not this one.

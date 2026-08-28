# Per-crown TOUCH / COVER — 2009, arms `fullext_sectors_v1`, `rgb3_nodeb`

## Read this before quoting a number

**This is not ground truth.** The crown layer is itself model output — phase 0 instance segmentation anchored to the 2020 hand annotations — not hand-drawn truth.

**Shared ancestry.** The crown layer (phase 0) and `MASK_2020` (`phase3/edmonds_canopy_mask_2020.tif`, the training key here) BOTH descend from the same 2020 hand annotations. Independence is at the LABEL-PATHWAY level — these crowns never entered these models' training labels — not total independence.

**Temporal confound.** 2020 crowns scored against 2009 predictions makes real 2009->2020 planting count as model error, and real removal count as model credit. Same family as CLAUDE.md rule 5's circularity ban. Therefore **absolute touch rates and cover fractions are NOT quotable**; only the ARM-vs-ARM delta on the identical crown set below is interpretable.

## Provenance gate (read from each arm's own run manifest, not a tag list)

| arm | status | evidence |
|---|---|---|
| `fullext_sectors_v1` | **clean** | citywide 2020-mask labels, no add-overlay |
| `rgb3_nodeb` | **clean** | citywide 2020-mask labels, no add-overlay |

- `fullext_sectors_v1` manifest: `G:\My Drive\treedata\phase4\runs\20260827T061455Z_2009_fullext_sectors_v1_tile\manifest.json`
- `rgb3_nodeb` manifest: `G:\My Drive\treedata\phase4\runs\20260828T150856Z_2009_rgb3_nodeb_tile\manifest.json`

**No exclusion needed** — every arm's manifest shows the plain citywide 2020-mask recipe with no add-canopy overlay, so the crown layer is fully held out for all of them.

## Footprint

- Common valid footprint (INTERSECTION of `!= 255` across all arms): **198,770,664 px** = 799.3 ha true
- Of which scorable against the reference (curve/threshold work only): 198,770,664 px
- Crown gate: in-grid pixels >= 1 AND valid fraction (`n_valid / n_rast`) >= 0.90, so only crowns genuinely inside the scored footprint count. Rasterisation `all_touched=False`.
- Crowns loaded 222,435 -> dropped 0 with no in-grid pixels, 179,976 outside/partly outside the footprint, 0 contaminated -> **42,459 scored**.
- AOI-restricted inference writes at BLOCK granularity (WORKPLAN 1.5, 'AOI block-leak'), so valid pixels extend beyond the sector rects; the sector table below separates in-sector crowns from leaked-block crowns.

## Thresholds — one per arm, and why

| arm | threshold | DN cut | reason |
|---|---|---|---|
| `fullext_sectors_v1` | 0.5000 | 127 | matched to `fullext_sectors_v1`@0.50 (precision 0.8472); thr 0.5000, pixel recall 0.6989 |
| `rgb3_nodeb` | 0.5039 | 128 | matched to `fullext_sectors_v1`@0.50 (precision 0.8472); thr 0.5039, pixel recall 0.5990 |

### Pixel-curve self-check (imported machinery — compare to `arm_pr_curves_2009.md`)

| arm | AUROC | PR-AUC (AP) | pixel recall@0.5 | pixel precision@0.5 |
|---|---|---|---|---|
| `fullext_sectors_v1` | 0.9210 | 0.8632 | 0.6989 | 0.8472 |
| `rgb3_nodeb` | 0.9063 | 0.8365 | 0.6567 | 0.8306 |

## Overall (identical crown set for every arm)

| group | crowns | touch | cover med | q25 | q75 | >=0.25 | >=0.50 | >=0.75 |
|---|---|---|---|---|---|---|---|---|
| `fullext_sectors_v1` | 42,459 | 0.8166 | 0.9757 | 0.3352 | 1.0000 | 0.7659 | 0.7158 | 0.6421 |
| `rgb3_nodeb` | 42,459 | 0.7726 | 0.7955 | 0.0524 | 1.0000 | 0.6998 | 0.6262 | 0.5237 |

## By RECOMPUTED size class (TRUE EPSG:26910 area — the stored `area_m2` and `size_class` are Web-Mercator-inflated 2.2215x and are NOT used)

Bins are true m², with the equivalent circular diameter in brackets.

**`fullext_sectors_v1`**

| group | crowns | touch | cover med | q25 | q75 | >=0.25 | >=0.50 | >=0.75 |
|---|---|---|---|---|---|---|---|---|
| 0-5 m² [0.0-2.5 m] | 2,029 | 0.4298 | 0.0000 | 0.0000 | 1.0000 | 0.3938 | 0.3588 | 0.3351 |
| 5-10 m² [2.5-3.6 m] | 3,780 | 0.5386 | 0.1178 | 0.0000 | 1.0000 | 0.4735 | 0.4259 | 0.3854 |
| 10-25 m² [3.6-5.6 m] | 12,949 | 0.7353 | 0.8352 | 0.0000 | 1.0000 | 0.6634 | 0.5995 | 0.5284 |
| 25-50 m² [5.6-8.0 m] | 12,939 | 0.9044 | 1.0000 | 0.6429 | 1.0000 | 0.8500 | 0.7943 | 0.7089 |
| 50-100 m² [8.0-11.3 m] | 9,047 | 0.9765 | 1.0000 | 0.8696 | 1.0000 | 0.9570 | 0.9240 | 0.8380 |
| 100-250 m² [11.3-17.8 m] | 1,713 | 0.9942 | 0.9904 | 0.8885 | 1.0000 | 0.9825 | 0.9644 | 0.8932 |
| >=250 m² [>=17.8 m] | 2 | 1.0000 | 0.9104 | 0.8808 | 0.9400 | 1.0000 | 1.0000 | 1.0000 |

**`rgb3_nodeb`**

| group | crowns | touch | cover med | q25 | q75 | >=0.25 | >=0.50 | >=0.75 |
|---|---|---|---|---|---|---|---|---|
| 0-5 m² [0.0-2.5 m] | 2,029 | 0.3568 | 0.0000 | 0.0000 | 0.9620 | 0.3149 | 0.2918 | 0.2711 |
| 5-10 m² [2.5-3.6 m] | 3,780 | 0.4587 | 0.0000 | 0.0000 | 1.0000 | 0.3989 | 0.3492 | 0.3114 |
| 10-25 m² [3.6-5.6 m] | 12,949 | 0.6709 | 0.5342 | 0.0000 | 1.0000 | 0.5804 | 0.5096 | 0.4413 |
| 25-50 m² [5.6-8.0 m] | 12,939 | 0.8680 | 0.8942 | 0.3497 | 1.0000 | 0.7827 | 0.6973 | 0.5844 |
| 50-100 m² [8.0-11.3 m] | 9,047 | 0.9646 | 0.9318 | 0.6338 | 1.0000 | 0.9136 | 0.8296 | 0.6661 |
| 100-250 m² [11.3-17.8 m] | 1,713 | 0.9912 | 0.9041 | 0.7016 | 1.0000 | 0.9667 | 0.9025 | 0.7023 |
| >=250 m² [>=17.8 m] | 2 | 1.0000 | 0.8480 | 0.8186 | 0.8774 | 1.0000 | 1.0000 | 1.0000 |

## By sector ( `(none)` = AOI block-leak ground, outside the sector rects )

**`fullext_sectors_v1`**

| group | crowns | touch | cover med | q25 | q75 | >=0.25 | >=0.50 | >=0.75 |
|---|---|---|---|---|---|---|---|---|
| (none) | 3,862 | 0.7921 | 0.9224 | 0.1597 | 1.0000 | 0.7354 | 0.6763 | 0.5948 |
| S1 | 3,398 | 0.8976 | 1.0000 | 0.8443 | 1.0000 | 0.8623 | 0.8296 | 0.7793 |
| S2 | 9,632 | 0.9001 | 1.0000 | 0.8405 | 1.0000 | 0.8664 | 0.8332 | 0.7804 |
| S3 | 7,034 | 0.7553 | 0.8538 | 0.0114 | 1.0000 | 0.6979 | 0.6423 | 0.5533 |
| S4 | 10,406 | 0.7475 | 0.8235 | 0.0000 | 1.0000 | 0.6813 | 0.6171 | 0.5353 |
| S5 | 8,127 | 0.8367 | 0.9653 | 0.4452 | 1.0000 | 0.7884 | 0.7378 | 0.6571 |

**`rgb3_nodeb`**

| group | crowns | touch | cover med | q25 | q75 | >=0.25 | >=0.50 | >=0.75 |
|---|---|---|---|---|---|---|---|---|
| (none) | 3,862 | 0.7437 | 0.6955 | 0.0000 | 1.0000 | 0.6618 | 0.5831 | 0.4767 |
| S1 | 3,398 | 0.8714 | 1.0000 | 0.6072 | 1.0000 | 0.8264 | 0.7769 | 0.7004 |
| S2 | 9,632 | 0.8620 | 1.0000 | 0.5185 | 1.0000 | 0.8138 | 0.7548 | 0.6808 |
| S3 | 7,034 | 0.7201 | 0.6585 | 0.0000 | 1.0000 | 0.6436 | 0.5644 | 0.4562 |
| S4 | 10,406 | 0.6900 | 0.5282 | 0.0000 | 0.9923 | 0.5963 | 0.5129 | 0.4028 |
| S5 | 8,127 | 0.7902 | 0.7490 | 0.1103 | 1.0000 | 0.7111 | 0.6296 | 0.4990 |

## PAIRED comparison — the same crowns, both arms

Aggregate rates can agree while the two arms disagree crown by crown. These are the discordant counts (McNemar-style).

| stratum | crowns | touch: `fullext_sectors_v1` only | touch: `rgb3_nodeb` only | McNemar z (touch) | cover>=0.5: `fullext_sectors_v1` only | cover>=0.5: `rgb3_nodeb` only | mean cover delta (`rgb3_nodeb`-`fullext_sectors_v1`) |
|---|---|---|---|---|---|---|---|
| ALL | 42,459 | 2,111 | 244 | +38.47 | 3,990 | 184 | -0.0898 |
| 0-5 m² | 2,029 | 168 | 20 | +10.79 | 150 | 14 | -0.0686 |
| 5-10 m² | 3,780 | 334 | 32 | +15.79 | 326 | 36 | -0.0745 |
| 10-25 m² | 12,949 | 941 | 107 | +25.76 | 1,241 | 77 | -0.0839 |
| 25-50 m² | 12,939 | 530 | 59 | +19.41 | 1,297 | 41 | -0.0937 |
| 50-100 m² | 9,047 | 133 | 26 | +8.49 | 869 | 15 | -0.1028 |
| 100-250 m² | 1,713 | 5 | 0 | +2.24 | 107 | 1 | -0.0942 |
| >=250 m² | 2 | 0 | 0 | +0.00 | 0 | 0 | -0.0624 |

The McNemar z is **NOMINAL and overstated**: it assumes crowns are independent samples, and they are not — crowns are spatially clustered and CLAUDE.md rule 5 puts the effective independent sample size at ~5 sites, not tens of thousands. Use it to read the SIGN and the concentration across strata, never as a p-value. The cluster-level test below is the honest one.

### Cluster-level check — one paired delta per sector

| sector | crowns | touch `fullext_sectors_v1` | touch `rgb3_nodeb` | delta | mean cover `fullext_sectors_v1` | mean cover `rgb3_nodeb` | delta |
|---|---|---|---|---|---|---|---|
| (none) | 3,862 | 0.7921 | 0.7437 | -0.0484 | 0.6577 | 0.5641 | -0.0935 |
| S1 | 3,398 | 0.8976 | 0.8714 | -0.0262 | 0.8150 | 0.7572 | -0.0578 |
| S2 | 9,632 | 0.9001 | 0.8620 | -0.0381 | 0.8183 | 0.7423 | -0.0760 |
| S3 | 7,034 | 0.7553 | 0.7201 | -0.0353 | 0.6188 | 0.5427 | -0.0762 |
| S4 | 10,406 | 0.7475 | 0.6900 | -0.0575 | 0.5999 | 0.4959 | -0.1040 |
| S5 | 8,127 | 0.8367 | 0.7902 | -0.0465 | 0.7123 | 0.6011 | -0.1113 |

**Sign test over sector-level paired deltas — the honest test.** It respects the spatial clustering the McNemar z ignores.

- Over the **5 designed sectors**: `rgb3_nodeb` has the lower touch rate in **5 of 5**, two-sided p = **0.0625**. *This is the number to quote.*
- Including the `(none)` AOI-leak bucket (6 of 6, p = 0.0312) — reported for completeness only; leaked blocks are ground adjacent to the same sectors, not an independent cluster, so this p is optimistic.

**What this sign test CANNOT tell you.** It clusters on SPACE, not on TRAINING RUNS — and there is exactly ONE run per arm here. A single training run that landed slightly low by seed is worse in *every* sector, so spatial consistency cannot separate 'this recipe is worse' from 'this run is worse'. The rerun noise floor (recall sd .0100, n=5, same seed — itself a LOWER bound) is the scale the recipe-level question lives on, and it is not measured by anything on this page. Treat the sign test as evidence about THESE TWO RASTERS, and leave the recipe verdict where the pre-registered read put it.

---

Generated by `qc/phase4_crown_touch.py`. Crown layer: `D:\edmonds-pipeline\backup\inference\edmonds_crowns_2020.gpkg`. Analysis only — writes no row to `qc_indep_report.csv`.
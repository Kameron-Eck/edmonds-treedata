# chm2005 validation — certified-flat ground (S3.3)

Reference: `verified_background_lidar_2005_2016.tif` — 691,905 cells (2.77 km²) measured under 2 m in **both** epochs, then
eroded 6 m so no cell can excuse a tall reading as a clipped crown edge.

On this ground every product should read ~0 m. This is the test that exposed
the original raster.

| product | mean | p50 | p90 | p99 | asserts >2 m | coverage of flat ground |
|---|---|---|---|---|---|---|
| `chm2005 (new, 2 m)` | 0.48 m | 0.40 | 1.00 | 2.00 | **0.17%** | 100.0% |
| `chm2    (2016, .5 m)` | 0.19 m | 0.00 | 0.60 | 1.80 | **0.01%** | 100.0% |
| `chm     (old, inflated)` | 0.86 m | 0.20 | 2.00 | 7.40 | **8.82%** | 96.3% |

## Verdict: **PASS**

- chm2005 asserts vegetation on **0.17%** of certified-flat ground; the old raster asserts it on **8.82%**.
- chm2 (2016 rebuild) asserts it on 0.01% — the standard a rebuild is expected to reach.
- chm2005 does **not** carry the neighbourhood-maximum inflation that made the original raster unusable on open ground.

## Vertical accuracy — both figures, never averaged

| source | figure | metric |
|---|---|---|
| Digital Coast | **6.3 cm** | fundamental vertical, 95th pct, mixed cover |
| InPort | **25 cm** avg, 15–25 cm soft-vegetated | different metric |

IMAGERY_FACTS is explicit that these are different metrics and that both are
recorded rather than reconciled. A 2 m cell dominates either figure anyway.

## What this does not establish

- Whether chm2005 improves the model (S3.5 — needs shared normalisation stats
  and 3 seeds per arm, or it repeats the underpowered chm2 test).
- Accuracy under canopy, where no independent reference exists.


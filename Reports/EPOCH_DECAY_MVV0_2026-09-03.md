# Does lidar epoch-distance matter? The in-house answer (MVV-0)

**Status: closes the KC/Shoreline epoch question on the record (adversarial review
2026-09-03, idea A). No new measurement — this assembles tracked Tier-1 numbers.
Pending Kam's K4 confirmation like the rest of the review block.**

## Question

King County holds lidar epochs Edmonds cannot get (notably a 2021 flight stopping at
the county line). Would more epochs improve lidar-as-INPUT for per-year models —
i.e., does the CHM's value decay with |imagery year − lidar year|?

## The 8-arm answer already in phase4/qc/tier1_results.csv (recall@prec0.75, test blocks)

| imagery year | in05 (2005 CHM) Δbase | in16 (2016 CHM) Δbase | era-matched epoch wins? |
|---|---|---|---|
| 2006s | +0.0226 | **+0.0461** | NO — the 10-years-distant CHM wins |
| 2011s | +0.0174 | +0.0208 | tie inside the honest floor (~.012) |
| 2016  | **+0.0748** | +0.0658 | NO — the 11-years-distant CHM wins |
| 2020  | +0.0351 | +0.0190 | (anchor; both CIs span 0) |

The era-matched epoch never beats the distant epoch beyond the replicate floor on
its own year. The two significant orderings go the WRONG way for epoch-currency.
The bootstrap CIs (phase4/qc/tier1_bootstrap_ci.csv) confirm all six non-2020
input deltas positive-significant — the INPUT effect is real; the EPOCH effect
is not detectable inside it.

## Mechanism

The model uses the CHM as structural context (where tall things stand, texture of
canopy vs ground), not as a current-year height measurement. Structure at 2 m
resolution changes slowly enough over 10–15 years that the finer, cleaner product
(chm2, 50 cm, rebuilt from raw points) beats the temporally-nearer coarse one
(chm2005, 2 m) even on 2006 imagery — resolution-and-quality beats era. Consistent
with: chm2005-input losing to chm2-input on 2006s (+.023 vs +.046).

## Caveats carried with this finding

- Reference-epoch leakage was raised against the input verdict and BOUNDED by the
  era-matched rescore (C-CAP 2016 reference): at matched precision the input wins
  are reference-stable, 6/6 arms positive under both references (dense sweeps
  qc_indep_sweep_*_ccap_2016_hires_lc_sample-test.csv).
- 2006s scores on ~9.3% of the footprint of the other years (1 m GSD).
- Two epochs, three years: this bounds the epoch effect at ≲ the honest floor per
  decade; it cannot fit a decay curve. That is exactly why it is NOT worth buying
  more epochs to refine: the bound already sits below the decision-relevant size.

## Decision consequence

Per-year recipe: use the best-QUALITY CHM (chm2) as input everywhere lidar input is
used; do not chase epoch-nearness; KC/Shoreline acquisition for epoch science is
NOT-WORTH-IT pre-36-run (master board, WORKPLAN.md).

## Addendum — C1 lidar-epoch anchors (2026-09-03, test AOI, buildings IGNOREd)

Physical reference = epoch CHM >= 2 m, building+2 m excluded (still includes
power lines/tall shrubs — a "tall vegetation-like surface" reference):

| arm | reference | recall | precision | independence |
|---|---|---|---|---|
| 2016_base | chm2 (own epoch) | .7512 | .7118 | CLEAN — no lidar in the model |
| 2016_in16 | chm2 | .6999 | .8901 | **CIRCULAR — chm2 is also the arm's INPUT; partly self-agreement, never quote as accuracy** |
| 2006s_base | chm2005 (1 yr off) | .4597 | .8666 | clean; low recall = the weak year, high precision = what fires is real tall veg |
| 2011s_base | chm2005 (6 yr stale) | .6363 | .7902 | clean but includes real 2005→2011 change — a bound, not truth |

2016_base agreeing with physical lidar at ~the same level as with C-CAP is the
first zero-circularity evidence that reference error is not dominating the 2016
scores. Rows live in qc_indep_report.csv (ref *_canopy2m_binary, aoi sample-test).

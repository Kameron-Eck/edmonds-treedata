"""Q136: would reference-sample area estimation actually fix the threshold problem, and does
it work at the sample size P3 plans? MEASUREMENT ONLY - nothing is changed in the pipeline.

The pipeline computes area as `total_canopy_px * pixel_area` (phase3_semantic_dev.py:1722):
a MAP COUNT off a thresholded mask. it.73 measured the threshold moving the call rate from
22.0% to 30.5% across years, so the deliverable inherits that directly.

The Olofsson/CEOS alternative stratifies BY THE MAP and estimates from a reference sample:
    A_hat = sum_h W_h * ybar_h
where W_h is the map's own stratum weight and ybar_h the reference canopy rate in stratum h.
Its key property is that it is unbiased for the reference prevalence REGARDLESS of where the
threshold sat - the map is used only to stratify, never to count.

Two things are tested here, because the first alone would be near-tautological:
  (1) how far map-count drifts with threshold, against how far the stratified estimate drifts;
  (2) whether the stratified estimator still works at n=250/yr, P3's planned budget, by
      simulating the sampling many times rather than assuming the asymptotics.

Honest framing: C-CAP stands in for truth here. It is not truth. This measures whether the
ESTIMATOR removes threshold sensitivity, not whether C-CAP is right.
"""
import numpy as np, rasterio
from sampler import sample
from pathlib import Path

CCAP = r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif'
M = Path(r'G:\My Drive\treedata\phase4\masks')
CANOPY = [9, 10, 11, 13, 16]
YEAR, NSIM, NSAMP = 2013, 4000, 250
rng = np.random.default_rng(0)

d = np.load('pts.npz', allow_pickle=True); X, Y = d['X'], d['Y']
crs = rasterio.open(CCAP).crs
cc, _ = sample(CCAP, X, Y, crs)
pv, nd = sample(M / f'edmonds_canopy_prob_{YEAR}_citywide_rgb.tif', X, Y, crs)

ok = (cc != 0) & (pv != 255)
if nd is not None: ok &= (pv != nd)
ref = np.isin(cc, CANOPY)[ok]          # reference canopy indicator
prob = pv[ok].astype(np.float32)
N = ref.size
TRUTH = float(ref.mean())
print(f'{N:,} usable points; reference canopy prevalence = {100*TRUTH:.2f}%\n')

print(f'{"thresh":>7}{"MAP-COUNT %":>13}{"map bias pp":>13}'
      f'{"STRAT %(full)":>15}{"strat bias pp":>15}{"n=250 mean":>12}{"n=250 SD":>10}{"95% halfwidth":>15}')
for t in (0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70):
    call = prob >= t * 254.0
    W1 = float(call.mean()); W0 = 1.0 - W1
    map_pct = W1
    # full-census stratified estimate
    y1 = float(ref[call].mean()) if call.any() else 0.0
    y0 = float(ref[~call].mean()) if (~call).any() else 0.0
    strat_full = W1 * y1 + W0 * y0
    # simulate n=250, allocated proportionally but with a floor of 40 per stratum
    n1 = int(np.clip(round(NSAMP * W1), 40, NSAMP - 40)); n0 = NSAMP - n1
    i1 = np.flatnonzero(call); i0 = np.flatnonzero(~call)
    est = np.empty(NSIM)
    for k in range(NSIM):
        s1 = ref[rng.choice(i1, n1, replace=False)]
        s0 = ref[rng.choice(i0, n0, replace=False)]
        est[k] = W1 * s1.mean() + W0 * s0.mean()
    print(f'{t:>7.2f}{100*map_pct:>13.2f}{100*(map_pct-TRUTH):>+13.2f}'
          f'{100*strat_full:>15.2f}{100*(strat_full-TRUTH):>+15.2f}'
          f'{100*est.mean():>12.2f}{100*est.std():>10.2f}'
          f'{100*1.96*est.std():>15.2f}')

print(f'\nREAD: "map bias pp" is how far the pipeline\'s own area number sits from the reference,')
print('purely as a function of where the threshold was put. "strat bias pp" is the same for the')
print('Olofsson estimator. The n=250 columns say whether P3\'s planned budget is enough to use it.')

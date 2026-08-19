"""Q121 (point-sampled): is the cross-year recall wander an OPERATING-POINT series?

Prior work, so this is not overclaimed: the 2026-08-18 CHATLOG entry already dissolved a
per-year spread by holding the RECIPE constant, at a FIXED threshold of 0.5. A fixed threshold
is NOT a matched operating point - the same threshold gives different call rates on different
models. This holds recipe constant AND call rate constant.
"""
import numpy as np
from sampler import sample
from pathlib import Path

M = Path(r'G:\My Drive\treedata\phase4\masks')
CCAP = Path(r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif')
CANOPY = [9, 10, 11, 13, 16]
YEARS = [2000, 2002, 2005, 2007, 2009, 2013, 2015, 2021]

d = np.load('pts.npz', allow_pickle=True)
X, Y = d['X'], d['Y']
import rasterio
crs = rasterio.open(CCAP).crs
print(f'{X.size:,} sample points', flush=True)

cc, _ = sample(CCAP, X, Y, crs)
print('C-CAP sampled', flush=True)

vals, ok_all = {}, (cc != 0)
for y in YEARS:
    f = M / f'edmonds_canopy_prob_{y}_citywide_rgb.tif'
    if not f.exists():
        print(f'  {y}: no raster'); continue
    v, nd = sample(f, X, Y, crs)
    ok = (v != 255)
    if nd is not None: ok &= (v != nd)
    vals[y] = v; ok_all &= ok
    print(f'  {y}: sampled, valid {int(ok.sum()):,}', flush=True)

have = sorted(vals)
n = int(ok_all.sum())
c_in = np.isin(cc, CANOPY)[ok_all]
V = {y: vals[y][ok_all].astype(np.float32) for y in have}
print(f'\nCOMMON footprint {n:,} of {X.size:,} points ({100*n/X.size:.1f}%); '
      f'C-CAP canopy {int(c_in.sum()):,} ({100*c_in.mean():.1f}% prevalence)\n')

def rec_at(v, rate):
    t = np.quantile(v, 1.0 - rate)
    return float((v[c_in] >= t).mean()), float(t) / 254.0

rates = [0.20, 0.25, 0.30, 0.35]
print('(A) RECALL AT A COMMON CALL RATE  -- recipe AND operating point both held constant')
print(f"{'year':<7}" + ''.join(f'{f"cr={r:.2f}":>10}' for r in rates))
tab = {y: [rec_at(V[y], r)[0] for r in rates] for y in have}
for y in have:
    print(f'{y:<7}' + ''.join(f'{x:>10.4f}' for x in tab[y]))
sp = [max(tab[y][i] for y in have) - min(tab[y][i] for y in have) for i in range(len(rates))]
print(f"{'SPREAD':<7}" + ''.join(f'{x:>10.4f}' for x in sp))

print('\n(B) THE SAME YEARS AT A FIXED THRESHOLD 0.5  -- recipe held, operating point NOT')
print(f"{'year':<7}{'call rate':>11}{'recall':>10}")
cr5, rc5 = [], []
for y in have:
    call = V[y] >= 0.5 * 254.0
    cr5.append(float(call.mean())); rc5.append(float(call[c_in].mean()))
    print(f'{y:<7}{cr5[-1]:>11.4f}{rc5[-1]:>10.4f}')
print(f"{'SPREAD':<7}{max(cr5)-min(cr5):>11.4f}{max(rc5)-min(rc5):>10.4f}")

print(f'\nSPREAD at fixed threshold 0.5      : {max(rc5)-min(rc5):.4f}')
print(f'SPREAD at matched call rate 0.30   : {sp[2]:.4f}')
print(f'reduction                          : {(max(rc5)-min(rc5))-sp[2]:+.4f}')
print('\nREAD: finding 3 quotes a cross-year honest-recall spread of about 0.28 (.50-.78).')
print('If (A) is much tighter than (B), the operating point was carrying part of that wander.')

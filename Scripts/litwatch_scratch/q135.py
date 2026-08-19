"""Q135/Q98: what does the model actually key on, and how much does it beat colour alone?

Running the trained U-Net for an ablation needs a GPU. This is the cheap proxy: sample the
model's own probability output at the same 162,829 points and compare it against the two
single-pixel colour features measured in it.75.

  AUC(model) vs AUC(brightness) -> how much context/texture buys over colour alone
  rank corr(model, brightness) vs rank corr(model, GRVI) -> which cue it RESEMBLES

Rank correlation is used so the comparison is invariant to each year's colour cast, which
it.72 showed is large and per-sensor.
"""
import numpy as np, rasterio
from sampler import sample
from pathlib import Path

CCAP = r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif'
M = Path(r'G:\My Drive\treedata\phase4\masks')
CANOPY = [9, 10, 11, 13, 16]
PAIRS = [('2000_king_rgb.tif', 2000), ('2005_king_rgb.tif', 2005), ('2009_king_rgb.tif', 2009),
         ('2013_king_rgb.tif', 2013), ('2021_king_rgb.tif', 2021)]

d = np.load('pts.npz', allow_pickle=True); X, Y = d['X'], d['Y']
crs = rasterio.open(CCAP).crs
cc, _ = sample(CCAP, X, Y, crs)
z = np.load('rg_cache.npz', allow_pickle=True)

def auc(score, pos):
    ok = np.isfinite(score); s, p = score[ok], pos[ok]
    r = np.argsort(np.argsort(s)) + 1.0
    n1 = float(p.sum()); n0 = float((~p).sum())
    if n1 < 10 or n0 < 10: return np.nan
    return (r[p].sum() - n1*(n1+1)/2) / (n1*n0)

def rankcorr(a, b, m):
    ra = np.argsort(np.argsort(a[m])); rb = np.argsort(np.argsort(b[m]))
    return float(np.corrcoef(ra, rb)[0, 1])

print(f"{'year':<7}{'AUC model':>11}{'AUC bright':>12}{'AUC GRVI':>10}"
      f"{'model gain':>12}{'corr(m,bright)':>16}{'corr(m,GRVI)':>14}")
for fn, yr in PAIRS:
    f = M / f'edmonds_canopy_prob_{yr}_citywide_rgb.tif'
    if not f.exists() or fn not in z.files:
        print(f'{yr:<7} missing'); continue
    pv, nd = sample(f, X, Y, crs)
    v = z[fn]; R, G = v[:, 0].astype(np.float32), v[:, 1].astype(np.float32)
    okc = (R + G) > 0
    okp = (pv != 255)
    if nd is not None: okp &= (pv != nd)
    pos = np.isin(cc, CANOPY); neg = (cc != 0) & ~pos
    keep = (pos | neg) & okc & okp
    gr = (G - R) / np.maximum(G + R, 1e-6)
    br = -(R + G)
    pf = pv.astype(np.float32)
    a_m = auc(np.where(keep, pf, np.nan), pos)
    a_b = auc(np.where(keep, br, np.nan), pos)
    a_g = auc(np.where(keep, gr, np.nan), pos)
    cb = rankcorr(pf, br, keep); cg = rankcorr(pf, gr, keep)
    print(f'{yr:<7}{a_m:>11.4f}{a_b:>12.4f}{a_g:>10.4f}{a_m-a_b:>+12.4f}'
          f'{cb:>+16.4f}{cg:>+14.4f}', flush=True)

print('\nREAD: "model gain" is how much the network buys over the best single-pixel colour cue.')
print('A LARGE gain means texture and context dominate and the colour instability found in it.72/75')
print('matters less than feared. The two correlations say which cue the model RESEMBLES - but')
print('resemblance is not causation, and only a channel ablation on the trained net settles Q98.')

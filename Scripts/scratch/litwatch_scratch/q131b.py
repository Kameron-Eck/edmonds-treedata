"""Q131 (decisive form): is the within-year GRVI variation LAND COVER or COLOUR CAST?

The first run found 2013's "fraction called green" ranging 0.179-0.843 across blocks of the
SAME image - 85% as large as the 0.78 between-year spread. But blocks genuinely differ in land
cover: a forested block IS greener than downtown. That confound has to be removed.

THE SEPARATOR: compare the SAME blocks across years.
  land cover drives it -> block ranking is STABLE between years (high rank correlation)
  colour cast drives it -> block ranking SHUFFLES between years (low/negative correlation)

Samples once and caches, because sampling is the expensive step on rasters with no overviews.
"""
import numpy as np, rasterio, os
from rasterio.warp import transform as warp_xy

CCAP = r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif'
FILES = ['2000_king_rgb.tif', '2005_king_rgb.tif', '2009_king_rgb.tif', '2013_king_rgb.tif',
         '2019_king_rgb.tif', '2021_king_rgb.tif', '2019_naip_rgbi.tif', '2016_snoh_rgbi.tif']
NB = 6
CACHE = 'rg_cache.npz'

d = np.load('pts.npz', allow_pickle=True)
X, Y = d['X'], d['Y']
crs = rasterio.open(CCAP).crs

if os.path.exists(CACHE):
    z = np.load(CACHE, allow_pickle=True)
    data = {k: z[k] for k in z.files}
    print(f'loaded cache with {len(data)} acquisitions', flush=True)
else:
    data = {}
for fn in FILES:
    if fn in data: continue
    p = rf'D:\edmonds-pipeline\Imagery\{fn}'
    try:
        with rasterio.open(p) as r:
            xs, ys = warp_xy(crs, r.crs, list(X), list(Y)) if r.crs != crs else (list(X), list(Y))
            v = np.array([s[:2] for s in r.sample(zip(xs, ys), indexes=[1, 2])], dtype=np.float32)
        data[fn] = v
        np.savez(CACHE, **data)
        print(f'  sampled {fn}', flush=True)
    except Exception as e:
        print(f'  {fn} ERROR {str(e)[:50]}', flush=True)

bx = np.clip(((X - X.min()) / (X.max() - X.min() + 1e-9) * NB).astype(int), 0, NB-1)
by = np.clip(((Y - Y.min()) / (Y.max() - Y.min() + 1e-9) * NB).astype(int), 0, NB-1)
bid = by * NB + bx

have = [f for f in FILES if f in data]
prof = {}
print(f"\n{'acquisition':<22}{'frac>.02':>10}{'blockMIN':>10}{'blockMAX':>10}{'range':>9}")
for fn in have:
    v = data[fn]; R, G = v[:, 0], v[:, 1]
    ok = (R + G) > 0
    gr = np.where(ok, (G - R) / np.maximum(G + R, 1e-6), np.nan)
    fr = {}
    for b in range(NB * NB):
        m = (bid == b) & ok
        if m.sum() >= 300: fr[b] = float((gr[m] > 0.02).mean())
    prof[fn] = fr
    vals = list(fr.values())
    print(f'{fn[:21]:<22}{float((gr[ok]>0.02).mean()):>10.4f}{min(vals):>10.4f}'
          f'{max(vals):>10.4f}{max(vals)-min(vals):>9.4f}')

from itertools import combinations
def spearman(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])

print('\nPER-BLOCK RANK CORRELATION BETWEEN ACQUISITIONS')
print('(high = the same blocks are green every year = LAND COVER)')
print('(low  = the green blocks move between years  = COLOUR CAST)')
rows = []
for a, b in combinations(have, 2):
    common = sorted(set(prof[a]) & set(prof[b]))
    if len(common) < 8: continue
    r = spearman([prof[a][k] for k in common], [prof[b][k] for k in common])
    rows.append((r, a, b))
for r, a, b in sorted(rows):
    print(f'  {r:+.3f}   {a[:20]:<21} vs {b[:20]}')
if rows:
    rs = [r for r, _, _ in rows]
    print(f'\nmean rank correlation {np.mean(rs):+.3f}   min {min(rs):+.3f}   max {max(rs):+.3f}')
print('\nREAD: if the mean is HIGH (>0.7) the within-year spread is mostly real land cover and the')
print('it.72 caveat holds. If it is LOW or mixed, the green blocks MOVE between years, which land')
print('cover cannot do over a few years - that would be spatially varying CAST, and no GRVI use,')
print('within-year or across, is safe without normalisation.')

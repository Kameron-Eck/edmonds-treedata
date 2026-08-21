"""Q131: does the colour cast vary WITHIN a single acquisition?

it.72 concluded that cross-year GRVI is unsafe but WITHIN-year use survives "because the cast
is global". That caveat is load-bearing and it is an ASSUMPTION, not a measurement. Aerial
mosaics are built from many frames, each separately colour-balanced, with vignetting toward
frame edges - so the cast may vary spatially, in which case within-year use is compromised too.

Test: split the city into blocks, compute GRVI stats per block, and ask how much of the total
GRVI variation is BETWEEN blocks. Compare that against the between-YEAR variation already
measured (frac>.02 spanning 0.11-0.89).
"""
import numpy as np, rasterio
from sampler import sample

CCAP = r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif'
YEARS = [('2000_king_rgb.tif', 3), ('2013_king_rgb.tif', 3), ('2019_king_rgb.tif', 3),
         ('2021_king_rgb.tif', 3), ('2019_naip_rgbi.tif', 4)]
NB = 6  # NB x NB grid of blocks

d = np.load('pts.npz', allow_pickle=True)
X, Y = d['X'], d['Y']
crs = rasterio.open(CCAP).crs
print(f'{X.size:,} points, {NB}x{NB} spatial blocks\n', flush=True)

# block id from position
bx = np.clip(((X - X.min()) / (X.max() - X.min() + 1e-9) * NB).astype(int), 0, NB-1)
by = np.clip(((Y - Y.min()) / (Y.max() - Y.min() + 1e-9) * NB).astype(int), 0, NB-1)
bid = by * NB + bx

def rgb(path):
    import rasterio as rio
    from rasterio.warp import transform as warp_xy
    with rio.open(path) as r:
        xs, ys = warp_xy(crs, r.crs, list(X), list(Y)) if r.crs != crs else (list(X), list(Y))
        v = np.array([s[:3] for s in r.sample(zip(xs, ys), indexes=[1, 2, 3])], dtype=np.float32)
    return v

print(f"{'acquisition':<22}{'GRVI mu':>9}{'frac>.02':>10}{'blockMIN':>10}{'blockMAX':>10}"
      f"{'blockRANGE':>12}{'betweenBlockVar%':>18}")
for fn, nb in YEARS:
    p = rf'D:\edmonds-pipeline\Imagery\{fn}'
    try:
        v = rgb(p)
    except Exception as e:
        print(f'{fn[:21]:<22} ERROR {str(e)[:40]}'); continue
    ok = np.any(v > 0, axis=1)
    R, G = v[:, 0], v[:, 1]
    gr = np.where(ok, (G - R) / np.maximum(G + R, 1e-6), np.nan)
    fr, mu = [], []
    for b in range(NB * NB):
        m = (bid == b) & ok
        if m.sum() < 300: continue
        fr.append(float((gr[m] > 0.02).mean())); mu.append(float(np.nanmean(gr[m])))
    if len(fr) < 6:
        print(f'{fn[:21]:<22} too few populated blocks'); continue
    gv = gr[ok]
    tot = float(np.nanvar(gv))
    # between-block variance of the block MEANS, as a share of total pixel variance
    btw = float(np.var(mu))
    print(f'{fn[:21]:<22}{np.nanmean(gv):>+9.4f}{float((gv>0.02).mean()):>10.4f}'
          f'{min(fr):>10.4f}{max(fr):>10.4f}{max(fr)-min(fr):>12.4f}'
          f'{100*btw/max(tot,1e-9):>17.1f}%', flush=True)

print('\nREAD: blockRANGE is the spread of "fraction called green" ACROSS PARTS OF THE SAME IMAGE.')
print('Compare it against the BETWEEN-YEAR spread of 0.78 (2019 King .1146 vs 2019 NAIP .8919).')
print('A large within-year range would mean the it.72 caveat - that within-year GRVI survives')
print('because the cast is global - is WRONG, and no GRVI use is safe without normalisation.')

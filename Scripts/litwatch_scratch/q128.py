"""Q128: does MODEL DISAGREEMENT predict per-year error WITHOUT labels?

The project's hardest practical problem: 17 acquisitions, one hand-labelled year. Baek 2022
(tracker ID 153, agreement-on-the-line) says OOD accuracy can be estimated from unlabelled
target data using several models' mutual agreement. We already own the ingredients - 2000,
2002, 2013 and 2015 each carry 4-5 independently trained variants.

Design, with it.68's lesson applied: agreement is computed at a MATCHED CALL RATE, never at a
matched threshold, or the result is just a threshold-difference map.

VALIDATION IS THE POINT. Disagreement is only useful if it tracks error where error IS
measurable. So for the same years, measure recall against C-CAP and see whether the two rank
the years the same way. If they do, disagreement becomes a reliability proxy for the years that
have no reference at all.
"""
import numpy as np, rasterio, geopandas as gpd, gc, itertools
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.features import geometry_mask
from pathlib import Path

CITY = Path(r'G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp')
CCAP = Path(r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif')
M    = Path(r'G:\My Drive\treedata\phase4\masks')
CANOPY, DECIM, CR = [9, 10, 11, 13, 16], 6, 0.30
VARIANTS = ['', '_citywide_rgb', '_xsensor_rgb', '_xsensor_train', '_xsensor_sample']
YEARS = [2000, 2002, 2013, 2015]

with rasterio.open(CCAP) as c:
    H, W = c.height // DECIM, c.width // DECIM
    tr, crs = c.transform * Affine.scale(DECIM), c.crs
    cc = c.read(1, out_shape=(H, W), resampling=Resampling.nearest)

def warp(p):
    with rasterio.open(p) as r:
        with WarpedVRT(r, crs=crs, transform=tr, width=W, height=H,
                       resampling=Resampling.nearest) as v:
            return v.read(1), r.nodata

g = gpd.read_file(CITY).to_crs(crs)
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
inside = ~geometry_mask([geom], out_shape=cc.shape, transform=tr, invert=False)
base = inside & (cc != 0)
print(f'city cells {int(inside.sum()):,}   with C-CAP data {int(base.sum()):,}', flush=True)

print(f"\n{'year':<7}{'variants':>9}{'footprint':>12}{'meanPairDisagree':>19}"
      f"{'minPair':>10}{'maxPair':>10}{'recall(cr=.30)':>16}", flush=True)
rows = []
for y in YEARS:
    files = [(v, M / f'edmonds_canopy_prob_{y}{v}.tif') for v in VARIANTS]
    files = [(v, f) for v, f in files if f.exists()]
    if len(files) < 2:
        print(f'{y:<7} only {len(files)} variant - skipped', flush=True); continue
    # pass 1: common footprint for THIS year's variants
    fp = base.copy()
    for v, f in files:
        pr, nd = warp(f); ok = (pr != 255)
        if nd is not None: ok &= (pr != nd)
        fp &= ok; del pr, ok; gc.collect()
    n = int(fp.sum())
    if n < 20000:
        print(f'{y:<7} common footprint only {n:,} - skipped', flush=True); continue
    c_in = np.isin(cc, CANOPY)[fp]
    # pass 2: binarise each variant at the SAME call rate
    calls = {}
    for v, f in files:
        pr, _ = warp(f); vec = pr[fp].astype(np.float32); del pr; gc.collect()
        t = np.quantile(vec, 1.0 - CR)
        calls[v] = vec >= t
        del vec; gc.collect()
    ds = [float((calls[a] != calls[b]).mean()) for a, b in itertools.combinations(calls, 2)]
    rec = float(np.mean([calls[v][c_in].mean() for v in calls]))
    rows.append((y, len(files), n, float(np.mean(ds)), min(ds), max(ds), rec))
    print(f'{y:<7}{len(files):>9}{n:>12,}{np.mean(ds):>19.4f}{min(ds):>10.4f}'
          f'{max(ds):>10.4f}{rec:>16.4f}', flush=True)
    del calls; gc.collect()

if len(rows) >= 3:
    d = np.array([r[3] for r in rows]); rc = np.array([r[6] for r in rows])
    print(f'\nPearson r(disagreement, recall) = {np.corrcoef(d, rc)[0,1]:+.4f}  over n={len(rows)} years')
    print('ranking by DISAGREEMENT (worst first):', [r[0] for r in sorted(rows, key=lambda x:-x[3])])
    print('ranking by RECALL       (worst first):', [r[0] for r in sorted(rows, key=lambda x: x[6])])
print('\nREAD: a strong NEGATIVE correlation means high disagreement marks the years the model')
print('does worst on - i.e. disagreement is a usable LABEL-FREE reliability proxy, and could be')
print('reported for the years that have no reference at all. A flat or positive correlation means')
print('it is not, and the idea should be dropped rather than quietly kept.')

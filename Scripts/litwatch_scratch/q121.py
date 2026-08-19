"""Q121: is the cross-year recall wander (.50-.78, finding 3) partly an OPERATING-POINT series?

Every year's threshold is calibrated separately. Q119 showed a fixed threshold can manufacture
a +0.225 "improvement" out of nothing. So: take ONE model recipe (citywide_rgb) across every
year it exists, score against ONE reference (C-CAP 2016) on ONE common footprint, and compare
  (a) recall at each year's own deployed threshold  [if a binary mask exists]
  (b) recall at a COMMON CALL RATE across all years
If the spread collapses in (b), a chunk of finding 3 is threshold calibration, not imagery.

Vintage caveat: C-CAP 2016 vs imagery 2000-2021. Real canopy change inflates the spread in
BOTH arms, so the SHRINKAGE from (a) to (b) is still interpretable; the levels are not.
"""
import numpy as np, rasterio, geopandas as gpd
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.features import geometry_mask
from pathlib import Path

CITY = Path(r'G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp')
CCAP = Path(r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif')
M    = Path(r'G:\My Drive\treedata\phase4\masks')
CANOPY, DECIM = [9, 10, 11, 13, 16], 6
YEARS = [2000, 2002, 2005, 2007, 2009, 2013, 2015, 2021]

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

probs, have = {}, []
for y in YEARS:
    f = M / f'edmonds_canopy_prob_{y}_citywide_rgb.tif'
    if not f.exists():
        print(f'  {y}: no citywide_rgb prob raster'); continue
    pr, nd = warp(f)
    ok = (pr != 255)
    if nd is not None: ok &= (pr != nd)
    probs[y] = (pr, ok); have.append(y)

common = inside & (cc != 0)
for y in have:
    common &= probs[y][1]
can = common & np.isin(cc, CANOPY)
print(f'\nyears with a citywide_rgb raster: {have}')
print(f'COMMON footprint across all of them: {int(common.sum()):,} cells '
      f'({100*common.sum()/max(inside.sum(),1):.1f}% of city)')
print(f'C-CAP canopy inside it: {int(can.sum()):,} ({100*can.sum()/max(common.sum(),1):.1f}% prevalence)\n')
if int(common.sum()) < 10000:
    print('common footprint too small to interpret - stopping'); raise SystemExit

v_all = {y: probs[y][0][common].astype(np.float32) for y in have}
c_in  = np.isin(cc, CANOPY)[common]

def recall_at_callrate(v, rate):
    t = np.quantile(v, 1.0 - rate)
    return float((v[c_in] >= t).mean()), float(t) / 254.0

print('RECALL AT A COMMON CALL RATE  (call rate = fraction of the common footprint called canopy)')
rates = [0.20, 0.25, 0.30, 0.35]
print(f"{'year':<7}" + ''.join(f'{f"cr={r:.2f}":>10}' for r in rates))
tab = {}
for y in have:
    row = [recall_at_callrate(v_all[y], r)[0] for r in rates]
    tab[y] = row
    print(f'{y:<7}' + ''.join(f'{x:>10.4f}' for x in row))
print(f"{'SPREAD':<7}" + ''.join(f'{max(tab[y][i] for y in have)-min(tab[y][i] for y in have):>10.4f}'
                                 for i in range(len(rates))))
print('\nfinding 3 quotes a cross-year honest-recall spread of about 0.28 (.50 to .78).')
print('Compare that with the SPREAD row above, which holds the operating point FIXED.')

print('\nWHAT THRESHOLD EACH YEAR NEEDS TO HIT A 0.30 CALL RATE')
print(f"{'year':<7}{'thr@cr=.30':>12}{'recall':>10}")
for y in have:
    r, t = recall_at_callrate(v_all[y], 0.30)
    print(f'{y:<7}{t:>12.4f}{r:>10.4f}')
print('\nREAD: if these thresholds differ wildly, the per-year calibration is doing a lot of')
print('work, and any cross-year recall comparison at per-year thresholds is confounded by it.')

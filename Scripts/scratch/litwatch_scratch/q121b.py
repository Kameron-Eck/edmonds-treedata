"""Q121 (streaming rewrite): is the cross-year recall wander an OPERATING-POINT series?

The first attempt held 8 full prob rasters in memory at once and thrashed. This version makes
two passes and never holds more than one raster.

Prior work this builds on, so it is not overclaimed: the 2026-08-18 CHATLOG entry already
dissolved a per-year spread by holding the RECIPE constant, at a FIXED threshold of 0.5.
A fixed threshold is NOT a matched operating point - the same threshold gives different call
rates on different models. This holds recipe constant AND call rate constant.
"""
import numpy as np, rasterio, geopandas as gpd, gc
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

files = {y: M / f'edmonds_canopy_prob_{y}_citywide_rgb.tif' for y in YEARS}
have = [y for y in YEARS if files[y].exists()]
print('years with a citywide_rgb raster:', have, flush=True)

# PASS 1 - build the common footprint one raster at a time
common = inside & (cc != 0)
for y in have:
    pr, nd = warp(files[y])
    ok = (pr != 255)
    if nd is not None: ok &= (pr != nd)
    common &= ok
    print(f'  pass1 {y}: valid {int(ok.sum()):,}  running common {int(common.sum()):,}', flush=True)
    del pr, ok; gc.collect()

n = int(common.sum())
c_in = np.isin(cc, CANOPY)[common]
print(f'\nCOMMON footprint {n:,} cells ({100*n/max(int(inside.sum()),1):.1f}% of city); '
      f'C-CAP canopy inside {int(c_in.sum()):,} ({100*c_in.mean():.1f}% prevalence)\n', flush=True)
if n < 10000:
    raise SystemExit('common footprint too small to interpret')

# PASS 2 - keep only the 1-D extracted vector per year
vals = {}
for y in have:
    pr, _ = warp(files[y])
    vals[y] = pr[common].copy()
    print(f'  pass2 {y}: extracted {vals[y].size:,}', flush=True)
    del pr; gc.collect()

def recall_at_callrate(v, rate):
    t = np.quantile(v, 1.0 - rate)
    return float((v[c_in] >= t).mean()), float(t) / 254.0

rates = [0.20, 0.25, 0.30, 0.35]
print('\nRECALL AT A COMMON CALL RATE (call rate = fraction of the common footprint called canopy)')
print(f"{'year':<7}" + ''.join(f'{f"cr={r:.2f}":>10}' for r in rates))
tab = {y: [recall_at_callrate(vals[y], r)[0] for r in rates] for y in have}
for y in have:
    print(f'{y:<7}' + ''.join(f'{x:>10.4f}' for x in tab[y]))
print(f"{'SPREAD':<7}" + ''.join(
    f'{max(tab[y][i] for y in have)-min(tab[y][i] for y in have):>10.4f}' for i in range(len(rates))))

print('\nTHRESHOLD EACH YEAR NEEDS TO HIT A 0.30 CALL RATE')
print(f"{'year':<7}{'thr':>10}{'recall':>10}")
for y in have:
    r, t = recall_at_callrate(vals[y], 0.30)
    print(f'{y:<7}{t:>10.4f}{r:>10.4f}')

print('\nAND THE OTHER DIRECTION - call rate each year produces at a FIXED threshold 0.5')
print(f"{'year':<7}{'call rate':>11}{'recall':>10}")
for y in have:
    v = vals[y]; call = v >= 0.5 * 254.0
    print(f'{y:<7}{float(call.mean()):>11.4f}{float(call[c_in].mean()):>10.4f}')

print('\nREAD: finding 3 quotes a cross-year honest-recall spread of about 0.28 (.50-.78).')
print('If the SPREAD row is much smaller, a large part of that wander is the operating point,')
print('not the imagery. The last table shows how far apart the years are at a FIXED threshold -')
print('which is what the prior recipe-controlled run used.')

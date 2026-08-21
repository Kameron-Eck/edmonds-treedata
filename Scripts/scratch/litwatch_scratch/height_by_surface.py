"""Q118: is the recall-by-height staircase just the overhang deficit in disguise?

Canopy over impervious is disproportionately short suburban crowns. Recompute
recall-by-CHM-band SEPARATELY over pervious ground and over impervious ground.
  staircase FLATTENS on pervious -> height was a proxy for overhang
  staircase SURVIVES on pervious -> two independent deficits, both need fixing
"""
import numpy as np, rasterio, geopandas as gpd
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.features import geometry_mask, rasterize
from pathlib import Path

CITY = Path(r'G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp')
BLDG = Path(r'G:\My Drive\treedata\building_footprints\data.json')
CCAP = Path(r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif')
CHM = Path(r'D:\edmonds-pipeline\Imagery\lidar_snoh_chm.tif')
IMP = Path(r'G:\My Drive\treedata\impervious\impervious_edmonds.tif')
PROB = Path(r'G:\My Drive\treedata\phase4\masks\edmonds_canopy_prob_2016.tif')
THRESH, CANOPY, DECIM = 0.509, [9, 10, 11, 13, 16], 4
BANDS = [(0, 2), (2, 5), (5, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 100)]

with rasterio.open(CCAP) as c:
    H, W = c.height // DECIM, c.width // DECIM
    tr = c.transform * Affine.scale(DECIM)
    crs = c.crs
    cc = c.read(1, out_shape=(H, W), resampling=Resampling.nearest)


def warp(path, **kw):
    with rasterio.open(path) as r:
        with WarpedVRT(r, crs=crs, transform=tr, width=W, height=H,
                       resampling=Resampling.nearest, **kw) as v:
            return v.read(1), r.nodata


dn, _ = warp(CHM, src_nodata=0, nodata=0)
pr, pr_nd = warp(PROB)
iv, i_nd = warp(IMP)

g = gpd.read_file(CITY).to_crs(crs)
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
inside = ~geometry_mask([geom], out_shape=cc.shape, transform=tr, invert=False)

b = gpd.read_file(BLDG).to_crs(crs)
b = b[b.geometry.notna() & b.geometry.is_valid]
bmask = rasterize(((geo, 1) for geo in b.geometry), out_shape=cc.shape,
                  transform=tr, fill=0, dtype='uint8').astype(bool)
imp = (iv > 0)
if i_nd is not None:
    imp &= (iv != i_nd)
under_imp = bmask | imp

hgt = (dn.astype(np.float32) - 1.0) * 0.2
hgt[dn == 0] = np.nan

valid = inside & (cc != 0) & np.isfinite(hgt) & (pr != 255)
if pr_nd is not None:
    valid &= (pr != pr_nd)
can = valid & np.isin(cc, CANOPY)
call = valid & (pr >= THRESH * 254.0)

print('RECALL BY CHM BAND, SPLIT BY WHAT LIES BENEATH  (2016 baseline, C-CAP city ref)')
print(f"{'band':<11}{'PERVIOUS':>10}{'n':>11}   {'IMPERVIOUS':>11}{'n':>10}   {'gap':>8}")
rows = []
for lo, hi in BANDS:
    m = can & (hgt >= lo) & (hgt < hi)
    mp = m & ~under_imp
    mi = m & under_imp
    np_, ni = int(mp.sum()), int(mi.sum())
    rp = int((mp & call).sum()) / max(np_, 1)
    ri = int((mi & call).sum()) / max(ni, 1)
    lab = f'{lo}-{hi} m' if hi < 100 else f'{lo}+ m'
    rows.append((lab, rp, np_, ri, ni))
    print(f'{lab:<11}{rp:>10.4f}{np_:>11,}   {ri:>11.4f}{ni:>10,}   {ri-rp:>+8.4f}')

pv = [r for r in rows if r[2] > 500]
iv_ = [r for r in rows if r[4] > 500]
print()
if pv:
    lo_p = pv[0][1]; hi_p = pv[-1][1]
    print(f'  PERVIOUS   staircase: {pv[0][0]} = {lo_p:.4f}  ->  {pv[-1][0]} = {hi_p:.4f}'
          f'   spread {hi_p-lo_p:+.4f}')
if iv_:
    lo_i = iv_[0][3]; hi_i = iv_[-1][3]
    print(f'  IMPERVIOUS staircase: {iv_[0][0]} = {lo_i:.4f}  ->  {iv_[-1][0]} = {hi_i:.4f}'
          f'   spread {hi_i-lo_i:+.4f}')
print()
print('READ: if the PERVIOUS spread is still large, the height effect is real and')
print('independent of overhang. If it collapses, height was standing in for overhang.')

"""Test STATE's suburban over-count hypothesis.

STATE holds that C-CAP inflates canopy by counting lawns and roofs BETWEEN yard trees
as "Upland Forest". If true, a substantial share of C-CAP canopy pixels should sit at
LOW lidar height. C-CAP's own height came from a photogrammetric stereo DSM; our CHM is
3DEP lidar - independent height sources, so this is a fair test.

Also runs the same test on the NDVI reference for contrast - though that one is partly
circular, since the NDVI reference REQUIRES CHM >= 2 m by construction.
"""
import numpy as np, rasterio, geopandas as gpd
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.features import geometry_mask
from pathlib import Path

CITY = Path(r'G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp')
CCAP = Path(r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif')
NDVI = Path(r'G:\My Drive\treedata\phase4\qc\ndvi_ref_2016.tif')
CHM = Path(r'D:\edmonds-pipeline\Imagery\lidar_snoh_chm.tif')
CANOPY = [9, 10, 11, 13, 16]
DECIM = 4

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

nd, nd_nodata = warp(NDVI)
dn, _ = warp(CHM, src_nodata=0, nodata=0)

g = gpd.read_file(CITY).to_crs(crs)
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
inside = ~geometry_mask([geom], out_shape=cc.shape, transform=tr, invert=False)

hgt = (dn.astype(np.float32) - 1.0) * 0.2
hgt[dn == 0] = np.nan
has_chm = inside & np.isfinite(hgt)

ccap_can = has_chm & np.isin(cc, CANOPY)
ndvi_can = has_chm & (nd == 2)
if nd_nodata is not None:
    ndvi_can &= (nd != nd_nodata)

print(f'city cells with CHM coverage: {int(has_chm.sum()):,} '
      f'({100*has_chm.sum()/max(inside.sum(),1):.1f}% of city)')
print()
BANDS = [(0, 1), (1, 2), (2, 3), (3, 5), (5, 10), (10, 20), (20, 100)]
print('HEIGHT DISTRIBUTION OF PIXELS EACH REFERENCE CALLS CANOPY')
print(f"{'CHM height':<14}{'C-CAP':>12}{'%':>8}   {'NDVI ref':>12}{'%':>8}")
tc = int(ccap_can.sum()); tn = int(ndvi_can.sum())
for lo, hi in BANDS:
    m = (hgt >= lo) & (hgt < hi)
    a = int((ccap_can & m).sum()); b = int((ndvi_can & m).sum())
    lab = f'{lo}-{hi} m' if hi < 100 else f'{lo}+ m'
    print(f'{lab:<14}{a:>12,}{100*a/max(tc,1):>7.2f}%   {b:>12,}{100*b/max(tn,1):>7.2f}%')
print(f"{'TOTAL':<14}{tc:>12,}{100:>7.2f}%   {tn:>12,}{100:>7.2f}%")
print()
for nm, m, t in (('C-CAP', ccap_can, tc), ('NDVI ref', ndvi_can, tn)):
    low = int((m & (hgt < 2)).sum())
    print(f'  {nm:<9} canopy below 2 m : {low:>10,}  = {100*low/max(t,1):5.2f}%')
print()
print('READ: STATE holds C-CAP over-counts by including lawn/roof BETWEEN yard trees.')
print('That predicts a LARGE share of C-CAP canopy at low lidar height. The NDVI')
print('reference requires CHM >= 2 m by construction, so its low-height share is a')
print('floor set by reprojection/edge effects, not evidence - use it only as a scale.')

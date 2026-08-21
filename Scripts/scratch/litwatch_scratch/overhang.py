"""Q115: on-building tall pixels - overhanging canopy (real miss) or miscalled roof (C-CAP error)?

Canopy overhanging a roof sits ABOVE the building height; a miscalled roof sits AT it.
Rasterise the per-building `height` attribute and compare against the lidar CHM on the
on-building pixels of the 'unmeasurable' band.
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
NDVI = Path(r'G:\My Drive\treedata\phase4\qc\ndvi_ref_2016.tif')
CHM = Path(r'D:\edmonds-pipeline\Imagery\lidar_snoh_chm.tif')
PROB = Path(r'G:\My Drive\treedata\phase4\masks\edmonds_canopy_prob_2016.tif')
THRESH, CANOPY, DECIM = 0.509, [9, 10, 11, 13, 16], 4

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


nd, nd_nd = warp(NDVI)
dn, _ = warp(CHM, src_nodata=0, nodata=0)
pr, pr_nd = warp(PROB)

g = gpd.read_file(CITY).to_crs(crs)
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
inside = ~geometry_mask([geom], out_shape=cc.shape, transform=tr, invert=False)

b = gpd.read_file(BLDG).to_crs(crs)
b = b[b.geometry.notna() & b.geometry.is_valid].copy()
b['h'] = b['height'].astype(float).fillna(0.0)
print(f'buildings {len(b):,}  height: median {b.h.median():.1f} m  '
      f'p10 {b.h.quantile(.1):.1f}  p90 {b.h.quantile(.9):.1f}  zero-height {int((b.h<=0).sum()):,}')
if 'heightScore' in b.columns:
    print(f'  heightScore: median {b.heightScore.astype(float).median():.2f}')

bh = rasterize(((geo, hh) for geo, hh in zip(b.geometry, b.h)), out_shape=cc.shape,
               transform=tr, fill=0.0, dtype='float32')
has_b = bh > 0

hgt = (dn.astype(np.float32) - 1.0) * 0.2
hgt[dn == 0] = np.nan
valid = inside & (cc != 0) & np.isfinite(hgt) & (pr != 255)
if nd_nd is not None:
    valid &= (nd != nd_nd)
if pr_nd is not None:
    valid &= (pr != pr_nd)

ccap_can = valid & np.isin(cc, CANOPY)
ndvi_can = valid & (nd == 2)
called = valid & (pr >= THRESH * 254.0)
miss = ccap_can & ~called
band = miss & ~ndvi_can
tall = band & (hgt >= 2)
onb = tall & has_b

d = (hgt - bh)[onb]
d = d[np.isfinite(d)]
n = d.size
print()
print(f'on-building tall band cells with a building height: {n:,}')
print()
print('CHM height MINUS building height  (positive = something above the roof)')
for lo, hi, lab in [(-99, -2, 'below roof by >2 m'), (-2, 1, 'AT roof (-2 to +1 m)'),
                    (1, 3, '+1 to +3 m'), (3, 6, '+3 to +6 m'),
                    (6, 12, '+6 to +12 m'), (12, 999, '+12 m or more')]:
    k = int(((d >= lo) & (d < hi)).sum())
    print(f'  {lab:<22}{k:>10,}  {100*k/max(n,1):5.2f}%')
print(f'  median delta {np.median(d):+.2f} m')
print()
at_roof = int(((d >= -2) & (d < 1)).sum())
above = int((d >= 1).sum())
below = int((d < -2).sum())
print(f'  AT roof   (likely C-CAP miscall) {at_roof:>10,}  {100*at_roof/max(n,1):5.2f}%')
print(f'  ABOVE roof (likely overhang)     {above:>10,}  {100*above/max(n,1):5.2f}%')
print(f'  BELOW roof (height mismatch)     {below:>10,}  {100*below/max(n,1):5.2f}%')
print()
print('CAVEATS: building heights are MODELLED estimates from a 2025-vintage vector')
print('product, matched against a ~2016 lidar CHM - so vintage and modelling error')
print('both blur the comparison. Treat the split as indicative, not exact.')

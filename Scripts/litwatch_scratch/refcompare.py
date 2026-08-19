"""Compare C-CAP and the NDVI+CHM reference ON IDENTICAL GROUND.

The famous 8.2 pp gap (C-CAP 29.5% vs NDVI 37.7%) was never measured on a common
footprint: C-CAP came from a rectangle covering ~80% of the city, the NDVI reference
from Snohomish imagery covering ~66.7% of it. This intersects
city boundary AND C-CAP valid AND NDVI-ref valid, then computes both canopy
fractions on exactly those cells. Read-only.
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
CANOPY = [9, 10, 11, 13, 16]
DECIM = 4

with rasterio.open(NDVI) as n:
    print(f'ndvi_ref_2016  {n.width}x{n.height} {n.crs} nodata={n.nodata} dtype={n.dtypes[0]}')
with rasterio.open(CCAP) as c:
    print(f'ccap_2016_edmonds {c.width}x{c.height} {c.crs} nodata={c.nodata}')

# grid on the C-CAP city raster (already city-clipped, 1 m)
with rasterio.open(CCAP) as c:
    H, W = c.height // DECIM, c.width // DECIM
    tr = c.transform * Affine.scale(DECIM)
    crs = c.crs
    cc = c.read(1, out_shape=(H, W), resampling=Resampling.nearest)

with rasterio.open(NDVI) as n:
    with WarpedVRT(n, crs=crs, transform=tr, width=W, height=H,
                   resampling=Resampling.nearest) as v:
        nd = v.read(1)
        n_nodata = n.nodata

g = gpd.read_file(CITY).to_crs(crs)
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
inside = ~geometry_mask([geom], out_shape=cc.shape, transform=tr, invert=False)

ccap_valid = inside & (cc != 0)
ndvi_valid = inside.copy()
if n_nodata is not None:
    ndvi_valid &= (nd != n_nodata)
common = ccap_valid & ndvi_valid

cell_km2 = abs(tr.a * tr.e) / 1e6
city_cells = int(inside.sum())


def pct(mask, arr, codes):
    n = int(mask.sum())
    if not n:
        return 0.0, 0
    return 100.0 * float(np.isin(arr[mask], codes).sum()) / n, n


print()
print('COVERAGE WITHIN THE CITY BOUNDARY')
print(f'  city cells            {city_cells:>12,}  = {city_cells*cell_km2:6.2f} km2  (100.0%)')
for nm, m in (('C-CAP valid', ccap_valid), ('NDVI-ref valid', ndvi_valid), ('COMMON', common)):
    k = int(m.sum())
    print(f'  {nm:<21} {k:>12,}  = {k*cell_km2:6.2f} km2  ({100*k/city_cells:5.1f}%)')

print()
print('CANOPY FRACTION, EACH ON ITS OWN FOOTPRINT')
a, na = pct(ccap_valid, cc, CANOPY)
b, nb = pct(ndvi_valid, nd, [2])
print(f'  C-CAP    {a:6.2f}%   over {na:,} cells')
print(f'  NDVI ref {b:6.2f}%   over {nb:,} cells')
print(f'  apparent gap {b-a:+.2f} pp   <- NOT like-for-like')

print()
print('CANOPY FRACTION ON THE *COMMON* FOOTPRINT  <- the honest comparison')
a2, n2 = pct(common, cc, CANOPY)
b2, _ = pct(common, nd, [2])
print(f'  C-CAP    {a2:6.2f}%')
print(f'  NDVI ref {b2:6.2f}%   over {n2:,} common cells')
print(f'  TRUE GAP {b2-a2:+.2f} pp')

print()
agree_can = int((common & np.isin(cc, CANOPY) & (nd == 2)).sum())
agree_non = int((common & ~np.isin(cc, CANOPY) & (nd != 2)).sum())
ccap_only = int((common & np.isin(cc, CANOPY) & (nd != 2)).sum())
ndvi_only = int((common & ~np.isin(cc, CANOPY) & (nd == 2)).sum())
tot = max(int(common.sum()), 1)
print('PER-PIXEL AGREEMENT ON THE COMMON FOOTPRINT')
print(f'  both canopy      {agree_can:>12,}  {100*agree_can/tot:5.2f}%')
print(f'  both non-canopy  {agree_non:>12,}  {100*agree_non/tot:5.2f}%')
print(f'  C-CAP only       {ccap_only:>12,}  {100*ccap_only/tot:5.2f}%')
print(f'  NDVI only        {ndvi_only:>12,}  {100*ndvi_only/tot:5.2f}%')
print(f'  DISAGREE         {ccap_only+ndvi_only:>12,}  {100*(ccap_only+ndvi_only)/tot:5.2f}%')

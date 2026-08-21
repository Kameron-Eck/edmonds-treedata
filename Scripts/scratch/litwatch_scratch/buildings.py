"""Q113: how much of the tall 'unmeasurable' band is BUILDINGS, not trees?

The CHM is height-above-ground and includes structures, so tall C-CAP-canopy pixels
that the NDVI reference rejects could be buildings C-CAP miscalled rather than trees
the model missed. building_footprints/data.json (GeoJSON, with per-building heights)
has been on disk since February and never used for this.
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

b = gpd.read_file(BLDG)
print(f'buildings loaded: {len(b):,}  crs={b.crs}')
b = b.to_crs(crs)
b = b[b.geometry.notna() & b.geometry.is_valid]
bmask = rasterize(((geo, 1) for geo in b.geometry), out_shape=cc.shape,
                  transform=tr, fill=0, dtype='uint8').astype(bool)
# dilate by one cell so roof edges and reprojection slop are covered
from scipy.ndimage import binary_dilation
try:
    bmask_d = binary_dilation(bmask, iterations=1)
except Exception:
    bmask_d = bmask
print(f'building pixels in city: {int((bmask & inside).sum()):,} '
      f'({100*(bmask & inside).sum()/max(inside.sum(),1):.2f}% of city); dilated '
      f'{int((bmask_d & inside).sum()):,}')

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
band = miss & ~ndvi_can                      # the 'unmeasurable' band
tall = band & (hgt >= 2)

nb = int(band.sum()); nt = int(tall.sum())
on_b = int((tall & bmask_d).sum())
off_b = nt - on_b
print()
print(f'"unmeasurable" band        {nb:>10,}')
print(f'  of which TALL (>=2 m)    {nt:>10,}  {100*nt/max(nb,1):5.2f}%')
print(f'    on a building footprint{on_b:>10,}  {100*on_b/max(nt,1):5.2f}% of tall')
print(f'    NOT on a building      {off_b:>10,}  {100*off_b/max(nt,1):5.2f}% of tall')
print()
print('REVISED SPLIT of all model misses of C-CAP canopy')
agree = int((miss & ndvi_can).sum()); tot = max(int(miss.sum()), 1)
real = agree + off_b
print(f'  real miss (both refs agree)              {agree:>10,}  {100*agree/tot:5.1f}%')
print(f'  real miss (tall, NOT a building)         {off_b:>10,}  {100*off_b/tot:5.1f}%')
print(f'  probable C-CAP error (tall ON building)  {on_b:>10,}  {100*on_b/tot:5.1f}%')
print(f'  short / ambiguous                        {nb-nt:>10,}  {100*(nb-nt)/tot:5.1f}%')
print()
print(f'  => REAL MISS total {real:,} = {100*real/tot:.1f}% of the shortfall')
print()
print('CAVEAT: canopy legitimately OVERHANGS buildings, and C-CAP folds an')
print('"impervious under canopy" class into canopy by design (iteration 61). So the')
print('on-building figure is an UPPER bound on C-CAP error, and the not-on-building')
print('figure is a LOWER bound on real miss.')

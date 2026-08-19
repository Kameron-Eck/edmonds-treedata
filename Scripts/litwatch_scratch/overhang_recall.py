"""Q116: is canopy OVER IMPERVIOUS the model's dominant failure mode?

Split C-CAP canopy pixels by what lies beneath - building/impervious vs pervious ground -
and compute the model's recall on each. If overhang is the weakness, recall over
impervious should be markedly worse.
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
CANOPY = [9, 10, 11, 13, 16]
DECIM = 4
RUNS = [('2016', 'edmonds_canopy_prob_2016.tif', 0.509),
        ('2013', 'edmonds_canopy_prob_2013_xsensor_rgb.tif', 0.5209),
        ('2017', 'edmonds_canopy_prob_2017_xsensor_train.tif', 0.4759)]
MASKS = Path(r'G:\My Drive\treedata\phase4\masks')

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
g = gpd.read_file(CITY).to_crs(crs)
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
inside = ~geometry_mask([geom], out_shape=cc.shape, transform=tr, invert=False)

b = gpd.read_file(BLDG).to_crs(crs)
b = b[b.geometry.notna() & b.geometry.is_valid]
bmask = rasterize(((geo, 1) for geo in b.geometry), out_shape=cc.shape,
                  transform=tr, fill=0, dtype='uint8').astype(bool)

imp = None
try:
    iv, i_nd = warp(IMP)
    imp = iv > 0
    if i_nd is not None:
        imp &= (iv != i_nd)
    print(f'impervious raster loaded: {int((imp & inside).sum()):,} cells '
          f'({100*(imp & inside).sum()/max(inside.sum(),1):.1f}% of city)')
except Exception as e:
    print(f'impervious raster unavailable ({e}); using buildings + C-CAP developed classes')

# "under impervious" = building footprint OR impervious raster OR C-CAP high-intensity developed
under_imp = bmask.copy()
if imp is not None:
    under_imp |= imp
print(f'buildings alone: {int((bmask & inside).sum()):,} cells '
      f'({100*(bmask & inside).sum()/max(inside.sum(),1):.1f}% of city)')
print(f'combined impervious mask: {int((under_imp & inside).sum()):,} cells '
      f'({100*(under_imp & inside).sum()/max(inside.sum(),1):.1f}% of city)')
print()

hgt = (dn.astype(np.float32) - 1.0) * 0.2
hgt[dn == 0] = np.nan

print(f"{'year':<7}{'recall OVER IMPERVIOUS':>24}{'recall over pervious':>22}{'gap':>9}")
for yr, fn, th in RUNS:
    pp = MASKS / fn
    if not pp.exists():
        print(f'{yr:<7} missing {fn}')
        continue
    pr, pr_nd = warp(pp)
    valid = inside & (cc != 0) & (pr != 255)
    if pr_nd is not None:
        valid &= (pr != pr_nd)
    can = valid & np.isin(cc, CANOPY)
    call = valid & (pr >= th * 254.0)
    a = can & under_imp
    p_ = can & ~under_imp
    ra = int((a & call).sum()) / max(int(a.sum()), 1)
    rp = int((p_ & call).sum()) / max(int(p_.sum()), 1)
    print(f'{yr:<7}{ra:>23.4f} {rp:>21.4f}{ra-rp:>+9.4f}')
    if yr == '2016':
        print(f'        (canopy over impervious: {int(a.sum()):,} cells = '
              f'{100*a.sum()/max(can.sum(),1):.1f}% of all C-CAP canopy)')
print()
print('READ: a large negative gap means the model is markedly worse at canopy')
print('overhanging buildings and pavement - the hard RGB case, and the failure mode')
print('iterations 62-65 pointed at.')

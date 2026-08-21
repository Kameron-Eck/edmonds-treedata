"""Is Phase 2's 'unmeasurable band' actually unmeasurable?

Phase 2 (ref_agreement_2016) splits the model's C-CAP misses into
  35.4% BOTH refs agree it is canopy  -> called REAL MISS
  64.6% refs DISAGREE                 -> called UNMEASURABLE
The disagreeing pixels are C-CAP-canopy that the NDVI reference rejects.

Iteration 62 showed C-CAP is conservative and tall-skewed, so those pixels may be
genuine tall vegetation that the NDVI reference misses for being insufficiently GREEN.
If independent lidar says they are tall, they are trees - and 'unmeasurable' is the
wrong label. Uses the 3DEP CHM, independent of both references.
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
PROB = Path(r'G:\My Drive\treedata\phase4\masks\edmonds_canopy_prob_2016.tif')
THRESH = 0.509
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
pr, pr_nodata = warp(PROB)

g = gpd.read_file(CITY).to_crs(crs)
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
inside = ~geometry_mask([geom], out_shape=cc.shape, transform=tr, invert=False)

hgt = (dn.astype(np.float32) - 1.0) * 0.2
hgt[dn == 0] = np.nan

valid = inside & (cc != 0) & np.isfinite(hgt)
if nd_nodata is not None:
    valid &= (nd != nd_nodata)
if pr_nodata is not None:
    valid &= (pr != pr_nodata)
valid &= (pr != 255)

ccap_can = valid & np.isin(cc, CANOPY)
ndvi_can = valid & (nd == 2)
called = valid & (pr >= THRESH * 254.0)

miss = ccap_can & ~called                     # model missed what C-CAP calls canopy
agree_miss = miss & ndvi_can                  # Phase 2 'REAL MISS'
disag_miss = miss & ~ndvi_can                 # Phase 2 'UNMEASURABLE'

t = max(int(miss.sum()), 1)
print(f'valid cells {int(valid.sum()):,} | C-CAP canopy {int(ccap_can.sum()):,} | model misses {int(miss.sum()):,}')
print()
print(f'  Phase 2 REAL MISS   (both refs agree canopy) {int(agree_miss.sum()):>10,}  {100*agree_miss.sum()/t:5.1f}%')
print(f'  Phase 2 UNMEASURABLE (refs disagree)         {int(disag_miss.sum()):>10,}  {100*disag_miss.sum()/t:5.1f}%')
print()
BANDS = [(0, 2), (2, 3), (3, 5), (5, 10), (10, 20), (20, 100)]
print('LIDAR HEIGHT OF THE "UNMEASURABLE" MISSES  (independent of BOTH references)')
print(f"{'height':<12}{'cells':>12}{'%':>8}")
d = max(int(disag_miss.sum()), 1)
for lo, hi in BANDS:
    m = disag_miss & (hgt >= lo) & (hgt < hi)
    k = int(m.sum())
    lab = f'{lo}-{hi} m' if hi < 100 else f'{lo}+ m'
    print(f'{lab:<12}{k:>12,}{100*k/d:>7.2f}%')
tall = int((disag_miss & (hgt >= 2)).sum())
print()
print(f'  TALL (>= 2 m by lidar): {tall:,} = {100*tall/d:.2f}% of the "unmeasurable" band')
print(f'  -> reclassifying those as REAL MISS moves the split to:')
real = int(agree_miss.sum()) + tall
print(f'     REAL MISS {real:,} = {100*real/t:.1f}%   truly ambiguous {t-real:,} = {100*(t-real)/t:.1f}%')
print()
rec_old = int(called.sum() & 0) # placeholder
tp = int((ccap_can & called).sum())
print(f'  recall as reported                 {tp/max(int(ccap_can.sum()),1):.4f}')
print('  (recall does not change - what changes is how much of the SHORTFALL is')
print('   excusable as reference disagreement rather than genuine under-detection)')

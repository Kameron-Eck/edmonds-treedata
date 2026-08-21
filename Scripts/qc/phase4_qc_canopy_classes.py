"""Which value is TREE and which is SHRUB in the NOAA hi-res canopy product?

Kam: "1 and 2 mean shrub or tree, cant recall".

Settle it with the CHM instead of guessing: shrub must sit markedly lower
than tree. This also produces exactly what U1/D1 needs - the HEIGHT
DISTRIBUTION of what a purpose-built product calls shrub versus tree, which
is the empirical basis for choosing a minimum-height cut.
"""
import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from pathlib import Path

NOAA = Path(r"C:\Users\Kameron\Documents\ArcGIS\NOAA")
CANOPY = NOAA / "Tree Canopy" / "wa_2021_ccap_v2_hires_canopy.tif"
CHM = Path(r"D:\edmonds-pipeline\Imagery\lidar_snoh_chm.tif")
REF = Path(r"G:\My Drive\treedata\phase3\edmonds_canopy_mask_2020.tif")
GRID = "EPSG:26910"
CELL = 2.0
DN_PER_M = 1.0 / 0.2

with rasterio.open(REF) as s:
    w, s_, e, n = transform_bounds(s.crs, GRID, *s.bounds, densify_pts=21)
W, H = int((e - w) // CELL), int((n - s_) // CELL)
T = from_origin(w, n, CELL, CELL)
print(f"grid {W}x{H} @ {CELL} m  ({GRID})")


def read(p, **kw):
    with rasterio.open(p) as src:
        with WarpedVRT(src, crs=GRID, transform=T, width=W, height=H,
                       resampling=Resampling.nearest, **kw) as v:
            return v.read(1)


cls = read(CANOPY)
dn = read(CHM, src_nodata=0, nodata=0)
hgt = (dn.astype(np.float32) - 1.0) / DN_PER_M
hgt[dn == 0] = np.nan

print(f"\n{'class':<8} {'cells':>12} {'% of grid':>10} {'CHM n':>12} "
      f"{'p10':>7} {'p50':>7} {'p90':>7} {'mean':>7} {'>=3m':>7}")
for v in (0, 1, 2):
    m = cls == v
    h = hgt[m]
    h = h[np.isfinite(h)]
    if h.size == 0:
        print(f"{v:<8} {int(m.sum()):>12,} {100*m.mean():>9.2f}%  (no CHM)")
        continue
    print(f"{v:<8} {int(m.sum()):>12,} {100*m.mean():>9.2f}% {h.size:>12,} "
          f"{np.percentile(h,10):>7.2f} {np.percentile(h,50):>7.2f} "
          f"{np.percentile(h,90):>7.2f} {h.mean():>7.2f} "
          f"{100*(h>=3).mean():>6.1f}%")

h1 = hgt[cls == 1]; h1 = h1[np.isfinite(h1)]
h2 = hgt[cls == 2]; h2 = h2[np.isfinite(h2)]
if h1.size and h2.size:
    print(f"\nmedian height: class1 {np.median(h1):.2f} m  vs  class2 {np.median(h2):.2f} m")
    if np.median(h1) > np.median(h2):
        print("=> CLASS 1 = TREE, CLASS 2 = SHRUB (1 is taller)")
    else:
        print("=> CLASS 2 = TREE, CLASS 1 = SHRUB (2 is taller)")

# What U1 actually needs: how much of each class clears a candidate cut?
print(f"\n{'cut':<8} {'% of class1 kept':>18} {'% of class2 kept':>18}")
for cut in (2.0, 3.0, 5.0):
    a = 100 * (h1 >= cut).mean() if h1.size else float('nan')
    b = 100 * (h2 >= cut).mean() if h2.size else float('nan')
    print(f">={cut:<5.1f}m {a:>17.1f}% {b:>17.1f}%")
print("\nA height cut is a proxy for the tree/shrub call. If a cut keeps most")
print("of the tree class and drops most of the shrub class, it reproduces the")
print("product's own distinction - which is what D1/D2 are trying to codify.")

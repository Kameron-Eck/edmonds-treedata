"""Q122: is the over-impervious recall gap SHADOW or CONTRAST?

Liu 2023 (RS 15:519) reports U-Net specifically suffers high omission from canopy SHADOW.
Our assumed mechanism was low contrast (dark foliage on dark roof). These make OPPOSITE
predictions about geometry:

  SHADOW   -> misses are DIRECTIONAL. Northern hemisphere, sun to the south, so building
              shadow falls to the NORTH. Miss rate should peak on the north side.
  CONTRAST -> misses are ISOTROPIC. A dark roof is equally dark on all sides.

For every C-CAP canopy pixel near a building, take the bearing from the nearest building
pixel and compute recall per compass sector. A north-side deficit is shadow; a flat profile
is contrast.
"""
import numpy as np, rasterio, geopandas as gpd
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.features import geometry_mask, rasterize
from scipy import ndimage
from pathlib import Path

CITY = Path(r'G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp')
BLDG = Path(r'G:\My Drive\treedata\building_footprints\data.json')
CCAP = Path(r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif')
M    = Path(r'G:\My Drive\treedata\phase4\masks')
CANOPY, DECIM, TH = [9, 10, 11, 13, 16], 4, 0.509

with rasterio.open(CCAP) as c:
    H, W = c.height // DECIM, c.width // DECIM
    tr, crs = c.transform * Affine.scale(DECIM), c.crs
    cc = c.read(1, out_shape=(H, W), resampling=Resampling.nearest)
print(f'CRS {crs}   rotation terms b={tr.b:.6g} d={tr.d:.6g}  (must be 0 for north-up)')
assert abs(tr.b) < 1e-9 and abs(tr.d) < 1e-9, 'raster is rotated - azimuths would be wrong'
cell = abs(tr.a)
print(f'cell size {cell:.3f} CRS units')

def warp(p):
    with rasterio.open(p) as r:
        with WarpedVRT(r, crs=crs, transform=tr, width=W, height=H,
                       resampling=Resampling.nearest) as v:
            return v.read(1), r.nodata

pr, nd = warp(M / 'edmonds_canopy_prob_2016.tif')
g = gpd.read_file(CITY).to_crs(crs)
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
inside = ~geometry_mask([geom], out_shape=cc.shape, transform=tr, invert=False)
b = gpd.read_file(BLDG).to_crs(crs)
b = b[b.geometry.notna() & b.geometry.is_valid]
bm = rasterize(((x,1) for x in b.geometry), out_shape=cc.shape, transform=tr,
               fill=0, dtype='uint8').astype(bool)

ok = inside & (cc != 0) & (pr != 255)
if nd is not None: ok &= (pr != nd)
can  = ok & np.isin(cc, CANOPY) & ~bm     # canopy NEXT TO buildings, not on them
call = pr >= TH * 254.0

# distance to nearest building pixel + which pixel that is
dist, idx = ndimage.distance_transform_edt(~bm, return_indices=True)
rr, ccol = np.indices(cc.shape)
dy = (rr - idx[0]).astype(np.float32)     # +down  = SOUTH
dx = (ccol - idx[1]).astype(np.float32)   # +right = EAST
az = (np.degrees(np.arctan2(dx, -dy)) + 360.0) % 360.0   # 0=N, 90=E

for maxd_m in (10.0, 20.0):
    maxd = maxd_m / cell if cell > 0.9 else maxd_m * 3.28084 / cell  # ft CRS guard
    near = can & (dist > 0) & (dist <= maxd)
    n = int(near.sum())
    print(f'\n--- canopy within {maxd_m:.0f} m of a building  (n={n:,}) ---')
    if n < 5000:
        print('  too few - skipping'); continue
    print(f"{'sector':<10}{'recall':>9}{'n':>10}")
    secs = [('N',337.5,22.5),('NE',22.5,67.5),('E',67.5,112.5),('SE',112.5,157.5),
            ('S',157.5,202.5),('SW',202.5,247.5),('W',247.5,292.5),('NW',292.5,337.5)]
    vals = {}
    for nm, a0, a1 in secs:
        m = near & ((az >= a0) & (az < a1) if a0 < a1 else ((az >= a0) | (az < a1)))
        k = int(m.sum())
        v = int((m & call).sum()) / max(k, 1)
        vals[nm] = (v, k)
        print(f'{nm:<10}{v:>9.4f}{k:>10,}')
    north = np.mean([vals[s][0] for s in ('NW','N','NE')])
    south = np.mean([vals[s][0] for s in ('SE','S','SW')])
    print(f'\n  NORTH side (NW,N,NE) mean recall : {north:.4f}')
    print(f'  SOUTH side (SE,S,SW) mean recall : {south:.4f}')
    print(f'  NORTH minus SOUTH                : {north-south:+.4f}')
    sp = max(v[0] for v in vals.values()) - min(v[0] for v in vals.values())
    print(f'  max-min across all 8 sectors     : {sp:.4f}')

print('\nREAD: a clearly NEGATIVE north-minus-south (north side worse) supports SHADOW.')
print('A near-zero difference and a small 8-sector spread supports CONTRAST, and means')
print('the fix must be structural (height/NIR) rather than radiometric.')

"""Q138: measure EFFECTIVE resolution in ground metres, not as a spectral heuristic.

Q137 showed nominal gsd_cm misdescribes at least 1998, 2005 and 2013, but its HF-share metric
only supported an ORDERING. This gives a number in the same units the config claims to use.

METHOD - automatic edge-response (the slanted-edge idea, without hand-picked targets):
  find strong gradients, take intensity profiles along the gradient direction, align and
  average them into an Edge Spread Function, then measure the 10-90% rise distance and
  convert to ground centimetres using each year's TRUE GSD.

A properly sampled image rises in about 1-2 pixels. A rise of 4 pixels on a 10 cm grid means
the real detail is nearer 40 cm however fine the grid is.

Same sites for every year, so scene content is controlled rather than assumed away.
"""
import numpy as np, rasterio, geopandas as gpd
from rasterio.warp import transform as warp_xy
from rasterio.windows import Window

CITY = r'G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp'
g = gpd.read_file(CITY).to_crs('EPSG:4326')
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
minx, miny, maxx, maxy = geom.bounds
SITES = [(minx + (maxx-minx)*fx, miny + (maxy-miny)*fy)
         for fx in (0.3, 0.45, 0.6, 0.75) for fy in (0.25, 0.4, 0.55)]
YEARS = [('1998', '1998_king_rgb.tif', 40.1), ('2000', '2000_king_rgb.tif', 40.1),
         ('2002', '2002_king_rgb.tif', 40.1), ('2005', '2005_king_rgb.tif', 20.1),
         ('2007', '2007_king_rgb.tif', 20.1), ('2009', '2009_king_rgb.tif', 20.1),
         ('2013', '2013_king_rgb.tif', 10.0), ('2015', '2015_king_rgb.tif', 10.0),
         ('2019', '2019_king_rgb.tif', 10.0), ('2021', '2021_king_rgb.tif', 10.0),
         ('2023', '2023_king_rgb.tif', 10.0)]
PX, HALF, SUB = 512, 6, 4     # profile reaches +/-6 px, sampled at 1/4 px

def esf(a):
    """Average Edge Spread Function from the strongest edges in the window."""
    gy, gx = np.gradient(a)
    mag = np.hypot(gx, gy)
    thr = np.percentile(mag, 99.0)
    ys, xs = np.nonzero(mag >= thr)
    keep = (ys > HALF+1) & (ys < a.shape[0]-HALF-1) & (xs > HALF+1) & (xs < a.shape[1]-HALF-1)
    ys, xs = ys[keep], xs[keep]
    if ys.size < 40: return None
    if ys.size > 900:
        sel = np.linspace(0, ys.size-1, 900).astype(int); ys, xs = ys[sel], xs[sel]
    off = np.arange(-HALF, HALF + 1/SUB, 1/SUB)
    prof = []
    for y, x in zip(ys, xs):
        d = np.hypot(gx[y, x], gy[y, x])
        if d < 1e-6: continue
        ux, uy = gx[y, x]/d, gy[y, x]/d          # unit vector ACROSS the edge
        yy = np.clip(y + off*uy, 0, a.shape[0]-1)
        xx = np.clip(x + off*ux, 0, a.shape[1]-1)
        v = a[np.round(yy).astype(int), np.round(xx).astype(int)].astype(np.float32)
        lo, hi = v[:3].mean(), v[-3:].mean()
        if hi - lo < 8: continue                  # need a real step, not noise
        prof.append((v - lo) / (hi - lo))
    if len(prof) < 30: return None
    return off, np.median(np.array(prof), axis=0)

def rise_px(off, e):
    """10-90% rise distance in PIXELS, read off the averaged edge profile."""
    e = (e - e.min()) / max(e.max() - e.min(), 1e-9)
    if not (e[0] < 0.3 and e[-1] > 0.7): return np.nan
    try:
        x10 = np.interp(0.10, e, off); x90 = np.interp(0.90, e, off)
    except Exception:
        return np.nan
    return float(x90 - x10)

print(f'{len(SITES)} sites, {PX}px windows, automatic edge response\n')
print(f"{'year':<7}{'nominal cm':>12}{'n sites':>9}{'rise px':>9}{'EFFECTIVE cm':>14}{'ratio':>8}")
for nm, fn, gsd in YEARS:
    rs = []
    try:
        with rasterio.open(rf'D:\edmonds-pipeline\Imagery\{fn}') as r:
            for lon, lat in SITES:
                xs_, ys_ = warp_xy('EPSG:4326', r.crs, [lon], [lat])
                row, col = r.index(xs_[0], ys_[0])
                if not (0 <= row < r.height and 0 <= col < r.width): continue
                r0 = max(0, min(r.height-PX, row-PX//2)); c0 = max(0, min(r.width-PX, col-PX//2))
                a = r.read(1, window=Window(c0, r0, PX, PX)).astype(np.float32)
                if a.shape != (PX, PX) or a.std() < 3: continue
                out = esf(a)
                if out is None: continue
                v = rise_px(*out)
                if np.isfinite(v) and 0 < v < 2*HALF: rs.append(v)
    except Exception as e:
        print(f'{nm:<7} ERROR {str(e)[:45]}'); continue
    if len(rs) < 3:
        print(f'{nm:<7}{gsd:>12.1f}{len(rs):>9}   too few usable edges'); continue
    m = float(np.median(rs))
    print(f'{nm:<7}{gsd:>12.1f}{len(rs):>9}{m:>9.2f}{m*gsd:>14.1f}{m*gsd/gsd:>8.2f}')

print('\nREAD: EFFECTIVE cm = 10-90% edge rise distance x true GSD. It is the ground distance over')
print('which the image actually transitions across a sharp boundary, so it is comparable ACROSS')
print('years in real units - unlike gsd_cm, which only describes the sampling grid.')

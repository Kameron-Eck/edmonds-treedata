"""Q137 (clean): is each acquisition SHARP FOR ITS OWN PIXEL GRID?

The first attempt block-averaged different years by different factors (1, 2, 4) to reach a
common 40 cm, but the downsample factor changes the spectrum shape on its own, so 2005 (f=2)
and 2013 (f=4) were not comparable. Confound removed here: NO RESAMPLING. Every year is read
at native resolution and scored against ITS OWN Nyquist.

That answers the question that actually matters. A well-formed image has real detail out to
its own sampling limit. If 2000 is soft RELATIVE TO ITS OWN 40 cm grid, then its effective
resolution is worse than nominal - the grid is finer than the optics - and calling it a
"40 cm image" overstates it.
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

# true ground GSD in cm, per the 2026-08-18 config correction
YEARS = [('1998 (1-band)', '1998_king_rgb.tif', 40.1), ('2000', '2000_king_rgb.tif', 40.1),
         ('2002', '2002_king_rgb.tif', 40.1), ('2005', '2005_king_rgb.tif', 20.1),
         ('2007', '2007_king_rgb.tif', 20.1), ('2009', '2009_king_rgb.tif', 20.1),
         ('2013', '2013_king_rgb.tif', 10.0), ('2015', '2015_king_rgb.tif', 10.0),
         ('2019', '2019_king_rgb.tif', 10.0), ('2021', '2021_king_rgb.tif', 10.0),
         ('2023', '2023_king_rgb.tif', 10.0)]
PX = 256

def hf_share(a):
    a = a - a.mean()
    if a.std() < 1e-6: return np.nan
    a = a / a.std()
    w = np.hanning(a.shape[0])[:, None] * np.hanning(a.shape[1])[None, :]
    P = np.abs(np.fft.fftshift(np.fft.fft2(a * w))) ** 2
    cy, cx = np.array(P.shape) // 2
    yy, xx = np.ogrid[:P.shape[0], :P.shape[1]]
    r = np.sqrt(((yy - cy) / cy) ** 2 + ((xx - cx) / cx) ** 2)
    tot = P[r <= 1.0].sum()
    return float(P[(r > 0.5) & (r <= 1.0)].sum() / max(tot, 1e-12))

print(f'{len(SITES)} sites, {PX}px native windows, NO resampling\n')
print(f"{'year':<16}{'GSD cm':>8}{'n':>4}{'HF share':>11}{'sd':>9}{'window m':>10}")
for nm, fn, gsd in YEARS:
    vals = []
    try:
        with rasterio.open(rf'D:\edmonds-pipeline\Imagery\{fn}') as r:
            for lon, lat in SITES:
                xs, ys = warp_xy('EPSG:4326', r.crs, [lon], [lat])
                row, col = r.index(xs[0], ys[0])
                if not (0 <= row < r.height and 0 <= col < r.width): continue
                r0 = max(0, min(r.height - PX, row - PX//2))
                c0 = max(0, min(r.width - PX, col - PX//2))
                a = r.read(1, window=Window(c0, r0, PX, PX)).astype(np.float32)
                if a.shape != (PX, PX) or a.std() < 1e-6: continue
                v = hf_share(a)
                if np.isfinite(v): vals.append(v)
    except Exception as e:
        print(f'{nm:<16} ERROR {str(e)[:40]}'); continue
    if not vals: print(f'{nm:<16}{gsd:>8.1f}   no usable windows'); continue
    print(f'{nm:<16}{gsd:>8.1f}{len(vals):>4}{np.mean(vals):>11.4f}{np.std(vals):>9.4f}'
          f'{PX*gsd/100:>10.1f}')

print('\nREAD: HF share is power above HALF-NYQUIST of each image\'s OWN grid. A sharp, properly')
print('sampled image carries real detail there. A LOW value means the pixel grid is finer than')
print('the actual optical detail - the image is soft for its own stated resolution, and its')
print('nominal GSD overstates what the model can actually see.')

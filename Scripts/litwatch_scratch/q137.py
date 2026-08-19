"""Q137: is 2000's EFFECTIVE resolution as good as its nominal 40 cm?

it.71 warned that a grid spacing is not an optical resolution. it.73 and it.77 both found the
pre-2005 years are the only ones that underperform, and both attributed it to resolution. But
"40 cm" for 2000 is a CRS-derived number, and 2000 is a scanned/older product - its real
detail may be far below its pixel grid.

THE CONTROLLED TEST: take 2013 at ~10 cm and DEGRADE IT to 40 cm by block-averaging. That is a
synthetic 40 cm image of the SAME GROUND with known, ideal optics. Compare its high-frequency
content against 2000's NATIVE 40 cm.

  2000 similar to degraded-2013  -> 2000 really is a 40 cm image; resolution alone explains it
  2000 much SOFTER               -> its effective resolution is worse than nominal, and the
                                    pre-2005 deficit is partly image QUALITY, not just GSD

Metric is scale-free: the share of spectral power above half-Nyquist, normalised by total
power, so it does not depend on contrast or the colour cast measured in it.72.
"""
import numpy as np, rasterio, geopandas as gpd
from rasterio.warp import transform as warp_xy
from rasterio.windows import Window

CITY = r'G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp'
g = gpd.read_file(CITY).to_crs('EPSG:4326')
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
minx, miny, maxx, maxy = geom.bounds
SITES = [(minx + (maxx-minx)*fx, miny + (maxy-miny)*fy)
         for fx in (0.35, 0.5, 0.65) for fy in (0.3, 0.45)]

def hf_share(a):
    """Share of 2D spectral power above half-Nyquist. Contrast- and offset-invariant."""
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

def grab(path, lon, lat, px):
    with rasterio.open(path) as r:
        xs, ys = warp_xy('EPSG:4326', r.crs, [lon], [lat])
        row, col = r.index(xs[0], ys[0])
        r0 = max(0, min(r.height - px, row - px // 2))
        c0 = max(0, min(r.width - px, col - px // 2))
        a = r.read(1, window=Window(c0, r0, px, px)).astype(np.float32)
    return a if a.size == px * px else None

def block_avg(a, f):
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    return a[:h, :w].reshape(h // f, f, w // f, f).mean(axis=(1, 3))

N40 = 256                      # 256 px at 40 cm ~ 102 m of ground
rows = {}
for lon, lat in SITES:
    # native 40 cm sources
    for nm, path, f in (('2000 native 40cm', '2000_king_rgb.tif', 1),
                        ('2002 native 40cm', '2002_king_rgb.tif', 1),
                        ('2005 native 20cm->40', '2005_king_rgb.tif', 2),
                        ('2013 native 10cm->40', '2013_king_rgb.tif', 4),
                        ('2019 native 10cm->40', '2019_king_rgb.tif', 4)):
        a = grab(rf'D:\edmonds-pipeline\Imagery\{path}', lon, lat, N40 * f)
        if a is None or a.std() < 1e-6: continue
        b = block_avg(a, f) if f > 1 else a
        if b.shape[0] < N40 or b.std() < 1e-6: continue
        rows.setdefault(nm, []).append(hf_share(b[:N40, :N40]))
    # and 2013 at its OWN native scale, as the ceiling
    a = grab(r'D:\edmonds-pipeline\Imagery\2013_king_rgb.tif', lon, lat, N40)
    if a is not None and a.std() > 1e-6:
        rows.setdefault('2013 at native 10cm', []).append(hf_share(a))

print(f'{len(SITES)} sites, {N40}px windows at a common 40 cm scale\n')
print(f"{'source':<24}{'n':>3}{'HF share':>10}{'sd':>8}")
for nm in ('2013 at native 10cm', '2013 native 10cm->40', '2019 native 10cm->40',
           '2005 native 20cm->40', '2002 native 40cm', '2000 native 40cm'):
    v = [x for x in rows.get(nm, []) if np.isfinite(x)]
    if not v: print(f'{nm:<24}  no data'); continue
    print(f'{nm:<24}{len(v):>3}{np.mean(v):>10.4f}{np.std(v):>8.4f}')

print('\nREAD: all rows except the first are resampled to the SAME 40 cm scale, so they are')
print('directly comparable. If 2000 sits well BELOW the degraded 2013/2019 rows, its effective')
print('resolution is worse than its nominal 40 cm and the pre-2005 deficit is partly image')
print('QUALITY - which no amount of retraining at 40 cm would recover.')

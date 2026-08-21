"""Is the GRVI colour cast a per-year property? If so, every greenness diagnostic in this
project is confounded across years, and the leaf-off / rendering signature built on GRVI in an
earlier iteration is not comparable between acquisitions without per-year normalisation.

Windowed reads this time: the imagery is TILED (512x512) so a window is cheap, whereas the
decimated whole-raster read used before was silently reading entire multi-GB files because
NOTHING in this project has overviews.

Window is centred on the same ground point in every year, so the years see the same place.
"""
import numpy as np, rasterio, glob, os, geopandas as gpd
from rasterio.warp import transform as warp_xy
from rasterio.windows import Window

CITY = r'G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp'
SIZE = 2400

g = gpd.read_file(CITY)
cen = g.to_crs('EPSG:4326').union_all().centroid if hasattr(g, 'union_all') else \
      g.to_crs('EPSG:4326').unary_union.centroid
lon, lat = cen.x, cen.y
print(f'window {SIZE}x{SIZE} px centred on {lat:.5f}, {lon:.5f} in every raster\n')

files = sorted(glob.glob(r'D:\edmonds-pipeline\Imagery\*_king_rgb.tif')) + \
        sorted(glob.glob(r'D:\edmonds-pipeline\Imagery\*_coe_rgb.tif')) + \
        sorted(glob.glob(r'D:\edmonds-pipeline\Imagery\*_snoh_rgbi.tif')) + \
        sorted(glob.glob(r'D:\edmonds-pipeline\Imagery\*naip*.tif'))

print(f"{'file':<24}{'nb':>3}{'meanR':>8}{'meanG':>8}{'meanB':>8}"
      f"{'GRVI mu':>9}{'GRVI sd':>9}{'frac>.02':>10}{'satur%':>8}")
for p in files:
    try:
        with rasterio.open(p) as r:
            xs, ys = warp_xy('EPSG:4326', r.crs, [lon], [lat])
            row, col = r.index(xs[0], ys[0])
            r0 = max(0, min(r.height - SIZE, row - SIZE // 2))
            c0 = max(0, min(r.width - SIZE, col - SIZE // 2))
            w = Window(c0, r0, min(SIZE, r.width), min(SIZE, r.height))
            n = min(r.count, 3)
            a = r.read(list(range(1, n + 1)), window=w).astype(np.float32)
            m = np.any(a > 0, axis=0)
            nm = os.path.basename(p)
            if m.sum() < 1000:
                print(f'{nm[:23]:<24}{r.count:>3}  window empty/outside'); continue
            if n < 3:
                v = a[0][m]
                sat = float((v >= 254).mean()) * 100
                print(f'{nm[:23]:<24}{r.count:>3}{v.mean():>8.1f}{"-":>8}{"-":>8}'
                      f'{"SINGLE BAND":>9}{"":>9}{"":>10}{sat:>8.2f}')
                continue
            R, G, B = a[0][m], a[1][m], a[2][m]
            gr = (G - R) / np.maximum(G + R, 1e-6)
            sat = float((np.maximum(np.maximum(R, G), B) >= 254).mean()) * 100
            print(f'{nm[:23]:<24}{r.count:>3}{R.mean():>8.1f}{G.mean():>8.1f}{B.mean():>8.1f}'
                  f'{gr.mean():>+9.4f}{gr.std():>9.4f}{float((gr > 0.02).mean()):>10.4f}{sat:>8.2f}')
    except Exception as e:
        print(f'{os.path.basename(p)[:23]:<24} ERROR {str(e)[:45]}')
print('\nREAD: frac>.02 is the share of pixels a naive GRVI vegetation test calls green, over the')
print('SAME ground in every year. Values near 1.0 mean a global colour cast, not vegetation - the')
print('index is not discriminating there. Wide variation across years means GRVI is not')
print('comparable between them without per-year normalisation.')

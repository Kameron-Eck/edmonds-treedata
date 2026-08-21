"""Is the 1936 frame actually imaging Edmonds, or is the sampled window blank border?
mean 253 over a 2400 px window is suspicious. Probe several windows across the city.
"""
import numpy as np, rasterio, geopandas as gpd
from rasterio.warp import transform as warp_xy
from rasterio.windows import Window

CITY = r'G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp'
g = gpd.read_file(CITY).to_crs('EPSG:4326')
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
minx, miny, maxx, maxy = geom.bounds
pts = [(minx + (maxx-minx)*fx, miny + (maxy-miny)*fy)
       for fx in (0.25, 0.5, 0.75) for fy in (0.25, 0.5, 0.75)]
S = 1200
for name in ('1936_king_rgb.tif', '1998_king_rgb.tif', '2000_king_rgb.tif'):
    p = rf'D:\edmonds-pipeline\Imagery\{name}'
    with rasterio.open(p) as r:
        print(f'=== {name}  {r.width}x{r.height}  bounds ok ===')
        for lon, lat in pts:
            xs, ys = warp_xy('EPSG:4326', r.crs, [lon], [lat])
            row, col = r.index(xs[0], ys[0])
            if not (0 <= row < r.height and 0 <= col < r.width):
                print(f'   {lat:.4f},{lon:.4f}  OUTSIDE raster'); continue
            r0 = max(0, min(r.height - S, row - S//2)); c0 = max(0, min(r.width - S, col - S//2))
            a = r.read(1, window=Window(c0, r0, S, S)).astype(np.float32)
            print(f'   {lat:.4f},{lon:.4f}  mean {a.mean():7.1f}  std {a.std():6.2f}  '
                  f'min {a.min():5.0f}  max {a.max():5.0f}  '
                  f'frac==255 {float((a>=255).mean()):.3f}  frac==0 {float((a<=0).mean()):.3f}')
    print()

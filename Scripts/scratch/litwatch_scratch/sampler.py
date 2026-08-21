"""Shared point sampler. Built after discovering the real cost driver: NO raster in this
project has overviews (ovr=[]), so every out_shape/decimated read silently reads the WHOLE
file, and the prob rasters are row-striped (block=(1,18944)) rather than tiled.

Point sampling on a limited set of ROWS reads few blocks and is orders of magnitude cheaper,
while being statistically cleaner than a decimated grid.
"""
import numpy as np, rasterio, geopandas as gpd
from rasterio.warp import transform as warp_xy
from shapely.geometry import Point
from pathlib import Path

CITY = Path(r'G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp')
REF  = Path(r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif')

def build_points(n_rows=500, n_cols=700, seed=0):
    """Systematic grid restricted to the city polygon, in the REFERENCE raster's CRS."""
    with rasterio.open(REF) as r:
        crs, b = r.crs, r.bounds
    g = gpd.read_file(CITY).to_crs(crs)
    geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
    ys = np.linspace(b.bottom, b.top, n_rows + 2)[1:-1]
    xs = np.linspace(b.left, b.right, n_cols + 2)[1:-1]
    X, Y = np.meshgrid(xs, ys)
    X, Y = X.ravel(), Y.ravel()
    minx, miny, maxx, maxy = geom.bounds
    keep = (X >= minx) & (X <= maxx) & (Y >= miny) & (Y <= maxy)
    X, Y = X[keep], Y[keep]
    inside = np.fromiter((geom.contains(Point(x, y)) for x, y in zip(X, Y)), bool, X.size)
    return X[inside], Y[inside], crs

def sample(path, X, Y, src_crs):
    """Values at the points, plus the raster's nodata. Points are transformed per raster CRS."""
    with rasterio.open(path) as r:
        if r.crs != src_crs:
            xs, ys = warp_xy(src_crs, r.crs, list(X), list(Y))
        else:
            xs, ys = list(X), list(Y)
        v = np.array([s[0] for s in r.sample(zip(xs, ys), indexes=1)])
        return v, r.nodata

if __name__ == '__main__':
    X, Y, crs = build_points()
    print(f'{X.size:,} points inside the city, CRS {crs}')
    np.savez(r'C:\Users\Kameron\AppData\Local\Temp\claude\C--Users-Kameron'
             r'\c7464206-58af-4d13-a789-93a4082439c5\scratchpad\pts.npz',
             X=X, Y=Y, crs=str(crs))
    print('saved pts.npz')

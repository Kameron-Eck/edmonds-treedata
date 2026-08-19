import numpy as np, rasterio
from rasterio.enums import Resampling
for y in ('1936','1998','2000','2013'):
    p = rf'D:\edmonds-pipeline\Imagery\{y}_king_rgb.tif'
    try:
        with rasterio.open(p) as r:
            print(f'=== {y} ===  {r.count} bands  {r.dtypes[0]}  {r.crs}  {r.width}x{r.height}  nodata={r.nodata}')
            n = min(r.count, 3)
            a = r.read(list(range(1, n+1)),
                       out_shape=(n, min(r.height, 900), min(r.width, 900)),
                       resampling=Resampling.average).astype(np.float32)
            m = np.ones(a.shape[1:], bool)
            if r.nodata is not None:
                m = ~np.all(a == r.nodata, axis=0)
            m &= np.any(a > 0, axis=0)
            for i in range(n):
                v = a[i][m]
                print(f'   band{i+1}  mean {v.mean():8.2f}  std {v.std():7.2f}  '
                      f'p1 {np.percentile(v,1):6.1f}  p99 {np.percentile(v,99):6.1f}')
            if n >= 3:
                rb, gb, bb = a[0][m], a[1][m], a[2][m]
                d_rg = float(np.abs(rb-gb).mean()); d_gb = float(np.abs(gb-bb).mean())
                print(f'   MEAN |R-G| = {d_rg:.3f}   MEAN |G-B| = {d_gb:.3f}')
                grvi = (gb-rb)/np.maximum(gb+rb, 1e-6)
                print(f'   GRVI mean {grvi.mean():+.4f}  std {grvi.std():.4f}  '
                      f'frac>0.02 {float((grvi>0.02).mean()):.4f}')
                if d_rg < 0.5 and d_gb < 0.5:
                    print('   *** PANCHROMATIC: bands are identical - NO COLOUR INFORMATION ***')
    except Exception as e:
        print(f'=== {y} === ERROR {e}')
    print()

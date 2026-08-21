"""Is the GRVI colour cast a per-year property? If so, every greenness diagnostic in this
project is confounded across years and any leaf-off / rendering signature built on GRVI
needs a per-year normalisation before it can be compared.

Also records BAND COUNT, because 1936/1998 turned out to be single-band despite _rgb names.
"""
import numpy as np, rasterio, glob, os, re
from rasterio.enums import Resampling

files = sorted(glob.glob(r'D:\edmonds-pipeline\Imagery\*_king_rgb.tif')) + \
        sorted(glob.glob(r'D:\edmonds-pipeline\Imagery\*coe*.tif'))
print(f"{'file':<26}{'nb':>3}{'W x H':>18}{'meanR':>8}{'meanG':>8}{'meanB':>8}"
      f"{'GRVI mu':>9}{'GRVI sd':>9}{'frac>.02':>10}{'p1':>5}{'p99':>5}")
for p in files:
    try:
        with rasterio.open(p) as r:
            n = min(r.count, 3)
            a = r.read(list(range(1, n+1)), out_shape=(n, 700, 700),
                       resampling=Resampling.average).astype(np.float32)
            m = np.any(a > 0, axis=0)
            nm = os.path.basename(p)
            if n < 3:
                v = a[0][m]
                print(f'{nm[:25]:<26}{r.count:>3}{f"{r.width}x{r.height}":>18}'
                      f'{v.mean():>8.1f}{"-":>8}{"-":>8}{"SINGLE BAND":>9}{"":>9}{"":>10}'
                      f'{np.percentile(v,1):>5.0f}{np.percentile(v,99):>5.0f}')
                continue
            R, G, B = a[0][m], a[1][m], a[2][m]
            gr = (G - R) / np.maximum(G + R, 1e-6)
            print(f'{nm[:25]:<26}{r.count:>3}{f"{r.width}x{r.height}":>18}'
                  f'{R.mean():>8.1f}{G.mean():>8.1f}{B.mean():>8.1f}'
                  f'{gr.mean():>+9.4f}{gr.std():>9.4f}{float((gr>0.02).mean()):>10.4f}'
                  f'{np.percentile(G,1):>5.0f}{np.percentile(G,99):>5.0f}')
    except Exception as e:
        print(f'{os.path.basename(p)[:25]:<26} ERROR {str(e)[:50]}')
print('\nREAD: frac>.02 is the share of ALL pixels a naive GRVI vegetation test would call green.')
print('Values near 1.0 mean the index is NOT DISCRIMINATING in that year - a global colour cast,')
print('not vegetation. Wide variation across years means GRVI is not comparable between them.')

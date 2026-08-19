"""Compare per-year recall/precision on the OLD clipped C-CAP footprint vs the new
CITY-clipped reference. Read-only: does not touch the project's QC CSVs."""
import numpy as np, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from pathlib import Path

IMG = Path(r'D:\edmonds-pipeline\Imagery')
MASKS = Path(r'G:\My Drive\treedata\phase4\masks')
CANOPY = [9, 10, 11, 13, 16]
DECIM = 32

YEARS = [
    ('2000', 'edmonds_canopy_prob_2000_xsensor_rgb.tif', 0.5133, 0.6303),
    ('2002', 'edmonds_canopy_prob_2002_xsensor_rgb.tif', 0.5700, 0.5069),
    ('2013', 'edmonds_canopy_prob_2013_xsensor_rgb.tif', 0.5209, 0.7094),
    ('2015', 'edmonds_canopy_prob_2015_xsensor_rgb.tif', 0.5760, 0.6222),
    ('2017', 'edmonds_canopy_prob_2017_xsensor_train.tif', 0.4759, 0.7784),
]


def score(prob_path, ref_path, thresh):
    thr = thresh * 254.0
    with rasterio.open(prob_path) as p:
        H, W = p.height // DECIM, p.width // DECIM
        dt = p.transform * Affine.scale(DECIM)
        crs = p.crs
        nod = 255 if p.nodata is None else p.nodata
        pr = p.read(1, out_shape=(H, W), resampling=Resampling.nearest)
    with rasterio.open(ref_path) as r:
        with WarpedVRT(r, crs=crs, transform=dt, width=W, height=H,
                       resampling=Resampling.nearest) as v:
            rc = v.read(1)
            rnd = r.nodata
    valid = (pr != nod) & (rc != 0)
    if rnd is not None:
        valid &= rc != rnd
    can = valid & np.isin(rc, CANOPY)
    call = valid & (pr >= thr)
    tp = int((can & call).sum()); fn = int((can & ~call).sum()); fp = int((~can & call & valid).sum())
    rec = tp / (tp + fn) if tp + fn else float('nan')
    pre = tp / (tp + fp) if tp + fp else float('nan')
    return rec, pre, int(valid.sum()), int(can.sum())


print('RE-SCORED ON THE CITY FOOTPRINT vs THE OLD CLIP')
print('ref A = ccap_2016_hires_lc.tif (old rectangle, 80% of city)')
print('ref B = ccap_2016_edmonds.tif  (city boundary, 100%)')
print()
print(f"{'year':<7}{'old rec':>9}{'CITY rec':>10}{'delta':>8}   {'old pre':>8}{'CITY pre':>10}{'delta':>8}   {'city ref canopy%':>17}")
old_ref = IMG / 'ccap_2016_hires_lc.tif'
new_ref = IMG / 'ccap_2016_edmonds.tif'
for y, f, th, published in YEARS:
    pp = MASKS / f
    if not pp.exists():
        print(f'{y:<7} MISSING {f}')
        continue
    ra, pa, na, ca = score(pp, old_ref, th)
    rb, pb, nb, cb = score(pp, new_ref, th)
    print(f'{y:<7}{ra:>9.4f}{rb:>10.4f}{rb-ra:>+8.4f}   {pa:>8.4f}{pb:>10.4f}{pb-pa:>+8.4f}   {100*cb/max(nb,1):>16.2f}%')
print()
print('  (published column check: 2013 should reproduce ~0.7094 on the old ref)')

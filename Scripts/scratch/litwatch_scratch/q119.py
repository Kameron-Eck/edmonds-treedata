"""Q119: does the NIR+CHM-corrected model close the OVER-IMPERVIOUS recall gap?

prob_2016 (baseline, RGB labels) vs prob_2016_corrected (labels corrected with NIR+CHM).
Same year, same imagery, same footprint -> a controlled test.

Confound to defuse: the corrected model may simply call MORE canopy everywhere, which
lifts over-impervious recall without fixing the mechanism. So report BOTH
  (a) each model at its deployed threshold 0.509
  (b) the corrected model RE-THRESHOLDED to match the baseline's OVERALL recall
If the gap narrows only in (a) and not (b), it bought recall, not understanding.
"""
import numpy as np, rasterio, geopandas as gpd
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.features import geometry_mask, rasterize
from pathlib import Path

CITY = Path(r'G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp')
BLDG = Path(r'G:\My Drive\treedata\building_footprints\data.json')
CCAP = Path(r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif')
CHM  = Path(r'D:\edmonds-pipeline\Imagery\lidar_snoh_chm.tif')
IMP  = Path(r'G:\My Drive\treedata\impervious\impervious_edmonds.tif')
M    = Path(r'G:\My Drive\treedata\phase4\masks')
CANOPY, DECIM, TH = [9, 10, 11, 13, 16], 4, 0.509
BANDS = [(0,2),(2,5),(5,10),(10,15),(15,20),(20,25),(25,30),(30,100)]

with rasterio.open(CCAP) as c:
    H, W = c.height // DECIM, c.width // DECIM
    tr, crs = c.transform * Affine.scale(DECIM), c.crs
    cc = c.read(1, out_shape=(H, W), resampling=Resampling.nearest)

def warp(p, **kw):
    with rasterio.open(p) as r:
        with WarpedVRT(r, crs=crs, transform=tr, width=W, height=H,
                       resampling=Resampling.nearest, **kw) as v:
            return v.read(1), r.nodata

dn, _ = warp(CHM, src_nodata=0, nodata=0)
iv, i_nd = warp(IMP)
pb, pb_nd = warp(M / 'edmonds_canopy_prob_2016.tif')
pc, pc_nd = warp(M / 'edmonds_canopy_prob_2016_corrected.tif')

g = gpd.read_file(CITY).to_crs(crs)
geom = g.union_all() if hasattr(g, 'union_all') else g.unary_union
inside = ~geometry_mask([geom], out_shape=cc.shape, transform=tr, invert=False)

b = gpd.read_file(BLDG).to_crs(crs)
b = b[b.geometry.notna() & b.geometry.is_valid]
bmask = rasterize(((x,1) for x in b.geometry), out_shape=cc.shape, transform=tr,
                  fill=0, dtype='uint8').astype(bool)
imp = (iv > 0)
if i_nd is not None: imp &= (iv != i_nd)
under = bmask | imp

hgt = (dn.astype(np.float32) - 1.0) * 0.2
hgt[dn == 0] = np.nan

# COMMON footprint only - footprint mismatch has burned this project before
ok = inside & (cc != 0) & (pb != 255) & (pc != 255)
if pb_nd is not None: ok &= (pb != pb_nd)
if pc_nd is not None: ok &= (pc != pc_nd)
can = ok & np.isin(cc, CANOPY)
noncan = ok & ~np.isin(cc, CANOPY)
print(f'common footprint: {int(ok.sum()):,} cells   C-CAP canopy in it: {int(can.sum()):,}')
print(f'canopy over impervious: {int((can & under).sum()):,} = '
      f'{100*(can & under).sum()/max(can.sum(),1):.1f}% of canopy\n')

ci, cp = can & under, can & ~under

def stats(pr, t):
    call = pr >= t * 254.0
    r  = int((can & call).sum()) / max(int(can.sum()), 1)
    ri = int((ci  & call).sum()) / max(int(ci.sum()),  1)
    rp = int((cp  & call).sum()) / max(int(cp.sum()),  1)
    fp = int((noncan & call).sum()) / max(int(noncan.sum()), 1)
    return r, ri, rp, ri - rp, fp

hdr = f"{'model':<26}{'thr':>7}{'recall':>9}{'over IMP':>10}{'over PERV':>11}{'GAP':>9}{'FPrate':>9}"
print('(a) AT THE DEPLOYED THRESHOLD')
print(hdr)
rb = stats(pb, TH); rc = stats(pc, TH)
for nm, s in (('2016 baseline (RGB)', rb), ('2016 corrected (NIR+CHM)', rc)):
    print(f'{nm:<26}{TH:>7.3f}{s[0]:>9.4f}{s[1]:>10.4f}{s[2]:>11.4f}{s[3]:>+9.4f}{s[4]:>9.4f}')
print(f"{'  change':<26}{'':>7}{rc[0]-rb[0]:>+9.4f}{rc[1]-rb[1]:>+10.4f}"
      f"{rc[2]-rb[2]:>+11.4f}{rc[3]-rb[3]:>+9.4f}{rc[4]-rb[4]:>+9.4f}")

# (b) re-threshold corrected to match baseline OVERALL recall
target = rb[0]
lo, hi = 0.001, 0.999
for _ in range(40):
    mid = (lo + hi) / 2
    if stats(pc, mid)[0] > target: lo = mid
    else: hi = mid
tm = (lo + hi) / 2
rm = stats(pc, tm)
print('\n(b) CORRECTED RE-THRESHOLDED TO THE BASELINE\'S OVERALL RECALL')
print(hdr)
print(f"{'2016 baseline (RGB)':<26}{TH:>7.3f}{rb[0]:>9.4f}{rb[1]:>10.4f}{rb[2]:>11.4f}{rb[3]:>+9.4f}{rb[4]:>9.4f}")
print(f"{'2016 corrected, matched':<26}{tm:>7.3f}{rm[0]:>9.4f}{rm[1]:>10.4f}{rm[2]:>11.4f}{rm[3]:>+9.4f}{rm[4]:>9.4f}")
print(f"{'  change':<26}{'':>7}{rm[0]-rb[0]:>+9.4f}{rm[1]-rb[1]:>+10.4f}"
      f"{rm[2]-rb[2]:>+11.4f}{rm[3]-rb[3]:>+9.4f}{rm[4]-rb[4]:>+9.4f}")

print('\n(c) THE WORST CELL: recall on SHORT (2-5 m) canopy OVER IMPERVIOUS')
for nm, pr, t in (('baseline', pb, TH), ('corrected', pc, TH), ('corrected matched', pc, tm)):
    m = ci & (hgt >= 2) & (hgt < 5)
    v = int((m & (pr >= t*254.0)).sum()) / max(int(m.sum()), 1)
    print(f'  {nm:<20}{v:>9.4f}   (n={int(m.sum()):,})')

print('\n(d) GAP BY HEIGHT BAND, baseline -> corrected(matched)')
print(f"{'band':<11}{'base gap':>10}{'corr gap':>10}{'narrowed by':>13}{'n imp':>9}")
for lo_, hi_ in BANDS:
    hb = (hgt >= lo_) & (hgt < hi_)
    mi, mp = ci & hb, cp & hb
    if int(mi.sum()) < 500: continue
    def gp(pr, t):
        return (int((mi & (pr>=t*254.0)).sum())/max(int(mi.sum()),1)
                - int((mp & (pr>=t*254.0)).sum())/max(int(mp.sum()),1))
    gb, gc = gp(pb, TH), gp(pc, tm)
    lab = f'{lo_}-{hi_} m' if hi_ < 100 else f'{lo_}+ m'
    print(f'{lab:<11}{gb:>+10.4f}{gc:>+10.4f}{gc-gb:>+13.4f}{int(mi.sum()):>9,}')

print('\nREAD: in (b) a NARROWED gap at EQUAL overall recall means the correction actually')
print('redistributed detection toward overhang - a real fix. An UNCHANGED gap means it just')
print('called more canopy everywhere and the mechanism is untouched.')

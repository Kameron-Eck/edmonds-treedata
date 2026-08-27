r"""Build the ArcGIS annotation-pilot layers (Tier-1 "please look here" targeting).

Outputs (local only, lake untouched):
  D:\edmonds-pipeline\ARCGIS\MachineLearning\annotation_pilot\
    hotspots_2016.gpkg            layers: arm_disagree, shared_fn
    paint_target_2016_from2020mask.tif   clipped COPY of the 2020 mask (Pixel Editor target)
    hotspots_README.txt

Conventions copied from qc/phase4_qc_indep.py (the scoring authority):
  prob valid = DN != 255; canopy call = DN >= thresh*254
  C-CAP forest_wetland canopy = classes {9,10,11,13,16}; ignore = {0,1,24,25} + nodata
"""
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import sieve, shapes
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window, from_bounds
from pathlib import Path

CHM = Path(r"G:/My Drive/treedata/phase4/masks/edmonds_canopy_prob_2016_fullext_sectors_v1.tif")
NIR = Path(r"G:/My Drive/treedata/phase4/masks/edmonds_canopy_prob_2016_nir_m06.tif")
REF = Path(r"D:/edmonds-pipeline/Imagery/ccap_2016_hires_lc_snohfull.tif")
MASK2020 = Path(r"G:/My Drive/treedata/phase3/edmonds_canopy_mask_2020.tif")
OUT = Path(r"D:/edmonds-pipeline/ARCGIS/MachineLearning/annotation_pilot")

THR_CHM = 0.5223            # each arm at its OWN deployed threshold
THR_NIR = 0.5939
CANOPY_CODES = np.array([9, 10, 11, 13, 16])     # forest_wetland def
IGNORE_CODES = np.array([0, 1, 24, 25])
MIN_AREA_M2 = 100.0
TOP_N = 40
BLOCK = 2048

for p in (CHM, NIR, REF, MASK2020):
    if not p.exists():
        raise SystemExit(f"MISSING INPUT: {p}")
OUT.mkdir(parents=True, exist_ok=True)

with rasterio.open(CHM) as a, rasterio.open(NIR) as b:
    assert a.crs == b.crs and a.transform == b.transform and a.shape == b.shape, \
        "prob rasters are not on one grid — refusing"
    H, W, crs, transform = a.height, a.width, a.crs, a.transform

from pyproj import CRS as pyCRS
unit_m = float(pyCRS.from_user_input(crs).axis_info[0].unit_conversion_factor)
px_area_m2 = abs(transform.a * transform.e) * unit_m ** 2
sieve_px = int(np.ceil(MIN_AREA_M2 / px_area_m2))
print(f"grid {W}x{H}  px={px_area_m2:.4f} m2  sieve>={sieve_px} px (>= {MIN_AREA_M2} m2)")

thr_chm_u8, thr_nir_u8 = THR_CHM * 254.0, THR_NIR * 254.0
disagree = np.zeros((H, W), dtype=np.uint8)
shared_fn = np.zeros((H, W), dtype=np.uint8)
n_valid = 0

ref_src = rasterio.open(REF)
ref_nodata = ref_src.nodata
with rasterio.open(CHM) as da, rasterio.open(NIR) as db, \
     WarpedVRT(ref_src, crs=crs, transform=transform, width=W, height=H,
               resampling=Resampling.nearest) as vref:
    n_blocks = (H + BLOCK - 1) // BLOCK
    for bi, row0 in enumerate(range(0, H, BLOCK)):
        rows = min(BLOCK, H - row0)
        win = Window(0, row0, W, rows)
        pa = da.read(1, window=win)
        pb = db.read(1, window=win)
        valid = (pa != 255) & (pb != 255)
        if not valid.any():
            continue
        ca = valid & (pa >= thr_chm_u8)
        cb = valid & (pb >= thr_nir_u8)
        disagree[row0:row0 + rows] = (ca ^ cb).astype(np.uint8)
        rc = vref.read(1, window=win)
        ref_ig = np.isin(rc, IGNORE_CODES)
        if ref_nodata is not None:
            ref_ig |= (rc == ref_nodata)
        ref_can = np.isin(rc, CANOPY_CODES) & ~ref_ig
        shared_fn[row0:row0 + rows] = (valid & ~ref_ig & ref_can & ~ca & ~cb).astype(np.uint8)
        n_valid += int(valid.sum())
        if bi % 4 == 0 or bi == n_blocks - 1:
            print(f"  block {bi+1}/{n_blocks}", flush=True)
ref_src.close()
print(f"valid px (both arms): {n_valid:,}  ({n_valid*px_area_m2/1e4:,.1f} ha)")

import geopandas as gpd
from shapely.geometry import shape as shp_shape

def polygonize_top(mask_u8, kind):
    total_px = int(mask_u8.sum())
    s = sieve(mask_u8, size=sieve_px)
    kept_px = int(s.sum())
    feats = []
    for geom, val in shapes(s, mask=s.astype(bool), transform=transform):
        g = shp_shape(geom)
        feats.append((g, g.area * unit_m ** 2))
    feats.sort(key=lambda t: -t[1])
    top = feats[:TOP_N]
    gdf = gpd.GeoDataFrame(
        {"rank": range(1, len(top) + 1),
         "area_m2": [round(a, 1) for _, a in top],
         "kind": kind,
         "note": ("model arms disagree — one is wrong; your call decides which"
                  if kind == "arm_disagree" else
                  "BOTH arms miss what C-CAP calls canopy — judge model vs reference"),
         },
        geometry=[g for g, _ in top], crs=crs)
    print(f"{kind}: raw {total_px:,} px ({total_px*px_area_m2/1e4:,.2f} ha), "
          f"post-sieve {kept_px:,} px, {len(feats)} regions, kept top {len(top)} "
          f"({sum(a for _, a in top)/1e4:,.2f} ha)")
    return gdf, total_px, kept_px, len(feats)

gdf_d, d_raw, d_kept, d_nreg = polygonize_top(disagree, "arm_disagree")
gdf_f, f_raw, f_kept, f_nreg = polygonize_top(shared_fn, "shared_fn")
gpkg = OUT / "hotspots_2016.gpkg"
if gpkg.exists():
    gpkg.unlink()
gdf_d.to_file(gpkg, layer="arm_disagree", driver="GPKG")
gdf_f.to_file(gpkg, layer="shared_fn", driver="GPKG")
print("wrote", gpkg)

# paint target: 1 km buffer around the union of the top-10 hotspots (both kinds, by area)
allten = sorted(list(zip(gdf_d.geometry, gdf_d.area_m2)) +
                list(zip(gdf_f.geometry, gdf_f.area_m2)), key=lambda t: -t[1])[:10]
from shapely.ops import unary_union
u = unary_union([g for g, _ in allten])
buf_units = 1000.0 / unit_m                       # 1 km in CRS units (US ft)
minx, miny, maxx, maxy = u.buffer(buf_units).bounds
import pyproj
tf = pyproj.Transformer.from_crs(crs, "EPSG:3857", always_xy=True)
(x0, x1), (y0, y1) = tf.transform([minx, maxx], [miny, maxy])
with rasterio.open(MASK2020) as m:
    win = from_bounds(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1), m.transform)
    win = win.round_offsets().round_lengths()
    data = m.read(1, window=win)
    prof = m.profile.copy()
    tgt = OUT / "paint_target_2016_from2020mask.tif"
    if tgt.exists():
        tgt.unlink()                  # a corrupt partial can't be opened by GDAL's deleter
    prof.pop("blockxsize", None)      # source is strip-organized; a carried
    prof.pop("blockysize", None)      # blockysize=1 is invalid with tiled=True
    prof.update(width=int(win.width), height=int(win.height),
                transform=m.window_transform(win), compress="lzw",
                tiled=True, blockxsize=512, blockysize=512)
    with rasterio.open(OUT / "paint_target_2016_from2020mask.tif", "w", **prof) as dst:
        dst.write(data, 1)
vals, cnts = np.unique(data, return_counts=True)
print("paint target:", dict(zip(vals.tolist(), cnts.tolist())),
      f"  {int(win.width)}x{int(win.height)} px")

(OUT / "hotspots_README.txt").write_text(
    "annotation_pilot — Tier-1 'please look here' targeting (2016, sample footprint)\n"
    "hotspots_2016.gpkg / arm_disagree : the two model arms disagree here — one is wrong;\n"
    "    your annotation decides which. Biggest polygons first (rank 1 = most area).\n"
    "hotspots_2016.gpkg / shared_fn    : BOTH arms miss what C-CAP calls canopy — the\n"
    "    label-limited blind spot. Judge whether the model or the reference is wrong.\n"
    "paint_target_2016_from2020mask.tif : a clipped COPY of the 2020 training mask\n"
    "    (0=background 1=canopy 255=IGNORE) for Pixel Editor painting. The original\n"
    "    on the lake is untouched. Corrections here follow the ADD-ONLY rule: add\n"
    "    canopy or IGNORE; never turn canopy into background.\n"
    "Work the biggest polygons first — they are the highest-value annotation targets.\n",
    encoding="utf-8")
print("wrote", OUT / "hotspots_README.txt")

# top-5 locations (combined, by area) in lat/lon + compass position within extent
tf_ll = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
with rasterio.open(CHM) as a:
    bx = a.bounds
comb = sorted(list(zip(gdf_d.geometry, gdf_d.area_m2, ["arm_disagree"] * len(gdf_d))) +
              list(zip(gdf_f.geometry, gdf_f.area_m2, ["shared_fn"] * len(gdf_f))),
              key=lambda t: -t[1])[:5]
print("\nTOP-5 hotspots (combined):")
for i, (g, a_m2, kind) in enumerate(comb, 1):
    c = g.centroid
    lon, lat = tf_ll.transform(c.x, c.y)
    ew = "west" if (c.x - bx.left) / (bx.right - bx.left) < 0.33 else \
         ("east" if (c.x - bx.left) / (bx.right - bx.left) > 0.67 else "central")
    ns = "south" if (c.y - bx.bottom) / (bx.top - bx.bottom) < 0.33 else \
         ("north" if (c.y - bx.bottom) / (bx.top - bx.bottom) > 0.67 else "mid")
    print(f"  {i}. {kind:12s} {a_m2/1e4:6.2f} ha  {ns}-{ew}  ({lat:.5f}, {lon:.5f})")

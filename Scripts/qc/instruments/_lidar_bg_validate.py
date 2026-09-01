r"""Validate the lidar verified-background raster: strip coverage, comparison to
the existing negative sources, and an independent cross-check against the
2016 CHM (which was deliberately NOT used to build the mask).
"""
import numpy as np
import rasterio
import rasterio.warp
import geopandas as gpd
from rasterio.features import rasterize
from rasterio.enums import Resampling

BG = r"D:\edmonds-pipeline\Imagery\verified_background_lidar_2005_2016.tif"
SECT = r"G:\My Drive\treedata\phase4\qc\sectors\sectors_v1.gpkg"
CHM = r"D:\edmonds-pipeline\Imagery\lidar_snoh_chm.tif"
BLD = r"G:\My Drive\treedata\buildings\masks\building_mask_2013_1m.tif"

with rasterio.open(BG) as s:
    bg = s.read(1)
    tf, crs, W, H = s.transform, s.crs, s.width, s.height
    cell = abs(tf.a)
ha = lambda m: float(m.sum()) * cell * cell / 1e4

print("RASTER  %d x %d @ %.1f m  %s" % (W, H, cell, crs))
print("  verified background : %8.0f ha" % ha(bg == 1))
print("  not verified        : %8.0f ha" % ha(bg == 0))
print("  unknown (255)       : %8.0f ha" % ha(bg == 255))

# ---- strips -------------------------------------------------------------
sec = gpd.read_file(SECT, layer="sectors").to_crs(crs)
strip = rasterize([(g, 1) for g in sec.geometry], out_shape=(H, W), transform=tf,
                  fill=0, dtype="uint8").astype(bool)
land_true = float(gpd.read_file(SECT, layer="sectors").land_ha_true.sum())
in_strip = strip & (bg != 255)
ver_strip = strip & (bg == 1)
print("\nSTRIPS (sectors_v1)")
print("  sector polygons rasterised     : %8.0f ha (true land per gpkg: %.0f ha)"
      % (ha(strip), land_true))
print("  lidar-known inside strips      : %8.0f ha  (%.1f%% of rasterised)"
      % (ha(in_strip), 100 * in_strip.sum() / max(1, strip.sum())))
print("  VERIFIED BACKGROUND in strips  : %8.0f ha  (%.1f%% of true land %.0f ha)"
      % (ha(ver_strip), 100 * ha(ver_strip) / land_true, land_true))

# ---- compare with the existing negative source (buildings) --------------
try:
    with rasterio.open(BLD) as b:
        bb = np.zeros((H, W), dtype=np.uint8)
        rasterio.warp.reproject(
            source=rasterio.band(b, 1), destination=bb,
            dst_transform=tf, dst_crs=crs, resampling=Resampling.nearest)
    bld = strip & (bb == 1)
    print("\nCOMPARISON WITH EXISTING NEGATIVES")
    print("  buildings (2013 mask) in strips: %8.0f ha" % ha(bld))
    print("  lidar background in strips     : %8.0f ha  = %.1fx the building area"
          % (ha(ver_strip), ha(ver_strip) / max(1e-9, ha(bld))))
    print("  overlap (lidar bg AND building): %8.0f ha  (buildings are TALL, so this"
          % ha(bld & ver_strip))
    print("                                             should be ~0 — a sanity check)")
except Exception as e:
    print("\nbuilding comparison skipped:", type(e).__name__, e)

# ---- independent cross-check vs the CHM we did NOT use ------------------
try:
    with rasterio.open(CHM) as c:
        ch = np.zeros((H, W), dtype=np.uint8)
        rasterio.warp.reproject(
            source=rasterio.band(c, 1), destination=ch,
            dst_transform=tf, dst_crs=crs, resampling=Resampling.nearest)
    cov = ch > 0                      # 0 = CHM nodata
    v = (bg == 1) & cov
    if v.any():
        m = ch[v] * 0.2
        print("\nCROSS-CHECK vs lidar_snoh_chm.tif (NOT used in the build)")
        print("  CHM covers %.1f%% of verified-background cells" % (100 * v.sum() / max(1, (bg == 1).sum())))
        print("  CHM height on those cells: median %.2f m  p90 %.2f m  p99 %.2f m"
              % (np.median(m), np.percentile(m, 90), np.percentile(m, 99)))
        print("  fraction with CHM >= 2 m : %.2f%%   (should be small — disagreement)"
              % (100 * (m >= 2).mean()))
except Exception as e:
    print("\nCHM cross-check skipped:", type(e).__name__, e)

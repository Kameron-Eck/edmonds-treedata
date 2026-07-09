"""One-off: fetch county LIDAR bare-earth hillshade on the exact grid of the
staged first-return hillshade, then build the terrain-cancelled structure
raster  struct = clip((fr - be) + 127, 1, 254)  (U8, 0 = nodata).

Same acquisition pattern as the 2026-06-29 first-return fetch (see
HANDOFF_2026-06-29.md): 6 full-width horizontal strips through exportImage
(under the 15000x4100 cap), each strip georeferenced from its REQUEST bbox
(never trusting server geotags), then rasterio.merge, then a final exact-grid
reproject onto the fr raster so the difference is pixel-aligned.

Outputs (scratchpad, staged to Drive afterwards):
  lidar_snoh_hillshade_be.tif   bare-earth hillshade, fr grid
  lidar_snoh_structure.tif      fr-be+127 structure channel, fr grid
Prints /255 nonzero mean/std for the structure raster (for HS_STATS).
"""
import math
import sys
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.io import MemoryFile
from rasterio.merge import merge as rio_merge
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

FR_PATH = Path(r"G:\My Drive\treedata\Full_Image\Pipeline Imagery\lidar_snoh_hillshade_fr.tif")
OUT_DIR = Path(__file__).parent
BE_PATH = OUT_DIR / "lidar_snoh_hillshade_be.tif"
STRUCT_PATH = OUT_DIR / "lidar_snoh_structure.tif"

EXPORT = ("https://gis.snoco.org/img/rest/services/Topography/"
          "LIDAR_HILLSHADE_BARE_EARTH/ImageServer/exportImage")
N_STRIPS = 6
MAX_W, MAX_H = 15000, 4100

with rasterio.open(FR_PATH) as fr_ds:
    fr_profile = fr_ds.profile.copy()
    fr = fr_ds.read(1)
    fr_bounds = fr_ds.bounds
    fr_crs = fr_ds.crs
    W, H = fr_ds.width, fr_ds.height
print(f"fr grid: {W}x{H} {fr_crs} bounds={tuple(round(b,1) for b in fr_bounds)}")
assert W <= MAX_W and math.ceil(H / N_STRIPS) <= MAX_H, "strip plan violates export cap"

px = (fr_bounds.right - fr_bounds.left) / W
strip_h = math.ceil(H / N_STRIPS)
srcs = []
for i in range(N_STRIPS):
    r0 = i * strip_h
    r1 = min(H, r0 + strip_h)
    if r0 >= r1:
        break
    top = fr_bounds.top - r0 * px
    bot = fr_bounds.top - r1 * px
    bbox = (fr_bounds.left, bot, fr_bounds.right, top)
    size = (W, r1 - r0)
    print(f"strip {i}: rows {r0}..{r1}  size {size[0]}x{size[1]} ...", flush=True)
    resp = requests.get(EXPORT, params={
        "bbox": ",".join(map(str, bbox)), "bboxSR": "3857", "imageSR": "3857",
        "size": f"{size[0]},{size[1]}", "format": "tiff", "f": "image",
    }, timeout=600)
    resp.raise_for_status()
    if not resp.content[:4] in (b"II*\x00", b"MM\x00*"):
        sys.exit(f"strip {i}: not a TIFF ({resp.content[:200]!r})")
    mem = MemoryFile(resp.content)
    ds = mem.open()
    arr = ds.read(1)
    # georeference from the REQUEST bbox, not the server's geotags
    tf = from_bounds(*bbox, width=arr.shape[1], height=arr.shape[0])
    prof = {"driver": "GTiff", "dtype": "uint8", "count": 1, "crs": "EPSG:3857",
            "transform": tf, "width": arr.shape[1], "height": arr.shape[0]}
    m2 = MemoryFile()
    with m2.open(**prof) as w:
        w.write(arr.astype(np.uint8), 1)
    srcs.append(m2.open())
    ds.close(); mem.close()

mosaic, mtf = rio_merge(srcs)
for s in srcs:
    s.close()
print(f"mosaic: {mosaic.shape}")

# Snap onto the fr grid exactly (identity if the request grid matched).
be = np.zeros((H, W), np.uint8)
reproject(mosaic[0], be,
          src_transform=mtf, src_crs="EPSG:3857",
          dst_transform=fr_profile["transform"], dst_crs=fr_crs,
          resampling=Resampling.nearest)

prof = fr_profile.copy()
prof.update(dtype="uint8", count=1, compress="deflate", nodata=0)
with rasterio.open(BE_PATH, "w", **prof) as w:
    w.write(be, 1)
print(f"wrote {BE_PATH}  nonzero={np.count_nonzero(be)/be.size:.1%}")

# structure = (fr - be) + 127, valid only where BOTH inputs have data;
# clamp to 1..254 so 0 stays the nodata sentinel (same convention as fr).
valid = (fr > 0) & (be > 0)
diff = fr.astype(np.int16) - be.astype(np.int16) + 127
struct = np.clip(diff, 1, 254).astype(np.uint8)
struct[~valid] = 0
with rasterio.open(STRUCT_PATH, "w", **prof) as w:
    w.write(struct, 1)

nz = struct[struct > 0].astype(np.float64) / 255.0
print(f"wrote {STRUCT_PATH}  valid={valid.mean():.1%}")
print(f"STRUCT stats (/255 nonzero): mean={nz.mean():.4f} std={nz.std():.4f}")
print(f"BE    stats (/255 nonzero): mean={be[be>0].mean()/255:.4f} std={be[be>0].std()/255:.4f}")
print("DONE")

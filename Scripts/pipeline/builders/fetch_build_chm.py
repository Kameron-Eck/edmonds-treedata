"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — Build a REAL canopy-height 4th channel (lidar_snoh_chm.tif)
  Edmonds Temporal Active Learning Pipeline
╚══════════════════════════════════════════════════════════════════╝

WHY
───
The old `lidar_snoh_structure.tif` = clip((fr_hillshade − be_hillshade)+127) is a
DIFFERENCE OF TWO SHADED-RELIEF IMAGES, not height. Hillshade encodes slope/aspect,
not elevation, so a flat 20 m roof → struct ≈ 0 and a bumpy shrub → struct lights up.
It cannot separate grass (green+flat) from tree (green+tall) — the model's 29.5%
grass false-positive rate.

This builds a TRUE height-above-ground raster from USGS 3DEP lidar (via Microsoft
Planetary Computer's `3dep-lidar-hag` collection — Height Above Ground in metres,
computed by PDAL from the classified point cloud, ~2 m GSD, Puget Sound ~2016). HAG
gives "how tall", RGB gives "how green"; together they resolve grass↔tree↔building.

OUTPUT
──────
  lidar_snoh_chm.tif   U8, on the EXACT grid of lidar_snoh_hillshade_fr.tif so it
                       drops into the existing 4th-channel plumbing unchanged.
                       Encoding: 0 = nodata; DN = 1 + round(clip(height_m,0,50.6)*5)
                       → 0.2 m per DN, DN 1 = 0 m (grass/ground), DN 254 ≈ 50.6 m.
  Prints coverage %, /255 nonzero mean/std (for HS_STATS["chm"]), a height
  histogram, and the source item vintage.

RUN (Colab, Drive mounted — needs network + rasterio)
─────────────────────────────────────────────────────
  %cd /content/repo/Scripts/pipeline   # code cloned from GitHub since 2026-08-20
  !python fetch_build_chm.py
  # then stage lidar_snoh_chm.tif into Full_Image/Pipeline Imagery/ (default writes there)
"""

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject, transform_bounds

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "3dep-lidar-hag"          # Height Above Ground, metres, ~2 m COGs
HAG_ASSET = "data"                     # MPC 3dep-lidar-* assets use key "data"

# fr grid candidates (Colab first, then local Drive-for-Desktop mount)
FR_CANDIDATES = [
    Path("/content/drive/MyDrive/treedata/Full_Image/Pipeline Imagery/lidar_snoh_hillshade_fr.tif"),
    Path(r"G:\My Drive\treedata\Full_Image\Pipeline Imagery\lidar_snoh_hillshade_fr.tif"),
]

M_PER_DN = 0.2                         # height quantisation: 0.2 m per DN
MAX_H_M = 253 * M_PER_DN               # 50.6 m → DN 254 (DN = 1 + round(h/0.2))


def _ensure(pkg, mod=None):
    try:
        __import__(mod or pkg)
    except ImportError:
        print(f"  • installing {pkg} …", flush=True)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])


def resolve_fr(explicit):
    if explicit:
        p = Path(explicit)
        if not p.exists():
            sys.exit(f"ERROR: --fr-grid not found: {p}")
        return p
    for p in FR_CANDIDATES:
        if p.exists():
            return p
    sys.exit("ERROR: lidar_snoh_hillshade_fr.tif not found; pass --fr-grid PATH")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fr-grid", default=None,
                    help="reference grid raster (default: auto-detect the fr hillshade)")
    ap.add_argument("--out", default=None,
                    help="output path (default: lidar_snoh_chm.tif beside the fr grid)")
    ap.add_argument("--max-height", type=float, default=MAX_H_M,
                    help=f"clip ceiling in metres (default {MAX_H_M:.1f})")
    args = ap.parse_args()

    _ensure("planetary-computer", "planetary_computer")
    _ensure("pystac-client", "pystac_client")
    import planetary_computer
    from pystac_client import Client

    fr_path = resolve_fr(args.fr_grid)
    out_path = Path(args.out) if args.out else fr_path.with_name("lidar_snoh_chm.tif")

    with rasterio.open(fr_path) as fr:
        prof = fr.profile.copy()
        dst_crs = fr.crs
        dst_tf = fr.transform
        W, H = fr.width, fr.height
        b = fr.bounds
    print(f"fr grid: {W}x{H} {dst_crs} bounds={tuple(round(v,1) for v in b)}")

    # AOI in lon/lat for the STAC search
    west, south, east, north = transform_bounds(dst_crs, "EPSG:4326",
                                                 b.left, b.bottom, b.right, b.top)
    print(f"AOI (4326): {west:.5f},{south:.5f},{east:.5f},{north:.5f}")

    client = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = list(client.search(collections=[COLLECTION],
                               bbox=[west, south, east, north]).items())
    if not items:
        sys.exit(f"ERROR: no {COLLECTION} items over the AOI — try the DSM/DTM fallback")
    def _vintage(it):                       # these items use start/end_datetime
        d = it.datetime or it.properties.get("start_datetime") \
            or it.properties.get("end_datetime")
        return str(d)[:10] if d else "?"
    dts = sorted(_vintage(it) for it in items)
    print(f"{len(items)} HAG item(s); vintage {dts[0]} … {dts[-1]}")

    # Accumulate HAG (metres) onto the fr grid; keep first valid per pixel.
    acc = np.full((H, W), np.nan, np.float32)
    for i, it in enumerate(items):
        href = it.assets[HAG_ASSET].href
        with rasterio.open(href) as src:
            tmp = np.full((H, W), np.nan, np.float32)
            reproject(
                source=rasterio.band(src, 1), destination=tmp,
                src_nodata=src.nodata, dst_nodata=np.nan,
                dst_crs=dst_crs, dst_transform=dst_tf,
                resampling=Resampling.bilinear)
        fill = np.isnan(acc) & np.isfinite(tmp)
        acc[fill] = tmp[fill]
        cov = np.isfinite(acc).mean()
        print(f"  item {i+1}/{len(items)}: coverage now {cov:.1%}", flush=True)

    valid = np.isfinite(acc)
    if not valid.any():
        sys.exit("ERROR: HAG reprojected to zero valid pixels")

    # metres → U8 (0 = nodata, DN = 1 + round(clip(h,0,max)/0.2))
    h_m = np.clip(np.where(valid, acc, 0.0), 0.0, args.max_height)
    dn = (1 + np.round(h_m / M_PER_DN)).astype(np.int32)
    out = np.zeros((H, W), np.uint8)
    out[valid] = np.clip(dn[valid], 1, 254).astype(np.uint8)

    prof.update(dtype="uint8", count=1, compress="deflate", nodata=0,
                tiled=True, blockxsize=256, blockysize=256)  # tiled → no BLOCKXSIZE warning
    with rasterio.open(out_path, "w", **prof) as w:
        w.write(out, 1)

    nz = out[out > 0].astype(np.float64) / 255.0
    hv = acc[valid]
    pct = np.percentile(hv, [0, 10, 50, 90, 99])
    print(f"\nwrote {out_path}")
    print(f"  coverage: {valid.mean():.1%}  (old struct was ~57%)")
    print(f"  HS_STATS['chm'] = ([{nz.mean():.4f}], [{nz.std():.4f}])   ← paste into the pipeline")
    print(f"  height m  p0={pct[0]:.1f} p10={pct[1]:.1f} p50={pct[2]:.1f} "
          f"p90={pct[3]:.1f} p99={pct[4]:.1f}")
    print(f"  grass check: fraction of valid < 1 m = {(hv < 1.0).mean():.1%}  "
          f"(lawns/fields should be a big chunk)")
    print("DONE")


if __name__ == "__main__":
    main()

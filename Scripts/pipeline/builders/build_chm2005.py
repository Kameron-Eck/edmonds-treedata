r"""S3.2 — a canopy height model from the raw 2005 PSLC point cloud (chm2005).

WHY. Every height-channel run to date feeds a ~2016 raster to imagery from 2000-2024.
For the early half of the archive that is a 7-16 year mismatch: config.py calls
2000-2012 the "highest drift" band, and CHM_CREDIBLE_YEARS excludes 2009 outright —
while the pipeline still uses that raster as an *input* for 2009. A 2005-derived CHM is
temporally native to roughly half the archive. None has ever been built.

METHOD — deliberately identical to qc/build_chm2_2016.py, whose primitives this script
IMPORTS rather than copies (one home for the method):
  per-cell MAX height above ground, ground = per-cell MIN z of class-2 with a pull-push
  fill, then the SAME uint8 encoding as every other height product here
      DN = 1 + round(clip(h, 0, 50.6) / 0.2),  0 = nodata
  so chm2005 drops into the existing band-4 slot with no other change.

WHAT DIFFERS FROM THE 2016 BUILD, AND WHY — measured, not assumed
  cell sizes    2.0 m canopy / 4.0 m ground   (2016 build: 0.5 m / 2.0 m)
  Set from qc/instruments/audit_lidar_2005_coverage.py, which measured ground-return occupancy on
  these tiles:  1 m 44.6% | 2 m 69.5% | 3 m 80.3% | 4 m 86.5% | 5 m 90.5%.
  The 2016 build chose 2.0 m ground because ~80% of its 2 m cells held a ground return.
  For 2005 that fraction is only reached at 3 m, and the builder requires the ground
  grid to nest exactly inside the canopy grid (integer ratio), so 2.0/4.0 is the
  nesting-compatible pair that MEETS the precedent (86.5% >= 80%) rather than
  undershooting it. Copying 0.5/2.0 would have run the ground interpolation on 69.5%
  occupancy — thinner than the precedent it was borrowed from.
  Canopy at 2 m because only 12.2% of 1 m cells hold the >=3 returns needed to trust a
  per-cell maximum, against 50.6% at 2 m.

  CRS  EPSG:3740, NAD83(HARN) / UTM 10N — the cloud's ACTUAL declared CRS, read from
  the tile headers. The 2016 product is tagged 26910 (plain NAD83). The realisations
  differ by well under the 2 m cell, but tagging it 26910 would be a small lie in the
  metadata and the engine reprojects on read anyway, so it is tagged honestly.

THE LIMITATION, STATED BEFORE THE BUILD RATHER THAN AFTER
  This product is 4x coarser than chm2, and the height channel's measured value is
  CONCENTRATED IN SMALL CROWNS (+7.3 pp under 5 m2 ~= 2.2 m across). A 2 m cell is the
  size of the crowns it most needs to resolve. So chm2005 trades resolution for temporal
  correctness, and whether a correct-era 2 m height beats a 7-years-wrong 0.5 m height
  is EMPIRICAL — this script does not assume it, and S3.5 is where it gets tested with
  shared normalisation stats and 3 seeds per arm.

Run:
  py -3.12 qc/build_chm2005.py                 # build + write local, then copy to lake
  py -3.12 qc/build_chm2005.py --no-lake       # local only
"""
import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from scipy import ndimage
from phase4seg.names import clean_argv  # noqa: E402

HERE = Path(__file__).resolve().parent


def _load_builder():
    """Import the 2016 builder for its primitives. It is __main__-guarded, so this
    defines functions and constants without building anything."""
    spec = importlib.util.spec_from_file_location("_chm2", HERE / "build_chm2_2016.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


B = _load_builder()

SRC_2005 = Path(r"D:\edmonds-pipeline\Imagery\PSLC_2005")
LOCAL_OUT = Path(r"D:\edmonds-pipeline\Imagery")
NAME = "lidar_chm2005_2m.tif"
EPSG_2005 = 3740                       # NAD83(HARN) / UTM 10N — read from the headers


def log(m):
    print(m, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cell", type=float, default=2.0,
                    help="canopy grid (m). 2.0 from measured return occupancy.")
    ap.add_argument("--ground-cell", type=float, default=4.0,
                    help="ground grid (m). 4.0 = 86.5%% occupancy AND nests in --cell.")
    ap.add_argument("--max-height", type=float, default=B.MAX_H_M)
    ap.add_argument("--epsg", type=int, default=EPSG_2005)
    ap.add_argument("--rebuild", action="store_true", help="ignore the point-pass cache")
    ap.add_argument("--no-lake", action="store_true")
    a = ap.parse_args(clean_argv())

    step_ratio = a.ground_cell / a.cell
    if abs(step_ratio - round(step_ratio)) > 1e-9:
        raise SystemExit(
            f"--ground-cell ({a.ground_cell}) must be an integer multiple of --cell "
            f"({a.cell}); grid_from_bounds nests the coarse grid inside the fine one. "
            f"Measured occupancy: 3 m reaches the 80% precedent, 4 m gives 86.5% and "
            f"nests in 2 m — which is why the defaults are 2.0/4.0 and not 2.0/3.0.")

    files = B.tiles(SRC_2005)
    if not files:
        raise SystemExit(f"no non-empty tiles in {SRC_2005}")
    log(f"tiles: {len(files)} non-empty")

    x0, y1, w, h, step, _bb = B.grid_from_bounds(files, a.cell, a.ground_cell)
    wc, hc = w // step, h // step
    log(f"canopy grid {w} x {h} @ {a.cell} m ({w*h/1e6:.1f} Mcell)  origin {x0:.1f} {y1:.1f}")
    log(f"ground grid {wc} x {hc} @ {a.ground_cell} m ({wc*hc/1e6:.1f} Mcell)")

    cmax = LOCAL_OUT / f"_chm2005_maxz_{a.cell:.2f}.npy"
    cgnd = LOCAL_OUT / f"_chm2005_gmin_{a.ground_cell:.2f}.npy"
    maxz = gmin = census = None
    if cmax.exists() and cgnd.exists() and not a.rebuild:
        maxz, gmin = np.load(cmax), np.load(cgnd)
        if maxz.shape != (h, w) or gmin.shape != (hc, wc):
            log("cache shape mismatch — re-reading the cloud")
            maxz = gmin = None
        else:
            log(f"cache HIT ({cmax.name}) — skipping the point pass")
    if maxz is None:
        log(f"\n── point pass ({len(files)} tiles) ──")
        maxz, gmin, census = B.point_pass(files, x0, y1, w, h, a.cell, a.ground_cell)
        np.save(cmax, maxz)
        np.save(cgnd, gmin)
        log("cache WRITTEN")

    if census is not None:
        log("\n── class census (raw returns) ──")
        names = {1: "Unclassified", 2: "Ground", 7: "Low Point", 9: "Water",
                 17: "Bridge Deck", 18: "High Noise", 20: "Ignored Ground"}
        for k in np.nonzero(census)[0]:
            note = ("DROPPED from canopy" if k in B.DROP_FROM_CANOPY else
                    ("ground surface" if k == B.GROUND_CLASS else "kept in canopy max-z"))
            log(f"  class {int(k):2d} {names.get(int(k), '?'):16s} {census[k]:13d}"
                f"  {100*census[k]/census.sum():6.3f}%   {note}")

    log("\n── ground surface ──")
    gknown = np.isfinite(gmin)
    # Report BOTH denominators. The audit measured occupancy over cells the cloud
    # COVERS; this grid is a bbox that is ~half water and out-of-swath, so a
    # whole-grid fraction is a different number and comparing them directly reads
    # like a contradiction when they agree.
    log(f"  coarse cells WITH a class-2 return: {100*gknown.mean():.2f}% of the GRID")
    log(f"    (the audit's ~86.5% was over COVERED cells only; this grid is a bbox "
        f"that is roughly half water/out-of-swath, so the two agree when the "
        f"coverage fraction below is applied)")
    if (~gknown).any():
        d = ndimage.distance_transform_edt(~gknown, sampling=a.ground_cell)
        log("  fill distance for the rest (m): p50 %.1f  p90 %.1f  p99 %.1f  max %.1f"
            % tuple(np.percentile(d[~gknown], [50, 90, 99, 100])))
        del d
    ground_c, _ = B.pull_push_fill(gmin)
    log("  ground z (m NAVD88): p1 %.1f  p50 %.1f  p99 %.1f"
        % tuple(np.percentile(ground_c, [1, 50, 99])))

    log("\n── height above ground ──")
    crs = rasterio.crs.CRS.from_epsg(a.epsg)
    ground_f = np.empty((h, w), dtype=np.float32)
    reproject(source=ground_c, destination=ground_f,
              src_transform=from_origin(x0, y1, a.ground_cell, a.ground_cell), src_crs=crs,
              dst_transform=from_origin(x0, y1, a.cell, a.cell), dst_crs=crs,
              resampling=Resampling.bilinear)
    del ground_c
    valid = np.isfinite(maxz)
    log(f"  cells with a kept return: {100*valid.mean():.2f}% of the grid")
    hag = np.where(valid, maxz - ground_f, 0.0).astype(np.float32)
    del ground_f, maxz
    neg = int((valid & (hag < -0.5)).sum())
    log(f"  HAG < -0.5 m (ground model above the return): {neg} cells "
        f"({100*neg/max(1, valid.sum()):.3f}%) -> DN 1")
    log("  height m  p0 %.1f  p10 %.1f  p50 %.1f  p90 %.1f  p99 %.1f  max %.1f"
        % tuple(np.percentile(hag[valid], [0, 10, 50, 90, 99, 100])))

    dn = B.encode_dn(hag, valid, a.max_height)
    del hag, valid
    raw_cov = float((dn > 0).mean())
    dn, nfill = B.fill_sampling_gaps(dn)
    log(f"  sampling gaps filled: {nfill} cells ({100*nfill/dn.size:.3f}% of grid)")
    log(f"  coverage of the full grid: {100*raw_cov:.2f}% raw -> "
        f"{100*(dn>0).mean():.2f}% after gap fill")
    nsp = B.spike_census(dn)
    log(f"  isolated spikes >{B.SPIKE_M:.0f} m above all 8 neighbours: {nsp} "
        f"({100*nsp/max(1,(dn>0).sum()):.5f}% of valid) — NOT filtered")

    local = LOCAL_OUT / NAME
    prof = dict(driver="GTiff", height=h, width=w, count=1, dtype="uint8",
                crs=crs, transform=from_origin(x0, y1, a.cell, a.cell),
                nodata=0, compress="deflate", zlevel=6, tiled=True,
                blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")
    with rasterio.open(local, "w", **prof) as dst:
        dst.write(dn, 1)
        dst.update_tags(
            SOURCE="PSLC 2005 (2004-11-11 .. 2005-07-15), raw returns",
            METHOD=f"per-cell MAX height above ground; ground = MIN z class-2 on "
                   f"{a.ground_cell} m + pull-push fill; bilinear to {a.cell} m",
            CELL_M=f"{a.cell}", GROUND_CELL_M=f"{a.ground_cell}",
            ENCODING="DN = 1 + round(clip(h,0,50.6)/0.2); 0 = nodata",
            CELL_RATIONALE="ground-return occupancy measured at 44.6/69.5/80.3/86.5% "
                           "for 1/2/3/4 m; 4 m meets the 2016 build's ~80% precedent "
                           "and nests in the 2 m canopy grid",
            VERTICAL_ACCURACY="6.3 cm fundamental (Digital Coast) AND 25 cm avg / "
                              "15-25 cm soft-vegetated (InPort) - different metrics, "
                              "both recorded, never averaged",
            CAVEAT="4x coarser than lidar_chm2_2016_50cm.tif; the height channel's "
                   "value is concentrated in small crowns (~2.2 m), the size of this cell")
    log(f"\nwrote {local} ({local.stat().st_size:,} bytes)")

    if not a.no_lake:
        B._copy_verified(local, B.LAKE_OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

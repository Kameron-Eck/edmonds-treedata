r"""Verified BACKGROUND from two lidar epochs — ground flat in 2005 AND 2016.

Kam's idea (2026-08-27): a cell whose maximum height above ground is below a
low threshold in BOTH the 2005 PSLC and the 2016 USGS lidar had nothing tall
standing on it across those eleven years, so it is trustworthy BACKGROUND for
every year in that window — 2007 / 2009 / 2013 above all.

WHY THIS MATTERS: the label experiment's other negatives (water, buildings that
pre-date the year) are EASY negatives the model already rejects — measured
2026-08-27: false positives sit on buildings at the canopy base rate, i.e. not
enriched at all. The population the model actually confuses is *vegetated
ground* — lawn, grass, field, low scrub at tree margins. Those are flat, and
only lidar can certify them.

DENSITY, MEASURED (2026-08-27, this project, 46 non-empty Edmonds tiles):
PSLC 2005 realises **median 1.68 pts/m² (0.42–2.35)**, not the 0.25 stated /
0.17 cross-checked recorded in IMAGERY_FACTS.md §8 — understated ~7×. A 2 m
cell therefore holds ~7 points, so this is usable well below the "stand scale
only" limitation the docs assume. WORKPLAN §4 Tier 2 asked for exactly this
measurement before any cell size was chosen; this is it.

METHOD — deliberately IDENTICAL for both epochs
  ground     per-cell minimum z of class-2 (ground) returns, holes filled from
             the nearest known cell. Ground accuracy only bites near the
             threshold, i.e. in OPEN ground, which is where ground returns are
             densest — under closed canopy the answer is "tall" regardless.
  height     per-cell MAXIMUM z of all returns, minus that cell's ground.
  unknown    fewer than MIN_PTS returns in the cell → UNKNOWN, never "flat".
  flat       max height above ground < FLAT_M.
  verified   flat AND known in BOTH epochs, then eroded.

The two epochs differ 12× in density (1.68 vs ~21 pts/m²). For a FLATNESS test
that asymmetry is benign and points the safe way: the denser epoch is more
likely to catch a tall object, so 2016 is the stricter of the two, and 2016 is
the trustworthy epoch. This is NOT the invalid comparison IMAGERY_FACTS §8
warns about — that warning is about DIFFERENCING the two CHMs to quote change,
where sparse-reads-low manufactures growth. A conjunction of two independent
"is anything tall here" tests has no such failure: reading low can only make an
epoch say "flat" more often, and the dense epoch vetoes.

WHY POINTS FOR 2016 RATHER THAN lidar_snoh_chm.tif: symmetry. The existing CHM
is a bilinear-upsampled uint8 convenience product; using it for one epoch and
raw points for the other would make the two sides of the conjunction mean
different things. It IS used here as an independent CROSS-CHECK instead.

EROSION: the mask is consumed by warping onto each year's ORTHO grid, and this
project has measured a ~5 m east-side ortho-vs-CHM displacement (crown lean +
registration). Lidar-to-lidar needs no such allowance, but lidar-to-imagery
does, so the shipped product is eroded by EROSION_CELLS (default 3 cells = 6 m).
Areas at other erosions are reported so the choice can be revisited.

OUTPUT 1 = verified background, 0 = not verified (NOT "canopy" — this raster
never asserts canopy anywhere), nodata 255.

  py -3.12 qc/build_lidar_background.py [--flat-m 2.0] [--cell 2.0] [--erode 3]

Local CPU only. Writes local first, then copies to the data lake beside
lidar_snoh_chm.tif (the stated home for rasters derived from these clouds).
"""
import argparse
import glob
import os
import shutil
import sys
import time
from pathlib import Path

import laspy
import numpy as np
import rasterio
from rasterio.transform import from_origin
from scipy import ndimage

SRC_2005 = Path(r"D:\edmonds-pipeline\Imagery\PSLC_2005")
SRC_2016 = Path(r"D:\edmonds-pipeline\Imagery\USGS_2016")
LAKE_OUT = Path(r"G:\My Drive\treedata\Full_Image\Pipeline Imagery")
LOCAL_OUT = Path(r"D:\edmonds-pipeline\Imagery")
NAME = "verified_background_lidar_2005_2016.tif"

CHM_CHECK = Path(r"D:\edmonds-pipeline\Imagery\lidar_snoh_chm.tif")
SECTORS = Path(r"G:\My Drive\treedata\phase4\qc\sectors\sectors_v1.gpkg")

GROUND_CLASS = 2
LOW_NOISE_CLASSES = (7, 18)          # low point / high noise, excluded from ground
MIN_PTS = 3                          # fewer returns in a cell -> UNKNOWN
CHUNK = 4_000_000


def log(m):
    print(m, flush=True)


def tiles(d):
    return [f for f in sorted(glob.glob(str(d / "*.laz")))
            if laspy.open(f).header.point_count > 1000]


def grid_from_bounds(files, cell):
    xs, ys = [], []
    for f in files:
        with laspy.open(f) as fh:
            h = fh.header
            xs += [h.x_min, h.x_max]
            ys += [h.y_min, h.y_max]
    x0 = np.floor(min(xs) / cell) * cell
    y1 = np.ceil(max(ys) / cell) * cell
    w = int(np.ceil((max(xs) - x0) / cell))
    h = int(np.ceil((y1 - min(ys)) / cell))
    return x0, y1, w, h, from_origin(x0, y1, cell, cell)


def accumulate(files, x0, y1, w, h, cell, label):
    """Per-cell max z (all returns), min z (ground returns), and return count."""
    maxz = np.full(h * w, -np.inf, dtype=np.float32)
    gmin = np.full(h * w, np.inf, dtype=np.float32)
    cnt = np.zeros(h * w, dtype=np.int32)
    t0 = time.time()
    for i, f in enumerate(files, 1):
        n_f = 0
        with laspy.open(f) as fh:
            for pts in fh.chunk_iterator(CHUNK):
                x = np.asarray(pts.x, dtype=np.float64)
                y = np.asarray(pts.y, dtype=np.float64)
                z = np.asarray(pts.z, dtype=np.float32)
                c = np.asarray(pts.classification, dtype=np.uint8)
                col = ((x - x0) / cell).astype(np.int64)
                row = ((y1 - y) / cell).astype(np.int64)
                ok = (col >= 0) & (col < w) & (row >= 0) & (row < h)
                keep = ok & ~np.isin(c, LOW_NOISE_CLASSES)
                idx = row[keep] * w + col[keep]
                zz = z[keep]
                # bincount/lexsort rather than ufunc.at: `.at` is unbuffered and
                # far too slow at 863M points. Sorting by (cell, z) puts each
                # cell's extreme value last/first, so the scatter shrinks from
                # one update per POINT to one per occupied CELL.
                cnt += np.bincount(idx, minlength=cnt.size).astype(np.int32)
                order = np.lexsort((zz, idx))
                sidx, sz = idx[order], zz[order]
                last = np.empty(sidx.size, dtype=bool)
                last[-1] = True
                last[:-1] = sidx[1:] != sidx[:-1]
                np.maximum.at(maxz, sidx[last], sz[last])
                g = c[keep] == GROUND_CLASS
                if g.any():
                    gi, gz = idx[g], zz[g]
                    go = np.lexsort((gz, gi))
                    gi, gz = gi[go], gz[go]
                    first = np.empty(gi.size, dtype=bool)
                    first[0] = True
                    first[1:] = gi[1:] != gi[:-1]
                    np.minimum.at(gmin, gi[first], gz[first])
                n_f += int(keep.sum())
        log("    [%s] %2d/%d %-42s %8.2fM pts  %5.0fs"
            % (label, i, len(files), os.path.basename(f)[:42], n_f / 1e6, time.time() - t0))
    return (maxz.reshape(h, w), gmin.reshape(h, w), cnt.reshape(h, w))


def fill_ground(gmin):
    """Fill cells with no ground return from the nearest cell that has one.

    Justified: ground error only matters where the height answer is near the
    flat threshold, i.e. open ground, where ground returns are dense and the
    fill distance is a cell or two. Under canopy the fill can be poor, but
    there max-height is far above any threshold and the cell is 'not flat' on
    any plausible ground value.
    """
    known = np.isfinite(gmin)
    if known.all():
        return gmin, known
    idx = ndimage.distance_transform_edt(~known, return_distances=False,
                                         return_indices=True)
    return gmin[tuple(idx)], known


def epoch_hag(files, x0, y1, w, h, cell, label):
    maxz, gmin, cnt = accumulate(files, x0, y1, w, h, cell, label)
    ground, ground_known = fill_ground(gmin)
    hag = np.where(np.isfinite(maxz), maxz - ground, np.nan).astype(np.float32)
    known = (cnt >= MIN_PTS) & np.isfinite(maxz) & np.isfinite(ground)
    log("    [%s] cells known %.1f%% | ground returns present in %.1f%% | median HAG %.2f m"
        % (label, 100 * known.mean(), 100 * ground_known.mean(),
           float(np.nanmedian(hag[known])) if known.any() else float("nan")))
    return hag, known


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cell", type=float, default=2.0)
    ap.add_argument("--flat-m", type=float, default=2.0)
    ap.add_argument("--erode", type=int, default=3, help="cells; 3 x 2 m = 6 m")
    a = ap.parse_args([x for x in sys.argv[1:] if not (x == "-f" or x.endswith(".json"))])

    f05, f16 = tiles(SRC_2005), tiles(SRC_2016)
    log("tiles: 2005 %d | 2016 %d" % (len(f05), len(f16)))
    x0, y1, w, h, tf = grid_from_bounds(f05 + f16, a.cell)
    log("grid: %d x %d cells @ %.1f m  (%.1f Mcell)" % (w, h, a.cell, w * h / 1e6))

    # Cache the per-epoch height rasters: the point pass costs ~5 min and the
    # threshold/erosion choices are exactly what a reviewer will want to retune.
    cache = LOCAL_OUT / ("_lidar_bg_cache_%.1fm.npz" % a.cell)
    if cache.exists():
        z = np.load(cache)
        if z["shape"].tolist() == [h, w]:
            hag05, k05, hag16, k16 = z["hag05"], z["k05"], z["hag16"], z["k16"]
            log("cache HIT %s — skipping the point pass" % cache.name)
        else:
            cache.unlink()
    if not cache.exists():
        hag05, k05 = epoch_hag(f05, x0, y1, w, h, a.cell, "2005")
        hag16, k16 = epoch_hag(f16, x0, y1, w, h, a.cell, "2016")
        np.savez_compressed(cache, hag05=hag05, k05=k05, hag16=hag16, k16=k16,
                            shape=np.array([h, w]))
        log("cache WRITTEN %s" % cache.name)

    both = k05 & k16
    log("\ncells known in BOTH epochs: %.1f%% (%.0f ha)"
        % (100 * both.mean(), both.sum() * a.cell ** 2 / 1e4))

    log("\nFLAT-THRESHOLD SENSITIVITY (verified background, pre-erosion)")
    log("  thresh_m      cells        ha   %%of-both")
    for t in (1.0, 1.5, 2.0, 2.5):
        v = both & (hag05 < t) & (hag16 < t)
        log("  %6.1f   %10d  %8.0f     %5.1f%%"
            % (t, v.sum(), v.sum() * a.cell ** 2 / 1e4, 100 * v.sum() / max(1, both.sum())))

    ver = both & (hag05 < a.flat_m) & (hag16 < a.flat_m)
    log("\nEROSION SENSITIVITY (at flat<%.1f m)" % a.flat_m)
    out = None
    for e in (0, 1, 2, 3, 5):
        er = ndimage.binary_erosion(ver, iterations=e) if e else ver
        log("  erode %d cell (%.0f m): %8.0f ha" % (e, e * a.cell, er.sum() * a.cell ** 2 / 1e4))
        if e == a.erode:
            out = er
    if out is None:
        out = ndimage.binary_erosion(ver, iterations=a.erode) if a.erode else ver

    arr = np.where(both, out.astype(np.uint8), 255).astype(np.uint8)
    prof = dict(driver="GTiff", height=h, width=w, count=1, dtype="uint8",
                crs=rasterio.crs.CRS.from_epsg(26910), transform=tf, nodata=255,
                compress="LZW", tiled=True, blockxsize=512, blockysize=512)
    local = LOCAL_OUT / NAME
    with rasterio.open(local, "w", **prof) as dst:
        dst.write(arr, 1)
        dst.update_tags(
            source="PSLC 2005 + USGS 2016 lidar, points only",
            method="max height above ground < %.1f m in BOTH epochs, eroded %d cells"
                   % (a.flat_m, a.erode),
            meaning="1 = VERIFIED BACKGROUND 2005-2016; 0 = not verified; 255 = unknown",
            density_2005_measured="median 1.68 pts/m2 (IMAGERY_FACTS S8 understates ~7x)",
            cell_m="%.1f" % a.cell, built="2026-08-27")
    log("\n-> %s (%.1f MB)" % (local, local.stat().st_size / 1e6))
    try:
        shutil.copy2(local, LAKE_OUT / NAME)
        log("-> %s" % (LAKE_OUT / NAME))
    except OSError as e:
        log("lake copy FAILED (local copy stands): %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())

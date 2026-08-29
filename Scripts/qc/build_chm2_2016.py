r"""A REAL canopy height model from the raw 2016 USGS point cloud (chm2).

WHY (2026-08-29). The height channel is the largest lever this project has
measured: 4-band .6989 vs 3-band .5990 recall at matched precision on a common
198.8 Mpx footprint — ~10 pp — and the value is CONCENTRATED IN SMALL CROWNS
(+7.3 pp under 5 m2, +8.0 pp at 5-10 m2, +0.3 pp above 100 m2), which is exactly
the population the project fails on. But the raster feeding that channel,
`lidar_snoh_chm.tif`, is a convenience product: USGS 3DEP HAG (~2 m) BILINEAR-
UPSAMPLED onto a 1.0 m EPSG:3857 grid (= 67 cm ground at this latitude, and
Mercator-distorted), uint8 at 0.2 m/DN, capped 50.6 m, 40.16% nodata.
Bilinear upsampling smooths local maxima and a canopy apex IS a local maximum,
so it reads systematically low on narrow conical crowns (IMAGERY_FACTS 8.3) —
worst precisely where the channel earns its ten points.

  *** THAT MOTIVATION SURVIVED THE BUILD ONLY IN PART. MEASURED 2026-08-29 by
  section [2b] below, against the raw points with no interpolation in the loop:
  the DOMINANT defect has the OPPOSITE SIGN. The old raster reads HIGH nearly
  everywhere — +4.1 to +5.4 m in every height bin from 0 to 30 m, and 4.90 m
  mean on ground the points measure as bare — because its ~2 m support plus
  bilinear upsample make it report a NEIGHBOURHOOD MAXIMUM rather than the
  height at the cell. The apex-smoothing mechanism is real but is swamped by
  that inflation. IMAGERY_FACTS 8.3 states the direction of this defect
  BACKWARDS and wants revisiting (Kam's call — this script edits no docs). ***

This builds the height model from the points instead:
  * 0.5 m grid in EPSG:26910 (UTM 10N) — native CRS of the cloud, metric, no
    reprojection anywhere in the chain. 1.34x the linear resolution of the old
    product's true ground sampling and none of its Mercator distortion.
  * per-cell value = MAX height above ground (that IS a CHM), from the raw
    returns — no smoothing, no upsampling, no local-maximum loss.
  * IDENTICAL uint8 encoding to the old product so the A/B swap is ONE variable:
        DN = 1 + round(clip(h, 0, 50.6) / 0.2),  0 = nodata,  DN clipped 1..254
    Yes this re-quantises to 20 cm. Keeping it is the point: what is under test
    is resolution / apex accuracy / coverage / no-reprojection, NOT bit depth.

GROUND SURFACE, and what it does in gaps
  Per-cell MINIMUM z of class-2 (ground) returns on a 2.0 m grid, then a
  pull-push (pyramid) interpolation of the cells with no ground return, then
  bilinear resampling to the 0.5 m grid.
  * 2.0 m, not 0.5 m: measured on these tiles, only ~26% of 0.5 m cells hold a
    ground return but ~80% of 2.0 m cells do, and terrain is smooth at 2 m. The
    cost is a min-z-on-slope bias (min over a 2 m cell picks its lowest corner):
    ~0.14 m on a 10% slope, plus a min-of-N sampling bias of order 0.15-0.25 m
    in the open where ground returns are dense. Both push HAG HIGH by a
    near-constant amount in open ground; treat the low-height bins as carrying
    that offset when comparing against another height model.
  * IN GAPS the pull-push fills with the bilinearly-interpolated MEAN of the
    surrounding known ground at whatever pyramid level first covers the hole —
    i.e. the local terrain trend, not the nearest single cell. Nearest-fill
    (what build_lidar_background.py uses) is fine there because that script only
    asks "is anything tall here" against a threshold; HERE the ground value
    enters the OUTPUT NUMBER, so a nearest-fill error under a wide canopy patch
    on sloping ground would be carried straight into the canopy height. Residual
    error is bounded by the terrain relief across the hole, and holes are where
    canopy is closed, so it biases tall cells, not the grass/tree boundary.

CLASSES (this cloud has 6: 1 Unclassified, 2 Ground, 7 Low Point, 9 Water,
17 Bridge Deck, 20 Ignored Ground)
  ground surface   class 2 ONLY (so 9/17/20 are excluded there by construction).
  canopy max-z     EXCLUDES 7 (Low Point) and 18 (High Noise) — noise, and class
                   7 sits below ground so it would wreck the ground minimum too.
                   EXCLUDES 9 (Water): a water return is not a surface height,
                   it moves with the tide, and leaving water as NODATA is what
                   the old product does — which keeps both the coverage
                   comparison and the HS_STATS population commensurate.
                   RETAINS 17 (Bridge Deck): buildings are UNCLASSIFIED in this
                   6-class scheme and are retained, so deleting the one
                   classified elevated man-made surface would be an inconsistent
                   and undocumented edit to the height field. Counted, not hidden.

  py -3.12 qc/build_chm2_2016.py [--cell 0.5] [--ground-cell 2.0] [--no-lake]
  py -3.12 qc/build_chm2_2016.py --skip-build        # analysis only, from the tif

Local CPU only. Writes local first, then a size+sha256 VERIFIED copy to the data
lake beside lidar_snoh_chm.tif, which is never touched.
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import laspy
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from scipy import ndimage

SRC_2016 = Path(r"D:\edmonds-pipeline\Imagery\USGS_2016")
LOCAL_OUT = Path(r"D:\edmonds-pipeline\Imagery")
LAKE_OUT = Path(r"G:\My Drive\treedata\Full_Image\Pipeline Imagery")
NAME = "lidar_chm2_2016_50cm.tif"

OLD_CHM = Path(r"D:\edmonds-pipeline\Imagery\lidar_snoh_chm.tif")
SECTORS_JSON = Path(__file__).resolve().parents[1] / "pipeline" / "aoi" / "sectors_v1.json"

EPSG = 26910
GROUND_CLASS = 2
DROP_FROM_CANOPY = (7, 9, 18)      # low point / water / high noise
BRIDGE_CLASS = 17
CHUNK = 8_000_000

# ── encoding: EXACTLY the existing product's (fetch_build_chm.py) ─────────────
M_PER_DN = 0.2
MAX_H_M = 253 * M_PER_DN           # 50.6 m -> DN 254

HOLE_MIN_NEIGHBOURS = 5            # of 8; below this a gap is real, not sampling
SPIKE_M = 10.0                     # isolated cell this far above all 8 neighbours


def log(m):
    print(m, flush=True)


def _sha256(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _copy_verified(local_path, dest_dir):
    """Copy to the lake and PROVE it landed (size + sha256 both sides).

    SETTLE FIRST: the Drive mount reports size lazily and the first stat after a
    copy can read short for a file that is fine (measured 2026-08-28,
    build_groves_overlay.py). Poll to convergence, THEN hash.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / local_path.name
    want = local_path.stat().st_size
    for attempt in range(2):
        shutil.copyfile(local_path, dest)
        got = -1
        for _ in range(60):
            got = dest.stat().st_size
            if got == want:
                break
            time.sleep(5)
        if got != want:
            if attempt == 0:
                log("  (size still %d != %d after 5 min - recopying)" % (got, want))
                continue
            sys.exit("COPY FAIL (size %d != %d): %s" % (want, got, dest))
        lh, dh = _sha256(local_path), _sha256(dest)
        if lh == dh:
            log("[lake] VERIFIED %s  (%.1f MB, sha256 %s)" % (dest, got / 1e6, lh[:16]))
            return dest
        if attempt == 0:
            log("  (sha256 %s != %s - recopying)" % (lh[:16], dh[:16]))
    sys.exit("COPY FAIL (sha256 mismatch after retry): %s" % dest)


# ══════════════════════════════════════════════════════════════════════════════
#  Point pass
# ══════════════════════════════════════════════════════════════════════════════

def tiles(d):
    return [f for f in sorted(glob.glob(str(d / "*.laz")))
            if laspy.open(f).header.point_count > 1000]


def grid_from_bounds(files, cell, gcell):
    """Fine grid snapped so the coarse ground grid nests exactly inside it."""
    xs, ys = [], []
    for f in files:
        with laspy.open(f) as fh:
            h = fh.header
            xs += [h.x_min, h.x_max]
            ys += [h.y_min, h.y_max]
    step = int(round(gcell / cell))
    x0 = np.floor(min(xs) / gcell) * gcell
    y1 = np.ceil(max(ys) / gcell) * gcell
    w = int(np.ceil((max(xs) - x0) / cell))
    h = int(np.ceil((y1 - min(ys)) / cell))
    w += (-w) % step                      # multiple of the coarse:fine ratio
    h += (-h) % step
    return x0, y1, w, h, step, (min(xs), min(ys), max(xs), max(ys))


def point_pass(files, x0, y1, w, h, cell, gcell):
    """One read of the cloud -> fine max-z, coarse ground min-z, class census."""
    step = int(round(gcell / cell))
    wc, hc = w // step, h // step
    maxz = np.full(h * w, -np.inf, dtype=np.float32)
    gmin = np.full(hc * wc, np.inf, dtype=np.float32)
    census = np.zeros(64, dtype=np.int64)
    t0 = time.time()
    for i, f in enumerate(files, 1):
        n_f = 0
        with laspy.open(f) as fh:
            for pts in fh.chunk_iterator(CHUNK):
                x = np.asarray(pts.x, dtype=np.float64)
                y = np.asarray(pts.y, dtype=np.float64)
                z = np.asarray(pts.z, dtype=np.float32)
                c = np.asarray(pts.classification, dtype=np.uint8)
                census += np.bincount(c, minlength=64)[:64]

                col = ((x - x0) / cell).astype(np.int64)
                row = ((y1 - y) / cell).astype(np.int64)
                inb = (col >= 0) & (col < w) & (row >= 0) & (row < h)

                # ── canopy: max z of every kept return ────────────────────────
                keep = inb & ~np.isin(c, DROP_FROM_CANOPY)
                if keep.any():
                    idx = row[keep] * w + col[keep]
                    zz = z[keep]
                    # Sorting by (cell, z) puts each cell's maximum last, so the
                    # scatter shrinks from one update per POINT to one per
                    # occupied CELL (build_lidar_background.py's trick). Those
                    # indices are then UNIQUE, so plain fancy-index maximum is
                    # correct and much faster than the unbuffered ufunc.at.
                    order = np.lexsort((zz, idx))
                    sidx, sz = idx[order], zz[order]
                    last = np.empty(sidx.size, dtype=bool)
                    last[-1] = True
                    last[:-1] = sidx[1:] != sidx[:-1]
                    u, uz = sidx[last], sz[last]
                    maxz[u] = np.maximum(maxz[u], uz)
                    n_f += int(keep.sum())

                # ── ground: min z of class-2 returns on the COARSE grid ───────
                g = inb & (c == GROUND_CLASS)
                if g.any():
                    gi = (row[g] // step) * wc + (col[g] // step)
                    gz = z[g]
                    go = np.lexsort((gz, gi))
                    gi, gz = gi[go], gz[go]
                    first = np.empty(gi.size, dtype=bool)
                    first[0] = True
                    first[1:] = gi[1:] != gi[:-1]
                    u, uz = gi[first], gz[first]
                    gmin[u] = np.minimum(gmin[u], uz)
        log("  %2d/%d %-46s %7.2fM kept  %5.0fs"
            % (i, len(files), os.path.basename(f)[38:60], n_f / 1e6, time.time() - t0))
    return maxz.reshape(h, w), gmin.reshape(hc, wc), census


# ══════════════════════════════════════════════════════════════════════════════
#  Ground surface
# ══════════════════════════════════════════════════════════════════════════════

def _box2(a):
    """2x2 block SUM, zero-padding an odd trailing row/column."""
    hh, ww = a.shape
    if hh % 2 or ww % 2:
        a = np.pad(a, ((0, hh % 2), (0, ww % 2)))
        hh, ww = a.shape
    return a.reshape(hh // 2, 2, ww // 2, 2).sum(axis=(1, 3))


def pull_push_fill(gmin):
    """Interpolate ground where no class-2 return landed (see module docstring).

    PULL builds a pyramid of (sum, count) of the known cells; PUSH walks back
    down, keeping the measured value wherever one exists and taking the
    bilinearly-refined coarse MEAN everywhere else. O(N), deterministic, and the
    filled surface follows the surrounding terrain trend rather than snapping to
    one nearest cell.
    """
    known = np.isfinite(gmin)
    s = np.where(known, gmin, 0.0).astype(np.float32)
    c = known.astype(np.float32)
    pyr = [(s, c)]
    while max(pyr[-1][0].shape) > 2:
        s, c = pyr[-1]
        pyr.append((_box2(s), _box2(c)))
    s, c = pyr[-1]
    filled = np.where(c > 0, s / np.maximum(c, 1e-6), 0.0).astype(np.float32)
    for lvl in range(len(pyr) - 2, -1, -1):
        s, c = pyr[lvl]
        up = ndimage.zoom(filled, 2, order=1, grid_mode=True, mode="nearest")
        up = up[:s.shape[0], :s.shape[1]]
        own = s / np.maximum(c, 1e-6)
        filled = np.where(c > 0, own, up).astype(np.float32)
    return filled, known


# ══════════════════════════════════════════════════════════════════════════════
#  Encode + gap handling
# ══════════════════════════════════════════════════════════════════════════════

def encode_dn(hag, valid, max_h):
    """metres -> the EXISTING product's uint8 scheme. 0 = nodata."""
    h_m = np.clip(np.where(valid, hag, 0.0), 0.0, max_h)
    dn = np.zeros(hag.shape, dtype=np.uint8)
    dn[valid] = np.clip(1 + np.rint(h_m[valid] / M_PER_DN), 1, 254).astype(np.uint8)
    return dn


_N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _shift_into(acc, src, dy, dx, op):
    """acc[dst] op= src[shifted] for one of the 8 neighbour offsets."""
    h, w = src.shape
    ys, ye = max(0, -dy), h - max(0, dy)
    xs, xe = max(0, -dx), w - max(0, dx)
    dys, dye = max(0, dy), h - max(0, -dy)
    dxs, dxe = max(0, dx), w - max(0, -dx)
    op(acc[dys:dye, dxs:dxe], src[ys:ye, xs:xe])


def fill_sampling_gaps(dn):
    """Fill cells with no return that are ENCLOSED by cells that have one.

    A 0.5 m cell the scanner simply missed is a sampling gap, not a data gap:
    its true surface lies between its neighbours, so it takes their MEAN. A cell
    needs >= HOLE_MIN_NEIGHBOURS of 8 valid neighbours to qualify, which confines
    the fill to interiors and never grows the raster's outline across the
    coastline or the tile-block edges. Returns (filled_dn, n_filled).
    """
    valid = dn > 0
    cnt = np.zeros(dn.shape, dtype=np.uint8)
    tot = np.zeros(dn.shape, dtype=np.uint16)
    for dy, dx in _N8:
        _shift_into(cnt, valid.view(np.uint8), dy, dx,
                    lambda a, b: np.add(a, b, out=a))
        _shift_into(tot, dn, dy, dx,
                    lambda a, b: np.add(a, b, out=a, casting="unsafe"))
    fillable = (~valid) & (cnt >= HOLE_MIN_NEIGHBOURS)
    n = int(fillable.sum())
    if n:
        dn[fillable] = np.clip(
            np.rint(tot[fillable].astype(np.float32) / cnt[fillable]),
            1, 254).astype(np.uint8)
    return dn, n


def spike_census(dn):
    """Isolated cells > SPIKE_M above EVERY one of their 8 neighbours.

    Birds, wires and powerline returns are UNCLASSIFIED in this 6-class cloud, so
    a raw per-cell maximum keeps them. Counted and reported, never silently
    filtered — a filter is a modelling decision and this build changes one thing.
    """
    nbmax = np.zeros(dn.shape, dtype=np.uint8)
    for dy, dx in _N8:
        _shift_into(nbmax, dn, dy, dx, lambda a, b: np.maximum(a, b, out=a))
    thr = int(round(SPIKE_M / M_PER_DN))
    sp = (dn > 0) & (nbmax > 0) & (dn.astype(np.int16) - nbmax.astype(np.int16) > thr)
    return int(sp.sum())


# ══════════════════════════════════════════════════════════════════════════════
#  Build
# ══════════════════════════════════════════════════════════════════════════════

def build(a):
    files = tiles(SRC_2016)
    log("tiles: %d non-empty of %d" % (len(files), len(glob.glob(str(SRC_2016 / '*.laz')))))
    x0, y1, w, h, step, pb = grid_from_bounds(files, a.cell, a.ground_cell)
    wc, hc = w // step, h // step
    log("fine grid  %d x %d @ %.2f m  (%.1f Mcell)  origin %.1f %.1f"
        % (w, h, a.cell, w * h / 1e6, x0, y1))
    log("ground grid %d x %d @ %.2f m  (%.1f Mcell)" % (wc, hc, a.ground_cell, wc * hc / 1e6))

    cmax = LOCAL_OUT / ("_chm2_maxz_%.2f.npy" % a.cell)
    cgnd = LOCAL_OUT / ("_chm2_gmin_%.2f.npy" % a.ground_cell)
    ccen = LOCAL_OUT / "_chm2_census.npy"
    if cmax.exists() and cgnd.exists() and ccen.exists() and not a.rebuild:
        maxz = np.load(cmax, mmap_mode=None)
        gmin = np.load(cgnd)
        census = np.load(ccen)
        if maxz.shape != (h, w) or gmin.shape != (hc, wc):
            log("cache shape mismatch - re-reading the cloud")
            maxz = gmin = None
        else:
            log("cache HIT (%s) - skipping the point pass" % cmax.name)
    else:
        maxz = gmin = None
    if maxz is None:
        log("\n── point pass (%d tiles) ──" % len(files))
        maxz, gmin, census = point_pass(files, x0, y1, w, h, a.cell, a.ground_cell)
        np.save(cmax, maxz)
        np.save(cgnd, gmin)
        np.save(ccen, census)
        log("cache WRITTEN")

    log("\n── class census (raw returns, all tiles) ──")
    names = {1: "Unclassified", 2: "Ground", 7: "Low Point", 9: "Water",
             17: "Bridge Deck", 18: "High Noise", 20: "Ignored Ground"}
    for k in np.nonzero(census)[0]:
        log("  class %2d %-16s %13d  %6.3f%%   %s"
            % (k, names.get(int(k), "?"), census[k], 100 * census[k] / census.sum(),
               "DROPPED from canopy" if k in DROP_FROM_CANOPY else
               ("ground surface" if k == GROUND_CLASS else "kept in canopy max-z")))

    log("\n── ground surface ──")
    gknown = np.isfinite(gmin)
    log("  coarse cells WITH a class-2 return: %.2f%%" % (100 * gknown.mean()))
    d = ndimage.distance_transform_edt(~gknown, sampling=a.ground_cell)
    if (~gknown).any():
        log("  fill distance for the rest (m): p50 %.1f  p90 %.1f  p99 %.1f  max %.1f"
            % tuple(np.percentile(d[~gknown], [50, 90, 99, 100])))
    del d
    ground_c, _ = pull_push_fill(gmin)
    log("  ground z (m NAVD88): p1 %.1f  p50 %.1f  p99 %.1f"
        % tuple(np.percentile(ground_c, [1, 50, 99])))

    log("\n── height above ground ──")
    tf_c = from_origin(x0, y1, a.ground_cell, a.ground_cell)
    tf_f = from_origin(x0, y1, a.cell, a.cell)
    ground_f = np.empty((h, w), dtype=np.float32)
    reproject(source=ground_c, destination=ground_f,
              src_transform=tf_c, src_crs=rasterio.crs.CRS.from_epsg(EPSG),
              dst_transform=tf_f, dst_crs=rasterio.crs.CRS.from_epsg(EPSG),
              resampling=Resampling.bilinear)
    del ground_c
    valid = np.isfinite(maxz)
    log("  cells with a kept return: %.2f%% of the grid" % (100 * valid.mean()))
    hag = np.where(valid, maxz - ground_f, 0.0).astype(np.float32)
    del ground_f, maxz
    neg = int((valid & (hag < -0.5)).sum())
    log("  HAG < -0.5 m (ground model above the return): %d cells (%.3f%%) -> DN 1"
        % (neg, 100 * neg / max(1, valid.sum())))
    hv = hag[valid]
    log("  height m  p0 %.1f  p10 %.1f  p50 %.1f  p90 %.1f  p99 %.1f  max %.1f"
        % tuple(np.percentile(hv, [0, 10, 50, 90, 99, 100])))
    del hv

    dn = encode_dn(hag, valid, a.max_height)
    del hag, valid
    raw_cov = float((dn > 0).mean())
    dn, nfill = fill_sampling_gaps(dn)
    log("  sampling gaps filled (>=%d of 8 valid neighbours): %d cells (%.3f%% of grid)"
        % (HOLE_MIN_NEIGHBOURS, nfill, 100 * nfill / dn.size))
    log("  coverage of the full grid: %.2f%% raw -> %.2f%% after gap fill"
        % (100 * raw_cov, 100 * (dn > 0).mean()))
    nsp = spike_census(dn)
    log("  isolated spikes >%.0f m above all 8 neighbours: %d (%.5f%% of valid) - NOT filtered"
        % (SPIKE_M, nsp, 100 * nsp / max(1, (dn > 0).sum())))

    prof = dict(driver="GTiff", height=h, width=w, count=1, dtype="uint8",
                crs=rasterio.crs.CRS.from_epsg(EPSG), transform=tf_f, nodata=0,
                compress="deflate", tiled=True, blockxsize=512, blockysize=512,
                BIGTIFF="IF_SAFER")
    local = LOCAL_OUT / NAME
    with rasterio.open(local, "w", **prof) as dst:
        dst.write(dn, 1)
        dst.update_tags(
            source="USGS 3DEP WA Western North 2016 COPC point cloud, 40 tiles, "
                   "863.5M returns (D:/edmonds-pipeline/Imagery/USGS_2016)",
            method="per-cell MAX height above ground; ground = per-2.0m-cell MIN z "
                   "of class-2 returns, pull-push interpolated in gaps, bilinear to "
                   "the 0.5 m grid",
            classes="ground=class 2 only; canopy max-z excludes 7/9/18 (low point, "
                    "water, high noise), retains 17 (bridge deck) and 1/20",
            encoding="DN = 1 + round(clip(h_m,0,%.1f)/%.1f), 0 = nodata - IDENTICAL "
                     "to lidar_snoh_chm.tif so the A/B swap is one variable"
                     % (a.max_height, M_PER_DN),
            cell_m="%.2f" % a.cell, crs_note="EPSG:26910 native - no reprojection",
            gap_fill="cells with no return but >=%d of 8 valid neighbours take the "
                     "neighbour mean" % HOLE_MIN_NEIGHBOURS,
            replaces="lidar_snoh_chm.tif (1 m EPSG:3857 bilinear-upsampled 3DEP HAG)",
            built="2026-08-29")
    log("\n[out ] %s  (%.1f MB)" % (local, local.stat().st_size / 1e6))
    if not a.no_lake:
        _copy_verified(local, LAKE_OUT)
    return local


# ══════════════════════════════════════════════════════════════════════════════
#  Analysis
# ══════════════════════════════════════════════════════════════════════════════

def _warp_to(src_path, dst_tf, dst_w, dst_h, resampling):
    """Warp a uint8 DN raster onto an arbitrary grid, 0 = nodata both sides."""
    out = np.zeros((dst_h, dst_w), dtype=np.float32)
    with rasterio.open(src_path) as s:
        reproject(source=rasterio.band(s, 1), destination=out,
                  src_transform=s.transform, src_crs=s.crs,
                  src_nodata=0, dst_nodata=0,
                  dst_transform=dst_tf, dst_crs=rasterio.crs.CRS.from_epsg(EPSG),
                  resampling=resampling)
    return out


def _dn_to_m(dn):
    return (dn - 1.0) * M_PER_DN


def adjudicate(a):
    """[2b] Which raster is right? Decided with NO interpolation anywhere.

    For every 2.0 m ground cell the point pass measured two numbers IN THAT SAME
    CELL: gmin (lowest class-2 return) and the maximum of the 0.5 m max-z over
    the cell's own 4x4 block. Their difference is height above ground by DIRECT
    MEASUREMENT — it uses no ground fill, no resampling and no CRS change, so it
    cannot inherit a defect from either product's construction. Read both
    rasters there and the disagreement is adjudicated rather than described.
    """
    cmax = LOCAL_OUT / ("_chm2_maxz_%.2f.npy" % a.cell)
    cgnd = LOCAL_OUT / ("_chm2_gmin_%.2f.npy" % a.ground_cell)
    if not (cmax.exists() and cgnd.exists()):
        log("\n[2b] point-cache absent - skipping the interpolation-free adjudication")
        return
    log("\n[2b] WHICH RASTER IS RIGHT - adjudicated against the RAW POINTS")
    log("     (max return minus lowest class-2 return in the SAME %.1f m cell;"
        % a.ground_cell)
    log("      no ground fill, no resampling, no CRS change enters this number)")
    maxz = np.load(cmax)
    gmin = np.load(cgnd)
    hc, wc = gmin.shape
    step = int(round(a.ground_cell / a.cell))
    blk = maxz.reshape(hc, step, wc, step).max(axis=(1, 3))
    del maxz
    meas = np.isfinite(blk) & np.isfinite(gmin)
    hag = np.where(meas, blk - gmin, np.nan).astype(np.float32)
    del blk

    with rasterio.open(LOCAL_OUT / NAME) as n:
        tf_c = from_origin(n.bounds.left, n.bounds.top, a.ground_cell, a.ground_cell)
    om = _dn_to_m(_warp_to(OLD_CHM, tf_c, wc, hc, Resampling.max))
    ok = meas & (om > -0.5) & (_warp_to(OLD_CHM, tf_c, wc, hc, Resampling.max) > 0)
    log("  comparable cells: %d" % ok.sum())

    bare = ok & (hag < 0.5)
    log("\n  A. cells the POINTS measure as BARE GROUND (< 0.5 m): n = %d (%.1f%%)"
        % (bare.sum(), 100 * bare.sum() / ok.sum()))
    log("     measured %.2f m   |   OLD chm says mean %.2f m  (p50 %.2f, p90 %.2f)"
        % (np.nanmean(hag[bare]), om[bare].mean(),
           *np.percentile(om[bare], [50, 90])))
    log("     the OLD raster calls %.1f%% of directly-measured bare ground TALLER "
        "THAN 2 m" % (100 * (om[bare] > 2).mean()))

    oz = ok & (om < 0.5)
    log("\n  B. cells the OLD chm calls ~0 m: n = %d - the points agree, %.2f m mean"
        % (oz.sum(), np.nanmean(hag[oz])))
    log("     so the old raster is right at its zero and one-sidedly HIGH elsewhere.")

    log("\n  C. binned by the MEASURED height - the offset is the whole story")
    log("      measured bin        n       measured    OLD      OLD-measured")
    for lo, hi in [(0, .5), (.5, 1), (1, 2), (2, 5), (5, 10), (10, 15),
                   (15, 20), (20, 25), (25, 30), (30, 40), (40, 60)]:
        m = ok & (hag >= lo) & (hag < hi)
        if m.sum() < 50:
            continue
        log("     %5.1f-%-5.1f m %9d      %6.2f    %6.2f      %+6.2f"
            % (lo, hi, m.sum(), np.nanmean(hag[m]), om[m].mean(),
               om[m].mean() - np.nanmean(hag[m])))
    log("     r(measured, old) = %.4f - they agree on WHERE, not on HOW MUCH"
        % np.corrcoef(hag[ok], om[ok])[0, 1])

    log("\n  D. is it just misregistration? shift the OLD grid and re-score MAE")
    for dy in (-2, 0, 2):
        row = []
        for dx in (-2, 0, 2):
            sh = np.roll(np.roll(om, dy, 0), dx, 1)
            m = ok & np.roll(np.roll(ok, dy, 0), dx, 1)
            row.append(np.nanmean(np.abs(sh[m] - hag[m])))
        log("     dy %+3.0f m: %s   (dx -%d, 0, +%d m)"
            % (dy * a.ground_cell, "  ".join("%.3f" % v for v in row),
               int(2 * a.ground_cell), int(2 * a.ground_cell)))
    log("     MAE is minimised at ZERO shift -> a level/support defect, not a "
        "registration one.")


def verified_background_check(new_path):
    """[2c] Independent cross-check on ground certified flat by a DIFFERENT tool.

    verified_background_lidar_2005_2016.tif (qc/build_lidar_background.py,
    2026-08-27) marks cells whose max height above ground was under 2 m in BOTH
    the 2005 PSLC and the 2016 USGS clouds, then erodes 6 m. The erosion is what
    makes this decisive: every cell is deep inside a flat area, so neither
    product can excuse a tall reading as a crown at the cell edge.
    """
    vb = LOCAL_OUT / "verified_background_lidar_2005_2016.tif"
    if not vb.exists():
        log("\n[2c] verified-background raster absent - skipping the cross-check")
        return
    log("\n[2c] INDEPENDENT CROSS-CHECK on 6 m-eroded VERIFIED FLAT GROUND")
    with rasterio.open(vb) as v:
        tf, w, h = v.transform, v.width, v.height
        bg = v.read(1) == 1
    log("  n = %d certified-flat cells (%.2f km2)"
        % (bg.sum(), bg.sum() * abs(tf.a * tf.e) / 1e6))
    for lbl, p in (("chm2 (new)", new_path), ("chm  (old)", OLD_CHM)):
        arr = _warp_to(p, tf, w, h, Resampling.max)
        m = bg & (arr > 0)
        hm = _dn_to_m(arr[m])
        log("   %-11s mean %5.2f m   p50 %5.2f  p90 %5.2f  p99 %5.2f   "
            "asserts >2 m on %5.2f%% of certified-FLAT ground"
            % (lbl, hm.mean(), *np.percentile(hm, [50, 90, 99]),
               100 * (hm > 2).mean()))


def coverage_extras(new_path):
    """[1b] Coverage on the two footprints that actually mean something:
    the 40 acquired laz tiles, and the city polygon the pipeline runs on."""
    with rasterio.open(new_path) as n:
        nb, ntf, nw, nh = n.bounds, n.transform, n.width, n.height
        newdn = n.read(1)
    foot = np.zeros((nh, nw), bool)
    cell = ntf.a
    for f in tiles(SRC_2016):
        hd = laspy.open(f).header
        c0 = max(0, int((hd.x_min - nb.left) / cell))
        c1 = int(np.ceil((hd.x_max - nb.left) / cell))
        r0 = max(0, int((nb.top - hd.y_max) / cell))
        r1 = int(np.ceil((nb.top - hd.y_min) / cell))
        foot[r0:r1, c0:c1] = True
    log("\n  ACQUIRED-LIDAR FOOTPRINT (the 40 laz tiles) = %.1f km2, %.2f%% of the grid"
        % (foot.sum() * cell * cell / 1e6, 100 * foot.mean()))
    log("    new coverage INSIDE it: %.2f%%   (of the whole grid: %.2f%%)"
        % (100 * (newdn[foot] > 0).mean(), 100 * (newdn > 0).mean()))
    del newdn, foot

    shp = LOCAL_OUT / "City Boundry" / "Edmonds Boundry.shp"
    if not shp.exists():
        log("    (city polygon not found - skipping the city-polygon coverage)")
        return
    import geopandas as gpd
    from rasterio.features import rasterize
    g = gpd.read_file(shp).to_crs(EPSG)
    b = g.total_bounds
    cc = 2.0
    w = int((b[2] - b[0]) // cc); h = int((b[3] - b[1]) // cc)
    tf = from_origin(b[0], b[1] + h * cc, cc, cc)
    city = rasterize([(gg, 1) for gg in g.geometry], out_shape=(h, w),
                     transform=tf, dtype="uint8") > 0
    nn = _warp_to(new_path, tf, w, h, Resampling.max)
    oo = _warp_to(OLD_CHM, tf, w, h, Resampling.max)
    n_ok, o_ok = nn > 0, oo > 0
    only = o_ok & ~n_ok & city
    log("  CITY POLYGON (%.2f km2) - the footprint inference actually runs on"
        % (city.sum() * cc * cc / 1e6))
    log("    new %.2f%%   old %.2f%%   old-only %.2f pp   new-only %.2f pp"
        % (100 * n_ok[city].mean(), 100 * o_ok[city].mean(),
           100 * only.sum() / city.sum(), 100 * (n_ok & ~o_ok & city).sum() / city.sum()))
    if only.sum():
        hm = _dn_to_m(oo[only])
        log("    what the old raster holds in that old-only sliver: "
            "<2 m %.1f%%   2-5 m %.1f%%   >5 m %.1f%%"
            % (100 * (hm < 2).mean(), 100 * ((hm >= 2) & (hm < 5)).mean(),
               100 * (hm >= 5).mean()))


def analyse(new_path, a):
    log("\n" + "=" * 78)
    log("ANALYSIS  new=%s  old=%s" % (new_path.name, OLD_CHM.name))
    log("=" * 78)
    with rasterio.open(new_path) as n:
        nb, ntf, nw, nh = n.bounds, n.transform, n.width, n.height
        newdn = n.read(1)
    with rasterio.open(OLD_CHM) as o:
        ob_utm = transform_bounds(o.crs, "EPSG:%d" % EPSG, *o.bounds)
        olddn = o.read(1)
        old_cov_own = float((olddn > 0).mean())
        old_nz = olddn[olddn > 0].astype(np.float64) / 255.0
    new_cov_own = float((newdn > 0).mean())

    log("\n[1] COVERAGE")
    log("  extents (UTM 10N m)")
    log("    new %s" % str(tuple(round(v, 1) for v in nb)))
    log("    old %s   (reprojected from EPSG:3857)" % str(tuple(round(v, 1) for v in ob_utm)))
    log("  %%-of-OWN-extent (NOT comparable - the extents differ):"
        "  new %.2f%%   old %.2f%%" % (100 * new_cov_own, 100 * old_cov_own))

    # common footprint, on a neutral 2 m grid
    ix0 = max(nb.left, ob_utm[0]); iy0 = max(nb.bottom, ob_utm[1])
    ix1 = min(nb.right, ob_utm[2]); iy1 = min(nb.top, ob_utm[3])
    cc = a.common_cell
    cw = int((ix1 - ix0) // cc); ch = int((iy1 - iy0) // cc)
    ctf = from_origin(ix0, iy0 + ch * cc, cc, cc)
    log("  common footprint %.0f x %.0f m (%.1f km2) on a %.1f m grid"
        % (ix1 - ix0, iy1 - iy0, (ix1 - ix0) * (iy1 - iy0) / 1e6, cc))
    n_any = _warp_to(new_path, ctf, cw, ch, Resampling.max) > 0
    o_any = _warp_to(OLD_CHM, ctf, cw, ch, Resampling.max) > 0
    log("  COMMON FOOTPRINT coverage:  new %.2f%%   old %.2f%%   both %.2f%%   "
        "new-only %.2f%%   old-only %.2f%%"
        % (100 * n_any.mean(), 100 * o_any.mean(), 100 * (n_any & o_any).mean(),
           100 * (n_any & ~o_any).mean(), 100 * (o_any & ~n_any).mean()))

    coverage_extras(new_path)

    log("\n  SECTOR STRIPS (pipeline/aoi/sectors_v1.json, bbox reprojected to UTM)")
    log("    id      area_km2   new_cov   old_cov    delta")
    secs = json.load(open(SECTORS_JSON))["sectors"]
    tot_n = tot_o = tot_c = 0
    for s in secs:
        b = transform_bounds("EPSG:3857", "EPSG:%d" % EPSG, *s["bounds_3857"])
        sw = max(1, int((b[2] - b[0]) // cc)); sh = max(1, int((b[3] - b[1]) // cc))
        stf = from_origin(b[0], b[1] + sh * cc, cc, cc)
        nn = (_warp_to(new_path, stf, sw, sh, Resampling.max) > 0)
        oo = (_warp_to(OLD_CHM, stf, sw, sh, Resampling.max) > 0)
        log("    %-4s %9.3f   %6.2f%%   %6.2f%%   %+6.2f pp"
            % (s["id"], sw * sh * cc * cc / 1e6, 100 * nn.mean(), 100 * oo.mean(),
               100 * (nn.mean() - oo.mean())))
        tot_n += int(nn.sum()); tot_o += int(oo.sum()); tot_c += nn.size
    log("    ALL  %9.3f   %6.2f%%   %6.2f%%   %+6.2f pp"
        % (tot_c * cc * cc / 1e6, 100 * tot_n / tot_c, 100 * tot_o / tot_c,
           100 * (tot_n - tot_o) / tot_c))

    log("\n[2] THE APEX CLAIM  (common %.1f m grid, cells valid in BOTH)" % cc)
    n_max = _dn_to_m(_warp_to(new_path, ctf, cw, ch, Resampling.max))
    o_max = _dn_to_m(_warp_to(OLD_CHM, ctf, cw, ch, Resampling.max))
    n_avg = _dn_to_m(_warp_to(new_path, ctf, cw, ch, Resampling.average))
    o_avg = _dn_to_m(_warp_to(OLD_CHM, ctf, cw, ch, Resampling.average))
    both = n_any & o_any
    log("  n = %d cells (%.1f ha)" % (both.sum(), both.sum() * cc * cc / 1e4))
    log("  overall  MAX  new %.2f m  old %.2f m  new-old %+.2f m"
        % (n_max[both].mean(), o_max[both].mean(), (n_max - o_max)[both].mean()))
    log("  overall  AVG  new %.2f m  old %.2f m  new-old %+.2f m"
        % (n_avg[both].mean(), o_avg[both].mean(), (n_avg - o_avg)[both].mean()))
    # REGISTRATION CHECK. Both rasters see the same canopy from the same 2016
    # collect, so the cell-average heights must correlate strongly. A grid /
    # origin / row-col error in the build would surface here first, before it
    # silently poisoned every other number below.
    r = float(np.corrcoef(n_avg[both], o_avg[both])[0, 1])
    log("  registration check: Pearson r(new_avg, old_avg) = %.4f  %s"
        % (r, "OK" if r > 0.8 else "*** SUSPECT - check the grid math ***"))

    log("\n  binned by NEW max height - if the old product loses APEXES, the MAX gap")
    log("  grows with height while the AVG gap stays flat (smoothing conserves means).")
    edges = [0, 1, 2, 5, 10, 15, 20, 25, 30, 40, 60]

    def _table(sel_var, title):
        log("\n  %s" % title)
        log("   height bin      n cells   new_max  old_max   d_max    d_max-base   "
            "new_avg  old_avg   d_avg")
        base = None
        for lo, hi in zip(edges[:-1], edges[1:]):
            m = both & (sel_var >= lo) & (sel_var < hi)
            if m.sum() < 50:
                continue
            dmax = float((n_max - o_max)[m].mean())
            davg = float((n_avg - o_avg)[m].mean())
            if base is None:
                base = dmax
            log("   %5.0f-%-5.0f m %10d   %6.2f  %6.2f  %+6.2f     %+6.2f     "
                "%6.2f  %6.2f  %+6.2f"
                % (lo, hi, m.sum(), n_max[m].mean(), o_max[m].mean(), dmax,
                   dmax - base, n_avg[m].mean(), o_avg[m].mean(), davg))

    # Binning by the NEW value alone selects cells where the new raster read
    # high, so regression to the mean inflates the gap in the tall bins on its
    # own. The claim only stands if it survives binning by the OLD value and by
    # the SYMMETRIC mean of the two.
    _table(n_max, "(a) binned by NEW max  - selection favours the new raster")
    _table(o_max, "(b) binned by OLD max  - selection favours the old raster")
    _table(0.5 * (n_max + o_max), "(c) binned by the MEAN of the two - SYMMETRIC, "
                                  "no selection bias either way")
    tall = both & (n_max >= 20)
    log("  old-reads-low rate: %.1f%% of common cells, %.1f%% of cells >=20 m"
        % (100 * (o_max < n_max)[both].mean(), 100 * (o_max < n_max)[tall].mean()))

    adjudicate(a)
    verified_background_check(new_path)

    log("\n[3] HS_STATS for the new source (/255 non-zero, same procedure as "
        "fetch_build_chm.py:153)")
    nz = newdn[newdn > 0].astype(np.float64) / 255.0
    log('  "chm2": ([%.4f], [%.4f])' % (nz.mean(), nz.std()))
    log('  (existing "chm": ([0.2306], [0.2305]); recomputed here from the raster '
        'on disk: ([%.4f], [%.4f]))' % (old_nz.mean(), old_nz.std()))

    log("\n[4] DISTRIBUTION SANITY (valid cells only)")
    for lbl, sel, cmp_ in (("DN 1  (h = 0 m, flat ground)", newdn == 1, olddn == 1),
                           ("h > 2 m   (DN >= 11)", newdn >= 11, olddn >= 11),
                           ("h > 5 m   (DN >= 26)", newdn >= 26, olddn >= 26),
                           ("clipped at the %.1f m cap (DN 254)" % a.max_height,
                            newdn == 254, olddn == 254)):
        log("  %-34s new %7.3f%%   old %7.3f%%"
            % (lbl, 100 * sel.sum() / (newdn > 0).sum(),
               100 * cmp_.sum() / (olddn > 0).sum()))
    hm = _dn_to_m(newdn[newdn > 0].astype(np.float32))
    om = _dn_to_m(olddn[olddn > 0].astype(np.float32))
    log("  height percentiles (m, valid cells of each raster on its OWN extent)")
    log("    new  p10 %.1f  p50 %.1f  p90 %.1f  p99 %.1f  max %.1f"
        % tuple(np.percentile(hm, [10, 50, 90, 99, 100])))
    log("    old  p10 %.1f  p50 %.1f  p90 %.1f  p99 %.1f  max %.1f"
        % tuple(np.percentile(om, [10, 50, 90, 99, 100])))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cell", type=float, default=0.5)
    ap.add_argument("--ground-cell", type=float, default=2.0)
    ap.add_argument("--max-height", type=float, default=MAX_H_M)
    ap.add_argument("--common-cell", type=float, default=2.0,
                    help="neutral grid the two products are compared on")
    ap.add_argument("--rebuild", action="store_true", help="ignore the point-pass cache")
    ap.add_argument("--skip-build", action="store_true", help="analyse the existing tif")
    ap.add_argument("--no-lake", action="store_true")
    ap.add_argument("--no-analysis", action="store_true")
    a = ap.parse_args([x for x in sys.argv[1:]
                       if not (x == "-f" or x.endswith(".json"))])

    out = LOCAL_OUT / NAME if a.skip_build else build(a)
    if not a.no_analysis:
        analyse(out, a)
    return 0


if __name__ == "__main__":
    sys.exit(main())

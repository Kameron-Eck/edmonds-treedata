r"""S3.1 — is a 2005 canopy height model worth building? Coverage + density gate.

WHY (2026-08-29). The pipeline feeds a ~2016 height raster to 2000-2012 imagery — a
band config.py itself calls "highest drift", and CHM_CREDIBLE_YEARS excludes 2009
outright while still using that raster as an input. A 2005-derived CHM would be
temporally native to roughly half the archive. No 2005 height product has ever been
built.

Two facts make it plausible now. IMAGERY_FACTS measured the 2005 density on the
ACQUIRED Edmonds tiles at **1.68 pts/m² median**, against a stated 0.25 — understating
the local data ~7x — and concluded "2005 is not stand-scale-only". And 47 .copc.laz
tiles are already on local disk.

THIS SCRIPT DOES NOT BUILD ANYTHING. It answers the two questions that decide whether
building is justified, and it is a GATE: if 2005 covers materially less of the city
than 2016, the honest outcome is "one epoch is all we have" and the program stops here.

  Q1 COVERAGE  - what fraction of the city do the 2005 tiles cover, versus 2016?
  Q2 CELL SIZE - at what cell size do enough cells hold a GROUND return to
                 interpolate a ground surface? build_chm2_2016.py chose its 2.0 m
                 ground grid because ~80% of 2 m cells held a ground return in the
                 dense 2016 cloud. That fraction MUST be measured for 2005, not
                 copied — copying it is the failure mode this script exists to prevent.

Method notes:
  * Q1 is header-only (bbox + point_count per tile), so it is seconds, not minutes.
  * Q2 does ONE point pass at a 1.0 m base cell and block-aggregates to 2/3/4/5 m,
    rather than one pass per candidate size. 0.5 m is not evaluated because at
    1.68 pts/m² a 0.5 m cell holds ~0.42 returns — arithmetic, not measurement.
  * Ground = classification 2, excluding the low-noise classes the background tool
    already excludes, so this stays consistent with build_lidar_background.py.

Run:
  py -3.12 qc/audit_lidar_2005_coverage.py
"""
import argparse
import glob
import sys
from pathlib import Path

import laspy
import numpy as np

SRC_2005 = Path(r"D:\edmonds-pipeline\Imagery\PSLC_2005")
SRC_2016 = Path(r"D:\edmonds-pipeline\Imagery\USGS_2016")
CITY_SHP = Path(r"G:\My Drive\treedata\City Boundry\Edmonds Boundry.shp")
OUT_DIR = Path(r"D:\edmonds-pipeline\treedata\phase4\qc")

GROUND_CLASS = 2
LOW_NOISE_CLASSES = (7, 18)      # matches build_lidar_background.py
CHUNK = 4_000_000
BASE_CELL = 1.0                  # one pass at this, aggregated upward
AGG = (1, 2, 3, 4, 5)            # metres = BASE_CELL * factor


def log(m):
    print(m, flush=True)


MIN_TILE_PTS = 1000              # matches build_lidar_background.tiles() / build_chm2_2016


def headers(d, min_pts=MIN_TILE_PTS):
    """Per-tile bbox + point count, header-only. Cheap enough to run on everything.

    Tiles below `min_pts` are EXCLUDED, matching both existing builders. This is not
    cosmetic: the 2005 set contains near-empty tiles (one holds 3 points in a
    15 x 89 m box = 0.002 pts/m2), and including them drags the density median away
    from the figure IMAGERY_FACTS reports, which was measured on n=46 NON-EMPTY tiles.
    A density statistic is only comparable if the population matches.
    """
    out, skipped = [], 0
    for f in sorted(glob.glob(str(d / "*.laz"))):
        try:
            h = laspy.open(f).header
        except Exception as e:                     # a corrupt tile must be visible,
            log(f"    ! unreadable {Path(f).name}: {type(e).__name__}: {e}")
            continue                               # not silently skipped
        n = h.point_count
        if n < min_pts:
            skipped += 1
            continue
        area = max((h.x_max - h.x_min) * (h.y_max - h.y_min), 1.0)
        out.append(dict(path=f, n=n, x0=h.x_min, x1=h.x_max, y0=h.y_min, y1=h.y_max,
                        area=area, dens=n / area))
    if skipped:
        log(f"    ({skipped} tile(s) below {min_pts} pts excluded)")
    return out


def union_area_m2(tiles, cell=5.0):
    """Rasterised union of tile bboxes — avoids a geometry dependency and is exact
    enough at 5 m for a coverage percentage."""
    if not tiles:
        return 0.0, None
    x0 = min(t["x0"] for t in tiles); x1 = max(t["x1"] for t in tiles)
    y0 = min(t["y0"] for t in tiles); y1 = max(t["y1"] for t in tiles)
    w = int(np.ceil((x1 - x0) / cell)); h = int(np.ceil((y1 - y0) / cell))
    grid = np.zeros((h, w), bool)
    for t in tiles:
        c0 = int((t["x0"] - x0) / cell); c1 = int(np.ceil((t["x1"] - x0) / cell))
        r0 = int((y1 - t["y1"]) / cell); r1 = int(np.ceil((y1 - t["y0"]) / cell))
        grid[max(r0, 0):r1, max(c0, 0):c1] = True
    return float(grid.sum()) * cell * cell, (x0, y1, w, h, cell, grid)


def ground_occupancy(tiles):
    """One pass at BASE_CELL: per-cell total returns and ground returns.
    Returns (n_total, n_ground) as 2-D arrays on the 2005 bbox grid."""
    x0 = min(t["x0"] for t in tiles); x1 = max(t["x1"] for t in tiles)
    y0 = min(t["y0"] for t in tiles); y1 = max(t["y1"] for t in tiles)
    w = int(np.ceil((x1 - x0) / BASE_CELL)); h = int(np.ceil((y1 - y0) / BASE_CELL))
    log(f"    grid {w} x {h} @ {BASE_CELL} m ({w*h/1e6:.1f} Mcell)")
    tot = np.zeros(h * w, np.int32)
    gnd = np.zeros(h * w, np.int32)
    for i, t in enumerate(tiles, 1):
        with laspy.open(t["path"]) as fh:
            for pts in fh.chunk_iterator(CHUNK):
                x = np.asarray(pts.x, np.float64)
                y = np.asarray(pts.y, np.float64)
                c = np.asarray(pts.classification, np.uint8)
                col = ((x - x0) / BASE_CELL).astype(np.int64)
                row = ((y1 - y) / BASE_CELL).astype(np.int64)
                ok = (col >= 0) & (col < w) & (row >= 0) & (row < h) \
                    & ~np.isin(c, LOW_NOISE_CLASSES)
                idx = row[ok] * w + col[ok]
                tot += np.bincount(idx, minlength=h * w).astype(np.int32)
                g = ok & (c == GROUND_CLASS)
                gidx = row[g] * w + col[g]
                gnd += np.bincount(gidx, minlength=h * w).astype(np.int32)
        if i % 10 == 0 or i == len(tiles):
            log(f"      tile {i}/{len(tiles)}")
    return tot.reshape(h, w), gnd.reshape(h, w)


def agg_block(a, k):
    """Sum k x k blocks, trimming the ragged edge."""
    h, w = a.shape
    h2, w2 = (h // k) * k, (w // k) * k
    return a[:h2, :w2].reshape(h2 // k, k, w2 // k, k).sum(axis=(1, 3))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--min-pts", type=int, default=3,
                    help="returns per cell below which a cell is UNKNOWN "
                         "(matches build_lidar_background.MIN_PTS)")
    ap.add_argument("--skip-pass", action="store_true",
                    help="Q1 only; skip the point pass")
    ap.add_argument("--out-name", default="lidar_2005_coverage_audit.md")
    a = ap.parse_args([x for x in sys.argv[1:]
                       if not (x == "-f" or x.endswith(".json"))])

    L = ["# 2005 lidar — coverage and cell-size gate (S3.1)", ""]

    log("[Q1] reading tile headers …")
    t05, t16 = headers(SRC_2005), headers(SRC_2016)
    if not t05:
        raise SystemExit("no readable 2005 tiles — nothing to audit")
    a05, _ = union_area_m2(t05)
    a16, _ = union_area_m2(t16)

    d05 = np.array([t["dens"] for t in t05])
    d16 = np.array([t["dens"] for t in t16])
    n05 = sum(t["n"] for t in t05)
    n16 = sum(t["n"] for t in t16)

    L += ["## Q1 — coverage and density (header-only)", "",
          "| | 2005 (PSLC) | 2016 (USGS) |", "|---|---|---|",
          f"| tiles | {len(t05)} | {len(t16)} |",
          f"| total returns | {n05:,} | {n16:,} |",
          f"| bbox-union area | {a05/1e6:.2f} km² | {a16/1e6:.2f} km² |",
          f"| density, median | **{np.median(d05):.2f} pts/m²** | {np.median(d16):.2f} |",
          f"| density, range | {d05.min():.2f} – {d05.max():.2f} | {d16.min():.2f} – {d16.max():.2f} |",
          ""]
    ratio = a05 / a16 if a16 else float("nan")
    L += [f"2005 bbox-union covers **{100*ratio:.1f}%** of the 2016 union area.", ""]
    if ratio < 0.75:
        L += ["> **GATE — 2005 coverage is materially smaller than 2016.** Building a "
              "2005 CHM would leave a large part of the AOI with no temporally-native "
              "height. Report this and stop rather than building a partial product.", ""]
    else:
        L += ["> Coverage is comparable; the gate does not block on Q1.", ""]

    log(f"    2005: {len(t05)} tiles, {n05:,} pts, {a05/1e6:.2f} km², "
        f"median {np.median(d05):.2f} pts/m²")
    log(f"    2016: {len(t16)} tiles, {n16:,} pts, {a16/1e6:.2f} km², "
        f"median {np.median(d16):.2f} pts/m²")

    if not a.skip_pass:
        log("[Q2] one point pass at 1.0 m, aggregating upward …")
        tot, gnd = ground_occupancy(t05)
        L += ["## Q2 — ground-return occupancy by cell size (2005, measured)", "",
              "`build_chm2_2016.py` chose a 2.0 m ground grid because ~80% of 2 m cells",
              "held a ground return in the 2016 cloud. This is that same measurement for",
              "2005 — it must not be assumed.", "",
              "| cell | cells | any return | >= min-pts | **any GROUND return** |",
              "|---|---|---|---|---|"]
        for k in AGG:
            t_k, g_k = (tot, gnd) if k == 1 else (agg_block(tot, k), agg_block(gnd, k))
            occupied = t_k > 0
            n_occ = int(occupied.sum())
            if n_occ == 0:
                continue
            any_ret = 100.0 * n_occ / t_k.size
            enough = 100.0 * float((t_k >= a.min_pts).sum()) / t_k.size
            # ground occupancy is only meaningful where the cloud covers at all
            gocc = 100.0 * float((g_k[occupied] > 0).sum()) / n_occ
            L.append(f"| {k*BASE_CELL:.0f} m | {t_k.size:,} | {any_ret:.1f}% | "
                     f"{enough:.1f}% | **{gocc:.1f}%** |")
            log(f"    {k*BASE_CELL:.0f} m: any {any_ret:.1f}% | >= {a.min_pts} pts "
                f"{enough:.1f}% | ground {gocc:.1f}%")
        L += ["", "`any GROUND return` is computed over cells the cloud actually covers,",
              "not over the whole bbox — the bbox includes water and out-of-swath area.",
              "", "**Read it against the 2016 precedent (~80% at 2 m).** The smallest cell",
              "reaching a comparable fraction is the defensible ground-grid size for a 2005",
              "build; the canopy grid can be finer, since a canopy cell needs any return,",
              "not a ground return.", ""]

    L += ["## What this does NOT establish", "",
          "- Vertical accuracy. The 2005 record carries two figures that must both be",
          "  recorded and never averaged: 6.3 cm fundamental (Digital Coast) and",
          "  25 cm avg / 15-25 cm soft-vegetated (InPort).",
          "- Whether a 2005 CHM improves the model. That is S3.5, and it needs shared",
          "  normalisation stats and 3 seeds per arm, or it repeats the underpowered",
          "  chm2 test.", ""]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / a.out_name
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    log(f"[audit] wrote {out}")


if __name__ == "__main__":
    main()

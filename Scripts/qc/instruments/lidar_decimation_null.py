"""Decimation NULL for the 2005->2016 lidar change signal (direction Step 1b).

The 2005 PSLC cloud is ~10.8x sparser than 2016 (1.61 vs 17.39 pts/m2,
phase4/qc/lidar_2005_coverage_audit.md). Sparse sampling under-reads crown
maxima, so a 2005-vs-2016 height difference manufactures GAIN even on
unchanged ground. This instrument measures that artifact directly:

  decimate the 2016 cloud to 1.61 pts/m2 (keep-prob p = 1.61/17.39, chunk-
  level Bernoulli, seeded) -> rebuild a 2005-style CHM (2 m max-z canopy,
  4 m class-2 ground min, pull-push fill — the chm2005 grid parameters,
  constants and class rules imported from build_chm2_2016 itself) ->
  run the SAME change predicates used by certified_change_cells.csv against
  the real full-density chm2 on identical ground. TRUE change is zero by
  construction; every LOSS/GAIN cell in the output is pure density artifact.

Output: phase4/qc/lidar_decimation_null.csv
"""
import csv
import importlib.util
import io
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1]


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "_chm2b", SCRIPTS / "pipeline" / "builders" / "build_chm2_2016.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)      # main-guarded
    return mod


B = _load_builder()
import laspy  # noqa: E402  (builder already imported it)
import rasterio  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.vrt import WarpedVRT  # noqa: E402

CELL, GCELL = 2.0, 4.0                 # chm2005's grids
P_KEEP = 1.61 / 17.39                  # measured densities, coverage audit
SEED = 20260904
CHM2 = Path(r"D:\edmonds-pipeline\Imagery\lidar_chm2_2016_50cm.tif")
OUT = SCRIPTS.parent / "phase4" / "qc" / "lidar_decimation_null.csv"
LOSS_HI, FLAT_LO = 5.0, 2.0            # certified_change_cells predicates


def main():
    files = B.tiles(B.SRC_2016)
    x0, y1, w, h, step, _bounds = B.grid_from_bounds(files, CELL, GCELL)
    wc, hc = w // step, h // step
    maxz = np.full(h * w, -np.inf, dtype=np.float32)
    gmin = np.full(hc * wc, np.inf, dtype=np.float32)
    rng = np.random.default_rng(SEED)
    kept = total = 0
    for i, f in enumerate(files, 1):
        with laspy.open(f) as fh:
            for pts in fh.chunk_iterator(B.CHUNK):
                x = np.asarray(pts.x, dtype=np.float64)
                total += x.size
                sel = rng.random(x.size) < P_KEEP
                if not sel.any():
                    continue
                kept += int(sel.sum())
                x = x[sel]
                y = np.asarray(pts.y, dtype=np.float64)[sel]
                z = np.asarray(pts.z, dtype=np.float32)[sel]
                c = np.asarray(pts.classification, dtype=np.uint8)[sel]
                col = ((x - x0) / CELL).astype(np.int64)
                row = ((y1 - y) / CELL).astype(np.int64)
                inb = (col >= 0) & (col < w) & (row >= 0) & (row < h)
                keep = inb & ~np.isin(c, B.DROP_FROM_CANOPY)
                if keep.any():
                    idx = row[keep] * w + col[keep]
                    zz = z[keep]
                    order = np.lexsort((zz, idx))
                    sidx, sz = idx[order], zz[order]
                    last = np.empty(sidx.size, dtype=bool)
                    last[-1] = True
                    last[:-1] = sidx[1:] != sidx[:-1]
                    maxz[sidx[last]] = np.maximum(maxz[sidx[last]], sz[last])
                g = inb & (c == B.GROUND_CLASS)
                if g.any():
                    gi = (row[g] // step) * wc + (col[g] // step)
                    gz = z[g]
                    go = np.lexsort((gz, gi))
                    gi, gz = gi[go], gz[go]
                    first = np.empty(gi.size, dtype=bool)
                    first[0] = True
                    first[1:] = gi[1:] != gi[:-1]
                    gmin[gi[first]] = np.minimum(gmin[gi[first]], gz[first])
        print(f"  tile {i}/{len(files)}  kept {kept:,}/{total:,}", flush=True)

    maxz = maxz.reshape(h, w)
    gmin = gmin.reshape(hc, wc)
    gfill, _known = B.pull_push_fill(gmin)
    ground = np.repeat(np.repeat(gfill, step, 0), step, 1)[:h, :w]
    hag = maxz - ground
    covered = np.isfinite(maxz)
    hag = np.where(covered, hag, np.nan)

    # real full-density product on the same grid (max within each 2m cell)
    from affine import Affine
    tf = Affine(CELL, 0, x0, 0, -CELL, y1)
    with rasterio.open(CHM2) as c2:
        with WarpedVRT(c2, crs=c2.crs, transform=tf, width=w, height=h,
                       resampling=Resampling.max) as v:
            dn = v.read(1)
    real = np.where(dn > 0, (dn.astype(np.float32) - 1) * 0.2, np.nan)

    both = covered & np.isfinite(real)
    sim, act = hag[both], real[both]
    n = int(both.sum())
    cell_km2 = CELL * CELL / 1e6
    fake_gain = int(((sim < FLAT_LO) & (act >= LOSS_HI)).sum())   # sparse 'past' low, dense 'now' tall
    fake_loss = int(((sim >= LOSS_HI) & (act < FLAT_LO)).sum())
    rows = [dict(quantity=q, cells=v_, km2=round(v_ * cell_km2, 4), note=nt)
            for q, v_, nt in (
        ("compared_cells", n, f"dual-covered 2m cells; keep-p {P_KEEP:.4f}, seed {SEED}"),
        ("artifact_gain", fake_gain, "sim<2m & real>=5m — density artifact ONLY (true change=0)"),
        ("artifact_loss", fake_loss, "sim>=5m & real<2m"),
    )]
    rows.append(dict(quantity="points_kept_frac", cells=kept,
                     km2=round(kept / max(total, 1), 5),
                     note=f"of {total:,} points"))
    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        wcsv = csv.DictWriter(f, fieldnames=["quantity", "cells", "km2", "note"])
        wcsv.writeheader(); wcsv.writerows(rows)
    print(f"\ncompared {n:,} cells: ARTIFACT GAIN {fake_gain:,} "
          f"({fake_gain*cell_km2:.3f} km2)  ARTIFACT LOSS {fake_loss:,} "
          f"({fake_loss*cell_km2:.3f} km2)")
    print(f"real 2005->2016 signal was GAIN 3.509 / LOSS 0.764 km2 "
          f"(certified_change_cells.csv) — compare directly.")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

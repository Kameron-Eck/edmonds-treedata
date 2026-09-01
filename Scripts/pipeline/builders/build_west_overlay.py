"""Build a WEST-ONLY copy of a corrected-label overlay, for a geographic holdout.

WHY (2026-08-29). Node C (projected labels + proven-canopy overlay) beats Node B,
but WHY it wins is unknown, and the answer decides whether the approach scales.
The obvious test — compare the gain where labels were added against everywhere
else — was run and is INVALID: the model trains on 512 px tiles, so a tile
containing any added label gets better supervision across its whole area, and at a
full-tile exclusion only 1,513 of 67,163,941 reference-canopy pixels lie outside
the labelled region. The overlay covers just 1.445% of the city BY AREA but is
scattered so finely that essentially all canopy sits within ~100 m of a label.
Coverage fraction is not spatial separation. That overlay cannot answer the
question at any buffer.

THE FIX is to make the labels spatially CONFINED by construction: keep the
overlay only west of a cut column, train on that, and score on eastern ground
that has no added labels at any distance. Measured on the scored footprint, a cut
at prob-grid column 21024 leaves 46% of the overlay in the west and still leaves
~27.5M reference-canopy px (45%) east of it — a well-powered holdout with a
1168 px (~234 m) gap to the scoring region, more than double a training tile.

The cut is applied ON THE PROBABILITY GRID, not the overlay's native EPSG:2285.
A column in one projected CRS is not a column in another — a vertical line in
Mercator maps to a slightly rotated line in Washington-North Lambert, worth tens
of metres over the city's N-S extent, which would eat into the gap. The engine
reprojects overlays anyway (labels.py additions_from_mask warps src_crs->dst_crs),
so writing on the prob grid is free and makes the cut exact.

Scoring afterwards needs no new tooling: pass this file to
phase4_arm_bootstrap_ci.py as --split-mask with --split-buffer 512, and the
"outside" region it reports IS the label-free-tile ground.

Run:
  py -3.12 qc/build_west_overlay.py --cut-col 21024
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from phase4seg.names import clean_argv  # noqa: E402

SRC_OVERLAY = Path(r"G:/My Drive/treedata/phase4/labels_corrected/add_nodec_2009.tif")
GRID = Path(r"G:/My Drive/treedata/phase4/masks/edmonds_canopy_prob_2009_nodec_v1.tif")
DST_DRIVE = Path(r"G:/My Drive/treedata/phase4/labels_corrected/add_nodecW_2009.tif")


def main():
    ap = argparse.ArgumentParser(description="West-only overlay for a geographic holdout.")
    ap.add_argument("--cut-col", type=int, default=21024,
                    help="prob-grid column; overlay is ZEROED at and east of this")
    ap.add_argument("--src", default=str(SRC_OVERLAY))
    ap.add_argument("--grid", default=str(GRID))
    ap.add_argument("--out", default=None, help="local staging path (default: alongside cwd)")
    ap.add_argument("--block-rows", type=int, default=4096)
    args = ap.parse_args(clean_argv())

    src_p, grid_p = Path(args.src), Path(args.grid)
    for p in (src_p, grid_p):
        if not p.exists():
            raise SystemExit(f"missing: {p}")
    # local-then-copy (rule 3): never write a multi-GB raster straight to the mount
    local = Path(args.out) if args.out else Path.cwd() / DST_DRIVE.name

    with rasterio.open(grid_p) as g:
        W, H, crs, tf = g.width, g.height, g.crs, g.transform
    if not 0 < args.cut_col < W:
        raise SystemExit(f"--cut-col {args.cut_col} outside grid width {W}")

    prof = dict(driver="GTiff", width=W, height=H, count=1, dtype="uint8",
                crs=crs, transform=tf, nodata=0, compress="deflate", zlevel=6,
                tiled=True, blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")

    kept = dropped = 0
    print(f"[west] grid {W}x{H} {crs}")
    print(f"[west] cut at column {args.cut_col} — overlay kept WEST of it, zeroed at/east")
    with rasterio.open(src_p) as asrc, rasterio.open(local, "w", **prof) as dst:
        with WarpedVRT(asrc, crs=crs, transform=tf, width=W, height=H,
                       resampling=Resampling.nearest) as vrt:
            n = (H + args.block_rows - 1) // args.block_rows
            for bi, row0 in enumerate(range(0, H, args.block_rows)):
                rows = min(args.block_rows, H - row0)
                win = rasterio.windows.Window(0, row0, W, rows)
                a = vrt.read(1, window=win)
                nz = a != 0
                dropped += int(nz[:, args.cut_col:].sum())
                kept += int(nz[:, :args.cut_col].sum())
                a[:, args.cut_col:] = 0
                dst.write(a, 1, window=win)
                if bi % 4 == 0 or bi == n - 1:
                    print(f"    block {bi+1}/{n}", flush=True)

    tot = kept + dropped
    print(f"[west] overlay px kept  (west): {kept:,}  ({100*kept/tot:.1f}% of the original)")
    print(f"[west] overlay px zeroed (east): {dropped:,}")
    if kept == 0:
        raise SystemExit("REFUSING: the west half has no labels left — cut column too small")
    if dropped == 0:
        raise SystemExit("REFUSING: nothing was zeroed — this is just a copy of the original")

    size = local.stat().st_size
    print(f"[west] wrote {local} ({size:,} bytes)")
    print(f"\nNEXT: copy to {DST_DRIVE} (verified), then train an arm with")
    print(f"      --add-canopy-mask /content/drive/MyDrive/treedata/phase4/"
          f"labels_corrected/{DST_DRIVE.name}")
    print(f"      and score with --split-mask {DST_DRIVE.name} --split-buffer 512;")
    print(f"      the 'outside' region it reports is the label-free-tile holdout.")


if __name__ == "__main__":
    main()

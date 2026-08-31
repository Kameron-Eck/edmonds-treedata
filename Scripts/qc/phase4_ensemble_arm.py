"""Average N probability rasters into one ensemble arm.

WHY (2026-08-29). The dominant finding of the all-night run is that RETRAIN NOISE
is large: same recipe, different seed, AUROC moves .0047 on the whole footprint
and .0157 in the sparse-canopy region, and roughly one run in three converges
early to a visibly worse optimum (seed777: phase B best at epoch 4, peak val
.6785 against .6852 / .6842 for its siblings). Every A/B verdict tonight has been
fighting that, and the week's headline came back UNRESOLVED because of it.

Averaging independent runs is the standard remedy — the noise is independent
across seeds, the signal is not, so it cancels. This tests it with rasters that
already exist: no GPU, no retraining.

WHAT IT IS NOT. This does not make a single run more trustworthy, and it is not a
substitute for measuring the spread. An ensemble that beats its members tells you
how to DEPLOY; it says nothing about whether a one-run A/B was sound.

Averaging is done on the DN scale, which is linear in probability (DN/254), so the
mean DN is the mean probability. 255 is nodata: a pixel is nodata in the output if
it is nodata in ANY input, so every arm is scored on identical ground — the same
intersection rule the comparison tools use.

Run:
  py -3.12 qc/phase4_ensemble_arm.py --year 2009 \
      --tags nodec_v1,nodec_s1234 --out-tag nodecENS
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))


def main():
    ap = argparse.ArgumentParser(description="Average prob rasters into an ensemble arm.")
    ap.add_argument("--year", default="2009")
    ap.add_argument("--tags", required=True, help="comma-separated run tags to average")
    ap.add_argument("--out-tag", required=True, help="run tag for the ensemble raster")
    ap.add_argument("--masks-dir",
                    default=r"G:/My Drive/treedata/phase4/masks")
    ap.add_argument("--out-dir", default=None,
                    help="local staging dir (default: alongside cwd); rule 3, never "
                         "write a multi-GB raster straight to the mount")
    ap.add_argument("--reduce", default="mean", choices=["mean", "max", "median"],
                    help="how to combine the arms. MEAN is the classic ensemble. MAX "
                         "exists because mean was measured to HURT in the sparse-canopy "
                         "region (2026-08-29, -.0033 AUROC vs the best member): where "
                         "positives are rare, averaging blurs a confident minority "
                         "detection - one run finds an isolated tree, two miss it, the mean "
                         "lands near 1/3 and that true positive's rank collapses. MAX keeps "
                         "the finder. Expect it to cost precision on non-canopy, since it "
                         "amplifies false positives too.")
    ap.add_argument("--block-rows", type=int, default=4096)
    args = ap.parse_args(clean_argv())

    M = Path(args.masks_dir)
    tags = [t.strip() for t in args.tags.split(",")]
    if len(tags) < 2:
        raise SystemExit("need at least two arms to ensemble")
    paths = [M / f"edmonds_canopy_prob_{args.year}_{t}.tif" for t in tags]
    for p in paths:
        if not p.exists():
            raise SystemExit(f"missing: {p}")

    metas = []
    for p in paths:
        with rasterio.open(p) as s:
            metas.append((s.width, s.height, s.crs.to_string(),
                          tuple(round(v, 6) for v in s.transform[:6])))
    if len(set(metas)) != 1:
        raise SystemExit("arms are NOT on a common grid; refusing to average")

    with rasterio.open(paths[0]) as s0:
        prof = s0.profile.copy()
        W, H = s0.width, s0.height
    prof.update(dtype="uint8", count=1, nodata=255, compress="deflate", zlevel=6,
                tiled=True, blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")

    out_dir = Path(args.out_dir) if args.out_dir else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    local = out_dir / f"edmonds_canopy_prob_{args.year}_{args.out_tag}.tif"

    print(f"[ens] reduce={args.reduce} over {len(tags)} arms: {tags}")
    print(f"[ens] grid {W}x{H} -> {local.name}")
    srcs = [rasterio.open(p) for p in paths]
    valid_px = 0
    try:
        with rasterio.open(local, "w", **prof) as dst:
            n = (H + args.block_rows - 1) // args.block_rows
            for bi, row0 in enumerate(range(0, H, args.block_rows)):
                rows = min(args.block_rows, H - row0)
                win = rasterio.windows.Window(0, row0, W, rows)
                arrs = [s.read(1, window=win) for s in srcs]
                # nodata in ANY arm -> nodata out, so every arm is scored on the
                # SAME ground; this mirrors the intersection rule the comparison
                # tools apply, rather than silently averaging over ragged edges
                bad = np.zeros(arrs[0].shape, bool)
                for a in arrs:
                    bad |= (a == 255)
                stack = np.stack(arrs)
                if args.reduce == "mean":
                    acc = np.zeros(arrs[0].shape, np.uint16)
                    for a in arrs:
                        acc += a
                    # FLOOR, not round: every mean pixel landed up to (n-1)/n DN
                    # LOW, which is a systematic downward bias on exactly the
                    # quantity the ensemble is measured on (canopy area at a fixed
                    # threshold), pushing borderline pixels to the non-canopy side.
                    comb = ((acc + len(arrs) // 2) // len(arrs)).astype(np.uint8)
                else:
                    # 255 is nodata, so it must not win a max/median; those pixels are
                    # overwritten by `bad` below, but let them poison the statistic and
                    # a ragged edge would silently become confident canopy
                    st = stack.astype(np.int16)
                    st[st == 255] = -1
                    comb = (st.max(axis=0) if args.reduce == "max"
                            else np.median(st, axis=0)).clip(0, 254).astype(np.uint8)
                comb[bad] = 255
                valid_px += int((~bad).sum())
                dst.write(comb, 1, window=win)
                if bi % 4 == 0 or bi == n - 1:
                    print(f"    block {bi+1}/{n}", flush=True)
    finally:
        for s in srcs:
            s.close()

    print(f"[ens] wrote {local} ({local.stat().st_size:,} bytes), "
          f"{valid_px:,} valid px")
    print(f"[ens] NEXT: copy to {M / local.name} and score it like any other arm,")
    print(f"      e.g. phase4_verdict.py --arm {args.out_tag}")


if __name__ == "__main__":
    main()

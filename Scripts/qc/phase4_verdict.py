"""Apply a PRE-REGISTERED verdict band to an arm-vs-baseline gap. Mechanically.

WHY THIS EXISTS (2026-08-29). Pre-registration only works if the reading is not
done by the same judgement that wants a result. In one night this session made
three interpretation errors, every one of them a human-style framing choice
rather than a computation:
  - compared a REGION-SPECIFIC gap against a WHOLE-FOOTPRINT noise floor, which
    inflated a result 3x;
  - called .0057 "inside" a .0047 spread;
  - read a generalisation claim off a split that could not support one.
None were arithmetic slips. All three were choosing which number to compare to.

So the bands go on the command line BEFORE the arm finishes, and this script
prints the verdict. It does not decide anything: it computes the gap on the
common footprint and reports which pre-registered interval the gap falls in,
including the one nobody wants, UNRESOLVED.

The curve maths is imported from phase4_arm_pr_curves — the scorer of record —
so this can never disagree with the published tables.

Run (bands from pipeline/queue_nodec_rep.yaml):
  py -3.12 qc/phase4_verdict.py --baseline rgb3_nodeb --arm nodec_s1234 \
      --ref D:/edmonds-pipeline/Imagery/ccap_2016_hires_lc_snohfull.tif \
      --replicate-at 0.006 --refute-at 0.002 \
      --note "Node C replicate at seed 1234"
"""
import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window

HERE = Path(__file__).resolve().parent


def _load_arm_pr():
    spec = importlib.util.spec_from_file_location(
        "_arm_pr", HERE / "phase4_arm_pr_curves.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AP = _load_arm_pr()
QI = AP.QI
MASKS = AP.MASKS


def main():
    ap = argparse.ArgumentParser(description="Mechanical pre-registered verdict on an arm gap.")
    ap.add_argument("--year", default="2009")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ref-scheme", default="ccap", choices=["ccap", "binary"])
    ap.add_argument("--ref-map", default=None)
    ap.add_argument("--replicate-at", type=float, required=True,
                    help="dAUROC at or above which the pre-registration says REPLICATED")
    ap.add_argument("--refute-at", type=float, required=True,
                    help="dAUROC at or below which the pre-registration says DOES NOT STAND")
    ap.add_argument("--block-rows", type=int, default=2048)
    ap.add_argument("--note", default="")
    args = ap.parse_args([a for a in sys.argv[1:]
                          if not (a == "-f" or a.endswith(".json"))])

    if args.refute_at >= args.replicate_at:
        raise SystemExit("--refute-at must be BELOW --replicate-at; the band between them "
                         "is the unresolved zone and it must exist")

    tags = [args.baseline, args.arm]
    paths = []
    for t in tags:
        p = MASKS / f"edmonds_canopy_prob_{args.year}_{t}.tif"
        if not p.exists():
            raise SystemExit(f"missing prob raster: {p}")
        paths.append(p)

    names, canopy_order, _g, code_to_group = QI.load_ref_map(args.ref_scheme, args.ref_map)
    lut = QI.build_lut(names, code_to_group) if args.ref_scheme != "binary" else None
    defs = QI.canopy_definitions(canopy_order)
    _pname, primary_groups = defs[1 if len(defs) >= 2 else 0]
    ignore_id = names.index("ignore")
    prim_ids = [names.index(g) for g in primary_groups]

    metas = []
    for p in paths:
        with rasterio.open(p) as s:
            metas.append((s.width, s.height, s.crs.to_string(),
                          tuple(round(v, 6) for v in s.transform[:6])))
    if len(set(metas)) != 1:
        raise SystemExit("arms are NOT on a common grid; refusing to compare")
    W, H = metas[0][0], metas[0][1]

    pos = {t: np.zeros(256, np.int64) for t in tags}
    neg = {t: np.zeros(256, np.int64) for t in tags}
    srcs = [rasterio.open(p) for p in paths]
    ref_src = rasterio.open(args.ref)
    ref_nodata = ref_src.nodata
    try:
        with WarpedVRT(ref_src, crs=srcs[0].crs, transform=srcs[0].transform,
                       width=W, height=H, resampling=Resampling.nearest) as rv:
            n = (H + args.block_rows - 1) // args.block_rows
            for bi, row0 in enumerate(range(0, H, args.block_rows)):
                rows = min(args.block_rows, H - row0)
                win = Window(0, row0, W, rows)
                prs = [s.read(1, window=win) for s in srcs]
                rc = rv.read(1, window=win)
                if args.ref_scheme == "binary":
                    gid = np.full(rc.shape, names.index("other"), np.int16)
                    gid[rc > 0] = names.index("canopy")
                    if ref_nodata is not None:
                        gid[rc == ref_nodata] = ignore_id
                else:
                    gid = lut[np.clip(rc.astype(np.int64), 0, 255)]
                    if ref_nodata is not None and 0 <= int(ref_nodata) < 256:
                        gid[rc == ref_nodata] = ignore_id
                valid = gid != ignore_id
                for pr in prs:
                    valid &= (pr != 255)
                if not valid.any():
                    continue
                prim = valid & np.isin(gid, prim_ids)
                other = valid & ~prim
                for t, pr in zip(tags, prs):
                    pos[t] += np.bincount(pr[prim], minlength=256)
                    neg[t] += np.bincount(pr[other], minlength=256)
                if bi % 5 == 0 or bi == n - 1:
                    print(f"    block {bi+1}/{n}", flush=True)
    finally:
        for s in srcs:
            s.close()
        ref_src.close()

    cur = {t: AP._curve_from_hists(pos[t][:255], neg[t][:255]) for t in tags}
    b, a = cur[args.baseline], cur[args.arm]
    d_auroc = a["auroc"] - b["auroc"]
    d_ap = a["ap"] - b["ap"]

    print("\n" + "=" * 72)
    if args.note:
        print(f"  {args.note}")
    print(f"  baseline {args.baseline:22s} AUROC {b['auroc']:.4f}  PR-AUC {b['ap']:.4f}")
    print(f"  arm      {args.arm:22s} AUROC {a['auroc']:.4f}  PR-AUC {a['ap']:.4f}")
    print(f"  GAP                             dAUROC {d_auroc:+.4f}  dPR-AUC {d_ap:+.4f}")
    print(f"  pre-registered bands: replicated >= {args.replicate_at:+.4f} · "
          f"does-not-stand <= {args.refute_at:+.4f}")
    print("-" * 72)
    if d_auroc >= args.replicate_at:
        v = "REPLICATED — the result stands on this evidence."
    elif d_auroc <= args.refute_at:
        v = ("DOES NOT STAND — the original was a lucky draw. Report this as loudly "
             "as the positive was reported.")
    else:
        v = ("UNRESOLVED — the gap fell between the bands. This is NOT a win and NOT a "
             "refutation; it needs another run. Do not pick whichever reading flatters "
             "the week.")
    print(f"  VERDICT: {v}")
    print("=" * 72)
    print("  Scope: one reference, one footprint, threshold-free curve metrics. This")
    print("  applies the band; it does not establish mechanism, and it does not include")
    print("  retrain noise beyond whatever the band was set from.")


if __name__ == "__main__":
    main()

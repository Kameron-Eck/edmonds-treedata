"""WHERE do same-recipe runs disagree? Maps retrain instability onto ground.

WHY (2026-08-29). Tonight measured that retrain noise is not uniform: same recipe,
different seed, AUROC moves .0059 in the dense-canopy region and .0157 in the
sparse one — 2.7x — and nobody has explained why. Averaging three runs absorbs a
bad draw (ties the best member on AUROC, beats all on PR-AUC) while averaging two
buys only the mean, which says the runs' errors are substantially CORRELATED.

Magnitude is only half the question. The decision-relevant half is WHERE the runs
disagree, because disagreement among identically-trained models is a direct
readout of where the model is genuinely uncertain — and that is where labelling
effort would actually change something. This reads it off rasters already on disk.

WHAT IT REPORTS, over the common valid footprint, split by reference class and by
an optional region mask:
  - mean |DN spread| across arms (max-min), the raw instability in probability
  - the fraction of pixels where the arms DISAGREE about the class at a threshold
    — the disagreement that actually changes a map
  - both, split canopy vs non-canopy, so "unstable" is not confused with "rare"

CAUTION ON READING IT. High disagreement where the reference says canopy means the
runs cannot agree on real trees. High disagreement on non-canopy means they cannot
agree on what is NOT a tree — a false-positive problem. These have different fixes
and the split is the point.

Run:
  py -3.12 qc/phase4_arm_disagreement.py --year 2009 \
      --tags fullext_sectors_v1,seed1234,seed777 \
      --ref D:/edmonds-pipeline/Imagery/ccap_2016_hires_lc_snohfull.tif \
      --region-mask "G:/My Drive/treedata/phase4/labels_corrected/add_nodec_2009.tif" \
      --region-buffer 75
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


def _load(name, mod_name):
    spec = importlib.util.spec_from_file_location(mod_name, HERE / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


AP = _load("phase4_arm_pr_curves.py", "_arm_pr")
BC = _load("phase4_arm_bootstrap_ci.py", "_boot")     # reuse the O(n) dilation
QI = AP.QI
MASKS = AP.MASKS


def main():
    ap = argparse.ArgumentParser(description="Where do same-recipe arms disagree?")
    ap.add_argument("--year", default="2009")
    ap.add_argument("--tags", required=True, help="comma-separated SAME-RECIPE run tags")
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ref-scheme", default="ccap", choices=["ccap", "binary"])
    ap.add_argument("--ref-map", default=None)
    ap.add_argument("--region-mask", default=None,
                    help="optional raster; nonzero splits the report into in/out")
    ap.add_argument("--region-buffer", type=int, default=0)
    ap.add_argument("--thresh", type=float, default=0.5)
    ap.add_argument("--block-rows", type=int, default=2048)
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args([a for a in sys.argv[1:]
                          if not (a == "-f" or a.endswith(".json"))])

    tags = [t.strip() for t in args.tags.split(",")]
    if len(tags) < 2:
        raise SystemExit("need at least two arms to have a disagreement")
    paths = [MASKS / f"edmonds_canopy_prob_{args.year}_{t}.tif" for t in tags]
    for p in paths:
        if not p.exists():
            raise SystemExit(f"missing: {p}")

    names, canopy_order, _g, code_to_group = QI.load_ref_map(args.ref_scheme, args.ref_map)
    lut = QI.build_lut(names, code_to_group) if args.ref_scheme != "binary" else None
    defs = QI.canopy_definitions(canopy_order)
    _pn, primary_groups = defs[1 if len(defs) >= 2 else 0]
    ignore_id = names.index("ignore")
    prim_ids = [names.index(g) for g in primary_groups]

    with rasterio.open(paths[0]) as s0:
        W, H, crs, tf = s0.width, s0.height, s0.crs, s0.transform
    dn_thr = args.thresh * 254.0

    regions = ["all"] if not args.region_mask else ["all", "inside", "outside"]
    # accumulators: [region][cls] where cls 0=ref canopy, 1=ref non-canopy
    n_px = {r: [0, 0] for r in regions}
    spread_sum = {r: [0.0, 0.0] for r in regions}
    disagree = {r: [0, 0] for r in regions}

    srcs = [rasterio.open(p) for p in paths]
    ref_src = rasterio.open(args.ref)
    reg_src = rasterio.open(args.region_mask) if args.region_mask else None
    ref_nodata = ref_src.nodata
    try:
        import contextlib
        with contextlib.ExitStack() as st:
            rv = st.enter_context(WarpedVRT(ref_src, crs=crs, transform=tf, width=W,
                                            height=H, resampling=Resampling.nearest))
            gv = (st.enter_context(WarpedVRT(reg_src, crs=crs, transform=tf, width=W,
                                             height=H, resampling=Resampling.nearest))
                  if reg_src else None)
            n = (H + args.block_rows - 1) // args.block_rows
            for bi, row0 in enumerate(range(0, H, args.block_rows)):
                rows = min(args.block_rows, H - row0)
                win = Window(0, row0, W, rows)
                arrs = [s.read(1, window=win) for s in srcs]
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
                for a in arrs:
                    valid &= (a == a) & (a != 255)
                if not valid.any():
                    continue
                stack = np.stack([a.astype(np.int16) for a in arrs])
                spread = (stack.max(axis=0) - stack.min(axis=0)).astype(np.float32)
                pos = (stack >= dn_thr)
                # disagreement = the arms do not all call the pixel the same class
                dis = pos.any(axis=0) & ~pos.all(axis=0)

                prim = valid & np.isin(gid, prim_ids)
                other = valid & ~prim
                sel = {"all": (prim, other)}
                if gv is not None:
                    ins = gv.read(1, window=win) != 0
                    ins = BC._dilate(ins, args.region_buffer)
                    sel["inside"] = (prim & ins, other & ins)
                    sel["outside"] = (prim & ~ins, other & ~ins)
                for r in regions:
                    for ci, m in enumerate(sel[r]):
                        c = int(m.sum())
                        if c:
                            n_px[r][ci] += c
                            spread_sum[r][ci] += float(spread[m].sum())
                            disagree[r][ci] += int(dis[m].sum())
                if bi % 5 == 0 or bi == n - 1:
                    print(f"    block {bi+1}/{n}", flush=True)
    finally:
        for s in srcs:
            s.close()
        ref_src.close()
        if reg_src:
            reg_src.close()

    L = [f"# Where same-recipe arms disagree — {args.year}", "",
         f"Arms: {', '.join('`%s`' % t for t in tags)} · class threshold {args.thresh}", "",
         "`mean spread` = average (max-min) of the arms' DN on that ground, in DN units",
         "(0-254, so 2.54 DN = 1 percentage point of probability).",
         "`disagree` = share of pixels the arms do not all put on the same side of the",
         "threshold — the disagreement that actually changes a map.", "",
         "| region | ref class | pixels | mean spread (DN) | disagree |",
         "|---|---|---|---|---|"]
    for r in regions:
        for ci, cname in enumerate(("canopy", "non-canopy")):
            c = n_px[r][ci]
            if not c:
                continue
            L.append(f"| {r} | {cname} | {c:,} | {spread_sum[r][ci]/c:.2f} | "
                     f"{100*disagree[r][ci]/c:.2f}% |")
    L += ["", "Reading it: disagreement on reference CANOPY means the runs cannot agree on",
          "real trees; disagreement on NON-CANOPY means they cannot agree on what is not a",
          "tree. Different problems, different fixes — which is why the split is here.", ""]

    out = Path(args.out_dir) / f"arm_disagreement_{args.year}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\n[dis] wrote {out}")


if __name__ == "__main__":
    main()

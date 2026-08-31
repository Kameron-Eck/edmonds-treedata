"""Is a region an OVER-prediction or UNDER-prediction problem? Confusion by region.

WHY (2026-08-29). This project has operated since 2026-07-05 on the finding that
the model UNDER-predicts canopy, and labelling effort has been aimed accordingly.
Tonight's disagreement map complicated that: in the sparse-canopy region the
same-recipe runs disagree on canopy at 9.60% against 1.59% on non-canopy — but the
POPULATIONS are wildly uneven (4.37M canopy px vs 71.58M non-canopy), so in
ABSOLUTE counts the instability is ~419k canopy px against ~1.14M non-canopy px.
That reading suggests spurious detections, not missed trees, dominate there.

It was recorded as post-hoc and untested, and it must not change any labelling
recommendation until it is tested, because it points the opposite way from the
standing belief. This tests it directly: at the deployed threshold, count FP and
FN per region. FP-dominated means the region over-predicts (label negatives /
tighten precision); FN-dominated means it under-predicts (label positives).

The counts come from the SAME DN histograms phase4_arm_pr_curves scores from, so
this cannot disagree with the published tables.

CAUTION. This is measured against ONE reference (C-CAP) whose own errors are not
modelled here, and at ONE threshold. A region that is FP-dominated against this
reference may simply be where the reference disagrees with the imagery — the
2016 C-CAP reference is being applied to a 2009 raster, so real 2009->2016 change
lands in FP/FN too. Treat direction, not magnitude, as the finding.

Run:
  py -3.12 qc/phase4_region_confusion.py --year 2009 --tags rgb3_nodeb,nodec_v1 \
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
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402

HERE = Path(__file__).resolve().parent


def _load(name, mod):
    spec = importlib.util.spec_from_file_location(mod, HERE / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


AP = _load("phase4_arm_pr_curves.py", "_arm_pr")
BC = _load("phase4_arm_bootstrap_ci.py", "_boot")
QI = AP.QI
MASKS = AP.MASKS


def main():
    ap = argparse.ArgumentParser(description="FP/FN balance per region.")
    ap.add_argument("--year", default="2009")
    ap.add_argument("--tags", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ref-scheme", default="ccap", choices=["ccap", "binary"])
    ap.add_argument("--ref-map", default=None)
    ap.add_argument("--region-mask", default=None)
    ap.add_argument("--region-buffer", type=int, default=0)
    ap.add_argument("--thresh", type=float, default=0.5)
    ap.add_argument("--block-rows", type=int, default=2048)
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--out-name", default=None,
                    help="output filename; defaults to region_confusion_{year}.md.")
    ap.add_argument("--overwrite", action="store_true",
                    help="permit writing over an existing table. Without this the run "
                         "refuses rather than replacing a published measurement.")
    args = ap.parse_args(clean_argv())

    out = Path(args.out_dir) / (args.out_name or f"region_confusion_{args.year}.md")
    # THE DEFAULT NAME DEPENDS ONLY ON THE YEAR, but the table's content depends on
    # --tags and --region-mask. Adding --out-name was not enough: it defaults to None,
    # so the naming stayed year-only and a later run still replaced an earlier one.
    # That happened - a 4-arm all-only run wrote over the 2-arm inside/outside table
    # the canopy-area finding was read from, and only git still had it. Existence is
    # now a refusal, not a silent replacement.
    if out.exists() and not args.overwrite:
        raise SystemExit(
            f"refusing to overwrite {out}"
            f"{chr(10)}  It already holds a measurement, and this run's --tags/--region-mask"
            f"{chr(10)}  may differ from the run that wrote it. Pass --out-name <other>.md"
            f"{chr(10)}  to keep both, or --overwrite if you mean to replace it.")
    # checked BEFORE the raster passes: refusing after ten minutes of block reads
    # would be correct and useless.

    tags = [t.strip() for t in args.tags.split(",")]
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

    regions = ["all"] if not args.region_mask else ["all", "inside", "outside"]
    # pos/neg DN histograms per (arm, region) — same objects arm_pr_curves scores from
    pos = {(t, r): np.zeros(256, np.int64) for t in tags for r in regions}
    neg = {(t, r): np.zeros(256, np.int64) for t in tags for r in regions}

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
                    valid &= (a != 255)
                if not valid.any():
                    continue
                prim = valid & np.isin(gid, prim_ids)
                other = valid & ~prim
                sel = {"all": (prim, other)}
                if gv is not None:
                    ins = BC._dilate(gv.read(1, window=win) != 0, args.region_buffer)
                    sel["inside"] = (prim & ins, other & ins)
                    sel["outside"] = (prim & ~ins, other & ~ins)
                for t, a in zip(tags, arrs):
                    for r in regions:
                        mp, mo = sel[r]
                        pos[(t, r)] += np.bincount(a[mp], minlength=256)
                        neg[(t, r)] += np.bincount(a[mo], minlength=256)
                if bi % 5 == 0 or bi == n - 1:
                    print(f"    block {bi+1}/{n}", flush=True)
    finally:
        for s in srcs:
            s.close()
        ref_src.close()
        if reg_src:
            reg_src.close()

    cut = int(round(args.thresh * 254))
    L = [f"# FP/FN balance by region — {args.year}, threshold {args.thresh}", "",
         "FP = reference says NOT canopy, model says canopy (over-prediction).",
         "FN = reference says canopy, model says not (under-prediction).",
         "`FP:FN` above 1 means the region OVER-predicts; below 1, under-predicts.", "",
         "| arm | region | TP | FP | FN | FP:FN | recall | precision |",
         "|---|---|---|---|---|---|---|---|"]
    for t in tags:
        for r in regions:
            P, N = pos[(t, r)][:255], neg[(t, r)][:255]
            tp = int(P[cut:].sum()); fn = int(P[:cut].sum())
            fp = int(N[cut:].sum()); tn = int(N[:cut].sum())
            if tp + fn == 0:
                continue
            rec = tp / (tp + fn)
            pre = tp / (tp + fp) if (tp + fp) else float("nan")
            ratio = (fp / fn) if fn else float("inf")
            L.append(f"| `{t}` | {r} | {tp:,} | {fp:,} | {fn:,} | {ratio:.2f} | "
                     f"{rec:.4f} | {pre:.4f} |")
    L += ["", "CAUTION: one reference (C-CAP 2016) applied to a 2009 raster, at one",
          "threshold. Real 2009->2016 change lands in FP/FN too, and the reference's own",
          "errors are not modelled. Read the DIRECTION, not the magnitude.", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\n[conf] wrote {out}")


if __name__ == "__main__":
    main()

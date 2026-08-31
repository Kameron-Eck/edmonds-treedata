"""Spatial block-bootstrap confidence interval on the GAP between two arms.

WHY THIS EXISTS (2026-08-29). Every arm comparison in this project is quoted as a
point estimate — "Node C beats Node B by AUROC +.0116" — against a retrain noise
floor measured by training the same recipe twice. That covers only ONE of the two
uncertainties in the claim:

  retrain noise    : if I trained again, how far would the number move?
                     (measured by repeat runs; needs a GPU)
  EVALUATION noise : given these two FIXED rasters, how sure am I that this arm
                     really ranks better on this reference?  (THIS TOOL, free)

The second has never been measured here, and the naive answer — "198.8 million
pixels, so the standard error is tiny" — is wrong. Canopy is massively spatially
correlated: neighbouring pixels are the same tree. The effective sample size is
closer to the number of independent PATCHES than the number of pixels, and the
honest unit of resampling is a spatial block, not a pixel.

HOW. phase4_arm_pr_curves computes AUROC/AP exactly from 256-bin DN histograms of
reference-canopy and non-canopy pixels. Histograms ADD, so accumulating them
PER BLOCK and then resampling blocks with replacement gives an EXACT block
bootstrap — no pixel subsampling, no approximation, ~4 KB of state per block per
arm. The curve maths itself is imported from that script rather than copied, so
there is still one home for it.

PAIRED BY CONSTRUCTION: every replicate scores all arms on the SAME resampled
blocks, so the interval is on the DIFFERENCE and the shared ground cancels. That
is the quantity the verdict rests on.

--split-mask: DID IT GENERALISE, OR DID IT MEMORISE?  (added 2026-08-29)
An arm trained on ADDED labels must be asked where its gain actually lives. Pass
the overlay that says where labels were added and the gap is reported separately
INSIDE that region and OUTSIDE it. Gain only inside is close to tautological —
we told the model the answer there, so citywide would need labels citywide. Gain
that survives OUTSIDE is the model having learned something transferable, which
is the result that scales. --split-buffer dilates the inside region so that
spillover into neighbouring pixels is charged to "inside" rather than being
mistaken for generalisation.

WHAT IT DOES NOT TELL YOU. This is uncertainty from where we happened to LOOK,
under one reference and one trained pair of models. It does not include retrain
noise, reference error, or the circularity caveats. A gap that clears this
interval is not thereby "real" — it is "not explained by spatial sampling".

Run:
  py -3.12 qc/phase4_arm_bootstrap_ci.py --year 2009 \
      --tags rgb3_nodeb,nodec_v1 \
      --ref D:/edmonds-pipeline/Imagery/ccap_2016_hires_lc_snohfull.tif \
      --split-mask "G:/My Drive/treedata/phase4/labels_corrected/add_nodec_2009.tif"
"""
import argparse
import contextlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from phase4seg.names import clean_argv  # noqa: E402

HERE = Path(__file__).resolve().parent


def _load_arm_pr():
    """Import the scorer of record so AUROC/AP come from the SAME code that
    produced every published arm table — never a second implementation."""
    spec = importlib.util.spec_from_file_location(
        "_arm_pr", HERE / "phase4_arm_pr_curves.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # safe: __main__-guarded
    return mod


AP = _load_arm_pr()
QI = AP.QI
MASKS = AP.MASKS


def _box_any(a, r, axis):
    """True where any input pixel lies within r along `axis` — a 1-D box test done
    with a running sum, so cost does NOT grow with r."""
    n = a.shape[axis]
    c = np.cumsum(a, axis=axis, dtype=np.int32)
    hi = np.clip(np.arange(n) + r, 0, n - 1)
    lo = np.arange(n) - r - 1
    top = np.take(c, hi, axis=axis)
    bot = np.take(c, np.clip(lo, 0, n - 1), axis=axis)
    shape = [1] * a.ndim
    shape[axis] = n
    bot = np.where((lo < 0).reshape(shape), 0, bot)
    return (top - bot) > 0


def _dilate(mask, r):
    """Grow a boolean mask by r pixels, as two separable 1-D box tests.

    Rectangular dilation is separable, and a box test via running sums is O(n)
    regardless of r. That matters here: the honest buffer for this pipeline is a
    FULL TRAINING TILE (512 px), and a maximum_filter with a 1025-wide footprint
    at that size is prohibitively slow on a 76 Mpx strip.
    """
    if r <= 0:
        return mask
    return _box_any(_box_any(mask.astype(np.int32), r, 1).astype(np.int32), r, 0)


def main():
    ap = argparse.ArgumentParser(
        description="Spatial block-bootstrap CI on the gap between arms.")
    ap.add_argument("--year", default="2009")
    ap.add_argument("--tags", required=True,
                    help="comma-separated; the FIRST is the baseline every gap is against")
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ref-scheme", default="ccap", choices=["ccap", "binary"])
    ap.add_argument("--ref-map", default=None)
    ap.add_argument("--block-rows", type=int, default=512,
                    help="block height in px; blocks are the RESAMPLING UNIT")
    ap.add_argument("--block-cols", type=int, default=2048,
                    help="block width in px; row-strips alone are too elongated "
                         "to act as independent spatial units")
    ap.add_argument("--split-mask", default=None,
                    help="raster whose NONZERO pixels mark where labels were added; "
                         "gaps are then reported inside vs outside that region")
    ap.add_argument("--split-buffer", type=int, default=0,
                    help="dilate the split mask by this many px, so spillover next to "
                         "an added label counts as INSIDE and is not mistaken for "
                         "generalisation")
    ap.add_argument("--reps", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--out-name", default=None)
    args = ap.parse_args(clean_argv())

    tags = [t.strip() for t in args.tags.split(",")]
    if len(tags) < 2:
        raise SystemExit("need at least two arms to have a gap")
    paths = []
    for t in tags:
        p = MASKS / (f"edmonds_canopy_prob_{args.year}" + (f"_{t}" if t else "") + ".tif")
        if not p.exists():
            raise SystemExit(f"missing prob raster: {p}")
        paths.append(p)

    names, canopy_order, _g, code_to_group = QI.load_ref_map(args.ref_scheme, args.ref_map)
    lut = QI.build_lut(names, code_to_group) if args.ref_scheme != "binary" else None
    defs = QI.canopy_definitions(canopy_order)
    primary_name, primary_groups = defs[1 if len(defs) >= 2 else 0]
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

    regions = ["all"] if not args.split_mask else ["all", "inside", "outside"]
    nR = len(regions)
    print(f"[boot] year={args.year} arms={tags}")
    print(f"[boot] canopy definition: {primary_name}")
    print(f"[boot] block = {args.block_rows}x{args.block_cols} px")
    if args.split_mask:
        print(f"[boot] split mask: {Path(args.split_mask).name}  buffer={args.split_buffer}px")

    # per-block DN histograms, shape (n_arms, n_regions, 2, 256):
    # [arm][region][0]=reference-canopy, [arm][region][1]=non-canopy.
    # Histograms add, which is what makes the bootstrap exact.
    blocks = []
    srcs = [rasterio.open(p) for p in paths]
    ref_src = rasterio.open(args.ref)
    ref_nodata = ref_src.nodata
    split_src = rasterio.open(args.split_mask) if args.split_mask else None
    try:
        # both VRTs go through ExitStack so each is properly entered AND closed —
        # a WarpedVRT used bare outside `with` is left un-exited on the error path
        with contextlib.ExitStack() as stack:
            ref_vrt = stack.enter_context(
                WarpedVRT(ref_src, crs=srcs[0].crs, transform=srcs[0].transform,
                          width=W, height=H, resampling=Resampling.nearest))
            split_vrt = (stack.enter_context(
                WarpedVRT(split_src, crs=srcs[0].crs, transform=srcs[0].transform,
                          width=W, height=H, resampling=Resampling.nearest))
                if split_src else None)
            n_strips = (H + args.block_rows - 1) // args.block_rows
            for si, row0 in enumerate(range(0, H, args.block_rows)):
                rows = min(args.block_rows, H - row0)
                win = Window(0, row0, W, rows)
                prs = [s.read(1, window=win) for s in srcs]
                rc = ref_vrt.read(1, window=win)

                if args.ref_scheme == "binary":
                    gid = np.full(rc.shape, names.index("other"), dtype=np.int16)
                    gid[rc > 0] = names.index("canopy")
                    if ref_nodata is not None:
                        gid[rc == ref_nodata] = ignore_id
                else:
                    gid = lut[np.clip(rc.astype(np.int64), 0, 255)]
                    if ref_nodata is not None and 0 <= int(ref_nodata) < 256:
                        gid[rc == ref_nodata] = ignore_id

                valid = gid != ignore_id
                for pr in prs:
                    valid &= (pr != 255)          # intersection of all arms
                if not valid.any():
                    if si % 20 == 0 or si == n_strips - 1:
                        print(f"    strip {si+1}/{n_strips}", flush=True)
                    continue
                prim = valid & np.isin(gid, prim_ids)
                other = valid & ~prim

                if split_vrt is not None:
                    ins = split_vrt.read(1, window=win) != 0
                    # dilation is truncated at strip edges; with 512-row strips and a
                    # buffer of tens of px that touches a small fraction of the border
                    ins = _dilate(ins, args.split_buffer)
                else:
                    ins = None

                for col0 in range(0, W, args.block_cols):
                    c1 = min(col0 + args.block_cols, W)
                    bp = prim[:, col0:c1]
                    bo = other[:, col0:c1]
                    if not (bp.any() or bo.any()):
                        continue
                    if ins is not None:
                        bi = ins[:, col0:c1]
                        sel = [(bp, bo), (bp & bi, bo & bi), (bp & ~bi, bo & ~bi)]
                    else:
                        sel = [(bp, bo)]
                    hist = np.zeros((len(tags), nR, 2, 256), dtype=np.int64)
                    for ai, pr in enumerate(prs):
                        sub = pr[:, col0:c1]
                        for ri, (mp, mo) in enumerate(sel):
                            hist[ai, ri, 0] = np.bincount(sub[mp], minlength=256)
                            hist[ai, ri, 1] = np.bincount(sub[mo], minlength=256)
                    blocks.append(hist)

                if si % 20 == 0 or si == n_strips - 1:
                    print(f"    strip {si+1}/{n_strips}  blocks so far={len(blocks)}",
                          flush=True)
    finally:
        for s in srcs:
            s.close()
        ref_src.close()
        if split_src:
            split_src.close()

    if len(blocks) < 20:
        raise SystemExit(f"only {len(blocks)} non-empty blocks — too few to bootstrap; "
                         "shrink --block-rows/--block-cols")
    B = np.stack(blocks)                    # (n_blocks, n_arms, n_regions, 2, 256)
    nb = B.shape[0]
    tot = B.sum(axis=0)
    print(f"[boot] {nb} non-empty blocks")
    for ri, rn in enumerate(regions):
        print(f"    {rn:8s} {int(tot[0][ri][0].sum()):>14,} canopy px  "
              f"{int(tot[0][ri][1].sum()):>14,} non-canopy px")

    def score(h):                            # h: (2, 256)
        if h[0].sum() == 0 or h[1].sum() == 0:
            return float("nan"), float("nan")
        c = AP._curve_from_hists(h[0][:255], h[1][:255])
        return c["auroc"], c["ap"]

    point = {t: [score(tot[i][ri]) for ri in range(nR)] for i, t in enumerate(tags)}

    rng = np.random.default_rng(args.seed)
    reps = {t: [{"auroc": [], "ap": []} for _ in range(nR)] for t in tags}
    for r in range(args.reps):
        idx = rng.integers(0, nb, nb)        # SAME blocks for every arm -> paired
        s = B[idx].sum(axis=0)
        for i, t in enumerate(tags):
            for ri in range(nR):
                a, p = score(s[i][ri])
                reps[t][ri]["auroc"].append(a)
                reps[t][ri]["ap"].append(p)
        if (r + 1) % 50 == 0:
            print(f"    replicate {r+1}/{args.reps}", flush=True)

    base = tags[0]
    L = [f"# Block-bootstrap CI on arm gaps — {args.year}", "",
         f"Resampling unit: {args.block_rows}x{args.block_cols} px blocks · "
         f"**{nb} non-empty blocks** · {args.reps} replicates · "
         f"paired (same blocks per replicate)", "",
         "Effective sample size is the BLOCK count, not the pixel count — neighbouring",
         "pixels are the same tree. This interval covers uncertainty from WHERE WE",
         "LOOKED only: not retrain noise, not reference error.", ""]
    if args.split_mask:
        L += [f"Split mask: `{Path(args.split_mask).name}`, buffer {args.split_buffer} px. "
              f"**inside** = where labels were added (plus buffer); **outside** = the rest.",
              "A gain confined to *inside* is close to tautological — the model was told the",
              "answer there. A gain that survives *outside* is transferable, and is the only",
              "version of the result that scales beyond the labelled area.", ""]

    for ri, rn in enumerate(regions):
        L += [f"## Region: {rn}", "", "| arm | AUROC | PR-AUC |", "|---|---|---|"]
        for t in tags:
            a, p = point[t][ri]
            L.append(f"| `{t}` | {a:.4f} | {p:.4f} |")
        L += ["", f"Gaps vs `{base}` (95% percentile CI of the paired difference)", "",
              "| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |",
              "|---|---|---|---|---|---|---|"]
        for t in tags[1:]:
            row = [f"| `{t}` "]
            for k, j in (("auroc", 0), ("ap", 1)):
                d = np.array(reps[t][ri][k]) - np.array(reps[base][ri][k])
                d = d[~np.isnan(d)]
                pt = point[t][ri][j] - point[base][ri][j]
                if d.size == 0 or np.isnan(pt):
                    row.append("| n/a | n/a | n/a ")
                    continue
                lo, hi = np.percentile(d, [2.5, 97.5])
                stable = float((d > 0).mean()) if pt > 0 else float((d < 0).mean())
                row.append(f"| {pt:+.4f} | [{lo:+.4f}, {hi:+.4f}] | {stable*100:.1f}% ")
            L.append("".join(row) + "|")
        L.append("")

    L += ["`sign stable` = share of replicates where the gap kept the sign of the",
          "point estimate. Below ~95% the ordering is not established by this evidence.",
          "",
          "## READ THIS BEFORE QUOTING A CI THAT EXCLUDES ZERO", "",
          "A tight interval here proves the two RASTERS differ on this ground. It does",
          "NOT prove the two RECIPES differ, because retrain noise is not in it: train",
          "the same recipe twice and you get two different rasters, and this tool would",
          "call that gap significant too. Compare the gap against BOTH numbers — this",
          "interval AND the measured retrain spread for the branch — and quote the",
          "larger. A gap that clears spatial sampling but sits at the retrain scale is",
          "trajectory noise wearing a confidence interval.", ""]

    name = args.out_name or f"arm_bootstrap_ci_{args.year}.md"
    out = Path(args.out_dir) / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\n[boot] wrote {out}")


if __name__ == "__main__":
    main()

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

WHAT IT DOES NOT TELL YOU. This is uncertainty from where we happened to LOOK,
under one reference and one trained pair of models. It does not include retrain
noise, reference error, or the circularity caveats. A gap that clears this
interval is not thereby "real" — it is "not explained by spatial sampling".

Run:
  py -3.12 qc/phase4_arm_bootstrap_ci.py --year 2009 \
      --tags rgb3_nodeb,nodec_v1 \
      --ref D:/edmonds-pipeline/Imagery/ccap_2016_hires_lc_snohfull.tif
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
    ap.add_argument("--reps", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args([a for a in sys.argv[1:]
                          if not (a == "-f" or a.endswith(".json"))])

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

    print(f"[boot] year={args.year} arms={tags}")
    print(f"[boot] canopy definition: {primary_name}")
    print(f"[boot] block = {args.block_rows}x{args.block_cols} px")

    # per-block DN histograms, shape (n_arms, 2, 256): [arm][0]=reference-canopy,
    # [arm][1]=non-canopy. Histograms add, which is what makes the bootstrap exact.
    blocks = []
    srcs = [rasterio.open(p) for p in paths]
    ref_src = rasterio.open(args.ref)
    ref_nodata = ref_src.nodata
    try:
        with WarpedVRT(ref_src, crs=srcs[0].crs, transform=srcs[0].transform,
                       width=W, height=H, resampling=Resampling.nearest) as ref_vrt:
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

                for col0 in range(0, W, args.block_cols):
                    c1 = min(col0 + args.block_cols, W)
                    bp = prim[:, col0:c1]
                    bo = other[:, col0:c1]
                    if not (bp.any() or bo.any()):
                        continue
                    hist = np.zeros((len(tags), 2, 256), dtype=np.int64)
                    for ai, pr in enumerate(prs):
                        sub = pr[:, col0:c1]
                        hist[ai, 0] = np.bincount(sub[bp], minlength=256)
                        hist[ai, 1] = np.bincount(sub[bo], minlength=256)
                    blocks.append(hist)

                if si % 20 == 0 or si == n_strips - 1:
                    print(f"    strip {si+1}/{n_strips}  blocks so far={len(blocks)}",
                          flush=True)
    finally:
        for s in srcs:
            s.close()
        ref_src.close()

    if len(blocks) < 20:
        raise SystemExit(f"only {len(blocks)} non-empty blocks — too few to bootstrap; "
                         "shrink --block-rows/--block-cols")
    B = np.stack(blocks)                    # (n_blocks, n_arms, 2, 256)
    nb = B.shape[0]
    tot = B.sum(axis=0)
    print(f"[boot] {nb} non-empty blocks; "
          f"{int(tot[0][0].sum()):,} reference-canopy px, "
          f"{int(tot[0][1].sum()):,} non-canopy")

    def score(h):                            # h: (2, 256)
        c = AP._curve_from_hists(h[0][:255], h[1][:255])
        return c["auroc"], c["ap"]

    point = {t: score(tot[i]) for i, t in enumerate(tags)}

    rng = np.random.default_rng(args.seed)
    reps = {t: {"auroc": [], "ap": []} for t in tags}
    for r in range(args.reps):
        idx = rng.integers(0, nb, nb)        # SAME blocks for every arm -> paired
        s = B[idx].sum(axis=0)
        for i, t in enumerate(tags):
            a, p = score(s[i])
            reps[t]["auroc"].append(a)
            reps[t]["ap"].append(p)
        if (r + 1) % 50 == 0:
            print(f"    replicate {r+1}/{args.reps}", flush=True)

    base = tags[0]
    lines = [f"# Block-bootstrap CI on arm gaps — {args.year}", "",
             f"Resampling unit: {args.block_rows}x{args.block_cols} px blocks · "
             f"**{nb} non-empty blocks** · {args.reps} replicates · "
             f"paired (same blocks per replicate)", "",
             "Effective sample size is the BLOCK count, not the pixel count — neighbouring",
             "pixels are the same tree. This interval covers uncertainty from WHERE WE",
             "LOOKED only: not retrain noise, not reference error.", "",
             "## Point estimates", "",
             "| arm | AUROC | PR-AUC |", "|---|---|---|"]
    for t in tags:
        lines.append(f"| `{t}` | {point[t][0]:.4f} | {point[t][1]:.4f} |")
    lines += ["", f"## Gaps vs `{base}` (95% percentile CI of the paired difference)", "",
              "| arm | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | sign stable |",
              "|---|---|---|---|---|---|---|"]
    verdicts = []
    for t in tags[1:]:
        row = [f"| `{t}` "]
        for k, j in (("auroc", 0), ("ap", 1)):
            d = np.array(reps[t][k]) - np.array(reps[base][k])
            pt = point[t][j] - point[base][j]
            lo, hi = np.percentile(d, [2.5, 97.5])
            stable = float((d > 0).mean()) if pt > 0 else float((d < 0).mean())
            row.append(f"| {pt:+.4f} | [{lo:+.4f}, {hi:+.4f}] | {stable*100:.1f}% ")
            if k == "auroc":
                verdicts.append((t, pt, lo, hi, stable))
        lines.append("".join(row) + "|")
    lines += ["", "`sign stable` = share of replicates where the gap kept the sign of the",
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
    for t, pt, lo, hi, stable in verdicts:
        if lo > 0 or hi < 0:
            lines.append(f"- `{t}`: AUROC gap {pt:+.4f}, CI excludes zero — "
                         f"NOT explained by spatial sampling.")
        else:
            lines.append(f"- `{t}`: AUROC gap {pt:+.4f}, CI **includes zero** "
                         f"({stable*100:.1f}% sign-stable) — spatial sampling alone can "
                         f"produce this ordering. Do not report it as a win on this evidence.")

    out = Path(args.out_dir) / f"arm_bootstrap_ci_{args.year}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[boot] wrote {out}")


if __name__ == "__main__":
    main()

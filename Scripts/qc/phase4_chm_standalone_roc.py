r"""
from phase4seg.names import clean_argv  # noqa: E402
╔══════════════════════════════════════════════════════════════════╗
  THE CHEAP PRIOR — score the HEIGHT RASTERS THEMSELVES as standalone
  canopy classifiers, against C-CAP, with a stated power.
  Edmonds Temporal Active Learning Pipeline

  WHY THIS EXISTS (2026-08-29)
  ------------------------------------------------------------------
  A training A/B concluded that "fixing the inflated height raster buys
  nothing". An audit RETRACTED that conclusion twice over:

    * it was underpowered — a -.0057 AUROC gap read against a .0047
      same-recipe noise floor, judged against a baseline that was the MAX
      of three seeds, and
    * the per-source standardisation had already DELETED most of the
      treatment: the two rasters' HS_STATS means differ by exactly the
      4.43 m inflation under test, so z_chm = 0.869 * z_chm2 — a scalar
      gain a zero-initialised conv-1 channel absorbs for free.

  The supported statement was "undetermined", not "no difference". This
  script exists so the question is not re-answered by another ~6 A100-hours
  of arms that cannot resolve the effect they are looking for.

  WHAT IT DOES
  ------------------------------------------------------------------
  Every height product here shares ONE uint8 encoding —
      DN = 1 + round(clip(h_m, 0, 50.6) / 0.2),  0 = nodata
  (stated in the header of each of fetch_build_chm.py, build_chm2_2016.py and
  build_chm2005.py) — so a
  height raster IS already a 254-level canopy score, and sweeping the cut over
  every DN enumerates every "canopy is taller than h metres" classifier there
  is. One pass over the COMMON valid footprint (intersection of every raster
  compared x scorable reference) accumulates per-block DN histograms split by
  reference class; from those, EXACTLY:

    * AUROC / PR-AUC per raster, threshold-free
    * recall / precision / F1 / Youden J at every height, in METRES
    * a PAIRED spatial block bootstrap -> a 95% CI on every pairwise gap

  THE POWER REQUIREMENT — THE WHOLE POINT
  ------------------------------------------------------------------
  The failure being remediated is a confident null. So this script states its
  own resolving power BEFORE any verdict, and its verdict vocabulary is
  {BETTER, WORSE, UNDETERMINED}: a gap smaller than its own confidence
  interval is reported UNDETERMINED. The words "no difference" are not
  available to it.

  WHAT A CONSTANT OFFSET CAN AND CANNOT DO (read before using --offset)
  ------------------------------------------------------------------
  AUROC and PR-AUC are invariant under any strictly monotone transform of the
  score. Subtracting a constant from a height raster is monotone. Therefore
  the CONSTANT component of the ground inflation CANNOT change AUROC by
  construction — it can only move the height at which the best operating
  point sits. Run --offset anyway: it turns that algebra into a measurement
  (the best-F1 height should slide by ~the offset while AUROC stays put), and
  any deviation beyond the DN-1 floor clamp is a bug in this pipeline. What is
  left of an old-vs-new gap after that is RANK-ORDER (shape) difference — real
  discrimination — which is the decomposition the training A/B could not see.

  WHAT THIS TEST LICENSES, AND WHAT IT DOES NOT
  ------------------------------------------------------------------
  It measures MARGINAL discrimination: how well each raster separates canopy
  from non-canopy ON ITS OWN. A raster that wins here is strictly more
  informative about canopy. But a raster that does NOT win here is not thereby
  useless to training: a 4th channel is judged CONDITIONALLY on RGB, and a
  weaker marginal discriminator can still carry information RGB lacks. So:

      a positive result here is a green light,
      a null here is NOT a proof that training cannot benefit.

  Shipping the second as if it were the first is exactly the error being
  remediated. The script says so in its own output.

  USAGE
    py -3.12 qc/phase4_chm_standalone_roc.py --tag chm_vs_chm2 \
        --rasters "chm=D:\edmonds-pipeline\Imagery\lidar_snoh_chm.tif,chm2=D:\edmonds-pipeline\Imagery\lidar_chm2_2016_50cm.tif" \
        --offset "chm=-4.43"

    --rasters      name=path pairs, comma separated (paths may not contain ',')
    --offset       name=metres -> a DERIVED arm, base shifted then clamped to DN 1..254
    --fuse-max     a,b        -> a DERIVED arm, per-pixel max(a, b)
    --grid-res     analysis grid metres (default 1.0 = the C-CAP reference's own)
    --block-rows/--block-cols   bootstrap resampling unit, in grid px
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import contextlib
import csv
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.windows import Window

HERE = Path(__file__).resolve().parent


def _load(modname, filename):
    """Import a sibling QC script as a module so its maths is the SAME OBJECT
    the scorers of record use, never a second implementation."""
    spec = importlib.util.spec_from_file_location(modname, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # safe: those scripts are __main__-guarded
    return mod


AP = _load("_arm_pr", "phase4_arm_pr_curves.py")   # _curve_from_hists
QI = AP.QI                                          # the reference LUT of record

# ── the ONE height encoding shared by all three products ──────────────────────
M_PER_DN = 0.2
DN_MAX = 254
CAP_M = (DN_MAX - 1) * M_PER_DN          # 50.6 m

DEFAULT_RASTERS = {
    "chm":     "lidar_snoh_chm.tif",
    "chm2":    "lidar_chm2_2016_50cm.tif",
    "chm2005": "lidar_chm2005_2m.tif",
}
MIRROR = Path(r"D:\edmonds-pipeline\Imagery")
LAKE = Path(r"G:\My Drive\treedata\Full_Image\Pipeline Imagery")

HEIGHT_ROWS_M = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]

VERDICT_BETTER = "BETTER"
VERDICT_WORSE = "WORSE"
VERDICT_UNDET = "UNDETERMINED"


def dn_to_m(dn):
    return (np.asarray(dn, dtype=np.float64) - 1.0) * M_PER_DN


def m_to_dn(m):
    return int(np.clip(1 + round(float(m) / M_PER_DN), 1, DN_MAX))


def resolve_default(name):
    for root in (MIRROR, LAKE):
        p = root / DEFAULT_RASTERS[name]
        if p.exists():
            return p
    raise SystemExit(f"cannot find {DEFAULT_RASTERS[name]} in {MIRROR} or {LAKE}")


def parse_rasters(spec):
    if not spec:
        return {k: resolve_default(k) for k in DEFAULT_RASTERS}
    out = {}
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"--rasters entry must be name=path: {item!r}")
        name, path = item.split("=", 1)
        name = name.strip()
        p = Path(path.strip())
        if not p.exists():
            p2 = resolve_default(name) if name in DEFAULT_RASTERS else None
            if p2 is None:
                raise SystemExit(f"raster not found: {p}")
            p = p2
        out[name] = p
    if not out:
        raise SystemExit("--rasters resolved to nothing")
    return out


def build_grid(paths, ref_path, res):
    """Analysis grid: the INTERSECTION of every raster's footprint with the
    reference's, on the reference's CRS and snapped to its lattice, so the
    reference is resampled by an identity nearest-neighbour lookup at res=1."""
    with rasterio.open(ref_path) as r:
        ref_crs = r.crs
        rtf = r.transform
        rb = r.bounds
    box = (rb.left, rb.bottom, rb.right, rb.top)
    for p in paths:
        with rasterio.open(p) as s:
            bb = transform_bounds(s.crs, ref_crs, *s.bounds, densify_pts=21)
        box = (max(box[0], bb[0]), max(box[1], bb[1]),
               min(box[2], bb[2]), min(box[3], bb[3]))
    if box[2] <= box[0] or box[3] <= box[1]:
        raise SystemExit(f"rasters do not overlap in {ref_crs}: {box}")
    x0 = rtf.c + math.floor((box[0] - rtf.c) / res) * res
    y0 = rtf.f - math.floor((rtf.f - box[3]) / res) * res
    W = int(math.floor((box[2] - x0) / res))
    H = int(math.floor((y0 - box[1]) / res))
    if W <= 0 or H <= 0:
        raise SystemExit(f"degenerate analysis grid: {W}x{H}")
    return ref_crs, Affine(res, 0.0, x0, 0.0, -res, y0), W, H, box


def apply_offset(dn, metres):
    """Shift a DN raster by `metres` and re-clamp to the encoding's own range.

    The clamp is the ONLY reason this is not a pure monotone transform: DN 1 is
    the floor (h = 0 m), so a negative offset collapses everything below the
    shift into a tie at DN 1. That tie is the sole mechanism by which an offset
    can move AUROC at all, and it can only ever LOWER it (ties destroy ordering
    information, never create it)."""
    shift = int(round(metres / M_PER_DN))
    out = np.zeros_like(dn)
    v = dn != 0
    out[v] = np.clip(dn[v].astype(np.int32) + shift, 1, DN_MAX).astype(np.uint8)
    return out


def fuse_max(a, b):
    """Per-pixel tallest-of-two. Valid only where BOTH are valid, so this arm
    never gets credit for coverage the others do not have."""
    out = np.zeros_like(a)
    v = (a != 0) & (b != 0)
    out[v] = np.maximum(a[v], b[v])
    return out


def max_filter_dn(dn, r):
    """Neighbourhood maximum over a (2r+1)^2 window — the CONFOUND TEST.

    `lidar_snoh_chm.tif` is USGS 3DEP HAG at ~2 m GSD BILINEAR-UPSAMPLED onto a
    0.67 m ground grid (fetch_build_chm.py's header, and its main()), and
    build_chm2_2016.py
    measured the consequence: it reports a NEIGHBOURHOOD MAXIMUM rather than the
    height at the cell, +4.1 to +5.4 m nearly everywhere. A neighbourhood
    maximum is a DILATED canopy — it spreads crown height into the gaps between
    crowns. The reference is 1 m C-CAP, which labels a forest patch wall to
    wall, gaps included. So a blurrier height field can score BETTER against it
    without carrying more information, purely by matching the reference's
    granularity.

    Applying the same dilation to a sharp raster separates the two: if the sharp
    raster catches up under this filter, the gap was support, not information.
    Validity is the SOURCE's — this never invents coverage, and nodata (DN 0) is
    the encoding's minimum so it can never win a maximum."""
    if r <= 0:
        return dn.copy()
    from scipy import ndimage          # lazy: only this arm needs scipy
    m = ndimage.maximum_filter(dn, size=2 * r + 1, mode="nearest")
    out = np.zeros_like(dn)
    v = dn != 0
    out[v] = m[v]
    return out


def smooth_dn(dn, r):
    """Valid-normalised box mean over a (2r+1)^2 window — the second half of the
    old product's mechanism.

    A hard maximum filter is a PESSIMISTIC model of `lidar_snoh_chm.tif`: it
    creates plateaus, and plateaus are ties, and AUROC charges ties at 0.5. The
    real raster is ~2 m HAG BILINEAR-upsampled, which produces a smoothly graded
    field — dilated AND continuous. Chaining maxN then smoothM reproduces both
    halves, so the residual after it is the honest estimate of how much of the
    old raster's lead is information rather than form. Nodata is excluded from
    the mean rather than counted as zero, so edges are not dragged down."""
    if r <= 0:
        return dn.copy()
    from scipy import ndimage
    v = dn != 0
    k = 2 * r + 1
    s = ndimage.uniform_filter(np.where(v, dn, 0).astype(np.float32),
                               size=k, mode="nearest")
    c = ndimage.uniform_filter(v.astype(np.float32), size=k, mode="nearest")
    out = np.zeros_like(dn)
    good = v & (c > 0)
    out[good] = np.clip(np.rint(s[good] / c[good]), 1, DN_MAX).astype(np.uint8)
    return out


def arm_metrics(pos, neg):
    """Everything derivable from one arm's two DN histograms."""
    c = AP._curve_from_hists(pos[:255], neg[:255])
    rec, prec, fpr = c["recall"], c["precision"], c["fpr"]
    with np.errstate(invalid="ignore"):
        f1 = np.where(np.isfinite(prec) & (prec + rec > 0),
                      2 * prec * rec / (prec + rec), np.nan)
    d = np.arange(len(rec))
    live = d >= 1                        # DN 0 is nodata, never a threshold
    f1m = np.where(live, np.nan_to_num(f1, nan=-1.0), -1.0)
    jm = np.where(live, rec - fpr, -1.0)
    bf, bj = int(np.argmax(f1m)), int(np.argmax(jm))
    c.update(f1=f1, best_f1_dn=bf, best_f1=float(f1m[bf]),
             best_j_dn=bj, best_j=float(jm[bj]))
    return c


def _fmt(x, n=4):
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{n}f}"


def main():
    ap = argparse.ArgumentParser(
        description="Standalone canopy discrimination of the height rasters, "
                    "with a stated power.")
    ap.add_argument("--rasters", default=None,
                    help="name=path,... (default: chm, chm2, chm2005 from the mirror)")
    ap.add_argument("--offset", default=None,
                    help="name=metres,... -> derived shifted arms")
    ap.add_argument("--fuse-max", default=None,
                    help="a,b -> a derived per-pixel max(a,b) arm")
    ap.add_argument("--maxfilter", default=None,
                    help="name=radius_px,... -> derived neighbourhood-maximum arms; "
                         "the support/dilation confound test (see max_filter_dn)")
    ap.add_argument("--smooth", default=None,
                    help="name=radius_px,... -> derived box-mean arms. May name an "
                         "arm declared EARLIER (including a maxN one), so "
                         "'--maxfilter chm2=2 --smooth max2(chm2)=2' reproduces both "
                         "halves of the old product's dilate-and-blur mechanism.")
    ap.add_argument("--shift", default=None,
                    help="name=dx,dy;... (metres, ';'-separated) -> arms read from a "
                         "TRANSLATED window of the same file. A dilation test cannot "
                         "tell 'the reference is blobbier than the raster' from 'the "
                         "reference is offset from the raster' — a max filter hides "
                         "both. If AUROC peaks at a NONZERO shift, the reference sits "
                         "that far from the lidar and the sharp raster is being charged "
                         "for a registration error. Sampled at (x+dx, y+dy), so the "
                         "peak's (dx,dy) IS the reference's offset from the lidar.")
    ap.add_argument("--ref", default=r"D:\edmonds-pipeline\Imagery\ccap_2016_hires_lc_snohfull.tif")
    ap.add_argument("--ref-scheme", default="ccap", choices=["ccap", "binary"])
    ap.add_argument("--ref-map", default=None)
    ap.add_argument("--ref-epoch", default="2016",
                    help="the reference's acquisition epoch, for the epoch-mismatch caveat")
    ap.add_argument("--epoch", default="chm=2016,chm2=2016,chm2005=2005",
                    help="name=year,... — arms whose epoch differs from the reference "
                         "get their verdicts flagged as epoch-handicapped")
    ap.add_argument("--grid-res", type=float, default=1.0)
    ap.add_argument("--strip-rows", type=int, default=2048,
                    help="I/O strip height in grid px (not the bootstrap unit)")
    ap.add_argument("--block-rows", type=int, default=512)
    ap.add_argument("--block-cols", type=int, default=512)
    ap.add_argument("--reps", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tag", default="chm")
    ap.add_argument("--out-dir", default=r"D:\edmonds-pipeline\treedata\phase4\qc")
    args = ap.parse_args(clean_argv())

    if args.strip_rows % args.block_rows:
        raise SystemExit("--strip-rows must be a multiple of --block-rows so that "
                         "bootstrap blocks are never split across strips")

    base = parse_rasters(args.rasters)
    base_names = list(base)

    shifts = []                      # (name, base_name, dx_m, dy_m)
    if args.shift:
        for item in args.shift.split(";"):
            item = item.strip()
            if not item:
                continue
            nm, val = item.split("=", 1)
            nm = nm.strip()
            if nm not in base:
                raise SystemExit(f"--shift names an unknown raster: {nm}")
            dxs, dys = val.split(",")
            dx, dy = float(dxs), float(dys)
            shifts.append((f"{nm}@{dx:+g}E{dy:+g}N", nm, dx, dy))
    shift_names = [s[0] for s in shifts]

    derived = []                     # (name, kind, spec)
    if args.offset:
        for item in args.offset.split(","):
            item = item.strip()
            if not item:
                continue
            nm, val = item.split("=", 1)
            nm = nm.strip()
            if nm not in base:
                raise SystemExit(f"--offset names an unknown raster: {nm}")
            off = float(val)
            derived.append((f"{nm}{off:+.2f}m", "offset", (nm, off)))
    if args.maxfilter:
        for item in args.maxfilter.split(","):
            item = item.strip()
            if not item:
                continue
            nm, val = item.split("=", 1)
            nm = nm.strip()
            if nm not in base:
                raise SystemExit(f"--maxfilter names an unknown raster: {nm}")
            rad = int(val)
            derived.append((f"max{rad}({nm})", "maxfilter", (nm, rad)))
    if args.smooth:
        for item in args.smooth.split(","):
            item = item.strip()
            if not item:
                continue
            nm, val = item.split("=", 1)
            nm = nm.strip()
            # may reference an arm declared earlier — cur[] is filled in order
            known = set(base) | set(shift_names) | {d[0] for d in derived}
            if nm not in known:
                raise SystemExit(f"--smooth names an arm not declared before it: {nm}")
            rad = int(val)
            derived.append((f"smooth{rad}({nm})", "smooth", (nm, rad)))
    if args.fuse_max:
        parts = [p.strip() for p in args.fuse_max.split(",") if p.strip()]
        if len(parts) != 2:
            raise SystemExit("--fuse-max takes exactly two arm names")
        for p in parts:
            if p not in base:
                raise SystemExit(f"--fuse-max names an unknown raster: {p}")
        derived.append((f"max({parts[0]},{parts[1]})", "fusemax", tuple(parts)))

    arms = base_names + shift_names + [d[0] for d in derived]
    nA = len(arms)
    if nA < 2:
        raise SystemExit("need at least two arms to have a gap")

    epoch = {}
    for item in (args.epoch or "").split(","):
        item = item.strip()
        if item and "=" in item:
            k, v = item.split("=", 1)
            epoch[k.strip()] = v.strip()

    names, canopy_order, _grass, code_to_group = QI.load_ref_map(
        args.ref_scheme, args.ref_map)
    lut = QI.build_lut(names, code_to_group) if args.ref_scheme != "binary" else None
    defs = QI.canopy_definitions(canopy_order)
    primary_name, primary_groups = defs[1 if len(defs) >= 2 else 0]
    ignore_id = names.index("ignore")
    prim_ids = [names.index(g) for g in primary_groups]

    ref_crs, tf, W, H, box = build_grid(list(base.values()), args.ref, args.grid_res)
    print(f"[chm-roc] tag={args.tag}  arms={arms}")
    print(f"[chm-roc] canopy definition: {primary_name}")
    print(f"[chm-roc] grid {W}x{H} @ {args.grid_res} m in {ref_crs} "
          f"({W*H/1e6:.1f} Mpx)")

    # per-block DN histograms: (n_arms, 2, 256); [arm][0]=ref-canopy, [1]=non-canopy
    blocks = []
    own_valid = np.zeros(nA, dtype=np.int64)     # arm valid & reference scorable
    own_grid = np.zeros(nA, dtype=np.int64)      # arm valid anywhere on the grid
    dn1 = np.zeros(nA, dtype=np.int64)           # DN 1 mass inside the intersection
    ref_scorable = 0
    common = 0

    srcs = {n: rasterio.open(p) for n, p in base.items()}
    ref_src = rasterio.open(args.ref)
    ref_nodata = ref_src.nodata
    try:
        with contextlib.ExitStack() as stack:
            vrts = {n: stack.enter_context(
                        WarpedVRT(s, crs=ref_crs, transform=tf, width=W, height=H,
                                  resampling=Resampling.nearest))
                    for n, s in srcs.items()}
            # a shifted arm is the SAME file read through a translated window —
            # no roll, no edge wrap, no strip-boundary artefact
            for snm, bnm, sdx, sdy in shifts:
                stf = Affine(tf.a, tf.b, tf.c + sdx, tf.d, tf.e, tf.f + sdy)
                vrts[snm] = stack.enter_context(
                    WarpedVRT(srcs[bnm], crs=ref_crs, transform=stf,
                              width=W, height=H, resampling=Resampling.nearest))
            ref_vrt = stack.enter_context(
                WarpedVRT(ref_src, crs=ref_crs, transform=tf, width=W, height=H,
                          resampling=Resampling.nearest))
            n_strips = (H + args.strip_rows - 1) // args.strip_rows
            for si, row0 in enumerate(range(0, H, args.strip_rows)):
                rows = min(args.strip_rows, H - row0)
                win = Window(0, row0, W, rows)

                cur = {n: v.read(1, window=win) for n, v in vrts.items()}
                for nm, kind, spec in derived:
                    if kind == "offset":
                        cur[nm] = apply_offset(cur[spec[0]], spec[1])
                    elif kind == "maxfilter":
                        cur[nm] = max_filter_dn(cur[spec[0]], spec[1])
                    elif kind == "smooth":
                        cur[nm] = smooth_dn(cur[spec[0]], spec[1])
                    else:
                        cur[nm] = fuse_max(cur[spec[0]], cur[spec[1]])
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

                scorable = gid != ignore_id
                ref_scorable += int(scorable.sum())
                valid = scorable.copy()
                for ai, a in enumerate(arms):
                    nz = cur[a] != 0
                    own_grid[ai] += int(nz.sum())
                    own_valid[ai] += int((nz & scorable).sum())
                    valid &= nz

                if not valid.any():
                    print(f"    strip {si+1}/{n_strips}  (empty)", flush=True)
                    continue

                prim = valid & np.isin(gid, prim_ids)
                other = valid & ~prim
                common += int(valid.sum())
                for ai, a in enumerate(arms):
                    dn1[ai] += int((cur[a][valid] == 1).sum())

                for r0 in range(0, rows, args.block_rows):
                    r1 = min(r0 + args.block_rows, rows)
                    for c0 in range(0, W, args.block_cols):
                        c1 = min(c0 + args.block_cols, W)
                        bp = prim[r0:r1, c0:c1]
                        bo = other[r0:r1, c0:c1]
                        if not (bp.any() or bo.any()):
                            continue
                        hist = np.zeros((nA, 2, 256), dtype=np.int64)
                        for ai, a in enumerate(arms):
                            sub = cur[a][r0:r1, c0:c1]
                            hist[ai, 0] = np.bincount(sub[bp], minlength=256)
                            hist[ai, 1] = np.bincount(sub[bo], minlength=256)
                        blocks.append(hist)
                print(f"    strip {si+1}/{n_strips}  blocks={len(blocks)}", flush=True)
    finally:
        for s in srcs.values():
            s.close()
        ref_src.close()

    if common == 0:
        raise SystemExit("common valid footprint is EMPTY — nothing to compare.")
    if len(blocks) < 20:
        raise SystemExit(f"only {len(blocks)} non-empty blocks — too few to bootstrap; "
                         "shrink --block-rows/--block-cols")

    B = np.stack(blocks)                      # (n_blocks, n_arms, 2, 256)
    nb = B.shape[0]
    tot = B.sum(axis=0)
    point = {a: arm_metrics(tot[i][0], tot[i][1]) for i, a in enumerate(arms)}
    P = point[arms[0]]["P"]
    N = point[arms[0]]["N"]
    print(f"[chm-roc] {nb} blocks · common {common:,} px · "
          f"ref-canopy {P:,} · non-canopy {N:,}")

    # ── paired spatial block bootstrap ────────────────────────────────────────
    rng = np.random.default_rng(args.seed)
    rep_auroc = np.full((args.reps, nA), np.nan)
    rep_ap = np.full((args.reps, nA), np.nan)
    for r in range(args.reps):
        idx = rng.integers(0, nb, nb)          # SAME blocks for every arm -> paired
        s = B[idx].sum(axis=0)
        for ai in range(nA):
            if s[ai][0].sum() == 0 or s[ai][1].sum() == 0:
                continue
            c = AP._curve_from_hists(s[ai][0][:255], s[ai][1][:255])
            rep_auroc[r, ai] = c["auroc"]
            rep_ap[r, ai] = c["ap"]
        if (r + 1) % 100 == 0:
            print(f"    replicate {r+1}/{args.reps}", flush=True)

    # per-arm CI (for context only — the VERDICT uses the paired gap)
    arm_ci = {}
    for ai, a in enumerate(arms):
        d = rep_auroc[:, ai]
        d = d[np.isfinite(d)]
        arm_ci[a] = (float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))) \
            if d.size else (float("nan"), float("nan"))

    pairs = []
    for i in range(nA):
        for j in range(i + 1, nA):
            a, b = arms[i], arms[j]
            row = {"a": a, "b": b}
            for key, reps in (("auroc", rep_auroc), ("ap", rep_ap)):
                d = reps[:, i] - reps[:, j]
                d = d[np.isfinite(d)]
                pt = point[a][key] - point[b][key]
                if d.size == 0:
                    row.update({f"d_{key}": np.nan, f"lo_{key}": np.nan,
                                f"hi_{key}": np.nan, f"stable_{key}": np.nan,
                                f"half_{key}": np.nan})
                    continue
                lo, hi = (float(v) for v in np.percentile(d, [2.5, 97.5]))
                stable = float((d > 0).mean()) if pt > 0 else float((d < 0).mean())
                row.update({f"d_{key}": pt, f"lo_{key}": lo, f"hi_{key}": hi,
                            f"stable_{key}": stable, f"half_{key}": (hi - lo) / 2.0})
            # THE VERDICT RULE. A gap that does not clear its own interval is
            # UNDETERMINED — never "no difference". That distinction is the
            # entire reason this script exists.
            lo, hi, st = row["lo_auroc"], row["hi_auroc"], row["stable_auroc"]
            if not np.isfinite(lo):
                row["verdict"] = "n/a"
            elif lo > 0 and st >= 0.95:
                row["verdict"] = VERDICT_BETTER
            elif hi < 0 and st >= 0.95:
                row["verdict"] = VERDICT_WORSE
            else:
                row["verdict"] = VERDICT_UNDET
            ea, eb = epoch.get(a), epoch.get(b)
            row["epoch_flag"] = bool(
                (ea and ea != args.ref_epoch) or (eb and eb != args.ref_epoch))
            pairs.append(row)

    # ── report ────────────────────────────────────────────────────────────────
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    L = []
    A = L.append
    A(f"# Height rasters as STANDALONE canopy classifiers — `{args.tag}`\n")
    A("The cheap prior. No training, no GPU. Every height raster is already a "
      "254-level canopy score under the shared encoding "
      "`DN = 1 + round(clip(h,0,50.6)/0.2)`, `0 = nodata`, so sweeping the cut over "
      "every DN enumerates every *canopy is taller than h metres* classifier there is.\n")
    A(f"Reference: `{Path(args.ref).name}` (epoch {args.ref_epoch}) · canopy "
      f"definition `{primary_name}` · scored on the INTERSECTION of every raster "
      "below, so coverage is never charged as accuracy.\n")

    A("## Inputs\n")
    A("| arm | source | CRS | native res (m) | epoch |")
    A("|---|---|---|---|---|")
    for a in base_names:
        with rasterio.open(base[a]) as s:
            A(f"| `{a}` | `{base[a].name}` | {s.crs} | "
              f"{s.res[0]:.2f} x {s.res[1]:.2f} | {epoch.get(a, '?')} |")
    for snm, bnm, sdx, sdy in shifts:
        A(f"| `{snm}` | `{bnm}` sampled at (x{sdx:+g} m, y{sdy:+g} m) — "
          f"the registration test | — | — | {epoch.get(bnm, '—')} |")
    for nm, kind, spec in derived:
        if kind == "offset":
            what = (f"derived: `{spec[0]}` shifted {spec[1]:+.2f} m, "
                    "re-clamped to DN 1..254")
        elif kind == "maxfilter":
            what = (f"derived: `{spec[0]}` under a {2*spec[1]+1}x{2*spec[1]+1} px "
                    f"({(2*spec[1]+1)*args.grid_res:g} m) neighbourhood MAXIMUM — "
                    "the support/dilation confound test")
        elif kind == "smooth":
            what = (f"derived: `{spec[0]}` under a {2*spec[1]+1}x{2*spec[1]+1} px "
                    f"({(2*spec[1]+1)*args.grid_res:g} m) box MEAN — the second half "
                    "of the old product's dilate-and-blur mechanism")
        else:
            what = f"derived: per-pixel max(`{spec[0]}`, `{spec[1]}`)"
        A(f"| `{nm}` | {what} | — | — | {epoch.get(nm, '—')} |")
    A("")
    if shifts:
        A("A `@dxE dyN` arm is the same file sampled from a translated window. A "
          "dilation test alone cannot separate *the reference is blobbier than the "
          "raster* from *the reference is offset from the raster* — a neighbourhood "
          "maximum hides both. If AUROC peaks at a NONZERO shift, the reference sits "
          "that far from the lidar and every sharp raster is being charged for a "
          "registration error rather than for its own accuracy. If it peaks at zero, "
          "registration is excluded and granularity is left holding the result.\n")
    if any(k in ("maxfilter", "smooth") for _n, k, _s in derived):
        A("A `maxN(...)` arm exists to test ONE hypothesis: the old product is ~2 m "
          "HAG bilinear-upsampled and measurably behaves as a neighbourhood maximum "
          "(`build_chm2_2016.py` [2b]), while the reference labels forest patches wall "
          "to wall. If a SHARP raster catches up once it is dilated to the same "
          "support, the gap between them was granularity, not information — and "
          "granularity matched to a 1 m reference is not evidence about a channel the "
          "engine consumes at 10-15 cm. The filter is truncated at I/O strip "
          f"boundaries ({args.strip_rows} rows), which touches "
          f"~{200.0*max((s[1] if k in ('maxfilter', 'smooth') else 0) for _n, k, s in derived)/args.strip_rows:.2f}% "
          "of rows.\n")

    A("## Footprint and coverage\n")
    A(f"Analysis grid: **{W} x {H} @ {args.grid_res:g} m** in {ref_crs} "
      f"= {W*H/1e6:.1f} Mpx, the intersection of every raster's own extent with the "
      f"reference's, snapped to the reference lattice.\n")
    A(f"Reference-scorable on that grid: **{ref_scorable:,} px**. "
      f"Common valid (all arms x scorable): **{common:,} px** "
      f"({100.0*common/max(1, ref_scorable):.2f}% of scorable).\n")
    A("| arm | own valid / grid | own valid & ref-scorable | share of the common footprint "
      "it alone would add | DN 1 (h = 0 m) inside common |")
    A("|---|---|---|---|---|")
    for ai, a in enumerate(arms):
        A(f"| `{a}` | {100.0*own_grid[ai]/(W*H):.2f}% | {own_valid[ai]:,} | "
          f"{100.0*(own_valid[ai]-common)/max(1, own_valid[ai]):.2f}% dropped by the "
          f"intersection | {100.0*dn1[ai]/max(1, common):.2f}% |")
    A("")
    A("The DN-1 column is also an encoding check: DN 1 is *flat ground*, not nodata. "
      "An arm reporting ~0% there would mean its zero-height mass had been swallowed by "
      "the nodata code and every metre label below would be wrong.\n")

    A("## Standalone discrimination\n")
    A(f"Reference canopy px: {P:,} · non-canopy: {N:,} · "
      f"prevalence {100.0*P/max(1, P+N):.2f}%\n")
    A("| arm | AUROC | 95% CI (own) | PR-AUC | best-F1 height | F1 | best-Youden height | J |")
    A("|---|---|---|---|---|---|---|---|")
    for a in arms:
        c = point[a]
        lo, hi = arm_ci[a]
        A(f"| `{a}` | {c['auroc']:.4f} | [{lo:.4f}, {hi:.4f}] | {c['ap']:.4f} | "
          f"{dn_to_m(c['best_f1_dn']):.1f} m | {c['best_f1']:.4f} | "
          f"{dn_to_m(c['best_j_dn']):.1f} m | {c['best_j']:.4f} |")
    A("")

    A("## Performance by height threshold — where does each raster discriminate?\n")
    A("Recall / precision / F1 of the rule *canopy iff height >= h*.\n")
    A("| h (m) | " + " | ".join(f"`{a}` R/P/F1" for a in arms) + " |")
    A("|---" * (nA + 1) + "|")
    for h in HEIGHT_ROWS_M:
        d = m_to_dn(h)
        cells = []
        for a in arms:
            c = point[a]
            cells.append(f"{c['recall'][d]:.3f}/{_fmt(c['precision'][d], 3)}/"
                         f"{_fmt(c['f1'][d], 3)}")
        A(f"| {h:.1f} | " + " | ".join(cells) + " |")
    A("")

    # ── POWER, STATED BEFORE ANY VERDICT ──────────────────────────────────────
    A("## POWER OF THIS TEST — read before any verdict below\n")
    A(f"Paired spatial block bootstrap: **{nb} non-empty blocks** of "
      f"{args.block_rows} x {args.block_cols} px ({args.block_rows*args.grid_res:g} m "
      f"x {args.block_cols*args.grid_res:g} m) · {args.reps} replicates · every "
      "replicate scores every arm on the SAME resampled blocks, so the shared ground "
      "cancels and the interval is on the DIFFERENCE.\n")
    A("Effective sample size is the BLOCK count, not the pixel count — neighbouring "
      "pixels are the same tree. `resolving power` below is the half-width of the "
      "95% interval on the paired gap: **a difference smaller than that number is not "
      "measurable by this evaluation and is reported UNDETERMINED, not as absence of "
      "an effect.**\n")
    A("| pair | observed dAUROC | resolving power (+-) | measurable? |")
    A("|---|---|---|---|")
    for row in pairs:
        meas = "yes" if abs(row["d_auroc"]) > row["half_auroc"] else "**NO**"
        A(f"| `{row['a']}` vs `{row['b']}` | {row['d_auroc']:+.4f} | "
          f"{row['half_auroc']:.4f} | {meas} |")
    A("")

    A("## Verdicts\n")
    A("| pair | dAUROC | 95% CI | sign stable | dPR-AUC | 95% CI | verdict |")
    A("|---|---|---|---|---|---|---|")
    for row in pairs:
        v = row["verdict"]
        if v in (VERDICT_BETTER, VERDICT_WORSE):
            v = f"`{row['a']}` **{v}** than `{row['b']}`"
        if row["epoch_flag"]:
            v += " · epoch-handicapped"
        A(f"| `{row['a']}` vs `{row['b']}` | {row['d_auroc']:+.4f} | "
          f"[{row['lo_auroc']:+.4f}, {row['hi_auroc']:+.4f}] | "
          f"{100*row['stable_auroc']:.1f}% | {row['d_ap']:+.4f} | "
          f"[{row['lo_ap']:+.4f}, {row['hi_ap']:+.4f}] | {v} |")
    A("")
    A(f"`{VERDICT_UNDET}` means the gap is inside this test's own resolving power. "
      "It is **not** a null: this evaluation could not tell the two apart, which is a "
      "statement about the evidence, not about the rasters.\n")
    if any(r["epoch_flag"] for r in pairs):
        A(f"`epoch-handicapped`: an arm in that pair is from a different epoch than the "
          f"{args.ref_epoch} reference, so real canopy growth and removal between the two "
          "dates is charged to the raster as classification error. Its score is a LOWER "
          "BOUND on its discrimination in its own epoch — which is the epoch it would "
          "actually be used in.\n")

    A("## What this test licenses\n")
    A("* It measures MARGINAL discrimination — how well each raster separates canopy "
      "from non-canopy **on its own**. An arm that wins here is strictly more "
      "informative about canopy, and that is a green light.\n"
      "* It does **not** measure CONDITIONAL value. The height raster enters training as "
      "a 4th channel beside RGB; a weaker marginal discriminator can still carry "
      "information RGB lacks. A gap this test cannot resolve therefore does not license "
      "the claim that training cannot benefit.\n"
      "* AUROC and PR-AUC are invariant under any strictly monotone transform of the "
      "score, and subtracting a constant is monotone. **The constant component of a "
      "ground-height inflation cannot move AUROC by construction** — it moves only the "
      "height at which the best operating point sits. Any offset arm above therefore "
      "tests the machinery, and the surviving old-vs-new gap is RANK-ORDER difference: "
      "real discrimination, not level.\n"
      "* The reference is C-CAP: a 1 m classified product with its own errors, not hand "
      "truth. It cannot resolve crowns below its own cell, so every raster here is "
      "scored at C-CAP's information limit.\n")

    md = "\n".join(L) + "\n"
    md_path = out / f"chm_standalone_roc_{args.tag}.md"
    md_path.write_text(md, encoding="utf-8")

    with (out / f"chm_standalone_roc_{args.tag}_arms.csv").open(
            "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["arm", "auroc", "auroc_lo", "auroc_hi", "pr_auc",
                    "best_f1_height_m", "best_f1", "best_j_height_m", "best_j",
                    "own_valid_px", "common_px", "ref_canopy_px", "ref_noncanopy_px"])
        for a in arms:
            c = point[a]
            ai = arms.index(a)
            w.writerow([a, f"{c['auroc']:.6f}", f"{arm_ci[a][0]:.6f}",
                        f"{arm_ci[a][1]:.6f}", f"{c['ap']:.6f}",
                        f"{dn_to_m(c['best_f1_dn']):.1f}", f"{c['best_f1']:.6f}",
                        f"{dn_to_m(c['best_j_dn']):.1f}", f"{c['best_j']:.6f}",
                        int(own_valid[ai]), common, c["P"], c["N"]])

    with (out / f"chm_standalone_roc_{args.tag}_pairs.csv").open(
            "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["a", "b", "d_auroc", "ci_lo", "ci_hi", "resolving_power",
                    "sign_stable", "d_pr_auc", "verdict", "epoch_handicapped"])
        for row in pairs:
            w.writerow([row["a"], row["b"], f"{row['d_auroc']:+.6f}",
                        f"{row['lo_auroc']:+.6f}", f"{row['hi_auroc']:+.6f}",
                        f"{row['half_auroc']:.6f}", f"{row['stable_auroc']:.4f}",
                        f"{row['d_ap']:+.6f}", row["verdict"],
                        int(row["epoch_flag"])])

    print("\n" + md)
    print(f"[chm-roc] wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

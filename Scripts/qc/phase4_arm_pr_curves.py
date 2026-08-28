r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — QC: THRESHOLD-FREE comparison of several arms of one year

  WHY
    A single thresholded (recall, precision) pair only compares two models if
    they are calibrated alike. They often are not. The 2009 stable-groves
    experiment made that unmissable: both sparse-label arms came back saturated
    (VERIFY maxprob=1.000, p99.9=1.000, vs the projected-key baseline's
    0.878/0.791), and the lidar arm fell from recall .871 @0.45 to .391 @0.50 —
    a cliff, i.e. probability mass piled up right at the deployed cut. Scored at
    a fixed 0.5 those arms are not being compared to the baseline, they are
    being compared to an accident of where their mass landed.

    Method_Pipeline.md "Operating-point protocol" says it plainly: judge a MODEL
    on curve-level metrics; a threshold describes a PRODUCT. This script is that
    rule made runnable.

  WHAT IT DOES
    One pass over the arms' COMMON valid footprint (intersection — every number
    on identical ground), accumulating, per arm, a 256-bin histogram of the
    predicted DN split by reference class. Because the prob rasters are uint8,
    those two histograms determine the ENTIRE curve EXACTLY at all 255 possible
    thresholds — no sampling, no interpolation. From them:
      · full PR and ROC curves, AUROC, PR-AUC (average precision)
      · MATCHED operating points: each arm's recall where its precision equals a
        reference precision, and vice versa — the only honest way to say "better"
      · a calibration histogram, which is what exposes saturation

  CONVENTIONS ARE IMPORTED, NOT RESTATED
    The C-CAP class map, the canopy definitions, the 255-is-nodata rule and the
    DN/254 probability convention all come from phase4_qc_indep.py by import, so
    they cannot drift from the scorer of record.

  NOT A RE-SCORE. Writes no row to qc_indep_report.csv. Analysis only.

  USAGE
    py -3.12 qc/phase4_arm_pr_curves.py --year 2009 \
        --tags fullext_sectors_v1,groves_nolidar,groves_lidar \
        --ref D:\edmonds-pipeline\Imagery\ccap_2016_hires_lc_snohfull.tif
╚══════════════════════════════════════════════════════════════════╝
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


def _load_qc_indep():
    """Import phase4_qc_indep as a module so the class map / DN convention are
    the SAME OBJECTS the scorer of record uses, not a copy that can rot."""
    spec = importlib.util.spec_from_file_location(
        "_qc_indep", HERE / "phase4_qc_indep.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # safe: the script is __main__-guarded
    return mod


QI = _load_qc_indep()
MASKS = QI.MASKS


def _curve_from_hists(pos, neg):
    """Exact PR/ROC from DN histograms of positives and negatives.

    pos[d] / neg[d] = count of valid reference-canopy / non-canopy pixels whose
    predicted DN == d, for d in 0..254 (255 is nodata and never enters).

    A pixel is called canopy at threshold t when DN >= t*254, so sweeping the cut
    over every integer DN enumerates every distinct model decision there is.
    Returned arrays are ordered by DECREASING threshold (recall ascending).
    """
    P, N = pos.sum(), neg.sum()
    # suffix sums: tp[i] = pixels with DN >= i
    tp = np.cumsum(pos[::-1])[::-1].astype(np.float64)
    fp = np.cumsum(neg[::-1])[::-1].astype(np.float64)
    thr = np.arange(len(pos), dtype=np.float64) / 254.0

    recall = tp / P if P else np.zeros_like(tp)
    with np.errstate(divide="ignore", invalid="ignore"):
        precision = np.where(tp + fp > 0, tp / (tp + fp), np.nan)
    fpr = fp / N if N else np.zeros_like(fp)

    # Walk thresholds from HIGHEST DN down to 0. That order makes recall (and
    # FPR) monotonically non-decreasing by construction, which is what both
    # integrals below need. Do NOT argsort on recall instead: recall ties are
    # common here (saturated arms put huge mass in one bin) and argsort then
    # picks an arbitrary member of the tie — on a perfect separator that scored
    # AP 0.500 instead of 1.000, caught by the synthetic test.
    r_d, p_d, f_d = recall[::-1], precision[::-1], fpr[::-1]

    # AUROC — trapezoid over (FPR, TPR), anchored at both corners
    fx = np.concatenate(([0.0], f_d, [1.0]))
    ty = np.concatenate(([0.0], r_d, [1.0]))
    auroc = float(np.trapezoid(ty, fx))

    # PR-AUC as average precision: sum precision * d(recall), the step-wise form
    # that does not reward interpolating across a cliff.
    dr = np.diff(np.concatenate(([0.0], r_d)))
    ap = float(np.nansum(np.nan_to_num(p_d, nan=0.0) * dr))

    return dict(thr=thr, recall=recall, precision=precision, fpr=fpr,
                auroc=auroc, ap=ap, P=int(P), N=int(N))


def _at_precision(c, target):
    """Highest recall achievable at precision >= target (and the threshold)."""
    ok = np.isfinite(c["precision"]) & (c["precision"] >= target) & (c["recall"] > 0)
    if not ok.any():
        return None
    i = np.argmax(np.where(ok, c["recall"], -1.0))
    return float(c["recall"][i]), float(c["precision"][i]), float(c["thr"][i])


def _at_recall(c, target):
    """Best precision achievable at recall >= target (and the threshold)."""
    ok = c["recall"] >= target
    if not ok.any():
        return None
    prec = np.where(ok, np.nan_to_num(c["precision"], nan=-1.0), -1.0)
    i = int(np.argmax(prec))
    return float(c["recall"][i]), float(c["precision"][i]), float(c["thr"][i])


def main():
    ap = argparse.ArgumentParser(
        description="Threshold-free (PR/ROC) comparison of arms of one year.")
    ap.add_argument("--year", default="2009")
    ap.add_argument("--tags", default="fullext_sectors_v1,groves_nolidar,groves_lidar",
                    help="comma-separated run tags; '' means the untagged raster")
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ref-scheme", default="ccap", choices=["ccap", "binary"])
    ap.add_argument("--ref-map", default=None)
    ap.add_argument("--block-rows", type=int, default=512)
    ap.add_argument("--match-precision", type=float, default=None,
                    help="default: the FIRST arm's precision at 0.5")
    ap.add_argument("--match-recall", type=float, default=None,
                    help="default: the FIRST arm's recall at 0.5")
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args([a for a in sys.argv[1:]
                          if not (a == "-f" or a.endswith(".json"))])

    tags = [t.strip() for t in args.tags.split(",")]
    paths = []
    for t in tags:
        p = MASKS / (f"edmonds_canopy_prob_{args.year}"
                     + (f"_{t}" if t else "") + ".tif")
        if not p.exists():
            raise SystemExit(f"missing prob raster: {p}")
        paths.append(p)

    names, canopy_order, _grass, code_to_group = QI.load_ref_map(
        args.ref_scheme, args.ref_map)
    lut = QI.build_lut(names, code_to_group) if args.ref_scheme != "binary" else None
    defs = QI.canopy_definitions(canopy_order)
    primary_idx = 1 if len(defs) >= 2 else 0
    primary_name, primary_groups = defs[primary_idx]
    ignore_id = names.index("ignore")
    prim_ids = [names.index(g) for g in primary_groups]

    print(f"[arm-pr] year={args.year}  arms={tags}")
    print(f"[arm-pr] primary canopy definition: {primary_name}")

    # every arm must share one grid, or 'identical ground' is a lie
    metas = []
    for p in paths:
        with rasterio.open(p) as s:
            metas.append((s.width, s.height, s.crs.to_string(),
                          tuple(round(v, 6) for v in s.transform[:6])))
    if len(set(metas)) != 1:
        raise SystemExit("arms are NOT on a common grid; refusing to compare:\n  "
                         + "\n  ".join(map(str, metas)))
    W, H = metas[0][0], metas[0][1]

    pos = {t: np.zeros(256, dtype=np.int64) for t in tags}
    neg = {t: np.zeros(256, dtype=np.int64) for t in tags}
    allhist = {t: np.zeros(256, dtype=np.int64) for t in tags}
    common_valid = 0

    srcs = [rasterio.open(p) for p in paths]
    ref_src = rasterio.open(args.ref)
    ref_nodata = ref_src.nodata
    try:
        with WarpedVRT(ref_src, crs=srcs[0].crs, transform=srcs[0].transform,
                       width=W, height=H, resampling=Resampling.nearest) as ref_vrt:
            n_blocks = (H + args.block_rows - 1) // args.block_rows
            for bi, row0 in enumerate(range(0, H, args.block_rows)):
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
                for pr in prs:                      # INTERSECTION of all arms
                    valid &= (pr != 255)
                if not valid.any():
                    if bi % 20 == 0 or bi == n_blocks - 1:
                        print(f"    block {bi+1}/{n_blocks}", flush=True)
                    continue

                prim = valid & np.isin(gid, prim_ids)
                other = valid & ~prim
                common_valid += int(valid.sum())
                for t, pr in zip(tags, prs):
                    pos[t] += np.bincount(pr[prim], minlength=256)
                    neg[t] += np.bincount(pr[other], minlength=256)
                    allhist[t] += np.bincount(pr[valid], minlength=256)

                if bi % 20 == 0 or bi == n_blocks - 1:
                    print(f"    block {bi+1}/{n_blocks}", flush=True)
    finally:
        for s in srcs:
            s.close()
        ref_src.close()

    if common_valid == 0:
        raise SystemExit("common valid footprint is EMPTY — nothing to compare.")

    curves = {t: _curve_from_hists(pos[t][:255], neg[t][:255]) for t in tags}

    base = tags[0]
    b = curves[base]
    i50 = int(round(0.5 * 254))
    base_p50 = float(b["precision"][i50])
    base_r50 = float(b["recall"][i50])
    tgt_p = args.match_precision if args.match_precision is not None else base_p50
    tgt_r = args.match_recall if args.match_recall is not None else base_r50

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    L = []
    A = L.append
    A(f"# Arm comparison — {args.year}, threshold-free\n")
    A(f"Common valid footprint (intersection of all arms x scorable reference): "
      f"**{common_valid:,} px**")
    A(f"Reference canopy px (`{primary_name}`): {b['P']:,} · non-canopy: {b['N']:,}\n")
    A("## Curve metrics (threshold-free — the actual 'is it better' answer)\n")
    A("| arm | AUROC | PR-AUC (AP) | recall@0.5 | precision@0.5 |")
    A("|---|---|---|---|---|")
    for t in tags:
        c = curves[t]
        A(f"| `{t}` | {c['auroc']:.4f} | {c['ap']:.4f} | "
          f"{c['recall'][i50]:.4f} | {c['precision'][i50]:.4f} |")
    A("")
    A(f"## Matched operating points (vs `{base}` @0.5: "
      f"precision {tgt_p:.4f}, recall {tgt_r:.4f})\n")
    A(f"| arm | recall @ precision>={tgt_p:.4f} | thr | precision @ recall>={tgt_r:.4f} | thr |")
    A("|---|---|---|---|---|")
    for t in tags:
        mp = _at_precision(curves[t], tgt_p)
        mr = _at_recall(curves[t], tgt_r)
        A(f"| `{t}` | " +
          (f"{mp[0]:.4f} | {mp[2]:.4f} | " if mp else "unreachable | — | ") +
          (f"{mr[1]:.4f} | {mr[2]:.4f} |" if mr else "unreachable | — |"))
    A("")
    A("## Calibration (fraction of common-valid px)\n")
    A("| arm | p in [0,0.01] | p in [0.49,0.51] | p in [0.99,1.0] |")
    A("|---|---|---|---|")
    for t in tags:
        h = allhist[t][:255].astype(np.float64)
        tot = h.sum()
        lo = h[:int(0.01 * 254) + 1].sum() / tot
        mid = h[int(0.49 * 254):int(0.51 * 254) + 1].sum() / tot
        hi = h[int(0.99 * 254):].sum() / tot
        A(f"| `{t}` | {lo:.4f} | {mid:.4f} | {hi:.4f} |")
    A("")
    A("Noise floor for interpretation: recall sd .0100, precision sd .0052 "
      "(n=5, same seed — a LOWER bound).")
    md = "\n".join(L)
    (out / f"arm_pr_curves_{args.year}.md").write_text(md, encoding="utf-8")
    print("\n" + md)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(12, 5))
        for t in tags:
            c = curves[t]
            o = np.argsort(c["recall"])
            ax[0].plot(c["recall"][o], c["precision"][o], label=f"{t} (AP {c['ap']:.3f})")
            k = np.argsort(c["fpr"])
            ax[1].plot(c["fpr"][k], c["recall"][k], label=f"{t} (AUROC {c['auroc']:.3f})")
            ax[0].plot(c["recall"][i50], c["precision"][i50], "o", ms=6)
        ax[0].set_xlabel("recall"); ax[0].set_ylabel("precision")
        ax[0].set_title(f"{args.year} PR (dots = the deployed 0.5)")
        ax[1].plot([0, 1], [0, 1], "k--", lw=0.6)
        ax[1].set_xlabel("false-positive rate"); ax[1].set_ylabel("recall")
        ax[1].set_title(f"{args.year} ROC")
        for a in ax:
            a.legend(fontsize=8); a.grid(alpha=.3)
        fig.tight_layout()
        fig.savefig(out / f"arm_pr_curves_{args.year}.png", dpi=130)
        print(f"\n[arm-pr] plot -> {out / f'arm_pr_curves_{args.year}.png'}")
    except Exception as e:                              # noqa: BLE001
        print(f"[arm-pr] plot skipped: {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

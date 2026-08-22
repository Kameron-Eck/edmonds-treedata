"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — REFERENCE DISAGREEMENT MAP   (honest-measurement-overhaul, P2)
  Edmonds Temporal Active Learning Pipeline

  WHY THIS EXISTS
  ---------------
  Every headline number in this project is scored against a PROXY:
    • C-CAP        — NOAA 1 m generalized land cover, 2016/2021 vintages
    • NDVI+CHM ref — built from this project's own imagery (NIR years only),
                     with a ~2016 CHM whose vintage rarely matches the year
  Neither is ground truth. So when the model "misses" 30-35% of C-CAP forest,
  an unknown share of that is REFERENCE ERROR, not model error.

  The 2026-08-18 result made separating these urgent: 2023n is the strongest
  model in the project (4-ch rgb+chm, NIR, out-of-sample AUROC .9538, healthy
  calibration, max prob .972) and it STILL scores recall .6564 — squarely
  inside the .51-.71 band of much weaker years. If the gap were mainly model
  quality, that model would have closed it. It did not. So either the
  references over-call canopy, or every model shares one blind spot.

  WHAT IT DOES
  ------------
  Warps both references onto the prob grid and partitions every valid pixel:

      BOTH_CANOPY      both refs say canopy   → trustworthy positive
      BOTH_NONCANOPY   neither says canopy    → trustworthy negative
      DISAGREE         exactly one says canopy → UNMEASURABLE

  Then re-scores the model inside each partition. The deliverables:

    1. Recall/precision on the BOTH-AGREE subset — the honest number with
       reference noise largely removed.
    2. The share of the model's C-CAP "misses" that land in DISAGREE — the
       part of the gap that cannot be attributed to the model at all.

  A miss that both references confirm is a real blind spot worth labelling.
  A miss where the references contradict each other is a measurement problem,
  and no amount of retraining will fix it.

  Reads only. Local-safe (rasterio, no torch).

  USAGE
    py -3.12 phase4_ref_agreement.py --year 2023n \\
        --ndvi-ref phase4/qc/ndvi_ref_2023n.tif \\
        --ref  D:/edmonds-pipeline/Imagery/ccap_2021_hires_lc.tif \\
        --prob phase4/masks/edmonds_canopy_prob_2023n.tif --thresh 0.404

  OUTPUT
    phase4/qc/ref_agreement_{year}.txt   human-readable
    phase4/qc/ref_agreement_{year}.csv   one row per partition
    phase4/qc/ref_agreement_report.csv   appended headline row per year
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import importlib
import subprocess
import sys
from pathlib import Path


def _pip(spec):
    try:
        importlib.import_module(spec.split("==")[0].replace("-", "_"))
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=False)


_pip("rasterio")

import numpy as np                                            # noqa: E402
import rasterio                                               # noqa: E402
from rasterio.vrt import WarpedVRT                             # noqa: E402
from rasterio.enums import Resampling                          # noqa: E402
from rasterio.windows import Window                            # noqa: E402

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE

QC_DIR   = BASE / "phase4" / "qc"
MASKS    = BASE / "phase4" / "masks"
LOGS_DIR = BASE / "phase4" / "logs"

# C-CAP canopy codes — MUST match phase4_qc_indep.py's map (forest+wetland =
# the PRIMARY definition every headline number in this project uses).
CCAP_FOREST  = [9, 10, 11]
CCAP_WETLAND = [13, 16]
CCAP_CANOPY  = CCAP_FOREST + CCAP_WETLAND

# NDVI reference codes, per phase4_qc_ndvi.py: 0=non-veg, 1=grass, 2=canopy
NDVI_CANOPY = 2


class Unscorable(RuntimeError):
    """Inputs cannot yield an honest partition. Never write a nan row."""


def analyse(year, ndvi_path, ccap_path, prob_path, thresh, block_rows=2048):
    print(f"[ref-agree] year={year}  thresh={thresh}")
    print(f"    ndvi ref : {ndvi_path}")
    print(f"    ccap ref : {ccap_path}")
    print(f"    prob     : {prob_path}")

    thr_u8 = thresh * 254.0
    ndvi_ds = rasterio.open(ndvi_path)
    ccap_ds = rasterio.open(ccap_path)

    with rasterio.open(prob_path) as prob:
        H, W = prob.height, prob.width
        print(f"    grid     : {W}x{H}  {prob.crs}")

        nv = WarpedVRT(ndvi_ds, crs=prob.crs, transform=prob.transform,
                       width=W, height=H, resampling=Resampling.nearest)
        cv = WarpedVRT(ccap_ds, crs=prob.crs, transform=prob.transform,
                       width=W, height=H, resampling=Resampling.nearest)
        ccap_nodata = ccap_ds.nodata

        # counters: [partition] -> dict of px / model-canopy px
        parts = ["both_canopy", "both_noncanopy", "ndvi_only", "ccap_only"]
        px = {p: 0 for p in parts}
        mc = {p: 0 for p in parts}          # model calls canopy here
        valid_total = 0
        # C-CAP-only accounting, to split the headline FN
        ccap_canopy_total = 0
        ccap_tp = 0
        fn_both = 0                          # missed AND both refs agree canopy
        fn_disagree = 0                      # missed BUT refs disagree

        n_blocks = (H + block_rows - 1) // block_rows
        for bi, row0 in enumerate(range(0, H, block_rows)):
            rows = min(block_rows, H - row0)
            win = Window(0, row0, W, rows)

            pr = prob.read(1, window=win)
            nd = nv.read(1, window=win)
            cc = cv.read(1, window=win)

            valid = pr != 255
            if ccap_nodata is not None:
                valid &= cc != ccap_nodata
            # C-CAP 0 is Background/unclassified in this legend -> exclude
            valid &= cc != 0
            if not valid.any():
                continue

            nd_can = valid & (nd == NDVI_CANOPY)
            cc_can = valid & np.isin(cc, CCAP_CANOPY)
            model  = valid & (pr >= thr_u8)

            both   = nd_can & cc_can
            neither = valid & ~nd_can & ~cc_can
            n_only = nd_can & ~cc_can
            c_only = cc_can & ~nd_can

            for key, m in (("both_canopy", both), ("both_noncanopy", neither),
                           ("ndvi_only", n_only), ("ccap_only", c_only)):
                px[key] += int(m.sum())
                mc[key] += int((m & model).sum())

            valid_total += int(valid.sum())
            ccap_canopy_total += int(cc_can.sum())
            ccap_tp += int((cc_can & model).sum())
            fn_both += int((both & ~model).sum())
            fn_disagree += int((c_only & ~model).sum())

            if bi % 5 == 0 or bi == n_blocks - 1:
                print(f"    block {bi+1}/{n_blocks}", flush=True)

        nv.close(); cv.close()

    ndvi_ds.close(); ccap_ds.close()

    if valid_total == 0:
        raise Unscorable(
            f"year {year}: ZERO valid px across prob + both references.\n"
            "  No row written — an unscorable year must not look like a scored one.")

    return dict(year=year, thresh=thresh, valid=valid_total, px=px, mc=mc,
                ccap_canopy=ccap_canopy_total, ccap_tp=ccap_tp,
                fn_both=fn_both, fn_disagree=fn_disagree,
                ndvi_ref=Path(ndvi_path).name, ccap_ref=Path(ccap_path).name,
                prob=Path(prob_path).name)


def _safe(n, d):
    return n / d if d else float("nan")


def report(R):
    v = R["valid"]; px = R["px"]; mc = R["mc"]
    both = px["both_canopy"]; n_only = px["ndvi_only"]; c_only = px["ccap_only"]
    disagree = n_only + c_only

    # Honest metrics on the BOTH-AGREE subset: positives = both_canopy,
    # negatives = both_noncanopy. Disagreement pixels are EXCLUDED entirely.
    tp = mc["both_canopy"]
    fn = both - tp
    fp = mc["both_noncanopy"]
    rec  = _safe(tp, tp + fn)
    prec = _safe(tp, tp + fp)

    ccap_fn = R["ccap_canopy"] - R["ccap_tp"]
    share_unmeasurable = _safe(R["fn_disagree"], ccap_fn)

    L = [f"REFERENCE DISAGREEMENT MAP — year {R['year']}",
         f"  ndvi ref : {R['ndvi_ref']}",
         f"  ccap ref : {R['ccap_ref']}",
         f"  prob     : {R['prob']}   @ thresh {R['thresh']}",
         "",
         f"  valid px (prob + both refs present) : {v:,}",
         "",
         "  AGREEMENT PARTITION:",
         f"    BOTH say canopy        {both:>15,}  ({100*_safe(both,v):5.2f}%)  <- trustworthy positive",
         f"    BOTH say non-canopy    {px['both_noncanopy']:>15,}  ({100*_safe(px['both_noncanopy'],v):5.2f}%)  <- trustworthy negative",
         f"    NDVI only              {n_only:>15,}  ({100*_safe(n_only,v):5.2f}%)  \\",
         f"    C-CAP only             {c_only:>15,}  ({100*_safe(c_only,v):5.2f}%)  / DISAGREE = UNMEASURABLE",
         f"    -> refs disagree on    {disagree:>15,}  ({100*_safe(disagree,v):5.2f}%) of all valid pixels",
         "",
         "  MODEL SCORED ON THE BOTH-AGREE SUBSET ONLY (reference noise removed):",
         f"    recall    {rec:.4f}",
         f"    precision {prec:.4f}",
         f"    TP {tp:,}  FN {fn:,}  FP {fp:,}",
         "",
         "  WHERE THE HEADLINE C-CAP MISS ACTUALLY LIVES:",
         f"    C-CAP canopy px         {R['ccap_canopy']:,}",
         f"    model missed (FN)       {ccap_fn:,}",
         f"      ...of which BOTH refs agree it IS canopy : {R['fn_both']:,} "
         f"({100*_safe(R['fn_both'], ccap_fn):.1f}%)  <- REAL MISS",
         f"      ...of which refs DISAGREE                : {R['fn_disagree']:,} "
         f"({100*share_unmeasurable:.1f}%)  <- UNMEASURABLE",
         "",
         "  MODEL CANOPY-CALL RATE BY PARTITION (diagnostic):"]
    for p in ("both_canopy", "ndvi_only", "ccap_only", "both_noncanopy"):
        L.append(f"    {p:<18} {100*_safe(mc[p], px[p]):6.2f}%   ({mc[p]:,} / {px[p]:,})")
    L += ["",
          "  READ:",
          "    * The BOTH-AGREE recall is the honest number with most reference",
          "      noise removed. If it is much higher than the raw C-CAP recall,",
          "      the references — not the model — carry a large share of the gap.",
          "    * A high 'ccap_only' canopy-call rate means the model sides with",
          "      NDVI; a high 'ndvi_only' rate means it sides with C-CAP.",
          "    * CAVEAT: the NDVI reference uses a ~2016 CHM regardless of year,",
          "      so its height test is temporally offset (see ndvi_ref_*.txt)."]
    txt = "\n".join(L)
    print("\n" + txt)

    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"ref_agreement_{R['year']}.txt").write_text(txt, encoding="utf-8")

    with open(QC_DIR / f"ref_agreement_{R['year']}.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["partition", "px", "pct_of_valid", "model_canopy_px", "model_canopy_rate"])
        for p in ("both_canopy", "both_noncanopy", "ndvi_only", "ccap_only"):
            w.writerow([p, px[p], round(100*_safe(px[p], v), 4),
                        mc[p], round(_safe(mc[p], px[p]), 4)])

    main_csv = QC_DIR / "ref_agreement_report.csv"
    fields = ["year", "thresh", "valid", "both_canopy", "both_noncanopy",
              "ndvi_only", "ccap_only", "disagree_pct",
              "recall_agree", "precision_agree",
              "ccap_fn", "fn_both_real", "fn_disagree_unmeasurable",
              "unmeasurable_share_of_fn", "ndvi_ref", "ccap_ref", "prob", "ts"]
    row = dict(year=R["year"], thresh=R["thresh"], valid=v,
               both_canopy=both, both_noncanopy=px["both_noncanopy"],
               ndvi_only=n_only, ccap_only=c_only,
               disagree_pct=round(100*_safe(disagree, v), 4),
               recall_agree=round(rec, 4), precision_agree=round(prec, 4),
               ccap_fn=ccap_fn, fn_both_real=R["fn_both"],
               fn_disagree_unmeasurable=R["fn_disagree"],
               unmeasurable_share_of_fn=round(share_unmeasurable, 4),
               ndvi_ref=R["ndvi_ref"], ccap_ref=R["ccap_ref"], prob=R["prob"],
               ts=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    keep = []
    if main_csv.exists():
        keep = [r for r in csv.DictReader(open(main_csv, encoding="utf-8"))
                if not (r.get("year") == str(R["year"]) and r.get("prob") == R["prob"])]
    with open(main_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in keep:
            w.writerow({k: r.get(k, "") for k in fields})
        w.writerow(row)
    out_txt = QC_DIR / f"ref_agreement_{R['year']}.txt"
    print(f"\n[ref-agree] wrote {out_txt}")
    print(f"[ref-agree] wrote {main_csv}")


def write_step_log(R):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_ref_agreement_{R['year']}_{ts}.log").write_text(
            f"phase4_ref_agreement.py year={R['year']} valid={R['valid']} "
            f"both_canopy={R['px']['both_canopy']} ndvi_only={R['px']['ndvi_only']} "
            f"ccap_only={R['px']['ccap_only']} fn_both={R['fn_both']} "
            f"fn_disagree={R['fn_disagree']}\n", encoding="utf-8")
    except Exception as e:                                     # noqa: BLE001
        print(f"[ref-agree] WARN log: {e}")


def main():
    filtered = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(
        description="Partition pixels by reference agreement; split the model's "
                    "miss into REAL vs UNMEASURABLE.")
    ap.add_argument("--year", required=True)
    ap.add_argument("--ndvi-ref", default=None,
                    help="Default phase4/qc/ndvi_ref_{year}.tif")
    ap.add_argument("--ref", required=True, help="C-CAP raster.")
    ap.add_argument("--prob", required=True, help="Model probability raster.")
    ap.add_argument("--thresh", type=float, required=True,
                    help="Operating threshold, same one the headline score used.")
    ap.add_argument("--block-rows", type=int, default=2048)
    args = ap.parse_args(filtered)

    ndvi = Path(args.ndvi_ref) if args.ndvi_ref else QC_DIR / f"ndvi_ref_{args.year}.tif"
    for p in (ndvi, Path(args.ref), Path(args.prob)):
        if not Path(p).exists():
            raise FileNotFoundError(p)

    try:
        R = analyse(args.year, ndvi, Path(args.ref), Path(args.prob),
                    args.thresh, args.block_rows)
    except Unscorable as e:
        print(f"\n[ref-agree] UNSCORABLE — no row written\n{e}\n", file=sys.stderr)
        raise SystemExit(2)
    report(R)
    write_step_log(R)


if __name__ == "__main__":
    main()

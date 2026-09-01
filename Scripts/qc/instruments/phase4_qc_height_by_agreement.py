"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — RECALL BY HEIGHT *WITHIN* EACH REFERENCE-AGREEMENT PARTITION
  Edmonds Temporal Active Learning Pipeline

  THE QUESTION IT WAS BUILT FOR  (assessment 2026-08-18, unknown U3)
  ------------------------------------------------------------------
  Two facts sit next to each other and have never been crossed:

    P1c  — recall is a monotonic function of canopy height
           (.16 below 5 m rising to .93 above 30 m; 5-15 m holds 53% of
           all missed pixels).                    -> phase4_qc_height_curve.py
    P2   — the two references disagree on 15-17% of pixels, every year,
           and the model's "miss" is 64.6% inside that disagreement.
                                                  -> phase4_ref_agreement.py

  And a third, from the visual grounding: 8/8 inspected missed stands were
  SUBURBAN (yard / ornamental, many low-NDVI); ZERO were deciduous forest.
  C-CAP counts the lawn and roof BETWEEN yard trees as "Upland Forest".

  Short trees live in yards. Tall trees live in stands. So HEIGHT and
  LAND-USE CONTEXT are confounded in every number we have, and the height
  staircase may be a suburban-vs-forest staircase wearing a height costume.

  THE TEST
  --------
  Recompute the height curve SEPARATELY inside each agreement partition:

    * BOTH-AGREE CANOPY  — both references call it canopy. Reference noise
      is largely removed here, so recall means what it says.
        - staircase SURVIVES  -> detection really is height-dependent.
                                 The 5-15 m deficit is a model problem and
                                 Hamraz-style height-conditioned training
                                 (Literature_Tracker ID 86) is the lever.
        - staircase FLATTENS  -> the curve was mostly C-CAP's suburban
                                 over-count. The lever is the canopy
                                 DEFINITION (ID 81) and suburban labels,
                                 not height conditioning.

    * C-CAP ONLY  — C-CAP says canopy, NDVI+CHM says not. Expected to be
      dominated by low CHM (lawn/roof between yard trees). This partition is
      the suburban-over-count hypothesis made visible.

    * NDVI ONLY   — NDVI+CHM says canopy, C-CAP says not. Vegetated AND
      >= 2 m but outside C-CAP's forest classes: scattered yard/ornamental
      crowns. The genuine-under-detection hypothesis made visible.

  On the two contested partitions there is no truth, so the reported number
  is a MODEL CALL RATE, not a recall. It is labelled as such.

  This is a SAMPLE (decimated), like phase4_qc_height_curve.py. The SHAPE of
  each curve is the robust quantity, not the exact per-band counts.

  USAGE
    py -3.12 phase4_qc_height_by_agreement.py \\
        --prob  phase4/masks/edmonds_canopy_prob_2016.tif \\
        --ccap  D:/edmonds-pipeline/Imagery/ccap_2016_hires_lc.tif \\
        --ndvi  phase4/qc/ndvi_ref_2016.tif \\
        --thresh 0.509 --label 2016_baseline

  OUTPUT
    phase4/qc/height_by_agreement_{label}.txt / .csv
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import io
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from phase4seg.names import clean_argv  # noqa: E402

# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
from lake import BASE  # noqa: E402
QC_DIR = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "phase4" / "logs"

_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
CHM_NAME = "lidar_snoh_chm.tif"
CHM_DN_PER_M = 1.0 / 0.2

HEIGHT_BINS = [0, 2, 5, 10, 15, 20, 25, 30, 100]
CCAP_CANOPY = [9, 10, 11, 13, 16]          # forest + forested wetland, as qc_indep
NDVI_CANOPY = 2                            # ndvi_ref codes: 0 non-veg, 1 grass, 2 canopy

PARTITIONS = ["both_canopy", "ccap_only", "ndvi_only"]
PART_KIND = {"both_canopy": "recall", "ccap_only": "call rate", "ndvi_only": "call rate"}


def resolve_chm():
    for d in (_LOCAL_IMG, _DRIVE_IMG):
        p = d / CHM_NAME
        if p.exists():
            return p
    raise FileNotFoundError(CHM_NAME)


def _band_labels():
    out = []
    for i in range(len(HEIGHT_BINS) - 1):
        lo, hi = HEIGHT_BINS[i], HEIGHT_BINS[i + 1]
        out.append(f"{lo:>2}-{hi:<3}m" if hi < 100 else f"{lo:>2}+   m")
    return out


def analyse(prob_path, ccap_path, ndvi_path, thresh, decim):
    chm_path = resolve_chm()
    print(f"[height-by-agreement] prob = {prob_path}")
    print(f"[height-by-agreement] ccap = {ccap_path}")
    print(f"[height-by-agreement] ndvi = {ndvi_path}")
    print(f"[height-by-agreement] chm  = {chm_path}")
    print(f"[height-by-agreement] decimation 1/{decim}  (a SAMPLE — shape is the robust part)")

    thr_u8 = thresh * 254.0
    with rasterio.open(prob_path) as p:
        H = p.height // decim
        W = p.width // decim
        dt = p.transform * Affine.scale(decim)
        crs = p.crs
        nodata = 255 if p.nodata is None else p.nodata
        pr = p.read(1, out_shape=(H, W), resampling=Resampling.nearest)

    with rasterio.open(ccap_path) as r:
        with WarpedVRT(r, crs=crs, transform=dt, width=W, height=H,
                       resampling=Resampling.nearest) as rv:
            rc = rv.read(1)
            ccap_nodata = r.nodata
    with rasterio.open(ndvi_path) as n:
        with WarpedVRT(n, crs=crs, transform=dt, width=W, height=H,
                       resampling=Resampling.nearest) as nv:
            nd = nv.read(1)
            ndvi_nodata = n.nodata
    with rasterio.open(chm_path) as c:
        with WarpedVRT(c, crs=crs, transform=dt, width=W, height=H,
                       resampling=Resampling.nearest, src_nodata=0, nodata=0) as cv:
            dn = cv.read(1)

    hgt = (dn.astype(np.float32) - 1.0) / CHM_DN_PER_M
    hgt[dn == 0] = np.nan

    # valid = model + BOTH references present, matching phase4_ref_agreement
    valid = pr != nodata
    if ccap_nodata is not None:
        valid &= rc != ccap_nodata
    valid &= rc != 0
    if ndvi_nodata is not None:
        valid &= nd != ndvi_nodata

    ccap_can = valid & np.isin(rc, CCAP_CANOPY)
    ndvi_can = valid & (nd == NDVI_CANOPY)
    called = pr >= thr_u8

    masks = {
        "both_canopy": ccap_can & ndvi_can,
        "ccap_only": ccap_can & ~ndvi_can,
        "ndvi_only": ndvi_can & ~ccap_can,
    }

    n_bins = len(HEIGHT_BINS) - 1
    R = {"valid": int(valid.sum()), "decim": decim, "thresh": thresh,
         "prob": Path(prob_path).name, "ccap": Path(ccap_path).name,
         "ndvi": Path(ndvi_path).name, "parts": {}}

    for name, m in masks.items():
        hit = np.zeros(n_bins, dtype=np.int64)
        miss = np.zeros(n_bins, dtype=np.int64)
        for arr, sel in ((hit, m & called), (miss, m & ~called)):
            hv = hgt[sel]
            hv = hv[np.isfinite(hv)]
            if hv.size:
                idx = np.clip(np.digitize(hv, HEIGHT_BINS) - 1, 0, n_bins - 1)
                arr += np.bincount(idx, minlength=n_bins)
        R["parts"][name] = {
            "hit": hit, "miss": miss,
            "n": int(m.sum()), "n_called": int((m & called).sum()),
            "n_chm": int(hit.sum() + miss.sum()),
        }
    return R


def report(R, label):
    bands = _band_labels()
    n_bins = len(bands)
    L = [f"RECALL BY HEIGHT *WITHIN* EACH REFERENCE-AGREEMENT PARTITION — {label}",
         f"  prob : {R['prob']}   @ thresh {R['thresh']}",
         f"  ccap : {R['ccap']}",
         f"  ndvi : {R['ndvi']}",
         f"  sample : 1/{R['decim']} decimation · {R['valid']:,} valid cells "
         f"(model + BOTH refs present)",
         ""]

    for name in PARTITIONS:
        P = R["parts"][name]
        kind = PART_KIND[name]
        rate = P["n_called"] / P["n"] if P["n"] else float("nan")
        cov = 100 * P["n_chm"] / max(P["n"], 1)
        L += [f"  -- {name}  ({kind}) " + "-" * (46 - len(name) - len(kind)),
              f"     partition size {P['n']:,} cells · overall {kind} {rate:.4f}",
              f"     CHM-covered {P['n_chm']:,} ({cov:.0f}%)",
              "",
              f"     band        {kind:<10} called / not",
              ]
        for i in range(n_bins):
            t, f = int(P["hit"][i]), int(P["miss"][i])
            if t + f == 0:
                continue
            L.append(f"     {bands[i]:<11} {t/(t+f):.4f}     {t:>10,} / {f:<10,}")
        L.append("")

    # the discriminating comparison, stated numerically
    B = R["parts"]["both_canopy"]
    lo = sum(int(B["hit"][i]) for i in range(n_bins) if HEIGHT_BINS[i] >= 5 and HEIGHT_BINS[i + 1] <= 15)
    lo_m = sum(int(B["miss"][i]) for i in range(n_bins) if HEIGHT_BINS[i] >= 5 and HEIGHT_BINS[i + 1] <= 15)
    hi = sum(int(B["hit"][i]) for i in range(n_bins) if HEIGHT_BINS[i] >= 20)
    hi_m = sum(int(B["miss"][i]) for i in range(n_bins) if HEIGHT_BINS[i] >= 20)
    r_lo = lo / (lo + lo_m) if lo + lo_m else float("nan")
    r_hi = hi / (hi + hi_m) if hi + hi_m else float("nan")

    L += ["  -- THE TEST " + "-" * 46,
          f"     both-agree recall  5-15 m : {r_lo:.4f}",
          f"     both-agree recall  20 m+  : {r_hi:.4f}",
          f"     spread                    : {r_hi - r_lo:+.4f}",
          "",
          "     A large spread means detection really IS height-dependent even",
          "     where both references agree -> the 5-15 m deficit is a MODEL",
          "     problem; height-conditioned training is the lever.",
          "",
          "     A small spread means the raw height staircase was largely",
          "     C-CAP's suburban over-count -> the lever is the canopy",
          "     DEFINITION and suburban/ornamental labels, not height.",
          "",
          "     Cross-check: if ccap_only concentrates at LOW height, that is",
          "     the lawn-and-roof-between-yard-trees hypothesis confirmed.",
          "",
          "  CAVEATS",
          "     * decimated sample; shape is robust, exact counts are not.",
          "     * the CHM is ~2016 vintage at ~60% city coverage, so every",
          "       band is conditioned on CHM presence (see coverage % above).",
          "     * the NDVI reference's own height test uses the SAME CHM, so",
          "       ndvi_only / both_canopy are not independent of the height axis.",
          "       Read the ccap_only curve as the cleaner suburban probe."]

    txt = "\n".join(L)
    print("\n" + txt)

    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"height_by_agreement_{label}.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / f"height_by_agreement_{label}.csv", "w",
                 encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["partition", "measure", "band_lo_m", "band_hi_m", "rate", "called", "not_called"])
        for name in PARTITIONS:
            P = R["parts"][name]
            for i in range(n_bins):
                t, fn = int(P["hit"][i]), int(P["miss"][i])
                if t + fn == 0:
                    continue
                w.writerow([name, PART_KIND[name], HEIGHT_BINS[i], HEIGHT_BINS[i + 1],
                            round(t / (t + fn), 4), t, fn])
    print(f"\n[height-by-agreement] wrote {QC_DIR / f'height_by_agreement_{label}.txt'}")
    return r_lo, r_hi


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(
        description="Recall by canopy height within each reference-agreement partition.")
    ap.add_argument("--prob", required=True)
    ap.add_argument("--ccap", required=True)
    ap.add_argument("--ndvi", required=True)
    ap.add_argument("--thresh", type=float, required=True)
    ap.add_argument("--label", required=True, help="Name for the output files.")
    ap.add_argument("--decim", type=int, default=8, help="Decimation factor (default 8).")
    args = ap.parse_args(argv)

    R = analyse(Path(args.prob), Path(args.ccap), Path(args.ndvi), args.thresh, args.decim)
    r_lo, r_hi = report(R, args.label)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_height_by_agreement_{args.label}_{ts}.log").write_text(
            f"phase4_qc_height_by_agreement.py label={args.label} decim={args.decim} "
            f"valid={R['valid']} both_canopy={R['parts']['both_canopy']['n']} "
            f"ccap_only={R['parts']['ccap_only']['n']} ndvi_only={R['parts']['ndvi_only']['n']} "
            f"both_recall_5_15={r_lo:.4f} both_recall_20plus={r_hi:.4f}\n",
            encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()

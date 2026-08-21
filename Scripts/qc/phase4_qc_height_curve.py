"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — RECALL-BY-HEIGHT CURVE (decimated, imagery-free)
  Edmonds Temporal Active Learning Pipeline

  WHY THIS EXISTS SEPARATELY FROM phase4_qc_forest_misses.py
  ----------------------------------------------------------
  The 2026-08-18 P1c result is that recall is essentially a FUNCTION OF
  CANOPY HEIGHT (2016 baseline: .15 below 5 m rising monotonically to .93
  above 30 m). Answering "does raster X show that same curve?" needs only
  three things: the raster, a canopy reference, and the CHM.

  forest_misses also reads the year's ORTHO, for RGB/NDVI statistics. For the
  anchor year that ortho is 27 GB and is not mirrored locally, so the read
  streams over the Drive FUSE mount and fails outright when Colab is using the
  same mount (`TIFFFillTile: got 0 bytes`). This tool drops the imagery
  entirely and decimates, so the same question is answered in seconds from a
  few million samples instead of 31.5 Gpx.

  It is a SAMPLE, deliberately: the curve's SHAPE is the robust quantity, not
  the exact per-band counts. Use forest_misses when you need the full-census
  numbers and the spectral columns.

  THE QUESTION IT WAS BUILT FOR
  -----------------------------
  phase3/edmonds_canopy_mask_2020.tif is a model PREDICTION that Phase 4 then
  uses as the training LABEL for every coarse year (config.MASK_2020 ->
  labels.canopy_label_from_2020_mask). If the label source carries the same
  height deficiency as its students, the blind spot is being taught rather
  than merely inherited.

  USAGE
    py -3.12 phase4_qc_height_curve.py \\
        --prob phase3/edmonds_canopy_mask_2020.tif \\
        --ref  D:/edmonds-pipeline/Imagery/ccap_2021_hires_lc.tif \\
        --thresh 0.002 --label 2020_mask

    --thresh is on the 0-1 scale after dividing by 254, matching
    forest_misses. For a BINARY 0/1 mask use a small value like 0.002.

  OUTPUT
    phase4/qc/height_curve_{label}.txt / .csv
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

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE
QC_DIR = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "phase4" / "logs"

_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
CHM_NAME = "lidar_snoh_chm.tif"
CHM_DN_PER_M = 1.0 / 0.2

HEIGHT_BINS = [0, 2, 5, 10, 15, 20, 25, 30, 100]
CCAP_CANOPY = [9, 10, 11, 13, 16]          # forest + forested wetland, as qc_indep


def resolve_chm():
    for d in (_LOCAL_IMG, _DRIVE_IMG):
        p = d / CHM_NAME
        if p.exists():
            return p
    raise FileNotFoundError(CHM_NAME)


def curve(prob_path, ref_path, thresh, decim):
    chm_path = resolve_chm()
    print(f"[height-curve] prob = {prob_path}")
    print(f"[height-curve] ref  = {ref_path}")
    print(f"[height-curve] chm  = {chm_path}")
    print(f"[height-curve] decimation 1/{decim}  (a SAMPLE — shape is the robust part)")

    thr_u8 = thresh * 254.0
    with rasterio.open(prob_path) as p:
        H = p.height // decim
        W = p.width // decim
        # transform of the decimated grid
        dt = p.transform * Affine.scale(decim)
        crs = p.crs
        nodata = 255 if p.nodata is None else p.nodata
        pr = p.read(1, out_shape=(H, W), resampling=Resampling.nearest)

    with rasterio.open(ref_path) as r, rasterio.open(chm_path) as c:
        with WarpedVRT(r, crs=crs, transform=dt, width=W, height=H,
                       resampling=Resampling.nearest) as rv:
            rc = rv.read(1)
            ref_nodata = r.nodata
        with WarpedVRT(c, crs=crs, transform=dt, width=W, height=H,
                       resampling=Resampling.nearest, src_nodata=0, nodata=0) as cv:
            dn = cv.read(1)

    hgt = (dn.astype(np.float32) - 1.0) / CHM_DN_PER_M
    hgt[dn == 0] = np.nan

    valid = pr != nodata
    if ref_nodata is not None:
        valid &= rc != ref_nodata
    valid &= rc != 0
    canopy = valid & np.isin(rc, CCAP_CANOPY)
    called = canopy & (pr >= thr_u8)

    n_bins = len(HEIGHT_BINS) - 1
    h_tp = np.zeros(n_bins, dtype=np.int64)
    h_fn = np.zeros(n_bins, dtype=np.int64)
    for arr, mask in ((h_tp, called), (h_fn, canopy & ~called)):
        hv = hgt[mask]
        hv = hv[np.isfinite(hv)]
        if hv.size:
            idx = np.clip(np.digitize(hv, HEIGHT_BINS) - 1, 0, n_bins - 1)
            arr += np.bincount(idx, minlength=n_bins)

    return dict(h_tp=h_tp, h_fn=h_fn,
                sampled=int(valid.sum()), ref_canopy=int(canopy.sum()),
                tp=int(called.sum()), decim=decim,
                prob=Path(prob_path).name, ref=Path(ref_path).name, thresh=thresh)


def report(R, label):
    h_tp, h_fn = R["h_tp"], R["h_fn"]
    tot_t, tot_f = int(h_tp.sum()), int(h_fn.sum())
    overall = R["tp"] / R["ref_canopy"] if R["ref_canopy"] else float("nan")

    L = [f"RECALL BY CANOPY HEIGHT — {label}",
         f"  prob   : {R['prob']}   @ thresh {R['thresh']}",
         f"  ref    : {R['ref']}   (canopy = forest + forested wetland)",
         f"  sample : 1/{R['decim']} decimation · {R['sampled']:,} valid cells",
         "",
         f"  overall recall on sampled C-CAP canopy : {overall:.4f}",
         f"  ({R['tp']:,} of {R['ref_canopy']:,})",
         "",
         "  band        recall     recalled / missed",
         ]
    for i in range(len(HEIGHT_BINS) - 1):
        t, f = int(h_tp[i]), int(h_fn[i])
        if t + f == 0:
            continue
        lo, hi = HEIGHT_BINS[i], HEIGHT_BINS[i + 1]
        band = f"{lo:>2}-{hi:<3}m" if hi < 100 else f"{lo:>2}+   m"
        L.append(f"  {band:<11} {t/(t+f):.4f}    {t:>11,} / {f:<11,}")
    L += ["",
          f"  CHM-covered sample: {tot_t + tot_f:,} of {R['ref_canopy']:,} canopy cells "
          f"({100*(tot_t+tot_f)/max(R['ref_canopy'],1):.0f}%) — the CHM covers ~60% of the city.",
          "  A rising staircase means detection is height-dependent.",
          "  A flat line means it is not."]
    txt = "\n".join(L)
    print("\n" + txt)

    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"height_curve_{label}.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / f"height_curve_{label}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["band_lo_m", "band_hi_m", "recall", "recalled", "missed"])
        for i in range(len(HEIGHT_BINS) - 1):
            t, fn = int(h_tp[i]), int(h_fn[i])
            if t + fn == 0:
                continue
            w.writerow([HEIGHT_BINS[i], HEIGHT_BINS[i + 1],
                        round(t / (t + fn), 4), t, fn])
    print(f"\n[height-curve] wrote {QC_DIR / f'height_curve_{label}.txt'}")


def main():
    argv = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(description="Decimated recall-by-height curve; no imagery needed.")
    ap.add_argument("--prob", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--thresh", type=float, required=True)
    ap.add_argument("--label", required=True, help="Name for the output files.")
    ap.add_argument("--decim", type=int, default=8, help="Decimation factor (default 8).")
    args = ap.parse_args(argv)

    R = curve(Path(args.prob), Path(args.ref), args.thresh, args.decim)
    report(R, args.label)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_height_curve_{args.label}_{ts}.log").write_text(
            f"phase4_qc_height_curve.py label={args.label} decim={args.decim} "
            f"sampled={R['sampled']} ref_canopy={R['ref_canopy']} tp={R['tp']}\n",
            encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()

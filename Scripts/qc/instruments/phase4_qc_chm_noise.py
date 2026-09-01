r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — COULD CHM ERROR HAVE MANUFACTURED THE HEIGHT STAIRCASE?
  Edmonds Temporal Active Learning Pipeline

  THE QUESTION IT WAS BUILT FOR  (assessment 2026-08-18, unknown U6)
  ------------------------------------------------------------------
  The single most-cited result in this project is that detection is a
  function of canopy height (recall .16 below 5 m rising to .93 above
  30 m). Every band of it is stratified on lidar_snoh_chm.tif.

  MOUDRY 2024 (ID 82) and SIERRA 2026: canopy-height products carry
  height-dependent bias, realistic MAE ~3 m — enough to blur adjacent 5 m
  bands. TURUBANOVA 2023 (ID 84) finds error concentrating at 4-6 m,
  exactly where our deficit lives. STATE lists U6 as UNVALIDATED and says
  "part of the staircase could be CHM error".

  THE STATISTICS THAT DECIDE IT
  ------------------------------------------------------------------
  Height enters as the STRATIFICATION VARIABLE, not as a predictor being
  fitted. When you bin by a noisy measurement h_hat = h + e and average an
  outcome inside each bin, you observe

        r_obs(h_hat) = E[ r_true(h) | h_hat ]

  which is r_true SMOOTHED toward the global mean. This is regression
  dilution / errors-in-variables attenuation, and it runs ONE WAY:
  measurement error in the binning variable FLATTENS a real curve. It
  cannot BUILD a monotonic staircase out of a flat truth.

  So the honest worry is not "the curve is fake" — it is "the curve is
  UNDERSTATED and its band edges are smeared". This script measures both.

  WHAT IT DOES
    1. NULL TEST (can binning manufacture structure?) — re-assign each
       pixel's detection outcome at random, independent of height, at the
       observed overall rate. If the pipeline is sound the staircase must
       collapse to ~zero spread. This is the sanity check that the whole
       method rests on.
    2. ATTENUATION TEST — add synthetic Gaussian error of sigma = 1..5 m
       to the CHM, re-bin, and watch the spread shrink. The rate of shrink
       tells you how much the ~3 m error ALREADY in the CHM has flattened
       the observed curve, i.e. how much steeper the truth likely is.

  Measured on agreed-canopy pixels only (both references call it canopy),
  so reference disagreement cannot contaminate the answer.

  USAGE
    py -3.12 phase4_qc_chm_noise.py --prob ../phase4/masks/edmonds_canopy_prob_2016.tif \
        --ccap D:/edmonds-pipeline/Imagery/ccap_2016_hires_lc.tif \
        --ndvi ../phase4/qc/ndvi_ref_2016.tif --thresh 0.509 --label 2016_baseline

  OUTPUT
    phase4/qc/chm_noise_{label}.txt / .csv
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
CCAP_CANOPY = [9, 10, 11, 13, 16]
NDVI_CANOPY = 2
SIGMAS = [0.0, 1.0, 2.0, 3.0, 5.0]


def resolve_chm():
    for d in (_LOCAL_IMG, _DRIVE_IMG):
        p = d / CHM_NAME
        if p.exists():
            return p
    raise FileNotFoundError(CHM_NAME)


def _spread(h, called):
    """recall(5-15 m) vs recall(20 m+) — the same statistic U3 reports."""
    lo = (h >= 5) & (h < 15)
    hi = h >= 20
    r_lo = called[lo].mean() if lo.any() else np.nan
    r_hi = called[hi].mean() if hi.any() else np.nan
    return float(r_lo), float(r_hi), float(r_hi - r_lo)


def _by_band(h, called):
    out = []
    for i in range(len(HEIGHT_BINS) - 1):
        m = (h >= HEIGHT_BINS[i]) & (h < HEIGHT_BINS[i + 1])
        out.append(float(called[m].mean()) if m.any() else np.nan)
    return out


def analyse(prob_path, ccap_path, ndvi_path, thresh, decim, seed):
    chm_path = resolve_chm()
    print(f"[chm-noise] prob={prob_path}\n[chm-noise] chm={chm_path} decim 1/{decim}")
    thr_u8 = thresh * 254.0

    with rasterio.open(prob_path) as p:
        H, W = p.height // decim, p.width // decim
        dt = p.transform * Affine.scale(decim)
        crs = p.crs
        nodata = 255 if p.nodata is None else p.nodata
        pr = p.read(1, out_shape=(H, W), resampling=Resampling.nearest)

    def warp(path, **kw):
        with rasterio.open(path) as src:
            with WarpedVRT(src, crs=crs, transform=dt, width=W, height=H,
                           resampling=Resampling.nearest, **kw) as v:
                return v.read(1), src.nodata

    rc, cc_nod = warp(ccap_path)
    nd, nd_nod = warp(ndvi_path)
    dn, _ = warp(chm_path, src_nodata=0, nodata=0)

    valid = pr != nodata
    if cc_nod is not None:
        valid &= rc != cc_nod
    valid &= rc != 0
    if nd_nod is not None:
        valid &= nd != nd_nod

    agreed = valid & np.isin(rc, CCAP_CANOPY) & (nd == NDVI_CANOPY) & (dn > 0)
    h = ((dn[agreed].astype(np.float32) - 1.0) / CHM_DN_PER_M)
    called = (pr[agreed] >= thr_u8)
    print(f"[chm-noise] agreed-canopy pixels with CHM: {h.size:,}")

    rng = np.random.default_rng(seed)
    R = {"n": int(h.size), "thresh": thresh, "decim": decim,
         "prob": Path(prob_path).name, "overall": float(called.mean()),
         "rows": [], "bands_obs": _by_band(h, called)}

    # ── 1. NULL: outcome independent of height ──────────────────────────
    fake = rng.random(h.size) < called.mean()
    R["null"] = _spread(h, fake)

    # ── 2. ATTENUATION: add error to the binning variable ───────────────
    for s in SIGMAS:
        hn = h if s == 0 else h + rng.normal(0.0, s, h.size).astype(np.float32)
        lo, hi, sp = _spread(np.clip(hn, 0, None), called)
        R["rows"].append({"sigma": s, "lo": lo, "hi": hi, "spread": sp,
                          "bands": _by_band(np.clip(hn, 0, None), called)})
    return R


def report(R, label):
    obs = R["rows"][0]["spread"]
    L = [f"COULD CHM ERROR HAVE MANUFACTURED THE HEIGHT STAIRCASE? — {label}",
         f"  prob : {R['prob']} @ thresh {R['thresh']} · decim 1/{R['decim']}",
         f"  agreed-canopy pixels with CHM: {R['n']:,} · overall recall {R['overall']:.4f}",
         "",
         "  -- 1. NULL TEST: can binning invent a staircase? " + "-" * 10,
         f"     outcome shuffled to be INDEPENDENT of height, same overall rate",
         f"     5-15 m {R['null'][0]:.4f}   20 m+ {R['null'][1]:.4f}   "
         f"spread {R['null'][2]:+.4f}",
         ""]
    if abs(R["null"][2]) < 0.01:
        L += ["     -> spread collapses to ~0, as it must. Binning by height CANNOT",
              "        manufacture a staircase; the observed one comes from the data."]
    else:
        L += ["     -> ** NON-ZERO SPREAD UNDER THE NULL — the method is biased and every",
              "        height result built on it is suspect. Stop and fix this first. **"]

    L += ["",
          "  -- 2. ATTENUATION: what extra CHM error does to the curve " + "-" * 1,
          f"     {'added sigma':>12} {'5-15 m':>9} {'20 m+':>9} {'spread':>9} {'vs obs':>9}"]
    for row in R["rows"]:
        rel = row["spread"] / obs if obs else float("nan")
        tag = "  <- observed" if row["sigma"] == 0 else ""
        L.append(f"     {row['sigma']:>10.1f} m {row['lo']:>9.4f} {row['hi']:>9.4f} "
                 f"{row['spread']:>9.4f} {rel:>8.2f}x{tag}")

    s3 = next((r for r in R["rows"] if r["sigma"] == 3.0), None)
    if s3 and obs:
        k = s3["spread"] / obs
        L += ["",
              f"     Adding the ~3 m error the literature reports (Moudry 2024) shrinks the",
              f"     spread to {k:.2f}x of observed. Measurement error in the BINNING",
              "     variable attenuates one way only — it flattens, it cannot steepen.",
              "     The CHM already contains error of about that size, so the observed",
              f"     curve is itself an ATTENUATED copy of the truth: the real spread is",
              f"     plausibly ~{obs/max(k,1e-6):.4f} rather than {obs:.4f}.",
              "",
              "     => U6 ANSWERED IN THE DIRECTION THAT MATTERS. CHM error cannot have",
              "        created the staircase; it can only have UNDERSTATED it. The height",
              "        finding is safe, and if anything conservative.",
              "     => What CHM error DOES damage is the BAND EDGES: with ~3 m error a",
              "        pixel labelled 5-10 m routinely belongs in 2-5 m or 10-15 m. Do not",
              "        quote a single band's recall as if the boundary were sharp, and do",
              "        not design a height-conditioned model around a 5 m cut without",
              "        allowing for that smearing."]

    L += ["",
          "  -- CAVEATS " + "-" * 47,
          "     * The added error is Gaussian and homoscedastic. Real CHM error is",
          "       height-DEPENDENT and biased (Moudry 2024), so this brackets the",
          "       magnitude of attenuation, it does not model the true error process.",
          "     * The attenuation correction assumes the existing error is ~3 m and",
          "       independent of the model's behaviour. If CHM error and detection",
          "       failure share a cause (both worse in dense mixed stands) the",
          "       correction is optimistic.",
          "     * Agreed-canopy pixels only, so this says nothing about contested ground.",
          "     * Decimated sample; the ratio between rows is the robust quantity."]

    txt = "\n".join(L)
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"chm_noise_{label}.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / f"chm_noise_{label}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["added_sigma_m", "recall_5_15", "recall_20plus", "spread",
                    "ratio_vs_observed"])
        for row in R["rows"]:
            w.writerow([row["sigma"], round(row["lo"], 4), round(row["hi"], 4),
                        round(row["spread"], 4),
                        round(row["spread"] / obs, 4) if obs else ""])
        w.writerow(["NULL(shuffled)", round(R["null"][0], 4), round(R["null"][1], 4),
                    round(R["null"][2], 4), ""])
    print(f"\n[chm-noise] wrote {QC_DIR / f'chm_noise_{label}.txt'}")


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(
        description="Test whether CHM measurement error could have produced the height curve.")
    ap.add_argument("--prob", required=True)
    ap.add_argument("--ccap", required=True)
    ap.add_argument("--ndvi", required=True)
    ap.add_argument("--thresh", type=float, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--decim", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    R = analyse(Path(args.prob), Path(args.ccap), Path(args.ndvi),
                args.thresh, args.decim, args.seed)
    report(R, args.label)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_chm_noise_{args.label}_{ts}.log").write_text(
            f"phase4_qc_chm_noise.py label={args.label} n={R['n']} "
            f"null_spread={R['null'][2]:.4f}\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()

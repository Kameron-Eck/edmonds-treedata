r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — HOW MUCH CANOPY IS THE MISSING LIDAR HIDING?
  Edmonds Temporal Active Learning Pipeline

  THE QUESTION IT WAS BUILT FOR  (U1 / result 9d, 2026-08-18)
  ------------------------------------------------------------------
  Every canopy definition this project uses is "green AND tall", so it
  needs a CHM height. Where the lidar does not reach, a pixel CANNOT be
  canopy — it is forced to background by ABSENCE OF DATA rather than by
  the definition. Measured on the 2016 analysis area, ~16.5% of valid
  cells have no CHM.

  That makes every figure in the D1 threshold sweep (ndvi_ref_2016.txt)
  a LOWER BOUND. STATE has always asserted the uncovered strip is "Puget
  Sound W edge + S margin = water, no canopy" — plausible, and never
  verified. If it is water, the bound is tight and nothing changes. If it
  contains green land, the city canopy number is understated and the
  canopy definition inherits a coverage bias.

  WHAT THIS MEASURES
    Over the imaged area, split pixels by CHM presence and compare their
    NDVI. Water is strongly NEGATIVE in NDVI, so a no-CHM zone that is
    genuinely water will show a negative NDVI distribution. Vegetation
    sits high. The gap between those two readings is the answer.

    Reported:
      * share of imaged pixels with / without CHM
      * NDVI percentiles inside each
      * how much canopy % could be hiding in the no-CHM zone, as an
        UPPER BOUND (every green no-CHM pixel counted as canopy)

  The upper bound is deliberately generous: it assumes every vegetated
  pixel without lidar is a tree, which is false (lawns are green too). It
  brackets the error rather than estimating it.

  USAGE
    py -3.12 phase4_qc_chm_gap.py --year 2016
    py -3.12 phase4_qc_chm_gap.py --year 2016 --decim 4

  OUTPUT
    phase4/qc/chm_gap_{year}.txt / .csv
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

# same catalogue as phase4_qc_ndvi.py — all are R,G,B,NIR
NIR_CATALOG = {
    "2016": {"file": "2016_snoh_rgbi.tif", "nir": 4},
    "2019n": {"file": "2019_naip_rgbi.tif", "nir": 4},
    "2021s": {"file": "2021_snoh_rgbi.tif", "nir": 4},
    "2023n": {"file": "2023_naip_rgbi.tif", "nir": 4},
}
VEG_CUTS = [0.20, 0.25, 0.30]


def resolve(fname):
    for d in (_LOCAL_IMG, _DRIVE_IMG):
        p = d / fname
        if p.exists():
            return p
    raise FileNotFoundError(fname)


def analyse(year, decim):
    spec = NIR_CATALOG[year]
    img_path = resolve(spec["file"])
    chm_path = resolve(CHM_NAME)
    print(f"[chm-gap] imagery = {img_path}")
    print(f"[chm-gap] chm     = {chm_path}   decim 1/{decim}")

    with rasterio.open(img_path) as img:
        H, W = img.height // decim, img.width // decim
        dt = img.transform * Affine.scale(decim)
        crs = img.crs
        r = img.read(1, out_shape=(H, W), resampling=Resampling.average).astype(np.float32)
        nir = img.read(spec["nir"], out_shape=(H, W),
                       resampling=Resampling.average).astype(np.float32)

    with rasterio.open(chm_path) as c:
        with WarpedVRT(c, crs=crs, transform=dt, width=W, height=H,
                       resampling=Resampling.nearest, src_nodata=0, nodata=0) as v:
            dn = v.read(1)

    # imaged = any signal; the orthos pad with 0 outside the flight footprint
    imaged = (r + nir) > 0
    ndvi = (nir - r) / (nir + r + 1e-6)
    has_chm = imaged & (dn > 0)
    no_chm = imaged & (dn == 0)

    def pct(a, b):
        return 100.0 * a / b if b else float("nan")

    n_img = int(imaged.sum())
    R = {"year": year, "decim": decim, "n_imaged": n_img,
         "n_chm": int(has_chm.sum()), "n_nochm": int(no_chm.sum()),
         "img": img_path.name}

    for name, m in (("has_chm", has_chm), ("no_chm", no_chm)):
        v = ndvi[m]
        R[name] = {
            "n": int(m.sum()),
            "p10": float(np.percentile(v, 10)) if v.size else float("nan"),
            "p50": float(np.percentile(v, 50)) if v.size else float("nan"),
            "p90": float(np.percentile(v, 90)) if v.size else float("nan"),
            "neg": float((v < 0).mean()) if v.size else float("nan"),
            "veg": {c: float((v >= c).mean()) for c in VEG_CUTS} if v.size else {},
        }
    # upper bound: every green no-CHM pixel counted as canopy, as % of imaged
    R["upper_add"] = {c: pct(R["no_chm"]["veg"][c] * R["n_nochm"], n_img) for c in VEG_CUTS}
    return R


def report(R):
    n = R["n_imaged"]
    H, N = R["has_chm"], R["no_chm"]

    def pc(x):
        return 100.0 * x / n

    L = [f"WHAT IS HIDING IN THE NO-LIDAR ZONE? — {R['year']}",
         f"  imagery : {R['img']} · decim 1/{R['decim']}",
         f"  imaged pixels {n:,}",
         "",
         "  -- COVERAGE " + "-" * 46,
         f"     with CHM    {H['n']:>14,}  ({pc(H['n']):5.1f}%)",
         f"     NO CHM      {N['n']:>14,}  ({pc(N['n']):5.1f}%)  <- forced to non-canopy",
         "",
         "  -- IS THE NO-CHM ZONE WATER, AS STATE ASSUMES? " + "-" * 11,
         f"     {'zone':<10} {'NDVI p10':>9} {'NDVI p50':>9} {'NDVI p90':>9} {'% NDVI<0':>9}",
         f"     {'has CHM':<10} {H['p10']:>9.3f} {H['p50']:>9.3f} {H['p90']:>9.3f}"
         f" {100*H['neg']:>8.1f}%",
         f"     {'NO CHM':<10} {N['p10']:>9.3f} {N['p50']:>9.3f} {N['p90']:>9.3f}"
         f" {100*N['neg']:>8.1f}%",
         ""]

    L.append(f"     {'green share of each zone':<28}"
             + "".join(f"  NDVI>={c:.2f}" for c in VEG_CUTS))
    L.append(f"     {'has CHM':<28}"
             + "".join(f"     {100*H['veg'][c]:5.1f}%" for c in VEG_CUTS))
    L.append(f"     {'NO CHM':<28}"
             + "".join(f"     {100*N['veg'][c]:5.1f}%" for c in VEG_CUTS))
    L.append("")

    L += ["  -- HOW MUCH CANOPY COULD BE HIDING THERE? " + "-" * 15,
          "     UPPER BOUND — every green no-CHM pixel counted as canopy.",
          "     Deliberately generous: lawns are green too, so the truth is lower.",
          ""]
    for c in VEG_CUTS:
        L.append(f"     at NDVI>={c:.2f}:  up to +{R['upper_add'][c]:.2f} pp of imaged area")
    L.append("")

    worst = max(R["upper_add"].values())
    if N["neg"] > 0.5:
        L += ["     -> THE NO-CHM ZONE IS MOSTLY WATER (majority negative NDVI), which is",
              "        what STATE assumed. The assumption is now CHECKED, not asserted."]
    elif N["veg"][0.30] > 0.25:
        L += ["     -> THE NO-CHM ZONE IS SUBSTANTIALLY GREEN LAND, NOT WATER. STATE's",
              "        assumption is WRONG and the D1 sweep understates city canopy by a",
              "        material amount. The canopy definition inherits a coverage bias that",
              "        has to be stated with every number."]
    else:
        L += ["     -> MIXED: neither clean water nor clean vegetation. The bound below is",
              "        real but modest; state it rather than resolving it."]
    L += [f"     -> worst-case understatement of city canopy: {worst:.2f} pp.",
          "",
          "  -- CAVEATS " + "-" * 47,
          "     * NDVI here is computed on decimated, AVERAGED reflectance, so mixed",
          "       pixels are smoothed; percentiles are indicative.",
          "     * 'imaged' = R+NIR > 0. Genuine black pixels inside the footprint would",
          "       be misread as unimaged (rare, and it shrinks both zones equally).",
          "     * Water bodies can read slightly positive when turbid or sun-glinted, so",
          "       '% NDVI<0' understates water a little.",
          "     * This bounds the CHM-coverage bias only. It says nothing about whether",
          "       the CHM is ACCURATE where it does exist (that is U6)."]

    txt = "\n".join(L)
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"chm_gap_{R['year']}.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / f"chm_gap_{R['year']}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "zone", "n", "share_of_imaged", "ndvi_p10", "ndvi_p50",
                    "ndvi_p90", "frac_ndvi_neg"]
                   + [f"frac_ndvi_ge_{c}" for c in VEG_CUTS])
        for name, Z in (("has_chm", H), ("no_chm", N)):
            w.writerow([R["year"], name, Z["n"], round(Z["n"] / n, 4),
                        round(Z["p10"], 4), round(Z["p50"], 4), round(Z["p90"], 4),
                        round(Z["neg"], 4)] + [round(Z["veg"][c], 4) for c in VEG_CUTS])
    out_txt = QC_DIR / f"chm_gap_{R['year']}.txt"
    print(f"\n[chm-gap] wrote {out_txt}")


def main():
    argv = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(
        description="Bound how much canopy the missing-lidar zone could be hiding.")
    ap.add_argument("--year", default="2016", choices=sorted(NIR_CATALOG))
    ap.add_argument("--decim", type=int, default=8)
    args = ap.parse_args(argv)

    R = analyse(args.year, args.decim)
    report(R)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_chm_gap_{args.year}_{ts}.log").write_text(
            f"phase4_qc_chm_gap.py year={args.year} decim={args.decim} "
            f"no_chm_share={R['n_nochm']/max(R['n_imaged'],1):.4f}\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()

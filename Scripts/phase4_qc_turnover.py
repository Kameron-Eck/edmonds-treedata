"""
+==================================================================+
  PHASE 4 - MEASURED CANOPY TURNOVER BETWEEN TWO REFERENCE DATES
  Edmonds Temporal Active Learning Pipeline

  WHY (open questions Q50 / Q78, lit-watch iterations 35, 41, 42)
  ---------------------------------------------------------------
  Two separate designs are currently sized on a GUESSED turnover rate:

   1. PAIRED SAMPLE PRECISION (lit ID 170, Frayer & Furnival). Paired
      variance is driven ONLY by discordant pairs, so the sample size
      needed to resolve a ~2.6 pp change depends entirely on how many
      points actually change. We assumed 4%/1.4% and 6%/3.4%.

   2. WEAK TEMPORAL SUPERVISION (lit ID 193, Bou et al. 2026). It assumes
      same-location pairs are "predominantly unchanged". Which of our 18
      acquisitions can serve as training pairs depends on where that
      assumption breaks - we estimated safe to ~3 yr, violated by ~13 yr.

  Both estimates are guesses. This measures the thing.

  THE INSTRUMENT
  --------------
  C-CAP hi-res 2016 vs 2021: the SAME product, SAME producer, 5-year gap,
  and - critically - INDEPENDENT OF OUR MODEL. Using our own masks would
  confound real turnover with model instability, which is precisely the
  distinction we are trying to establish (Q75).

  Reports the four-way partition (stable canopy / stable non-canopy /
  loss / gain), the discordance rate, and the implied annualised rate.

  CAVEATS PRINTED WITH THE RESULT - read them. C-CAP has its own error,
  and product error inflates apparent turnover. This measures an UPPER
  BOUND on true turnover, which is the conservative direction for sample
  sizing and the ANTI-conservative direction for the weak-supervision
  assumption. Say which you are using it for.

  USAGE
    py -3.12 phase4_qc_turnover.py
    py -3.12 phase4_qc_turnover.py --a <tif> --b <tif> --years 5 --label mypair

  OUTPUT
    phase4/qc/turnover_{label}.txt / .csv
+==================================================================+
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
LOGS_DIR = BASE / "Scripts" / "logs"
_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")

CCAP_CANOPY = [9, 10, 11, 13, 16]      # forest + forested wetland, as qc_indep


def resolve(name):
    for d in (_LOCAL_IMG, BASE / "Full_Image" / "Pipeline Imagery", QC_DIR):
        p = d / name
        if p.exists():
            return p
    raise FileNotFoundError(name)


def turnover(a_path, b_path, decim, canopy_codes, zero_is_nodata=True):
    print(f"[turnover] date A = {a_path}")
    print(f"[turnover] date B = {b_path}")
    print(f"[turnover] decimation 1/{decim}")

    with rasterio.open(a_path) as A:
        H, W = A.height // decim, A.width // decim
        dt = A.transform * Affine.scale(decim)
        crs, a_nd = A.crs, A.nodata
        a = A.read(1, out_shape=(H, W), resampling=Resampling.nearest)
    with rasterio.open(b_path) as B:
        with WarpedVRT(B, crs=crs, transform=dt, width=W, height=H,
                       resampling=Resampling.nearest) as bv:
            b = bv.read(1)
            b_nd = B.nodata

    # CRITICAL: 0 means NODATA in C-CAP, but means NON-VEGETATED - a real class -
    # in the NDVI references (0 non-veg / 1 grass / 2 canopy). Treating 0 as nodata
    # there silently drops every non-vegetated pixel and inflates the canopy share.
    valid = np.ones_like(a, dtype=bool)
    for arr, nd in ((a, a_nd), (b, b_nd)):
        if zero_is_nodata:
            valid &= arr != 0
        if nd is not None:
            valid &= arr != nd

    ca = valid & np.isin(a, canopy_codes)
    cb = valid & np.isin(b, canopy_codes)

    n = int(valid.sum())
    if n == 0:
        raise SystemExit("[turnover] ABORT: no overlapping valid pixels.")
    return {
        "n": n,
        "stable_canopy": int((ca & cb).sum()),
        "stable_non": int((~ca & ~cb & valid).sum()),
        "loss": int((ca & ~cb).sum()),
        "gain": int((~ca & cb & valid).sum()),
        "a": Path(a_path).name, "b": Path(b_path).name, "decim": decim,
    }


def report(R, years, label):
    n = R["n"]
    pc = lambda k: 100.0 * R[k] / n
    disc = R["loss"] + R["gain"]
    disc_pc = 100.0 * disc / n
    can_a = R["stable_canopy"] + R["loss"]
    # annualised, on the CANOPY base (loss as a fraction of date-A canopy)
    loss_of_canopy = 100.0 * R["loss"] / can_a if can_a else float("nan")
    ann = (1 - (1 - loss_of_canopy / 100.0) ** (1.0 / years)) * 100 if years else float("nan")

    L = [f"MEASURED CANOPY TURNOVER - {label}",
         f"  date A : {R['a']}",
         f"  date B : {R['b']}    (gap {years} years)",
         f"  sample : 1/{R['decim']} decimation, {n:,} valid cells",
         "",
         "  FOUR-WAY PARTITION",
         f"    stable canopy      {R['stable_canopy']:>12,}  {pc('stable_canopy'):>6.2f}%",
         f"    stable non-canopy  {R['stable_non']:>12,}  {pc('stable_non'):>6.2f}%",
         f"    LOSS  (A can -> B non) {R['loss']:>8,}  {pc('loss'):>6.2f}%",
         f"    GAIN  (A non -> B can) {R['gain']:>8,}  {pc('gain'):>6.2f}%",
         "",
         f"  DISCORDANCE (loss+gain)  {disc:>12,}  {disc_pc:>6.2f}%   <- drives paired precision",
         f"  net change                              {pc('gain') - pc('loss'):>+6.2f} pp",
         f"  loss as % of date-A canopy              {loss_of_canopy:>6.2f}%",
         f"  implied ANNUALISED loss rate            {ann:>6.2f}%/yr",
         "",
         "  WHAT THIS IS FOR",
         "    * paired-sample sizing (lit ID 170): the DISCORDANCE rate is the",
         "      only quantity that matters. Higher discordance -> more points needed.",
         "    * weak temporal supervision (lit ID 193): the assumption is that",
         "      same-location pairs are 'predominantly unchanged'. Discordance IS",
         "      the violation rate of that assumption at this gap.",
         "",
         "  CAVEATS - READ BEFORE USING THE NUMBER",
         "    * This is REFERENCE-vs-REFERENCE, not truth. C-CAP has its own error",
         "      (~84% OA regionally, lit ID 77), and product error INFLATES apparent",
         "      turnover. Treat this as an UPPER BOUND on real turnover.",
         "    * Upper-bound is CONSERVATIVE for sample sizing (you will size up) and",
         "      ANTI-conservative for the weak-supervision assumption (real pairs are",
         "      more 'unchanged' than this suggests). State which use you are making.",
         "    * C-CAP 2016 and 2021 are different vintages of the same product; some",
         "      apparent change is method revision, not trees (cf lit ID 167, Seattle).",
         "    * Decimated sample; proportions are robust, exact counts are not."]

    txt = "\n".join(L)
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"turnover_{label}.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / f"turnover_{label}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "date_a", "date_b", "gap_years", "n_valid",
                    "stable_canopy", "stable_non", "loss", "gain",
                    "discordance_pct", "net_change_pp", "annualised_loss_pct"])
        w.writerow([label, R["a"], R["b"], years, n, R["stable_canopy"], R["stable_non"],
                    R["loss"], R["gain"], round(disc_pc, 3),
                    round(pc("gain") - pc("loss"), 3), round(ann, 3)])
    print(f"\n[turnover] wrote {QC_DIR / f'turnover_{label}.txt'}")
    return disc_pc


def main():
    argv = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(description="Measure canopy turnover between two reference dates.")
    ap.add_argument("--a", default="ccap_2016_hires_lc.tif")
    ap.add_argument("--b", default="ccap_2021_hires_lc.tif")
    ap.add_argument("--years", type=float, default=5.0)
    ap.add_argument("--label", default="ccap_2016_2021")
    ap.add_argument("--decim", type=int, default=8)
    ap.add_argument("--zero-is-data", action="store_true",
                    help="Treat 0 as a REAL class rather than nodata. Required for the NDVI "
                         "references (0 = non-vegetated); leave off for C-CAP (0 = nodata).")
    ap.add_argument("--canopy-codes", default=None,
                    help="Comma-separated canopy class codes. Default = C-CAP forest+forested "
                         "wetland. For the NDVI references use 2 (0 non-veg, 1 grass, 2 canopy).")
    args = ap.parse_args(argv)

    codes = ([int(x) for x in args.canopy_codes.split(",")]
             if args.canopy_codes else CCAP_CANOPY)
    print(f"[turnover] canopy codes = {codes}")
    print(f"[turnover] zero treated as {'DATA' if args.zero_is_data else 'NODATA'}")
    R = turnover(resolve(args.a), resolve(args.b), args.decim, codes,
                 zero_is_nodata=not args.zero_is_data)
    disc = report(R, args.years, args.label)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_turnover_{args.label}_{ts}.log").write_text(
            f"phase4_qc_turnover.py {args.a} vs {args.b} gap={args.years} "
            f"n={R['n']} discordance={disc:.3f}%\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()

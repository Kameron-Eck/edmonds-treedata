"""
+==================================================================+
  PHASE 4 - IS AN ACQUISITION LEAF-OFF? (open question Q84)
  Edmonds Temporal Active Learning Pipeline

  WHY
  ---
  The Puget Sound regional orthophoto consortium (King County lead, 88
  participants) specifies acquisition during LEAF-OFF season, March-May.
  NAIP specifies LEAF-ON, peak growing season. Our 18 acquisitions mix
  the two and nothing in the pipeline accounts for it.

  If 2020 - our ONE hand-labelled year - is leaf-off, then the labels
  omit deciduous canopy by construction, and the conifer-only blind
  spot, the recall-by-height staircase and finding 3 (model strength
  does not move recall) all have a PHYSICAL rather than algorithmic
  explanation. See Scripts/litwatch_robustness.md iteration 45.

  THE TEST - needs no species map and no acquisition metadata
  -----------------------------------------------------------
  Take pixels that a canopy mask calls CANOPY, and look at the
  distribution of greenness (GRVI) inside them.

    LEAF-ON  -> canopy is green. GRVI unimodal and positive.
    LEAF-OFF -> conifers stay green, deciduous crowns are bare grey/brown.
                GRVI becomes BIMODAL, with a substantial low/negative mode.

  The low-greenness FRACTION of known canopy is therefore a direct
  leaf-off signature, and comparing it against a known LEAF-ON
  acquisition (NAIP, by specification) calibrates it.

  Reads a modest grid of windows rather than the whole 27 GB ortho.

  USAGE
    py -3.12 phase4_qc_leafoff.py                        # 2020 vs 2023n NAIP
    py -3.12 phase4_qc_leafoff.py --img <tif> --label X

  OUTPUT
    phase4/qc/leafoff_{label}.txt / .csv
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
from rasterio.windows import Window
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402

# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
import sys as _sys_lake
from pathlib import Path as _P_lake
_sys_lake.path.insert(0, str(_P_lake(__file__).resolve().parents[1] / "pipeline"))
from lake import BASE  # noqa: E402
QC_DIR = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "phase4" / "logs"
IMG_DIR = BASE / "Full_Image" / "Pipeline Imagery"
MASK_2020 = BASE / "phase3" / "edmonds_canopy_mask_2020.tif"
_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")


def resolve(name):
    for d in (IMG_DIR, _LOCAL_IMG, QC_DIR):
        p = d / name
        if p.exists():
            return p
    raise FileNotFoundError(name)


def grvi(r, g):
    r = r.astype(np.float32)
    g = g.astype(np.float32)
    den = g + r
    out = np.full(r.shape, np.nan, dtype=np.float32)
    ok = den > 12          # skip near-black pixels (deep shadow / nodata)
    out[ok] = (g[ok] - r[ok]) / den[ok]
    return out


def sample(img_path, mask_path, n_side, win, min_canopy):
    """Grid-sample windows; keep those with enough canopy; return GRVI over canopy."""
    vals = []
    kept = tot = 0
    with rasterio.open(mask_path) as M, rasterio.open(img_path) as I:
        same_grid = (I.width, I.height) == (M.width, M.height) and I.crs == M.crs
        H, W = M.height, M.width
        ys = np.linspace(win, H - 2 * win, n_side).astype(int)
        xs = np.linspace(win, W - 2 * win, n_side).astype(int)
        for y in ys:
            for x in xs:
                tot += 1
                w = Window(int(x), int(y), win, win)
                m = M.read(1, window=w)
                can = m > 0
                if can.mean() < min_canopy:
                    continue
                if same_grid:
                    rgb = I.read((1, 2, 3), window=w)
                else:
                    # reproject the same ground window onto the image grid
                    bounds = rasterio.windows.bounds(w, M.transform)
                    with WarpedVRT(I, crs=M.crs, transform=M.transform,
                                   width=M.width, height=M.height,
                                   resampling=Resampling.bilinear) as v:
                        rgb = v.read((1, 2, 3), window=w)
                gv = grvi(rgb[0], rgb[1])
                sel = gv[can & np.isfinite(gv)]
                if sel.size:
                    vals.append(sel)
                    kept += 1
    if not vals:
        raise SystemExit("[leafoff] ABORT: no windows met the canopy threshold.")
    return np.concatenate(vals), kept, tot


def report(v, kept, tot, label, img_name):
    q = np.percentile(v, [5, 10, 25, 50, 75, 90, 95])
    low = float((v < 0.02).mean())
    neg = float((v < 0.0).mean())
    L = [f"LEAF-OFF TEST - {label}",
         f"  imagery : {img_name}",
         f"  canopy pixels sampled : {v.size:,}  ({kept} of {tot} windows kept)",
         "",
         "  GRVI = (G-R)/(G+R) over pixels the 2020 canopy mask calls CANOPY",
         f"    p05 {q[0]:+.4f}   p10 {q[1]:+.4f}   p25 {q[2]:+.4f}",
         f"    p50 {q[3]:+.4f}   p75 {q[4]:+.4f}   p90 {q[5]:+.4f}   p95 {q[6]:+.4f}",
         f"    mean {v.mean():+.4f}   sd {v.std():.4f}",
         "",
         f"  LOW-GREENNESS FRACTION (GRVI < 0.02) : {low*100:6.2f}%",
         f"  NEGATIVE  fraction     (GRVI < 0)    : {neg*100:6.2f}%",
         "",
         "  HOW TO READ",
         "    LEAF-ON  -> canopy is green: unimodal, positive, small low-fraction.",
         "    LEAF-OFF -> conifers stay green but deciduous crowns are bare:",
         "                BIMODAL, with a substantial low/negative mode.",
         "    The low-greenness fraction is the signature. Compare it against a",
         "    known LEAF-ON acquisition (NAIP is leaf-on BY SPECIFICATION) rather",
         "    than against an absolute threshold - colour balance differs by sensor.",
         "",
         "  CAVEATS",
         "    * The canopy mask is itself a MODEL OUTPUT with the very blind spot",
         "      under investigation. If it already omits bare deciduous crowns, this",
         "      test UNDERSTATES the low-greenness fraction - i.e. it is biased",
         "      AGAINST finding leaf-off. A positive result is therefore strong.",
         "    * Deep shadow is excluded (R+G <= 12) but thin shadow is not, and",
         "      leaf-off flights have LOW SUN ANGLE, so shadow and phenology are",
         "      correlated. Do not read the low mode as purely deciduous.",
         "    * Grid windows, not a probability sample. Indicative, not an estimate."]
    txt = "\n".join(L)
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"leafoff_{label}.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / f"leafoff_{label}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "imagery", "n_px", "windows_kept", "windows_tried",
                    "p05", "p25", "p50", "p75", "p95", "mean", "sd",
                    "frac_lt_002", "frac_negative"])
        w.writerow([label, img_name, v.size, kept, tot,
                    *[round(float(x), 4) for x in (q[0], q[2], q[3], q[4], q[6])],
                    round(float(v.mean()), 4), round(float(v.std()), 4),
                    round(low, 4), round(neg, 4)])
    print(f"\n[leafoff] wrote {QC_DIR / f'leafoff_{label}.txt'}")
    return low


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(description="Detect leaf-off conditions from canopy greenness.")
    ap.add_argument("--img", default="2020_coe_rgb.tif")
    ap.add_argument("--label", default="2020_coe")
    ap.add_argument("--mask", default=str(MASK_2020))
    ap.add_argument("--n-side", type=int, default=4, help="grid is n_side x n_side windows")
    ap.add_argument("--win", type=int, default=1200, help="window size in mask pixels")
    ap.add_argument("--min-canopy", type=float, default=0.15)
    args = ap.parse_args(argv)

    img = resolve(args.img)
    print(f"[leafoff] imagery = {img}")
    print(f"[leafoff] mask    = {args.mask}")
    v, kept, tot = sample(img, Path(args.mask), args.n_side, args.win, args.min_canopy)
    low = report(v, kept, tot, args.label, Path(img).name)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_leafoff_{args.label}_{ts}.log").write_text(
            f"phase4_qc_leafoff.py img={Path(img).name} n_px={v.size} "
            f"windows={kept}/{tot} frac_lt_002={low:.4f}\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()

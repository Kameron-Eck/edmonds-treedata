r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — SCORE EVERY YEAR ON THE SAME GROUND
  Edmonds Temporal Active Learning Pipeline

  THE QUESTION IT WAS BUILT FOR  (STATE result 12c, 2026-08-18)
  ------------------------------------------------------------------
  Kam noticed the 2016 imagery does not cover Edmonds. It covers 41.9% of
  the study area — a central coastal band — while 2000 / 2013 / 2015 cover
  100% and C-CAP covers 53.1%.

  Because every score intersects with C-CAP, that means the cross-year
  comparison in STATE result (7) was computed on DIFFERENT GROUND:

      2000 / 2002 / 2013 / 2015   scored on ~C-CAP's 53.1%
      2016                        scored on its own 41.9% SUBSET

  and the headline of (7e) — "2016 is the outlier at 66.2% deep misses" —
  compares a central band against a larger one. 2016's band excludes the
  northern forest and skews suburban, which is the KNOWN blind spot, so
  part of that 66.2% could be geography rather than a model property.

  THE TEST
  --------
  Re-score every year INSIDE THE 2016 FOOTPRINT, on one grid, at one fixed
  threshold, against the same C-CAP forest classes. Then compare each
  year's extent-matched deep-miss share with its full-extent value:

    * gap SURVIVES  -> 2016 really is structurally different. Result (7e)
                       stands and the geography caveat can be retired.
    * gap COLLAPSES -> the "outlier" was the footprint. (7e) must be
                       withdrawn, and every cross-year comparison in this
                       project has to be extent-matched from now on.

  Everything is warped onto ONE grid derived from the 2016 raster, so no
  year gets a denominator the others do not.

  USAGE
    py -3.12 phase4_qc_extent_matched.py
    py -3.12 phase4_qc_extent_matched.py --cell-m 2.0 --thresh 0.5

  OUTPUT
    phase4/qc/extent_matched.txt / .csv
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
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from phase4seg.names import clean_argv  # noqa: E402

# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
from lake import BASE  # noqa: E402
QC_DIR = BASE / "phase4" / "qc"
MASKS = BASE / "phase4" / "masks"
LOGS_DIR = BASE / "phase4" / "logs"
_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"

FOREST_CODES = [9, 10, 11]          # == phase4_qc_forest_misses.DEFAULT_FOREST_CODES
EXTENT_SRC = "2016_snoh_rgbi.tif"   # the limiting footprint
GRID_CRS = "EPSG:26910"             # metric, matches C-CAP

# year -> (prob raster, C-CAP epoch). Same recipe family as result (7):
# the _citywide_rgb rasters, and 2016's native coarse-recipe raster.
YEARS = [
    ("2000", "edmonds_canopy_prob_2000_citywide_rgb.tif", "ccap_2016_hires_lc.tif"),
    ("2002", "edmonds_canopy_prob_2002_citywide_rgb.tif", "ccap_2016_hires_lc.tif"),
    ("2013", "edmonds_canopy_prob_2013_citywide_rgb.tif", "ccap_2016_hires_lc.tif"),
    ("2015", "edmonds_canopy_prob_2015_citywide_rgb.tif", "ccap_2016_hires_lc.tif"),
    ("2016", "edmonds_canopy_prob_2016.tif", "ccap_2016_hires_lc.tif"),
]
# full-extent deep-miss shares already measured, for the side-by-side
FULL_EXTENT_DEEP = {"2000": 0.277, "2002": 0.318, "2013": 0.308,
                    "2015": 0.482, "2016": 0.662}


def resolve(name, *dirs):
    for d in dirs:
        p = Path(d) / name
        if p.exists():
            return p
    raise FileNotFoundError(name)


def build_grid(cell_m):
    """One grid for everybody, from the 2016 footprint, in GRID_CRS."""
    src = resolve(EXTENT_SRC, _LOCAL_IMG, _DRIVE_IMG)
    with rasterio.open(src) as s:
        w, s_, e, n = transform_bounds(s.crs, GRID_CRS, *s.bounds, densify_pts=21)
    W = int((e - w) // cell_m)
    H = int((n - s_) // cell_m)
    return from_origin(w, n, cell_m, cell_m), W, H, (w, s_, e, n)


def score(year, prob_name, ccap_name, transform, W, H, thresh):
    prob_p = MASKS / prob_name
    if not prob_p.exists():
        return None
    ccap_p = resolve(ccap_name, _LOCAL_IMG, _DRIVE_IMG)

    def warp(path, **kw):
        with rasterio.open(path) as src:
            with WarpedVRT(src, crs=GRID_CRS, transform=transform, width=W, height=H,
                           resampling=Resampling.nearest, **kw) as v:
                return v.read(1), src.nodata

    pr, pr_nod = warp(prob_p)
    rc, cc_nod = warp(ccap_p)

    nod = 255 if pr_nod is None else pr_nod
    valid = pr != nod
    if cc_nod is not None:
        valid &= rc != cc_nod
    valid &= rc != 0
    forest = valid & np.isin(rc, FOREST_CODES)

    called = pr >= thresh * 254.0
    tp = int((forest & called).sum())
    fn = int((forest & ~called).sum())
    if tp + fn == 0:
        return None
    miss = pr[forest & ~called].astype(np.float32)
    deep = float((miss < 0.12 * 254).mean())
    very = float((miss < 0.06 * 254).mean())
    return {"year": year, "prob": prob_name, "n_forest": tp + fn,
            "recall": tp / (tp + fn), "deep": deep, "very_deep": very,
            "n_valid": int(valid.sum())}


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(
        description="Re-score every year inside the 2016 footprint, on one grid.")
    ap.add_argument("--cell-m", type=float, default=2.0)
    ap.add_argument("--thresh", type=float, default=0.5)
    args = ap.parse_args(argv)

    transform, W, H, bnds = build_grid(args.cell_m)
    print(f"[extent-matched] grid {W}x{H} @ {args.cell_m} m in {GRID_CRS}")
    print(f"[extent-matched] bounds {bnds}")
    print(f"[extent-matched] forest codes {FOREST_CODES} · thresh {args.thresh}")

    rows = []
    for year, prob, ccap in YEARS:
        r = score(year, prob, ccap, transform, W, H, args.thresh)
        if r is None:
            print(f"  ! {year}: no data on this grid — skipped")
            continue
        rows.append(r)
        print(f"  ✓ {year}: recall {r['recall']:.4f}  deep {100*r['deep']:.1f}%  "
              f"forest cells {r['n_forest']:,}")

    L = ["EVERY YEAR SCORED ON THE SAME GROUND (the 2016 footprint)",
         f"  grid {W}x{H} @ {args.cell_m} m · {GRID_CRS} · thresh {args.thresh}",
         f"  C-CAP forest codes {FOREST_CODES}",
         "  WHY: 2016 covers 41.9% of the study area, the others 100%, so the",
         "  cross-year comparison in STATE (7) used different ground per year.",
         "",
         f"  {'year':<6} {'recall':>8} {'deep<.12':>9} {'<.06':>7} {'forest cells':>14}"
         f" {'deep FULL-extent':>17} {'shift':>8}"]
    for r in rows:
        fe = FULL_EXTENT_DEEP.get(r["year"])
        shift = (r["deep"] - fe) if fe is not None else float("nan")
        fe_s = f"{100*fe:.1f}%" if fe is not None else "  n/a"
        L.append(f"  {r['year']:<6} {r['recall']:>8.4f} {100*r['deep']:>8.1f}% "
                 f"{100*r['very_deep']:>6.1f}% {r['n_forest']:>14,} {fe_s:>17}"
                 f" {100*shift:>+7.1f}")

    d = {r["year"]: r["deep"] for r in rows}
    L.append("")
    if "2016" in d and len(d) > 1:
        others = [v for k, v in d.items() if k != "2016"]
        gap_matched = d["2016"] - max(others)
        gap_full = FULL_EXTENT_DEEP["2016"] - max(
            v for k, v in FULL_EXTENT_DEEP.items() if k != "2016")
        L += [f"  -- THE TEST " + "-" * 46,
              f"     2016 minus the next-deepest year:",
              f"       full extent      {100*gap_full:+.1f} pp",
              f"       extent-matched   {100*gap_matched:+.1f} pp",
              ""]
        if gap_matched > 0.10:
            L += ["     -> THE GAP SURVIVES. 2016 is structurally different, not just",
                  "        differently framed. STATE (7e) stands; retire the geography",
                  "        caveat but keep the footprint note for AREA-based claims."]
        elif gap_matched < 0.04:
            L += ["     -> THE GAP COLLAPSES. '2016 is the outlier' was the FOOTPRINT.",
                  "        WITHDRAW STATE (7e) and extent-match every cross-year",
                  "        comparison in this project before quoting it again."]
        else:
            L += ["     -> PARTLY GEOGRAPHIC. The gap shrinks but does not vanish, so",
                  "        2016 is somewhat different AND somewhat differently framed.",
                  "        Quote only the extent-matched number."]

    L += ["",
          "  -- CAVEATS " + "-" * 47,
          "     * Restricting to a common footprint does NOT make the years",
          "       equivalent: they still differ in sensor, season and radiometry.",
          "       It removes ONE confound, the biggest and the most avoidable.",
          "     * C-CAP 2016 is applied to 2000/2002/2013/2015, so real canopy",
          "       change between those dates still counts as model error.",
          "     * Nearest-neighbour warp onto a 2 m grid; the fine years are",
          "       down-sampled, which slightly smooths their probability field.",
          "     * The 2016 raster is 15.4 cm imagery trained as a coarse year",
          "       (STATE 12d) — that difference is NOT removed here."]

    txt = "\n".join(L)
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / "extent_matched.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / "extent_matched.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "prob", "recall", "deep_lt_012", "deep_lt_006",
                    "forest_cells", "valid_cells", "deep_full_extent", "cell_m", "thresh"])
        for r in rows:
            w.writerow([r["year"], r["prob"], round(r["recall"], 4), round(r["deep"], 4),
                        round(r["very_deep"], 4), r["n_forest"], r["n_valid"],
                        FULL_EXTENT_DEEP.get(r["year"], ""), args.cell_m, args.thresh])
    print(f"\n[extent-matched] wrote {QC_DIR / 'extent_matched.txt'}")

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_extent_matched_{ts}.log").write_text(
            f"phase4_qc_extent_matched.py cell_m={args.cell_m} thresh={args.thresh} "
            f"years={[r['year'] for r in rows]}\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()

r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — WHAT IS THE NDVI REFERENCE ACTUALLY OVER-CALLING?
  Edmonds Temporal Active Learning Pipeline

  THE QUESTION IT WAS BUILT FOR  (STATE results 5, 9, 15c — 2026-08-18)
  ------------------------------------------------------------------
  Latent-class modelling put true canopy prevalence near .29 while the
  NDVI+CHM reference says .377, and I read the ~8 pp surplus as "shrubs and
  hedges in the 2-5 m band", because the NDVI ref's specificity is lowest
  there.

  Then the NOAA hi-res canopy product turned up, which separates TREE from
  SHRUB explicitly — and its SHRUB class is only 1.25% of the study grid.
  If shrubs are one point of the map, they cannot be eight points of the
  disagreement. So the "surplus = shrubs" reading is probably wrong, and
  what the NDVI reference is over-calling is genuinely unknown.

  THE TEST
  --------
  Cross the NDVI reference against the NOAA canopy classes on one grid,
  VINTAGE-MATCHED (ndvi_ref_2021s vs the 2021 canopy product, so canopy
  change between dates cannot explain the disagreement), and characterise
  every disputed pixel by CHM height and greenness.

  The decisive cell is NDVI-says-canopy / NOAA-says-neither:
     * tall + green -> real trees NOAA misses (NDVI ref is RIGHT, and the
       low latent prevalence is an artefact of two sources sharing a
       stand-based definition)
     * short        -> the NDVI ref is counting low vegetation that is
       neither tree nor NOAA-shrub — lawn edges, hedges, garden beds
     * not green    -> the NDVI ref's own threshold is leaking

  USAGE
    py -3.12 phase4_qc_ndvi_vs_tree.py --year 2021s
    py -3.12 phase4_qc_ndvi_vs_tree.py --year 2016    (5-yr gap — see caveat)

  OUTPUT
    phase4/qc/ndvi_vs_tree_{year}.txt / .csv
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
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE
QC_DIR = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "phase4" / "logs"
_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")

NOAA_CANOPY = Path(r"C:\Users\Kameron\Documents\ArcGIS\NOAA\Tree Canopy"
                   r"\wa_2021_ccap_v2_hires_canopy.tif")
CHM = _LOCAL_IMG / "lidar_snoh_chm.tif"
DN_PER_M = 1.0 / 0.2
GRID_CRS = "EPSG:26910"
NDVI_CANOPY, NDVI_GRASS = 2, 1
TREE, SHRUB = 1, 2


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(
        description="Cross the NDVI reference with the NOAA tree/shrub product.")
    ap.add_argument("--year", default="2021s")
    ap.add_argument("--cell-m", type=float, default=2.0)
    args = ap.parse_args(argv)

    ndvi_p = QC_DIR / f"ndvi_ref_{args.year}.tif"
    for p in (ndvi_p, NOAA_CANOPY, CHM):
        if not p.exists():
            raise SystemExit(f"missing {p}")

    # grid = the NDVI reference's own footprint (the limiting layer)
    with rasterio.open(ndvi_p) as s:
        w, s_, e, n = transform_bounds(s.crs, GRID_CRS, *s.bounds, densify_pts=21)
    W, H = int((e - w) // args.cell_m), int((n - s_) // args.cell_m)
    T = from_origin(w, n, args.cell_m, args.cell_m)
    print(f"[ndvi-vs-tree] {args.year} · grid {W}x{H} @ {args.cell_m} m ({GRID_CRS})")

    def read(p, **kw):
        with rasterio.open(p) as src:
            with WarpedVRT(src, crs=GRID_CRS, transform=T, width=W, height=H,
                           resampling=Resampling.nearest, **kw) as v:
                return v.read(1), src.nodata

    nd, nd_nod = read(ndvi_p)
    cn, _ = read(NOAA_CANOPY)
    dn, _ = read(CHM, src_nodata=0, nodata=0)
    hgt = (dn.astype(np.float32) - 1.0) / DN_PER_M
    hgt[dn == 0] = np.nan

    valid = np.ones_like(nd, dtype=bool)
    if nd_nod is not None:
        valid &= nd != nd_nod
    valid &= (nd == NDVI_CANOPY) | (nd == NDVI_GRASS) | (nd == 0)

    ndvi_can = valid & (nd == NDVI_CANOPY)
    noaa_tree = valid & (cn == TREE)
    noaa_shrub = valid & (cn == SHRUB)
    noaa_none = valid & (cn == 0)
    nv = int(valid.sum())

    def pct(m):
        return 100.0 * int(m.sum()) / max(nv, 1)

    L = [f"WHAT IS THE NDVI REFERENCE OVER-CALLING? — {args.year}",
         f"  ndvi ref : {ndvi_p.name}",
         f"  tree/shrub: {NOAA_CANOPY.name}  (class 1 = tree, 2 = shrub)",
         f"  grid {W}x{H} @ {args.cell_m} m · {nv:,} valid cells",
         "  VINTAGE: " + ("MATCHED (both 2021) — canopy change cannot explain the gap."
                          if args.year == "2021s" else
                          f"MISMATCHED ({args.year} vs 2021 canopy) — some disagreement is REAL CHANGE."),
         "",
         "  -- WHAT EACH SOURCE CALLS CANOPY " + "-" * 25,
         f"     NDVI ref canopy      {pct(ndvi_can):>6.2f}%",
         f"     NOAA tree            {pct(noaa_tree):>6.2f}%",
         f"     NOAA tree+shrub      {pct(noaa_tree | noaa_shrub):>6.2f}%",
         "",
         "  -- WHERE THE NDVI REF'S CANOPY LANDS " + "-" * 21,
         f"     {'NOAA says':<14} {'% of NDVI canopy':>17} {'CHM p50':>9} {'>=3m':>7}"]

    rows = []
    for name, m in (("tree", ndvi_can & noaa_tree),
                    ("shrub", ndvi_can & noaa_shrub),
                    ("NEITHER", ndvi_can & noaa_none)):
        share = 100.0 * int(m.sum()) / max(int(ndvi_can.sum()), 1)
        h = hgt[m]
        h = h[np.isfinite(h)]
        p50 = float(np.median(h)) if h.size else float("nan")
        ge3 = 100.0 * float((h >= 3).mean()) if h.size else float("nan")
        L.append(f"     {name:<14} {share:>16.2f}% {p50:>9.2f} {ge3:>6.1f}%")
        rows.append(dict(year=args.year, group=f"ndvi_canopy_and_noaa_{name}",
                         share_of_ndvi_canopy=round(share, 2),
                         chm_p50=round(p50, 2) if h.size else "",
                         pct_ge_3m=round(ge3, 1) if h.size else "",
                         n=int(m.sum())))

    # the decisive cell
    disputed = ndvi_can & noaa_none
    hd = hgt[disputed]
    hd = hd[np.isfinite(hd)]
    L += ["",
          "  -- THE DECISIVE CELL: NDVI says canopy, NOAA says neither " + "-" * 1,
          f"     {int(disputed.sum()):,} cells = {100*int(disputed.sum())/max(nv,1):.2f}% "
          f"of the grid, {100*int(disputed.sum())/max(int(ndvi_can.sum()),1):.1f}% of NDVI canopy"]
    if hd.size:
        L += [f"     CHM height p10/p50/p90 : {np.percentile(hd,10):.2f} / "
              f"{np.percentile(hd,50):.2f} / {np.percentile(hd,90):.2f} m",
              f"     share >= 3 m           : {100*(hd>=3).mean():.1f}%",
              f"     share >= 5 m           : {100*(hd>=5).mean():.1f}%"]
        med = float(np.median(hd))
        L.append("")
        if med >= 8.0:
            L += ["     -> THE DISPUTED PIXELS ARE TALL. These look like REAL TREES that the",
                  "        NOAA product misses, not shrubs. That would mean the NDVI ref is",
                  "        closer to right than latent class suggested, and that the low",
                  "        latent prevalence came from TWO sources sharing a stand-based",
                  "        definition rather than from the NDVI ref over-calling.",
                  "        RE-OPENS result (5). Do NOT treat ~.29 as settled."]
        elif med >= 3.0:
            L += ["     -> MID-HEIGHT. Neither clean trees nor ground: hedges, garden beds,",
                  "        young/ornamental crowns. This is the population U1 has to rule on",
                  "        explicitly — it is exactly what a written definition decides."]
        else:
            L += ["     -> THE DISPUTED PIXELS ARE LOW. The NDVI ref IS counting vegetation",
                  "        that is neither tree nor NOAA-shrub. Its surplus is low greenery,",
                  "        so result (5)'s reading survives in substance even though the",
                  "        'shrub' label was wrong."]

    L += ["",
          "  -- CAVEATS " + "-" * 47,
          "     * NOAA canopy is a MODEL PRODUCT too, not truth. Where it and the NDVI",
          "       ref disagree, this says WHAT the disagreement looks like, not who wins.",
          "     * The NDVI ref requires CHM >= 2 m by construction, so it cannot call",
          "       canopy below 2 m at all — the disputed set is 2 m+ by definition.",
          "     * CHM is ~2016 and covers ~83% of the analysis area; height rows are",
          "       conditioned on CHM presence.",
          "     * 2 m grid, nearest-neighbour: thin features (hedgerows) are under-",
          "       represented relative to their true area."]

    txt = "\n".join(L)
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"ndvi_vs_tree_{args.year}.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / f"ndvi_vs_tree_{args.year}.csv", "w",
                 encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print(f"\n[ndvi-vs-tree] wrote {QC_DIR / f'ndvi_vs_tree_{args.year}.txt'}")

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_ndvi_vs_tree_{args.year}_{ts}.log").write_text(
            f"phase4_qc_ndvi_vs_tree.py year={args.year} valid={nv}\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()

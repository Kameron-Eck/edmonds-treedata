"""
+==================================================================+
  PHASE 4 - BUILD A CITY-CLIPPED C-CAP REFERENCE  (Q99/Q100/Q101/Q102)
  Edmonds Temporal Active Learning Pipeline

  WHY
  ---
  The canonical reference `ccap_2016_hires_lc.tif` covers 19.71 of the
  city's 24.65 km2 - **80.0% of Edmonds** - stopping 3.06 km short of the
  northern boundary. Every headline recall/precision figure, and the
  canopy fractions behind the 29.5% vs 37.7% policy dispute, are computed
  on four fifths of the city without that being stated anywhere.
  See Scripts/litwatch_robustness.md iteration 56.

  `ccap_*_hires_lc_snohfull.tif` covers the WHOLE COUNTY and therefore
  contains the missing strip. This clips it to the actual city boundary,
  producing - for the first time - a reference whose footprint is the
  deliverable's footprint.

  ALSO REPORTS, because it is free once the mask exists:
    * canopy fraction over the whole city;
    * canopy fraction SOUTH of the old clip's northern edge (the area we
      have been evaluating) vs NORTH of it (the omitted fifth), which
      tells us whether the omission was merely smaller or also BIASED.

  USAGE
    py -3.12 phase4_build_ccap_city.py                    # 2016
    py -3.12 phase4_build_ccap_city.py --src <tif> --label 2021

  OUTPUT
    D:/edmonds-pipeline/Imagery/ccap_{label}_edmonds.tif   (or Drive)
    phase4/qc/ccap_city_{label}.txt
+==================================================================+
"""

import argparse
import datetime as _dt
import io
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.features import geometry_mask
import sys as _sys_for_names
from pathlib import Path as _P_for_names
_sys_for_names.path.insert(0, str(_P_for_names(__file__).resolve().parents[1] / "pipeline"))
from phase4seg.names import clean_argv  # noqa: E402

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE
QC_DIR = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "phase4" / "logs"
BOUNDARY = BASE / "City Boundry" / "Edmonds Boundry.shp"
_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")

CCAP_CANOPY = [9, 10, 11, 13, 16]
OLD_CLIP_NORTH_UTM = 5297858.0        # northern edge of ccap_*_hires_lc, UTM 10N


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser(description="Clip county-wide C-CAP to the Edmonds boundary.")
    ap.add_argument("--src", default="ccap_2016_hires_lc_snohfull.tif")
    ap.add_argument("--label", default="2016")
    ap.add_argument("--boundary", default=str(BOUNDARY))
    args = ap.parse_args(argv)

    import geopandas as gpd

    src = _LOCAL_IMG / args.src
    if not src.exists():
        raise SystemExit(f"[ccap-city] ABORT: {src} not found")
    out = _LOCAL_IMG / f"ccap_{args.label}_edmonds.tif"

    g = gpd.read_file(args.boundary)
    print(f"[ccap-city] boundary {args.boundary}  crs={g.crs}  features={len(g)}")

    with rasterio.open(src) as s:
        gg = g.to_crs(s.crs)
        geom = gg.union_all() if hasattr(gg, "union_all") else gg.unary_union
        win = from_bounds(*geom.bounds, transform=s.transform)
        win = win.round_offsets().round_lengths()
        a = s.read(1, window=win)
        tr = s.window_transform(win)
        prof = s.profile.copy()
        prof.update(height=a.shape[0], width=a.shape[1], transform=tr,
                    compress="deflate", predictor=2, tiled=True, nodata=0)
        crs = s.crs

    outside = geometry_mask([geom], out_shape=a.shape, transform=tr, invert=False)
    a = a.copy()
    a[outside] = 0                                  # 0 = nodata in C-CAP
    inside = ~outside

    with rasterio.open(out, "w", **prof) as d:
        d.write(a, 1)

    # north/south split at the OLD clip's northern edge, in this raster's CRS
    rows, cols = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    ys = tr.f + tr.e * (rows + 0.5)                 # northing of each cell
    north = inside & (ys > OLD_CLIP_NORTH_UTM)      # the omitted fifth
    south = inside & (ys <= OLD_CLIP_NORTH_UTM)     # what we have been evaluating

    def frac(m):
        n = int(m.sum())
        if not n:
            return 0, 0.0
        return n, 100.0 * float(np.isin(a[m], CCAP_CANOPY).sum()) / n

    n_all, f_all = frac(inside)
    n_s, f_s = frac(south)
    n_n, f_n = frac(north)
    px_km2 = abs(tr.a * tr.e) / 1e6

    L = [f"CITY-CLIPPED C-CAP REFERENCE - {args.label}",
         f"  source   : {args.src}",
         f"  boundary : {Path(args.boundary).name}",
         f"  output   : {out}",
         f"  grid     : {a.shape[1]} x {a.shape[0]}  @ {abs(tr.a):.2f} m  {crs}",
         "",
         f"  city cells inside boundary : {n_all:,}  = {n_all*px_km2:.2f} km2",
         f"  CANOPY FRACTION, WHOLE CITY: {f_all:.2f}%",
         "",
         "  SPLIT AT THE OLD CLIP'S NORTHERN EDGE (N 5,297,858)",
         f"    SOUTH - the area we have been evaluating",
         f"        cells {n_s:,} = {n_s*px_km2:.2f} km2 ({100*n_s/max(n_all,1):.1f}% of city)",
         f"        canopy {f_s:.2f}%",
         f"    NORTH - the omitted fifth",
         f"        cells {n_n:,} = {n_n*px_km2:.2f} km2 ({100*n_n/max(n_all,1):.1f}% of city)",
         f"        canopy {f_n:.2f}%",
         "",
         f"  DIFFERENCE (north - south) : {f_n - f_s:+.2f} pp",
         "",
         "  HOW TO READ",
         "    If north and south have similar canopy fractions, the old clip was a",
         "    SMALLER sample but not a biased one, and citywide figures shift only",
         "    slightly. If they differ, the omission was BIASED and every stratified",
         "    design built on the old footprint inherits it.",
         "",
         "  CAVEAT",
         "    C-CAP carries its own error (~84% OA regionally, lit ID 77) and the",
         "    hi-res product was never validated at single-pixel scale (lit ID 77).",
         "    These fractions are the reference's opinion, not ground truth."]

    txt = "\n".join(L)
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"ccap_city_{args.label}.txt").write_text(txt, encoding="utf-8")
    print(f"\n[ccap-city] wrote {out}")
    print(f"[ccap-city] wrote {QC_DIR / f'ccap_city_{args.label}.txt'}")

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_build_ccap_city_{args.label}_{ts}.log").write_text(
            f"src={args.src} out={out.name} city_km2={n_all*px_km2:.2f} "
            f"canopy_all={f_all:.2f} canopy_south={f_s:.2f} canopy_north={f_n:.2f}\n",
            encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()

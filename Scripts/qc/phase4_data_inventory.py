r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — DATA INVENTORY: every raster, its TRUE geometry, its coverage
  Edmonds Temporal Active Learning Pipeline

  WHY THIS EXISTS  (Kam, 2026-08-18: "we should be performing better
  metadata management")
  ------------------------------------------------------------------
  Three separate bugs in one day, all of them metadata bugs, all of them
  invisible until something downstream looked wrong:

    1. The 2016 ortho covers 41.9% of the study area, not the city. Found
       only because Kam said so; the evidence (a sentinel site "outside
       2016 imagery extent") had been printed and ignored.
    2. phase4seg/config.py's gsd_cm is the CRS pixel size x 100, which
       assumes every CRS is metric. EPSG:2285 is US SURVEY FEET, so 2016
       is 15.4 cm imagery recorded as 50 cm — and TIER is derived from
       that field.
    3. ccap_2016_hires_lc.tif — the independent reference that gates every
       honest number — is a CLIPPED copy covering 51.9% of the study area,
       while the source in the user's ArcGIS folder covers 91.0%.

  None of these were hard to detect. Nothing was looking.

  WHAT IT DOES
    Walks the known data locations, opens each raster's HEADER ONLY (no
    pixel reads except an optional coverage probe), and records:
      path · role · CRS · CRS LINEAR UNIT · pixel size in CRS units ·
      TRUE GROUND GSD (derived from the WGS84 span and pixel count, so it
      cannot be fooled by feet-vs-metres or Web-Mercator inflation) ·
      bounds · % of the study area covered · dtype · nodata · size
    and flags any raster whose stated and true resolution disagree.

  THE ONE RULE THIS ENFORCES
    TRUE GSD and COVERAGE are computed from the file, never copied from a
    config. A config value is a claim; this is a measurement.

  USAGE
    py -3.12 phase4_data_inventory.py
    py -3.12 phase4_data_inventory.py --deep     (adds real data-coverage %,
                                                  reads pixels, slower)

  OUTPUT
    phase4/qc/data_inventory.csv / .txt
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import io
import sys
from math import cos, radians
from pathlib import Path

import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE
QC_DIR = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "phase4" / "logs"

STUDY_AREA = BASE / "phase3" / "edmonds_canopy_mask_2020.tif"

# (role, directory, glob). Roles are how the pipeline USES the file, which is
# the thing a bare filename never tells you.
SOURCES = [
    ("ortho",      Path(r"D:\edmonds-pipeline\Imagery"), "*_rgb*.tif"),
    ("reference",  Path(r"D:\edmonds-pipeline\Imagery"), "ccap_*.tif"),
    ("height",     Path(r"D:\edmonds-pipeline\Imagery"), "lidar_*.tif"),
    ("mask",       Path(r"D:\edmonds-pipeline\Imagery"), "edmonds_canopy_mask_*.tif"),
    ("model-out",  BASE / "phase4" / "masks", "edmonds_canopy_prob_*.tif"),
    ("study-area", BASE / "phase3", "edmonds_canopy_mask_2020.tif"),
    # external candidates found 2026-08-18 — full-coverage replacements
    ("noaa-src",   Path(r"C:\Users\Kameron\Documents\ArcGIS\NOAA"), "**/*.tif"),
]


def study_bounds():
    with rasterio.open(STUDY_AREA) as s:
        return transform_bounds(s.crs, "EPSG:4326", *s.bounds, densify_pts=21)


def describe(p, ref, deep_grid=None):
    with rasterio.open(p) as s:
        b = transform_bounds(s.crs, "EPSG:4326", *s.bounds, densify_pts=21)
        mid = (b[1] + b[3]) / 2
        km_w = (b[2] - b[0]) * 111.320 * cos(radians(mid))
        true_gsd = km_w * 1000 / s.width if s.width else float("nan")
        unit = s.crs.linear_units if s.crs else "?"
        px = abs(s.transform.a)
        # stated-vs-true: px is in CRS units; if the CRS is not metric, or is
        # Web Mercator, px*100 (what config.py records) is NOT ground cm.
        stated_cm = px * 100.0
        ratio = stated_cm / (true_gsd * 100.0) if true_gsd else float("nan")

        W, S, E, N = ref
        iw = max(0.0, min(E, b[2]) - max(W, b[0]))
        ih = max(0.0, min(N, b[3]) - max(S, b[1]))
        bbox_cov = (iw * ih) / ((E - W) * (N - S)) * 100.0

        data_cov = ""
        if deep_grid is not None:
            T, GW, GH, crs = deep_grid
            try:
                with WarpedVRT(s, crs=crs, transform=T, width=GW, height=GH,
                               resampling=Resampling.nearest) as v:
                    a = v.read(1)
                nod = s.nodata if s.nodata is not None else 0
                data_cov = round(100.0 * float((a != nod).mean()), 1)
            except Exception:
                data_cov = "err"

        return dict(
            path=str(p), name=p.name, crs=str(s.crs), unit=unit,
            px_in_crs_units=round(px, 4), stated_cm=round(stated_cm, 1),
            true_gsd_m=round(true_gsd, 4), gsd_ratio=round(ratio, 2),
            width=s.width, height=s.height, dtype=s.dtypes[0],
            nodata=s.nodata, size_gb=round(p.stat().st_size / 1e9, 3),
            bbox_cov_pct=round(bbox_cov, 1), data_cov_pct=data_cov,
            lon_w=round(b[0], 5), lat_s=round(b[1], 5),
            lon_e=round(b[2], 5), lat_n=round(b[3], 5))


def main():
    argv = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(description="Inventory every raster's true geometry.")
    ap.add_argument("--deep", action="store_true",
                    help="Also measure real DATA coverage (reads pixels; slower).")
    ap.add_argument("--cell-m", type=float, default=8.0)
    args = ap.parse_args(argv)

    if not STUDY_AREA.exists():
        raise SystemExit(f"study area raster missing: {STUDY_AREA}")
    ref = study_bounds()
    print(f"[inventory] study area = {STUDY_AREA.name}  {ref}")

    deep_grid = None
    if args.deep:
        crs = "EPSG:26910"
        with rasterio.open(STUDY_AREA) as s:
            w, s_, e, n = transform_bounds(s.crs, crs, *s.bounds, densify_pts=21)
        GW, GH = int((e - w) // args.cell_m), int((n - s_) // args.cell_m)
        deep_grid = (from_origin(w, n, args.cell_m, args.cell_m), GW, GH, crs)
        print(f"[inventory] deep mode: {GW}x{GH} @ {args.cell_m} m")

    rows, seen = [], set()
    for role, d, pat in SOURCES:
        if not d.exists():
            print(f"  ! {role}: {d} not present — skipped")
            continue
        for p in sorted(d.glob(pat)):
            if not p.is_file() or p.resolve() in seen:
                continue
            seen.add(p.resolve())
            try:
                r = describe(p, ref, deep_grid)
            except Exception as ex:
                print(f"  ! {p.name}: {ex}")
                continue
            r["role"] = role
            rows.append(r)
            print(f"  {role:<11} {p.name:<44} true {r['true_gsd_m']:>6.3f} m  "
                  f"bbox {r['bbox_cov_pct']:>5.1f}%"
                  + (f"  data {r['data_cov_pct']}%" if args.deep else ""))

    # ---------- report ----------
    L = ["DATA INVENTORY — true geometry, measured from the files themselves",
         f"  study area : {STUDY_AREA.name}",
         f"  generated  : {_dt.datetime.now().isoformat(timespec='seconds')}",
         f"  rasters    : {len(rows)}",
         "",
         "  TRUE GSD is derived from the WGS84 span and the pixel count, so it is",
         "  immune to feet-vs-metres and Web-Mercator inflation. 'stated_cm' is what",
         "  a naive px*100 would give — which is what config.py records.",
         "",
         f"  {'role':<11} {'file':<42} {'unit':<11} {'stated':>7} {'TRUE m':>7}"
         f" {'x':>5} {'bbox%':>6}" + ("  data%" if args.deep else "")]
    for r in sorted(rows, key=lambda x: (x["role"], x["name"])):
        L.append(f"  {r['role']:<11} {r['name'][:42]:<42} {r['unit'][:11]:<11} "
                 f"{r['stated_cm']:>7.1f} {r['true_gsd_m']:>7.3f} {r['gsd_ratio']:>5.2f}"
                 f" {r['bbox_cov_pct']:>6.1f}"
                 + (f"  {r['data_cov_pct']}" if args.deep else ""))

    bad = [r for r in rows if r["gsd_ratio"] and abs(r["gsd_ratio"] - 1.0) > 0.05]
    part = [r for r in rows if r["bbox_cov_pct"] < 99.0]
    L += ["", "  -- FLAGS " + "-" * 49]
    if bad:
        L.append(f"  {len(bad)} raster(s) where px*100 MISSTATES ground resolution:")
        for r in sorted(bad, key=lambda x: -abs(x["gsd_ratio"] - 1)):
            L.append(f"     {r['name'][:44]:<44} stated {r['stated_cm']:>6.1f} cm "
                     f"vs true {100*r['true_gsd_m']:>6.1f} cm  ({r['gsd_ratio']:.2f}x)")
        L.append("     -> config.py gsd_cm is derived this way. TIER comes from gsd_cm.")
    if part:
        L.append(f"  {len(part)} raster(s) NOT covering the full study area:")
        for r in sorted(part, key=lambda x: x["bbox_cov_pct"]):
            L.append(f"     {r['name'][:44]:<44} {r['bbox_cov_pct']:>5.1f}% of study bbox")
        L.append("     -> any 'citywide' number from these is scoped to their footprint.")
    if not bad and not part:
        L.append("  none.")

    L += ["", "  -- HOW TO USE THIS " + "-" * 39,
          "     * Before quoting a CITY number, check the source's bbox%/data%.",
          "     * Before comparing two years, check they share a footprint",
          "       (phase4_qc_extent_matched.py scores them on one grid).",
          "     * Before trusting a resolution, read TRUE m, not config.py.",
          "     * Re-run after adding any raster. It is header-only and cheap."]

    txt = "\n".join(L)
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / "data_inventory.txt").write_text(txt, encoding="utf-8")
    if rows:
        cols = ["role", "name", "path", "crs", "unit", "px_in_crs_units", "stated_cm",
                "true_gsd_m", "gsd_ratio", "width", "height", "dtype", "nodata",
                "size_gb", "bbox_cov_pct", "data_cov_pct",
                "lon_w", "lat_s", "lon_e", "lat_n"]
        with io.open(QC_DIR / "data_inventory.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in cols})
    print(f"\n[inventory] wrote {QC_DIR / 'data_inventory.csv'}")

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_data_inventory_{ts}.log").write_text(
            f"phase4_data_inventory.py rasters={len(rows)} gsd_flags={len(bad)} "
            f"partial_coverage={len(part)}\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()

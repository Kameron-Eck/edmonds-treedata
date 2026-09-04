"""Certified-flat scoring — absolute false-positive rates on physically empty
ground, plus the model-free dual-epoch change cell count.

TRUTH: verified_background_lidar_2005_2016.tif (qc/build_lidar_background.py,
2026-08-27): 2 m cells whose max height above ground was < 2 m in BOTH the 2005
PSLC and 2016 USGS point clouds, eroded 6 m. No model, no human, no C-CAP in
the truth definition — anything any product calls canopy here is WRONG absolutely.

Scored products:
  - C-CAP 2016 + C-CAP 2021 hi-res (canopy classes = CCAP_CANOPY from
    phase4_accuracy_sample.py) -> the model-free C-CAP over-call bound.
  - Every edmonds_canopy_prob_*_t1_*.tif at its policy-C deployed threshold
    (indep_thresholds.csv); t1 probs are AOI-restricted so n is small — reported.
  - Named citywide probs at their live thresholds.
Convention: product warped to the vb 2 m grid with Resampling.max — "asserts
vegetation anywhere in the cell" (same convention as build_chm2_2016
verified_background_check). FP rate = called-canopy cells / valid flat cells.

Change count (Idea 2 LOSS, same pass): chm2 (max-warped to the chm2005 2 m
grid) vs chm2005 on dual-covered ground: LOSS = h2005>=5m & h2016<2m;
GAIN = h2005<2m & h2016>=5m. Physical bound, thresholds stated, no model.

Outputs: phase4/qc/certified_flat_scores.csv, certified_change_cells.csv
"""
import csv
import io
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from lake import BASE

IMG = Path(r"D:\edmonds-pipeline\Imagery")
VB = IMG / "verified_background_lidar_2005_2016.tif"
MASKS = BASE / "phase4" / "masks"
QC = BASE / "phase4" / "qc"
OUT = Path(__file__).resolve().parents[3] / "phase4" / "qc"
CCAP_CANOPY = [9, 10, 11, 13, 16]        # phase4_accuracy_sample.py::CCAP_CANOPY
CITYWIDE = [  # (prob file, thresh, note)
    ("edmonds_canopy_prob_2016_fullext_sectors_v1.tif", 0.5223, "2016 fullext (sample_2016 design thresh)"),
    ("edmonds_canopy_prob_2023n.tif", 0.404, "2023n live row"),
]


def warp_max(path, vb_ds, band=1):
    with rasterio.open(path) as src:
        with WarpedVRT(src, crs=vb_ds.crs, transform=vb_ds.transform,
                       width=vb_ds.width, height=vb_ds.height,
                       resampling=Resampling.max) as v:
            return v.read(band), src.nodata


def main():
    vb_ds = rasterio.open(VB)
    bg = vb_ds.read(1) == 1
    n_bg = int(bg.sum())
    cell_km2 = abs(vb_ds.transform.a * vb_ds.transform.e) / 1e6
    print(f"certified-flat cells: {n_bg:,} ({n_bg*cell_km2:.2f} km2)")

    rows = []

    def score(name, called, valid, note):
        v = valid & bg
        n = int(v.sum())
        fp = int((called & v).sum())
        rate = fp / n if n else float("nan")
        rows.append(dict(product=name, n_flat_cells=n, fp_cells=fp,
                         fp_rate=round(rate, 5) if n else "",
                         note=note))
        print(f"  {name:55s} n={n:>9,}  FP={fp:>7,}  rate={rate if n else float('nan'):.4f}")

    for ccap in ("ccap_2016_hires_lc.tif", "ccap_2021_hires_lc.tif"):
        arr, nod = warp_max(IMG / ccap, vb_ds)
        valid = np.ones_like(arr, bool) if nod is None else (arr != nod)
        score(ccap, np.isin(arr, CCAP_CANOPY), valid, "reference product itself")

    thr = {}
    with open(QC / "indep_thresholds.csv", newline="") as f:
        for r in csv.DictReader(f):
            if r["ref"] == "ccap_2021_hires_lc.tif":
                thr[(r["year"], r["run_tag"])] = float(r["thresh"])
    for p in sorted(MASKS.glob("edmonds_canopy_prob_*_t1_*.tif")):
        import re
        m = re.search(r"prob_([0-9a-z]+)_(t1_.+)\.tif", p.name)
        t = thr.get((m.group(1), m.group(2)))
        if t is None:
            continue
        arr, _ = warp_max(p, vb_ds)
        valid = arr != 255
        score(p.name, valid & (arr >= t * 254.0), valid,
              f"t1 arm @ policy-C {t} (AOI-restricted prob; small n)")

    for name, t, note in CITYWIDE:
        p = MASKS / name
        if not p.exists():
            continue
        arr, _ = warp_max(p, vb_ds)
        valid = arr != 255
        score(name, valid & (arr >= t * 254.0), valid, f"citywide @ {t}: {note}")

    OUT.mkdir(parents=True, exist_ok=True)
    with io.open(OUT / "certified_flat_scores.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"wrote {OUT / 'certified_flat_scores.csv'} ({len(rows)} products)")

    # ── dual-epoch physical change count ────────────────────────────────────
    c05 = rasterio.open(IMG / "lidar_chm2005_2m.tif")
    a05 = c05.read(1)
    with rasterio.open(IMG / "lidar_chm2_2016_50cm.tif") as c16:
        with WarpedVRT(c16, crs=c05.crs, transform=c05.transform,
                       width=c05.width, height=c05.height,
                       resampling=Resampling.max) as v:
            a16 = v.read(1)
    both = (a05 > 0) & (a16 > 0)
    h05 = (a05.astype(np.float32) - 1) * 0.2
    h16 = (a16.astype(np.float32) - 1) * 0.2
    loss = both & (h05 >= 5.0) & (h16 < 2.0)
    gain = both & (h05 < 2.0) & (h16 >= 5.0)
    cell = abs(c05.transform.a * c05.transform.e)
    with io.open(OUT / "certified_change_cells.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["quantity", "cells", "km2", "definition"])
        w.writerow(["dual_covered", int(both.sum()), round(both.sum()*cell/1e6, 3),
                    "DN>0 in both chm2005(2m) and chm2 max-warped to its grid"])
        w.writerow(["loss_2005_2016", int(loss.sum()), round(loss.sum()*cell/1e6, 3),
                    "h2005>=5m AND h2016<2m (physical, model-free)"])
        w.writerow(["gain_2005_2016", int(gain.sum()), round(gain.sum()*cell/1e6, 3),
                    "h2005<2m AND h2016>=5m"])
    print(f"change: covered {both.sum():,} cells, LOSS {loss.sum():,} "
          f"({loss.sum()*cell/1e6:.3f} km2), GAIN {gain.sum():,} "
          f"({gain.sum()*cell/1e6:.3f} km2)")
    print(f"wrote {OUT / 'certified_change_cells.csv'}")


if __name__ == "__main__":
    main()

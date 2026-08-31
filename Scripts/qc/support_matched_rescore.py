r"""Is the pilot's resolution result real, or an artifact of measurement SUPPORT?

THE QUESTION. The 2019 pilot measured the COARSER arm scoring higher on the same date:

    2019s  eff 42.6 cm   rec 0.6331  prec 0.7735
    2019n  eff 82.5 cm   rec 0.6915  prec 0.7858

Both were scored against the same 1 m C-CAP reference — but each on ITS OWN grid. A 30.5 cm
prediction is compared to the reference one way and a 60 cm prediction another, and the
finer arm is penalised for detail the reference cannot resolve: it can put canopy in a
1 m cell's corner and be right, while the reference only knows the cell. That is a
SUPPORT mismatch, and it inflates the apparent skill of whichever arm happens to sit closer
to the reference's own support.

This script removes that difference. Both arms are aggregated onto ONE common grid at
several supports and scored there. If the gap collapses as the support coarsens, it was a
measurement artifact and resolution is UNDETERMINED (CLAUDE.md 3.5 — an effect smaller than
the noise floor is UNDETERMINED, not "no difference"). If it survives, the gap is real —
though still confounded by program and sensor, since 2019s is Snohomish HXIP and 2019n is
USDA NAIP, two different flights on one date.

WHY 1 m IS THE FINEST SUPPORT TESTED. C-CAP is a 1 m product. Scoring below its support
would mean interpolating the reference and then measuring the interpolation. 1 / 2 / 4 m.

METHOD, and each step exists to avoid a specific way of being wrong:
  · Both arms and the reference are put on ONE EPSG:26910 grid over their common extent —
    C-CAP's, which is the smallest of the three.
  · The 255 sentinel is masked BEFORE any aggregation. Averaging it as a number would put
    255-valued "canopy" into every cell touching nodata.
  · Each arm is thresholded at ITS OWN operating threshold from qc_indep (2019s 0.4816,
    2019n 0.4951) — the deployed cut, not a shared 0.5 that neither arm uses.
  · Aggregation is by AREA FRACTION: two layers (canopy, valid) are averaged and divided,
    so a cell that is half nodata is scored on the half that is real rather than diluted.
  · A cell counts as canopy when its fraction >= 0.5, applied identically to prediction and
    reference, so the comparison is symmetric.

  py -3.12 qc/support_matched_rescore.py
  py -3.12 qc/support_matched_rescore.py --supports 1 2 4 8 --csv out.csv
"""
import argparse
import csv
import sys
import warnings
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent

_COLAB = Path("/content/drive/MyDrive/treedata")
BASE = _COLAB if _COLAB.exists() else Path(r"G:\My Drive\treedata")
MASKS = BASE / "phase4" / "masks"
REF = BASE / "Full_Image" / "Pipeline Imagery" / "ccap_2021_hires_lc.tif"
GRID_CRS = "EPSG:26910"

# forest + wetland = the PRIMARY canopy definition (qc/phase4_qc_indep.py::CCAP_DEFAULT)
CANOPY_CLASSES = [9, 10, 11, 13, 16]
IGNORE_CLASSES = [0, 1, 24, 25]

ARMS = [
    ("2019s", "pilot_e2_medium", 0.4816, 42.58),
    ("2019n", "pilot_e2_coarse", 0.4951, 82.54),
]


def _common_bounds(paths):
    import rasterio
    from rasterio.warp import transform_bounds
    xs0, ys0, xs1, ys1 = [], [], [], []
    for p in paths:
        with rasterio.open(p) as d:
            b = transform_bounds(d.crs, GRID_CRS, *d.bounds)
        xs0.append(b[0]); ys0.append(b[1]); xs1.append(b[2]); ys1.append(b[3])
    return max(xs0), max(ys0), min(xs1), min(ys1)


def _agg(path, bounds, res, kind, thresh_u8=None):
    """Aggregate one raster onto the common grid as (canopy_frac, valid_frac).

    kind="prob": uint8 probability, 255 = nodata, canopy where >= thresh_u8.
    kind="ref" : C-CAP classes, canopy where in CANOPY_CLASSES, invalid where IGNORE.
    """
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    x0, y0, x1, y1 = bounds
    w = max(1, int(round((x1 - x0) / res)))
    h = max(1, int(round((y1 - y0) / res)))
    dst_tf = rasterio.Affine(res, 0, x0, 0, -res, y1)

    with rasterio.open(path) as d:
        a = d.read(1)
        if kind == "prob":
            valid = (a != 255)
            canopy = valid & (a >= thresh_u8)
        else:
            valid = ~np.isin(a, IGNORE_CLASSES)
            canopy = valid & np.isin(a, CANOPY_CLASSES)
        out_c = np.zeros((h, w), "float32")
        out_v = np.zeros((h, w), "float32")
        for src_arr, dst_arr in ((canopy.astype("float32"), out_c),
                                 (valid.astype("float32"), out_v)):
            reproject(src_arr, dst_arr, src_transform=d.transform, src_crs=d.crs,
                      dst_transform=dst_tf, dst_crs=GRID_CRS,
                      resampling=Resampling.average, src_nodata=None, dst_nodata=0.0)
    return out_c, out_v


def main():
    warnings.filterwarnings("ignore")
    import numpy as np

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--supports", type=float, nargs="+", default=[1.0, 2.0, 4.0],
                    help="cell sizes in metres (default 1 2 4; 1 m is C-CAP's own support "
                         "and therefore the finest honest one)")
    ap.add_argument("--min-valid", type=float, default=0.5,
                    help="a cell is scored only if this fraction of it is real ground")
    ap.add_argument("--csv", type=str, default=None)
    a = ap.parse_args()

    paths = {lab: MASKS / f"edmonds_canopy_prob_{lab}_{tag}.tif"
             for lab, tag, _t, _e in ARMS}
    missing = [str(p) for p in list(paths.values()) + [REF] if not p.exists()]
    if missing:
        raise SystemExit("missing inputs:\n  " + "\n  ".join(missing))

    bounds = _common_bounds(list(paths.values()) + [REF])
    print(f"common extent (EPSG:26910): "
          f"{(bounds[2]-bounds[0])/1000:.2f} x {(bounds[3]-bounds[1])/1000:.2f} km")
    print(f"reference: {REF.name}  (canopy = forest+wetland, the PRIMARY definition)")
    print()

    rows = []
    for res in a.supports:
        rc, rv = _agg(REF, bounds, res, "ref")
        ref_ok = rv >= a.min_valid
        ref_can = (rc / np.maximum(rv, 1e-6)) >= 0.5
        line = {}
        for lab, tag, thr, eff in ARMS:
            thr_u8 = int(round(thr * 254))
            pc, pv = _agg(paths[lab], bounds, res, "prob", thr_u8)
            ok = ref_ok & (pv >= a.min_valid)
            pred = (pc / np.maximum(pv, 1e-6)) >= 0.5
            tp = int((pred & ref_can & ok).sum())
            fn = int((~pred & ref_can & ok).sum())
            fp = int((pred & ~ref_can & ok).sum())
            rec = tp / max(tp + fn, 1)
            prec = tp / max(tp + fp, 1)
            line[lab] = (rec, prec)
            rows.append(dict(support_m=res, arm=lab, eff_cm=eff, thresh=thr,
                             cells=int(ok.sum()), tp=tp, fp=fp, fn=fn,
                             recall=round(rec, 4), precision=round(prec, 4)))
        d_rec = line["2019n"][0] - line["2019s"][0]
        d_prec = line["2019n"][1] - line["2019s"][1]
        print(f"support {res:>4.1f} m   "
              f"2019s rec {line['2019s'][0]:.4f} prec {line['2019s'][1]:.4f}   |   "
              f"2019n rec {line['2019n'][0]:.4f} prec {line['2019n'][1]:.4f}   |   "
              f"coarse-minus-medium  rec {d_rec:+.4f}  prec {d_prec:+.4f}")

    print()
    print("READ IT THIS WAY: the pilot's native-grid gap was rec +0.0584, prec +0.0123 in")
    print("favour of the COARSER arm. If |gap| shrinks toward 0 as the support coarsens,")
    print("the pilot was measuring support, not resolution -> report UNDETERMINED.")
    print("If it holds, the gap is real but STILL confounded by program/sensor (Snohomish")
    print("HXIP vs USDA NAIP), so it is not yet a resolution result either.")

    if a.csv:
        with open(a.csv, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

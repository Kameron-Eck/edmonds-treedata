r"""
╔══════════════════════════════════════════════════════════════════╗
  SEPARABILITY INDEX CONTROL — separating "better imagery" from "better index"
  Edmonds Temporal Active Learning Pipeline · 2026-08-24

  THE CONFOUND THIS EXISTS TO KILL
  ------------------------------------------------------------------
  `imagery_canopy_separability.py` scores each raster with the best index it
  can compute: NDVI for a 4-band file, Excess Green (2G-R-B) for a 3-band one.
  The first run showed NIR-bearing files at AUROC 0.84-0.89 and RGB files at
  0.64-0.81 — but that comparison is NOT clean. NDVI is simply a stronger
  vegetation index than ExG, so some unknown share of the gap is the INDEX,
  not the imagery. Concluding "NIR acquisitions are better" from it would be
  exactly the kind of flattered comparison this project keeps catching
  (IMAGERY_FACTS 10.1: a metric read on unequal footing flatters one side).

  So compute BOTH indices on the SAME pixels of the SAME files:

    ExG on every raster        -> a like-for-like ranking of the IMAGERY,
                                  4-band and 3-band files on one scale.
    NDVI on the 4-band ones    -> paired with that file's own ExG, the
                                  isolated INDEX effect (same pixels, same
                                  ground, same day — only the formula changes).

  Reading the output:
    auroc_exg    compare freely across ALL files: imagery vs imagery.
    auroc_ndvi   only meaningful against the SAME file's auroc_exg.
    ndvi_gain    auroc_ndvi - auroc_exg = what the NIR band buys, per file.

  Same caveats as the parent script: the 2020 mask is a MODEL PREDICTION with
  its own blind spots, and for a non-2020 year it also carries real canopy
  change as error. Within-year contrast is the honest reading.

  USAGE
    py -3.12 qc/separability_index_control.py [--points 40] [--workers 3] [--only PAT]
╚══════════════════════════════════════════════════════════════════╝
"""
import argparse
import datetime as dt
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "qc"))
import imagery_qc_suite as QS                 # noqa: E402
import imagery_canopy_separability as SEP     # noqa: E402
from phase4seg.names import clean_argv  # noqa: E402

TODAY = dt.date.today().isoformat()


def exg(A):
    r, g, b = A[0], A[1], A[2]
    s = np.maximum(r + g + b, 1e-6)
    return (2 * g - r - b) / s


def ndvi(A):
    red, nir = A[0], A[3]
    return (nir - red) / np.maximum(nir + red, 1e-6)


def score(rec, pts, args):
    path = rec["path"]
    pos_e, neg_e, pos_n, neg_n, used = [], [], [], [], 0
    try:
        with rasterio.open(path) as ds:
            nb = ds.count
        if nb < 3:
            return None                      # ExG needs RGB; 1-band pans are out of scope here
        for lon, lat in pts:
            A, grid = SEP.grab_common(path, lon, lat, args.box_m, args.grid_cm / 100.0)
            if A is None:
                continue
            m = SEP.grab_mask(*grid)
            if m is None:
                continue
            base = np.isfinite(A).all(axis=0) & (A.sum(axis=0) > 0) & (m != 255)
            e = exg(A)
            ve = base & np.isfinite(e)
            pos_e.append(e[ve & (m == 1)]); neg_e.append(e[ve & (m == 0)])
            if nb >= 4:
                n_ = ndvi(A)
                vn = base & np.isfinite(n_)
                pos_n.append(n_[vn & (m == 1)]); neg_n.append(n_[vn & (m == 0)])
            used += 1
        if not used:
            return None
        pe, ne = np.concatenate(pos_e), np.concatenate(neg_e)
        a_e = SEP.auroc(pe, ne)
        row = dict(file=rec["file"], key=rec["key"], year=QS.year_of(rec["key"]), bands=nb,
                   windows=used, auroc_exg=round(a_e, 4) if np.isfinite(a_e) else None)
        if nb >= 4 and pos_n:
            pn, nn = np.concatenate(pos_n), np.concatenate(neg_n)
            a_n = SEP.auroc(pn, nn)
            row["auroc_ndvi"] = round(a_n, 4) if np.isfinite(a_n) else None
            if row["auroc_ndvi"] and row["auroc_exg"]:
                row["ndvi_gain"] = round(row["auroc_ndvi"] - row["auroc_exg"], 4)
        print(f"  {rec['file']:32s} ExG {row['auroc_exg']}"
              + (f"   NDVI {row.get('auroc_ndvi')}  gain {row.get('ndvi_gain'):+.4f}" if row.get("ndvi_gain") else ""),
              flush=True)
        return row
    except Exception as ex:
        return dict(file=rec["file"], key=rec["key"], note=f"ERROR {type(ex).__name__}: {ex}")


def main():
    argv = clean_argv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", type=int, default=40)
    ap.add_argument("--box-m", type=float, default=60.0)
    ap.add_argument("--grid-cm", type=float, default=50.0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only")
    ap.add_argument("--outdir", type=Path, default=SCRIPTS.parent / "phase4" / "qc")
    args = ap.parse_args(argv)
    args.outdir.mkdir(parents=True, exist_ok=True)

    inv = [r for r in QS.inventory(args.only) if r["path"] is not None]
    pts = SEP.sample_points(args.points)      # same seed -> the same ground as the parent run
    print(f"INDEX CONTROL — {len(inv)} rasters x {len(pts)} seeded locations "
          f"(ExG on all; NDVI additionally on 4-band)")
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(lambda rec: score(rec, pts, args), inv):
            if r:
                rows.append(r)
    ok = [r for r in rows if r.get("auroc_exg")]
    ok.sort(key=lambda r: -r["auroc_exg"])
    QS.write_csv(rows, args.outdir / f"imagery_separability_index_control_{TODAY}.csv")

    print("\n  LIKE-FOR-LIKE IMAGERY RANKING (ExG on every file — index held constant)")
    for r in ok:
        tag = " [4-band]" if r["bands"] >= 4 else ""
        print(f"   {r['auroc_exg']:.4f}  {r['file']:32s}{tag}")
    gains = [r["ndvi_gain"] for r in rows if r.get("ndvi_gain") is not None]
    if gains:
        print(f"\n  ISOLATED INDEX EFFECT (same pixels, NDVI vs ExG, n={len(gains)} four-band files)")
        print(f"   median gain {np.median(gains):+.4f}   range {min(gains):+.4f} .. {max(gains):+.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

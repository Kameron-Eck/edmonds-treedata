"""E2: per-point covariate flags for a drawn photo-interp sample — joined as a
SEPARATE file (sample_{year}_covariates.csv) so the sampler/labels contract is
untouched. Flags:
  low_grvi  : GRVI = (G-R)/(G+R) < 0.02 at the point (leafoff instrument's
              exact convention, incl. the den>12 near-black skip -> blank)
  dark_px   : mean(R,G,B) < 60 DN (deep shadow / near-black; the shadow-probe
              residual E2 asked to carry as a covariate, not a stratum)
Values: 1 / 0 / '' (blank = not computable: nodata, near-black GRVI, off-image).
Strata and Olofsson weights are untouched — these are covariates for post-hoc
splits of Kam's labels, never part of the estimator.
Usage: py -3.12 qc/instruments/build_sample_covariates.py --year 2016 --ortho <path>
"""
import argparse
import csv
import io
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform

from lake import BASE

QC_DIR = BASE / "phase4" / "qc"
GRVI_THRESH = 0.02      # phase4_qc_leafoff.py grvi/LOW-GREENNESS convention
DEN_MIN = 12            # phase4_qc_leafoff.py::grvi near-black skip
DARK_DN = 60


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", required=True)
    ap.add_argument("--ortho", required=True)
    args = ap.parse_args()

    samp_p = QC_DIR / f"sample_{args.year}.csv"
    meta = json.loads((QC_DIR / f"sample_{args.year}_meta.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(io.open(samp_p, encoding="utf-8", newline="")))

    xs = [float(r["x"]) for r in rows]
    ys = [float(r["y"]) for r in rows]
    with rasterio.open(args.ortho) as src:
        if str(src.crs) != meta["crs"]:
            xs, ys = warp_transform(meta["crs"], src.crs, xs, ys)
        nod = src.nodata
        vals = np.array([v[:3] for v in src.sample(zip(xs, ys), (1, 2, 3))],
                        dtype=np.float32)

    out = QC_DIR / f"sample_{args.year}_covariates.csv"
    n_low = n_dark = n_blank = 0
    with io.open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["point_id", "low_grvi", "dark_px", "ortho"])
        for r, (R, G, B) in zip(rows, vals):
            if nod is not None and R == nod and G == nod and B == nod:
                w.writerow([r["point_id"], "", "", Path(args.ortho).name])
                n_blank += 1
                continue
            dark = int((R + G + B) / 3.0 < DARK_DN)
            den = G + R
            if den > DEN_MIN:
                low = int((G - R) / den < GRVI_THRESH)
            else:
                low = ""
                n_blank += 1
            n_low += 1 if low == 1 else 0
            n_dark += dark
            w.writerow([r["point_id"], low, dark, Path(args.ortho).name])
    print(f"wrote {out}: {len(rows)} points, low_grvi={n_low}, dark_px={n_dark}, "
          f"blank={n_blank}")


if __name__ == "__main__":
    main()

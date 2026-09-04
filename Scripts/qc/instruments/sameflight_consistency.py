"""C3 — the processing-chain consistency ceiling no reference can see.

2019s and 2019n are ONE Hexagon flight delivered two ways (WA consortium 1-ft
vs NAIP 60 cm; qc/imagery_pixelsize_and_date.csv). The pilot scored both with
ZERO engine diff between their commits, so mask disagreement between them is
pure processing-chain + GSD effect: identical sun, atmosphere, phenology,
sensor. Whatever this disagreement is, no accuracy claim about either product
can honestly be tighter than it.

Method: warp the 2019n mask (nearest) onto the 2019s grid; on valid overlap
(both masks 0/1, neither nodata): overall disagreement, canopy IoU, and
1-px-tolerant disagreement (8-neighbourhood, splits boundary jitter from
body-level disagreement). Output: phase4/qc/sameflight_consistency.csv
"""
import csv
import io
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from lake import BASE

MASKS = BASE / "phase4" / "masks"
A = MASKS / "edmonds_canopy_mask_2019s_pilot_e2_medium.tif"
B = MASKS / "edmonds_canopy_mask_2019n_pilot_e2_coarse.tif"
OUT = Path(__file__).resolve().parents[3] / "phase4" / "qc" / "sameflight_consistency.csv"


def dilate8(a):
    out = a.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                out |= np.roll(np.roll(a, dy, 0), dx, 1)
    return out


def main():
    with rasterio.open(A) as sa:
        ma = sa.read(1)
        nda = sa.nodata
        px = abs(sa.res[0])
        with rasterio.open(B) as sb:
            ndb = sb.nodata
            with WarpedVRT(sb, crs=sa.crs, transform=sa.transform,
                           width=sa.width, height=sa.height,
                           resampling=Resampling.nearest) as v:
                mb = v.read(1)
    valid = np.isin(ma, (0, 1)) & np.isin(mb, (0, 1))
    if nda is not None:
        valid &= ma != nda
    if ndb is not None:
        valid &= mb != ndb
    a1 = valid & (ma == 1)
    b1 = valid & (mb == 1)
    dis = valid & (ma != mb)
    inter = (a1 & b1).sum()
    union = (a1 | b1).sum()
    a1d, b1d = dilate8(a1), dilate8(b1)
    # tolerant disagreement: a px disagrees only if the OTHER mask has no same
    # class within 1 px — removes pure boundary jitter.
    hard = (a1 & ~b1d) | (b1 & ~a1d)
    rows = [dict(
        mask_a=A.name, mask_b=B.name, grid_px_m=round(px, 4),
        valid_px=int(valid.sum()),
        canopy_a_frac=round(float(a1.sum() / valid.sum()), 4),
        canopy_b_frac=round(float(b1.sum() / valid.sum()), 4),
        disagree_frac=round(float(dis.sum() / valid.sum()), 4),
        canopy_iou=round(float(inter / max(union, 1)), 4),
        hard_disagree_frac=round(float(hard.sum() / valid.sum()), 4),
        note="one flight, two deliveries, zero engine diff (pilot e2); "
             "hard = no same-class pixel within 1px in the other mask",
    )]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    r = rows[0]
    print(f"valid {r['valid_px']:,} px  canopy {r['canopy_a_frac']:.3f} vs "
          f"{r['canopy_b_frac']:.3f}  disagree {r['disagree_frac']:.4f}  "
          f"IoU {r['canopy_iou']:.4f}  hard-disagree {r['hard_disagree_frac']:.4f}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

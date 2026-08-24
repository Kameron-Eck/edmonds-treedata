r"""Re-score the CoE rasters that failed the separability sweep with FUSE read retry
(2026-08-24, local QC agent).

Why this exists: `imagery_canopy_separability.py` scored 40/43 rasters; three did not
score — 2018_coe_marsh2cm_rgb.tif legitimately (a ~1 km^2 marsh footprint, so the
citywide sample points miss it), and 2020_coe_rgb.tif / 2024_coe_rgb.tif with
`RasterioIOError: Read failed`. Those two are NOT defective: they live on the Drive
mount (D: is a partial mirror with no CoE orthos), have no overview pyramids, and a
single transient FUSE streaming failure kills the read. Retrying the same tile
succeeded immediately.

The 2020 file is the project's hand-annotated ANCHOR, so its separability score is not
optional — it is the reference every other year is judged against.

This wraps the read in a bounded retry and re-scores only the missing files, writing a
CSV that merges into the parent run's table.

Run: py -3.12 scratch/separability_retry_coe.py
"""
import sys
import time
from pathlib import Path

import numpy as np
import rasterio

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))
sys.path.insert(0, str(SCRIPTS / "qc"))
import imagery_qc_suite as QS                 # noqa: E402
import imagery_canopy_separability as SEP     # noqa: E402

TARGETS = ["2020_coe_rgb.tif", "2024_coe_rgb.tif"]
POINTS, BOX_M, GRID_CM = 40, 60.0, 50.0


def grab_retry(path, lon, lat, tries=4):
    """SEP.grab_common with backoff — a Drive FUSE read can fail transiently mid-stream."""
    for i in range(tries):
        try:
            return SEP.grab_common(path, lon, lat, BOX_M, GRID_CM / 100.0)
        except rasterio.errors.RasterioIOError:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))
    return None, None


def main():
    inv = {r["file"]: r["path"] for r in QS.inventory() if r["path"] is not None}
    pts = SEP.sample_points(POINTS)           # same seed -> same ground as the parent run
    rows = []
    for name in TARGETS:
        p = inv.get(name)
        if p is None:
            print(f"{name}: not resolvable"); continue
        pos, neg, used, retries, fails, idx_name = [], [], 0, 0, 0, None
        for lon, lat in pts:
            try:
                A, grid = grab_retry(p, lon, lat)
            except Exception as ex:
                fails += 1
                continue
            if A is None:
                continue
            m = SEP.grab_mask(*grid)
            if m is None:
                continue
            with rasterio.open(p) as ds:
                nb = ds.count
            idx, idx_name = SEP.canopy_index(A, nb)
            v = np.isfinite(idx) & (A.sum(axis=0) > 0) & (m != 255)
            pos.append(idx[v & (m == 1)]); neg.append(idx[v & (m == 0)])
            used += 1
        if not used:
            print(f"{name}: no usable windows"); continue
        pv, nv = np.concatenate(pos), np.concatenate(neg)
        a = SEP.auroc(pv, nv)
        pooled = np.sqrt((pv.var() + nv.var()) / 2)
        d = float((pv.mean() - nv.mean()) / pooled) if pooled > 0 else float("nan")
        rows.append(dict(file=name, index=idx_name, windows=used, windows_failed=fails,
                         auroc=round(a, 4), cohens_d=round(d, 3),
                         n_canopy_px=int(pv.size), n_background_px=int(nv.size)))
        print(f"  {a:.4f} AUROC  {name:28s} {idx_name:5s} d={d:.2f}  "
              f"({used} windows scored, {fails} unreadable after retry)")
    if rows:
        out = SCRIPTS.parent / "phase4" / "qc" / "imagery_separability_coe_retry_2026-08-24.csv"
        QS.write_csv(rows, out)
        print(f"  -> {out}")


if __name__ == "__main__":
    sys.exit(main())

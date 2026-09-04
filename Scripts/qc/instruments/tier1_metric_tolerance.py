"""C2b — METRIC edge-tolerance curves (supersedes the 1-native-px C2 read).

Same arms/blocks/thresholds as tier1_buffer_tolerant.py, but tolerance is a
PHYSICAL distance — the error sources are metric (registration medians to
2.2 m, coregistration.csv; crown-edge gradients ~0.5-1 m; 2020-flight label
projection) and a native-pixel buffer conflates them with the delivery grid
(+/-1 px was 3.28 m of forgiveness on 2006s and 7 cm on 2020).

Tolerances: strict, 0.5 m, 1 m, 2 m — dilation by round(tol/px) pixels
(8-neighbourhood chamfer approximation; 0 rounds -> strict). The jump
strict->1m is boundary/registration accounting; 1m->2m adds the measured
registration tail; the residual past 2 m is genuine detection error.

Output: phase4/qc/metric_tolerance_scores.csv (one row per arm x tolerance).
"""
import csv
import io
import re
import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features as rfeat
import rasterio.warp
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window, from_bounds

SCRIPTS = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(SCRIPTS / "qc"))  # phase4_qc_indep (qc root)
import phase4_qc_indep as qci  # noqa: E402

from lake import BASE  # noqa: E402

MASKS = BASE / "phase4" / "masks"
QC = BASE / "phase4" / "qc"
REF = Path(r"D:\edmonds-pipeline\Imagery\ccap_2021_hires_lc.tif")
MAN = SCRIPTS.parent / "phase4" / "qc" / "science_sample_manifest.csv"
OUT = SCRIPTS.parent / "phase4" / "qc" / "metric_tolerance_scores.csv"
TOL_M = (0.0, 0.5, 1.0, 2.0)
ARMS = [f"t1_{y}_{s}" for y in ("2006s", "2011s", "2016", "2019n", "2020")
        for s in ("base", "in16") if not (y == "2019n" and s == "in16")]


def dilate_n(a, n):
    """n iterations of 8-neighbourhood dilation (chamfer-approx disk)."""
    out = a.copy()
    for _ in range(n):
        d = out.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    d |= np.roll(np.roll(out, dy, 0), dx, 1)
        out = d
    return out


def main():
    geoms, epsg, _ = qci.load_aoi(str(MAN), ("test",))
    names, canopy_order, _, code_to_group = qci.load_ref_map("ccap", None)
    ignore_id = names.index("ignore")
    lut = qci.build_lut(names, code_to_group)
    prim_ids = [names.index(g) for g in qci.canopy_definitions(canopy_order)[1][1]]

    thr = {}
    with open(QC / "indep_thresholds.csv", newline="") as f:
        for r in csv.DictReader(f):
            if r["ref"] == "ccap_2021_hires_lc.tif":
                thr[r["run_tag"]] = float(r["thresh"])

    rows = []
    for tag in ARMS:
        year = re.match(r"t1_([0-9a-z]+)_", tag).group(1)
        p = MASKS / f"edmonds_canopy_prob_{year}_{tag}.tif"
        t = thr.get(tag)
        if not p.exists() or t is None:
            print(f"skip {tag}")
            continue
        with rasterio.open(p) as prob, rasterio.open(REF) as ref_src:
            ref_nodata = ref_src.nodata
            px_m = abs(prob.res[0])
            iters = {tol: int(round(tol / px_m)) for tol in TOL_M}
            acc = {tol: dict(tp=0, fn=0, fp_hard=0, npred=0) for tol in TOL_M}
            with WarpedVRT(ref_src, crs=prob.crs, transform=prob.transform,
                           width=prob.width, height=prob.height,
                           resampling=Resampling.nearest) as ref_vrt:
                for g in geoms:
                    gw = rasterio.warp.transform_geom(f"EPSG:{epsg}", prob.crs, g)
                    xs = [pt[0] for pt in gw["coordinates"][0]]
                    ys = [pt[1] for pt in gw["coordinates"][0]]
                    # pad the window by the largest dilation so tolerance can
                    # see canopy just OUTSIDE the block edge
                    pad = max(iters.values()) + 1
                    win = from_bounds(min(xs), min(ys), max(xs), max(ys),
                                      prob.transform).round_offsets().round_lengths()
                    win = Window(win.col_off - pad, win.row_off - pad,
                                 win.width + 2 * pad, win.height + 2 * pad)
                    win = win.intersection(Window(0, 0, prob.width, prob.height))
                    if win.width <= 2 or win.height <= 2:
                        continue
                    pr = prob.read(1, window=win)
                    rc = ref_vrt.read(1, window=win)
                    gid = lut[np.clip(rc.astype(np.int64), 0, 255)]
                    if ref_nodata is not None:
                        gid[rc == ref_nodata] = ignore_id
                    valid = (gid != ignore_id) & (pr != 255)
                    wtf = rasterio.windows.transform(win, prob.transform)
                    inaoi = rfeat.rasterize([(gw, 1)], out_shape=pr.shape,
                                            transform=wtf, fill=0,
                                            dtype="uint8").astype(bool)
                    scope = valid & inaoi
                    prim_all = valid & np.isin(gid, prim_ids)   # incl. pad ring
                    pred_all = valid & (pr >= t * 254.0)
                    prim, pred = prim_all & inaoi, pred_all & inaoi
                    for tol, n in iters.items():
                        pd = dilate_n(pred_all, n) if n else pred_all
                        rd = dilate_n(prim_all, n) if n else prim_all
                        a = acc[tol]
                        a["tp"] += int((prim & pd).sum())
                        a["fn"] += int((prim & ~pd).sum())
                        a["fp_hard"] += int((pred & ~rd).sum())
                        a["npred"] += int(pred.sum())
        for tol in TOL_M:
            a = acc[tol]
            rec = a["tp"] / max(a["tp"] + a["fn"], 1)
            prec = 1 - a["fp_hard"] / max(a["npred"], 1)
            rows.append(dict(tag=tag, px_m=round(px_m, 4), tol_m=tol,
                             dilate_px=iters[tol],
                             recall=round(rec, 4), precision=round(prec, 4)))
        line = "  ".join(f"{tol}m R{r['recall']:.3f}/P{r['precision']:.3f}"
                         for tol, r in zip(TOL_M, rows[-len(TOL_M):]))
        print(f"{tag:18s} px={px_m:.2f}m  {line}", flush=True)

    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

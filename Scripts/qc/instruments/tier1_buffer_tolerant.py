"""C2 — buffer-tolerant re-scoring: how much Tier-1 'error' is boundary/
registration accounting rather than missed or invented trees?

For each year's base and in16 arms, on TEST blocks at the arm's deployed
policy-C threshold: strict pixel recall/precision vs 1-pixel-tolerant
(a ref-canopy pixel counts as found if ANY predicted-canopy pixel sits in
its 8-neighbourhood; a predicted pixel counts as correct if ANY ref-canopy
pixel does). The strict-vs-tolerant gap IS the crown-edge/registration
share of the error — measured registration medians run to 2.2 m
(coregistration.csv) against ~6.5 m crowns, so this share is real and it
is not a model defect. Tolerance is 1 px of the arm's native prob grid;
the pixel size is reported beside every row.

Output: phase4/qc/buffer_tolerant_scores.csv
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
OUT = SCRIPTS.parent / "phase4" / "qc" / "buffer_tolerant_scores.csv"
ARMS = [f"t1_{y}_{s}" for y in ("2006s", "2011s", "2016", "2019n", "2020")
        for s in ("base", "in16") if not (y == "2019n" and s == "in16")]


def dilate8(a):
    out = a.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                out |= np.roll(np.roll(a, dy, 0), dx, 1)
    return out


def main():
    geoms, epsg, nb = qci.load_aoi(str(MAN), ("test",))
    names, canopy_order, _, code_to_group = qci.load_ref_map("ccap", None)
    ignore_id = names.index("ignore")
    lut = qci.build_lut(names, code_to_group)
    prim_ids = [names.index(g) for g in
                (qci.canopy_definitions(canopy_order)[1][1])]

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
            print(f"skip {tag}: missing prob or thresh")
            continue
        acc = dict(tp=0, fn=0, fp=0, tp_tol=0, fn_tol=0, fp_tol=0)
        with rasterio.open(p) as prob, rasterio.open(REF) as ref_src:
            ref_nodata = ref_src.nodata
            px_m = abs(prob.res[0])
            with WarpedVRT(ref_src, crs=prob.crs, transform=prob.transform,
                           width=prob.width, height=prob.height,
                           resampling=Resampling.nearest) as ref_vrt:
                for g in geoms:
                    gw = rasterio.warp.transform_geom(f"EPSG:{epsg}", prob.crs, g)
                    xs = [pt[0] for pt in gw["coordinates"][0]]
                    ys = [pt[1] for pt in gw["coordinates"][0]]
                    win = from_bounds(min(xs), min(ys), max(xs), max(ys),
                                      prob.transform).round_offsets().round_lengths()
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
                    valid &= inaoi
                    prim = valid & np.isin(gid, prim_ids)
                    pred = valid & (pr >= t * 254.0)
                    pred_d, prim_d = dilate8(pred), dilate8(prim)
                    acc["tp"] += int((prim & pred).sum())
                    acc["fn"] += int((prim & ~pred).sum())
                    acc["fp"] += int((pred & ~prim).sum())
                    acc["tp_tol"] += int((prim & pred_d).sum())
                    acc["fn_tol"] += int((prim & ~pred_d).sum())
                    acc["fp_tol"] += int((pred & ~prim_d).sum())
        rs = acc["tp"] / max(acc["tp"] + acc["fn"], 1)
        ps = acc["tp"] / max(acc["tp"] + acc["fp"], 1)
        rt = acc["tp_tol"] / max(acc["tp_tol"] + acc["fn_tol"], 1)
        # tolerant precision: predicted px is wrong only if NO ref canopy in
        # its 8-neighbourhood — fp_tol counts exactly those.
        pt = 1 - acc["fp_tol"] / max(acc["tp"] + acc["fp"], 1)
        rows.append(dict(tag=tag, thresh=t, px_m=round(px_m, 4),
                         recall_strict=round(rs, 4), recall_tol1px=round(rt, 4),
                         recall_gap=round(rt - rs, 4),
                         precision_strict=round(ps, 4),
                         precision_tol1px=round(pt, 4),
                         precision_gap=round(pt - ps, 4),
                         **{k: acc[k] for k in ("tp", "fn", "fp", "fp_tol")}))
        print(f"{tag:18s} px={px_m:.2f}m  R {rs:.4f}->{rt:.4f} (+{rt-rs:.4f})  "
              f"P {ps:.4f}->{pt:.4f} (+{pt-ps:.4f})", flush=True)
    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

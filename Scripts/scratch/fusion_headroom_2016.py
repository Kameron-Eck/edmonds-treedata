r"""Fusion headroom test (2026-08-26, one-shot analysis): does combining the CHM
arm and the NIR arm of 2016 look worth input-level 5-band training?

TASK A — error overlap at each arm's own deployed threshold (do the two inputs
miss the SAME trees?).  TASK B — decision fusion (mean prob) threshold sweep vs
both parents at deployed AND at their own best-on-sweep points.

Conventions copied from qc/phase4_qc_indep.py (NOT reinvented): prob rasters are
uint8 DN, 255 = nodata, canopy call = DN >= thresh*254; C-CAP reference warped
nearest onto the prob grid; primary canopy def = forest_wetland ({forest,
wetland}); FP = model-canopy on any valid non-primary pixel; ignore = codes
{0,1,24,25} + ref nodata.  Scored on the INTERSECTION of both arms' valid
footprints only.

Writes markdown results to the session scratchpad. Reads only; no lake writes.
"""
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from pathlib import Path

CHM_PROB = Path(r"G:\My Drive\treedata\phase4\masks\edmonds_canopy_prob_2016_fullext_sectors_v1.tif")
NIR_PROB = Path(r"G:\My Drive\treedata\phase4\masks\edmonds_canopy_prob_2016_nir_m06.tif")
REF      = Path(r"D:\edmonds-pipeline\Imagery\ccap_2016_hires_lc_snohfull.tif")
OUT_MD   = Path(r"C:\Users\Kameron\AppData\Local\Temp\claude\D--edmonds-pipeline-treedata-Scripts"
                r"\38ce7527-5e87-4d98-b55b-f039524783e8\scratchpad\fusion_headroom_2016.md")

THR_CHM, THR_NIR = 0.5223, 0.5939          # each arm's own deployed threshold
SWEEP = [round(0.30 + 0.02 * i, 2) for i in range(21)]   # 0.30..0.70
BLOCK = 1024

# C-CAP grouping — verbatim from qc/phase4_qc_indep.py CCAP_DEFAULT
GROUPS = {
    "forest": [9, 10, 11], "wetland": [13, 16], "scrub": [12, 14, 17],
    "grass": [5, 7, 8], "cropland": [6], "developed": [2, 3, 4],
    "barren": [19, 20], "emergent_wetland": [15, 18], "water": [21, 22, 23],
    "ignore": [0, 1, 24, 25],
}
PRIMARY = {"forest", "wetland"}            # primary def = forest_wetland

names = list(GROUPS.keys()) + ["other"]
other_id, ignore_id = names.index("other"), names.index("ignore")
lut = np.full(256, other_id, dtype=np.int16)
for g, codes in GROUPS.items():
    for c in codes:
        lut[c] = names.index(g)
primary_ids = np.array([names.index(g) for g in PRIMARY])


def metrics(tp, fn, fp):
    rec = tp / (tp + fn) if tp + fn else float("nan")
    prec = tp / (tp + fp) if tp + fp else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else float("nan")
    iou = tp / (tp + fn + fp) if tp + fn + fp else float("nan")
    return rec, prec, f1, iou


chm = rasterio.open(CHM_PROB)
nir = rasterio.open(NIR_PROB)
assert chm.crs == nir.crs and chm.transform == nir.transform \
    and (chm.height, chm.width) == (nir.height, nir.width), \
    "prob rasters are NOT on the same grid — directive premise fails, refusing"
H, W = chm.height, chm.width

ref_src = rasterio.open(REF)
ref_nodata = ref_src.nodata

# accumulators
A = dict(fn_c=0, fn_n=0, fn_both=0, fp_c=0, fp_n=0, fp_both=0,
         tp_c=0, tp_n=0, valid=0, prim=0)
sw = {t: {k: dict(tp=0, fn=0, fp=0) for k in ("chm", "nir", "fus")} for t in SWEEP}

thr_c_u8, thr_n_u8 = THR_CHM * 254.0, THR_NIR * 254.0

with WarpedVRT(ref_src, crs=chm.crs, transform=chm.transform, width=W, height=H,
               resampling=Resampling.nearest) as vrt:
    n_blocks = (H + BLOCK - 1) // BLOCK
    for bi, row0 in enumerate(range(0, H, BLOCK)):
        rows = min(BLOCK, H - row0)
        win = Window(0, row0, W, rows)
        pc = chm.read(1, window=win)
        pn = nir.read(1, window=win)
        rc = vrt.read(1, window=win)

        gid = lut[np.clip(rc.astype(np.int64), 0, 255)]
        if ref_nodata is not None and 0 <= int(ref_nodata) < 256:
            gid[rc == ref_nodata] = ignore_id

        valid = (gid != ignore_id) & (pc != 255) & (pn != 255)   # INTERSECTION
        if not valid.any():
            continue
        prim = valid & np.isin(gid, primary_ids)
        notp = valid & ~np.isin(gid, primary_ids)

        mc = pc >= thr_c_u8
        mn = pn >= thr_n_u8
        fn_c = prim & ~mc
        fn_n = prim & ~mn
        fp_c = notp & mc
        fp_n = notp & mn
        A["valid"] += int(valid.sum()); A["prim"] += int(prim.sum())
        A["fn_c"] += int(fn_c.sum()); A["fn_n"] += int(fn_n.sum())
        A["fn_both"] += int((fn_c & fn_n).sum())
        A["fp_c"] += int(fp_c.sum()); A["fp_n"] += int(fp_n.sum())
        A["fp_both"] += int((fp_c & fp_n).sum())
        A["tp_c"] += int((prim & mc).sum()); A["tp_n"] += int((prim & mn).sum())

        fus = (pc.astype(np.uint16) + pn.astype(np.uint16))      # 2*mean, in DN
        for t in SWEEP:
            tu = t * 254.0
            for key, call in (("chm", pc >= tu), ("nir", pn >= tu),
                              ("fus", fus >= 2 * tu)):
                s = sw[t][key]
                s["tp"] += int((prim & call).sum())
                s["fn"] += int((prim & ~call).sum())
                s["fp"] += int((notp & call).sum())
        if bi % 5 == 0 or bi == n_blocks - 1:
            print(f"  block {bi + 1}/{n_blocks}", flush=True)

chm.close(); nir.close(); ref_src.close()

fn_union = A["fn_c"] + A["fn_n"] - A["fn_both"]
fp_union = A["fp_c"] + A["fp_n"] - A["fp_both"]
fn_jac = A["fn_both"] / fn_union if fn_union else float("nan")
fp_jac = A["fp_both"] / fp_union if fp_union else float("nan")

lines = []
lines.append("# Fusion headroom test — 2016, CHM arm vs NIR arm\n")
lines.append(f"Footprint: intersection of both arms' valid pixels = {A['valid']:,} px "
             f"(primary-canopy ref px within it: {A['prim']:,}). Reference: "
             f"{REF.name}, primary def = forest_wetland. Sample strips only (~11% of city).\n")
lines.append("## Task A — error overlap at deployed thresholds "
             f"(CHM @ {THR_CHM}, NIR @ {THR_NIR})\n")
lines.append("| error | CHM arm | NIR arm | both (∩) | ∩/CHM | ∩/NIR | Jaccard |")
lines.append("|---|---|---|---|---|---|---|")
lines.append(f"| FN (missed canopy) | {A['fn_c']:,} | {A['fn_n']:,} | {A['fn_both']:,} "
             f"| {A['fn_both']/A['fn_c']:.1%} | {A['fn_both']/A['fn_n']:.1%} | {fn_jac:.3f} |")
lines.append(f"| FP (false canopy) | {A['fp_c']:,} | {A['fp_n']:,} | {A['fp_both']:,} "
             f"| {A['fp_both']/A['fp_c']:.1%} | {A['fp_both']/A['fp_n']:.1%} | {fp_jac:.3f} |\n")

best_f1 = {}
best_iou = {}
for key in ("chm", "nir", "fus"):
    rows = [(t, *metrics(sw[t][key]["tp"], sw[t][key]["fn"], sw[t][key]["fp"])) for t in SWEEP]
    best_f1[key] = max(rows, key=lambda r: (r[3] if r[3] == r[3] else -1))
    best_iou[key] = max(rows, key=lambda r: (r[4] if r[4] == r[4] else -1))

def dep_row(key, thr_u8):
    # deployed points recomputed on THIS footprint from the sweep's nearest thr
    # is not exact; use the Task-A accumulators instead (exact at deployed thr).
    if key == "chm":
        tp, fn, fp = A["tp_c"], A["fn_c"], A["fp_c"]
        t = THR_CHM
    else:
        tp, fn, fp = A["tp_n"], A["fn_n"], A["fp_n"]
        t = THR_NIR
    return (t, *metrics(tp, fn, fp))

lines.append("## Task B — decision fusion (mean prob) vs parents, same footprint\n")
lines.append("| arm | operating point | thresh | recall | precision | F1 | IoU |")
lines.append("|---|---|---|---|---|---|---|")
for key, label in (("chm", "CHM (rgb+chm)"), ("nir", "NIR (rgb+nir)")):
    t, rec, prec, f1, iou = dep_row(key, None)
    lines.append(f"| {label} | deployed | {t} | {rec:.4f} | {prec:.4f} | {f1:.4f} | {iou:.4f} |")
for key, label in (("chm", "CHM (rgb+chm)"), ("nir", "NIR (rgb+nir)"), ("fus", "FUSION (mean)")):
    t, rec, prec, f1, iou = best_f1[key]
    lines.append(f"| {label} | best-F1 on sweep | {t} | {rec:.4f} | {prec:.4f} | {f1:.4f} | {iou:.4f} |")
for key, label in (("chm", "CHM (rgb+chm)"), ("nir", "NIR (rgb+nir)"), ("fus", "FUSION (mean)")):
    t, rec, prec, f1, iou = best_iou[key]
    lines.append(f"| {label} | best-IoU on sweep | {t} | {rec:.4f} | {prec:.4f} | {f1:.4f} | {iou:.4f} |")
lines.append("")
OUT_MD.parent.mkdir(parents=True, exist_ok=True)
OUT_MD.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
print("wrote", OUT_MD)

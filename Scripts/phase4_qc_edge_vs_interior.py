r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — ARE THE MISSES CROWN PERIMETERS, OR REAL MISSED TREES?
  Edmonds Temporal Active Learning Pipeline

  THE QUESTION IT WAS BUILT FOR  (hypothesis raised 2026-08-18 by the
  sentinel error overlays, phase4_sentinel_qc_overlay.py)
  ------------------------------------------------------------------
  In the residential and marsh sentinel windows the FN (red) formed RINGS
  around the TP (green) cores — the model finds each tree clump and loses
  its EDGE.  Two things ride on whether that generalises:

    1. THE DIAGNOSIS.  If most FN are crown perimeter, then suburban recall
       .575 is an under-SEGMENTATION problem, not a "cannot see yard trees"
       problem, and the fix is boundary handling / the operating point —
       NOT the new crown labels the annotation plan assumes.

    2. RESULT (1), THE HEIGHT STAIRCASE.  Crown edges carry LOWER CHM than
       crown centres (the canopy surface slopes down to the ground at the
       crown boundary).  So the 5-15 m bands may be over-populated by the
       EDGES OF TALL TREES rather than by genuinely short trees — which
       would make part of the staircase a GEOMETRY ARTEFACT.

  THE TEST
  --------
  Split agreed-canopy pixels into INTERIOR and EDGE by binary erosion of
  the agreed-canopy mask, then recompute recall for each, overall and BY
  HEIGHT BAND.

    * If the staircase SURVIVES inside INTERIOR-only pixels, the height
      effect is real and is not crown geometry.  Result (1) stands.
    * If interior recall is FLAT across bands and only the edge recall
      varies, the staircase was largely geometry.

  Reads the same rasters and uses the same bands/partitions as
  phase4_qc_height_by_agreement.py, so the numbers sit beside U3's.

  A NOTE ON WHAT "EDGE" MEANS HERE
    Erosion happens on the DECIMATED lattice, so one erosion step = one
    decimated cell.  At --decim 4 on 50 cm imagery that is a 2 m ring,
    which is the right order for a crown perimeter.  The edge width is
    reported in metres so the result cannot be read without it.

  USAGE
    py -3.12 phase4_qc_edge_vs_interior.py \
        --prob  ../phase4/masks/edmonds_canopy_prob_2016.tif \
        --ccap  D:/edmonds-pipeline/Imagery/ccap_2016_hires_lc.tif \
        --ndvi  ../phase4/qc/ndvi_ref_2016.tif \
        --thresh 0.509 --label 2016_baseline --decim 4

  OUTPUT
    phase4/qc/edge_vs_interior_{label}.txt / .csv
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import io
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine

_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE
QC_DIR = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "Scripts" / "logs"

_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
CHM_NAME = "lidar_snoh_chm.tif"
CHM_DN_PER_M = 1.0 / 0.2

HEIGHT_BINS = [0, 2, 5, 10, 15, 20, 25, 30, 100]
CCAP_CANOPY = [9, 10, 11, 13, 16]
NDVI_CANOPY = 2


def resolve_chm():
    for d in (_LOCAL_IMG, _DRIVE_IMG):
        p = d / CHM_NAME
        if p.exists():
            return p
    raise FileNotFoundError(CHM_NAME)


def _band_labels():
    out = []
    for i in range(len(HEIGHT_BINS) - 1):
        lo, hi = HEIGHT_BINS[i], HEIGHT_BINS[i + 1]
        out.append(f"{lo:>2}-{hi:<3}m" if hi < 100 else f"{lo:>2}+   m")
    return out


def erode(m, iters=1):
    """8-connected binary erosion, numpy only (no scipy dependency)."""
    for _ in range(iters):
        p = np.pad(m, 1, mode="constant", constant_values=False)
        m = (p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
             & p[:-2, :-2] & p[:-2, 2:] & p[2:, :-2] & p[2:, 2:])
    return m


def analyse(prob_path, ccap_path, ndvi_path, thresh, decim, erode_iters):
    chm_path = resolve_chm()
    print(f"[edge-vs-interior] prob = {prob_path}")
    print(f"[edge-vs-interior] decim {decim} · erosion {erode_iters} cell(s)")

    thr_u8 = thresh * 254.0
    with rasterio.open(prob_path) as p:
        H, W = p.height // decim, p.width // decim
        dt = p.transform * Affine.scale(decim)
        crs = p.crs
        nodata = 255 if p.nodata is None else p.nodata
        pr = p.read(1, out_shape=(H, W), resampling=Resampling.nearest)
        cell_m = abs(dt.a)

    def warp(path, **kw):
        with rasterio.open(path) as src:
            with WarpedVRT(src, crs=crs, transform=dt, width=W, height=H,
                           resampling=Resampling.nearest, **kw) as v:
                return v.read(1), src.nodata

    rc, ccap_nodata = warp(ccap_path)
    nd, ndvi_nodata = warp(ndvi_path)
    dn, _ = warp(chm_path, src_nodata=0, nodata=0)

    valid = pr != nodata
    if ccap_nodata is not None:
        valid &= rc != ccap_nodata
    valid &= rc != 0
    if ndvi_nodata is not None:
        valid &= nd != ndvi_nodata

    agreed_canopy = valid & np.isin(rc, CCAP_CANOPY) & (nd == NDVI_CANOPY)
    called = pr >= thr_u8

    interior = erode(agreed_canopy, erode_iters)
    edge = agreed_canopy & ~interior

    hgt = (dn.astype(np.float32) - 1.0) / CHM_DN_PER_M
    hgt[dn == 0] = np.nan

    n_bins = len(HEIGHT_BINS) - 1
    R = {"decim": decim, "thresh": thresh, "cell_m": cell_m,
         "edge_m": cell_m * erode_iters, "erode": erode_iters,
         "prob": Path(prob_path).name, "n_agreed": int(agreed_canopy.sum()),
         "parts": {}}

    for name, m in (("interior", interior), ("edge", edge)):
        hit = np.zeros(n_bins, dtype=np.int64)
        miss = np.zeros(n_bins, dtype=np.int64)
        for arr, sel in ((hit, m & called), (miss, m & ~called)):
            hv = hgt[sel]
            hv = hv[np.isfinite(hv)]
            if hv.size:
                idx = np.clip(np.digitize(hv, HEIGHT_BINS) - 1, 0, n_bins - 1)
                arr += np.bincount(idx, minlength=n_bins)

        # IS THE LOSS RECOVERABLE, AND IS IT REAL CANOPY?
        # miss depth: deep misses need labels/architecture; near-threshold ones
        # are reachable by moving the operating point (cf. result 7).
        mv = pr[m & ~called].astype(np.float32)
        deep = float((mv < 0.06 * 254).mean()) if mv.size else float("nan")
        mid = float(((mv >= 0.06 * 254) & (mv < 0.12 * 254)).mean()) if mv.size else float("nan")
        near = float((mv >= 0.12 * 254).mean()) if mv.size else float("nan")
        # CHM on missed vs recalled: if missed edge pixels carry canopy-height
        # returns, they are real canopy the model lost — not reference bleed
        # onto bare ground.
        h_miss = hgt[m & ~called]
        h_hit = hgt[m & called]
        h_miss = h_miss[np.isfinite(h_miss)]
        h_hit = h_hit[np.isfinite(h_hit)]
        R["parts"][name] = {"hit": hit, "miss": miss, "n": int(m.sum()),
                            "n_called": int((m & called).sum()),
                            "n_miss": int((m & ~called).sum()),
                            "deep": deep, "mid": mid, "near": near,
                            "chm_miss": float(h_miss.mean()) if h_miss.size else float("nan"),
                            "chm_hit": float(h_hit.mean()) if h_hit.size else float("nan"),
                            "miss_ge3m": float((h_miss >= 3).mean()) if h_miss.size else float("nan")}
    return R


def report(R, label):
    bands = _band_labels()
    n_bins = len(bands)
    I, E = R["parts"]["interior"], R["parts"]["edge"]
    tot_miss = I["n_miss"] + E["n_miss"]
    edge_share = E["n_miss"] / tot_miss if tot_miss else float("nan")
    edge_area_share = E["n"] / max(R["n_agreed"], 1)

    L = [f"ARE THE MISSES CROWN PERIMETERS? — {label}",
         f"  prob : {R['prob']} @ thresh {R['thresh']}",
         f"  lattice {R['cell_m']:.2f} m/cell · EDGE = outer {R['edge_m']:.2f} m "
         f"({R['erode']} cell erosion) of agreed canopy",
         f"  agreed-canopy cells {R['n_agreed']:,}",
         "",
         "  -- THE HEADLINE " + "-" * 42,
         f"     edge is {100*edge_area_share:.1f}% of agreed-canopy AREA",
         f"     but carries {100*edge_share:.1f}% of ALL MISSES",
         f"     interior recall {I['n_called']/max(I['n'],1):.4f}   "
         f"edge recall {E['n_called']/max(E['n'],1):.4f}",
         ""]
    if edge_share > edge_area_share * 1.5:
        L.append("     -> MISSES ARE DISPROPORTIONATELY PERIMETER. The ring pattern in the")
        L.append("        sentinel overlays is real and general, not two cherry-picked windows.")
    else:
        L.append("     -> misses are NOT concentrated at the perimeter; the sentinel ring")
        L.append("        pattern did NOT generalise. Treat it as a local appearance only.")

    L += ["",
          "  -- THE DECIDING TABLE: recall by height, INTERIOR vs EDGE " + "-" * 4,
          f"     {'band':<11} {'interior':>10} {'edge':>10} {'int n':>14} {'edge n':>14}"]
    for i in range(n_bins):
        it, im = int(I["hit"][i]), int(I["miss"][i])
        et, em = int(E["hit"][i]), int(E["miss"][i])
        if it + im + et + em == 0:
            continue
        ir = it / (it + im) if it + im else float("nan")
        er = et / (et + em) if et + em else float("nan")
        L.append(f"     {bands[i]:<11} {ir:>10.4f} {er:>10.4f} {it+im:>14,} {et+em:>14,}")

    def spread(P):
        lo = sum(int(P["hit"][i]) for i in range(n_bins)
                 if HEIGHT_BINS[i] >= 5 and HEIGHT_BINS[i + 1] <= 15)
        lom = sum(int(P["miss"][i]) for i in range(n_bins)
                  if HEIGHT_BINS[i] >= 5 and HEIGHT_BINS[i + 1] <= 15)
        hi = sum(int(P["hit"][i]) for i in range(n_bins) if HEIGHT_BINS[i] >= 20)
        him = sum(int(P["miss"][i]) for i in range(n_bins) if HEIGHT_BINS[i] >= 20)
        a = lo / (lo + lom) if lo + lom else float("nan")
        b = hi / (hi + him) if hi + him else float("nan")
        return a, b, b - a

    ilo, ihi, isp = spread(I)
    elo, ehi, esp = spread(E)
    L += ["",
          "  -- DOES THE HEIGHT STAIRCASE SURVIVE INSIDE CROWNS? " + "-" * 9,
          f"     INTERIOR  5-15 m {ilo:.4f}   20 m+ {ihi:.4f}   spread {isp:+.4f}",
          f"     EDGE      5-15 m {elo:.4f}   20 m+ {ehi:.4f}   spread {esp:+.4f}",
          ""]
    if isp > 0.15:
        L += ["     -> THE STAIRCASE SURVIVES IN CROWN INTERIORS. Height is a real",
              "        detection axis; it is NOT an artefact of crown geometry.",
              "        RESULT (1) STANDS and the U3 confound test is reinforced."]
    elif isp < 0.05:
        L += ["     -> THE STAIRCASE COLLAPSES in crown interiors — it lived mostly in",
              "        edge pixels. Result (1) would then be substantially a GEOMETRY",
              "        artefact and the height-conditioned-training plan needs rethinking."]
    else:
        L += ["     -> PARTIAL. The staircase weakens but does not vanish inside crowns;",
              "        height and geometry are BOTH contributing. Neither the pure",
              "        height reading nor the pure geometry reading is safe."]

    L += ["",
          "  -- IS THE PERIMETER LOSS RECOVERABLE, AND IS IT REAL CANOPY? " + "-" * 1,
          f"     {'part':<10} {'deep<.06':>9} {'.06-.12':>9} {'.12-thr':>9}"
          f" {'CHM miss':>9} {'CHM hit':>9} {'miss>=3m':>9}"]
    for name in ("interior", "edge"):
        P = R["parts"][name]
        L.append(f"     {name:<10} {P['deep']:>9.3f} {P['mid']:>9.3f} {P['near']:>9.3f}"
                 f" {P['chm_miss']:>8.1f}m {P['chm_hit']:>8.1f}m {P['miss_ge3m']:>9.3f}")
    E_near, E_deep = E["near"], E["deep"]
    L.append("")
    if E_near > 0.5:
        L += [f"     -> {100*E_near:.0f}% of EDGE misses sit above 0.12 and below the operating",
              "        threshold — the perimeter loss is largely NEAR-THRESHOLD, so a lower",
              "        operating point recovers much of it (at a precision cost). It is a",
              "        CALIBRATION/BOUNDARY problem, not missing knowledge."]
    elif E_deep > 0.5:
        L += [f"     -> {100*E_deep:.0f}% of EDGE misses are DEEP (prob<0.06): the model is",
              "        confidently wrong at crown boundaries. A threshold will not fix this;",
              "        it needs boundary-aware supervision."]
    else:
        L += ["     -> edge misses are spread across the confidence range; part is reachable",
              "        by the operating point and part is not."]
    if E["miss_ge3m"] > 0.7:
        L += [f"     -> {100*E['miss_ge3m']:.0f}% of edge misses carry CHM >= 3 m, i.e. they are",
              "        REAL CANOPY the model lost — not the reference bleeding onto bare",
              "        ground. The reference-error caveat is therefore BOUNDED, not fatal."]
    else:
        L += [f"     -> only {100*E['miss_ge3m']:.0f}% of edge misses carry CHM >= 3 m, so a large",
              "        share may be reference over-reach onto ground rather than model error.",
              "        Discount the perimeter share accordingly."]

    L += ["",
          "  -- CAVEATS " + "-" * 47,
          f"     * 'Edge' is defined on a {R['cell_m']:.2f} m lattice. A different decim",
          "       changes the edge width and therefore every number above.",
          "     * Erosion cannot tell a crown perimeter from the boundary of a CLUMP of",
          "       adjacent crowns; both are 'edge' here.",
          "     * The agreed-canopy mask itself comes from two references that disagree",
          "       most at boundaries, so the edge band is also where reference error is",
          "       highest. Some edge FN is reference error, not model error.",
          "     * CHM at crown edges is genuinely lower AND noisier (mixed ground/canopy",
          "       returns), which is the mechanism under test — not a flaw in the test.",
          "     * Decimated sample; shape over exact counts."]

    txt = "\n".join(L)
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"edge_vs_interior_{label}.txt").write_text(txt, encoding="utf-8")
    with io.open(QC_DIR / f"edge_vs_interior_{label}.csv", "w",
                 encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["part", "band_lo_m", "band_hi_m", "recall", "called", "missed",
                    "edge_width_m"])
        for name, P in (("interior", I), ("edge", E)):
            for i in range(n_bins):
                t, m = int(P["hit"][i]), int(P["miss"][i])
                if t + m == 0:
                    continue
                w.writerow([name, HEIGHT_BINS[i], HEIGHT_BINS[i + 1],
                            round(t / (t + m), 4), t, m, round(R["edge_m"], 2)])
    print(f"\n[edge-vs-interior] wrote {QC_DIR / f'edge_vs_interior_{label}.txt'}")
    return edge_share, isp


def main():
    argv = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(
        description="Split agreed-canopy misses into crown INTERIOR vs EDGE and retest "
                    "the height staircase inside crowns.")
    ap.add_argument("--prob", required=True)
    ap.add_argument("--ccap", required=True)
    ap.add_argument("--ndvi", required=True)
    ap.add_argument("--thresh", type=float, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--decim", type=int, default=4)
    ap.add_argument("--erode", type=int, default=1, help="Erosion steps = edge width in cells.")
    args = ap.parse_args(argv)

    R = analyse(Path(args.prob), Path(args.ccap), Path(args.ndvi),
                args.thresh, args.decim, args.erode)
    edge_share, isp = report(R, args.label)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_edge_vs_interior_{args.label}_{ts}.log").write_text(
            f"phase4_qc_edge_vs_interior.py label={args.label} decim={args.decim} "
            f"erode={args.erode} edge_miss_share={edge_share:.4f} "
            f"interior_spread={isp:.4f}\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()

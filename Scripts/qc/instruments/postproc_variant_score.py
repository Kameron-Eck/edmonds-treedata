r"""postproc_variant_score.py — score postproc-knob variants vs the independent ref.

THE INSTRUMENT behind phase4/qc/postproc_variant_scores.csv (recipe deep-dive,
2026-09-01). Measures what each postproc stage does to recall/precision against
the independent C-CAP reference, using PRODUCTION code, not replicas:

  - phase4seg.postproc.threshold_and_clean (imported) applied in the production
    4096-row chunks with no halo -> the mask-raster deliverable's semantics;
  - sieve_min_px + rasterio.features.sieve per polygonize-sized strip,
    connectivity POLYGON_CONNECTIVITY -> the GPKG path's semantics;
  - qc/phase4_qc_indep.score() with QC_DIR redirected to --workdir so NO rows
    land in the honest ledger (these are diagnostics, not arms).

Validated by an EQUIVALENCE ANCHOR: the shipped 2011s hy_e3 mask scored
pixel-identical (tp=60,497,713 fp=9,344,235) to the morph@0.643 replica.

Findings (2026-09-01, both pilot years): morphology and sieve are NEUTRAL
(<=0.6 recall pt, within one u8 quantization step; sieve moves 0.016% of px).
The operating threshold is the only postproc knob with large impact
(2011s: 23 recall pts between the circular-label 0.643 and 0.45).
Full narrative: Reports/RECIPE_AUDIT_2026-09-01.md.

Usage (stage prob rasters to local NVMe first — G: reads are 5-10x slower):
  py -3.12 qc/instruments/postproc_variant_score.py --workdir <scratch> \
     --year 2011s --prob <local prob.tif> --variants 0.643 0.643:sieve 0.45 \
     [--anchor-mask <shipped mask.tif>]
Threshold note: scores here binarize the WRITTEN mask (thresh 0.003 passes
value 1), so they use production's int(round(thr*254)) cut; qc_indep raw-prob
rows compare pr >= thr*254.0 unrounded — one u8 step apart at most.
"""
import argparse
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS / "qc"))   # phase4_qc_indep (qc root, uninstalled)

import numpy as np
import rasterio
import rasterio.features
import rasterio.windows

from phase4seg.postproc import threshold_and_clean, sieve_min_px
from phase4seg.common import _crs_unit_m
from phase4seg.config import TILE_SIZE, POLYGON_CONNECTIVITY, MORPH_KERNEL_SIZE

CHUNK = 4096                             # production step_postproc chunking


def make_variant(prob_path, out_path, thr, do_sieve):
    """thr float -> u8 exactly as production; morph per 4096-row chunk (no halo);
    optional strip-wise sieve exactly as the polygonize path applies it."""
    thr_u8 = int(round(thr * 254))
    kernel = np.ones((MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE), dtype=bool)
    with rasterio.open(prob_path) as src:
        H, W = src.height, src.width
        prof = {"driver": "GTiff", "dtype": "uint8", "width": W, "height": H,
                "count": 1, "crs": src.crs, "transform": src.transform,
                "compress": "lzw", "nodata": 255, "BIGTIFF": "YES"}
        px_true = abs(src.transform.a * src.transform.e) * _crs_unit_m(src.crs) ** 2
        canopy_px = valid_px = 0
        with rasterio.open(out_path, "w", **prof) as dst:
            for r0 in range(0, H, CHUNK):
                r1 = min(r0 + CHUNK, H)
                win = rasterio.windows.Window(0, r0, W, r1 - r0)
                m = threshold_and_clean(src.read(1, window=win), thr_u8, kernel)
                canopy_px += int((m == 1).sum())
                valid_px += int((m != 255).sum())
                dst.write(m[np.newaxis], window=win)
    if do_sieve:
        min_px = sieve_min_px(px_true)
        strip = max(TILE_SIZE, min(H, int(400_000_000 / max(W, 1))))
        sieved_path = out_path.with_name(out_path.stem + "_sv.tif")
        canopy_px = 0
        with rasterio.open(out_path) as src, \
             rasterio.open(sieved_path, "w", **prof) as dst:
            for r0 in range(0, H, strip):
                win = rasterio.windows.Window(0, r0, W, min(strip, H - r0))
                m = src.read(1, window=win)
                clean = rasterio.features.sieve(
                    (m == 1).astype(np.uint8), size=min_px,
                    connectivity=POLYGON_CONNECTIVITY)
                out = np.where(m == 255, 255, clean).astype(np.uint8)
                canopy_px += int((out == 1).sum())
                dst.write(out[np.newaxis], window=win)
        out_path.unlink()
        sieved_path.rename(out_path)
    return canopy_px, valid_px, px_true


def score_mask(qi, ref, year, mask_path, label):
    """Score a {0,1,255} mask via the production scorer.
    thresh=0.003 -> thr_u8=0.762: value 1 passes, 0 fails, 255 excluded."""
    R = qi.score(year, ref, mask_path, 0.003, "ccap", None, 2048)
    prim = R["defs"][R["primary_idx"]]
    tp = sum(R["gmc"][g] for g in prim[1])
    refc = sum(R["gpx"][g] for g in prim[1])
    fp = sum(R["gmc"].values()) - tp
    rec, prec = tp / refc, tp / (tp + fp)
    f1 = 2 * prec * rec / (prec + rec)
    print(f"RESULT {label}: recall={rec:.4f} prec={prec:.4f} f1={f1:.4f} "
          f"tp={tp} fp={fp} refc={refc}", flush=True)
    return dict(label=label, recall=rec, prec=prec, f1=f1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workdir", required=True,
                    help="Local scratch dir; also receives the scorer's txt/csv "
                         "output (the honest ledger is NEVER written).")
    ap.add_argument("--year", required=True)
    ap.add_argument("--prob", required=True, help="LOCAL copy of the prob raster.")
    ap.add_argument("--ref", default=r"D:\edmonds-pipeline\Imagery\ccap_2021_hires_lc.tif")
    ap.add_argument("--variants", nargs="+", required=True,
                    help="thr or thr:sieve, e.g. 0.643 0.643:sieve 0.45")
    ap.add_argument("--anchor-mask", default=None,
                    help="Shipped mask to score as the equivalence anchor.")
    args = ap.parse_args()

    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    import phase4_qc_indep as qi
    qi.QC_DIR = work / "qc_out"          # ledger stays clean
    qi.QC_DIR.mkdir(parents=True, exist_ok=True)
    ref = Path(args.ref)

    rows = []
    for v in args.variants:
        thr_s, _, sv_s = v.partition(":")
        thr, sv = float(thr_s), sv_s == "sieve"
        t0 = time.time()
        tag = f"{args.year}_morph{'_sieve' if sv else ''}@{thr}"
        vp = work / f"variant_{args.year}_{thr}{'_sv' if sv else ''}.tif"
        cpx, vpx, pxa = make_variant(Path(args.prob), vp, thr, sv)
        print(f"variant {tag}: canopy_px={cpx} ({cpx*pxa/1e4:.1f} ha true, "
              f"{100*cpx/vpx:.2f}% of valid)  [{time.time()-t0:.0f}s]", flush=True)
        rows.append(score_mask(qi, ref, args.year, vp, tag))
        vp.unlink()
    if args.anchor_mask:
        rows.append(score_mask(qi, ref, args.year, Path(args.anchor_mask),
                               f"{args.year}_SHIPPED_MASK"))

    print("\n=== FINAL TABLE (independent ref, forest_wetland primary) ===")
    print(f"{'variant':<28}{'recall':>8}{'prec':>8}{'f1':>8}")
    for r in rows:
        print(f"{r['label']:<28}{r['recall']:>8.4f}{r['prec']:>8.4f}{r['f1']:>8.4f}")


if __name__ == "__main__":
    main()

r"""S3.3 — validate lidar_chm2005_2m.tif against ground certified flat by a different tool.

WHY THIS TEST AND NOT A HEIGHT COMPARISON. You cannot validate a 2005 CHM by comparing
it to a 2016 CHM: eleven years of growth and removal mean any difference is signal, not
error, and there is no way to tell which. The one place the two epochs MUST agree is
ground that was flat in BOTH — and that ground already exists as a product:

  verified_background_lidar_2005_2016.tif  (qc/build_lidar_background.py, 2026-08-27)
  cells whose max height above ground was under 2 m in BOTH the 2005 PSLC and the 2016
  USGS clouds, then eroded 6 m. The erosion is what makes it decisive: every cell is
  deep inside a flat area, so no product can excuse a tall reading as a crown clipped at
  a cell edge.

This is exactly the test that exposed the original raster: `lidar_snoh_chm.tif` reads
4.90 m mean on ground the points measure as bare, and calls 57.3% of it taller than 2 m.
A rebuilt product has to beat that, and chm2 did (0.01% on certified-flat ground). If
chm2005 does not, it has inherited the same neighbourhood-maximum defect and should not
be wired into the pipeline.

WHAT THIS DOES NOT ESTABLISH
  * Absolute vertical accuracy. The 2005 record carries TWO figures on different
    metrics, and IMAGERY_FACTS is explicit that both are recorded and neither is
    averaged into the other:
        6.3 cm  fundamental vertical, 95th pct, mixed cover   (Digital Coast)
        25 cm   average / 15-25 cm soft-vegetated             (InPort)
  * Whether chm2005 helps the model. That is S3.5, and it needs shared normalisation
    stats and 3 seeds per arm or it repeats the underpowered chm2 test.

Run:
  py -3.12 qc/validate_chm2005.py
"""
import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
LOCAL = Path(r"D:\edmonds-pipeline\Imagery")

PRODUCTS = [
    ("chm2005 (new, 2 m)", LOCAL / "lidar_chm2005_2m.tif"),
    ("chm2    (2016, .5 m)", LOCAL / "lidar_chm2_2016_50cm.tif"),
    ("chm     (old, inflated)", LOCAL / "lidar_snoh_chm.tif"),
]


def _load_builder():
    spec = importlib.util.spec_from_file_location("_chm2", HERE / "build_chm2_2016.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


B = _load_builder()


def log(m):
    print(m, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--flat-m", type=float, default=2.0,
                    help="a product 'asserts vegetation' above this height")
    ap.add_argument("--out-name", default="chm2005_validation.md")
    a = ap.parse_args([x for x in sys.argv[1:]
                       if not (x == "-f" or x.endswith(".json"))])

    vb = LOCAL / "verified_background_lidar_2005_2016.tif"
    if not vb.exists():
        raise SystemExit(f"missing the independent reference: {vb}")

    with rasterio.open(vb) as v:
        tf, w, h = v.transform, v.width, v.height
        bg = v.read(1) == 1
    cell_m2 = abs(tf.a * tf.e)
    log(f"certified-flat cells: {bg.sum():,} ({bg.sum()*cell_m2/1e6:.2f} km²), "
        f"flat in BOTH 2005 and 2016, eroded 6 m")

    L = ["# chm2005 validation — certified-flat ground (S3.3)", "",
         f"Reference: `verified_background_lidar_2005_2016.tif` — {bg.sum():,} cells "
         f"({bg.sum()*cell_m2/1e6:.2f} km²) measured under 2 m in **both** epochs, then",
         "eroded 6 m so no cell can excuse a tall reading as a clipped crown edge.", "",
         "On this ground every product should read ~0 m. This is the test that exposed",
         "the original raster.", "",
         "| product | mean | p50 | p90 | p99 | asserts >2 m | coverage of flat ground |",
         "|---|---|---|---|---|---|---|"]

    rows = {}
    for lbl, p in PRODUCTS:
        if not p.exists():
            log(f"  ! missing {p.name} — skipped")
            L.append(f"| `{lbl}` | — | — | — | — | **MISSING** | — |")
            continue
        arr = B._warp_to(str(p), tf, w, h, rasterio.enums.Resampling.max)
        m = bg & (arr > 0)
        if not m.any():
            L.append(f"| `{lbl}` | — | — | — | — | no overlap | 0.0% |")
            continue
        hm = B._dn_to_m(arr[m])
        cov = 100.0 * m.sum() / bg.sum()
        pct = 100.0 * (hm > a.flat_m).mean()
        rows[lbl] = dict(mean=hm.mean(), p50=np.percentile(hm, 50),
                         p90=np.percentile(hm, 90), p99=np.percentile(hm, 99),
                         pct=pct, cov=cov)
        L.append(f"| `{lbl}` | {hm.mean():.2f} m | {np.percentile(hm,50):.2f} | "
                 f"{np.percentile(hm,90):.2f} | {np.percentile(hm,99):.2f} | "
                 f"**{pct:.2f}%** | {cov:.1f}% |")
        log(f"  {lbl:26s} mean {hm.mean():5.2f} m  p50 {np.percentile(hm,50):5.2f}  "
            f"p90 {np.percentile(hm,90):5.2f}  >2 m on {pct:6.2f}%  cov {cov:5.1f}%")

    L.append("")
    new = rows.get("chm2005 (new, 2 m)")
    old = rows.get("chm     (old, inflated)")
    ref = rows.get("chm2    (2016, .5 m)")
    if new and old:
        verdict = ("PASS" if new["pct"] <= max(1.0, 0.25 * old["pct"]) else "FAIL")
        L += [f"## Verdict: **{verdict}**", "",
              f"- chm2005 asserts vegetation on **{new['pct']:.2f}%** of certified-flat "
              f"ground; the old raster asserts it on **{old['pct']:.2f}%**."]
        if ref:
            L.append(f"- chm2 (2016 rebuild) asserts it on {ref['pct']:.2f}% — the "
                     f"standard a rebuild is expected to reach.")
        if verdict == "PASS":
            L.append("- chm2005 does **not** carry the neighbourhood-maximum inflation "
                     "that made the original raster unusable on open ground.")
        else:
            L += ["- chm2005 **inherits the defect** and must not be wired into the "
                  "pipeline until the cause is found.",
                  "- Likely suspects in order: the 4 m ground grid interpolating across "
                  "a slope; the 2 m canopy max picking a neighbouring crown; or the "
                  "pull-push fill reaching too far in sparse ground."]
        L.append("")

    L += ["## Vertical accuracy — both figures, never averaged", "",
          "| source | figure | metric |", "|---|---|---|",
          "| Digital Coast | **6.3 cm** | fundamental vertical, 95th pct, mixed cover |",
          "| InPort | **25 cm** avg, 15–25 cm soft-vegetated | different metric |", "",
          "IMAGERY_FACTS is explicit that these are different metrics and that both are",
          "recorded rather than reconciled. A 2 m cell dominates either figure anyway.", "",
          "## What this does not establish", "",
          "- Whether chm2005 improves the model (S3.5 — needs shared normalisation stats",
          "  and 3 seeds per arm, or it repeats the underpowered chm2 test).",
          "- Accuracy under canopy, where no independent reference exists.", ""]

    out = Path(r"D:\edmonds-pipeline\treedata\phase4\qc") / a.out_name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    log(f"[validate] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

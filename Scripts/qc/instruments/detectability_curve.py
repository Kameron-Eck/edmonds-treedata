"""detectability_curve.py — recall as a function of crown size, per epoch. Measured, not transferred.

THE CORRECTION THIS IMPLEMENTS (Kam, 2026-09-06): "Perhaps the detectability should be on a
curve. So we can measure how detectability threshold impacts the recall."

Right, and it fixes a real weakness. Every detectability number this project has quoted for
crown size came from the LITERATURE — Hao 2023's 50 px/tree floor, Pouliot 2002's
crown-diameter RMSE ladder — and the angle-10 audit ruled both transfers shaky: Hao measured a
weeded single-species Chinese-fir plantation from sub-centimetre drone imagery, and Pouliot's
own adjudicating skeptic ruled his crown-to-pixel ladder inapplicable to urban crowns, whose
ratios run three to four times beyond anything he tested. Asserting "mature crowns are
detectable, saplings are not" from those sources is a borrowed cutoff.

This measures OUR curve on OUR archive, so the size threshold becomes an operating point read
off a curve rather than a constant asserted from someone else's forest.

THE ESTIMATOR. A crown is taken as PRESENT at epoch t when the epochs on both sides of t see
it — bracketing evidence, which comes from imagery other than t's. Recall at t is then the
fraction of bracketed crowns that t also sees, binned by crown diameter. The evidence for
presence never comes from the epoch being scored, so the measurement is not circular in the
way a self-scored recall would be.

WHAT IT CANNOT SEE, stated plainly because it bounds every number below:
  * A crown missed in EVERY epoch is never bracketed and never counted. This is therefore
    recall CONDITIONAL on the crown being detectable somewhere in the series — an upper bound
    on true recall, not an estimate of it.
  * Crowns are the frozen 2020 delineation. For a pre-2020 loss the polygon may outline a
    replacement rather than the original, and a crown genuinely removed before t is
    indistinguishable here from one t failed to see — which is precisely why only BRACKETED
    crowns are scored: a real removal breaks the bracket.
  * Cover is computed on the 2 m analysis lattice, so the smallest bins are coarse by
    construction: a 2 m crown is about one cell.

Output: phase4/qc/detectability_curve.csv — one row per (epoch, size bin); cumulative rows
giving recall for all crowns at or above each threshold, which is the form a sieve design
actually consumes; and `conditional_cover` rows giving the mean measured extent, per epoch,
of the crowns EVERY epoch sees. That last family answers a different question from the
curve: given that an epoch finds a crown, does it outline it the same size as the others?
The gap between the two is the gap between a DETECTION problem and a DELINEATION problem.

Run:  py -3.12 qc/instruments/detectability_curve.py            (local CPU, ~1-2 min)
      py -3.12 qc/instruments/detectability_curve.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

STACK = Path(r"D:\edmonds-pipeline\trend8_stack_2m.npz")
CROWNS = Path(r"D:\edmonds-pipeline\backup\inference\edmonds_crowns_2020.gpkg")

# Effective (measured) resolution per epoch — NOT nominal GSD. qc/imagery_pixelsize_and_date.csv
# is the home; these are carried here only to report px/crown alongside recall.
EFF_CM = {"2009": 26.1, "2011s": 38.1, "2013": 13.2, "2015": 13.7,
          "2016": 35.4, "2019": 12.6, "2021": 12.6, "2024": 6.8}

# Crown-diameter bins in metres. Fine at the bottom (where the curve turns) and open-ended
# at the top (mature crowns, the regime a mature-crown sieve operates in).
BINS = [(0, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 8), (8, 10), (10, 14), (14, 999)]
COVER_DETECT = 0.50      # a crown counts as SEEN when half its area reads canopy


def load():
    import geopandas as gpd
    import numpy as np
    import rasterio.features
    from affine import Affine

    d = np.load(STACK)
    stack, inside = d["stack"], d["inside"]
    years = [str(y) for y in d["years"]]
    tf = Affine(*d["transform"])

    g = gpd.read_file(CROWNS)
    # The stack lattice is the analysis grid; crowns arrive in web mercator.
    g = g.to_crs("EPSG:26910")
    g = g[g.geometry.notna() & (g["diameter_m"] > 0)].reset_index(drop=True)
    g["idx"] = range(1, len(g) + 1)          # 0 is the raster's "no crown"

    ids = rasterio.features.rasterize(
        ((geom, i) for geom, i in zip(g.geometry, g["idx"])),
        out_shape=inside.shape, transform=tf, fill=0, dtype="int32")
    return stack, inside, years, g, ids


def per_crown_cover(stack_epoch, ids, n_crowns, valid_only):
    """Return (canopy_frac, valid_frac) per crown id, on the 2 m lattice."""
    import numpy as np
    flat_ids = ids.ravel()
    m = flat_ids > 0
    ids_m = flat_ids[m]
    px = stack_epoch.ravel()[m]
    total = np.bincount(ids_m, minlength=n_crowns + 1).astype(float)
    valid = np.bincount(ids_m, weights=(px != 255).astype(float),
                        minlength=n_crowns + 1)
    canopy = np.bincount(ids_m, weights=(px == 1).astype(float),
                         minlength=n_crowns + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(valid > 0, canopy / np.maximum(valid, 1), np.nan)
        vfrac = np.where(total > 0, valid / np.maximum(total, 1), np.nan)
    if valid_only:
        frac = np.where(vfrac >= 0.5, frac, np.nan)
    return frac


def build():
    import numpy as np
    if not STACK.exists() or not CROWNS.exists():
        return None, f"need {STACK.name} and {CROWNS.name} (local mirror)"

    stack, inside, years, g, ids = load()
    n = len(g)
    cov = np.vstack([per_crown_cover(stack[i], ids, n, True)
                     for i in range(len(years))])           # (epochs, crowns+1)
    seen = cov >= COVER_DETECT
    diam = np.full(n + 1, np.nan)
    diam[g["idx"].to_numpy()] = g["diameter_m"].to_numpy()

    rows = []
    for t in range(1, len(years) - 1):                       # interior epochs only
        # BRACKETED: both neighbours see it. Evidence from imagery other than epoch t.
        brack = seen[t - 1] & seen[t + 1]
        hit = brack & seen[t]
        for lo, hi in BINS:
            sel = brack & (diam >= lo) & (diam < hi)
            k = int(sel.sum())
            if k == 0:
                continue
            det = int((hit & sel).sum())
            px = (np.pi / 4) * (((lo + hi) / 2 * 100) / EFF_CM[years[t]]) ** 2
            rows.append({
                "epoch": years[t], "eff_cm": EFF_CM[years[t]],
                "kind": "bin", "diam_lo_m": lo, "diam_hi_m": hi if hi < 999 else "",
                "n_bracketed": k, "n_detected": det,
                "recall": round(det / k, 4),
                "px_per_crown_at_eff_gsd": round(px, 1),
            })
        # CUMULATIVE: what a sieve with a minimum-diameter threshold would capture.
        for lo, _ in BINS:
            sel = brack & (diam >= lo)
            k = int(sel.sum())
            if k == 0:
                continue
            det = int((hit & sel).sum())
            rows.append({
                "epoch": years[t], "eff_cm": EFF_CM[years[t]],
                "kind": "cumulative_ge", "diam_lo_m": lo, "diam_hi_m": "",
                "n_bracketed": k, "n_detected": det,
                "recall": round(det / k, 4), "px_per_crown_at_eff_gsd": "",
            })
    # ---- conditional delineation: on crowns EVERY epoch sees, how much does the
    # measured extent differ between epochs? This separates a DETECTION problem from a
    # DELINEATION problem, and the answer decides whether a transplant needs a scale
    # parameter at all.
    allseen = np.all(seen, axis=0)
    for i, y in enumerate(years):
        mc = float(np.nanmean(cov[i, allseen]))
        rows.append({
            "epoch": y, "eff_cm": EFF_CM[y], "kind": "conditional_cover",
            "diam_lo_m": "", "diam_hi_m": "",
            "n_bracketed": int(allseen.sum()), "n_detected": "",
            "recall": round(mc, 4), "px_per_crown_at_eff_gsd": "",
        })
    return rows, None


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    rows, err = build()
    if err:
        print(f"FATAL: {err}")
        return 2

    cols = ["epoch", "eff_cm", "kind", "diam_lo_m", "diam_hi_m",
            "n_bracketed", "n_detected", "recall", "px_per_crown_at_eff_gsd"]
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    if not a.dry_run:
        QC.mkdir(parents=True, exist_ok=True)
        (QC / "detectability_curve.csv").write_text(buf.getvalue(), encoding="utf-8",
                                                    newline="")

    print(f"{'DRY RUN: ' if a.dry_run else ''}phase4/qc/detectability_curve.csv "
          f"({len(rows)} rows)")
    print("\nRECALL BY CROWN DIAMETER (bracketed crowns; interior epochs)")
    eps = sorted({r["epoch"] for r in rows}, key=lambda e: -EFF_CM[e])
    hdr = "  size (m)  " + "".join(f"{e:>9}" for e in eps)
    print(hdr)
    print("  " + " " * 9 + "".join(f"{EFF_CM[e]:>8.1f}c" for e in eps))
    for lo, hi in BINS:
        lab = f"{lo}-{hi}" if hi < 999 else f"{lo}+"
        line = f"  {lab:>9} "
        for e in eps:
            m = [r for r in rows if r["epoch"] == e and r["kind"] == "bin"
                 and r["diam_lo_m"] == lo]
            line += f"{m[0]['recall']:>9.3f}" if m else f"{'—':>9}"
        print(line)
    print("\n  read down a column: how this epoch's sensitivity falls off with crown size")
    print("  read across a row:  how much of that fall-off is resolution")
    return 0


if __name__ == "__main__":
    sys.exit(main())

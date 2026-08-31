r"""How much of a tile is one tree? The object-ratio diagnostic (plan item 4.6).

THE QUESTION, AND WHY IT IS WORTH AN HOUR. Tiles are a fixed 512 PIXELS, so the GROUND they
cover scales with GSD: the same tile is ~66 m across at 13 cm and ~420 m across at 82 cm.
A crown does not scale — it is the same tree. So the tree-to-tile ratio varies by ~6x across
the archive, and every tier trains on a different amount of context per sample without
anything in the recipe saying so.

THREE MEASUREMENTS ABOUT THIS ONE QUANTITY CURRENTLY DISAGREE:

  (a) Recorded 2026-08-27: the varying object ratio is a candidate explanation for coarse
      years UNDERperforming, independent of labels and radiometry.
  (b) Measured 2026-08-31 (the 2019 pilot): coarse BEAT medium on the same date —
      2019n eff 82.5 cm rec 0.6915 prec 0.7858 vs 2019s eff 42.6 cm rec 0.6331 prec 0.7735.
      The opposite direction from (a).
  (c) Measured 2026-08-30 (ERF, 16 real tiles): 50% of a prediction's influence sits inside
      106 px of a 512 px tile. In GROUND terms that is ~14 m at 13 cm and ~87 m at 82 cm.

This script computes the ratios so (a), (b) and (c) can be read against each other instead
of quoted separately.

CROWN SIZE IS MEASURED, NOT ASSUMED — 20,000 crowns sampled from the Phase-0 layer and
reprojected to EPSG:26910 for TRUE areas, because the stored area_m2 is EPSG:3857 and
inflated ~2.22x at this latitude (the CRS-unit trap this repo already records). Median
equivalent-circle diameter 6.46 m; p10 3.57, p90 10.33.

GSD IS THE MEASURED effective_cm where the date table has it, NOT the nominal — nominal lies
here, and by a lot: 2019n is delivered at 60 cm and resolves at 82.5 cm, 2005 is nominally
20 cm and resolves at 80.7.

  py -3.12 qc/tile_object_ratio.py
  py -3.12 qc/tile_object_ratio.py --crown-m 10.33     # p90 crowns instead of the median
"""
import argparse
import csv
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))

from phase4seg import config as C          # noqa: E402
from phase4seg.common import tier_for      # noqa: E402

# Measured 2026-08-31 from 20,000 Phase-0 crowns, true EPSG:26910 areas.
CROWN_MEDIAN_M = 6.46
ERF_PX = 106                               # qc/phase4_erf.py, RepLKNet method, 16 real tiles
DATE_TABLE = SCRIPTS / "qc" / "imagery_pixelsize_and_date.csv"


def effective_cm_by_label():
    """label -> measured effective_cm. Falls back to nominal, and SAYS so."""
    out = {}
    if not DATE_TABLE.exists():
        return out
    for r in csv.DictReader(open(DATE_TABLE, encoding="utf-8")):
        lab = (r.get("year_label") or "").strip()
        raw = (r.get("effective_cm") or "").strip()
        if not lab or not raw:
            continue
        # the column carries prose for some rows ("42.58 (median of 5 sites; ...)")
        head = raw.split("(")[0].strip().split("-")[0].strip()
        try:
            val = float(head)
        except ValueError:
            continue
        key = lab.split(" ")[0].strip()
        out.setdefault(key, val)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crown-m", type=float, default=CROWN_MEDIAN_M,
                    help=f"crown diameter in metres (default {CROWN_MEDIAN_M}, the "
                         f"measured median)")
    ap.add_argument("--csv", type=str, default=None, help="write rows here")
    a = ap.parse_args()

    eff = effective_cm_by_label()
    tile_px = C.TILE_SIZE
    rows = []
    for e in sorted(C.YEAR_CATALOG, key=lambda x: str(x["label"])):
        lab = str(e["label"])
        nominal = float(e["gsd_cm"])
        cm = eff.get(lab, nominal)
        measured = lab in eff
        m_per_px = cm / 100.0
        tile_m = tile_px * m_per_px
        crown_px = a.crown_m / m_per_px
        crowns_per_edge = tile_m / a.crown_m
        erf_m = ERF_PX * m_per_px
        erf_per_crown = erf_m / a.crown_m
        rows.append(dict(label=lab, tier=tier_for(e), nominal_cm=round(nominal, 2),
                         gsd_cm=round(cm, 2), measured=int(measured),
                         tile_m=round(tile_m, 1), crown_px=round(crown_px, 1),
                         crowns_per_tile_edge=round(crowns_per_edge, 1),
                         erf_m=round(erf_m, 1),
                         erf_per_crown=round(erf_per_crown, 2)))

    print(f"tile = {tile_px} px   crown = {a.crown_m} m (measured median)   "
          f"ERF = {ERF_PX} px")
    print(f"{'label':7s} {'tier':7s} {'gsd_cm':>7s} {'src':4s} {'tile_m':>7s} "
          f"{'crown_px':>9s} {'crowns/edge':>12s} {'erf_m':>7s} {'erf/crown':>10s}")
    for r in rows:
        print(f"{r['label']:7s} {r['tier']:7s} {r['gsd_cm']:7.2f} "
              f"{'meas' if r['measured'] else 'NOM ':4s} {r['tile_m']:7.1f} "
              f"{r['crown_px']:9.1f} {r['crowns_per_tile_edge']:12.1f} "
              f"{r['erf_m']:7.1f} {r['erf_per_crown']:10.2f}")

    by_tier = {}
    for r in rows:
        by_tier.setdefault(r["tier"], []).append(r)
    print()
    print("PER TIER (median):")
    for t in ("fine", "medium", "coarse"):
        g = by_tier.get(t) or []
        if not g:
            continue
        def med(k):
            v = sorted(x[k] for x in g)
            return v[len(v) // 2]
        print(f"  {t:7s} n={len(g):2d}  tile={med('tile_m'):7.1f} m  "
              f"crown={med('crown_px'):6.1f} px  crowns/edge={med('crowns_per_tile_edge'):6.1f}  "
              f"ERF={med('erf_m'):6.1f} m  ERF/crown={med('erf_per_crown'):5.2f}")

    spans = [r["tile_m"] for r in rows]
    print()
    print(f"tile ground span spans {min(spans):.0f}-{max(spans):.0f} m "
          f"({max(spans)/min(spans):.1f}x) across the archive, from ONE fixed 512 px tile.")
    fine = by_tier.get("fine") or []
    coarse = by_tier.get("coarse") or []
    if fine and coarse:
        f_epc = sorted(x["erf_per_crown"] for x in fine)[len(fine) // 2]
        c_epc = sorted(x["erf_per_crown"] for x in coarse)[len(coarse) // 2]
        print(f"ERF covers {f_epc:.2f} crown-widths at the fine end and {c_epc:.2f} at the "
              f"coarse end.")
        print("READ THIS AGAINST: (a) the 2026-08-27 note predicting COARSE-year "
              "underperformance from")
        print("  the object ratio, and (b) the 2019 pilot, which measured coarse BEATING "
              "medium on one date.")
        print("  If the ERF is the binding constraint, (b) is what the numbers predict and "
              "(a) is backwards.")

    if a.csv:
        with open(a.csv, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

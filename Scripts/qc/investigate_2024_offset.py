r"""2024 cross-source offset — what is it, and which file is displaced?

FINDING UNDER INVESTIGATION (QC suite, 2026-08-24)
  2020_coe vs 2020_snoh_3in : offset 0.00 m, r 0.995  -> same pixels, same georeferencing
  2022_coe vs 2022_snoh_3in : offset 0.00 m, r 0.996  -> same pixels, same georeferencing
  2024_coe vs 2024_snoh_3in : offset 1.29 m, r 0.682  -> ???
The 1.29 m is systematic (five scattered sites agree to 0.03 m), so it is not noise. But r
alone cannot tell us what it means: a 1.29 m shift is ~17 px on the 7.62 cm grid, and shifting
two identical images by 17 px would depress r on its own. Two experiments settle it.

EXPERIMENT 1 — shift-corrected correlation.
  Re-correlate the 2024 pair AFTER removing the measured shift. If r jumps to ~0.99 the two
  files are the SAME imagery with a georeferencing discrepancy; if it stays low they are
  genuinely different acquisitions that happen to share a year.

EXPERIMENT 2 — which one moved?
  Both 2020 files agree with each other, so 2020 is a trustworthy positional reference.
  Align each 2024 file to 2020_coe and to 2020_snoh_3in independently. Real change over four
  years lowers r, but phase correlation locks on the stable built environment. Whichever 2024
  file sits ~0 m from BOTH 2020 files is correctly georeferenced; the other is the displaced one.

Writes phase4/qc/investigate_2024_offset_<date>.json + a printed verdict. Measures only.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))
sys.path.insert(0, str(SCRIPTS / "qc"))
import imagery_measure as im               # noqa: E402
import imagery_qc_suite as QS              # noqa: E402

# Resolve through the catalog, never by hardcoded root: the city (CoE) copies live on the
# Drive data plane while the county copies are on the local D: mirror, and imagery_roots()
# is the only thing that knows which root each file actually resolved to on this machine.
_INV = {r["key"]: r["path"] for r in QS.inventory()}
F = {"2020_coe": _INV["2020"], "2020_snoh": _INV["2020s"],
     "2022_coe": _INV["2022"], "2022_snoh": _INV["2022s"],
     "2024_coe": _INV["2024"], "2024_snoh": _INV["2024s"]}
BOX_M = 200.0


def corr(a, b, ok=None):
    m = ok if ok is not None else np.ones(a.shape, dtype=bool)
    if m.sum() < 500:
        return None
    return float(np.corrcoef(a[m], b[m])[0, 1])


def shift_correct(A, B, dx, dy):
    """Crop both arrays to their overlap after removing an integer (dx, dy) shift of A vs B."""
    ix, iy = int(round(dx)), int(round(dy))
    h, w = A.shape
    ax0, bx0 = (max(0, -ix), max(0, ix))
    ay0, by0 = (max(0, -iy), max(0, iy))
    ww, hh = w - abs(ix), h - abs(iy)
    if ww < 64 or hh < 64:
        return None, None
    return A[ay0:ay0 + hh, ax0:ax0 + ww], B[by0:by0 + hh, bx0:bx0 + ww]


def pair(pa: Path, pb: Path, label: str):
    """Offset + raw r + shift-corrected r, median over the five sites."""
    raw, fixed, offs, dxs, dys = [], [], [], [], []
    for site, (lon, lat) in im.SITES.items():
        A, B, g = QS.common_grid_pair(pa, pb, lon, lat, BOX_M)
        if A is None:
            continue
        ok = (A > 0) & (B > 0)
        if ok.mean() < 0.5:
            continue
        sh = QS.phase_shift(A, B)
        if sh is None:
            continue
        dx, dy, peak = sh
        r0 = corr(A, B, ok)
        A2, B2 = shift_correct(A, B, dx, dy)
        r1 = corr(A2, B2, (A2 > 0) & (B2 > 0)) if A2 is not None else None
        if r0 is not None:
            raw.append(r0)
        if r1 is not None:
            fixed.append(r1)
        offs.append(float(np.hypot(dx, dy) * g))
        dxs.append(dx * g)
        dys.append(dy * g)
    med = lambda v: round(float(np.median(v)), 4) if v else None       # noqa: E731
    out = dict(pair=label, n_sites=len(offs), offset_m=med(offs),
               dx_m=med(dxs), dy_m=med(dys), r_raw=med(raw), r_shift_corrected=med(fixed))
    out["r_gain"] = round(out["r_shift_corrected"] - out["r_raw"], 4) if (out["r_raw"] and out["r_shift_corrected"]) else None
    print(f"  {label:26s} offset {out['offset_m']}m  r {out['r_raw']} -> {out['r_shift_corrected']} "
          f"(gain {out['r_gain']})", flush=True)
    return out


def main():
    res = {"date": dt.date.today().isoformat(), "box_m": BOX_M, "pairs": []}
    print("EXPERIMENT 1 — same imagery, or different acquisitions?")
    print("  (controls first: 2020 and 2022 are known same-pixel pairs)")
    for lab, a, b in (("2020_coe|2020_snoh", "2020_coe", "2020_snoh"),
                      ("2022_coe|2022_snoh", "2022_coe", "2022_snoh"),
                      ("2024_coe|2024_snoh", "2024_coe", "2024_snoh")):
        res["pairs"].append(pair(F[a], F[b], lab))

    print("\nEXPERIMENT 2 — which 2024 file is displaced? (2020 pair = positional reference)")
    for lab, a, b in (("2024_coe|2020_coe", "2024_coe", "2020_coe"),
                      ("2024_coe|2020_snoh", "2024_coe", "2020_snoh"),
                      ("2024_snoh|2020_coe", "2024_snoh", "2020_coe"),
                      ("2024_snoh|2020_snoh", "2024_snoh", "2020_snoh"),
                      ("2022_coe|2020_coe", "2022_coe", "2020_coe")):     # control: a year gap, no known offset
        res["pairs"].append(pair(F[a], F[b], lab))

    g = {p["pair"]: p for p in res["pairs"]}
    v24 = g["2024_coe|2024_snoh"]
    same_imagery = (v24["r_shift_corrected"] or 0) > 0.95
    coe_off = np.median([g["2024_coe|2020_coe"]["offset_m"], g["2024_coe|2020_snoh"]["offset_m"]])
    snoh_off = np.median([g["2024_snoh|2020_coe"]["offset_m"], g["2024_snoh|2020_snoh"]["offset_m"]])
    res["verdict"] = {
        "same_imagery_after_shift_correction": bool(same_imagery),
        "r_raw": v24["r_raw"], "r_shift_corrected": v24["r_shift_corrected"],
        "2024_coe_offset_vs_2020_m": round(float(coe_off), 3),
        "2024_snoh_offset_vs_2020_m": round(float(snoh_off), 3),
        "displaced_file": ("2024_coe_rgb.tif" if coe_off > snoh_off + 0.5 else
                           "2024_snoh_3in_rgb.tif" if snoh_off > coe_off + 0.5 else
                           "INCONCLUSIVE — both sit similar distances from the 2020 reference"),
    }
    print("\nVERDICT")
    for k, v in res["verdict"].items():
        print(f"  {k}: {v}")
    out = SCRIPTS.parent / "phase4" / "qc" / f"investigate_2024_offset_{res['date']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"\n  -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

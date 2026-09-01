r"""coregistration.py — the per-year registration-error table (STATS_CHECKLIST item 4).

WHY: cross-year change statistics die on positional disagreement — one pixel of
misregistration at 60 cm turns every crown edge into "change". Nothing recorded how
far each acquisition's geometry sits from its peers; this measures it.

HOW (classical, deterministic, self-selecting — no manual anchor picking):
  1. Candidate chips on a uniform grid inside the city polygon (~500 m spacing).
  2. Both years' chips are read through WarpedVRT onto the ANALYSIS GRID at the
     pair's common support (the coarser member's ground pixel), so feet/Mercator
     never touch the arithmetic.
  3. PHASE CORRELATION per chip: FFT cross-power spectrum -> inverse -> the peak's
     offset IS the local shift; 3-point parabola gives sub-pixel. A bad anchor (lawn,
     shadow, real change, repaved lot) produces a weak smeared peak and REJECTS
     ITSELF via the peak-quality threshold — the measurement grades its own anchors,
     and n_used/n_tried records how selective it had to be.
  4. Robust per-pair stats: median shift vector (a consistent direction = a
     correctable georeferencing offset; scatter = ortho residuals, only boundable),
     p68/p95 magnitude in TRUE metres.

ANCHOR: 2020s (local, 3-inch, leaf-on) carries the 35 legs; ONE measured bridge row
2020s<->2020 (the label source, Drive-resident) connects every leg to the imagery
the labels came from. Any pair's error is bounded by its two anchor legs (triangle
inequality) — 36 rows instead of 630.

Writes: phase4/qc/coregistration.csv     (gated: qc/test_analysis_grid.py)

    py -3.12 qc/instruments/coregistration.py [--only 2005] [--chips 90]
"""
import argparse
import csv
import datetime as _dt
from pathlib import Path

import numpy as np

from phase4seg.names import clean_argv

SCRIPTS = Path(__file__).resolve().parents[2]  # instruments/ -> qc/ -> Scripts/
OUT = SCRIPTS.parent / "phase4" / "qc" / "coregistration.csv"
ANCHOR = "2020s"
BRIDGE = "2020"          # the label source; Drive-resident, fewer chips
CHIP_GROUND_M = 64.0     # constant GROUND extent per chip — v1 sized chips in
                         # PIXELS, so fine pairs measured ~10 m chips with a
                         # +/-0.9 m detection window (right-censoring their p95)
                         # while coarse pairs got 100+ m. One ruler now.
QUALITY_MIN = 4.0        # peak / mean(|surface|) — below this a chip self-rejects
MAX_SHIFT_M = 8.0        # a "peak" farther than this is a false lock, reject

COLS = ["label", "vs", "n_tried", "n_used", "median_dx_m", "median_dy_m",
        "p68_mag_m", "p95_mag_m", "support_m", "chip_ground_m",
        "systematic", "measured_utc", "note"]


def _city():
    import geopandas as gpd
    from imagery_measure import CITY_SHP
    from phase4seg.config import ANALYSIS_GRID_EPSG
    g = gpd.read_file(CITY_SHP).to_crs(epsg=ANALYSIS_GRID_EPSG)
    return g.union_all() if hasattr(g, "union_all") else g.unary_union


def _grid_points(poly, spacing_m):
    minx, miny, maxx, maxy = poly.bounds
    from shapely.geometry import Point
    pts = []
    y = miny + spacing_m / 2
    while y < maxy:
        x = minx + spacing_m / 2
        while x < maxx:
            if poly.contains(Point(x, y)):
                pts.append((x, y))
            x += spacing_m
        y += spacing_m
    return pts


def _entry(label):
    from phase4seg.config import YEAR_CATALOG
    return next(e for e in YEAR_CATALOG if str(e["label"]) == label)


def _open_on_grid(label, support_m):
    """WarpedVRT of a year's ortho on the analysis grid at the given support."""
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from rasterio.crs import CRS
    from phase4seg.config import ANALYSIS_GRID_EPSG, resolve_imagery
    path, _ = resolve_imagery(_entry(label)["native_file"])
    src = rasterio.open(path)
    vrt = WarpedVRT(src, crs=CRS.from_epsg(ANALYSIS_GRID_EPSG),
                    resampling=Resampling.bilinear)
    return src, vrt


def _chip_px(support_m):
    return int(np.clip(round(CHIP_GROUND_M / support_m), 64, 512))


def _chip(vrt, x, y, support_m):
    """Square chip of ~CHIP_GROUND_M metres of ground, centred on (x, y)."""
    import rasterio.windows
    n = _chip_px(support_m)
    half = n * support_m / 2
    win = rasterio.windows.from_bounds(x - half, y - half, x + half, y + half,
                                       transform=vrt.transform)
    return vrt.read(1, window=win, out_shape=(n, n)).astype(np.float32)


def phase_shift(a, b):
    """(dx_px, dy_px, quality) — b's offset relative to a via phase correlation."""
    n = a.shape[0]
    w = np.hanning(n)
    win2 = np.outer(w, w)
    fa, fb = np.fft.fft2(a * win2), np.fft.fft2(b * win2)
    cross = fa * np.conj(fb)
    denom = np.abs(cross)
    denom[denom == 0] = 1e-9
    surf = np.abs(np.fft.ifft2(cross / denom))
    py_, px_ = np.unravel_index(np.argmax(surf), surf.shape)
    quality = float(surf[py_, px_] / (surf.mean() + 1e-12))

    def sub(v_m1, v_0, v_p1):
        d = (v_m1 - v_p1) / (2 * (v_m1 - 2 * v_0 + v_p1) + 1e-12)
        return float(np.clip(d, -0.5, 0.5))
    dy = py_ + sub(surf[(py_ - 1) % n, px_], surf[py_, px_], surf[(py_ + 1) % n, px_])
    dx = px_ + sub(surf[py_, (px_ - 1) % n], surf[py_, px_], surf[py_, (px_ + 1) % n])
    if dx > n / 2:
        dx -= n
    if dy > n / 2:
        dy -= n
    return dx, dy, quality


def measure_pair(label, ref_label, points, geo):
    """One table row: `label` measured against `ref_label` on their common support."""
    ga = float(geo[ref_label]["px_ground_x_m"])
    gb = float(geo[label]["px_ground_x_m"])
    support = max(ga, gb)
    src_a, vrt_a = _open_on_grid(ref_label, support)
    src_b, vrt_b = _open_on_grid(label, support)
    shifts = []
    tried = 0
    try:
        for (x, y) in points:
            tried += 1
            a = _chip(vrt_a, x, y, support)
            b = _chip(vrt_b, x, y, support)
            if a.std() < 4 or b.std() < 4:        # featureless chip (water, void)
                continue
            dx, dy, q = phase_shift(a, b)
            if q < QUALITY_MIN or max(abs(dx), abs(dy)) * support > MAX_SHIFT_M:
                continue
            shifts.append((dx * support, dy * support))
    finally:
        vrt_a.close(); src_a.close(); vrt_b.close(); src_b.close()
    row = dict(label=label, vs=ref_label, n_tried=tried, n_used=len(shifts),
               support_m=round(support, 4),
               chip_ground_m=round(_chip_px(support) * support, 1))
    if len(shifts) >= 8:
        arr = np.array(shifts)
        mags = np.hypot(arr[:, 0], arr[:, 1])
        mdx, mdy = float(np.median(arr[:, 0])), float(np.median(arr[:, 1]))
        row.update(median_dx_m=round(mdx, 3), median_dy_m=round(mdy, 3),
                   p68_mag_m=round(float(np.percentile(mags, 68)), 3),
                   p95_mag_m=round(float(np.percentile(mags, 95)), 3),
                   # systematic if the median vector explains most of the p68 energy
                   systematic=int(np.hypot(mdx, mdy) > 0.6 * np.percentile(mags, 68)
                                  and np.hypot(mdx, mdy) > 0.05))
    else:
        row["note"] = f"only {len(shifts)} usable chips — UNDETERMINED, not zero"
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", help="single label to (re)measure")
    ap.add_argument("--chips", type=int, default=90, help="grid target for local files")
    a = ap.parse_args(clean_argv())
    from phase4seg.config import YEAR_CATALOG
    geo = {r["label"]: r for r in csv.DictReader(
        (SCRIPTS.parent / "phase4" / "qc" / "imagery_geometry.csv").open(encoding="utf-8"))}
    poly = _city()
    spacing = max(300.0, (poly.area / a.chips) ** 0.5)
    points = _grid_points(poly, spacing)
    print(f"{len(points)} candidate chips (spacing {spacing:.0f} m)")
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    labels = [str(e["label"]) for e in YEAR_CATALOG if str(e["label"]) != ANCHOR]
    if a.only:
        labels = [a.only]
    rows = []
    for lab in sorted(labels):
        pts = points if geo.get(lab, {}).get("root") == "local" else points[::3]
        ref = ANCHOR if lab != BRIDGE else ANCHOR   # bridge measured like any leg
        try:
            r = measure_pair(lab, ref, pts, geo)
        except Exception as ex:                      # noqa: BLE001 — record, not crash
            r = dict(label=lab, vs=ref, note=f"failed: {ex}"[:160])
        r["measured_utc"] = ts
        r.setdefault("note", "")
        rows.append(r)
        print(f"  {lab:<7} vs {r['vs']:<6} used {r.get('n_used', 0):>3}/{r.get('n_tried', 0):<3}"
              f"  median ({r.get('median_dx_m', '—')}, {r.get('median_dy_m', '—')}) m"
              f"  p95 {r.get('p95_mag_m', '—')} m  {r['note']}")
    if not a.only:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in COLS})
        print(f"\nwrote {OUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

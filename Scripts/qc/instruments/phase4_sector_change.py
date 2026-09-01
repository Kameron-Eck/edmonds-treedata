r"""Paired sector change + strip-slope trend for the Edmonds sector series (2026-08-25).

WHAT. Pure post-processing of `qc/instruments/phase4_sector_series.py`'s output
`sector_canopy_series.csv`. Nothing here re-reads a raster; nothing here re-thresholds.
Two design-based products, both from the SAME 5 sampled sector strips:

  (1) PAIRED CHANGE between consecutive years of ONE arm. Per-strip differences
      D_h = p_h(t2) - p_h(t1); the estimate is the area-weighted sum(W_h * D_h).
      Pairing WITHIN a strip removes the strip-to-strip level differences that
      dominate the single-year variance, so a change CI is much tighter than the
      difference of two independent single-year CIs.
  (2) STRIP-SLOPE TREND across all of the arm's years. One OLS slope per strip
      (p on calendar year); the 5 slopes ARE the design replicates.

ARM DISCIPLINE (hard rail). A "difference" only means something if both years came
from the same model/inference arm. `is_champion` selects a DIFFERENT arm per year by
construction, so a champion series is NOT pairable — the script refuses it. One arm,
one difference, always. Default arm = `citywide_rgb`, the 13-year RGB-only backbone
(2000 2002 2005 2007 2009 2013 2015 2017 2019 2021 2022 2023 2024).

VARIANCE. Both products use the successive-difference estimator for a systematic
sample of L=5 ordered bands — the same estimator `phase4_sector_series.py` applies to
the per-year fractions, here applied to the per-pair differences D_h and to the
per-strip slopes b_h:

    V = ( sum_h W_h^2 ) * [ 1/(2(L-1)) * sum_{h=1..L-1} (x_{h+1} - x_h)^2 ]
    CI95 = t(0.975, L-1) * sqrt(V),   t(0.975, 4) = 2.776

with x = D (paired) or x = b (trend), strips in band order S1..S5. Two alternative
weighted-variance forms were computed and rejected: the reliability-weight form
s2_w * sum W^2 with s2_w = sum W_h (x_h - x_w)^2 / (1 - sum W_h^2), and the
with-replacement PSU form L/(L-1) * sum (W_h (x_h - x_w))^2. Both give WIDER CIs
(trend p_raw: 0.061 and 0.050 pp/yr vs 0.037), neither matches the adversarial
review's published numbers, and neither is what the sibling script uses. The
successive-difference form is kept for consistency with the sibling script and
because the strips are a systematic (not simple-random) sample of bands.

WEIGHTS. W_h = strip true land area / SAMPLED true land area (563 ha, NOT the city).
Default `--weights series` recovers A_land_true per strip from the series' own
columns as median(canopy_ha_true / p_adj) over that strip's rows — exact up to the
CSV's own rounding (canopy_ha_true to 0.01 ha, p_adj to 5 dp), and identical to the
geometry route (sectors gpkg n city - water, area x cos^2(47.81 deg)) to ~3e-5
relative. Chosen as the default because it makes this script pure post-processing:
the same numbers the published CSV was built from, with no geopandas/gpkg/shapefile
dependency that could drift out from under it. `--weights geometry` recomputes from
the polygons for cross-check.

p_raw IS THE HEADLINE; p_adj IS SENSITIVITY ONLY. p_adj = p_raw * precision / recall
applies a CITYWIDE per-year constant to every strip. That multiplier carries ZERO
uncertainty into the strip replicates, so a p_adj CI understates the real error while
the point estimate absorbs all the year-to-year swing in the calibration pair. Report
p_raw; quote p_adj only to show what the calibration would do.

OUTPUTS (data:phase4/qc/sector_campaign/)
  sector_change_paired.csv  arm, metric, year_a, year_b, delta, se, ci_lo, ci_hi, n_sectors
  sector_trend.csv          arm, metric, slope_per_yr, se, ci_lo, ci_hi, df, years_used

Both files carry `#` comment lines above the header row (conditionality + p_adj
caveat). Read them with pandas `comment='#'` or csv after skipping leading `#` lines.
Values in the CSVs are FRACTIONS (0-1) per year; the printed summary is in
percentage points (pp) for readability.

USAGE
  PYTHONUTF8=1 py -3.12 qc/instruments/phase4_sector_change.py
  PYTHONUTF8=1 py -3.12 qc/instruments/phase4_sector_change.py --arm xsensor_rgb --weights geometry
"""
import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path

import numpy as np
from phase4seg.names import clean_argv  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2]  # instruments/ -> qc/ -> Scripts/

DATA = Path(r"G:\My Drive\treedata")
CAMP = DATA / "phase4" / "qc" / "sector_campaign"
SERIES = CAMP / "sector_canopy_series.csv"
COS2 = float(np.cos(np.radians(47.81))) ** 2
T975_DF4 = 2.776

CONDITIONALITY = ("Spatial-sampling CI conditional on model, threshold and calibration "
                  "— common-mode per-year error is invisible to strip replicates.")
PADJ_CAVEAT = ("p_adj rows are SENSITIVITY ONLY, never the headline: the calibration "
               "multiplier precision/recall is a citywide per-year constant applied "
               "identically to every strip, so it carries ZERO uncertainty into the "
               "strip replicates - the p_adj CI is not a real error bar for it. "
               "p_raw is the headline metric.")


def succ_diff_var(x, w):
    """Design variance for a systematic sample of L ordered bands.

    V = (sum_h w_h^2) * [ 1/(2(L-1)) * sum_{h=1..L-1} (x_{h+1} - x_h)^2 ]

    x and w are parallel sequences in BAND ORDER (S1..S5); w sums to 1. The bracket
    is the successive-difference estimate of the per-strip sampling variance sigma^2
    (unbiased under a linear trend across bands, unlike the plain sample variance);
    multiplying by sum w_h^2 converts it to the variance of the weighted total
    sum w_h x_h. Same estimator as phase4_sector_series.py uses on per-year p.
    """
    L = len(x)
    s2 = sum((x[i + 1] - x[i]) ** 2 for i in range(L - 1)) / (2.0 * (L - 1))
    return float(sum(wi ** 2 for wi in w) * s2)


def weights_from_series(rows):
    """A_land_true (m2) per strip, recovered from the series' own columns.

    canopy_ha_true = round(p_adj * A_land_true / 1e4, 2) in the producer, so
    A_land_ha = canopy_ha_true / p_adj up to the CSV's rounding. The median over all
    of a strip's rows (every year, every arm) kills the rounding jitter; observed
    within-strip spread is <=4.4e-4 relative, and the median agrees with the geometry
    route to ~3e-5 relative.
    """
    per = {}
    for r in rows:
        p = float(r["p_adj"])
        if p <= 0:
            continue
        per.setdefault(r["sector"], []).append(float(r["canopy_ha_true"]) / p * 1e4)
    return {k: statistics.median(v) for k, v in sorted(per.items())}


def weights_from_geometry(aoi_rel="pipeline/aoi/sectors_v1.json"):
    """A_land_true (m2) per strip recomputed from polygons, exactly as the producer
    does: sector geometry n city boundary - waterbody union, 3857 area x cos^2(lat)."""
    import imagery_measure as im
    import geopandas as gpd
    from shapely.ops import unary_union

    aoi = json.loads((SCRIPTS / aoi_rel).read_text(encoding="utf-8"))
    ver = aoi["version"]
    sectors = gpd.read_file(DATA / "phase4" / "qc" / "sectors" / f"{ver}.gpkg",
                            layer="sectors")
    city = gpd.read_file(im.CITY_SHP).to_crs("EPSG:3857")
    city_poly = city.union_all() if hasattr(city, "union_all") else city.unary_union
    water = gpd.read_file(DATA / "bathology" / "GDBA_HYDROGRAPHY__waterbody_snoco.shp")
    water = water[water.geometry.notna() & water.is_valid]
    minx, miny, maxx, maxy = city_poly.buffer(2000).bounds
    water_u = unary_union(list(water.cx[minx:maxx, miny:maxy].geometry))
    out = {}
    for _, s in sectors.iterrows():
        out[s["id"]] = s.geometry.intersection(city_poly).difference(water_u).area * COS2
    return dict(sorted(out.items()))


def cal_year(tok):
    """Calendar year from a year-label token ('2019' -> 2019, '2021s' -> 2021)."""
    m = re.match(r"(\d{4})", str(tok))
    if not m:
        raise ValueError(f"unparseable year label {tok!r}")
    return int(m.group(1))


def write_csv(path, cols, rows, notes):
    with open(path, "w", newline="", encoding="utf-8") as f:
        for n in notes:
            f.write(f"# {n}\n")
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"-> {path} ({len(rows)} rows)")


def main():
    ap = argparse.ArgumentParser(description="paired sector change + strip-slope trend")
    ap.add_argument("--arm", default="citywide_rgb",
                    help="the ONE tag to restrict to (default citywide_rgb, the 13-year "
                         "RGB backbone). 'is_champion'/'champion' is refused: it mixes "
                         "arms and is not pairable.")
    ap.add_argument("--weights", choices=("series", "geometry"), default="series",
                    help="strip land-area weights: recovered from the series CSV "
                         "(default, pure post-processing) or recomputed from polygons")
    ap.add_argument("--series", default=str(SERIES))
    a = ap.parse_args(clean_argv())

    if a.arm.strip().lower() in ("is_champion", "champion", "champions", "1"):
        print("REFUSED: is_champion selects a different inference arm per year by "
              "construction. A difference between two arms is a model artefact, not "
              "canopy change - the champion series is NOT pairable. Pass one --arm.")
        return 2

    all_rows = list(csv.DictReader(open(a.series, encoding="utf-8")))
    print(f"series: {a.series} ({len(all_rows)} rows)")
    rows = [r for r in all_rows if r["tag"] == a.arm]
    if not rows:
        tags = sorted({r["tag"] for r in all_rows})
        print(f"REFUSED: no rows with tag=={a.arm!r}. Available arms: {tags}")
        return 2
    assert len({r["tag"] for r in rows}) == 1, "arm filter leaked a second tag"

    # ---- weights -----------------------------------------------------------
    A = (weights_from_series(all_rows) if a.weights == "series"
         else weights_from_geometry())
    A_tot = sum(A.values())
    W = {k: v / A_tot for k, v in A.items()}
    print(f"weights ({a.weights}): sampled land {A_tot/1e4:,.1f} ha true; " +
          "  ".join(f"{k} {A[k]/1e4:,.2f} ha W={W[k]:.6f}" for k in sorted(W)))

    # ---- strips x years, complete years only -------------------------------
    strips = sorted(W)                       # band order S1..S5 - the systematic sample
    L = len(strips)
    by_year = {}
    for r in rows:
        by_year.setdefault(r["year"], {})[r["sector"]] = r
    years = sorted(by_year, key=cal_year)
    dropped = [y for y in years if set(by_year[y]) != set(strips)]
    for y in dropped:
        print(f"  ! {a.arm}/{y}: only {len(by_year[y])}/{L} strips - year DROPPED "
              f"(a paired difference needs every strip in both years)")
    years = [y for y in years if y not in dropped]
    if len(years) < 2:
        print(f"REFUSED: arm {a.arm!r} has {len(years)} complete year(s) - nothing to pair.")
        return 2
    cy = [cal_year(y) for y in years]
    print(f"arm {a.arm}: {len(years)} complete years {years} x {L} strips {strips}")

    wv = [W[s] for s in strips]
    notes_common = [CONDITIONALITY, PADJ_CAVEAT,
                    f"arm={a.arm}  strips={strips}  weights={a.weights}  "
                    f"sampled_land_ha={A_tot/1e4:.1f}  t(0.975,4)={T975_DF4}",
                    "values are FRACTIONS of land area (0-1), not percent."]

    # ---- (1) paired change -------------------------------------------------
    paired = []
    for metric in ("p_raw", "p_adj"):
        P = {(y, s): float(by_year[y][s][metric]) for y in years for s in strips}
        for i in range(len(years) - 1):
            ya, yb = years[i], years[i + 1]
            D = [P[(yb, s)] - P[(ya, s)] for s in strips]      # per-strip difference
            delta = sum(w * d for w, d in zip(wv, D))
            se = float(np.sqrt(succ_diff_var(D, wv)))
            paired.append({"arm": a.arm, "metric": metric, "year_a": ya, "year_b": yb,
                           "delta": round(delta, 6), "se": round(se, 6),
                           "ci_lo": round(delta - T975_DF4 * se, 6),
                           "ci_hi": round(delta + T975_DF4 * se, 6),
                           "n_sectors": L})

    write_csv(CAMP / "sector_change_paired.csv",
              ["arm", "metric", "year_a", "year_b", "delta", "se", "ci_lo", "ci_hi",
               "n_sectors"], paired,
              notes_common + [
                  "PAIRED consecutive-year change within one arm. D_h = p_h(year_b) - "
                  "p_h(year_a); delta = sum W_h D_h; V = (sum W_h^2) * "
                  "[1/(2(L-1)) sum (D_{h+1}-D_h)^2] over strips in band order.",
                  "A pair is significant when ci_lo and ci_hi share a sign."])

    # ---- (2) strip-slope trend --------------------------------------------
    trend = []
    slopes_by_metric = {}
    for metric in ("p_raw", "p_adj"):
        b = [float(np.polyfit(np.asarray(cy, float),
                              np.asarray([float(by_year[y][s][metric]) for y in years]),
                              1)[0]) for s in strips]
        slopes_by_metric[metric] = b
        bw = sum(w * bi for w, bi in zip(wv, b))            # area-weighted mean slope
        se = float(np.sqrt(succ_diff_var(b, wv)))
        trend.append({"arm": a.arm, "metric": metric, "slope_per_yr": round(bw, 8),
                      "se": round(se, 8), "ci_lo": round(bw - T975_DF4 * se, 8),
                      "ci_hi": round(bw + T975_DF4 * se, 8), "df": L - 1,
                      "years_used": len(years)})
        # robustness line: unweighted mean of the 5 replicates, classic t interval
        bu = float(np.mean(b))
        seu = float(np.std(b, ddof=1) / np.sqrt(L))
        trend.append({"arm": a.arm, "metric": metric + "_unweighted",
                      "slope_per_yr": round(bu, 8), "se": round(seu, 8),
                      "ci_lo": round(bu - T975_DF4 * seu, 8),
                      "ci_hi": round(bu + T975_DF4 * seu, 8), "df": L - 1,
                      "years_used": len(years)})

    write_csv(CAMP / "sector_trend.csv",
              ["arm", "metric", "slope_per_yr", "se", "ci_lo", "ci_hi", "df",
               "years_used"], trend,
              notes_common + [
                  "STRIP-SLOPE trend: one OLS slope b_h of p on calendar year per strip; "
                  "the L=5 slopes are the design replicates. slope_per_yr = sum W_h b_h; "
                  "V = (sum W_h^2) * [1/(2(L-1)) sum (b_{h+1}-b_h)^2] over strips in band "
                  "order. Rows tagged '_unweighted' are the robustness line: plain mean of "
                  "the 5 slopes +/- t(0.975,4)*sd/sqrt(5), no area weighting.",
                  "slope_per_yr is a FRACTION per year; multiply by 100 for pp/yr."])

    # ---- readable summary --------------------------------------------------
    pp = 100.0
    print(f"\n=== PAIRED CONSECUTIVE-YEAR CHANGE - arm {a.arm} (pp of land area) ===")
    for metric in ("p_raw", "p_adj"):
        head = "HEADLINE" if metric == "p_raw" else "sensitivity only, NOT the headline"
        print(f"  -- {metric} ({head})")
        for r in [x for x in paired if x["metric"] == metric]:
            sig = "*" if r["ci_lo"] * r["ci_hi"] > 0 else " "
            print(f"     {r['year_a']}->{r['year_b']}  {r['delta']*pp:+7.3f} "
                  f"+/- {T975_DF4*r['se']*pp:6.3f} pp  "
                  f"[{r['ci_lo']*pp:+7.3f}, {r['ci_hi']*pp:+7.3f}] {sig}")
    print("     (* = CI excludes zero, spatial-sampling only)")

    span = cy[-1] - cy[0]
    print(f"\n=== STRIP-SLOPE TREND - arm {a.arm}, {len(years)} years "
          f"{cy[0]}-{cy[-1]} ({span} yr span), df={L-1} ===")
    for metric in ("p_raw", "p_adj"):
        head = "HEADLINE" if metric == "p_raw" else "sensitivity only, NOT the headline"
        wrow = next(r for r in trend if r["metric"] == metric)
        urow = next(r for r in trend if r["metric"] == metric + "_unweighted")
        b = slopes_by_metric[metric]
        print(f"  -- {metric} ({head})")
        print(f"     per-strip slopes  " +
              "  ".join(f"{s} {bi*pp:+.4f}" for s, bi in zip(strips, b)) + " pp/yr")
        for lbl, r in (("area-weighted", wrow), ("unweighted   ", urow)):
            sig = "SIGNIFICANT" if r["ci_lo"] * r["ci_hi"] > 0 else "not significant"
            print(f"     {lbl}  {r['slope_per_yr']*pp:+.4f} +/- "
                  f"{T975_DF4*r['se']*pp:.4f} pp/yr  "
                  f"[{r['ci_lo']*pp:+.4f}, {r['ci_hi']*pp:+.4f}]  {sig}")
        print(f"     -> {span}-yr change {wrow['slope_per_yr']*span*pp:+.3f} +/- "
              f"{T975_DF4*wrow['se']*span*pp:.3f} pp (area-weighted, linear extrapolation)")

    print(f"\n{CONDITIONALITY}")
    print(PADJ_CAVEAT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

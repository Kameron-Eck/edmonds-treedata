r"""
╔══════════════════════════════════════════════════════════════════╗
  R2 — RADIOMETRY NORMALIZATION (per-acquisition gain/offset onto one reference)
  Edmonds Temporal Active Learning Pipeline

  WHAT THIS IS, AND WHAT IT IS NOT
  ------------------------------------------------------------------
  R1 (qc/radiometry_fingerprint.py) MEASURED the problem: over pseudo-invariant
  hardscape — ground whose true reflectance does not change — the 36 catalogued
  acquisitions disagree by amounts that cannot be vegetation. IMAGERY_FACTS §3
  proves the extreme case (2019 King reads .1146 vegetated, 2019 NAIP .8919, same
  year, same ground) and states the rule: COLOUR NUMBERS NEVER COMPARE ACROSS
  SOURCES UNCORRECTED.

  This module is the correction — a PER-ACQUISITION, PER-BAND LINEAR MAP

      DN_reference  ~=  gain * DN_acquisition + offset

  fitted so that each acquisition's invariant-spine statistics land on the
  reference acquisition's. It is deliberately the weakest correction that can
  work: one gain and one offset per band per acquisition, fitted on ground that
  is known not to change.

  IT IS NEVER APPLIED AUTOMATICALLY. Nothing in the pipeline calls it. It writes
  a TABLE; a caller that wants cross-year comparability opts in. See the POLICY
  block on normalize_array() for the full rule.

  THE FIT
  ------------------------------------------------------------------
  Targets: the R1 COLOUR SPINE ONLY — neg_parking (asphalt retail lot) and
  school_k12 (Edmonds Heights K-12), both PIF-masked to hardscape from the fixed
  2020 anchor. neg_water is target_class=invariant in the fingerprint but is
  EXCLUDED here for the same reason R1 excludes it from every colour ratio:
  sun-glint is a per-flight accident, not a calibration property, and it would
  drag the dark end of the fit by an amount that varies with flight geometry.
  Water is used here only for the NIR-floor health test (§12), never in a fit.

  Points: p5 / p50 / p95 of each spine target = up to 6 (x, y) pairs per band,
  x = the acquisition's quantile, y = the reference's SAME quantile of the SAME
  target. Two targets are used rather than one pooled distribution because they
  sit at different brightness levels (2020s red p50: parking 139, school 181),
  so together they pin a slope that a single target's 3 quantiles would not.

  CLIPPED POINTS ARE DROPPED. A quantile at or above CLIP_HI (254) or at or
  below CLIP_LO (1) is a censored value, not a measurement — 2000's school-red
  and school-blue p95 both sit at 255, and left in they would bend the 2000 fit
  toward the very cast it is meant to remove. n_points records what survived.

  Estimator: ORDINARY LEAST SQUARES by default, with --method theil-sen (median
  of pairwise slopes, then median intercept) available. Theil-Sen was the first
  choice on robustness grounds and it LOST on measurement — run
  `--step compare-methods` to reproduce the table. On the same-flight
  cross-sensor pairs (the honest held-out test, below), fitted to 2020s:

      quantile set        method   mean |d(p50)|   mean spine RMS
      p5/p50/p95          ols          3.3 DN          4.7 DN   <- default
      p5/p50/p95          theil-sen    4.4 DN          6.9 DN
      p1..p99 (5 q)       ols          4.6 DN          5.3 DN
      p50 only            either       0.0 DN        117-250 DN  <- see below
      RAW (no correction)             12.5 DN         15.1 DN

  With only six points, Theil-Sen's MIN_DX guard discards most of the pairwise
  slopes and the median is taken over what is left; least squares uses all six.
  The p50-only row is the cautionary one and the reason TWO measures are
  reported everywhere below: two points through the two targets' medians map
  those medians onto each other EXACTLY (d(p50) = 0.00 by construction) while
  the line it defines is nonsense away from them (spine RMS 117-250 DN). A
  headline that only quotes d(p50) can be satisfied by a fit that is wrong.

  fit_quality = RMS residual in DN of the fitted points against the reference.
  Read it against pre_rms (the same RMS with no correction at all): the pair is
  the honest before/after, and a fit whose residual is not much below pre_rms
  has not bought anything.

  WHY fit_quality IS LARGE (~15-30 DN) EVEN WHERE THE PAIRS CONVERGE WELL
  ------------------------------------------------------------------
  Measured, and it is a property of the DATA, not a bug in the fit: THE TWO
  SPINE TARGETS ARE NOT MUTUALLY CONSISTENT IN THE TAILS. 2019n red, for
  instance, has parking p5 = 47 and school p5 = 49 — two all-but-identical
  acquisition values — while the reference's are 89 and 135. No monotone
  function, linear or otherwise, can send 47->89 and 49->135. So a residual of
  that size is FORCED before any estimator is chosen.

  The cause is that a quantile is a rank statistic over a spatial patch, and the
  rank is not preserved across acquisitions of different GSD: at 60 cm (NAIP) a
  nominally-hardscape PIF pixel mixes in the shaded edge of the adjacent canopy,
  which drags the 5th percentile down far harder than it does at 7.6 cm (the
  2020s EagleView). The p50 is comparatively immune — half the patch has to
  change for it to move — which is why the p50 numbers converge well while the
  tails do not. TREAT fit_quality AS A FLOOR SET BY TARGET DISAGREEMENT, and the
  same-flight pair convergence in [1] of --step validate as the real test.

  THE OFFSETS ONTO 2020s ARE PART RADIOMETRY, PART POINT-SPREAD — MEASURED
  ------------------------------------------------------------------
  Same mechanism, and it matters enough to state separately because it lands in
  the OFFSET column a reader will be tempted to read as path radiance. Red p5
  on the hardscape spine (parking / school):

      2020s  7.6 cm   89 / 135     <- the default reference
      2018s 15.2 cm   46 /  43
      2019s 30.5 cm   32 /  36
      2019n   60 cm   47 /  49
      2021n   60 cm   30 /  17
      2023n   60 cm   79 /  56

  The reference is an OUTLIER at the dark end, and not because it is brighter:
  at 7.6 cm a PIF-masked hardscape pixel is pure hardscape, while at 60 cm the
  same nominal pixel mixes in the shaded edge of the neighbouring canopy. So a
  large part of the ~+70 DN red offset fitted for the coarse years is the
  reference's SHARPNESS, not its calibration. The gain is far less affected —
  it is set by the bright end, where mixing has little to do.

  This does not invalidate the table: every acquisition is mapped onto the SAME
  target, which is what cross-year comparability requires, and [1] confirms that
  independent sensors of the same scene land together. It DOES mean an offset is
  not a physical black-point estimate, and it is why the fitted DOMAIN is
  published per row — see below.

  THE FIT HAS A DOMAIN, AND IT IS PUBLISHED (fit_x_min / fit_x_max)
  ------------------------------------------------------------------
  A line fitted on hardscape between, say, 47 and 217 DN says nothing about a
  pixel at 3 DN. Every row therefore carries the DN range its points spanned.
  Outside it the map is EXTRAPOLATION, and --step validate's [4] measures what
  that costs on the darkest real target in the record (open water).

  Measured consequence, so nobody has to discover it: over water, red is lifted
  by the ~+70 DN offset while NIR barely moves, so normalized NDVI over dark
  targets is driven hard negative and six of the eight healthy 4-band years
  CLAMP at exactly -1.000. That is a degenerate agreement, not a convergence
  win — the same failure mode as the p50-only row above — and it means the
  normalized NDVI product CANNOT carry the §12 negative-tail diagnostic. Run the
  lifted-floor test on the NATIVE stack, always.

  THE REFERENCE
  ------------------------------------------------------------------
  --reference 2020s  (default) — the anchor-era Snohomish EagleView 3-in RGB.
  It is chosen because it is contemporaneous with the 2020 hand-annotated
  dataset the whole pipeline is anchored to, so "normalized" means "looks like
  the era the labels came from".

  --nir-reference 2019s  (default) — 2020s IS RGB-ONLY, so it cannot serve as a
  NIR reference. The NIR reference must be a 4-band acquisition with a healthy
  dark-target floor (§12); 2019s is the nearest such acquisition to the anchor
  era (2019-10-11, floor p1 = 3 DN, county 1-ft HXIP). CONSEQUENCE, stated
  plainly: a normalized NDVI built from this table is on a HYBRID scale — red
  mapped onto 2020s, NIR mapped onto 2019s — and equals no single acquisition's
  native NDVI. That is acceptable because every year maps onto the SAME hybrid
  target, which is what cross-year comparability requires; it is not acceptable
  to leave unsaid, so the reference is carried per row in the table.

  THE LIFTED FLOORS ARE NOT CORRECTED (IMAGERY_FACTS §12)
  ------------------------------------------------------------------
  2015n (NIR p1 = 33 DN) and 2021s (25-28 DN) carry LIFTED BLACK POINTS, traced
  in both cases to the delivery itself, not our export path. A hardscape-spine
  gain/offset would happily produce numbers for them — and those numbers would
  be a LIE, because a lifted floor is not a linear stretch: it is haze/path
  radiance added on top of a signal that has already been quantised and, on the
  bright hardscape the spine samples, largely saturated out of view. Fitting on
  hardscape and extrapolating down to open water is exactly the extrapolation
  the data cannot support.

  So their NIR rows are EMITTED WITH NO gain/offset and an excluded_reason, and
  normalize_array() RAISES on them rather than silently passing the array
  through. A silent identity would read, downstream, as "corrected".

  WHAT A LINEAR INVARIANT-SPINE FIT CANNOT FIX — read before trusting output
  ------------------------------------------------------------------
  * PHENOLOGY. The fit is blind to vegetation by construction. An April frame
    and an August frame of the same year, both perfectly normalized, still
    disagree over grass and deciduous canopy because the plants really differ.
    Normalization makes the CAMERAS comparable, never the SEASONS.
  * PER-SCENE / WITHIN-SCENE STRUCTURE. One gain + one offset for a whole
    acquisition cannot touch vignetting, BRDF/hotspot gradients, per-tile mosaic
    seams, or a flight line that was balanced differently from its neighbour.
    The spine is two small footprints; whatever they measure is asserted for the
    whole city.
  * LIFTED FLOORS (above) — refused, not fixed.
  * SATURATION. Where a source clipped at 255 the information is gone; a gain
    below 1 spreads the clip, it does not recover it.
  * NON-LINEARITY. Gamma, tone curves and 8-bit JPEG-ish compression in a
    delivery chain are not affine. A 2-parameter map is a first-order correction
    to whatever the real transfer function was.
  * REGISTRATION. The PIF mask is fixed 2020 geometry reprojected into each
    acquisition's grid; on the 1 m years a metre of misregistration changes
    which pixels are sampled.

  PRODUCES  (data plane — phase4/qc/)
    radiometry_norm.csv   one row per acquisition x band: gain, offset,
                          reference, fit_quality, n_targets, n_points,
                          excluded_reason, evidence note

  USAGE
    py -3.12 qc/radiometry_norm.py                      # fit + validate
    py -3.12 qc/radiometry_norm.py --step fit
    py -3.12 qc/radiometry_norm.py --step validate
    py -3.12 qc/radiometry_norm.py --step compare-methods   # reproduce the table above
    py -3.12 qc/radiometry_norm.py --reference 2020 --nir-reference 2018s
    py -3.12 qc/radiometry_norm.py --method theil-sen
      --fingerprint PATH   override the R1 CSV
      --out PATH           override phase4/qc/radiometry_norm.csv

  IMPORTED AS A MODULE (the opt-in path)
    from radiometry_norm import load_table, normalize_array, normalize_stack_band
╚══════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent            # …/Scripts/qc
SCRIPTS = _HERE.parent                             # …/Scripts

# ── data plane ────────────────────────────────────────────────────────────────
_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if (_COLAB_BASE / "Full_Image").exists() else _LOCAL_BASE
QC_DIR = BASE / "phase4" / "qc"

FP_CSV = QC_DIR / "radiometry_fingerprint.csv"
OUT_CSV = QC_DIR / "radiometry_norm.csv"

# ── the fit ───────────────────────────────────────────────────────────────────
# The R1 colour spine. NOT every target_class=invariant row: neg_water is
# invariant ground but sun-glint sensitive, and R1 excludes it from every colour
# ratio for that reason. Same exclusion here — see the header.
SPINE = ("neg_parking", "school_k12")
QUANTILES = ("p5", "p50", "p95")

DEFAULT_REF = "2020s"        # anchor-era EagleView 3-in RGB
DEFAULT_NIR_REF = "2019s"    # 2020s has no NIR; nearest healthy-floor 4-band year
# MEASURED, not assumed: ols beat theil-sen on the same-flight pairs (header table,
# reproducible with --step compare-methods). QUANTILES is the fitted set.
DEFAULT_METHOD = "ols"

CLIP_LO = 1.0                # a quantile at/below this is censored, not measured
CLIP_HI = 254.0              # ditto at the top (2000 school R/B p95 = 255)
MIN_DX = 3.0                 # Theil-Sen: ignore pairs closer than this in x (DN)
MIN_POINTS = 4               # refuse a fit built on fewer surviving points

# §12 dark-target NIR floor test, threshold shared with pipeline/make_nir_stack.py
LIFTED_NIR_P1 = 20           # DN: a healthy NIR band floors near 0 over open water
FLOOR_TARGET = "neg_water"

RGB = ("R", "G", "B")
ALL_BANDS = ("R", "G", "B", "N")

# Same-flight cross-sensor pairs — the strongest available convergence test,
# because the two members saw the SAME GROUND on the SAME DAY through different
# sensors and processing chains. Any residual difference is radiometry alone.
SAME_FLIGHT_PAIRS = [
    ("2015n", "2015s", "NAIP 1 m vs Snoh HXIP 1 ft, both 2015-08-07"),
    ("2017n", "2017s", "NAIP 1 m vs Snoh HXIP 1 ft, both 2017-08-15/21"),
    ("2019n", "2019s", "NAIP 60 cm vs Snoh HXIP 1 ft, both 2019-10-11 (same Hexagon flight)"),
]
# NOT same-flight: 2019 King is Apr 25-May 8, 2019n is Oct 11. Included because
# IMAGERY_FACTS §3 names this pair as the decisive cross-source disagreement —
# but the six-month date gap means residual difference is NOT all radiometry.
CROSS_SOURCE_PAIRS = [
    ("2019n", "2019", "NAIP 2019-10-11 vs King County 2019-04-25/05-08 — "
                      "the IMAGERY_FACTS §3 decisive pair; DATE-MISMATCHED"),
]


# ══════════════════════════════════════════════════════════════════════════════
#  reading the R1 fingerprint
# ══════════════════════════════════════════════════════════════════════════════

def read_fingerprint(path: Path = FP_CSV) -> dict:
    """R1 CSV -> {acquisition: {"meta": {...}, "stats": {(target, band): row}}}.

    Values are floats; a blank or unparseable cell becomes None so a missing
    quantile is visibly absent rather than silently zero.
    """
    if not Path(path).exists():
        raise FileNotFoundError(
            f"R1 fingerprint not found: {path}\n"
            f"  run:  py -3.12 qc/radiometry_fingerprint.py")
    acq: dict = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            key = str(row["key"]).strip()
            rec = acq.setdefault(key, {"meta": {}, "stats": {}})
            if not rec["meta"]:
                rec["meta"] = {
                    "label": row.get("label", key), "source": row.get("source", ""),
                    "source_group": row.get("source_group", ""),
                    "native_file": row.get("native_file", ""),
                    "gsd_cm": row.get("gsd_cm", ""), "bands": row.get("bands", ""),
                    "date_shot": row.get("date_shot", ""),
                }
            st = {"target_class": row.get("target_class", ""),
                  "coverage": _f(row.get("coverage")),
                  "valid_px": _f(row.get("valid_px"))}
            for q in ("p1", "p5", "p50", "p95", "p99", "mean", "std"):
                st[q] = _f(row.get(q))
            rec["stats"][(row["target"], row["band"])] = st
    return acq


def _f(v):
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def spine_points(rec: dict, band: str):
    """(x-values, target names) — the surviving spine quantiles for one band.

    Returns a list of (target, quantile_name, value). Censored quantiles are
    dropped here so every caller sees the same surviving set.
    """
    out = []
    for t in SPINE:
        st = rec["stats"].get((t, band))
        if st is None:
            continue
        for q in QUANTILES:
            v = st.get(q)
            if v is None or v <= CLIP_LO or v >= CLIP_HI:
                continue
            out.append((t, q, v))
    return out


def nir_floor(rec: dict):
    """Dark-target NIR p1 over open water — the §12 lifted-black-point test."""
    st = rec["stats"].get((FLOOR_TARGET, "N"))
    return None if st is None else st.get("p1")


def spine_p50(rec: dict, band: str):
    """Median of the spine targets' p50 for one band — R1's `spine_*_p50`."""
    vals = [rec["stats"][(t, band)]["p50"] for t in SPINE
            if (t, band) in rec["stats"] and rec["stats"][(t, band)]["p50"] is not None]
    return float(np.median(vals)) if vals else None


# ══════════════════════════════════════════════════════════════════════════════
#  the estimators
# ══════════════════════════════════════════════════════════════════════════════

def theil_sen(x, y, min_dx: float = MIN_DX):
    """Median of pairwise slopes, then the median intercept.

    Pairs closer than min_dx in x are skipped: with uint8 quantiles two nearly
    equal x values make (y2-y1)/(x2-x1) explode, and one such pair can otherwise
    reach the median when there are only six points.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    slopes = [(y[j] - y[i]) / (x[j] - x[i])
              for i, j in combinations(range(len(x)), 2)
              if abs(x[j] - x[i]) >= min_dx]
    if not slopes:
        return None, None
    g = float(np.median(slopes))
    b = float(np.median(y - g * x))
    return g, b


def ols(x, y):
    """Least-squares line — the comparison estimator (--method ols)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 2 or np.ptp(x) == 0:
        return None, None
    g, b = np.polyfit(x, y, 1)
    return float(g), float(b)


def _rms(v):
    v = np.asarray(v, float)
    return float(np.sqrt(np.mean(v ** 2))) if v.size else float("nan")


# ══════════════════════════════════════════════════════════════════════════════
#  fitting the table
# ══════════════════════════════════════════════════════════════════════════════

def fit_band(acq_rec, ref_rec, band, method=DEFAULT_METHOD):
    """One (gain, offset) mapping acq -> ref for one band, plus its diagnostics.

    The reference value for each point is the reference acquisition's SAME
    quantile of the SAME target, so the pairing is ground-for-ground, not a
    pooled-histogram match.
    """
    a_pts = {(t, q): v for t, q, v in spine_points(acq_rec, band)}
    r_pts = {(t, q): v for t, q, v in spine_points(ref_rec, band)}
    keys = sorted(set(a_pts) & set(r_pts))
    if len(keys) < MIN_POINTS:
        return None
    x = np.array([a_pts[k] for k in keys], float)
    y = np.array([r_pts[k] for k in keys], float)

    g, b = (theil_sen(x, y) if method == "theil-sen" else ols(x, y))
    if g is None or not np.isfinite(g) or g <= 0:
        return None

    resid = y - (g * x + b)
    return {
        "gain": g, "offset": b,
        "fit_quality": _rms(resid), "resid_max": float(np.max(np.abs(resid))),
        "pre_rms": _rms(y - x),
        "n_points": len(keys),
        "n_targets": len({t for t, _ in keys}),
        "dropped": (len(SPINE) * len(QUANTILES)) - len(keys),
        # THE DOMAIN. A line fitted between these two DNs says nothing about a
        # pixel outside them; publishing the range is what makes extrapolation
        # detectable instead of invisible.
        "x_min": float(np.min(x)), "x_max": float(np.max(x)),
        "x": x, "y": y, "keys": keys,
    }


def build_table(fp, reference=DEFAULT_REF, nir_reference=DEFAULT_NIR_REF,
                method=DEFAULT_METHOD):
    """Every acquisition x band row of the normalization table.

    Emits a row for every band the acquisition has — including the two §12
    lifted-floor NIR bands, which carry an excluded_reason and NO coefficients.
    A silently missing row and a refused row are different facts and the table
    must be able to say which.
    """
    for k in (reference, nir_reference):
        if k not in fp:
            raise KeyError(f"reference {k!r} is not in the fingerprint "
                           f"({', '.join(sorted(fp))})")
    ref_rgb, ref_nir = fp[reference], fp[nir_reference]
    ref_floor = nir_floor(ref_nir)
    if ref_floor is not None and ref_floor > LIFTED_NIR_P1:
        raise ValueError(
            f"NIR reference {nir_reference} has a LIFTED floor (p1={ref_floor:.0f} DN "
            f"> {LIFTED_NIR_P1}); it cannot serve as a NIR reference (§12)")

    rows = []
    for key in sorted(fp, key=lambda s: (s[:4], s)):
        rec = fp[key]
        meta = rec["meta"]
        has_nir = any(b == "N" for (_, b) in rec["stats"])
        floor = nir_floor(rec)

        for band in ALL_BANDS:
            if band == "N" and not has_nir:
                continue
            ref_key = nir_reference if band == "N" else reference
            ref_rec = ref_nir if band == "N" else ref_rgb

            base = {
                "acquisition": key, "band": band,
                "reference": ref_key,
                "source": meta["source"], "source_group": meta["source_group"],
                "gsd_cm": meta["gsd_cm"], "native_file": meta["native_file"],
                "fit_method": method,
                "fit_targets": "+".join(SPINE),
                "nir_floor_water_p1": "" if floor is None else f"{floor:.0f}",
                "acq_spine_p50": _fmt(spine_p50(rec, band), 1),
                "ref_spine_p50": _fmt(spine_p50(ref_rec, band), 1),
            }

            # ── §12 refusal: never a coefficient for a lifted floor ──────────
            if band == "N" and floor is not None and floor > LIFTED_NIR_P1:
                rows.append({
                    **base, "gain": "", "offset": "", "fit_quality": "",
                    "resid_max": "", "pre_rms": "", "n_points": 0, "n_targets": 0,
                    "excluded_reason":
                        f"LIFTED NIR BLACK POINT (IMAGERY_FACTS §12): dark-target "
                        f"p1 = {floor:.0f} DN over open water vs <= {LIFTED_NIR_P1} DN "
                        f"on the healthy 4-band years. Traced to the delivery, not "
                        f"our export path. A hardscape-spine gain/offset is fitted on "
                        f"bright ground and cannot be extrapolated to a dark-end haze "
                        f"lift, so NO coefficient is emitted — emitting one would "
                        f"pretend the floor was fixed. Within-band structure and "
                        f"vegetation LOCATION stay honest; absolute NDVI does not.",
                    "note": "REFUSED - relative use only",
                })
                continue

            if key == ref_key:
                fit = fit_band(rec, ref_rec, band, method)
                rows.append({
                    **base, "gain": "1.000000", "offset": "0.000000",
                    "fit_quality": "0.000000", "resid_max": "0.000000",
                    "pre_rms": "0.000000",
                    "n_points": (fit or {}).get("n_points", 0),
                    "n_targets": (fit or {}).get("n_targets", 0),
                    "fit_x_min": _fmt((fit or {}).get("x_min"), 1),
                    "fit_x_max": _fmt((fit or {}).get("x_max"), 1),
                    "excluded_reason": "",
                    "note": f"IDENTITY - {key} is the {band} reference",
                })
                continue

            fit = fit_band(rec, ref_rec, band, method)
            if fit is None:
                rows.append({
                    **base, "gain": "", "offset": "", "fit_quality": "",
                    "resid_max": "", "pre_rms": "", "n_points": 0, "n_targets": 0,
                    "excluded_reason":
                        f"UNFITTABLE: fewer than {MIN_POINTS} uncensored spine "
                        f"quantiles shared with {ref_key} (clipped at <= {CLIP_LO:.0f} "
                        f"or >= {CLIP_HI:.0f} DN, or the target was skipped by R1 for "
                        f"coverage). No coefficient guessed.",
                    "note": "no fit",
                })
                continue

            rows.append({
                **base,
                "gain": f"{fit['gain']:.6f}", "offset": f"{fit['offset']:.6f}",
                "fit_quality": f"{fit['fit_quality']:.6f}",
                "resid_max": f"{fit['resid_max']:.6f}",
                "pre_rms": f"{fit['pre_rms']:.6f}",
                "n_points": fit["n_points"], "n_targets": fit["n_targets"],
                "fit_x_min": f"{fit['x_min']:.1f}", "fit_x_max": f"{fit['x_max']:.1f}",
                "excluded_reason": "",
                "note": _evidence_note(key, band, ref_key, fit, method),
            })
    return rows


def _evidence_note(key, band, ref_key, fit, method):
    """The per-row evidence sentence: what was fitted, on what, how well."""
    drop = (f"; {fit['dropped']} of {len(SPINE) * len(QUANTILES)} quantiles dropped "
            f"as censored (<= {CLIP_LO:.0f} or >= {CLIP_HI:.0f} DN)"
            if fit["dropped"] else "")
    return (f"{method} on {fit['n_points']} PIF-masked hardscape quantiles "
            f"(p5/p50/p95 x {fit['n_targets']} spine targets: {'+'.join(SPINE)}; "
            f"neg_water excluded - sun-glint) mapping {key} band {band} onto "
            f"{ref_key}. Spine RMS residual {fit['fit_quality']:.1f} DN vs "
            f"{fit['pre_rms']:.1f} DN uncorrected{drop}. VALID OVER DN "
            f"[{fit['x_min']:.0f}, {fit['x_max']:.0f}] - outside that range this "
            f"is EXTRAPOLATION (see --step validate [4]). Fitted on invariant "
            f"ground ONLY - says nothing about vegetation, season, vignetting or "
            f"within-scene gradient (see module header).")


def _fmt(v, nd=4):
    return "" if v is None else f"{v:.{nd}f}"


CSV_COLUMNS = [
    "acquisition", "band", "gain", "offset", "reference", "fit_quality",
    "n_targets", "n_points", "excluded_reason", "note",
    "resid_max", "pre_rms", "fit_x_min", "fit_x_max",
    "acq_spine_p50", "ref_spine_p50",
    "nir_floor_water_p1", "fit_method", "fit_targets",
    "source", "source_group", "gsd_cm", "native_file",
]


def write_table(rows, out_path: Path = OUT_CSV):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return out_path


# ══════════════════════════════════════════════════════════════════════════════
#  THE APPLY HELPERS — pure functions, OPT-IN ONLY
# ══════════════════════════════════════════════════════════════════════════════

_TABLE_CACHE: dict = {}


def load_table(table_path: Path = OUT_CSV, force: bool = False) -> dict:
    """radiometry_norm.csv -> {(acquisition, band): row-dict}. Cached per path.

    Rows with no gain (refused / unfittable) ARE returned — the caller must be
    able to see that a correction was REFUSED rather than merely absent.
    """
    p = str(Path(table_path))
    if not force and p in _TABLE_CACHE:
        return _TABLE_CACHE[p]
    if not Path(p).exists():
        raise FileNotFoundError(
            f"normalization table not found: {p}\n"
            f"  run:  py -3.12 qc/radiometry_norm.py --step fit")
    table = {}
    with open(p, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            row["gain"] = _f(row.get("gain"))
            row["offset"] = _f(row.get("offset"))
            table[(str(row["acquisition"]).strip(), str(row["band"]).strip())] = row
    _TABLE_CACHE[p] = table
    return table


def coefficients(acquisition, band, table_path: Path = OUT_CSV, table=None):
    """(gain, offset, row) for one acquisition/band, or raise with the reason.

    Raises KeyError if the pair is not in the table at all, and ValueError with
    the recorded excluded_reason where a correction was deliberately REFUSED
    (the §12 lifted floors). Refusing loudly is the point: a silent identity
    return would be indistinguishable downstream from a real correction.
    """
    table = table if table is not None else load_table(table_path)
    row = table.get((str(acquisition).strip(), str(band).strip()))
    if row is None:
        raise KeyError(f"no normalization row for {acquisition!r} band {band!r} "
                       f"in the table")
    if row["gain"] is None or row["offset"] is None:
        raise ValueError(f"normalization REFUSED for {acquisition} band {band}: "
                         f"{row.get('excluded_reason') or 'no coefficient'}")
    return row["gain"], row["offset"], row


def normalize_array(arr, acquisition, band, table_path: Path = OUT_CSV,
                    table=None, valid=None, out_dtype=None, clip=True):
    r"""Apply the linear radiometric map to one band array. PURE — no I/O on arr.

    ══ POLICY — READ BEFORE CALLING ═════════════════════════════════════════
    Normalization is OPT-IN, and it exists for ONE PURPOSE: cross-year
    comparison products — change detection, the normalized NDVI stack, any
    figure or statistic that places two acquisitions on one axis.

    It MUST NEVER silently rewrite pipeline inputs or headline products.
    Concretely, it is NOT to be wired into: phase4seg tiling or training input,
    inference, the citywide masks, the independent NDVI/C-CAP references, or
    any number reported as a headline metric. Those consume NATIVE DNs, and a
    normalized number reported beside a native one without saying so is a
    measurement error dressed as a correction.

    Every product built with this function must NAME it — in the filename, the
    band description, and the README. If a reader cannot tell from the artifact
    alone whether it was normalized, the artifact is wrong.

    The map is fitted on hardscape and is blind to phenology, vignetting,
    within-scene gradient, saturation and non-linearity (module header).
    ═════════════════════════════════════════════════════════════════════════

    arr        : 2-D (or any-shape) array of DNs for ONE band.
    acquisition: catalog key, e.g. "2019n".
    band       : "R" | "G" | "B" | "N".
    table_path : radiometry_norm.csv (data plane by default).
    table      : a preloaded table dict, to avoid re-reading per band.
    valid      : optional bool mask of imaged pixels. Where False, the ORIGINAL
                 value is preserved untouched. This matters: the project's
                 nodata convention is all-bands-exactly-0, and a positive offset
                 would turn those 0s into a plausible-looking DN — fabricating
                 imagery out of the fill value. Extract the mask from the RAW
                 pixels BEFORE calling this.
    out_dtype  : output dtype. Default: uint8 in -> uint8 out, else float32.
                 Pass "float32" when the result feeds a RATIO (NDVI): the uint8
                 round-and-clip is a lossy quantisation and doing it before the
                 division throws away the precision the correction just added.
    clip       : clip to the dtype's range (0-255 for uint8). Always applied for
                 integer output. For float output it clamps at 0 only — an
                 offset can push dark pixels negative, and a negative DN is not
                 a physical reflectance.

    RAISES ValueError where the table REFUSES a correction (§12 lifted floors),
    carrying the recorded reason. Callers that want the raw band for those
    acquisitions must ask for it explicitly and tag the result.
    """
    gain, offset, _row = coefficients(acquisition, band, table_path, table)
    a = np.asarray(arr)
    if out_dtype is None:
        out_dtype = np.uint8 if a.dtype == np.uint8 else np.float32
    out_dtype = np.dtype(out_dtype)

    work = a.astype(np.float32, copy=False) * np.float32(gain) + np.float32(offset)

    if np.issubdtype(out_dtype, np.integer):
        info = np.iinfo(out_dtype)
        lo, hi = (info.min, info.max) if clip else (info.min, info.max)
        work = np.clip(np.rint(work), lo, hi)
    elif clip:
        work = np.maximum(work, 0.0)

    out = work.astype(out_dtype)
    if valid is not None:
        out = np.where(valid, out, a.astype(out_dtype, copy=False))
    return out


def normalize_stack_band(stack, acquisition, bands=("R", "G", "B", "N"),
                         table_path: Path = OUT_CSV, table=None, valid=None,
                         out_dtype=None, clip=True, skip_missing=False):
    r"""normalize_array over a multi-band (K, H, W) stack for ONE acquisition.

    Same POLICY as normalize_array — OPT-IN, never auto-applied, never allowed
    to rewrite pipeline inputs or headline products. See that docstring.

    stack       : (K, H, W) array; stack[i] is band bands[i].
    bands       : band names in stack order. The repo-wide 4-band convention is
                  R,G,B,NIR (band 1 = RED, band 4 = NIR) — see
                  pipeline/make_nir_stack.py and qc/phase4_qc_ndvi.py.
    skip_missing: when True, a band the table REFUSES or does not carry is
                  returned UNCHANGED instead of raising, and its name is
                  collected. The caller then gets (out, refused) and is
                  OBLIGED to tag those bands as uncorrected — this is the only
                  sanctioned way past the refusal, and it is not silent.

    Returns the normalized stack, or (stack, [refused band names]) when
    skip_missing is True.
    """
    a = np.asarray(stack)
    if a.shape[0] != len(bands):
        raise ValueError(f"stack has {a.shape[0]} bands but `bands` names "
                         f"{len(bands)}: {bands}")
    table = table if table is not None else load_table(table_path)
    if out_dtype is None:
        out_dtype = np.uint8 if a.dtype == np.uint8 else np.float32

    out = np.empty(a.shape, np.dtype(out_dtype))
    refused = []
    for i, b in enumerate(bands):
        try:
            out[i] = normalize_array(a[i], acquisition, b, table_path, table,
                                     valid=valid, out_dtype=out_dtype, clip=clip)
        except (KeyError, ValueError):
            if not skip_missing:
                raise
            refused.append(b)
            out[i] = a[i].astype(out_dtype, copy=False)
    return (out, refused) if skip_missing else out


def apply_to_quantile(value, acquisition, band, table_path: Path = OUT_CSV,
                      table=None):
    """The map applied to a scalar statistic.

    Legitimate because the map is affine and monotone increasing (gain > 0 is
    enforced at fit time), so the q-th quantile of the normalized array IS the
    normalized q-th quantile of the raw array — exactly, up to clipping at the
    dtype bounds. That identity is what lets the validation below quantify
    convergence from the R1 CSV without re-reading a single ortho.
    """
    gain, offset, _ = coefficients(acquisition, band, table_path, table)
    return gain * float(value) + offset


# ══════════════════════════════════════════════════════════════════════════════
#  VALIDATION — does the table actually make acquisitions agree?
# ══════════════════════════════════════════════════════════════════════════════

def _pair_convergence(fp, table, a_key, b_key, bands=RGB):
    """Before/after spine agreement for one pair, per band.

    TWO measures, because they answer different questions:
      p50 delta  — the headline "do the medians land on each other".
      spine RMS  — RMS over every shared uncensored spine quantile (p5/p50/p95
                   x 2 targets). Harder to satisfy: a p50 can agree while the
                   ends diverge, which is precisely what a gain error looks like.
    """
    out = []
    for band in bands:
        a_pts = {(t, q): v for t, q, v in spine_points(fp[a_key], band)}
        b_pts = {(t, q): v for t, q, v in spine_points(fp[b_key], band)}
        keys = sorted(set(a_pts) & set(b_pts))
        if not keys:
            continue
        av = np.array([a_pts[k] for k in keys], float)
        bv = np.array([b_pts[k] for k in keys], float)

        try:
            ga, oa, _ = coefficients(a_key, band, table=table)
            gb, ob, _ = coefficients(b_key, band, table=table)
        except (KeyError, ValueError) as exc:
            out.append({"band": band, "skipped": str(exc).split(":")[0], "n": len(keys)})
            continue

        an, bn = ga * av + oa, gb * bv + ob
        ap50, bp50 = spine_p50(fp[a_key], band), spine_p50(fp[b_key], band)
        out.append({
            "band": band, "n": len(keys),
            "a_p50": ap50, "b_p50": bp50,
            "d_p50_before": (ap50 - bp50) if (ap50 and bp50) else None,
            "a_p50_norm": ga * ap50 + oa if ap50 else None,
            "b_p50_norm": gb * bp50 + ob if bp50 else None,
            "d_p50_after": ((ga * ap50 + oa) - (gb * bp50 + ob)) if (ap50 and bp50) else None,
            "rms_before": _rms(av - bv), "rms_after": _rms(an - bn),
        })
    return out


def _gr_invariant(fp, key, table=None, corrected=False):
    """R1's gr_invariant: median over spine targets of (G p50 / R p50).

    Formula copied from qc/radiometry_fingerprint.derive() so the corrected
    number is comparable to the published raw one, digit for digit.
    """
    vals = []
    for t in SPINE:
        g = fp[key]["stats"].get((t, "G"), {}).get("p50")
        r = fp[key]["stats"].get((t, "R"), {}).get("p50")
        if g is None or r is None or r <= 0:
            continue
        if corrected:
            gg, go, _ = coefficients(key, "G", table=table)
            rg, ro, _ = coefficients(key, "R", table=table)
            g, r = gg * g + go, rg * r + ro
        if r <= 0:
            continue
        vals.append(g / r)
    return float(np.median(vals)) if vals else None


def validate(fp, table, reference, nir_reference, out=print):
    """The convergence report. Returns a dict of the headline numbers."""
    res = {"pairs": {}, "gr": {}, "identity": {}}

    out("")
    out("=" * 78)
    out(f"  VALIDATION — reference {reference} (RGB) / {nir_reference} (NIR)")
    out("=" * 78)

    # ── 0. identity sanity: the reference must fit to gain 1, offset 0 ────────
    out("")
    out("  [0] REFERENCE IDENTITY CHECK (catches a sign / axis swap in the fit)")
    for key, bands in ((reference, RGB), (nir_reference, ("N",))):
        for b in bands:
            g, o, _ = coefficients(key, b, table=table)
            ok = abs(g - 1.0) < 1e-9 and abs(o) < 1e-9
            res["identity"][f"{key}:{b}"] = (g, o, ok)
            out(f"      {key:6s} {b}  gain={g:.6f} offset={o:+.4f}  "
                f"{'OK' if ok else '!! NOT IDENTITY'}")
    # and a genuinely refitted acquisition must not come back as identity
    probe = [k for k in fp if k not in (reference, nir_reference)][:1]
    if probe:
        g, o, _ = coefficients(probe[0], "R", table=table)
        out(f"      {probe[0]:6s} R  gain={g:.6f} offset={o:+.4f}  "
            f"(non-reference — identity here would mean the fit is a no-op)")

    # ── 1. same-flight cross-sensor pairs ─────────────────────────────────────
    out("")
    out("  [1] SAME-FLIGHT CROSS-SENSOR CONVERGENCE")
    out("      Same ground, same day, different sensor + processing chain, so a")
    out("      residual difference over invariant hardscape is radiometry alone.")
    out("      d(p50)   = spine median difference, DN.  RMS = over all shared")
    out("      uncensored spine quantiles (p5/p50/p95 x 2 targets).")

    for a_key, b_key, why in SAME_FLIGHT_PAIRS + CROSS_SOURCE_PAIRS:
        if a_key not in fp or b_key not in fp:
            out(f"      !! {a_key} vs {b_key}: not in the fingerprint")
            continue
        bands = list(RGB)
        if all(any(b == "N" for (_, b) in fp[k]["stats"]) for k in (a_key, b_key)):
            bands.append("N")
        rows = _pair_convergence(fp, table, a_key, b_key, bands)
        res["pairs"][f"{a_key}|{b_key}"] = rows
        out("")
        out(f"      {a_key} vs {b_key}  —  {why}")
        out(f"        band  {'p50 A':>7s} {'p50 B':>7s} | {'d(p50) raw':>11s} "
            f"{'d(p50) norm':>12s} | {'RMS raw':>8s} {'RMS norm':>9s}  verdict")
        for r in rows:
            if "skipped" in r:
                out(f"        {r['band']:4s}  {'—':>7s} {'—':>7s} | "
                    f"REFUSED — {r['skipped']}")
                continue
            # 0.5 DN is half a uint8 step — below it there is nothing to call.
            db, da = abs(r["d_p50_before"]), abs(r["d_p50_after"])
            imp = ("converged" if da < db - 0.5 else
                   "flat" if da <= db + 0.5 else "WORSE")
            out(f"        {r['band']:4s}  {r['a_p50']:7.1f} {r['b_p50']:7.1f} | "
                f"{r['d_p50_before']:+11.1f} {r['d_p50_after']:+12.1f} | "
                f"{r['rms_before']:8.1f} {r['rms_after']:9.1f}  {imp}")
        fin = [r for r in rows if "skipped" not in r]
        if fin:
            out(f"        MEAN |d(p50)|  raw {np.mean([abs(r['d_p50_before']) for r in fin]):5.1f} DN"
                f"  ->  norm {np.mean([abs(r['d_p50_after']) for r in fin]):5.1f} DN"
                f"   |  MEAN RMS  raw {np.mean([r['rms_before'] for r in fin]):5.1f}"
                f"  ->  norm {np.mean([r['rms_after'] for r in fin]):5.1f} DN")

    # ── 2. the 2000 King colour cast ──────────────────────────────────────────
    out("")
    out("  [2] THE 2000 KING COLOUR CAST (IMAGERY_FACTS §3, R1 anomaly)")
    out("      gr_invariant = median over spine targets of (G p50 / R p50) —")
    out("      R1's own formula. On invariant hardscape this SHOULD sit at the")
    out("      reference's value; 2000 reads far green of it.")
    ref_gr = _gr_invariant(fp, reference)
    out(f"        reference {reference}: gr_invariant = {ref_gr:.4f}   "
        f"<- the target, NOT 1.0000 (hardscape is not neutral grey)")
    for key in ("2000", "2005", "2007", "2009"):
        if key not in fp:
            continue
        raw = _gr_invariant(fp, key)
        try:
            cor = _gr_invariant(fp, key, table=table, corrected=True)
        except (KeyError, ValueError):
            cor = None
        if raw is None:
            continue
        mark = "  <- THE 2000 CAST" if key == "2000" else ""
        if cor is None:
            out(f"        {key:6s} raw {raw:.4f}  corrected —{mark}")
            continue
        res["gr"][key] = (raw, cor, ref_gr)
        out(f"        {key:6s} raw {raw:.4f} ({(raw / ref_gr - 1) * 100:+6.2f}% vs ref)"
            f"  ->  corrected {cor:.4f} ({(cor / ref_gr - 1) * 100:+6.2f}% vs ref)"
            f"{mark}")

    # ── 3. record-wide spread ─────────────────────────────────────────────────
    out("")
    out("  [3] RECORD-WIDE SPREAD ON INVARIANT GROUND (all acquisitions)")
    out("      Std-dev across acquisitions of the spine p50, per band. This is")
    out("      the quantity that makes cross-year colour uncomparable.")
    for band in ALL_BANDS:
        raw, cor = [], []
        for key in fp:
            v = spine_p50(fp[key], band)
            if v is None:
                continue
            raw.append(v)
            try:
                cor.append(apply_to_quantile(v, key, band, table=table))
            except (KeyError, ValueError):
                pass
        if len(raw) < 3:
            continue
        out(f"        {band}  n={len(raw):2d} raw  sd={np.std(raw):6.2f} DN "
            f"range {min(raw):5.1f}-{max(raw):5.1f}   |   "
            f"n={len(cor):2d} norm sd={np.std(cor):6.2f} DN "
            f"range {min(cor):5.1f}-{max(cor):5.1f}")
    out("")
    out("      CAVEAT on [3]: unlike [1], this pools acquisitions from different")
    out("      DATES, so part of the raw spread is real illumination/season and")
    out("      the shrink is not all 'error removed'. [1] is the honest test.")

    # ── 4. dark-end extrapolation — where the table STOPS being trustworthy ───
    out("")
    out("  [4] DARK-END EXTRAPOLATION CHECK  (a DOMAIN WARNING, not a result)")
    out("      The fit spans hardscape DNs only. Open water is the darkest real")
    out("      target in the record and sits FAR below that span, so what the")
    out("      table does there is extrapolation. This measures the cost.")
    out("")
    out(f"      {'acq':7s} {'fit domain R':>13s} {'water R':>8s} "
        f"{'fit domain N':>13s} {'water N':>8s} | {'NDVI raw':>9s} {'NDVI norm':>10s}")
    raw_w, norm_w, clamped = [], [], 0
    for key in sorted(fp, key=lambda s: (s[:4], s)):
        st = fp[key]["stats"]
        if (FLOOR_TARGET, "N") not in st or (FLOOR_TARGET, "R") not in st:
            continue
        wr, wn = st[(FLOOR_TARGET, "R")]["p50"], st[(FLOOR_TARGET, "N")]["p50"]
        if wr is None or wn is None:
            continue
        rr = table.get((key, "R"))
        nr = table.get((key, "N"))
        dom_r = (f"[{rr['fit_x_min']},{rr['fit_x_max']}]"
                 if rr and rr.get("fit_x_min") else "—")
        dom_n = (f"[{nr['fit_x_min']},{nr['fit_x_max']}]"
                 if nr and nr.get("fit_x_min") else "—")
        ndvi_raw = (wn - wr) / (wn + wr + 1e-6)
        try:
            nrr = max(apply_to_quantile(wr, key, "R", table=table), 0.0)
            nnn = max(apply_to_quantile(wn, key, "N", table=table), 0.0)
            ndvi_n = (nnn - nrr) / (nnn + nrr + 1e-6)
            if ndvi_n <= -0.999:
                clamped += 1
            raw_w.append(ndvi_raw)
            norm_w.append(ndvi_n)
            s_n = f"{ndvi_n:+10.3f}"
        except (KeyError, ValueError):
            s_n = f"{'REFUSED':>10s}"
        out(f"      {key:7s} {dom_r:>13s} {wr:8.0f} {dom_n:>13s} {wn:8.0f} | "
            f"{ndvi_raw:+9.3f} {s_n}")
    if norm_w:
        out("")
        out(f"      water NDVI sd across the fitted 4-band years: "
            f"raw {np.std(raw_w):.3f}  ->  normalized {np.std(norm_w):.3f}   "
            f"({clamped} of {len(norm_w)} CLAMPED at -1.000)")
        out("      DO NOT READ THAT SHRINK AS A CONVERGENCE WIN. It is DEGENERATE")
        out("      agreement — the same failure mode as the p50-only fit in")
        out("      --step compare-methods. The raw spread shows the dark end was")
        out("      already incomparable; normalization does not rescue it, it")
        out("      flattens it. The offset lifts red by tens of DN where NIR")
        out("      barely moves, so normalized NDVI runs hard negative in SHADOW")
        out("      as well as on water.")
        out("      CONSEQUENCES: (a) the §12 lifted-floor negative-tail test must")
        out("      be run on the NATIVE stack, never the normalized one; (b) a")
        out("      vegetation-presence read in deep shadow is LESS reliable in the")
        out("      normalized product than in the native one.")
    return res


def compare_methods(fp, reference=DEFAULT_REF, nir_reference=DEFAULT_NIR_REF,
                    out=print):
    """Reproduce the estimator-choice table in the header. Writes nothing.

    The criterion is the SAME-FLIGHT PAIR convergence, which is a fair test of a
    fit made against 2020s: neither pair member is fitted to the other, so their
    agreement after correction is not something the fit was tuned on.

    Both measures are printed because either alone can be gamed — see the
    p50-only row, which scores a perfect 0.00 on d(p50) with a line that is
    catastrophically wrong everywhere else.
    """
    variants = [(("p5", "p50", "p95"), "ols"), (("p5", "p50", "p95"), "theil-sen"),
                (("p5", "p50"), "ols"), (("p50", "p95"), "ols"),
                (("p1", "p5", "p50", "p95", "p99"), "ols"), (("p50",), "ols")]

    def _pts(rec, band, qs):
        o = {}
        for t in SPINE:
            st = rec["stats"].get((t, band))
            if not st:
                continue
            for q in qs:
                v = st.get(q)
                if v is not None and CLIP_LO < v < CLIP_HI:
                    o[(t, q)] = v
        return o

    def _fit(key, band, qs, method):
        ref = nir_reference if band == "N" else reference
        a, b = _pts(fp[key], band, qs), _pts(fp[ref], band, qs)
        keys = sorted(set(a) & set(b))
        if len(keys) < 2:
            return None
        x = np.array([a[k] for k in keys], float)
        y = np.array([b[k] for k in keys], float)
        g, o = (theil_sen(x, y) if method == "theil-sen" else ols(x, y))
        return None if (g is None or g <= 0) else (g, o)

    def _score(qs, method):
        dp, rms = [], []
        for a_key, b_key, _ in SAME_FLIGHT_PAIRS + CROSS_SOURCE_PAIRS:
            bands = list(RGB)
            if all(any(b == "N" for (_, b) in fp[k]["stats"]) for k in (a_key, b_key)):
                bands.append("N")
            for band in bands:
                fa, fb = (_fit(a_key, band, qs, method) if qs else None), \
                         (_fit(b_key, band, qs, method) if qs else None)
                pa, pb = spine_p50(fp[a_key], band), spine_p50(fp[b_key], band)
                ap = {(t, q): v for t, q, v in spine_points(fp[a_key], band)}
                bp = {(t, q): v for t, q, v in spine_points(fp[b_key], band)}
                keys = sorted(set(ap) & set(bp))
                av = np.array([ap[k] for k in keys], float)
                bv = np.array([bp[k] for k in keys], float)
                if qs is None:                                   # raw baseline
                    dp.append(abs(pa - pb))
                    rms.append(_rms(av - bv))
                    continue
                if not fa or not fb:
                    continue
                dp.append(abs((fa[0] * pa + fa[1]) - (fb[0] * pb + fb[1])))
                rms.append(_rms((fa[0] * av + fa[1]) - (fb[0] * bv + fb[1])))
        return float(np.mean(dp)), float(np.mean(rms)), len(dp)

    out("")
    out("=" * 78)
    out("  ESTIMATOR COMPARISON — scored on same-flight cross-sensor convergence")
    out("=" * 78)
    out("  Both members of each pair are fitted to the REFERENCE, never to each")
    out("  other, so their post-correction agreement is not tuned on.")
    out("")
    out(f"  {'quantile set':22s} {'method':10s} {'mean |d(p50)|':>14s} "
        f"{'mean spine RMS':>15s}  n")
    for qs, method in variants:
        d, r, n = _score(qs, method)
        star = "  <- DEFAULT" if (qs == QUANTILES and method == DEFAULT_METHOD) else ""
        warn = "  <- DEGENERATE: exact by construction, line is nonsense" \
            if len(qs) == 1 else ""
        out(f"  {'/'.join(qs):22s} {method:10s} {d:11.2f} DN {r:12.2f} DN  "
            f"{n:2d}{star}{warn}")
    d, r, n = _score(None, None)
    out(f"  {'RAW (no correction)':22s} {'—':10s} {d:11.2f} DN {r:12.2f} DN  {n:2d}")
    out("")
    out("  The p50-only row is why d(p50) is never quoted alone: two points through")
    out("  the two targets' medians satisfy it exactly and define a wildly wrong line.")


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

def _print_table(rows, out=print):
    out("")
    out("=" * 78)
    out("  FITTED TABLE")
    out("=" * 78)
    out(f"  {'acq':7s} {'b':2s} {'gain':>8s} {'offset':>8s} {'RMS':>6s} "
        f"{'pre':>6s} {'n':>2s}  reference / reason")
    for r in rows:
        if r["gain"] == "":
            out(f"  {r['acquisition']:7s} {r['band']:2s} {'—':>8s} {'—':>8s} "
                f"{'—':>6s} {'—':>6s} {'—':>2s}  REFUSED: "
                f"{r['excluded_reason'].split(':')[0]}")
            continue
        out(f"  {r['acquisition']:7s} {r['band']:2s} {float(r['gain']):8.4f} "
            f"{float(r['offset']):+8.2f} {float(r['fit_quality']):6.2f} "
            f"{float(r['pre_rms']):6.2f} {r['n_points']:2d}  {r['reference']}")


def main():
    filtered = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(
        description="Fit a per-acquisition per-band linear radiometric "
                    "normalization onto one reference, from the R1 fingerprint.")
    ap.add_argument("--step", default="all",
                    choices=["fit", "validate", "all", "compare-methods"])
    ap.add_argument("--reference", default=DEFAULT_REF,
                    help=f"RGB reference acquisition (default {DEFAULT_REF}).")
    ap.add_argument("--nir-reference", default=DEFAULT_NIR_REF,
                    help=f"NIR reference; must have a healthy floor "
                         f"(default {DEFAULT_NIR_REF}).")
    ap.add_argument("--method", default=DEFAULT_METHOD,
                    choices=["theil-sen", "ols"],
                    help=f"Line estimator (default {DEFAULT_METHOD} — see the header "
                         f"table and --step compare-methods).")
    ap.add_argument("--fingerprint", default=str(FP_CSV))
    ap.add_argument("--out", default=str(OUT_CSV))
    ap.add_argument("--quiet-table", action="store_true",
                    help="Do not print the fitted table row by row.")
    args = ap.parse_args(filtered)

    fp = read_fingerprint(Path(args.fingerprint))
    print(f"[radiometry-norm] fingerprint : {args.fingerprint}")
    print(f"[radiometry-norm] acquisitions: {len(fp)}")
    print(f"[radiometry-norm] reference   : {args.reference} (RGB) / "
          f"{args.nir_reference} (NIR)")
    print(f"[radiometry-norm] method      : {args.method}  on {'+'.join(SPINE)} "
          f"p5/p50/p95 (neg_water excluded — sun-glint)")

    out_path = Path(args.out)
    if args.step == "compare-methods":
        compare_methods(fp, args.reference, args.nir_reference)
        return 0

    if args.step in ("fit", "all"):
        rows = build_table(fp, args.reference, args.nir_reference, args.method)
        write_table(rows, out_path)
        n_fit = sum(1 for r in rows if r["gain"] != "")
        n_ref = sum(1 for r in rows if r["gain"] == "")
        print(f"[radiometry-norm] wrote {out_path}  "
              f"({len(rows)} rows: {n_fit} fitted, {n_ref} refused)")
        if not args.quiet_table:
            _print_table(rows)

    if args.step in ("validate", "all"):
        table = load_table(out_path, force=True)
        validate(fp, table, args.reference, args.nir_reference)

    print("")
    print("  REMINDER: this table is OPT-IN. Nothing applies it automatically, and")
    print("  it must never silently rewrite pipeline inputs or headline products.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

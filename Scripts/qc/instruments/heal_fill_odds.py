"""heal_fill_odds.py — the four-field fill-odds Λ, one row per fill the healer made.

AUDIT STATISTIC. NOT A LICENCE. Read this paragraph before reading any number below.

Four literatures converge on one formula for "present, then k absences, then present"
(`Reports/LIT_HEALING_ANALOGUES_2026-09-08.md` §3: occupancy — MacKenzie 2003 Eqs. 3-5;
two-state HMM bridging; interval-censored survival — Gu 2015 Eq. 2.1; astronomy's joint
non-detection):

    Λ = (1-ε)^(k+1) · ∏_{t in gap}(1-p_t) / [ ε · γ · (1-γ)^(k-1) ]

and the same report establishes that it CANNOT license a fill here, because its
denominator needs γ_conditional = P(regain | recent removal) and the panel supplies only
P(colonisation | empty site), three orders of magnitude smaller. At the panel's γ the
posterior returns HEAL for every acquisition at any recall below 99.99%, so a
pre-registered threshold on it decides nothing. §14(d) of
`Reports/HEALING_TOOL_REASONING_2026-09-07.md` therefore asks for exactly this: Λ
REPORTED BESIDE the tier that licensed the fill, never in place of it. Nothing in this
file changes `temporal_heal.py` or its output.

FOUR REASONS THE NUMBER IS SOFTER THAN IT LOOKS, all of them one-sided:
  * γ_conditional is UNMEASURED. Both γ variants below are stand-ins, and the report's
    test 3 (adjudicate the impossible triples) is the measurement that would replace them.
  * MISSES ARE CORRELATED across acquisitions (recall vs canopy fraction r = 0.9089,
    `phase4/qc/sensitivity_sawtooth.csv`), so ∏(1-p_t) understates P(all missed | present)
    and Λ is biased toward DECLARING LOSS. At k = 1 — every fill in this file — the
    product and the conservative max_t(1-p_t) form of §6 G7 are the same number, so that
    correction has nothing to bite on here and would matter only for k >= 2.
  * p_t is read from `detectability_curve.csv`, whose own docstring says it is recall
    CONDITIONAL on the crown being detectable somewhere in the series — an upper bound on
    true recall. An overstated p_t understates (1-p_t) and biases Λ toward REFUSING.
  * Outside the panel's verified interval p_t is measured against projected-2020 labels
    and is circular (a real removal scores as a miss), biasing p_t down and Λ toward
    FILLING (§3, F7 skeptic). Two unbounded biases of opposite sign; neither is corrected.

THE FILL IS NOT THE CROWN, and the curve only models crowns. p_t is P(a crown reads
>= 0.50 cover at t | both flanks saw it) — a crown-level event — while a fill is a
connected component of healed cells that may be a sliver of an otherwise-detected crown.
`crown_cover_raw` (the dominant crown's RAW canopy fraction at the gap epoch) is published
per row so a reader can see which case they are in: near 0 means the whole-crown miss the
curve models, near 0.5 means a partial miss it does not. Λ assumes the former.

k = 1 FOR EVERY ROW, structurally. `temporal_heal.py::build` only ever tests a single
absent epoch flanked by two present ones, so the gap is one acquisition wide and
(1-γ)^(k-1) = 1. The k column is kept because the formula is general and the healer's
candidate rule is not a property of the formula.

THE TWO γ VARIANTS, side by side, both stated for what they are:
  γ_colonisation   MEASURED, wrong quantity. The panel's gains over its interval, i.e.
                   P(colonisation | empty site). Reported on BOTH denominators §3 names:
                   all gold points, and an empty-site denominator (§3's ~422). Λ under it
                   is enormous and its posterior is ~1 for every fill — that is the
                   report's finding reproduced, not a result about any particular fill.
  γ_rule = 0.20    RULE-IMPLIED, not measured. §3's sensitivity table: at γ ≈ 0.2 the
                   posterior drops below 0.99 for p > 0.912, i.e. fine-year absences
                   refuse and coarse-year absences fill — "the project's tier logic
                   reproduced". It is the value at which the formula would behave like the
                   tiers, quoted back as a diagnostic. It is NOT scaled by Δt: §3's
                   sensitivity uses it directly at k = 1 (this file's
                   `qc/test_heal_fill_odds.py` reproduces the 0.912 crossing), so scaling
                   it while ε is per-interval would put the two on different bases. Stated
                   rather than silently fixed.

ε IS PER ACQUISITION-INTERVAL (§3, F9b skeptic — the archive is irregular):
ε_Δ = 1-(1-ε_annual)^Δt, with ε_annual back-derived from the panel over its own window so
that the window rate is reproduced exactly. The gap's two intervals get their own ε: the
numerator carries (1-ε_left)(1-ε_right); the denominator carries ε_left alone, because a
removal that a regain by t_{k+1} could hide must happen in the FIRST interval.

Δt COMES FROM ACQUISITION DATES where they exist (`qc/imagery_pixelsize_and_date.csv`),
midpoint of the flight window, else from the year labels. `dt_basis` says which, per row.
2011s has no date in that table at all — "NOT FOUND (year from the county service name
Aerial_2011 only)" — so both of its intervals fall back. This is not cosmetic: dated,
2013->2015 is 1.73 yr and 2015->2016 is 1.46 yr, because the 2015 acquisition is a
February-March flight. That same leaf-off flight is why 2015's measured recall is the
series' lowest, so Λ argues loudest for filling exactly where the SEASON changed rather
than the tree. The formula has no term for that.

Output: phase4/qc/heal_fill_odds.csv (one row per fill) + a log10 Λ distribution by tier.

Run:  py -3.12 qc/instruments/heal_fill_odds.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

CURVE_CSV = QC / "detectability_curve.csv"
GOLD_CSV = QC / "panel_a_gold.csv"
META_JSON = QC / "panel_a_meta.json"
HEALGOLD_CSV = QC / "heal_vs_gold.csv"
DATES_CSV = SCRIPTS / "qc" / "imagery_pixelsize_and_date.csv"

CELL_M = 2.0

# The value §3's sensitivity table uses. RULE-IMPLIED, not a measurement — see docstring.
GAMMA_RULE = 0.20

# §3's empty-site denominator: the 2 gains plus "420 of 1169 no-change points [that]
# can't produce a false loss at all" (Reports/CHANGE_DETECTOR_DESIGN_2026-09-06.md, the
# pre-registered-gates paragraph). [inferred] there, so it is cross-checked below against
# the gold's own trajectories rather than trusted.
EMPTY_SITE_DENOM_REPORTED = 422

# Which row of qc/imagery_pixelsize_and_date.csv carries each stack epoch's flight date.
# The mapping is a JUDGEMENT (the table keys on product labels, the stack on epoch names);
# the dates themselves are measured. 2011s is present in the table with no date found.
EPOCH_DATE_ROW = {
    "2009": "2009",
    "2011s": "2011s (campaign S11)",
    "2013": "2013",
    "2015": "2015 (King)",
    "2016": "2016",
    "2019": "2019 (King)",
    "2021": "2021 (King)",
    "2024": "2024 (CoE)",
}

_DATE_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:\s+to\s+(\d{4})-(\d{2})-(\d{2}))?")


# ---------------------------------------------------------------- pure statistics

def annual_from_window(count, n, window_years):
    """Back out the ANNUAL rate whose Δt=window compounding reproduces count/n exactly.

    1-(1-a)^W = count/n. Reproduces §3's quoted 0.0044/yr from 42/1213 over 8 years and
    2.1e-4/yr from 2/1213, which a naive (count/n)/W does not (0.0043).
    """
    if n <= 0 or window_years <= 0:
        return None
    q = count / n
    if q <= 0:
        return 0.0
    if q >= 1:
        return 1.0
    return 1.0 - (1.0 - q) ** (1.0 / window_years)


def interval_rate(annual, dt_years):
    """1-(1-ε_annual)^Δt — §3's per-acquisition-INTERVAL conversion (F9b skeptic)."""
    if annual is None or dt_years is None or dt_years <= 0:
        return None
    return 1.0 - (1.0 - annual) ** dt_years


def fill_odds(k, miss_product, eps_intervals, gamma):
    """Λ = ∏(1-ε_i) · ∏(1-p_t) / [ ε_first · γ · (1-γ)^(k-1) ].

    `eps_intervals` is the k+1 per-interval loss probabilities spanning t0..t_{k+1}; the
    denominator takes the FIRST of them because only a removal in the opening interval can
    be hidden by a regain before t_{k+1}. Returns None when any input is missing or the
    denominator is zero — never a default (a defaulted Λ would be a fabricated licence).
    """
    if miss_product is None or gamma is None or not eps_intervals:
        return None
    if any(e is None for e in eps_intervals):
        return None
    if gamma <= 0 or gamma >= 1:
        return None
    eps_first = eps_intervals[0]
    if eps_first <= 0:
        return None
    num = miss_product
    for e in eps_intervals:
        num *= (1.0 - e)
    den = eps_first * gamma * (1.0 - gamma) ** (k - 1)
    if den <= 0:
        return None
    return num / den


def posterior_fill(lam):
    """Λ/(1+Λ) — MacKenzie 2003 Eq. 3-5 with K=1, the two-path dominant approximation."""
    if lam is None:
        return None
    return lam / (1.0 + lam)


# ---------------------------------------------------------------- the curve

def read_curve(path):
    """{(epoch, diam_lo): row} for kind=bin rows, plus the per-epoch bin ladder."""
    rows = _rows(path)
    curve, bins = {}, {}
    for r in rows:
        if r.get("kind") != "bin":
            continue
        lo = float(r["diam_lo_m"])
        hi = float(r["diam_hi_m"]) if r["diam_hi_m"] not in ("", None) else math.inf
        curve[(r["epoch"], lo)] = {"recall": float(r["recall"]), "hi": hi,
                                   "n_bracketed": int(r["n_bracketed"])}
        bins.setdefault(r["epoch"], []).append((lo, hi))
    for e in bins:
        bins[e] = sorted(bins[e])
    return curve, bins


def size_class_for(diam_m, bins):
    """The curve's own bin containing this diameter, or None. The bins come FROM the
    curve file, so a class always names a row that exists."""
    if diam_m is None or not bins:
        return None
    for lo, hi in bins:
        if lo <= diam_m < hi:
            return (lo, hi)
    return None


def class_label(cls):
    if cls is None:
        return ""
    lo, hi = cls
    return f"{lo:g}+" if hi == math.inf else f"{lo:g}-{hi:g}"


def p_at(curve, epoch, cls):
    """(p_t, source key) from the curve, or (None, '') — never a default value."""
    if cls is None:
        return None, ""
    hit = curve.get((epoch, cls[0]))
    if hit is None:
        return None, ""
    return hit["recall"], f"{epoch}|bin|{class_label(cls)}"


# ---------------------------------------------------------------- rates from the panel

def _rows(p):
    p = Path(p)
    if not p.exists():
        return []
    body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def _window_years(meta_interval):
    """'2016->2024' -> 8. The panel's own interval, read rather than assumed."""
    m = re.match(r"\s*(\d{4})\s*->\s*(\d{4})", str(meta_interval))
    if not m:
        return None
    return int(m.group(2)) - int(m.group(1))


def derive_rates(gold_rows, meta, healgold_rows, years):
    """ε and both γ variants, derived from the frozen gold — no rate is typed in here.

    §3 quotes 1,169/42/2 = 1,213 from CHANGE_DETECTOR_DESIGN_2026-09-06.md; the frozen
    file this reads holds 1,170/42/2 = 1,214 (the one-point drift that document names).
    The file is the home, so the file wins; nothing here moves to two significant figures.
    """
    lab = [r["label"] for r in gold_rows]
    n_gold, n_loss, n_gain = len(lab), lab.count("loss"), lab.count("gain")
    win = _window_years(meta.get("interval"))
    eps_a = annual_from_window(n_loss, n_gold, win)
    gam_all = annual_from_window(n_gain, n_gold, win)

    # Empty-site denominator, cross-checked instead of trusted. §3's ~422 = the gains plus
    # the no-change points that hold no canopy at the interval's start. heal_vs_gold.csv
    # already publishes the raw trajectory at every gold point, so the count is readable.
    n_empty = None
    start_yr = str(meta.get("interval", "")).split("->")[0].strip()
    if healgold_rows and start_yr in years:
        i = years.index(start_yr)
        empty = sum(1 for r in healgold_rows
                    if r.get("label") == "nochange"
                    and len(r.get("raw_trajectory", "")) > i
                    and r["raw_trajectory"][i] == ".")
        n_empty = empty + sum(1 for r in healgold_rows if r.get("label") == "gain")
    denom_empty = n_empty if n_empty else EMPTY_SITE_DENOM_REPORTED
    gam_empty = annual_from_window(n_gain, denom_empty, win)
    return {
        "n_gold": n_gold, "n_loss": n_loss, "n_gain": n_gain, "window_years": win,
        "eps_annual": eps_a, "gamma_annual_colonisation": gam_all,
        "gamma_annual_emptysite": gam_empty, "gamma_rule": GAMMA_RULE,
        "empty_site_denom_used": denom_empty,
        "empty_site_denom_measured": n_empty,
        "empty_site_denom_reported": EMPTY_SITE_DENOM_REPORTED,
    }


# ---------------------------------------------------------------- acquisition dates

def read_dates(path):
    """{stack epoch: (decimal year, verbatim window)} for the epochs a date exists for."""
    out = {}
    rows = _rows(path)
    by_label = {r["year_label"]: r for r in rows}
    for epoch, key in EPOCH_DATE_ROW.items():
        r = by_label.get(key)
        if not r:
            continue
        m = _DATE_RE.match(r.get("date_shot", "") or "")
        if not m:
            continue
        y0 = _decimal_year(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if m.group(4):
            y1 = _decimal_year(int(m.group(4)), int(m.group(5)), int(m.group(6)))
            out[epoch] = ((y0 + y1) / 2.0, f"{m.group(0).strip()} (midpoint)")
        else:
            out[epoch] = (y0, m.group(0).strip())
    return out


def _decimal_year(y, m, d):
    leap = (y % 4 == 0 and y % 100 != 0) or y % 400 == 0
    cum = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    doy = cum[m - 1] + d - 1 + (1 if (leap and m > 2) else 0)
    return y + doy / (366.0 if leap else 365.0)


def delta_years(dates, a, b):
    """(Δt, basis). Dated where both endpoints carry a date, else the year labels."""
    if a in dates and b in dates:
        return dates[b][0] - dates[a][0], "acquisition_date"
    return float(int(b[:4]) - int(a[:4])), "year_label"


# ---------------------------------------------------------------- one row per fill

def make_row(fill, epoch_meta, curve, bins, rates):
    """Everything about one fill, including a blank Λ when the curve has no value.

    `fill` carries the geometry (fill_id, epoch, n_cells, area_m2, crown_id,
    crown_diam_m, crown_cells, cells_in_crown, crown_cover_raw); `epoch_meta` the bracket
    (tier, gaps, Δt and its basis). Pure: given the same inputs it returns the same dict.
    """
    cls = size_class_for(fill.get("crown_diam_m"), bins.get(fill["epoch"], []))
    p, src = p_at(curve, fill["epoch"], cls)
    miss = None if p is None else (1.0 - p)

    eps_a = rates["eps_annual"]
    e_left = interval_rate(eps_a, epoch_meta["dt_left_yr"])
    e_right = interval_rate(eps_a, epoch_meta["dt_right_yr"])
    eps_iv = [e_left, e_right]
    k = epoch_meta["k"]

    g_col = interval_rate(rates["gamma_annual_colonisation"], epoch_meta["dt_right_yr"])
    g_emp = interval_rate(rates["gamma_annual_emptysite"], epoch_meta["dt_right_yr"])
    g_rule = rates["gamma_rule"]          # NOT Δt-scaled — see docstring

    lam_col = fill_odds(k, miss, eps_iv, g_col)
    lam_emp = fill_odds(k, miss, eps_iv, g_emp)
    lam_rule = fill_odds(k, miss, eps_iv, g_rule)

    return {
        "fill_id": fill["fill_id"],
        "epoch": fill["epoch"],
        "prev_epoch": epoch_meta["prev"],
        "next_epoch": epoch_meta["next"],
        "tier": epoch_meta["tier"],
        "k": k,
        "gap_years": epoch_meta["gap_years"],
        "dt_left_yr": _r(epoch_meta["dt_left_yr"], 3),
        "dt_right_yr": _r(epoch_meta["dt_right_yr"], 3),
        "dt_basis": epoch_meta["dt_basis"],
        "n_cells": fill["n_cells"],
        "area_m2": _r(fill["area_m2"], 1),
        "crown_id": fill["crown_id"] or "",
        "crown_diam_m": _r(fill.get("crown_diam_m"), 2),
        "size_class": class_label(cls),
        "crown_cells": fill["crown_cells"] or "",
        "fill_cells_in_crown": fill["cells_in_crown"] or "",
        "fill_share_of_crown": _r(fill.get("fill_share_of_crown"), 3),
        "crown_cover_raw": _r(fill.get("crown_cover_raw"), 3),
        "p_t_list": "" if p is None else f"{p:g}",
        "p_t_source": src,
        "miss_product": _r(miss, 4),
        "epsilon_interval": _r(e_left, 6),
        "epsilon_interval_next": _r(e_right, 6),
        "gamma_interval_colonisation": _sig(g_col, 4),
        "gamma_interval_emptysite": _sig(g_emp, 4),
        "lambda_colonisation": _sig(lam_col, 6),
        "lambda_colonisation_emptysite": _sig(lam_emp, 6),
        "lambda_rule": _sig(lam_rule, 6),
        "log10_lambda_colonisation": _r(_log10(lam_col), 4),
        "log10_lambda_rule": _r(_log10(lam_rule), 4),
        "posterior_fill_colonisation": _r(posterior_fill(lam_col), 8),
        "posterior_fill_colonisation_emptysite": _r(posterior_fill(lam_emp), 8),
        "posterior_fill_rule": _r(posterior_fill(lam_rule), 8),
    }


def _r(v, nd):
    return "" if v is None else round(float(v), nd)


def _sig(v, nd):
    return "" if v is None else float(f"{float(v):.{nd}g}")


def _log10(v):
    if v is None or v <= 0:
        return None
    return math.log10(v)


# ---------------------------------------------------------------- the measurement

def build():
    """Re-run the healer read-only, expand its components into rows, attach Λ.

    Sibling imports live in here, not at module scope: run directly the instruments dir is
    sys.path[0] and they resolve with no path hack (qc/instruments/CLAUDE.md), while a test
    that loads this file by path can still exercise every pure function above.
    """
    import numpy as np
    from scipy import ndimage

    from detectability_curve import load as load_geometry   # same rasterisation as p_t
    from temporal_heal import build as heal_build

    if not CURVE_CSV.exists():
        return None, None, f"{CURVE_CSV.name} absent — run detectability_curve.py"
    gold = _rows(GOLD_CSV)
    if not gold:
        return None, None, "panel_a_gold.csv absent — run freeze_panel_a_gold.py"
    meta = json.loads(META_JSON.read_text(encoding="utf-8"))

    heal_rows, overlays, err = heal_build()
    if err:
        return None, None, err

    stack, inside, years, g, ids = load_geometry()
    rates = derive_rates(gold, meta, _rows(HEALGOLD_CSV), years)
    curve, bins = read_curve(CURVE_CSV)
    dates = read_dates(DATES_CSV)

    n_crowns = int(len(g))
    diam = np.full(n_crowns + 1, np.nan)
    diam[g["idx"].to_numpy()] = g["diameter_m"].to_numpy()
    flat_ids = ids.ravel()
    crown_cells = np.bincount(flat_ids, minlength=n_crowns + 1)

    rows, comp_check = [], []
    for hr in heal_rows:
        epoch = hr["epoch"]
        ov = overlays.get(epoch)
        if ov is None:
            continue
        keep = ov["heal"] | ov["ignore"]
        dl, bl = delta_years(dates, hr["prev"], epoch)
        dr, br = delta_years(dates, epoch, hr["next"])
        epoch_meta = {
            "prev": hr["prev"], "next": hr["next"], "tier": hr["tier"],
            "k": 1,                       # the healer tests one absent epoch, always
            "gap_years": int(hr["gap_left_yr"]) + int(hr["gap_right_yr"]),
            "dt_left_yr": dl, "dt_right_yr": dr,
            "dt_basis": bl if bl == br else f"{bl}|{br}",
        }
        ti = years.index(epoch)
        px = stack[ti].ravel()
        canopy = np.bincount(flat_ids, weights=(px == 1).astype(float),
                             minlength=n_crowns + 1)
        valid = np.bincount(flat_ids, weights=(px != 255).astype(float),
                            minlength=n_crowns + 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            cover = np.where(valid > 0, canopy / np.maximum(valid, 1), np.nan)

        for fill in _components(keep, ids, n_crowns, epoch, ndimage, np):
            cid = fill["crown_id"]
            if cid:
                fill["crown_diam_m"] = (None if np.isnan(diam[cid])
                                        else float(diam[cid]))
                fill["crown_cells"] = int(crown_cells[cid])
                fill["crown_cover_raw"] = (None if np.isnan(cover[cid])
                                           else float(cover[cid]))
                fill["fill_share_of_crown"] = (fill["cells_in_crown"]
                                               / max(int(crown_cells[cid]), 1))
            rows.append(make_row(fill, epoch_meta, curve, bins, rates))
        comp_check.append((epoch, int(hr["n_components"]),
                           sum(1 for r in rows if r["epoch"] == epoch)))
    return rows, {"rates": rates, "comp_check": comp_check, "dates": dates,
                  "cell_m": CELL_M}, None


def _components(keep, ids, n_crowns, epoch, ndimage, np):
    """One dict per connected fill — the unit temporal_heal.csv counts as n_components.

    8-connectivity, the same structure the healer sieved with, so relabelling the kept
    mask reproduces the healer's own component set rather than a different partition.
    """
    lab, n = ndimage.label(keep, structure=np.ones((3, 3), int))
    if not n:
        return []
    h, w = keep.shape
    flat_lab, flat_ids = lab.ravel(), ids.ravel()
    idx = np.flatnonzero(flat_lab > 0)
    L = flat_lab[idx]
    C = flat_ids[idx]

    cells = np.bincount(L, minlength=n + 1)
    first = np.zeros(n + 1, np.int64)
    first[L[::-1]] = idx[::-1]                    # ascending idx, last write = smallest

    dom_crown = np.zeros(n + 1, np.int64)
    dom_cells = np.zeros(n + 1, np.int64)
    sel = C > 0
    if sel.any():
        key = L[sel].astype(np.int64) * (n_crowns + 1) + C[sel]
        uk, cnt = np.unique(key, return_counts=True)
        comp, crown = uk // (n_crowns + 1), uk % (n_crowns + 1)
        order = np.lexsort((cnt, comp))
        comp, crown, cnt = comp[order], crown[order], cnt[order]
        last = np.ones(len(comp), bool)
        last[:-1] = comp[:-1] != comp[1:]
        dom_crown[comp[last]] = crown[last]
        dom_cells[comp[last]] = cnt[last]

    out = []
    for i in range(1, n + 1):
        r0, c0 = divmod(int(first[i]), w)
        out.append({
            "fill_id": f"{epoch}#{r0}_{c0}",      # row-major first cell: stable, unique
            "epoch": epoch,
            "n_cells": int(cells[i]),
            "area_m2": int(cells[i]) * CELL_M ** 2,
            "crown_id": int(dom_crown[i]) or 0,
            "cells_in_crown": int(dom_cells[i]),
            "crown_diam_m": None, "crown_cells": 0,
            "crown_cover_raw": None, "fill_share_of_crown": None,
        })
    return out


# ---------------------------------------------------------------- report

def _quantiles(vals):
    v = sorted(vals)
    if not v:
        return None

    def q(f):
        if len(v) == 1:
            return v[0]
        i = f * (len(v) - 1)
        lo, hi = int(math.floor(i)), int(math.ceil(i))
        return v[lo] + (v[hi] - v[lo]) * (i - lo)
    return {"n": len(v), "min": v[0], "p25": q(0.25), "med": q(0.5),
            "p75": q(0.75), "max": v[-1]}


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    rows, meta, err = build()
    if err:
        print(f"FATAL: {err}")
        return 2

    cols = list(rows[0].keys())
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    R = meta["rates"]
    for k in ("n_gold", "n_loss", "n_gain", "window_years", "eps_annual",
              "gamma_annual_colonisation", "gamma_annual_emptysite", "gamma_rule",
              "empty_site_denom_used", "empty_site_denom_measured",
              "empty_site_denom_reported"):
        buf.write(f"# {k},{R[k]}\n")
    buf.write("# p_t_source_file,phase4/qc/detectability_curve.csv\n")
    buf.write("# gamma_rule_is_measured,0\n")
    buf.write(f"# n_fills,{len(rows)}\n")
    buf.write(f"# n_fills_without_lambda,"
              f"{sum(1 for r in rows if r['lambda_rule'] == '')}\n")
    if not a.dry_run:
        (QC / "heal_fill_odds.csv").write_text(buf.getvalue(), encoding="utf-8",
                                               newline="")

    print(f"{'DRY RUN: ' if a.dry_run else ''}phase4/qc/heal_fill_odds.csv "
          f"— {len(rows):,} fills")
    print(f"\nRATES (derived from panel_a_gold.csv over {R['window_years']} yr, "
          f"{R['n_gold']} points)")
    print(f"  eps_annual                 {R['eps_annual']:.6f}   "
          f"({R['n_loss']} verified losses)  MEASURED")
    print(f"  gamma_annual colonisation  {R['gamma_annual_colonisation']:.3e}  "
          f"({R['n_gain']} gains / {R['n_gold']} points)  MEASURED, WRONG QUANTITY")
    print(f"  gamma_annual empty-site    {R['gamma_annual_emptysite']:.3e}  "
          f"({R['n_gain']} gains / {R['empty_site_denom_used']} empty sites; "
          f"measured denom {R['empty_site_denom_measured']}, "
          f"report says {R['empty_site_denom_reported']})")
    print(f"  gamma_rule                 {R['gamma_rule']:.2f}        "
          f"RULE-IMPLIED (§3 sensitivity), NOT a measurement, NOT Dt-scaled")

    print("\nCOMPONENT CROSS-CHECK vs temporal_heal.csv n_components")
    for e, want, got in meta["comp_check"]:
        print(f"  {e:6} temporal_heal {want:>7,}   here {got:>7,}   "
              f"{'match' if want == got else 'DIFFER'}")

    for name, col in (("gamma_colonisation (panel gains)", "log10_lambda_colonisation"),
                      ("gamma_rule = 0.20 (rule-implied)", "log10_lambda_rule")):
        print(f"\nlog10 LAMBDA by tier — {name}")
        print(f"  {'tier':8}{'n':>8}{'min':>9}{'p25':>9}{'median':>9}{'p75':>9}"
              f"{'max':>9}{'post<0.99':>11}{'post<0.5':>10}")
        pcol = ("posterior_fill_colonisation" if "colonisation" in col
                else "posterior_fill_rule")
        for tier in ("HEAL", "REVIEW", "BLIND", "ALL"):
            sel = [r for r in rows if (tier == "ALL" or r["tier"] == tier)
                   and r[col] != ""]
            if not sel:
                continue
            q = _quantiles([float(r[col]) for r in sel])
            # Two bars, because they mean different things. §3's sensitivity quotes 0.99
            # as the point the formula stops being unanimous; 0.5 is the point it
            # actually prefers LOSS over FILL. A row can be under the first and far
            # above the second, which is "the formula is no longer certain", not
            # "the formula disagrees with the heal".
            r99 = sum(1 for r in sel if float(r[pcol]) < 0.99)
            r50 = sum(1 for r in sel if float(r[pcol]) < 0.5)
            print(f"  {tier:8}{q['n']:>8,}{q['min']:>9.2f}{q['p25']:>9.2f}"
                  f"{q['med']:>9.2f}{q['p75']:>9.2f}{q['max']:>9.2f}"
                  f"{r99 / q['n']:>10.1%}{r50 / q['n']:>10.1%}")

    blank = sum(1 for r in rows if r["lambda_rule"] == "")
    print(f"\n  {blank:,} of {len(rows):,} fills carry NO lambda — the fill overlaps no "
          f"2020 crown,\n  so the detectability curve has no row for it. Blank, never a "
          f"default.")

    # Is Lambda even being applied to the event p_t models? The curve's p_t is a
    # WHOLE-CROWN detection; a fill on a crown already reading half canopy is a partial
    # miss it does not model. Measured, not assumed.
    cov = [float(r["crown_cover_raw"]) for r in rows if r["crown_cover_raw"] != ""]
    if cov:
        q = _quantiles(cov)
        lo = sum(1 for v in cov if v < 0.10) / len(cov)
        hi = sum(1 for v in cov if v > 0.40) / len(cov)
        print(f"\n  crown_cover_raw at the gap epoch, over the {len(cov):,} fills that "
              f"sit on a 2020 crown:\n    p25 {q['p25']:.3f}  median {q['med']:.3f}  p75 "
              f"{q['p75']:.3f}   <0.10: {lo:.1%}   >0.40: {hi:.1%}")
        print("    p_t is P(the CROWN reads >=0.50 cover). A fill on a crown already "
              "reading well\n    above 0 is a PARTIAL miss the curve does not model, and "
              "Lambda assumes it is the\n    whole-crown miss. Read this line before "
              "reading any Lambda.")
    print("\n  NOT A LICENCE. gamma_conditional = P(regain | recent removal) is "
          "UNMEASURED;\n  both gamma variants here are stand-ins (one measures "
          "colonisation of empty sites,\n  the other is the value at which the formula "
          "imitates the tiers). The tier column\n  is what licensed each fill. "
          "Reports/LIT_HEALING_ANALOGUES_2026-09-08.md §3, §7.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

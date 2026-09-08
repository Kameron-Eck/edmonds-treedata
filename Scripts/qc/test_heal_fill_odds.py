"""Gates for the fill-odds audit statistic — chiefly that its kill direction FIRES.

CLAUDE.md 3.4c: "a kill criterion must be shown to FIRE on a known-bad input before it
counts as a gate". Λ's whole claim is that a fill becomes less defensible as the epoch's
detection probability rises — if the acquisition would almost certainly have seen the
crown, an absence is evidence of removal, not of a miss. That is a claim about arithmetic,
so it is tested as one, at both ends and monotonically between them.

The second family pins Λ to the numbers `Reports/LIT_HEALING_ANALOGUES_2026-09-08.md` §3
publishes. If those stop reproducing, either the formula here has drifted or the report's
sensitivity was misread, and both are worth failing over.

The module is loaded BY PATH via importlib, adding nothing to the import path (the 3B
ledger in test_status_discovery.py holds every such site and this adds none),
and every function these tests touch is pure, so no stack, gold or crown file is needed.
"""
from __future__ import annotations

import csv
import importlib.util
import math
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"
CSV_OUT = QC / "heal_fill_odds.csv"
SCHEMAS = SCRIPTS / "docs" / "SCHEMAS.md"


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load("qc/instruments/heal_fill_odds.py", "_heal_fill_odds")

# §3's own worked constants, quoted so a drift in either direction is visible here.
EPS_3 = 0.0044
GAM_COL_3 = 2.1e-4
GAM_RULE_3 = 0.20


def _lam(p, gamma, eps=EPS_3, k=1):
    return M.fill_odds(k, 1.0 - p, [eps] * (k + 1), gamma)


# ------------------------------------------------------------------ the kill direction

def test_certain_detection_drives_lambda_to_zero():
    """MUTATION, the refusing end. p_t -> 1 means the epoch would have seen the crown, so
    an absence is a removal and the fill must lose all support."""
    lam_hi = _lam(0.999999, GAM_RULE_3)
    assert lam_hi < 1.0, lam_hi
    assert M.posterior_fill(lam_hi) < 0.5, "a near-certain detector still licenses a fill"
    assert _lam(1.0, GAM_RULE_3) == 0.0
    assert M.posterior_fill(_lam(1.0, GAM_RULE_3)) == 0.0


def test_hopeless_detection_drives_lambda_up():
    """MUTATION, the filling end. p_t -> 0 means the absence carries no information, so
    the prior odds against a loss-then-regain dominate and the fill is supported."""
    lam_lo = _lam(0.0, GAM_RULE_3)
    assert lam_lo > 1.0, lam_lo
    assert M.posterior_fill(lam_lo) > 0.99
    assert lam_lo > _lam(0.9, GAM_RULE_3) > _lam(0.999, GAM_RULE_3)


def test_lambda_is_strictly_decreasing_in_p():
    vals = [_lam(p, GAM_RULE_3) for p in (0.0, 0.2, 0.5, 0.8, 0.9, 0.95, 0.99, 0.999)]
    assert all(a > b for a, b in zip(vals, vals[1:])), vals


def test_lambda_falls_as_the_gap_widens():
    """A longer run of absences is a weaker case for a fill at fixed p — the whole point
    of a cap. Note which term does that: (1-γ)^(k-1) < 1 SHRINKS the denominator and
    pushes Λ up; it is the miss product ∏(1-p_t) shrinking geometrically that dominates
    it. The relief and the penalty run opposite ways and the penalty wins."""
    a = M.fill_odds(1, 0.1, [EPS_3] * 2, GAM_RULE_3)
    b = M.fill_odds(2, 0.1 * 0.1, [EPS_3] * 3, GAM_RULE_3)
    assert b < a


# ------------------------------------------------------------------ pinned to §3

def test_reproduces_the_reports_gamma_rule_crossing():
    """§3: 'at γ ≈ 0.2 the posterior drops below 0.99 for p > 0.912'."""
    assert M.posterior_fill(_lam(0.912, GAM_RULE_3)) > 0.99
    assert M.posterior_fill(_lam(0.913, GAM_RULE_3)) < 0.99


def test_reproduces_the_reports_colonisation_posteriors():
    """§3, the F8 skeptic's table: 0.999999 at p = 0.3, 0.999991 at p = 0.9,
    0.999908 at p = 0.99 — the reason the panel's γ cannot refuse anything.

    Tolerance 3e-6: the report quotes six decimals from its own rounding of ε and γ
    (0.0044 and 2.1e-4 are themselves rounded), and the third value reproduces as
    0.9999068 here. The claim under test is that no p refuses, not the sixth decimal.
    """
    for p, want in ((0.3, 0.999999), (0.9, 0.999991), (0.99, 0.999908)):
        got = M.posterior_fill(_lam(p, GAM_COL_3))
        assert abs(got - want) < 3e-6, (p, got, want)
        assert got > 0.99, "the panel's γ refused a fill, which §3 says it cannot"


def test_annual_from_window_reproduces_the_quoted_rates():
    """§3 quotes 0.0044/yr from 42 losses, 2.1e-4/yr and ~5.9e-4/yr from 2 gains."""
    assert round(M.annual_from_window(42, 1213, 8), 4) == 0.0044
    assert float(f"{M.annual_from_window(2, 1213, 8):.1e}") == 2.1e-4
    assert float(f"{M.annual_from_window(2, 422, 8):.1e}") == 5.9e-4


def test_interval_rate_compounds_back_to_the_window():
    a = M.annual_from_window(42, 1213, 8)
    assert abs(M.interval_rate(a, 8) - 42 / 1213) < 1e-12
    assert M.interval_rate(a, 2) > M.interval_rate(a, 1)


# ------------------------------------------------------------------ never a default

def _bins():
    return [(0.0, 2.0), (2.0, 6.0), (6.0, math.inf)]


def _curve():
    return {("2015", 0.0): {"recall": 0.75, "hi": 2.0, "n_bracketed": 10},
            ("2015", 2.0): {"recall": 0.80, "hi": 6.0, "n_bracketed": 20},
            ("2015", 6.0): {"recall": 0.95, "hi": math.inf, "n_bracketed": 30}}


def _meta():
    return {"prev": "2013", "next": "2016", "tier": "HEAL", "k": 1, "gap_years": 3,
            "dt_left_yr": 1.7, "dt_right_yr": 1.5, "dt_basis": "acquisition_date"}


def _rates():
    return {"eps_annual": 0.0044, "gamma_annual_colonisation": 2.1e-4,
            "gamma_annual_emptysite": 5.9e-4, "gamma_rule": 0.20}


def _fill(**kw):
    f = {"fill_id": "2015#10_20", "epoch": "2015", "n_cells": 9, "area_m2": 36.0,
         "crown_id": 7, "crown_diam_m": 8.0, "crown_cells": 30, "cells_in_crown": 9,
         "crown_cover_raw": 0.1, "fill_share_of_crown": 0.3}
    f.update(kw)
    return f


def test_a_fill_with_no_curve_row_gets_a_blank_lambda_not_a_default():
    """The failure this forbids is a defaulted p_t: a fabricated licence that reads like
    a measurement. A fill on no 2020 crown, or on an epoch the curve never scored, must
    leave every Λ column EMPTY."""
    no_crown = M.make_row(_fill(crown_id=0, crown_diam_m=None), _meta(),
                          _curve(), {"2015": _bins()}, _rates())
    for k in ("p_t_list", "p_t_source", "miss_product", "lambda_colonisation",
              "lambda_rule", "posterior_fill_rule", "log10_lambda_rule"):
        assert no_crown[k] == "", (k, no_crown[k])

    unscored_epoch = M.make_row(_fill(epoch="1996s"),
                                dict(_meta(), prev="1994", next="1998"),
                                _curve(), {"2015": _bins()}, _rates())
    assert unscored_epoch["lambda_rule"] == ""
    assert unscored_epoch["size_class"] == ""


def test_size_class_and_source_name_a_row_that_exists():
    row = M.make_row(_fill(), _meta(), _curve(), {"2015": _bins()}, _rates())
    assert row["size_class"] == "6+"
    assert row["p_t_source"] == "2015|bin|6+"
    assert row["p_t_list"] == "0.95"
    assert ("2015", 6.0) in _curve()


def test_size_class_for_uses_the_curves_own_ladder():
    b = _bins()
    assert M.size_class_for(1.0, b) == (0.0, 2.0)
    assert M.size_class_for(2.0, b) == (2.0, 6.0)
    assert M.size_class_for(99.0, b) == (6.0, math.inf)
    assert M.size_class_for(None, b) is None
    assert M.size_class_for(5.0, []) is None


def test_make_row_is_deterministic():
    a = M.make_row(_fill(), _meta(), _curve(), {"2015": _bins()}, _rates())
    b = M.make_row(_fill(), _meta(), _curve(), {"2015": _bins()}, _rates())
    assert a == b


def test_fill_odds_refuses_impossible_inputs_rather_than_guessing():
    assert M.fill_odds(1, 0.1, [0.0, 0.0], 0.2) is None      # no loss hazard
    assert M.fill_odds(1, 0.1, [0.004, None], 0.2) is None   # an interval with no Dt
    assert M.fill_odds(1, None, [0.004, 0.004], 0.2) is None  # no curve value
    assert M.fill_odds(1, 0.1, [0.004, 0.004], 0.0) is None  # no regain hazard
    assert M.posterior_fill(None) is None


# ------------------------------------------------------------------ the tracked output

def _schema_columns(stem):
    if not SCHEMAS.exists():
        pytest.skip("SCHEMAS.md absent")
    text = SCHEMAS.read_text(encoding="utf-8")
    parts = re.split(r"^## ", text, flags=re.M)
    sec = [p for p in parts if p.startswith(f"{stem} ")]
    assert sec, f"docs/SCHEMAS.md has no '## {stem}' entry"
    m = re.search(r"Columns:\s*`([^`]+)`", sec[0])
    assert m, f"the {stem} entry names no `Columns:` list"
    return [c.strip() for c in m.group(1).split(",") if c.strip()]


def test_the_tracked_csv_matches_its_schema_entry():
    if not CSV_OUT.exists():
        pytest.skip("heal_fill_odds.csv absent — run qc/instruments/heal_fill_odds.py")
    with CSV_OUT.open(encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == _schema_columns("heal_fill_odds.csv"), (
        "the CSV's columns and docs/SCHEMAS.md disagree — one of them is lying to a "
        "reader who cannot see the other")


def test_the_tracked_csv_never_carries_a_lambda_without_a_source():
    """Every Λ names the detectability_curve row it read p_t from. A Λ with no source is
    a number nobody can re-derive, which is the failure 3.4b exists to prevent."""
    if not CSV_OUT.exists():
        pytest.skip("heal_fill_odds.csv absent")
    body = [ln for ln in CSV_OUT.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    rows = list(csv.DictReader(body))
    assert rows, "no fills scored"
    bad = [r["fill_id"] for r in rows if r["lambda_rule"] != "" and not r["p_t_source"]]
    assert not bad, bad[:5]
    blank = [r for r in rows if r["lambda_rule"] == ""]
    assert all(r["p_t_list"] == "" for r in blank), (
        "a fill has a p_t but no Λ — the formula silently declined a value it had")


def test_the_tracked_csv_says_gamma_rule_is_not_measured():
    """The one thing a reader must not mistake. 0.20 is the value at which the formula
    imitates the tiers; it is not a measurement of P(regain | recent removal)."""
    if not CSV_OUT.exists():
        pytest.skip("heal_fill_odds.csv absent")
    text = CSV_OUT.read_text(encoding="utf-8")
    assert "# gamma_rule_is_measured,0" in text
    src = (SCRIPTS / "qc" / "instruments" / "heal_fill_odds.py").read_text(
        encoding="utf-8")
    assert "NOT A LICENCE" in src and "UNMEASURED" in src, (
        "the instrument no longer states that Λ is an audit statistic, not a licence")

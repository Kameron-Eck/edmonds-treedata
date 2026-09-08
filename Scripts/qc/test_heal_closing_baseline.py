"""Gates for the closing baseline — and for the fact that one of its criteria CANNOT fire.

CLAUDE.md 3.4c asks for a kill criterion to be shown firing on a known-bad input before it
counts as a gate. Doing that here produced a result worth keeping: the laundered-loss
criterion the healing design is gated on — filling the TERMINAL absence of a verified loss
— is UNABLE to fire for any both-sides rule, because a both-sides rule needs a detection
after the cell it fills and a terminal absence has none. Two tests below pin both halves:
the terminal counter stays at zero on an input built to trip it, and the in-interval
counter — the one on the population where a fill really does assert canopy in the middle of
a verified removal — fires at exactly the cap where the run first fits and not one cap
earlier. A criterion that cannot fire is documented as such rather than quoted as a pass.

The rest gates the operator's three morphological properties (extensive, idempotent,
nested), which the comparison rests on, and the year-denominated cap against
`temporal_heal.py::tier_for` itself, so the "equal cap" row cannot silently stop being
equal.

Modules load BY PATH via importlib, adding nothing to the import path (the 3B ledger in
test_status_discovery.py holds every such site and this adds none). Every function here
is pure, so no stack, gold or healer run is needed.
"""
from __future__ import annotations

import csv
import importlib.util
import random
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"
CSV_OUT = QC / "heal_closing_baseline.csv"
HVG_CSV = QC / "heal_vs_gold.csv"
SCHEMAS = SCRIPTS / "docs" / "SCHEMAS.md"

C, A, X = 1, 0, 255      # canopy / absent / IGNORE, the stack's own codes


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load("qc/instruments/heal_closing_baseline.py", "_heal_closing_baseline")
TH = _load("qc/instruments/temporal_heal.py", "_temporal_heal_ro")

# The trend8 cadence, which is what every year-denominated cap is measured against.
YRS = [2009, 2011, 2013, 2015, 2016, 2019, 2021, 2024]


# ------------------------------------------------------------------ the operator

def test_closing_only_fills_runs_bracketed_on_both_sides():
    assert M.close_1d([C, A, C], [0, 1, 2], "acq", 1) == [C, C, C]
    assert M.close_1d([A, A, C], [0, 1, 2], "acq", 3) == [A, A, C]   # no left flank
    assert M.close_1d([C, A, A], [0, 1, 2], "acq", 3) == [C, A, A]   # no right flank
    assert M.close_1d([C, A, X, A, C], [0, 1, 2, 3, 4], "acq", 5) == [C, A, X, A, C]
    assert M.close_1d([X, A, C], [0, 1, 2], "acq", 3) == [X, A, C]   # 255 is no anchor


def test_closing_respects_the_acquisition_cap():
    t = [C, A, A, C]
    assert M.close_1d(t, [0, 1, 2, 3], "acq", 1) == t
    assert M.close_1d(t, [0, 1, 2, 3], "acq", 2) == [C, C, C, C]


def test_closing_is_extensive_and_never_writes_canopy_down():
    """Breen, Jones & Talbot 2000 Table 1 §3.2: closings are extensive. Random over the
    state space rather than a hand-picked case, because 1 -> 0 is the failure the whole
    healing design forbids and a hand-picked case would miss it."""
    rng = random.Random(20260908)
    for _ in range(400):
        n = rng.randint(3, 8)
        t = [rng.choice([C, A, X]) for _ in range(n)]
        yrs = YRS[:n]
        for rule, K in (("acq", 2), ("step_years", 3), ("span_years", 6),
                        ("tier_matched", 0)):
            out = M.close_1d(t, yrs, rule, K)
            assert all(o == v for o, v in zip(out, t) if v != A), "a non-absent cell moved"
            assert all(o in (A, C) for o, v in zip(out, t) if v == A)
            assert sum(v == C for v in out) >= sum(v == C for v in t)


def test_closing_is_idempotent_and_nested_in_K():
    rng = random.Random(7)
    for _ in range(200):
        t = [rng.choice([C, A, A, X]) for _ in range(8)]
        once = M.close_1d(t, YRS, "acq", 3)
        assert M.close_1d(once, YRS, "acq", 3) == once, "not idempotent"
        for k in (1, 2, 3, 4, 5):
            lo = M.close_1d(t, YRS, "acq", k)
            hi = M.close_1d(t, YRS, "acq", k + 1)
            assert all(h == C for h, o in zip(hi, lo) if o == C), "not nested in K"


def test_the_year_cap_matches_the_tiers_own_gap_rule():
    """`step_years` must agree with what makes a bracket BLIND, or the 'equal cap' row in
    the table is not equal. temporal_heal.py::tier_for is the authority and is imported."""
    assert TH.tier_for("2013", "2015", "2016") != "BLIND"
    assert M.admits("step_years", 2, 1, 1, [2013, 2015, 2016])
    assert TH.tier_for("2015", "2016", "2019") == "BLIND"
    assert not M.admits("step_years", 2, 1, 1, [2015, 2016, 2019])
    assert TH.tier_for("2019", "2021", "2024") == "BLIND"
    assert not M.admits("step_years", 2, 1, 1, [2019, 2021, 2024])
    # and the combined arm is exactly "one absent epoch, no step over 2 years"
    assert M.admits("tier_matched", 0, 1, 1, [2013, 2015, 2016])
    assert not M.admits("tier_matched", 0, 1, 2, [2013, 2015, 2016, 2019])
    assert not M.admits("tier_matched", 0, 1, 1, [2016, 2019, 2021])


def test_admits_refuses_an_unknown_rule_instead_of_defaulting():
    with pytest.raises(ValueError):
        M.admits("whatever", 3, 1, 1, YRS)


# ------------------------------------------------------------------ the kill criteria

def test_in_interval_laundering_fires_at_K_and_not_at_K_minus_one():
    """MUTATION. A verified loss whose absence runs across the panel's interior epochs is
    injected; the criterion must catch it exactly when the cap first admits the run.

    2016 C, 2019 absent, 2021 absent, 2024 C — a real removal followed by something the
    2024 acquisition reads as canopy. Both interior epochs are inside the panel's
    2016->2024 window, so filling them asserts canopy in the middle of a verified event.
    """
    raw = [C, C, C, C, C, A, A, C]                 # ...2016 C, 2019 ., 2021 ., 2024 C
    interior = [5, 6]                              # 2019, 2021
    at2 = M.close_1d(raw, YRS, "acq", 2)
    at1 = M.close_1d(raw, YRS, "acq", 1)
    assert M.filled_at(raw, at2, interior) == 2, "the known-bad fill was not detected"
    assert M.filled_at(raw, at1, interior) == 0, "the cap below it fired anyway"

    agg2 = M.score_arm([("loss", raw, at2)], interior)
    agg1 = M.score_arm([("loss", raw, at1)], interior)
    assert agg2["laundered_in_interval"] == 2
    assert agg1["laundered_in_interval"] == 0
    assert M.eligibility([("loss", raw)], YRS, interior)[1] == 1, (
        "the at-risk denominator does not contain the point the criterion just caught")


def test_the_terminal_criterion_cannot_fire_for_a_both_sides_rule():
    """MUTATION, and it deliberately FAILS TO FIRE — that is the finding.

    The same injected loss, plus a genuinely terminal one, scored with heal_vs_gold's
    definition of laundering (filling the TRAILING run of absences). No cap, however
    permissive, produces a hit: the trailing run has no 1 after it, and a both-sides rule
    fills nothing that has no 1 after it. `0 of 42 laundered` is therefore not evidence
    about this family of rules; the at-risk denominator is structurally zero and must be
    published beside the count (§6 G2).
    """
    cases = [[C, C, C, C, C, A, A, C],      # interior absences, a later detection
             [C, C, C, C, C, A, A, A],      # a true terminal removal
             [C, A, C, A, A, A, A, A],      # a dropout AND a terminal removal
             [C, C, A, C, C, A, C, A]]      # flicker with a terminal absence
    for raw in cases:
        for K in range(1, 9):
            new = M.close_1d(raw, YRS, "acq", K)
            assert M.terminal_laundered(raw, new) == 0
        assert M.eligibility([("loss", raw)], YRS, [5, 6])[0] == 0


def test_eligibility_is_the_unbounded_rule_not_a_chosen_cap():
    """The denominator has to be the most permissive member of the family, or a narrow
    cap would flatter itself by shrinking its own at-risk set."""
    raw = [C, C, C, A, A, A, A, C]          # a 4-wide interior run
    n_term, n_int = M.eligibility([("loss", raw)], YRS, [5, 6])
    assert (n_term, n_int) == (0, 1)


def test_canopy_only_refuses_to_credit_an_ignore_mark():
    """A cell marked 255 stops being a triple's middle without anyone asserting a tree.
    The like-for-like column must not count that as a triple removed."""
    raw = [C, A, C]
    ignored = [C, X, C]
    filled = [C, C, C]
    assert M.triples(raw) == 1
    assert M.triples(ignored) == 0                       # the raw count is fooled
    assert M.triples(M.canopy_only(raw, ignored)) == 1    # the like-for-like is not
    assert M.triples(M.canopy_only(raw, filled)) == 0

    a = M.score_arm([("nochange", raw, ignored)], [1])
    assert a["nochange_triples_removed"] == 1
    assert a["nochange_triples_removed_canopy_only"] == 0


def test_scoring_is_deterministic():
    rng = random.Random(3)
    pts = [("nochange", [rng.choice([C, A, X]) for _ in range(8)]) for _ in range(50)]
    pairs = [(lab, raw, M.close_1d(raw, YRS, "acq", 2)) for lab, raw in pts]
    assert M.score_arm(pairs, [5, 6]) == M.score_arm(pairs, [5, 6])


# ------------------------------------------------------------------ parity and the output

def _rows(p):
    body = [ln for ln in Path(p).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def test_the_rescoring_reproduces_heal_vs_gold_row_for_row():
    """The comparison is only honest if both arms go through the same scorer. This checks
    the re-implementation against heal_vs_gold.py's OWN published per-point numbers —
    the same check `build()` runs before it prints a table."""
    if not HVG_CSV.exists():
        pytest.skip("heal_vs_gold.csv absent — run qc/instruments/heal_vs_gold.py")
    bad = []
    for r in _rows(HVG_CSV):
        raw, new = M.decode(r["raw_trajectory"]), M.decode(r["healed_trajectory"])
        mine = (M.triples(raw), M.triples(new), M.terminal_laundered(raw, new),
                M.terminal_censored(raw, new), M.filled_at(raw, new, range(len(raw))))
        theirs = (int(r["impossible_triples_raw"]), int(r["impossible_triples_healed"]),
                  int(r["terminal_laundered"]), int(r["terminal_censored"]),
                  int(r["healed_to_canopy"]))
        if mine != theirs:
            bad.append((r["point_id"], mine, theirs))
    assert not bad, bad[:5]


def test_the_tracked_csv_matches_its_schema_entry():
    if not CSV_OUT.exists():
        pytest.skip("heal_closing_baseline.csv absent — run the instrument")
    if not SCHEMAS.exists():
        pytest.skip("SCHEMAS.md absent")
    parts = re.split(r"^## ", SCHEMAS.read_text(encoding="utf-8"), flags=re.M)
    sec = [p for p in parts if p.startswith("heal_closing_baseline.csv ")]
    assert sec, "docs/SCHEMAS.md has no '## heal_closing_baseline.csv' entry"
    m = re.search(r"Columns:\s*`([^`]+)`", sec[0])
    assert m, "the entry names no `Columns:` list"
    with CSV_OUT.open(encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == [c.strip() for c in m.group(1).split(",") if c.strip()]


def test_the_tracked_csv_publishes_both_at_risk_denominators():
    """A laundering count without its denominator is the defect §6 G2 exists to stop."""
    if not CSV_OUT.exists():
        pytest.skip("heal_closing_baseline.csv absent")
    text = CSV_OUT.read_text(encoding="utf-8")
    assert "# n_eligible_terminal," in text
    assert "# n_eligible_in_interval," in text
    rows = _rows(CSV_OUT)
    assert rows, "no arms scored"
    assert all("n_eligible_terminal" in r and "n_eligible_in_interval" in r for r in rows)
    assert any(r["arm"] == "healer" for r in rows), (
        "the healer's own row is missing — the baseline has nothing to be a baseline for")

"""Tests for the referee's scorer, crown_state_vs_gold.py.

No lake, no gpkg, no stack: the scoring core is pure and is exercised on synthetic
trajectories. The one test that matters most is the MUTATION test — `test_laundering_
counter_fires` shows the counter going from 0 to non-zero when a verified loss's TERMINAL
absence is asserted as canopy. A gate that has never been shown to fire is not known to
work (CLAUDE.md 3.4c).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
MOD_PATH = HERE / "instruments" / "crown_state_vs_gold.py"


def _mod():
    spec = importlib.util.spec_from_file_location("_csvg_test", MOD_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def M():
    return _mod()


# ------------------------------------------------------------------ the definitions

def test_triples_matches_heal_vs_gold_definition(M):
    assert M.triples([1, 0, 1]) == 1
    assert M.triples([1, 0, 1, 0, 1]) == 2
    assert M.triples([1, 1, 1]) == 0
    assert M.triples([1, 255, 1]) == 0          # IGNORE is not an absence
    assert M.triples([0, 1, 0]) == 0
    assert M.triples([1, 0]) == 0               # needs a right flank


def test_terminal_start(M):
    assert M.terminal_start([1, 1, 1]) == 3     # no terminal absence
    assert M.terminal_start([1, 1, 0, 0]) == 2
    assert M.terminal_start([0, 0, 0]) == 0
    assert M.terminal_start([1, 0, 1, 0]) == 3  # only the LAST run counts


# ------------------------------------------------------------------ the K1 mutation

def test_laundering_counter_fires(M):
    """MUTATION TEST. Same verified loss, two model outputs. The only thing that changes
    is whether the model asserts canopy inside the terminal absence."""
    raw = [1, 1, 1, 0, 0]                        # a real removal after epoch 2
    honest = [1, 1, 1, 0, 0]                     # the model agrees the tree is gone
    launderer = [1, 1, 1, 1, 1]                  # the model fills the removal back in

    ok = M.score_point(raw, honest, honest)
    bad = M.score_point(raw, launderer, launderer)

    assert ok["terminal_absent_epochs"] == 2
    assert ok["terminal_laundered"] == 0, "the honest path must not be flagged"
    assert bad["terminal_absent_epochs"] == 2
    assert bad["terminal_laundered"] == 2, "the gate did not fire on a known-bad input"
    assert bad["terminal_laundered_posterior"] == 2


def test_midseries_dropout_is_not_laundering(M):
    """heal_vs_gold's own correction: filling an UPSTREAM dropout at a point cut later is
    the operator working. Only the terminal run counts."""
    raw = [1, 0, 1, 0, 0]
    after = [1, 1, 1, 0, 0]
    r = M.score_point(raw, after, after)
    assert r["terminal_laundered"] == 0
    assert r["healed_to_canopy"] == 1           # the dropout WAS filled
    assert r["impossible_triples_raw"] == 1
    assert r["impossible_triples_healed"] == 0


def test_censoring_is_structurally_zero(M):
    """The model has no IGNORE state, so the column exists but can never be non-zero."""
    raw = [1, 1, 0, 0]
    r = M.score_point(raw, [1, 1, 0, 0], [1, 1, 0, 0])
    assert r["terminal_censored"] == 0
    assert r["healed_to_ignore"] == 0


def test_viterbi_and_posterior_paths_scored_separately(M):
    raw = [1, 1, 0, 0]
    r = M.score_point(raw, [1, 1, 0, 0], [1, 1, 1, 1])
    assert r["terminal_laundered"] == 0
    assert r["terminal_laundered_posterior"] == 2


# ------------------------------------------------------------------ the aggregation

def _row(M, label, raw, after, offcrown=0):
    r = M.score_point(raw, after, after)
    r.update({"label": label, "offcrown": offcrown, "point_id": "p"})
    return r


def test_summarise_excludes_offcrown_and_counts_it(M):
    rows = [
        _row(M, "nochange", [1, 0, 1], [1, 1, 1]),
        _row(M, "nochange", [1, 0, 1], [1, 0, 1]),
        _row(M, "nochange", [1, 0, 1], [1, 1, 1], offcrown=1),
        _row(M, "loss", [1, 1, 0], [1, 1, 1]),
    ]
    by, off = M.summarise(rows)
    assert off == 1
    assert by["nochange"]["n"] == 2, "the off-crown point must not enter a label trailer"
    assert by["nochange"]["triples_raw"] == 2
    assert by["nochange"]["triples_fixed"] == 1
    assert by["loss"]["laundered"] == 1
    assert by["loss"]["laundered_points"] == 1
    assert by["loss"]["has_terminal_absence"] == 1


def test_offcrown_triples_are_reported_for_the_yaml_denominator(M):
    rows = [
        _row(M, "nochange", [1, 0, 1], [1, 1, 1], offcrown=1),
        _row(M, "nochange", [1, 0, 1, 0, 1], [1, 1, 1, 1, 1], offcrown=1),
        _row(M, "nochange", [1, 0, 1], [1, 1, 1]),
    ]
    t = M.offcrown_triples(rows)
    assert t["nochange"] == 3, ("off-crown raw triples must be counted so K2 can be read "
                                "on the full 1,170-point denominator")


def test_trailer_keys_match_heal_vs_gold(M):
    """The two files are read side by side; the key names must line up."""
    rows = [_row(M, "nochange", [1, 0, 1], [1, 1, 1]),
            _row(M, "loss", [1, 1, 0], [1, 1, 0])]
    by, _ = M.summarise(rows)
    for k in ("triples_raw", "triples_healed", "triples_fixed", "laundered",
              "term_censored", "n", "touched", "to_canopy", "to_ignore",
              "has_terminal_absence"):
        assert k in by["nochange"] or k in by["loss"], k


def test_trailer_reader(M, tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2\n# nochange_triples_fixed,240\n# off_grid,0\n",
                 encoding="utf-8")
    t = M._trailer(p)
    assert t["nochange_triples_fixed"] == "240"
    assert t["off_grid"] == "0"


def test_raw_triple_reconciliation_target_is_the_healer_file(M):
    """The expected counts are not invented here — they are the heal_vs_gold_12ep.csv
    trailer, and the scorer refuses to report anything if the raws disagree."""
    t = M._trailer(M.HEALER)
    if not t:
        pytest.skip("heal_vs_gold_12ep.csv not present")
    assert M.RAW_TRIPLES_EXPECTED["nochange"] == int(t["nochange_triples_raw"])
    assert M.RAW_TRIPLES_EXPECTED["loss"] == int(t["loss_triples_raw"])
    assert M.RAW_TRIPLES_EXPECTED["gain"] == int(t["gain_triples_raw"])

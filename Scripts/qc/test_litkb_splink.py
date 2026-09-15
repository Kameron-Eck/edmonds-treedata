"""Tests for the Splink candidate-scoring evaluation's comparison configuration and gold.

No network, no database, no Splink required to run the normalisation and gold tests --
the Splink-dependent tests skip unless the dedicated venv is the interpreter
(D:\\edmonds-pipeline\\venv-splink, requirements-litkb-link.txt), because splink is not a
pipeline dependency and must not become one by way of the test suite.

What is guarded here is the part that decides outcomes: the field normalisation the
comparisons see, and the fact that the review/edition/mutation gold rows still point at the
references they were frozen against.
"""
import json
from pathlib import Path

import pytest

INSTR = Path(__file__).resolve().parent / "instruments" / "litkb_splink_eval.py"
GOLD = Path(__file__).resolve().parents[2] / "Reports" / "litkb_splink_gold_2026-09-15.json"


def _mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("litkb_splink_eval", INSTR)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


m = _mod()


# ----------------------------------------------------------------- normalisation
@pytest.mark.parametrize("raw,want", [
    ("https://doi.org/10.1234/ABC", "10.1234/abc"),
    ("DOI:10.1234/abc", "10.1234/abc"),
    ("  10.1234/AbC ", "10.1234/abc"),
    ("", ""),
    (None, ""),
])
def test_norm_doi(raw, want):
    assert m.norm_doi(raw) == want


def test_norm_title_strips_markup_and_punctuation():
    assert m.norm_title("<i>BlockCV</i>: an R package, for k-fold CV!") == \
        "blockcv an r package for k fold cv"


def test_title_key_is_order_independent():
    """The blocking key must not depend on word order, or a reference whose parser reordered
    the title would never be compared against its own record."""
    a = m.title_key("Modelling error in overlaid categorical maps")
    b = m.title_key("Overlaid categorical maps: modelling error")
    assert a == b and a


def test_title_key_drops_stopwords_and_short_tokens():
    assert "the" not in m.title_key("The accuracy of the spatial databases").split()


@pytest.mark.parametrize("raw,want", [("2016", 2016), ("2019a", 2019), ("", None),
                                      ("n.d.", None), (1978, 1978)])
def test_as_year(raw, want):
    """'2019a' is the tracker's same-year suffix, the exact cell that killed the P3 load."""
    assert m.as_year(raw) == want


def test_pages_first_takes_the_start_page():
    assert m.pages_first("122-143") == "122"
    assert m.pages_first("") is None


# ----------------------------------------------------------------- the frozen gold
@pytest.fixture(scope="module")
def gold():
    if not GOLD.exists():
        pytest.skip("gold not built")
    return json.loads(GOLD.read_text(encoding="utf-8"))


def test_gold_counts_are_the_frozen_ones(gold):
    """The evaluation's headline numbers are ratios over these. If one moves, every number in
    Reports/LITKB_SPLINK_2026-09-15.md is stale and must be re-derived, not patched."""
    assert gold["counts"] == {
        "references_total": 658, "positives": 365, "must_not_link": 77,
        "near_positive_mutations": 20, "lost_genuine": 5, "duplicate_pairs": 4,
        "admitted_works": 348,
    }


def test_gold_positives_all_carry_a_normalised_doi(gold):
    for p in gold["positives"]:
        assert p["gold_doi"] == m.norm_doi(p["gold_doi"]) and p["gold_doi"]


def test_must_not_link_never_overlaps_a_positive(gold):
    """A row that is both a positive and a must-not-link would make the evaluation
    unfalsifiable: every threshold would be wrong for one of the two."""
    pos = {(p["ref_id"], p["gold_doi"]) for p in gold["positives"]}
    bad = {(g["ref_id"], g["bad_doi"]) for g in gold["must_not_link"]}
    assert not (pos & bad)


def test_the_five_lost_genuine_are_not_in_the_positives(gold):
    """Task C only means anything if the resolver really refused these five."""
    pos = {p["ref_id"] for p in gold["positives"]}
    assert not ({g["ref_id"] for g in gold["lost_genuine"]} & pos)


def test_303_60_is_gold_as_related_not_duplicate(gold):
    pair = [p for p in gold["duplicate_pairs"] if p["left_id"] == "303" and p["right_id"] == "60"]
    assert len(pair) == 1
    assert pair[0]["verdict"] == "related_not_duplicate"


def test_mutation_kills_and_near_positives_are_disjoint(gold):
    kills = {g["ref_id"] for g in gold["must_not_link"] if g["kind"].startswith("mutation_")}
    near = {g["ref_id"] for g in gold["near_positive_mutations"]}
    assert len(kills) == 70 and len(near) == 20 and not (kills & near)


# ----------------------------------------------------------------- comparison config
def _have_splink():
    import importlib.util
    return importlib.util.find_spec("splink") is not None


splink_only = pytest.mark.skipif(
    not _have_splink(),
    reason="splink installed only in D:\\edmonds-pipeline\\venv-splink")


@splink_only
def test_year_comparison_has_the_levels_the_rule_uses():
    """decisions.yaml 15.15 turns on +/-1, and the P6 kills mutate by exactly 3. Both
    distances must be their OWN level or neither can be scored."""
    c = m.year_comparison().get_comparison("duckdb")
    labels = [lv.label_for_charts for lv in c.comparison_levels]
    assert any("<= 1" in x for x in labels)
    assert any("<= 3" in x for x in labels)
    assert sum("Exact" in x for x in labels) == 1


@splink_only
def test_settings_drops_the_comparison_the_ablation_names():
    def cols(**kw):
        s = m.settings("link_only", **kw).get_settings("duckdb")
        return {c.output_column_name for c in s.comparisons}

    full = cols()
    assert "first_author" in full and "journal" in full
    assert "first_author" not in cols(with_author=False)
    assert "journal" not in cols(with_journal=False)
    assert "first_author" not in cols(with_author=False, with_journal=False)
    assert "journal" not in cols(with_author=False, with_journal=False)


@splink_only
def test_blocking_off_really_is_the_cartesian_product():
    """The no-blocking kill is worthless if turning blocking off leaves a rule in place."""
    s = m.settings("link_only", blocking=False).get_settings("duckdb")
    sql = " ".join(r.blocking_rule_sql for r in s._blocking_rules_to_generate_predictions)
    assert "1=1" in sql.replace(" ", "")

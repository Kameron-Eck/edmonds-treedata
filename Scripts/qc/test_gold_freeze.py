"""Gates for the frozen Panel A gold set.

The gold had three counts (1155 / 1169 / 1170) because no script pinned the dedup. Now
one does, and these gates keep it pinned: the counts are frozen constants, and the
freezer's resolution must stay identical to the estimator's, since the whole justification
for these semantics is that they are the ones that produced the -2.21 pp headline.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
GOLD = REPO / "phase4" / "qc" / "panel_a_gold.csv"

# FROZEN. Changing these is a scientific decision, not a maintenance edit: every
# downstream precision and recall number is scored against this population.
FROZEN = {"nochange": 1170, "loss": 42, "gain": 2}


def _rows(p):
    if not Path(p).exists():
        return []
    body = [ln for ln in Path(p).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def _gold():
    rows = _rows(GOLD)
    if not rows:
        pytest.skip("panel_a_gold.csv absent — run "
                    "qc/instruments/freeze_panel_a_gold.py")
    return rows


def test_counts_are_frozen():
    import collections
    got = collections.Counter(r["label"] for r in _gold())
    assert dict(got) == FROZEN, (
        f"gold counts moved: {dict(got)} vs frozen {FROZEN}. If the labels genuinely "
        f"changed this is a SCIENTIFIC decision — every downstream precision and recall "
        f"number is scored against this population.")


def test_point_ids_unique():
    seen = set()
    for r in _gold():
        assert r["point_id"] not in seen, f"duplicate gold point {r['point_id']}"
        seen.add(r["point_id"])


def test_only_live_change_labels():
    for r in _gold():
        assert r["label"] in FROZEN, f"{r['point_id']}: label {r['label']!r} not a gold class"


def test_freezer_matches_the_estimator():
    """The semantics must stay the estimator's, or the gold and the headline diverge.

    This re-resolves through the freezer, which imports `_load_labels` from
    panel_a_paired_change directly — so a change to the estimator's dedup rule shows up
    here as a count mismatch rather than as a silent disagreement with the -2.21 pp
    estimate every downstream number leans on.
    """
    sys.path.insert(0, str(SCRIPTS / "qc" / "instruments"))  # ledger: test_status_discovery
    import collections

    from freeze_panel_a_gold import resolve
    gold, _ = resolve()
    assert dict(collections.Counter(r["label"] for r in gold)) == FROZEN
    assert len(gold) == sum(FROZEN.values())


def test_the_1169_discrepancy_is_recorded_not_silently_resolved():
    """The design doc asserts 1169 no-change; the estimator yields 1170.

    Freezing a number that contradicts the written record is only honest if the
    contradiction is stated where a reader will meet it. This pins that it is.
    """
    src = (SCRIPTS / "qc" / "instruments" / "freeze_panel_a_gold.py").read_text(
        encoding="utf-8")
    assert "1169" in src, (
        "the freezer no longer names the 1169 it contradicts — a frozen constant that "
        "silently overrides the written record is how the next three-way count starts")

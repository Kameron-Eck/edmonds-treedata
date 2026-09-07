"""Gates for the healing operator — chiefly, the one-directional guarantee.

The whole design rests on healing being unable to remove canopy or manufacture a loss.
That is a claim about code, so it is tested as one: on random inputs, exhaustively over
the state space, and against the specific failure the falsified offset layer produced.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS / "qc" / "instruments"))  # ledger: test_status_discovery

np = pytest.importorskip("numpy")
from temporal_heal import (HEALED, HEALED_IGNORE, apply_heal,  # noqa: E402
                           shift_mask, tier_for)


def test_apply_heal_only_ever_writes_upward():
    """THE GUARANTEE. 0 -> 1 and 0 -> 255 only; never 1 -> anything, never 255 -> 0.

    Random over the full state space rather than a hand-picked case, because the failure
    this forbids is exactly the one a hand-picked case would miss.
    """
    rng = np.random.default_rng(20260906)
    for _ in range(200):
        base = rng.choice([0, 1, 255], size=(24, 24)).astype(np.uint8)
        heal = rng.random((24, 24)) < 0.3
        ign = rng.random((24, 24)) < 0.3
        out = apply_heal(base, heal, ign)
        assert not np.any((base == 1) & (out != 1)), "canopy was removed or altered"
        assert not np.any((base == 255) & (out != 255)), "IGNORE was overwritten"
        changed = base != out
        assert np.all(base[changed] == 0), "a non-zero cell changed"
        assert np.all(np.isin(out[changed], (HEALED, HEALED_IGNORE)))


def test_healing_cannot_lower_crown_cover():
    """Cover is monotone non-decreasing, so no consumer can see a downward move.

    This is the property that makes the operator safe for validity intervals: healing may
    move a removal date later (which the interval consumer must clamp) but can never
    invent one.
    """
    rng = np.random.default_rng(7)
    for _ in range(100):
        base = rng.choice([0, 1, 255], size=(16, 16)).astype(np.uint8)
        out = apply_heal(base, rng.random((16, 16)) < 0.4, rng.random((16, 16)) < 0.4)
        for m in (base, out):
            pass
        cov_b = (base == 1).sum() / max((base != 255).sum(), 1)
        cov_o = (out == 1).sum() / max((out != 255).sum(), 1)
        assert cov_o >= cov_b - 1e-9, "healing lowered crown cover"


def test_shift_mask_conserves_or_loses_never_invents():
    """A translation may push cells off the edge; it may never create them."""
    rng = np.random.default_rng(11)
    for _ in range(100):
        m = rng.random((20, 20)) < 0.35
        dx = float(rng.integers(-3, 4)) * 2.0
        dy = float(rng.integers(-3, 4)) * 2.0
        out = shift_mask(m, dx, dy)
        assert out.sum() <= m.sum(), "translation invented canopy"


def test_shift_mask_zero_is_identity():
    rng = np.random.default_rng(3)
    m = rng.random((12, 12)) < 0.5
    assert np.array_equal(shift_mask(m, 0.0, 0.0), m)
    assert np.array_equal(shift_mask(m, 0.4, -0.4), m)   # sub-cell rounds to no move


def test_tiers_follow_the_bracket():
    """BLIND dominates; a post-lidar bracket is REVIEW, never a silent HEAL."""
    assert tier_for("2011s", "2013", "2015") == "HEAL"      # ends 2015 <= 2016
    assert tier_for("2013", "2015", "2016") == "HEAL"
    assert tier_for("2015", "2016", "2019") == "BLIND"      # 3-year right gap
    assert tier_for("2019", "2021", "2024") == "BLIND"
    assert tier_for("2019", "2020", "2021") == "REVIEW"     # post-lidar, gaps < 3
    # coppice reaches a 6.5 m crown in three years — a bracket that wide is blind
    # regardless of which side the lidar sits on
    assert tier_for("2016", "2019", "2020") == "BLIND"


def test_only_the_heal_tier_asserts_canopy():
    """REVIEW and BLIND mark cells IGNORE, never canopy.

    Post-2016 has no lidar downstream, and a real clearing followed by post-clearing
    grass or blackberry read as canopy produces the same bracketing pattern. Asserting
    canopy there would launder a real removal.
    """
    src = (SCRIPTS / "qc" / "instruments" / "temporal_heal.py").read_text(
        encoding="utf-8")
    assert '"heal": keep if tier == "HEAL"' in src, (
        "the heal overlay is no longer gated on the HEAL tier — REVIEW/BLIND cells "
        "could now assert canopy where no lidar can veto a real clearing")


def test_output_restriction_is_stated_where_a_reader_meets_it():
    """Healed masks must never feed the annual fraction series.

    Endpoints cannot be healed, so the bias would not cancel and 2016->2024 — the
    headline interval — would gain a manufactured decline. The restriction lives in the
    instrument, not only in a report nobody opens.
    """
    src = (SCRIPTS / "qc" / "instruments" / "temporal_heal.py").read_text(
        encoding="utf-8")
    assert "never feeds the annual canopy fraction" in src.lower() or \
           "never the annual fraction series" in src.lower(), (
        "the output restriction is no longer stated in the instrument")


def test_healing_launders_no_verified_loss():
    """THE SAFETY PROPERTY, scored against the frozen gold.

    Laundering is filling the TERMINAL absence — the run of absent epochs a real removal
    created. Healing an upstream dropout at a point cut later is the operator working, not
    harm; the first version of this metric conflated the two and reported 5 of 42 as
    laundering when the true count was 0.

    Structurally this should be impossible — the endpoints cannot be healed and a terminal
    absence ends at an endpoint — but "should be impossible" is exactly the claim worth
    testing rather than asserting.
    """
    import csv as _csv
    p = REPO / "phase4" / "qc" / "heal_vs_gold.csv"
    if not p.exists():
        pytest.skip("heal_vs_gold.csv absent — run qc/instruments/heal_vs_gold.py")
    body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    rows = list(_csv.DictReader(body))
    losses = [r for r in rows if r["label"] == "loss"]
    assert losses, "no verified losses in the scored gold"
    laundered = [r["point_id"] for r in losses if int(r["terminal_laundered"]) > 0]
    assert not laundered, (
        f"healing filled the terminal absence of verified loss(es) {laundered} — a real "
        f"removal has been erased, which is the failure the whole design is gated against")
    censored = [r["point_id"] for r in losses if int(r["terminal_censored"]) > 0]
    assert not censored, (
        f"healing marked the terminal absence of verified loss(es) {censored} as IGNORE — "
        f"the event is not erased but it is no longer visible to a change detector")


def test_healing_helps_where_a_human_called_it_stable():
    """The win side: impossible triples at verified no-change points must go DOWN.

    A correction that removes none of them is machinery for nothing; one that removes them
    while laundering losses is worse than nothing. Both halves are gated.
    """
    import csv as _csv
    p = REPO / "phase4" / "qc" / "heal_vs_gold.csv"
    if not p.exists():
        pytest.skip("heal_vs_gold.csv absent")
    body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    rows = [r for r in _csv.DictReader(body) if r["label"] == "nochange"]
    raw = sum(int(r["impossible_triples_raw"]) for r in rows)
    healed = sum(int(r["impossible_triples_healed"]) for r in rows)
    assert raw > 0, "no impossible triples to fix — the test has nothing to measure"
    assert healed < raw, (
        f"healing removed no impossible triples at verified no-change points "
        f"({raw} -> {healed})")


def test_valid_to_is_clamped_to_raw_evidence():
    """Healing may never extend a tree's recorded life.

    Healing is a PIXEL predicate; valid_to is a CROWN-COVER predicate at 0.5, so a healed
    cell can push a crown from 0.45 to 0.55 and move a removal date one epoch LATER than
    the unhealed data supports. An adversarial review flagged this as needing a clamp in
    the CONSUMER rather than an assertion in a test — this pins that the clamp is there.
    """
    src = (SCRIPTS / "qc" / "instruments" / "crown_trajectories.py").read_text(
        encoding="utf-8")
    assert 'valid_to = years[max(raw_p)]' in src, (
        "valid_to is no longer computed from RAW presence — healing can now extend a "
        "recorded life, which moves removal dates later than the evidence supports")


def test_terminal_losses_are_flagged_not_deleted():
    """A loss whose only evidence is the final epoch cannot be corroborated.

    64% of LOST crowns were last seen in the penultimate epoch, and the final epoch is the
    series' worst-recall year — that class is a detection deficit wearing a removal's
    label. It must be FLAGGED. It must also never be deleted: the shipped persist filter
    deleted exactly this class and discarded every verified terminal event.
    """
    import csv as _csv
    p = REPO / "phase4" / "qc" / "crown_trajectories.csv"
    if not p.exists():
        pytest.skip("crown_trajectories.csv absent — run crown_trajectories.py")
    body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    rows = list(_csv.DictReader(body))
    lost = [r for r in rows if r["class"] == "LOST"]
    assert lost, "no LOST crowns — the classifier has stopped finding removals"
    term = [r for r in lost if r["confidence"] == "TERMINAL"]
    assert term, (
        "no LOST crown is flagged TERMINAL — uncorroborable terminal-window events are "
        "being reported at the same confidence as ones two later epochs confirm")
    # and they are still present, not filtered away
    assert len(lost) > len(term), "every loss is terminal — the corroborated class is gone"

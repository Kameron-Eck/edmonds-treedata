"""Gates for claims.yaml — every load-bearing number still matches its evidence.

This is the check the findings ledger never had. When the 2026-09-06 recalibration
superseded the era F-numbers, nothing noticed for three days; a drifted claim now
fails the suite the moment the evidence moves.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS / "qc"))     # ledger: test_status_discovery.py
import claims as _claims                     # noqa: E402


def _load():
    cs = _claims.load()
    if not cs:
        pytest.skip("claims.yaml absent or empty")
    return cs


def test_ids_unique_and_fields_present():
    seen = set()
    for c in _load():
        for f in ("id", "statement", "value", "evidence"):
            assert str(c.get(f, "")).strip(), f"{c.get('id')}: missing {f}"
        assert c["id"] not in seen, f"duplicate claim id {c['id']!r}"
        seen.add(c["id"])


def test_every_claim_still_matches_its_evidence():
    """The whole point: a number that moved must not keep being asserted."""
    drifted = []
    for c in _load():
        state, detail = _claims.verify(c)
        assert state != "error", f"{c['id']}: {detail}"
        if state == "drifted":
            drifted.append(f"{c['id']}: {detail} — restated in "
                           f"{', '.join(c.get('stated_in') or []) or '(nowhere)'}")
    assert not drifted, "claims no longer match their evidence:\n  " + \
        "\n  ".join(drifted)


def test_stated_in_files_exist():
    """`stated_in` is the fix-list when a claim drifts — a dead path makes it useless."""
    for c in _load():
        for where in (c.get("stated_in") or []):
            assert (REPO / where).exists() or (SCRIPTS / where).exists(), (
                f"{c['id']}: stated_in {where} does not exist")


def test_entries_named_by_claims_exist():
    import yaml
    for c in _load():
        name = c.get("entry")
        if not name:
            continue
        assert (SCRIPTS / "experiments" / f"{name}.yaml").exists(), (
            f"{c['id']}: entry {name!r} is not in the registry")
        spec = yaml.safe_load(
            (SCRIPTS / "experiments" / f"{name}.yaml").read_text(encoding="utf-8"))
        assert spec.get("name") == name, f"{c['id']}: entry name mismatch"

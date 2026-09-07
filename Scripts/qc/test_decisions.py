"""Gates for decisions.yaml — the open-decision registry.

The board used to carry these as prose bullets, where a broken dependency or a
decision recorded without its decision text was invisible. These checks make the
stack's structure real: ids resolve, the dependency graph is acyclic, a decided entry
actually says what was decided, and every pointer a decider is sent to exists.

Repo-only by construction.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
DECISIONS = SCRIPTS / "decisions.yaml"

STATUSES = {"open", "decided", "superseded", "dropped"}
OWNERS = {"kam", "claude", "either"}
# Same rule as the experiment registry: lake mounts and globs are legitimate
# provenance but cannot be existence-checked from a checkout.
_UNCHECKABLE = ("G:", "/content/", "D:", "http", "~")


def _load():
    if not DECISIONS.exists():
        pytest.skip("decisions.yaml absent")
    spec = yaml.safe_load(DECISIONS.read_text(encoding="utf-8")) or {}
    return spec.get("decisions", [])


def test_ids_are_unique_and_well_formed():
    seen = set()
    for d in _load():
        i = d.get("id", "")
        assert i and i == i.lower() and " " not in i, f"bad id {i!r}"
        assert i not in seen, f"duplicate decision id {i!r}"
        seen.add(i)


def test_required_fields():
    for d in _load():
        for f in ("id", "question", "owner", "status", "why"):
            assert str(d.get(f, "")).strip(), f"{d.get('id')}: missing {f}"
        assert d["status"] in STATUSES, f"{d['id']}: bad status {d['status']!r}"
        assert d["owner"] in OWNERS, f"{d['id']}: bad owner {d['owner']!r}"


def test_decided_entries_say_what_was_decided():
    """A status of `decided` with no decision text is worse than leaving it open —
    it reads as settled while recording nothing that can be acted on or cited."""
    for d in _load():
        if d["status"] == "decided":
            assert str(d.get("decision", "")).strip(), (
                f"{d['id']}: decided but no `decision` text")
            assert str(d.get("decided", "")).strip(), (
                f"{d['id']}: decided but no `decided` date")
        else:
            assert not d.get("decision"), (
                f"{d['id']}: carries a decision but status is {d['status']}")


def test_links_resolve():
    ids = {d["id"] for d in _load()}
    for d in _load():
        for field in ("blocks", "blocked_by"):
            for ref in (d.get(field) or []):
                assert ref in ids, f"{d['id']}.{field} names unknown decision {ref!r}"


def test_dependency_graph_is_acyclic():
    """A cycle would mean nothing can ever start — and prose cannot show you one."""
    graph = {d["id"]: list(d.get("blocked_by") or []) for d in _load()}
    state = {}

    def visit(node, trail):
        if state.get(node) == "done":
            return
        assert state.get(node) != "visiting", (
            f"dependency cycle: {' -> '.join(trail + [node])}")
        state[node] = "visiting"
        for parent in graph.get(node, []):
            visit(parent, trail + [node])
        state[node] = "done"

    for node in graph:
        visit(node, [])


def test_blocks_and_blocked_by_agree():
    """If A blocks B, B must be blocked_by A — a one-sided edge hides a dependency."""
    ds = _load()
    blocks = {d["id"]: set(d.get("blocks") or []) for d in ds}
    blocked = {d["id"]: set(d.get("blocked_by") or []) for d in ds}
    for a, targets in blocks.items():
        for b in targets:
            assert a in blocked.get(b, set()), (
                f"{a} claims to block {b}, but {b}.blocked_by omits {a}")
    for b, parents in blocked.items():
        for a in parents:
            assert b in blocks.get(a, set()), (
                f"{b} says it is blocked by {a}, but {a}.blocks omits {b}")


def test_evidence_pointers_exist():
    for d in _load():
        for p in (d.get("evidence") or []):
            if str(p).startswith(_UNCHECKABLE):
                continue
            assert (REPO / p).exists() or (SCRIPTS / p).exists(), (
                f"{d['id']}: evidence {p} does not exist")


def test_open_decisions_are_reachable_from_the_board():
    """WORKPLAN must POINT at this file rather than restating the stack.

    Two homes for the same decisions is how the board and the ledger drifted apart
    before; the board keeps intent, this file keeps the decisions.
    """
    board = (SCRIPTS / "WORKPLAN.md").read_text(encoding="utf-8")
    assert "decisions.yaml" in board, (
        "WORKPLAN.md no longer points at decisions.yaml — the decision stack has "
        "two homes again")

"""experiments/*.yaml — the schema gate.

An experiment file is the agent-facing contract (experiments/README.md). This gate
keeps the contract honest with repo-only checks: parseable, schema-complete, verdict
discipline (a decided experiment says so; an undecided one does not pretend), tags
owned by exactly one experiment, and a COMPLETE experiment's tags actually present in
run_registry.csv — a "complete" experiment whose runs left no provenance is fiction.
"""
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
EXP_DIR = SCRIPTS / "experiments"
STATUSES = {"queued", "live", "complete", "tabled"}
REQUIRED = {"name", "status", "hypothesis", "arms", "baseline", "metric",
            "decision_rule", "verdict", "decided"}


def _specs():
    return sorted(p for p in EXP_DIR.glob("*.yaml"))


def test_experiments_exist():
    assert _specs(), "experiments/ holds no experiment files"


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_schema(path):
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = REQUIRED - set(spec)
    assert not missing, f"{path.name}: missing keys {sorted(missing)}"
    assert spec["name"] == path.stem, f"{path.name}: name != filename stem"
    assert spec["status"] in STATUSES, f"{path.name}: status {spec['status']!r}"
    assert spec["arms"], f"{path.name}: no arms"
    for a in spec["arms"]:
        assert str(a.get("year")) and str(a.get("tag")), f"{path.name}: arm {a}"
    assert str(spec["decision_rule"]).strip(), (
        f"{path.name}: decision_rule is empty — it must be written BEFORE results")


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_verdict_discipline(path):
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    decided = spec["status"] in ("complete", "tabled")
    if decided:
        assert spec["verdict"] and spec["decided"], (
            f"{path.name}: status {spec['status']} but verdict/decided missing")
    else:
        assert not spec["verdict"] and not spec["decided"], (
            f"{path.name}: carries a verdict while status says {spec['status']} — "
            f"either flip the status or remove the verdict")


def test_every_tag_is_owned_by_one_experiment():
    owner = {}
    for p in _specs():
        for a in yaml.safe_load(p.read_text(encoding="utf-8"))["arms"]:
            tag = str(a["tag"])
            assert tag not in owner, f"tag {tag!r} owned by {owner[tag]} AND {p.name}"
            owner[tag] = p.name


def test_complete_experiments_have_registry_provenance():
    reg = (SCRIPTS / "run_registry.csv").read_text(encoding="utf-8")
    for p in _specs():
        spec = yaml.safe_load(p.read_text(encoding="utf-8"))
        if spec["status"] != "complete":
            continue
        for a in spec["arms"]:
            assert str(a["tag"]) in reg, (
                f"{p.name}: complete, but tag {a['tag']!r} never appears in "
                f"run_registry.csv — a finished experiment leaves provenance")


def test_generated_queues_match_their_experiments():
    """One source of truth: every pipeline/queue_*.yaml carrying the GENERATED header
    must equal an in-memory regeneration from its experiment file. Edit the
    experiment, rerun qc/experiment_queue.py — never the queue file."""
    import re
    from experiment_queue import MARK, generate
    checked = 0
    for q in (SCRIPTS / "pipeline").glob("queue_*.yaml"):
        head = q.read_text(encoding="utf-8")
        if not head.startswith(MARK):
            continue
        m = re.search(r"experiments/(\S+\.yaml)", head)
        assert m, f"{q.name}: GENERATED header names no experiment file"
        text, _ = generate(EXP_DIR / m.group(1))
        assert head == text, (
            f"{q.name} drifted from its experiment — regenerate: "
            f"py -3.12 qc/experiment_queue.py --experiment experiments/{m.group(1)}")
        checked += 1
    # zero generated files is legal (none launched yet); drift is not


def test_generator_refuses_decided_experiments():
    import pytest as _pt
    from experiment_queue import generate
    with _pt.raises(SystemExit, match="complete"):
        generate(EXP_DIR / "pilot_2019.yaml")


def test_generator_jobs_carry_the_queue_contract():
    """id/year/tag/extra are what phase4_train_queue._load_queue consumes; the
    generated shape must keep matching the hand-written pilot shape."""
    from experiment_queue import generate
    text, spec = generate(EXP_DIR / "resolution_1x2x4.yaml")
    jobs = yaml.safe_load(text)
    assert len(jobs) == len(spec["arms"])
    for j in jobs:
        assert set(j) >= {"id", "year", "tag", "extra", "why"}
        assert j["id"].startswith(spec["name"] + "_")

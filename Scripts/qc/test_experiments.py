"""experiments/*.yaml — the schema gate.

An entry file is the agent-facing contract (experiments/README.md). This gate keeps
the contract honest with repo-only checks: parseable, schema-complete, verdict
discipline (a decided entry says so; an undecided one does not pretend), tags owned by
exactly one entry, and a COMPLETE experiment's tags actually present in
run_registry.csv — a "complete" experiment whose runs left no provenance is fiction.

EXTENDED 2026-09-06, when the directory stopped being nine live experiments and became
the registry of everything the project has ever run. Three things had to change and
each one is a gate, not a convention:

  kind          Panel A, the coregistration sweep and the literature hunt have no
                (year, tag) arms. Forcing an arms table on them would have meant
                INVENTING arms. `kind` splits the shapes; `arms` is required non-empty
                only for `kind: experiment`.
  retrospective A backfilled entry's decision_rule is reconstructed from a verdict that
                already existed. Writing it unflagged fabricates pre-registration —
                the exact property this directory exists to guarantee. So: verdict
                dated before the file was first committed => the flag is REQUIRED.
  n / n_source  Sample size is the one number the authored layer may restate, and only
                because it is PINNED — the gate resolves n_source and fails on
                disagreement. Everything else stays a pointer; the generated index
                (qc/experiments_index.py) is where values get resolved.

Repo-only by construction: every check reads tracked files, so CI passes with no lake
mounted. Lake paths in provenance fields are legitimate and deliberately unchecked.
"""
import csv
import json
import subprocess
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
EXP_DIR = SCRIPTS / "experiments"
STATUSES = {"queued", "live", "complete", "tabled", "needs-kam"}
KINDS = {"experiment", "measurement-campaign", "instrument-finding"}
UNDECIDED = {"queued", "live", "needs-kam"}
REQUIRED = {"name", "status", "hypothesis", "arms", "baseline", "metric",
            "decision_rule", "verdict", "decided"}
# Provenance fields holding repo-relative paths that must resolve.
PATH_FIELDS = ("design_doc", "reports", "instruments", "inputs", "outputs")
# Prefixes that mark a path as NOT repo-relative: the data lake (both mounts) and
# glob patterns. Legitimate provenance, unverifiable from a checkout.
_UNCHECKABLE = ("G:", "/content/", "D:", "http", "~")


def _specs():
    return sorted(p for p in EXP_DIR.glob("*.yaml"))


def _load(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def kind_of(spec):
    """Absent `kind` means `experiment` — the nine pre-extension files stay valid."""
    return spec.get("kind", "experiment")


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


# ---------------------------------------------------------------- n / n_source

def resolve_n(source, root=REPO):
    """Resolve an `n_source` pointer to an integer. Grammar in experiments/README.md.

    Returns None when the pointer cannot be resolved from a checkout (missing file,
    lake path) — the caller decides whether that is a failure. Raises ValueError on a
    malformed pointer, which IS always a failure.
    """
    if "#" not in str(source):
        raise ValueError(f"n_source {source!r} has no '#<selector>'")
    rel, sel = str(source).rsplit("#", 1)
    if rel.startswith(_UNCHECKABLE):
        return None
    p = root / rel
    if not p.exists():
        p = SCRIPTS / rel                       # bare names resolve under Scripts/
    if not p.exists():
        return None
    if sel == "lines":
        return sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
                   if ln.strip() and not ln.lstrip().startswith("#"))
    if sel.startswith("json:"):
        val = json.loads(p.read_text(encoding="utf-8"))[sel[5:]]
        return int(val)
    if sel == "rows" or sel.startswith("rows:"):
        # `#` comment lines are stripped before the header is read — champion_arms.csv
        # style banners would otherwise be parsed as data.
        body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")]
        rows = list(csv.DictReader(body))
        if sel == "rows":
            return len(rows)
        col, _, want = sel[5:].partition("=")
        return sum(1 for r in rows if str(r.get(col, "")).strip() == want)
    raise ValueError(f"n_source {source!r}: unknown selector {sel!r}")


# ---------------------------------------------------------------- core schema

def test_experiments_exist():
    assert _specs(), "experiments/ holds no entry files"


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_schema(path):
    spec = _load(path)
    missing = REQUIRED - set(spec)
    assert not missing, f"{path.name}: missing keys {sorted(missing)}"
    assert spec["name"] == path.stem, f"{path.name}: name != filename stem"
    assert spec["status"] in STATUSES, f"{path.name}: status {spec['status']!r}"
    kind = kind_of(spec)
    assert kind in KINDS, f"{path.name}: kind {kind!r} not in {sorted(KINDS)}"
    assert isinstance(spec["arms"], list), (
        f"{path.name}: arms must be a list ([] for an arms-less entry, never null — "
        f"pilot_gate.load_arms iterates it)")
    if kind == "experiment":
        assert spec["arms"], (
            f"{path.name}: kind experiment with no arms. An entry with nothing to run "
            f"is a measurement-campaign or an instrument-finding (README: kind)")
    for a in spec["arms"]:
        assert str(a.get("year")) and str(a.get("tag")), f"{path.name}: arm {a}"
    assert str(spec["decision_rule"]).strip(), (
        f"{path.name}: decision_rule is empty — it must be written BEFORE results")


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_verdict_discipline(path):
    spec = _load(path)
    if spec["status"] in UNDECIDED:
        assert not spec["verdict"] and not spec["decided"], (
            f"{path.name}: carries a verdict while status says {spec['status']} — "
            f"either flip the status or remove the verdict")
    else:
        assert spec["verdict"] and spec["decided"], (
            f"{path.name}: status {spec['status']} but verdict/decided missing")


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_only_experiments_carry_launch_machinery(path):
    """launch_defaults / steps drive experiment_queue. On a campaign they would
    generate a queue for work that has no arms to run."""
    spec = _load(path)
    if kind_of(spec) == "experiment":
        return
    for f in ("launch_defaults", "steps"):
        assert not spec.get(f), (
            f"{path.name}: kind {kind_of(spec)} carries {f!r} — launch machinery "
            f"belongs to kind: experiment only")


def test_every_tag_is_owned_by_one_experiment():
    owner = {}
    for p in _specs():
        for a in _load(p)["arms"]:
            tag = str(a["tag"])
            assert tag not in owner, f"tag {tag!r} owned by {owner[tag]} AND {p.name}"
            owner[tag] = p.name


def test_complete_experiments_have_registry_provenance():
    reg = (SCRIPTS / "run_registry.csv").read_text(encoding="utf-8")
    for p in _specs():
        spec = _load(p)
        if spec["status"] != "complete" or kind_of(spec) != "experiment":
            continue
        for a in spec["arms"]:
            assert str(a["tag"]) in reg, (
                f"{p.name}: complete, but tag {a['tag']!r} never appears in "
                f"run_registry.csv — a finished experiment leaves provenance")


# ------------------------------------------------------- retrospective honesty

def _first_commit_date(path):
    """Date the file was first ADDED, per git. None when git cannot answer."""
    try:
        r = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%as", "--", str(path)],
            cwd=str(REPO), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    dates = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    return min(dates) if dates else None       # oldest add wins (file may be re-added)


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_retrospective_entries_say_so(path):
    """A verdict older than the file that records it is a BACKFILL. Saying nothing
    would present a reconstructed decision_rule as pre-registration — the one property
    this directory promises. Silent when git cannot answer (shallow clone, export)."""
    spec = _load(path)
    decided, added = spec.get("decided"), _first_commit_date(path)
    if not decided or not added:
        return
    if str(decided) < added:
        assert spec.get("retrospective") is True, (
            f"{path.name}: decided {decided} but the file was first committed {added} "
            f"— that is a backfill. Set `retrospective: true`; without it the "
            f"reconstructed decision_rule reads as pre-registration.")


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_retrospective_is_a_bool(path):
    v = _load(path).get("retrospective")
    assert v is None or isinstance(v, bool), (
        f"{path.name}: retrospective must be true/false, got {v!r}")


# ------------------------------------------------------------ provenance gates

@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_pointer_paths_resolve(path):
    """Repo-relative pointers must exist. A registry of dead paths is worse than no
    registry — it reads as provenance and is not."""
    spec = _load(path)
    for field in PATH_FIELDS:
        for rel in _as_list(spec.get(field)):
            rel = str(rel)
            if rel.startswith(_UNCHECKABLE) or "*" in rel:
                continue                        # lake path / glob: not checkable here
            assert (REPO / rel).exists() or (SCRIPTS / rel).exists(), (
                f"{path.name}: {field} points at {rel!r}, which does not exist "
                f"(tried {REPO / rel} and {SCRIPTS / rel})")


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_supersession_links_resolve(path):
    """supersedes / superseded_by name entries, not files or prose."""
    names = {p.stem for p in _specs()}
    spec = _load(path)
    for field in ("supersedes", "superseded_by"):
        for other in _as_list(spec.get(field)):
            assert str(other) in names, (
                f"{path.name}: {field} names {other!r}, which is not an entry "
                f"(expected one of experiments/*.yaml stems)")
            assert str(other) != path.stem, f"{path.name}: {field} points at itself"


def test_supersession_is_symmetric():
    """If A supersedes B, B says superseded_by A. A one-sided link means a reader
    arriving at the stale entry is never told it is stale."""
    specs = {p.stem: _load(p) for p in _specs()}
    for name, spec in specs.items():
        for other in _as_list(spec.get("supersedes")):
            assert name in _as_list(specs[other].get("superseded_by")), (
                f"{name} supersedes {other}, but {other} does not list "
                f"superseded_by: [{name}] — the stale entry must say it is stale")
        for other in _as_list(spec.get("superseded_by")):
            assert name in _as_list(specs[other].get("supersedes")), (
                f"{name} says superseded_by {other}, but {other} does not list "
                f"supersedes: [{name}]")


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_imagery_labels_are_catalog_keys(path):
    from phase4seg.config import YEAR_CATALOG
    labels = {str(e["label"]) for e in YEAR_CATALOG}
    for lab in _as_list(_load(path).get("imagery")):
        assert str(lab) in labels, (
            f"{path.name}: imagery {lab!r} is not a config.YEAR_CATALOG label — "
            f"acquisitions are named by catalog key, never by calendar year alone")


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_run_ids_exist_in_the_registry(path):
    reg = {r["run_id"] for r in csv.DictReader(
        (SCRIPTS / "run_registry.csv").open(encoding="utf-8"))}
    for rid in _as_list(_load(path).get("run_ids")):
        assert str(rid) in reg, (
            f"{path.name}: run_id {rid!r} is not in run_registry.csv — registry rows "
            f"are DERIVED from manifests (qc/landed.py), never hand-typed")


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_n_is_pinned_to_its_source(path):
    """The one restated number in the authored layer, and the reason it is allowed."""
    spec = _load(path)
    n, src = spec.get("n"), spec.get("n_source")
    assert (n is None) == (src is None), (
        f"{path.name}: n and n_source are a pair — both or neither "
        f"(n={n!r}, n_source={src!r})")
    if n is None:
        return
    assert isinstance(n, int), f"{path.name}: n must be an int, got {n!r}"
    got = resolve_n(src)
    if got is None:
        return                                  # unresolvable from a checkout
    assert got == n, (
        f"{path.name}: n says {n} but {src} resolves to {got}. Fix the entry, or fix "
        f"the pointer — do not fix the number by hand.")


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_searchability_fields_are_well_formed(path):
    spec = _load(path)
    cat = spec.get("category")
    assert cat is None or (isinstance(cat, str) and cat and " " not in cat), (
        f"{path.name}: category must be a single word, got {cat!r}")
    tags = spec.get("tags")
    assert tags is None or (isinstance(tags, list)
                            and all(isinstance(t, str) and t for t in tags)), (
        f"{path.name}: tags must be a list of strings, got {tags!r}")


# ----------------------------------------------------------- generated layers

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


def test_generator_refuses_arms_less_kinds():
    """A campaign has nothing to launch. Before `kind` existed the generator only
    refused complete/tabled, so a queued campaign would have written an empty queue."""
    import pytest as _pt
    from experiment_queue import generate
    campaigns = [p for p in _specs() if kind_of(_load(p)) != "experiment"]
    if not campaigns:
        pytest.skip("no non-experiment entries yet")
    with _pt.raises(SystemExit, match="kind"):
        generate(campaigns[0])


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

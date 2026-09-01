"""CI gates (overhaul E03) — four cheap, data-plane-free invariants that a push must not break.

These run on GitHub Actions (ubuntu, no Drive, no GPU, no torch) and locally.
Everything resolves from __file__ — never from cwd.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_ci_gates.py -q
"""
import ast, csv, os, re, subprocess, sys
from datetime import datetime
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]          # …/treedata/Scripts


def _registry_columns():
    """The schema's ONE home is registry_from_manifests.COLUMNS — importing it
    means a future header migration updates generator and gate together (the
    E04 migration broke a hardcoded copy of this list within hours of it being
    written)."""
    from registry_from_manifests import COLUMNS
    return COLUMNS


_VERSION_OPS = "<>=~!"
_BOOTSTRAP_FILES = ["pipeline/phase4seg/common.py",
                    "pipeline/phase4seg/core.py",
                    "pipeline/frozen/phase3_semantic_dev.py"]


def _norm(name):
    """PEP 503 normalisation: lowercase, runs of -_. collapse to a single -."""
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _pkg_name(spec):
    return _norm(re.split(r"[<>=!~;\[\s]", spec, maxsplit=1)[0])


def _requirement_lines(path):
    """Stripped, non-comment, non-empty lines (the FROZEN LEGACY pins are comments — excluded)."""
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def _bootstrap_specs():
    """{filename: [[pip_spec, …] per _ensure_deps([...]) call site]} — parsed, never imported."""
    per_file = {}
    for rel in _BOOTSTRAP_FILES:
        path = SCRIPTS / rel
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        sites = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_ensure_deps" and node.args):
                continue
            arg = node.args[0]
            assert isinstance(arg, (ast.List, ast.Tuple)), \
                f"{rel}:{node.lineno}: _ensure_deps arg is not a literal list of pairs"
            specs = []
            for elt in arg.elts:
                assert isinstance(elt, ast.Tuple) and len(elt.elts) == 2, \
                    f"{rel}:{node.lineno}: expected (module_name, pip_spec) 2-tuples"
                specs.append(ast.literal_eval(elt.elts[1]))
            sites.append(specs)
        per_file[rel] = sites
    return per_file


def test_dag_validates():
    """Every stage script named in pipeline/dag.yaml exists in the repo."""
    sys.path.insert(0, str(SCRIPTS / "qc"))
    from pipeline_status import _read_dag, validate_dag
    assert validate_dag(_read_dag()) == []


def test_torch_stays_lazy():
    """Importing phase4seg.cli must not pull torch — the whole package stays importable
    (and preflight/QC stay runnable) on a machine with no torch installed.
    Subprocess so the assertion is order-independent under pytest."""
    code = ("import sys; sys.path.insert(0, 'pipeline'); import phase4seg.cli; "
            "assert 'torch' not in sys.modules, 'torch was imported at phase4seg.cli import time'")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(SCRIPTS),
                       env={**os.environ, "PYTHONUTF8": "1"},
                       capture_output=True, text=True)
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"


def test_bootstrap_consistency():
    """The in-script pip bootstraps must agree with requirements-colab.txt (the AUTHORITY):
    SUBSET of its names, and any versioned spec byte-identical to its line."""
    per_file = _bootstrap_specs()
    for rel, sites in per_file.items():
        assert sites, f"{rel}: no _ensure_deps([...]) call site parsed — did the bootstrap move?"

    specs = [s for sites in per_file.values() for site in sites for s in site]
    assert specs, "no pip specs parsed from any bootstrap"

    lines = _requirement_lines(SCRIPTS / "requirements-colab.txt")
    names = {_pkg_name(ln) for ln in lines}

    # (i) SUBSET only — requirements-colab.txt deliberately lists extras (timm, pandas,
    #     numpy) that no bootstrap carries, so set-equality would be wrong.
    missing = sorted({_pkg_name(s) for s in specs} - names)
    assert not missing, f"bootstrap packages absent from requirements-colab.txt: {missing}"

    # (ii) PIN MATCH — a versioned bootstrap spec must appear verbatim as a requirement line.
    pinned = {s for s in specs if any(c in s for c in _VERSION_OPS)}
    drifted = sorted(pinned - set(lines))
    assert not drifted, \
        f"pinned bootstrap specs not byte-identical in requirements-colab.txt: {drifted}"


def test_registry_schema():
    """run_registry.csv stays machine-readable: header == the generator's COLUMNS
    (one home), unique non-empty run_id, ISO date.
    No run_id format check — the legacy rows predate any convention."""
    cols = _registry_columns()
    with open(SCRIPTS / "run_registry.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows, "run_registry.csv is empty"
    assert rows[0] == cols, f"header drift: {rows[0]} != generator COLUMNS {cols}"

    seen = set()
    for lineno, row in enumerate(rows[1:], start=2):
        assert len(row) == len(cols), \
            f"row {lineno}: {len(row)} fields, expected {len(cols)}"
        run_id, date = row[0].strip(), row[1].strip()
        assert run_id, f"row {lineno}: empty run_id"
        assert run_id not in seen, f"row {lineno}: duplicate run_id {run_id!r}"
        seen.add(run_id)
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            pytest.fail(f"row {lineno} ({run_id}): date {date!r} is not %Y-%m-%d")


def _emitted_bootstrap():
    """The VM script gen_vm_bootstrap.py emits, with a placeholder standing in for
    each {substitution} — enough to parse, without needing any secret."""
    src = (SCRIPTS / "pipeline" / "gen_vm_bootstrap.py").read_text(encoding="utf-8")
    body = None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "body" for t in node.targets):
            body = node.value
    assert body is not None, "gen_vm_bootstrap.py has no `body = ...` assignment"
    assert isinstance(body, ast.JoinedStr), \
        f"`body` is {type(body).__name__}, not an f-string — this gate cannot read it"
    return "".join(v.value if isinstance(v, ast.Constant) else "'_SUBST_'"
                   for v in body.values)


def _static_str(node):
    """Best-effort source text for a watchdog line. Literal strings come through
    verbatim; a runtime-computed fragment (`"MOUNT = " + repr(MOUNT)`) keeps its
    literal half and gets a quoted placeholder for the rest, so the reassembled
    line is still parseable Python."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _static_str(node.left) + _static_str(node.right)
    return "'_SUBST_'"


def test_emitted_vm_bootstrap_is_valid_python():
    """gen_vm_bootstrap.py's product is CODE, and nothing checked its syntax.

    py_compile only ever sees the generator; the script it emits is a string, and
    the emitted script in turn WRITES A SECOND script (/content/vm_selfstop.py) as a
    list of source lines. Both layers run unattended on a billing VM — the watchdog
    layer is what drains the rclone upload backlog and calls runtime.unassign() —
    and a syntax error in either is only discoverable by spending a runtime on it.
    Both are parsed here.

    An f-string substitution can also silently eat code: a stray brace in the
    template becomes a format field rather than a Python brace, which is why the
    placeholder round-trip is done through the AST rather than by regex.
    """
    emitted = _emitted_bootstrap()
    ast.parse(emitted)                      # layer 1: the bootstrap itself

    wd = None
    for node in ast.walk(ast.parse(emitted)):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "_WD" for t in node.targets):
            wd = node.value
    assert wd is not None and isinstance(wd, ast.List), \
        "the emitted bootstrap no longer builds _WD as a literal list of source lines"
    lines = [_static_str(e) for e in wd.elts]
    assert len(lines) > 20, f"_WD collapsed to {len(lines)} lines — is it still the watchdog?"
    ast.parse("\n".join(lines))             # layer 2: the self-stop watchdog

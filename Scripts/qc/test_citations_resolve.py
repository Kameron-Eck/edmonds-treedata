"""Cross-file citations must name SYMBOLS, not line numbers — and must resolve.

WHAT DRIFTED, MEASURED 2026-08-30. Thirty comments across pipeline/ and qc/ cited
another file by line number. Resolving every one against the file it names showed the
class is not merely untidy — the pointers had rotted into pointing at unrelated code:

    core.py line 1032   cited in THREE files (common.py, vm_heartbeat.py,
                        test_vm_heartbeat.py) for the mount canary's admission that
                        os.replace was only ever proven absent-destination.
                        Real location: _deploy_smoothed_keeping_raw, ~374 lines later.
                        Line 1032 is now `for c in cols:`. One drift, copied three ways.

    core.py line 1161   postproc's reason for keying a threshold by channel arm.
                        Real location: step_evaluate, ~1,139 lines later.

    core.py line 785    phase4_crown_touch's evidence that step_train reads only
                        tile_index_*.csv — the claim the whole script's premise rests
                        on. Line 785 is a BLANK LINE inside _seg_loss.

    cli.py 576-578      the citywide= expression. Landed inside a --boundary-weight
                        help string added the same day.

    cli.py line 414     "the manifest, written by cli.py 414". Line 414 is an import.

The severity is not the wrong number. It is that a reader chasing `core.py` line 785
finds plausible-looking code and has no way to tell it is not the cited code — a stale
pointer that still resolves is worse than a broken one.

WHY A SYMBOL SURVIVES WHAT A LINE NUMBER DOES NOT. Inserting a line above a function
moves it; the function's NAME does not move. Renaming or deleting it breaks this test
loudly, at the moment of the rename, which is the moment someone can still say what the
citation meant.

SCOPE. pipeline/ and qc/ only. scratch/litwatch_scratch/ holds 77 one-shot writers that
are historical records of runs already made — editing them would falsify the record, the
same reason Stage 1 leaves the dated qc/*.md alone. _archive/ likewise.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_citations_resolve.py -q
"""
import ast
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
GATED = ("pipeline", "qc")

# Built by concatenation so this file does not violate its own ban — the examples in
# the docstring above are written without the colon form for the same reason.
_PY = r"[A-Za-z0-9_/]+[.]py"
LINE_CITE = re.compile(_PY + ":" + r"[0-9]+(?:-[0-9]+)?")
SYM_CITE = re.compile("(" + _PY + ")" + "::" + r"([A-Za-z_][A-Za-z0-9_]*)")


def _gated_files():
    out = []
    for root in GATED:
        for p in (SCRIPTS / root).rglob("*.py"):
            if "_archive" in p.parts or "litwatch_scratch" in p.parts:
                continue
            out.append(p)
    return sorted(out)


def _index():
    """basename -> [paths], across the gated tree plus anything it may cite."""
    idx = {}
    for p in SCRIPTS.rglob("*.py"):
        if "_archive" in p.parts:
            continue
        idx.setdefault(p.name, []).append(p)
    return idx


def _symbols(path):
    """Every name a citation may legitimately anchor to: defs, classes, methods, and
    module-level constants. Constants matter — GROVES, CROWNS, BASE, QC_DIR and STATUS
    are all cited, and they are exactly the kind of thing that gets moved."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


@pytest.mark.parametrize("path", _gated_files(), ids=lambda p: p.name)
def test_no_line_number_citations(path):
    """A hard ban, not a ratchet. The set was taken to zero on 2026-08-30, so any hit
    is a NEW citation and can be written as a symbol at the moment it is added — which
    is the only moment anyone knows what it was meant to point at."""
    hits = []
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace")
                             .splitlines(), 1):
        for m in LINE_CITE.finditer(line):
            hits.append(f"{path.name} line {i} cites {m.group(0)}")
    assert not hits, (
        "cite the SYMBOL, not the line — `cli.py` + `::main`, never a line number. "
        "Line numbers in this repo drift by hundreds of lines and keep resolving to "
        "unrelated code:" + chr(10) + chr(10).join("  " + h for h in hits))


def test_every_symbol_citation_resolves():
    """The other half. Banning line numbers is worthless if the replacement can name a
    function that does not exist — that would be the same stale pointer wearing better
    clothes."""
    idx = _index()
    cache = {}
    broken = []
    for path in _gated_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            for m in SYM_CITE.finditer(line):
                ref, sym = m.group(1), m.group(2)
                cands = idx.get(ref.split("/")[-1], [])
                if not cands:
                    broken.append(f"{path.name} line {i} -> {ref} (no such file)")
                    continue
                pref = [c for c in cands
                        if str(c).replace(chr(92), "/").endswith(ref)] or cands
                if len(pref) > 1:
                    broken.append(f"{path.name} line {i} -> {ref} is ambiguous "
                                  f"({len(pref)} files share that name; cite a path)")
                    continue
                t = pref[0]
                if t not in cache:
                    cache[t] = _symbols(t)
                if sym not in cache[t]:
                    broken.append(f"{path.name} line {i} -> {ref}::{sym} does not exist")
    assert not broken, (
        "symbol citations that no longer resolve — the symbol was renamed or removed "
        "and the citation was not:" + chr(10) + chr(10).join("  " + b for b in broken))


def test_the_evidence_chain_in_crown_touch_still_holds():
    """phase4_crown_touch exists on ONE premise: a citywide run never sees crown
    polygons, so no holdout has to be reserved. Three of the five links in its cited
    chain had drifted onto unrelated code. Re-anchoring them fixed the pointers; this
    checks the CLAIM, which is the part that would actually invalidate the metric."""
    core = (SCRIPTS / "pipeline" / "phase4seg" / "core.py").read_text(encoding="utf-8")
    assert "crown" not in core.lower(), (
        "core.py now mentions crowns — phase4_crown_touch's premise that the training "
        "path cannot see the instance layer needs re-verifying, not just re-citing")

    labels = (SCRIPTS / "pipeline" / "phase4seg" / "labels.py").read_text(encoding="utf-8")
    tree = ast.parse(labels)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "step_labels")
    body = ast.get_source_segment(labels, fn) or ""
    assert "if citywide:" in body and "SKIPPED" in body, (
        "step_labels no longer short-circuits on citywide — the crown-burn step may "
        "now run in citywide mode, which would put crowns into the training labels")

"""heal_vs_gold's stack plumbing: defaults regenerate the tracked table, and the stack
handed in is the one the healer runs on (the closing baseline refuses a mismatch)."""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
QC = SCRIPTS.parent / "phase4" / "qc"


def _load():
    p = SCRIPTS / "qc" / "instruments" / "heal_vs_gold.py"
    spec = importlib.util.spec_from_file_location("heal_vs_gold_under_test", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_parser_defaults_are_the_module_constants():
    """A later edit cannot silently move the published table or the cache it reads."""
    M = _load()
    a = M._parser().parse_args([])
    assert a.stack == str(M.STACK) and a.out == str(M.OUT_CSV) and not a.dry_run
    assert M.STACK == Path(r"D:\edmonds-pipeline\trend8_stack_2m.npz")
    assert M.OUT_CSV == QC / "heal_vs_gold.csv"


def test_build_takes_the_stack_and_forwards_it_to_the_healer():
    """The gold trajectories and the healer's overlays must index ONE lattice. The stack
    parameter exists, defaults to the published cache, and is the value passed on."""
    M = _load()
    sig = inspect.signature(M.build)
    assert "stack" in sig.parameters and sig.parameters["stack"].default is None
    src = inspect.getsource(M.build)
    assert "heal_build(stack=stack_path)" in src and "np.load(stack_path)" in src
    assert "np.load(STACK)" not in src


def test_closing_baseline_hands_its_stack_to_heal_vs_gold():
    """The years-equality gate in heal_closing_baseline can only pass on a 12-epoch stack
    if heal_vs_gold scored the same stack; the call must forward it."""
    p = SCRIPTS / "qc" / "instruments" / "heal_closing_baseline.py"
    src = p.read_text(encoding="utf-8")
    assert "hvg_build(stack=stack_path)" in src

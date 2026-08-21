#!/usr/bin/env python3
"""
Local pre-flight for the phase4seg engine. Run this BEFORE pushing to Colab to
catch the error classes that keep biting on the Drive round-trip:
  - syntax errors            (py_compile)
  - missing imports / undefined names   (config-star + torch-handle aware sweep)
  - import-time failures     (actually imports the package)
  - bad command-line args    (validates via cli --check)

No GPU, no torch, no /content paths needed — the package imports lazily, so this
runs on your local machine with just the geo stack you already use for the QC
scripts. Training/inference still happen on Colab; this only proves the code and
your command are VALID before you spend a Colab round-trip on them.

Usage (from the repo's Scripts/pipeline/ directory):
    py -3.12 phase4seg_preflight.py --year 2000,2002,2013,2015,2017,2019,2022 --no-compile
    py -3.12 phase4seg_preflight.py --year 2016 --step tile
Pass the SAME args you intend to hand the Colab %run. Exit 0 = safe to push.
"""
import ast
import builtins
import py_compile
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE / "phase4seg"
MODULES = ["config", "common", "labels", "tiling", "core", "postproc", "cli"]


def fail(msg):
    print(f"\n[FAILED] {msg}")
    sys.exit(1)


# ── 1. syntax ──────────────────────────────────────────────────────────────
print("[1/4] py_compile ...")
for f in [HERE / "phase4_semantic_finetune.py"] + [PKG / f"{m}.py" for m in MODULES]:
    try:
        py_compile.compile(str(f), doraise=True)
    except py_compile.PyCompileError as e:
        fail(f"syntax error in {f.name}:\n{e}")
print("      ok")

# ── 2. undefined-name sweep (star-import + lazy-torch aware) ────────────────
print("[2/4] undefined-name sweep ...")
sys.path.insert(0, str(HERE))
import phase4seg.config as cfg  # noqa: E402

CONFIG_STAR = {n for n in dir(cfg) if not n.startswith("_")}
BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
TORCH = {"torch", "nn", "Dataset", "DataLoader", "WeightedRandomSampler",
         "smp", "A", "ToTensorV2"}
problems = []
for m in MODULES:
    tree = ast.parse((PKG / f"{m}.py").read_text(encoding="utf-8"))
    bound, used = set(), []

    class B(ast.NodeVisitor):
        def visit_Import(s, n):
            for a in n.names:
                bound.add((a.asname or a.name).split(".")[0])
        def visit_ImportFrom(s, n):
            for a in n.names:
                if a.name != "*":
                    bound.add(a.asname or a.name)
        def visit_FunctionDef(s, n):
            bound.add(n.name)
            ar = n.args
            for a in ar.posonlyargs + ar.args + ar.kwonlyargs:
                bound.add(a.arg)
            if ar.vararg:
                bound.add(ar.vararg.arg)
            if ar.kwarg:
                bound.add(ar.kwarg.arg)
            s.generic_visit(n)
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_Lambda(s, n):
            ar = n.args
            for a in ar.posonlyargs + ar.args + ar.kwonlyargs:
                bound.add(a.arg)
            s.generic_visit(n)
        def visit_ClassDef(s, n):
            bound.add(n.name)
            s.generic_visit(n)
        def visit_ExceptHandler(s, n):
            if n.name:
                bound.add(n.name)
            s.generic_visit(n)
        def visit_Name(s, n):
            if isinstance(n.ctx, ast.Store):
                bound.add(n.id)
            s.generic_visit(n)
        def visit_Global(s, n):
            for nm in n.names:
                bound.add(nm)
            s.generic_visit(n)

    B().visit(tree)

    class U(ast.NodeVisitor):
        def visit_Name(s, n):
            if isinstance(n.ctx, ast.Load):
                used.append(n.id)

    U().visit(tree)
    avail = bound | CONFIG_STAR | BUILTINS | TORCH
    miss = sorted(set(u for u in used if u not in avail))
    if miss:
        problems.append(f"{m}.py references undefined name(s): {miss}")
if problems:
    fail("undefined names (usually a missing import):\n  " + "\n  ".join(problems))
print("      ok")

# ── 3. import the package (catches import-time errors) ─────────────────────
print("[3/4] import phase4seg.cli ...")
try:
    import phase4seg.cli  # noqa: E402,F401
except Exception as e:
    fail(f"import error: {type(e).__name__}: {e}")
print(f"      ok (torch stayed unloaded: {'torch' not in sys.modules})")

# ── 4. validate YOUR command line (parse-only via --check) ─────────────────
print("[4/4] argparse validation of your command ...")
user_args = list(sys.argv[1:])
sys.argv = ["phase4_semantic_finetune.py"] + user_args + ["--check"]
try:
    phase4seg.cli.main()
except SystemExit as e:
    if e.code not in (0, None):
        fail("argparse rejected your command (see the usage/error printed above).")
print()
print("[PASSED] pre-flight clean — safe to push to Colab.")
print("         (Nothing ran on a GPU; training/inference still happen on Colab.)")

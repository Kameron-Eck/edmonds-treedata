"""check.py — THE local verification ladder, one command. (refactor follow-up, 2026-09-01)

Definition of done for any edit in this repo:

    py -3.12 qc/check.py            the full ladder
    py -3.12 qc/check.py --fast     skip the runtime smoke (engine untouched? still run it
                                    before any Colab push — CLAUDE.md 3.1)
    py -3.12 qc/check.py --status   also regenerate STATUS.md (reads the lake; slower)

Rungs, fast to slow, stop at first failure:
    1. ruff        F821/F401/F811 (config: pyproject [tool.ruff]) — undefined names are
                   runtime NameErrors py_compile cannot see; first run caught 7
    2. compile     py_compile over pipeline/ + qc/ (frozen/ included — it must stay parseable)
    3. pytest      the full qc suite
    4. preflight   static engine gate (phase4seg_preflight)
    5. smoke       CPU runtime gate (phase4seg_smoke) — skipped by --fast
    6. status      STATUS.md regen — only with --status

CI runs the same rungs in ci.yml; this is the local mirror so no session forgets one.
Stdlib only. Exit 0 = every rung passed.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


def rung(name, cmd, cwd=SCRIPTS):
    t0 = time.time()
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       errors="replace")
    dt = time.time() - t0
    ok = r.returncode == 0
    print(f"  [{'PASS' if ok else 'FAIL'}] {name:<10} {dt:6.1f}s")
    if not ok:
        tail = ((r.stdout or "") + "\n" + (r.stderr or "")).strip().splitlines()[-25:]
        print("\n".join("    " + ln for ln in tail))
        print(f"\ncheck: FAILED at rung '{name}' — fix, then rerun. "
              f"({' '.join(str(c) for c in cmd)})")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="run the full local verification ladder")
    ap.add_argument("--fast", action="store_true", help="skip the CPU runtime smoke")
    ap.add_argument("--status", action="store_true", help="also regenerate STATUS.md")
    a = ap.parse_args()
    py = sys.executable
    t0 = time.time()
    print(f"check.py — ladder from {SCRIPTS}")

    rung("ruff", [py, "-m", "ruff", "check", "Scripts/pipeline", "Scripts/qc"],
         cwd=SCRIPTS.parent)
    rung("compile", [py, "-c",
         "import compileall,sys;"
         "ok=all(compileall.compile_dir(d,quiet=1,maxlevels=10) for d in ('pipeline','qc'));"
         "sys.exit(0 if ok else 1)"])
    rung("pytest", [py, "-m", "pytest", "qc", "-q"])
    rung("preflight", [py, str(SCRIPTS / "pipeline" / "phase4seg_preflight.py")])
    if a.fast:
        print("  [skip] smoke        (--fast; run the full ladder before any Colab push)")
    else:
        rung("smoke", [py, str(SCRIPTS / "pipeline" / "phase4seg_smoke.py")])
    if a.status:
        rung("status", [py, str(SCRIPTS / "qc" / "pipeline_status.py"), "--markdown"])
    print(f"\ncheck: ALL RUNGS PASSED in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

"""landed.py — CLAUDE.md 3.12 as a COMMAND, not a prose checklist.

The registry tool existed and got bypassed the same night it mattered (2026-09-01:
two canary rows hand-typed with invented run_ids while registry_from_manifests sat
unused; the derived rows replaced them). A checklist nothing executes is decoration —
so this runs it:

    py -3.12 qc/landed.py            after a landed milestone / Colab run
    py -3.12 qc/landed.py --dry-run  show what it would do

  1. registry   registry_from_manifests (append-only, idempotent) — every finished
                manifest becomes a row; hand-typing is retired
  2. exp        experiment-file consistency (qc/test_experiments.py)
  3. docs       drift gates over the gated docs
  4. status     STATUS.md + STATUS.json regenerated (lake mounted only)
  5. chatlog    HEURISTIC reminder + entry stub when the newest LOG entry is not
                from today — printed, never written (the log stays human-authored)
  6. stage      `git status --short` so nothing lands unstaged (never add -A)

Commit + CHATLOG prose remain yours; everything mechanical is now one command.
"""
import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


def run(name, cmd, dry):
    print(f"\n── {name} " + "─" * (68 - len(name)))
    if dry:
        print("  (dry-run) $", " ".join(str(c) for c in cmd))
        return 0
    r = subprocess.run(cmd, cwd=str(SCRIPTS))
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    py = sys.executable
    fails = 0

    reg = [py, str(SCRIPTS / "pipeline" / "registry_from_manifests.py")]
    if a.dry_run:
        reg.append("--dry-run")
    fails += run("registry <- manifests", reg, dry=False) != 0   # its own dry-run flag
    fails += run("experiment consistency",
                 [py, "-m", "pytest", "qc/test_experiments.py", "-q"], a.dry_run) != 0
    fails += run("doc drift gates",
                 [py, "-m", "pytest", "qc/test_docs_match_code.py", "-q"], a.dry_run) != 0
    from lake import BASE
    if BASE.exists():
        fails += run("STATUS.md", [py, str(SCRIPTS / "qc" / "pipeline_status.py"),
                                   "--markdown"], a.dry_run) != 0
        fails += run("STATUS.json", [py, str(SCRIPTS / "qc" / "pipeline_status.py"),
                                     "--json"], a.dry_run) != 0
    else:
        print("\n── STATUS regen skipped — lake not mounted")

    print("\n── CHATLOG " + "─" * 60)
    log = (SCRIPTS / "CHATLOG.md").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^## (\d{4}-\d{2}-\d{2})", log, re.M)
    today = _dt.date.today().isoformat()
    if m and m.group(1) >= today:   # >= : a session can straddle midnight
        print(f"  newest entry is from today ({m.group(1)}) — assumed current")
    else:
        print(f"  newest entry: {m.group(1) if m else 'NONE'} — append one "
              f"(caveman style, schema in the file header):\n"
              f"  ## {today}  <slug>\n  goal:    \n  did:     \n  files:   \n  next:    ")

    print("\n── unstaged " + "─" * 59)
    subprocess.run(["git", "status", "--short"], cwd=str(SCRIPTS))
    if fails:
        sys.exit(f"\nlanded: {fails} rung(s) failed — fix before committing")
    print("\nlanded: mechanical rungs clean — write the CHATLOG prose and commit.")


if __name__ == "__main__":
    main()

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
  3. decisions  the open-decision registry (qc/test_decisions.py)
  4. claims     every load-bearing number re-resolved against its evidence
                (qc/verify_claims.py) — this is what the findings ledger never had
  5. docs       drift gates over the gated docs
  6. status     STATUS.md + STATUS.json regenerated (lake mounted only)
  7. harvest    tilesets, run passports, arm metrics + curves, failures — the
                lake-reading harvests, so a landed campaign cannot leave the tracked
                context tables describing the PREVIOUS state of the lake
  8. regen      year scoreboard, coverage map, experiment index, SCIENCE.md —
                derived from tracked homes, so they run with or without the lake
  9. chatlog    HEURISTIC reminder + entry stub when the newest LOG entry is not
                from today — printed, never written (the log stays human-authored)
 10. stage      `git status --short` so nothing lands unstaged (never add -A)

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
    fails += run("decision registry",
                 [py, "-m", "pytest", "qc/test_decisions.py", "-q"], a.dry_run) != 0
    fails += run("claims vs evidence",
                 [py, str(SCRIPTS / "qc" / "verify_claims.py")], a.dry_run) != 0
    fails += run("doc drift gates",
                 [py, "-m", "pytest", "qc/test_docs_match_code.py", "-q"], a.dry_run) != 0
    from lake import BASE
    if BASE.exists():
        fails += run("STATUS.md", [py, str(SCRIPTS / "qc" / "pipeline_status.py"),
                                   "--markdown"], a.dry_run) != 0
        fails += run("STATUS.json", [py, str(SCRIPTS / "qc" / "pipeline_status.py"),
                                     "--json"], a.dry_run) != 0
        # The lake-reading harvests. A campaign that lands without these leaves every
        # tracked context table describing the PREVIOUS state of the lake — the same
        # silent-drift failure as the .docx ledger, just faster. They are idempotent
        # and cheap (seconds), so they run on every landed milestone rather than
        # relying on anyone remembering.
        for name, script in (("tilesets", "instruments/harvest_tilesets.py"),
                             ("run passports", "instruments/harvest_run_passport.py"),
                             ("arm metrics + curves", "instruments/harvest_arm_metrics.py"),
                             ("failures", "instruments/harvest_failures.py")):
            fails += run(f"harvest: {name}",
                         [py, str(SCRIPTS / "qc" / script)], a.dry_run) != 0
    else:
        print("\n── STATUS regen skipped — lake not mounted")
        print("── harvests skipped — they read the lake; tracked views still regenerate")

    # Derived from TRACKED homes only, so these regenerate with or without the lake —
    # and their freshness gates fail the suite if they are not run.
    for name, script in (("year scoreboard", "year_scoreboard.py"),
                         ("coverage map", "coverage_map.py"),
                         ("experiment index", "experiments_index.py"),
                         ("science digest", "science_digest.py")):
        fails += run(f"regenerate: {name}",
                     [py, str(SCRIPTS / "qc" / script)], a.dry_run) != 0

    print("\n── CHATLOG " + "─" * 60)
    log = (SCRIPTS / "CHATLOG.md").read_text(encoding="utf-8", errors="replace")
    # ALL matches, take the last: entries append at the BOTTOM, and the rotated
    # stub keeps old entries above — re.search took the first (= oldest) and
    # nagged for entries that already existed (caught 2026-09-05).
    dates = re.findall(r"^## (\d{4}-\d{2}-\d{2})", log, re.M)
    newest = max(dates) if dates else None
    today = _dt.date.today().isoformat()
    if newest and newest >= today:   # >= : a session can straddle midnight
        print(f"  newest entry is from today ({newest}) — assumed current")
    else:
        print(f"  newest entry: {newest or 'NONE'} — append one "
              f"(caveman style, schema in the file header):\n"
              f"  ## {today}  <slug>\n  goal:    \n  did:     \n  files:   \n  next:    ")

    print("\n── unstaged " + "─" * 59)
    subprocess.run(["git", "status", "--short"], cwd=str(SCRIPTS))
    if fails:
        sys.exit(f"\nlanded: {fails} rung(s) failed — fix before committing")
    print("\nlanded: mechanical rungs clean — write the CHATLOG prose and commit.")


if __name__ == "__main__":
    main()

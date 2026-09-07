"""year_scoreboard.py — where the best performance is, per year, at a HELD cut.

"It's important to know where the best performance is for a given year. It's also
important to be able to hold certain points on the curve steady for objective
comparison." (Kam, 2026-09-06). Those two sentences are one requirement: a "best" arm
is only meaningful at a stated operating point, because at per-arm best-F1 cuts every
arm is best at something.

So this ranks arms per year at ONE policy — `matched_p75` by default: the highest
recall available while precision stays at or above 0.75. One axis pinned, the other
compared. Change it with --policy; the choice is printed in the output so a reader can
never mistake which cut a ranking was made at.

Writes `phase4/qc/year_scoreboard.md` (scannable) from tracked homes only:

    phase4/qc/arm_metrics.csv      the operating points and their curves
    phase4/qc/tileset_registry.csv what the arm trained on
    phase4/qc/run_passport.csv     the run that produced it
    pipeline/champion_arms.csv     which arm is the designated deliverable

WHAT IT REFUSES TO DO. It does not rank across DIFFERENT evaluation populations. Two
arms scored on different footprints or different LOSO halves are not comparable, and
silently sorting them into one table is how a coverage difference gets read as a skill
difference — 2017's four deliveries span 15.8 M to 5.7 B scored pixels. Arms are
grouped by (reference, scope) and each group ranked within itself, with its population
printed. A group of one is reported as a group of one, not as a winner.

Run:  py -3.12 qc/year_scoreboard.py [--policy matched_p75]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"


def _rows(path):
    if not path.exists():
        return []
    body = [ln for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build(policy="matched_p75"):
    metrics = [m for m in _rows(QC / "arm_metrics.csv") if m["policy"] == policy]
    tiles = {(t["label"], t["run_tag"]): t
             for t in _rows(QC / "tileset_registry.csv") if t["tileset_id"]}
    try:
        import champion
        champs = champion.load_champions()
    except Exception:
        champs = {}

    out = [f"# YEAR SCOREBOARD — best arm per year at `{policy}` — GENERATED",
           "",
           f"Regenerate: `py -3.12 qc/year_scoreboard.py --policy {policy}`.",
           "",
           "Every ranking here is made at ONE held operating point. At per-arm best-F1",
           "cuts every arm is best at something, which is how one 2017 flight delivered",
           "three ways came to look 10.09 pp apart when matched cuts put it at 1.07.",
           "",
           "Arms are grouped by (reference, evaluation scope) and ranked only WITHIN a",
           "group: different populations are not comparable, and `population` is printed",
           "so a coverage gap can never be read as a skill gap. ★ = the designated",
           "champion (pipeline/champion_arms.csv).",
           ""]

    years = sorted({m["year"] for m in metrics})
    for year in years:
        rows = [m for m in metrics if m["year"] == year]
        groups = {}
        for m in rows:
            groups.setdefault((m["ref"], m["eval_scope"]), []).append(m)
        out.append(f"## {year}")
        out.append("")
        for (ref, scope), arms in sorted(groups.items()):
            arms.sort(key=lambda m: (-(_f(m["recall"]) or -1)))
            lone = " — single arm, nothing to rank against" if len(arms) == 1 else ""
            out.append(f"**ref `{ref}`** · scope `{scope or 'citywide'}`{lone}")
            out.append("")
            out.append("| arm | recall | precision | thresh | pr_auc | population "
                       "| eligible cuts | tiles (train) | curve |")
            out.append("|---|---|---|---|---|---|---|---|---|")
            for m in arms:
                tag = m["run_tag"]
                star = " ★" if champs.get(year) == tag else ""
                t = tiles.get((year, tag))
                tinfo = (f"{t['n_tiles']} ({t['n_train']})" if t else "—")
                pop = f"{int(m['population']):,}" if m["population"] else "—"
                out.append(
                    f"| {tag or '(untagged)'}{star} | {m['recall']} | {m['precision']} "
                    f"| {m['thresh']} | {m['pr_auc'] or '—'} | {pop} "
                    f"| {m['n_eligible_cuts'] or '—'} | {tinfo} "
                    f"| `{m['curve_file'] or '—'}` |")
            out.append("")
    if not years:
        out.append(f"_No arms carry a `{policy}` operating point yet._")
        out.append("")
    return "\n".join(out), len(years), len(metrics)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--policy", default="matched_p75",
                    help="operating point to rank at (default: matched_p75)")
    a = ap.parse_args(argv)

    from instruments.harvest_arm_metrics import POLICIES  # noqa: F401  (validation)
    if a.policy not in POLICIES:
        print(f"FATAL: unknown policy {a.policy!r} — allowed: {POLICIES}")
        return 2

    md, n_years, n_arms = build(a.policy)
    (QC / "year_scoreboard.md").write_text(md, encoding="utf-8", newline="\n")
    print(f"wrote phase4/qc/year_scoreboard.md — {n_arms} arms over {n_years} years "
          f"at {a.policy}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(SCRIPTS / "qc"))   # ledger: test_status_discovery.py
    sys.exit(main())

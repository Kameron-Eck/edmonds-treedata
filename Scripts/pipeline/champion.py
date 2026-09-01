r"""Champion-arm pointer loader (E05).

One home for "which arm is the deliverable for year Y":
Scripts/pipeline/champion_arms.csv (authored, git-versioned — see its header).
Consumers must FAIL LOUD (skip + list) on a year with live rows but no champion
row — never fall back to last-wins: that silently plotted the wrong 2013 arm.
"""
import csv
import re
from pathlib import Path

CHAMPION_CSV = Path(__file__).resolve().parents[1] / "pipeline" / "champion_arms.csv"


def prob_arm(prob_name):
    """Arm tag parsed from a prob filename — the same parse qc_indep and
    live_thresholds() use ('' = untagged citywide)."""
    m = re.search(r"prob_[0-9a-z]+_(.+)\.tif", prob_name or "")
    return m.group(1) if m else ""


def load_champions():
    """{year: tag}. Comment lines (#) in the CSV are authored header text."""
    with open(CHAMPION_CSV, encoding="utf-8") as f:
        lines = [ln for ln in f if not ln.lstrip().startswith("#")]
    return {r["year"].strip(): (r["tag"] or "").strip()
            for r in csv.DictReader(lines) if (r.get("year") or "").strip()}

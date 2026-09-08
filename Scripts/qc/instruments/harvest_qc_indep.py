"""harvest_qc_indep.py — bring the tracked copy of the HONEST results home up to the lake.

THE RULEBOOK NAMES `phase4/qc/qc_indep_report.csv` AS THE HOME OF HONEST SCORED RESULTS,
AND NOTHING REFRESHED IT. `qc/landed.py` harvests seven lake tables on every landed
milestone (tilesets, passports, arm metrics, failures, hw, timing, sessions) — this one
was hand-copied. Twice it fell behind the lake unnoticed: 120 rows on 2026-08-30
(commit 1f6d53d), then 285 rows and nine days on 2026-09-08, when a reader answering
"what does the current recipe score" found ZERO rows for any current-recipe arm in the
tracked file while the lake held 42 live ones. Every session reads the tracked file.
A stale honest-results table is worse than none: it is trusted.

WHAT IT COPIES (lake `phase4/qc/` -> tracked `phase4/qc/`, byte-for-byte):

    qc_indep_report.csv           the contract (docs/SCHEMAS.md "qc_indep_report.csv")
    qc_indep_{year}.txt           the human-readable per-year breakout
    qc_indep_surfaces_{year}.csv  the per-surface-group breakout

NOT copied: `qc_indep_sweep_*.csv` (curves are `harvest_arm_metrics.py`'s job and are
re-keyed there), `*.bak_*` and `*.CONTAMINATED*` (lake-side history, never tracked).

THREE GATES, because a harvest is a write over the tracked record:

    never shrink      if the lake report has FEWER rows than the tracked copy, refuse.
                      A shrinking lake table is the symptom of the six-day ledger
                      erasure (phase4/qc/ledger_recovery/), not a harvest. Override
                      only with --allow-shrink, deliberately.
    same contract     the header must equal the SCHEMAS column set exactly; a changed
                      writer must change the schema first, not silently re-shape the
                      tracked file.
    lineage sanity    the writer keeps ONE live generation per (year, ref, arm, aoi):
                      every live=1 row in a lineage shares one `ts`. A lineage with two
                      live timestamps is reported (not fatal — the lake is the truth and
                      the fix belongs in the writer), so a reader filtering live==1
                      knows which years carry two answers.

Run:  py -3.12 qc/instruments/harvest_qc_indep.py [--dry-run] [--allow-shrink]
Exit: 0 harvested (or nothing to do) · 2 a gate refused · 3 lake not reachable
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
TRACKED_QC = REPO / "phase4" / "qc"

REPORT = "qc_indep_report.csv"
# The contract, verbatim from docs/SCHEMAS.md "qc_indep_report.csv".
REPORT_COLS = ("year", "ref", "prob", "canopy_def", "thresh", "recall", "precision",
               "grass_reject", "tp", "fn", "fp", "ref_canopy", "valid", "indep_1m_cells",
               "primary", "live", "run_tag", "aoi", "ts")
# Sidecars: the per-year text and per-surface breakouts. Sweeps are excluded on purpose.
SIDECAR_PATTERNS = (re.compile(r"^qc_indep_[0-9]{4}[a-z]?\.txt$"),
                    re.compile(r"^qc_indep_surfaces_[0-9]{4}[a-z]?\.csv$"))


def _lake_qc_dir() -> Path | None:
    try:
        from phase4seg import config
        cands = [Path(config.BASE) / "phase4" / "qc"]
    except Exception:  # pragma: no cover - phase4seg not installed
        cands = []
    cands.append(Path(r"G:/My Drive/treedata/phase4/qc"))
    for cand in cands:
        if (cand / REPORT).exists():
            return cand
    return None


def _read_rows(path: Path) -> tuple[list[str], list[dict]]:
    text = path.read_text(encoding="utf-8")
    rdr = csv.DictReader(io.StringIO(text))
    rows = list(rdr)
    return list(rdr.fieldnames or []), rows


def _arm(prob_name: str) -> str:
    # champion.py::prob_arm is the canonical parser; import it when installed so the
    # lineage key here can never drift from the writer's.
    try:
        from champion import prob_arm
        return prob_arm(prob_name) or ""
    except Exception:
        m = re.match(r"^edmonds_canopy_prob_[0-9]{4}[a-z]?_(.+)\.tif$", prob_name)
        return m.group(1) if m else ""


def live_lineage_conflicts(rows: list[dict]) -> list[tuple]:
    """Lineages (year, ref, arm, aoi) whose live=1 rows carry more than one `ts`."""
    seen: dict[tuple, set] = defaultdict(set)
    for r in rows:
        if r.get("live", "1") == "0":
            continue
        key = (r.get("year", ""), r.get("ref", ""), _arm(r.get("prob", "")),
               r.get("aoi", ""))
        seen[key].add(r.get("ts", ""))
    return sorted(k for k, ts in seen.items() if len(ts) > 1)


def sidecars(lake_dir: Path) -> list[Path]:
    return sorted(p for p in lake_dir.iterdir()
                  if p.is_file() and any(pat.match(p.name) for pat in SIDECAR_PATTERNS))


def harvest(lake_dir: Path, tracked_dir: Path, *, dry_run: bool = False,
            allow_shrink: bool = False, out=None) -> int:
    out = out or sys.stdout          # resolved at call time, so capture sees it
    src = lake_dir / REPORT
    dst = tracked_dir / REPORT
    header, lake_rows = _read_rows(src)
    if tuple(header) != REPORT_COLS:
        print(f"[harvest-qc-indep] REFUSED: lake header != SCHEMAS contract\n"
              f"  lake:     {header}\n  contract: {list(REPORT_COLS)}", file=out)
        return 2
    tracked_n = len(_read_rows(dst)[1]) if dst.exists() else 0
    lake_n = len(lake_rows)
    if lake_n < tracked_n and not allow_shrink:
        print(f"[harvest-qc-indep] REFUSED: lake report has {lake_n} rows, tracked has "
              f"{tracked_n} — a shrinking lake table is a symptom, not a harvest "
              f"(see phase4/qc/ledger_recovery/). Re-run with --allow-shrink only if "
              f"the shrink is understood.", file=out)
        return 2

    live_rows = [r for r in lake_rows if r.get("live", "1") != "0"]
    conflicts = live_lineage_conflicts(lake_rows)
    side = sidecars(lake_dir)
    changed = [p for p in side
               if not (tracked_dir / p.name).exists()
               or (tracked_dir / p.name).read_bytes() != p.read_bytes()]
    report_changed = (not dst.exists()) or dst.read_bytes() != src.read_bytes()

    # Files the tracked dir holds that the lake no longer does: a lake-side rename
    # (e.g. `.CONTAMINATED-…` quarantine) leaves the tracked copy orphaned. Reported,
    # never deleted — retiring tracked history is a decision, not a harvest.
    orphans = sorted(p.name for p in tracked_dir.iterdir()
                     if any(pat.match(p.name) for pat in SIDECAR_PATTERNS)
                     and not (lake_dir / p.name).exists()) if tracked_dir.exists() else []

    print(f"[harvest-qc-indep] lake {lake_n} rows ({len(live_rows)} live) · tracked "
          f"{tracked_n} rows · +{lake_n - tracked_n} · sidecars {len(side)} "
          f"({len(changed)} changed)", file=out)
    if orphans:
        print(f"[harvest-qc-indep] ! {len(orphans)} tracked file(s) have no lake "
              f"counterpart (renamed or quarantined lake-side; left in place): "
              f"{', '.join(orphans)}", file=out)
    if conflicts:
        print(f"[harvest-qc-indep] ! {len(conflicts)} live lineage(s) carry two "
              f"timestamps — readers filtering live==1 get two answers:", file=out)
        for year, ref, arm, aoi in conflicts:
            print(f"    {year} {arm or 'untagged'} vs {ref}{' aoi=' + aoi if aoi else ''}",
                  file=out)
    if dry_run:
        print("[harvest-qc-indep] dry run — nothing written", file=out)
        return 0
    if not report_changed and not changed:
        print("[harvest-qc-indep] tracked copy already matches the lake", file=out)
        return 0
    tracked_dir.mkdir(parents=True, exist_ok=True)
    if report_changed:
        shutil.copyfile(src, dst)
    for p in changed:
        shutil.copyfile(p, tracked_dir / p.name)
    print(f"[harvest-qc-indep] wrote {dst.relative_to(REPO) if dst.is_relative_to(REPO) else dst}"
          f" + {len(changed)} sidecar(s)", file=out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-shrink", action="store_true",
                    help="accept a lake report with fewer rows than the tracked copy")
    ap.add_argument("--lake-dir", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--tracked-dir", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    lake = Path(a.lake_dir) if a.lake_dir else _lake_qc_dir()
    if lake is None or not (lake / REPORT).exists():
        print("[harvest-qc-indep] lake not reachable — nothing harvested", file=sys.stderr)
        return 3
    tracked = Path(a.tracked_dir) if a.tracked_dir else TRACKED_QC
    return harvest(lake, tracked, dry_run=a.dry_run, allow_shrink=a.allow_shrink)


if __name__ == "__main__":
    sys.exit(main())

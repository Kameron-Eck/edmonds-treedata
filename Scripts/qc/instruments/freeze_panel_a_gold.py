"""freeze_panel_a_gold.py — pin the gold set, once, with semantics taken from the estimator.

THE PROBLEM THIS ENDS. Every downstream number is scored against Panel A's gold — the
0.431 weighted precision a detector must beat, the 41/42 loss corroboration, the
terminal-class recall target. But the gold had no pinned definition: `panel_a_labels.csv`
holds 1,393 rows over 1,311 distinct points with 66 points labelled more than once and 42
`undo` entries, and `panel_a_verify.csv` adds 111 rows over 61 points with 25 more undos.
Reasonable people resolved that differently and got 1155, 1169 and 1170 no-change points.
`Reports/CHANGE_DETECTOR_DESIGN_2026-09-06.md` names this the blocker for everything and
says plainly: "No script pins this dedup; that's why three analysts got three counts."

This is that script.

THE SEMANTICS ARE NOT NEW, AND THAT IS THE POINT. They are lifted from
`panel_a_paired_change.step_estimate` — the code that produced the -2.21 pp headline every
other number is measured against. Inventing a cleaner rule here would create a second
authority disagreeing with the published estimate, which is the disease, not the cure:

  1. Replay `panel_a_labels.csv` IN FILE ORDER. `undo` REMOVES the point; any other label
     replaces it. (File order, not timestamp order — that is what the estimator does, and
     a re-sort silently changes which of 66 repeated points wins.)
  2. Replay `panel_a_verify.csv` the same way, then let it override. Verify is the
     three-epoch leaf-on re-judgement and wins where it speaks; it overturned 18 calls.
  3. Keep points whose `kind` is `live` and whose resolved label is loss / gain /
     nochange. `unsure` is excluded by the estimator and is excluded here; blur, drift and
     duplicate controls are not `live` and never enter the gold.

A CORRECTION TO THE RECORD, which is what freezing it produced. Under these semantics the
gold is 1,170 no-change / 42 loss / 2 gain. The design doc asserts 1,169 no-change. The
loss and gain counts are stable under every verify convention I tested (verify overrides
everything / only prior change calls / only already-labelled points — all three give the
same three numbers), so 42 and 2 are solid and the 1,169 is off by one with no derivation
any of those rules reproduces. The frozen value is 1,170 because it is the one the
estimator's own code yields; the discrepancy is recorded rather than reconciled by fiat.

THE GOLD IS SPENT. It is a development set forever (design doc §confirmatory): 42
positives means held-out recall has sd 7.3 pp, so no recall difference under ~10 pp is
resolvable on it, ever. Anything confirmatory needs a fresh draw.

Output: phase4/qc/panel_a_gold.csv — one row per gold point, with its stratum and the
weight the estimator gives it.

Run:  py -3.12 qc/instruments/freeze_panel_a_gold.py [--dry-run]
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"

GOLD_LABELS = ("loss", "gain", "nochange")
COLS = ["point_id", "label", "stratum", "stratum_name", "estimator_stratum",
        "x", "y", "verify_overturned"]


def resolve():
    """Return (gold, provenance). Semantics are step_estimate's, not this file's."""
    sys.path.insert(0, str(SCRIPTS / "qc" / "instruments"))  # ledger: test_status_discovery
    from panel_a_paired_change import _load_labels

    base = _load_labels(QC / "panel_a_labels.csv")
    ver = _load_labels(QC / "panel_a_verify.csv")
    overturned = {pid for pid, lab in ver.items()
                  if pid in base and lab != base[pid]}
    labels = dict(base)
    labels.update(ver)

    pts = {r["point_id"]: r for r in csv.DictReader(
        io.open(QC / "panel_a_points.csv", encoding="utf-8", newline=""))}
    meta = json.loads((QC / "panel_a_meta.json").read_text(encoding="utf-8"))

    gold = []
    for pid, lab in labels.items():
        p = pts.get(pid)
        if p is None or p["kind"] != "live" or lab not in GOLD_LABELS:
            continue
        # The estimator routes srs_floor points through the stratum they physically
        # fall in; carrying that here keeps the weight with the point.
        sid = (int(p["overlap_stratum"]) if p["stratum_name"] == "srs_floor"
               else int(p["stratum"]))
        gold.append({
            "point_id": pid, "label": lab,
            "stratum": p["stratum"], "stratum_name": p["stratum_name"],
            "estimator_stratum": sid, "x": p["x"], "y": p["y"],
            "verify_overturned": int(pid in overturned),
        })
    gold.sort(key=lambda r: r["point_id"])
    prov = {
        "n_label_rows": sum(1 for _ in csv.DictReader(
            io.open(QC / "panel_a_labels.csv", encoding="utf-8", newline=""))),
        "n_verify_rows": sum(1 for _ in csv.DictReader(
            io.open(QC / "panel_a_verify.csv", encoding="utf-8", newline=""))),
        "n_overturned": len(overturned),
        "strata_in_meta": len(meta["strata"]),
    }
    return gold, prov


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    gold, prov = resolve()
    counts = collections.Counter(r["label"] for r in gold)

    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(gold)
    buf.write("# FROZEN gold set. Semantics: panel_a_paired_change.step_estimate.\n")
    for k in sorted(counts):
        buf.write(f"# count_{k},{counts[k]}\n")
    buf.write(f"# n_gold,{len(gold)}\n")
    for k, v in prov.items():
        buf.write(f"# {k},{v}\n")
    if not a.dry_run:
        (QC / "panel_a_gold.csv").write_text(buf.getvalue(), encoding="utf-8",
                                             newline="")

    print(f"{'DRY RUN: ' if a.dry_run else ''}phase4/qc/panel_a_gold.csv — "
          f"{len(gold)} gold points")
    print(f"  {dict(sorted(counts.items()))}")
    print(f"  from {prov['n_label_rows']} label rows + {prov['n_verify_rows']} verify "
          f"rows; verify overturned {prov['n_overturned']}")
    if counts["nochange"] != 1169:
        print(f"\n  NOTE — correction to the record: the design doc asserts 1169 "
              f"no-change; the estimator's own semantics yield {counts['nochange']}.")
        print(f"  loss ({counts['loss']}) and gain ({counts['gain']}) are stable under "
              f"every verify convention tested. The discrepancy is recorded, not "
              f"reconciled by fiat.")
    print("\n  This set is SPENT — development only. 42 positives => recall sd 7.3 pp.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

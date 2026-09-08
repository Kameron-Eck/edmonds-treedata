"""heal_vs_gold.py — does healing fix false losses without laundering real ones?

THE TEST THAT DECIDES WHETHER THE HEALER IS WORTH HAVING. Bounded temporal backfill fills
absences the flanking epochs contradict. Two things can happen at a location where a human
has already ruled:

    THE WIN      a verified NO-CHANGE point currently shows a canopy -> gone -> canopy
                 trajectory. That is a detection failure, and healing should remove it.
    THE HARM     a verified LOSS point gets healed, so a real removal is filled back in
                 and the event disappears. This is the laundering failure the whole design
                 is gated against, and it must be ZERO.

Truth is `phase4/qc/panel_a_gold.csv` — 1,170 no-change / 42 loss / 2 gain, frozen with
the estimator's own semantics (`freeze_panel_a_gold.py`). It is a DEVELOPMENT set: 42
positives means held-out recall has sd 7.3 pp, so this instrument reports counts and
directions, never a precision that implies more resolution than 42 points carry.

WHAT THIS CAN AND CANNOT SETTLE, and the limit is structural rather than statistical.
Panel A ruled on 2016 -> 2024. The healer's HEAL tier fires only on 2011s, 2013 and 2015,
because every later bracket spans >= 3 years and is BLIND. So the HEAL tier operates
ENTIRELY UPSTREAM of the interval the gold covers, and the gold cannot score it directly.
What the gold CAN score is whether the healer's IGNORE marking censors verified events
inside its own interval, and whether the epochs it does touch carry spurious flicker at
locations a human called stable. Both are reported; the gap is named rather than papered
over, because a scorer that reports a number it cannot support is worse than one that
reports the gap.

Output: phase4/qc/heal_vs_gold.csv

Run:  py -3.12 qc/instruments/heal_vs_gold.py
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"
STACK = Path(r"D:\edmonds-pipeline\trend8_stack_2m.npz")


def _rows(p):
    if not Path(p).exists():
        return []
    body = [ln for ln in Path(p).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def build(stack=None):
    """`stack` defaults to the published 8-epoch cache. The healer is run on the SAME
    stack, so the gold trajectories and the overlays index one lattice — the closing
    baseline refuses anything else."""
    import numpy as np
    sys.path.insert(0, str(SCRIPTS / "qc" / "instruments"))  # ledger: test_status_discovery
    from temporal_heal import apply_heal, build as heal_build

    stack_path = Path(stack) if stack is not None else STACK
    gold = _rows(QC / "panel_a_gold.csv")
    if not gold:
        return None, None, "panel_a_gold.csv absent — run freeze_panel_a_gold.py"
    heal_rows, overlays, err = heal_build(stack=stack_path)
    if err:
        return None, None, err

    d = np.load(stack_path)
    stack, inside, tf = d["stack"], d["inside"], d["transform"]
    years = [str(y) for y in d["years"]]
    h, w = inside.shape

    # Gold points carry map coordinates; the stack is the analysis lattice.
    def cell(x, y):
        col = int((float(x) - tf[2]) / tf[0])
        row = int((float(y) - tf[5]) / tf[4])
        return (row, col) if (0 <= row < h and 0 <= col < w) else None

    healed = {}
    for i, yr in enumerate(years):
        ov = overlays.get(yr)
        if ov is None:
            healed[yr] = stack[i]
        else:
            healed[yr] = apply_heal(stack[i], ov["heal"], ov["ignore"])
    tiers = {r["epoch"]: r["tier"] for r in heal_rows}

    out, off = [], 0
    for g in gold:
        rc = cell(g["x"], g["y"])
        if rc is None or not inside[rc]:
            off += 1
            continue
        r, c = rc
        raw = [int(stack[i][r, c]) for i in range(len(years))]
        new = [int(healed[yr][r, c]) for yr in years]
        touched = [years[i] for i in range(len(years)) if raw[i] != new[i]]
        # an impossible triple: canopy -> gone -> canopy on consecutive valid epochs
        def triples(t):
            return sum(1 for i in range(1, len(t) - 1)
                       if t[i - 1] == 1 and t[i] == 0 and t[i + 1] == 1)
        # LAUNDERING, defined correctly. The first version counted any heal-to-canopy at
        # a loss point, which is wrong: all five hits were 2015 dropouts at points cut
        # LATER, where the tree is present on both flanks and the loss still stands at
        # the end. Filling an upstream detection failure is the operator working.
        # Laundering is filling the TERMINAL ABSENCE — the run of absent epochs the loss
        # itself created. Those are what a reader would call "the tree is gone".
        term = len(raw)
        while term > 0 and raw[term - 1] == 0:
            term -= 1
        laundered = sum(1 for i in range(term, len(raw))
                        if raw[i] == 0 and new[i] == 1)
        term_censored = sum(1 for i in range(term, len(raw))
                            if raw[i] == 0 and new[i] == 255)
        out.append({
            "point_id": g["point_id"], "label": g["label"],
            "terminal_absent_epochs": len(raw) - term,
            "terminal_laundered": laundered,
            "terminal_censored": term_censored,
            "raw_trajectory": "".join("C" if v == 1 else ("." if v == 0 else "x")
                                      for v in raw),
            "healed_trajectory": "".join("C" if v == 1 else ("." if v == 0 else "x")
                                         for v in new),
            "n_epochs_touched": len(touched),
            "epochs_touched": ",".join(touched),
            "tiers_touched": ",".join(sorted({tiers.get(e, "?") for e in touched})),
            "impossible_triples_raw": triples(raw),
            "impossible_triples_healed": triples(new),
            "healed_to_canopy": sum(1 for i in range(len(years))
                                    if raw[i] == 0 and new[i] == 1),
            "healed_to_ignore": sum(1 for i in range(len(years))
                                    if raw[i] == 0 and new[i] == 255),
        })
    return out, {"off_grid": off, "years": years}, None


OUT_CSV = QC / "heal_vs_gold.csv"


def _parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stack", default=str(STACK),
                    help="epoch stack the healer and the gold trajectories index "
                         "(default: the published 8-epoch cache)")
    ap.add_argument("--out", default=str(OUT_CSV),
                    help="where the table goes (default: the tracked heal_vs_gold.csv)")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv=None):
    from phase4seg.names import clean_argv
    a = _parser().parse_args(clean_argv() if argv is None else argv)

    rows, meta, err = build(stack=a.stack)
    if err:
        print(f"FATAL: {err}")
        return 2

    cols = list(rows[0].keys())
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)

    by = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        b = by[r["label"]]
        b["n"] += 1
        b["touched"] += int(r["n_epochs_touched"] > 0)
        b["to_canopy"] += int(r["healed_to_canopy"] > 0)
        b["to_ignore"] += int(r["healed_to_ignore"] > 0)
        b["triples_raw"] += r["impossible_triples_raw"]
        b["triples_healed"] += r["impossible_triples_healed"]
        b["triples_fixed"] += max(0, r["impossible_triples_raw"]
                                  - r["impossible_triples_healed"])
        b["laundered"] += r["terminal_laundered"]
        b["term_censored"] += r["terminal_censored"]
        b["has_terminal_absence"] += int(r["terminal_absent_epochs"] > 0)
    for lab in sorted(by):
        for k, v in by[lab].items():
            buf.write(f"# {lab}_{k},{v}\n")
    buf.write(f"# off_grid,{meta['off_grid']}\n")
    if not a.dry_run:
        Path(a.out).write_text(buf.getvalue(), encoding="utf-8", newline="")

    print(f"{'DRY RUN: ' if a.dry_run else ''}{a.out} "
          f"— {len(rows)} gold points scored, {meta['off_grid']} off-grid")
    print(f"\n{'label':10}{'n':>7}{'touched':>9}{'->canopy':>10}{'->ignore':>10}"
          f"{'triples raw':>13}{'healed':>9}{'fixed':>7}")
    for lab in ("nochange", "loss", "gain"):
        b = by.get(lab)
        if not b:
            continue
        print(f"{lab:10}{b['n']:>7}{b['touched']:>9}{b['to_canopy']:>10}"
              f"{b['to_ignore']:>10}{b['triples_raw']:>13}{b['triples_healed']:>9}"
              f"{b['triples_fixed']:>7}")

    loss = by.get("loss", collections.Counter())
    nc = by.get("nochange", collections.Counter())
    print("\nTHE TWO QUESTIONS")
    print(f"  HARM — verified losses LAUNDERED (the TERMINAL absence filled back in): "
          f"{loss['laundered']} of {loss['n']}   <- must be 0")
    print(f"         upstream dropouts healed at loss points: {loss['to_canopy']} — these "
          f"are NOT laundering.")
    print(f"         Each is a mid-series detection failure at a point cut LATER: the "
          f"tree is present on")
    print(f"         both flanks and the loss still stands at the end. The first version "
          f"of this metric")
    print(f"         counted them as harm, which was wrong.")
    print(f"  WIN  — impossible triples removed at verified NO-CHANGE: "
          f"{nc['triples_fixed']} of {nc['triples_raw']}")
    print(f"  censoring — verified losses with a TERMINAL cell marked IGNORE: "
          f"{loss['term_censored']} of {loss['n']}  (unknowable, never asserted away)")
    print("\n  STRUCTURAL LIMIT: Panel A ruled on 2016->2024; the HEAL tier fires only on"
          "\n  2011s/2013/2015, entirely upstream of that interval. The gold cannot score"
          "\n  the HEAL tier directly — it scores censoring and flicker, and the gap is"
          "\n  named rather than filled with a number it cannot support.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

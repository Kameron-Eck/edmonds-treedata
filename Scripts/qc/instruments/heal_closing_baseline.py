"""heal_closing_baseline.py — the dumbest fill rule, scored beside the healer. AUDIT ONLY.

THE QUESTION §14(d) LEFT OPEN. `Reports/LIT_HEALING_ANALOGUES_2026-09-08.md` §4.9 ranks
the 1-D morphological closing REFUTED as a healer and STANDS as the comparator baseline —
"the comparator any learned or tiered heal must beat", never yet run. The healer carries
three pieces of machinery the closing does not: a validated global shift per flank, a
28 m2 size floor (one mature crown), and the HEAL/REVIEW/BLIND tier that decides whether a
fill writes canopy or IGNORE. This file asks what those three buy, by running the closing
at the SAME gap caps with none of them and scoring both the same way.

THE OPERATOR. x • B_L along t: fill any interior 0-run flanked by 1 on both sides, subject
to a cap. NO size floor, NO alignment, NO lidar veto, NO tier — every admitted run is
filled with canopy. Extensive (never 1 -> 0), idempotent, nested in K (Breen, Jones &
Talbot 2000 Table 1 §3.2); all three are gated in `qc/test_heal_closing_baseline.py`.

FOUR CAPS, because the units disagree and the disagreement is the point:
  acq K          run length <= K acquisitions. The literal closing. K = 1 is the healer's
                 own candidate rule (one absent epoch) with the machinery stripped off.
  step_years K   every inter-acquisition step across the bracket <= K years. This is the
                 unit `temporal_heal.py::tier_for` actually uses (BLIND_GAP_YEARS = 3 on
                 max(y1-y0, y2-y1)), which the §4.9 skeptic's central objection names:
                 "the SE length is in samples; the project's constraint is in years".
  span_years K   total bracket span <= K years — the skeptic's own re-specification.
  tier_matched   acq <= 1 AND step_years <= 2. The healer's non-BLIND candidate set
                 exactly, minus alignment, floor and tier. THE equal-cap comparison.

THE CLOSING RUNS ON THE UNALIGNED STACK. The healer shifts each flank onto the gap epoch
by the validated global offset (r = 0.9457 vs imagery, 7.4 cm median) before testing the
bracket; the closing does not. Part of every fill-count difference below is that, not the
floor or the tier, and nothing here separates the two.

THE LAUNDERING CRITERION IS VACUOUS FOR BOTH, and that is a finding, not an obstacle.
`heal_vs_gold.py` defines laundering as filling the TERMINAL absence — the trailing run of
0s a real removal created. A both-sides rule needs a 1 AFTER the cell it fills; a terminal
cell has none, by definition of terminal. So laundered ≡ 0 and n_eligible ≡ 0 for the
closing at every K, for the healer, and for any both-sides rule anyone proposes.
`0 of 42 laundered` therefore certifies nothing about this family — it cannot fire.
That is §4.9 M7's "if n_eligible = 0 ... the rule degenerates to unbounded temporal hole
filling", shown rather than argued, and it is mutation-tested both ways in
`qc/test_heal_closing_baseline.py`: the terminal counter does NOT fire on an adversarial
input built to trip it, and the in-interval counter below DOES.

SO A SECOND COUNTER, ON THE POPULATION WHERE A FILL IS AN ASSERTION ABOUT THE VERIFIED
EVENT. `laundered_in_interval` counts verified LOSS POINTS filled at one or more epochs
strictly inside the panel's own interval (read from `panel_a_meta.json`; on the trend8
stack that is 2019 and 2021). Its at-risk denominator `n_eligible_in_interval` is the
number of loss points an UNBOUNDED both-sides rule could fill there — publish the pair,
never the count alone (§6 G2). BOTH ARE PER POINT, and the unit matters: a point whose
absent run spans two interior epochs is filled twice but counted ONCE, so the count can
never exceed its denominator. (Until 2026-09-08 the numerator counted per (point, epoch)
fill EVENT against a per-point denominator — invisible on the 8-epoch stack, where no
eligible loss is filled at two interior epochs, and 13 of 12 on the 10-epoch trial.)
Cells filled, if wanted, are `loss_cells_filled`. This does not count the 5 upstream
fills `heal_vs_gold.py` correctly refuses to call laundering: those are 2015 dropouts at
points cut later, before the panel's window opens.

READ `laundered_in_interval` AS AN UPPER BOUND, NOT AN ERASURE COUNT. It is a NECESSARY
signature of laundering, not a sufficient one: a fill at an interior epoch asserts canopy
inside the verified window, but if the trajectory still ends absent the removal event
itself survives and a change detector still sees it. Distinguishing the two needs the
trajectory, which is why the CSV publishes the counts and `heal_vs_gold.csv` publishes the
shapes. Where it fires, go and read them.

SCORING IS heal_vs_gold's, RE-IMPLEMENTED, NOT RE-FACTORED. `heal_vs_gold.py` computes its
scores inline inside `build()`; there is no scoring function to import and this file
factors nothing out of it (it is another agent's file this session). Instead it calls that
module the way its own `main()` does — `heal_vs_gold.build()` — takes the per-point
`raw_trajectory` / `healed_trajectory` strings it publishes, and re-scores them here. The
re-implementation is checked against heal_vs_gold's OWN per-row numbers for every point
before any comparison is printed; a mismatch is reported and the table is refused.

Output: phase4/qc/heal_closing_baseline.csv

Run:  py -3.12 qc/instruments/heal_closing_baseline.py [--dry-run]
      py -3.12 qc/instruments/heal_closing_baseline.py --stack S.npz --heal H.csv --out O.csv
      (defaults regenerate the tracked CSV from the published 8-epoch cache)
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"
STACK = Path(r"D:\edmonds-pipeline\trend8_stack_2m.npz")
META_JSON = QC / "panel_a_meta.json"
HEAL_CSV = QC / "temporal_heal.csv"
OUT_CSV = QC / "heal_closing_baseline.csv"

CELL_M = 2.0
CANOPY, ABSENT, IGNORE = 1, 0, 255
_CODE = {"C": CANOPY, ".": ABSENT, "x": IGNORE}

# The caps swept. `acq` covers every run an 8-epoch series can hold; the year sweeps
# bracket temporal_heal.py::BLIND_GAP_YEARS = 3 on both sides so the tier's own cap is
# inside the curve rather than at its edge.
SWEEP = (("acq", (1, 2, 3, 4, 5, 6)),
         ("step_years", (1, 2, 3, 4, 5, 8)),
         ("span_years", (2, 3, 4, 5, 6, 8, 10, 15)),
         ("tier_matched", (0,)))


# ---------------------------------------------------------------- the operator

def admits(rule, K, i, j, yrs):
    """Does `rule` at cap K fill the 0-run at indices i..j, bracketed by i-1 and j+1?

    Pure, and shared by the trajectory closing and the citywide count so the two can
    never drift apart.
    """
    length = j - i + 1
    steps = [yrs[t + 1] - yrs[t] for t in range(i - 1, j + 1)]
    if rule == "acq":
        return length <= K
    if rule == "step_years":
        return max(steps) <= K
    if rule == "span_years":
        return yrs[j + 1] - yrs[i - 1] <= K
    if rule == "tier_matched":
        # temporal_heal.py::tier_for calls a bracket BLIND at max(y1-y0, y2-y1) >= 3,
        # and temporal_heal.py::build only ever tests ONE absent epoch. Both, no floor.
        return length <= 1 and max(steps) <= 2
    raise ValueError(f"unknown rule {rule!r}")


def close_1d(traj, yrs, rule, K):
    """The closing. Only 0 -> 1, only inside a run flanked by 1 on BOTH sides.

    IGNORE (255) neither brackets nor fills: a run containing one is not a 0-run, and a
    255 flank is not a detection. Nothing else is touched, so the result is extensive.
    """
    out = list(traj)
    n = len(traj)
    i = 0
    while i < n:
        if traj[i] != ABSENT:
            i += 1
            continue
        j = i
        while j + 1 < n and traj[j + 1] == ABSENT:
            j += 1
        if (i - 1 >= 0 and j + 1 < n
                and traj[i - 1] == CANOPY and traj[j + 1] == CANOPY
                and admits(rule, K, i, j, yrs)):
            for t in range(i, j + 1):
                out[t] = CANOPY
        i = j + 1
    return out


# ---------------------------------------------------------------- scoring (heal_vs_gold's)

def triples(t):
    """canopy -> gone -> canopy on consecutive epochs. heal_vs_gold.py::build::triples."""
    return sum(1 for i in range(1, len(t) - 1)
               if t[i - 1] == CANOPY and t[i] == ABSENT and t[i + 1] == CANOPY)


def terminal_index(raw):
    """First index of the trailing run of absences. heal_vs_gold.py::build, inline."""
    term = len(raw)
    while term > 0 and raw[term - 1] == ABSENT:
        term -= 1
    return term


def terminal_laundered(raw, new):
    term = terminal_index(raw)
    return sum(1 for i in range(term, len(raw))
               if raw[i] == ABSENT and new[i] == CANOPY)


def terminal_censored(raw, new):
    term = terminal_index(raw)
    return sum(1 for i in range(term, len(raw))
               if raw[i] == ABSENT and new[i] == IGNORE)


def filled_at(raw, new, idxs):
    """0 -> 1 writes restricted to a set of epoch indices."""
    return sum(1 for i in idxs if raw[i] == ABSENT and new[i] == CANOPY)


def canopy_only(raw, new):
    """`new` with the IGNORE writes reverted — the fill rule's CANOPY assertions alone.

    Needed for a fair triple count. `triples` tests `t[i] == 0`, so a cell marked 255
    stops being a triple's middle without anyone asserting a tree there. The healer's
    REVIEW/BLIND tiers write 255 by design and the closing has no such state, so
    comparing raw `triples_removed` credits the healer for a move the closing is not
    allowed to make. Both columns are published; this one is the like-for-like.
    """
    return [CANOPY if (r == ABSENT and n == CANOPY) else r for r, n in zip(raw, new)]


def score_arm(pairs, interior_idx):
    """One row's worth of counts, for whatever fill rule produced `pairs`.

    `pairs` is [(label, raw_list, new_list), ...]. The healer and every closing arm go
    through this one scorer, so no arm can be measured by a different code path.
    """
    agg = {
        "gold_cells_filled": 0, "gold_points_filled": 0,
        "loss_cells_filled": 0, "loss_points_filled": 0,
        "laundered_terminal": 0, "laundered_in_interval": 0,
        "nochange_triples_raw": 0, "nochange_triples_after": 0,
        "nochange_triples_after_canopy_only": 0,
        "loss_triples_raw": 0, "loss_triples_after": 0,
        "terminal_censored": 0,
    }
    for label, raw, new in pairs:
        nfill = filled_at(raw, new, range(len(raw)))
        agg["gold_cells_filled"] += nfill
        agg["gold_points_filled"] += int(nfill > 0)
        if label == "loss":
            agg["loss_cells_filled"] += nfill
            agg["loss_points_filled"] += int(nfill > 0)
            # PER POINT, like `n_eligible_terminal`. (`terminal_censored` stays in
            # cells: it has no published denominator and the healer's row reads it.)
            agg["laundered_terminal"] += int(terminal_laundered(raw, new) > 0)
            agg["terminal_censored"] += terminal_censored(raw, new)
            # PER POINT — the same unit as `eligibility`'s denominator. `filled_at`
            # sums over epochs; wrapping it in `> 0` is what keeps count <= n_eligible.
            agg["laundered_in_interval"] += int(filled_at(raw, new, interior_idx) > 0)
            agg["loss_triples_raw"] += triples(raw)
            agg["loss_triples_after"] += triples(new)
        elif label == "nochange":
            agg["nochange_triples_raw"] += triples(raw)
            agg["nochange_triples_after"] += triples(new)
            agg["nochange_triples_after_canopy_only"] += triples(canopy_only(raw, new))
    _finish(agg)
    return agg


def _finish(agg):
    agg["nochange_triples_removed"] = max(
        0, agg["nochange_triples_raw"] - agg["nochange_triples_after"])
    agg["nochange_triples_removed_canopy_only"] = max(
        0, agg["nochange_triples_raw"] - agg["nochange_triples_after_canopy_only"])


def eligibility(points, yrs, interior_idx):
    """The at-risk denominators, from the UNBOUNDED both-sides rule (§6 G2, §4.9 M7).

    A loss is at risk from a family iff SOME member of that family could fill it. The
    unbounded closing is the most permissive both-sides rule there is, so what it cannot
    reach, none of them can. Both counts are PER POINT (`> 0`), the unit `score_arm`'s
    `laundered_*` counters use: every closing arm fills only both-flanked 0-runs, the
    unbounded closing fills all of them, so an arm's per-point count is <= this by
    construction. The healer aligns its flanks and the closing does not, so for its row
    the inequality is CHECKED in `build()` rather than assumed.
    """
    n_term = n_int = 0
    for label, raw in points:
        if label != "loss":
            continue
        new = close_1d(raw, yrs, "acq", len(raw))
        n_term += int(terminal_laundered(raw, new) > 0)
        n_int += int(filled_at(raw, new, interior_idx) > 0)
    return n_term, n_int


# ---------------------------------------------------------------- citywide

def citywide_fills(stack, inside, yrs, rule, K, np):
    """Cells the closing would write across the whole city, at this cap.

    Every interior window (i..j) is enumerated once; a run bracketed by 1s on both sides
    is maximal by construction, so the windows partition the fillable set with no
    double-count. Uses the same `admits` as the trajectory closing.
    """
    n = len(yrs)
    total = 0
    for i in range(1, n - 1):
        for j in range(i, n - 1):
            if not admits(rule, K, i, j, yrs):
                continue
            m = (stack[i - 1] == CANOPY) & (stack[j + 1] == CANOPY) & inside
            for t in range(i, j + 1):
                m &= (stack[t] == ABSENT)
            total += int(m.sum()) * (j - i + 1)
    return total


# ---------------------------------------------------------------- the measurement

def _rows(p):
    p = Path(p)
    if not p.exists():
        return []
    body = [ln for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def _footer(p):
    out = {}
    for ln in Path(p).read_text(encoding="utf-8").splitlines():
        if ln.startswith("# ") and "," in ln:
            k, _, v = ln[2:].partition(",")
            out[k.strip()] = v.strip()
    return out


def decode(s):
    return [_CODE[c] for c in s]


def build(stack=None, heal_csv=None):
    """Sibling imports stay inside here (qc/instruments/CLAUDE.md): run directly the
    instruments dir is sys.path[0], while a test can still load this file by path and
    exercise every pure function above with no stack and no gold.

    `stack` / `heal_csv` default to the module constants (the published 8-epoch cache and
    the tracked temporal_heal.csv). The stack's epochs must be the epochs heal_vs_gold
    scored — its trajectories index this stack — so a mismatch is refused, not indexed."""
    import numpy as np
    stack_path = Path(stack) if stack is not None else STACK
    heal_path = Path(heal_csv) if heal_csv is not None else HEAL_CSV

    from heal_vs_gold import build as hvg_build      # called as its own main() calls it

    hvg_rows, hvg_meta, err = hvg_build(stack=stack_path)   # same lattice, by construction
    if err:
        return None, None, err
    meta = json.loads(META_JSON.read_text(encoding="utf-8"))
    years = hvg_meta["years"]
    yrs = [int(str(y)[:4]) for y in years]

    m = re.match(r"\s*(\d{4})\s*->\s*(\d{4})", str(meta.get("interval", "")))
    lo, hi = (int(m.group(1)), int(m.group(2))) if m else (yrs[0], yrs[-1])
    interior_idx = [i for i, y in enumerate(yrs) if lo < y < hi]

    points = [(r["label"], decode(r["raw_trajectory"])) for r in hvg_rows]

    # PARITY. Re-score heal_vs_gold's own healed trajectories with the functions above and
    # compare to the numbers it computed itself. The comparison table is refused if these
    # disagree, because then "scored exactly as heal_vs_gold scores the healer" is false.
    parity = []
    for r in hvg_rows:
        raw, new = decode(r["raw_trajectory"]), decode(r["healed_trajectory"])
        mine = (triples(raw), triples(new), terminal_laundered(raw, new),
                terminal_censored(raw, new), filled_at(raw, new, range(len(raw))))
        theirs = (int(r["impossible_triples_raw"]), int(r["impossible_triples_healed"]),
                  int(r["terminal_laundered"]), int(r["terminal_censored"]),
                  int(r["healed_to_canopy"]))
        if mine != theirs:
            parity.append((r["point_id"], mine, theirs))

    n_term, n_int = eligibility(points, yrs, interior_idx)
    d = np.load(stack_path)
    stack, inside = d["stack"], d["inside"]
    if [str(y) for y in d["years"]] != [str(y) for y in years]:
        return None, None, (f"{stack_path.name} epochs {[str(y) for y in d['years']]} "
                            f"!= heal_vs_gold's {list(years)} — the gold trajectories "
                            f"index a different stack")

    rows = []
    for rule, caps in SWEEP:
        for K in caps:
            agg = score_arm([(lab, raw, close_1d(raw, yrs, rule, K))
                             for lab, raw in points], interior_idx)
            cw = citywide_fills(stack, inside, yrs, rule, K, np)
            rows.append(_row("closing", rule, K, agg, n_term, n_int, cw, 0, len(points)))

    # The healer, beside them. Its per-point outcome is read from the trajectories
    # heal_vs_gold published, not re-derived; its citywide numbers from temporal_heal.csv.
    healer = score_arm([(r["label"], decode(r["raw_trajectory"]),
                         decode(r["healed_trajectory"])) for r in hvg_rows],
                       interior_idx)

    hf = _footer(heal_path) if heal_path.exists() else {}
    heal_rows = _rows(heal_path)
    heal_cw = int(hf.get("heal_tier_cells", 0))
    ign_cw = sum(int(r["healed_cells"]) for r in heal_rows if r["tier"] != "HEAL")
    rows.append(_row("healer", "tier_matched", 0, healer, n_term, n_int,
                     heal_cw, ign_cw, len(points)))

    # A count above its own denominator means the two are not the same unit. Refused,
    # never published: that is exactly the row the 10-epoch trial printed (13 of 12).
    over = [(r["arm"], r["rule"], r["K"], c, r[c], r[d_])
            for r in rows
            for c, d_ in (("laundered_in_interval", "n_eligible_in_interval"),
                          ("laundered_terminal", "n_eligible_terminal"))
            if r[c] > r[d_]]
    if over:
        return None, None, (f"count exceeds its denominator — not the same unit: "
                            f"{over[:3]}")

    # Does the healer's alignment move anything AT THIS RESOLUTION? temporal_heal.py
    # translates by whole cells, so a sub-cell shift is the identity. Measured from the
    # healer's own published shifts, not assumed.
    shift_cells = {}
    for r in heal_rows:
        shift_cells[r["epoch"]] = max(
            abs(int(round(float(r[c]) / CELL_M)))
            for c in ("shift_prev_dx_m", "shift_prev_dy_m",
                      "shift_next_dx_m", "shift_next_dy_m"))

    return rows, {"parity": parity, "years": years,
                  "interior": [years[i] for i in interior_idx],
                  "interval": meta.get("interval"), "n_points": len(points),
                  "shift_cells": shift_cells,
                  "n_eligible_terminal": n_term, "n_eligible_in_interval": n_int}, None


def _row(arm, rule, K, agg, n_term, n_int, cw, ign, npts):
    return {
        "arm": arm, "rule": rule, "K": K,
        "K_unit": {"acq": "acquisitions", "step_years": "years_per_step",
                   "span_years": "years_of_span",
                   "tier_matched": "acq<=1 & step<=2yr"}[rule],
        "n_gold_points": npts,
        "gold_cells_filled": agg["gold_cells_filled"],
        "gold_points_filled": agg["gold_points_filled"],
        "loss_cells_filled": agg["loss_cells_filled"],
        "loss_points_filled": agg["loss_points_filled"],
        "laundered_terminal": agg["laundered_terminal"],
        "n_eligible_terminal": n_term,
        "laundered_in_interval": agg["laundered_in_interval"],
        "n_eligible_in_interval": n_int,
        "terminal_censored": agg["terminal_censored"],
        "nochange_triples_raw": agg["nochange_triples_raw"],
        "nochange_triples_after": agg["nochange_triples_after"],
        "nochange_triples_removed": agg["nochange_triples_removed"],
        "nochange_triples_removed_canopy_only":
            agg["nochange_triples_removed_canopy_only"],
        "loss_triples_raw": agg["loss_triples_raw"],
        "loss_triples_after": agg["loss_triples_after"],
        "citywide_cells_filled": cw,
        "citywide_ha": round(cw * CELL_M ** 2 / 10000.0, 1),
        "citywide_cells_ignored": ign,
    }


def _parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stack", default=str(STACK),
                    help="epoch stack npz (default: the published 8-epoch cache)")
    ap.add_argument("--heal", default=str(HEAL_CSV),
                    help="temporal_heal.csv to read (default: the tracked one)")
    ap.add_argument("--out", default=str(OUT_CSV),
                    help="CSV to write (default: the tracked one)")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv=None):
    from phase4seg.names import clean_argv
    a = _parser().parse_args(clean_argv() if argv is None else argv)

    rows, meta, err = build(a.stack, a.heal)
    if err:
        print(f"FATAL: {err}")
        return 2

    cols = list(rows[0].keys())
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    buf.write(f"# panel_interval,{meta['interval']}\n")
    buf.write(f"# interior_epochs,{'|'.join(meta['interior'])}\n")
    buf.write(f"# n_eligible_terminal,{meta['n_eligible_terminal']}\n")
    buf.write(f"# n_eligible_in_interval,{meta['n_eligible_in_interval']}\n")
    buf.write(f"# scoring_parity_mismatches,{len(meta['parity'])}\n")
    buf.write("# closing_runs_on_the_unaligned_stack,1\n")
    if not a.dry_run:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(buf.getvalue(), encoding="utf-8", newline="")

    n_bad = len(meta["parity"])
    print(f"{'DRY RUN: ' if a.dry_run else ''}{a.out} "
          f"— {len(rows)} arms over {meta['n_points']:,} gold points")
    print("\nSCORING PARITY vs heal_vs_gold.py's own per-row numbers: "
          + ("OK — 0 mismatches" if n_bad == 0 else f"{n_bad} MISMATCHES"))
    if n_bad:
        for pid, mine, theirs in meta["parity"][:5]:
            print(f"    point {pid}: here {mine} vs heal_vs_gold {theirs}")
        print("  TABLE REFUSED — the two are not scoring the same thing.")
        return 3

    print(f"\n{'arm':8}{'rule':13}{'K':>3}{'fills':>8}{'pts':>5}"
          f"{'launder/elig term':>19}{'in-int':>9}"
          f"{'triples rm':>12}{'by fill':>9}{'left':>6}{'citywide':>11}{'ha':>9}")
    for r in rows:
        term = f"{r['laundered_terminal']}/{r['n_eligible_terminal']}"
        inint = f"{r['laundered_in_interval']}/{r['n_eligible_in_interval']}"
        print(f"{r['arm']:8}{r['rule']:13}{r['K']:>3}"
              f"{r['gold_cells_filled']:>8,}{r['gold_points_filled']:>5}"
              f"{term:>19}{inint:>9}"
              f"{r['nochange_triples_removed']:>12}"
              f"{r['nochange_triples_removed_canopy_only']:>9}"
              f"{r['nochange_triples_after']:>6}"
              f"{r['citywide_cells_filled']:>11,}{r['citywide_ha']:>9.1f}")
    print("  'triples rm' credits an IGNORE mark; 'by fill' counts only the ones a "
          "CANOPY\n  assertion removed. The closing has no IGNORE, so its two columns "
          "are equal by\n  construction and the healer's difference is what its tiers "
          "declined to assert.")

    sc = meta["shift_cells"]
    moved = {e: n for e, n in sc.items() if n}
    print(f"\nALIGNMENT, measured from temporal_heal.csv's own shifts: max whole-cell "
          f"translation\n  per epoch on the {CELL_M:g} m lattice = "
          f"{ {e: n for e, n in sorted(sc.items())} }")
    if not moved:
        print("  EVERY validated shift is under one cell and rounds to ZERO — the "
              "healer's alignment\n  is the identity at this resolution "
              "(temporal_heal.py::shift_mask translates whole cells).\n  So at an equal "
              "cap the healer minus the closing is the 28 m2 floor and the tier,\n  not "
              "the transform. The transform is a claim about native-resolution masks.")

    print(f"\n  Panel interval {meta['interval']}; epochs strictly inside it on this "
          f"stack: {', '.join(meta['interior']) or 'NONE'}")
    print(f"  n_eligible_terminal = {meta['n_eligible_terminal']} — a both-sides rule "
          f"needs a 1 AFTER the cell it fills\n  and a terminal absence has none, so the "
          f"laundered-loss criterion CANNOT FIRE for any\n  member of this family. "
          f"0 of 42 certifies nothing here (§4.9 M7, §6 G2).")
    print(f"  n_eligible_in_interval = {meta['n_eligible_in_interval']} — losses an "
          f"unbounded both-sides rule could fill\n  on an epoch inside the verified "
          f"window. That is the denominator the in-interval count\n  belongs to; with a "
          f"denominator this small the criterion resolves little either.")
    print("  That count is an UPPER BOUND: asserting canopy inside the window is a "
          "necessary\n  signature of laundering, not a sufficient one — a trajectory "
          "that still ends absent\n  keeps its removal event. Read the shapes in "
          "heal_vs_gold.csv wherever it fires.")
    print("\n  The healer's citywide column is its HEAL-tier canopy only; "
          "citywide_cells_ignored\n  is what its REVIEW/BLIND tiers marked unknowable "
          "instead of asserting. The closing\n  has no IGNORE state — every admitted run "
          "becomes canopy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

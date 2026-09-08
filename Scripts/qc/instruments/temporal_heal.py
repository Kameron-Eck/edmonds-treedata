"""temporal_heal.py — bounded temporal backfill: heal absences the flanking epochs contradict.

WHAT THIS IS. A canopy cell that reads present → absent → present across three epochs is
almost certainly a DETECTION failure in the middle epoch, not a tree that vanished and
returned. This operator heals those, one-directionally, under evidence gates. It is the
first stage of the change detector.

THE LICENSE, measured rather than assumed:
  * The error is ONE-SIDED. At a held precision, recall tracks reported canopy at
    r = 0.9089 (phase4/qc/sensitivity_sawtooth.csv) and the flicker census shows three
    non-vegetated parcels holding 0.0-0.7% false canopy flat across all eight years. The
    model misses real trees; it does not invent them on bare ground. An asymmetric error
    is the only kind an asymmetric correction may address — and it is why the symmetric
    median-3 failed (correlation -0.999 with deviation-from-neighbour-mean).
  * Alignment uses ONE GLOBAL SHIFT per epoch pair. §11 validated it against imagery at
    r = 0.9457, 7.4 cm median error; §13 established that the local field, while genuine
    geometry (composes at r = 0.5857, 55/56 triples beat shuffle), is smaller than our
    ability to estimate it and does not beat a constant. One degree of freedom, validated.
  * NO SCALE PARAMETER. On crowns every epoch sees, measured extent differs by 2.3%
    worst-to-best (phase4/qc/detectability_curve.csv). Epochs differ in WHICH crowns they
    find, not how well they outline them. A fitted scale would have nothing to fit and
    would be free to absorb the sensitivity difference it is supposed to reveal.

THE GUARANTEE. `apply_heal` writes ONLY 0 -> 1 or 0 -> 255. It can never write 1 -> 0.
Crown cover is therefore monotone non-decreasing under healing and no consumer can see a
downward move caused by it. Gated in qc/test_temporal_heal.py against random inputs.

THE OUTPUT RESTRICTION, and it is not negotiable. Interior epochs can be healed; the
ENDPOINTS CANNOT — they have one side only, and 2024 is the worst-recall epoch in the
series. Healed masks feeding the annual fraction series would lift every interior year
while the endpoints stayed put, manufacturing decline on 2016->2024, the headline
interval. That is the smoothing trap's mirror image and harder to catch because it moves
the number the way we expect. **Healed output feeds per-location trajectories, validity
intervals (CLAUDE.md 3.8) and change maps. It never feeds the annual canopy fraction.**
Every written overlay carries HEALED_OVERLAY=1 so a consumer cannot mistake it.

TIERS, because not every candidate deserves the same confidence:
  HEAL          bracket ends on or before 2016, so a lidar epoch exists that could have
                vetoed a real removal, and none did.
  REVIEW        bracket lies entirely after 2016. No lidar downstream. A real clearing
                followed by post-clearing grass or blackberry read as canopy produces this
                exact pattern (flicker census: the instability IS sensitivity on real
                vegetation), and nothing in the mask can distinguish it. Flagged, never
                applied silently.
  BLIND         the bracket spans >= 3 years on at least one side. Bigleaf maple coppice
                reaches a 6.5 m crown in three years and trend8's largest gaps are exactly
                three, so a real cut-and-regrow can hide inside the window.

Output: phase4/qc/temporal_heal.csv, plus per-epoch overlays when --write-overlays.

Run:  py -3.12 qc/instruments/temporal_heal.py [--min-area 28] [--dry-run]
      py -3.12 qc/instruments/temporal_heal.py --stack other.npz --out other.csv
      (the defaults regenerate the tracked CSV from the published 8-epoch cache; a wider
       stack — heal_stack_build.py — goes through --stack/--out and never moves them)
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"
STACK = Path(r"D:\edmonds-pipeline\trend8_stack_2m.npz")
OUT_CSV = QC / "temporal_heal.csv"

CELL_M = 2.0
MIN_AREA_M2 = 28.0        # one mature crown (6 m disc) — the scale the sieve targets
LIDAR_LAST = 2016         # the last epoch a lidar veto could apply to
BLIND_GAP_YEARS = 3       # coppice can cross a gap this large (Silvics: 6.5 m in 3 yr)

HEALED = 1
HEALED_IGNORE = 255


def _year_int(label):
    return int(str(label)[:4])


def _import_machinery():
    sys.path.insert(0, str(SCRIPTS / "qc" / "instruments"))  # ledger: test_status_discovery
    from placement_accuracy import clusters, matched_pairs
    return clusters, matched_pairs


def global_shift(ca, cb, matched_pairs):
    """ONE median displacement a->b over unambiguous mutual matches, in metres."""
    import numpy as np
    pairs = matched_pairs(ca, cb)
    if len(pairs) < 50:
        return None, 0
    d = np.array([cb["xy"][k] - ca["xy"][i] for i, k in pairs])
    return (float(np.median(d[:, 0])), float(np.median(d[:, 1]))), len(pairs)


def shift_mask(mask, dx_m, dy_m):
    """Translate a boolean mask by whole cells. +x is +col; +y is -row (negative y scale)."""
    import numpy as np
    cj, ci = int(round(dx_m / CELL_M)), -int(round(dy_m / CELL_M))
    if ci == 0 and cj == 0:
        return mask
    out = np.zeros_like(mask)
    h, w = mask.shape
    r0, r1 = max(0, ci), min(h, h + ci)
    c0, c1 = max(0, cj), min(w, w + cj)
    if r1 <= r0 or c1 <= c0:
        return out
    out[r0:r1, c0:c1] = mask[r0 - ci:r1 - ci, c0 - cj:c1 - cj]
    return out


def apply_heal(base, overlay_heal, overlay_ignore):
    """THE GUARANTEE, in one function: only 0 -> 1 and 0 -> 255 are ever written.

    Never 1 -> 0, never 255 -> 0, never 1 -> 255. Anything else is a bug and the gate
    in qc/test_temporal_heal.py proves it on random inputs.
    """
    out = base.copy()
    writable = base == 0
    out[writable & overlay_heal] = HEALED
    out[writable & overlay_ignore & ~overlay_heal] = HEALED_IGNORE
    return out


def tier_for(prev_label, epoch_label, next_label):
    """HEAL / REVIEW / BLIND from the bracket alone — no per-cell evidence needed.

    BLIND dominates: a bracket wide enough for coppice to cross cannot be trusted no
    matter what a lidar epoch says about its ends. On the trend8 cadence every post-2016
    bracket is ALSO >= 3 years wide, so REVIEW never fires here — that is a fact about
    the archive's flight schedule, not dead logic, and it returns the moment a denser
    epoch (2020, 2022) joins the stack.
    """
    y0, y1, y2 = (_year_int(prev_label), _year_int(epoch_label),
                  _year_int(next_label))
    if max(y1 - y0, y2 - y1) >= BLIND_GAP_YEARS:
        return "BLIND"
    return "HEAL" if y2 <= LIDAR_LAST else "REVIEW"


def build(min_area_m2=MIN_AREA_M2, stack=None):
    """`stack` None resolves the module global STACK at CALL time, so a caller that
    rebinds `temporal_heal.STACK` (heal_fill_audit_sample.py::build) is still honoured."""
    import numpy as np
    from scipy import ndimage
    stack_path = Path(stack) if stack is not None else STACK
    if not stack_path.exists():
        return None, None, f"{stack_path} not found (local mirror)"
    clusters, matched_pairs = _import_machinery()
    d = np.load(stack_path)
    stack, inside, tf = d["stack"], d["inside"], d["transform"]
    years = [str(y) for y in d["years"]]

    cl = {y: clusters(stack[i] == 1, inside, tf) for i, y in enumerate(years)}
    min_cells = int(round(min_area_m2 / (CELL_M ** 2)))
    rows, overlays = [], {}

    for t in range(1, len(years) - 1):
        y, yp, yn = years[t], years[t - 1], years[t + 1]
        valid = (stack[t] != 255) & (stack[t - 1] != 255) & (stack[t + 1] != 255) & inside
        prev_c, next_c = stack[t - 1] == 1, stack[t + 1] == 1

        # Align each flank onto epoch t with its own validated global shift.
        sp = sn = (0.0, 0.0)
        npair_p = npair_n = 0
        if cl[yp] is not None and cl[y] is not None:
            s, n_ = global_shift(cl[yp], cl[y], matched_pairs)
            if s:
                sp, npair_p = s, n_
        if cl[yn] is not None and cl[y] is not None:
            s, n_ = global_shift(cl[yn], cl[y], matched_pairs)
            if s:
                sn, npair_n = s, n_
        prev_a = shift_mask(prev_c, *sp)
        next_a = shift_mask(next_c, *sn)

        # THE CANDIDATE: absent at t, present on BOTH aligned flanks, all three valid.
        cand = (stack[t] == 0) & prev_a & next_a & valid
        lab, n = ndimage.label(cand, structure=np.ones((3, 3), int))
        if n:
            sizes = np.bincount(lab.ravel())
            big = np.where(sizes >= min_cells)[0]
            big = big[big > 0]
            keep = np.isin(lab, big)
        else:
            keep = np.zeros_like(cand)

        gap_left = _year_int(y) - _year_int(yp)
        gap_right = _year_int(yn) - _year_int(y)
        tier = tier_for(yp, y, yn)

        # Only the HEAL tier writes canopy. REVIEW and BLIND write IGNORE — the cell is
        # marked unknowable rather than asserted either way (CLAUDE.md 3.6).
        overlays[y] = {"heal": keep if tier == "HEAL" else np.zeros_like(keep),
                       "ignore": keep if tier != "HEAL" else np.zeros_like(keep),
                       "tier": tier}
        n_cells = int(keep.sum())
        rows.append({
            "epoch": y, "prev": yp, "next": yn, "tier": tier,
            "gap_left_yr": gap_left, "gap_right_yr": gap_right,
            "shift_prev_dx_m": round(sp[0], 3), "shift_prev_dy_m": round(sp[1], 3),
            "shift_next_dx_m": round(sn[0], 3), "shift_next_dy_m": round(sn[1], 3),
            "n_match_prev": npair_p, "n_match_next": npair_n,
            "candidate_cells_raw": int(cand.sum()),
            "healed_cells": n_cells,
            "healed_ha": round(n_cells * (CELL_M ** 2) / 10000.0, 2),
            "healed_pp_of_city": round(100.0 * n_cells / max(int(inside.sum()), 1), 3),
            "n_components": int(len(big)) if n else 0,
        })
    return rows, overlays, None


def _parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-area", type=float, default=MIN_AREA_M2,
                    help="minimum healed component, m2 (default one mature crown)")
    ap.add_argument("--stack", default=str(STACK),
                    help="epoch stack npz (default: the published 8-epoch cache)")
    ap.add_argument("--out", default=str(OUT_CSV),
                    help="CSV to write (default: the tracked phase4/qc/temporal_heal.csv)")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv=None):
    from phase4seg.names import clean_argv
    a = _parser().parse_args(clean_argv() if argv is None else argv)

    rows, overlays, err = build(a.min_area, a.stack)
    if err:
        print(f"FATAL: {err}")
        return 2

    cols = list(rows[0].keys())
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    tot = sum(r["healed_cells"] for r in rows if r["tier"] == "HEAL")
    buf.write(f"# min_area_m2,{a.min_area}\n")
    buf.write(f"# heal_tier_cells,{tot}\n")
    for tier in ("HEAL", "REVIEW", "BLIND"):
        buf.write(f"# n_epochs_{tier},{sum(1 for r in rows if r['tier'] == tier)}\n")
    if not a.dry_run:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(buf.getvalue(), encoding="utf-8", newline="")

    print(f"{'DRY RUN: ' if a.dry_run else ''}{a.out} "
          f"(min component {a.min_area:.0f} m2 = one mature crown; stack {a.stack})")
    print(f"\n{'epoch':7}{'bracket':16}{'tier':8}{'shift prev':>12}{'shift next':>12}"
          f"{'cand':>9}{'healed':>9}{'ha':>8}{'pp':>7}")
    for r in rows:
        sp = f"{r['shift_prev_dx_m']:+.1f},{r['shift_prev_dy_m']:+.1f}"
        sn = f"{r['shift_next_dx_m']:+.1f},{r['shift_next_dy_m']:+.1f}"
        print(f"{r['epoch']:7}{r['prev'] + '-' + r['next']:16}{r['tier']:8}"
              f"{sp:>12}{sn:>12}{r['candidate_cells_raw']:>9,}"
              f"{r['healed_cells']:>9,}{r['healed_ha']:>8.1f}"
              f"{r['healed_pp_of_city']:>7.2f}")

    print(f"\n  HEAL tier writes canopy: {tot:,} cells "
          f"({tot * 4 / 10000:.1f} ha). REVIEW and BLIND write IGNORE — the cell is "
          f"marked unknowable, never asserted.")
    print(f"  size filter dropped "
          f"{sum(r['candidate_cells_raw'] - r['healed_cells'] for r in rows):,} cells "
          f"below one mature crown — boundary jitter, not trees.")
    print("\n  OUTPUT RESTRICTION: trajectories, validity intervals and change maps ONLY."
          "\n  Never the annual fraction series — endpoints cannot be healed and the bias "
          "would not cancel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

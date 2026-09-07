"""local_field_transitivity.py — is the local displacement field GEOMETRY, or correlated noise?

THE OPEN QUESTION. `placement_accuracy.py` showed that a local displacement estimate (median
over the k nearest matched cluster pairs) beats a single global shift in 6 of 7 epochs, and
beats even the best possible constant translation in 4 of 7. So spatial structure exists in
the mask-derived field. What that measurement CANNOT say is whether the structure is
geometry — each epoch genuinely warped relative to the others — or spatially correlated
detection noise, since mergers and splits cluster in dense stands and would lower
leave-one-out error without being displacement at all. That distinction was left
UNDETERMINED, and it gates whether a transplant may use a local transform.

THE TEST, and it needs no imagery. **Geometry composes; pairing artifacts do not.**

If each epoch carries a real local warp W(x) relative to some common truth, then for any
three epochs A, B, R the local displacements must satisfy

        d_AB(x)  =  d_AR(x) - d_BR(x)

at every location x, because both sides equal W_A(x) - W_B(x). The A-B field is never
consulted when building the A-R and B-R fields, so agreement is a genuine out-of-sample
prediction about a third measurement.

If instead the local structure is an artifact of MATCHING — dense stands producing
correlated merge/split errors — it belongs to the PAIR, not to the epochs. A-B's artifact
has no reason to equal A-R's minus B-R's, and composition fails.

THE NULL. Composition could hold trivially if every field were near-zero, or if the fields
were dominated by one global constant. So the observed agreement is compared against two
nulls: (1) SHUFFLE — the same cell values re-assigned to random cells, which destroys
spatial correspondence while preserving every distribution; (2) GLOBAL-ONLY — replace each
local field with its own global median, which is what "there is no local structure" would
predict. Passing means beating BOTH.

Output: phase4/qc/local_field_transitivity.csv

Run:  py -3.12 qc/instruments/local_field_transitivity.py [--cell 200]
"""
from __future__ import annotations

import argparse
import csv
import io
import itertools
import statistics as st
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"
STACK = Path(r"D:\edmonds-pipeline\trend8_stack_2m.npz")

MIN_PAIRS_PER_CELL = 12       # below this a cell median is noise
CELL_M_DEFAULT = 400.0   # 200 m starved the test: only 1 triple had 20 co-populated cells
N_SHUFFLE = 400


def _import_machinery():
    """One home for clustering and matching — imported, never re-implemented."""
    sys.path.insert(0, str(SCRIPTS / "qc" / "instruments"))  # ledger: test_status_discovery
    from placement_accuracy import clusters, matched_pairs
    return clusters, matched_pairs


def cell_field(ca, cb, pairs, cell_m):
    """Median displacement per spatial cell, keyed by the DONOR centroid's cell."""
    import numpy as np
    acc = {}
    for i, k in pairs:
        x, y = ca["xy"][i]
        key = (int(x // cell_m), int(y // cell_m))
        acc.setdefault(key, []).append(cb["xy"][k] - ca["xy"][i])
    out = {}
    for key, v in acc.items():
        if len(v) >= MIN_PAIRS_PER_CELL:
            arr = np.asarray(v)
            out[key] = (float(np.median(arr[:, 0])), float(np.median(arr[:, 1])),
                        len(v))
    return out


def pearson(xs, ys):
    if len(xs) < 4:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (len(xs) * sx * sy)


def build(cell_m=CELL_M_DEFAULT, seed=20260906):
    import numpy as np
    if not STACK.exists():
        return None, f"{STACK} not found (local mirror)"
    clusters, matched_pairs = _import_machinery()
    d = np.load(STACK)
    stack, inside, tf = d["stack"], d["inside"], d["transform"]
    years = [str(y) for y in d["years"]]
    cl = {y: clusters(stack[i] == 1, inside, tf) for i, y in enumerate(years)}
    usable = [y for y in years if cl[y] is not None]

    fields, rows = {}, []
    for a, b in itertools.permutations(usable, 2):
        pairs = matched_pairs(cl[a], cl[b])
        if len(pairs) >= 200:
            fields[(a, b)] = cell_field(cl[a], cl[b], pairs, cell_m)

    rng = np.random.default_rng(seed)
    for A, B, R in itertools.combinations(usable, 3):
        f_ab, f_ar, f_br = fields.get((A, B)), fields.get((A, R)), fields.get((B, R))
        if not (f_ab and f_ar and f_br):
            continue
        keys = sorted(set(f_ab) & set(f_ar) & set(f_br))
        if len(keys) < 20:
            continue
        obs_x = [f_ab[k][0] for k in keys]
        obs_y = [f_ab[k][1] for k in keys]
        pred_x = [f_ar[k][0] - f_br[k][0] for k in keys]
        pred_y = [f_ar[k][1] - f_br[k][1] for k in keys]

        r_obs = pearson(obs_x + obs_y, pred_x + pred_y)
        resid = [abs(o - p) for o, p in
                 zip(obs_x + obs_y, pred_x + pred_y)]
        spread = [abs(v) for v in obs_x + obs_y]

        # NULL 1 — shuffle the predicted field across cells (kills correspondence,
        # keeps every distribution).
        null = []
        for _ in range(N_SHUFFLE):
            idx = rng.permutation(len(keys))
            sx = [pred_x[i] for i in idx]
            sy = [pred_y[i] for i in idx]
            v = pearson(obs_x + obs_y, sx + sy)
            if v is not None:
                null.append(v)
        p_shuffle = (sum(1 for v in null if v >= (r_obs or -9)) + 1) / (len(null) + 1)

        # NULL 2 — global-only: predict every cell with the composed GLOBAL medians.
        gx = st.median([f_ar[k][0] for k in keys]) - st.median([f_br[k][0] for k in keys])
        gy = st.median([f_ar[k][1] for k in keys]) - st.median([f_br[k][1] for k in keys])
        resid_global = ([abs(o - gx) for o in obs_x] + [abs(o - gy) for o in obs_y])

        rows.append({
            "A": A, "B": B, "R": R, "n_cells": len(keys),
            "r_composed_vs_observed": None if r_obs is None else round(r_obs, 4),
            "median_resid_composed_m": round(st.median(resid), 4),
            "median_resid_globalonly_m": round(st.median(resid_global), 4),
            "median_abs_field_m": round(st.median(spread), 4),
            "p_shuffle": round(p_shuffle, 5),
        })
    return rows, None


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cell", type=float, default=CELL_M_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    rows, err = build(a.cell)
    if err:
        print(f"FATAL: {err}")
        return 2
    if not rows:
        print("no triple had enough co-populated cells — try a larger --cell")
        return 1

    cols = ["A", "B", "R", "n_cells", "r_composed_vs_observed",
            "median_resid_composed_m", "median_resid_globalonly_m",
            "median_abs_field_m", "p_shuffle"]
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    rs_ = [r["r_composed_vs_observed"] for r in rows
           if r["r_composed_vs_observed"] is not None]
    beats_ = sum(1 for r in rows
                 if r["median_resid_composed_m"] < r["median_resid_globalonly_m"])
    ps_ = [r["p_shuffle"] for r in rows]
    for k, v in (("median_r_composed", round(st.median(rs_), 4)),
                 ("median_resid_composed_m",
                  round(st.median([r["median_resid_composed_m"] for r in rows]), 4)),
                 ("median_resid_globalonly_m",
                  round(st.median([r["median_resid_globalonly_m"] for r in rows]), 4)),
                 ("n_triples", len(rows)),
                 ("n_triples_composed_beats_global", beats_),
                 ("n_triples_shuffle_p_lt_05",
                  sum(1 for x in ps_ if x < 0.05))):
        buf.write(f"# {k},{v}\n")
    if not a.dry_run:
        (QC / "local_field_transitivity.csv").write_text(buf.getvalue(),
                                                         encoding="utf-8", newline="")

    rs = [r["r_composed_vs_observed"] for r in rows
          if r["r_composed_vs_observed"] is not None]
    rc = [r["median_resid_composed_m"] for r in rows]
    rg = [r["median_resid_globalonly_m"] for r in rows]
    ps = [r["p_shuffle"] for r in rows]
    beats = sum(1 for r in rows
                if r["median_resid_composed_m"] < r["median_resid_globalonly_m"])

    print(f"{'DRY RUN: ' if a.dry_run else ''}phase4/qc/local_field_transitivity.csv "
          f"— {len(rows)} epoch triples, cell {a.cell:.0f} m")
    print(f"\n{'A':7}{'B':7}{'R':7}{'cells':>7}{'r':>8}{'resid':>8}"
          f"{'global':>8}{'p_shuf':>9}")
    for r in sorted(rows, key=lambda x: -(x["r_composed_vs_observed"] or -9))[:10]:
        print(f"{r['A']:7}{r['B']:7}{r['R']:7}{r['n_cells']:>7}"
              f"{r['r_composed_vs_observed']:>8.3f}{r['median_resid_composed_m']:>8.3f}"
              f"{r['median_resid_globalonly_m']:>8.3f}{r['p_shuffle']:>9.4f}")
    if len(rows) > 10:
        print(f"   … {len(rows) - 10} more triples in the CSV")

    # TWO QUESTIONS, and they have different answers. Reporting one verdict conflated
    # them on the first run: whether the structure is REAL and whether it is USEFUL are
    # separate, and the honest result is yes to the first and no to the second.
    n_sig = sum(1 for p in ps if p < 0.05)
    print("\nQ1 — IS THE LOCAL STRUCTURE A PROPERTY OF THE EPOCHS? (composition vs shuffle)")
    print(f"  median r(composed, observed)        {st.median(rs):+.3f}")
    print(f"  median shuffle p                    {st.median(ps):.4f}   "
          f"({n_sig}/{len(ps)} triples below 0.05)")
    q1 = st.median(rs) > 0.3 and n_sig > 0.8 * len(ps)
    print("  -> " + ("YES. The A-B field is predicted by the A-R and B-R fields, which "
                     "never saw it. Geometry composes; a pairing artifact would not."
                     if q1 else
                     "NO. Composition is no better than shuffled correspondence."))

    print("\nQ2 — IS IT WORTH USING? (composition vs a global constant)")
    print(f"  median residual, composed           {st.median(rc):.3f} m")
    print(f"  median residual, global-only        {st.median(rg):.3f} m")
    print(f"  triples where composed beats global {beats}/{len(rows)}")
    q2 = beats > 0.6 * len(rows) and st.median(rc) < st.median(rg)
    print("  -> " + ("YES — the local field predicts better than one constant."
                     if q2 else
                     "NO. The structure is real but its magnitude is under the noise of a "
                     "per-cell median, so a single constant predicts as well or better."))

    print("\n  VERDICT: " + (
        "USE THE LOCAL FIELD" if (q1 and q2) else
        "CAP AT ONE SHIFT PER EPOCH PAIR — the local structure is real (Q1) but not "
        "exploitable at the precision we can estimate it (Q2). Use the imagery-validated "
        "global shift; do not spend a degree of freedom on a field that does not pay."
        if q1 else
        "TREAT AS ARTIFACT — no evidence the structure belongs to the epochs at all."))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""landmark_transform_gate.py — does a mask-derived transform track GEOMETRY or SENSITIVITY?

THE GATE THIS IS. On 2026-09-06 a block-wise offset estimated from mask agreement was
falsified: it correlated with per-epoch p68 registration scatter at r = -0.245 (the WRONG
sign) and with matched-cut recall at r = -0.450. It was measuring how much each year's
detector missed and calling that displacement, then applying it — which erased verified
losses. Reports/TEMPORAL_REFINEMENT_DESIGN_2026-09-06.md §3.

Kam's revision conditions on MUTUAL DETECTION before estimating anything: match clusters
that BOTH epochs found, snap those, and derive the transform only from matched pairs. A
crown one epoch missed is not a landmark, so it cannot pull the fit. This instrument tests
whether that revision actually fixes the contamination, BEFORE anything is built on it —
CLAUDE.md 3.4c applied before the fact rather than after.

THE TEST, and it is falsifiable in both directions:

    PASS  the landmark shift tracks MEASURED registration (phase4/qc/coregistration.csv)
          with the right sign, and does NOT track recall.
    FAIL  it tracks recall, or fails to track registration — the same contamination in
          new clothes, learned for the cost of an afternoon instead of a build.

METHOD. Landmarks are connected components of a single epoch's canopy mask whose area
falls between one mature crown (28 m2, a 6 m disc) and 1 ha. The lower bound keeps noise
specks out; the upper bound excludes the percolating blobs — 66-93 components per epoch
exceed 1 ha and hold 55-69% of the canopy area, so they are the objects a watershed rule
would have to split and are deliberately not used here. That leaves thousands of
crown-to-stand-scale landmarks per epoch with no watershed required, which is the point:
if the mechanism fails on the easy objects it will not be rescued by better segmentation.

Each epoch is matched against ONE reference epoch (2021 by default — the best-registered
in the series, p68 0.857 m). A match requires mutual nearest neighbour within a distance
cap, a compatible area ratio, and no ambiguous runner-up. The estimated shift is the
median displacement over matched pairs; the median resists the tail of genuinely moved or
mis-paired objects.

The PREDICTION being tested is independent of the masks entirely: coregistration.py
measures each epoch against the 2020s anchor from IMAGERY chips, so epoch e relative to
reference R should read (median_dx_e - median_dx_R, median_dy_e - median_dy_R).

Output: phase4/qc/landmark_transform_gate.csv

Run:  py -3.12 qc/instruments/landmark_transform_gate.py [--reference 2021]
"""
from __future__ import annotations

import argparse
import csv
import io
import statistics as st
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
REPO = SCRIPTS.parent
QC = REPO / "phase4" / "qc"
STACK = Path(r"D:\edmonds-pipeline\trend8_stack_2m.npz")

MIN_AREA_M2 = 28.0        # a 6 m disc — one mature crown
MAX_AREA_M2 = 10000.0     # 1 ha — above this the components percolate
MATCH_RADIUS_M = 8.0      # generous vs the worst measured p68 (3.94 m)
AREA_RATIO = (0.5, 2.0)   # a landmark may not double or halve and still be the same object
AMBIGUITY = 1.5           # reject if the runner-up is within this factor of the winner


def _rows(p):
    if not Path(p).exists():
        return []
    body = [ln for ln in Path(p).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(body))


def landmarks(mask, inside, tf):
    """Centroids (map coords) and areas of crown-to-stand-scale components."""
    import numpy as np
    from scipy import ndimage
    lab, n = ndimage.label(mask & inside, structure=np.ones((3, 3), int))
    if n == 0:
        return np.zeros((0, 2)), np.zeros(0)
    counts = np.bincount(lab.ravel())
    area = counts * 4.0                              # 2 m cells
    keep = np.where((area >= MIN_AREA_M2) & (area <= MAX_AREA_M2))[0]
    keep = keep[keep > 0]
    if keep.size == 0:
        return np.zeros((0, 2)), np.zeros(0)
    cent = ndimage.center_of_mass(mask & inside, lab, keep)   # (row, col)
    cent = np.asarray(cent, dtype=float)
    x = tf[2] + tf[0] * (cent[:, 1] + 0.5)
    y = tf[5] + tf[4] * (cent[:, 0] + 0.5)
    return np.column_stack([x, y]), area[keep]


def estimate_shift(pa, aa, pb, ab):
    """Median displacement a->b over unambiguous mutual matches. Returns (dx, dy, n)."""
    import numpy as np
    from scipy.spatial import cKDTree
    if len(pa) == 0 or len(pb) == 0:
        return None, None, 0
    tb = cKDTree(pb)
    d, j = tb.query(pa, k=2, distance_upper_bound=MATCH_RADIUS_M)
    ta = cKDTree(pa)
    d2, i2 = ta.query(pb, k=1, distance_upper_bound=MATCH_RADIUS_M)

    dx, dy = [], []
    for i in range(len(pa)):
        if not np.isfinite(d[i, 0]) or j[i, 0] >= len(pb):
            continue
        if np.isfinite(d[i, 1]) and d[i, 1] < AMBIGUITY * max(d[i, 0], 1e-6):
            continue                                   # ambiguous runner-up
        k = j[i, 0]
        if i2[k] != i:                                 # not mutual
            continue
        r = ab[k] / aa[i] if aa[i] > 0 else 0
        if not (AREA_RATIO[0] <= r <= AREA_RATIO[1]):
            continue
        dx.append(pb[k, 0] - pa[i, 0])
        dy.append(pb[k, 1] - pa[i, 1])
    if len(dx) < 30:
        return None, None, len(dx)
    return st.median(dx), st.median(dy), len(dx)


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (n * sx * sy)


def build(reference="2021"):
    import numpy as np
    if not STACK.exists():
        return None, None, f"{STACK} not found (local mirror)"
    d = np.load(STACK)
    stack, inside, tf = d["stack"], d["inside"], d["transform"]
    years = [str(y) for y in d["years"]]
    if reference not in years:
        return None, None, f"reference {reference} not in {years}"

    coreg = {r["label"]: r for r in _rows(QC / "coregistration.csv")}
    cuts = {r["year"]: r for r in _rows(QC / "trend8_policy_cuts.csv")}

    lm = {y: landmarks(stack[i] == 1, inside, tf) for i, y in enumerate(years)}
    ri = years.index(reference)
    pr, ar = lm[reference]

    rows = []
    for i, y in enumerate(years):
        if y == reference:
            continue
        pa, aa = lm[y]
        dx, dy, nm = estimate_shift(pa, aa, pr, ar)
        cy, cr = coreg.get(y), coreg.get(reference)
        exp_dx = exp_dy = None
        if cy and cr:
            exp_dx = float(cr["median_dx_m"]) - float(cy["median_dx_m"])
            exp_dy = float(cr["median_dy_m"]) - float(cy["median_dy_m"])
        rows.append({
            "epoch": y, "reference": reference,
            "n_landmarks": len(pa), "n_matched": nm,
            "est_dx_m": None if dx is None else round(dx, 3),
            "est_dy_m": None if dy is None else round(dy, 3),
            "expected_dx_m": None if exp_dx is None else round(exp_dx, 3),
            "expected_dy_m": None if exp_dy is None else round(exp_dy, 3),
            "p68_mag_m": cy["p68_mag_m"] if cy else "",
            "recall_at_cut": cuts[y]["recall"] if y in cuts else "",
        })

    good = [r for r in rows if r["est_dx_m"] is not None
            and r["expected_dx_m"] is not None and r["recall_at_cut"]]
    stats = {}
    if len(good) >= 3:
        # SIGN CONVENTION, resolved EMPIRICALLY and declared rather than assumed.
        # coregistration.phase_shift works in ARRAY coordinates — dy runs down the rows
        # while map y runs up — and its docstring's a/b direction cannot be confirmed from
        # the docstring alone. Rather than pick a convention and hope, each axis is fitted
        # for its own sign and the choice is REPORTED in the output.
        #
        # This is legitimate here for exactly one reason: a sign is one bit per axis, and
        # the evidence being weighed is MAGNITUDE agreement across seven epochs, which no
        # choice of sign can manufacture. If the estimator were measuring sensitivity
        # rather than geometry, no sign flip would make 2024 read 1.00 m against a
        # measured 0.96 m while 2019 reads 0.02 m against 0.01 m.
        for axis in ("dx", "dy"):
            e = [r[f"est_{axis}_m"] for r in good]
            x = [r[f"expected_{axis}_m"] for r in good]
            r_pos, r_neg = pearson(e, x), pearson([-v for v in e], x)
            sign = 1 if (r_pos if r_pos is not None else -9) >= \
                        (r_neg if r_neg is not None else -9) else -1
            stats[f"sign_{axis}"] = sign
            stats[f"r_{axis}"] = max(r_pos if r_pos is not None else -9,
                                     r_neg if r_neg is not None else -9)
            for r in good:
                r[f"est_{axis}_m_aligned"] = round(sign * r[f"est_{axis}_m"], 3)

        est = ([r["est_dx_m_aligned"] for r in good]
               + [r["est_dy_m_aligned"] for r in good])
        exp = ([r["expected_dx_m"] for r in good]
               + [r["expected_dy_m"] for r in good])
        stats["r_est_vs_expected"] = pearson(est, exp)
        stats["median_abs_err_m"] = st.median([abs(a - b) for a, b in zip(est, exp)])

        # THE CONTAMINATION TEST, and it is sign-independent. If the estimator absorbs
        # sensitivity the way the block layer did, then what it gets WRONG — the residual
        # left after measured registration is accounted for — tracks recall. That is the
        # axis the block layer should have been judged on and was not.
        resid = [((r["est_dx_m_aligned"] - r["expected_dx_m"]) ** 2
                  + (r["est_dy_m_aligned"] - r["expected_dy_m"]) ** 2) ** 0.5
                 for r in good]
        rec = [float(r["recall_at_cut"]) for r in good]
        stats["r_residual_vs_recall"] = pearson(resid, rec)
        stats["r_residual_vs_p68"] = pearson(resid, [float(r["p68_mag_m"]) for r in good])

        # EXACT permutation null, and the null is given the SAME freedom the estimate
        # took. Two sign bits were fitted from this data, so a naive permutation would be
        # anticonservative; every shuffled world therefore refits its own signs too, and
        # the p-value prices in the fitting. All 7! = 5,040 relabellings of the epochs.
        import itertools
        obs = stats["r_est_vs_expected"]
        ex, ey = ([r["est_dx_m"] for r in good], [r["est_dy_m"] for r in good])
        xx, xy = ([r["expected_dx_m"] for r in good],
                  [r["expected_dy_m"] for r in good])

        def best_r(perm):
            px = [ex[i] for i in perm]
            py = [ey[i] for i in perm]
            out = []
            for e, x in ((px, xx), (py, xy)):
                rp, rn = pearson(e, x), pearson([-v for v in e], x)
                s = 1 if (rp if rp is not None else -9) >= \
                         (rn if rn is not None else -9) else -1
                out.append([s * v for v in e])
            return pearson(out[0] + out[1], xx + xy)

        hits = tot = 0
        for perm in itertools.permutations(range(len(good))):
            r = best_r(perm)
            tot += 1
            if r is not None and r >= obs - 1e-12:
                hits += 1
        stats["permutation_p"] = hits / tot
        stats["permutation_n"] = tot
    return rows, stats, None


def main(argv=None):
    from phase4seg.names import clean_argv
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference", default="2021")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(clean_argv() if argv is None else argv)

    rows, stats, err = build(a.reference)
    if err:
        print(f"FATAL: {err}")
        return 2

    cols = ["epoch", "reference", "n_landmarks", "n_matched", "est_dx_m", "est_dy_m",
            "expected_dx_m", "expected_dy_m", "p68_mag_m", "recall_at_cut"]
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    for k, v in stats.items():
        buf.write(f"# {k},{'' if v is None else round(v, 4)}\n")
    if not a.dry_run:
        (QC / "landmark_transform_gate.csv").write_text(buf.getvalue(),
                                                        encoding="utf-8", newline="")

    print(f"{'DRY RUN: ' if a.dry_run else ''}phase4/qc/landmark_transform_gate.csv "
          f"(reference {a.reference})")
    print(f"\n{'epoch':7}{'landmarks':>11}{'matched':>9}{'est dx,dy (m)':>18}"
          f"{'expected dx,dy':>18}{'recall':>9}")
    for r in rows:
        e = (f"{r['est_dx_m']:+.2f},{r['est_dy_m']:+.2f}"
             if r["est_dx_m"] is not None else "—")
        x = (f"{r['expected_dx_m']:+.2f},{r['expected_dy_m']:+.2f}"
             if r["expected_dx_m"] is not None else "—")
        print(f"{r['epoch']:7}{r['n_landmarks']:>11,}{r['n_matched']:>9,}{e:>18}{x:>18}"
              f"{r['recall_at_cut']:>9}")

    print("\nTHE GATE")
    print(f"  axis sign resolved EMPIRICALLY and declared: dx {stats.get('sign_dx'):+d}, "
          f"dy {stats.get('sign_dy'):+d}")
    print( "     (array-vs-map conventions; a sign is one bit, the magnitudes are the evidence)")
    rv = stats.get("r_est_vs_expected")
    rres = stats.get("r_residual_vs_recall")
    print(f"  r(estimated shift, MEASURED registration) = "
          f"{'n/a' if rv is None else format(rv, '+.3f')}   <- must be POSITIVE and strong")
    print(f"     per axis: dx {stats.get('r_dx', float('nan')):+.3f}   "
          f"dy {stats.get('r_dy', float('nan')):+.3f}")
    print(f"  median |error| vs measured                = "
          f"{stats.get('median_abs_err_m', float('nan')):.3f} m")
    print(f"  r(RESIDUAL, recall)                       = "
          f"{'n/a' if rres is None else format(rres, '+.3f')}   <- THE contamination test")
    print(f"  r(residual, p68 scatter)                  = "
          f"{stats.get('r_residual_vs_p68', float('nan')):+.3f}")
    print(f"  exact permutation p                       = "
          f"{stats.get('permutation_p', float('nan')):.5f}   over all "
          f"{stats.get('permutation_n', 0):,} relabellings, each refitting its own signs")
    print( "  [the falsified BLOCK layer: r=-0.245 vs p68 (wrong sign), -0.450 vs recall]")
    if rv is not None:
        ok = rv > 0.5 and (rres is None or abs(rres) < 0.5)
        print("\n  VERDICT: " + ("PASS — tracks geometry; the residual does not track "
                                 "sensitivity" if ok else "FAIL — see above"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
